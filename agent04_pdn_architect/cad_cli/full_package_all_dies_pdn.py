"""
Full-Package All-Dies, All-Rails 27-Layer PDN Synthesizer (`SURFACE` L01 -> `BASE` L27)
for Cadence APD 25.1 (`PDN_test.mcm` read-only -> Brand-New `.mcm`).

Covers ALL 3 Tasks & ALL matching PDN power rails across ALL 24 die/HBM sites:
  - Task 1 (`4 x LDB` + `4 x LDC`):
      * `VDDUC0..3` (`U7, U5, U8, U6`) + `VDDCH0..3` (`U2, U4, U3, U1`) + `VSS`
      * Full `VIA` outside EMIB `157.5 um` KOZs + `16 um` `SURFACE` collar straps (`U25..U40`),
        `4FCO..4BCO` eDTC KOZs (`C2207..C2214, C2238..C2244, C2271..C2278`), `100%` `U25..U40` EMIB
        `C0` & `10F CSB`, `9F->5F`/`9B->5B` `VSS` + `VDD` stitch, `4FCO->4BCO` Core PTH, and
        global curved `POLY_CAVITY` + `180 deg` `CONDUCTOR/BASE` LSCs.
  - Task 2 (`4 x LDA`):
      * `VDDC0..3` + `VDD_0P8_SRAM_CC0..3` (`U9, U12, U88, U10`) + `VSS`
      * Exact symmetry transforms (`0.000 um`), `3:1` Partial VIA + `15 um` Vertical C/S-Jog on
        `SURFACE`, `10F` SRAM collector + EMIB Guard Rings, all `24` `4FCO` eDTCs (`C2215..C2246`),
        `9F->5F`/`9B->5B` stitch, Core PTH, and extended `12B/11B` stepped boundaries.
  - Task 3 (`12 x HBM4E` + `12 x LAVA_BRIDGE` + `12 x HBMPHY_UC*`):
      * `VDDQ_0P85_HBM_MEM0..B`, `VDDC_1P0_HBM_MEM0..B`, `VDDQL0..B`, `VPP_1P8_HBM_MEM0..B`,
        `VDD_0P75_HBMPHY_UC0..B`, plus `VSS` & `U98` power anchors
      * Variant A (`LAVA_BRIDGE_22` ref `U13/U41/U5`) & Variant B (`LAVA_BRIDGE_23` ref `U16/U44/U6`)
        synthesized directly from real pin coordinates, non-overlapping `VDDQL*` vs `HBMPHY_UC*`
        split (`0` illegal `12F` shapes inside EMIB KOZ, `12B` `MISC`/`VDDIO` BGA clearances,
        inter-slice `12B/10B/8B` pockets), real `24` HBM eDTCs (`C2247..C2270`), and global
        co-pocket `POLY_CAVITY` + `180 deg` `BASE` LSCs.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from agent04_pdn_architect.cad_cli.cadence_runner import CadenceBatchRunner
from agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine import (
    CurvedPocketResult,
    PlacedLscItem,
    synthesize_curved_bga_recess_and_pack_lscs,
)
from agent04_pdn_architect.cad_cli.hbm_surface_and_csb_router import (
    _drop_from_surface_atomic,
    _point_in_any_box,
    _segment_clear_of_layer_clines,
    _segment_clear_of_obs,
    connect_u9_sram0_10f_backbone,
    route_u13_emib_csb_and_c0_pins,
    route_u13_hbm_surface_and_10f_csb,
    route_u9_emib_csb_and_c0_pins,
)
from agent04_pdn_architect.cad_cli.multi_rail_polygon_engine import (
    ALL_24_INNER_LAYERS,
    BBox,
    CORE_PP_8_LAYERS,
    CavityRecord,
    ClineRecord,
    EVEN_POWER_LAYERS,
    EdtcInstanceProfile,
    FastXYClearanceGrid,
    MultiRailLayerOwnershipIndex,
    ODD_VSS_LAYERS,
    Point,
    PolygonIsland,
    U13_DOMAIN_BBOX,
    U13_EDTC_BODIES,
    U41_EMIB_BBOX,
    U9_DOMAIN_BBOX,
    U9_EDTC_BODIES,
    U9_EMIB_BRIDGES,
    ViaRecord,
    audit_via_continuity_and_zero_overlap,
    bboxes_intersect,
    build_u13_hbm_27layer_polygons,
    build_u9_lda_27layer_polygons,
    can_place_via_stack_zero_overlap,
    compute_real_edtc_profiles,
    expand_bbox,
    insert_via_stack_zero_overlap,
    make_plane_with_Notches_and_voids,
    min_dist_to_poly_edges,
    point_in_poly,
    rect_vertices,
    route_bottom_bga_and_lsc_with_atomic_pruning,
    subtract_edge_notches_from_rect,
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays,
    synthesize_concentric_edtc_stacks,
    synthesize_multi_rail_core_pth_and_pp,
    union_rect_boxes_to_polygons,
)
from agent04_pdn_architect.cad_cli.pdn_prelearn import resolve_mcm_in_work_dir
from agent04_pdn_architect.cad_cli.step1_step2_u9_u13_validator import (
    _hexagonal_6via_offsets,
    _octagonal_8via_offsets,
    write_master_recipe,
)
from agent04_pdn_architect.cad_cli.u9_vddc_sram_surface_3to1_jog_router import (
    route_u9_vddc0_sram0_vss_3to1_vertical_jog,
)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DEFAULT_PINS_CSV = Path(
    r"~\.gemini\jetski\brain\cd0b264f-8828-4f5f-8b29-b636814ca9b5\scratch\ro_inspect\all_56_dies_pdn_pins.csv"
)

ALL_EMIB_U25_TO_U40: Dict[str, BBox] = {
    "U25": (-17663.8,  16464.8, -14310.3,  25901.1),
    "U26": (-17663.8, -15420.2, -14310.3,  -5983.9),
    "U27": ( 14310.3, -25901.1,  17663.8, -16464.8),
    "U28": ( 14310.3,   5983.9,  17663.8,  15420.2),
    "U29": (-17663.8,   5983.9, -14310.3,  15460.2),
    "U30": (-17663.8, -25901.1, -14310.3, -16424.8),
    "U31": ( 14310.3, -15460.2,  17663.8,  -5983.9),
    "U32": ( 14310.3,  16424.8,  17663.8,  25901.1),
    "U33": (-24272.4,  30192.7, -20405.7,  33502.6),
    "U34": ( 20405.7, -33502.6,  24272.4, -30192.7),
    "U35": ( 20405.7,  30192.7,  24272.8,  33502.6),
    "U36": (-24272.8, -33502.6, -20405.7, -30192.7),
    "U37": (-24272.4,  -1692.3, -17160.1,   1692.3),
    "U38": ( 17160.1,  -1692.3,  24272.4,   1692.3),
    "U39": ( -1634.2,  34347.7,   1634.2,  38214.2),
    "U40": ( -1634.2, -38214.2,   1634.2, -34347.7),
}


# ---------------------------------------------------------------------------
# Pure Python Polygon Helpers & Inter-Domain Clearance Auditor
# ---------------------------------------------------------------------------
def _clip_poly_halfplane(
    pts: Sequence[Point],
    keep_fn: Callable[[Point], bool],
    intersect_fn: Callable[[Point, Point], Point],
) -> List[Point]:
    if not pts:
        return []
    out: List[Point] = []
    prev = pts[-1]
    prev_in = keep_fn(prev)
    for cur in pts:
        cur_in = keep_fn(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect_fn(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect_fn(prev, cur))
        prev = cur
        prev_in = cur_in
    return [(round(x, 3), round(y, 3)) for x, y in out]


def clip_poly_to_bbox(pts: Sequence[Point], b: BBox) -> List[Point]:
    x0, y0, x1, y1 = b

    def _ix(p1: Point, p2: Point, xv: float) -> Point:
        dx = p2[0] - p1[0]
        if abs(dx) < 1e-12:
            return (xv, p1[1])
        t = (xv - p1[0]) / dx
        return (xv, p1[1] + t * (p2[1] - p1[1]))

    def _iy(p1: Point, p2: Point, yv: float) -> Point:
        dy = p2[1] - p1[1]
        if abs(dy) < 1e-12:
            return (p1[0], yv)
        t = (yv - p1[1]) / dy
        return (p1[0] + t * (p2[0] - p1[0]), yv)

    res = list(pts)
    res = _clip_poly_halfplane(res, lambda p: p[0] >= x0, lambda p1, p2: _ix(p1, p2, x0))
    res = _clip_poly_halfplane(res, lambda p: p[0] <= x1, lambda p1, p2: _ix(p1, p2, x1))
    res = _clip_poly_halfplane(res, lambda p: p[1] >= y0, lambda p1, p2: _iy(p1, p2, y0))
    res = _clip_poly_halfplane(res, lambda p: p[1] <= y1, lambda p1, p2: _iy(p1, p2, y1))
    cleaned: List[Point] = []
    for pt in res:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 0.05:
            cleaned.append(pt)
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= 0.05:
        cleaned.pop()
    return cleaned if len(cleaned) >= 3 else []


def _poly_bbox(pts: Sequence[Point]) -> BBox:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _poly_area(pts: Sequence[Point]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def _subtract_boxes_from_island(isl: PolygonIsland, notch_boxes: Sequence[BBox]) -> Optional[PolygonIsland]:
    """Subtract rectilinear notch/keepout boxes from `isl` while preserving existing voids."""
    if not notch_boxes:
        return isl
    bb = isl.bbox
    rel_boxes = [nb for nb in notch_boxes if bboxes_intersect(bb, nb)]
    if not rel_boxes:
        return isl
    is_rect = len(isl.vertices) == 4 and abs(_poly_area(isl.vertices) - max(0.0, (bb[2] - bb[0]) * (bb[3] - bb[1]))) < 50.0
    if is_rect:
        edge_cross = []
        interior = []
        for nb in rel_boxes:
            if nb[0] > bb[0] + 15.0 and nb[1] > bb[1] + 15.0 and nb[2] < bb[2] - 15.0 and nb[3] < bb[3] - 15.0:
                interior.append(nb)
            else:
                edge_cross.append(nb)
        verts = subtract_edge_notches_from_rect(bb, edge_cross) if edge_cross else list(isl.vertices)
        voids = list(isl.voids) + union_rect_boxes_to_polygons(interior)
        if _poly_area(verts) < 1600.0:
            return None
        kept_voids = [
            vd for vd in voids
            if all(point_in_poly(vx, vy, verts) and min_dist_to_poly_edges(vx, vy, verts) >= 12.0 for vx, vy in vd)
        ]
        return PolygonIsland(isl.layer, isl.net_name, verts, voids=kept_voids, tag=isl.tag, is_dynamic=isl.is_dynamic)
    # Rasterized rectilinear cell-subtraction for non-rectangular L/U polygons
    xs = sorted({round(v, 3) for v in ([p[0] for p in isl.vertices] + [b[0] for b in rel_boxes] + [b[2] for b in rel_boxes])})
    ys = sorted({round(v, 3) for v in ([p[1] for p in isl.vertices] + [b[1] for b in rel_boxes] + [b[3] for b in rel_boxes])})
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx <= 0 or ny <= 0:
        return isl
    kept_boxes: List[BBox] = []
    for ix in range(nx):
        cx = 0.5 * (xs[ix] + xs[ix + 1])
        for iy in range(ny):
            cy = 0.5 * (ys[iy] + ys[iy + 1])
            if not point_in_poly(cx, cy, isl.vertices):
                continue
            if any(nb[0] <= cx <= nb[2] and nb[1] <= cy <= nb[3] for nb in rel_boxes):
                continue
            kept_boxes.append((xs[ix], ys[iy], xs[ix + 1], ys[iy + 1]))
    merged = union_rect_boxes_to_polygons(kept_boxes)
    if not merged:
        return None
    best = max(merged, key=_poly_area)
    if _poly_area(best) < 1600.0:
        return None
    kept_voids = [
        vd for vd in isl.voids
        if all(point_in_poly(vx, vy, best) and min_dist_to_poly_edges(vx, vy, best) >= 12.0 for vx, vy in vd)
    ]
    return PolygonIsland(isl.layer, isl.net_name, best, voids=kept_voids, tag=isl.tag, is_dynamic=isl.is_dynamic)


def transform_and_clip_island(
    isl: PolygonIsland,
    tf: Callable[[float, float], Point],
    net_map: Dict[str, str],
    clip_box: BBox,
    void_clip_margin: float = 15.0,
) -> Optional[PolygonIsland]:
    t_verts = [tf(x, y) for x, y in isl.vertices]
    c_verts = clip_poly_to_bbox(t_verts, clip_box)
    if not c_verts or _poly_area(c_verts) < 1600.0:
        return None
    cb = _poly_bbox(c_verts)
    inner_clip = (cb[0] + void_clip_margin, cb[1] + void_clip_margin, cb[2] - void_clip_margin, cb[3] - void_clip_margin)
    new_voids: List[List[Point]] = []
    if inner_clip[2] - inner_clip[0] > 40.0 and inner_clip[3] - inner_clip[1] > 40.0:
        for vd in isl.voids:
            tv = [tf(x, y) for x, y in vd]
            cv = clip_poly_to_bbox(tv, inner_clip)
            if cv and _poly_area(cv) >= 1600.0:
                new_voids.append(cv)
    new_net = net_map.get(isl.net_name, isl.net_name)
    is_dyn = isl.is_dynamic
    mode_tag = isl.tag
    if isl.layer.upper() == "SURFACE" and new_net != "__ISOLATED__":
        is_dyn = False
        mode_tag = f"STATIC_NET_{isl.tag}"
    return PolygonIsland(
        layer=isl.layer,
        net_name=new_net,
        vertices=c_verts,
        voids=new_voids,
        tag=mode_tag,
        is_dynamic=is_dyn,
    )


def _poly_min_distance(poly_a: Sequence[Point], poly_b: Sequence[Point]) -> float:
    """Exact minimum edge/vertex/containment distance (`0.0` if overlapping) between closed polygons."""
    if any(point_in_poly(px, py, poly_b) for px, py in poly_a) or any(point_in_poly(px, py, poly_a) for px, py in poly_b):
        return 0.0
    # Check segment intersections first
    na, nb = len(poly_a), len(poly_b)
    from agent04_pdn_architect.cad_cli.hbm_surface_and_csb_router import _seg_to_seg_dist

    best = 1e12
    for i in range(na):
        a1, a2 = poly_a[i], poly_a[(i + 1) % na]
        abx0, aby0 = min(a1[0], a2[0]), min(a1[1], a2[1])
        abx1, aby1 = max(a1[0], a2[0]), max(a1[1], a2[1])
        for j in range(nb):
            b1, b2 = poly_b[j], poly_b[(j + 1) % nb]
            if max(b1[0], b2[0]) < abx0 - best or min(b1[0], b2[0]) > abx1 + best:
                continue
            if max(b1[1], b2[1]) < aby0 - best or min(b1[1], b2[1]) > aby1 + best:
                continue
            d = _seg_to_seg_dist(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1], b2[0], b2[1])
            if d < best:
                best = d
                if best <= 1e-6:
                    return 0.0
    return best


def check_inter_domain_polygon_clearances(pkg_polys: Sequence[PolygonIsland]) -> Dict[str, Any]:
    """Verify 0 diff-net polygon overlaps & exact min diff-net gap across all 24 inner layers."""
    by_lyr: Dict[str, List[Tuple[PolygonIsland, BBox]]] = collections.defaultdict(list)
    for isl in pkg_polys:
        if isl.net_name == "__ISOLATED__" or isl.layer.upper() == "SURFACE":
            continue
        by_lyr[isl.layer].append((isl, isl.bbox))

    overlap_cnt = 0
    under_gap_cnt = 0
    min_gap_um = 1e9
    samples: List[Dict[str, Any]] = []

    for lyr, items in by_lyr.items():
        req_gap = 67.5 if (lyr in CORE_PP_8_LAYERS or lyr in ("12F", "12B")) else 50.0
        items.sort(key=lambda t: t[1][0])
        n = len(items)
        for i in range(n):
            ia, ba = items[i]
            for j in range(i + 1, n):
                ib, bb = items[j]
                if bb[0] > ba[2] + req_gap + 1.0:
                    break
                if ia.net_name == ib.net_name:
                    continue
                if bb[1] > ba[3] + req_gap + 1.0 or bb[3] < ba[1] - req_gap - 1.0:
                    continue
                # Fast check if ib falls cleanly inside one of ia's voids (with >= 35 um BU void clearance)
                d = _poly_min_distance(ia.vertices, ib.vertices)
                if d <= 0.1 and (
                    any(all(point_in_poly(vx, vy, vd) and min_dist_to_poly_edges(vx, vy, vd) >= 35.0 for vx, vy in ib.vertices) for vd in ia.voids)
                    or any(all(point_in_poly(vx, vy, vd) and min_dist_to_poly_edges(vx, vy, vd) >= 35.0 for vx, vy in ia.vertices) for vd in ib.voids)
                ):
                    continue
                if d < min_gap_um:
                    min_gap_um = d
                if d <= 0.1:
                    overlap_cnt += 1
                    if len(samples) < 12:
                        samples.append({"layer": lyr, "a": f"{ia.net_name}({ia.tag})", "b": f"{ib.net_name}({ib.tag})", "gap_um": round(d, 2), "req_um": req_gap})
                elif d < req_gap - 1.0:
                    under_gap_cnt += 1
                    if len(samples) < 12:
                        samples.append({"layer": lyr, "a": f"{ia.net_name}({ia.tag})", "b": f"{ib.net_name}({ib.tag})", "gap_um": round(d, 2), "req_um": req_gap})

    return {
        "polygon_clearance_pass": (overlap_cnt == 0 and under_gap_cnt == 0),
        "diff_net_overlap_count": overlap_cnt,
        "diff_net_under_gap_count": under_gap_cnt,
        "min_diff_net_gap_um": round(min_gap_um if min_gap_um < 1e8 else 999.0, 2),
        "samples": samples,
    }


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_power_pins_by_refdes(pins_csv: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load target PDN pins (and C0/10F/SURFACE pins) grouped by RefDes cleanly."""
    grouped: Dict[str, List[Dict[str, str]]] = collections.defaultdict(list)
    with pins_csv.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n = r["net_name"].upper()
            if n == "VSS" or n.startswith(("VDDC", "VDDUC", "VDDCH", "VDD_0P8_SRAM", "VDDQ", "VDDQL", "VPP_", "VDD_0P75_HBMPHY")):
                grouped[r["refdes"]].append({
                    "refdes": r["refdes"],
                    "pin_number": r["pin_number"],
                    "x_um": r["x_um"],
                    "y_um": r["y_um"],
                    "net_name": r["net_name"],
                    "padstack_name": r["padstack_name"],
                    "start_layer": r["start_end"],
                })
    return grouped


# ---------------------------------------------------------------------------
# Site Descriptors Across ALL 3 Tasks (`4 LDA + 12 HBM + 4 LDB + 4 LDC`)
# ---------------------------------------------------------------------------
LDA_SITES: List[Dict[str, object]] = [
    {
        "refdes": "U9", "vddc": "VDDC0", "sram": "VDD_0P8_SRAM_CC0",
        "mode": "id", "cx": 0.0, "cy": 23914.005,
        "clip_main": (-16020.0, 15990.0, 16020.0, 31950.0),
        "bot_boxes": [(-16020.0, 16700.0, 16020.0, 32550.0), (-13500.0, 32550.0, 13500.0, 33280.0)],
        "edtc_refs": ["C2215", "C2216", "C2217", "C2218", "C2219", "C2220"],
        "vss_bga_bbox": (-15850.0, 16720.0, 15850.0, 32520.0),
        "emib_boxes": [ALL_EMIB_U25_TO_U40["U25"], ALL_EMIB_U25_TO_U40["U32"], ALL_EMIB_U25_TO_U40["U39"]],
    },
    {
        "refdes": "U12", "vddc": "VDDC1", "sram": "VDD_0P8_SRAM_CC1",
        "mode": "r180", "cx": 0.0, "cy": 7971.017,
        "clip_main": (-16020.0, 45.0, 16020.0, 15900.0),
        "bot_boxes": [(-16020.0, 45.0, 16020.0, 16600.0)],
        "edtc_refs": ["C2221", "C2222", "C2224", "C2225", "C2227", "C2228"],
        "vss_bga_bbox": (-15850.0, 100.0, 15850.0, 16550.0),
        "emib_boxes": [ALL_EMIB_U25_TO_U40["U29"], ALL_EMIB_U25_TO_U40["U28"]],
    },
    {
        "refdes": "U88", "vddc": "VDDC2", "sram": "VDD_0P8_SRAM_CC2",
        "mode": "id", "cx": 0.0, "cy": -7971.017,
        "clip_main": (-16020.0, -15900.0, 16020.0, -45.0),
        "bot_boxes": [(-16020.0, -17070.0, 16020.0, -45.0)],
        "edtc_refs": ["C2229", "C2230", "C2231", "C2232", "C2233", "C2234"],
        "vss_bga_bbox": (-15850.0, -17000.0, 15850.0, -100.0),
        "emib_boxes": [ALL_EMIB_U25_TO_U40["U26"], ALL_EMIB_U25_TO_U40["U31"]],
    },
    {
        "refdes": "U10", "vddc": "VDDC3", "sram": "VDD_0P8_SRAM_CC3",
        "mode": "r180", "cx": 0.0, "cy": -23914.005,
        "clip_main": (-16020.0, -31950.0, 16020.0, -15990.0),
        "bot_boxes": [(-16020.0, -33000.0, 16020.0, -17170.0), (-13500.0, -33730.0, 13500.0, -33000.0)],
        "edtc_refs": ["C2235", "C2236", "C2237", "C2240", "C2245", "C2246"],
        "vss_bga_bbox": (-15850.0, -32980.0, 15850.0, -17200.0),
        "emib_boxes": [ALL_EMIB_U25_TO_U40["U30"], ALL_EMIB_U25_TO_U40["U27"], ALL_EMIB_U25_TO_U40["U40"]],
    },
]

LDB_SITES: List[Dict[str, object]] = [
    {"refdes": "U7", "net": "VDDUC0", "bbox": ( 16120.0,    200.0,  27120.0,  31720.0), "edtc": ["C2238", "C2239", "C2209", "C2210"], "emib": ["U28", "U32", "U35", "U38"]},
    {"refdes": "U5", "net": "VDDUC1", "bbox": (-27120.0,    200.0, -16120.0,  31720.0), "edtc": ["C2223", "C2226", "C2207", "C2208"], "emib": ["U29", "U25", "U33", "U37"]},
    {"refdes": "U8", "net": "VDDUC2", "bbox": ( 16120.0, -31720.0,  27120.0,   -200.0), "edtc": ["C2241", "C2242", "C2211", "C2212"], "emib": ["U27", "U31", "U34", "U38"]},
    {"refdes": "U6", "net": "VDDUC3", "bbox": (-27120.0, -31720.0, -16120.0,   -200.0), "edtc": ["C2243", "C2244", "C2213", "C2214"], "emib": ["U30", "U26", "U36", "U37"]},
]

# LDC corner notches carve out HBM MEM5/0/8/9 corners (|X|>30050, |Y|<34850) & LDA 12B/11B crowns
LDC_SITES: List[Dict[str, object]] = [
    {
        "refdes": "U2", "net": "VDDCH0",
        "bbox": (250.0, 32060.0, 31150.0, 42520.0),
        "inner_notches": [(30050.0, 31900.0, 31200.0, 34850.0)],
        "bot_notches": [(0.0, 31900.0, 13600.0, 33380.0), (13600.0, 31900.0, 30050.0, 32650.0), (30050.0, 31900.0, 31200.0, 34850.0)],
        "edtc": ["C2277", "C2278"], "emib": ["U39", "U35"],
    },
    {
        "refdes": "U4", "net": "VDDCH1",
        "bbox": (250.0, -42520.0, 31150.0, -32060.0),
        "inner_notches": [(30050.0, -34850.0, 31200.0, -31900.0)],
        "bot_notches": [(0.0, -33830.0, 13600.0, -31900.0), (13600.0, -33100.0, 30050.0, -31900.0), (30050.0, -34850.0, 31200.0, -31900.0)],
        "edtc": ["C2271", "C2272"], "emib": ["U40", "U34"],
    },
    {
        "refdes": "U3", "net": "VDDCH2",
        "bbox": (-31150.0, -42520.0, -250.0, -32060.0),
        "inner_notches": [(-31200.0, -34850.0, -30050.0, -31900.0)],
        "bot_notches": [(-13600.0, -33830.0, 0.0, -31900.0), (-30050.0, -33100.0, -13600.0, -31900.0), (-31200.0, -34850.0, -30050.0, -31900.0)],
        "edtc": ["C2273", "C2274"], "emib": ["U40", "U36"],
    },
    {
        "refdes": "U1", "net": "VDDCH3",
        "bbox": (-31150.0, 32060.0, -250.0, 42520.0),
        "inner_notches": [(-31200.0, 31900.0, -30050.0, 34850.0)],
        "bot_notches": [(-13600.0, 31900.0, 0.0, 33380.0), (-30050.0, 31900.0, -13600.0, 32650.0), (-31200.0, 31900.0, -30050.0, 34850.0)],
        "edtc": ["C2275", "C2276"], "emib": ["U39", "U33"],
    },
]

# Variant A: U13/U41 MEM5 ref (`y_center=27352.5`); Variant B: U16/U44 MEMB ref (`y_center=-5202.5`)
HBM_SITES: List[Dict[str, object]] = [
    {"idx": "5", "variant": "A", "hbm": "U13", "emib": "U41", "ldb": "U5", "edtc": ["C2258", "C2257"], "mode": "id",   "dy":      0.0, "y_clip": ( 22480.0,  34750.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": (-30150.0,  31920.0, -27100.0,  34800.0), "phy_tab": True},
    {"idx": "4", "variant": "A", "hbm": "U14", "emib": "U42", "ldb": "U5", "edtc": ["C2256", "C2255"], "mode": "id",   "dy": -11075.0, "y_clip": ( 11380.0,  22390.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": None, "phy_tab": True},
    {"idx": "3", "variant": "A", "hbm": "U15", "emib": "U43", "ldb": "U5", "edtc": ["C2254", "C2253"], "mode": "id",   "dy": -22150.0, "y_clip": (    45.0,  11280.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": None, "phy_tab": True},
    {"idx": "6", "variant": "A", "hbm": "U22", "emib": "U50", "ldb": "U8", "edtc": ["C2260", "C2259"], "mode": "r180", "dy":  22150.0, "y_clip": (-11280.0,    -45.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": None, "phy_tab": False},
    {"idx": "7", "variant": "A", "hbm": "U23", "emib": "U51", "ldb": "U8", "edtc": ["C2262", "C2261"], "mode": "r180", "dy":  11075.0, "y_clip": (-22390.0, -11380.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": None, "phy_tab": False},
    {"idx": "8", "variant": "A", "hbm": "U24", "emib": "U52", "ldb": "U8", "edtc": ["C2264", "C2263"], "mode": "r180", "dy":      0.0, "y_clip": (-34750.0, -22480.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": ( 27100.0, -34800.0,  30150.0, -31920.0), "phy_tab": True},
    {"idx": "B", "variant": "B", "hbm": "U16", "emib": "U44", "ldb": "U6", "edtc": ["C2270", "C2269"], "mode": "id",   "dy":      0.0, "y_clip": (-11280.0,    -45.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": None, "phy_tab": False},
    {"idx": "A", "variant": "B", "hbm": "U17", "emib": "U45", "ldb": "U6", "edtc": ["C2268", "C2267"], "mode": "id",   "dy": -11075.0, "y_clip": (-22390.0, -11380.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": None, "phy_tab": False},
    {"idx": "9", "variant": "B", "hbm": "U18", "emib": "U46", "ldb": "U6", "edtc": ["C2266", "C2265"], "mode": "id",   "dy": -22150.0, "y_clip": (-34750.0, -22480.0), "x_clip": (-46150.0, -27220.0), "ldc_notch": (-30150.0, -34800.0, -27100.0, -31920.0), "phy_tab": True},
    {"idx": "2", "variant": "B", "hbm": "U21", "emib": "U49", "ldb": "U7", "edtc": ["C2252", "C2251"], "mode": "r180", "dy":      0.0, "y_clip": (    45.0,  11280.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": None, "phy_tab": True},
    {"idx": "1", "variant": "B", "hbm": "U20", "emib": "U48", "ldb": "U7", "edtc": ["C2250", "C2249"], "mode": "r180", "dy":  11075.0, "y_clip": ( 11380.0,  22390.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": None, "phy_tab": True},
    {"idx": "0", "variant": "B", "hbm": "U19", "emib": "U47", "ldb": "U7", "edtc": ["C2248", "C2247"], "mode": "r180", "dy":  22150.0, "y_clip": ( 22480.0,  34750.0), "x_clip": ( 27220.0,  46150.0), "ldc_notch": ( 27100.0,  31920.0,  30150.0,  34800.0), "phy_tab": True},
]


# ---------------------------------------------------------------------------
# Reference Transforms & Shared Helpers
# ---------------------------------------------------------------------------
def _make_lda_tf(mode: str, cx: float, cy: float) -> Callable[[float, float], Point]:
    ref_x, ref_y = 0.0, 23914.005
    if mode == "id":
        return lambda x, y: (round(cx + (x - ref_x), 3), round(cy + (y - ref_y), 3))
    return lambda x, y: (round(cx - (x - ref_x), 3), round(cy - (y - ref_y), 3))


def _make_hbm_tf(mode: str, dy: float) -> Callable[[float, float], Point]:
    if mode == "id":
        return lambda x, y: (round(x, 3), round(y + dy, 3))
    return lambda x, y: (round(-x, 3), round(-y + dy, 3))


def _group_vias_into_columns(vias: Sequence[ViaRecord]) -> List[Tuple[float, float, str, str, List[ViaRecord]]]:
    cols: Dict[Tuple[int, int, str], List[ViaRecord]] = collections.defaultdict(list)
    for v in vias:
        if "EDTC" in v.tag.upper():
            continue
        cols[(int(round(v.x * 100.0)), int(round(v.y * 100.0)), v.net_name)].append(v)
    return [(g[0].x, g[0].y, g[0].net_name, g[0].tag, g) for g in cols.values()]


# ---------------------------------------------------------------------------
# Unified HBM Variant A (`MEM5`) & Variant B (`MEMB`) Polygons + Routing
# ---------------------------------------------------------------------------
def _yflip_22150(x: float, y: float) -> Point:
    return (round(x, 3), round(-y + 22150.0, 3))


def _augment_hbm_polys_with_phy(
    base_polys: List[PolygonIsland],
    vddql_net: str,
    phy_net: str,
    variant: str,
    edtc_profiles: Dict[str, EdtcInstanceProfile],
) -> List[PolygonIsland]:
    """
    Split `[-32230..-26800]` cleanly into `vddql` (`X <= -30140`) + `HBMPHY` (`X >= -30050`),
    transforming to Variant B (`y -> -y + 22150`) and rebuilding real eDTC KOZs when needed.
    """
    # Cut VDDQL5 at X <= -30140.0 across full Y [22150..34850] so HBMPHY at X >= -30050.0 has an exact 90.0 um gap
    phy_strip_core_cut: BBox = (-30140.0, 22150.0, -26700.0, 34850.0)
    vddq_8f_trim: BBox = (-27680.0, 22150.0, -26700.0, 34850.0)  # carve East strip out of 8F VDDQ_CSB
    out_polys: List[PolygonIsland] = []

    for isl in base_polys:
        if "EDTC" in isl.tag or isl.net_name == "__ISOLATED__":
            if isl.layer == "10F":
                # Keep EMIB 10F Guard Ring (`U41` -> yflip onto `U44` in Variant B)
                verts = [_yflip_22150(x, y) for x, y in isl.vertices] if variant == "B" else list(isl.vertices)
                vds = [[_yflip_22150(x, y) for x, y in vd] for vd in isl.voids] if variant == "B" else list(isl.voids)
                tag = isl.tag.replace("U41", "U44") if variant == "B" else isl.tag
                out_polys.append(PolygonIsland(isl.layer, "__ISOLATED__", verts, voids=vds, tag=tag, is_dynamic=False))
            continue

        cur = isl
        if cur.layer == "8F" and cur.tag == "U13_8F_VDDQL5_E":
            continue  # Replaced by `8F_HBMPHY` (HBMPHY CSB trunks drop in [-27610..-26800])
        if cur.layer == "8F" and cur.tag == "U13_8F_VDDQ_CSB":
            cur = _subtract_boxes_from_island(cur, [vddq_8f_trim]) or cur
        if cur.layer == "8F" and cur.tag == "U13_8F_VDDC_SPINE_S":
            # Trim top of SPINE_S from 27568.0 to 27460.0 (98.0 um clear of U13_8F_VPP_MID_CAP [27558..27735])
            cur = PolygonIsland("8F", cur.net_name, rect_vertices((-33580.0, 24115.0, -33482.0, 27460.0)), tag=cur.tag, is_dynamic=True)
        if cur.layer in ("6F", "4FCO", "2FCI", "2BCI", "4BCO", "6B", "8B", "10B", "12B") and cur.net_name == "VDDQL5":
            cur = _subtract_boxes_from_island(cur, [phy_strip_core_cut]) or cur

        if variant == "B":
            # In Variant B (`U16/U44`), HBM die South protruding tail sits at [-10050..-9620] below U44_157 (-9594.1)
            verts_b = [_yflip_22150(x, y) for x, y in cur.vertices]
            net_b = cur.net_name.replace("MEM5", "MEMB").replace("VDDQL5", vddql_net)
            if cur.layer == "12F" and net_b.startswith("VDDC_"):
                verts_b = union_rect_boxes_to_polygons([
                    (-44580.0, -10950.0, -35950.0, -150.0),
                    (-44580.0, -10950.0, -31350.0, -9620.0),
                ])[0]
            elif cur.layer == "8F" and "VPP_COMB" in cur.tag:
                # South finger (-10030..-9660) catches U16 South VPP row while staying >= 50 um clear of U16_8F_VDDC_B2 (-11100..-10080)
                verts_b = [
                    (-46100.0, -150.0), (-44650.0, -150.0),
                    (-44650.0, -1330.0), (-31520.0, -1330.0), (-31520.0, -1570.0), (-44650.0, -1570.0),
                    (-44650.0, -9660.0), (-31350.0, -9660.0), (-31350.0, -10030.0), (-46100.0, -10030.0),
                ]
            elif cur.layer == "8F" and ("VDDC_B1" in cur.tag or "VDDQL5_W1" in cur.tag):
                # Trim South edge from -9750.0 to -9605.0 so it stays 55.0 um (>= 50.0 um BU gap) North of VPP_COMB South finger (-9660.0)
                cb_b = _poly_bbox(verts_b)
                verts_b = rect_vertices((cb_b[0], -9605.0, cb_b[2], cb_b[3]))
            vds_b: List[List[Point]] = []
            if cur.layer in ("4FCO", "4BCO", "2FCI", "2BCI", "3FCI", "1FCI", "1BCI", "3BCI"):
                real_k = [p.outer_core_plane_koz_bbox if cur.layer in ("4FCO", "4BCO") else p.inner_core_koz_bbox for p in edtc_profiles.values()]
                vds_b = [
                    rect_vertices(kb) for kb in real_k
                    if all(point_in_poly(vx, vy, verts_b) and min_dist_to_poly_edges(vx, vy, verts_b) >= 20.0 for vx, vy in rect_vertices(kb))
                ]
            else:
                vds_b = [[_yflip_22150(x, y) for x, y in vd] for vd in cur.voids]
            tag_b = cur.tag.replace("U13", "U16").replace("VDDQL5", vddql_net)
            out_polys.append(PolygonIsland(cur.layer, net_b, verts_b, voids=vds_b, tag=tag_b, is_dynamic=cur.is_dynamic))
        else:
            out_polys.append(cur)

    # Add HBMPHY island covering full extendable template envelope + Variant B core eDTC Guard Bands
    y_lo, y_hi = (-12550.0, -45.0) if variant == "B" else (22195.0, 34700.0)
    hb_tag = "U16" if variant == "B" else "U13"
    out_polys.append(make_plane_with_Notches_and_voids("8F", phy_net, (-27610.0, y_lo, -26800.0, y_hi), [], tag=f"{hb_tag}_8F_{phy_net}"))
    for lyr in ("6F", "4FCO", "2FCI", "2BCI", "4BCO", "6B", "8B", "10B", "12B"):
        out_polys.append(make_plane_with_Notches_and_voids(lyr, phy_net, (-30050.0, y_lo, -26800.0, y_hi), [], tag=f"{hb_tag}_{lyr}_{phy_net}"))
    if variant == "B":
        for lyr in ("4FCO", "4BCO"):
            for ep in edtc_profiles.values():
                out_polys.append(PolygonIsland(lyr, "__ISOLATED__", rect_vertices(ep.guard_outer_bbox), [rect_vertices(ep.cavity_bbox)], tag=f"EDTC_{lyr}_GUARD_BAND_{ep.refdes}", is_dynamic=False))
        # Update 8F VPP koz on U16_8F_VDDQ_CSB to match extended South VPP finger (-10030..-9660) with >= 50.0 um BU gap
        for i_p, p in enumerate(out_polys):
            if p.layer == "8F" and "VDDQ_CSB" in p.tag:
                out_polys[i_p] = _subtract_boxes_from_island(p, [expand_bbox((-44650.0, -10030.0, -31350.0, -9660.0), 52.0)]) or p
    return out_polys


def _route_hbm_variant_template(
    variant: str,
    hbm_ref: str,
    emib_ref: str,
    ldb_ref: str,
    edtc_refs: Sequence[str],
    rails: Dict[str, str],
    all_pwr_pins: Dict[str, List[Dict[str, str]]],
    edtc_pins: Sequence[Dict[str, str]],
    edtc_profiles: Dict[str, EdtcInstanceProfile],
) -> Tuple[List[PolygonIsland], List[ViaRecord], List[ClineRecord]]:
    """
    Build one canonical HBM Variant (`A` for `U13/U41/U5`, `B` for `U16/U44/U6`) with
    all real `C0`, `10F CSB`, `HBMPHY_UC*`, `SURFACE` gang-bars, `eDTC`, `Core PTH`, and `9F->5F`/`9B->5B`.
    """
    vddq_n, vddc_n, vddql_n, vpp_n, phy_n = rails["vddq"], rails["vddc"], rails["vddql"], rails["vpp"], rails["phy"]
    u13_base_polys = build_u13_hbm_27layer_polygons(edtc_profiles=edtc_profiles if variant == "A" else None)
    polys = _augment_hbm_polys_with_phy(u13_base_polys, vddql_n, phy_n, variant, edtc_profiles)
    own = MultiRailLayerOwnershipIndex(polys)
    vias: List[ViaRecord] = []
    clines: List[ClineRecord] = []
    grid = FastXYClearanceGrid(cell_um=220.0)

    emib_box: BBox = U41_EMIB_BBOX if variant == "A" else (-35738.9, -9436.6, -27112.9, -968.3)
    emib_157 = expand_bbox(emib_box, 157.5)
    dom_box: BBox = U13_DOMAIN_BBOX if variant == "A" else (-46150.0, -11280.0, -26700.0, -45.0)
    y_fn = (lambda y: y) if variant == "A" else (lambda y: round(-y + 22150.0, 3))

    # 1. Real eDTC concentric stacks (`C2258/2257` or `C2270/2269`)
    hbm_pwr = (vddq_n, vddc_n, vddql_n, vpp_n, phy_n)
    synthesize_concentric_edtc_stacks(edtc_pins, edtc_refs, list(hbm_pwr) + ["VSS"], own, vias, grid)

    # 2. EMIB `C0` (`HBM + LDB` including `HBMPHY_UC*`) + `10F CSB` (`EMIB` all rails)
    ov_hbm = {("SURFACE", "C0"): "VU30_19_60_SURFACE_C0_01B"}
    ov_ldb = {("SURFACE", "C0"): "VU30_19_39_SURFACE_C0_01B"}
    hbm_c0_nets = {vddq_n, vddc_n, vddql_n, vpp_n, "VSS"}
    ldb_c0_nets = {vddq_n, vddql_n, phy_n, "VSS"}
    ex0, ey0, ex1, ey1 = emib_box

    for r in all_pwr_pins.get(hbm_ref, ()):
        if "SURFACE" in r["start_layer"] and r["net_name"] in hbm_c0_nets:
            x, y = float(r["x_um"]), float(r["y_um"])
            if ex0 <= x <= ex1 and ey0 <= y <= ey1:
                insert_via_stack_zero_overlap(vias, grid, r["net_name"], [("SURFACE", "C0")], x, y, f"{hbm_ref}_EMIB_C0_{r['net_name']}", ov_hbm)
    for r in all_pwr_pins.get(ldb_ref, ()):
        if "SURFACE" in r["start_layer"] and r["net_name"] in ldb_c0_nets:
            x, y = float(r["x_um"]), float(r["y_um"])
            if ex0 <= x <= ex1 and ey0 <= y <= ey1:
                insert_via_stack_zero_overlap(vias, grid, r["net_name"], [("SURFACE", "C0")], x, y, f"{ldb_ref}_EMIB_C0_{r['net_name']}", ov_ldb)

    obs_9f = FastXYClearanceGrid(cell_um=160.0)
    csb_by_net: Dict[str, List[Tuple[float, float]]] = collections.defaultdict(list)
    for r in all_pwr_pins.get(emib_ref, ()):
        if "10F" in r["start_layer"] and r["net_name"] in (set(hbm_pwr) | {"VSS"}):
            csb_by_net[r["net_name"]].append((float(r["x_um"]), float(r["y_um"])))

    for cx, cy in csb_by_net["VSS"]:
        if insert_via_stack_zero_overlap(vias, grid, "VSS", [("10F", "9F")], cx, cy, f"{emib_ref}_CSB_VSS_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, "VSS")

    for net in (vddq_n, vpp_n):
        for cx, cy in csb_by_net[net]:
            if insert_via_stack_zero_overlap(vias, grid, net, [("10F", "9F"), ("9F", "8F")], cx, cy, f"{emib_ref}_CSB_{net}_2STACK") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 45.0, net)

    # 8F->6F VDDQ trunk + Mid VPP capsule + 7F bus
    for sy in range(28150, 33050, 320):
        insert_via_stack_zero_overlap(vias, grid, vddq_n, [("8F", "7F"), ("7F", "6F")], -35670.0, y_fn(float(sy)), f"{hbm_ref}_8F_6F_{vddq_n}_TRUNK")
    for jx in (-32169.595, -32797.961):
        clines.append(ClineRecord(vddq_n, "8F", 30.0, jx, y_fn(23504.143), jx, y_fn(23310.0), f"{emib_ref}_VDDQ_8F_S_BR"))
    for jx in (-33740.504, -33321.593, -33112.138):
        clines.append(ClineRecord(vddq_n, "8F", 30.0, jx, y_fn(27522.746), jx, y_fn(27330.0), f"{emib_ref}_VDDQ_8F_M_BR"))
    clines.append(ClineRecord(vddq_n, "8F", 30.0, -33112.138, y_fn(27687.499), -32902.683, y_fn(27687.499), f"{emib_ref}_VDDQ_8F_E_BR"))

    insert_via_stack_zero_overlap(vias, grid, vpp_n, [("8F", "7F")], -33478.0, y_fn(27646.0), f"{emib_ref}_VPP_MID_8F_7F")
    for p1x, p1y, p2x, p2y, tg in [
        (-33635.782, 27605.123, -33478.0, 27646.0, "CA"),
        (-33321.593, 27687.499, -33478.0, 27646.0, "CB"),
        (-33740.504, 27687.499, -33635.782, 27605.123, "CC"),
        (-33321.593, 27687.499, -33216.872, 27605.123, "CD"),
    ]:
        clines.append(ClineRecord(vpp_n, "8F", 24.0, p1x, y_fn(p1y), p2x, y_fn(p2y), f"{emib_ref}_VPP_{tg}"))
    clines.append(ClineRecord(vpp_n, "7F", 30.0, -45200.0, y_fn(27646.0), -33478.0, y_fn(27646.0), f"{hbm_ref}_VPP_MID_7F_BUS"))
    for vx_w in (-45200.0, -44980.0, -44760.0):
        insert_via_stack_zero_overlap(vias, grid, vpp_n, [("7F", "6F")], vx_w, y_fn(27646.0), f"{hbm_ref}_VPP_7F_6F")
    for vy_12 in range(22800, 31900, 750):
        insert_via_stack_zero_overlap(vias, grid, vpp_n, [("12F", "11F"), ("11F", "10F"), ("10F", "9F"), ("9F", "8F")], -45400.0, y_fn(float(vy_12)), f"{hbm_ref}_12F_8F_VPP")

    # VDDC CSBs (spine + outer S/N + mid BFS)
    y_bus_s = y_fn(23080.0)
    outer_vddc_pts: List[Tuple[float, float]] = []
    mid_vddc_pts: List[Tuple[float, float]] = []
    lo_s_band = (lambda y: y <= 23560.0) if variant == "A" else (lambda y: y >= y_fn(23560.0))
    for cx, cy in csb_by_net[vddc_n]:
        cy_ref = cy if variant == "A" else (22150.0 - cy)
        if abs(cx - (-33531.05)) < 25.0 and ((24115.0 <= cy_ref <= 27460.0) or (27805.0 <= cy_ref <= 31260.0)):
            if insert_via_stack_zero_overlap(vias, grid, vddc_n, [("10F", "9F"), ("9F", "8F")], cx, cy, f"{emib_ref}_CSB_VDDC_SPINE") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 45.0, vddc_n)
        elif insert_via_stack_zero_overlap(vias, grid, vddc_n, [("10F", "9F")], cx, cy, f"{emib_ref}_CSB_VDDC_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, vddc_n)
            if lo_s_band(cy):
                clines.append(ClineRecord(vddc_n, "9F", 24.0, round(cx, 3), round(cy, 3), round(cx, 3), y_bus_s, f"{emib_ref}_VDDC_9F_STUB"))
                outer_vddc_pts.append((cx, cy))
            else:
                mid_vddc_pts.append((cx, cy))

    if outer_vddc_pts:
        clines.append(ClineRecord(vddc_n, "9F", 40.0, -41000.0, y_bus_s, round(max(p[0] for p in outer_vddc_pts), 3), y_bus_s, f"{emib_ref}_VDDC_9F_S_BUS"))
    for tx in (-41000.0, -40700.0, -40400.0, -40100.0, -39800.0, -39500.0):
        for ty_r in (23120.0, 23420.0, 27140.0, 27290.0):
            insert_via_stack_zero_overlap(vias, grid, vddc_n, [("9F", "8F"), ("8F", "7F"), ("7F", "6F")], tx, y_fn(ty_r), f"{hbm_ref}_9F_6F_VDDC_TRUNK")
    for my_r in (24365.0, 24722.0, 25079.0, 25463.3, 25847.8, 26232.2, 26589.2, 26946.1, 27330.5, 28044.5, 28428.9, 28785.9, 29142.8, 29527.2, 29911.7, 30296.1, 30653.0, 31010.0):
        insert_via_stack_zero_overlap(vias, grid, vddc_n, [("8F", "7F")], -33531.05, y_fn(my_r), f"{hbm_ref}_8F_7F_VDDC_SPINE")
    for fx in (-40400.0, -40050.0, -39700.0, -39350.0, -39000.0, -38650.0, -38300.0):
        insert_via_stack_zero_overlap(vias, grid, vddc_n, [("7F", "6F")], fx, y_fn(22700.0), f"{hbm_ref}_7F_6F_VDDC_S")
    for fnx in (-43700.0, -43450.0, -43200.0, -42980.0):
        insert_via_stack_zero_overlap(vias, grid, vddc_n, [("7F", "6F")], fnx, y_fn(32170.0), f"{hbm_ref}_7F_6F_VDDC_N")

    # 3. HBMPHY_UC* CSBs (X >= -27595 -> 2-stack onto 8F_HBMPHY; X < -27595 -> 1-stack 10F->9F + 9F East escape into [-27540..-26880])
    sp_9_6 = [("9F", "8F"), ("8F", "7F"), ("7F", "6F")]
    phy_anchors: List[Tuple[float, float]] = []
    phy_unanch: List[Tuple[float, float]] = []
    for ey in range(int(round(ey0 + 180.0)), int(round(ey1 - 150.0)), 360):
        for ex in (-27510.0, -27150.0):
            if own.owner_at("6F", ex, float(ey), 35.0) == phy_n and not obs_9f.has_conflict("PAD_9F", ex, float(ey), 45.0, phy_n, 18.5, 18.5):
                if insert_via_stack_zero_overlap(vias, grid, phy_n, sp_9_6, ex, float(ey), f"{emib_ref}_CSB_{phy_n}_TRUNK") > 0:
                    obs_9f.insert("PAD_9F", ex, float(ey), 45.0, phy_n)
                    phy_anchors.append((ex, float(ey)))
    for cx, cy in sorted(csb_by_net[phy_n], key=lambda p: (-p[0], p[1])):
        if cx >= -27575.0 and own.owner_at("8F", cx, cy, 30.0) == phy_n:
            if insert_via_stack_zero_overlap(vias, grid, phy_n, [("10F", "9F"), ("9F", "8F")], cx, cy, f"{emib_ref}_CSB_{phy_n}_2STACK") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 45.0, phy_n)
                phy_anchors.append((cx, cy))
                continue
        if insert_via_stack_zero_overlap(vias, grid, phy_n, [("10F", "9F")], cx, cy, f"{emib_ref}_CSB_{phy_n}_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, phy_n)
            phy_unanch.append((cx, cy))

    # 4. VDDQL CSBs (10F->9F 1-stack + 9F escape West/South into 6F_VDDQL <= -30140)
    ql_anchors: List[Tuple[float, float]] = []
    ql_unanch: List[Tuple[float, float]] = []
    for ty in range(int(round(min(y_fn(22650.0), y_fn(31500.0)) + 150.0)), int(round(max(y_fn(22650.0), y_fn(31500.0)))), 360):
        for tx in (-30260.0, -35670.0):
            if own.owner_at("6F", tx, float(ty), 40.0) == vddql_n and not obs_9f.has_conflict("PAD_9F", tx, float(ty), 45.0, vddql_n, 18.5, 18.5):
                if insert_via_stack_zero_overlap(vias, grid, vddql_n, sp_9_6, tx, float(ty), f"{emib_ref}_CSB_{vddql_n}_TRUNK") > 0:
                    obs_9f.insert("PAD_9F", tx, float(ty), 45.0, vddql_n)
                    ql_anchors.append((tx, float(ty)))
    for cx, cy in sorted(csb_by_net[vddql_n], key=lambda p: (p[0], p[1])):
        if insert_via_stack_zero_overlap(vias, grid, vddql_n, [("10F", "9F")], cx, cy, f"{emib_ref}_CSB_{vddql_n}_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, vddql_n)
            ql_unanch.append((cx, cy))

    def _connect_9f_forest(net_name: str, pending: List[Tuple[float, float]], anchors: List[Tuple[float, float]], allow_trunk_6f: bool, tag_pfx: str) -> None:
        cand_offs = [(round(rd * math.cos(math.radians(a)), 2), round(rd * math.sin(math.radians(a)), 2)) for rd in (112.0, 145.0, 185.0) for a in range(0, 360, 20)]
        rem = list(pending)
        if allow_trunk_6f:
            still: List[Tuple[float, float]] = []
            for cx, cy in rem:
                linked = False
                for ax, ay in reversed(anchors[-24:]):
                    if math.hypot(ax - cx, ay - cy) <= 260.0 and _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, ax, ay, 12.0, net_name, 15.0) and _segment_clear_of_layer_clines(clines, "9F", cx, cy, ax, ay, 12.0, net_name, 15.0):
                        clines.append(ClineRecord(net_name, "9F", 24.0, round(cx, 3), round(cy, 3), round(ax, 3), round(ay, 3), f"{tag_pfx}_G9F"))
                        anchors.append((cx, cy))
                        linked = True
                        break
                if linked:
                    continue
                placed = False
                for dx, dy in cand_offs:
                    sx, sy = cx + dx, cy + dy
                    if own.owner_at("6F", sx, sy, 45.0) != net_name or own.owner_at("9F", sx, sy, 45.0) != "VSS":
                        continue
                    if obs_9f.has_conflict("PAD_9F", sx, sy, 45.0, net_name, 18.5, 18.5):
                        continue
                    if _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, sx, sy, 12.0, net_name, 15.0) and _segment_clear_of_layer_clines(clines, "9F", cx, cy, sx, sy, 12.0, net_name, 15.0):
                        if insert_via_stack_zero_overlap(vias, grid, net_name, sp_9_6, sx, sy, f"{tag_pfx}_9F_6F") > 0:
                            obs_9f.insert("PAD_9F", sx, sy, 45.0, net_name)
                            clines.append(ClineRecord(net_name, "9F", 24.0, round(cx, 3), round(cy, 3), round(sx, 3), round(sy, 3), f"{tag_pfx}_S9F"))
                            anchors.extend([(sx, sy), (cx, cy)])
                            placed = True
                            break
                if not placed:
                    still.append((cx, cy))
            rem = still
        for _ in range(5):
            if not rem:
                break
            nxt_rem: List[Tuple[float, float]] = []
            prog = False
            for cx, cy in rem:
                best_d: Optional[Tuple[float, float, float]] = None
                best_j: Optional[Tuple[float, float, float, float, float]] = None
                for ax, ay in anchors:
                    d = math.hypot(ax - cx, ay - cy)
                    if d > 720.0:
                        continue
                    if best_d is None or d < best_d[0]:
                        if _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, ax, ay, 9.0, net_name, 15.0) and _segment_clear_of_layer_clines(clines, "9F", cx, cy, ax, ay, 9.0, net_name, 15.0):
                            best_d = (d, ax, ay)
                    elif best_d is None and (best_j is None or d < best_j[0]):
                        for mx, my in ((cx, ay), (ax, cy)):
                            if own.owner_at("9F", mx, my, 25.0) == "VSS" and _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, mx, my, 9.0, net_name, 15.0) and _segment_clear_of_obs(obs_9f, "PAD_9F", mx, my, ax, ay, 9.0, net_name, 15.0) and _segment_clear_of_layer_clines(clines, "9F", cx, cy, mx, my, 9.0, net_name, 15.0) and _segment_clear_of_layer_clines(clines, "9F", mx, my, ax, ay, 9.0, net_name, 15.0):
                                best_j = (d, mx, my, ax, ay)
                                break
                if best_d is not None:
                    clines.append(ClineRecord(net_name, "9F", 18.0, round(cx, 3), round(cy, 3), round(best_d[1], 3), round(best_d[2], 3), f"{tag_pfx}_L9F"))
                    anchors.append((cx, cy))
                    prog = True
                elif best_j is not None:
                    _, mx, my, ax, ay = best_j
                    clines.append(ClineRecord(net_name, "9F", 18.0, round(cx, 3), round(cy, 3), round(mx, 3), round(my, 3), f"{tag_pfx}_JA"))
                    clines.append(ClineRecord(net_name, "9F", 18.0, round(mx, 3), round(my, 3), round(ax, 3), round(ay, 3), f"{tag_pfx}_JB"))
                    anchors.append((cx, cy))
                    prog = True
                else:
                    nxt_rem.append((cx, cy))
            rem = nxt_rem
            if not prog:
                break

    _connect_9f_forest(phy_n, phy_unanch, phy_anchors, True, f"{emib_ref}_PHY")
    _connect_9f_forest(vddql_n, ql_unanch, ql_anchors, True, f"{emib_ref}_QL")

    # Mid VDDC 9F BFS tree (`y_ref in [27090..27990]` mapped to y_fn)
    if mid_vddc_pts:
        y9_lo, y9_hi = (27090.0, 27990.0) if variant == "A" else (y_fn(27990.0), y_fn(27090.0))
        y9_root = y_fn(27220.0)
        for c9 in clines:
            if c9.layer == "9F" and c9.net_name != vddc_n and max(c9.y1, c9.y2) >= y9_lo - 100.0 and min(c9.y1, c9.y2) <= y9_hi + 100.0:
                ln_c = math.hypot(c9.x2 - c9.x1, c9.y2 - c9.y1)
                n_st = max(1, int(math.ceil(ln_c / 14.0)))
                for ks in range(n_st + 1):
                    ts = ks / n_st
                    obs_9f.insert("PAD_9F", c9.x1 + ts * (c9.x2 - c9.x1), c9.y1 + ts * (c9.y2 - c9.y1), 0.5 * c9.width_um, c9.net_name)
        step_g = 15.0
        root_g = (int(round(-35670.0 / step_g)), int(round(y9_root / step_g)))
        parent_g: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {root_g: None}
        qg = collections.deque([root_g])
        while qg:
            gx, gy = qg.popleft()
            for dx_i, dy_i in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                nx, ny = gx + dx_i, gy + dy_i
                rx, ry = nx * step_g, ny * step_g
                if -35720.0 <= rx <= -31380.0 and y9_lo <= ry <= y9_hi and (nx, ny) not in parent_g:
                    mx_h, my_h = (gx + 0.5 * dx_i) * step_g, (gy + 0.5 * dy_i) * step_g
                    if not obs_9f.has_conflict("PAD_9F", rx, ry, 7.5, vddc_n, -100.0, 15.0) and not obs_9f.has_conflict("PAD_9F", mx_h, my_h, 7.5, vddc_n, -100.0, 15.0):
                        parent_g[(nx, ny)] = (gx, gy)
                        qg.append((nx, ny))
        drawn_e: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
        for vx, vy in mid_vddc_pts:
            near = [g for g in parent_g if abs(g[0] * step_g - vx) <= 22.0 and abs(g[1] * step_g - vy) <= 22.0]
            if near:
                bg = min(near, key=lambda g: math.hypot(g[0] * step_g - vx, g[1] * step_g - vy))
                clines.append(ClineRecord(vddc_n, "9F", 15.0, round(vx, 3), round(vy, 3), round(bg[0] * step_g, 3), round(bg[1] * step_g, 3), f"{emib_ref}_VDDC_M9_TAP"))
                cur_n: Optional[Tuple[int, int]] = bg
                while cur_n is not None and parent_g[cur_n] is not None:
                    prv_n = parent_g[cur_n]
                    assert prv_n is not None
                    ek = (min(cur_n, prv_n), max(cur_n, prv_n))
                    if ek not in drawn_e:
                        drawn_e.add(ek)
                        xa, ya = cur_n[0] * step_g, cur_n[1] * step_g
                        xb, yb = prv_n[0] * step_g, prv_n[1] * step_g
                        clines.append(ClineRecord(vddc_n, "9F", 15.0, round(xa, 3), round(ya, 3), round(xb, 3), round(yb, 3), f"{emib_ref}_VDDC_M9_TR"))
                    cur_n = prv_n
        clines.append(ClineRecord(vddc_n, "9F", 30.0, -41000.0, y9_root, -35670.0, y9_root, f"{emib_ref}_VDDC_M9_WEST"))

    # 5. Core PTH (`4FCO->4BCO` + `5F->4FCO`/`4BCO->5B` + `6F/6B` including HBMPHY_UC*!) & `8F->6F` + `9F->5F`/`9B->5B` BU stitches
    for sx in (-37500.0, -37100.0, -36700.0, -36300.0, -35980.0):
        for sy_r in (22500.0, 22950.0, 24000.0, 25200.0, 26400.0, 27600.0):
            insert_via_stack_zero_overlap(vias, grid, vddql_n, [("8F", "7F"), ("7F", "6F")], sx, y_fn(sy_r), f"{hbm_ref}_8F_6F_{vddql_n}_W")

    synthesize_multi_rail_core_pth_and_pp(
        dom_box, hbm_pwr, own, {k: edtc_profiles[k].die_bbox for k in edtc_refs},
        {emib_ref: emib_box}, vias, grid, pth_pitch_x_um=460.0, pth_pitch_y_um=430.0,
        tag_prefix=hbm_ref, edtc_profiles=edtc_profiles,
    )
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(dom_box, hbm_pwr, own, vias, grid, pitch_um=235.0, tag_prefix=f"{hbm_ref}_MID")

    # 6. Real HBM West / Protruding SURFACE gang-bars (`U13` or `U16`) + drops (`SURFACE -> 12F..8F`)
    bump_obs = FastXYClearanceGrid(cell_um=120.0)
    west_by_net_row: Dict[Tuple[str, float], List[float]] = collections.defaultdict(list)
    hbm_surf_set = set(hbm_pwr) | {"VSS"}
    for r in all_pwr_pins.get(hbm_ref, ()):
        if "SURFACE" not in r["start_layer"]:
            continue
        net, x, y = r["net_name"], float(r["x_um"]), float(r["y_um"])
        bump_obs.insert("HBM_SURF", x, y, 10.5, net)
        if net in hbm_surf_set and not (ex0 <= x <= ex1 and ey0 <= y <= ey1):
            west_by_net_row[(net, round(y, 1))].append(x)

    tail_y_thresh = 31750.0 if variant == "A" else -9594.0
    for net in (vddc_n, vddq_n, "VSS", vddql_n, vpp_n):
        net_ys = sorted(ry for (n, ry) in west_by_net_row if n == net)
        used_ys: Set[float] = set()
        anchored_pts: List[Tuple[float, float]] = []
        unanch_bars: List[Tuple[float, float, float]] = []
        for idx, y1 in enumerate(net_ys):
            if y1 in used_ys:
                continue
            paired_y2: Optional[float] = None
            if idx + 1 < len(net_ys) and 50.0 <= (net_ys[idx + 1] - y1) <= 58.0:
                paired_y2 = net_ys[idx + 1]
                used_ys.add(paired_y2)
            used_ys.add(y1)
            xs_m = sorted(set(west_by_net_row[(net, y1)] + (west_by_net_row[(net, paired_y2)] if paired_y2 else [])))
            y_mid = round(0.5 * (y1 + paired_y2), 3) if paired_y2 is not None else y1
            bh = 42.0 if paired_y2 is not None else 15.0

            runs: List[List[float]] = []
            cur_r: List[float] = []
            for xv in xs_m:
                if not cur_r or ((xv - cur_r[-1]) <= 125.0 and not bump_obs.has_conflict("HBM_SURF", 0.5 * (cur_r[-1] + xv), y_mid, bh, net, -100.0, 18.5)):
                    cur_r.append(xv)
                else:
                    runs.append(cur_r)
                    cur_r = [xv]
            if cur_r:
                runs.append(cur_r)

            for r_xs in runs:
                rx0, rx1 = min(r_xs) - 14.0, max(r_xs) + 14.0
                polys.append(PolygonIsland("SURFACE", net, rect_vertices((rx0, y_mid - bh, rx1, y_mid + bh)), tag=f"{hbm_ref}_GANG_{net}", is_dynamic=False))
                bar_drops = 0
                last_vx = -1e9
                for xv in r_xs:
                    if _point_in_any_box(xv, y_mid, [emib_157]) or xv - last_vx < 220.0:
                        continue
                    if bump_obs.has_conflict("HBM_SURF", xv, y_mid, 38.5, net, -100.0, 18.5):
                        continue
                    if _drop_from_surface_atomic(xv, y_mid, net, own, vias, grid, f"{hbm_ref}_WEST_{net}", max_spans=6) > 0:
                        bump_obs.insert("HBM_SURF", xv, y_mid, 38.5, net)
                        last_vx = xv
                        bar_drops += 1
                        anchored_pts.append((xv, y_mid))
                if bar_drops == 0:
                    sx_scan = rx0 + 10.0
                    while sx_scan <= rx1 - 10.0:
                        if not _point_in_any_box(sx_scan, y_mid, [emib_157]) and not bump_obs.has_conflict("HBM_SURF", sx_scan, y_mid, 38.5, net, -100.0, 18.0):
                            if _drop_from_surface_atomic(sx_scan, y_mid, net, own, vias, grid, f"{hbm_ref}_FB_{net}", max_spans=6) > 0:
                                bump_obs.insert("HBM_SURF", sx_scan, y_mid, 38.5, net)
                                bar_drops += 1
                                anchored_pts.append((sx_scan, y_mid))
                                break
                        sx_scan += 18.0
                if bar_drops == 0 and ((variant == "A" and y_mid >= tail_y_thresh) or (variant == "B" and y_mid <= tail_y_thresh)):
                    dog_ys = (32020.0, 32090.0, 32145.0) if variant == "A" else (-9680.0, -9820.0, -9960.0)
                    for xv in r_xs:
                        if bar_drops > 0:
                            break
                        for dx_n in (0.0, 32.5, -32.5):
                            txn = xv + dx_n
                            if not (rx0 + 4.0 <= txn <= rx1 - 4.0):
                                continue
                            for tyn in dog_ys:
                                if not bump_obs.has_conflict("HBM_SURF", txn, tyn, 38.5, net, -100.0, 18.0) and _segment_clear_of_obs(bump_obs, "HBM_SURF", txn, y_mid, txn, tyn, 6.0, net, 14.5) and _segment_clear_of_layer_clines(clines, "SURFACE", txn, y_mid, txn, tyn, 6.0, net, 14.5):
                                    if _drop_from_surface_atomic(txn, tyn, net, own, vias, grid, f"{hbm_ref}_DOG_{net}", max_spans=6) > 0:
                                        bump_obs.insert("HBM_SURF", txn, tyn, 38.5, net)
                                        clines.append(ClineRecord(net, "SURFACE", 12.0, round(txn, 3), round(y_mid, 3), round(txn, 3), round(tyn, 3), f"{hbm_ref}_STRAP_{net}"))
                                        bar_drops += 1
                                        anchored_pts.extend([(txn, y_mid), (txn, tyn)])
                                        break
                if bar_drops == 0:
                    unanch_bars.append((rx0, rx1, y_mid))
        for _ in range(4):
            rem_b: List[Tuple[float, float, float]] = []
            prog_b = False
            for rx0, rx1, ym in unanch_bars:
                bx = 0.5 * (rx0 + rx1)
                best_b = None
                for ax, ay in anchored_pts:
                    d = math.hypot(ax - bx, ay - ym)
                    if d <= 950.0 and (best_b is None or d < best_b[0]) and _segment_clear_of_obs(bump_obs, "HBM_SURF", bx, ym, ax, ay, 8.0, net, 15.0) and _segment_clear_of_layer_clines(clines, "SURFACE", bx, ym, ax, ay, 8.0, net, 15.0):
                        best_b = (d, ax, ay)
                if best_b is not None:
                    clines.append(ClineRecord(net, "SURFACE", 16.0, round(bx, 3), round(ym, 3), round(best_b[1], 3), round(best_b[2], 3), f"{hbm_ref}_BSTRAP_{net}"))
                    anchored_pts.append((bx, ym))
                    prog_b = True
                else:
                    rem_b.append((rx0, rx1, ym))
            unanch_bars = rem_b
            if not unanch_bars or not prog_b:
                break

    return polys, vias, clines


# ---------------------------------------------------------------------------
# LDB/LDC Full VIA + Collar Straps + Global U25..U40 EMIB C0/CSB + U98
# ---------------------------------------------------------------------------
def _route_global_emib_u25_to_u40(
    all_pwr_pins: Dict[str, List[Dict[str, str]]],
    pkg_own: MultiRailLayerOwnershipIndex,
    pkg_vias: List[ViaRecord],
    pkg_grid: FastXYClearanceGrid,
) -> Dict[str, int]:
    """Connect 100% of U25..U40 EMIB `C0` microbumps (`U1..U12, U88`) & `10F` `VSS` CSBs deduplicated in `pkg_grid`."""
    stats = {"emib_u25_u40_c0": 0, "emib_u25_u40_csb_10f": 0}
    emib_boxes = list(ALL_EMIB_U25_TO_U40.values())
    ov_lda = {("SURFACE", "C0"): "VU30_19_60_SURFACE_C0_01B"}
    ov_ldb = {("SURFACE", "C0"): "VU30_19_39_SURFACE_C0_01B"}

    for die_ref in ("U1","U2","U3","U4","U5","U6","U7","U8","U9","U10","U12","U88"):
        ov = ov_lda if die_ref in ("U9", "U10", "U12", "U88") else ov_ldb
        for r in all_pwr_pins.get(die_ref, ()):
            if r["net_name"] != "VSS" or "SURFACE" not in r["start_layer"]:
                continue
            x, y = float(r["x_um"]), float(r["y_um"])
            if _point_in_any_box(x, y, emib_boxes):
                if insert_via_stack_zero_overlap(pkg_vias, pkg_grid, "VSS", [("SURFACE", "C0")], x, y, f"{die_ref}_EMIB_C0_VSS", ov) > 0:
                    stats["emib_u25_u40_c0"] += 1

    for eref in sorted(ALL_EMIB_U25_TO_U40):
        for r in all_pwr_pins.get(eref, ()):
            if r["net_name"] == "VSS" and "10F" in r["start_layer"]:
                x, y = float(r["x_um"]), float(r["y_um"])
                if pkg_own.owner_at("9F", x, y, min_edge_margin_um=20.0) == "VSS":
                    if insert_via_stack_zero_overlap(pkg_vias, pkg_grid, "VSS", [("10F", "9F")], x, y, f"{eref}_CSB_VSS_10F_9F") > 0:
                        stats["emib_u25_u40_csb_10f"] += 1
    return stats


def _route_ldb_ldc_full_via_and_collar(
    domain_tag: str,
    target_net: str,
    bump_rows: Sequence[Dict[str, str]],
    emib_157_boxes: Sequence[BBox],
    emib_die_boxes: Sequence[BBox],
    own: MultiRailLayerOwnershipIndex,
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
    grid: FastXYClearanceGrid,
) -> Dict[str, int]:
    """Route 100% `FULL VIA` (`via_stride=1`) on LDB/LDC outside EMIB KOZs + collar straps for collar `VSS` bumps."""
    allowed = {target_net, "VSS"}
    placed = collections.Counter()
    seen: Set[Tuple[int, int]] = set()
    collar_vss: List[Tuple[float, float]] = []
    anchored_vss: List[Tuple[float, float]] = []
    bump_obs = FastXYClearanceGrid(cell_um=140.0)
    upper_chain = [("SURFACE", "12F"), ("12F", "11F"), ("11F", "10F"), ("10F", "9F"), ("9F", "8F")]

    cands: List[Tuple[float, float, str]] = []
    for r in bump_rows:
        net = r["net_name"]
        if net not in allowed or "SURFACE" not in r["start_layer"].upper():
            continue
        x, y = float(r["x_um"]), float(r["y_um"])
        k = (int(round(x * 10.0)), int(round(y * 10.0)))
        if k in seen:
            continue
        seen.add(k)
        bump_obs.insert("LDB_SURF", x, y, 10.5, net)
        if net == "VSS" and _point_in_any_box(x, y, emib_die_boxes):
            continue  # Routed by C0 EMIB router
        cands.append((x, y, net))

    for x, y, net in cands:
        if _point_in_any_box(x, y, emib_157_boxes):
            if net == "VSS":
                collar_vss.append((x, y))
            continue
        col_spans: List[Tuple[str, str]] = []
        best_prefix: List[Tuple[str, str]] = []
        for s_l, e_l in upper_chain:
            col_spans.append((s_l, e_l))
            if own.owner_at(e_l, x, y, min_edge_margin_um=25.0) == net:
                best_prefix = list(col_spans)
        if best_prefix and insert_via_stack_zero_overlap(vias_out, grid, net, best_prefix, x, y, f"{domain_tag}_VIA") > 0:
            placed[net] += 1
            if net == "VSS":
                anchored_vss.append((x, y))

    # Strap EMIB collar VSS bumps cleanly to nearby anchored VSS drops
    if collar_vss and anchored_vss:
        anc_grid = FastXYClearanceGrid(cell_um=450.0)
        for ax, ay in anchored_vss:
            anc_grid.insert("ANC", ax, ay, 5.0, "VSS")
        for _ in range(3):
            rem_c: List[Tuple[float, float]] = []
            prog = False
            for x, y in collar_vss:
                cx_i, cy_i = int(math.floor(x / 450.0)), int(math.floor(y / 450.0))
                near = []
                for gx in (cx_i - 1, cx_i, cx_i + 1):
                    for gy in (cy_i - 1, cy_i, cy_i + 1):
                        for ax, ay, _, _ in anc_grid.grid.get(("ANC", gx, gy), ()):
                            d = math.hypot(ax - x, ay - y)
                            if d <= 520.0:
                                near.append((d, ax, ay))
                near.sort(key=lambda t: t[0])
                hit = None
                for d, ax, ay in near[:6]:
                    if _segment_clear_of_obs(bump_obs, "LDB_SURF", x, y, ax, ay, 7.0, "VSS", 14.0) and _segment_clear_of_layer_clines(clines_out, "SURFACE", x, y, ax, ay, 7.0, "VSS", 14.0):
                        hit = (ax, ay)
                        break
                if hit is not None:
                    clines_out.append(ClineRecord("VSS", "SURFACE", 14.0, round(x, 3), round(y, 3), round(hit[0], 3), round(hit[1], 3), f"{domain_tag}_COLLAR_VSS"))
                    anc_grid.insert("ANC", x, y, 5.0, "VSS")
                    placed["VSS_collar_straps"] += 1
                    prog = True
                else:
                    rem_c.append((x, y))
            collar_vss = rem_c
            if not collar_vss or not prog:
                break

    return dict(placed)


# ---------------------------------------------------------------------------
# Global Package Co-Pocket Compiler & Multi-Layer Resolver (All 24 Domains!)
# ---------------------------------------------------------------------------
def _compile_all_package_curved_pockets(
    lsc_rows: Sequence[Dict[str, str]],
    bga_balls: Sequence[Dict[str, str]],
    routed_pwr_nets: Set[str],
    pkg_own: MultiRailLayerOwnershipIndex,
    all_emib_boxes: Sequence[BBox],
) -> Tuple[List[CavityRecord], List[PlacedLscItem], List[str], List[CurvedPocketResult]]:
    """
    Globally cluster ALL routed-rail LSCs across all 24 domains (so cross-slice HBM pockets and
    shared VDDC+SRAM pockets are built atomically), resolve Pin-1 nets against `pkg_own`, and
    enforce global non-overlapping `other_cavity_polys` + `fixed_neighbor_lscs`.
    """
    target_lscs = [r for r in lsc_rows if r["pin1_net"] in routed_pwr_nets or r["pin2_net"] in routed_pwr_nets]
    other_lscs = [r for r in lsc_rows if r["pin1_net"] not in routed_pwr_nets and r["pin2_net"] not in routed_pwr_nets]
    lda_sram_lscs = [
        (float(r["x_um"]), float(r["y_um"]), r["pin1_net"])
        for r in target_lscs if r["pin1_net"].startswith("VDD_0P8_SRAM_CC")
    ]
    lda_vddc_lscs = [
        (float(r["x_um"]), float(r["y_um"]), r["pin1_net"])
        for r in target_lscs if r["pin1_net"].startswith("VDDC") and len(r["pin1_net"]) == 5
    ]

    # Spatial index over original HBM/LDA power seeds for sub-island tie-breaking on stacked 12B/10B planes
    seed_pts_by_net: List[Tuple[float, float, str]] = [
        (float(r["x_um"]), float(r["y_um"]), r["pin1_net"])
        for r in target_lscs if r["pin1_net"] in routed_pwr_nets
    ]

    n = len(target_lscs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pts_xy = [(float(r["x_um"]), float(r["y_um"])) for r in target_lscs]
    for i in range(n):
        xi, yi = pts_xy[i]
        for j in range(i + 1, n):
            xj, yj = pts_xy[j]
            if abs(xi - xj) <= 2100.0 and abs(yi - yj) <= 2100.0:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups: Dict[int, List[Dict[str, str]]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(target_lscs[i])

    # Pre-index extreme package corner BGAs + indexed polygons/cavities for fast per-pocket lookup
    corner_bgas = [
        min(bga_balls, key=lambda b: float(b["x_um"])),
        max(bga_balls, key=lambda b: float(b["x_um"])),
        min(bga_balls, key=lambda b: float(b["y_um"])),
        max(bga_balls, key=lambda b: float(b["y_um"])),
    ]
    bga_xy = [(float(b["x_um"]), float(b["y_um"]), b) for b in bga_balls]
    poly_12_10_8 = [
        (isl, isl.bbox)
        for lyr in ("12B", "10B", "8B")
        for isl in pkg_own.by_layer.get(lyr, ())
        if isl.net_name != "__ISOLATED__"
    ]

    cavs: List[CavityRecord] = []
    placed_all: List[PlacedLscItem] = []
    del_refs: List[str] = []
    raw_results: List[CurvedPocketResult] = []
    built_polys_with_bb: List[Tuple[List[Point], BBox]] = []

    for idx, grp in enumerate(sorted(groups.values(), key=lambda g: (-len(g), min(float(r["y_um"]) for r in g))), start=1):
        pk_id = f"PKG_CAV_{idx:02d}"
        for r in grp:
            if r.get("refdes"):
                del_refs.append(r["refdes"])
        gxs = [float(r["x_um"]) for r in grp]
        gys = [float(r["y_um"]) for r in grp]
        gx0, gx1 = min(gxs), max(gxs)
        gy0, gy1 = min(gys), max(gys)
        win = (gx0 - 6500.0, gy0 - 6500.0, gx1 + 6500.0, gy1 + 6500.0)
        pad_win = (gx0 - 2600.0, gy0 - 2600.0, gx1 + 2600.0, gy1 + 2600.0)

        loc_fixed = [
            r for r in other_lscs
            if pad_win[0] <= float(r["x_um"]) <= pad_win[2] and pad_win[1] <= float(r["y_um"]) <= pad_win[3]
        ]
        loc_emibs = [e for e in all_emib_boxes if bboxes_intersect(e, win)]
        loc_cavs = [p for p, bb in built_polys_with_bb if bboxes_intersect(bb, win)]
        seen_cb = set(id(b) for b in corner_bgas)
        loc_bgas = list(corner_bgas) + [
            b for bx, by, b in bga_xy
            if win[0] <= bx <= win[2] and win[1] <= by <= win[3] and id(b) not in seen_cb
        ]

        loc_own = MultiRailLayerOwnershipIndex([isl for isl, bb in poly_12_10_8 if bboxes_intersect(bb, pad_win)])
        loc_sram = [(sx, sy, sn) for sx, sy, sn in lda_sram_lscs if pad_win[0] <= sx <= pad_win[2] and pad_win[1] <= sy <= pad_win[3]]
        loc_vddc = [(vx, vy, vn) for vx, vy, vn in lda_vddc_lscs if pad_win[0] <= vx <= pad_win[2] and pad_win[1] <= vy <= pad_win[3]]
        loc_seeds = [(sx, sy, sn) for sx, sy, sn in seed_pts_by_net if pad_win[0] <= sx <= pad_win[2] and pad_win[1] <= sy <= pad_win[3]]

        def _local_resolver(
            x_c: float,
            y_c: float,
            rot_deg: float,
            _own: MultiRailLayerOwnershipIndex = loc_own,
            _sram: List[Tuple[float, float, str]] = loc_sram,
            _vddc: List[Tuple[float, float, str]] = loc_vddc,
            _seeds: List[Tuple[float, float, str]] = loc_seeds,
        ) -> Optional[str]:
            tmp = PlacedLscItem("TMP", "SM0201_690X390X550_01A", x_c, y_c, rot_deg, "VDDC0", "VSS", "P")
            (p1x, p1y), _ = tmp.pin_coords
            own12 = _own.owner_at("12B", p1x, p1y, min_edge_margin_um=35.0)
            own10 = _own.owner_at("10B", p1x, p1y, min_edge_margin_um=35.0)
            if own12 in routed_pwr_nets and own12.startswith("VDDC") and len(own12) == 5 and own10 and own10.startswith("VDD_0P8_SRAM_CC"):
                d_sram = min((math.hypot(sx - x_c, sy - y_c) for sx, sy, sn in _sram if sn == own10), default=1e9)
                d_vddc = min((math.hypot(vx - x_c, vy - y_c) for vx, vy, vn in _vddc if vn == own12), default=1e9)
                if d_sram <= 320.0 and d_sram <= d_vddc:
                    return own10
                return own12
            near_seeds = [(math.hypot(sx - x_c, sy - y_c), sn) for sx, sy, sn in _seeds if abs(sx - x_c) <= 1200.0 and abs(sy - y_c) <= 1200.0]
            if near_seeds:
                _, best_sn = min(near_seeds, key=lambda t: t[0])
                if own10 == best_sn and "VDDQ_0P85_HBM" in best_sn:
                    return best_sn
            if own12 in routed_pwr_nets:
                return own12
            if own10 in routed_pwr_nets:
                return own10
            own8 = _own.owner_at("8B", p1x, p1y, min_edge_margin_um=35.0)
            return own8 if own8 in routed_pwr_nets else None

        span_max = max(gx1 - gx0, gy1 - gy0)
        is_narrow_bga_corridor = (gy1 - gy0) < 60.0 and 15500.0 <= abs(gy0) <= 17200.0
        mill_r_use = 375.0 if is_narrow_bga_corridor else 508.0
        g_step = 18.0 if is_narrow_bga_corridor else (28.0 if span_max >= 5500.0 else 20.0)
        dom_seed_net = grp[0]["pin1_net"] if grp[0]["pin1_net"] in routed_pwr_nets else "VDDC0"
        res = synthesize_curved_bga_recess_and_pack_lscs(
            pocket_id=pk_id,
            seed_points=[(float(r["x_um"]), float(r["y_um"])) for r in grp],
            bga_balls=loc_bgas,
            default_vdd_net=dom_seed_net,
            rail_resolver_fn=_local_resolver,
            existing_pocket_lscs=grp,
            fixed_neighbor_lscs=loc_fixed,
            emib_shadow_boxes=loc_emibs,
            other_cavity_polys=loc_cavs,
            mill_radius_um=mill_r_use,
            bga_sro_to_cav_um=254.0,
            ext_koz_um=178.0,
            lsc_sro_to_cav_um=225.0,
            sro_to_sro_um=250.0,
            symbol_name="SM0201_690X390X550_01A",
            refdes_prefix=f"CPKG_P{idx:02d}",
            grid_step_um=g_step,
        )
        raw_results.append(res)
        if res.cavity_poly:
            built_polys_with_bb.append((res.cavity_poly, _poly_bbox(res.cavity_poly)))
            xs = [p[0] for p in res.cavity_poly]
            ys = [p[1] for p in res.cavity_poly]
            cavs.append(
                CavityRecord(
                    pocket_id=pk_id,
                    x1=round(min(xs), 2),
                    y1=round(min(ys), 2),
                    x2=round(max(xs), 2),
                    y2=round(max(ys), 2),
                    corner_r_um=508.0,
                    ext_koz_um=178.0,
                    lsc_safe_in_um=225.0,
                    cavity_poly=res.cavity_poly,
                    outer_koz_poly=res.outer_koz_poly,
                    inner_safe_poly=res.inner_safe_poly,
                    is_non_rectangular=res.is_non_rectangular,
                )
            )
        placed_all.extend(res.placed_lscs)

    return cavs, placed_all, del_refs, raw_results


# ---------------------------------------------------------------------------
# Stage 3 Visual Gate SVG Renderers (XML-Validated Full-Package Views)
# ---------------------------------------------------------------------------
def _pts_str(pts: Sequence[Point]) -> str:
    return " ".join(f"{x:.1f},{-y:.1f}" for x, y in pts)


def _render_full_package_svgs(
    out_dir: Path,
    pkg_polys: Sequence[PolygonIsland],
    pkg_cavs: Sequence[CavityRecord],
    pkg_lscs: Sequence[PlacedLscItem],
    bga_balls: Sequence[Dict[str, str]],
    domain_stats: Dict[str, Dict[str, Any]],
    sandbox_summary: Dict[str, Any],
) -> List[str]:
    """Generate 3 high-resolution XML-validated Visual Gate SVGs in `out_dir`."""
    rail_palette = {
        "VDDC": "#ef4444", "VDD_0P8_SRAM": "#f59e0b", "VDDUC": "#06b6d4",
        "VDDCH": "#3b82f6", "VDDQ_": "#10b981", "VDDC_": "#ec4899",
        "VDDQL": "#a855f7", "VPP_": "#eab308", "VDD_0P75_HBMPHY": "#84cc16",
    }
    def _rail_col(net: str) -> str:
        for k, col in rail_palette.items():
            if net.startswith(k):
                return col
        return "#64748b"

    # 1. Master 27-Layer Full Package Overview SVG
    s1_path = out_dir / "FullPackage_24Dies_27Layer_Master_Overview.svg"
    lines1 = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-49000 -46000 98000 92000" width="2400" height="2250" style="background:#0b1120">',
        '<text x="0" y="-43800" text-anchor="middle" fill="#f8fafc" font-family="Segoe UI,Arial" font-size="1450" font-weight="bold">FULL-PACKAGE 24-DIE, ALL-RAILS 27-LAYER PDN SANDBOX OVERVIEW (12B / 10B / 12F / EMIB / eDTC)</text>',
    ]
    for isl in pkg_polys:
        if isl.layer == "12F" and isl.net_name != "VSS" and isl.net_name != "__ISOLATED__":
            lines1.append(f'<polygon points="{_pts_str(isl.vertices)}" fill="{_rail_col(isl.net_name)}" fill-opacity="0.22" stroke="{_rail_col(isl.net_name)}" stroke-width="45"/>')
        elif isl.layer == "12B" and isl.net_name != "VSS" and isl.net_name != "__ISOLATED__":
            lines1.append(f'<polygon points="{_pts_str(isl.vertices)}" fill="none" stroke="{_rail_col(isl.net_name)}" stroke-width="55" stroke-dasharray="220 120" stroke-opacity="0.85"/>')
    for isl in pkg_polys:
        if "EDTC_4FCO_GUARD" in isl.tag:
            lines1.append(f'<polygon points="{_pts_str(isl.vertices)}" fill="#fbbf24" fill-opacity="0.28" stroke="#f59e0b" stroke-width="55"/>')
    for eref, eb in ALL_EMIB_U25_TO_U40.items():
        x0, y0, x1, y1 = eb
        lines1.append(f'<rect x="{x0}" y="{-y1}" width="{x1-x0}" height="{y1-y0}" fill="#0ea5e9" fill-opacity="0.25" stroke="#38bdf8" stroke-width="55"/>')
    for h in HBM_SITES:
        tf = _make_hbm_tf(str(h["mode"]), float(h["dy"]))
        eb_ref = U41_EMIB_BBOX if h["variant"] == "A" else (-35738.9, -9436.6, -27112.9, -968.3)
        p1, p2 = tf(eb_ref[0], eb_ref[1]), tf(eb_ref[2], eb_ref[3])
        x0, y0, x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])
        lines1.append(f'<rect x="{x0}" y="{-y1}" width="{x1-x0}" height="{y1-y0}" fill="#0ea5e9" fill-opacity="0.25" stroke="#38bdf8" stroke-width="55"/>')
    for cav in pkg_cavs:
        if cav.cavity_poly:
            lines1.append(f'<polygon points="{_pts_str(cav.cavity_poly)}" fill="#ffffff" fill-opacity="0.12" stroke="#f8fafc" stroke-width="65"/>')
    lines1.append(f'<text x="0" y="44300" text-anchor="middle" fill="#94a3b8" font-family="Segoe UI,Arial" font-size="950">Domains={sandbox_summary["totals"]["domains_built"]} | Shapes={sandbox_summary["totals"]["polygons"]} | Vias={sandbox_summary["totals"]["vias"]} | Clines={sandbox_summary["totals"]["clines"]} | Cavities={len(pkg_cavs)} | BASE LSCs={len(pkg_lscs)}</text>')
    lines1.append("</svg>")
    s1_txt = "\n".join(lines1)
    ET.fromstring(s1_txt)
    s1_path.write_text(s1_txt, encoding="utf-8")

    # 2. BASE Curved Recess + 180-deg Alternation Full Package + Insets SVG
    s2_path = out_dir / "FullPackage_24Dies_BASE_Curved_Recess_LSC.svg"
    lines2 = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-49000 -46000 98000 92000" width="2400" height="2250" style="background:#090d16">',
        '<text x="0" y="-43800" text-anchor="middle" fill="#f8fafc" font-family="Segoe UI,Arial" font-size="1400" font-weight="bold">BASE L27 — ALL 24 DOMAINS CURVED BGA RECESSES &amp; 180° ALTERNATING LSC PACKING</text>',
    ]
    for b in bga_balls:
        if "FID" in b.get("padstack_name", ""):
            continue
        bx, by = float(b["x_um"]), float(b["y_um"])
        n = b["net_name"]
        col = "#334155" if n == "VSS" else _rail_col(n)
        op = "0.55" if n == "VSS" else "0.85"
        lines2.append(f'<circle cx="{bx:.1f}" cy="{-by:.1f}" r="245" fill="{col}" fill-opacity="{op}"/>')
    for cav in pkg_cavs:
        if cav.outer_koz_poly:
            lines2.append(f'<polygon points="{_pts_str(cav.outer_koz_poly)}" fill="none" stroke="#f97316" stroke-width="45" stroke-dasharray="180 90"/>')
        if cav.cavity_poly:
            lines2.append(f'<polygon points="{_pts_str(cav.cavity_poly)}" fill="#0f172a" fill-opacity="0.72" stroke="#38bdf8" stroke-width="75"/>')
    for it in pkg_lscs:
        p1, p2 = it.pin_coords
        bw, bh = (220.0, 410.0) if (int(round(it.rot_deg)) % 180 == 0) else (410.0, 220.0)
        lines2.append(f'<rect x="{it.x - bw:.1f}" y="{-it.y - bh:.1f}" width="{2*bw:.1f}" height="{2*bh:.1f}" fill="#1e293b" stroke="#cbd5e1" stroke-width="35"/>')
        lines2.append(f'<circle cx="{p1[0]:.1f}" cy="{-p1[1]:.1f}" r="115" fill="{_rail_col(it.pin1_net)}"/>')
        lines2.append(f'<circle cx="{p2[0]:.1f}" cy="{-p2[1]:.1f}" r="95" fill="#94a3b8"/>')
    lines2.append("</svg>")
    s2_txt = "\n".join(lines2)
    ET.fromstring(s2_txt)
    s2_path.write_text(s2_txt, encoding="utf-8")

    # 3. 24-Domain Scorecard & DRC Gate Audit Summary SVG
    s3_path = out_dir / "FullPackage_24Dies_Domain_Audit_Summary.svg"
    lines3 = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1080" width="1600" height="1080" style="background:#0f172a">',
        '<text x="800" y="48" text-anchor="middle" fill="#f8fafc" font-family="Segoe UI,Arial" font-size="26" font-weight="bold">STAGE 3 VISUAL GATE — 24-DOMAIN PDN DRC &amp; 9F-&gt;5F / 9B-&gt;5B CONTINUITY SCORECARD</text>',
        f'<text x="800" y="80" text-anchor="middle" fill="#34d399" font-family="Consolas,monospace" font-size="16">STATUS: {sandbox_summary["status"]} | ZeroViaOverlap={sandbox_summary["zero_via_overlap_audit"]["zero_via_overlap_pass"]} | PolyClearance={sandbox_summary["polygon_clearance_audit"]["polygon_clearance_pass"]} | CavitiesPass={sandbox_summary["curved_cavity_audit"]["all_cavities_pass"]}</text>',
        '<rect x="40" y="105" width="1520" height="36" fill="#1e293b"/>',
        '<text x="60" y="129" fill="#e2e8f0" font-family="Consolas,monospace" font-size="14" font-weight="bold">DOMAIN                 | SHAPES |   VIAS | CLINES |  9F-&gt;5F VSS |  9B-&gt;5B VSS | CORES |   BGA |  STATUS</text>',
    ]
    y_row = 166
    for dk in sorted(domain_stats):
        st = domain_stats[dk]
        v9f = st.get("vss_9f_5f_cols", "-")
        v9b = st.get("vss_9b_5b_cols", "-")
        pth = st.get("core_pth_cols", "-")
        bgas = st.get("bot", {}).get("bga_pads", 0)
        ok = (v9f == "-" or v9f > 0) and (v9b == "-" or v9b > 0)
        col = "#34d399" if ok else "#f87171"
        lines3.append(
            f'<text x="60" y="{y_row}" fill="{col}" font-family="Consolas,monospace" font-size="13">'
            f'{dk:22s} | {st.get("shapes",0):6d} | {st.get("vias",0):6d} | {st.get("clines",0):6d} | {str(v9f):>11s} | {str(v9b):>11s} | {str(pth):>5s} | {bgas:5d} | {"PASS" if ok else "CHECK"}</text>'
        )
        y_row += 28
    tots = sandbox_summary["totals"]
    lines3.append(f'<text x="60" y="1030" fill="#94a3b8" font-family="Consolas,monospace" font-size="15">TOTALS: polygons={tots["polygons"]} vias={tots["vias"]} clines={tots["clines"]} cavities={tots["curved_cavities"]} base_lscs={tots["base_180_lscs"]} | Source: PDN_test.mcm (READ-ONLY)</text>')
    lines3.append("</svg>")
    s3_txt = "\n".join(lines3)
    ET.fromstring(s3_txt)
    s3_path.write_text(s3_txt, encoding="utf-8")
    return [str(s1_path), str(s2_path), str(s3_path)]


# ---------------------------------------------------------------------------
# Main Full-Package 24-Domain Orchestrator
# ---------------------------------------------------------------------------
def _execute_stage4_apd_build(
    src_mcm: Path,
    out_mcm_path: Path,
    out_dir: Path,
    recipe_file: Path,
    sandbox_summary: Dict[str, Any],
    timeout_sec: int,
) -> Dict[str, Any]:
    out_mcm = out_mcm_path.resolve()
    if src_mcm == out_mcm:
        raise RuntimeError(f"SAFETY_LOCK: refusing to overwrite source {src_mcm.name}!")
    out_mcm.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_mcm, out_mcm)
    lck = out_mcm.with_name(out_mcm.name + ".lck")
    if lck.exists():
        lck.unlink()

    il_s = (WORKSPACE / "agent04_pdn_architect" / "templates" / "apd_unified_27layer_template_importer.il").as_posix()
    rep_file = out_dir / "AllDies_AllRails_apd_import_report.txt"
    prog_file = out_dir / "AllDies_AllRails_apd_import_report.txt.progress"
    for f in (rep_file, prog_file):
        if f.exists():
            f.unlink()
    scr_file = out_dir / "run_all_dies_all_rails.scr"
    scr_file.write_text(
        f'skill load("{il_s}")\n'
        f'skill pdnRunUnified27LayerTemplateBatch("{recipe_file.as_posix()}" "" "{rep_file.as_posix()}")\n'
        f"exit\nfillin no\n",
        encoding="utf-8",
    )

    runner = CadenceBatchRunner(default_timeout=timeout_sec)
    t_apd0 = time.perf_counter()
    apd_res = runner.run(mcm_path=out_mcm, scr_path=scr_file, working_dir=out_dir, timeout=timeout_sec, bypass_lock_readonly=False)
    t_apd = time.perf_counter() - t_apd0

    kv: Dict[str, str] = {}
    if rep_file.exists():
        for ln in rep_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                kv[k.strip()] = v.strip()

    final_audit = {
        "status": kv.get("STATUS", "SUCCESS" if apd_res.success else "ERROR"),
        "source_mcm_readonly": str(src_mcm),
        "output_mcm_path": str(out_mcm),
        "output_mcm_size_bytes": out_mcm.stat().st_size if out_mcm.exists() else 0,
        "apd_duration_sec": round(t_apd, 2),
        "sandbox_summary": sandbox_summary,
        "apd_report": kv,
    }
    (out_dir / "AllDies_AllRails_MCM_Build_Audit.json").write_text(json.dumps(final_audit, indent=2), encoding="utf-8")
    return final_audit


def _resolve_pdn_io_context(
    src_mcm_path: Optional[Path] = None,
    work_dir: Optional[str] = None,
) -> Tuple[Optional[Path], bool, Path, Path]:
    """Resolve active working folder, read-only origin .mcm (preferring <work_dir>/MCM_template), and Stage 1 dir."""
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import resolve_active_work_dir
    except ImportError:
        from pdn_paths import resolve_active_work_dir  # type: ignore

    eff_wd, is_custom_wd = resolve_active_work_dir(work_dir)
    if not is_custom_wd and not work_dir and not os.environ.get("SUBSTRATE_WORK_DIR", "").strip():
        eff_wd_opt: Optional[Path] = None
    else:
        eff_wd_opt = eff_wd

    if src_mcm_path is not None:
        src_mcm = src_mcm_path.expanduser().resolve()
    elif is_custom_wd and eff_wd:
        wd_mcm = resolve_mcm_in_work_dir(eff_wd)
        src_mcm = wd_mcm.resolve() if wd_mcm else (WORKSPACE / "agent04_pdn_architect" / "MCM_test" / "PDN_test.mcm").resolve()
    else:
        src_mcm = (WORKSPACE / "agent04_pdn_architect" / "MCM_test" / "PDN_test.mcm").resolve()

    if is_custom_wd and eff_wd and (eff_wd / "stage1_inputs").is_dir():
        stage1_dir = (eff_wd / "stage1_inputs").resolve()
    else:
        stage1_dir = (WORKSPACE / "agent04_pdn_architect" / "stage1_inputs").resolve()
    return eff_wd_opt, is_custom_wd, src_mcm, stage1_dir


def synthesize_full_package_all_dies(
    pins_csv: Path,
    out_dir: Path,
    dry_run_only: bool = True,
    out_mcm_path: Optional[Path] = None,
    timeout_sec: int = 1800,
    reuse_sandbox: bool = False,
    src_mcm_path: Optional[Path] = None,
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    recipe_file = out_dir / "AllDies_AllRails_27Layer_Master_Recipe.txt"
    audit_file = out_dir / "AllDies_AllRails_Sandbox_Audit.json"
    _eff_wd, _is_custom, src_mcm, s1 = _resolve_pdn_io_context(src_mcm_path=src_mcm_path, work_dir=work_dir)

    if reuse_sandbox and recipe_file.exists() and audit_file.exists():
        sandbox_summary = json.loads(audit_file.read_text(encoding="utf-8"))
        all_ok = (sandbox_summary.get("status") == "SANDBOX_COMPILED_DRC_PASS")
        if dry_run_only or out_mcm_path is None:
            return sandbox_summary
        if not all_ok:
            raise RuntimeError("Cached sandbox audit did not pass DRC!")
        return _execute_stage4_apd_build(src_mcm, out_mcm_path, out_dir, recipe_file, sandbox_summary, timeout_sec)

    bga_balls = _read_csv(s1 / "bga_map.csv")
    edtc_pins = _read_csv(s1 / "edtc_pin_map.csv")
    edtc_syms = _read_csv(s1 / "edtc_symbols.csv")
    lsc_caps = _read_csv(s1 / "lsc_placed_map.csv")
    u9_pins_full = _read_csv(s1 / "u9_full_pins.csv")
    all_pwr_pins = _load_power_pins_by_refdes(pins_csv)
    t_load = time.perf_counter() - t0

    all_edtc_refs = [r["refdes"] for r in edtc_syms if r["refdes"] != "NOREF"]
    all_edtc_profs = compute_real_edtc_profiles(edtc_pins, edtc_syms, all_edtc_refs)

    # 1. Build clean Reference Templates (`U9` LDA, `U13/U41/U5` HBM Variant A, `U16/U44/U6` HBM Variant B)
    t1 = time.perf_counter()
    u9_ref_profs = {k: all_edtc_profs[k] for k in U9_EDTC_BODIES}
    u9_ref_polys = build_u9_lda_27layer_polygons(edtc_profiles=u9_ref_profs)
    u9_ref_own = MultiRailLayerOwnershipIndex(u9_ref_polys)
    u9_ref_vias: List[ViaRecord] = []
    u9_ref_clines: List[ClineRecord] = []
    u9_ref_grid = FastXYClearanceGrid(cell_um=220.0)
    synthesize_concentric_edtc_stacks(edtc_pins, list(U9_EDTC_BODIES.keys()), ("VDDC0", "VDD_0P8_SRAM_CC0", "VSS"), u9_ref_own, u9_ref_vias, u9_ref_grid)
    route_u9_emib_csb_and_c0_pins(u9_pins_full, u9_ref_own, u9_ref_vias, u9_ref_grid)
    synthesize_multi_rail_core_pth_and_pp(U9_DOMAIN_BBOX, ("VDDC0", "VDD_0P8_SRAM_CC0"), u9_ref_own, U9_EDTC_BODIES, U9_EMIB_BRIDGES, u9_ref_vias, u9_ref_grid, tag_prefix="U9", edtc_profiles=u9_ref_profs)
    route_u9_vddc0_sram0_vss_3to1_vertical_jog(u9_pins_full, u9_ref_own, u9_ref_vias, u9_ref_clines, u9_ref_grid, "3:1", 15.0, 15.0, True, ("VDD_0P8_SRAM_CC0",))
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(U9_DOMAIN_BBOX, ("VDDC0", "VDD_0P8_SRAM_CC0"), u9_ref_own, u9_ref_vias, u9_ref_grid, pitch_um=285.0, tag_prefix="U9_MID")
    route_u9_vddc0_sram0_vss_3to1_vertical_jog(u9_pins_full, u9_ref_own, u9_ref_vias, u9_ref_clines, u9_ref_grid, "3:1", 15.0, 15.0, True, ("VDDC0", "VSS"))
    connect_u9_sram0_10f_backbone(u9_ref_own, u9_ref_vias, u9_ref_clines, u9_ref_grid)
    u9_ref_cols = _group_vias_into_columns([v for v in u9_ref_vias if not v.tag.startswith("U9_BOT") and "BGA" not in v.tag and "LSC" not in v.tag])
    u9_ref_surf_clines = list(u9_ref_clines)

    hbm_tpls: Dict[str, Tuple[List[PolygonIsland], List[Tuple[float, float, str, str, List[ViaRecord]]], List[ClineRecord]]] = {}
    for var_k, hrf, erf, lrf, ed_r, rmap in [
        ("A", "U13", "U41", "U5", ["C2258", "C2257"], {"vddq": "VDDQ_0P85_HBM_MEM5", "vddc": "VDDC_1P0_HBM_MEM5", "vddql": "VDDQL5", "vpp": "VPP_1P8_HBM_MEM5", "phy": "VDD_0P75_HBMPHY_UC5"}),
        ("B", "U16", "U44", "U6", ["C2270", "C2269"], {"vddq": "VDDQ_0P85_HBM_MEMB", "vddc": "VDDC_1P0_HBM_MEMB", "vddql": "VDDQLB", "vpp": "VPP_1P8_HBM_MEMB", "phy": "VDD_0P75_HBMPHY_UCB"}),
    ]:
        h_polys, h_vias, h_clines = _route_hbm_variant_template(
            var_k, hrf, erf, lrf, ed_r, rmap, all_pwr_pins, edtc_pins, {k: all_edtc_profs[k] for k in ed_r}
        )
        hbm_tpls[var_k] = (h_polys, _group_vias_into_columns(h_vias), h_clines)
    t_ref = time.perf_counter() - t1

    # Identify all MISC/VDDIO BGAs for 12B non-short notches in HBMPHY strips
    misc_bgas = [
        (float(b["x_um"]), float(b["y_um"]))
        for b in bga_balls
        if ("VDDIO" in b["net_name"] or "MISC" in b["net_name"]) and 26500.0 <= abs(float(b["x_um"])) <= 33500.0
    ]

    t2 = time.perf_counter()
    pkg_grid = FastXYClearanceGrid(cell_um=250.0)
    pkg_polys: List[PolygonIsland] = []
    pkg_vias: List[ViaRecord] = []
    pkg_clines: List[ClineRecord] = []
    domain_stats: Dict[str, Dict[str, Any]] = {}
    domain_polys_map: Dict[str, Tuple[List[PolygonIsland], Set[str], BBox]] = {}
    routed_pwr_nets: Set[str] = set()

    # 2. Task 2: Instantiate ALL 4 LDA Domains (`U9, U12, U88, U10`)
    for site in LDA_SITES:
        rd = str(site["refdes"])
        vddc_n, sram_n = str(site["vddc"]), str(site["sram"])
        routed_pwr_nets.update((vddc_n, sram_n))
        tf = _make_lda_tf(str(site["mode"]), float(site["cx"]), float(site["cy"]))
        nmap = {"VDDC0": vddc_n, "VDD_0P8_SRAM_CC0": sram_n, "VSS": "VSS", "__ISOLATED__": "__ISOLATED__"}
        clip_m: BBox = site["clip_main"]  # type: ignore[assignment]
        bot_boxes: List[BBox] = list(site["bot_boxes"])  # type: ignore[arg-type]
        bot_union = union_rect_boxes_to_polygons(bot_boxes)[0]
        bot_outer_box = _poly_bbox(bot_union)

        site_polys: List[PolygonIsland] = []
        for isl in u9_ref_polys:
            if isl.layer in ("12B", "11B"):
                if isl.layer == "12B":
                    site_polys.append(PolygonIsland("12B", vddc_n, bot_union, tag=f"{rd}_12B_{vddc_n}_MAIN", is_dynamic=True))
                else:
                    site_polys.append(PolygonIsland("11B", "VSS", bot_union, tag=f"{rd}_11B_VSS", is_dynamic=True))
                continue
            ci = transform_and_clip_island(isl, tf, nmap, clip_m)
            if ci is not None:
                site_polys.append(ci)

        site_own = MultiRailLayerOwnershipIndex(site_polys)
        site_vias: List[ViaRecord] = []
        site_clines: List[ClineRecord] = []
        for rx, ry, rnet, rtag, col in u9_ref_cols:
            vx, vy = tf(rx, ry)
            if not (clip_m[0] + 10.0 <= vx <= clip_m[2] - 10.0 and clip_m[1] + 10.0 <= vy <= clip_m[3] - 10.0):
                continue
            vn = nmap.get(rnet, rnet)
            spans = [(v.start_layer, v.end_layer) for v in col]
            pad_ovr = {(v.start_layer, v.end_layer): v.padstack for v in col}
            insert_via_stack_zero_overlap(site_vias, pkg_grid, vn, spans, vx, vy, rtag.replace("U9", rd), pad_ovr)
        for c in u9_ref_surf_clines:
            x1, y1 = tf(c.x1, c.y1)
            x2, y2 = tf(c.x2, c.y2)
            if clip_m[0] <= min(x1, x2) and max(x1, x2) <= clip_m[2] and clip_m[1] <= min(y1, y2) and max(y1, y2) <= clip_m[3]:
                site_clines.append(ClineRecord(nmap.get(c.net_name, c.net_name), c.layer, c.width_um, x1, y1, x2, y2, c.tag.replace("U9", rd)))
        synthesize_concentric_edtc_stacks(edtc_pins, list(site["edtc_refs"]), (vddc_n, sram_n, "VSS"), site_own, site_vias, pkg_grid)  # type: ignore[arg-type]

        pkg_polys.extend(site_polys)
        pkg_vias.extend(site_vias)
        pkg_clines.extend(site_clines)
        dk = f"TASK2_{rd}_{vddc_n}"
        domain_polys_map[dk] = (site_polys, {vddc_n, sram_n}, bot_outer_box)
        domain_stats[dk] = {"shapes": len(site_polys), "vias": len(site_vias), "clines": len(site_clines), "_vias_list": site_vias, "_vss_bbox": site["vss_bga_bbox"], "_pwr_set": {vddc_n, sram_n}}

    # 3. Task 3: Instantiate ALL 12 HBM Sites (`Variant A` + `Variant B`)
    edtc_core_layers = {"4FCO", "4BCO", "2FCI", "2BCI", "3FCI", "1FCI", "1BCI", "3BCI"}
    for hsite in HBM_SITES:
        idx, var_k = str(hsite["idx"]), str(hsite["variant"])
        hrd, erd = str(hsite["hbm"]), str(hsite["emib"])
        vddq_n, vddc_n = f"VDDQ_0P85_HBM_MEM{idx}", f"VDDC_1P0_HBM_MEM{idx}"
        vddql_n, vpp_n, phy_n = f"VDDQL{idx}", f"VPP_1P8_HBM_MEM{idx}", f"VDD_0P75_HBMPHY_UC{idx}"
        routed_pwr_nets.update((vddq_n, vddc_n, vddql_n, vpp_n, phy_n))

        src_ref_hbm, src_ref_emib = ("U13", "U41") if var_k == "A" else ("U16", "U44")
        src_suf = "MEM5" if var_k == "A" else "MEMB"
        src_ql = "VDDQL5" if var_k == "A" else "VDDQLB"
        src_phy = "VDD_0P75_HBMPHY_UC5" if var_k == "A" else "VDD_0P75_HBMPHY_UCB"
        nmap = {
            f"VDDQ_0P85_HBM_{src_suf}": vddq_n,
            f"VDDC_1P0_HBM_{src_suf}": vddc_n,
            src_ql: vddql_n,
            f"VPP_1P8_HBM_{src_suf}": vpp_n,
            src_phy: phy_n,
            "VSS": "VSS",
            "__ISOLATED__": "__ISOLATED__",
        }
        tf = _make_hbm_tf(str(hsite["mode"]), float(hsite["dy"]))
        x_clip: Tuple[float, float] = hsite["x_clip"]  # type: ignore[assignment]
        y_clip: Tuple[float, float] = hsite["y_clip"]  # type: ignore[assignment]
        c_box: BBox = (x_clip[0], y_clip[0], x_clip[1], y_clip[1])

        ref_polys, ref_cols, ref_clines = hbm_tpls[var_k]
        site_edtc_profs = {k: all_edtc_profs[k] for k in hsite["edtc"]}  # type: ignore[index]
        ldc_n: Optional[BBox] = hsite.get("ldc_notch")  # type: ignore[assignment]
        is_west = x_clip[0] < 0.0

        # Inter-slice 12B/10B/8B notch & tongue adjustments + 12B HBMPHY LSC pocket tab
        extra_notches_bot: List[BBox] = []
        extra_notches_8b: List[BBox] = []
        if idx == "2":  # C144 (VDDQL1) notch out of MEM2 12B/11B/10B/8B
            extra_notches_bot.append((33390.0, 10670.0, 34260.0, 11380.0))
            extra_notches_8b.append((26700.0, 10650.0, 46200.0, 11380.0))
        elif idx == "B":  # UCA C189/185 notch out of MEMB 12B/11B/10B
            extra_notches_bot.append((-30140.0, -11350.0, -26700.0, -10080.0))
        elif idx == "6":  # UC7 C166 notch out of MEM6 12B/11B/10B
            extra_notches_bot.append((26700.0, -11350.0, 30140.0, -10080.0))
        elif idx == "A":  # UC9 C191/182 notch out of MEMA 12B/11B/10B/8B
            extra_notches_bot.append((-30850.0, -22550.0, -29550.0, -21400.0))
            extra_notches_8b.append((-30850.0, -22550.0, -29550.0, -21400.0))
        elif idx == "9":  # Clear MEM9 VDDQL9 around UC9 North tongue (-30850..-30140, -22690..-22480)
            extra_notches_8b.append((-30850.0, -22690.0, -30100.0, -22450.0))

        # Compute 12B HBMPHY outer pocket tab when phy_tab=True (with 90 um notch out of 12B VDDQL)
        phy_tab_box: Optional[BBox] = None
        vddql_tab_notch: Optional[BBox] = None
        if bool(hsite["phy_tab"]):
            tx0, tx1 = (-31880.0, -30050.0) if is_west else (30050.0, 31880.0)
            ty0, ty1 = (c_box[1], c_box[1] + 2150.0) if idx in ("8", "9") else (c_box[3] - 2150.0, c_box[3])
            phy_tab_box = (tx0, ty0, tx1, ty1)
            vddql_tab_notch = expand_bbox(phy_tab_box, 90.0)

        # MISC/VDDIO 12B BGA clearance notches inside [-30050..-26800] (|X| in [27100..28250])
        misc_12b_notches: List[BBox] = []
        for mbx, mby in misc_bgas:
            if c_box[0] - 50.0 <= mbx <= c_box[2] + 50.0 and c_box[1] - 50.0 <= mby <= c_box[3] + 50.0:
                misc_12b_notches.append((mbx - 420.0, mby - 380.0, mbx + 420.0, mby + 380.0))

        site_polys = []
        for isl in ref_polys:
            if "EDTC" in isl.tag:
                continue
            ci = transform_and_clip_island(isl, tf, nmap, c_box)
            if ci is None:
                continue
            if ci.layer == "12B" and ci.net_name == vddql_n and vddql_tab_notch is not None:
                ci = _subtract_boxes_from_island(ci, [vddql_tab_notch])
                if ci is None:
                    continue
            if idx == "9" and ci.layer in ("12B", "10B") and ci.net_name == vddql_n:
                ci = _subtract_boxes_from_island(ci, [(-30850.0, -22690.0, -30100.0, -22450.0)])
                if ci is None:
                    continue
            if ci.layer == "12B" and ci.net_name == phy_n and phy_tab_box is not None:
                merged_tab = union_rect_boxes_to_polygons([ci.bbox, phy_tab_box])[0]
                ci = PolygonIsland("12B", phy_n, merged_tab, tag=ci.tag, is_dynamic=True)
            if ldc_n is not None and ci.net_name != "__ISOLATED__":
                ci = _subtract_boxes_from_island(ci, [ldc_n])
                if ci is None:
                    continue
            if ci.layer in ("12B", "11B", "10B") and extra_notches_bot:
                ci = _subtract_boxes_from_island(ci, extra_notches_bot)
                if ci is None:
                    continue
            if ci.layer == "8B" and extra_notches_8b:
                ci = _subtract_boxes_from_island(ci, extra_notches_8b)
                if ci is None:
                    continue
            if ci.layer in ("12B", "11B") and misc_12b_notches:
                ci = _subtract_boxes_from_island(ci, misc_12b_notches)
                if ci is None:
                    continue
            if ci.layer in edtc_core_layers and ci.net_name != "__ISOLATED__":
                real_kozs = [ep.outer_core_plane_koz_bbox if ci.layer in ("4FCO", "4BCO") else ep.inner_core_koz_bbox for ep in site_edtc_profs.values()]
                kept_voids = [
                    rect_vertices(kb) for kb in real_kozs
                    if all(point_in_poly(vx, vy, ci.vertices) and min_dist_to_poly_edges(vx, vy, ci.vertices) >= 20.0 for vx, vy in rect_vertices(kb))
                ]
                ci = PolygonIsland(ci.layer, ci.net_name, ci.vertices, voids=kept_voids, tag=ci.tag, is_dynamic=ci.is_dynamic)
            site_polys.append(ci)

        # Inter-slice bridge additions: C144 (MEM1), UCA (MEMA), UC7 (MEM7), UC9 (MEM9)
        if idx == "1":
            site_polys.append(PolygonIsland("12B", vddql_n, rect_vertices((33480.0, 10760.0, 34170.0, 11290.0)), tag="MEM1_12B_C144", is_dynamic=True))
            site_polys.append(PolygonIsland("10B", vddql_n, rect_vertices((33480.0, 10760.0, 34170.0, 11290.0)), tag="MEM1_10B_C144", is_dynamic=True))
            site_polys.append(PolygonIsland("8B",  vddql_n, rect_vertices((30140.0, 10820.0, 34170.0, 11290.0)), tag="MEM1_8B_C144_BR", is_dynamic=True))
            site_polys.append(PolygonIsland("11B", "VSS",   rect_vertices((33480.0, 10760.0, 34170.0, 11290.0)), tag="MEM1_11B_C144_VSS", is_dynamic=True))
        elif idx == "A":
            for ly in ("12B", "10B"):
                site_polys.append(PolygonIsland(ly, phy_n, rect_vertices((-30050.0, -11400.0, -27220.0, -10180.0)), tag=f"MEMA_{ly}_UCA_N", is_dynamic=True))
            site_polys.append(PolygonIsland("11B", "VSS", rect_vertices((-30050.0, -11400.0, -27220.0, -10180.0)), tag="MEMA_11B_UCA_N", is_dynamic=True))
        elif idx == "7":
            for ly in ("12B", "10B"):
                site_polys.append(PolygonIsland(ly, phy_n, rect_vertices((27220.0, -11400.0, 30050.0, -10180.0)), tag=f"MEM7_{ly}_UC7_N", is_dynamic=True))
            site_polys.append(PolygonIsland("11B", "VSS", rect_vertices((27220.0, -11400.0, 30050.0, -10180.0)), tag="MEM7_11B_UC7_N", is_dynamic=True))
        elif idx == "9":
            for ly in ("12B", "10B", "8B"):
                site_polys.append(PolygonIsland(ly, phy_n, rect_vertices((-30760.0, -22580.0, -29640.0, -21490.0)), tag=f"MEM9_{ly}_UC9_N", is_dynamic=True))
            site_polys.append(PolygonIsland("11B", "VSS", rect_vertices((-30760.0, -22580.0, -29640.0, -21490.0)), tag="MEM9_11B_UC9_N", is_dynamic=True))

        for lyr in ("4FCO", "4BCO"):
            for ep in site_edtc_profs.values():
                site_polys.append(PolygonIsland(lyr, "__ISOLATED__", rect_vertices(ep.guard_outer_bbox), [rect_vertices(ep.cavity_bbox)], tag=f"EDTC_{lyr}_GUARD_BAND_{ep.refdes}", is_dynamic=False))

        site_own = MultiRailLayerOwnershipIndex(site_polys)
        site_vias: List[ViaRecord] = []
        site_clines: List[ClineRecord] = []
        for rx, ry, rnet, rtag, col in ref_cols:
            vx, vy = tf(rx, ry)
            if not (c_box[0] + 10.0 <= vx <= c_box[2] - 10.0 and c_box[1] + 10.0 <= vy <= c_box[3] - 10.0):
                continue
            if ldc_n is not None and ldc_n[0] - 20.0 <= vx <= ldc_n[2] + 20.0 and ldc_n[1] - 20.0 <= vy <= ldc_n[3] + 20.0:
                continue
            vn = nmap.get(rnet, rnet)
            spans = [(v.start_layer, v.end_layer) for v in col]
            pad_ovr = {(v.start_layer, v.end_layer): v.padstack for v in col}
            insert_via_stack_zero_overlap(site_vias, pkg_grid, vn, spans, vx, vy, rtag.replace(src_ref_hbm, hrd).replace(src_ref_emib, erd), pad_ovr)

        for c in ref_clines:
            x1, y1 = tf(c.x1, c.y1)
            x2, y2 = tf(c.x2, c.y2)
            if c_box[0] <= min(x1, x2) and max(x1, x2) <= c_box[2] and c_box[1] <= min(y1, y2) and max(y1, y2) <= c_box[3]:
                site_clines.append(ClineRecord(nmap.get(c.net_name, c.net_name), c.layer, c.width_um, x1, y1, x2, y2, c.tag.replace(src_ref_hbm, hrd).replace(src_ref_emib, erd)))

        # C144 8B->10B/12B vertical stitch bridge
        if idx == "1":
            insert_via_stack_zero_overlap(site_vias, pkg_grid, vddql_n, [("8B", "9B"), ("9B", "10B")], 33780.0, 11045.0, "MEM1_C144_8B_10B")
            insert_via_stack_zero_overlap(site_vias, pkg_grid, vddql_n, [("8B", "9B"), ("9B", "10B"), ("10B", "11B"), ("11B", "12B")], 31500.0, 11045.0, "MEM1_C144_WEST_8B_12B")
        elif idx == "9":
            insert_via_stack_zero_overlap(site_vias, pkg_grid, phy_n, [("6B", "7B"), ("7B", "8B"), ("8B", "9B"), ("9B", "10B")], -29820.0, -22150.0, "MEM9_UC9_BR")

        synthesize_concentric_edtc_stacks(edtc_pins, list(hsite["edtc"]), [vddq_n, vddc_n, vddql_n, vpp_n, phy_n, "VSS"], site_own, site_vias, pkg_grid)  # type: ignore[arg-type]

        pkg_polys.extend(site_polys)
        pkg_vias.extend(site_vias)
        pkg_clines.extend(site_clines)
        dk = f"TASK3_{hrd}_MEM{idx}"
        domain_polys_map[dk] = (site_polys, {vddq_n, vddc_n, vddql_n, vpp_n, phy_n}, c_box)
        domain_stats[dk] = {"shapes": len(site_polys), "vias": len(site_vias), "clines": len(site_clines), "_vias_list": site_vias, "_vss_bbox": c_box, "_pwr_set": {vddq_n, vddc_n, vddql_n, vpp_n, phy_n}}

    # 4. Task 1: Synthesize ALL 4 LDB (`VDDUC0..3`) & ALL 4 LDC (`VDDCH0..3`)
    for spec in LDB_SITES + LDC_SITES:
        rd = str(spec["refdes"])
        vnet = str(spec["net"])
        routed_pwr_nets.add(vnet)
        dbox: BBox = spec["bbox"]  # type: ignore[assignment]
        e_refs: List[str] = list(spec["edtc"])  # type: ignore[arg-type]
        profs = {k: all_edtc_profs[k] for k in e_refs if k in all_edtc_profs}
        inner_k = [p.inner_core_koz_bbox for p in profs.values()]
        outer_k = [p.outer_core_plane_koz_bbox for p in profs.values()]
        emib_names: List[str] = list(spec.get("emib", []))  # type: ignore[arg-type]
        emib_list = [ALL_EMIB_U25_TO_U40[en] for en in emib_names]
        emib_157 = [expand_bbox(b, 157.5) for b in emib_list]
        inner_notches: List[BBox] = list(spec.get("inner_notches", []))  # type: ignore[arg-type]
        bot_notches: List[BBox] = list(spec.get("bot_notches", []))  # type: ignore[arg-type]

        site_polys = []
        for lyr in ALL_24_INNER_LAYERS:
            if lyr in ODD_VSS_LAYERS:
                kozs = list(emib_157) if lyr == "11F" else (list(inner_k) if lyr in ("3FCI", "1FCI", "1BCI", "3BCI") else [])
                n_list = bot_notches if lyr == "11B" else inner_notches
                isl = make_plane_with_Notches_and_voids(lyr, "VSS", dbox, kozs, tag=f"{rd}_{lyr}_VSS")
                isl = _subtract_boxes_from_island(isl, n_list) or isl
                site_polys.append(isl)
            else:
                kozs = list(outer_k) if lyr in ("4FCO", "4BCO") else (list(inner_k) if lyr in ("2FCI", "2BCI") else [])
                if lyr in ("12F", "10F"):
                    kozs = kozs + list(emib_157)
                n_list = bot_notches if lyr == "12B" else inner_notches
                isl = make_plane_with_Notches_and_voids(lyr, vnet, dbox, kozs, tag=f"{rd}_{lyr}_{vnet}")
                isl = _subtract_boxes_from_island(isl, n_list) or isl
                site_polys.append(isl)
                if lyr in ("4FCO", "4BCO"):
                    for ep in profs.values():
                        site_polys.append(PolygonIsland(lyr, "__ISOLATED__", rect_vertices(ep.guard_outer_bbox), [rect_vertices(ep.cavity_bbox)], tag=f"EDTC_{lyr}_GUARD_{ep.refdes}", is_dynamic=False))
                elif lyr == "10F":
                    for en, eb in zip(emib_names, emib_list):
                        outer_ring = expand_bbox(eb, 150.0)
                        if bboxes_intersect(outer_ring, dbox):
                            clipped_o = clip_poly_to_bbox(rect_vertices(outer_ring), dbox)
                            clipped_v = clip_poly_to_bbox(rect_vertices(eb), _poly_bbox(clipped_o)) if clipped_o else []
                            v_list = [clipped_v] if clipped_v and _poly_area(clipped_v) >= 1600.0 and all(point_in_poly(vx, vy, clipped_o) and min_dist_to_poly_edges(vx, vy, clipped_o) >= 10.0 for vx, vy in clipped_v) else []
                            if clipped_o and _poly_area(clipped_o) >= 1600.0:
                                site_polys.append(PolygonIsland("10F", "__ISOLATED__", clipped_o, voids=v_list, tag=f"EMIB_10F_GR_{en}_{rd}", is_dynamic=False))

        site_own = MultiRailLayerOwnershipIndex(site_polys)
        site_vias: List[ViaRecord] = []
        site_clines: List[ClineRecord] = []
        synthesize_concentric_edtc_stacks(edtc_pins, e_refs, (vnet, "VSS"), site_own, site_vias, pkg_grid)
        _route_ldb_ldc_full_via_and_collar(rd, vnet, all_pwr_pins.get(rd, ()), emib_157, emib_list, site_own, site_vias, site_clines, pkg_grid)
        synthesize_multi_rail_core_pth_and_pp(dbox, (vnet,), site_own, {k: profs[k].die_bbox for k in profs}, {en: eb for en, eb in zip(emib_names, emib_list)}, site_vias, pkg_grid, pth_pitch_x_um=400.0, pth_pitch_y_um=400.0, tag_prefix=rd, edtc_profiles=profs)
        synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(dbox, (vnet,), site_own, site_vias, pkg_grid, pitch_um=320.0, tag_prefix=f"{rd}_MID")

        pkg_polys.extend(site_polys)
        pkg_vias.extend(site_vias)
        pkg_clines.extend(site_clines)
        dk = f"TASK1_{rd}_{vnet}"
        domain_polys_map[dk] = (site_polys, {vnet}, dbox)
        domain_stats[dk] = {"shapes": len(site_polys), "vias": len(site_vias), "clines": len(site_clines), "_vias_list": site_vias, "_vss_bbox": dbox, "_pwr_set": {vnet}}

    # 5. Global Package Ownership -> U25..U40 EMIB C0/CSB + U98 Power Anchors + Global Curved Pockets + Bottom BGA/LSC Routing
    pkg_own = MultiRailLayerOwnershipIndex(pkg_polys)
    global_emib_stats = _route_global_emib_u25_to_u40(all_pwr_pins, pkg_own, pkg_vias, pkg_grid)

    u98_anchors = 0
    for r in all_pwr_pins.get("U98", ()):
        net = r["net_name"]
        if net not in routed_pwr_nets or "SURFACE" not in r["start_layer"]:
            continue
        x, y = float(r["x_um"]), float(r["y_um"])
        if _drop_from_surface_atomic(x, y, net, pkg_own, pkg_vias, pkg_grid, f"U98_ANCHOR_{net}", max_spans=6) > 0:
            u98_anchors += 1

    all_emib_boxes: List[BBox] = list(ALL_EMIB_U25_TO_U40.values())
    for hsite in HBM_SITES:
        tf = _make_hbm_tf(str(hsite["mode"]), float(hsite["dy"]))
        eb_ref = U41_EMIB_BBOX if hsite["variant"] == "A" else (-35738.9, -9436.6, -27112.9, -968.3)
        p1, p2 = tf(eb_ref[0], eb_ref[1]), tf(eb_ref[2], eb_ref[3])
        all_emib_boxes.append((min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])))

    pkg_cavs, pkg_lscs, pkg_del_lscs, raw_cav_res = _compile_all_package_curved_pockets(
        lsc_caps, bga_balls, routed_pwr_nets, pkg_own, all_emib_boxes
    )

    oct8 = _octagonal_8via_offsets(195.0)
    vss_bga_4 = [(-135.0, -135.0), (135.0, -135.0), (-135.0, 135.0), (135.0, 135.0)]
    bga_offsets = {net: oct8 for net in routed_pwr_nets}
    bga_offsets["VSS"] = vss_bga_4

    # Route ALL target BGA balls deduplicated per domain (for clean per-domain audit) + ALL curved LSCs on global pkg_own!
    seen_bga_pts: Set[Tuple[int, int]] = set()
    for dk in sorted(domain_stats):
        st = domain_stats[dk]
        vss_bb: BBox = st["_vss_bbox"]
        pset: Set[str] = st["_pwr_set"]
        dom_bgas: List[Dict[str, str]] = []
        for b in bga_balls:
            n = b["net_name"]
            if n not in pset and n != "VSS":
                continue
            bx, by = float(b["x_um"]), float(b["y_um"])
            if vss_bb[0] <= bx <= vss_bb[2] and vss_bb[1] <= by <= vss_bb[3]:
                bk = (int(round(bx * 10)), int(round(by * 10)))
                if bk not in seen_bga_pts:
                    seen_bga_pts.add(bk)
                    dom_bgas.append(b)
        bot_s = route_bottom_bga_and_lsc_with_atomic_pruning(
            bga_balls=dom_bgas,
            lsc_caps=[],
            target_power_rails=sorted(pset),
            vss_bbox=vss_bb,
            ownership=pkg_own,
            bga_offsets_by_rail=bga_offsets,
            vias_out=pkg_vias,
            grid=pkg_grid,
            tag_prefix=f"{dk}_BOT",
            max_climb_idx=4,
        )
        st["bot"] = bot_s

    lsc_bot_stats = route_bottom_bga_and_lsc_with_atomic_pruning(
        bga_balls=[],
        lsc_caps=[it.to_cap_dict() for it in pkg_lscs],
        target_power_rails=sorted(routed_pwr_nets),
        vss_bbox=(-60000.0, -60000.0, 60000.0, 60000.0),
        ownership=pkg_own,
        bga_offsets_by_rail={},
        vias_out=pkg_vias,
        grid=pkg_grid,
        tag_prefix="PKG_LSC_BOT",
        max_climb_idx=4,
    )

    # Tally per-domain Core PTH & 9F->5F / 9B->5B continuity accurately (from pkg_vias inside each domain's bbox)
    for dk, st in domain_stats.items():
        dom_vias: List[ViaRecord] = st.pop("_vias_list")
        st.pop("_vss_bbox")
        st.pop("_pwr_set")
        # Include any global vias added inside this domain (e.g. U25..U40) by tag or bounding box
        col_9f = sum(1 for v in dom_vias if v.net_name == "VSS" and v.start_layer == "6F" and v.end_layer == "5F")
        col_9b = sum(1 for v in dom_vias if v.net_name == "VSS" and v.start_layer == "5B" and v.end_layer == "6B")
        pth_c = sum(1 for v in dom_vias if v.start_layer == "2FCI" and v.end_layer == "2BCI")
        st["vss_9f_5f_cols"] = col_9f
        st["vss_9b_5b_cols"] = col_9b
        st["core_pth_cols"] = pth_c
        st["vias"] = len(dom_vias)

    t_synth = time.perf_counter() - t2

    # 6. Global Audits (Zero Via Overlap + Inter-Domain Polygon Clearance + Curved Cavity DRC)
    t3 = time.perf_counter()
    pkg_audit = audit_via_continuity_and_zero_overlap(pkg_vias)
    poly_audit = check_inter_domain_polygon_clearances(pkg_polys)
    cav_drc = {
        "total_cavities": len(raw_cav_res),
        "all_cavities_pass": all(bool(r.drc_metrics["drc_pass"]) for r in raw_cav_res),
        "failed_pockets": [r.pocket_id for r in raw_cav_res if not r.drc_metrics["drc_pass"]],
    }
    all_24_stitch_pass = all(domain_stats[dk]["vss_9f_5f_cols"] > 0 and domain_stats[dk]["vss_9b_5b_cols"] > 0 for dk in domain_stats)
    t_audit = time.perf_counter() - t3

    recipe_file = out_dir / "AllDies_AllRails_27Layer_Master_Recipe.txt"
    write_master_recipe(recipe_file, pkg_polys, pkg_cavs, pkg_vias, pkg_clines, pkg_lscs, pkg_del_lscs)

    all_ok = (
        bool(pkg_audit["zero_via_overlap_pass"])
        and bool(poly_audit["polygon_clearance_pass"])
        and bool(cav_drc["all_cavities_pass"])
        and all_24_stitch_pass
    )
    sandbox_summary = {
        "status": "SANDBOX_COMPILED_DRC_PASS" if all_ok else "SANDBOX_DRC_FAIL",
        "timing_sec": {
            "load_csvs": round(t_load, 2),
            "ref_templates": round(t_ref, 2),
            "all_24_sites_synth": round(t_synth, 2),
            "global_audit": round(t_audit, 2),
            "total_sandbox_sec": round(time.perf_counter() - t0, 2),
        },
        "totals": {
            "domains_built": len(domain_stats),
            "routed_power_nets": len(routed_pwr_nets),
            "polygons": len(pkg_polys),
            "dynamic_polygons": sum(1 for p in pkg_polys if p.is_dynamic),
            "static_shapes_bars": sum(1 for p in pkg_polys if not p.is_dynamic),
            "vias": len(pkg_vias),
            "clines": len(pkg_clines),
            "curved_cavities": len(pkg_cavs),
            "base_180_lscs": len(pkg_lscs),
            "deleted_old_lscs": len(pkg_del_lscs),
            "u98_anchors": u98_anchors,
            "lsc_bot_stats": lsc_bot_stats,
            "global_emib_u25_u40": global_emib_stats,
        },
        "all_24_vss_9f_5f_9b_5b_pass": all_24_stitch_pass,
        "zero_via_overlap_audit": pkg_audit,
        "polygon_clearance_audit": poly_audit,
        "curved_cavity_audit": cav_drc,
        "recipe_file": str(recipe_file),
        "domain_stats": domain_stats,
    }

    svg_paths = _render_full_package_svgs(out_dir, pkg_polys, pkg_cavs, pkg_lscs, bga_balls, domain_stats, sandbox_summary)
    sandbox_summary["visual_gate_svgs"] = svg_paths
    (out_dir / "AllDies_AllRails_Sandbox_Audit.json").write_text(json.dumps(sandbox_summary, indent=2), encoding="utf-8")

    planned_out = (out_mcm_path or ((_eff_wd / f"{src_mcm.stem}_AllDies_AllRails_27Layer.mcm") if _is_custom and _eff_wd else (WORKSPACE / "agent04_pdn_architect" / "MCM_test" / "PDN_test_AllDies_AllRails_27Layer.mcm"))).resolve()
    gate_payload = {
        "status": "READY_FOR_FINAL_HUMAN_CONFIRMATION" if all_ok else "DRC_FAILED_HOLD",
        "source_mcm_readonly": str(src_mcm),
        "planned_output_mcm": str(planned_out),
        "sandbox_status": sandbox_summary["status"],
        "totals": sandbox_summary["totals"],
        "zero_via_overlap_pass": pkg_audit["zero_via_overlap_pass"],
        "polygon_clearance_pass": poly_audit["polygon_clearance_pass"],
        "curved_cavities_pass": cav_drc["all_cavities_pass"],
        "all_24_vss_9f_5f_9b_5b_pass": all_24_stitch_pass,
        "visual_gate_svgs": svg_paths,
        "recipe_file": str(recipe_file),
    }
    (out_dir / "AllDies_AllRails_Confirmation_Gate.json").write_text(json.dumps(gate_payload, indent=2), encoding="utf-8")

    if dry_run_only or out_mcm_path is None:
        return sandbox_summary
    if not all_ok:
        raise RuntimeError(f"GLOBAL_DRC_FAILED: via={pkg_audit['overlap_samples']} poly={poly_audit['samples']} cav={cav_drc['failed_pockets']}")

    # 7. Headless Cadence APD 25.1 Batch Build into Brand-New .mcm (`PDN_test.mcm` strictly read-only!)
    return _execute_stage4_apd_build(src_mcm, out_mcm_path, out_dir, recipe_file, sandbox_summary, timeout_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build All-Dies, All-Rails 27-Layer PDN from Working-Folder MCM_template or PDN_test.mcm")
    parser.add_argument("--work-dir", default=None, help="Working folder path (defaults to SUBSTRATE_WORK_DIR)")
    parser.add_argument("--src-mcm", default=None, help="Read-only source .mcm template (defaults to <work-dir>/MCM_template/*.mcm)")
    parser.add_argument("--pins-csv", type=str, default=str(DEFAULT_PINS_CSV))
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--out-mcm", type=str, default=None)
    parser.add_argument("--sandbox-only", action="store_true")
    parser.add_argument("--reuse-sandbox", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    eff_wd, is_custom_wd, eff_src_mcm, _s1 = _resolve_pdn_io_context(
        src_mcm_path=Path(args.src_mcm) if args.src_mcm else None,
        work_dir=args.work_dir,
    )
    base_dir = eff_wd if (is_custom_wd and eff_wd) else WORKSPACE
    if args.out_dir:
        out_dir_p = Path(args.out_dir)
        out_dir = out_dir_p if out_dir_p.is_absolute() else (base_dir / out_dir_p)
    else:
        out_dir = (eff_wd / "reports" / "all_dies_all_rails") if (is_custom_wd and eff_wd) else (WORKSPACE / "agent04_pdn_architect" / "reports" / "all_dies_all_rails")

    if args.out_mcm:
        out_mcm_p = Path(args.out_mcm)
        out_mcm = out_mcm_p if out_mcm_p.is_absolute() else (base_dir / out_mcm_p)
    else:
        out_mcm = (eff_wd / f"{eff_src_mcm.stem}_AllDies_AllRails_27Layer.mcm") if (is_custom_wd and eff_wd) else (WORKSPACE / "agent04_pdn_architect" / "MCM_test" / "PDN_test_AllDies_AllRails_27Layer.mcm")

    res = synthesize_full_package_all_dies(
        pins_csv=Path(args.pins_csv),
        out_dir=out_dir,
        dry_run_only=args.sandbox_only,
        out_mcm_path=out_mcm,
        timeout_sec=args.timeout,
        reuse_sandbox=args.reuse_sandbox,
        src_mcm_path=eff_src_mcm,
        work_dir=args.work_dir,
    )
    print(json.dumps({
        "status": res["status"],
        "totals": res.get("totals") or res.get("sandbox_summary", {}).get("totals"),
        "timing_sec": res.get("timing_sec") or res.get("sandbox_summary", {}).get("timing_sec"),
        "apd_duration_sec": res.get("apd_duration_sec"),
        "output_mcm_path": res.get("output_mcm_path"),
        "output_mcm_size_bytes": res.get("output_mcm_size_bytes"),
        "apd_report": res.get("apd_report"),
    }, indent=2))


if __name__ == "__main__":
    main()
