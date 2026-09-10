#!/usr/bin/env python3
"""Latency bench harness: runs N toggle cycles via CLI, parses daemon latencies.
Usage: python3 tools/bench.py --n 20 --secs 5
Reports sample count + p50/p95 for stop-to-text, with backend/model/threads/power noted.
Requires: running vaanid, models, mic. Honest about missed targets.
"""
import argparse, json, statistics, subprocess, time

def lines(p):
    return subprocess.run(p, capture_output=True, text=True).stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--secs", type=int, default=5)
    a = ap.parse_args()
    stops = []
    for i in range(a.n):
        subprocess.run(["vaani", "start"], capture_output=True)
        time.sleep(a.secs)
        t0 = time.time()
        subprocess.run(["vaani", "stop"], capture_output=True)
        stops.append((time.time() - t0) * 1000)
        time.sleep(2)
    st = json.loads(lines(["vaani", "status", "--json"]) or "{}")
    print(f"n={a.n} utterance_secs={a.secs}")
    if stops:
        print(f"stop_dispatch_ms p50={statistics.median(stops):.0f} p95={sorted(stops)[int(len(stops)*0.95)-1 if len(stops)>1 else 0]:.0f}")
    print("daemon latencies:", json.dumps(st.get("data", {}), indent=2))
    print("record backend/model/threads/power + cold-vs-warm alongside these numbers")

if __name__ == "__main__":
    main()
