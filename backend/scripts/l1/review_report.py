#!/usr/bin/env python3
"""
Generate a human-readable HTML review page for the L1 gold labels.

For a clinician: shows each note next to the AI-extracted facts (with the
supporting quote highlighted in the note), with an OK / Needs-fix toggle and a
free-text correction box per note. NO JSON editing. A "Download review" button
saves your verdicts; re-run apply_review.py to fold them into the labels.

Usage:
  ./venv/bin/python scripts/l1/review_report.py <gold_dir>                 # all
  ./venv/bin/python scripts/l1/review_report.py <gold_dir> --out review_sample.html <id1> <id2>
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.source_normalizers import normalize_to_cprs  # noqa: E402
from app.services.note_processing.clinical_timeline import extract_psa_trajectory  # noqa: E402

# Where the patient source extracts live (to pull read-only PSA/meds context).
SOURCE_DIRS = [
    Path(__file__).resolve().parents[2] / "../tests/Tumor_6_24_2026",
    Path(__file__).resolve().parents[2] / "../tests/loose_batch",
    Path(__file__).resolve().parents[2] / "../tests/Monday_batch",
]
_CTX_CACHE: dict = {}


def _locate_source(patient_file: str):
    for d in SOURCE_DIRS:
        p = d / patient_file
        if p.exists():
            return p
    return None


def _active_meds(raw: str):
    """(drug, sig) pairs from the authoritative RXOP active-outpatient list."""
    m = re.search(r"-+ RXOP - OUTPT RX-ACTIVE ONLY -+\n(.*?)(?=\n-{6,} [A-Z])",
                  raw, re.S)
    if not m:
        return []
    body = m.group(1)
    if re.search(r"No data available", body, re.I):
        return [("(no active outpatient medications on file)", "")]
    out, lines = [], body.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        # Drug-name line: uppercase start, has a strength/form, not a field label.
        if re.match(r"^[A-Z][A-Z0-9/,\.\-\(\) ]{2,}$", s) and \
           re.search(r"\b(MG|MCG|GM|G|%|UNIT|TAB|CAP|CAPS?|SOLN|CREAM|INJ|PEN|ML|"
                     r"SUPP|PATCH|GEL|OINT|SUSP|LIQUID|INHALER)\b", s) and \
           not s.startswith(("RX ", "SIG", "INDICATION", "PROVIDER", "DRUG")):
            sig = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                sm = re.search(r"SIG:\s*(.+)", lines[j])
                if sm:
                    sig = sm.group(1).strip()
                    break
            out.append((s, sig))
    return out


def _patient_context(patient_file: str):
    if patient_file in _CTX_CACHE:
        return _CTX_CACHE[patient_file]
    src = _locate_source(patient_file)
    psa, meds = [], []
    if src:
        raw = src.read_text(errors="ignore")
        try:
            psa = extract_psa_trajectory(normalize_to_cprs(raw, "vista"))
        except Exception:
            psa = []
        meds = _active_meds(raw)
    _CTX_CACHE[patient_file] = (psa, meds)
    return psa, meds


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def highlight(text, spans):
    """Wrap source spans in <mark>. spans = list of [start,end]."""
    spans = sorted([s for s in spans if s], key=lambda s: s[0])
    out, cur = [], 0
    for a, b in spans:
        if a < cur or a > len(text):
            continue
        out.append(esc(text[cur:a]))
        out.append(f"<mark>{esc(text[a:b])}</mark>")
        cur = b
    out.append(esc(text[cur:]))
    return "".join(out)


def _grade_str(g):
    if not g:
        return ""
    sys_ = g.get("system")
    if sys_ == "gleason-isup":
        return f"Gleason {esc(g.get('gleason'))} / GG{esc(g.get('grade_group'))}"
    if sys_ == "fuhrman":
        return f"Fuhrman nuclear grade {esc(g.get('nuclear_grade'))}"
    if sys_ == "who":
        s = f"WHO {esc(g.get('who_grade'))}"
        if g.get("bladder_stage"):
            s += f", stage {esc(g.get('bladder_stage'))}"
        return s
    return esc(g.get("value") or "")


def render_facts(lab):
    rows = []
    if lab.get("primary_context") == "non_urologic":
        rows.append("<div class=badge>⚠ NON-UROLOGIC note (kept for "
                    "cross-specialty facts — chemo / radiation / "
                    "hospitalization / palliative; no primary urologic "
                    "diagnosis minted)</div>")
    dxs = lab.get("diagnoses") or []
    for d in dxs:
        gr = _grade_str(d.get("grade"))
        rows.append(
            f"<div class=grp><b>Diagnosis {esc(d.get('id'))}</b> "
            f"<span class=cat>{esc(d.get('category'))}</span><table>"
            f"<tr><td>name</td><td>{esc(d.get('name'))}</td></tr>"
            f"<tr><td>site</td><td>{esc(d.get('site'))}</td></tr>"
            f"<tr><td>dx date</td><td>{esc(d.get('diagnosis_date'))}</td></tr>"
            + (f"<tr><td>grade</td><td>{gr}</td></tr>" if gr else "")
            + (f"<tr><td>stage</td><td>{esc(d.get('stage_tnm'))}</td></tr>" if d.get('stage_tnm') else "")
            + (f"<tr><td>risk</td><td>{esc(d.get('risk'))}</td></tr>" if d.get('risk') else "")
            + "</table></div>")
    if not dxs:
        rows.append("<div class=grp><b>Diagnoses</b> <i>none extracted</i></div>")
    tev = lab.get("treatment_events") or []
    if tev:
        r = "<div class=grp><b>Treatments</b><table><tr><th>for dx</th><th>modality</th><th>agent</th><th>start</th><th>end</th><th>status</th></tr>"
        for e in tev:
            r += (f"<tr><td>{esc(e.get('for_diagnosis'))}</td><td>{esc(e.get('modality'))}</td>"
                  f"<td>{esc(e.get('agent'))}</td><td>{esc(e.get('start_date'))}</td>"
                  f"<td>{esc(e.get('end_date'))}</td><td>{esc(e.get('status'))}</td></tr>")
        rows.append(r + "</table></div>")
    pr = lab.get("procedures") or []
    if pr:
        r = "<div class=grp><b>Procedures (interventions)</b><table><tr><th>type</th><th>date</th><th>finding</th></tr>"
        for p in pr:
            r += f"<tr><td>{esc(p.get('type'))}</td><td>{esc(p.get('date'))}</td><td>{esc(p.get('finding'))}</td></tr>"
        rows.append(r + "</table></div>")
    im = lab.get("imaging") or []
    if im:
        r = "<div class=grp><b>Imaging</b><table><tr><th>modality</th><th>date</th><th>impression</th></tr>"
        for p in im:
            r += f"<tr><td>{esc(p.get('modality'))}</td><td>{esc(p.get('date'))}</td><td>{esc(p.get('impression'))}</td></tr>"
        rows.append(r + "</table></div>")
    mets = lab.get("metastases") or []
    if mets:
        r = "<div class=grp><b>Metastases</b><table><tr><th>site</th><th>date</th></tr>"
        for m in mets:
            r += f"<tr><td>{esc(m.get('site'))}</td><td>{esc(m.get('date'))}</td></tr>"
        rows.append(r + "</table></div>")
    return "".join(rows) or "<i>no facts extracted</i>"


def render_context(patient_file):
    """Read-only PSA curve + active meds for clinical reference (NOT labeled)."""
    psa, meds = _patient_context(patient_file)
    psa_html = "<i>none</i>"
    if psa:
        cells = "".join(
            f"<span class=psa>{esc(disp)} <b>{esc(val)}</b></span>"
            for _k, disp, val in psa[:14]
        )
        psa_html = f"<div class=psa-row>{cells}</div>"
    meds_html = "<i>none</i>"
    if meds:
        meds_html = "".join(
            f"<div class=med><b>{esc(d)}</b>{(' — ' + esc(sig)) if sig else ''}</div>"
            for d, sig in meds[:14]
        )
    return (f"<div class=ctx><div class=ctxh>REFERENCE (auto-extracted, not "
            f"reviewed here)</div>"
            f"<div class=ctxbody><div><span class=ctxlbl>PSA curve</span>{psa_html}</div>"
            f"<div><span class=ctxlbl>Active outpatient meds (RXOP)</span>{meds_html}</div>"
            f"</div></div>")


def all_spans(lab):
    spans = []
    for k in ("diagnoses", "treatment_events", "procedures", "imaging", "metastases"):
        for r in lab.get(k) or []:
            if r.get("source_span"):
                spans.append(r["source_span"])
    return spans


CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1a1a2e}
header{position:sticky;top:0;background:#0f3460;color:#fff;padding:10px 16px;z-index:5;display:flex;gap:14px;align-items:center}
header button{font-size:14px;padding:6px 12px;border:0;border-radius:6px;background:#16c79a;color:#04111d;font-weight:600;cursor:pointer}
.card{background:#fff;margin:14px;border-radius:10px;box-shadow:0 1px 4px #0002;overflow:hidden}
.card h3{margin:0;padding:8px 14px;background:#eef1f6;font-size:13px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0}
.note{white-space:pre-wrap;font:12px/1.45 ui-monospace,Menlo,monospace;padding:12px;border-right:1px solid #eee;max-height:460px;overflow:auto;background:#fbfcfe}
.facts{padding:12px;max-height:460px;overflow:auto}
mark{background:#fff3a0;padding:0 1px}
table{border-collapse:collapse;margin:4px 0 10px;width:100%}
td,th{border:1px solid #e3e6ee;padding:2px 6px;text-align:left;vertical-align:top;font-size:12px}
th{background:#f0f3f9}
.grp{margin-bottom:8px}
.ctx{background:#eef6ff;border-top:1px solid #d6e6fb;border-bottom:1px solid #d6e6fb;padding:8px 14px;font-size:12px}
.ctxh{font-size:10px;letter-spacing:.5px;color:#5a7ab0;font-weight:700;margin-bottom:4px}
.ctxbody{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.ctxlbl{display:block;font-weight:700;color:#34507e;margin-bottom:2px}
.psa-row{display:flex;flex-wrap:wrap;gap:4px}
.psa{background:#fff;border:1px solid #cfe0f5;border-radius:4px;padding:1px 5px;white-space:nowrap}
.med{padding:1px 0}
.badge{background:#ffe7c2;border:1px solid #f0b860;color:#7a4a00;padding:4px 8px;border-radius:6px;margin-bottom:8px;font-weight:600;font-size:11px}
.cat{font-size:10px;background:#e6ecf6;border-radius:4px;padding:1px 6px;color:#34507e;text-transform:uppercase}
.ctl{padding:10px 14px;background:#fafbfd;border-top:1px solid #eee;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ctl textarea{flex:1;min-width:240px;min-height:34px;font:13px sans-serif;padding:6px;border:1px solid #ccd;border-radius:6px}
label.v{font-weight:600;cursor:pointer;padding:4px 8px;border-radius:6px}
input[type=radio]{vertical-align:middle}
.ok{color:#0a8754}.fix{color:#c0392b}
#prog{margin-left:auto;font-weight:600}
"""

JS = """
function downloadReview(){
 const out={};
 document.querySelectorAll('.card').forEach(c=>{
  const id=c.dataset.id;
  const v=c.querySelector('input[name="v_"+id]:checked');
  out[id]={verdict:v?v.value:'unreviewed',correction:c.querySelector('textarea').value.trim()};
 });
 const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='review_verdicts.json';a.click();
}
function prog(){
 const n=document.querySelectorAll('.card').length;
 const d=document.querySelectorAll('input[type=radio]:checked').length;
 document.getElementById('prog').textContent=d+' / '+n+' reviewed';
}
document.addEventListener('change',e=>{if(e.target.type==='radio')prog()});
window.onload=prog;
"""


def main():
    gold = Path(sys.argv[1])
    argv = sys.argv[2:]
    out_name = "review.html"
    if "--out" in argv:
        i = argv.index("--out")
        out_name = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    only_ids = set(argv) or None

    seg_dir, lab_dir = gold / "segments", gold / "labels"
    cards = []
    label_files = ([lab_dir / f"{i}.json" for i in argv]
                   if only_ids else sorted(lab_dir.glob("*.json")))
    for lab_p in label_files:
        if not lab_p.exists():
            continue
        sid = lab_p.stem
        lab = json.loads(lab_p.read_text())
        text = (seg_dir / f"{sid}.txt").read_text(errors="ignore") if (seg_dir / f"{sid}.txt").exists() else ""
        meta_p = seg_dir / f"{sid}.meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        title = f"{meta.get('patient_file','')} — {meta.get('note_date','')} {meta.get('title','')}"
        cards.append(f"""
<div class=card data-id="{sid}">
  <h3>{esc(title)} <span style="color:#888">[{sid}]</span></h3>
  {render_context(meta.get('patient_file',''))}
  <div class=cols>
    <div class=note>{highlight(text, all_spans(lab))}</div>
    <div class=facts>{render_facts(lab)}</div>
  </div>
  <div class=ctl>
    <label class="v ok"><input type=radio name="v_{sid}" value=ok> ✓ looks right</label>
    <label class="v fix"><input type=radio name="v_{sid}" value=fix> ✗ needs fix</label>
    <textarea placeholder="if wrong: what's the correct fact? (e.g. 'dx date is 2016-07, not 2019'; 'drop the SBRT event'; 'GG should be 4')"></textarea>
  </div>
</div>""")
    doc = f"""<!doctype html><meta charset=utf-8><title>L1 gold review</title>
<style>{CSS}</style>
<header><b>L1 gold-label review</b>
<button onclick=downloadReview()>⬇ Download review</button>
<span style="font-weight:400">Read each note (left) vs the extracted facts (right); highlighted text = the AI's evidence. Mark ✓/✗ and note fixes. Then Download.</span>
<span id=prog></span></header>
{''.join(cards)}
<script>{JS}</script>"""
    out = gold / out_name
    out.write_text(doc)
    print(f"wrote {out}  ({len(cards)} notes)")
    print(f"open it in a browser:  file://{out.resolve()}")


if __name__ == "__main__":
    main()
