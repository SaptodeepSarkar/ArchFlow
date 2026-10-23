"""Shared helpers for the V8 training scripts.

Both trainers and both evals import this, so the frozen formatter prompt, the
resume state and the checkpoint layout cannot drift between training and eval.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import wave

import torch

# --- the frozen runtime prompt (crates/llm-formatter/src/llm.rs, do not edit) --

FROZEN_PROMPT = (
    "You format dictated speech into clean written text.\n"
    "Rules:\n"
    "1. Remove filler words (umm, hmm, uh, er, ah, like as filler).\n"
    "2. If the speaker corrects themselves, keep only the correction.\n"
    "3. Fix capitalization and punctuation. Keep the speaker's wording.\n"
    "4. Never add, explain, translate, or comment. No quotes around the result.\n"
    "5. Reply with ONLY the formatted text.\n"
    'Example: input "umm so i think hmm we should ship it" -> '
    'output "So I think we should ship it."\n'
)


def build_prompt(vocab=None):
    """Rule 6 is appended only when the row carries a vocab, exactly as in Rust."""
    prompt = FROZEN_PROMPT
    if vocab:
        prompt += "6. Replace these spoken words with exactly this text:\n"
        for spoken, typed in vocab:
            prompt += f'   "{spoken}" -> "{typed}"\n'
    return prompt


def chat_messages(row):
    """system/user/assistant messages for one formatter row."""
    return [
        {"role": "system", "content": build_prompt(row.get("vocab") or [])},
        {"role": "user", "content": row["input"]},
        {"role": "assistant", "content": row["output"]},
    ]


# --- files and state ---------------------------------------------------------

def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    """Atomic write: a Colab disconnect must never leave half a JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_state(out_dir):
    return read_json(os.path.join(out_dir, "state.json"), {}) or {}


def write_state(out_dir, stage=None, **fields):
    """Update `$OUT/state.json`: top-level keys mirror the current stage."""
    state = read_state(out_dir)
    stages = state.setdefault("stages", {})
    flat = {k: v for k, v in fields.items() if k in ("step", "epoch", "best", "status")}
    if stage:
        stages.setdefault(stage, {}).update(flat)
        state["stage"] = stage
    state.update(flat)
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(os.path.join(out_dir, "state.json"), state)
    return state


def stage_status(state, stage):
    return (state.get("stages") or {}).get(stage, {}).get("status", "pending")


def stage_done(out_dir, stage):
    return stage_status(read_state(out_dir), stage) == "done"


# --- config and CLI ----------------------------------------------------------

def load_config(path, overrides=None):
    """Config JSON is the single source of the recipe; flags win over it."""
    cfg = read_json(path, {})
    if not cfg:
        raise SystemExit(f"config not found or empty: {path}")
    for key, value in (overrides or {}).items():
        if value is not None:
            cfg[key] = value
    return cfg


def add_common_args(parser, model_env):
    parser.add_argument("--config", default=None, help="recipe JSON")
    parser.add_argument("--data", default=None, help="data root (VAANI_DATA_DIR)")
    parser.add_argument("--out", default=None, help="output root (VAANI_OUT_DIR)")
    parser.add_argument("--model", default=None, help=f"base model ({model_env})")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--session-limit-min", type=float, default=None)
    parser.add_argument("--eval-every", type=int, default=None)
    parser.add_argument("--save-every", type=int, default=None)
    parser.add_argument("--eval-limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--grad-accum", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--split", default="train")
    parser.add_argument("--smoke", action="store_true", help="tiny run: short evals, exports skipped")
    parser.add_argument("--no-resume", action="store_true")
    return parser


def env_default(name, fallback):
    return os.environ.get(name, fallback)


def resume_enabled(args):
    if args.no_resume:
        return False
    return os.environ.get("VAANI_RESUME", "1") != "0"


def session_limit_reached(t0, limit_min):
    """Contract: stop 120 s before the limit so the save always lands."""
    if not limit_min:
        return False
    return (time.time() - t0) > (limit_min * 60.0 - 120.0)


# --- heartbeat ---------------------------------------------------------------

class Heartbeat:
    """A flushed line every <=20 s, so a Colab client never sees an idle kernel."""

    def __init__(self, stage, interval=15):
        self.stage = stage
        self.interval = interval
        self.t0 = time.time()
        self.fields = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()

    def update(self, **fields):
        with self._lock:
            self.fields.update(fields)

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.print_now()
            except Exception:  # a heartbeat must never kill training
                pass

    def print_now(self):
        with self._lock:
            f = dict(self.fields)
        parts = ["HEARTBEAT", f"stage={self.stage}"]
        parts.append(f"step={f.get('step', 0)}")
        if "loss" in f:
            parts.append(f"loss={f['loss']:.4f}")
        if "lr" in f:
            parts.append(f"lr={f['lr']:.3g}")
        if "mem" in f:
            parts.append(f"mem={f['mem']:.1f}")
        parts.append(f"elapsed={int(time.time() - self.t0)}s")
        print(" ".join(parts), flush=True)


def gpu_mem_gb():
    if torch.cuda.is_available():
        return torch.cuda.max_memory_reserved() / 2**30
    return 0.0


# --- optimizer and schedule --------------------------------------------------

def make_optimizer(params, lr, weight_decay):
    # No requires_grad filter: the STT unfreezes encoder layers mid-run and the
    # optimizer must already hold them. 8-bit state is allocated on first grad.
    params = list(params)
    try:
        import bitsandbytes as bnb

        return bnb.optim.AdamW8bit(params, lr=lr, weight_decay=weight_decay)
    except Exception as exc:  # CPU smoke, or a bad bnb build
        print(f"[warn] 8-bit AdamW unavailable ({exc}); using torch AdamW", flush=True)
        return torch.optim.AdamW(params, lr=lr, weight_decay=weight_decay)


def wsd_factor(step, total_steps, warmup=0.05, stable=0.75, decay=0.20, min_ratio=0.0):
    """Warmup-stable-decay as fractions of `total_steps` (5/75/20 by default)."""
    total_steps = max(1, total_steps)
    warm = max(1, int(total_steps * warmup))
    stable_steps = int(total_steps * stable)
    decay_steps = max(1, total_steps - warm - stable_steps)
    if step < warm:
        return (step + 1) / warm
    if step < warm + stable_steps:
        return 1.0
    progress = min(1.0, (step - warm - stable_steps + 1) / decay_steps)
    return max(min_ratio, 1.0 - (1.0 - min_ratio) * progress)


def set_lr(optimizer, lr):
    for group in optimizer.param_groups:
        group["lr"] = lr


# --- checkpoints -------------------------------------------------------------

def checkpoint_dir(root, step):
    return os.path.join(root, f"step-{step:06d}")


def _torch_save(obj, path):
    tmp = path + ".tmp"
    torch.save(obj, tmp)
    os.replace(tmp, path)


def save_checkpoint(root, step, model, optimizer=None, meta=None, scaler=None):
    """`step-XXXXXX/{model.pt,optimizer.pt,meta.json}`; scaler rides in optimizer.pt."""
    directory = checkpoint_dir(root, step)
    os.makedirs(directory, exist_ok=True)
    _torch_save(model.state_dict(), os.path.join(directory, "model.pt"))
    if optimizer is not None:
        blob = {"optimizer": optimizer.state_dict()}
        if scaler is not None:
            blob["grad_scaler"] = scaler.state_dict()
        _torch_save(blob, os.path.join(directory, "optimizer.pt"))
    write_json(os.path.join(directory, "meta.json"), {"step": step, **(meta or {})})
    return directory


def list_checkpoints(root):
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        match = re.fullmatch(r"step-(\d{6})", name)
        path = os.path.join(root, name)
        if match and os.path.exists(os.path.join(path, "model.pt")):
            meta = read_json(os.path.join(path, "meta.json"), {}) or {}
            found.append({"step": int(match.group(1)), "dir": path, "meta": meta})
    return sorted(found, key=lambda c: c["step"])


def prune_checkpoints(root, keep_last=1, keep_best=2, lower_is_better=True):
    """Keep the newest checkpoint plus the two best by metric."""
    checkpoints = list_checkpoints(root)
    keep = {c["dir"] for c in checkpoints[-keep_last:]}
    scored = [c for c in checkpoints if isinstance(c["meta"].get("metric"), (int, float))]
    scored.sort(key=lambda c: c["meta"]["metric"], reverse=not lower_is_better)
    keep |= {c["dir"] for c in scored[:keep_best]}
    for c in checkpoints:
        if c["dir"] not in keep:
            shutil.rmtree(c["dir"], ignore_errors=True)


def best_checkpoints(root, k=3, lower_is_better=True):
    scored = [c for c in list_checkpoints(root) if isinstance(c["meta"].get("metric"), (int, float))]
    scored.sort(key=lambda c: c["meta"]["metric"], reverse=not lower_is_better)
    return scored[:k]


def average_checkpoints(paths, device="cpu"):
    """Plain mean of the float tensors. No EMA: three files, no extra state.

    Checkpoints are mmap'd so peak memory is one accumulator plus one tensor.
    """
    acc = None
    for path in paths:
        state = torch.load(path, map_location="cpu", mmap=True)
        if acc is None:
            acc = {k: (v.float().to(device) if v.is_floating_point() else v.clone())
                   for k, v in state.items()}
        else:
            for key, value in state.items():
                if acc[key].is_floating_point():
                    acc[key] += value.float().to(device)
        del state
    if acc is None:
        raise SystemExit("average_checkpoints: no checkpoints")
    for key in acc:
        if acc[key].is_floating_point():
            acc[key] /= len(paths)
    return acc


def average_top_checkpoints(stage_root, lower_is_better, k=3):
    """Average the top-k scored checkpoints into a state dict, or None."""
    top = best_checkpoints(stage_root, k=k, lower_is_better=lower_is_better)
    if not top:
        return None, []
    device = "cuda" if torch.cuda.is_available() else "cpu"
    acc = average_checkpoints([os.path.join(c["dir"], "model.pt") for c in top], device=device)
    steps = [c["step"] for c in top]
    print(f"averaged {len(steps)} checkpoints (steps {steps})", flush=True)
    return acc, steps


# --- audio -------------------------------------------------------------------

def load_wav_16k(path):
    """Contract data is 16 kHz mono PCM16; anything else is a data-prep bug."""
    with wave.open(path, "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit(f"{path}: expected 16 kHz mono PCM16, got "
                             f"{wav.getframerate()} Hz {wav.getnchannels()}ch {wav.getsampwidth() * 8}bit")
        raw = wav.readframes(wav.getnframes())
    import numpy as np

    return np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0


def stt_audio_path(data_dir, row):
    return os.path.join(data_dir, "stt", row["audio"])


def stt_split(data_dir, split):
    return read_jsonl(os.path.join(data_dir, "stt", f"{split}.jsonl"))


def formatter_split(data_dir, split):
    return read_jsonl(os.path.join(data_dir, "formatter", f"{split}.jsonl"))
