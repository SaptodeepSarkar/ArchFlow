"""Validate shipped Voice Core contracts without Blender or Android dependencies.

Run `python tools/verify_voice_core.py --media` to check editorial deliverables too.
This checks artifact structure; it does not claim Filament/device compatibility.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "android/app/src/main/assets/models/vaani_voice_core.glb"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_model(path=MODEL):
    data = path.read_bytes()
    require(len(data) >= 20, "GLB header truncated")
    magic, version, length = struct.unpack_from("<4sII", data)
    require(magic == b"glTF" and version == 2, "Expected glTF 2 binary")
    require(length == len(data), "GLB length mismatch")
    require(length < 100_000, "Voice Core exceeds 100KB asset budget")
    chunks = {}
    offset = 12
    while offset < length:
        size, kind = struct.unpack_from("<I4s", data, offset)
        require(size % 4 == 0 and offset + 8 + size <= length, "Invalid GLB chunk")
        chunks[kind] = data[offset + 8:offset + 8 + size]
        offset += 8 + size
    doc = json.loads(chunks[b"JSON"])
    require(b"BIN\0" in chunks, "Missing embedded buffer")
    require(not any("uri" in b for b in doc["buffers"]), "External buffers prohibited")
    require(not doc.get("images"), "This asset contract uses zero textures")
    require(not doc.get("cameras"), "Runtime camera must not come from asset")
    require("KHR_draco_mesh_compression" in doc.get("extensionsRequired", []), "Missing Draco compression")
    names = {node.get("name") for node in doc["nodes"]}
    require({"VoiceCore", "VoiceRibbon1", "VoiceRibbon2", "VoiceRibbon3"} <= names,
            "Named core/ribbon objects missing")
    triangles = 0
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            require(primitive.get("mode", 4) == 4, "Only triangle geometry allowed")
            count = doc["accessors"][primitive["indices"]]["count"]
            require(count % 3 == 0, "Malformed triangle indices")
            triangles += count // 3
            require("KHR_draco_mesh_compression" in primitive.get("extensions", {}), "Uncompressed mesh")
    require(0 < triangles < 10_000, "Triangle budget exceeded")
    expected = {"intro": .6, "idle": 6., "listen": 1., "process": 1.5, "success": .45}
    animations = doc["animations"]
    require(len(animations) == len(expected), "Unexpected clip count")
    require({a["name"] for a in animations} == set(expected), "Clip names changed")
    for animation in animations:
        require(len({c["target"]["node"] for c in animation["channels"]}) == 4,
                "Every clip must animate all four objects")
        for sampler in animation["samplers"]:
            times = doc["accessors"][sampler["input"]]
            require(abs(times["min"][0]) < .0001, "Clip must start at zero")
            require(abs(times["max"][0] - expected[animation["name"]]) < .0001,
                    f"Wrong duration: {animation['name']}")
    require(any("emissiveFactor" in material for material in doc["materials"]), "No amber emission")
    print(f"PASS model: {length:,} bytes, {triangles:,} triangles, 5 correctly timed clips, zero textures")


def verify_media():
    directory = ROOT / "android/brand/voice-core"
    for name in ("vaani_voice_core.blend", "vaani_voice_core_studio.blend"):
        require((directory / name).read_bytes()[:7] == b"BLENDER", f"Invalid editable scene: {name}")
    for name in ("poster", "privacy", "listening", "writing"):
        path = directory / "renders" / f"voice_core_{name}.png"
        data = path.read_bytes()
        require(data[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG: {name}")
        require(struct.unpack_from(">II", data, 16) == (512, 512), f"Wrong dimensions: {name}")
    video = directory / "renders/voice_core_loop.mp4"
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video),
    ], text=True))
    streams = metadata["streams"]
    require(len(streams) == 1 and streams[0]["codec_type"] == "video", "Loop must be silent")
    require(streams[0]["width"] == 384 and streams[0]["height"] == 384, "Wrong loop dimensions")
    require(4 <= float(metadata["format"]["duration"]) <= 6, "Loop must last 4–6 seconds")
    require(video.stat().st_size < 1_000_000, "Loop exceeds 1MB budget")
    print(f"PASS media: editable Blender scenes, 3 editorial illustrations, poster, silent loop ({video.stat().st_size:,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media", action="store_true")
    args = parser.parse_args()
    verify_model()
    if args.media:
        verify_media()
