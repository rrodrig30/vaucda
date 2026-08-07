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


def _rising_groups(series: List[Tuple[Ymd, float]]) -> List[List[Tuple[Ymd, float]]]:
    """Segment into runs separated by a >=10% drop. Within a run, rising / equal /
    <10% dips are all kept (natural variability)."""
    if not series:
        return []
    groups, cur = [], [series[0]]
    for i in range(1, len(series)):
        prev_v, cur_v = series[i - 1][1], series[i][1]
        # a drop of <10% (or any rise / equality) keeps the group going
        if cur_v > prev_v * 0.90:
            cur.append(series[i])
        else:
            groups.append(cur)
            cur = [series[i]]
    groups.append(cur)
    return groups


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


def compute_psadt(psa_data: str) -> List[PSADTResult]:
    """PSADT intervals for the chart's PSA series, chronological. A true nadir is
    a TROUGH — every group after the first begins after a >=10% drop, so its start
    is a genuine post-decline nadir. The FIRST group is the record's opening phase;
    it is a real nadir only when the record itself starts at a (low) post-treatment
    nadir — so it is skipped when it opens from a higher pre-treatment baseline
    (>=0.5 ng/mL), which would otherwise lump the lifetime diagnostic rise into one
    bogus interval."""
    series = _parse_psa(psa_data)
    groups = _rising_groups(series)
    results = []
    for gi, g in enumerate(groups):
        if gi == 0 and min(p[1] for p in g) >= 0.5:
            continue
        r = _psadt_for_group(g)
        if r is not None:
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


def build_psadt_section(psa_data: str) -> str:
    """Gated (VAUCDA_PSADT, default on) rendered PSADT table, or '' if none."""
    if os.environ.get("VAUCDA_PSADT", "1") != "1":
        return ""
    try:
        return render_psadt_table(compute_psadt(psa_data))
    except Exception:  # never break note assembly
        return ""
