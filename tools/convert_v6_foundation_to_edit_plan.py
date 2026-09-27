#!/usr/bin/env python3
"""Conservatively convert approved foundation rows to the V6 edit-plan control format."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from import_v6_grounded_corpus import grounded_labels, make_row

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", type=Path, nargs="+", required=True); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    rows=[]; rejected=0; seen=set()
    for path in args.inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            r=json.loads(line)
            if r.get("annotation",{}).get("review_status") != "approved": rejected += 1; continue
            source=r["utterance"]["raw_stt"].strip(); target=r["utterance"]["clean_target"].strip()
            if not source or not target or source.casefold() in seen: rejected += 1; continue
            labels=grounded_labels(source,target)
            if labels is None: rejected += 1; continue
            out=make_row(len(rows)+1,source,target,labels, r.get("provenance",{}).get("source", path.stem))
            if out is None: rejected += 1; continue
            out["id"] = r["example_id"]
            out["metadata"].update({"base_id": r.get("group_id", r["example_id"]), "foundation_example_id": r["example_id"], "reviewer": r["annotation"].get("reviewer")})
            rows.append(out); seen.add(source.casefold())
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in rows), encoding="utf-8")
    print(json.dumps({"accepted":len(rows),"rejected":rejected,"out":str(args.out)}))
if __name__ == "__main__": main()
