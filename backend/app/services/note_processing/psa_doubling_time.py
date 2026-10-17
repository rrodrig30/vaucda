"""Deterministic PSA doubling-time (PSADT), one per continuously-rising group.

A prostate-cancer PSA series can contain SEVERAL distinct rising phases, each
separated by a treatment-induced drop to a new nadir — e.g. biochemical
recurrence after radical prostatectomy gives one rising phase, then salvage
radiation drives PSA to a NEW nadir before it rises again from a new source of
progression. Each rising phase gets its OWN doubling time, computed from the
NADIR (group minimum / start) to the HIGHEST PSA of that group, dated over the
interval. LLM-free.

Grouping rule (per provider spec): a PSA stays in the current rising group as
long as it is NOT a significant drop from the prior value — an identical value
is allowed, and a value within <10% below the prior is allowed (natural PSA
variability). A drop of >=10% ends the group and begins a new nadir.

PSADT = ln(2) * dt_months / ln(PSA_peak / PSA_nadir)   (nadir -> peak, two-point)
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_MON3 = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

Ymd = Tuple[int, int, int]


@dataclass
class PSADTResult:
    nadir_ymd: Ymd
    nadir_val: float
    peak_ymd: Ymd
    peak_val: float
    n_points: int          # PSAs in the rising group
    psadt_months: Optional[float]


def _parse_psa(psa_data: str) -> List[Tuple[Ymd, float]]:
    """Parse '(Mon DD, YYYY [time]  <?VALUE [H])' PSA lines -> chronological
    [((y,m,d), value)]. Handles '<0.01' (undetectable) as its numeric value and
    de-dupes identical (date,value)."""
    out: List[Tuple[Ymd, float]] = []
    pat = re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})[^\n]*?(<?\s*\d+\.\d+)",
                     re.IGNORECASE)
    seen = set()
    for m in pat.finditer(psa_data or ""):
        mo = _MON3.get(m.group(1)[:3].lower())
        if not mo:
            continue
        d, y = int(m.group(2)), int(m.group(3))
        try:
            v = float(m.group(4).replace("<", "").strip())
        except ValueError:
            continue
        if not (1900 <= y <= 2100 and 1 <= d <= 31):
            continue
        key = ((y, mo, d), v)
        if key in seen:
            continue
        seen.add(key)
        out.append(((y, mo, d), v))
    out.sort(key=lambda p: p[0])
    return out


def _days_between(a: Ymd, b: Ymd) -> int:
    from datetime import date
    return (date(*b) - date(*a)).days


def _allowed_drop(prev_v: float) -> float:
    """Largest drop from prev_v that is still 'natural variability' (stays in the
    group). LOW RANGE (<1.0 ng/mL) is intentionally more forgiving — a 10% swing
    there is a tiny absolute change / assay noise — so a minor low fluctuation
    can't fragment a rising trend: up to 20% or an absolute floor of 0.05 ng/mL.
    At/above 1.0 the standard 10% applies."""
    if prev_v < 1.0:
        return max(0.20 * prev_v, 0.05)
    return 0.10 * prev_v


def _rising_groups(series: List[Tuple[Ymd, float]]) -> List[List[Tuple[Ymd, float]]]:
    """Segment into runs separated by a SIGNIFICANT drop. Within a run, rising,
    equal, and minor dips (per _allowed_drop) are kept."""
    if not series:
        return []
    groups, cur = [], [series[0]]
    for i in range(1, len(series)):
        prev_v, cur_v = series[i - 1][1], series[i][1]
        if cur_v >= prev_v - _allowed_drop(prev_v):
            cur.append(series[i])
        else:
            groups.append(cur)
            cur = [series[i]]
    groups.append(cur)
    return groups


# STRONG definitive-treatment phrases only (bare "RP"/"radiation" match note
# headers and generic prose, so they are excluded) with a TIGHTLY-adjacent date.
_TX_KW = re.compile(
    r"(?:radical\s+prostatectomy|prostatectom\w*|\bRRP\b|\bRALP\b|"
    r"\bEBRT\b|\bXRT\b|\bIMRT\b|\bVMAT\b|brachytherap\w*|\bSBRT\b|"
    r"salvage\s+(?:radiation|radiotherapy|rt)|external\s+beam(?:\s+radiation)?|"
    r"radiation\s+therapy|radiotherapy)", re.I)
# date must sit within ~30 chars AFTER the treatment phrase (or ~10 before) —
# "s/p RRP 2018", "prostatectomy 1/2022", "completion of XRT 6/2025"
_DATE_TOK = re.compile(r"(\d{1,2})[/-](?:(\d{1,2})[/-])?((?:19|20)\d{2})|\b((?:19|20)\d{2})\b")

# Radical prostatectomy — PSADT is only reported for post-RP biochemical
# recurrence (PSA > 0.2). Intact-prostate / radiation-only patients use the
# Phoenix nadir+2 definition instead, not this table.
# UNAMBIGUOUS radical prostatectomy (incl. retropubic / perineal / robotic / lap
# variants and the RRP/RALP/RARP abbreviations).
_RP_RE = re.compile(
    r"radical\s+(?:retropubic\s+|perineal\s+|robotic\s+|robot[\s-]?assisted\s+|"
    r"laparoscopic\s+)?prostatectomy|\bRRP\b|\bRALP\b|\bRARP\b|"
    r"robot\w*[\s\w-]{0,25}?prostatectomy|laparoscopic[\s\w-]{0,25}?prostatectomy",
    re.I)
_RP_BARE = re.compile(r"\bprostatectomy\b", re.I)
# The patient actually UNDERWENT it — a bare "prostatectomy" only counts as the
# patient's own history near one of these anchors.
_PT_HAD_ANCHOR = re.compile(
    r"s/?p\b|status[\s-]?post|post[\s-]?op|underw\w+|had\s+(?:a\s+)?|"
    r"history\s+of|\bh/?o\b|prior\s+|previous\s+|following\s+|after\s+", re.I)
# Contexts where a bare "prostatectomy" is NOT the patient's own radical RP:
#  - BPH procedures that leave prostate tissue (TURP / HoLEP / simple / enucleation)
#  - family history (brother/father/…)
#  - hypothetical / options / declined / template menus
_NONRADICAL_OR_HYPO = re.compile(
    r"\bturp\b|\(turp\)|holep|holmium|enucleation|transurethral|simple\s+prostatectomy|"
    r"brother|father|sibling|\bson\b|paternal|maternal|family|uncle|relative|"
    r"\bdad\b|\bmom\b|grandfather|grandpa|grandmother|grandpa|"      # colloquial family hx
    r"option|choos|interested|includ|discuss|candidate|proceed|consider|"
    r"\bvs\.?\b|versus|declin|recommend|offer|elect|"
    # a treatment-OPTIONS menu lists RP next to other definitive modalities
    r"brachytherap|perineal\s+prostatectomy\b|hormone\s+therapy",
    re.I)

# HYPOTHETICAL / PREDICTIVE constructions checked in a TIGHT window immediately
# around the RP phrase — a bare radical-prostatectomy mention that is a
# conditional ("would be possible"), a genomic-classifier prediction ("risk of
# adverse pathology at radical prostatectomy", Decipher/Oncotype/GPS), or
# counseling is NOT a performed surgery and must not license PSADT. Kept tight
# (adjacent only) so it never suppresses a real, terse "s/p RRP 1996".
_HYPOTHETICAL_RP = re.compile(
    r"would\b|could\b|\bpossible\b|potential|adverse\s+pathology|risk\s+of\b|"
    r"\bGPS\b|decipher|oncotype|prolaris|nomogram|not\s+a\s+candidate|"
    r"questions?\s+about|counsel|planning\s+(?:for|to)|awaiting|considering|"
    # nomogram / outcome-prediction tables: "progression-free probability AFTER
    # radical prostatectomy / 5 YR 88%" is a projected statistic, not a surgery.
    r"probability|progression[\s-]?free|free[\s-]?survival|\d\s*%",
    re.I)
# Post-RP biochemical-recurrence PSA threshold.
_BCR_PSA_THRESHOLD = 0.2

# Explicit clinician correction that the patient had RADIATION, not surgery — an
# erroneous "status post prostatectomy" note that was corrected must not license
# PSADT. When present, only UNAMBIGUOUS radical-RP evidence counts (not a bare
# narrative "prostatectomy", which is exactly what gets copied-forward in error).
_SURGERY_CORRECTION_RE = re.compile(
    r"treated\s+with\s+(?:xrt|radiation|ebrt|imrt|sbrt|radiotherapy)[^.\n]{0,25}?,?\s*"
    r"not\s+surg\w*|radiation[,\s]+not\s+(?:surgery|surgical|prostatectomy)|"
    r"\bnot\s+surgery\b|(?:did\s+not|never|has\s+not)\s+(?:have|undergo|had)\s+"
    r"(?:a\s+)?(?:surgery|prostatectomy)|denies\s+(?:any\s+)?(?:surgery|prostatectomy)",
    re.IGNORECASE,
)


def _had_radical_prostatectomy(chart: str) -> bool:
    if not chart:
        return False
    _corrected = bool(_SURGERY_CORRECTION_RE.search(chart))
    # Unambiguous radical prostatectomy — but only if that very phrase isn't itself
    # in a hypothetical/options/menu context (e.g. "radical prostatectomy vs XRT").
    for m in _RP_RE.finditer(chart):
        win = chart[max(0, m.start() - 70):m.end() + 40]
        tight = chart[max(0, m.start() - 45):m.end() + 30]
        if not _NONRADICAL_OR_HYPO.search(win) and not _HYPOTHETICAL_RP.search(tight):
            return True
    # A bare "prostatectomy" counts ONLY when the patient clearly underwent it
    # (s/p / status-post / underwent anchor nearby) AND it isn't a BPH procedure,
    # family history, or a hypothetical/options mention. Skipped entirely when the
    # chart corrects the record to radiation-not-surgery (strong RP above still
    # counts; a bare narrative 'prostatectomy' does not).
    if _corrected:
        return False
    for m in _RP_BARE.finditer(chart):
        win = chart[max(0, m.start() - 80):m.end() + 40]
        tight = chart[max(0, m.start() - 45):m.end() + 30]
        if (_PT_HAD_ANCHOR.search(win) and not _NONRADICAL_OR_HYPO.search(win)
                and not _HYPOTHETICAL_RP.search(tight)):
            return True
    return False


def _treatment_dates(chart: str) -> List[Ymd]:
    """Dates of documented definitive treatments (RP / radiation / salvage) for
    treatment-aware nadir detection. Deliberately conservative — a missed date is
    fine (the >=50% drop test carries the common case); a false one is not."""
    out: List[Ymd] = []
    if not chart:
        return out
    for km in _TX_KW.finditer(chart):
        window = chart[km.start():km.end() + 30]        # forward-adjacent only
        dm = _DATE_TOK.search(window)
        if not dm:
            continue
        if dm.group(4):                                 # bare 4-digit year
            y, mm, dd = int(dm.group(4)), 6, 15
        else:
            mm = int(dm.group(1))
            y = int(dm.group(3))
            dd = int(dm.group(2)) if dm.group(2) and 1 <= int(dm.group(2)) <= 31 else 15
            if not (1 <= mm <= 12):
                continue
        if 1990 <= y <= 2100:
            out.append((y, mm, dd))
    return out


def _is_real_nadir(nadir_ymd: Ymd, nadir_val: float,
                   series: List[Tuple[Ymd, float]], tx_dates: List[Ymd]) -> bool:
    """A REAL nadir is a genuine treatment-response trough, not a minor dip.
    When earlier PSA exists, require a >=50% drop from the highest prior PSA — the
    treatment-induced fall is itself the treatment signal, so this is robust to
    noisy treatment-date parsing. Only when the record STARTS at this nadir (no
    earlier PSA) do we fall back to documented treatment, and only for a clearly
    post-treatment low (<0.5 ng/mL) so a pre-diagnosis opening value can't slip
    through on a stray date."""
    prior = [v for (d, v) in series if d < nadir_ymd]
    if prior:
        return nadir_val <= max(prior) * 0.5
    return nadir_val < 0.5 and any(td < nadir_ymd for td in tx_dates)


def _psadt_for_group(group: List[Tuple[Ymd, float]]) -> Optional[PSADTResult]:
    """Doubling time from the group's nadir (min value / earliest) to its highest
    PSA. None unless the group genuinely RISES to a later, higher peak."""
    if len(group) < 2:
        return None
    nadir = min(group, key=lambda p: (p[1], p[0]))     # lowest value, earliest
    peak = max(group, key=lambda p: (p[1], p[0]))      # highest value, latest
    if peak[1] <= nadir[1] or peak[0] <= nadir[0]:
        return None                                    # not a rise to a later peak
    days = _days_between(nadir[0], peak[0])
    if days <= 0:
        return None
    months = days / 30.4375
    try:
        psadt = months * math.log(2) / math.log(peak[1] / nadir[1])
    except (ValueError, ZeroDivisionError):
        psadt = None
    # count PSAs from the nadir date through the peak date (the rising span)
    n = sum(1 for p in group if nadir[0] <= p[0] <= peak[0])
    return PSADTResult(nadir[0], nadir[1], peak[0], peak[1], n, psadt)


def compute_psadt(psa_data: str, chart_text: str = "") -> List[PSADTResult]:
    """PSADT intervals for the chart's PSA series, chronological. Reported ONLY for
    post-RADICAL-PROSTATECTOMY patients whose PSA has risen above 0.2 ng/mL
    (post-RP biochemical recurrence) — not intact-prostate / radiation-only
    patients. A rising phase must also start from a REAL nadir (a >=50% drop from a
    prior peak, or a nadir following a documented definitive treatment), so
    pre-diagnosis rises and minor fluctuations are not reported."""
    if not _had_radical_prostatectomy(chart_text):
        return []
    series = _parse_psa(psa_data)
    tx_dates = _treatment_dates(chart_text)
    results = []
    for g in _rising_groups(series):
        r = _psadt_for_group(g)
        if (r is not None and r.peak_val > _BCR_PSA_THRESHOLD
                and _is_real_nadir(r.nadir_ymd, r.nadir_val, series, tx_dates)):
            results.append(r)
    return results


def _fmt_date(ymd: Ymd) -> str:
    return f"{ymd[1]:02d}/{ymd[2]:02d}/{ymd[0]}"


def _fmt_psadt(months: Optional[float]) -> str:
    if months is None:
        return "n/a"
    if months >= 24:
        return f"{months:.1f} mo (~{months / 12:.1f} yr)"
    return f"{months:.1f} mo"


def render_psadt_table(results: List[PSADTResult]) -> str:
    """ASCII table of one row per rising interval. '' when nothing to show."""
    if not results:
        return ""
    rows = []
    for r in results:
        rows.append((
            f"{_fmt_date(r.nadir_ymd)} - {_fmt_date(r.peak_ymd)}",
            f"{r.nadir_val:g} -> {r.peak_val:g}",
            str(r.n_points),
            _fmt_psadt(r.psadt_months),
        ))
    h = ("Interval (nadir -> peak)", "PSA ng/mL", "# PSAs", "PSADT")
    w = [max(len(h[i]), *(len(row[i]) for row in rows)) for i in range(4)]
    line = "+-" + "-+-".join("-" * w[i] for i in range(4)) + "-+"
    def fmt(cells):
        return "| " + " | ".join(cells[i].ljust(w[i]) for i in range(4)) + " |"
    out = ["PSA DOUBLING TIME (auto-calculated from the PSA curve — provider to "
           "VERIFY; each interval is a distinct rising phase from its nadir):",
           line, fmt(h), line]
    out += [fmt(r) for r in rows]
    out.append(line)
    return "\n".join(out)


# A post-RP PSA at/above this is "detectable and rising" but still below the 0.2
# biochemical-recurrence threshold — worth flagging, not yet worth a PSADT.
_BCR_DETECTABLE_FLOOR = 0.1


def subthreshold_psadt_note(psa_data: str, chart_text: str = "") -> str:
    """One explanatory line for the post-RADICAL-PROSTATECTOMY patient whose PSA is
    detectable and rising from a real nadir but has NOT yet reached the 0.2 ng/mL
    biochemical-recurrence threshold — so a PSADT is intentionally not calculated.
    Makes the omission explicit (vs looking like missing data). '' otherwise.

    Uses the SAME gates as compute_psadt (post-RP, real nadir) so it can only fire
    for exactly the patients a PSADT would apply to once they cross 0.2."""
    if not _had_radical_prostatectomy(chart_text):
        return ""
    # If a qualifying (>=0.2) interval exists, the table already covers it.
    if compute_psadt(psa_data, chart_text):
        return ""
    series = _parse_psa(psa_data)
    tx_dates = _treatment_dates(chart_text)
    best: Optional[PSADTResult] = None
    for g in _rising_groups(series):
        r = _psadt_for_group(g)
        if (r is not None and _BCR_DETECTABLE_FLOOR <= r.peak_val < _BCR_PSA_THRESHOLD
                and _is_real_nadir(r.nadir_ymd, r.nadir_val, series, tx_dates)):
            if best is None or r.peak_val > best.peak_val:
                best = r
    if best is None:
        return ""
    return (f"PSA detectable and rising post-prostatectomy ({best.peak_val:g} ng/mL) "
            f"but below the {_BCR_PSA_THRESHOLD:g} ng/mL biochemical-recurrence "
            f"threshold; PSA doubling time not yet calculated.")


def build_psadt_section(psa_data: str, chart_text: str = "") -> str:
    """Gated (VAUCDA_PSADT, default on) rendered PSADT table, or '' if none.
    chart_text supplies treatment context for treatment-aware nadir detection.
    When no >=0.2 interval qualifies, a rising sub-threshold post-RP PSA gets a
    one-line explanation instead."""
    if os.environ.get("VAUCDA_PSADT", "1") != "1":
        return ""
    try:
        table = render_psadt_table(compute_psadt(psa_data, chart_text))
        return table if table else subthreshold_psadt_note(psa_data, chart_text)
    except Exception:  # never break note assembly
        return ""
