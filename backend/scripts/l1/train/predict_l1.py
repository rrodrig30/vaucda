#!/usr/bin/env python3
"""
M3 eval: run the fine-tuned L1 (base medgemma-27b + LoRA adapter) over a segment
dir and write candidate labels in the scorer's format. Provenance spans are
resolved from the model's source_quotes with the SAME hardened resolver used in
production (flexible whitespace over segment + pathology).

Usage:
  python scripts/l1/train/predict_l1.py <adapter_dir> <gold_dir> <out_dir> [--base google/medgemma-27b-text-it]

Then:
  python scripts/l1/score.py <gold_dir> <out_dir>
"""
import argparse
import json
import re
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from make_finetune_jsonl import INSTRUCTION  # noqa: E402  (identical inference prompt)
from app.services.note_processing.agents.hpi_json_prompt import parse_hpi_json  # noqa: E402

_REC = ("diagnoses", "treatment_events", "procedures", "imaging", "metastases")


def resolve(rec, haystacks):
    q = rec.pop("source_quote", None)
    span = src = None
    if q and q.split():
        pat = re.compile(r"\s+".join(re.escape(t) for t in q.split()), re.S)
        for name, text in haystacks:
            m = pat.search(text)
            if m:
                span, src = [m.start(), m.end()], name
                break
    rec["source_span"], rec["source"] = span, src
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter")
    ap.add_argument("gold_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--base", default="google/medgemma-27b-text-it")
    ap.add_argument("--max-new", type=int, default=2048)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.adapter)
    # Left-pad for decoder-only batched generation (generated tokens align at the
    # end, so one prompt-length slice decodes every row in the batch).
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=bnb, torch_dtype=torch.bfloat16,
        device_map="auto", attn_implementation="sdpa")
    model = PeftModel.from_pretrained(base, args.adapter)
    model.eval()
    # Stop on <end_of_turn> as well as eos so short JSON doesn't run to max_new.
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    eos_ids = [i for i in {tok.eos_token_id, eot} if i is not None and i >= 0]

    seg_dir = Path(args.gold_dir) / "segments"
    out = Path(args.out_dir) / "labels"
    out.mkdir(parents=True, exist_ok=True)
    sids = sorted(p.stem for p in seg_dir.glob("*.txt") if not p.name.endswith(".pathology.txt"))

    # Build every prompt up front, record token length for length-sorted batching.
    MAXLEN = 8192
    items = []
    for sid in sids:
        seg = (seg_dir / f"{sid}.txt").read_text(errors="ignore")
        pth = seg_dir / f"{sid}.pathology.txt"
        path = pth.read_text(errors="ignore") if pth.exists() else "(no surgical pathology on file)"
        user = (INSTRUCTION + "\n\n=== NOTE SEGMENT ===\n" + seg
                + "\n\n=== SURGICAL PATHOLOGY ===\n" + path)
        prompt = tok.apply_chat_template([{"role": "user", "content": user}],
                                         tokenize=False, add_generation_prompt=True)
        n = min(len(tok(prompt, add_special_tokens=False).input_ids), MAXLEN)
        items.append({"sid": sid, "seg": seg, "path": path, "prompt": prompt, "n": n})

    # Sort short->long, then greedily pack batches under a KV-cache token budget:
    # batch_size * (padded_prompt_len + max_new) <= BUDGET. Short segments batch
    # heavily; the few long ones batch small — bounds peak memory either way.
    # Budget on a realistic generation estimate, not worst-case max_new: actual
    # JSON outputs are ~hundreds of tokens, and gemma3's sliding-window KV (1024
    # on 5/6 layers) keeps cache small even if a row runs to max_new.
    items.sort(key=lambda it: it["n"])
    BUDGET, GEN_EST = 50000, 1024
    batches, cur, cur_max = [], [], 0
    for it in items:
        nmax = max(cur_max, it["n"])
        if cur and ((len(cur) + 1) * (nmax + GEN_EST) > BUDGET or len(cur) >= 24):
            batches.append(cur)
            cur, cur_max = [], 0
        cur.append(it)
        cur_max = max(cur_max, it["n"])
    if cur:
        batches.append(cur)

    ok = fail = done = 0
    for bi, batch in enumerate(batches):
        enc = tok([it["prompt"] for it in batch], return_tensors="pt", padding=True,
                  truncation=True, max_length=MAXLEN).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=args.max_new, do_sample=False,
                                  eos_token_id=eos_ids,
                                  pad_token_id=tok.pad_token_id or tok.eos_token_id)
        plen = enc["input_ids"].shape[1]
        for row, it in zip(gen, batch):
            text = tok.decode(row[plen:], skip_special_tokens=True)
            draft, err = parse_hpi_json(text)
            if not draft:
                fail += 1
                draft = {"primary_context": "urologic", "diagnoses": [],
                         "treatment_events": [], "procedures": [], "imaging": [], "metastases": []}
            else:
                ok += 1
            rec = {"segment_id": it["sid"],
                   "primary_context": draft.get("primary_context", "urologic")}
            hs = [("segment", it["seg"]), ("pathology", it["path"])]
            for k in _REC:
                rec[k] = [resolve(dict(r), hs) for r in (draft.get(k) or [])]
            (out / f"{it['sid']}.json").write_text(json.dumps(rec, indent=1))
        done += len(batch)
        print(f"  batch {bi+1}/{len(batches)} (bs={len(batch)}, len<={batch[-1]['n']}) "
              f"-> {done}/{len(items)} done", flush=True)
    print(f"predicted {len(items)} segments ({ok} parsed, {fail} fell back) -> {out}")
    print(f"score:  python scripts/l1/score.py {args.gold_dir} {args.out_dir}")


if __name__ == "__main__":
    main()
