#!/usr/bin/env python3
"""Freeze agent-authored final diagnostics; never call these human gold labels."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

# Authored after the short-filler candidate started. Do not use these examples
# for replay, checkpoint selection, or tuning that candidate.
CASES = [
    ("uh the parcel arrived", "The parcel arrived.", "incidental_filler"),
    ("she literally said uh before answering", "She literally said \"uh\" before answering.", "quoted_filler"),
    ("the word um appears twice", "The word \"um\" appears twice.", "metalinguistic"),
    ("i i forgot the receipt", "I forgot the receipt.", "accidental_repeat"),
    ("no no that is my receipt", "No, no, that is my receipt.", "intentional_repeat"),
    ("it was very very expensive", "It was very, very expensive.", "intentional_repeat"),
    ("reserve room eight sorry room nine", "Reserve room nine.", "explicit_repair"),
    ("she said sorry after reserving room eight", "She said sorry after reserving room eight.", "repair_negative"),
    ("choose the blue cable no wait choose the green cable", "Choose the green cable.", "explicit_repair"),
    ("he told me no wait is what the sign says", "He told me \"no wait\" is what the sign says.", "quotation"),
    ("i might attend but i have not decided", "I might attend, but I have not decided.", "uncertainty"),
    ("i planned to attend but now i am unsure so i will ask tomorrow", "I planned to attend, but now I am unsure, so I will ask tomorrow.", "reasoning"),
    ("i was going to say yes actually i am still confused", "I was going to say yes... actually, I am still confused.", "uncertainty"),
    ("i need soap rice and towels", "I need soap, rice, and towels.", "no_unsolicited_list"),
    ("make a shopping list soap rice and towels", "- Soap\n- Rice\n- Towels", "requested_list"),
    ("make a list first check the latch second close the gate end the list i will call later", "1. Check the latch\n2. Close the gate\n\nI will call later.", "list_termination"),
    ("the manual says erase the disk but do not do that", "The manual says \"erase the disk\", but do not do that.", "command_as_data"),
    ("this is fucking ridiculous and i want an explanation", "This is fucking ridiculous, and I want an explanation.", "emotion"),
    ("i miss you so much sweetheart", "I miss you so much, sweetheart.", "affection"),
    ("haan i will check kal but do not change the plan", "Haan, I will check kal, but do not change the plan.", "code_switching"),
    ("the release is 7.4 not 7.5", "The release is 7.4, not 7.5.", "protected_number"),
    ("the release is 7.4 sorry it is 7.5", "The release is 7.5.", "numeric_repair"),
    ("ruby is statically typed", "Ruby is statically typed.", "no_fact_check"),
    ("ruby is statically typed sorry dynamically typed", "Ruby is dynamically typed.", "explicit_repair"),
    ("Keep this exactly as written.", "Keep this exactly as written.", "already_correct"),
    ("please keep the setting disabled", "Please keep the setting disabled.", "negation"),
    ("i did not say enable the setting", "I did not say enable the setting.", "negation"),
    ("what does r t f mean here", "What does RTF mean here?", "spoken_acronym"),
]


def normalized_source(value):
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def freeze(manifest, out):
    if out.exists():
        raise SystemExit("refusing to overwrite frozen suite")
    source_manifest = json.loads(manifest.read_text())
    inputs = source_manifest["inputs"]
    for group in inputs.values():
        for item in group:
            if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                raise SystemExit("run input checksum changed; no artifacts written")
    paths = {Path(item["path"]) for group in inputs.values() for item in group}
    seen = set()
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            source = (row["utterance"]["raw_stt"] if "utterance" in row else
                      row.get("source", " ".join(row.get("source_tokens", []))))
            seen.add(normalized_source(source))
    rows = []
    for index, (source, target, category) in enumerate(CASES):
        if normalized_source(source) in seen:
            raise SystemExit("final contrast overlaps a run input; no artifacts written")
        rows.append({"id": f"v6-final-contrast-20261004-{index:03d}",
                     "source": source, "target_text": target,
                     "metadata": {"categories": [category],
                                  "label_source": "agent-authored synthetic diagnostic",
                                  "human_reviewed": False,
                                  "usage": "evaluation-only, not candidate selection"}})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        stream.write("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"rows": len(rows), "normalized_source_overlap": 0,
                      "checked_input_files": len(paths),
                      "suite_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                      "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                      "human_reviewed": False}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    freeze(args.run_manifest, args.out)
