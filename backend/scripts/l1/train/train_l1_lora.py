#!/usr/bin/env python3
"""
M3: QLoRA fine-tune medgemma-27b (text) on the L1 silver SFT corpus.

Runs on the H100 (NOT in the agent sandbox). Trains a LoRA adapter to emit the
v2 extraction JSON from (instruction + note segment + surgical pathology).
Completion-only loss (the model learns to GENERATE the JSON, not echo the
prompt). Confidence-tier aware: low-tier silver is excluded by default,
high-tier can be oversampled.

Quickstart:
    pip install -r scripts/l1/train/requirements.txt
    huggingface-cli login              # medgemma is a gated model
    python scripts/l1/train/train_l1_lora.py \
        --data ../tests/l1_train/l1_sft.jsonl \
        --out  ../tests/l1_model/medgemma27b-l1-lora

Then evaluate against the FROZEN GOLD:
    scripts/l1/train/eval_l1.sh ../tests/l1_model/medgemma27b-l1-lora

Defaults are tuned for a single 96 GB H100 (QLoRA 4-bit, 27B).
"""
import argparse
import json
import random

import torch
from datasets import Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          BitsAndBytesConfig)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTConfig, SFTTrainer


def load_examples(path, include_tiers, oversample_high):
    rows = [json.loads(l) for l in open(path)]
    kept = [r for r in rows if r.get("confidence", "high") in include_tiers]
    if oversample_high > 1:
        extra = [r for r in kept if r.get("confidence") == "high"]
        kept = kept + extra * (oversample_high - 1)
    random.Random(13).shuffle(kept)
    # SFTTrainer consumes the chat "messages" field directly.
    return Dataset.from_list([{"messages": r["messages"], "confidence": r.get("confidence", "high")}
                              for r in kept])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="l1_sft.jsonl")
    ap.add_argument("--out", required=True, help="adapter output dir")
    ap.add_argument("--model", default="google/medgemma-27b-text-it")
    ap.add_argument("--include-tiers", default="high,medium",
                    help="confidence tiers to train on (low excluded by default — noisy)")
    ap.add_argument("--oversample-high", type=int, default=1,
                    help="duplicate high-tier examples N times")
    ap.add_argument("--max-seq-len", type=int, default=8192)
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--micro-batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--dev-frac", type=float, default=0.05,
                    help="silver slice held out for eval-loss (the GOLD is the real metric)")
    args = ap.parse_args()

    tiers = set(args.include_tiers.split(","))
    ds = load_examples(args.data, tiers, args.oversample_high)
    split = ds.train_test_split(test_size=args.dev_frac, seed=13)
    print(f"train={len(split['train'])}  dev={len(split['test'])}  tiers={tiers}")

    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=bnb, torch_dtype=torch.bfloat16,
        attn_implementation="eager", device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    cfg = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.micro_batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
        bf16=True, gradient_checkpointing=True,
        max_length=args.max_seq_len,
        packing=False,                      # one example per sequence (varied lengths)
        assistant_only_loss=True,           # completion-only: loss on the JSON, not the prompt
        logging_steps=10, save_strategy="epoch", eval_strategy="epoch",
        report_to="none", optim="paged_adamw_8bit",
    )
    trainer = SFTTrainer(
        model=model, args=cfg, processing_class=tok,
        train_dataset=split["train"], eval_dataset=split["test"],
    )
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    print(f"\nLoRA adapter saved -> {args.out}")
    print("Evaluate on the frozen gold:  scripts/l1/train/eval_l1.sh " + args.out)


if __name__ == "__main__":
    main()
