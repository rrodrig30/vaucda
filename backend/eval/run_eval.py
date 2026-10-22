#!/usr/bin/env python
"""VAUCDA note-level accuracy eval.

Scores generated clinic notes against per-patient GOLD specs and prints a
per-patient scorecard + a cohort summary (accuracy per metric). Architecture-
agnostic: point it at ANY directory of generated notes to A/B approaches
(current hybrid vs. holistic vs. whatever) on the identical gold set.

Usage:
  # score a directory of already-generated notes
  python -m eval.run_eval --notes DIR [--gold eval/gold] [--json OUT.json]

  # generate the notes first (current pipeline), then score
  python -m eval.run_eval --generate --out-notes DIR [--gold eval/gold] ...

Gold spec: one JSON per patient in --gold (see eval/gold/_SCHEMA.md). Only
patients with both a gold spec AND a generated note are scored; the summary
reports coverage so partial gold is fine and grows over time.

Run from the backend/ dir (so `eval` and `app` import cleanly).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval.scorers import METRIC_NAMES, score_note  # noqa: E402


def _load_gold(gold_dir: str) -> dict:
    gold = {}
    for path in glob.glob(os.path.join(gold_dir, "*.json")):
        if os.path.basename(path).startswith("_"):
            continue
        with open(path) as f:
            spec = json.load(f)
        gold[spec["patient_id"]] = spec
    return gold


def _match_note(notes_dir: str, patient_id: str):
    """Find the generated note whose filename contains the patient_id."""
    for path in sorted(glob.glob(os.path.join(notes_dir, "*.txt"))
                       + glob.glob(os.path.join(notes_dir, "*.vaucda"))):
        stem = os.path.basename(path)
        if patient_id.lower() in stem.lower():
            return path
    return None


def _source_psa(source_path: str) -> list:
    """Deterministic PSA value set from the source chart (grounding truth)."""
    if not source_path or not os.path.exists(source_path):
        return []
    try:
        from app.services.note_processing.extractors.psa_extractor import extract_psa
        raw = open(source_path, errors="ignore").read()
        vals = []
        for line in extract_psa(raw).splitlines():
            m = re.search(r":\s*<?(\d+\.?\d*)\s*$", line)
            if m:
                vals.append(float(m.group(1)))
        return vals
    except Exception:
        return []


def _resolve(path: str) -> str:
    """Resolve a gold source_file path relative to the repo root."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cand = os.path.join(repo, path)
    return cand if os.path.exists(cand) else path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=os.path.join(os.path.dirname(__file__), "gold"))
    ap.add_argument("--notes", help="directory of generated notes to score")
    ap.add_argument("--generate", action="store_true",
                    help="generate notes with the current pipeline first")
    ap.add_argument("--out-notes", help="where --generate writes notes")
    ap.add_argument("--json", help="write full results to this JSON path")
    ap.add_argument("--label", default="run", help="label for this run in output")
    args = ap.parse_args()

    gold = _load_gold(args.gold)
    if not gold:
        print(f"No gold specs in {args.gold}", file=sys.stderr)
        return 2

    notes_dir = args.notes
    if args.generate:
        notes_dir = args.out_notes or "/tmp/vaucda_eval_notes"
        _generate_notes(gold, notes_dir)

    if not notes_dir or not os.path.isdir(notes_dir):
        print(f"--notes dir not found: {notes_dir}", file=sys.stderr)
        return 2

    results = []
    for pid, spec in sorted(gold.items()):
        note_path = _match_note(notes_dir, pid)
        if not note_path:
            results.append((pid, None))
            continue
        note = open(note_path, errors="ignore").read()
        src = _resolve(spec.get("source_file", ""))
        r = score_note(pid, note, spec, _source_psa(src))
        results.append((pid, r))

    _print_report(args.label, results)
    if args.json:
        _write_json(args.json, args.label, results)
    # exit non-zero if any scored patient failed any metric (CI-friendly)
    any_fail = any(r and any(not m.passed for m in r.metrics) for _, r in results)
    return 1 if any_fail else 0


def _generate_notes(gold: dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    from app.services.note_processing.note_builder import (
        build_authoritative_patient_facts, build_urology_note,
    )
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.note_identifier import identify_notes
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from batch_generate_notes import make_configs, SOURCE_FORMAT
        s1, s2 = make_configs()
    except Exception as e:
        print(f"generate: cannot build LLM configs: {e}", file=sys.stderr)
        return
    for pid, spec in sorted(gold.items()):
        src = _resolve(spec.get("source_file", ""))
        if not os.path.exists(src):
            continue
        text = open(src, errors="ignore").read()
        m = re.search(r"\bDATE:\s*(\d{1,2}/\d{1,2}/\d{4})", text[:4000])
        ci = f"VISIT DATE: {m.group(1) if m else '7/8/2026'}\n\n{text}"
        facts = build_authoritative_patient_facts(ci, SOURCE_FORMAT, llm_task_config=s1)
        stage1 = build_urology_note(clinical_text=ci, task_config=s1,
                                    source_format=SOURCE_FORMAT, patient_facts=facts)
        nd = identify_notes(text)
        final = build_stage2_note(
            stage1_note=stage1, gu_notes=nd.get("gu_notes", []),
            non_gu_notes=nd.get("non_gu_notes", []), ambient_transcript=None,
            calculator_results={}, rag_content="", task_config=s2,
            note_type="clinic_note", patient_facts=facts)
        open(os.path.join(out_dir, f"{pid}.txt"), "w").write(final)
        print(f"  generated {pid}")


def _print_report(label: str, results: list) -> None:
    print(f"\n{'='*72}\nVAUCDA note-eval — {label}\n{'='*72}")
    scored = [(p, r) for p, r in results if r]
    print(f"gold patients: {len(results)} | scored: {len(scored)} | "
          f"missing note: {len(results) - len(scored)}\n")
    # per-patient grid
    hdr = f"{'patient':22}" + "".join(f"{n[:12]:>14}" for n in METRIC_NAMES)
    print(hdr)
    print("-" * len(hdr))
    for pid, r in results:
        if not r:
            print(f"{pid:22}{'(no note)':>14}")
            continue
        row = f"{pid:22}"
        for n in METRIC_NAMES:
            mm = r.get(n)
            row += f"{('PASS' if mm.passed else 'FAIL'):>14}"
        print(row)
    # cohort accuracy per metric
    print(f"\n{'metric':22}{'pass rate':>14}")
    print("-" * 36)
    for n in METRIC_NAMES:
        vals = [r.get(n).passed for _, r in scored if r.get(n)]
        rate = (sum(vals) / len(vals) * 100) if vals else 0.0
        print(f"{n:22}{f'{rate:.0f}% ({sum(vals)}/{len(vals)})':>14}")
    # overall
    allm = [m.passed for _, r in scored for m in r.metrics]
    overall = (sum(allm) / len(allm) * 100) if allm else 0.0
    print(f"\nOVERALL metric pass rate: {overall:.1f}%  ({sum(allm)}/{len(allm)})")
    # show failing details
    fails = [(p, m) for p, r in scored for m in r.metrics if not m.passed]
    if fails:
        print(f"\nFAILURES ({len(fails)}):")
        for p, m in fails:
            print(f"  [{p}] {m.name}: {m.detail}")


def _write_json(path: str, label: str, results: list) -> None:
    out = {"label": label, "patients": {}}
    for pid, r in results:
        if not r:
            out["patients"][pid] = None
            continue
        out["patients"][pid] = {
            m.name: {"passed": m.passed, "score": m.score, "detail": m.detail}
            for m in r.metrics}
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
