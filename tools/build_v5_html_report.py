#!/usr/bin/env python3
"""Build a local, self-contained V5 STT/LLM audit HTML report."""
from __future__ import annotations
import argparse, html, json
from pathlib import Path

def load(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stt',action='append',default=[]); ap.add_argument('--llm',action='append',default=[]); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    stt=[]
    for p in a.stt:
        for r in load(p):
            stt.append((Path(p).name,r))
    llm=[]
    for p in a.llm:
        for r in load(p): llm.append((Path(p).name,r))
    def cell(x): return html.escape(str(x if x is not None else ''))
    body=['<!doctype html><meta charset="utf-8"><title>Vaani V5 audit</title><style>body{font:14px system-ui;margin:2rem;background:#f7f7f7}section{background:white;padding:1rem;margin:1rem 0;border-radius:8px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.45rem;text-align:left;vertical-align:top}audio{max-width:280px}.bad{background:#fff0f0}.good{background:#effff0}pre{white-space:pre-wrap}</style><h1>Vaani V5 STT + LLM audit</h1>']
    body.append(f'<section><h2>STT cases ({len(stt)})</h2><table><tr><th>Run</th><th>Audio</th><th>Reference</th><th>Raw STT</th><th>WER</th><th>Errors</th></tr>')
    for run,r in stt:
        audio=r.get('audio_path',''); href=html.escape(Path(audio).as_uri()) if audio else ''
        cls='good' if not r.get('normalized_errors') else 'bad'
        player=f'<audio controls src="{href}"></audio><br>{cell(audio)}' if audio else 'Not included in audit'
        body.append(f'<tr class="{cls}"><td>{cell(run)}</td><td>{player}</td><td>{cell(r.get("reference"))}</td><td>{cell(r.get("hypothesis"))}</td><td>{cell(r.get("normalized_wer"))}</td><td><pre>{cell(r.get("errors"))}</pre></td></tr>')
    body.append('</table></section>')
    body.append(f'<section><h2>LLM cases ({len(llm)})</h2><table><tr><th>Run</th><th>Input</th><th>Expected</th><th>Generated</th><th>Exact</th><th>Valid</th></tr>')
    for run,r in llm:
        cls='good' if r.get('exact') else 'bad'
        body.append(f'<tr class="{cls}"><td>{cell(run)}</td><td>{cell(r.get("input"))}</td><td><pre>{cell(r.get("expected"))}</pre></td><td><pre>{cell(r.get("generated"))}</pre></td><td>{cell(r.get("exact"))}</td><td>{cell(r.get("valid"))}</td></tr>')
    body.append('</table></section>')
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(''.join(body),encoding='utf-8'); print(a.out)
if __name__=='__main__': main()
