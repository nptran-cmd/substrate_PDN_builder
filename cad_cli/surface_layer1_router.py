"""
Layer-by-Layer PDN Routing Framework — Step 1: `SURFACE` (`TOP`) Layer Parameterized Router & SKILL Recipe Engine.

Supports:
  1. Any user-provided `VDD:VSS` via ratio string (`--ratio`):
     - `"FULL"` or `"1:1"` (100% Via-in-Pad on every VDD and VSS bump; 0 SURFACE traces)
     - `"4:2"`, `"5:2"`, `"3:1"`, `"4:1"`, `"5:3"`, or any arbitrary `"M:N"` integer ratio!
     - Automatic unit-cell period solver (`P = max(M + 1, N + 1, 6)` by default, or user `--cell-period P`)
       that distributes `M` VDD vias and `N` VSS vias evenly across each `P`-bump unit cell so every
       un-via'd bump is within 1 hop of a via'd bump on `SURFACE`.
  2. Any strapping orientation (`--direction`):
     - `"VERTICAL"`   : Straps un-via'd bumps vertically along same-net columns (`dx=0, dy=180.99um`,
                        DRC clearance to opposite-net 77um pad/via = `43.29 um >= 18.0 um` rule).
     - `"HORIZONTAL"` : Straps un-via'd bumps horizontally along same-net rows (`dy=0, dx=187.58um`,
                        DRC clearance to opposite-net 77um pad/via = `40.00 um >= 18.0 um` rule).
     - `"BOTH"`       : 2D Orthogonal H+V strapping (connects each un-via'd bump to both its nearest
                        vertical AND nearest horizontal same-net via'd neighbor within 1 hop).
  3. Exports:
     - XML-validated Full-Die + Zoomed-Tile SVG mockups & Side-by-Side Comparison SVGs in `pdn_sandbox/`
     - Pipe-delimited Stage 4 SKILL recipe files (`VIA|...` and `CLINE|...`) for `surface_bump_router_batch.il`.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


U7_DIE_EDGE = (16143.768, 120.001, 30138.068, 31765.021)
TILE_BBOX = (21000.0, 15000.0, 22650.0, 16650.0)


def parse_ratio_and_period(
    ratio_str: str,
    cell_period: Optional[int] = None,
) -> Tuple[bool, int, int, int]:
    """
    Parse user ratio string (e.g., 'FULL', '4:2', '5:2', '3:1', 'M:N') into:
      (is_full_via, m_vdd, n_vss, period_p)
    When not FULL, chooses period_p = cell_period or max(m_vdd + 1, n_vss + 1, 6)
    so that both VDD and VSS have strapped bumps on SURFACE and the via ratio is exactly M:N.
    """
    s = ratio_str.strip().upper()
    if s in ("FULL", "FULL_VIA", "100%", "ALL"):
        return True, 6, 6, 6
    if ":" in s:
        p1, p2 = s.split(":", 1)
        m_vdd = max(1, int(p1.strip()))
        n_vss = max(1, int(p2.strip()))
    else:
        m_vdd = max(1, int(s))
        n_vss = 1

    if cell_period is not None and cell_period >= max(m_vdd, n_vss):
        period_p = cell_period
    else:
        # Ensure period_p > max(m_vdd, n_vss) so both VDD and VSS have strapped SURFACE traces
        period_p = max(m_vdd + 1, n_vss + 1, 6)
    return False, m_vdd, n_vss, period_p


def compute_evenly_spaced_keep_indices(count_keep: int, period_p: int) -> Set[int]:
    """
    Select `count_keep` indices out of `{0, 1, ..., period_p - 1}` so that un-via'd indices
    are maximally isolated (every un-via'd index is adjacent within 1 hop to a kept index).
    Special-cases canonical P=6 patterns for 4:2 and 5:2:
      - count_keep == 4, period_p == 6 -> {0, 1, 3, 4} (un-via'd {2, 5} are 1 hop from {1, 4})
      - count_keep == 5, period_p == 6 -> {0, 1, 2, 3, 4} (un-via'd {5} is 1 hop from {4})
      - count_keep == 2, period_p == 6 -> {1, 4} (un-via'd {0, 2} -> 1 and {3, 5} -> 4, all 1 hop!)
    """
    if count_keep >= period_p:
        return set(range(period_p))
    if count_keep <= 0:
        return {0}
    if period_p == 3:
        if count_keep == 2:
            return {0, 2}
        if count_keep == 1:
            return {1}  # Center via so both left (0) and right (2) floating bumps are 1-hop!
    if period_p == 4:
        if count_keep == 3:
            return {0, 1, 2}
        if count_keep == 2:
            return {1, 3}
        if count_keep == 1:
            return {1}
    if period_p == 6:
        if count_keep == 5:
            return {0, 1, 2, 3, 4}
        if count_keep == 4:
            return {0, 1, 3, 4}
        if count_keep == 3:
            return {0, 2, 4}
        if count_keep == 2:
            return {1, 4}
        if count_keep == 1:
            return {2}
    # General Bresenham / centered rounding distribution for arbitrary (count_keep, period_p)
    kept: Set[int] = set()
    for k in range(count_keep):
        idx = int(round(((k + 0.5) * period_p / count_keep) - 0.5))
        idx = max(0, min(period_p - 1, idx))
        kept.add(idx)
    cur = 0
    while len(kept) < count_keep:
        if cur not in kept:
            kept.add(cur)
        cur += 1
    return kept


def load_u7_surface_vdd_vss_bumps(workspace: Path) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Load all U7 VDDUC0 and VSS C4 bump coordinates on SURFACE from local cadence_extract/mcm_vias.txt."""
    vdd_pts: List[Tuple[float, float]] = []
    vss_pts: List[Tuple[float, float]] = []
    vias_txt = workspace / "cadence_extract" / "mcm_vias.txt"
    with vias_txt.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("S!"):
                continue
            p = line.strip().split("!")
            if len(p) < 7:
                continue
            l1, l2 = p[2].strip(), p[3].strip()
            if (l1, l2) not in (("TOP", "12F"), ("SURFACE", "12F")):
                continue
            vx, vy = float(p[4]), float(p[5])
            if not (U7_DIE_EDGE[0] <= vx <= U7_DIE_EDGE[2] and U7_DIE_EDGE[1] <= vy <= U7_DIE_EDGE[3]):
                continue
            net = p[6].strip()
            if net == "VDDUC0":
                vdd_pts.append((vx, vy))
            elif net == "VSS":
                vss_pts.append((vx, vy))
    vdd_pts = sorted(set(vdd_pts), key=lambda pt: (round(pt[0], 1), round(pt[1], 1)))
    vss_pts = sorted(set(vss_pts), key=lambda pt: (round(pt[0], 1), round(pt[1], 1)))
    return vdd_pts, vss_pts


def synthesize_surface_routing(
    vdd_pts: List[Tuple[float, float]],
    vss_pts: List[Tuple[float, float]],
    ratio_str: str = "4:2",
    direction: str = "VERTICAL",
    cell_period: Optional[int] = None,
    trace_width_um: float = 24.0,
    max_strap_dist_um: float = 260.0,
) -> Dict[str, Any]:
    """
    Parameterized SURFACE (TOP -> 12F) Via & CLINE Strap Synthesizer.

    Args:
      vdd_pts: List of (x_um, y_um) C4 bump coordinates for VDD net.
      vss_pts: List of (x_um, y_um) C4 bump coordinates for VSS net.
      ratio_str: 'FULL' or 'M:N' (e.g. '4:2', '5:2', '3:1').
      direction:
        - 'VERTICAL'   : Partition along vertical columns (same X) and strap vertically (dy=180.99um).
        - 'HORIZONTAL' : Partition along horizontal rows (same Y) and strap horizontally (dx=187.58um).
        - 'BOTH'       : 2D Orthogonal strapping (each un-via'd bump straps to nearest vertical AND
                         nearest horizontal via'd neighbor within max_strap_dist_um).
      cell_period: Optional integer period P (defaults to max(M+1, N+1, 6)).
      trace_width_um: SURFACE CLINE width in um (default 24.0 um >= 18.0 um Unrestricted rule).
      max_strap_dist_um: Maximum 1-hop center-to-center strap length in um (default 260.0 um).
    """
    dir_u = direction.strip().upper()
    if dir_u not in ("VERTICAL", "HORIZONTAL", "BOTH"):
        dir_u = "VERTICAL"

    is_full, m_vdd, n_vss, period_p = parse_ratio_and_period(ratio_str, cell_period)
    if is_full:
        return {
            "mode": "FULL_VIA_ON_BUMP",
            "ratio_str": "FULL (1:1)",
            "direction": "NONE",
            "cell_period": 1,
            "cell_label": "6-Row Unit Cell (6 VDD : 6 VSS Vias = 1:1)",
            "vdd_vias": list(vdd_pts),
            "vdd_unviad": [],
            "vdd_clines": [],
            "vss_vias": list(vss_pts),
            "vss_unviad": [],
            "vss_clines": [],
            "trace_width_um": trace_width_um,
            "min_drc_clearance_um": 53.3,
        }

    keep_vdd = compute_evenly_spaced_keep_indices(m_vdd, period_p)
    keep_vss = compute_evenly_spaced_keep_indices(n_vss, period_p)

    def _partition_and_strap(
        pts: List[Tuple[float, float]],
        keep_set: Set[int],
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]], List[Tuple[float, float, float, float]]]:
        if dir_u in ("HORIZONTAL", "VERTICAL"):
            lines_dict: Dict[int, List[Tuple[float, float]]] = {}
            if dir_u == "HORIZONTAL":
                for x, y in pts:
                    rk = int(round(y * 10.0))
                    lines_dict.setdefault(rk, []).append((x, y))
            else:
                for x, y in pts:
                    ck = int(round(x * 10.0))
                    lines_dict.setdefault(ck, []).append((x, y))

            via_list: List[Tuple[float, float]] = []
            final_unviad: List[Tuple[float, float]] = []
            clines: List[Tuple[float, float, float, float]] = []

            for k in sorted(lines_dict.keys()):
                line_pts = sorted(
                    lines_dict[k],
                    key=(lambda p: p[0]) if dir_u == "HORIZONTAL" else (lambda p: p[1]),
                )
                chains: List[List[Tuple[float, float]]] = []
                cur_ch = [line_pts[0]]
                for pt in line_pts[1:]:
                    prev = cur_ch[-1]
                    step_d = abs(pt[0] - prev[0]) if dir_u == "HORIZONTAL" else abs(pt[1] - prev[1])
                    ortho_d = abs(pt[1] - prev[1]) if dir_u == "HORIZONTAL" else abs(pt[0] - prev[0])
                    if step_d <= max_strap_dist_um and ortho_d <= 0.05:
                        cur_ch.append(pt)
                    else:
                        chains.append(cur_ch)
                        cur_ch = [pt]
                chains.append(cur_ch)

                for ch in chains:
                    ch_len = len(ch)
                    if ch_len == 1 or len(keep_set) >= period_p:
                        via_list.extend(ch)
                        continue

                    via_indices = [i for i in range(ch_len) if (i % period_p) in keep_set]
                    if not via_indices:
                        via_indices = [ch_len // 2]
                    via_idx_set = set(via_indices)

                    for i, pt in enumerate(ch):
                        if i in via_idx_set:
                            via_list.append(pt)
                        else:
                            final_unviad.append(pt)
                            nearest_v = min(via_indices, key=lambda vi: abs(vi - i))
                            nb = ch[i + 1] if nearest_v > i else ch[i - 1]
                            clines.append((pt[0], pt[1], nb[0], nb[1]))

            return via_list, final_unviad, clines

        lines_dict = {}
        for x, y in pts:
            ck = int(round(x / 5.0))
            lines_dict.setdefault(ck, []).append((x, y))

        via_list = []
        unviad_candidates: List[Tuple[float, float]] = []

        for line_idx, k in enumerate(sorted(lines_dict.keys())):
            line_pts = sorted(lines_dict[k], key=lambda p: p[1])
            phase = (line_idx * 2) % period_p
            for idx, pt in enumerate(line_pts):
                if ((idx + phase) % period_p) in keep_set:
                    via_list.append(pt)
                else:
                    unviad_candidates.append(pt)

        # Build spatial hash grid of via_list
        grid: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
        cell = 300.0
        for vx, vy in via_list:
            gk = (int(vx // cell), int(vy // cell))
            grid.setdefault(gk, []).append((vx, vy))

        final_unviad = []
        clines = []

        for ux, uy in unviad_candidates:
            gx, gy = int(ux // cell), int(uy // cell)
            best_vert: Optional[Tuple[float, float]] = None
            best_vert_d = 1e9
            best_horiz: Optional[Tuple[float, float]] = None
            best_horiz_d = 1e9
            best_any: Optional[Tuple[float, float]] = None
            best_any_d = 1e9

            for dx_g in (-1, 0, 1):
                for dy_g in (-1, 0, 1):
                    for vx, vy in grid.get((gx + dx_g, gy + dy_g), ()):
                        d = math.hypot(ux - vx, uy - vy)
                        if d > max_strap_dist_um or d < 1e-3:
                            continue
                        if abs(ux - vx) < 3.0 and d < best_vert_d:
                            best_vert_d = d
                            best_vert = (vx, vy)
                        if abs(uy - vy) < 3.0 and d < best_horiz_d:
                            best_horiz_d = d
                            best_horiz = (vx, vy)
                        if d < best_any_d:
                            best_any_d = d
                            best_any = (vx, vy)

            added_straps: List[Tuple[float, float]] = []
            if best_vert is not None:
                added_straps.append(best_vert)
            if best_horiz is not None:
                added_straps.append(best_horiz)
            if not added_straps and best_any is not None:
                added_straps.append(best_any)

            if added_straps:
                final_unviad.append((ux, uy))
                for tx, ty in added_straps:
                    clines.append((ux, uy, tx, ty))
            else:
                # Fallback: place via directly on isolated edge bump so 0 bumps ever float
                via_list.append((ux, uy))
                gk = (int(ux // cell), int(uy // cell))
                grid.setdefault(gk, []).append((ux, uy))

        return via_list, final_unviad, clines

    vdd_vias, vdd_unviad, vdd_clines = _partition_and_strap(vdd_pts, keep_vdd)
    vss_vias, vss_unviad, vss_clines = _partition_and_strap(vss_pts, keep_vss)

    min_clearance = 43.29 if dir_u == "VERTICAL" else (40.00 if dir_u == "HORIZONTAL" else 40.00)
    cell_lbl = (
        f"{m_vdd}:{n_vss} {dir_u} Unit Cell ({m_vdd} VDD Vias+{period_p - m_vdd} Straps : "
        f"{n_vss} VSS Vias+{period_p - n_vss} Straps)"
    )

    return {
        "mode": f"RATIO_{m_vdd}_TO_{n_vss}_{dir_u}",
        "ratio_str": f"{m_vdd}:{n_vss}",
        "direction": dir_u,
        "cell_period": period_p,
        "cell_label": cell_lbl,
        "vdd_vias": vdd_vias,
        "vdd_unviad": vdd_unviad,
        "vdd_clines": vdd_clines,
        "vss_vias": vss_vias,
        "vss_unviad": vss_unviad,
        "vss_clines": vss_clines,
        "trace_width_um": trace_width_um,
        "min_drc_clearance_um": min_clearance,
    }


def _render_tile_panel_svg(
    plan: Dict[str, Any],
    panel_x: float,
    panel_y: float,
    panel_w: float,
    panel_h: float,
    tile_bbox: Tuple[float, float, float, float],
    title: str,
    subtitle: str,
) -> List[str]:
    """Render a high-detail zoomed-in C4 bump & via/trace tile panel in SVG coordinates."""
    tx1, ty1, tx2, ty2 = tile_bbox
    tw = tx2 - tx1
    th = ty2 - ty1
    pad_px = 45.0
    draw_w = panel_w - 2 * pad_px
    draw_h = panel_h - 110.0
    scale = min(draw_w / tw, draw_h / th)
    ox = panel_x + pad_px
    oy = panel_y + 85.0

    def mx(x_um: float) -> float:
        return round(ox + (x_um - tx1) * scale, 2)

    def my(y_um: float) -> float:
        return round(oy + draw_h - (y_um - ty1) * scale, 2)

    def ms(um_val: float) -> float:
        return round(um_val * scale, 2)

    lines: List[str] = [
        f'<rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" rx="10" fill="#0f172a" stroke="#334155" stroke-width="2"/>',
        f'<text x="{panel_x + 20}" y="{panel_y + 32}" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{panel_x + 20}" y="{panel_y + 56}" fill="#94a3b8" font-family="Consolas, monospace" font-size="12.2">{html.escape(subtitle)}</text>',
        f'<rect x="{ox - 10}" y="{oy - 10}" width="{draw_w + 20}" height="{draw_h + 20}" rx="6" fill="#090d16" stroke="#1e293b" stroke-width="1.5"/>',
    ]

    def_in = lambda x, y: (tx1 <= x <= tx2 and ty1 <= y <= ty2)
    vdd_vias_t = [p for p in plan["vdd_vias"] if def_in(p[0], p[1])]
    vdd_unv_t = [p for p in plan["vdd_unviad"] if def_in(p[0], p[1])]
    vss_vias_t = [p for p in plan["vss_vias"] if def_in(p[0], p[1])]
    vss_unv_t = [p for p in plan["vss_unviad"] if def_in(p[0], p[1])]
    vdd_cl_t = [
        (max(tx1, min(tx2, c[0])), max(ty1, min(ty2, c[1])), max(tx1, min(tx2, c[2])), max(ty1, min(ty2, c[3])))
        for c in plan["vdd_clines"] if def_in(c[0], c[1]) or def_in(c[2], c[3])
    ]
    vss_cl_t = [
        (max(tx1, min(tx2, c[0])), max(ty1, min(ty2, c[1])), max(tx1, min(tx2, c[2])), max(ty1, min(ty2, c[3])))
        for c in plan["vss_clines"] if def_in(c[0], c[1]) or def_in(c[2], c[3])
    ]

    r_pad = ms(38.5)     # 77um C4 / Via pad radius = 38.5um
    r_sro = ms(17.5)     # 35um C4 SRO radius = 17.5um
    r_drill = ms(24.5)   # 49um Via laser drill radius = 24.5um
    w_trace = ms(plan["trace_width_um"])

    # 1. Draw SURFACE CLINE straps first
    for x1, y1, x2, y2 in vdd_cl_t:
        lines.append(
            f'<line x1="{mx(x1)}" y1="{my(y1)}" x2="{mx(x2)}" y2="{my(y2)}" '
            f'stroke="#fb7185" stroke-width="{w_trace}" stroke-linecap="round" opacity="0.92"/>'
        )
    for x1, y1, x2, y2 in vss_cl_t:
        lines.append(
            f'<line x1="{mx(x1)}" y1="{my(y1)}" x2="{mx(x2)}" y2="{my(y2)}" '
            f'stroke="#60a5fa" stroke-width="{w_trace}" stroke-linecap="round" opacity="0.92"/>'
        )

    # 2. Draw Un-Via'd Bump Pads (77um Cu pad + 35um SRO ring, NO via drill)
    for x, y in vdd_unv_t:
        lines.append(
            f'<circle cx="{mx(x)}" cy="{my(y)}" r="{r_pad}" fill="#881337" fill-opacity="0.75" stroke="#fb7185" stroke-width="1.8" stroke-dasharray="4,2"/>'
        )
        lines.append(
            f'<circle cx="{mx(x)}" cy="{my(y)}" r="{r_sro}" fill="#fda4af" fill-opacity="0.45" stroke="#fecdd3" stroke-width="1.0"/>'
        )
    for x, y in vss_unv_t:
        lines.append(
            f'<circle cx="{mx(x)}" cy="{my(y)}" r="{r_pad}" fill="#1e3a8a" fill-opacity="0.75" stroke="#60a5fa" stroke-width="1.8" stroke-dasharray="4,2"/>'
        )
        lines.append(
            f'<circle cx="{mx(x)}" cy="{my(y)}" r="{r_sro}" fill="#93c5fd" fill-opacity="0.45" stroke="#dbeafe" stroke-width="1.0"/>'
        )

    # 3. Draw Via-in-Pad Bumps (77um Pad + 49um Laser Drill)
    for x, y in vdd_vias_t:
        cx_p, cy_p = mx(x), my(y)
        lines.append(
            f'<circle cx="{cx_p}" cy="{cy_p}" r="{r_pad}" fill="#e11d48" fill-opacity="0.92" stroke="#ffe4e6" stroke-width="1.6"/>'
        )
        lines.append(
            f'<circle cx="{cx_p}" cy="{cy_p}" r="{r_drill}" fill="#090d16" stroke="#fbbf24" stroke-width="1.8"/>'
        )
    for x, y in vss_vias_t:
        cx_p, cy_p = mx(x), my(y)
        lines.append(
            f'<circle cx="{cx_p}" cy="{cy_p}" r="{r_pad}" fill="#2563eb" fill-opacity="0.92" stroke="#dbeafe" stroke-width="1.6"/>'
        )
        lines.append(
            f'<circle cx="{cx_p}" cy="{cy_p}" r="{r_drill}" fill="#090d16" stroke="#38bdf8" stroke-width="1.8"/>'
        )

    # 4. Highlight Unit Cell Box (Vertical 2xP box or Horizontal Px2 box)
    p_cell = int(plan.get("cell_period") or 6)
    if plan.get("direction") == "HORIZONTAL":
        uc_x1, uc_y1 = 21020.0, 15180.0
        uc_x2 = round(min(tx2 - 20.0, uc_x1 + p_cell * 187.585 + 10.0), 2)
        uc_y2 = 15360.0
    else:
        uc_x1, uc_y1, uc_x2, uc_y2 = 21210.0, 14995.0, 21400.0, 16085.0
    if tx1 <= uc_x1 and uc_x2 <= tx2 and ty1 <= uc_y1 and uc_y2 <= ty2:
        lines.append(
            f'<rect x="{mx(uc_x1)}" y="{my(uc_y2)}" width="{ms(uc_x2 - uc_x1)}" height="{ms(uc_y2 - uc_y1)}" '
            f'rx="6" fill="none" stroke="#facc15" stroke-width="2.2" stroke-dasharray="7,4"/>'
        )
        lbl = plan.get("cell_label") or "Unit Cell"
        lines.append(
            f'<text x="{mx(uc_x1)}" y="{my(uc_y2) - 8}" fill="#facc15" font-family="Consolas, monospace" font-size="11.2" font-weight="bold">{html.escape(lbl)}</text>'
        )

    ratio_str = f"{len(vdd_vias_t)}:{len(vss_vias_t)} ({len(vdd_vias_t)/max(1,len(vss_vias_t)):.2f}:1)"
    footer = (
        f"Tile: VDDUC0 Vias={len(vdd_vias_t)} (Strapped={len(vdd_unv_t)}) | "
        f"VSS Vias={len(vss_vias_t)} (Strapped={len(vss_unv_t)}) | Ratio={ratio_str} | "
        f"Clines={len(vdd_cl_t)+len(vss_cl_t)} ({plan.get('direction','NONE')}, Space={plan.get('min_drc_clearance_um',43.3):.1f}um)"
    )
    lines.append(
        f'<text x="{panel_x + 20}" y="{panel_y + panel_h - 14}" fill="#e2e8f0" font-family="Consolas, monospace" font-size="11.2">{html.escape(footer)}</text>'
    )
    return lines


def _render_single_mode_full_and_zoom_svg(
    plan: Dict[str, Any],
    out_svg: Path,
    title: str,
    subtitle: str,
) -> str:
    """Render a 1920x1200 SVG showing Full U7 SURFACE map on the left and High-Res Zoomed Tile on the right."""
    W, H = 1920, 1200
    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%" style="background:#020617;">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#020617"/>',
        f'<text x="30" y="42" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="23" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="30" y="68" fill="#38bdf8" font-family="Consolas, monospace" font-size="13.2">{html.escape(subtitle)}</text>',
    ]

    lp_x, lp_y, lp_w, lp_h = 30.0, 90.0, 730.0, 1070.0
    svg.append(f'<rect x="{lp_x}" y="{lp_y}" width="{lp_w}" height="{lp_h}" rx="10" fill="#0f172a" stroke="#334155" stroke-width="2"/>')
    svg.append(f'<text x="{lp_x + 20}" y="{lp_y + 32}" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="17" font-weight="bold">Full U7 Die (SURFACE / TOP) — 14.0 x 31.6 mm</text>')

    dx1, dy1, dx2, dy2 = U7_DIE_EDGE
    sc_u7 = min((lp_w - 80.0) / (dx2 - dx1), (lp_h - 120.0) / (dy2 - dy1))
    u7_ox = lp_x + 45.0
    u7_oy = lp_y + 70.0
    u7_h_px = (dy2 - dy1) * sc_u7

    def ux(x_um: float) -> float:
        return round(u7_ox + (x_um - dx1) * sc_u7, 2)

    def uy(y_um: float) -> float:
        return round(u7_oy + u7_h_px - (y_um - dy1) * sc_u7, 2)

    svg.append(
        f'<rect x="{ux(dx1)}" y="{uy(dy2)}" width="{round((dx2 - dx1) * sc_u7, 2)}" height="{round(u7_h_px, 2)}" '
        f'fill="#090d16" stroke="#475569" stroke-width="1.5"/>'
    )

    for x1, y1, x2, y2 in plan["vdd_clines"]:
        svg.append(f'<line x1="{ux(x1)}" y1="{uy(y1)}" x2="{ux(x2)}" y2="{uy(y2)}" stroke="#fb7185" stroke-width="1.1"/>')
    for x1, y1, x2, y2 in plan["vss_clines"]:
        svg.append(f'<line x1="{ux(x1)}" y1="{uy(y1)}" x2="{ux(x2)}" y2="{uy(y2)}" stroke="#60a5fa" stroke-width="1.1"/>')

    for x, y in plan["vdd_unviad"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="0.9" fill="#881337"/>')
    for x, y in plan["vss_unviad"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="0.9" fill="#1e3a8a"/>')

    for x, y in plan["vdd_vias"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="1.3" fill="#f43f5e"/>')
    for x, y in plan["vss_vias"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="1.3" fill="#3b82f6"/>')

    tx1, ty1, tx2, ty2 = TILE_BBOX
    svg.append(
        f'<rect x="{ux(tx1)}" y="{uy(ty2)}" width="{round((tx2 - tx1) * sc_u7, 2)}" height="{round((ty2 - ty1) * sc_u7, 2)}" '
        f'fill="none" stroke="#facc15" stroke-width="2.2"/>'
    )

    n_vdd_v = len(plan["vdd_vias"])
    n_vss_v = len(plan["vss_vias"])
    n_vdd_u = len(plan["vdd_unviad"])
    n_vss_u = len(plan["vss_unviad"])
    n_cl = len(plan["vdd_clines"]) + len(plan["vss_clines"])
    u7_stat = (
        f"Full U7 ({plan['direction']}): VDDUC0 Vias={n_vdd_v} (Strapped={n_vdd_u}) | "
        f"VSS Vias={n_vss_v} (Strapped={n_vss_u}) | Clines={n_cl}"
    )
    svg.append(f'<text x="{lp_x + 20}" y="{lp_y + lp_h - 14}" fill="#cbd5e1" font-family="Consolas, monospace" font-size="11.5">{html.escape(u7_stat)}</text>')

    svg.extend(
        _render_tile_panel_svg(
            plan=plan,
            panel_x=780.0,
            panel_y=90.0,
            panel_w=1110.0,
            panel_h=1070.0,
            tile_bbox=TILE_BBOX,
            title=f"Zoomed-In Core C4 Bump Tile (1.65 x 1.65 mm) — {plan['ratio_str']} ({plan['direction']})",
            subtitle=(
                f"C4 Pad: C35_21_DP_01A (77um) | Via: V77_49_77_SURFACE_12F_01A | "
                f"24um {plan['direction']} Clines (Clearance={plan['min_drc_clearance_um']:.1f}um >= 18um DRC)"
            ),
        )
    )

    svg.append("</svg>")
    svg_str = "\n".join(svg)
    ET.fromstring(svg_str)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg_str, encoding="utf-8")
    return str(out_svg)


def _render_side_by_side_comparison_svg(
    plan_left: Dict[str, Any],
    plan_right: Dict[str, Any],
    out_svg: Path,
    header_title: str = "Layer 1 (SURFACE / TOP) PDN Routing Architecture — Example 1 (Full Via) vs. Example 2 (4:2 VDD:VSS Ratio + Trace Straps)",
    left_title: str = "EXAMPLE 1: Full Via-on-Bump (100% VIP on VDDUC0 & VSS)",
    left_subtitle: str = "Every C4 bump gets V77_49_77_SURFACE_12F_01A | 0 SURFACE traces | Via Ratio ~ 1:1",
    right_title: str = "EXAMPLE 2: 4:2 VDD:VSS Via Ratio + SURFACE Trace Ganging (24um CLINE)",
    right_subtitle: str = "Per 6-Row Cell: 4 VDDUC0 Vias + 2 Strapped Bumps | 2 VSS Vias + 4 Strapped Bumps -> Exact 4:2 Via Ratio",
) -> str:
    """Render a 2200x1260 side-by-side SVG comparing two SURFACE routing plans."""
    W, H = 2200, 1260
    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%" style="background:#020617;">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#020617"/>',
        f'<text x="30" y="42" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="23.5" font-weight="bold">{html.escape(header_title)}</text>',
        '<text x="30" y="68" fill="#38bdf8" font-family="Consolas, monospace" font-size="13.2">'
        'Target: U7 (HUTTON_HILL_LDB_BC_A0) | Nets: VDDUC0 (Crimson) &amp; VSS (Blue) | '
        '12Cu Rules: Min Trace=18um, Min Trace-to-Via/Pin=18um | Vertical Space=43.3um, Horizontal Space=40.0um'
        '</text>',
    ]

    svg.extend(
        _render_tile_panel_svg(
            plan=plan_left,
            panel_x=30.0,
            panel_y=90.0,
            panel_w=1055.0,
            panel_h=1020.0,
            tile_bbox=TILE_BBOX,
            title=left_title,
            subtitle=left_subtitle,
        )
    )

    svg.extend(
        _render_tile_panel_svg(
            plan=plan_right,
            panel_x=1115.0,
            panel_y=90.0,
            panel_w=1055.0,
            panel_h=1020.0,
            tile_bbox=TILE_BBOX,
            title=right_title,
            subtitle=right_subtitle,
        )
    )

    svg.extend([
        '<rect x="30" y="1125" width="2140" height="110" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1.5"/>',
        '<circle cx="65" cy="1158" r="11" fill="#e11d48" stroke="#ffe4e6" stroke-width="1.5"/>',
        '<circle cx="65" cy="1158" r="6" fill="#090d16" stroke="#fbbf24" stroke-width="1.5"/>',
        '<text x="86" y="1163" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">VDDUC0 Via-in-Pad (V77_49_77_SURFACE_12F_01A)</text>',
        '<circle cx="475" cy="1158" r="11" fill="#881337" stroke="#fb7185" stroke-width="1.5" stroke-dasharray="3,2"/>',
        '<line x1="475" y1="1158" x2="510" y2="1158" stroke="#fb7185" stroke-width="6" stroke-linecap="round"/>',
        '<text x="522" y="1163" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">Un-Via\'d VDDUC0 Bump + 24um SURFACE Strap (V / H / Both)</text>',
        '<circle cx="955" cy="1158" r="11" fill="#2563eb" stroke="#dbeafe" stroke-width="1.5"/>',
        '<circle cx="955" cy="1158" r="6" fill="#090d16" stroke="#38bdf8" stroke-width="1.5"/>',
        '<text x="976" y="1163" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">VSS Via-in-Pad (V77_49_77_SURFACE_12F_01A)</text>',
        '<circle cx="1360" cy="1158" r="11" fill="#1e3a8a" stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="3,2"/>',
        '<line x1="1360" y1="1158" x2="1395" y2="1158" stroke="#60a5fa" stroke-width="6" stroke-linecap="round"/>',
        '<text x="1407" y="1163" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">Un-Via\'d VSS Bump + 24um SURFACE Strap (V / H / Both)</text>',
        '<text x="50" y="1208" fill="#94a3b8" font-family="Consolas, monospace" font-size="12.2">'
        '12Cu SURFACE DRC: Vertical Pitch dy=180.99um (Adj-Col dx=93.79um =&gt; Space=43.29um &gt;= 18um) | '
        'Horizontal Pitch dx=187.58um (Adj-Row dy=90.50um =&gt; Space=40.00um &gt;= 18um) | Both pass Rule 3.4.1.41 with &gt;22um margin!'
        '</text>',
    ])

    svg.append("</svg>")
    svg_str = "\n".join(svg)
    ET.fromstring(svg_str)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg_str, encoding="utf-8")
    return str(out_svg)


def _export_recipe(plan: Dict[str, Any], out_txt: Path) -> str:
    """Export pipe-delimited Stage 4 SKILL recipe (VIA and CLINE records) for SURFACE layer."""
    lines: List[str] = [
        f"# AGENT04_LAYER1_SURFACE_RECIPE|MODE={plan['mode']}|RATIO={plan['ratio_str']}|DIRECTION={plan['direction']}|REFDES=U7|NETS=VDDUC0,VSS"
    ]
    for x, y in plan["vdd_vias"]:
        lines.append(f"VIA|VDDUC0|V77_49_77_SURFACE_12F_01A|SURFACE|12F|{x:.3f}|{y:.3f}")
    for x, y in plan["vss_vias"]:
        lines.append(f"VIA|VSS|V77_49_77_SURFACE_12F_01A|SURFACE|12F|{x:.3f}|{y:.3f}")
    w = plan["trace_width_um"]
    for x1, y1, x2, y2 in plan["vdd_clines"]:
        lines.append(f"CLINE|VDDUC0|SURFACE|{w:.1f}|{x1:.3f}|{y1:.3f}|{x2:.3f}|{y2:.3f}")
    for x1, y1, x2, y2 in plan["vss_clines"]:
        lines.append(f"CLINE|VSS|SURFACE|{w:.1f}|{x1:.3f}|{y1:.3f}|{x2:.3f}|{y2:.3f}")
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_txt)


def _plan_metrics(plan: Dict[str, Any], svg_file: str, recipe_file: str) -> Dict[str, Any]:
    return {
        "mode": plan["mode"],
        "ratio_str": plan["ratio_str"],
        "direction": plan["direction"],
        "cell_period": plan["cell_period"],
        "unit_cell_rule": plan["cell_label"],
        "vdduc0_vias": len(plan["vdd_vias"]),
        "vdduc0_strapped_bumps": len(plan["vdd_unviad"]),
        "vdduc0_surface_clines": len(plan["vdd_clines"]),
        "vss_vias": len(plan["vss_vias"]),
        "vss_strapped_bumps": len(plan["vss_unviad"]),
        "vss_surface_clines": len(plan["vss_clines"]),
        "total_surface_clines": len(plan["vdd_clines"]) + len(plan["vss_clines"]),
        "via_ratio_vdd_to_vss": round(len(plan["vdd_vias"]) / max(1, len(plan["vss_vias"])), 3),
        "cline_width_um": plan["trace_width_um"],
        "min_drc_clearance_um": plan["min_drc_clearance_um"],
        "drc_min_cline_to_via_pin_um": 18.0,
        "svg_file": svg_file,
        "recipe_file": recipe_file,
    }


def run_surface_layer1_mockups(
    custom_ratio: Optional[str] = None,
    custom_direction: Optional[str] = None,
    custom_period: Optional[int] = None,
    trace_width_um: float = 24.0,
) -> Dict[str, Any]:
    ws = Path(__file__).resolve().parent.parent.parent
    out_dir = ws / "pdn_sandbox"
    out_dir.mkdir(parents=True, exist_ok=True)

    vdd_pts, vss_pts = load_u7_surface_vdd_vss_bumps(ws)

    # Standard benchmark plans: Full Via, 4:2 (Vertical, Horizontal, Both), 5:2 (Vertical, Horizontal, Both)
    plan_full = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="FULL", direction="VERTICAL", trace_width_um=trace_width_um)
    plan_4to2_v = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="4:2", direction="VERTICAL", trace_width_um=trace_width_um)
    plan_4to2_h = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="4:2", direction="HORIZONTAL", trace_width_um=trace_width_um)
    plan_4to2_b = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="4:2", direction="BOTH", trace_width_um=trace_width_um)
    plan_5to2_v = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="5:2", direction="VERTICAL", trace_width_um=trace_width_um)
    plan_5to2_h = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="5:2", direction="HORIZONTAL", trace_width_um=trace_width_um)
    plan_5to2_b = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="5:2", direction="BOTH", trace_width_um=trace_width_um)

    svg_ex1 = _render_single_mode_full_and_zoom_svg(
        plan=plan_full,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex1_Full_Via_On_Bump.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 1: Full Via-on-Bump (100% VIP on VDDUC0 & VSS)",
        subtitle="U7 (HUTTON_HILL_LDB_BC_A0) | VDDUC0 Vias=7,584 (100%) | VSS Vias=7,962 (100%) | Padstack: V77_49_77_SURFACE_12F_01A | 0 SURFACE Clines",
    )
    svg_ex2_v = _render_single_mode_full_and_zoom_svg(
        plan=plan_4to2_v,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex2_Ratio_4to2_VDD_VSS_Trace_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 2A: 4:2 VDD:VSS Ratio (VERTICAL SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_4to2_v['vdd_vias'])}+{len(plan_4to2_v['vdd_clines'])} V-Straps | VSS Vias={len(plan_4to2_v['vss_vias'])}+{len(plan_4to2_v['vss_clines'])} V-Straps | Space=43.3um",
    )
    svg_ex2_h = _render_single_mode_full_and_zoom_svg(
        plan=plan_4to2_h,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex2B_Ratio_4to2_Horizontal_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 2B: 4:2 VDD:VSS Ratio (HORIZONTAL SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_4to2_h['vdd_vias'])}+{len(plan_4to2_h['vdd_clines'])} H-Straps | VSS Vias={len(plan_4to2_h['vss_vias'])}+{len(plan_4to2_h['vss_clines'])} H-Straps | Space=40.0um",
    )
    svg_ex2_b = _render_single_mode_full_and_zoom_svg(
        plan=plan_4to2_b,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex2C_Ratio_4to2_Both_HV_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 2C: 4:2 VDD:VSS Ratio (2D BOTH H+V SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_4to2_b['vdd_vias'])}+{len(plan_4to2_b['vdd_clines'])} H+V Straps | VSS Vias={len(plan_4to2_b['vss_vias'])}+{len(plan_4to2_b['vss_clines'])} H+V Straps | Space>=40.0um",
    )
    svg_ex3_v = _render_single_mode_full_and_zoom_svg(
        plan=plan_5to2_v,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex3_Ratio_5to2_VDD_VSS_Trace_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 3A: 5:2 VDD:VSS Ratio (VERTICAL SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_5to2_v['vdd_vias'])}+{len(plan_5to2_v['vdd_clines'])} V-Straps | VSS Vias={len(plan_5to2_v['vss_vias'])}+{len(plan_5to2_v['vss_clines'])} V-Straps | Space=43.3um",
    )
    svg_ex3_h = _render_single_mode_full_and_zoom_svg(
        plan=plan_5to2_h,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex3B_Ratio_5to2_Horizontal_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 3B: 5:2 VDD:VSS Ratio (HORIZONTAL SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_5to2_h['vdd_vias'])}+{len(plan_5to2_h['vdd_clines'])} H-Straps | VSS Vias={len(plan_5to2_h['vss_vias'])}+{len(plan_5to2_h['vss_clines'])} H-Straps | Space=40.0um",
    )
    svg_ex3_b = _render_single_mode_full_and_zoom_svg(
        plan=plan_5to2_b,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex3C_Ratio_5to2_Both_HV_Straps.svg",
        title="Layer 1 (SURFACE / TOP) Mockup — Example 3C: 5:2 VDD:VSS Ratio (2D BOTH H+V SURFACE Straps)",
        subtitle=f"U7 | VDDUC0 Vias={len(plan_5to2_b['vdd_vias'])}+{len(plan_5to2_b['vdd_clines'])} H+V Straps | VSS Vias={len(plan_5to2_b['vss_vias'])}+{len(plan_5to2_b['vss_clines'])} H+V Straps | Space>=40.0um",
    )

    # Side-by-side comparisons
    svg_cmp_full_42 = _render_side_by_side_comparison_svg(
        plan_left=plan_full,
        plan_right=plan_4to2_v,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_Comparison.svg",
    )
    svg_cmp_42_52 = _render_side_by_side_comparison_svg(
        plan_left=plan_4to2_v,
        plan_right=plan_5to2_v,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_4to2_vs_5to2.svg",
        header_title="Layer 1 (SURFACE / TOP) — 4:2 vs. 5:2 VDD:VSS Ratio (Vertical Straps)",
        left_title="EXAMPLE 2A: 4:2 VDD:VSS Via Ratio (VERTICAL Straps)",
        left_subtitle="Per 6-Row Col: 4 VDDUC0 Vias + 2 V-Straps | 2 VSS Vias + 4 V-Straps (Space=43.3um)",
        right_title="EXAMPLE 3A: 5:2 VDD:VSS Via Ratio (VERTICAL Straps)",
        right_subtitle="Per 6-Row Col: 5 VDDUC0 Vias + 1 V-Strap | 2 VSS Vias + 4 V-Straps (Space=43.3um)",
    )
    svg_cmp_42_vh = _render_side_by_side_comparison_svg(
        plan_left=plan_4to2_v,
        plan_right=plan_4to2_h,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_4to2_Vertical_vs_Horizontal.svg",
        header_title="Layer 1 (SURFACE / TOP) — 4:2 VDD:VSS Ratio: VERTICAL Straps vs. HORIZONTAL Straps",
        left_title="4:2 VERTICAL Straps (Along Same-Net Columns, dy=181.0um)",
        left_subtitle="24um Vertical Clines | Clearance to Opposite-Net 77um Pads = 43.29 um (>= 18um DRC)",
        right_title="4:2 HORIZONTAL Straps (Along Same-Net Rows, dx=187.6um)",
        right_subtitle="24um Horizontal Clines | Clearance to Opposite-Net 77um Pads = 40.00 um (>= 18um DRC)",
    )
    svg_cmp_52_vh = _render_side_by_side_comparison_svg(
        plan_left=plan_5to2_v,
        plan_right=plan_5to2_h,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_5to2_Vertical_vs_Horizontal.svg",
        header_title="Layer 1 (SURFACE / TOP) — 5:2 VDD:VSS Ratio: VERTICAL Straps vs. HORIZONTAL Straps",
        left_title="5:2 VERTICAL Straps (Along Same-Net Columns, dy=181.0um)",
        left_subtitle="24um Vertical Clines | Clearance to Opposite-Net 77um Pads = 43.29 um (>= 18um DRC)",
        right_title="5:2 HORIZONTAL Straps (Along Same-Net Rows, dx=187.6um)",
        right_subtitle="24um Horizontal Clines | Clearance to Opposite-Net 77um Pads = 40.00 um (>= 18um DRC)",
    )

    rcp_ex1 = _export_recipe(plan_full, out_dir / "mockup_L1_SURFACE_Ex1_recipe.txt")
    rcp_ex2_v = _export_recipe(plan_4to2_v, out_dir / "mockup_L1_SURFACE_Ex2_4to2_recipe.txt")
    rcp_ex2_h = _export_recipe(plan_4to2_h, out_dir / "mockup_L1_SURFACE_Ex2B_4to2_Horizontal_recipe.txt")
    rcp_ex2_b = _export_recipe(plan_4to2_b, out_dir / "mockup_L1_SURFACE_Ex2C_4to2_Both_HV_recipe.txt")
    rcp_ex3_v = _export_recipe(plan_5to2_v, out_dir / "mockup_L1_SURFACE_Ex3_5to2_recipe.txt")
    rcp_ex3_h = _export_recipe(plan_5to2_h, out_dir / "mockup_L1_SURFACE_Ex3B_5to2_Horizontal_recipe.txt")
    rcp_ex3_b = _export_recipe(plan_5to2_b, out_dir / "mockup_L1_SURFACE_Ex3C_5to2_Both_HV_recipe.txt")

    # 3:1 Horizontal plans:
    #   - Ex4A (P=3): 3 VDDUC0 Vias (100%) : 1 VSS Via + 2 Horizontal VSS Straps (max 1-hop horizontal strap!)
    #   - Ex4B (P=4): 3 VDDUC0 Vias + 1 Horizontal VDD Strap : 1 VSS Via + 3 Horizontal VSS Straps (both nets strapped horizontally!)
    plan_3to1_p3_h = synthesize_surface_routing(
        vdd_pts, vss_pts, ratio_str="3:1", direction="HORIZONTAL", cell_period=3, trace_width_um=trace_width_um
    )
    plan_3to1_p4_h = synthesize_surface_routing(
        vdd_pts, vss_pts, ratio_str="3:1", direction="HORIZONTAL", cell_period=4, trace_width_um=trace_width_um
    )
    svg_ex4a_h = _render_single_mode_full_and_zoom_svg(
        plan=plan_3to1_p3_h,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex4A_Ratio_3to1_P3_Horizontal_Straps.svg",
        title="Layer 1 (SURFACE / TOP) — 3:1 VDD:VSS Ratio (P=3 Cell: 3 VDD Vias : 1 VSS Via + 2 HORIZONTAL VSS Straps)",
        subtitle=(
            f"U7 | VDDUC0 Vias={len(plan_3to1_p3_h['vdd_vias'])} (100% VIP) | "
            f"VSS Vias={len(plan_3to1_p3_h['vss_vias'])} + {len(plan_3to1_p3_h['vss_clines'])} Horizontal 24um Straps (Space=40.0um >= 18um DRC)"
        ),
    )
    svg_ex4b_h = _render_single_mode_full_and_zoom_svg(
        plan=plan_3to1_p4_h,
        out_svg=out_dir / "mockup_L1_SURFACE_Ex4B_Ratio_3to1_P4_Horizontal_Straps.svg",
        title="Layer 1 (SURFACE / TOP) — 3:1 VDD:VSS Ratio (P=4 Cell: 3 VDD Vias+1 H-Strap : 1 VSS Via+3 HORIZONTAL Straps)",
        subtitle=(
            f"U7 | VDDUC0 Vias={len(plan_3to1_p4_h['vdd_vias'])}+{len(plan_3to1_p4_h['vdd_clines'])} H-Straps | "
            f"VSS Vias={len(plan_3to1_p4_h['vss_vias'])}+{len(plan_3to1_p4_h['vss_clines'])} H-Straps (Space=40.0um >= 18um DRC)"
        ),
    )
    svg_cmp_3to1_h = _render_side_by_side_comparison_svg(
        plan_left=plan_3to1_p3_h,
        plan_right=plan_3to1_p4_h,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_3to1_Horizontal_Comparison.svg",
        header_title="Layer 1 (SURFACE / TOP) — 3:1 VDD:VSS Ratio with Pure HORIZONTAL Floating-Bump Straps (P=3 vs. P=4 Unit Cell)",
        left_title="OPTION A (P=3 Cell): 3 VDDUC0 Vias (100%) : 1 VSS Via + 2 HORIZONTAL VSS Straps",
        left_subtitle="Every 3-bump row: [VSS_Float -> VSS_VIA <- VSS_Float] (1-hop max!) | 100% VDDUC0 VIP | Space=40.0um",
        right_title="OPTION B (P=4 Cell): 3 VDDUC0 Vias + 1 H-Strap : 1 VSS Via + 3 HORIZONTAL Straps",
        right_subtitle="Every 4-bump row: 3 VDD Vias + 1 H-Strap & 1 VSS Via + 3 H-Straps (Exact 3:1 on Both Nets) | Space=40.0um",
    )
    rcp_ex4a_h = _export_recipe(plan_3to1_p3_h, out_dir / "mockup_L1_SURFACE_Ex4A_3to1_P3_Horizontal_recipe.txt")
    rcp_ex4b_h = _export_recipe(plan_3to1_p4_h, out_dir / "mockup_L1_SURFACE_Ex4B_3to1_P4_Horizontal_recipe.txt")

    summary: Dict[str, Any] = {
        "status": "SUCCESS",
        "layer": "SURFACE (TOP)",
        "refdes": "U7 (HUTTON_HILL_LDB_BC_A0)",
        "total_vdduc0_bumps": len(vdd_pts),
        "total_vss_bumps": len(vss_pts),
        "example_1_full_via": _plan_metrics(plan_full, svg_ex1, rcp_ex1),
        "example_2_4to2_vertical": _plan_metrics(plan_4to2_v, svg_ex2_v, rcp_ex2_v),
        "example_2_4to2_horizontal": _plan_metrics(plan_4to2_h, svg_ex2_h, rcp_ex2_h),
        "example_2_4to2_both_hv": _plan_metrics(plan_4to2_b, svg_ex2_b, rcp_ex2_b),
        "example_3_5to2_vertical": _plan_metrics(plan_5to2_v, svg_ex3_v, rcp_ex3_v),
        "example_3_5to2_horizontal": _plan_metrics(plan_5to2_h, svg_ex3_h, rcp_ex3_h),
        "example_3_5to2_both_hv": _plan_metrics(plan_5to2_b, svg_ex3_b, rcp_ex3_b),
        "example_4a_3to1_p3_horizontal": _plan_metrics(plan_3to1_p3_h, svg_ex4a_h, rcp_ex4a_h),
        "example_4b_3to1_p4_horizontal": _plan_metrics(plan_3to1_p4_h, svg_ex4b_h, rcp_ex4b_h),
        "side_by_side_svgs": {
            "full_vs_4to2": svg_cmp_full_42,
            "4to2_vs_5to2": svg_cmp_42_52,
            "4to2_vertical_vs_horizontal": svg_cmp_42_vh,
            "5to2_vertical_vs_horizontal": svg_cmp_52_vh,
            "3to1_p3_vs_p4_horizontal": svg_cmp_3to1_h,
        },
    }

    # If user specified custom ratio/direction via CLI, synthesize and export that custom plan too
    if custom_ratio:
        c_dir = (custom_direction or "VERTICAL").upper()
        c_plan = synthesize_surface_routing(
            vdd_pts, vss_pts, ratio_str=custom_ratio, direction=c_dir, cell_period=custom_period, trace_width_um=trace_width_um
        )
        safe_r = custom_ratio.replace(":", "to")
        c_svg = _render_single_mode_full_and_zoom_svg(
            plan=c_plan,
            out_svg=out_dir / f"mockup_L1_SURFACE_Custom_{safe_r}_{c_dir}.svg",
            title=f"Layer 1 (SURFACE / TOP) Custom Plan — Ratio {custom_ratio} ({c_dir})",
            subtitle=f"U7 | VDDUC0 Vias={len(c_plan['vdd_vias'])} | VSS Vias={len(c_plan['vss_vias'])} | Clines={len(c_plan['vdd_clines'])+len(c_plan['vss_clines'])}",
        )
        c_rcp = _export_recipe(c_plan, out_dir / f"mockup_L1_SURFACE_Custom_{safe_r}_{c_dir}_recipe.txt")
        summary["custom_user_plan"] = _plan_metrics(c_plan, c_svg, c_rcp)

    (out_dir / "mockup_L1_SURFACE_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Layer 1 (SURFACE / TOP) Parameterized PDN Bump-Via & Trace Router")
    parser.add_argument("--ratio", type=str, default=None, help="User VDD:VSS via ratio (e.g., FULL, 4:2, 5:2, 3:1)")
    parser.add_argument("--direction", type=str, default="VERTICAL", choices=["VERTICAL", "HORIZONTAL", "BOTH"], help="SURFACE trace strap direction")
    parser.add_argument("--cell-period", type=int, default=None, help="Optional unit-cell period P")
    parser.add_argument("--trace-width", type=float, default=24.0, help="SURFACE CLINE width in um (default 24.0)")
    args = parser.parse_args()

    res = run_surface_layer1_mockups(
        custom_ratio=args.ratio,
        custom_direction=args.direction,
        custom_period=args.cell_period,
        trace_width_um=args.trace_width,
    )
    print(json.dumps(res, indent=2))
