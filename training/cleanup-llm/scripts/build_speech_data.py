#!/usr/bin/env python3
"""Stage 3 (speech): synthetic transcript->clean pairs -> data/sft_speech.jsonl.

Mirrors Vaani's deterministic polish (fillers, false starts, duplicates) and
extends it where judgment is needed: punctuation, capitalization, lists and
points, spelling of common homophones. Deterministic 95/5 train/holdout
split. Synthetic by construction: every pair is hand-specified below, so no
fact can leak in from the wild.
"""
import json
import os
import random

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

SYSTEM = (
    "You are a conservative transcription editor. Fix ONLY grammar, "
    "punctuation, capitalization, and obvious filler words. Preserve meaning, "
    "negation, numbers, names, units, code, paths, and the original language. "
    "When the speaker enumerates items, format them as a short list, one per "
    "line starting with '- '. Do not add facts, do not rephrase claims, do "
    "not translate. If unsure, return the input unchanged."
)

# (raw transcript, cleaned) — covers fillers, false starts, duplicates,
# punctuation, capitalization, homophones, lists/points, light emotion cues.
PAIRS = [
    ("uh i went to the store um yesterday", "I went to the store yesterday."),
    ("so i'm sorry for last night i was trying to be nice", "So, I'm sorry for last night. I was trying to be nice."),
    ("i can't i can't move oh sorry", "I can't move. Oh, sorry."),
    ("genuine genuinely sorry about that", "Genuinely sorry about that."),
    ("i need milk eggs bread and butter", "I need:\n- milk\n- eggs\n- bread\n- butter"),
    ("first finish the report then call vishal and then book the tickets", "First finish the report, then call Vishal, and then book the tickets."),
    ("their going to come they're house over there", "They're going to come to their house over there."),
    ("its a beautiful day isn't it", "It's a beautiful day, isn't it?"),
    ("i was so happy i mean really really happy", "I was so happy — I mean really, really happy!"),
    ("no no don't go there", "No, no, don't go there."),
    ("the meeting is on monday at ten a m", "The meeting is on Monday at 10 a.m."),
    ("can you send me the file the presentation file", "Can you send me the file, the presentation file?"),
    ("wow that is amazing oh my god", "Wow, that is amazing! Oh my God!"),
    ("i think that he is kind of a mischievous person", "I think that he is kind of a mischievous person."),
    ("we need three things courage patience and honesty", "We need three things:\n- courage\n- patience\n- honesty"),
    ("hello i don't give a fuck bro", "Hello, I don't give a fuck, bro."),
    ("remind me to call mom buy groceries and pay rent", "Remind me to:\n- call mom\n- buy groceries\n- pay rent"),
    ("it was very very good", "It was very, very good."),
    ("where are you going are you coming", "Where are you going? Are you coming?"),
    ("i will defiantly be their tomorrow", "I will definitely be there tomorrow."),
]


def main() -> None:
    rows = [
        {"instruction": SYSTEM, "input": raw, "output": clean, "source": "synthetic:speech"}
        for raw, clean in PAIRS
    ]
    random.Random(7).shuffle(rows)
    cut = max(1, int(len(rows) * 0.95))
    with open(os.path.join(DATA, "sft_speech.jsonl"), "w") as f:
        for r in rows[:cut]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "eval_speech.jsonl"), "w") as f:
        for r in rows[cut:]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"speech pairs: train={cut} holdout={len(rows) - cut}")


main()
