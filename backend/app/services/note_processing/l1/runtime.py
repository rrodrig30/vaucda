"""L1 model runtime: lazy singleton + per-segment inference.

Loads the base medgemma-27b (4-bit nf4) once and attaches the fine-tuned LoRA
adapter, then runs greedy generation over one narrative segment at a time using
the SAME prompt format and JSON parser as training/eval (byte-identical, so the
gold-measured behavior carries over to production).

Env:
  VAUCDA_L1_ADAPTER  adapter dir   (default: <repo>/tests/l1_model/medgemma27b-l1-lora)
  VAUCDA_L1_BASE     base model    (default: google/medgemma-27b-text-it)
  VAUCDA_L1_MAX_NEW  max new toks  (default: 2048)
  HF_TOKEN           gated-model access (read from the already-loaded .env)
"""
import os
import sys
from pathlib import Path
from typing import List, Optional

# Reuse the validated L1 scripts (prompt, segment router) rather than duplicate
# them — keeps production inference identical to how the corpus was built/scored.
_BACKEND = Path(__file__).resolve().parents[4]            # .../backend
_L1_SCRIPTS = _BACKEND / "scripts" / "l1"
for _p in (str(_L1_SCRIPTS), str(_L1_SCRIPTS / "train")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_DEFAULT_ADAPTER = _BACKEND.parent / "tests" / "l1_model" / "medgemma27b-l1-lora"
_DEFAULT_BASE = "google/medgemma-27b-text-it"
_MAXLEN = 8192

_STATE = {"loaded": False, "tok": None, "model": None, "eos": None}


def _load():
    """Load tokenizer + base(4-bit) + adapter once; cache on _STATE."""
    if _STATE["loaded"]:
        return
    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig)
    from peft import PeftModel

    adapter = os.getenv("VAUCDA_L1_ADAPTER") or str(_DEFAULT_ADAPTER)
    base = os.getenv("VAUCDA_L1_BASE") or _DEFAULT_BASE
    if not Path(adapter).exists():
        raise FileNotFoundError(f"L1 adapter not found: {adapter} "
                                "(set VAUCDA_L1_ADAPTER)")

    print(f"[L1] loading base={base} + adapter={adapter} (4-bit, sdpa) ...")
    tok = AutoTokenizer.from_pretrained(adapter)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(
        base, quantization_config=bnb, torch_dtype=torch.bfloat16,
        device_map="auto", attn_implementation="sdpa")
    model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    eos = [i for i in {tok.eos_token_id, eot} if i is not None and i >= 0]

    _STATE.update(loaded=True, tok=tok, model=model, eos=eos)
    print("[L1] model ready")


def _build_prompt(tok, segment_text: str, pathology_text: str) -> str:
    from make_finetune_jsonl import INSTRUCTION  # validated training prompt
    path = pathology_text.strip() or "(no surgical pathology on file)"
    user = (INSTRUCTION + "\n\n=== NOTE SEGMENT ===\n" + segment_text
            + "\n\n=== SURGICAL PATHOLOGY ===\n" + path)
    return tok.apply_chat_template([{"role": "user", "content": user}],
                                   tokenize=False, add_generation_prompt=True)


def extract_batch(segment_texts: List[str], pathology_text: str) -> List[Optional[dict]]:
    """Run L1 over many segments (sharing one pathology reference) and return a
    parsed v2 JSON dict (or None) per input, in the SAME order.

    Generations are length-sorted and packed into token-budgeted batches (the
    same strategy as the offline eval predictor) so a 24-58 segment patient is a
    handful of batched forward passes, not dozens of sequential ones. Left-pad +
    a per-row prompt-length slice keep the decode aligned.
    """
    _load()
    import torch
    from app.services.note_processing.agents.hpi_json_prompt import parse_hpi_json

    tok, model, eos = _STATE["tok"], _STATE["model"], _STATE["eos"]
    max_new = int(os.getenv("VAUCDA_L1_MAX_NEW", "2048"))
    budget = int(os.getenv("VAUCDA_L1_BATCH_BUDGET", "50000"))
    gen_est = 1024

    items = []
    for i, seg in enumerate(segment_texts):
        prompt = _build_prompt(tok, seg, pathology_text)
        n = min(len(tok(prompt, add_special_tokens=False).input_ids), _MAXLEN)
        items.append({"i": i, "prompt": prompt, "n": n})
    items.sort(key=lambda it: it["n"])

    batches, cur, cur_max = [], [], 0
    for it in items:
        nmax = max(cur_max, it["n"])
        if cur and ((len(cur) + 1) * (nmax + gen_est) > budget or len(cur) >= 24):
            batches.append(cur)
            cur, cur_max = [], 0
        cur.append(it)
        cur_max = max(cur_max, it["n"])
    if cur:
        batches.append(cur)

    out: List[Optional[dict]] = [None] * len(segment_texts)
    for batch in batches:
        enc = tok([it["prompt"] for it in batch], return_tensors="pt", padding=True,
                  truncation=True, max_length=_MAXLEN).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                                 eos_token_id=eos,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        plen = enc["input_ids"].shape[1]
        for row, it in zip(gen, batch):
            text = tok.decode(row[plen:], skip_special_tokens=True)
            draft, _err = parse_hpi_json(text)
            out[it["i"]] = draft or None
    return out


def extract_segment(segment_text: str, pathology_text: str) -> Optional[dict]:
    """Run L1 on one narrative segment (+ pathology). Thin wrapper over the
    batched path so callers can use either."""
    return extract_batch([segment_text], pathology_text)[0]
