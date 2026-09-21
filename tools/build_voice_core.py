"""Original Vaani asset. Run with Blender 4.5: blender -b -t 1 --python tools/build_voice_core.py.

No downloaded geometry or textures. MIT, like the application. The exported
clips use NLA track names so all four objects animate as one glTF clip.
"""
from pathlib import Path
import math
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "android/app/src/main/assets/models/vaani_voice_core.glb"
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.fps = 60


def material(name, color, metallic, roughness, emission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Emission Color"].default_value = (*color, 1)
    shader.inputs["Emission Strength"].default_value = emission
    return mat


obsidian = material("Obsidian", (.025, .044, .035), .45, .42)
amber = material("Amber energy", (.88, .39, .075), .35, .36, .65)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
core = bpy.context.object
core.name = "VoiceCore"
for vertex in core.data.vertices:
    x, y, z = vertex.co
    # An asymmetric, gently fluted stone, with no spherical icon silhouette.
    radius = 1 + .06 * math.sin(z * 3 + x * 2) + .035 * math.cos(y * 5)
    vertex.co = (x * radius * .88, y * radius * .78, z * radius)
core.data.materials.append(obsidian)
objects = [core]
for index in range(3):
    vertices, faces = [], []
    for segment in range(97):
        angle = segment / 96 * math.tau
        radius = 1.035 + .04 * math.sin(angle * 3 + index)
        z = .24 * math.sin(angle * 2 + index * 1.8) + (index - 1) * .43
        for side in (-1, 1):
            vertices.append((radius * math.cos(angle) * .91,
                             radius * math.sin(angle) * .82, z + side * .025))
        if segment:
            a = (segment - 1) * 2
            faces.append((a, a + 1, a + 3, a + 2))
    mesh = bpy.data.meshes.new(f"RibbonMesh{index}")
    mesh.from_pydata(vertices, [], faces)
    ribbon = bpy.data.objects.new(f"VoiceRibbon{index + 1}", mesh)
    scene.collection.objects.link(ribbon)
    ribbon.data.materials.append(amber)
    # Thin solid ribbons remain visible from both sides, without transparency.
    bpy.context.view_layer.objects.active = ribbon
    solid = ribbon.modifiers.new("Ribbon thickness", "SOLIDIFY")
    solid.thickness = .012
    bpy.ops.object.modifier_apply(modifier=solid.name)
    objects.append(ribbon)

clips = {
    "intro": [(0, .84, -.06), (36, 1, 0)],
    "idle": [(0, 1, 0), (180, 1.012, .008), (360, 1, 0)],
    "listen": [(0, 1, 0), (30, 1.025, .025), (60, 1, 0)],
    "process": [(0, 1, 0), (45, .955, -.035), (90, 1, 0)],
    "success": [(0, 1, 0), (10, 1.075, .01), (27, 1, 0)],
}
for obj in objects:
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.animation_data_create()
    for name, keys in clips.items():
        action = bpy.data.actions.new(f"{obj.name}_{name}")
        obj.animation_data.action = action
        for frame, scale, shift in keys:
            obj.scale = (scale, scale, scale)
            obj.location.z = shift
            obj.keyframe_insert("scale", frame=frame)
            obj.keyframe_insert("location", frame=frame)
        track = obj.animation_data.nla_tracks.new()
        track.name = name
        track.strips.new(action.name, 0, action)
        obj.animation_data.action = None
    obj.scale = (1, 1, 1)
    obj.location.z = 0

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(OUTPUT), export_format="GLB", use_selection=False,
    export_animations=True, export_animation_mode="NLA_TRACKS",
    export_nla_strips=True, export_frame_range=False,
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6,
    export_cameras=False, export_lights=False,
)
triangles = sum(len(p.vertices) - 2 for obj in objects for p in obj.data.polygons)
assert triangles < 10000, triangles
print(f"Voice Core: {triangles} triangles, {OUTPUT.stat().st_size} bytes, zero textures")

# The editable source is kept outside Android assets so it never inflates the APK.
SOURCE = ROOT / "android/brand/voice-core"
SOURCE.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "vaani_voice_core.blend"))

if "--media" in sys.argv:
    from mathutils import Vector
    media = SOURCE / "renders"
    media.mkdir(parents=True, exist_ok=True)
    for obj in objects:
        for track in obj.animation_data.nla_tracks:
            track.mute = True
        obj.scale = (1, 1, 1)
        obj.location.z = 0
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.035, .065, .045, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .5
    scene.view_settings.view_transform = "AgX"
    bpy.ops.object.camera_add(location=(3.5, -6.5, 2.7))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4.4
    scene.camera = camera
    for name, location, energy, color, size in [
        ("Ivory key", (-3, -4, 5), 550, (1, .85, .65), 4),
        ("Forest fill", (3, 2, 1), 420, (.5, .75, .6), 3),
        ("Amber rim", (-2, 3, 3), 650, (1, .48, .15), 2),
    ]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy, light.data.color, light.data.shape, light.data.size = energy, color, "DISK", size
        light.rotation_euler = (-light.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -1.3))
    bpy.context.object.data.materials.append(material("Forest backdrop", (.009, .022, .014), 0, .9))

    def render(name):
        scene.render.filepath = str(media / name)
        bpy.ops.render.render(write_still=True)

    render("voice_core_poster.png")
    props = []
    # Privacy: an open protective cradle, never a lock implying encryption guarantees.
    for z, radius in [(-.95, 1.4), (-1.09, 1.53)]:
        bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=.035,
                                       major_segments=64, minor_segments=8, location=(0, 0, z))
        prop = bpy.context.object
        prop.data.materials.append(obsidian)
        props.append(prop)
    render("voice_core_privacy.png")
    for prop in props:
        prop.hide_render = True
    props = []
    # Listening: amplitude is represented in editorial art, never passed as live data.
    for i, height in enumerate([.14, .28, .5, .74, .43, .25, .12]):
        bpy.ops.mesh.primitive_cube_add(size=1, location=((i - 3) * .18, -1.05, -.95 + height / 2))
        prop = bpy.context.object
        prop.scale = (.055, .055, height)
        prop.data.materials.append(amber)
        props.append(prop)
    render("voice_core_listening.png")
    for prop in props:
        prop.hide_render = True
    props = []
    # Writing: a quiet writing plane with orderly strokes, no baked-in language.
    for i, width in enumerate([1.25, .94, .62]):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1.02, -.7 - i * .14))
        prop = bpy.context.object
        prop.scale = (width, .045, .035)
        prop.data.materials.append(amber)
        props.append(prop)
    render("voice_core_writing.png")
    for prop in props:
        prop.hide_render = True
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "vaani_voice_core_studio.blend"))

    if "--video" in sys.argv:
        frames = media / "frames"
        frames.mkdir(exist_ok=True)
        scene.render.resolution_x = scene.render.resolution_y = 384
        scene.cycles.samples = 8
        for frame in range(120):
            t = frame / 24
            # Ends at precisely the resting pose for a seamless 5-second loop.
            energy = (math.sin((t - 1) * math.pi) ** 2 * .035 if 1 <= t < 2
                      else -math.sin((t - 2) * math.pi / 1.4) ** 2 * .045 if 2 <= t < 3.4
                      else math.sin((t - 3.4) * math.pi / .45) ** 2 * .075 if 3.4 <= t < 3.85
                      else 0)
            for obj in objects:
                obj.scale = (1 + energy,) * 3
            render(f"frames/{frame:04d}.png")
