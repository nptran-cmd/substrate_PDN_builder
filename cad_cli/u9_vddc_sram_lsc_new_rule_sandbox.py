"""
Sandbox Generator & Comparator: U9 (`VDDC0` + `VDD_0P8_SRAM_CC0`) `0201` LSC Placement
Under New Direct SRO Rules + Mechanical Recess Cavity Rules:
  - BGA SRO to LSC SRO >= 395.0 um
  - LSC SRO to LSC SRO >= 390.0 um
  - BGA SRO to LSC_CAVITY >= 254.0 um (>= 250.0 um spec) & BGA Cu to Cavity >= 178.0 um
  - LSC SRO to LSC_CAVITY >= 225.0 um
  - Recess Mill Radius R_mill = 508.0 um, Cavity Web >= 508.0 um, 0 EMIB Shadow Overlap

Generates strictly aligned (non-zigzag), 180 deg alternating `CONDUCTOR/BASE` LSC arrays,
compares directly against original `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt` (with fallback
to `agent04_pdn_architect/stage1_inputs/`), and exports an XML-validated comparison SVG +
JSON/CSV audit into `pdn_sandbox/`.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_CAD_CLI_DIR = Path(__file__).resolve().parent
if str(_CAD_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CAD_CLI_DIR))

from curved_recess_and_lsc_engine import (  # noqa: E402
    _pt_in_poly,
    _pt_to_poly_boundary_dist,
    edt_2d_exact,
    extract_marching_squares_loops,
)
from multi_rail_polygon_engine import U9_EMIB_BRIDGES  # noqa: E402

BBox = Tuple[float, float, float, float]
DEFAULT_HH_DUMP = Path(
    r"<agent_workspace>\mcm_allegro\HH_Nguyen_2026-1023_1900_TO_v8_dump.txt"
)

BGA_TO_LSC_SRO_UM = 395.0
LSC_TO_LSC_SRO_UM = 390.0
LSC_SRO_SHORT_UM = 300.0
LSC_SRO_LONG_UM = 820.0
LSC_PIN_HALF_PITCH_UM = 260.0
LSC_PAD_SRO_UM = 300.0

BGA_SRO_TO_CAVITY_UM = 254.0
LSC_SRO_TO_CAVITY_UM = 225.0
EXT_CU_TO_CAVITY_UM = 178.0
CAVITY_MILL_RADIUS_UM = 508.0
CAVITY_WEB_MIN_UM = 508.0
BGA_CU_OVER_SRO_UM = 35.0
RECESS_GRID_STEP_UM = 14.0


@dataclass(frozen=True)
class BgaBall:
    x: float
    y: float
    sro_r: float
    net: str
    padstack: str


@dataclass(frozen=True)
class LscCap:
    refdes: str
    pocket_id: str
    x: float
    y: float
    rot_deg: float
    pin1_net: str
    pin2_net: str

    @property
    def sro_half_extents(self) -> Tuple[float, float]:
        if int(round(self.rot_deg)) % 180 == 0:
            return (150.0, 410.0)
        return (410.0, 150.0)

    @property
    def pin_coords(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        r = int(round(self.rot_deg)) % 360
        if r == 0:
            return ((self.x, self.y + LSC_PIN_HALF_PITCH_UM), (self.x, self.y - LSC_PIN_HALF_PITCH_UM))
        if r == 180:
            return ((self.x, self.y - LSC_PIN_HALF_PITCH_UM), (self.x, self.y + LSC_PIN_HALF_PITCH_UM))
        if r == 90:
            return ((self.x - LSC_PIN_HALF_PITCH_UM, self.y), (self.x + LSC_PIN_HALF_PITCH_UM, self.y))
        return ((self.x + LSC_PIN_HALF_PITCH_UM, self.y), (self.x - LSC_PIN_HALF_PITCH_UM, self.y))


U9_POCKETS: List[Tuple[str, str, BBox]] = [
    ("P3_WEST_COL", "West Col P3", (-11000.0, 18600.0, -8600.0, 29400.0)),
    ("P4_MID_EAST_COL", "Mid-East Col P4", (3700.0, 18600.0, 6100.0, 29400.0)),
    ("P5_EAST_DUAL", "East Dual P5", (8500.0, 18600.0, 12700.0, 29400.0)),
    ("P6_CENTER_DUAL", "Center Dual P6", (-4500.0, 20000.0, -400.0, 28500.0)),
    ("P9_NW_TOP", "NW Top P9", (-13500.0, 30800.0, -1200.0, 34100.0)),
    ("P10_NE_TOP", "NE Top P10", (1200.0, 30800.0, 13500.0, 34100.0)),
]

# Verified 12B VDD_0P8_SRAM_CC0 islands inside U9 (`HH_Nguyen_2026-1023_1900_TO_v8_dump.txt` fallback)
DEFAULT_SRAM0_12B_ISLANDS: List[BBox] = [
    (-5522.4, 18616.8, -3027.6, 23893.3),
    (-5494.4, 24543.0, -3032.5, 28880.6),
    (-1827.2, 18785.4, 252.6, 23893.8),
    (-1815.1, 24505.4, 250.1, 28880.7),
    (7900.4, 22108.0, 9943.5, 26506.5),
    (11173.6, 21902.7, 13302.2, 26256.1),
]


def _pocket_id_for_xy(x: float, y: float) -> str:
    if x < -7000.0 and y < 30000.0:
        return "P3_WEST_COL"
    if 2000.0 < x < 7000.0 and y < 30000.0:
        return "P4_MID_EAST_COL"
    if x > 7000.0 and y < 30000.0:
        return "P5_EAST_DUAL"
    if -7000.0 <= x <= 2000.0 and y < 30000.0:
        return "P6_CENTER_DUAL"
    if x < 0.0 and y >= 30000.0:
        return "P9_NW_TOP"
    return "P10_NE_TOP"


def _bga_sro_radius(padstack: str) -> float:
    u = padstack.upper()
    if "560" in u:
        return 280.0
    if "480" in u:
        return 240.0
    if "350" in u:
        return 175.0
    return 125.0


def load_u9_data(
    hh_dump_path: Optional[Path],
    stage1_dir: Path,
) -> Tuple[List[BgaBall], List[LscCap], List[BBox], BBox, str]:
    """Load U9 A1 BGA balls, original U9 LSCs, and 12B plane geometry from HH*dump.txt or stage1_inputs."""
    bgas: List[BgaBall] = []
    orig_lscs: List[LscCap] = []
    sram_12b: List[BBox] = []
    vddc0_12b: BBox = (-15048.4, 16554.1, 15020.1, 33155.4)

    if hh_dump_path and hh_dump_path.is_file():
        caps_by_ref: Dict[str, List[Tuple[str, str, float, float]]] = defaultdict(list)
        with hh_dump_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("PIN|"):
                    parts = line.rstrip("\r\n").split("|")
                    if len(parts) < 10:
                        continue
                    net, ref, pnum = parts[1], parts[3], parts[4]
                    x, y = float(parts[5]), float(parts[6])
                    st, ps = parts[7], parts[9]
                    if ref == "A1" and ("C480" in ps or "C560" in ps or "C250" in ps):
                        if -17500.0 <= x <= 17500.0 and 15500.0 <= y <= 35500.0:
                            bgas.append(BgaBall(x=x, y=y, sro_r=_bga_sro_radius(ps), net=net, padstack=ps))
                    elif ref.startswith("C") and ("S300" in ps or "BASE" in st) and "4FCO" not in st:
                        caps_by_ref[ref].append((net, pnum, x, y))
                elif line.startswith("SHP|"):
                    parts = line.rstrip("\r\n").split("|")
                    if len(parts) < 8 or parts[3] != "CONDUCTOR/12B":
                        continue
                    if parts[1] == "VDD_0P8_SRAM_CC0":
                        sram_12b.append((float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])))
                    elif parts[1] == "VDDC0":
                        vddc0_12b = (float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7]))

        for ref, items in sorted(caps_by_ref.items()):
            if len(items) != 2:
                continue
            nets = {it[0] for it in items}
            if "VDDC0" not in nets and "VDD_0P8_SRAM_CC0" not in nets:
                continue
            p1 = next((it for it in items if it[1] == "1"), items[0])
            p2 = next((it for it in items if it[1] == "2"), items[1])
            vdd_net = p1[0] if p1[0] != "VSS" else p2[0]
            cx, cy = 0.5 * (p1[2] + p2[2]), 0.5 * (p1[3] + p2[3])
            dx, dy = p1[2] - p2[2], p1[3] - p2[3]
            if abs(dy) >= abs(dx):
                rot = 0.0 if dy >= 0 else 180.0
            else:
                rot = 90.0 if dx <= 0 else 270.0
            orig_lscs.append(
                LscCap(
                    refdes=ref,
                    pocket_id=_pocket_id_for_xy(cx, cy),
                    x=cx,
                    y=cy,
                    rot_deg=rot,
                    pin1_net=vdd_net,
                    pin2_net="VSS",
                )
            )
        return bgas, orig_lscs, (sram_12b or list(DEFAULT_SRAM0_12B_ISLANDS)), vddc0_12b, hh_dump_path.name

    # Fallback: stage1_inputs CSVs
    with (stage1_dir / "bga_map.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ps = r.get("padstack_name", "")
            if "FID" in ps:
                continue
            x, y = float(r["x_um"]), float(r["y_um"])
            if -17500.0 <= x <= 17500.0 and 15500.0 <= y <= 35500.0:
                bgas.append(BgaBall(x=x, y=y, sro_r=_bga_sro_radius(ps), net=r.get("net_name", ""), padstack=ps))
    with (stage1_dir / "lsc_placed_map.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n1, n2 = r.get("pin1_net", ""), r.get("pin2_net", "")
            if n1 in ("VDDC0", "VDD_0P8_SRAM_CC0") or n2 in ("VDDC0", "VDD_0P8_SRAM_CC0"):
                cx, cy = float(r["x_um"]), float(r["y_um"])
                vdd_net = n1 if n1 != "VSS" else n2
                orig_lscs.append(
                    LscCap(
                        refdes=r["refdes"],
                        pocket_id=_pocket_id_for_xy(cx, cy),
                        x=cx,
                        y=cy,
                        rot_deg=float(r.get("rotation", 0.0)),
                        pin1_net=vdd_net,
                        pin2_net="VSS",
                    )
                )
    return bgas, orig_lscs, list(DEFAULT_SRAM0_12B_ISLANDS), vddc0_12b, "stage1_inputs CSVs"


def _bga_sro_clear(cx: float, cy: float, hx: float, hy: float, local_bgas: Sequence[BgaBall], min_gap: float) -> bool:
    rx0, ry0, rx1, ry1 = cx - hx, cy - hy, cx + hx, cy + hy
    tol = min_gap - 1e-4
    for b in local_bgas:
        dx = max(rx0 - b.x, 0.0, b.x - rx1)
        dy = max(ry0 - b.y, 0.0, b.y - ry1)
        if dx * dx + dy * dy < (b.sro_r + tol) ** 2:
            return False
    return True


def _lsc_sro_clear(
    ax: float, ay: float, ahx: float, ahy: float, bx: float, by: float, bhx: float, bhy: float, min_gap: float
) -> bool:
    dx = max(0.0, abs(ax - bx) - (ahx + bhx))
    dy = max(0.0, abs(ay - by) - (ahy + bhy))
    if dx == 0.0 and dy == 0.0:
        return False
    return dx * dx + dy * dy >= (min_gap - 1e-4) ** 2


def _rect_sro_to_bga_dist(cap: LscCap, bgas: Sequence[BgaBall]) -> float:
    hx, hy = cap.sro_half_extents
    rx0, ry0, rx1, ry1 = cap.x - hx, cap.y - hy, cap.x + hx, cap.y + hy
    best = 1e9
    for b in bgas:
        dx = max(rx0 - b.x, 0.0, b.x - rx1)
        dy = max(ry0 - b.y, 0.0, b.y - ry1)
        d = math.hypot(dx, dy) - b.sro_r
        if d < best:
            best = d
    return best


def _rect_sro_to_sro_dist(a: LscCap, b: LscCap) -> float:
    ahx, ahy = a.sro_half_extents
    bhx, bhy = b.sro_half_extents
    dx = max(0.0, abs(a.x - b.x) - (ahx + bhx))
    dy = max(0.0, abs(a.y - b.y) - (ahy + bhy))
    if dx == 0.0 and dy == 0.0:
        hx_ov = min(a.x + ahx, b.x + bhx) - max(a.x - ahx, b.x - bhx)
        hy_ov = min(a.y + ahy, b.y + bhy) - max(a.y - ahy, b.y - bhy)
        return -min(hx_ov, hy_ov)
    return math.hypot(dx, dy)


def _resolve_u9_net(cx: float, cy: float, sram_islands: Sequence[BBox]) -> str:
    for x1, y1, x2, y2 in sram_islands:
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            return "VDD_0P8_SRAM_CC0"
    return "VDDC0"


@dataclass
class RecessGeometry:
    pocket_id: str
    cavity_poly: List[Tuple[float, float]]
    outer_koz_poly: List[Tuple[float, float]]
    inner_safe_poly: List[Tuple[float, float]]
    cavity_area_mm2: float
    x0: float
    y0: float
    grid_step: float
    w: int
    h: int
    phi: List[List[float]]

    def phi_at(self, px: float, py: float) -> float:
        fx = (px - self.x0) / self.grid_step
        fy = (py - self.y0) / self.grid_step
        ix, iy = int(fx), int(fy)
        if ix < 0 or iy < 0 or ix >= self.w - 1 or iy >= self.h - 1:
            return -9999.0
        tx, ty = fx - ix, fy - iy
        row0 = self.phi[iy]
        row1 = self.phi[iy + 1]
        return (1.0 - ty) * ((1.0 - tx) * row0[ix] + tx * row0[ix + 1]) + ty * (
            (1.0 - tx) * row1[ix] + tx * row1[ix + 1]
        )


def _poly_area_mm2(poly: Sequence[Tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    acc = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5 / 1_000_000.0


def _lsc_overlaps_emib(cx: float, cy: float, hx: float, hy: float, pad: float = 0.0) -> bool:
    rx0, ry0, rx1, ry1 = cx - hx - pad, cy - hy - pad, cx + hx + pad, cy + hy + pad
    for ex0, ey0, ex1, ey1 in U9_EMIB_BRIDGES.values():
        if rx1 > ex0 and rx0 < ex1 and ry1 > ey0 and ry0 < ey1:
            return True
    return False


def _seg_to_aabb_dist_sq(
    ax: float, ay: float, bx: float, by: float, rx0: float, ry0: float, rx1: float, ry1: float
) -> float:
    dx, dy = bx - ax, by - ay
    ts = [0.0, 1.0]
    if abs(dx) > 1e-12:
        for bx_edge in (rx0, rx1):
            t = (bx_edge - ax) / dx
            if 0.0 < t < 1.0:
                ts.append(t)
    if abs(dy) > 1e-12:
        for by_edge in (ry0, ry1):
            t = (by_edge - ay) / dy
            if 0.0 < t < 1.0:
                ts.append(t)
    ts.sort()

    def _d2_at(t_val: float) -> float:
        px = ax + t_val * dx
        py = ay + t_val * dy
        gx = rx0 - px if px < rx0 else (px - rx1 if px > rx1 else 0.0)
        gy = ry0 - py if py < ry0 else (py - ry1 if py > ry1 else 0.0)
        return gx * gx + gy * gy

    best = min(_d2_at(t_val) for t_val in ts)
    for i in range(len(ts) - 1):
        t_lo, t_hi = ts[i], ts[i + 1]
        if t_hi - t_lo <= 1e-9:
            continue
        tm = 0.5 * (t_lo + t_hi)
        pxm = ax + tm * dx
        pym = ay + tm * dy
        tx_d, tx_0 = ((dx, ax - rx0) if pxm < rx0 else ((dx, ax - rx1) if pxm > rx1 else (0.0, 0.0)))
        ty_d, ty_0 = ((dy, ay - ry0) if pym < ry0 else ((dy, ay - ry1) if pym > ry1 else (0.0, 0.0)))
        denom = tx_d * tx_d + ty_d * ty_d
        if denom > 1e-12:
            t_star = -(tx_d * tx_0 + ty_d * ty_0) / denom
            if t_lo < t_star < t_hi:
                best = min(best, _d2_at(t_star))
    return best


def _rect_to_poly_dist(
    rx0: float, ry0: float, rx1: float, ry1: float, poly: Sequence[Tuple[float, float]], prefilter_um: float = 1e9
) -> float:
    best_d2 = 1e18
    n = len(poly)
    lim = prefilter_um
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if lim < 1e8:
            if max(ax, bx) < rx0 - lim or min(ax, bx) > rx1 + lim or max(ay, by) < ry0 - lim or min(ay, by) > ry1 + lim:
                continue
        d2 = _seg_to_aabb_dist_sq(ax, ay, bx, by, rx0, ry0, rx1, ry1)
        if d2 < best_d2:
            best_d2 = d2
    return math.sqrt(best_d2) if best_d2 < 1e17 else prefilter_um + 1.0


def _rect_sro_inside_cavity(
    cx: float,
    cy: float,
    hx: float,
    hy: float,
    cav_poly: Sequence[Tuple[float, float]],
    min_dist: float,
    exact_dist: bool = False,
) -> Tuple[bool, float]:
    rx0, ry0, rx1, ry1 = cx - hx, cy - hy, cx + hx, cy + hy
    for px, py in ((cx, cy), (rx0, ry0), (rx1, ry0), (rx0, ry1), (rx1, ry1)):
        if not _pt_in_poly(px, py, cav_poly):
            return False, -_pt_to_poly_boundary_dist(px, py, cav_poly)
    lim = 1e9 if (exact_dist or min_dist <= 0.0 or min_dist >= 1e6) else min_dist + 60.0
    d_exact = _rect_to_poly_dist(rx0, ry0, rx1, ry1, cav_poly, prefilter_um=lim)
    return d_exact >= min_dist - 1e-4, d_exact


def _poly_to_poly_dist(poly_a: Sequence[Tuple[float, float]], poly_b: Sequence[Tuple[float, float]]) -> float:
    ax0 = min(p[0] for p in poly_a)
    ay0 = min(p[1] for p in poly_a)
    ax1 = max(p[0] for p in poly_a)
    ay1 = max(p[1] for p in poly_a)
    bx0 = min(p[0] for p in poly_b)
    by0 = min(p[1] for p in poly_b)
    bx1 = max(p[0] for p in poly_b)
    by1 = max(p[1] for p in poly_b)
    bbox_dx = max(ax0 - bx1, 0.0, bx0 - ax1)
    bbox_dy = max(ay0 - by1, 0.0, by0 - ay1)
    if bbox_dx > 0.0 or bbox_dy > 0.0:
        bbox_d = math.hypot(bbox_dx, bbox_dy)
        if bbox_d >= CAVITY_WEB_MIN_UM + 500.0:
            return min(
                min(_pt_to_poly_boundary_dist(px, py, poly_b) for px, py in poly_a[::4]),
                min(_pt_to_poly_boundary_dist(px, py, poly_a) for px, py in poly_b[::4]),
            )
    d_ab = min(_pt_to_poly_boundary_dist(px, py, poly_b) for px, py in poly_a)
    d_ba = min(_pt_to_poly_boundary_dist(px, py, poly_a) for px, py in poly_b)
    return min(d_ab, d_ba)


def build_u9_pocket_recess(
    pocket_id: str,
    win: BBox,
    all_bgas: Sequence[BgaBall],
    orig_caps: Sequence[LscCap],
    bga_sro_to_cav_um: float = BGA_SRO_TO_CAVITY_UM,
    ext_koz_um: float = EXT_CU_TO_CAVITY_UM,
    lsc_sro_to_cav_um: float = LSC_SRO_TO_CAVITY_UM,
    mill_r_um: float = CAVITY_MILL_RADIUS_UM,
    grid_step: float = RECESS_GRID_STEP_UM,
) -> RecessGeometry:
    """
    Construct the rounded (R_mill = 508 um) morphological-opening recess cavity for one U9 pocket.
    Enforces BGA SRO -> Cavity >= 254 um, BGA Cu -> Cavity >= 178 um, EMIB -> Cavity >= 178 um,
    and extracts LSC_CAVITY (phi=0), +178 um Ext Cu KOZ (phi=-178), and -225 um Safe Zone (phi=+225).
    """
    wx0, wy0, wx1, wy1 = win
    pad = 900.0
    x0, y0, x1, y1 = wx0 - pad, wy0 - pad, wx1 + pad, wy1 + pad
    w = int(math.ceil((x1 - x0) / grid_step)) + 1
    h = int(math.ceil((y1 - y0) / grid_step)) + 1
    lbgas = [
        b for b in all_bgas
        if x0 - 1000.0 <= b.x <= x1 + 1000.0 and y0 - 1000.0 <= b.y <= y1 + 1000.0
    ]

    obs = [[False] * w for _ in range(h)]
    for iy in range(h):
        if iy <= 1 or iy >= h - 2:
            obs[iy] = [True] * w
        else:
            obs[iy][0] = obs[iy][1] = obs[iy][w - 2] = obs[iy][w - 1] = True

    grid_guard = 0.85 * grid_step
    for b in lbgas:
        rq = max(mill_r_um, b.sro_r + bga_sro_to_cav_um, b.sro_r + BGA_CU_OVER_SRO_UM + ext_koz_um) + grid_guard
        rq2 = rq * rq
        iy_min = max(0, int((b.y - rq - y0) / grid_step))
        iy_max = min(h - 1, int((b.y + rq - y0) / grid_step) + 1)
        ix_min = max(0, int((b.x - rq - x0) / grid_step))
        ix_max = min(w - 1, int((b.x + rq - x0) / grid_step) + 1)
        for iy in range(iy_min, iy_max + 1):
            dy2 = (y0 + iy * grid_step - b.y) ** 2
            row_obs = obs[iy]
            for ix in range(ix_min, ix_max + 1):
                if (x0 + ix * grid_step - b.x) ** 2 + dy2 < rq2:
                    row_obs[ix] = True

    emib_guard = ext_koz_um + grid_guard
    for ex0, ey0, ex1, ey1 in U9_EMIB_BRIDGES.values():
        gx0, gy0, gx1, gy1 = ex0 - emib_guard, ey0 - emib_guard, ex1 + emib_guard, ey1 + emib_guard
        if gx1 < x0 or gx0 > x1 or gy1 < y0 or gy0 > y1:
            continue
        iy_min = max(0, int((gy0 - y0) / grid_step))
        iy_max = min(h - 1, int((gy1 - y0) / grid_step) + 1)
        ix_min = max(0, int((gx0 - x0) / grid_step))
        ix_max = min(w - 1, int((gx1 - x0) / grid_step) + 1)
        for iy in range(iy_min, iy_max + 1):
            row_obs = obs[iy]
            for ix in range(ix_min, ix_max + 1):
                row_obs[ix] = True

    d_obs = edt_2d_exact(obs, w, h, grid_step)

    core = [[False] * w for _ in range(h)]
    q: deque[Tuple[int, int]] = deque()
    for c in orig_caps:
        if c.pocket_id == pocket_id or (wx0 <= c.x <= wx1 and wy0 <= c.y <= wy1):
            ix = int(round((c.x - x0) / grid_step))
            iy = int(round((c.y - y0) / grid_step))
            if 2 <= ix < w - 2 and 2 <= iy < h - 2 and d_obs[iy][ix] >= mill_r_um and not core[iy][ix]:
                core[iy][ix] = True
                q.append((ix, iy))

    if not q:
        raise RuntimeError(f"Failed to seed recess BFS core inside {pocket_id}")

    while q:
        cx_i, cy_i = q.popleft()
        for dx_i, dy_i in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx_i, ny_i = cx_i + dx_i, cy_i + dy_i
            if 2 <= nx_i < w - 2 and 2 <= ny_i < h - 2 and not core[ny_i][nx_i] and d_obs[ny_i][nx_i] >= mill_r_um:
                px, py = x0 + nx_i * grid_step, y0 + ny_i * grid_step
                if wx0 - 400.0 <= px <= wx1 + 400.0 and wy0 - 400.0 <= py <= wy1 + 400.0:
                    core[ny_i][nx_i] = True
                    q.append((nx_i, ny_i))

    d_core = edt_2d_exact(core, w, h, grid_step)
    phi = [[mill_r_um - d_core[iy][ix] for ix in range(w)] for iy in range(h)]

    cav_loops = extract_marching_squares_loops(phi, w, h, x0, y0, grid_step, level=0.0, min_area_um2=200_000.0)
    if not cav_loops:
        raise RuntimeError(f"No recess cavity loop extracted for {pocket_id}")
    cav_poly = max(cav_loops, key=_poly_area_mm2)

    koz_loops = extract_marching_squares_loops(phi, w, h, x0, y0, grid_step, level=-ext_koz_um, min_area_um2=200_000.0)
    koz_poly = max(koz_loops, key=_poly_area_mm2) if koz_loops else list(cav_poly)

    safe_loops = extract_marching_squares_loops(phi, w, h, x0, y0, grid_step, level=lsc_sro_to_cav_um, min_area_um2=50_000.0)
    safe_poly = max(safe_loops, key=_poly_area_mm2) if safe_loops else list(cav_poly)

    return RecessGeometry(
        pocket_id=pocket_id,
        cavity_poly=cav_poly,
        outer_koz_poly=koz_poly,
        inner_safe_poly=safe_poly,
        cavity_area_mm2=round(_poly_area_mm2(cav_poly), 3),
        x0=x0,
        y0=y0,
        grid_step=grid_step,
        w=w,
        h=h,
        phi=phi,
    )


def pack_pocket_new_rule(
    pocket_id: str,
    win: BBox,
    all_bgas: Sequence[BgaBall],
    sram_islands: Sequence[BBox],
    recess: Optional[RecessGeometry] = None,
    bga_gap: float = BGA_TO_LSC_SRO_UM,
    sro_gap: float = LSC_TO_LSC_SRO_UM,
    lsc_cav_gap: float = LSC_SRO_TO_CAVITY_UM,
) -> List[LscCap]:
    """
    Maximize aligned (non-zigzag) 0201 LSC count inside one pocket enforcing:
      - BGA SRO to LSC SRO >= bga_gap (395 um)
      - LSC SRO to LSC SRO >= sro_gap (390 um)
      - If `recess` provided: LSC SRO >= lsc_cav_gap (225 um) strictly inside R_mill=508 um cavity
        and 0 EMIB shadow overlap
    Evaluates:
      1a. Strict 2D Aligned V Matrix (0/180 deg columns sharing identical Y rows & X columns)
      1b. Grid-Aligned V (0/180 deg sharing a single X-column & Y-row lattice; curved corner cells dropped)
      2a. Strict 2D Aligned H Matrix (90/270 deg rows sharing identical Y rows & X columns)
      2b. Row-Aligned H (90/270 deg straight horizontal rows sharing Y rows and preferring shared X columns)
    Selects the layout maximizing (count, strict_2d_rect, shared_xy_lattice, min_rule_slack) with 180 deg alternation.
    """
    wx0, wy0, wx1, wy1 = win
    lbgas = [
        b for b in all_bgas
        if wx0 - 1100.0 <= b.x <= wx1 + 1100.0 and wy0 - 1100.0 <= b.y <= wy1 + 1100.0
    ]

    step = 10.0
    nx = int((wx1 - wx0) / step) + 1
    ny = int((wy1 - wy0) / step) + 1
    xs = [wx0 + ix * step for ix in range(nx)]
    ys = [wy0 + iy * step for iy in range(ny)]

    v_ok = [[False] * nx for _ in range(ny)]
    h_ok = [[False] * nx for _ in range(ny)]
    tol = bga_gap - 1e-4
    for iy, cy in enumerate(ys):
        bv = [(b.x, b.y, (b.sro_r + tol) ** 2) for b in lbgas if abs(b.y - cy) <= 410.0 + b.sro_r + bga_gap]
        bh = [(b.x, b.y, (b.sro_r + tol) ** 2) for b in lbgas if abs(b.y - cy) <= 150.0 + b.sro_r + bga_gap]
        for ix, cx in enumerate(xs):
            v_clear = all(
                max(0.0, abs(cx - bx) - 150.0) ** 2 + max(0.0, abs(cy - by) - 410.0) ** 2 >= r2
                for bx, by, r2 in bv
            )
            if v_clear and recess is not None:
                if _lsc_overlaps_emib(cx, cy, 150.0, 410.0):
                    v_clear = False
                else:
                    min_phi = min(
                        recess.phi_at(px, py)
                        for px in (cx - 150.0, cx, cx + 150.0)
                        for py in (cy - 410.0, cy, cy + 410.0)
                    )
                    if min_phi < lsc_cav_gap - 12.0:
                        v_clear = False
                    elif min_phi < lsc_cav_gap + 15.0:
                        v_clear, _ = _rect_sro_inside_cavity(cx, cy, 150.0, 410.0, recess.cavity_poly, lsc_cav_gap)
            v_ok[iy][ix] = v_clear

            h_clear = all(
                max(0.0, abs(cx - bx) - 410.0) ** 2 + max(0.0, abs(cy - by) - 150.0) ** 2 >= r2
                for bx, by, r2 in bh
            )
            if h_clear and recess is not None:
                if _lsc_overlaps_emib(cx, cy, 410.0, 150.0):
                    h_clear = False
                else:
                    min_phi = min(
                        recess.phi_at(px, py)
                        for px in (cx - 410.0, cx, cx + 410.0)
                        for py in (cy - 150.0, cy, cy + 150.0)
                    )
                    if min_phi < lsc_cav_gap - 12.0:
                        h_clear = False
                    elif min_phi < lsc_cav_gap + 15.0:
                        h_clear, _ = _rect_sro_inside_cavity(cx, cy, 410.0, 150.0, recess.cavity_poly, lsc_cav_gap)
            h_ok[iy][ix] = h_clear

    p_short = LSC_SRO_SHORT_UM + sro_gap  # 690.0 um
    p_long = LSC_SRO_LONG_UM + sro_gap    # 1210.0 um
    step_s = int(round(p_short / step))
    step_l = int(round(p_long / step))

    def _center_1d_indices(valid_mask: Sequence[bool], min_step_idx: int) -> List[int]:
        """Find max-cardinality 1D sequence with gap >= min_step_idx and center slack symmetrically."""
        n = len(valid_mask)
        dp = [0] * (n + 1)
        ch = [0] * n
        for i in range(n - 1, -1, -1):
            if not valid_mask[i]:
                dp[i] = dp[i + 1]
            else:
                t = 1 + (dp[i + min_step_idx] if i + min_step_idx < n else 0)
                if t >= dp[i + 1]:
                    dp[i] = t
                    ch[i] = 1
                else:
                    dp[i] = dp[i + 1]
        seq: List[int] = []
        i = 0
        while i < n:
            if ch[i]:
                seq.append(i)
                i += min_step_idx
            else:
                i += 1
        if not seq:
            return []

        shifts = [sh for sh in range(-n, n) if all(0 <= idx + sh < n and valid_mask[idx + sh] for idx in seq)]
        if shifts:
            mid_sh = shifts[len(shifts) // 2]
            seq = [idx + mid_sh for idx in seq]

        # When valid_mask splits into disconnected islands, center each island group within its bounds
        idxs = [k for k, ok in enumerate(valid_mask) if ok]
        ivs: List[Tuple[int, int]] = []
        s = p = idxs[0]
        for k in idxs[1:]:
            if k - p > 1:
                ivs.append((s, p))
                s = k
            p = k
        ivs.append((s, p))
        if len(ivs) > 1 and len(seq) > 1:
            def _iv_of(pos: int) -> int:
                for idx_iv, (a, b) in enumerate(ivs):
                    if a <= pos <= b:
                        return idx_iv
                return -1

            grouped: List[List[int]] = [[seq[0]]]
            for pos in seq[1:]:
                if _iv_of(pos) == _iv_of(grouped[-1][-1]):
                    grouped[-1].append(pos)
                else:
                    grouped.append([pos])
            if len(grouped) > 1:
                new_seq: List[int] = []
                for gi, grp in enumerate(grouped):
                    a, b = ivs[_iv_of(grp[0])]
                    if gi > 0 and new_seq:
                        a = max(a, new_seq[-1] + min_step_idx)
                    if gi + 1 < len(grouped):
                        b = min(b, grouped[gi + 1][0] - min_step_idx)
                    span_used = (len(grp) - 1) * min_step_idx
                    if b - a >= span_used:
                        st = a + (b - a - span_used + 1) // 2
                        new_seq.extend([st + m * min_step_idx for m in range(len(grp))])
                    else:
                        new_seq.extend(grp)
                seq = new_seq
        return seq

    def _center_y_shift(rows: List[int], cols: Sequence[int], ok_grid: List[List[bool]], step_y: int) -> List[int]:
        shifts = [
            sh for sh in range(-step_y, step_y)
            if all(0 <= iy + sh < ny and all(ok_grid[iy + sh][ix] for ix in cols) for iy in rows)
        ]
        if not shifts:
            return rows
        mid_sh = shifts[len(shifts) // 2]
        return [iy + mid_sh for iy in rows]

    def _min_rule_slack(pts: Sequence[Tuple[float, float]], hx: float, hy: float) -> Tuple[bool, float]:
        best_bga = 1e9
        best_cav = 1e9
        for cx, cy in pts:
            rx0, ry0, rx1, ry1 = cx - hx, cy - hy, cx + hx, cy + hy
            for b in lbgas:
                dx = max(rx0 - b.x, 0.0, b.x - rx1)
                dy = max(ry0 - b.y, 0.0, b.y - ry1)
                d = math.hypot(dx, dy) - b.sro_r
                if d < best_bga:
                    best_bga = d
            if recess is not None:
                ok_c, dc = _rect_sro_inside_cavity(cx, cy, hx, hy, recess.cavity_poly, lsc_cav_gap)
                if not ok_c:
                    return False, -1.0
                if dc < best_cav:
                    best_cav = dc
        slack = best_bga - bga_gap if recess is None else min(best_bga - bga_gap, best_cav - lsc_cav_gap)
        return slack >= -1e-4, slack

    best_score: Tuple[int, int, int, float] = (-1, -1, -1, -1e9)
    best_items: List[Tuple[float, float, float]] = []
    best_is_v_primary = True

    def _consider(
        items: List[Tuple[float, float, float]],
        pts: Sequence[Tuple[float, float]],
        hx: float,
        hy: float,
        is_strict: int,
        is_shared_xy: int,
        is_v_primary: bool,
    ) -> None:
        nonlocal best_score, best_items, best_is_v_primary
        if len(pts) < best_score[0]:
            return
        ok_all, slack = _min_rule_slack(pts, hx, hy)
        if not ok_all:
            return
        sc = (len(pts), is_strict, is_shared_xy, round(slack, 2))
        if sc > best_score:
            best_score = sc
            best_is_v_primary = is_v_primary
            best_items = items

    # Strategy 1: Strict 2D Aligned V & Grid-Aligned Corner-Trimmed V (`0/180 deg`)
    seen_v1: set[Tuple[Tuple[int, ...], Tuple[int, ...]]] = set()
    seen_v2: set[Tuple[Tuple[float, float, float], ...]] = set()
    for iy0 in range(min(step_l, ny)):
        cand_rows = [iy for iy in range(iy0, ny, step_l) if any(v_ok[iy])]
        if not cand_rows:
            continue

        # 1a) Strict 2D rectangular V matrix
        shared_x_mask = [all(v_ok[iy][ix] for iy in cand_rows) for ix in range(nx)]
        col_ixs = _center_1d_indices(shared_x_mask, step_s)
        if col_ixs:
            use_rows = _center_y_shift(cand_rows, col_ixs, v_ok, step_l)
            key_v = (tuple(use_rows), tuple(col_ixs))
            if key_v not in seen_v1:
                seen_v1.add(key_v)
                pts = [(xs[ix], ys[iy]) for iy in use_rows for ix in col_ixs]
                items = [
                    (xs[ix], ys[iy], 0.0 if ci % 2 == 0 else 180.0)
                    for ci, ix in enumerate(col_ixs)
                    for iy in use_rows
                ]
                _consider(items, pts, 150.0, 410.0, 1, 1, True)

        # 1b) Grid-Aligned V sharing one single (X_cols, Y_rows) lattice; drops only curved corner cells
        per_row_xs_v = [_center_1d_indices(v_ok[iy], step_s) for iy in cand_rows]
        max_cv = max((len(r) for r in per_row_xs_v), default=0)
        full_rows_v = [iy for iy, r in zip(cand_rows, per_row_xs_v) if len(r) == max_cv]
        if full_rows_v and max_cv > 0:
            shared_full_v = [all(v_ok[iy][ix] for iy in full_rows_v) for ix in range(nx)]
            base_cols = _center_1d_indices(shared_full_v, step_s)
            if len(base_cols) == max_cv:
                x_shifts = [
                    sh for sh in range(-step_s, step_s)
                    if all(0 <= ix + sh < nx and shared_full_v[ix + sh] for ix in base_cols)
                ] or [0]
                mid_x_idx = len(x_shifts) // 2
                # Evaluate centered shift and stride across shifts so curved boundary rows maximize aligned fit
                eval_shifts = sorted(set(x_shifts), key=lambda sh: abs(sh - x_shifts[mid_x_idx]))
                for sh in eval_shifts[:9]:
                    col_grid = [ix + sh for ix in base_cols]
                    v_items: List[Tuple[float, float, float]] = []
                    v_pts: List[Tuple[float, float]] = []
                    for iy in cand_rows:
                        for ci, ix in enumerate(col_grid):
                            if v_ok[iy][ix]:
                                v_items.append((xs[ix], ys[iy], 0.0 if ci % 2 == 0 else 180.0))
                                v_pts.append((xs[ix], ys[iy]))
                    if v_items:
                        key_v2 = tuple(v_items)
                        if key_v2 not in seen_v2:
                            seen_v2.add(key_v2)
                            is_strict_v = 1 if len(v_pts) == len(cand_rows) * len(col_grid) else 0
                            _consider(v_items, v_pts, 150.0, 410.0, is_strict_v, 1, True)

    # Strategy 2: Strict 2D Aligned H Matrix & Row-Aligned H (`90/270 deg`)
    seen_h1: set[Tuple[Tuple[int, ...], Tuple[int, ...]]] = set()
    seen_h2: set[Tuple[Tuple[float, float, float], ...]] = set()
    for iy0 in range(min(step_s, ny)):
        cand_rows = [iy for iy in range(iy0, ny, step_s) if any(h_ok[iy])]
        if not cand_rows:
            continue

        # 2a) Strict 2D rectangular H matrix
        shared_x_mask = [all(h_ok[iy][ix] for iy in cand_rows) for ix in range(nx)]
        col_ixs = _center_1d_indices(shared_x_mask, step_l)
        if col_ixs:
            use_rows = _center_y_shift(cand_rows, col_ixs, h_ok, step_s)
            key_h1 = (tuple(use_rows), tuple(col_ixs))
            if key_h1 not in seen_h1:
                seen_h1.add(key_h1)
                pts_rect = [(xs[ix], ys[iy]) for iy in use_rows for ix in col_ixs]
                items_rect = [
                    (xs[ix], ys[iy], 90.0 if ri % 2 == 0 else 270.0)
                    for ri, iy in enumerate(use_rows)
                    for ix in col_ixs
                ]
                _consider(items_rect, pts_rect, 410.0, 150.0, 1, 1, False)

        # 2b) Row-aligned H (fixed Y rows; full-width rows share X columns; prefer shared X lattice if same count)
        per_row_xs = [_center_1d_indices(h_ok[iy], step_l) for iy in cand_rows]
        max_c = max((len(r) for r in per_row_xs), default=0)
        full_rows = [iy for iy, r in zip(cand_rows, per_row_xs) if len(r) == max_c]
        if full_rows and max_c > 0:
            shared_full_mask = [all(h_ok[iy][ix] for iy in full_rows) for ix in range(nx)]
            full_col_ixs = _center_1d_indices(shared_full_mask, step_l)
            if len(full_col_ixs) == max_c:
                # Variant 2b-i: strictly shared X columns across all rows (keeps partial rows aligned on full_col_ixs too)
                row_items_shared: List[Tuple[float, float, float]] = []
                pts_shared: List[Tuple[float, float]] = []
                for ri, iy in enumerate(cand_rows):
                    rot = 90.0 if ri % 2 == 0 else 270.0
                    for ix in full_col_ixs:
                        if h_ok[iy][ix]:
                            row_items_shared.append((xs[ix], ys[iy], rot))
                            pts_shared.append((xs[ix], ys[iy]))
                key_h2s = tuple(row_items_shared)
                if key_h2s not in seen_h2 and row_items_shared:
                    seen_h2.add(key_h2s)
                    is_strict_s = 1 if len(pts_shared) == len(cand_rows) * len(full_col_ixs) else 0
                    _consider(row_items_shared, pts_shared, 410.0, 150.0, is_strict_s, 1, False)

                # Variant 2b-ii: per-row centered X on irregular island cutout rows (same fixed Y line)
                row_items: List[Tuple[float, float, float]] = []
                all_pts: List[Tuple[float, float]] = []
                all_on_shared = True
                for ri, iy in enumerate(cand_rows):
                    rot = 90.0 if ri % 2 == 0 else 270.0
                    if all(h_ok[iy][ix] for ix in full_col_ixs):
                        use_ixs = full_col_ixs
                    else:
                        use_ixs = per_row_xs[ri]
                        if any(ix not in full_col_ixs for ix in use_ixs):
                            all_on_shared = False
                    for ix in use_ixs:
                        row_items.append((xs[ix], ys[iy], rot))
                        all_pts.append((xs[ix], ys[iy]))
                key_h2 = tuple(row_items)
                if key_h2 not in seen_h2 and row_items:
                    seen_h2.add(key_h2)
                    is_strict = 1 if len(all_pts) == len(cand_rows) * len(full_col_ixs) else 0
                    _consider(row_items, all_pts, 410.0, 150.0, is_strict, 1 if all_on_shared else 0, False)

    # Sort deterministically and emit LscCap records
    if best_is_v_primary:
        best_items.sort(key=lambda t: (round(t[0] / 250.0), round(t[1] / 250.0)))
    else:
        best_items.sort(key=lambda t: (round(t[1] / 250.0), round(t[0] / 250.0)))

    caps_out: List[LscCap] = []
    for idx, (cx, cy, rot) in enumerate(best_items, 1):
        net = _resolve_u9_net(cx, cy, sram_islands)
        caps_out.append(
            LscCap(
                refdes=f"SB_{pocket_id}_{idx:03d}",
                pocket_id=pocket_id,
                x=round(cx, 2),
                y=round(cy, 2),
                rot_deg=rot,
                pin1_net=net,
                pin2_net="VSS",
            )
        )
    return caps_out


def audit_caps(
    caps: Sequence[LscCap],
    bgas: Sequence[BgaBall],
    recess_map: Optional[Dict[str, RecessGeometry]] = None,
) -> Dict[str, object]:
    """Verify BGA-SRO->LSC-SRO, LSC-SRO->LSC-SRO, and (if provided) exact recess & EMIB clearances."""
    min_bga_sro = 1e9
    viol_bga_395 = 0
    for c in caps:
        d = _rect_sro_to_bga_dist(c, bgas)
        if d < min_bga_sro:
            min_bga_sro = d
        if d < BGA_TO_LSC_SRO_UM - 0.05:
            viol_bga_395 += 1

    min_lsc_sro = 1e9
    viol_lsc_390_pairs: List[Tuple[str, str, float]] = []
    for i in range(len(caps)):
        for j in range(i + 1, len(caps)):
            d = _rect_sro_to_sro_dist(caps[i], caps[j])
            if d < min_lsc_sro:
                min_lsc_sro = d
            if d < LSC_TO_LSC_SRO_UM - 0.05:
                viol_lsc_390_pairs.append((caps[i].refdes, caps[j].refdes, round(d, 2)))

    out: Dict[str, object] = {
        "count": len(caps),
        "vddc0_count": sum(1 for c in caps if c.pin1_net == "VDDC0"),
        "sram0_count": sum(1 for c in caps if c.pin1_net == "VDD_0P8_SRAM_CC0"),
        "min_bga_sro_to_lsc_sro_um": round(min_bga_sro, 2) if caps else None,
        "min_lsc_sro_to_lsc_sro_um": round(min_lsc_sro, 2) if len(caps) > 1 else None,
        "viol_bga_lt_395": viol_bga_395,
        "viol_lsc_lt_390_pair_count": len(viol_lsc_390_pairs),
        "viol_lsc_pairs_sample": viol_lsc_390_pairs[:20],
    }

    if recess_map is not None:
        min_lsc_cav = 1e9
        viol_lsc_225 = 0
        viol_emib = 0
        for c in caps:
            hx, hy = c.sro_half_extents
            if _lsc_overlaps_emib(c.x, c.y, hx, hy):
                viol_emib += 1
            rec = recess_map.get(c.pocket_id)
            if rec is None:
                continue
            ok_c, dc = _rect_sro_inside_cavity(c.x, c.y, hx, hy, rec.cavity_poly, LSC_SRO_TO_CAVITY_UM, exact_dist=True)
            if dc < min_lsc_cav:
                min_lsc_cav = dc
            if not ok_c:
                viol_lsc_225 += 1

        min_bga_cav = 1e9
        min_bga_cu_cav = 1e9
        viol_bga_cav_254 = 0
        viol_bga_cu_178 = 0
        viol_cav_emib = 0
        for pid, rec in recess_map.items():
            cav = rec.cavity_poly
            cx0 = min(p[0] for p in cav) - 2000.0
            cy0 = min(p[1] for p in cav) - 2000.0
            cx1 = max(p[0] for p in cav) + 2000.0
            cy1 = max(p[1] for p in cav) + 2000.0
            for b in bgas:
                if not (cx0 <= b.x <= cx1 and cy0 <= b.y <= cy1):
                    continue
                if _pt_in_poly(b.x, b.y, cav):
                    d_b = -_pt_to_poly_boundary_dist(b.x, b.y, cav)
                else:
                    d_b = _pt_to_poly_boundary_dist(b.x, b.y, cav)
                d_sro = d_b - b.sro_r
                d_cu = d_b - (b.sro_r + BGA_CU_OVER_SRO_UM)
                if d_sro < min_bga_cav:
                    min_bga_cav = d_sro
                if d_cu < min_bga_cu_cav:
                    min_bga_cu_cav = d_cu
                if d_sro < BGA_SRO_TO_CAVITY_UM - 0.05:
                    viol_bga_cav_254 += 1
                if d_cu < EXT_CU_TO_CAVITY_UM - 0.05:
                    viol_bga_cu_178 += 1
            for ex0, ey0, ex1, ey1 in U9_EMIB_BRIDGES.values():
                if any(ex0 <= px <= ex1 and ey0 <= py <= ey1 for px, py in cav) or _rect_to_poly_dist(
                    ex0, ey0, ex1, ey1, cav, prefilter_um=EXT_CU_TO_CAVITY_UM + 10.0
                ) < EXT_CU_TO_CAVITY_UM - 1.0:
                    viol_cav_emib += 1

        min_web = 1e9
        rec_list = list(recess_map.values())
        for i in range(len(rec_list)):
            for j in range(i + 1, len(rec_list)):
                d_w = _poly_to_poly_dist(rec_list[i].cavity_poly, rec_list[j].cavity_poly)
                if d_w < min_web:
                    min_web = d_w

        out.update(
            {
                "min_lsc_sro_to_cav_um": round(min_lsc_cav, 2) if caps else None,
                "min_bga_sro_to_cav_um": round(min_bga_cav, 2) if recess_map else None,
                "min_bga_cu_to_cav_um": round(min_bga_cu_cav, 2) if recess_map else None,
                "min_cavity_web_um": round(min_web, 2) if len(rec_list) > 1 else None,
                "viol_lsc_to_cav_lt_225": viol_lsc_225,
                "viol_bga_sro_to_cav_lt_254": viol_bga_cav_254,
                "viol_bga_cu_to_cav_lt_178": viol_bga_cu_178,
                "viol_cavity_web_lt_508": 1 if (len(rec_list) > 1 and min_web < CAVITY_WEB_MIN_UM - 0.05) else 0,
                "emib_shadow_violations": viol_emib + viol_cav_emib,
            }
        )
    return out


def _grid_pattern_summary(caps: Sequence[LscCap], pocket_id: str) -> str:
    """Summarize aligned row/column structure of one pocket directly from placed coordinates."""
    pk = [c for c in caps if c.pocket_id == pocket_id]
    if not pk:
        return "0"
    n_v = sum(1 for c in pk if int(round(c.rot_deg)) % 180 == 0)
    by_y: Dict[int, int] = defaultdict(int)
    for c in pk:
        by_y[int(round(c.y / 10.0))] += 1
    row_cnts = [by_y[k] for k in sorted(by_y.keys())]
    if len(set(row_cnts)) == 1:
        return f"{len(row_cnts)}x{row_cnts[0]} {'V' if n_v == len(pk) else 'H'} ({len(pk)})"
    return f"{'+'.join(str(x) for x in row_cnts)} {'V' if n_v == len(pk) else 'H'} ({len(pk)})"


def _render_u9_panel(
    svg: List[str],
    px: float,
    py: float,
    pw: float,
    ph: float,
    title: str,
    subtitle: str,
    title_color: str,
    caps: Sequence[LscCap],
    bgas: Sequence[BgaBall],
    sram_islands: Sequence[BBox],
    vddc0_bbox: BBox,
    wx0: float,
    wy0: float,
    wx1: float,
    wy1: float,
    clip_id: str,
    show_395_halo: bool = False,
    highlight_lt_390: bool = False,
    pocket_labels: Optional[Dict[str, str]] = None,
    recesses: Optional[Sequence[RecessGeometry]] = None,
) -> None:
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="10" fill="#0b1224" stroke="#334155" stroke-width="1.5"/>')
    svg.append(f'<text x="{px+18}" y="{py+28}" fill="{title_color}" font-size="16" font-weight="700">{html.escape(title)}</text>')
    svg.append(f'<text x="{px+18}" y="{py+48}" fill="#94a3b8" font-size="12">{html.escape(subtitle)}</text>')

    in_l, in_t, in_r, in_b = 18.0, 58.0, 18.0, 18.0
    sc = min((pw - in_l - in_r) / (wx1 - wx0), (ph - in_t - in_b) / (wy1 - wy0))
    bx0 = px + in_l + 0.5 * ((pw - in_l - in_r) - (wx1 - wx0) * sc)
    by0 = py + in_t + 0.5 * ((ph - in_t - in_b) - (wy1 - wy0) * sc)
    cw_px, ch_px = (wx1 - wx0) * sc, (wy1 - wy0) * sc

    svg.append(f'<defs><clipPath id="{clip_id}"><rect x="{bx0:.1f}" y="{by0:.1f}" width="{cw_px:.1f}" height="{ch_px:.1f}"/></clipPath></defs>')
    svg.append(f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{cw_px:.1f}" height="{ch_px:.1f}" fill="#050914" stroke="#1e293b" stroke-width="1.2"/>')

    def mp(x: float, y: float) -> Tuple[float, float]:
        return (bx0 + (x - wx0) * sc, by0 + (wy1 - y) * sc)

    svg.append(f'<g clip-path="url(#{clip_id})">')

    # 12B VDDC0 bbox & SRAM0 sub-islands
    vx0, vy0_m = mp(vddc0_bbox[0], vddc0_bbox[3])
    vw_px = (vddc0_bbox[2] - vddc0_bbox[0]) * sc
    vh_px = (vddc0_bbox[3] - vddc0_bbox[1]) * sc
    svg.append(
        f'<rect x="{vx0:.1f}" y="{vy0_m:.1f}" width="{vw_px:.1f}" height="{vh_px:.1f}" '
        'fill="#ef4444" fill-opacity="0.04" stroke="#ef4444" stroke-opacity="0.45" stroke-width="1.2" stroke-dasharray="6,4"/>'
    )
    for x1, y1, x2, y2 in sram_islands:
        ix0, iy0 = mp(x1, y2)
        svg.append(
            f'<rect x="{ix0:.1f}" y="{iy0:.1f}" width="{(x2-x1)*sc:.1f}" height="{(y2-y1)*sc:.1f}" '
            'fill="#10b981" fill-opacity="0.11" stroke="#34d399" stroke-opacity="0.7" stroke-width="1.4" stroke-dasharray="4,3"/>'
        )

    # EMIB shadow regions & Curved Recess Cavities (+178 um Ext Cu KOZ / Cavity R=508 / -225 um Safe Envelope)
    if recesses is not None:
        for ex0, ey0, ex1, ey1 in U9_EMIB_BRIDGES.values():
            if ex1 < wx0 - 500.0 or ex0 > wx1 + 500.0 or ey1 < wy0 - 500.0 or ey0 > wy1 + 500.0:
                continue
            emx, emy = mp(ex0, ey1)
            svg.append(
                f'<rect x="{emx:.1f}" y="{emy:.1f}" width="{(ex1-ex0)*sc:.1f}" height="{(ey1-ey0)*sc:.1f}" '
                'fill="#64748b" fill-opacity="0.10" stroke="#94a3b8" stroke-opacity="0.45" stroke-width="1.0" stroke-dasharray="4,4"/>'
            )

        def _poly_pts(poly: Sequence[Tuple[float, float]]) -> str:
            return " ".join(f"{mp(px_p, py_p)[0]:.1f},{mp(px_p, py_p)[1]:.1f}" for px_p, py_p in poly)

        for rec in recesses:
            if rec.outer_koz_poly:
                svg.append(
                    f'<polygon points="{_poly_pts(rec.outer_koz_poly)}" '
                    'fill="none" stroke="#fb7185" stroke-opacity="0.75" stroke-width="1.15" stroke-dasharray="5,3"/>'
                )
            if rec.cavity_poly:
                svg.append(
                    f'<polygon points="{_poly_pts(rec.cavity_poly)}" '
                    'fill="#06b6d4" fill-opacity="0.09" stroke="#22d3ee" stroke-opacity="0.95" stroke-width="1.55"/>'
                )
            if rec.inner_safe_poly:
                svg.append(
                    f'<polygon points="{_poly_pts(rec.inner_safe_poly)}" '
                    'fill="none" stroke="#34d399" stroke-opacity="0.80" stroke-width="1.15" stroke-dasharray="4,3"/>'
                )

    # BGA balls + optional 395um BGA-SRO clearance ring
    for b in bgas:
        if not (wx0 - 900 <= b.x <= wx1 + 900 and wy0 - 900 <= b.y <= wy1 + 900):
            continue
        sbx, sby = mp(b.x, b.y)
        if show_395_halo:
            svg.append(
                f'<circle cx="{sbx:.2f}" cy="{sby:.2f}" r="{(b.sro_r + BGA_TO_LSC_SRO_UM)*sc:.2f}" '
                'fill="none" stroke="#38bdf8" stroke-opacity="0.24" stroke-width="0.9" stroke-dasharray="3,3"/>'
            )
        bcol = "#475569"
        if b.net == "VDDC0":
            bcol = "#7f1d1d"
        elif b.net == "VDD_0P8_SRAM_CC0":
            bcol = "#065f46"
        elif "VDDCH" in b.net or "VDDC1" in b.net or "UCIE" in b.net:
            bcol = "#312e81"
        svg.append(f'<circle cx="{sbx:.2f}" cy="{sby:.2f}" r="{b.sro_r*sc:.2f}" fill="{bcol}" fill-opacity="0.55" stroke="#94a3b8" stroke-width="0.9"/>')

    # Flag original caps with <390um LSC-to-LSC pairs if requested
    viol_refs: set[str] = set()
    if highlight_lt_390:
        for i in range(len(caps)):
            for j in range(i + 1, len(caps)):
                if _rect_sro_to_sro_dist(caps[i], caps[j]) < LSC_TO_LSC_SRO_UM - 0.05:
                    viol_refs.add(caps[i].refdes)
                    viol_refs.add(caps[j].refdes)

    # Draw LSCs
    for c in caps:
        hx, hy = c.sro_half_extents
        tlx, tly = mp(c.x - hx, c.y + hy)
        is_viol = c.refdes in viol_refs
        stroke = "#fbbf24" if is_viol else "#cbd5e1"
        sw = "1.4" if is_viol else "0.95"
        svg.append(
            f'<rect x="{tlx:.2f}" y="{tly:.2f}" width="{2*hx*sc:.2f}" height="{2*hy*sc:.2f}" rx="1.5" '
            f'fill="#0f172a" stroke="{stroke}" stroke-width="{sw}"/>'
        )
        (p1x, p1y), (p2x, p2y) = c.pin_coords
        p1col = "#10b981" if c.pin1_net == "VDD_0P8_SRAM_CC0" else "#ef4444"
        pw_p = 150.0 * sc
        for px_c, py_c, pcol in ((p1x, p1y, p1col), (p2x, p2y, "#06b6d4")):
            sx, sy = mp(px_c, py_c)
            svg.append(
                f'<rect x="{sx-pw_p:.2f}" y="{sy-pw_p:.2f}" width="{2*pw_p:.2f}" height="{2*pw_p:.2f}" '
                f'fill="{pcol}" fill-opacity="0.92"/>'
            )

    if pocket_labels:
        # Place clean pocket callouts anchored to each pocket's cap cluster centroid
        by_pk: Dict[str, List[LscCap]] = defaultdict(list)
        for c in caps:
            by_pk[c.pocket_id].append(c)
        for pid, ptext in pocket_labels.items():
            pts = by_pk.get(pid, [])
            if not pts:
                continue
            mx = sum(it.x for it in pts) / len(pts)
            my = max(it.y for it in pts) + 750.0
            if pid in ("P9_NW_TOP", "P10_NE_TOP"):
                my = min(it.y for it in pts) - 680.0
            lx, ly = mp(mx, my)
            bw = max(84.0, len(ptext) * 6.5 + 14.0)
            svg.append(
                f'<rect x="{lx - bw/2:.1f}" y="{ly - 11:.1f}" width="{bw:.1f}" height="20" rx="4" '
                'fill="#020617" fill-opacity="0.88" stroke="#475569" stroke-width="0.9"/>'
            )
            svg.append(f'<text x="{lx:.1f}" y="{ly+3:.1f}" text-anchor="middle" fill="#f8fafc" font-size="10.5" font-weight="700">{html.escape(ptext)}</text>')

    svg.append("</g>")


def render_comparison_svg(
    out_svg: Path,
    orig_caps: Sequence[LscCap],
    new_caps: Sequence[LscCap],
    bgas: Sequence[BgaBall],
    sram_islands: Sequence[BBox],
    vddc0_bbox: BBox,
    orig_audit: Dict[str, object],
    new_audit: Dict[str, object],
    per_pocket_rows: Sequence[Dict[str, object]],
    recess_map: Dict[str, RecessGeometry],
    source_label: str,
) -> Path:
    W, H = 2600, 1780
    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" style="background:#050814;font-family:Segoe UI,Arial,sans-serif">'
    ]

    diff_tot = int(new_audit["count"]) - int(orig_audit["count"])
    diff_vddc0 = int(new_audit["vddc0_count"]) - int(orig_audit["vddc0_count"])
    diff_sram0 = int(new_audit["sram0_count"]) - int(orig_audit["sram0_count"])

    drc_clean = (
        new_audit.get("viol_bga_lt_395", 1) == 0
        and new_audit.get("viol_lsc_lt_390_pair_count", 1) == 0
        and new_audit.get("viol_lsc_to_cav_lt_225", 1) == 0
        and new_audit.get("viol_bga_sro_to_cav_lt_254", 1) == 0
        and new_audit.get("viol_bga_cu_to_cav_lt_178", 1) == 0
        and new_audit.get("viol_cavity_web_lt_508", 1) == 0
        and new_audit.get("emib_shadow_violations", 1) == 0
    )

    # Header
    svg.append(f'<rect x="0" y="0" width="{W}" height="108" fill="#0b1224" stroke="#1e293b" stroke-width="1.5"/>')
    svg.append(
        '<text x="28" y="42" fill="#f8fafc" font-size="24.5" font-weight="800">'
        'U9 (VDDC0 + VDD_0P8_SRAM_CC0) 0201 LSC + Mechanical Recess — Aligned Grid vs Original HH*dump.txt'
        '</text>'
    )
    svg.append(
        '<text x="28" y="72" fill="#38bdf8" font-size="14">'
        'Rules: BGA SRO-&gt;LSC &gt;= 395 | LSC-&gt;LSC &gt;= 390 | BGA SRO-&gt;Cav &gt;= 254 (Cu &gt;= 178) | LSC SRO-&gt;Cav &gt;= 225 | R_mill=508 | Web &gt;= 508 um | '
        f'Src: {html.escape(source_label)}'
        '</text>'
    )
    badge_col = "#34d399" if drc_clean else "#f87171"
    svg.append(f'<rect x="1930" y="20" width="642" height="68" rx="8" fill="#052e16" stroke="{badge_col}" stroke-width="1.5"/>')
    svg.append(
        f'<text x="2251" y="49" text-anchor="middle" fill="{badge_col}" font-size="16.5" font-weight="800">'
        f'RECESS+ALIGNED: {new_audit["count"]} LSCs vs ORIG: {orig_audit["count"]} LSCs (Delta = {diff_tot:+d} | {diff_tot/orig_audit["count"]*100:+.1f}%)'
        '</text>'
    )
    svg.append(
        f'<text x="2251" y="74" text-anchor="middle" fill="#cbd5e1" font-size="12.5">'
        f'VDDC0: {new_audit["vddc0_count"]} vs {orig_audit["vddc0_count"]} ({diff_vddc0:+d})  |  '
        f'SRAM0: {new_audit["sram0_count"]} vs {orig_audit["sram0_count"]} ({diff_sram0:+d})  |  '
        f'Min Cav: LSC={new_audit["min_lsc_sro_to_cav_um"]} BGA={new_audit["min_bga_sro_to_cav_um"]} um'
        '</text>'
    )

    u9_view = (-16200.0, 17400.0, 16200.0, 35200.0)
    short_code = {
        "P3_WEST_COL": "P3",
        "P4_MID_EAST_COL": "P4",
        "P5_EAST_DUAL": "P5",
        "P6_CENTER_DUAL": "P6",
        "P9_NW_TOP": "P9",
        "P10_NE_TOP": "P10",
    }
    orig_lbls = {
        str(r["pocket_id"]): (
            f'{short_code[str(r["pocket_id"])]}: {r["orig_total"]} ({r["orig_vddc0"]}+{r["orig_sram0"]})'
            if int(r["orig_sram0"]) > 0
            else f'{short_code[str(r["pocket_id"])]}: {r["orig_total"]}'
        )
        for r in per_pocket_rows
    }
    new_lbls = {
        str(r["pocket_id"]): f'{short_code[str(r["pocket_id"])]}: {r["new_total"]} ({int(r["delta_total"]):+d})'
        for r in per_pocket_rows
    }
    recess_list = list(recess_map.values())

    # Left Main Panel: Original HH*dump.txt (No Recess)
    _render_u9_panel(
        svg,
        px=24, py=124, pw=990, ph=1020,
        title=f'ORIGINAL DESIGN (HH*dump.txt) - {orig_audit["count"]} LSCs ({orig_audit["vddc0_count"]} VDDC0 + {orig_audit["sram0_count"]} SRAM0)',
        subtitle=f'250 um LSC-to-LSC pitch (Amber = {orig_audit["viol_lsc_lt_390_pair_count"]} pairs < 390 um) | Min BGA={orig_audit["min_bga_sro_to_lsc_sro_um"]} um | No Recess',
        title_color="#f59e0b",
        caps=orig_caps, bgas=bgas, sram_islands=sram_islands, vddc0_bbox=vddc0_bbox,
        wx0=u9_view[0], wy0=u9_view[1], wx1=u9_view[2], wy1=u9_view[3],
        clip_id="clip_orig",
        show_395_halo=False,
        highlight_lt_390=True,
        pocket_labels=orig_lbls,
        recesses=None,
    )

    # Middle Main Panel: New Rule + Mechanical Recess Aligned Sandbox
    _render_u9_panel(
        svg,
        px=1032, py=124, pw=990, ph=1020,
        title=f'NEW RULE + RECESS CAVITY (Aligned Grid) - {new_audit["count"]} LSCs ({new_audit["vddc0_count"]} VDDC0 + {new_audit["sram0_count"]} SRAM0)',
        subtitle=(
            f'Min Gaps: BGA-SRO->LSC={new_audit["min_bga_sro_to_lsc_sro_um"]}, LSC->LSC={new_audit["min_lsc_sro_to_lsc_sro_um"]}, '
            f'LSC->Cav={new_audit["min_lsc_sro_to_cav_um"]}, BGA-SRO->Cav={new_audit["min_bga_sro_to_cav_um"]}, Web={new_audit["min_cavity_web_um"]} um'
        ),
        title_color="#34d399",
        caps=new_caps, bgas=bgas, sram_islands=sram_islands, vddc0_bbox=vddc0_bbox,
        wx0=u9_view[0], wy0=u9_view[1], wx1=u9_view[2], wy1=u9_view[3],
        clip_id="clip_new",
        show_395_halo=True,
        highlight_lt_390=False,
        pocket_labels=new_lbls,
        recesses=recess_list,
    )

    # Right Comparison Scorecard Panel (x = 2040..2576, y = 124..1144)
    rx, ry, rw, rh = 2040, 124, 536, 1020
    svg.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="10" fill="#0b1224" stroke="#334155" stroke-width="1.5"/>')
    svg.append(f'<text x="{rx+20}" y="{ry+30}" fill="#f8fafc" font-size="17" font-weight="800">LSC + Recess Cavity Comparison &amp; Audit</text>')

    # Legend items (compact spacing so full scorecard fits cleanly inside 1020px height)
    leg = [
        ("#ef4444", "Pin 1 Red = VDDC0 | Green = SRAM0 | Cyan Pin 2 = VSS"),
        ("#22d3ee", "Solid Cyan = LSC_CAVITY Edge (R_mill = 508 um, >=254 BGA)"),
        ("#34d399", "Dashed Emerald = -225 um Safe LSC SRO Envelope"),
        ("#fb7185", "Dashed Rose = +178 um Ext Cu KOZ (+395 um BGA Ring)"),
        ("#fbbf24", "Amber Box (Left) = Orig Pair < 390 um (250 um)"),
        ("#94a3b8", "Slate Circles = A1 BGA Pads (480 SRO / 550 Cu)"),
    ]
    ly = ry + 54
    for col, txt in leg:
        svg.append(f'<rect x="{rx+20}" y="{ly-10}" width="12" height="12" rx="3" fill="{col}"/>')
        svg.append(f'<text x="{rx+38}" y="{ly+1}" fill="#cbd5e1" font-size="11.5">{html.escape(txt)}</text>')
        ly += 21

    # Totals summary card
    cy = ly + 8
    svg.append(f'<rect x="{rx+18}" y="{cy}" width="{rw-36}" height="112" rx="8" fill="#060b16" stroke="#38bdf8" stroke-width="1.2"/>')
    svg.append(f'<text x="{rx+32}" y="{cy+24}" fill="#38bdf8" font-size="13.5" font-weight="700">Executive Delta Summary (With Mechanical Recess)</text>')
    svg.append(f'<text x="{rx+32}" y="{cy+48}" fill="#f8fafc" font-size="13">Original (No Recess): <tspan font-weight="800">{orig_audit["count"]}</tspan>  ({orig_audit["vddc0_count"]} VDDC0 + {orig_audit["sram0_count"]} SRAM0)</text>')
    svg.append(f'<text x="{rx+32}" y="{cy+72}" fill="#34d399" font-size="13">Aligned + Recess (395/390/225): <tspan font-weight="800">{new_audit["count"]}</tspan>  ({new_audit["vddc0_count"]} VDDC0 + {new_audit["sram0_count"]} SRAM0)</text>')
    svg.append(
        f'<text x="{rx+32}" y="{cy+97}" fill="#fbbf24" font-size="13.5" font-weight="800">'
        f'Net Difference: {diff_tot:+d} LSCs  (VDDC0 {diff_vddc0:+d}, SRAM0 {diff_sram0:+d})</text>'
    )

    # Per-pocket breakdown table
    ty = cy + 130
    svg.append(f'<text x="{rx+20}" y="{ty}" fill="#f8fafc" font-size="14" font-weight="700">Per-Pocket Comparison (Aligned Grid + Recess)</text>')
    ty += 14
    svg.append(f'<rect x="{rx+18}" y="{ty}" width="{rw-36}" height="30" fill="#1e293b"/>')
    cols_x = [rx+26, rx+196, rx+270, rx+338, rx+412]
    headers = ["Pocket (Ori)", "Orig", "New", "Delta", "VDDC0 / SRAM0"]
    for hx_t, htxt in zip(cols_x, headers):
        svg.append(f'<text x="{hx_t}" y="{ty+20}" fill="#e2e8f0" font-size="11.5" font-weight="700">{htxt}</text>')
    ty += 32

    for idx_r, row in enumerate(per_pocket_rows):
        bg = "#080f20" if idx_r % 2 == 0 else "#0d162c"
        svg.append(f'<rect x="{rx+18}" y="{ty}" width="{rw-36}" height="42" fill="{bg}" stroke="#1e293b" stroke-width="0.8"/>')
        d_tot = int(row["delta_total"])
        d_col = "#34d399" if d_tot > 0 else ("#f87171" if d_tot < 0 else "#cbd5e1")
        svg.append(f'<text x="{cols_x[0]}" y="{ty+19}" fill="#f8fafc" font-size="12" font-weight="700">{html.escape(str(row["pocket_label"]))}</text>')
        svg.append(f'<text x="{cols_x[0]}" y="{ty+35}" fill="#94a3b8" font-size="10.5">{html.escape(str(row["ori_summary"]))} | Cav={row["min_lsc_sro_to_cav_um"]}</text>')
        svg.append(f'<text x="{cols_x[1]}" y="{ty+25}" fill="#f59e0b" font-size="13" font-weight="700">{row["orig_total"]}</text>')
        svg.append(f'<text x="{cols_x[2]}" y="{ty+25}" fill="#34d399" font-size="13" font-weight="700">{row["new_total"]}</text>')
        svg.append(f'<text x="{cols_x[3]}" y="{ty+25}" fill="{d_col}" font-size="13" font-weight="800">{d_tot:+d}</text>')
        svg.append(f'<text x="{cols_x[4]}" y="{ty+18}" fill="#cbd5e1" font-size="11">Orig: {row["orig_vddc0"]} / {row["orig_sram0"]}</text>')
        svg.append(f'<text x="{cols_x[4]}" y="{ty+34}" fill="#38bdf8" font-size="11">New:  {row["new_vddc0"]} / {row["new_sram0"]}</text>')
        ty += 44

    # Physics & Recess Audit explanation box dynamically populated from actual computed pocket counts
    by_pid = {str(r["pocket_id"]): r for r in per_pocket_rows}
    p3_r, p4_r = by_pid["P3_WEST_COL"], by_pid["P4_MID_EAST_COL"]
    p5_r, p6_r = by_pid["P5_EAST_DUAL"], by_pid["P6_CENTER_DUAL"]
    p9_r, p10_r = by_pid["P9_NW_TOP"], by_pid["P10_NE_TOP"]

    ty += 12
    box_h = (ry + rh - 10) - ty
    svg.append(f'<rect x="{rx+18}" y="{ty}" width="{rw-36}" height="{box_h}" rx="8" fill="#060b16" stroke="#334155" stroke-width="1"/>')
    p3_pat = _grid_pattern_summary(new_caps, "P3_WEST_COL")
    p4_pat = _grid_pattern_summary(new_caps, "P4_MID_EAST_COL")
    p5_pat = _grid_pattern_summary(new_caps, "P5_EAST_DUAL")
    p6_pat = _grid_pattern_summary(new_caps, "P6_CENTER_DUAL")
    p9_pat = _grid_pattern_summary(new_caps, "P9_NW_TOP")
    p10_pat = _grid_pattern_summary(new_caps, "P10_NE_TOP")
    notes = [
        (f'Why Recess + Aligned Total = {new_audit["count"]} ({diff_tot:+d} vs {orig_audit["count"]} Orig):', "#f8fafc", 12.5, "700"),
        ("1. Curved Recess Cost (R_mill=508, BGA->Cav>=254, LSC->Cav>=225):", "#22d3ee", 11.5, "700"),
        (f'   - P3 ({p3_r["orig_total"]}->{p3_r["new_total"]}) & P4 ({p4_r["orig_total"]}->{p4_r["new_total"]}): {p3_pat}; top center BGA recess notch.', "#cbd5e1", 11, "400"),
        (f'   - P5 ({p5_r["orig_total"]}->{p5_r["new_total"]}) & P6 ({p6_r["orig_total"]}->{p6_r["new_total"]}): {p5_pat}; {p6_pat}.', "#cbd5e1", 11, "400"),
        (f'   - P9 ({p9_r["orig_total"]}->{p9_r["new_total"]}) & P10 ({p10_r["orig_total"]}->{p10_r["new_total"]}): {p9_pat}; {p10_pat}.', "#cbd5e1", 11, "400"),
        ("2. Strict Non-Zigzag Alignment & 180 deg Alternation:", "#34d399", 11.5, "700"),
        ("   Every pocket lies on shared Y rows / X cols (0/180 V & 90/270 H).", "#cbd5e1", 11, "400"),
        ("3. Verified Mechanical + Electrical DRC (0 Violations):", "#38bdf8", 11.5, "700"),
        (f'   - BGA SRO->LSC: {new_audit["min_bga_sro_to_lsc_sro_um"]} (>=395) | LSC->LSC: {new_audit["min_lsc_sro_to_lsc_sro_um"]} (>=390)', "#34d399", 11, "700"),
        (f'   - LSC->Cav: {new_audit["min_lsc_sro_to_cav_um"]} (>=225) | BGA->Cav: {new_audit["min_bga_sro_to_cav_um"]} (>=254) | Cu: {new_audit["min_bga_cu_to_cav_um"]}', "#34d399", 11, "700"),
        (f'   - Web: {new_audit["min_cavity_web_um"]} (>=508) | EMIB ov: {new_audit["emib_shadow_violations"]} | Tot Viol: 0', "#34d399", 11, "700"),
    ]
    ny = ty + 20
    for txt, col, sz, fw in notes:
        svg.append(f'<text x="{rx+28}" y="{ny}" fill="{col}" font-size="{sz}" font-weight="{fw}">{html.escape(txt)}</text>')
        ny += 21

    # Bottom Detail Zoom Panels (y = 1164..1756)
    _render_u9_panel(
        svg,
        px=24, py=1164, pw=1260, ph=592,
        title=f'DETAIL ZOOM A (Recess + Aligned): P4 ({p4_r["new_total"]} VDDC0) & P5 ({p5_r["new_total"]} = {p5_r["new_vddc0"]} VDDC0 + {p5_r["new_sram0"]} SRAM0)',
        subtitle=f'P4 = {p4_pat} (0/180 deg) | P5 = {p5_pat} (90/270 deg) inside R_mill=508 um LSC_CAVITY (-225 um Safe Envelope)',
        title_color="#38bdf8",
        caps=new_caps, bgas=bgas, sram_islands=sram_islands, vddc0_bbox=vddc0_bbox,
        wx0=3200.0, wy0=18200.0, wx1=13600.0, wy1=29600.0,
        clip_id="clip_zoom_p5",
        show_395_halo=True,
        highlight_lt_390=False,
        recesses=recess_list,
    )
    _render_u9_panel(
        svg,
        px=1304, py=1164, pw=1272, ph=592,
        title=f'DETAIL ZOOM B (Recess + Aligned): NW Top P9 ({p9_r["new_total"]}, {int(p9_r["delta_total"]):+d}) & NE Top P10 ({p10_r["new_total"]}, {int(p10_r["delta_total"]):+d})',
        subtitle=f'Straight 90/270 deg rows inside Top Recess (-225 um): P9 = {p9_pat} | P10 = {p10_pat} | U39 EMIB Bridge Excluded',
        title_color="#38bdf8",
        caps=new_caps, bgas=bgas, sram_islands=sram_islands, vddc0_bbox=vddc0_bbox,
        wx0=-14200.0, wy0=30400.0, wx1=14200.0, wy1=34400.0,
        clip_id="clip_zoom_top",
        show_395_halo=True,
        highlight_lt_390=False,
        recesses=recess_list,
    )

    svg.append("</svg>")
    xml_text = "\n".join(svg)
    ET.fromstring(xml_text.encode("utf-8"))
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(xml_text, encoding="utf-8")
    return out_svg


def run_u9_new_rule_sandbox(
    hh_dump_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, object]:
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import (
            resolve_active_work_dir,
            resolve_output_dir,
            resolve_stage1_inputs_dir,
        )
    except ImportError:
        from pdn_paths import resolve_active_work_dir, resolve_output_dir, resolve_stage1_inputs_dir  # type: ignore

    ws_root = Path(__file__).resolve().parents[2]
    eff_wd, is_custom = resolve_active_work_dir()
    if out_dir is None:
        out_dir = resolve_output_dir("agent04_pdn_architect/pdn_sandbox")
    elif is_custom and not out_dir.is_absolute():
        out_dir = (eff_wd / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    s1_dir = resolve_stage1_inputs_dir() if is_custom else (ws_root / "agent04_pdn_architect" / "stage1_inputs")
    dump_p = hh_dump_path if hh_dump_path is not None else (DEFAULT_HH_DUMP if DEFAULT_HH_DUMP.is_file() else None)

    bgas, orig_caps, sram_islands, vddc0_bbox, source_label = load_u9_data(dump_p, s1_dir)
    orig_audit = audit_caps(orig_caps, bgas)

    recess_map: Dict[str, RecessGeometry] = {
        pid: build_u9_pocket_recess(pid, pbox, bgas, orig_caps)
        for pid, _, pbox in U9_POCKETS
    }

    new_caps: List[LscCap] = []
    per_pocket_rows: List[Dict[str, object]] = []
    for pid, plabel, pbox in U9_POCKETS:
        rec = recess_map[pid]
        pk_new = pack_pocket_new_rule(pid, pbox, bgas, sram_islands, recess=rec)
        new_caps.extend(pk_new)

        pk_audit = audit_caps(pk_new, bgas, recess_map={pid: rec})
        pk_orig = [c for c in orig_caps if c.pocket_id == pid]
        ov = sum(1 for c in pk_orig if c.pin1_net == "VDDC0")
        os_cnt = sum(1 for c in pk_orig if c.pin1_net == "VDD_0P8_SRAM_CC0")
        nv = sum(1 for c in pk_new if c.pin1_net == "VDDC0")
        ns = sum(1 for c in pk_new if c.pin1_net == "VDD_0P8_SRAM_CC0")
        n_vert = sum(1 for c in pk_new if int(round(c.rot_deg)) % 180 == 0)
        n_horiz = len(pk_new) - n_vert
        per_pocket_rows.append(
            {
                "pocket_id": pid,
                "pocket_label": plabel,
                "orig_total": len(pk_orig),
                "orig_vddc0": ov,
                "orig_sram0": os_cnt,
                "new_total": len(pk_new),
                "new_vddc0": nv,
                "new_sram0": ns,
                "delta_total": len(pk_new) - len(pk_orig),
                "delta_vddc0": nv - ov,
                "delta_sram0": ns - os_cnt,
                "new_v_count": n_vert,
                "new_h_count": n_horiz,
                "ori_summary": f"V={n_vert}, H={n_horiz}",
                "cavity_area_mm2": rec.cavity_area_mm2,
                "min_bga_sro_to_cav_um": pk_audit["min_bga_sro_to_cav_um"],
                "min_bga_cu_to_cav_um": pk_audit["min_bga_cu_to_cav_um"],
                "min_lsc_sro_to_cav_um": pk_audit["min_lsc_sro_to_cav_um"],
            }
        )

    new_audit = audit_caps(new_caps, bgas, recess_map=recess_map)
    if (
        new_audit["viol_bga_lt_395"]
        or new_audit["viol_lsc_lt_390_pair_count"]
        or new_audit.get("viol_lsc_to_cav_lt_225", 0)
        or new_audit.get("viol_bga_sro_to_cav_lt_254", 0)
        or new_audit.get("viol_bga_cu_to_cav_lt_178", 0)
        or new_audit.get("viol_cavity_web_lt_508", 0)
        or new_audit.get("emib_shadow_violations", 0)
    ):
        raise RuntimeError(f"SANDBOX_DRC_VIOLATION: {json.dumps(new_audit)}")

    out_svg = out_dir / "u9_vddc0_sram0_lsc_new_rule_395_390_comparison.svg"
    render_comparison_svg(
        out_svg=out_svg,
        orig_caps=orig_caps,
        new_caps=new_caps,
        bgas=bgas,
        sram_islands=sram_islands,
        vddc0_bbox=vddc0_bbox,
        orig_audit=orig_audit,
        new_audit=new_audit,
        per_pocket_rows=per_pocket_rows,
        recess_map=recess_map,
        source_label=source_label,
    )

    # Export placement CSV & JSON audit
    out_csv = out_dir / "u9_vddc0_sram0_lsc_new_rule_395_390.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "refdes",
                "pocket_id",
                "x_um",
                "y_um",
                "rotation_deg",
                "pin1_net",
                "pin2_net",
                "sro_x1",
                "sro_y1",
                "sro_x2",
                "sro_y2",
                "min_bga_sro_um",
                "min_lsc_sro_to_cav_um",
            ]
        )
        for c in new_caps:
            hx, hy = c.sro_half_extents
            md_b = _rect_sro_to_bga_dist(c, bgas)
            _, md_c = _rect_sro_inside_cavity(c.x, c.y, hx, hy, recess_map[c.pocket_id].cavity_poly, 0.0, exact_dist=True)
            w.writerow(
                [
                    c.refdes,
                    c.pocket_id,
                    c.x,
                    c.y,
                    c.rot_deg,
                    c.pin1_net,
                    c.pin2_net,
                    round(c.x - hx, 2),
                    round(c.y - hy, 2),
                    round(c.x + hx, 2),
                    round(c.y + hy, 2),
                    round(md_b, 2),
                    round(md_c, 2),
                ]
            )

    summary = {
        "rules": {
            "bga_sro_to_lsc_sro_min_um": BGA_TO_LSC_SRO_UM,
            "lsc_sro_to_lsc_sro_min_um": LSC_TO_LSC_SRO_UM,
            "recess_cavity_ignored": False,
            "bga_sro_to_cavity_min_um": BGA_SRO_TO_CAVITY_UM,
            "lsc_sro_to_cavity_min_um": LSC_SRO_TO_CAVITY_UM,
            "ext_cu_to_cavity_min_um": EXT_CU_TO_CAVITY_UM,
            "cavity_mill_radius_um": CAVITY_MILL_RADIUS_UM,
            "cavity_web_min_um": CAVITY_WEB_MIN_UM,
        },
        "source_baseline": source_label,
        "original_hh_dump": orig_audit,
        "new_rule_sandbox": new_audit,
        "delta": {
            "total": int(new_audit["count"]) - int(orig_audit["count"]),
            "vddc0": int(new_audit["vddc0_count"]) - int(orig_audit["vddc0_count"]),
            "sram0": int(new_audit["sram0_count"]) - int(orig_audit["sram0_count"]),
        },
        "per_pocket": per_pocket_rows,
        "outputs": {"svg": str(out_svg), "csv": str(out_csv)},
    }
    out_json = out_dir / "u9_vddc0_sram0_lsc_new_rule_395_390_audit.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["outputs"]["json"] = str(out_json)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="U9 VDDC0+SRAM0 LSC Sandbox under 395um BGA-SRO / 390um LSC-SRO rule")
    parser.add_argument("--hh-dump", default=None, help="Path to HH*dump.txt (auto-detected if present)")
    parser.add_argument("--out-dir", default=None, help="Output directory (defaults to pdn_sandbox/)")
    args = parser.parse_args()
    res = run_u9_new_rule_sandbox(
        hh_dump_path=Path(args.hh_dump) if args.hh_dump else None,
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
