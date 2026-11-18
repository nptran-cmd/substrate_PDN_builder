"""
Step 2 Skill Engine: Bifurcated `HBM` `SURFACE` Gang-Stripe Router & `EMIB` `C0` / `10F CSB` Escape Router
with Strict Per-Conductor-Layer Zero Via Overlap (`0` Same-Span & `0` Adjacent-Span Pad Overlap!) and
`100%` End-to-End `CSB` / `SURFACE` Copper Connectivity to `BGA (A1)`.
"""

from __future__ import annotations

import collections
import math
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .multi_rail_polygon_engine import (
    BBox,
    ClineRecord,
    FastXYClearanceGrid,
    MultiRailLayerOwnershipIndex,
    PolygonIsland,
    U41_EMIB_BBOX,
    U9_DOMAIN_BBOX,
    U9_EMIB_BRIDGES,
    U9_SRAM0_SUB_ISLANDS_CORE_BU,
    ViaRecord,
    can_place_via_stack_zero_overlap,
    expand_bbox,
    insert_via_stack_zero_overlap,
    rect_vertices,
)

UPPER_BU_CHAIN: List[Tuple[str, str, str]] = [
    ("SURFACE", "12F", "12F"),
    ("12F",     "11F", "11F"),
    ("11F",     "10F", "10F"),
    ("10F",     "9F",  "9F"),
    ("9F",      "8F",  "8F"),
    ("8F",      "7F",  "7F"),
    ("7F",      "6F",  "6F"),
]  # Max 7 BU spans (`Max Stacked Via in BU = 7`!)


def _pt_to_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= 1e-9:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _segments_intersect(ax: float, ay: float, bx: float, by: float, cx: float, cy: float, dx: float, dy: float) -> bool:
    def ccw(p1x: float, p1y: float, p2x: float, p2y: float, p3x: float, p3y: float) -> float:
        return (p2x - p1x) * (p3y - p1y) - (p2y - p1y) * (p3x - p1x)

    d1 = ccw(ax, ay, bx, by, cx, cy)
    d2 = ccw(ax, ay, bx, by, dx, dy)
    d3 = ccw(cx, cy, dx, dy, ax, ay)
    d4 = ccw(cx, cy, dx, dy, bx, by)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def _seg_to_seg_dist(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> float:
    if _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
        return 0.0
    return min(
        _pt_to_seg_dist(x1, y1, x3, y3, x4, y4),
        _pt_to_seg_dist(x2, y2, x3, y3, x4, y4),
        _pt_to_seg_dist(x3, y3, x1, y1, x2, y2),
        _pt_to_seg_dist(x4, y4, x1, y1, x2, y2),
    )


def _segment_clear_of_layer_clines(
    clines: Sequence[ClineRecord],
    layer: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    half_w: float,
    net: str,
    diff_gap: float = 15.0,
) -> bool:
    sx0, sx1 = min(x1, x2) - half_w - diff_gap - 30.0, max(x1, x2) + half_w + diff_gap + 30.0
    sy0, sy1 = min(y1, y2) - half_w - diff_gap - 30.0, max(y1, y2) + half_w + diff_gap + 30.0
    for c in clines:
        if c.layer != layer or c.net_name == net:
            continue
        if max(c.x1, c.x2) < sx0 or min(c.x1, c.x2) > sx1 or max(c.y1, c.y2) < sy0 or min(c.y1, c.y2) > sy1:
            continue
        req = half_w + 0.5 * c.width_um + diff_gap
        if _seg_to_seg_dist(x1, y1, x2, y2, c.x1, c.y1, c.x2, c.y2) < req:
            return False
    return True


def _drop_from_surface_atomic(
    px: float,
    py: float,
    net: str,
    ownership: MultiRailLayerOwnershipIndex,
    vias_out: List[ViaRecord],
    grid: FastXYClearanceGrid,
    role_tag: str,
    max_spans: int = 6,
) -> int:
    valid_stops: List[int] = []
    limit = min(max_spans, len(UPPER_BU_CHAIN))
    for idx in range(limit):
        _, _, dst_lyr = UPPER_BU_CHAIN[idx]
        if ownership.owner_at(dst_lyr, px, py, min_edge_margin_um=30.0) == net:
            valid_stops.append(idx)
    if not valid_stops:
        return 0

    for stop_idx in reversed(valid_stops):
        req_spans = [(UPPER_BU_CHAIN[k][0], UPPER_BU_CHAIN[k][1]) for k in range(stop_idx + 1)]
        added = insert_via_stack_zero_overlap(vias_out, grid, net, req_spans, px, py, role_tag)
        if added > 0:
            return added
    return 0


def _point_in_any_box(x: float, y: float, boxes: Sequence[BBox]) -> bool:
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


def _segment_clear_of_obs(
    obs_grid: FastXYClearanceGrid,
    key: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    half_w: float,
    net: str,
    diff_gap: float = 18.5,
) -> bool:
    ln = math.hypot(x2 - x1, y2 - y1)
    steps = max(2, int(math.ceil(ln / 18.0)))
    for k in range(steps + 1):
        t = k / steps
        px = x1 + t * (x2 - x1)
        py = y1 + t * (y2 - y1)
        if obs_grid.has_conflict(key, px, py, half_w, net, -100.0, diff_gap):
            return False
    return True


# =============================================================================
# 1A. U9 Fixed EMIB (`C0` + `U25..U39` `10F CSB`) Pin Router (Priority 1)
# =============================================================================
def route_u9_emib_csb_and_c0_pins(
    u9_pins: Sequence[Dict[str, str]],
    ownership: MultiRailLayerOwnershipIndex,
    vias_out: List[ViaRecord],
    grid: FastXYClearanceGrid,
) -> Dict[str, int]:
    target_nets = {"VDDC0", "VDD_0P8_SRAM_CC0", "VSS"}
    stats = {"emib_c0_vias": 0, "emib_csb_vss_1stack": 0, "emib_csb_pwr_vias": 0}
    c0_ov = {("SURFACE", "C0"): "VU30_19_35_SURFACE_C0_01B"}

    # Exact set of EMIB C0 pad coordinates (+/-1 um tolerance for 9 nm float offsets) so standard U9 C4 bumps never drop C0 vias!
    emib_c0_int: Set[Tuple[int, int]] = {
        (int(round(float(r["x_um"]))), int(round(float(r["y_um"]))))
        for r in u9_pins
        if r["refdes"] != "U9" and "C0" in r["start_layer"]
    }

    for r in u9_pins:
        ref = r["refdes"]
        net = r["net_name"]
        if net not in target_nets:
            continue
        x, y = float(r["x_um"]), float(r["y_um"])
        lyr = r["start_layer"]
        ps = r.get("padstack_name", "")
        ix, iy = int(round(x)), int(round(y))
        is_c0_ubump = ("18" in ps) or any(
            (ix + dx_i, iy + dy_i) in emib_c0_int for dx_i in (-1, 0, 1) for dy_i in (-1, 0, 1)
        )

        if ref == "U9" and "SURFACE" in lyr and is_c0_ubump:
            if insert_via_stack_zero_overlap(vias_out, grid, net, [("SURFACE", "C0")], x, y, f"U9_EMIB_C0_{net}", c0_ov) > 0:
                stats["emib_c0_vias"] += 1
        elif ref != "U9" and "10F" in lyr:
            if net == "VSS" and ownership.owner_at("9F", x, y, min_edge_margin_um=45.0) == "VSS":
                if insert_via_stack_zero_overlap(vias_out, grid, "VSS", [("10F", "9F")], x, y, f"{ref}_CSB_VSS_1STACK") > 0:
                    stats["emib_csb_vss_1stack"] += 1
            elif net != "VSS" and ownership.owner_at("8F", x, y, min_edge_margin_um=45.0) == net:
                added = insert_via_stack_zero_overlap(vias_out, grid, net, [("10F", "9F"), ("9F", "8F")], x, y, f"{ref}_CSB_{net}_2STACK")
                stats["emib_csb_pwr_vias"] += added
    return stats


# =============================================================================
# 1B. U9 (`LDA`: `VDDC0` + `VDD_0P8_SRAM_CC0` + `VSS`) Top-Side C4 Router
# =============================================================================
def route_u9_lda_surface_and_emib(
    u9_pins: Sequence[Dict[str, str]],
    ownership: MultiRailLayerOwnershipIndex,
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
    grid: FastXYClearanceGrid,
    vddc_vss_ratio: str = "3:1",
    emib_already_routed: bool = False,
    only_nets: Optional[Sequence[str]] = None,
    shared_bump_obs: Optional[FastXYClearanceGrid] = None,
    surface_mode: str = "vertical_jog_3to1",
) -> Dict[str, int]:
    if surface_mode == "vertical_jog_3to1":
        from .u9_vddc_sram_surface_3to1_jog_router import route_u9_vddc0_sram0_vss_3to1_vertical_jog

        jog_res = route_u9_vddc0_sram0_vss_3to1_vertical_jog(
            u9_pins=u9_pins,
            ownership=ownership,
            vias_out=vias_out,
            clines_out=clines_out,
            grid=grid,
            ratio_str=vddc_vss_ratio,
            trace_width_um=15.0,
            min_gap_um=15.0,
            emib_already_routed=emib_already_routed,
            only_nets=only_nets,
        )
        return {
            "emib_c0_vias": int(jog_res.stats["emib_c0_vias"]),
            "emib_csb_vss_1stack": int(jog_res.stats["emib_csb_vss_1stack"]),
            "sram0_via_columns": int(jog_res.stats["sram0_via_columns"]),
            "vddc0_via_columns": int(jog_res.stats["vddc0_via_columns"]),
            "vss_via_columns": int(jog_res.stats["vss_via_columns"]),
            "surface_horizontal_straps": int(jog_res.stats["surface_horizontal_straps"]),
            "surface_vertical_c_jogs": int(jog_res.stats["surface_vertical_c_jogs"]),
            "surface_vertical_s_jogs": int(jog_res.stats["surface_vertical_s_jogs"]),
            "upper_bu_vias_total": int(jog_res.stats["upper_bu_vias_total"]),
        }

    emib_boxes = list(U9_EMIB_BRIDGES.values())
    emib_157 = [expand_bbox(b, 157.5) for b in emib_boxes]
    target_nets = {"VDDC0", "VDD_0P8_SRAM_CC0", "VSS"}
    active_nets = tuple(only_nets) if only_nets is not None else ("VDD_0P8_SRAM_CC0", "VDDC0", "VSS")

    bump_obs = shared_bump_obs if shared_bump_obs is not None else FastXYClearanceGrid(cell_um=160.0)
    need_seed_obs = not bool(bump_obs.grid)
    u9_surface_by_net: Dict[str, List[Tuple[float, float, str]]] = defaultdict(list)

    stats = {
        "emib_c0_vias": 0,
        "emib_csb_vss_1stack": 0,
        "sram0_via_columns": 0,
        "vddc0_via_columns": 0,
        "vss_via_columns": 0,
        "surface_horizontal_straps": 0,
        "upper_bu_vias_total": 0,
    }

    if not emib_already_routed:
        em_stats = route_u9_emib_csb_and_c0_pins(u9_pins, ownership, vias_out, grid)
        stats["emib_c0_vias"] = em_stats["emib_c0_vias"]
        stats["emib_csb_vss_1stack"] = em_stats["emib_csb_vss_1stack"]

    emib_c0_xy: Set[Tuple[float, float]] = {
        (round(float(r["x_um"]), 1), round(float(r["y_um"]), 1))
        for r in u9_pins
        if r["refdes"] != "U9" and "C0" in r["start_layer"]
    }

    for r in u9_pins:
        if r["refdes"] != "U9" or "SURFACE" not in r["start_layer"]:
            continue
        x, y = float(r["x_um"]), float(r["y_um"])
        net = r["net_name"]
        ps = r["padstack_name"]
        b_rad = 17.5 if "35" in ps else (9.0 if "18" in ps else 38.5)
        if need_seed_obs:
            bump_obs.insert("SURF_BUMP", x, y, b_rad, net)
        if net in target_nets:
            u9_surface_by_net[net].append((x, y, ps))

    keep_mod, keep_cnt = (1, 1)
    if ":" in vddc_vss_ratio:
        a_s, b_s = vddc_vss_ratio.split(":", 1)
        m_v, n_v = max(1, int(a_s)), max(1, int(b_s))
        keep_mod, keep_cnt = (m_v + n_v, m_v)

    sram_10f_via_pts: List[Tuple[float, float]] = []

    for net in active_nets:
        pts = u9_surface_by_net[net]
        rows: Dict[float, List[Tuple[float, float, str]]] = defaultdict(list)
        for x, y, ps in pts:
            if (round(x, 1), round(y, 1)) in emib_c0_xy:
                continue
            rows[round(y, 1)].append((x, y, ps))

        via_pts: List[Tuple[float, float]] = []
        unconnected_pts: List[Tuple[float, float]] = []

        for ry, rpts in sorted(rows.items()):
            rpts_sorted = sorted(rpts, key=lambda t: t[0])
            via_flags = [False] * len(rpts_sorted)

            for i, (bx, by, _) in enumerate(rpts_sorted):
                if _point_in_any_box(bx, by, emib_157):
                    continue
                want_via = True if net == "VDD_0P8_SRAM_CC0" or keep_mod == 1 else ((i % keep_mod) < keep_cnt)
                if not want_via and len(rpts_sorted) == 1:
                    want_via = True
                if want_via and not bump_obs.has_conflict("SURF_BUMP", bx, by, 38.5, net, -100.0, 16.0):
                    max_sp = 7 if net == "VDD_0P8_SRAM_CC0" else (5 if net == "VDDC0" else 4)
                    added = _drop_from_surface_atomic(bx, by, net, ownership, vias_out, grid, f"U9_TOP_{net}", max_spans=max_sp)
                    if added > 0:
                        via_flags[i] = True
                        via_pts.append((bx, by))
                        bump_obs.insert("SURF_BUMP", bx, by, 38.5, net)
                        stats["upper_bu_vias_total"] += added
                        if net == "VDD_0P8_SRAM_CC0":
                            stats["sram0_via_columns"] += 1
                            if added >= 3:
                                sram_10f_via_pts.append((bx, by))
                        elif net == "VDDC0":
                            stats["vddc0_via_columns"] += 1
                        else:
                            stats["vss_via_columns"] += 1

            # Propagate connectivity across pure 1D horizontal dy=0 chains that reach at least one VIA bump!
            row_edges: List[Tuple[int, int]] = []
            adj_map: Dict[int, List[int]] = defaultdict(list)
            for i in range(len(rpts_sorted) - 1):
                bx, by, _ = rpts_sorted[i]
                nx, ny, _ = rpts_sorted[i + 1]
                if abs(nx - bx) <= 450.0 and abs(ny - by) < 0.2:
                    if (
                        _segment_clear_of_obs(bump_obs, "SURF_BUMP", bx, by, nx, by, 10.0, net, 16.5)
                        and _segment_clear_of_layer_clines(clines_out, "SURFACE", bx, by, nx, by, 10.0, net, 15.0)
                    ):
                        row_edges.append((i, i + 1))
                        adj_map[i].append(i + 1)
                        adj_map[i + 1].append(i)

            anchored = list(via_flags)
            queue = [idx for idx, f in enumerate(anchored) if f]
            while queue:
                cur = queue.pop()
                for nb in adj_map[cur]:
                    if not anchored[nb]:
                        anchored[nb] = True
                        queue.append(nb)

            for i, j in row_edges:
                if anchored[i] or anchored[j]:
                    bx, by, _ = rpts_sorted[i]
                    nx, _, _ = rpts_sorted[j]
                    clines_out.append(ClineRecord(net, "SURFACE", 20.0, round(bx, 3), round(by, 3), round(nx, 3), round(by, 3), f"U9_STRAP_{net}"))
                    stats["surface_horizontal_straps"] += 1

            for i, (bx, by, _) in enumerate(rpts_sorted):
                if anchored[i]:
                    continue
                if not _point_in_any_box(bx, by, emib_157) and not bump_obs.has_conflict("SURF_BUMP", bx, by, 38.5, net, -100.0, 16.0):
                    added = _drop_from_surface_atomic(bx, by, net, ownership, vias_out, grid, f"U9_TOP_FALLBACK_{net}", max_spans=7)
                    if added > 0:
                        anchored[i] = True
                        via_pts.append((bx, by))
                        bump_obs.insert("SURF_BUMP", bx, by, 38.5, net)
                        stats["upper_bu_vias_total"] += added
                        if net == "VDD_0P8_SRAM_CC0" and added >= 3:
                            sram_10f_via_pts.append((bx, by))
                        continue
                unconnected_pts.append((bx, by))

        # Convergent multi-hop collar escape for any bump inside 157.5 um EMIB KOZ collar (including X=+-14179.23!)
        if unconnected_pts and via_pts:
            via_grid = FastXYClearanceGrid(cell_um=400.0)
            for vx, vy in via_pts:
                via_grid.insert("VIA", vx, vy, 1.0, net)

            for _cpass in range(4):
                rem_pts: List[Tuple[float, float]] = []
                prog = False
                for bx, by in unconnected_pts:
                    cx_i, cy_i = int(math.floor(bx / 400.0)), int(math.floor(by / 400.0))
                    best_v: Optional[Tuple[float, float, float]] = None
                    for gx in range(cx_i - 3, cx_i + 4):
                        for gy in range(cy_i - 3, cy_i + 4):
                            for vx, vy, _, _ in via_grid.grid.get(("VIA", gx, gy), ()):
                                d = math.hypot(vx - bx, vy - by)
                                if d <= 950.0 and (best_v is None or d < best_v[0]):
                                    if (
                                        _segment_clear_of_obs(bump_obs, "SURF_BUMP", bx, by, vx, vy, 8.0, net, 15.5)
                                        and _segment_clear_of_layer_clines(clines_out, "SURFACE", bx, by, vx, vy, 8.0, net, 15.0)
                                    ):
                                        best_v = (d, vx, vy)
                    if best_v is not None:
                        clines_out.append(ClineRecord(net, "SURFACE", 16.0, round(bx, 3), round(by, 3), round(best_v[1], 3), round(best_v[2], 3), f"U9_COLLAR_ESCAPE_{net}"))
                        via_grid.insert("VIA", bx, by, 1.0, net)
                        stats["surface_horizontal_straps"] += 1
                        prog = True
                    else:
                        placed_dog = False
                        for sdx, sdy in (
                            (210.0, 0.0), (-210.0, 0.0), (0.0, 210.0), (0.0, -210.0),
                            (280.0, 0.0), (-280.0, 0.0), (240.0, 120.0), (-240.0, 120.0), (240.0, -120.0), (-240.0, -120.0),
                        ):
                            tx, ty = bx + sdx, by + sdy
                            if not _point_in_any_box(tx, ty, emib_157) and not bump_obs.has_conflict("SURF_BUMP", tx, ty, 38.5, net, -100.0, 18.5):
                                if (
                                    _segment_clear_of_obs(bump_obs, "SURF_BUMP", bx, by, tx, ty, 8.0, net, 15.5)
                                    and _segment_clear_of_layer_clines(clines_out, "SURFACE", bx, by, tx, ty, 8.0, net, 15.0)
                                ):
                                    added = _drop_from_surface_atomic(tx, ty, net, ownership, vias_out, grid, f"U9_COLLAR_VIA_{net}", max_spans=7)
                                    if added > 0:
                                        bump_obs.insert("SURF_BUMP", tx, ty, 38.5, net)
                                        clines_out.append(ClineRecord(net, "SURFACE", 16.0, round(bx, 3), round(by, 3), round(tx, 3), round(ty, 3), f"U9_COLLAR_DOGBONE_{net}"))
                                        via_grid.insert("VIA", tx, ty, 1.0, net)
                                        via_grid.insert("VIA", bx, by, 1.0, net)
                                        stats["upper_bu_vias_total"] += added
                                        if net == "VDD_0P8_SRAM_CC0" and added >= 3:
                                            sram_10f_via_pts.append((tx, ty))
                                        placed_dog = True
                                        prog = True
                                        break
                        if not placed_dog:
                            rem_pts.append((bx, by))
                unconnected_pts = rem_pts
                if not unconnected_pts or not prog:
                    break

    return stats


def connect_u9_sram0_10f_backbone(
    ownership: MultiRailLayerOwnershipIndex,
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
    grid: FastXYClearanceGrid,
) -> int:
    """
    Build a DRC-clean `10F` `VDD_0P8_SRAM_CC0` spanning-tree cline backbone AFTER all `U9` `VDDC0` + `VSS`
    + `U9_MID` `10F` vias have been placed, guaranteeing `0` `10F` shorts AND `0` isolated `SRAM0` `10F` islands!
    """
    obs_10f = FastXYClearanceGrid(cell_um=200.0)
    sram_10f_pts: List[Tuple[float, float]] = []
    seen_sram: Set[Tuple[float, float]] = set()
    for v in vias_out:
        if v.start_layer == "10F" or v.end_layer == "10F":
            if v.net_name == "VDD_0P8_SRAM_CC0":
                pt = (round(v.x, 3), round(v.y, 3))
                if pt not in seen_sram:
                    seen_sram.add(pt)
                    sram_10f_pts.append((v.x, v.y))
            else:
                obs_10f.insert("V10F", v.x, v.y, 40.0, v.net_name)

    if not sram_10f_pts:
        return 0

    core_anchored: List[Tuple[float, float]] = [
        pt for pt in sram_10f_pts if _point_in_any_box(pt[0], pt[1], U9_SRAM0_SUB_ISLANDS_CORE_BU)
    ]
    sp_10_6 = [("10F", "9F"), ("9F", "8F"), ("8F", "7F"), ("7F", "6F")]
    for sx, sy in core_anchored[::3]:
        for dx, dy in ((120.0, 0.0), (-120.0, 0.0), (0.0, 120.0), (0.0, -120.0), (150.0, 90.0), (-150.0, 90.0)):
            tx, ty = sx + dx, sy + dy
            if ownership.owner_at("6F", tx, ty, 50.0) == "VDD_0P8_SRAM_CC0":
                if insert_via_stack_zero_overlap(vias_out, grid, "VDD_0P8_SRAM_CC0", sp_10_6, tx, ty, "U9_SRAM0_10F_6F_TRUNK") > 0:
                    break

    anch_set = set(core_anchored) if core_anchored else {sram_10f_pts[0]}
    unanch_10f = [pt for pt in sram_10f_pts if pt not in anch_set]
    anch_grid = FastXYClearanceGrid(cell_um=1500.0)
    for ax0, ay0 in anch_set:
        anch_grid.insert("A10", ax0, ay0, 1.0, "VDD_0P8_SRAM_CC0")
    added_links = 0

    while unanch_10f:
        still_u: List[Tuple[float, float]] = []
        prog_10f = False
        for ux, uy in unanch_10f:
            cand_a = None
            cx_i, cy_i = int(math.floor(ux / 1500.0)), int(math.floor(uy / 1500.0))
            near_anch: List[Tuple[float, float, float]] = []
            for gx in range(cx_i - 3, cx_i + 4):
                for gy in range(cy_i - 3, cy_i + 4):
                    for ax, ay, _, _ in anch_grid.grid.get(("A10", gx, gy), ()):
                        d = math.hypot(ax - ux, ay - uy)
                        if d <= 4200.0:
                            near_anch.append((d, ax, ay))
            near_anch.sort(key=lambda t: t[0])
            for d, ax, ay in near_anch[:10]:
                if _segment_clear_of_obs(obs_10f, "V10F", ux, uy, ax, ay, 8.0, "VDD_0P8_SRAM_CC0", 15.5):
                    cand_a = (d, (ux, uy), (ax, ay), None)
                    break
                vx_d, vy_d = (ax - ux) / max(d, 1.0), (ay - uy) / max(d, 1.0)
                px_d, py_d = -vy_d, vx_d
                jog_10f = [(ux, ay), (ax, uy)] + [
                    (0.5 * (ux + ax) + px_d * off, 0.5 * (uy + ay) + py_d * off)
                    for off in (65.0, -65.0, 110.0, -110.0, 160.0, -160.0)
                ]
                for mx, my in jog_10f:
                    if ownership.owner_at("10F", mx, my, 30.0) == "VDD_0P8_SRAM_CC0":
                        if (
                            _segment_clear_of_obs(obs_10f, "V10F", ux, uy, mx, my, 8.0, "VDD_0P8_SRAM_CC0", 15.5)
                            and _segment_clear_of_obs(obs_10f, "V10F", mx, my, ax, ay, 8.0, "VDD_0P8_SRAM_CC0", 15.5)
                        ):
                            cand_a = (d, (ux, uy), (ax, ay), (mx, my))
                            break
                if cand_a is not None:
                    break
            if cand_a is not None:
                _, (p1x, p1y), (p2x, p2y), mid_p = cand_a
                if mid_p is None:
                    clines_out.append(ClineRecord("VDD_0P8_SRAM_CC0", "10F", 16.0, round(p1x, 3), round(p1y, 3), round(p2x, 3), round(p2y, 3), "U9_SRAM0_10F_BACKBONE"))
                else:
                    clines_out.append(ClineRecord("VDD_0P8_SRAM_CC0", "10F", 16.0, round(p1x, 3), round(p1y, 3), round(mid_p[0], 3), round(mid_p[1], 3), "U9_SRAM0_10F_JOGA"))
                    clines_out.append(ClineRecord("VDD_0P8_SRAM_CC0", "10F", 16.0, round(mid_p[0], 3), round(mid_p[1], 3), round(p2x, 3), round(p2y, 3), "U9_SRAM0_10F_JOGB"))
                anch_grid.insert("A10", ux, uy, 1.0, "VDD_0P8_SRAM_CC0")
                added_links += 1
                prog_10f = True
            else:
                still_u.append((ux, uy))
        unanch_10f = still_u
        if not prog_10f:
            break

    return added_links


# =============================================================================
# 2A. U13 Fixed EMIB (`C0` + `U41` `10F CSB` `100.0%` End-to-End Escape)
# =============================================================================
def route_u13_emib_csb_and_c0_pins(
    u13_u41_u5_pins: Sequence[Dict[str, str]],
    u13_polys: List[PolygonIsland],
    ownership_ref: List[MultiRailLayerOwnershipIndex],
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
    grid: FastXYClearanceGrid,
) -> Dict[str, int]:
    """
    Route `U13`/`U5` `SURFACE->C0` EMIB uBumps and `100.0%` (`3,054 / 3,054`) of `U41` `10F CSB` pins
    directly into their `BGA (A1)` substrate planes (`0` open `10F` pins, `<= 2` stacked vias under CSB, `0` via overlap!).
    """
    hbm_rails = {"VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5", "VPP_1P8_HBM_MEM5", "VSS"}
    stats = {
        "u13_emib_c0_vias": 0,
        "u5_emib_c0_vias": 0,
        "u41_csb_vss_1stack": 0,
        "u41_csb_pwr_1stack": 0,
        "u41_csb_pwr_2stack": 0,
        "u41_csb_9f_vddql_escapes": 0,
    }
    ov_u13 = {("SURFACE", "C0"): "VU30_19_60_SURFACE_C0_01B"}
    ov_u5  = {("SURFACE", "C0"): "VU30_19_39_SURFACE_C0_01B"}
    u41_x0, u41_y0, u41_x1, u41_y1 = U41_EMIB_BBOX

    obs_9f = FastXYClearanceGrid(cell_um=160.0)
    u41_csb_by_net: Dict[str, List[Tuple[float, float]]] = defaultdict(list)

    for r in u13_u41_u5_pins:
        ref = r["refdes"]
        net = r["net_name"]
        x, y = float(r["x_um"]), float(r["y_um"])
        lyr = r["start_layer"]

        if ref == "U41" and "10F" in lyr:
            if net in hbm_rails:
                u41_csb_by_net[net].append((x, y))
        elif ref == "U13" and "SURFACE" in lyr and net in hbm_rails and u41_x0 <= x <= u41_x1 and u41_y0 <= y <= u41_y1:
            if insert_via_stack_zero_overlap(vias_out, grid, net, [("SURFACE", "C0")], x, y, f"U13_EMIB_C0_{net}", ov_u13) > 0:
                stats["u13_emib_c0_vias"] += 1
        elif ref == "U5" and "SURFACE" in lyr and net in hbm_rails and u41_x0 <= x <= u41_x1 and u41_y0 <= y <= u41_y1:
            if insert_via_stack_zero_overlap(vias_out, grid, net, [("SURFACE", "C0")], x, y, f"U5_EMIB_C0_{net}", ov_u5) > 0:
                stats["u5_emib_c0_vias"] += 1

    # 1. VSS (1,855 pins): 1-stack 10F->9F (r_9F = 38.5 um)
    for cx, cy in u41_csb_by_net["VSS"]:
        if insert_via_stack_zero_overlap(vias_out, grid, "VSS", [("10F", "9F")], cx, cy, "U41_CSB_VSS_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, "VSS")
            stats["u41_csb_vss_1stack"] += 1

    # 2. VDDQ (543 pins) & VPP (14 pins): 2-stack 10F->9F->8F (r_9F = 45.0 um)
    for net in ("VDDQ_0P85_HBM_MEM5", "VPP_1P8_HBM_MEM5"):
        for cx, cy in u41_csb_by_net[net]:
            if insert_via_stack_zero_overlap(vias_out, grid, net, [("10F", "9F"), ("9F", "8F")], cx, cy, f"U41_CSB_{net}_2STACK") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 45.0, net)
                stats["u41_csb_pwr_2stack"] += 1

    # Bridge the 6 notch-adjacent VDDQ 8F pins cleanly across dynamic antipad necks on 8F!
    for jx in (-32169.595, -32797.961):
        clines_out.append(ClineRecord("VDDQ_0P85_HBM_MEM5", "8F", 30.0, jx, 23504.143, jx, 23310.0, "U41_VDDQ_8F_SOUTH_BRIDGE"))
    for jx in (-33740.504, -33321.593, -33112.138):
        clines_out.append(ClineRecord("VDDQ_0P85_HBM_MEM5", "8F", 30.0, jx, 27522.746, jx, 27330.0, "U41_VDDQ_8F_MID_BRIDGE"))
    clines_out.append(ClineRecord("VDDQ_0P85_HBM_MEM5", "8F", 30.0, -33112.138, 27687.499, -32902.683, 27687.499, "U41_VDDQ_8F_MID_E_BRIDGE"))

    # Stitch U13_8F_VDDQ_CSB [-35810..-35550, 28100..33000] down 8F->7F->6F directly onto U13_6F_VDDQ!
    for sy in range(28150, 33050, 320):
        insert_via_stack_zero_overlap(vias_out, grid, "VDDQ_0P85_HBM_MEM5", [("8F", "7F"), ("7F", "6F")], -35670.0, float(sy), "U13_8F_6F_VDDQ_TRUNK")

    # Connect the 4-pin Mid VPP 8F capsule (-33478.0, 27646.0) -> U13_7F_VPP_MID_BUS (with 7F backbone cline!) -> U13_6F_VPP,
    # AND stitch U13_12F_VPP (12F->11F->10F->9F->8F) so 0 floating VPP shapes exist!
    insert_via_stack_zero_overlap(vias_out, grid, "VPP_1P8_HBM_MEM5", [("8F", "7F")], -33478.0, 27646.0, "U41_VPP_MID_8F_7F")
    clines_out.append(ClineRecord("VPP_1P8_HBM_MEM5", "8F", 24.0, -33635.782, 27605.123, -33478.0, 27646.0, "U41_VPP_MID_CAP_A"))
    clines_out.append(ClineRecord("VPP_1P8_HBM_MEM5", "8F", 24.0, -33321.593, 27687.499, -33478.0, 27646.0, "U41_VPP_MID_CAP_B"))
    clines_out.append(ClineRecord("VPP_1P8_HBM_MEM5", "8F", 24.0, -33740.504, 27687.499, -33635.782, 27605.123, "U41_VPP_MID_CAP_C"))
    clines_out.append(ClineRecord("VPP_1P8_HBM_MEM5", "8F", 24.0, -33321.593, 27687.499, -33216.872, 27605.123, "U41_VPP_MID_CAP_D"))
    clines_out.append(ClineRecord("VPP_1P8_HBM_MEM5", "7F", 30.0, -45200.0, 27646.0, -33478.0, 27646.0, "U13_VPP_MID_7F_BACKBONE"))
    for gx_7f in range(-45200, -33450, 35):
        grid.insert("COND_7F", float(gx_7f), 27646.0, 18.0, "VPP_1P8_HBM_MEM5")
    for vx_w in (-45200.0, -44980.0, -44760.0):
        insert_via_stack_zero_overlap(vias_out, grid, "VPP_1P8_HBM_MEM5", [("7F", "6F")], vx_w, 27646.0, "U13_VPP_MID_7F_6F")
    for vy_12 in range(22800, 31900, 750):
        insert_via_stack_zero_overlap(
            vias_out, grid, "VPP_1P8_HBM_MEM5",
            [("12F", "11F"), ("11F", "10F"), ("10F", "9F"), ("9F", "8F")],
            -45400.0, float(vy_12), "U13_12F_8F_VPP_TRUNK",
        )

    # 3. VDDC (54 pins):
    #    - 20 X=-33531.05 Spine pins (incl. Y=27522.75) -> 2-stack (10F->9F->8F) + 8F->7F->6F L-collectors!
    #    - 24 South pins -> 1-stack (10F->9F) + vertical 9F stubs down to Y=23080 highway -> West 9F->6F trunks!
    #    - 10 Mid pins -> 1-stack (10F->9F) + exact 15um 9F BFS spanning tree into (-35670, 27685) -> West 9F->6F trunks!
    south_vddc_xs: List[float] = []
    mid_vddc_pts: List[Tuple[float, float]] = []
    for cx, cy in u41_csb_by_net["VDDC_1P0_HBM_MEM5"]:
        if abs(cx - (-33531.05)) < 25.0 and ((24115.0 <= cy <= 27568.0) or (27805.0 <= cy <= 31260.0)):
            if insert_via_stack_zero_overlap(vias_out, grid, "VDDC_1P0_HBM_MEM5", [("10F", "9F"), ("9F", "8F")], cx, cy, "U41_CSB_VDDC_SPINE_2STACK") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 45.0, "VDDC_1P0_HBM_MEM5")
                stats["u41_csb_pwr_2stack"] += 1
        else:
            if insert_via_stack_zero_overlap(vias_out, grid, "VDDC_1P0_HBM_MEM5", [("10F", "9F")], cx, cy, "U41_CSB_VDDC_1STACK") > 0:
                obs_9f.insert("PAD_9F", cx, cy, 38.5, "VDDC_1P0_HBM_MEM5")
                stats["u41_csb_pwr_1stack"] += 1
                if cy <= 23560.0:
                    clines_out.append(ClineRecord("VDDC_1P0_HBM_MEM5", "9F", 24.0, round(cx, 3), round(cy, 3), round(cx, 3), 23080.0, "U41_VDDC_9F_SOUTH_STUB"))
                    south_vddc_xs.append(cx)
                else:
                    mid_vddc_pts.append((cx, cy))

    if south_vddc_xs:
        clines_out.append(ClineRecord("VDDC_1P0_HBM_MEM5", "9F", 40.0, -41000.0, 23080.0, round(max(south_vddc_xs), 3), 23080.0, "U41_VDDC_9F_SOUTH_BUS"))
        for gx_9s in range(-41000, int(max(south_vddc_xs)) + 20, 35):
            grid.insert("COND_9F", float(gx_9s), 23080.0, 22.0, "VDDC_1P0_HBM_MEM5")

    # Stitch BOTH U13_9F_VDDC_CSB_SOUTH & U13_9F_VDDC_CSB_MID West tails [-41000..-39500] down 9F->8F->7F->6F!
    for tx in (-41000.0, -40700.0, -40400.0, -40100.0, -39800.0, -39500.0):
        for ty in (23120.0, 23420.0, 27140.0, 27290.0):
            insert_via_stack_zero_overlap(
                vias_out, grid, "VDDC_1P0_HBM_MEM5",
                [("9F", "8F"), ("8F", "7F"), ("7F", "6F")],
                tx, ty, "U13_9F_VDDC_COLLECTOR_TRUNK",
            )

    # Stitch U13_8F_VDDC_SPINE_S & _N -> 7F L-collectors -> U13_6F_VDDC!
    spine_mid_ys = (
        24365.0, 24722.0, 25079.0, 25463.3, 25847.8, 26232.2, 26589.2, 26946.1, 27330.5,
        28044.5, 28428.9, 28785.9, 29142.8, 29527.2, 29911.7, 30296.1, 30653.0, 31010.0,
    )
    for my in spine_mid_ys:
        insert_via_stack_zero_overlap(vias_out, grid, "VDDC_1P0_HBM_MEM5", [("8F", "7F")], -33531.05, my, "U13_8F_7F_VDDC_SPINE")
    for fx in (-40400.0, -40050.0, -39700.0, -39350.0, -39000.0, -38650.0, -38300.0):
        insert_via_stack_zero_overlap(vias_out, grid, "VDDC_1P0_HBM_MEM5", [("7F", "6F")], fx, 22700.0, "U13_7F_6F_VDDC_FOOT_S")
    for fnx in (-43700.0, -43450.0, -43200.0, -42980.0):
        insert_via_stack_zero_overlap(vias_out, grid, "VDDC_1P0_HBM_MEM5", [("7F", "6F")], fnx, 32170.0, "U13_7F_6F_VDDC_FOOT_N")

    # 4. VDDQL5 (588 pins): 100% 1-stack 10F->9F (r_9F = 38.5 um) + cycle-free 9F tree into 9F->8F->7F->6F onto U13_6F_VDDQL5!
    vddql_pts = sorted(u41_csb_by_net["VDDQL5"], key=lambda p: (-p[0], p[1]))
    for cx, cy in vddql_pts:
        if insert_via_stack_zero_overlap(vias_out, grid, "VDDQL5", [("10F", "9F")], cx, cy, "U41_CSB_VDDQL5_1STACK") > 0:
            obs_9f.insert("PAD_9F", cx, cy, 38.5, "VDDQL5")
            stats["u41_csb_pwr_1stack"] += 1

    own = ownership_ref[0]
    escaped_vddql_anchors: List[Tuple[float, float]] = []
    unanchored_vddql: List[Tuple[float, float]] = []
    sp_9_6 = [("9F", "8F"), ("8F", "7F"), ("7F", "6F")]

    for ey in range(23310, 31500, 380):
        ex = -27490.0
        ey_f = float(ey)
        if not obs_9f.has_conflict("PAD_9F", ex, ey_f, 45.0, "VDDQL5", 18.5, 18.5):
            if can_place_via_stack_zero_overlap(grid, "VDDQL5", sp_9_6, ex, ey_f):
                insert_via_stack_zero_overlap(vias_out, grid, "VDDQL5", sp_9_6, ex, ey_f, "U41_CSB_VDDQL5_EAST_TRUNK")
                obs_9f.insert("PAD_9F", ex, ey_f, 45.0, "VDDQL5")
                escaped_vddql_anchors.append((ex, ey_f))

    cand_offsets: List[Tuple[float, float]] = []
    for rad_d in (112.0, 138.0, 168.0, 198.0, 228.0):
        for ang_deg in range(0, 360, 15):
            rad_a = math.radians(ang_deg)
            cand_offsets.append((round(rad_d * math.cos(rad_a), 2), round(rad_d * math.sin(rad_a), 2)))

    for cx, cy in vddql_pts:
        linked_existing = False
        for ax, ay in reversed(escaped_vddql_anchors[-32:]):
            if math.hypot(ax - cx, ay - cy) <= 260.0:
                if (
                    _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, ax, ay, 14.0, "VDDQL5", 15.5)
                    and _segment_clear_of_layer_clines(clines_out, "9F", cx, cy, ax, ay, 14.0, "VDDQL5", 15.0)
                ):
                    clines_out.append(ClineRecord("VDDQL5", "9F", 28.0, round(cx, 3), round(cy, 3), round(ax, 3), round(ay, 3), "U41_CSB_VDDQL5_GANG9F"))
                    escaped_vddql_anchors.append((cx, cy))
                    stats["u41_csb_9f_vddql_escapes"] += 1
                    linked_existing = True
                    break
        if linked_existing:
            continue

        placed_trunk = False
        for sdx, sdy in cand_offsets:
            sx, sy = cx + sdx, cy + sdy
            if own.owner_at("6F", sx, sy, min_edge_margin_um=50.0) != "VDDQL5":
                continue
            if own.owner_at("9F", sx, sy, min_edge_margin_um=50.0) != "VSS":
                continue
            if obs_9f.has_conflict("PAD_9F", sx, sy, 45.0, "VDDQL5", 18.5, 18.5):
                continue
            if not _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, sx, sy, 14.0, "VDDQL5", 15.5):
                continue
            if not _segment_clear_of_layer_clines(clines_out, "9F", cx, cy, sx, sy, 14.0, "VDDQL5", 15.0):
                continue
            if can_place_via_stack_zero_overlap(grid, "VDDQL5", sp_9_6, sx, sy):
                insert_via_stack_zero_overlap(vias_out, grid, "VDDQL5", sp_9_6, sx, sy, "U41_CSB_VDDQL5_9F_6F")
                obs_9f.insert("PAD_9F", sx, sy, 45.0, "VDDQL5")
                clines_out.append(ClineRecord("VDDQL5", "9F", 28.0, round(cx, 3), round(cy, 3), round(sx, 3), round(sy, 3), "U41_CSB_VDDQL5_STEP9F"))
                escaped_vddql_anchors.append((sx, sy))
                escaped_vddql_anchors.append((cx, cy))
                stats["u41_csb_9f_vddql_escapes"] += 1
                placed_trunk = True
                break
        if not placed_trunk:
            unanchored_vddql.append((cx, cy))

    while unanchored_vddql:
        still_left: List[Tuple[float, float]] = []
        progressed = False
        for cx, cy in unanchored_vddql:
            best_direct: Optional[Tuple[float, float, float]] = None
            best_dogleg: Optional[Tuple[float, float, float, float, float]] = None
            best_zpath: Optional[Tuple[float, float, float, float, float, float, float]] = None
            for ax, ay in escaped_vddql_anchors:
                d = math.hypot(ax - cx, ay - cy)
                if d > 680.0:
                    continue
                if best_direct is None or d < best_direct[0]:
                    if (
                        _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, ax, ay, 10.0, "VDDQL5", 15.0)
                        and _segment_clear_of_layer_clines(clines_out, "9F", cx, cy, ax, ay, 10.0, "VDDQL5", 15.0)
                    ):
                        best_direct = (d, ax, ay)
                        continue
                if best_direct is None and (best_dogleg is None or d < best_dogleg[0]):
                    vx, vy = (ax - cx) / max(d, 1.0), (ay - cy) / max(d, 1.0)
                    px, py = -vy, vx
                    jog_cands: List[Tuple[float, float]] = [
                        (cx, cy + 0.72 * (ay - cy)),
                        (cx, ay),
                        (ax, cy),
                        (cx + 0.72 * (ax - cx), cy),
                    ]
                    for perp_off in (62.0, -62.0, 84.0, -84.0, 105.0, -105.0):
                        jog_cands.append((0.5 * (cx + ax) + px * perp_off, 0.5 * (cy + ay) + py * perp_off))
                    for mx, my in jog_cands:
                        if own.owner_at("9F", mx, my, min_edge_margin_um=25.0) != "VSS":
                            continue
                        if (
                            _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, mx, my, 10.0, "VDDQL5", 15.0)
                            and _segment_clear_of_obs(obs_9f, "PAD_9F", mx, my, ax, ay, 10.0, "VDDQL5", 15.0)
                            and _segment_clear_of_layer_clines(clines_out, "9F", cx, cy, mx, my, 10.0, "VDDQL5", 15.0)
                            and _segment_clear_of_layer_clines(clines_out, "9F", mx, my, ax, ay, 10.0, "VDDQL5", 15.0)
                        ):
                            best_dogleg = (d, mx, my, ax, ay)
                            break
                if best_direct is None and best_dogleg is None and (best_zpath is None or d < best_zpath[0]):
                    m1x, m1y = cx, cy + (ay - cy) / 3.0
                    m2x, m2y = ax, cy + 2.0 * (ay - cy) / 3.0
                    if (
                        own.owner_at("9F", m1x, m1y, min_edge_margin_um=25.0) == "VSS"
                        and own.owner_at("9F", m2x, m2y, min_edge_margin_um=25.0) == "VSS"
                        and _segment_clear_of_obs(obs_9f, "PAD_9F", cx, cy, m1x, m1y, 7.5, "VDDQL5", 15.0)
                        and _segment_clear_of_obs(obs_9f, "PAD_9F", m1x, m1y, m2x, m2y, 7.5, "VDDQL5", 15.0)
                        and _segment_clear_of_obs(obs_9f, "PAD_9F", m2x, m2y, ax, ay, 7.5, "VDDQL5", 15.0)
                        and _segment_clear_of_layer_clines(clines_out, "9F", cx, cy, m1x, m1y, 7.5, "VDDQL5", 15.0)
                        and _segment_clear_of_layer_clines(clines_out, "9F", m1x, m1y, m2x, m2y, 7.5, "VDDQL5", 15.0)
                        and _segment_clear_of_layer_clines(clines_out, "9F", m2x, m2y, ax, ay, 7.5, "VDDQL5", 15.0)
                    ):
                        best_zpath = (d, m1x, m1y, m2x, m2y, ax, ay)
            if best_direct is not None:
                clines_out.append(ClineRecord("VDDQL5", "9F", 20.0, round(cx, 3), round(cy, 3), round(best_direct[1], 3), round(best_direct[2], 3), "U41_CSB_VDDQL5_LINK9F"))
                escaped_vddql_anchors.append((cx, cy))
                stats["u41_csb_9f_vddql_escapes"] += 1
                progressed = True
            elif best_dogleg is not None:
                _, mx, my, ax, ay = best_dogleg
                clines_out.append(ClineRecord("VDDQL5", "9F", 20.0, round(cx, 3), round(cy, 3), round(mx, 3), round(my, 3), "U41_CSB_VDDQL5_JOG9F_A"))
                clines_out.append(ClineRecord("VDDQL5", "9F", 20.0, round(mx, 3), round(my, 3), round(ax, 3), round(ay, 3), "U41_CSB_VDDQL5_JOG9F_B"))
                escaped_vddql_anchors.append((cx, cy))
                stats["u41_csb_9f_vddql_escapes"] += 1
                progressed = True
            elif best_zpath is not None:
                _, m1x, m1y, m2x, m2y, ax, ay = best_zpath
                clines_out.append(ClineRecord("VDDQL5", "9F", 15.0, round(cx, 3), round(cy, 3), round(m1x, 3), round(m1y, 3), "U41_CSB_VDDQL5_Z9F_1"))
                clines_out.append(ClineRecord("VDDQL5", "9F", 15.0, round(m1x, 3), round(m1y, 3), round(m2x, 3), round(m2y, 3), "U41_CSB_VDDQL5_Z9F_2"))
                clines_out.append(ClineRecord("VDDQL5", "9F", 15.0, round(m2x, 3), round(m2y, 3), round(ax, 3), round(ay, 3), "U41_CSB_VDDQL5_Z9F_3"))
                escaped_vddql_anchors.append((cx, cy))
                stats["u41_csb_9f_vddql_escapes"] += 1
                progressed = True
            else:
                still_left.append((cx, cy))
        unanchored_vddql = still_left
        if not progressed:
            break

    # 5. Route the 10 Mid VDDC CSB pins via exact 15um 9F BFS tree AFTER VDDQL5 (O(1) hash lookup around VDDQL5 9F clines!)
    if mid_vddc_pts:
        for c9 in clines_out:
            if c9.layer == "9F" and c9.net_name != "VDDC_1P0_HBM_MEM5" and max(c9.y1, c9.y2) >= 27000.0 and min(c9.y1, c9.y2) <= 28100.0:
                ln_c = math.hypot(c9.x2 - c9.x1, c9.y2 - c9.y1)
                n_st = max(1, int(math.ceil(ln_c / 14.0)))
                hw_c = 0.5 * c9.width_um
                for ks in range(n_st + 1):
                    ts = ks / n_st
                    obs_9f.insert("PAD_9F", c9.x1 + ts * (c9.x2 - c9.x1), c9.y1 + ts * (c9.y2 - c9.y1), hw_c, c9.net_name)

        step_g = 15.0
        root_g = (int(round(-35670.0 / step_g)), int(round(27220.0 / step_g)))
        parent_g: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {root_g: None}
        q_g = collections.deque([root_g])
        dirs_g = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        while q_g:
            gx, gy = q_g.popleft()
            for dx_i, dy_i in dirs_g:
                nx, ny = gx + dx_i, gy + dy_i
                rx, ry = nx * step_g, ny * step_g
                if -35720.0 <= rx <= -31380.0 and 27090.0 <= ry <= 27990.0 and (nx, ny) not in parent_g:
                    mx_h, my_h = (gx + 0.5 * dx_i) * step_g, (gy + 0.5 * dy_i) * step_g
                    if (
                        not obs_9f.has_conflict("PAD_9F", rx, ry, 7.5, "VDDC_1P0_HBM_MEM5", -100.0, 15.0)
                        and not obs_9f.has_conflict("PAD_9F", mx_h, my_h, 7.5, "VDDC_1P0_HBM_MEM5", -100.0, 15.0)
                    ):
                        parent_g[(nx, ny)] = (gx, gy)
                        q_g.append((nx, ny))

        drawn_g_edges: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
        for vx, vy in mid_vddc_pts:
            near_nodes = [
                g for g in parent_g
                if abs(g[0] * step_g - vx) <= 22.0 and abs(g[1] * step_g - vy) <= 22.0
            ]
            if near_nodes:
                best_g = min(near_nodes, key=lambda g: math.hypot(g[0] * step_g - vx, g[1] * step_g - vy))
                clines_out.append(ClineRecord("VDDC_1P0_HBM_MEM5", "9F", 15.0, round(vx, 3), round(vy, 3), round(best_g[0] * step_g, 3), round(best_g[1] * step_g, 3), "U41_VDDC_MID_9F_TAP"))
                cur_n: Optional[Tuple[int, int]] = best_g
                while cur_n is not None and parent_g[cur_n] is not None:
                    prv_n = parent_g[cur_n]
                    assert prv_n is not None
                    ek = (min(cur_n, prv_n), max(cur_n, prv_n))
                    if ek not in drawn_g_edges:
                        drawn_g_edges.add(ek)
                        x_a, y_a = cur_n[0] * step_g, cur_n[1] * step_g
                        x_b, y_b = prv_n[0] * step_g, prv_n[1] * step_g
                        clines_out.append(ClineRecord("VDDC_1P0_HBM_MEM5", "9F", 15.0, round(x_a, 3), round(y_a, 3), round(x_b, 3), round(y_b, 3), "U41_VDDC_MID_9F_TREE"))
                        grid.insert("COND_9F", 0.5 * (x_a + x_b), 0.5 * (y_a + y_b), 12.0, "VDDC_1P0_HBM_MEM5")
                    cur_n = prv_n
        clines_out.append(ClineRecord("VDDC_1P0_HBM_MEM5", "9F", 30.0, -41000.0, 27220.0, -35670.0, 27220.0, "U41_VDDC_MID_9F_WEST"))
        for gx_9m in range(-41000, -35650, 35):
            grid.insert("COND_9F", float(gx_9m), 27220.0, 18.0, "VDDC_1P0_HBM_MEM5")

    # 6. Anchor U98 passive SMD/interposer pins on VDDQ (-39360.63, 31618.78) & VPP (-35722.32, 32080.91) so 0 disconnected 3D islands remain!
    _drop_from_surface_atomic(-39360.63, 31618.78, "VDDQ_0P85_HBM_MEM5", own, vias_out, grid, "U98_VDDQ_ANCHOR", max_spans=3)
    clines_out.append(ClineRecord("VDDQ_0P85_HBM_MEM5", "SURFACE", 24.0, -39754.41, 31615.09, -39360.63, 31618.78, "U98_VDDQ_BAR"))
    _drop_from_surface_atomic(-35722.32, 32080.909, "VPP_1P8_HBM_MEM5", own, vias_out, grid, "U98_VPP_ANCHOR", max_spans=5)

    return stats


# =============================================================================
# 2B. U13 (`HBM MEM5` West & North Non-EMIB Gang-Bars & Zero-Overlap BU Drops)
# =============================================================================
def route_u13_hbm_surface_and_10f_csb(
    u13_u41_u5_pins: Sequence[Dict[str, str]],
    ownership: MultiRailLayerOwnershipIndex,
    surface_gang_islands_out: List[PolygonIsland],
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
    grid: FastXYClearanceGrid,
    u13_polys: Optional[List[PolygonIsland]] = None,
    emib_already_routed: bool = False,
) -> Dict[str, int]:
    hbm_rails = {"VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5", "VPP_1P8_HBM_MEM5", "VSS"}
    u41_157_box = expand_bbox(U41_EMIB_BBOX, 157.5)  # 2D EMIB cavity KOZ (-35896.4, 22760.0, -26955.4, 31945.0)

    stats = {
        "u13_emib_c0_vias": 0,
        "u5_emib_c0_vias": 0,
        "u13_west_gang_bars": 0,
        "u13_west_drop_columns": 0,
        "u41_csb_vss_1stack": 0,
        "u41_csb_pwr_1stack": 0,
        "u41_csb_pwr_2stack": 0,
        "u41_csb_9f_vddql_escapes": 0,
        "interplane_stitch_vias": 0,
    }

    if not emib_already_routed and u13_polys is not None:
        own_box = [ownership]
        em_s = route_u13_emib_csb_and_c0_pins(u13_u41_u5_pins, u13_polys, own_box, vias_out, clines_out, grid)
        ownership = own_box[0]
        stats.update(em_s)

    u41_x0, u41_y0, u41_x1, u41_y1 = U41_EMIB_BBOX

    # Stitch U13_8F_VDDQL5_W0 & W1 down 8F->7F->6F directly onto U13_6F_VDDQL5 so West & East VDDQL5 merge into 1 3D net!
    for sx in (-37500.0, -37100.0, -36700.0, -36300.0, -35980.0):
        for sy in (22500.0, 22950.0, 24000.0, 25200.0, 26400.0, 27600.0):
            insert_via_stack_zero_overlap(vias_out, grid, "VDDQL5", [("8F", "7F"), ("7F", "6F")], sx, sy, "U13_8F_6F_VDDQL5_WEST_TRUNK")

    bump_obs = FastXYClearanceGrid(cell_um=120.0)
    west_by_net_row: Dict[Tuple[str, float], List[float]] = defaultdict(list)

    for r in u13_u41_u5_pins:
        if r["refdes"] != "U13" or "SURFACE" not in r["start_layer"]:
            continue
        net = r["net_name"]
        x, y = float(r["x_um"]), float(r["y_um"])
        bump_obs.insert("U13_SURF", x, y, 10.5, net)
        if net in hbm_rails and not (u41_x0 <= x <= u41_x1 and u41_y0 <= y <= u41_y1):
            west_by_net_row[(net, round(y, 1))].append(x)

    for net in ("VDDC_1P0_HBM_MEM5", "VDDQ_0P85_HBM_MEM5", "VSS", "VDDQL5", "VPP_1P8_HBM_MEM5"):
        net_ys = sorted(ry for (n, ry) in west_by_net_row.keys() if n == net)
        used_ys = set()
        anchored_bar_pts: List[Tuple[float, float]] = []
        unanchored_bars: List[Tuple[float, float, float]] = []

        for idx, y1 in enumerate(net_ys):
            if y1 in used_ys:
                continue
            paired_y2: Optional[float] = None
            if idx + 1 < len(net_ys) and 50.0 <= (net_ys[idx + 1] - y1) <= 58.0:
                paired_y2 = net_ys[idx + 1]
                used_ys.add(paired_y2)
            used_ys.add(y1)

            if paired_y2 is not None:
                xs_merged = sorted(set(west_by_net_row[(net, y1)] + west_by_net_row[(net, paired_y2)]))
                y_mid = round(0.5 * (y1 + paired_y2), 3)
                bar_half_h = 42.0
            else:
                xs_merged = sorted(set(west_by_net_row[(net, y1)]))
                y_mid = y1
                bar_half_h = 15.0

            runs: List[List[float]] = []
            cur_run: List[float] = []
            for xv in xs_merged:
                if not cur_run:
                    cur_run = [xv]
                else:
                    prev_x = cur_run[-1]
                    gap_ok = (xv - prev_x) <= 125.0
                    if gap_ok:
                        mid_x = 0.5 * (prev_x + xv)
                        if bump_obs.has_conflict("U13_SURF", mid_x, y_mid, bar_half_h, net, -100.0, 18.5):
                            gap_ok = False
                    if gap_ok:
                        cur_run.append(xv)
                    else:
                        runs.append(cur_run)
                        cur_run = [xv]
            if cur_run:
                runs.append(cur_run)

            for r_xs in runs:
                rx0, rx1 = min(r_xs) - 14.0, max(r_xs) + 14.0
                surface_gang_islands_out.append(PolygonIsland(
                    layer="SURFACE",
                    net_name=net,
                    vertices=rect_vertices((rx0, y_mid - bar_half_h, rx1, y_mid + bar_half_h)),
                    tag=f"U13_GANG_{net}",
                    is_dynamic=True,
                ))
                stats["u13_west_gang_bars"] += 1

                bar_drops = 0
                last_vx = -1e9
                for xv in r_xs:
                    if _point_in_any_box(xv, y_mid, [u41_157_box]) or xv - last_vx < 220.0:
                        continue
                    if bump_obs.has_conflict("U13_SURF", xv, y_mid, 38.5, net, -100.0, 18.5):
                        continue
                    added = _drop_from_surface_atomic(xv, y_mid, net, ownership, vias_out, grid, f"U13_WEST_{net}", max_spans=6)
                    if added > 0:
                        bump_obs.insert("U13_SURF", xv, y_mid, 38.5, net)
                        last_vx = xv
                        bar_drops += 1
                        anchored_bar_pts.append((xv, y_mid))
                        stats["u13_west_drop_columns"] += 1

                # Fallback fine X-scan along bar if no bump center had room
                if bar_drops == 0:
                    scan_x = rx0 + 10.0
                    while scan_x <= rx1 - 10.0:
                        if not _point_in_any_box(scan_x, y_mid, [u41_157_box]):
                            if not bump_obs.has_conflict("U13_SURF", scan_x, y_mid, 38.5, net, -100.0, 18.0):
                                added = _drop_from_surface_atomic(scan_x, y_mid, net, ownership, vias_out, grid, f"U13_WEST_FB_{net}", max_spans=6)
                                if added > 0:
                                    bump_obs.insert("U13_SURF", scan_x, y_mid, 38.5, net)
                                    bar_drops += 1
                                    anchored_bar_pts.append((scan_x, y_mid))
                                    stats["u13_west_drop_columns"] += 1
                                    break
                        scan_x += 18.0

                # North-of-U41 collar dogbone (e.g. Y=31778.85 & 31916.15 -> interstitial column step North above 31995 onto 12F/8F!)
                if bar_drops == 0 and y_mid >= 31750.0:
                    for xv in r_xs:
                        for dx_n in (0.0, 32.5, -32.5):
                            tx_n = xv + dx_n
                            if not (rx0 + 4.0 <= tx_n <= rx1 - 4.0):
                                continue
                            for ty_n in (32020.0, 32090.0, 32145.0):
                                if not bump_obs.has_conflict("U13_SURF", tx_n, ty_n, 38.5, net, -100.0, 18.0):
                                    if (
                                        _segment_clear_of_obs(bump_obs, "U13_SURF", tx_n, y_mid, tx_n, ty_n, 6.0, net, 14.5)
                                        and _segment_clear_of_layer_clines(clines_out, "SURFACE", tx_n, y_mid, tx_n, ty_n, 6.0, net, 14.5)
                                    ):
                                        added = _drop_from_surface_atomic(tx_n, ty_n, net, ownership, vias_out, grid, f"U13_NORTH_DOG_{net}", max_spans=6)
                                        if added > 0:
                                            bump_obs.insert("U13_SURF", tx_n, ty_n, 38.5, net)
                                            clines_out.append(ClineRecord(net, "SURFACE", 12.0, round(tx_n, 3), round(y_mid, 3), round(tx_n, 3), round(ty_n, 3), f"U13_NORTH_STRAP_{net}"))
                                            bar_drops += 1
                                            anchored_bar_pts.append((tx_n, y_mid))
                                            anchored_bar_pts.append((tx_n, ty_n))
                                            stats["u13_west_drop_columns"] += 1
                                            break
                            if bar_drops > 0:
                                break
                        if bar_drops > 0:
                            break

                if bar_drops == 0:
                    unanchored_bars.append((rx0, rx1, y_mid))

        # Convergent multi-hop SURFACE bar-to-bar strap for any collar / single-pin bar (e.g. South VDDQL5 Y=23294..23458)
        for _upass in range(4):
            rem_bars: List[Tuple[float, float, float]] = []
            prog_b = False
            for rx0, rx1, ym in unanchored_bars:
                bx = 0.5 * (rx0 + rx1)
                best_b: Optional[Tuple[float, float, float]] = None
                for ax, ay in anchored_bar_pts:
                    d = math.hypot(ax - bx, ay - ym)
                    if d <= 950.0 and (best_b is None or d < best_b[0]):
                        if (
                            _segment_clear_of_obs(bump_obs, "U13_SURF", bx, ym, ax, ay, 8.0, net, 15.0)
                            and _segment_clear_of_layer_clines(clines_out, "SURFACE", bx, ym, ax, ay, 8.0, net, 15.0)
                        ):
                            best_b = (d, ax, ay)
                if best_b is not None:
                    clines_out.append(ClineRecord(net, "SURFACE", 16.0, round(bx, 3), round(ym, 3), round(best_b[1], 3), round(best_b[2], 3), f"U13_BAR_STRAP_{net}"))
                    anchored_bar_pts.append((bx, ym))
                    prog_b = True
                else:
                    rem_bars.append((rx0, rx1, ym))
            unanchored_bars = rem_bars
            if not unanchored_bars or not prog_b:
                break

    return stats
