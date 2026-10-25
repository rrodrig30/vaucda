# L1 Milestone 3 — QLoRA fine-tune medgemma-27b

Trains the L1 narrative extractor as a LoRA adapter on the GLM-5.2 silver corpus
(`tests/l1_train/l1_sft.jsonl`, 819 examples) and evaluates it against the
**frozen gold** (`tests/l1_gold`, 99 segments, urologist-approved) with
`scripts/l1/score.py`. **Runs on the H100 — not in the agent sandbox.**

## Prereqs
1. A CUDA box (your 96 GB H100). Fresh venv:
   `python -m venv .venv-l1 && . .venv-l1/bin/activate`
2. `pip install -r scripts/l1/train/requirements.txt`
3. medgemma is **gated**: accept the Health AI Developer Foundations license for
   `google/medgemma-27b-text-it` on HuggingFace, then `huggingface-cli login`.

## Train
```bash
cd backend
python scripts/l1/train/train_l1_lora.py \
    --data ../tests/l1_train/l1_sft.jsonl \
    --out  ../tests/l1_model/medgemma27b-l1-lora
```
Defaults (single H100): QLoRA 4-bit (nf4 + double-quant, bf16 compute), LoRA
r=16/α=32 on attn+MLP proj, max_len 8192, lr 1e-4 cosine, 3 epochs, micro-batch
1 × grad-accum 16 (effective 16). Completion-only loss
(`assistant_only_loss=True`) so it learns to GENERATE the JSON, not echo the
prompt. **Low-tier silver (36 noisy) is excluded by default**
(`--include-tiers high,medium`); `--oversample-high N` up-weights the confident
examples.

Rough envelope: ~40-60 GB VRAM at 8192 seq len; a few hours for 3 epochs over
~780 examples. Tune `--grad-accum` / `--max-seq-len` to taste.

## Evaluate (the real metric — vs frozen gold)
```bash
scripts/l1/train/eval_l1.sh ../tests/l1_model/medgemma27b-l1-lora
```
This generates L1 predictions on the gold segments (`predict_l1.py`, same prompt
as training, deterministic decode, hardened quote→span resolver) and prints
`score.py` for BOTH the regex baseline and the fine-tuned model.

**Bar to beat (regex baseline vs gold):** diagnoses R≈0.18, treatment-event
R≈0.07, grade-by-system ≈0.95. Success = treatment/diagnosis recall up sharply
while grade-by-system stays ≥0.9 and procedures-as-imaging stays 0.

## Files
| file | role |
|---|---|
| `train_l1_lora.py` | QLoRA SFT trainer (tier-aware, completion-only) |
| `predict_l1.py` | base+adapter inference over a segment dir → scorer-format labels |
| `eval_l1.sh` | predict on gold → score vs gold (+ the baseline) |
| `requirements.txt` | training deps |

## After M3 → M4
Once the adapter beats the baseline on gold, M4 wires it behind `VAUCDA_L1=1`:
the router (`scripts/l1/router.py`) sends narrative segments to L1, structured
stays deterministic, and L1's facts merge into `PatientStatusFacts` with the
span-resolver + L3 verifier as nets. Promote per-field only where L1 ≥ regex on
the gold.

## Notes
- Iteration accuracy depends on the silver teacher (GLM-5.2). If a field lags on
  gold, regenerate that slice of silver with a stronger prompt or a better
  teacher and retrain — the harness measures each change deterministically.
- To serve faster you can `merge_and_unload()` the adapter and re-quantize, or
  export to Ollama/vLLM; keep the inference prompt byte-identical to training.
