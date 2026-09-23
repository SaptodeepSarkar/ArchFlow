#!/usr/bin/env python3
"""Build review-required synthetic V6 candidates; never label them real data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CASES = [
    ("explicit_repair", "open firefox no wait open zen", "Open Zen.", "repair-firefox-zen"),
    ("reasoning_keep", "i opened firefox but no sorry i should explain zen behaves differently", "I opened Firefox, but no, sorry, I should explain: Zen behaves differently.", "repair-firefox-zen"),
    ("explicit_repair", "schedule it friday sorry monday", "Schedule it Monday.", "repair-friday-monday"),
    ("reasoning_keep", "i initially said friday but sorry monday is not possible either", "I initially said Friday, but sorry, Monday is not possible either.", "repair-friday-monday"),
    ("accidental_repetition", "i i think this works", "I think this works.", "repeat-think"),
    ("intentional_repetition", "i really really think this works", "I really, really think this works.", "repeat-think"),
    ("filler", "um send the report", "Send the report.", "filler-send"),
    ("metalinguistic_keep", "the word um belongs in the quote", "The word “um” belongs in the quote.", "filler-send"),
    ("uncertainty_keep", "tell her ill probably come around seven actually i dont know yet just tell her ill come", "Tell her I’ll probably come around seven… actually, I don’t know yet. Just tell her I’ll come.", "uncertainty-arrival"),
    ("reasoning_keep", "i was going to tell her id come around seven but actually i dont know yet so ill just tell her ill come", "I was going to tell her I’d come around seven, but actually I don’t know yet, so I’ll just tell her I’ll come.", "uncertainty-arrival"),
    ("factual_claim_keep", "python is statically typed", "Python is statically typed.", "python-claim"),
    ("explicit_repair", "python is statically typed sorry i mean dynamically typed", "Python is dynamically typed.", "python-claim"),
    ("prose_not_list", "i bought eggs milk bread and coffee", "I bought eggs, milk, bread, and coffee.", "shopping-list"),
    ("explicit_list", "make a shopping list with eggs milk bread and coffee", "Shopping list:\n1. Eggs\n2. Milk\n3. Bread\n4. Coffee", "shopping-list"),
    ("list_termination", "thats the shopping list i also need to call mom tomorrow", "That’s the shopping list. I also need to call Mom tomorrow.", "shopping-list-end"),
    ("heading", "add the heading release checklist then test package and publish", "Release checklist\n\n- Test\n- Package\n- Publish", "format-heading"),
    ("table", "make a table with name status vaani ready and cozy testing", "| Name | Status |\n| --- | --- |\n| Vaani | Ready |\n| Cozy | Testing |", "format-table"),
    ("quoted_speech", "he said quote uh i dont know end quote", "He said, “Uh, I don’t know.”", "quoted-uh"),
    ("command_as_content", "the command rm dash rf is dangerous", "The command `rm -rf` is dangerous.", "quoted-command"),
    ("url", "the url is https colon slash slash example dot com slash api", "The URL is https://example.com/api.", "technical-url"),
    ("acronym", "the u r l uses h t t p s", "The URL uses HTTPS.", "technical-url"),
    ("path", "the config is at slash etc slash vaani slash config dot toml", "The config is at `/etc/vaani/config.toml`.", "technical-path"),
    ("technical", "hyper land uses wayland", "Hyprland uses Wayland.", "technical-hyprland"),
    ("hinglish", "kal meeting ke baad i will send the PR", "Kal meeting ke baad I will send the PR.", "hinglish-pr"),
    ("anger", "this build is so damn broken", "This build is so damn broken.", "style-anger"),
    ("affection", "i love you so much", "I love you so much.", "style-affection"),
    ("already_correct", "the api returned 404", "The API returned 404.", "pass-through-api"),
    ("ambiguous_keep", "actually i think we should keep the old plan", "Actually, I think we should keep the old plan.", "actually-content"),
    ("contraction", "i cant join today", "I can’t join today.", "contraction-cant"),
    ("capitalization", "my name is aditi", "My name is Aditi.", "capitalization-aditi"),
    ("punctuation", "if the test passes ship it", "If the test passes, ship it.", "punctuation-ship"),
    ("implicit_repair", "we need whisper medium because actually parakeet might be better because its faster", "Parakeet might be better than Whisper Medium because it’s faster.", "implicit-whisper-parakeet"),
    ("reasoning_keep", "we need whisper medium because actually i want to compare it with parakeet because its faster", "We need Whisper Medium because, actually, I want to compare it with Parakeet because it’s faster.", "implicit-whisper-parakeet"),
    ("false_start", "i was going to email the report no wait ill send the link", "I’ll send the link.", "false-start-email"),
    ("abandoned_thought_keep", "i was going to email the report but the attachment is too big so ill send the link", "I was going to email the report, but the attachment is too big, so I’ll send the link.", "false-start-email"),
    ("hesitation_keep", "well i guess we could maybe try again tomorrow", "Well, I guess we could maybe try again tomorrow.", "hesitation-tomorrow"),
    ("spoken_letters", "spell vaani v a a n i", "Spell Vaani: V-A-A-N-I.", "spoken-vaani"),
    ("software_package", "install python dash faster whisper version one point one", "Install `python-faster-whisper` version 1.1.", "package-faster-whisper"),
    ("code_switching", "mujhe lagta hai the build kal ready hoga", "Mujhe lagta hai the build kal ready hoga.", "hinglish-build"),
    ("casual_style", "yeah nah that sounds kinda weird", "Yeah, nah, that sounds kinda weird.", "style-casual"),
    ("swearing_keep", "what the hell is this error", "What the hell is this error?", "style-swearing"),
    ("bullets", "make bullet points for test package publish", "- Test\n- Package\n- Publish", "format-bullets"),
    ("numbered_list", "make a numbered list first test second package third publish", "1. Test\n2. Package\n3. Publish", "format-numbered"),
    ("paragraph_request", "make two paragraphs first the build passed second deployment starts tonight", "The build passed.\n\nDeployment starts tonight.", "format-paragraphs"),
    ("list_continuation", "continue the list with coffee", "- Coffee", "format-list-continuation"),
    ("quoted_command", "she said open zen not open firefox", "She said, “Open Zen,” not “Open Firefox.”", "quoted-open-zen"),
    ("do_not_edit", "no no leave the old config alone", "No, no, leave the old config alone.", "intentional-no-no"),
    ("accidental_repetition", "genuine genuinely i forgot the key", "Genuinely, I forgot the key.", "repeat-genuine"),
]


def row(index: int, label: str, raw: str, target: str, group: str) -> dict:
    return {
        "schema_version": "vaani.v6.formatter-example/2",
        "example_id": f"v6-seed-{index:04d}",
        "source": {"name": "v6-foundation-seed", "record_id": f"seed-{index:04d}", "type": "synthetic"},
        "provenance": {"license_ref": "organization-authored", "transformation_history": ["hand-authored semantic contrast seed"]},
        "utterance": {"raw_stt": raw, "reference_transcript": None, "clean_target": target},
        "stt": {"backend": None, "model": None, "final": True, "words": []},
        "labels": [label, "meaning_preservation"],
        "language": {"primary": "hi-Latn" if label == "hinglish" else "en", "code_switching": label == "hinglish", "accent_or_domain": "synthetic"},
        "annotation": {"method": "hand-authored", "review_status": "needs_human_review", "reviewer": None},
        "split": None, "group_id": group, "audio": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = [row(index, *case) for index, case in enumerate(CASES, 1)]
    args.out.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
    print(json.dumps({"synthetic_candidates": len(rows), "review_status": "needs_human_review", "out": str(args.out)}))


if __name__ == "__main__":
    main()
