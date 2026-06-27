#!/usr/bin/env python3
"""
Generate a human-readable HTML review page for the L1 gold labels.

For a clinician: shows each note next to the AI-extracted facts (with the
supporting quote highlighted in the note), with an OK / Needs-fix toggle and a
free-text correction box per note. NO JSON editing. A "Download review" button
saves your verdicts; re-run apply_review.py to fold them into the labels.

Usage:
  ./venv/bin/python scripts/l1/review_report.py <gold_dir>
  # opens tests/l1_gold/review.html
"""
import html
import json
import sys
from pathlib import Path


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


def render_facts(lab):
    rows = []
    dx = lab.get("diagnosis")
    if dx:
        rows.append("<div class=grp><b>Diagnosis</b><table>"
                    + f"<tr><td>type</td><td>{esc(dx.get('cancer_type'))}</td></tr>"
                    + f"<tr><td>dx date</td><td>{esc(dx.get('diagnosis_date'))}</td></tr>"
                    + f"<tr><td>Gleason / GG</td><td>{esc(dx.get('gleason'))} / GG{esc(dx.get('grade_group'))}</td></tr>"
                    + f"<tr><td>stage</td><td>{esc(dx.get('stage_tnm'))}</td></tr>"
                    + f"<tr><td>risk</td><td>{esc(dx.get('risk'))}</td></tr></table></div>")
    tev = lab.get("treatment_events") or []
    if tev:
        r = "<div class=grp><b>Treatments</b><table><tr><th>modality</th><th>agent</th><th>start</th><th>end</th><th>status</th></tr>"
        for e in tev:
            r += (f"<tr><td>{esc(e.get('modality'))}</td><td>{esc(e.get('agent'))}</td>"
                  f"<td>{esc(e.get('start_date'))}</td><td>{esc(e.get('end_date'))}</td>"
                  f"<td>{esc(e.get('status'))}</td></tr>")
        rows.append(r + "</table></div>")
    pr = lab.get("procedures") or []
    if pr:
        r = "<div class=grp><b>Procedures</b><table><tr><th>type</th><th>date</th><th>finding</th></tr>"
        for p in pr:
            r += f"<tr><td>{esc(p.get('type'))}</td><td>{esc(p.get('date'))}</td><td>{esc(p.get('finding'))}</td></tr>"
        rows.append(r + "</table></div>")
    mets = lab.get("metastases") or []
    if mets:
        r = "<div class=grp><b>Metastases</b><table><tr><th>site</th><th>date</th></tr>"
        for m in mets:
            r += f"<tr><td>{esc(m.get('site'))}</td><td>{esc(m.get('date'))}</td></tr>"
        rows.append(r + "</table></div>")
    return "".join(rows) or "<i>no facts extracted</i>"


def all_spans(lab):
    spans = []
    dx = lab.get("diagnosis")
    if dx and dx.get("source_span"):
        spans.append(dx["source_span"])
    for k in ("treatment_events", "procedures", "metastases"):
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
    seg_dir, lab_dir = gold / "segments", gold / "labels"
    cards = []
    for lab_p in sorted(lab_dir.glob("*.json")):
        sid = lab_p.stem
        lab = json.loads(lab_p.read_text())
        text = (seg_dir / f"{sid}.txt").read_text(errors="ignore") if (seg_dir / f"{sid}.txt").exists() else ""
        meta_p = seg_dir / f"{sid}.meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        title = f"{meta.get('patient_file','')} — {meta.get('note_date','')} {meta.get('title','')}"
        cards.append(f"""
<div class=card data-id="{sid}">
  <h3>{esc(title)} <span style="color:#888">[{sid}]</span></h3>
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
    out = gold / "review.html"
    out.write_text(doc)
    print(f"wrote {out}  ({len(cards)} notes)")
    print(f"open it in a browser:  file://{out.resolve()}")


if __name__ == "__main__":
    main()
