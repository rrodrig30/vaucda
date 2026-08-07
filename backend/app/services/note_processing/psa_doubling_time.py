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
    """PSADT intervals for the chart's PSA series, chronological. A rising phase
    is reported ONLY when it starts from a REAL nadir — a genuine treatment-
    response trough (>=50% drop from a prior peak) or a nadir that follows a
    documented definitive treatment — so pre-diagnosis rises and minor
    fluctuations are not reported as spurious doubling times."""
    series = _parse_psa(psa_data)
    tx_dates = _treatment_dates(chart_text)
    results = []
    for g in _rising_groups(series):
        r = _psadt_for_group(g)
        if r is not None and _is_real_nadir(r.nadir_ymd, r.nadir_val, series, tx_dates):
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


def build_psadt_section(psa_data: str, chart_text: str = "") -> str:
    """Gated (VAUCDA_PSADT, default on) rendered PSADT table, or '' if none.
    chart_text supplies treatment context for treatment-aware nadir detection."""
    if os.environ.get("VAUCDA_PSADT", "1") != "1":
        return ""
    try:
        return render_psadt_table(compute_psadt(psa_data, chart_text))
    except Exception:  # never break note assembly
        return ""
