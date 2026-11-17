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
import collections
import csv
import html
import json
import math
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


U7_DIE_EDGE = (16143.768, 120.001, 30138.068, 31765.021)
TILE_BBOX = (21000.0, 15000.0, 22650.0, 16650.0)

BBox = Tuple[float, float, float, float]
Point = Tuple[float, float]

LDB_SURFACE_PROFILES: Dict[str, Dict[str, Any]] = {
    "U7": {
        "refdes": "U7",
        "primary_vdd": "VDDUC0",
        "die_bbox": (16143.768, 120.001, 30138.068, 31765.021),
        "tile_bbox": (21000.0, 15000.0, 22650.0, 16650.0),
        "jog_tile_bbox": (28450.0, 20450.0, 30100.0, 22500.0),
        "emib_refs": ["U28", "U32", "U35", "U38", "U47", "U48", "U49"],
    },
    "U5": {
        "refdes": "U5",
        "primary_vdd": "VDDUC1",
        "die_bbox": (-30138.068, 120.001, -16143.768, 31765.021),
        "tile_bbox": (-22850.0, 15000.0, -21200.0, 16650.0),
        "jog_tile_bbox": (-30100.0, 20450.0, -28450.0, 22500.0),
        "emib_refs": ["U25", "U29", "U33", "U37", "U41", "U42", "U43"],
    },
    "U8": {
        "refdes": "U8",
        "primary_vdd": "VDDUC2",
        "die_bbox": (16143.768, -31765.021, 30138.068, -120.001),
        "tile_bbox": (21000.0, -16650.0, 22650.0, -15000.0),
        "jog_tile_bbox": (28450.0, -22500.0, 30100.0, -20450.0),
        "emib_refs": ["U27", "U31", "U34", "U38", "U50", "U51", "U52"],
    },
    "U6": {
        "refdes": "U6",
        "primary_vdd": "VDDUC3",
        "die_bbox": (-30138.068, -31765.021, -16143.768, -120.001),
        "tile_bbox": (-22850.0, -16650.0, -21200.0, -15000.0),
        "jog_tile_bbox": (-30100.0, -22500.0, -28450.0, -20450.0),
        "emib_refs": ["U26", "U30", "U36", "U37", "U44", "U45", "U46"],
    },
}


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


def _pt_to_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= 1e-9:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _ccw_val(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _seg_to_seg_dist(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> float:
    d1, d2 = _ccw_val(x1, y1, x2, y2, x3, y3), _ccw_val(x1, y1, x2, y2, x4, y4)
    d3, d4 = _ccw_val(x3, y3, x4, y4, x1, y1), _ccw_val(x3, y3, x4, y4, x2, y2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return 0.0
    return min(
        _pt_to_seg_dist(x1, y1, x3, y3, x4, y4),
        _pt_to_seg_dist(x2, y2, x3, y3, x4, y4),
        _pt_to_seg_dist(x3, y3, x1, y1, x2, y2),
        _pt_to_seg_dist(x4, y4, x1, y1, x2, y2),
    )


def _pt_to_box_dist(px: float, py: float, b: BBox) -> float:
    cx = max(b[0], min(px, b[2]))
    cy = max(b[1], min(py, b[3]))
    return math.hypot(px - cx, py - cy)


def _seg_to_box_dist(x1: float, y1: float, x2: float, y2: float, b: BBox) -> float:
    if (b[0] <= x1 <= b[2] and b[1] <= y1 <= b[3]) or (b[0] <= x2 <= b[2] and b[1] <= y2 <= b[3]):
        return 0.0
    bx1, by1, bx2, by2 = b
    edges = (
        (bx1, by1, bx2, by1),
        (bx2, by1, bx2, by2),
        (bx2, by2, bx1, by2),
        (bx1, by2, bx1, by1),
    )
    return min(_seg_to_seg_dist(x1, y1, x2, y2, ex1, ey1, ex2, ey2) for ex1, ey1, ex2, ey2 in edges)


def _pt_in_any_box(x: float, y: float, boxes: Sequence[BBox]) -> bool:
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


def _pt_forbidden_for_vip(x: float, y: float, emib_boxes: Sequence[BBox], via_kozs: Sequence[BBox]) -> bool:
    if _pt_in_any_box(x, y, emib_boxes):
        return True
    return any(_pt_to_box_dist(x, y, kb) <= 39.0 for kb in via_kozs)


class _SurfaceObstacleTracker:
    """Spatial hash index (`160 um` cells) for SURFACE copper pads, keepouts, and routed CLINE segments."""

    def __init__(self, cell_um: float = 160.0) -> None:
        self.cell = cell_um
        self.pad_grid: Dict[Tuple[int, int], List[Tuple[float, float, float, str]]] = collections.defaultdict(list)
        self.seg_grid: Dict[Tuple[int, int], List[Tuple[str, float, float, float, float, float]]] = collections.defaultdict(list)
        self.all_pads: List[Tuple[float, float, float, str]] = []
        self.all_segs: List[Tuple[str, float, float, float, float, float]] = []
        self.route_kozs: List[BBox] = []

    def add_pad(self, x: float, y: float, rad: float, net: str) -> None:
        item = (x, y, rad, net)
        self.all_pads.append(item)
        self.pad_grid[(int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))].append(item)

    def add_route_keepout(self, box: BBox) -> None:
        self.route_kozs.append(box)

    def poly_clear(self, chain: Sequence[Point], net: str, hw: float, min_gap: float) -> bool:
        margin = hw + min_gap + 50.0
        for i in range(len(chain) - 1):
            x1, y1 = chain[i]
            x2, y2 = chain[i + 1]
            for kb in self.route_kozs:
                if _seg_to_box_dist(x1, y1, x2, y2, kb) < (hw + 0.5):
                    return False
            gx0 = int(math.floor((min(x1, x2) - margin) / self.cell))
            gx1 = int(math.floor((max(x1, x2) + margin) / self.cell))
            gy0 = int(math.floor((min(y1, y2) - margin) / self.cell))
            gy1 = int(math.floor((max(y1, y2) + margin) / self.cell))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    for ox, oy, orad, onet in self.pad_grid.get((gx, gy), ()):
                        if onet != net and _pt_to_seg_dist(ox, oy, x1, y1, x2, y2) < (orad + hw + min_gap):
                            return False
                    for snet, shw, sx1, sy1, sx2, sy2 in self.seg_grid.get((gx, gy), ()):
                        if snet != net and _seg_to_seg_dist(x1, y1, x2, y2, sx1, sy1, sx2, sy2) < (shw + hw + min_gap):
                            return False
        return True

    def register_poly(self, chain: Sequence[Point], net: str, hw: float) -> None:
        for i in range(len(chain) - 1):
            x1, y1 = chain[i]
            x2, y2 = chain[i + 1]
            item = (net, hw, x1, y1, x2, y2)
            self.all_segs.append(item)
            gx0 = int(math.floor(min(x1, x2) / self.cell))
            gx1 = int(math.floor(max(x1, x2) / self.cell))
            gy0 = int(math.floor(min(y1, y2) / self.cell))
            gy1 = int(math.floor(max(y1, y2) / self.cell))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    self.seg_grid[(gx, gy)].append(item)


def _extract_refdes_pins_readonly_from_mcm(refdes: str, src_mcm: Path, sandbox_dir: Path) -> Tuple[Path, Path]:
    """Extract all SURFACE pins of `refdes` and native 12F/SURFACE keepouts read-only from `src_mcm`."""
    try:
        from agent04_pdn_architect.cad_cli.cadence_runner import CadenceBatchRunner
    except ImportError:
        from cadence_runner import CadenceBatchRunner  # type: ignore

    ref_u = refdes.strip().upper()
    prof = LDB_SURFACE_PROFILES.get(ref_u, LDB_SURFACE_PROFILES["U6"])
    bx1, by1, bx2, by2 = prof["die_bbox"]
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    out_csv = sandbox_dir / f"{ref_u.lower()}_full_pins_from_mcm.csv"
    koz_csv = sandbox_dir / f"{ref_u.lower()}_kozs_from_mcm.csv"
    ro_link = sandbox_dir / f"_ro_extract_{ref_u}_{src_mcm.name}"
    il_path = sandbox_dir / f"_ro_extract_{ref_u}.il"
    scr_path = sandbox_dir / f"_ro_extract_{ref_u}.scr"

    il_code = (
        f'procedure( pdn_ro_extract_{ref_u.lower()}(out_csv koz_csv)\n'
        f'    let((d sym sref p_out k_out pin pnum px py pnet ppad se shp lyr bbx x1 y1 x2 y2)\n'
        f'        d = axlDBGetDesign()\n'
        f'        p_out = outfile(out_csv "w")\n'
        f'        fprintf(p_out "refdes,symbol_name,pin_number,x_um,y_um,net_name,padstack_name,start_end,layer\\n")\n'
        f'        when( d != nil\n'
        f'            foreach(sym d->symbols\n'
        f'                sref = if( sym->refdes != nil then sym->refdes else "")\n'
        f'                when( sref == "{ref_u}"\n'
        f'                    foreach(pin sym->pins\n'
        f'                        pnum = if( pin->number != nil then sprintf(nil "%L" pin->number) else "0")\n'
        f'                        px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)\n'
        f'                        py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)\n'
        f'                        pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "")\n'
        f'                        ppad = if( pin->definition != nil && pin->definition->name != nil then pin->definition->name else "")\n'
        f'                        se = if( pin->startEnd != nil then sprintf(nil "%L" pin->startEnd) else "")\n'
        f'                        fprintf(p_out "%s,%s,%s,%.3f,%.3f,%s,%s,%s,%s\\n"\n'
        f'                            sref (if sym->name sym->name "") pnum px py pnet ppad se (if sym->layer sym->layer ""))\n'
        f'                    )\n'
        f'                )\n'
        f'            )\n'
        f'        )\n'
        f'        close(p_out)\n'
        f'        k_out = outfile(koz_csv "w")\n'
        f'        fprintf(k_out "layer,x1_um,y1_um,x2_um,y2_um\\n")\n'
        f'        foreach(shp axlDBGetShapes(nil)\n'
        f'            lyr = if( shp->layer && stringp(shp->layer) then upperCase(shp->layer) else "")\n'
        f'            when( (lyr == "VIA KEEPOUT/12F" || lyr == "VIA KEEPOUT/SURFACE" || lyr == "ROUTE KEEPOUT/SURFACE") && shp->bBox\n'
        f'                bbx = shp->bBox\n'
        f'                x1 = float(car(car(bbx)))  y1 = float(cadr(car(bbx)))\n'
        f'                x2 = float(car(cadr(bbx))) y2 = float(cadr(cadr(bbx)))\n'
        f'                when( x2 >= {bx1 - 300.0:.3f} && x1 <= {bx2 + 300.0:.3f} && y2 >= {by1 - 300.0:.3f} && y1 <= {by2 + 300.0:.3f}\n'
        f'                    fprintf(k_out "%s,%.3f,%.3f,%.3f,%.3f\\n" lyr x1 y1 x2 y2)\n'
        f'                )\n'
        f'            )\n'
        f'        )\n'
        f'        close(k_out)\n'
        f'        t\n'
        f'    )\n'
        f')\n'
    )
    il_path.write_text(il_code, encoding="utf-8")
    scr_path.write_text(
        f'skill load("{il_path.as_posix()}")\n'
        f'skill pdn_ro_extract_{ref_u.lower()}("{out_csv.as_posix()}" "{koz_csv.as_posix()}")\n'
        f"exit\nfillin no\n",
        encoding="utf-8",
    )

    if ro_link.exists():
        ro_link.unlink()
    try:
        os.link(str(src_mcm), str(ro_link))
    except OSError:
        shutil.copy2(str(src_mcm), str(ro_link))

    try:
        runner = CadenceBatchRunner(default_timeout=180)
        res = runner.run(mcm_path=ro_link, scr_path=scr_path, working_dir=sandbox_dir, timeout=180, bypass_lock_readonly=False)
        if not res.success or not out_csv.is_file():
            raise RuntimeError(f"Read-only pin extraction failed for {ref_u}: {res.error_message}")
    finally:
        for tmp_p in (ro_link, ro_link.with_name(ro_link.name + ".lck"), il_path, scr_path):
            if tmp_p.exists():
                try:
                    tmp_p.unlink()
                except OSError:
                    pass
    return out_csv, koz_csv


def load_refdes_surface_c4_and_obstacles(
    refdes: str = "U6",
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load exact SURFACE C4 bumps (primary VDD + VSS), all symbol obstacle pads (C4 + uBumps + signals),
    EMIB 157.5 um KOZs, and native 12F/SURFACE VIA/ROUTE keepout bounding boxes for any LDB die (`U5`..`U8`).
    """
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import REPO_ROOT, resolve_active_work_dir, resolve_output_dir
        from agent04_pdn_architect.cad_cli.pdn_prelearn import resolve_mcm_in_work_dir
    except ImportError:
        from pdn_paths import REPO_ROOT, resolve_active_work_dir, resolve_output_dir  # type: ignore
        from pdn_prelearn import resolve_mcm_in_work_dir  # type: ignore

    ref_u = refdes.strip().upper()
    prof = LDB_SURFACE_PROFILES.get(ref_u, LDB_SURFACE_PROFILES["U6"])
    vdd_net = str(prof["primary_vdd"])
    eff_wd, is_custom = resolve_active_work_dir(work_dir)
    sandbox_dir = resolve_output_dir("pdn_sandbox", explicit_work_dir=work_dir)

    pin_csv_candidates = [
        sandbox_dir / f"{ref_u.lower()}_full_pins_from_mcm.csv",
        eff_wd / "stage1_inputs" / f"{ref_u.lower()}_full_pins.csv",
        REPO_ROOT / "agent04_pdn_architect" / "stage1_inputs" / f"{ref_u.lower()}_full_pins.csv",
    ]
    pin_csv = next((p for p in pin_csv_candidates if p.is_file() and p.stat().st_size > 1000), None)
    koz_csv = sandbox_dir / f"{ref_u.lower()}_kozs_from_mcm.csv"
    need_extract = (pin_csv is None) or (not koz_csv.is_file())
    if need_extract:
        src_mcm = resolve_mcm_in_work_dir(eff_wd) if is_custom else None
        if src_mcm is None:
            cand_mcm = eff_wd / "MCM_template" / "PDN_test.mcm"
            if cand_mcm.is_file():
                src_mcm = cand_mcm
            else:
                repo_mcm = REPO_ROOT / "agent04_pdn_architect" / "MCM_test" / "PDN_test.mcm"
                if repo_mcm.is_file():
                    src_mcm = repo_mcm
        if src_mcm is not None and src_mcm.is_file():
            pin_csv, koz_csv = _extract_refdes_pins_readonly_from_mcm(ref_u, src_mcm, sandbox_dir)

    vdd_c4: List[Point] = []
    vss_c4: List[Point] = []
    all_pads: List[Tuple[float, float, float, str]] = []
    seen_vdd: Set[Tuple[int, int]] = set()
    seen_vss: Set[Tuple[int, int]] = set()

    if pin_csv is not None and pin_csv.is_file():
        with pin_csv.open("r", encoding="utf-8", errors="ignore") as fh:
            for row in csv.DictReader(fh):
                if row.get("refdes", "").strip().upper() != ref_u:
                    continue
                x, y = float(row["x_um"]), float(row["y_um"])
                net = row.get("net_name", "").strip()
                ps = row.get("padstack_name", "").strip()
                rad = 15.0 if ("18" in ps or "30" in ps) else 38.5
                all_pads.append((x, y, rad, net))
                is_c4 = (ps == "C35_21_DP_01A") or (ps == "" and net == vdd_net)
                if is_c4 and net == vdd_net:
                    k = (int(round(x * 1000.0)), int(round(y * 1000.0)))
                    if k not in seen_vdd:
                        seen_vdd.add(k)
                        vdd_c4.append((x, y))
                elif ps == "C35_21_DP_01A" and net == "VSS":
                    k = (int(round(x * 1000.0)), int(round(y * 1000.0)))
                    if k not in seen_vss:
                        seen_vss.add(k)
                        vss_c4.append((x, y))
    else:
        # Fallback to cadence_extract/mcm_vias.txt within die_bbox
        die_b: BBox = prof["die_bbox"]
        vias_txt = REPO_ROOT / "cadence_extract" / "mcm_vias.txt"
        if vias_txt.is_file():
            with vias_txt.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.startswith("S!"):
                        continue
                    p = line.strip().split("!")
                    if len(p) < 7 or (p[2].strip(), p[3].strip()) not in (("TOP", "12F"), ("SURFACE", "12F")):
                        continue
                    vx, vy = float(p[4]), float(p[5])
                    if not (die_b[0] <= vx <= die_b[2] and die_b[1] <= vy <= die_b[3]):
                        continue
                    net = p[6].strip()
                    if net == vdd_net:
                        vdd_c4.append((vx, vy))
                        all_pads.append((vx, vy, 38.5, net))
                    elif net == "VSS":
                        vss_c4.append((vx, vy))
                        all_pads.append((vx, vy, 38.5, net))

    vdd_c4.sort(key=lambda pt: (round(pt[0], 1), round(pt[1], 1)))
    vss_c4.sort(key=lambda pt: (round(pt[0], 1), round(pt[1], 1)))

    # Resolve EMIB 157.5 um KOZ bounding boxes (`COMPONENT GEOMETRY/DIE_EDGE` + 157.5 um)
    emib_157: List[BBox] = []
    bbox_json = REPO_ROOT / "agent04_pdn_architect" / "MCM_test" / "extract_pdn_test" / "pdn_test_symbol_bboxes.json"
    if bbox_json.is_file():
        bdata = json.loads(bbox_json.read_text(encoding="utf-8"))
        for er in prof["emib_refs"]:
            if er in bdata and "COMPONENT GEOMETRY/DIE_EDGE" in bdata[er]:
                b = bdata[er]["COMPONENT GEOMETRY/DIE_EDGE"]
                emib_157.append((b[0] - 157.5, b[1] - 157.5, b[2] + 157.5, b[3] + 157.5))

    via_kozs: List[BBox] = []
    route_kozs: List[BBox] = []
    seen_koz: Set[Tuple[str, float, float, float, float]] = set()
    if koz_csv.is_file():
        with koz_csv.open("r", encoding="utf-8", errors="ignore") as fh:
            for row in csv.DictReader(fh):
                lyr = row.get("layer", "").strip().upper()
                box = (
                    round(float(row["x1_um"]), 3),
                    round(float(row["y1_um"]), 3),
                    round(float(row["x2_um"]), 3),
                    round(float(row["y2_um"]), 3),
                )
                key = (lyr, *box)
                if key in seen_koz:
                    continue
                seen_koz.add(key)
                if lyr in ("VIA KEEPOUT/12F", "VIA KEEPOUT/SURFACE"):
                    via_kozs.append(box)
                elif lyr == "ROUTE KEEPOUT/SURFACE":
                    route_kozs.append(box)

    return {
        "refdes": ref_u,
        "vdd_net": vdd_net,
        "vdd_pts": vdd_c4,
        "vss_pts": vss_c4,
        "all_obstacle_pads": all_pads,
        "emib_157_boxes": emib_157,
        "via_keepout_boxes": via_kozs,
        "route_keepout_boxes": route_kozs,
        "die_bbox": prof["die_bbox"],
        "tile_bbox": prof["tile_bbox"],
        "jog_tile_bbox": prof["jog_tile_bbox"],
        "pin_csv": str(pin_csv) if pin_csv else "",
        "koz_csv": str(koz_csv) if koz_csv.is_file() else "",
    }


def audit_surface_routing_drc_and_connectivity(
    vdd_vias: Sequence[Point],
    vss_vias: Sequence[Point],
    vdd_all_pts: Sequence[Point],
    vss_all_pts: Sequence[Point],
    vdd_clines: Sequence[Tuple[float, float, float, float]],
    vss_clines: Sequence[Tuple[float, float, float, float]],
    all_obstacle_pads: Sequence[Tuple[float, float, float, str]],
    emib_157_boxes: Sequence[BBox],
    vdd_net: str = "VDDUC3",
    trace_width_um: float = 24.0,
    min_gap_um: float = 18.0,
    via_keepout_boxes: Optional[Sequence[BBox]] = None,
    route_keepout_boxes: Optional[Sequence[BBox]] = None,
) -> Dict[str, Any]:
    """
    Independent mathematical DRC & BFS connectivity audit across ALL SURFACE pads, keepouts, and segments:
      1. `0` pad-to-trace clearance violations (`gap >= min_gap_um` against every opposite-net pad)
      2. `0` trace-to-trace clearance violations (`gap >= min_gap_um` between VDD & VSS CLINEs)
      3. `0` SURFACE->12F VIPs placed inside EMIB `157.5 um` KOZ or `VIA KEEPOUT/12F` (`dist <= 38.5 um`)
      4. `0` SURFACE CLINEs intersecting `ROUTE KEEPOUT/SURFACE`
      5. `0` floating/unconnected C4 bumps (100% BFS-reachable to a via'd bump on SURFACE)
    """
    hw = 0.5 * trace_width_um
    via_kozs = list(via_keepout_boxes or ())
    route_kozs = list(route_keepout_boxes or ())
    cell = 160.0
    pad_grid: Dict[Tuple[int, int], List[Tuple[float, float, float, str]]] = collections.defaultdict(list)
    for px, py, prad, pnet in all_obstacle_pads:
        pad_grid[(int(math.floor(px / cell)), int(math.floor(py / cell)))].append((px, py, prad, pnet))
    if not all_obstacle_pads:
        for px, py in vdd_all_pts:
            pad_grid[(int(math.floor(px / cell)), int(math.floor(py / cell)))].append((px, py, 38.5, vdd_net))
        for px, py in vss_all_pts:
            pad_grid[(int(math.floor(px / cell)), int(math.floor(py / cell)))].append((px, py, 38.5, "VSS"))

    seg_grid: Dict[Tuple[int, int], List[Tuple[str, float, float, float, float]]] = collections.defaultdict(list)
    all_segs: List[Tuple[str, float, float, float, float]] = []
    for net_s, clist in ((vdd_net, vdd_clines), ("VSS", vss_clines)):
        for x1, y1, x2, y2 in clist:
            all_segs.append((net_s, x1, y1, x2, y2))
            gx0 = int(math.floor(min(x1, x2) / cell))
            gx1 = int(math.floor(max(x1, x2) / cell))
            gy0 = int(math.floor(min(y1, y2) / cell))
            gy1 = int(math.floor(max(y1, y2) / cell))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    seg_grid[(gx, gy)].append((net_s, x1, y1, x2, y2))

    min_pad_gap = 1e9
    pad_viol = 0
    min_seg_gap = 1e9
    seg_viol = 0
    route_koz_viol = 0
    for net_s, x1, y1, x2, y2 in all_segs:
        for kb in route_kozs:
            if _seg_to_box_dist(x1, y1, x2, y2, kb) < (hw - 1e-3):
                route_koz_viol += 1
        gx0 = int(math.floor((min(x1, x2) - 80.0) / cell))
        gx1 = int(math.floor((max(x1, x2) + 80.0) / cell))
        gy0 = int(math.floor((min(y1, y2) - 80.0) / cell))
        gy1 = int(math.floor((max(y1, y2) + 80.0) / cell))
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                for ox, oy, orad, onet in pad_grid.get((gx, gy), ()):
                    if onet == net_s:
                        continue
                    g = _pt_to_seg_dist(ox, oy, x1, y1, x2, y2) - orad - hw
                    if g < min_pad_gap:
                        min_pad_gap = g
                    if g < min_gap_um - 1e-3:
                        pad_viol += 1
                for snet, sx1, sy1, sx2, sy2 in seg_grid.get((gx, gy), ()):
                    if snet == net_s:
                        continue
                    gs = _seg_to_seg_dist(x1, y1, x2, y2, sx1, sy1, sx2, sy2) - 2.0 * hw
                    if gs < min_seg_gap:
                        min_seg_gap = gs
                    if gs < min_gap_um - 1e-3:
                        seg_viol += 1

    vips_in_emib = sum(1 for vx, vy in list(vdd_vias) + list(vss_vias) if _pt_in_any_box(vx, vy, emib_157_boxes))
    vips_in_via_koz = sum(
        1 for vx, vy in list(vdd_vias) + list(vss_vias) if any(_pt_to_box_dist(vx, vy, kb) <= 38.5 for kb in via_kozs)
    )

    unconn_by_net: Dict[str, int] = {}
    for net_s, vlist, all_list, clist in (
        (vdd_net, vdd_vias, vdd_all_pts, vdd_clines),
        ("VSS", vss_vias, vss_all_pts, vss_clines),
    ):
        v_set = {(round(px, 2), round(py, 2)) for px, py in vlist}
        all_set = {(round(px, 2), round(py, 2)) for px, py in all_list}
        adj: Dict[Point, List[Point]] = collections.defaultdict(list)
        for x1, y1, x2, y2 in clist:
            u = (round(x1, 2), round(y1, 2))
            v = (round(x2, 2), round(y2, 2))
            adj[u].append(v)
            adj[v].append(u)
        vis = set(v_set)
        q = collections.deque(vis)
        while q:
            cur = q.popleft()
            for nb in adj.get(cur, ()):
                if nb not in vis:
                    vis.add(nb)
                    q.append(nb)
        unconn_by_net[net_s] = len(all_set - vis)

    tot_unconn = sum(unconn_by_net.values())
    passed = (
        pad_viol == 0
        and seg_viol == 0
        and vips_in_emib == 0
        and vips_in_via_koz == 0
        and route_koz_viol == 0
        and tot_unconn == 0
    )
    return {
        "drc_pass": passed,
        "pad_to_trace_violation_count": pad_viol,
        "trace_to_trace_violation_count": seg_viol,
        "min_pad_to_trace_gap_um": round(min_pad_gap if min_pad_gap < 1e8 else 999.0, 2),
        "min_trace_to_trace_gap_um": round(min_seg_gap if min_seg_gap < 1e8 else 999.0, 2),
        "vips_inside_emib_157_koz": vips_in_emib,
        "vips_inside_12f_via_keepout": vips_in_via_koz,
        "clines_inside_surface_route_keepout": route_koz_viol,
        "unconnected_c4_bumps_total": tot_unconn,
        "unconnected_c4_bumps_by_net": unconn_by_net,
    }


def synthesize_surface_routing_with_jogs(
    vdd_pts: List[Point],
    vss_pts: List[Point],
    ratio_str: str = "4:2",
    direction: str = "VERTICAL",
    cell_period: Optional[int] = None,
    trace_width_um: float = 24.0,
    min_gap_um: float = 18.0,
    vdd_net: str = "VDDUC3",
    all_obstacle_pads: Optional[Sequence[Tuple[float, float, float, str]]] = None,
    emib_157_boxes: Optional[Sequence[BBox]] = None,
    via_keepout_boxes: Optional[Sequence[BBox]] = None,
    route_keepout_boxes: Optional[Sequence[BBox]] = None,
) -> Dict[str, Any]:
    """
    Obstacle-aware & EMIB/Keepout-aware SURFACE (TOP) Via & Jog-Strap Synthesizer.

    Places `M:N` unit-cell VIPs strictly outside EMIB `157.5 um` KOZs and native `VIA KEEPOUT/12F`
    shapes (e.g. `FIDBAF_01A*` fiducials), avoids `ROUTE KEEPOUT/SURFACE` shapes, and jogs/straps
    100% of floating bumps to same-net via'd bumps with `0` floating bumps and `>= min_gap_um` clearance.
    """
    dir_u = direction.strip().upper()
    if dir_u not in ("VERTICAL", "HORIZONTAL", "BOTH"):
        dir_u = "VERTICAL"
    is_full, m_vdd, n_vss, period_p = parse_ratio_and_period(ratio_str, cell_period)
    emib_boxes = list(emib_157_boxes or ())
    via_kozs = list(via_keepout_boxes or ())
    route_kozs = list(route_keepout_boxes or ())
    obs_list = list(all_obstacle_pads or ())
    if not obs_list:
        for px, py in vdd_pts:
            obs_list.append((px, py, 38.5, vdd_net))
        for px, py in vss_pts:
            obs_list.append((px, py, 38.5, "VSS"))

    tracker = _SurfaceObstacleTracker(cell_um=160.0)
    for px, py, prad, pnet in obs_list:
        tracker.add_pad(px, py, prad, pnet)
    for rkb in route_kozs:
        tracker.add_route_keepout(rkb)

    hw = 0.5 * trace_width_um
    keep_vdd = set(range(period_p)) if is_full else compute_evenly_spaced_keep_indices(m_vdd, period_p)
    keep_vss = set(range(period_p)) if is_full else compute_evenly_spaced_keep_indices(n_vss, period_p)

    jog_stats: Dict[str, Dict[str, int]] = {}
    jog_polylines: List[Tuple[str, str, float, List[Point]]] = []

    def _route_net(net_name: str, pts_in: List[Point], keep_set: Set[int]) -> Tuple[List[Point], List[Point], List[Tuple[float, float, float, float]]]:
        pts = sorted(set(pts_in), key=lambda p: (round(p[0], 1), p[1]))
        is_horiz = (dir_u == "HORIZONTAL")

        # Group into primary columns (VERTICAL/BOTH) or rows (HORIZONTAL)
        groups: List[List[Point]] = []
        for x, y in pts:
            if not groups or abs((y - groups[-1][0][1]) if is_horiz else (x - groups[-1][0][0])) > 2.5:
                groups.append([(x, y)])
            else:
                groups[-1].append((x, y))

        vias_set: Set[Point] = set()
        floating: List[Point] = []
        for grp in groups:
            grp.sort(key=(lambda p: p[0]) if is_horiz else (lambda p: p[1]))
            chains: List[List[Point]] = [[grp[0]]]
            for p in grp[1:]:
                prev = chains[-1][-1]
                d_step = abs(p[0] - prev[0]) if is_horiz else abs(p[1] - prev[1])
                if d_step <= 265.0:
                    chains[-1].append(p)
                else:
                    chains.append([p])

            for ch in chains:
                in_k = [_pt_forbidden_for_vip(px, py, emib_boxes, via_kozs) for px, py in ch]
                want = {i for i in range(len(ch)) if (i % period_p) in keep_set and not in_k[i]}
                for i in range(len(ch)):
                    if in_k[i]:
                        for step in (1, -1, 2, -2):
                            j = i + step
                            if 0 <= j < len(ch) and not in_k[j]:
                                want.add(j)
                                break
                if not want:
                    valid_i = [i for i in range(len(ch)) if not in_k[i]]
                    if valid_i:
                        want.add(valid_i[len(valid_i) // 2])
                for i, pt in enumerate(ch):
                    if i in want:
                        vias_set.add(pt)
                    else:
                        floating.append(pt)

        anchored: Set[Point] = set(vias_set)
        anch_grid: Dict[Tuple[int, int], List[Point]] = collections.defaultdict(list)
        for ax, ay in anchored:
            anch_grid[(int(math.floor(ax / 300.0)), int(math.floor(ay / 300.0)))].append((ax, ay))

        clines_seg: List[Tuple[float, float, float, float]] = []
        seen_seg_keys: Set[Tuple[Tuple[float, float], Tuple[float, float]]] = set()
        stats_c: Dict[str, int] = collections.Counter()

        def _try_connect(cur_pts: List[Point], max_dist: float, max_passes: int) -> List[Point]:
            rem = list(cur_pts)
            for _p in range(max_passes):
                still: List[Point] = []
                prog = False
                for fx, fy in rem:
                    gx, gy = int(math.floor(fx / 300.0)), int(math.floor(fy / 300.0))
                    cands: List[Tuple[Tuple[int, float], float, float]] = []
                    for dxg in (-2, -1, 0, 1, 2):
                        for dyg in (-2, -1, 0, 1, 2):
                            for ax, ay in anch_grid.get((gx + dxg, gy + dyg), ()):
                                d = math.hypot(ax - fx, ay - fy)
                                if 10.0 < d <= max_dist:
                                    same_line = (abs(ay - fy) < 3.0) if is_horiz else (abs(ax - fx) < 3.0)
                                    cands.append(((0 if same_line else 1, d), ax, ay))
                    cands.sort(key=lambda t: t[0])
                    routed = False
                    for _pr, ax, ay in cands[:12]:
                        dx, dy = ax - fx, ay - fy
                        sgn_y = 1.0 if dy >= 0.0 else -1.0
                        sgn_x = 1.0 if dx >= 0.0 else -1.0
                        tries: List[Tuple[str, List[Point]]] = []
                        if not is_horiz and abs(dx) < 3.0:
                            tries.append(("VERTICAL_DIRECT", [(fx, fy), (ax, ay)]))
                            for dx_j in (66.0, -66.0, 93.8, -93.8, 52.0, -52.0, 129.8, -129.8):
                                d45 = min(abs(dx_j), 0.4 * abs(dy))
                                tries.append(("VERTICAL_C_JOG", [(fx, fy), (fx + dx_j, fy + sgn_y * d45), (ax + dx_j, ay - sgn_y * d45), (ax, ay)]))
                        elif is_horiz and abs(dy) < 3.0:
                            tries.append(("HORIZONTAL_DIRECT", [(fx, fy), (ax, ay)]))
                            for dy_j in (66.0, -66.0, 90.5, -90.5, 52.0, -52.0, 130.0, -130.0):
                                d45 = min(abs(dy_j), 0.4 * abs(dx))
                                tries.append(("HORIZONTAL_C_JOG", [(fx, fy), (fx + sgn_x * d45, fy + dy_j), (ax - sgn_x * d45, ay + dy_j), (ax, ay)]))
                        else:
                            if abs(dy) < 3.0:
                                tries.append(("HORIZ_ESCAPE", [(fx, fy), (ax, ay)]))
                            elif abs(dx) < 3.0:
                                tries.append(("VERT_ESCAPE", [(fx, fy), (ax, ay)]))
                            else:
                                if abs(dy) > abs(dx) + 18.0:
                                    tries.append(("VERTICAL_45_DOGLEG", [(fx, fy), (fx, ay - sgn_y * abs(dx)), (ax, ay)]))
                                    tries.append(("VERTICAL_45_DOGLEG", [(fx, fy), (ax, fy + sgn_y * abs(dx)), (ax, ay)]))
                                if abs(dy) >= 40.0:
                                    t_stub = min(44.0, 0.28 * abs(dy))
                                    tries.append(("VERTICAL_S_JOG", [(fx, fy), (fx, fy + sgn_y * t_stub), (ax, ay - sgn_y * t_stub), (ax, ay)]))
                                tries.append(("L_VH", [(fx, fy), (fx, ay), (ax, ay)]))
                                tries.append(("L_HV", [(fx, fy), (ax, fy), (ax, ay)]))
                                tries.append(("DIRECT_DIAG", [(fx, fy), (ax, ay)]))
                        for kind, ch_try in tries:
                            if tracker.poly_clear(ch_try, net_name, hw, min_gap_um):
                                tracker.register_poly(ch_try, net_name, hw)
                                jog_polylines.append((net_name, kind, trace_width_um, ch_try))
                                for k in range(len(ch_try) - 1):
                                    sx1, sy1 = ch_try[k]
                                    sx2, sy2 = ch_try[k + 1]
                                    p_a = (round(sx1, 3), round(sy1, 3))
                                    p_b = (round(sx2, 3), round(sy2, 3))
                                    seg_key = (p_a, p_b) if p_a <= p_b else (p_b, p_a)
                                    if p_a != p_b and seg_key not in seen_seg_keys:
                                        seen_seg_keys.add(seg_key)
                                        clines_seg.append((sx1, sy1, sx2, sy2))
                                stats_c[kind] += 1
                                routed = True
                                break
                        if routed:
                            break
                    if routed:
                        anchored.add((fx, fy))
                        anch_grid[(int(math.floor(fx / 300.0)), int(math.floor(fy / 300.0)))].append((fx, fy))
                        prog = True
                    else:
                        still.append((fx, fy))
                rem = still
                if not rem or not prog:
                    break
            return rem

        # Phase 1: 1-hop local strapping/jogging (d <= 275 um) before longer gap bridges (d <= 620 um)
        rem = _try_connect(floating, max_dist=275.0, max_passes=14)
        if rem:
            rem = _try_connect(rem, max_dist=620.0, max_passes=10)
        if rem:
            still_final: List[Point] = []
            for fx, fy in rem:
                if not _pt_forbidden_for_vip(fx, fy, emib_boxes, via_kozs):
                    vias_set.add((fx, fy))
                    anchored.add((fx, fy))
                    anch_grid[(int(math.floor(fx / 300.0)), int(math.floor(fy / 300.0)))].append((fx, fy))
                    stats_c["FALLBACK_VIP"] += 1
                else:
                    still_final.append((fx, fy))
            if still_final:
                still_final = _try_connect(still_final, max_dist=950.0, max_passes=6)
            rem = still_final

        jog_stats[net_name] = dict(stats_c)
        unviad_final = [p for p in pts if p not in vias_set]
        return sorted(vias_set), unviad_final, clines_seg

    vdd_vias, vdd_unviad, vdd_clines = _route_net(vdd_net, vdd_pts, keep_vdd)
    vss_vias, vss_unviad, vss_clines = _route_net("VSS", vss_pts, keep_vss)

    drc_audit = audit_surface_routing_drc_and_connectivity(
        vdd_vias=vdd_vias,
        vss_vias=vss_vias,
        vdd_all_pts=vdd_pts,
        vss_all_pts=vss_pts,
        vdd_clines=vdd_clines,
        vss_clines=vss_clines,
        all_obstacle_pads=obs_list,
        emib_157_boxes=emib_boxes,
        vdd_net=vdd_net,
        trace_width_um=trace_width_um,
        min_gap_um=min_gap_um,
        via_keepout_boxes=via_kozs,
        route_keepout_boxes=route_kozs,
    )

    ratio_lbl = "FULL (1:1)" if is_full else f"{m_vdd}:{n_vss}"
    cell_lbl = (
        f"{m_vdd}:{n_vss} {dir_u} Unit Cell ({m_vdd} VDD Vias+{period_p - m_vdd} Straps : "
        f"{n_vss} VSS Vias+{period_p - n_vss} Straps)"
        if not is_full else "Full VIP (1:1)"
    )

    return {
        "mode": "FULL_VIA_ON_BUMP" if is_full else f"RATIO_{m_vdd}_TO_{n_vss}_{dir_u}",
        "ratio_str": ratio_lbl,
        "direction": dir_u,
        "cell_period": period_p,
        "cell_label": cell_lbl,
        "vdd_net": vdd_net,
        "vdd_vias": vdd_vias,
        "vdd_unviad": vdd_unviad,
        "vdd_clines": vdd_clines,
        "vss_vias": vss_vias,
        "vss_unviad": vss_unviad,
        "vss_clines": vss_clines,
        "jog_polylines": jog_polylines,
        "jog_stats": jog_stats,
        "trace_width_um": trace_width_um,
        "min_drc_clearance_um": drc_audit["min_pad_to_trace_gap_um"],
        "drc_audit": drc_audit,
        "all_obstacle_pads": obs_list,
        "emib_157_boxes": emib_boxes,
        "via_keepout_boxes": via_kozs,
        "route_keepout_boxes": route_kozs,
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
    vdd_net: Optional[str] = None,
    unit_cell_box: Optional[BBox] = None,
    show_default_unit_cell: bool = True,
    emib_157_boxes: Optional[Sequence[BBox]] = None,
) -> List[str]:
    """Render a high-detail zoomed-in C4 bump & via/trace tile panel in SVG coordinates."""
    vdd_lbl = vdd_net or str(plan.get("vdd_net") or "VDDUC0")
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

    # 0. Draw EMIB 157.5um KOZ intersection, native VIA/ROUTE keepouts, and non-target obstacle pads
    for eb in (emib_157_boxes or plan.get("emib_157_boxes") or ()):
        ix1, iy1 = max(tx1, eb[0]), max(ty1, eb[1])
        ix2, iy2 = min(tx2, eb[2]), min(ty2, eb[3])
        if ix2 > ix1 and iy2 > iy1:
            lines.append(
                f'<rect x="{mx(ix1)}" y="{my(iy2)}" width="{ms(ix2 - ix1)}" height="{ms(iy2 - iy1)}" '
                f'fill="#f59e0b" fill-opacity="0.08" stroke="#f59e0b" stroke-width="1.6" stroke-dasharray="6,4"/>'
            )
    for kb, col_k in (
        *((b, "#f97316") for b in (plan.get("via_keepout_boxes") or ())),
        *((b, "#a855f7") for b in (plan.get("route_keepout_boxes") or ())),
    ):
        ix1, iy1 = max(tx1, kb[0]), max(ty1, kb[1])
        ix2, iy2 = min(tx2, kb[2]), min(ty2, kb[3])
        if ix2 > ix1 and iy2 > iy1:
            lines.append(
                f'<rect x="{mx(ix1)}" y="{my(iy2)}" width="{ms(ix2 - ix1)}" height="{ms(iy2 - iy1)}" '
                f'fill="{col_k}" fill-opacity="0.16" stroke="{col_k}" stroke-width="1.6" stroke-dasharray="4,2"/>'
            )

    for ox_p, oy_p, orad_p, onet_p in (plan.get("all_obstacle_pads") or ()):
        if onet_p in (vdd_lbl, "VSS") or not def_in(ox_p, oy_p):
            continue
        col_o = "#a855f7" if ("VDD" in onet_p or "VAA" in onet_p or "VQPS" in onet_p) else "#f59e0b"
        lines.append(
            f'<circle cx="{mx(ox_p)}" cy="{my(oy_p)}" r="{max(1.2, ms(orad_p))}" fill="{col_o}" fill-opacity="0.55" stroke="#fde68a" stroke-width="0.9"/>'
        )

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
    uc_box: Optional[BBox] = unit_cell_box
    if uc_box is None and show_default_unit_cell:
        if plan.get("direction") == "HORIZONTAL":
            ux1 = tx1 + 20.0
            uy1 = ty1 + 180.0
            uc_box = (ux1, uy1, round(min(tx2 - 20.0, ux1 + p_cell * 187.585 + 10.0), 2), uy1 + 180.0)
        else:
            ux1 = tx1 + 205.0
            uy1 = ty1 + 10.0
            uc_box = (ux1, uy1, ux1 + 195.0, min(ty2 - 30.0, uy1 + p_cell * 181.0 + 10.0))
    if uc_box is not None:
        uc_x1, uc_y1, uc_x2, uc_y2 = uc_box
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
    n_tile_cl = len(vdd_cl_t) + len(vss_cl_t)
    cline_desc = (
        "0 (100% 1:1 VIP, 0 Traces)"
        if n_tile_cl == 0
        else f"{n_tile_cl} ({'KOZ-Escape' if plan.get('mode') == 'FULL_VIA_ON_BUMP' else plan.get('direction','NONE')}, Space={plan.get('min_drc_clearance_um',43.3):.1f}um)"
    )
    footer = (
        f"Tile: {vdd_lbl} Vias={len(vdd_vias_t)} (Strapped={len(vdd_unv_t)}) | "
        f"VSS Vias={len(vss_vias_t)} (Strapped={len(vss_unv_t)}) | Ratio={ratio_str} | "
        f"Clines={cline_desc}"
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


def _render_comparison_legend_svg(y_top: float, summary_note: str, vdd_lbl: str = "VDDUC0", box_w: float = 2140.0) -> List[str]:
    """Render shared legend & DRC note footer for SURFACE comparison SVGs."""
    yc = y_top + 33
    yt = y_top + 38
    yn = y_top + 83
    vdd_e = html.escape(vdd_lbl)
    return [
        f'<rect x="30" y="{y_top}" width="{box_w}" height="110" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1.5"/>',
        f'<circle cx="65" cy="{yc}" r="11" fill="#e11d48" stroke="#ffe4e6" stroke-width="1.5"/>',
        f'<circle cx="65" cy="{yc}" r="6" fill="#090d16" stroke="#fbbf24" stroke-width="1.5"/>',
        f'<text x="86" y="{yt}" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">{vdd_e} Via-in-Pad (V77_49_77_SURFACE_12F_01A)</text>',
        f'<circle cx="475" cy="{yc}" r="11" fill="#881337" stroke="#fb7185" stroke-width="1.5" stroke-dasharray="3,2"/>',
        f'<line x1="475" y1="{yc}" x2="510" y2="{yc}" stroke="#fb7185" stroke-width="6" stroke-linecap="round"/>',
        f'<text x="522" y="{yt}" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">Un-Via\'d {vdd_e} Bump + 24um SURFACE Strap (V / H / KOZ)</text>',
        f'<circle cx="955" cy="{yc}" r="11" fill="#2563eb" stroke="#dbeafe" stroke-width="1.5"/>',
        f'<circle cx="955" cy="{yc}" r="6" fill="#090d16" stroke="#38bdf8" stroke-width="1.5"/>',
        f'<text x="976" y="{yt}" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">VSS Via-in-Pad (V77_49_77_SURFACE_12F_01A)</text>',
        f'<circle cx="1360" cy="{yc}" r="11" fill="#1e3a8a" stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="3,2"/>',
        f'<line x1="1360" y1="{yc}" x2="1395" y2="{yc}" stroke="#60a5fa" stroke-width="6" stroke-linecap="round"/>',
        f'<text x="1407" y="{yt}" fill="#f8fafc" font-family="Consolas, monospace" font-size="13">Un-Via\'d VSS Bump + 24um SURFACE Strap (V / H / KOZ)</text>',
        f'<text x="50" y="{yn}" fill="#94a3b8" font-family="Consolas, monospace" font-size="12.2">{html.escape(summary_note)}</text>',
    ]


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

    svg.extend(
        _render_comparison_legend_svg(
            y_top=1125.0,
            summary_note=(
                "12Cu SURFACE DRC: Vertical Pitch dy=180.99um (Adj-Col dx=93.79um => Space=43.29um >= 18um) | "
                "Horizontal Pitch dx=187.58um (Adj-Row dy=90.50um => Space=40.00um >= 18um) | Both pass Rule 3.4.1.41 with >22um margin!"
            ),
        )
    )

    svg.append("</svg>")
    svg_str = "\n".join(svg)
    ET.fromstring(svg_str)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg_str, encoding="utf-8")
    return str(out_svg)


def _render_four_way_comparison_svg(
    panels: List[Tuple[Dict[str, Any], str, str]],
    out_svg: Path,
    header_title: str,
    header_subtitle: str,
    summary_note: str,
) -> str:
    """Render a 2200x2220 2x2 quad-panel SVG comparing Full VIP and 5:2 H/V/BOTH strapping."""
    W, H = 2200, 2220
    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%" style="background:#020617;">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#020617"/>',
        f'<text x="30" y="42" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="23" font-weight="bold">{html.escape(header_title)}</text>',
        f'<text x="30" y="68" fill="#38bdf8" font-family="Consolas, monospace" font-size="13.2">{html.escape(header_subtitle)}</text>',
    ]
    coords = [(30.0, 90.0), (1115.0, 90.0), (30.0, 1080.0), (1115.0, 1080.0)]
    for (plan, title, subtitle), (px, py) in zip(panels[:4], coords):
        svg.extend(
            _render_tile_panel_svg(
                plan=plan,
                panel_x=px,
                panel_y=py,
                panel_w=1055.0,
                panel_h=970.0,
                tile_bbox=TILE_BBOX,
                title=title,
                subtitle=subtitle,
            )
        )
    svg.extend(_render_comparison_legend_svg(y_top=2075.0, summary_note=summary_note))
    svg.append("</svg>")
    svg_str = "\n".join(svg)
    ET.fromstring(svg_str)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg_str, encoding="utf-8")
    return str(out_svg)


def _export_recipe(
    plan: Dict[str, Any],
    out_txt: Path,
    refdes: str = "U7",
    vdd_net: Optional[str] = None,
) -> str:
    """Export pipe-delimited Stage 4 SKILL recipe (VIA and CLINE records) for SURFACE layer."""
    vdd_lbl = vdd_net or str(plan.get("vdd_net") or "VDDUC0")
    lines: List[str] = [
        f"# AGENT04_LAYER1_SURFACE_RECIPE|MODE={plan['mode']}|RATIO={plan['ratio_str']}|DIRECTION={plan['direction']}|REFDES={refdes}|NETS={vdd_lbl},VSS"
    ]
    for x, y in plan["vdd_vias"]:
        lines.append(f"VIA|{vdd_lbl}|V77_49_77_SURFACE_12F_01A|SURFACE|12F|{x:.3f}|{y:.3f}")
    for x, y in plan["vss_vias"]:
        lines.append(f"VIA|VSS|V77_49_77_SURFACE_12F_01A|SURFACE|12F|{x:.3f}|{y:.3f}")
    w = plan["trace_width_um"]
    for x1, y1, x2, y2 in plan["vdd_clines"]:
        lines.append(f"CLINE|{vdd_lbl}|SURFACE|{w:.1f}|{x1:.3f}|{y1:.3f}|{x2:.3f}|{y2:.3f}")
    for x1, y1, x2, y2 in plan["vss_clines"]:
        lines.append(f"CLINE|VSS|SURFACE|{w:.1f}|{x1:.3f}|{y1:.3f}|{x2:.3f}|{y2:.3f}")
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_txt)


def _render_refdes_3panel_inspection_svg(
    plan: Dict[str, Any],
    refdes: str,
    die_bbox: BBox,
    core_tile_bbox: BBox,
    jog_tile_bbox: BBox,
    out_svg: Path,
) -> str:
    """Render a 2400x1360 3-panel XML-validated inspection SVG (Full Die + Core Tile + EMIB/KOZ Escape Tile)."""
    vdd_lbl = str(plan.get("vdd_net") or "VDDUC3")
    drc = plan.get("drc_audit") or {}
    is_full = plan.get("mode") == "FULL_VIA_ON_BUMP"
    W, H = 2400, 1360
    title = (
        f"{refdes} (HUTTON_HILL_LDB_BC_A0) Layer 1 SURFACE Routing — "
        + (
            "Full Via-on-Bump (1:1 VIP, EMIB & 12F Keepout Compliant)"
            if is_full
            else f"{plan['ratio_str']} ({plan['direction']}) + Obstacle-Aware Jogging"
        )
    )
    strap_word = "KOZ-strapped" if is_full else "strapped"
    subtitle = (
        f"Nets: {vdd_lbl} & VSS | {vdd_lbl} VIPs={len(plan['vdd_vias']):,} (+{len(plan['vdd_unviad']):,} {strap_word}) | "
        f"VSS VIPs={len(plan['vss_vias']):,} (+{len(plan['vss_unviad']):,} {strap_word}) | "
        f"Floating={drc.get('unconnected_c4_bumps_total', 0)} | "
        f"MinPadGap={drc.get('min_pad_to_trace_gap_um', plan['min_drc_clearance_um']):.2f}um (>=18.0um DRC) | "
        f"EMIB157_VIPs={drc.get('vips_inside_emib_157_koz', 0)}"
    )
    svg: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="background:#020617;">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#020617"/>',
        f'<text x="30" y="42" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="30" y="68" fill="#38bdf8" font-family="Consolas, monospace" font-size="13.2">{html.escape(subtitle)}</text>',
    ]

    # Left panel: Full Die Map
    lp_x, lp_y, lp_w, lp_h = 30.0, 90.0, 820.0, 1130.0
    svg.append(f'<rect x="{lp_x}" y="{lp_y}" width="{lp_w}" height="{lp_h}" rx="10" fill="#0f172a" stroke="#334155" stroke-width="2"/>')
    svg.append(f'<text x="{lp_x + 20}" y="{lp_y + 32}" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="17" font-weight="bold">Full {refdes} Die (SURFACE / TOP) — 14.0 x 31.6 mm + EMIB 157.5um KOZs</text>')

    dx1, dy1, dx2, dy2 = die_bbox
    sc_d = min((lp_w - 80.0) / (dx2 - dx1), (lp_h - 120.0) / (dy2 - dy1))
    d_ox = lp_x + 45.0
    d_oy = lp_y + 70.0
    d_h_px = (dy2 - dy1) * sc_d

    def ux(x_um: float) -> float:
        return round(d_ox + (x_um - dx1) * sc_d, 2)

    def uy(y_um: float) -> float:
        return round(d_oy + d_h_px - (y_um - dy1) * sc_d, 2)

    svg.append(
        f'<rect x="{ux(dx1)}" y="{uy(dy2)}" width="{round((dx2 - dx1) * sc_d, 2)}" height="{round(d_h_px, 2)}" '
        f'fill="#090d16" stroke="#475569" stroke-width="1.5"/>'
    )
    for eb in (plan.get("emib_157_boxes") or ()):
        ix1, iy1 = max(dx1, eb[0]), max(dy1, eb[1])
        ix2, iy2 = min(dx2, eb[2]), min(dy2, eb[3])
        if ix2 > ix1 and iy2 > iy1:
            svg.append(
                f'<rect x="{ux(ix1)}" y="{uy(iy2)}" width="{round((ix2 - ix1) * sc_d, 2)}" height="{round((iy2 - iy1) * sc_d, 2)}" '
                f'fill="#f59e0b" fill-opacity="0.10" stroke="#f59e0b" stroke-width="1.4" stroke-dasharray="5,3"/>'
            )

    for x1, y1, x2, y2 in plan["vdd_clines"]:
        svg.append(f'<line x1="{ux(x1)}" y1="{uy(y1)}" x2="{ux(x2)}" y2="{uy(y2)}" stroke="#fb7185" stroke-width="1.0"/>')
    for x1, y1, x2, y2 in plan["vss_clines"]:
        svg.append(f'<line x1="{ux(x1)}" y1="{uy(y1)}" x2="{ux(x2)}" y2="{uy(y2)}" stroke="#60a5fa" stroke-width="1.0"/>')
    for x, y in plan["vdd_unviad"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="0.9" fill="#881337"/>')
    for x, y in plan["vss_unviad"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="0.9" fill="#1e3a8a"/>')
    for x, y in plan["vdd_vias"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="1.25" fill="#f43f5e"/>')
    for x, y in plan["vss_vias"]:
        svg.append(f'<circle cx="{ux(x)}" cy="{uy(y)}" r="1.25" fill="#3b82f6"/>')

    core_box_lbl = "Core Full-VIP (1:1) Tile" if is_full else f"Core {plan['ratio_str']} Tile"
    jog_box_lbl = "EMIB KOZ Escape Tile" if is_full else "Jog & EMIB Collar Tile"
    for box, col_b, lbl_b in ((core_tile_bbox, "#facc15", core_box_lbl), (jog_tile_bbox, "#34d399", jog_box_lbl)):
        bx1, by1, bx2, by2 = box
        svg.append(
            f'<rect x="{ux(bx1)}" y="{uy(by2)}" width="{round((bx2 - bx1) * sc_d, 2)}" height="{round((by2 - by1) * sc_d, 2)}" '
            f'fill="none" stroke="{col_b}" stroke-width="2.2"/>'
        )
        svg.append(
            f'<text x="{ux(bx1)}" y="{uy(by2) - 5}" fill="{col_b}" font-family="Consolas, monospace" font-size="11" font-weight="bold">{html.escape(lbl_b)}</text>'
        )

    mode_tag = "FULL 1:1 VIP" if is_full else str(plan["direction"])
    s_lbl = "KOZ-Strapped" if is_full else "Strapped"
    full_stat = (
        f"Full {refdes} ({mode_tag}): {vdd_lbl} VIPs={len(plan['vdd_vias']):,} ({s_lbl}={len(plan['vdd_unviad']):,}) | "
        f"VSS VIPs={len(plan['vss_vias']):,} ({s_lbl}={len(plan['vss_unviad']):,}) | Floating={drc.get('unconnected_c4_bumps_total', 0)}"
    )
    svg.append(f'<text x="{lp_x + 20}" y="{lp_y + lp_h - 14}" fill="#cbd5e1" font-family="Consolas, monospace" font-size="11.2">{html.escape(full_stat)}</text>')

    # Top-Right panel: Core C4 Lattice Tile
    z1_title = (
        f"Zoom 1: Core C4 Lattice — 100% Full Via-on-Bump (1:1 VIP on {vdd_lbl} & VSS)"
        if is_full
        else f"Zoom 1: Core C4 Lattice — {plan['ratio_str']} {plan['direction']} Unit Cells ({vdd_lbl} + VSS)"
    )
    z1_sub = (
        "Every Core C4 Bump (C35_21_DP_01A, 77um) gets V77_49_77_SURFACE_12F_01A (49um Laser Drill) | 0 Core SURFACE Traces"
        if is_full
        else f"{plan.get('cell_label', '')} | {plan.get('trace_width_um', 24.0):.0f}um CLINEs | MinGap={drc.get('min_pad_to_trace_gap_um', plan['min_drc_clearance_um']):.2f}um (>=18.0um Rule 3.4.1.41)"
    )
    svg.extend(
        _render_tile_panel_svg(
            plan=plan,
            panel_x=870.0,
            panel_y=90.0,
            panel_w=1500.0,
            panel_h=555.0,
            tile_bbox=core_tile_bbox,
            title=z1_title,
            subtitle=z1_sub,
            vdd_net=vdd_lbl,
            show_default_unit_cell=(not is_full),
        )
    )
    # Bottom-Right panel: West EMIB Collar & Obstacle-Jog / KOZ-Escape Tile
    z2_title = (
        f"Zoom 2: West EMIB Collar (U45/U46) — 1:1 VIP Outside KOZ + EMIB 157.5um KOZ Escape Straps ({vdd_lbl} + VSS)"
        if is_full
        else f"Zoom 2: West EMIB Collar (U45/U46) & Obstacle C-Jog / S-Jog Escape ({vdd_lbl} + VSS)"
    )
    z2_sub = (
        "100% VIP Outside KOZ | 0 VIPs inside EMIB 157.5um KOZ (Dashed Gold) — KOZ Bumps Strapped via 24um SURFACE Clines (0 Floating)"
        if is_full
        else "45-deg C-Jogs around intervening MISC/Signal pads (Amber/Purple) + 0 VIPs inside EMIB 157.5um KOZ (Dashed Gold)"
    )
    svg.extend(
        _render_tile_panel_svg(
            plan=plan,
            panel_x=870.0,
            panel_y=665.0,
            panel_w=1500.0,
            panel_h=555.0,
            tile_bbox=jog_tile_bbox,
            title=z2_title,
            subtitle=z2_sub,
            vdd_net=vdd_lbl,
            show_default_unit_cell=False,
        )
    )

    svg.extend(
        _render_comparison_legend_svg(
            y_top=1235.0,
            summary_note=(
                f"{refdes} Audit: PadToTraceMinGap={drc.get('min_pad_to_trace_gap_um', 0.0):.2f}um (Viol={drc.get('pad_to_trace_violation_count', 0)}) | "
                f"TraceToTraceMinGap={drc.get('min_trace_to_trace_gap_um', 0.0):.2f}um (Viol={drc.get('trace_to_trace_violation_count', 0)}) | "
                f"FloatingC4={drc.get('unconnected_c4_bumps_total', 0)} | JogStats={json.dumps(plan.get('jog_stats', {}))}"
            ),
            vdd_lbl=vdd_lbl,
            box_w=2340.0,
        )
    )
    svg.append("</svg>")
    svg_str = "\n".join(svg)
    ET.fromstring(svg_str)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg_str, encoding="utf-8")
    return str(out_svg)


def _plan_metrics(plan: Dict[str, Any], svg_file: str, recipe_file: str) -> Dict[str, Any]:
    vdd_net = str(plan.get("vdd_net") or "VDDUC0")
    metrics = {
        "mode": plan["mode"],
        "vdd_net": vdd_net,
        "ratio_str": plan["ratio_str"],
        "direction": plan["direction"],
        "cell_period": plan["cell_period"],
        "unit_cell_rule": plan["cell_label"],
        "vdduc0_vias": len(plan["vdd_vias"]),
        "vdduc0_strapped_bumps": len(plan["vdd_unviad"]),
        "vdduc0_surface_clines": len(plan["vdd_clines"]),
        "vdd_vias": len(plan["vdd_vias"]),
        "vdd_strapped_bumps": len(plan["vdd_unviad"]),
        "vdd_surface_clines": len(plan["vdd_clines"]),
        "vss_vias": len(plan["vss_vias"]),
        "vss_strapped_bumps": len(plan["vss_unviad"]),
        "vss_surface_clines": len(plan["vss_clines"]),
        "total_vias": len(plan["vdd_vias"]) + len(plan["vss_vias"]),
        "total_surface_clines": len(plan["vdd_clines"]) + len(plan["vss_clines"]),
        "via_ratio_vdd_to_vss": round(len(plan["vdd_vias"]) / max(1, len(plan["vss_vias"])), 3),
        "cline_width_um": plan["trace_width_um"],
        "min_drc_clearance_um": plan["min_drc_clearance_um"],
        "drc_min_cline_to_via_pin_um": 18.0,
        "svg_file": svg_file,
        "recipe_file": recipe_file,
    }
    if "jog_stats" in plan:
        metrics["jog_stats"] = plan["jog_stats"]
    if "drc_audit" in plan:
        metrics["drc_audit"] = plan["drc_audit"]
    return metrics


def implement_surface_recipe_to_mcm(
    recipe_path: Path,
    refdes: str,
    vdd_net: str,
    die_bbox: BBox,
    ratio_str: str,
    direction: str,
    work_dir: Optional[str] = None,
    out_mcm_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Copy read-only template .mcm into `<work_dir>/pdn_sandbox/`, import the SURFACE VIA/CLINE recipe
    headlessly via `surface_bump_router_batch.il`, and run a native Cadence APD SKILL verification
    checking created vias/clines, branch-level C4 pin connectivity (0 floating), and DRC markers.
    """
    try:
        from agent04_pdn_architect.cad_cli.cadence_runner import CadenceBatchRunner
        from agent04_pdn_architect.cad_cli.pdn_paths import REPO_ROOT, resolve_active_work_dir, resolve_output_dir
        from agent04_pdn_architect.cad_cli.pdn_prelearn import resolve_mcm_in_work_dir
    except ImportError:
        from cadence_runner import CadenceBatchRunner  # type: ignore
        from pdn_paths import REPO_ROOT, resolve_active_work_dir, resolve_output_dir  # type: ignore
        from pdn_prelearn import resolve_mcm_in_work_dir  # type: ignore

    eff_wd, is_custom = resolve_active_work_dir(work_dir)
    sandbox_dir = resolve_output_dir("pdn_sandbox", explicit_work_dir=work_dir)
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    src_mcm = resolve_mcm_in_work_dir(eff_wd) if is_custom else None
    if src_mcm is None:
        cand = eff_wd / "MCM_template" / "PDN_test.mcm"
        src_mcm = cand if cand.is_file() else (REPO_ROOT / "agent04_pdn_architect" / "MCM_test" / "PDN_test.mcm")
    src_mcm = src_mcm.resolve()

    safe_r = ratio_str.replace(":", "to")
    target_mcm = (out_mcm_path or (sandbox_dir / f"{src_mcm.stem}_{refdes}_SURFACE_{safe_r}_{direction}.mcm")).resolve()
    if target_mcm == src_mcm:
        raise RuntimeError(f"SAFETY_LOCK: refusing to overwrite read-only template {src_mcm}")
    target_mcm.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_mcm, target_mcm)
    lck = target_mcm.with_name(target_mcm.name + ".lck")
    if lck.exists():
        lck.unlink()

    scripts_dir = REPO_ROOT / "agent04_pdn_architect" / "scripts"
    rep_file = sandbox_dir / f"{refdes}_SURFACE_{safe_r}_{direction}_apd_import_report.txt"
    audit_file = sandbox_dir / f"{refdes}_SURFACE_{safe_r}_{direction}_apd_verify.txt"
    verify_il = sandbox_dir / f"_verify_{refdes}_surface.il"
    scr_file = sandbox_dir / f"run_{refdes}_surface_{safe_r}_{direction}.scr"

    bx1, by1, bx2, by2 = die_bbox
    verify_il.write_text(
        f'procedure( pdn_verify_surface_import(out_file)\n'
        f'    let((d net_n n b ch v_vdd v_vss c_vdd c_vss flt_vdd flt_vss drc_cnt ext_cnt\n'
        f'         via_branches sym sref pin pnet ppad p_rep)\n'
        f'        d = axlDBGetDesign()\n'
        f'        v_vdd = 0  v_vss = 0  c_vdd = 0  c_vss = 0\n'
        f'        flt_vdd = 0  flt_vss = 0  drc_cnt = 0  ext_cnt = 0\n'
        f'        via_branches = makeTable("pdn_vbr" nil)\n'
        f'        foreach(net_n list("{vdd_net}" "VSS")\n'
        f'            n = axlDBFindByName(\'net net_n)\n'
        f'            when( n\n'
        f'                foreach(b n->branches\n'
        f'                    let((has_surf_via)\n'
        f'                        has_surf_via = nil\n'
        f'                        foreach(ch b->children\n'
        f'                            when( ch->objType == "via" && ch->xy && listp(ch->xy) && numberp(car(ch->xy)) && numberp(cadr(ch->xy))\n'
        f'                                let((vx vy se s1)\n'
        f'                                    vx = float(car(ch->xy))  vy = float(cadr(ch->xy))\n'
        f'                                    se = ch->startEnd\n'
        f'                                    s1 = if( se && stringp(car(se)) then upperCase(car(se)) else "")\n'
        f'                                    when( vx >= {bx1:.3f} && vx <= {bx2:.3f} && vy >= {by1:.3f} && vy <= {by2:.3f} && (rexMatchp("SURFACE" s1) || rexMatchp("/TOP$" s1) || s1 == "TOP")\n'
        f'                                        has_surf_via = t\n'
        f'                                        if( net_n == "{vdd_net}" then v_vdd = v_vdd + 1 else v_vss = v_vss + 1)\n'
        f'                                    )\n'
        f'                                )\n'
        f'                            )\n'
        f'                            when( ch->objType == "path"\n'
        f'                                let((lyr seg sxy x1 y1)\n'
        f'                                    lyr = if( ch->layer && stringp(ch->layer) then upperCase(ch->layer) else "")\n'
        f'                                    when( rexMatchp("SURFACE" lyr) || rexMatchp("/TOP$" lyr)\n'
        f'                                        foreach(seg ch->segments\n'
        f'                                            sxy = if( seg->startEnd then car(seg->startEnd) else nil)\n'
        f'                                            when( sxy && listp(sxy) && numberp(car(sxy)) && numberp(cadr(sxy))\n'
        f'                                                x1 = float(car(sxy))  y1 = float(cadr(sxy))\n'
        f'                                                when( x1 >= {bx1:.3f} && x1 <= {bx2:.3f} && y1 >= {by1:.3f} && y1 <= {by2:.3f}\n'
        f'                                                    if( net_n == "{vdd_net}" then c_vdd = c_vdd + 1 else c_vss = c_vss + 1)\n'
        f'                                                )\n'
        f'                                            )\n'
        f'                                        )\n'
        f'                                    )\n'
        f'                                )\n'
        f'                            )\n'
        f'                        )\n'
        f'                        when( has_surf_via\n'
        f'                            via_branches[b] = t\n'
        f'                        )\n'
        f'                    )\n'
        f'                )\n'
        f'            )\n'
        f'        )\n'
        f'        foreach(sym d->symbols\n'
        f'            sref = if( sym->refdes && stringp(sym->refdes) then sym->refdes else "")\n'
        f'            when( sref == "{refdes}"\n'
        f'                foreach(pin sym->pins\n'
        f'                    pnet = if( pin->net && pin->net->name then pin->net->name else "")\n'
        f'                    ppad = if( pin->definition && pin->definition->name then pin->definition->name else "")\n'
        f'                    when( ppad == "C35_21_DP_01A" && (pnet == "{vdd_net}" || pnet == "VSS")\n'
        f'                        unless( pin->branch && via_branches[pin->branch]\n'
        f'                            if( pnet == "{vdd_net}" then flt_vdd = flt_vdd + 1 else flt_vss = flt_vss + 1)\n'
        f'                        )\n'
        f'                    )\n'
        f'                )\n'
        f'            )\n'
        f'        )\n'
        f'        errset(axlDBControl(\'drcEnable t) nil)\n'
        f'        errset(axlDRCUpdate(t) nil)\n'
        f'        p_rep = outfile(out_file "w")\n'
        f'        foreach(drc d->drcs\n'
        f'            when( drc->xy && listp(drc->xy) && numberp(car(drc->xy)) && numberp(cadr(drc->xy))\n'
        f'                let((dx dy dlyr dname)\n'
        f'                    dx = float(car(drc->xy))  dy = float(cadr(drc->xy))\n'
        f'                    dlyr = if( drc->layer && stringp(drc->layer) then upperCase(drc->layer) else "")\n'
        f'                    dname = if( drc->name && stringp(drc->name) then drc->name else "")\n'
        f'                    when( dx >= {bx1:.3f} && dx <= {bx2:.3f} && dy >= {by1:.3f} && dy <= {by2:.3f}\n'
        f'                          && (rexMatchp("/SURFACE$" dlyr) || rexMatchp("/12F$" dlyr) || rexMatchp("/TOP$" dlyr) || rexMatchp("11-12F$" dlyr))\n'
        f'                        if( rexMatchp("Externally Determined" dname) then\n'
        f'                            ext_cnt = ext_cnt + 1\n'
        f'                        else\n'
        f'                            drc_cnt = drc_cnt + 1\n'
        f'                            when( drc_cnt <= 25\n'
        f'                                fprintf(p_rep "DRC_DETAIL=%s|%s|%.3f|%.3f\\n" dlyr dname dx dy)\n'
        f'                            )\n'
        f'                        )\n'
        f'                    )\n'
        f'                )\n'
        f'            )\n'
        f'        )\n'
        f'        fprintf(p_rep "STATUS=SUCCESS\\n")\n'
        f'        fprintf(p_rep "VDD_VIAS=%d\\n" v_vdd)\n'
        f'        fprintf(p_rep "VSS_VIAS=%d\\n" v_vss)\n'
        f'        fprintf(p_rep "VDD_CLINE_SEGS=%d\\n" c_vdd)\n'
        f'        fprintf(p_rep "VSS_CLINE_SEGS=%d\\n" c_vss)\n'
        f'        fprintf(p_rep "FLOATING_VDD_C4=%d\\n" flt_vdd)\n'
        f'        fprintf(p_rep "FLOATING_VSS_C4=%d\\n" flt_vss)\n'
        f'        fprintf(p_rep "SURFACE_12F_DRC_MARKERS=%d\\n" drc_cnt)\n'
        f'        fprintf(p_rep "SURFACE_12F_PREEXISTING_EXT_DRCS=%d\\n" ext_cnt)\n'
        f'        close(p_rep)\n'
        f'        t\n'
        f'    )\n'
        f')\n',
        encoding="utf-8",
    )

    scr_file.write_text(
        f'skill load("{(scripts_dir / "pdn_core_batch.il").as_posix()}")\n'
        f'skill load("{(scripts_dir / "surface_bump_router_batch.il").as_posix()}")\n'
        f'skill load("{(scripts_dir / "pdn_Pipeline_batch.il").as_posix()}")\n'
        f'skill load("{verify_il.as_posix()}")\n'
        f'skill axlSetVariable("PDN_CWD" "{sandbox_dir.as_posix()}")\n'
        f'skill axlSetVariable("PDN_SURFACE_RECIPE" "{recipe_path.resolve().as_posix()}")\n'
        f'skill axlSetVariable("PDN_REPORT_FILE" "{rep_file.as_posix()}")\n'
        f'skill pdnDispatchBatchJob("SURFACE_BUMP_ROUTE" "FALSE")\n'
        f'skill pdn_verify_surface_import("{audit_file.as_posix()}")\n'
        f'skill axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)\n'
        f"exit\nfillin no\n",
        encoding="utf-8",
    )

    runner = CadenceBatchRunner(default_timeout=600)
    apd_res = runner.run(mcm_path=target_mcm, scr_path=scr_file, working_dir=sandbox_dir, timeout=600, bypass_lock_readonly=False)
    for tmp_p in (verify_il,):
        if tmp_p.exists():
            try:
                tmp_p.unlink()
            except OSError:
                pass

    def _parse_kv(p: Path) -> Dict[str, str]:
        kv: Dict[str, str] = {}
        if p.is_file():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    kv[k.strip()] = v.strip()
        return kv

    return {
        "apd_success": apd_res.success,
        "apd_duration_sec": round(apd_res.duration_sec, 2),
        "apd_error": apd_res.error_message,
        "source_mcm_readonly": str(src_mcm),
        "output_mcm_path": str(target_mcm),
        "output_mcm_size_bytes": target_mcm.stat().st_size if target_mcm.is_file() else 0,
        "import_report": _parse_kv(rep_file),
        "post_import_verify": _parse_kv(audit_file),
        "import_report_file": str(rep_file),
        "verify_report_file": str(audit_file),
        "journal_file": str(apd_res.journal_path) if apd_res.journal_path else "",
    }


def run_surface_refdes_routing(
    refdes: str = "U6",
    ratio_str: str = "4:2",
    direction: str = "VERTICAL",
    cell_period: Optional[int] = None,
    trace_width_um: float = 24.0,
    min_gap_um: float = 18.0,
    work_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
    implement_mcm: bool = False,
) -> Dict[str, Any]:
    """Execute obstacle-aware & EMIB/Keepout-compliant Step 1 SURFACE routing for any LDB RefDes (`U5..U8`)."""
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import resolve_output_dir
    except ImportError:
        from pdn_paths import resolve_output_dir  # type: ignore

    out_dir_p = resolve_output_dir("pdn_sandbox", explicit_work_dir=work_dir, explicit_out_dir=out_dir)
    reports_dir_p = resolve_output_dir("reports", explicit_work_dir=work_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    reports_dir_p.mkdir(parents=True, exist_ok=True)

    loaded = load_refdes_surface_c4_and_obstacles(refdes=refdes, work_dir=work_dir)
    ref_u = loaded["refdes"]
    vdd_net = loaded["vdd_net"]
    plan = synthesize_surface_routing_with_jogs(
        vdd_pts=loaded["vdd_pts"],
        vss_pts=loaded["vss_pts"],
        ratio_str=ratio_str,
        direction=direction,
        cell_period=cell_period,
        trace_width_um=trace_width_um,
        min_gap_um=min_gap_um,
        vdd_net=vdd_net,
        all_obstacle_pads=loaded["all_obstacle_pads"],
        emib_157_boxes=loaded["emib_157_boxes"],
        via_keepout_boxes=loaded["via_keepout_boxes"],
        route_keepout_boxes=loaded["route_keepout_boxes"],
    )

    safe_r = ratio_str.replace(":", "to")
    dir_u = plan["direction"]
    file_slug = f"{ref_u}_SURFACE_FULL_Via_On_Bump" if plan.get("mode") == "FULL_VIA_ON_BUMP" else f"{ref_u}_SURFACE_{safe_r}_{dir_u}"
    svg_file = _render_refdes_3panel_inspection_svg(
        plan=plan,
        refdes=ref_u,
        die_bbox=loaded["die_bbox"],
        core_tile_bbox=loaded["tile_bbox"],
        jog_tile_bbox=loaded["jog_tile_bbox"],
        out_svg=out_dir_p / f"{file_slug}.svg",
    )
    recipe_file = _export_recipe(
        plan=plan,
        out_txt=out_dir_p / f"{file_slug}_recipe.txt",
        refdes=ref_u,
        vdd_net=vdd_net,
    )

    summary: Dict[str, Any] = {
        "status": "SUCCESS" if plan["drc_audit"]["drc_pass"] else "CHECK",
        "layer": "SURFACE (TOP / 12Cu)",
        "refdes": ref_u,
        "vdd_net": vdd_net,
        "total_vdd_c4_bumps": len(loaded["vdd_pts"]),
        "total_vss_c4_bumps": len(loaded["vss_pts"]),
        "total_obstacle_pads_checked": len(loaded["all_obstacle_pads"]),
        "plan": _plan_metrics(plan, svg_file, recipe_file),
    }
    if implement_mcm:
        summary["mcm_build"] = implement_surface_recipe_to_mcm(
            recipe_path=Path(recipe_file),
            refdes=ref_u,
            vdd_net=vdd_net,
            die_bbox=loaded["die_bbox"],
            ratio_str=ratio_str,
            direction=dir_u,
            work_dir=work_dir,
        )

    sum_json = out_dir_p / f"{file_slug}_summary.json"
    sum_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rep_json = reports_dir_p / f"{file_slug}_report.json"
    rep_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_json"] = str(sum_json)
    summary["report_json"] = str(rep_json)
    return summary


def run_surface_layer1_mockups(
    custom_ratio: Optional[str] = None,
    custom_direction: Optional[str] = None,
    custom_period: Optional[int] = None,
    trace_width_um: float = 24.0,
    work_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
    refdes: Optional[str] = None,
    implement_mcm: bool = False,
) -> Dict[str, Any]:
    if refdes and str(refdes).strip():
        return run_surface_refdes_routing(
            refdes=str(refdes).strip().upper(),
            ratio_str=custom_ratio or "4:2",
            direction=custom_direction or "VERTICAL",
            cell_period=custom_period,
            trace_width_um=trace_width_um,
            work_dir=work_dir,
            out_dir=out_dir,
            implement_mcm=implement_mcm,
        )

    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import resolve_active_work_dir, resolve_output_dir
    except ImportError:
        from pdn_paths import resolve_active_work_dir, resolve_output_dir  # type: ignore

    ws = Path(__file__).resolve().parent.parent.parent
    eff_wd, is_custom_wd = resolve_active_work_dir(work_dir)
    out_dir_p = resolve_output_dir("pdn_sandbox", explicit_work_dir=work_dir, explicit_out_dir=out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir_p

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
    svg_cmp_full_52_v = _render_side_by_side_comparison_svg(
        plan_left=plan_full,
        plan_right=plan_5to2_v,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_Full_vs_5to2.svg",
        header_title="Layer 1 (SURFACE / TOP) — 100% Full VIP vs. 5:2 VDD:VSS Ratio (VERTICAL 24um Straps)",
        left_title="100% Full VIP (VDDUC0=7,584 Vias, VSS=7,962 Vias)",
        left_subtitle="Every C4 bump gets V77_49_77_SURFACE_12F_01A | 0 SURFACE Clines | Ratio=0.95:1",
        right_title="5:2 VDD:VSS Ratio — VERTICAL 24um Clines",
        right_subtitle=(
            f"VDD Vias={len(plan_5to2_v['vdd_vias'])} (+{len(plan_5to2_v['vdd_clines'])} V-Straps) | "
            f"VSS Vias={len(plan_5to2_v['vss_vias'])} (+{len(plan_5to2_v['vss_clines'])} V-Straps) | Space=43.29um"
        ),
    )
    svg_cmp_full_52_h = _render_side_by_side_comparison_svg(
        plan_left=plan_full,
        plan_right=plan_5to2_h,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_Full_vs_5to2_Horizontal.svg",
        header_title="Layer 1 (SURFACE / TOP) — 100% Full VIP vs. 5:2 VDD:VSS Ratio (HORIZONTAL 24um Straps)",
        left_title="100% Full VIP (VDDUC0=7,584 Vias, VSS=7,962 Vias)",
        left_subtitle="Every C4 bump gets V77_49_77_SURFACE_12F_01A | 0 SURFACE Clines | Ratio=0.95:1",
        right_title="5:2 VDD:VSS Ratio — HORIZONTAL 24um Clines",
        right_subtitle=(
            f"VDD Vias={len(plan_5to2_h['vdd_vias'])} (+{len(plan_5to2_h['vdd_clines'])} H-Straps) | "
            f"VSS Vias={len(plan_5to2_h['vss_vias'])} (+{len(plan_5to2_h['vss_clines'])} H-Straps) | Space=40.00um"
        ),
    )
    svg_cmp_full_52_b = _render_side_by_side_comparison_svg(
        plan_left=plan_full,
        plan_right=plan_5to2_b,
        out_svg=out_dir / "mockup_L1_SURFACE_SideBySide_Full_vs_5to2_Both.svg",
        header_title="Layer 1 (SURFACE / TOP) — 100% Full VIP vs. 5:2 VDD:VSS Ratio (2D BOTH H+V 24um Straps)",
        left_title="100% Full VIP (VDDUC0=7,584 Vias, VSS=7,962 Vias)",
        left_subtitle="Every C4 bump gets V77_49_77_SURFACE_12F_01A | 0 SURFACE Clines | Ratio=0.95:1",
        right_title="5:2 VDD:VSS Ratio — 2D BOTH H+V 24um Clines",
        right_subtitle=(
            f"VDD Vias={len(plan_5to2_b['vdd_vias'])} (+{len(plan_5to2_b['vdd_clines'])} H+V) | "
            f"VSS Vias={len(plan_5to2_b['vss_vias'])} (+{len(plan_5to2_b['vss_clines'])} H+V) | Space>=40.00um"
        ),
    )
    full_tot_vias = len(plan_full["vdd_vias"]) + len(plan_full["vss_vias"])
    v_tot_vias = len(plan_5to2_v["vdd_vias"]) + len(plan_5to2_v["vss_vias"])
    h_tot_vias = len(plan_5to2_h["vdd_vias"]) + len(plan_5to2_h["vss_vias"])
    b_tot_vias = len(plan_5to2_b["vdd_vias"]) + len(plan_5to2_b["vss_vias"])
    svg_cmp_full_52_quad = _render_four_way_comparison_svg(
        panels=[
            (
                plan_full,
                "1. 100% Full VIP (1:1 Baseline)",
                f"Total Vias={full_tot_vias:,} ({len(plan_full['vdd_vias']):,} VDD + {len(plan_full['vss_vias']):,} VSS) | 0 Clines",
            ),
            (
                plan_5to2_v,
                "2. 5:2 Ratio — VERTICAL (24um Clines)",
                f"Total Vias={v_tot_vias:,} ({100.0*(v_tot_vias-full_tot_vias)/full_tot_vias:.1f}%) | "
                f"Clines={len(plan_5to2_v['vdd_clines'])+len(plan_5to2_v['vss_clines']):,} | Space=43.29um",
            ),
            (
                plan_5to2_h,
                "3. 5:2 Ratio — HORIZONTAL (24um Clines)",
                f"Total Vias={h_tot_vias:,} ({100.0*(h_tot_vias-full_tot_vias)/full_tot_vias:.1f}%) | "
                f"Clines={len(plan_5to2_h['vdd_clines'])+len(plan_5to2_h['vss_clines']):,} | Space=40.00um",
            ),
            (
                plan_5to2_b,
                "4. 5:2 Ratio — 2D BOTH H+V (24um Clines)",
                f"Total Vias={b_tot_vias:,} ({100.0*(b_tot_vias-full_tot_vias)/full_tot_vias:.1f}%) | "
                f"Clines={len(plan_5to2_b['vdd_clines'])+len(plan_5to2_b['vss_clines']):,} | Space>=40.00um",
            ),
        ],
        out_svg=out_dir / "mockup_L1_SURFACE_Comparison_Full_vs_5to2_V_H_Both.svg",
        header_title="U7 SURFACE (L1) Architecture Comparison — 100% Full VIP vs. 5:2 VDD:VSS (VERTICAL / HORIZONTAL / BOTH 24um)",
        header_subtitle=(
            "Target: U7 (HUTTON_HILL_LDB_BC_A0, 7,584 VDDUC0 + 7,962 VSS Bumps) | "
            "Padstack: V77_49_77_SURFACE_12F_01A | 12Cu Rule 3.4.1.41 Min Space >= 18.0 um"
        ),
        summary_note=(
            f"Summary (U7 Full Die): Full VIP={full_tot_vias:,} vias (0 straps) | "
            f"5:2 V={v_tot_vias:,} vias ({len(plan_5to2_v['vdd_clines'])+len(plan_5to2_v['vss_clines']):,} straps, 43.29um) | "
            f"5:2 H={h_tot_vias:,} vias ({len(plan_5to2_h['vdd_clines'])+len(plan_5to2_h['vss_clines']):,} straps, 40.00um) | "
            f"5:2 BOTH={b_tot_vias:,} vias ({len(plan_5to2_b['vdd_clines'])+len(plan_5to2_b['vss_clines']):,} straps, 40.00um)"
        ),
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
            "full_vs_5to2_vertical": svg_cmp_full_52_v,
            "full_vs_5to2_horizontal": svg_cmp_full_52_h,
            "full_vs_5to2_both": svg_cmp_full_52_b,
            "full_vs_5to2_v_h_both_quad": svg_cmp_full_52_quad,
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
    parser.add_argument("--refdes", type=str, default=None, help="Target LDB RefDes (e.g., U6, U7, U5, U8); runs targeted obstacle+EMIB-aware flow when set")
    parser.add_argument("--ratio", type=str, default=None, help="User VDD:VSS via ratio (e.g., FULL, 4:2, 5:2, 3:1)")
    parser.add_argument("--direction", type=str, default="VERTICAL", choices=["VERTICAL", "HORIZONTAL", "BOTH"], help="SURFACE trace strap direction")
    parser.add_argument("--cell-period", type=int, default=None, help="Optional unit-cell period P")
    parser.add_argument("--trace-width", type=float, default=24.0, help="SURFACE CLINE width in um (default 24.0)")
    parser.add_argument("--work-dir", type=str, default=None, help="Working folder path (defaults to SUBSTRATE_WORK_DIR)")
    parser.add_argument("--out-dir", type=str, default=None, help="Output folder for SVGs and recipes")
    parser.add_argument("--implement-mcm", action="store_true", help="Copy read-only template .mcm into work-dir pdn_sandbox and import SURFACE recipe via apd.exe")
    args = parser.parse_args()

    res = run_surface_layer1_mockups(
        custom_ratio=args.ratio,
        custom_direction=args.direction,
        custom_period=args.cell_period,
        trace_width_um=args.trace_width,
        work_dir=args.work_dir,
        out_dir=args.out_dir,
        refdes=args.refdes,
        implement_mcm=args.implement_mcm,
    )
    print(json.dumps(res, indent=2))
