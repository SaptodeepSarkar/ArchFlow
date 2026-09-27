#!/usr/bin/env python3
"""Train the V6 constrained copy-biased formatter on approved foundation rows.

The runtime protocol is fixed tokens plus the current raw utterance; no natural-
language system prompt is required.  Only the clean target contributes loss.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from torch.utils.data import Dataset

IN_TAG, OUT_TAG = "<|v6_input|>", "<|v6_output|>"

def read_rows(paths):
    rows=[]
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r=json.loads(line)
                if r.get("annotation",{}).get("review_status") == "approved": rows.append(r)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    args=ap.parse_args()
    rows=read_rows(args.train)
    tok=AutoTokenizer.from_pretrained(args.model)
    added=tok.add_special_tokens({"additional_special_tokens":[IN_TAG,OUT_TAG]})
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    encoded=[]
    for r in rows:
        raw=r["utterance"]["raw_stt"].strip(); target=r["utterance"]["clean_target"].strip()
        prefix=f"{IN_TAG}\n{raw}\n{OUT_TAG}\n"
        full=prefix+target+tok.eos_token
        item=tok(full, truncation=True, max_length=args.max_length)
        plen=len(tok(prefix, truncation=True, max_length=args.max_length)["input_ids"])
        labels=list(item["input_ids"]); labels[:min(plen,len(labels))]=[-100]*min(plen,len(labels))
        encoded.append({"input_ids":item["input_ids"],"attention_mask":item["attention_mask"],"labels":labels})
    class Encoded(Dataset):
        def __init__(self, items): self.items=items
        def __len__(self): return len(self.items)
        def __getitem__(self, i): return self.items[i]
    ds=Encoded(encoded)
    model=AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32)
    if added: model.resize_token_embeddings(len(tok))
    model.config.use_cache=False
    model.enable_input_require_grads()
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],task_type="CAUSAL_LM"))
    def collate(fs):
        return {k:torch.nn.utils.rnn.pad_sequence([torch.tensor(x[k]) for x in fs],batch_first=True,padding_value=(tok.pad_token_id if k=="input_ids" else 0 if k=="attention_mask" else -100)) for k in ("input_ids","attention_mask","labels")}
    args.out.mkdir(parents=True,exist_ok=True)
    trainer=Trainer(model=model,args=TrainingArguments(output_dir=str(args.out),max_steps=args.steps,per_device_train_batch_size=args.batch_size,gradient_accumulation_steps=args.grad_accum,learning_rate=1e-4,warmup_steps=100,lr_scheduler_type="cosine",bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),gradient_checkpointing=True,logging_steps=25,save_steps=500,save_total_limit=2,report_to="none",remove_unused_columns=False),train_dataset=ds,data_collator=collate)
    print(json.dumps({"rows":len(rows),"steps":args.steps,"cuda":torch.cuda.is_available()}),flush=True)
    trainer.train(); trainer.save_model(str(args.out)); tok.save_pretrained(str(args.out))
    print(json.dumps({"saved":str(args.out),"rows":len(rows),"steps":args.steps}),flush=True)
if __name__ == "__main__": main()
