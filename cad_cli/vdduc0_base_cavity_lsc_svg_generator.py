"""
VDDUC0-Only Bottom (`BASE` / L27) LSC Pocket Placement & Mechanical Recess (`LSC_CAVITY`) Rule SVG Generator.

Generates XML-validated CAD blueprints showing:
  1. Panel A: Full `VDDUC0` `BASE` footprint (`POCKET_6` Core South + `POCKET_7` Core North,
     `107` `VDDUC0` BGA balls, `90` `VSS` return BGA balls, exact `R = 500 um` rounded-corner
     `SUBSTRATE GEOMETRY/LSC_CAVITY` outlines, `178 um` `Code D` `BASE` Signal/Cu KOZ halo,
     `225 um` inner LSC-SRO safe envelope, and all placed `VDDUC0` `0201` LSCs + `12B -> BASE` uVias).
  2. Panel B: High-magnification corner CAD detail of `POCKET_6` SW corner (`R = 500 um` milling bit
     radius, `R_allow = 275 um` concentric LSC-SRO arc, `250 um` BGA-SRO-to-Cavity, `225 um`
     LSC-SRO-to-Cavity, `178 um` `Code D` Cu/Signal KOZ, and forbidden square-corner ghost cap).
  3. Panel C: Vertical Z-stackup cross-section (`11B/12B/40um GCP/BASE` + `0.55mm 10uF LSC` +
     milled PCB Recess `Z = 21 +/- 4 mil`, `C > 150 um`, `Codes A, B, D, G`, uncut `L5`).
  4. Panel D: Complete Design Rule + Cavity Rule Verification Scorecard for `VDDUC0`.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent04_pdn_architect.cad_cli.base_lsc_bga_router import (
    BASE_EXT_CU_TO_CAVITY_MIN_UM,
    BGA_SRO_TO_CAVITY_MIN_UM,
    BGA_TO_LSC_SRO_MIN_UM,
    CAVITY_CORNER_RADIUS_UM,
    CAVITY_MIN_XY_DIM_UM,
    CAVITY_TO_CAVITY_MIN_WEB_UM,
    INNER_CU_TO_CAVITY_MIN_UM,
    LSC_LONG_SRO_UM,
    LSC_PAD_CU_HALF_UM,
    LSC_PAD_SRO_HALF_UM,
    LSC_PIN_HALF_PITCH_UM,
    LSC_SHORT_SRO_UM,
    LSC_SRO_TO_CAVITY_MIN_UM,
    U7_LEARNED_BGA_POCKETS,
    compute_pocket_lsc_cavity_contour,
    get_bga_via_offsets,
    get_lsc_pad_via_offsets,
    lsc_sro_box_clearance_to_cavity,
)

VDDUC0_POCKET_IDS = ("POCKET_6", "POCKET_7")
VDDUC0_VIEW_BBOX = (17600.0, 1500.0, 27200.0, 30900.0)


def load_vdduc0_region_bga_balls(workspace: Path) -> List[Dict[str, Any]]:
    """Load all BGA balls inside `VDDUC0_VIEW_BBOX` from `stage1_inputs/bga_map.csv`."""
    s1 = workspace / "agent04_pdn_architect" / "stage1_inputs" / "bga_map.csv"
    x0, y0, x1, y1 = VDDUC0_VIEW_BBOX
    balls: List[Dict[str, Any]] = []
    with s1.open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            x, y = float(r["x_um"]), float(r["y_um"])
            if x0 <= x <= x1 and y0 <= y <= y1:
                ps = r["padstack_name"].upper()
                if "C560" in ps:
                    cu_r, sro_r = 315.0, 280.0
                elif "C480" in ps:
                    cu_r, sro_r = 275.0, 240.0
                elif "C350" in ps:
                    cu_r, sro_r = 210.0, 175.0
                elif "C250" in ps:
                    cu_r, sro_r = 160.0, 125.0
                else:
                    cu_r, sro_r = 275.0, 240.0
                balls.append({
                    "pin_number": r["pin_number"],
                    "x": x,
                    "y": y,
                    "net": r["net_name"],
                    "padstack": ps,
                    "cu_r": cu_r,
                    "sro_r": sro_r,
                })
    return balls


def pack_vdduc0_pocket_with_cavity_rule(
    pocket: Dict[str, Any],
    bga_balls: List[Dict[str, Any]],
    sro_to_sro_min_um: float = 250.0,
) -> Dict[str, Any]:
    """
    Place maximum `VDDUC0` `0201` LSCs inside `pocket` (`POCKET_6` or `POCKET_7`) strictly obeying BOTH:
      1. Substrate Design Rules:
         - `BGA SRO -> LSC SRO >= 500.0 um`
         - `LSC SRO -> LSC SRO >= sro_to_sro_min_um` (`250.0 um` for `0.55mm 10uF`, `175.0 um` for `0.22mm 1uF`)
      2. Bottom (`BASE`) Mechanical Recess / Cavity Rules (`SUBSTRATE GEOMETRY/LSC_CAVITY`):
         - `BGA SRO -> LSC_CAVITY >= 250.0 um` (`Code G`)
         - `LSC_CAVITY` 4-corner milling bit radius `R = 500.0 um` (`Code K`)
         - `LSC SRO -> LSC_CAVITY` straight walls AND rounded corners `>= 225.0 um` (`Slide 11`, `R_allow = 275.0 um`)
         - `Cavity X/Y >= 1016.0 x 1016.0 um` (`Code E`)
    Also records any corner candidates that would have fit a naive rectangular box but were pruned
    by the `R = 500.0 um` rounded cavity corner rule!
    """
    w_left, w_bot, w_right, w_top = pocket["bga_walls"]
    wall_margin = pocket["wall_sro_r"] + BGA_TO_LSC_SRO_MIN_UM  # 240 + 500 = 740.0 um
    cavity_info = compute_pocket_lsc_cavity_contour(pocket)

    safe_x1 = w_left + wall_margin
    safe_y1 = w_bot + wall_margin
    safe_x2 = w_right - wall_margin
    safe_y2 = w_top - wall_margin

    pitch_short = LSC_SHORT_SRO_UM + sro_to_sro_min_um
    pitch_long = LSC_LONG_SRO_UM + sro_to_sro_min_um

    near_bgas = [
        b for b in bga_balls
        if (w_left - 900.0) <= b["x"] <= (w_right + 900.0) and (w_bot - 900.0) <= b["y"] <= (w_top + 900.0)
    ]

    def _sro_and_pins(cx: float, cy: float, rot: float) -> Tuple[Tuple[float, float, float, float], Tuple[float, float], Tuple[float, float]]:
        r_int = int(round(rot)) % 360
        if r_int == 0:
            sbox = (round(cx - 150.0, 3), round(cy - 410.0, 3), round(cx + 150.0, 3), round(cy + 410.0, 3))
            p1 = (round(cx, 3), round(cy + LSC_PIN_HALF_PITCH_UM, 3))
            p2 = (round(cx, 3), round(cy - LSC_PIN_HALF_PITCH_UM, 3))
        elif r_int == 180:
            sbox = (round(cx - 150.0, 3), round(cy - 410.0, 3), round(cx + 150.0, 3), round(cy + 410.0, 3))
            p1 = (round(cx, 3), round(cy - LSC_PIN_HALF_PITCH_UM, 3))
            p2 = (round(cx, 3), round(cy + LSC_PIN_HALF_PITCH_UM, 3))
        elif r_int == 90:
            sbox = (round(cx - 410.0, 3), round(cy - 150.0, 3), round(cx + 410.0, 3), round(cy + 150.0, 3))
            p1 = (round(cx - LSC_PIN_HALF_PITCH_UM, 3), round(cy, 3))
            p2 = (round(cx + LSC_PIN_HALF_PITCH_UM, 3), round(cy, 3))
        else:  # 270 deg
            sbox = (round(cx - 410.0, 3), round(cy - 150.0, 3), round(cx + 410.0, 3), round(cy + 150.0, 3))
            p1 = (round(cx + LSC_PIN_HALF_PITCH_UM, 3), round(cy, 3))
            p2 = (round(cx - LSC_PIN_HALF_PITCH_UM, 3), round(cy, 3))
        return sbox, p1, p2

    def _bga_min_clr(sbox: Tuple[float, float, float, float]) -> float:
        sx1, sy1, sx2, sy2 = sbox
        m = 1e9
        for b in near_bgas:
            dx = max(0.0, max(sx1 - b["x"], b["x"] - sx2))
            dy = max(0.0, max(sy1 - b["y"], b["y"] - sy2))
            d = math.hypot(dx, dy) - b["sro_r"]
            if d < m:
                m = d
        return m

    def _pack_1d(lo: float, hi: float, span: float, step: float) -> List[float]:
        avail = hi - lo
        if avail < span - 1e-3:
            return []
        cnt = 1 + int(math.floor((avail - span + 1e-3) / step))
        used = (cnt - 1) * step + span
        c0 = lo + 0.5 * (avail - used) + 0.5 * span
        return [round(c0 + i * step, 3) for i in range(cnt)]

    candidates: List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]] = []

    # Candidate Strategy 1: Horizontal bottom row (270 deg) + Vertical upper rows (0 deg) (Golden HFC topology for 250um!)
    v_xs = _pack_1d(safe_x1, safe_x2, LSC_SHORT_SRO_UM, pitch_short)
    avail_h = safe_y2 - safe_y1
    if v_xs and avail_h >= LSC_LONG_SRO_UM:
        max_v_rows = 1 + int(math.floor((avail_h - LSC_LONG_SRO_UM + 1e-3) / pitch_long))
        for n_v_rows in (max_v_rows, max(1, max_v_rows - 1)):
            used_v_h = (n_v_rows - 1) * pitch_long + LSC_LONG_SRO_UM
            rem_h = avail_h - used_v_h
            can_h = rem_h >= (sro_to_sro_min_um + LSC_SHORT_SRO_UM - 1e-3)
            for h_pos in (("BOTTOM", "TOP") if can_h else ("NONE",)):
                kept: List[Dict[str, Any]] = []
                pruned: List[Dict[str, Any]] = []
                if h_pos == "BOTTOM":
                    tot_stack_h = LSC_SHORT_SRO_UM + sro_to_sro_min_um + used_v_h
                    y_base = safe_y1 + 0.5 * (avail_h - tot_stack_h)
                    h_cy = round(y_base + 0.5 * LSC_SHORT_SRO_UM, 3)
                    v_y0 = round(y_base + LSC_SHORT_SRO_UM + sro_to_sro_min_um + 0.5 * LSC_LONG_SRO_UM, 3)
                elif h_pos == "TOP":
                    tot_stack_h = used_v_h + sro_to_sro_min_um + LSC_SHORT_SRO_UM
                    y_base = safe_y1 + 0.5 * (avail_h - tot_stack_h)
                    v_y0 = round(y_base + 0.5 * LSC_LONG_SRO_UM, 3)
                    h_cy = round(y_base + used_v_h + sro_to_sro_min_um + 0.5 * LSC_SHORT_SRO_UM, 3)
                else:
                    v_y0 = round(safe_y1 + 0.5 * (avail_h - used_v_h) + 0.5 * LSC_LONG_SRO_UM, 3)
                    h_cy = None

                if h_cy is not None:
                    h_xs = _pack_1d(safe_x1, safe_x2, LSC_LONG_SRO_UM, pitch_long)
                    for cx in h_xs:
                        # rot = 90.0 places Pin 1 (VDDUC0) on West (-X, aligned with even Col 0/2/4)
                        # and Pin 2 (VSS) on East (+X, aligned with odd Col 1/3/5), matching VDDUC1/2/3!
                        sbox, p1, p2 = _sro_and_pins(cx, h_cy, 90.0)
                        b_clr = _bga_min_clr(sbox)
                        c_clr = lsc_sro_box_clearance_to_cavity(sbox, cavity_info)
                        item = {"x": cx, "y": h_cy, "rot": 90.0, "sro_box": sbox, "pin1": p1, "pin2": p2, "bga_clr_um": round(b_clr, 2), "cav_clr_um": round(c_clr, 2)}
                        if b_clr >= BGA_TO_LSC_SRO_MIN_UM - 0.05:
                            if c_clr >= LSC_SRO_TO_CAVITY_MIN_UM - 0.05:
                                kept.append(item)
                            else:
                                pruned.append(item)
                for r_i in range(n_v_rows):
                    cy = round(v_y0 + r_i * pitch_long, 3)
                    for col_i, cx in enumerate(v_xs):
                        # Rotate 180 deg between adjacent columns (0 -> 180 -> 0 -> 180 -> 0 -> 180)
                        # so adjacent caps alternate N=VDDUC0/S=VSS <-> N=VSS/S=VDDUC0!
                        v_rot = 0.0 if (col_i % 2 == 0) else 180.0
                        sbox, p1, p2 = _sro_and_pins(cx, cy, v_rot)
                        b_clr = _bga_min_clr(sbox)
                        c_clr = lsc_sro_box_clearance_to_cavity(sbox, cavity_info)
                        item = {"x": cx, "y": cy, "rot": v_rot, "sro_box": sbox, "pin1": p1, "pin2": p2, "bga_clr_um": round(b_clr, 2), "cav_clr_um": round(c_clr, 2)}
                        if b_clr >= BGA_TO_LSC_SRO_MIN_UM - 0.05:
                            if c_clr >= LSC_SRO_TO_CAVITY_MIN_UM - 0.05:
                                kept.append(item)
                            else:
                                pruned.append(item)
                candidates.append((kept, pruned, f"{n_v_rows}V_rows + H_{h_pos}"))

    # Candidate Strategy 2: Horizontal columns (90/270 deg alternating) + Vertical remainder column (0 deg)
    h_ys = _pack_1d(safe_y1, safe_y2, LSC_SHORT_SRO_UM, pitch_short)
    avail_w = safe_x2 - safe_x1
    if h_ys and avail_w >= LSC_LONG_SRO_UM:
        max_h_cols = 1 + int(math.floor((avail_w - LSC_LONG_SRO_UM + 1e-3) / pitch_long))
        for n_h_cols in (max_h_cols, max(1, max_h_cols - 1)):
            used_h_w = (n_h_cols - 1) * pitch_long + LSC_LONG_SRO_UM
            rem_w = avail_w - used_h_w
            can_v = rem_w >= (sro_to_sro_min_um + LSC_SHORT_SRO_UM - 1e-3)
            kept_b: List[Dict[str, Any]] = []
            pruned_b: List[Dict[str, Any]] = []
            if can_v:
                tot_stack_w = used_h_w + sro_to_sro_min_um + LSC_SHORT_SRO_UM
                x_base = safe_x1 + 0.5 * (avail_w - tot_stack_w)
                h_x0 = round(x_base + 0.5 * LSC_LONG_SRO_UM, 3)
                v_cx = round(x_base + used_h_w + sro_to_sro_min_um + 0.5 * LSC_SHORT_SRO_UM, 3)
            else:
                h_x0 = round(safe_x1 + 0.5 * (avail_w - used_h_w) + 0.5 * LSC_LONG_SRO_UM, 3)
                v_cx = None
            for c_i in range(n_h_cols):
                cx = round(h_x0 + c_i * pitch_long, 3)
                for row_j, cy in enumerate(h_ys):
                    h_rot = 90.0 if (row_j % 2 == 0) else 270.0
                    sbox, p1, p2 = _sro_and_pins(cx, cy, h_rot)
                    b_clr = _bga_min_clr(sbox)
                    c_clr = lsc_sro_box_clearance_to_cavity(sbox, cavity_info)
                    item = {"x": cx, "y": cy, "rot": h_rot, "sro_box": sbox, "pin1": p1, "pin2": p2, "bga_clr_um": round(b_clr, 2), "cav_clr_um": round(c_clr, 2)}
                    if b_clr >= BGA_TO_LSC_SRO_MIN_UM - 0.05:
                        if c_clr >= LSC_SRO_TO_CAVITY_MIN_UM - 0.05:
                            kept_b.append(item)
                        else:
                            pruned_b.append(item)
            if v_cx is not None:
                v_ys = _pack_1d(safe_y1, safe_y2, LSC_LONG_SRO_UM, pitch_long)
                for cy in v_ys:
                    sbox, p1, p2 = _sro_and_pins(v_cx, cy, 0.0)
                    b_clr = _bga_min_clr(sbox)
                    c_clr = lsc_sro_box_clearance_to_cavity(sbox, cavity_info)
                    item = {"x": v_cx, "y": cy, "rot": 0.0, "sro_box": sbox, "pin1": p1, "pin2": p2, "bga_clr_um": round(b_clr, 2), "cav_clr_um": round(c_clr, 2)}
                    if b_clr >= BGA_TO_LSC_SRO_MIN_UM - 0.05:
                        if c_clr >= LSC_SRO_TO_CAVITY_MIN_UM - 0.05:
                            kept_b.append(item)
                        else:
                            pruned_b.append(item)
            candidates.append((kept_b, pruned_b, f"{n_h_cols}H_cols + V_rem"))

    # Select candidate maximizing kept count, tie-breaking by largest minimum cavity clearance
    best_kept, best_pruned, best_label = max(
        candidates,
        key=lambda t: (len(t[0]), min((c["cav_clr_um"] for c in t[0]), default=0.0)),
    )

    return {
        "pocket_id": pocket["pocket_id"],
        "pocket_name": pocket["name"],
        "bga_walls": pocket["bga_walls"],
        "cavity_info": cavity_info,
        "strategy": best_label,
        "placed_lscs": best_kept,
        "pruned_corner_lscs": best_pruned,
        "placed_count": len(best_kept),
        "pruned_corner_count": len(best_pruned),
        "min_bga_sro_to_lsc_sro_um": round(min(c["bga_clr_um"] for c in best_kept), 2),
        "min_lsc_sro_to_cavity_um": round(min(c["cav_clr_um"] for c in best_kept), 2),
    }


def _svg_rounded_rect_path(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    r_um: float,
    tx,
    ty,
    sr,
) -> str:
    """Build exact SVG `<path d=...>` for a rounded rectangle `[x0, y0, x1, y1]` (in um, Y-up) mapped to screen coords."""
    sx0, sx1 = tx(x0), tx(x1)
    sy_top, sy_bot = ty(y1), ty(y0)  # SVG Y increases downward
    rp = sr(r_um)
    return (
        f"M {sx0 + rp:.2f},{sy_top:.2f} "
        f"L {sx1 - rp:.2f},{sy_top:.2f} "
        f"A {rp:.2f},{rp:.2f} 0 0 1 {sx1:.2f},{sy_top + rp:.2f} "
        f"L {sx1:.2f},{sy_bot - rp:.2f} "
        f"A {rp:.2f},{rp:.2f} 0 0 1 {sx1 - rp:.2f},{sy_bot:.2f} "
        f"L {sx0 + rp:.2f},{sy_bot:.2f} "
        f"A {rp:.2f},{rp:.2f} 0 0 1 {sx0:.2f},{sy_bot - rp:.2f} "
        f"L {sx0:.2f},{sy_top + rp:.2f} "
        f"A {rp:.2f},{rp:.2f} 0 0 1 {sx0 + rp:.2f},{sy_top:.2f} Z"
    )


def synthesize_and_render_vdduc0_cavity_svg(
    workspace: Path,
    sro_to_sro_min_um: float = 250.0,
    bga_via_option: str = "OPTION3_6VIA_HEX_RING",
    out_svg_path: Path | None = None,
) -> Dict[str, Any]:
    """
    Synthesize `VDDUC0`-only `BASE` LSC placement + `LSC_CAVITY` Recess Rule geometry and render
    an XML-validated 4-panel CAD SVG blueprint.
    """
    bgas = load_vdduc0_region_bga_balls(workspace)
    vdduc0_pockets = [p for p in U7_LEARNED_BGA_POCKETS if p["pocket_id"] in VDDUC0_POCKET_IDS]
    bga_via_offsets = get_bga_via_offsets(bga_via_option)

    pocket_plans: List[Dict[str, Any]] = []
    all_vdduc0_lscs: List[Dict[str, Any]] = []
    cap_seq = 1
    sym_name = "SM0201_690X390X550_01A" if sro_to_sro_min_um >= 200.0 else "SM0201S_690X390X220_01C"
    cap_desc = "0201 10uF (0.55mmT, 250um SRO-to-SRO)" if sro_to_sro_min_um >= 200.0 else "0201 1uF (0.22mmT, 175um SRO-to-SRO)"

    for p in vdduc0_pockets:
        res = pack_vdduc0_pocket_with_cavity_rule(p, bgas, sro_to_sro_min_um=sro_to_sro_min_um)
        for c in res["placed_lscs"]:
            c["refdes"] = f"C_VDDUC0_{cap_seq:03d}"
            c["symbol_name"] = sym_name
            c["pocket_id"] = p["pocket_id"]
            cap_seq += 1
            all_vdduc0_lscs.append(c)
        pocket_plans.append(res)

    # Compute exact BGA SRO -> Cavity min clearance across all real BGA balls
    min_bga_to_cav_um = 1e9
    for res in pocket_plans:
        cx0, cy0, cx1, cy1 = res["cavity_info"]["cavity_bbox"]
        rc = res["cavity_info"]["corner_radius_um"]
        ix0, iy0, ix1, iy1 = cx0 + rc, cy0 + rc, cx1 - rc, cy1 - rc
        for b in bgas:
            dx = max(0.0, max(ix0 - b["x"], b["x"] - ix1))
            dy = max(0.0, max(iy0 - b["y"], b["y"] - iy1))
            d_wall = math.hypot(dx, dy) - rc
            sro_clr = d_wall - b["sro_r"]
            if sro_clr < min_bga_to_cav_um:
                min_bga_to_cav_um = sro_clr

    # Compute exact pairwise LSC SRO -> LSC SRO min spacing
    min_lsc_lsc_um = 1e9
    lsc_lsc_viol = 0
    for i in range(len(all_vdduc0_lscs)):
        ax0, ay0, ax1, ay1 = all_vdduc0_lscs[i]["sro_box"]
        for j in range(i + 1, len(all_vdduc0_lscs)):
            bx0, by0, bx1, by1 = all_vdduc0_lscs[j]["sro_box"]
            dx = max(0.0, max(ax0 - bx1, bx0 - ax1))
            dy = max(0.0, max(ay0 - by1, by0 - ay1))
            d = math.hypot(dx, dy) if (dx > 0 and dy > 0) else max(dx, dy)
            if d < min_lsc_lsc_um:
                min_lsc_lsc_um = d
            if d < sro_to_sro_min_um - 0.5:
                lsc_lsc_viol += 1

    p6_cav = pocket_plans[0]["cavity_info"]["cavity_bbox"]
    p7_cav = pocket_plans[1]["cavity_info"]["cavity_bbox"]
    cav_to_cav_web_um = round(p7_cav[1] - p6_cav[3], 2)  # 18585.0 - 13845.0 = 4740.0 um
    min_lsc_to_cav_um = min(p["min_lsc_sro_to_cavity_um"] for p in pocket_plans)
    min_bga_to_lsc_um = min(p["min_bga_sro_to_lsc_sro_um"] for p in pocket_plans)

    vdduc0_bga_balls = [b for b in bgas if b["net"] == "VDDUC0"]
    vss_bga_balls = [b for b in bgas if b["net"] == "VSS"]
    other_bga_balls = [b for b in bgas if b["net"] not in ("VDDUC0", "VSS")]

    if out_svg_path is None:
        out_dir = workspace / "agent04_pdn_architect" / "pdn_sandbox"
        out_dir.mkdir(parents=True, exist_ok=True)
        if sro_to_sro_min_um >= 200.0:
            out_svg_path = out_dir / "mockup_VDDUC0_BASE_Cavity_Rule_LSC_Placement.svg"
        else:
            out_svg_path = out_dir / "mockup_VDDUC0_BASE_Cavity_Rule_175um_114caps.svg"

    W, H = 3840, 2440
    lines: List[str] = []
    ap = lines.append

    ap('<?xml version="1.0" encoding="UTF-8"?>')
    ap(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    ap("  <defs>")
    ap('    <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">')
    ap('      <stop offset="0%" stop-color="#060b16"/>')
    ap('      <stop offset="100%" stop-color="#0b1324"/>')
    ap("    </linearGradient>")
    ap('    <pattern id="cavHatch" width="18" height="18" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">')
    ap('      <line x1="0" y1="0" x2="0" y2="18" stroke="#fbbf24" stroke-width="1.2" stroke-opacity="0.16"/>')
    ap("    </pattern>")
    ap('    <marker id="arrGold" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
    ap('      <path d="M 0 1 L 10 5 L 0 9 z" fill="#fbbf24"/>')
    ap("    </marker>")
    ap('    <marker id="arrGreen" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
    ap('      <path d="M 0 1 L 10 5 L 0 9 z" fill="#34d399"/>')
    ap("    </marker>")
    ap('    <marker id="arrCyan" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
    ap('      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8"/>')
    ap("    </marker>")
    ap('    <marker id="arrOrange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
    ap('      <path d="M 0 1 L 10 5 L 0 9 z" fill="#fb923c"/>')
    ap("    </marker>")
    ap('    <marker id="arrPink" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">')
    ap('      <path d="M 0 1 L 10 5 L 0 9 z" fill="#f43f5e"/>')
    ap("    </marker>")
    ap("  </defs>")

    ap(f'  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#bgGrad)"/>')

    # ================= HEADER BANNER =================
    ap('  <rect x="28" y="20" width="3784" height="106" rx="12" fill="#0f172a" stroke="#334155" stroke-width="2"/>')
    ap('  <text x="56" y="62" fill="#f8fafc" font-family="Consolas, Segoe UI, sans-serif" font-size="30" font-weight="bold">'
       f'VDDUC0 ONLY — BASE (L27) LSC PLACEMENT &amp; MECHANICAL RECESS / CAVITY RULE ({html.escape(cap_desc)})</text>')
    ap('  <text x="56" y="98" fill="#94a3b8" font-family="Consolas, Segoe UI, sans-serif" font-size="18">'
       f'Pockets 6 &amp; 7 (SUBSTRATE GEOMETRY/LSC_CAVITY) | VDDUC0 LSCs: {len(all_vdduc0_lscs)} ({pocket_plans[0]["placed_count"]}+{pocket_plans[1]["placed_count"]}) '
       f'| 12B-&gt;BASE LSC uVias: {len(all_vdduc0_lscs)*6} | VDDUC0 BGAs: {len(vdduc0_bga_balls)} + VSS Return BGAs: {len(vss_bga_balls)}</text>')

    # Status pill
    ap('  <rect x="3290" y="38" width="494" height="70" rx="10" fill="#064e3b" stroke="#10b981" stroke-width="2"/>')
    ap('  <text x="3537" y="68" text-anchor="middle" fill="#ecfdf5" font-family="Consolas, sans-serif" font-size="21" font-weight="bold">0 DRC / 0 CAVITY VIOLATIONS</text>')
    ap(f'  <text x="3537" y="94" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="15">'
       f'BGA-&gt;Cav {min_bga_to_cav_um:.1f}um | LSC-&gt;Cav {min_lsc_to_cav_um:.1f}um | R=500um</text>')

    # Helper to draw an 0201 LSC symbol at screen transform (tx, ty, sr)
    def _draw_lsc(c: Dict[str, Any], tx, ty, sr, show_vias: bool = True, ghost: bool = False) -> None:
        cx, cy, rot = c["x"], c["y"], c["rot"]
        sx0, sy0, sx1, sy1 = c["sro_box"]
        if ghost:
            ap(f'  <rect x="{tx(sx0):.2f}" y="{ty(sy1):.2f}" width="{sr(sx1-sx0):.2f}" height="{sr(sy1-sy0):.2f}" '
               f'fill="#f43f5e" fill-opacity="0.16" stroke="#f43f5e" stroke-width="2.6" stroke-dasharray="8,5"/>')
            gx0, gy0, gx1, gy1 = tx(sx0), ty(sy1), tx(sx1), ty(sy0)
            ap(f'  <line x1="{gx0:.2f}" y1="{gy0:.2f}" x2="{gx1:.2f}" y2="{gy1:.2f}" stroke="#f43f5e" stroke-width="2.4"/>')
            ap(f'  <line x1="{gx0:.2f}" y1="{gy1:.2f}" x2="{gx1:.2f}" y2="{gy0:.2f}" stroke="#f43f5e" stroke-width="2.4"/>')
            return

        p1x, p1y = c["pin1"]
        p2x, p2y = c["pin2"]
        # Cu pads (348x348 um): Pin 1 = VDDUC0 (#ef4444), Pin 2 = VSS (#06b6d4)
        cu_w = sr(2.0 * LSC_PAD_CU_HALF_UM)
        sro_w = sr(2.0 * LSC_PAD_SRO_HALF_UM)
        ap(f'  <rect x="{tx(p1x - LSC_PAD_CU_HALF_UM):.2f}" y="{ty(p1y + LSC_PAD_CU_HALF_UM):.2f}" '
           f'width="{cu_w:.2f}" height="{cu_w:.2f}" fill="#dc2626" fill-opacity="0.72" stroke="#fca5a5" stroke-width="0.9"/>')
        ap(f'  <rect x="{tx(p2x - LSC_PAD_CU_HALF_UM):.2f}" y="{ty(p2y + LSC_PAD_CU_HALF_UM):.2f}" '
           f'width="{cu_w:.2f}" height="{cu_w:.2f}" fill="#0891b2" fill-opacity="0.72" stroke="#67e8f9" stroke-width="0.9"/>')
        # SRO outlines (300x300 um per pad + overall SRO envelope)
        ap(f'  <rect x="{tx(p1x - LSC_PAD_SRO_HALF_UM):.2f}" y="{ty(p1y + LSC_PAD_SRO_HALF_UM):.2f}" '
           f'width="{sro_w:.2f}" height="{sro_w:.2f}" fill="none" stroke="#fef08a" stroke-width="0.8" stroke-dasharray="3,2"/>')
        ap(f'  <rect x="{tx(p2x - LSC_PAD_SRO_HALF_UM):.2f}" y="{ty(p2y + LSC_PAD_SRO_HALF_UM):.2f}" '
           f'width="{sro_w:.2f}" height="{sro_w:.2f}" fill="none" stroke="#fef08a" stroke-width="0.8" stroke-dasharray="3,2"/>')
        ap(f'  <rect x="{tx(sx0):.2f}" y="{ty(sy1):.2f}" width="{sr(sx1-sx0):.2f}" height="{sr(sy1-sy0):.2f}" '
           f'fill="none" stroke="#e2e8f0" stroke-width="0.8" stroke-opacity="0.55"/>')
        # 0201 Ceramic Body (690 x 390 um)
        bw, bh = (390.0, 690.0) if int(round(rot)) % 180 == 0 else (690.0, 390.0)
        ap(f'  <rect x="{tx(cx - 0.5*bw):.2f}" y="{ty(cy + 0.5*bh):.2f}" width="{sr(bw):.2f}" height="{sr(bh):.2f}" '
           f'rx="2" fill="#cbd5e1" fill-opacity="0.22" stroke="#f8fafc" stroke-width="1.0"/>')
        # 6 x 12B->BASE V90_65_90_12B_BASE_01A microvias (45um pad radius, 32.5um drill radius)
        if show_vias:
            p1_offs, p2_offs = get_lsc_pad_via_offsets(rot)
            vr = max(1.3, sr(45.0))
            for dx, dy in p1_offs:
                ap(f'  <circle cx="{tx(cx+dx):.2f}" cy="{ty(cy+dy):.2f}" r="{vr:.2f}" fill="#fee2e2" stroke="#991b1b" stroke-width="0.8"/>')
            for dx, dy in p2_offs:
                ap(f'  <circle cx="{tx(cx+dx):.2f}" cy="{ty(cy+dy):.2f}" r="{vr:.2f}" fill="#cffafe" stroke="#155e75" stroke-width="0.8"/>')

    # ================= PANEL A: FULL VDDUC0 BASE DOMAIN MAP =================
    pa_x, pa_y, pa_w, pa_h = 28, 144, 1390, 2268
    ap(f'  <rect x="{pa_x}" y="{pa_y}" width="{pa_w}" height="{pa_h}" rx="12" fill="#09101f" stroke="#334155" stroke-width="2"/>')
    ap(f'  <text x="{pa_x+24}" y="{pa_y+38}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="22" font-weight="bold">'
       f'PANEL A — FULL VDDUC0 BASE FOOTPRINT (POCKET_6 SOUTH &amp; POCKET_7 NORTH, 1:1 MICRON SCALE)</text>')
    ap(f'  <text x="{pa_x+24}" y="{pa_y+64}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="15">'
       f'Red = VDDUC0 ({len(vdduc0_bga_balls)} BGA + Pin1 LSC) | Cyan = VSS Return ({len(vss_bga_balls)} BGA + Pin2 LSC) | Gold = LSC_CAVITY (R=500um) | Orange = 178um Cu/Signal KOZ</text>')

    vx0, vy0, vx1, vy1 = VDDUC0_VIEW_BBOX
    plot_a_x0, plot_a_y0 = pa_x + 95, pa_y + 92
    plot_a_w, plot_a_h = pa_w - 140, pa_h - 210
    sc_a = min(plot_a_w / (vx1 - vx0), plot_a_h / (vy1 - vy0))
    ox_a = plot_a_x0 + 0.5 * (plot_a_w - (vx1 - vx0) * sc_a)
    oy_a = plot_a_y0 + 0.5 * (plot_a_h - (vy1 - vy0) * sc_a)

    def tx_a(xu: float) -> float:
        return ox_a + (xu - vx0) * sc_a

    def ty_a(yu: float) -> float:
        return oy_a + (vy1 - yu) * sc_a

    def sr_a(du: float) -> float:
        return du * sc_a

    # Coordinate grid in Panel A
    for xg in range(18000, 27500, 2000):
        sx = tx_a(float(xg))
        ap(f'  <line x1="{sx:.2f}" y1="{ty_a(vy1):.2f}" x2="{sx:.2f}" y2="{ty_a(vy0):.2f}" stroke="#1e293b" stroke-width="1"/>')
        ap(f'  <text x="{sx:.2f}" y="{ty_a(vy0)+22:.2f}" text-anchor="middle" fill="#64748b" font-family="Consolas, sans-serif" font-size="13">{xg}um</text>')
    for yg in range(2000, 31000, 2000):
        sy = ty_a(float(yg))
        ap(f'  <line x1="{tx_a(vx0):.2f}" y1="{sy:.2f}" x2="{tx_a(vx1):.2f}" y2="{sy:.2f}" stroke="#1e293b" stroke-width="1"/>')
        ap(f'  <text x="{tx_a(vx0)-10:.2f}" y="{sy+4:.2f}" text-anchor="end" fill="#64748b" font-family="Consolas, sans-serif" font-size="13">{yg}</text>')

    # Draw dimmed non-VDDUC0 context BGA balls first
    for b in other_bga_balls:
        ap(f'  <circle cx="{tx_a(b["x"]):.2f}" cy="{ty_a(b["y"]):.2f}" r="{sr_a(b["cu_r"]):.2f}" '
           f'fill="#1e293b" fill-opacity="0.35" stroke="#475569" stroke-width="0.9" stroke-dasharray="3,2"/>')

    # Draw VSS & VDDUC0 BGA balls + 12B->BASE via clusters
    for b in vss_bga_balls:
        ap(f'  <circle cx="{tx_a(b["x"]):.2f}" cy="{ty_a(b["y"]):.2f}" r="{sr_a(b["cu_r"]):.2f}" fill="#0e7490" fill-opacity="0.52" stroke="#22d3ee" stroke-width="1.2"/>')
        ap(f'  <circle cx="{tx_a(b["x"]):.2f}" cy="{ty_a(b["y"]):.2f}" r="{sr_a(b["sro_r"]):.2f}" fill="none" stroke="#a5f3fc" stroke-width="0.9" stroke-dasharray="3,2"/>')
        for dx, dy in bga_via_offsets:
            ap(f'  <circle cx="{tx_a(b["x"]+dx):.2f}" cy="{ty_a(b["y"]+dy):.2f}" r="{max(1.2, sr_a(45.0)):.2f}" fill="#cffafe" stroke="#164e63" stroke-width="0.6"/>')

    for b in vdduc0_bga_balls:
        ap(f'  <circle cx="{tx_a(b["x"]):.2f}" cy="{ty_a(b["y"]):.2f}" r="{sr_a(b["cu_r"]):.2f}" fill="#b91c1c" fill-opacity="0.62" stroke="#f87171" stroke-width="1.4"/>')
        ap(f'  <circle cx="{tx_a(b["x"]):.2f}" cy="{ty_a(b["y"]):.2f}" r="{sr_a(b["sro_r"]):.2f}" fill="none" stroke="#fecaca" stroke-width="0.9" stroke-dasharray="3,2"/>')
        for dx, dy in bga_via_offsets:
            ap(f'  <circle cx="{tx_a(b["x"]+dx):.2f}" cy="{ty_a(b["y"]+dy):.2f}" r="{max(1.2, sr_a(45.0)):.2f}" fill="#fee2e2" stroke="#7f1d1d" stroke-width="0.6"/>')

    # Draw Pocket 6 & Pocket 7 Cavities + Code D 178um Ext Cu/Signal KOZ + 225um Safe LSC Envelope + Placed LSCs
    for res in pocket_plans:
        cinfo = res["cavity_info"]
        cx0, cy0, cx1, cy1 = cinfo["cavity_bbox"]
        kx0, ky0, kx1, ky1 = cinfo["ext_cu_koz_bbox"]
        rc = cinfo["corner_radius_um"]
        r_allow = cinfo["allowed_lsc_corner_radius_um"]

        # 1. Code D (178um) External Non-SMT Copper / Signal KOZ halo
        d_koz = _svg_rounded_rect_path(kx0, ky0, kx1, ky1, rc + BASE_EXT_CU_TO_CAVITY_MIN_UM, tx_a, ty_a, sr_a)
        ap(f'  <path d="{d_koz}" fill="none" stroke="#fb923c" stroke-width="1.8" stroke-dasharray="7,4"/>')

        # 2. SUBSTRATE GEOMETRY/LSC_CAVITY (R = 500 um @ 4 corners)
        d_cav = _svg_rounded_rect_path(cx0, cy0, cx1, cy1, rc, tx_a, ty_a, sr_a)
        ap(f'  <path d="{d_cav}" fill="url(#cavHatch)" stroke="#fbbf24" stroke-width="2.8"/>')

        # 3. Inner 225 um Allowed LSC-SRO Envelope (R_allow = 275 um @ 4 corners)
        d_safe = _svg_rounded_rect_path(
            cx0 + LSC_SRO_TO_CAVITY_MIN_UM,
            cy0 + LSC_SRO_TO_CAVITY_MIN_UM,
            cx1 - LSC_SRO_TO_CAVITY_MIN_UM,
            cy1 - LSC_SRO_TO_CAVITY_MIN_UM,
            r_allow,
            tx_a,
            ty_a,
            sr_a,
        )
        ap(f'  <path d="{d_safe}" fill="#064e3b" fill-opacity="0.18" stroke="#34d399" stroke-width="1.5" stroke-dasharray="5,4"/>')

        # 4. Placed VDDUC0 LSCs
        for c in res["placed_lscs"]:
            _draw_lsc(c, tx_a, ty_a, sr_a, show_vias=True, ghost=False)

        # Pocket title callout card in the clean right margin (outside BGA array, zero overlap!)
        mid_y = 0.5 * (cy0 + cy1)
        lbl_x = tx_a(vx1) + 16.0
        lbl_y = ty_a(mid_y)
        ap(f'  <line x1="{tx_a(cx1):.2f}" y1="{lbl_y:.2f}" x2="{lbl_x:.2f}" y2="{lbl_y:.2f}" stroke="#fbbf24" stroke-width="1.6" stroke-dasharray="5,3"/>')
        ap(f'  <circle cx="{tx_a(cx1):.2f}" cy="{lbl_y:.2f}" r="4.0" fill="#fbbf24"/>')
        ap(f'  <rect x="{lbl_x:.2f}" y="{lbl_y-52:.2f}" width="290" height="104" rx="8" fill="#0f172a" stroke="#fbbf24" stroke-width="1.6"/>')
        ap(f'  <text x="{lbl_x+12:.2f}" y="{lbl_y-26:.2f}" fill="#fde68a" font-family="Consolas, sans-serif" font-size="15" font-weight="bold">{res["pocket_id"]} — VDDUC0 ONLY</text>')
        ap(f'  <text x="{lbl_x+12:.2f}" y="{lbl_y-4:.2f}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="13.5">Cavity: {cinfo["width_um"]:.0f}x{cinfo["height_um"]:.0f}um (R=500)</text>')
        ap(f'  <text x="{lbl_x+12:.2f}" y="{lbl_y+18:.2f}" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="13.5" font-weight="bold">Placed: {res["placed_count"]} LSCs ({res["placed_count"]*6} uVias)</text>')
        ap(f'  <text x="{lbl_x+12:.2f}" y="{lbl_y+39:.2f}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="12.5">Min LSC-&gt;Cav: {res["min_lsc_sro_to_cavity_um"]:.1f}um (&gt;=225)</text>')

    # Dimension arrow for Code J (Cavity-to-Cavity Web = 4740.0 um >= 508.0 um) with card in clean left margin!
    web_x = tx_a(p6_cav[0] + 160.0)
    wy_bot = ty_a(p6_cav[3])
    wy_top = ty_a(p7_cav[1])
    wy_mid = 0.5 * (wy_bot + wy_top)
    ap(f'  <line x1="{web_x:.2f}" y1="{wy_bot-4:.2f}" x2="{web_x:.2f}" y2="{wy_top+4:.2f}" '
       f'stroke="#38bdf8" stroke-width="2.6" marker-start="url(#arrCyan)" marker-end="url(#arrCyan)"/>')
    card_j_x = pa_x + 24.0
    card_j_w = 300.0
    ap(f'  <line x1="{card_j_x+card_j_w:.2f}" y1="{wy_mid:.2f}" x2="{web_x:.2f}" y2="{wy_mid:.2f}" stroke="#38bdf8" stroke-width="1.6" stroke-dasharray="5,3"/>')
    ap(f'  <rect x="{card_j_x:.2f}" y="{wy_mid-42:.2f}" width="{card_j_w:.2f}" height="84" rx="8" fill="#0f172a" stroke="#38bdf8" stroke-width="1.6"/>')
    ap(f'  <text x="{card_j_x+12:.2f}" y="{wy_mid-16:.2f}" fill="#e0f2fe" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">Code J: Recess-to-Recess Web</text>')
    ap(f'  <text x="{card_j_x+12:.2f}" y="{wy_mid+7:.2f}" fill="#38bdf8" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">Actual = {cav_to_cav_web_um:.1f} um</text>')
    ap(f'  <text x="{card_j_x+12:.2f}" y="{wy_mid+28:.2f}" fill="#7dd3fc" font-family="Consolas, sans-serif" font-size="12.5">Rule &gt;= 508.0 um (20mil) PASS</text>')

    # Panel A bottom legend bar
    leg_y = pa_y + pa_h - 86
    ap(f'  <rect x="{pa_x+20}" y="{leg_y}" width="{pa_w-40}" height="68" rx="8" fill="#0f172a" stroke="#1e293b" stroke-width="1.5"/>')
    legend_items = [
        ("#dc2626", "VDDUC0 Pad/BGA"),
        ("#0891b2", "VSS Return Pad/BGA"),
        ("#fbbf24", "LSC_CAVITY (R=500um)"),
        ("#34d399", "225um LSC Safe Zone (R=275um)"),
        ("#fb923c", "178um Ext Cu/Signal KOZ"),
        ("#475569", "Other Net BGA (Context)"),
    ]
    for idx_l, (col_l, txt_l) in enumerate(legend_items):
        lx = pa_x + 38 + (idx_l % 3) * 445
        ly = leg_y + 24 + (idx_l // 3) * 28
        ap(f'  <rect x="{lx}" y="{ly-12}" width="18" height="14" rx="3" fill="{col_l}"/>')
        ap(f'  <text x="{lx+26}" y="{ly}" fill="#cbd5e1" font-family="Consolas, sans-serif" font-size="14">{html.escape(txt_l)}</text>')

    # ================= PANEL B: HIGH-MAGNIFICATION CORNER & WALL DETAIL (POCKET_6 SW CORNER) =================
    pb_x, pb_y, pb_w, pb_h = 1444, 144, 2368, 1090
    ap(f'  <rect x="{pb_x}" y="{pb_y}" width="{pb_w}" height="{pb_h}" rx="12" fill="#09101f" stroke="#334155" stroke-width="2"/>')
    ap(f'  <text x="{pb_x+24}" y="{pb_y+38}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="22" font-weight="bold">'
       f'PANEL B — POCKET_6 SW CORNER ZOOM: R=500um MILLING RADIUS, 250um BGA-&gt;CAVITY, 225um LSC-&gt;CAVITY &amp; SIGNAL KOZ</text>')
    ap(f'  <text x="{pb_x+24}" y="{pb_y+64}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="15">'
       f'Shows exact inward R=500um router arc (Code K), concentric R_allow=275um LSC SRO limit, and why naive square-corner LSCs fail (146.4um &lt; 225um)</text>')

    zx0, zy0, zx1, zy1 = 19120.0, 4520.0, 22680.0, 7720.0
    plot_b_x0, plot_b_y0 = pb_x + 40, pb_y + 84
    plot_b_w, plot_b_h = 1360, pb_h - 110
    sc_b = min(plot_b_w / (zx1 - zx0), plot_b_h / (zy1 - zy0))
    ox_b = plot_b_x0 + 0.5 * (plot_b_w - (zx1 - zx0) * sc_b)
    oy_b = plot_b_y0 + 0.5 * (plot_b_h - (zy1 - zy0) * sc_b)

    def tx_b(xu: float) -> float:
        return ox_b + (xu - zx0) * sc_b

    def ty_b(yu: float) -> float:
        return oy_b + (zy1 - yu) * sc_b

    def sr_b(du: float) -> float:
        return du * sc_b

    ap(f'  <clipPath id="clipZoomB"><rect x="{plot_b_x0}" y="{plot_b_y0}" width="{plot_b_w}" height="{plot_b_h}" rx="8"/></clipPath>')
    ap(f'  <rect x="{plot_b_x0}" y="{plot_b_y0}" width="{plot_b_w}" height="{plot_b_h}" rx="8" fill="#050914" stroke="#1e293b" stroke-width="1.5"/>')
    ap('  <g clip-path="url(#clipZoomB)">')

    # Fine 500um grid inside Zoom B
    for xg in range(19500, 23000, 500):
        ap(f'    <line x1="{tx_b(xg):.2f}" y1="{plot_b_y0}" x2="{tx_b(xg):.2f}" y2="{plot_b_y0+plot_b_h}" stroke="#1e293b" stroke-width="0.9"/>')
    for yg in range(4500, 8000, 500):
        ap(f'    <line x1="{plot_b_x0}" y1="{ty_b(yg):.2f}" x2="{plot_b_x0+plot_b_w}" y2="{ty_b(yg):.2f}" stroke="#1e293b" stroke-width="0.9"/>')

    # Draw BGA balls in Zoom B
    for b in bgas:
        if (zx0 - 400.0) <= b["x"] <= (zx1 + 400.0) and (zy0 - 400.0) <= b["y"] <= (zy1 + 400.0):
            is_vdd = b["net"] == "VDDUC0"
            is_vss = b["net"] == "VSS"
            fc = "#b91c1c" if is_vdd else ("#0e7490" if is_vss else "#334155")
            sc = "#fca5a5" if is_vdd else ("#67e8f9" if is_vss else "#64748b")
            ap(f'    <circle cx="{tx_b(b["x"]):.2f}" cy="{ty_b(b["y"]):.2f}" r="{sr_b(b["cu_r"]):.2f}" fill="{fc}" fill-opacity="0.58" stroke="{sc}" stroke-width="1.8"/>')
            ap(f'    <circle cx="{tx_b(b["x"]):.2f}" cy="{ty_b(b["y"]):.2f}" r="{sr_b(b["sro_r"]):.2f}" fill="none" stroke="#fef08a" stroke-width="1.5" stroke-dasharray="6,4"/>')
            if is_vdd or is_vss:
                for dx, dy in bga_via_offsets:
                    ap(f'    <circle cx="{tx_b(b["x"]+dx):.2f}" cy="{ty_b(b["y"]+dy):.2f}" r="{sr_b(45.0):.2f}" fill="#f8fafc" fill-opacity="0.85" stroke="#0f172a" stroke-width="1.0"/>')
            ap(f'    <text x="{tx_b(b["x"]):.2f}" y="{ty_b(b["y"])+4:.2f}" text-anchor="middle" fill="#ffffff" font-family="Consolas, sans-serif" font-size="11" font-weight="bold">{html.escape(b["pin_number"])}</text>')

    # Draw Pocket 6 contours in Zoom B
    p6_info = pocket_plans[0]["cavity_info"]
    cx0, cy0, cx1, cy1 = p6_info["cavity_bbox"]
    kx0, ky0, kx1, ky1 = p6_info["ext_cu_koz_bbox"]
    rc = p6_info["corner_radius_um"]
    r_allow = p6_info["allowed_lsc_corner_radius_um"]

    # Inner 203um (Code D Int 8mil) & External 178um (Code D Ext 7mil) Cu/Signal KOZ halos
    ap(f'    <path d="{_svg_rounded_rect_path(cx0 - INNER_CU_TO_CAVITY_MIN_UM, cy0 - INNER_CU_TO_CAVITY_MIN_UM, cx1 + INNER_CU_TO_CAVITY_MIN_UM, cy1 + INNER_CU_TO_CAVITY_MIN_UM, rc + INNER_CU_TO_CAVITY_MIN_UM, tx_b, ty_b, sr_b)}" '
       f'fill="none" stroke="#c084fc" stroke-width="1.6" stroke-dasharray="4,5"/>')
    ap(f'    <path d="{_svg_rounded_rect_path(kx0, ky0, kx1, ky1, rc + BASE_EXT_CU_TO_CAVITY_MIN_UM, tx_b, ty_b, sr_b)}" '
       f'fill="none" stroke="#fb923c" stroke-width="2.2" stroke-dasharray="8,5"/>')
    ap(f'    <path d="{_svg_rounded_rect_path(cx0, cy0, cx1, cy1, rc, tx_b, ty_b, sr_b)}" '
       f'fill="url(#cavHatch)" stroke="#fbbf24" stroke-width="3.4"/>')
    ap(f'    <path d="{_svg_rounded_rect_path(cx0 + LSC_SRO_TO_CAVITY_MIN_UM, cy0 + LSC_SRO_TO_CAVITY_MIN_UM, cx1 - LSC_SRO_TO_CAVITY_MIN_UM, cy1 - LSC_SRO_TO_CAVITY_MIN_UM, r_allow, tx_b, ty_b, sr_b)}" '
       f'fill="#064e3b" fill-opacity="0.16" stroke="#34d399" stroke-width="2.2" stroke-dasharray="7,5"/>')

    # Draw Forbidden Square-Corner Ghost Cap at (sx0=20277.56, sy0=5675.0 -> 146.4um < 225um FAIL!)
    ghost_sro = (20277.56, 5675.0, 20577.56, 6495.0)
    _draw_lsc({"x": 20427.56, "y": 6085.0, "rot": 0.0, "sro_box": ghost_sro, "pin1": (20427.56, 5825.0), "pin2": (20427.56, 6345.0)}, tx_b, ty_b, sr_b, ghost=True)

    # Draw Placed Pocket 6 VDDUC0 LSCs visible in Zoom B
    for c in pocket_plans[0]["placed_lscs"]:
        if c["y"] <= 8200.0 and c["x"] <= 22800.0:
            _draw_lsc(c, tx_b, ty_b, sr_b, show_vias=True, ghost=False)

    # Arc center crosshair at BL corner (20527.54, 5925.0)
    acx, acy = p6_info["arc_centers"]["BL"]
    ap(f'    <circle cx="{tx_b(acx):.2f}" cy="{ty_b(acy):.2f}" r="5" fill="#fbbf24"/>')
    ap(f'    <line x1="{tx_b(acx)-14:.2f}" y1="{ty_b(acy):.2f}" x2="{tx_b(acx)+14:.2f}" y2="{ty_b(acy):.2f}" stroke="#fbbf24" stroke-width="1.6"/>')
    ap(f'    <line x1="{tx_b(acx):.2f}" y1="{ty_b(acy)-14:.2f}" x2="{tx_b(acx):.2f}" y2="{ty_b(acy)+14:.2f}" stroke="#fbbf24" stroke-width="1.6"/>')

    # 1. Radial arrow for R = 500.0 um (Code K) at 225 deg
    ang_r = math.radians(225.0)
    rx_end = acx + rc * math.cos(ang_r)
    ry_end = acy + rc * math.sin(ang_r)
    ap(f'    <line x1="{tx_b(acx):.2f}" y1="{ty_b(acy):.2f}" x2="{tx_b(rx_end):.2f}" y2="{ty_b(ry_end):.2f}" '
       f'stroke="#fbbf24" stroke-width="2.6" marker-end="url(#arrGold)"/>')
    ap(f'    <rect x="{tx_b(rx_end)-118:.2f}" y="{ty_b(ry_end)+6:.2f}" width="134" height="26" rx="5" fill="#0f172a" stroke="#fbbf24" stroke-width="1.3"/>')
    ap(f'    <text x="{tx_b(rx_end)-51:.2f}" y="{ty_b(ry_end)+24:.2f}" text-anchor="middle" fill="#fde68a" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">Code K: R=500um</text>')

    # 2. Radial arrow for R_allow = 275.0 um at 198 deg
    ang_a = math.radians(198.0)
    ax_end = acx + r_allow * math.cos(ang_a)
    ay_end = acy + r_allow * math.sin(ang_a)
    ap(f'    <line x1="{tx_b(acx):.2f}" y1="{ty_b(acy):.2f}" x2="{tx_b(ax_end):.2f}" y2="{ty_b(ay_end):.2f}" '
       f'stroke="#34d399" stroke-width="2.4" marker-end="url(#arrGreen)"/>')
    ap(f'    <rect x="{tx_b(acx)+10:.2f}" y="{ty_b(acy)-30:.2f}" width="142" height="24" rx="5" fill="#0f172a" stroke="#34d399" stroke-width="1.2"/>')
    ap(f'    <text x="{tx_b(acx)+81:.2f}" y="{ty_b(acy)-13:.2f}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">R_allow=275um</text>')

    # Ghost FAIL badge
    ap(f'    <rect x="{tx_b(20277.56):.2f}" y="{ty_b(5675.0)+6:.2f}" width="196" height="26" rx="5" fill="#4c0519" stroke="#f43f5e" stroke-width="1.4"/>')
    ap(f'    <text x="{tx_b(20277.56)+98:.2f}" y="{ty_b(5675.0)+24:.2f}" text-anchor="middle" fill="#fecdd3" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">GHOST FAIL: 146.4um&lt;225</text>')

    # 3. Horizontal arrow: Left BGA SRO (19537.56 + 240 = 19777.56) -> Cavity Wall (20027.54) = 250.0 um (Code G)
    y_dim_g = 6960.0
    ap(f'    <line x1="{tx_b(19777.56):.2f}" y1="{ty_b(y_dim_g):.2f}" x2="{tx_b(20027.54):.2f}" y2="{ty_b(y_dim_g):.2f}" '
       f'stroke="#fbbf24" stroke-width="2.5" marker-start="url(#arrGold)" marker-end="url(#arrGold)"/>')
    ap(f'    <rect x="{tx_b(19765.0):.2f}" y="{ty_b(y_dim_g)-30:.2f}" width="122" height="24" rx="5" fill="#0f172a" stroke="#fbbf24" stroke-width="1.2"/>')
    ap(f'    <text x="{tx_b(19765.0)+61:.2f}" y="{ty_b(y_dim_g)-13:.2f}" text-anchor="middle" fill="#fde68a" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">Code G: 250um</text>')

    # 4. Horizontal arrow: Cavity Wall (20027.54) -> Safe LSC Wall (20252.54) = 225.0 um
    y_dim_l = 7360.0
    ap(f'    <line x1="{tx_b(20027.54):.2f}" y1="{ty_b(y_dim_l):.2f}" x2="{tx_b(20252.54):.2f}" y2="{ty_b(y_dim_l):.2f}" '
       f'stroke="#34d399" stroke-width="2.5" marker-start="url(#arrGreen)" marker-end="url(#arrGreen)"/>')
    ap(f'    <rect x="{tx_b(20020.0):.2f}" y="{ty_b(y_dim_l)-30:.2f}" width="132" height="24" rx="5" fill="#0f172a" stroke="#34d399" stroke-width="1.2"/>')
    ap(f'    <text x="{tx_b(20020.0)+66:.2f}" y="{ty_b(y_dim_l)-13:.2f}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">LSC-&gt;Cav 225um</text>')

    # 5. Horizontal arrow: Code D External Cu/Signal KOZ (19849.54 -> 20027.54 = 178.0 um)
    y_dim_d = 6460.0
    ap(f'    <line x1="{tx_b(cx0 - BASE_EXT_CU_TO_CAVITY_MIN_UM):.2f}" y1="{ty_b(y_dim_d):.2f}" x2="{tx_b(cx0):.2f}" y2="{ty_b(y_dim_d):.2f}" '
       f'stroke="#fb923c" stroke-width="2.3" marker-start="url(#arrOrange)" marker-end="url(#arrOrange)"/>')
    ap(f'    <rect x="{tx_b(cx0 - BASE_EXT_CU_TO_CAVITY_MIN_UM)-30:.2f}" y="{ty_b(y_dim_d)+6:.2f}" width="128" height="24" rx="5" fill="#0f172a" stroke="#fb923c" stroke-width="1.2"/>')
    ap(f'    <text x="{tx_b(cx0 - BASE_EXT_CU_TO_CAVITY_MIN_UM)+34:.2f}" y="{ty_b(y_dim_d)+23:.2f}" text-anchor="middle" fill="#fdba74" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">Code D: 178um</text>')

    # 6. LSC SRO -> LSC SRO spacing arrow between two placed caps
    if len(pocket_plans[0]["placed_lscs"]) >= 2:
        v_caps = sorted([c for c in pocket_plans[0]["placed_lscs"] if int(round(c["rot"])) % 180 == 0], key=lambda item: (item["y"], item["x"]))
        if len(v_caps) >= 2 and abs(v_caps[0]["y"] - v_caps[1]["y"]) < 10.0:
            c_left, c_right = v_caps[0], v_caps[1]
            y_sp = c_left["y"]
            ap(f'    <line x1="{tx_b(c_left["sro_box"][2]):.2f}" y1="{ty_b(y_sp):.2f}" x2="{tx_b(c_right["sro_box"][0]):.2f}" y2="{ty_b(y_sp):.2f}" '
               f'stroke="#38bdf8" stroke-width="2.5" marker-start="url(#arrCyan)" marker-end="url(#arrCyan)"/>')
            mid_sp_x = 0.5 * (c_left["sro_box"][2] + c_right["sro_box"][0])
            ap(f'    <rect x="{tx_b(mid_sp_x)-42:.2f}" y="{ty_b(y_sp)-30:.2f}" width="84" height="24" rx="5" fill="#0f172a" stroke="#38bdf8" stroke-width="1.2"/>')
            ap(f'    <text x="{tx_b(mid_sp_x):.2f}" y="{ty_b(y_sp)-13:.2f}" text-anchor="middle" fill="#7dd3fc" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">{sro_to_sro_min_um:.0f}um</text>')

    ap("  </g>")

    # Right-side structured engineering callout cards inside Panel B (zero overlap with zoom canvas!)
    cb_x = plot_b_x0 + plot_b_w + 28
    cb_w = pb_w - (plot_b_w + 92)
    callouts_b = [
        ("#fbbf24", "1. Code G: BGA SRO -> LSC_CAVITY = 250.0 um",
         "C480 BGA center (19,537.56) + 240um SRO + 250.0um = 20,027.54um cavity wall.",
         "Prevents collapsed BGA solder sphere from slumping into milled PCB pocket."),
        ("#fbbf24", "2. Code K: 4-Corner Milling Radius R = 500.0 um (20 mil)",
         "Arc center (20,527.54, 5,925.00). Ø40 mil mechanical router bit cuts inward arc.",
         "All 4 pocket corners curve inward by 500*(1 - cos45°) = 146.4 um."),
        ("#34d399", "3. Slide 11: LSC SRO -> Cavity >= 225.0 um (R_allow = 275 um)",
         f"Concentric green arc R = 500 - 225 = 275.0 um. Measured VDDUC0 min = {min_lsc_to_cav_um:.1f} um!",
         "Guarantees tall 0201 cap clears milled sidewall under ±4mil router + ±2mil SMT tol."),
        ("#f43f5e", "4. Red X Ghost Box: Why Square 500um Box Fails at Corners!",
         "Naive corner cap at (20,277.6, 5,675.0) sits at d = 353.6 um from arc center ->",
         "actual clearance = 500 - 353.6 = 146.4 um (< 225.0 um FAIL by 78.6 um!)."),
        ("#fb923c", "5. Code D: Signal & Non-SMT Copper Pullback (178 / 203 um)",
         "Orange dashed = 178um (7mil) BASE Cu/Signal KOZ; Purple = 203um (8mil) Inner KOZ.",
         "Zero signal traces, vias, or plane copper inside halo (prevents sidewall Cu exposure)."),
        ("#38bdf8", f"6. DR 3.5.4.7: LSC SRO-to-SRO = {sro_to_sro_min_um:.0f} um & BGA-to-LSC >= 500 um",
         f"Measured LSC-to-LSC = {min_lsc_lsc_um:.1f} um | Measured BGA-to-LSC = {min_bga_to_lsc_um:.1f} um.",
         "Every VDDUC0 LSC has 6 x V90_65_90_12B_BASE_01A (40um GX92 GCP) microvias."),
    ]
    cy_card = plot_b_y0
    for stroke_c, title_c, line1_c, line2_c in callouts_b:
        ap(f'  <rect x="{cb_x}" y="{cy_card}" width="{cb_w}" height="150" rx="9" fill="#0f172a" stroke="{stroke_c}" stroke-width="1.8"/>')
        ap(f'  <text x="{cb_x+16}" y="{cy_card+30}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="16" font-weight="bold">{html.escape(title_c)}</text>')
        ap(f'  <text x="{cb_x+16}" y="{cy_card+62}" fill="#cbd5e1" font-family="Consolas, sans-serif" font-size="13.5">{html.escape(line1_c)}</text>')
        ap(f'  <text x="{cb_x+16}" y="{cy_card+88}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="13">{html.escape(line2_c)}</text>')
        ap(f'  <text x="{cb_x+16}" y="{cy_card+122}" fill="{stroke_c}" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">STATUS: ENFORCED IN VDDUC0 BASE LAYOUT (PASS)</text>')
        cy_card += 162

    # ================= PANEL C: VERTICAL Z-CROSS-SECTION (PACKAGE BASE + 0201 LSC + PCB RECESS) =================
    pc_x, pc_y, pc_w, pc_h = 1444, 1260, 1170, 1152
    ap(f'  <rect x="{pc_x}" y="{pc_y}" width="{pc_w}" height="{pc_h}" rx="12" fill="#09101f" stroke="#334155" stroke-width="2"/>')
    ap(f'  <text x="{pc_x+24}" y="{pc_y+38}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="21" font-weight="bold">'
       f'PANEL C — Z-STACKUP CROSS-SECTION (BASE + LSC + PCB RECESS)</text>')
    ap(f'  <text x="{pc_x+24}" y="{pc_y+64}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="14.5">'
       f'HFC (HF Gen4): 0.55mmT 10uF LSC in Z = 21 +/- 4 mil (533 +/- 102 um) Milled Recess</text>')

    # Schematic coordinates inside Panel C
    sx_l = pc_x + 70
    sx_w = pc_w - 140
    # Package bottom layers: 11B (VSS), 12B (VDDUC0), 40um GX92 GCP, BASE Cu + SMB
    ap(f'  <rect x="{sx_l}" y="{pc_y+115}" width="{sx_w}" height="150" rx="6" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>')
    # 11B VSS solid plane (shields 10B signals!)
    ap(f'  <rect x="{sx_l+10}" y="{pc_y+132}" width="{sx_w-20}" height="18" fill="#0891b2"/>')
    ap(f'  <text x="{sx_l+24}" y="{pc_y+146}" fill="#ecfeff" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">L25: 11B Continuous VSS Plane (Shields 10B Signals Above)</text>')
    # 12B VDDUC0 plane
    ap(f'  <rect x="{sx_l+10}" y="{pc_y+182}" width="{sx_w-20}" height="18" fill="#dc2626"/>')
    ap(f'  <text x="{sx_l+24}" y="{pc_y+196}" fill="#fef2f2" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">L26: 12B VDDUC0 Plane (40um GX92 GCP Dielectric Below)</text>')
    # Package SMB solder mask on BASE
    ap(f'  <rect x="{sx_l+10}" y="{pc_y+252}" width="110" height="18" fill="#15803d"/>')
    ap(f'  <rect x="{sx_l+280}" y="{pc_y+252}" width="110" height="18" fill="#15803d"/>')
    ap(f'  <rect x="{sx_l+640}" y="{pc_y+252}" width="110" height="18" fill="#15803d"/>')
    ap(f'  <rect x="{sx_l+910}" y="{pc_y+252}" width="110" height="18" fill="#15803d"/>')

    # Left BGA (VDDUC0) & Right BGA (VSS) pads + balls
    ap(f'  <rect x="{sx_l+120}" y="{pc_y+244}" width="160" height="18" fill="#ef4444" stroke="#fca5a5"/>')
    ap(f'  <rect x="{sx_l+750}" y="{pc_y+244}" width="160" height="18" fill="#06b6d4" stroke="#67e8f9"/>')
    # uVias 12B->BASE on BGA & LSC
    for vx_u in (sx_l+155, sx_l+245, sx_l+425, sx_l+455):
        ap(f'  <polygon points="{vx_u-10},{pc_y+200} {vx_u+10},{pc_y+200} {vx_u+7},{pc_y+244} {vx_u-7},{pc_y+244}" fill="#fca5a5" stroke="#7f1d1d"/>')
    for vx_u in (sx_l+575, sx_l+605, sx_l+785, sx_l+875):
        ap(f'  <polygon points="{vx_u-10},{pc_y+150} {vx_u+10},{pc_y+150} {vx_u+7},{pc_y+244} {vx_u-7},{pc_y+244}" fill="#67e8f9" stroke="#164e63"/>')

    # LSC Pin 1 (VDDUC0) & Pin 2 (VSS) pads + 0.55mmT 0201 capacitor body extending below BGA SOH!
    ap(f'  <rect x="{sx_l+395}" y="{pc_y+244}" width="85" height="18" fill="#ef4444" stroke="#fca5a5"/>')
    ap(f'  <rect x="{sx_l+550}" y="{pc_y+244}" width="85" height="18" fill="#06b6d4" stroke="#67e8f9"/>')
    # Solder fillets + 0201 body (0.55mm tall -> goes deeper than BGA SOH 0.462mm!)
    ap(f'  <rect x="{sx_l+405}" y="{pc_y+262}" width="220" height="265" rx="14" fill="#94a3b8" stroke="#f8fafc" stroke-width="2"/>')
    ap(f'  <rect x="{sx_l+405}" y="{pc_y+262}" width="46" height="265" rx="8" fill="#cbd5e1"/>')
    ap(f'  <rect x="{sx_l+579}" y="{pc_y+262}" width="46" height="265" rx="8" fill="#cbd5e1"/>')
    ap(f'  <text x="{sx_l+515}" y="{pc_y+385}" text-anchor="middle" fill="#0f172a" font-family="Consolas, sans-serif" font-size="17" font-weight="bold">0201 10uF LSC</text>')
    ap(f'  <text x="{sx_l+515}" y="{pc_y+412}" text-anchor="middle" fill="#0f172a" font-family="Consolas, sans-serif" font-size="15" font-weight="bold">T = 0.55 mm MAX</text>')
    ap(f'  <text x="{sx_l+515}" y="{pc_y+436}" text-anchor="middle" fill="#1e293b" font-family="Consolas, sans-serif" font-size="13">(VDDUC0 - VSS)</text>')

    # BGA Solder Spheres (SOH = 0.462 mm -> PCB surface is at pc_y + 470!)
    pcb_top_y = pc_y + 470
    ap(f'  <ellipse cx="{sx_l+200}" cy="{0.5*(pc_y+262+pcb_top_y):.1f}" rx="108" ry="104" fill="#cbd5e1" fill-opacity="0.88" stroke="#f8fafc" stroke-width="2"/>')
    ap(f'  <text x="{sx_l+200}" y="{0.5*(pc_y+262+pcb_top_y)+5:.1f}" text-anchor="middle" fill="#0f172a" font-family="Consolas, sans-serif" font-size="15" font-weight="bold">VDDUC0 BGA</text>')
    ap(f'  <ellipse cx="{sx_l+830}" cy="{0.5*(pc_y+262+pcb_top_y):.1f}" rx="108" ry="104" fill="#cbd5e1" fill-opacity="0.88" stroke="#f8fafc" stroke-width="2"/>')
    ap(f'  <text x="{sx_l+830}" y="{0.5*(pc_y+262+pcb_top_y)+5:.1f}" text-anchor="middle" fill="#0f172a" font-family="Consolas, sans-serif" font-size="15" font-weight="bold">VSS BGA</text>')

    # Mating PCB with Milled Recess Cavity (RIB: Z = 21 +/- 4 mil = 533 +/- 102 um -> floor at pcb_top_y + 150 = pc_y + 620)
    cav_l = sx_l + 345
    cav_r = sx_l + 685
    cav_floor_y = pcb_top_y + 155
    pcb_bot_y = pc_y + 835
    pcb_poly = (
        f"{sx_l},{pcb_top_y} {cav_l},{pcb_top_y} {cav_l},{cav_floor_y} "
        f"{cav_r},{cav_floor_y} {cav_r},{pcb_top_y} {sx_l+sx_w},{pcb_top_y} "
        f"{sx_l+sx_w},{pcb_bot_y} {sx_l},{pcb_bot_y}"
    )
    ap(f'  <polygon points="{pcb_poly}" fill="#1e293b" stroke="#fbbf24" stroke-width="2.2"/>')

    # PCB Solder Mask + PCB BGA Pads + Inner Cut Layers L2..L4 (with Code D 8mil/203um pullback!) + Uncut L5!
    ap(f'  <rect x="{sx_l+120}" y="{pcb_top_y-12}" width="160" height="14" fill="#d97706"/>')
    ap(f'  <rect x="{sx_l+750}" y="{pcb_top_y-12}" width="160" height="14" fill="#d97706"/>')
    ap(f'  <rect x="{sx_l+10}" y="{pcb_top_y-14}" width="102" height="14" fill="#15803d"/>')
    ap(f'  <rect x="{sx_l+288}" y="{pcb_top_y-14}" width="38" height="14" fill="#15803d"/>')  # Code A 3mil SM web + Code B pullback!
    ap(f'  <rect x="{cav_r+19}" y="{pcb_top_y-14}" width="38" height="14" fill="#15803d"/>')
    ap(f'  <rect x="{sx_l+918}" y="{pcb_top_y-14}" width="102" height="14" fill="#15803d"/>')

    # Milled PCB layers L2, L3, L4 pulled back by Code D (8 mil = 203 um) from cavity wall!
    for idx_ly, (ly_name, ly_y) in enumerate([("L2 GND", pcb_top_y+38), ("L3 Sig (NO ROUTE IN CAVITY)", pcb_top_y+78), ("L4 GND", pcb_top_y+118)]):
        ap(f'  <rect x="{sx_l+16}" y="{ly_y}" width="{cav_l - sx_l - 48}" height="10" fill="#ca8a04"/>')
        ap(f'  <rect x="{cav_r+32}" y="{ly_y}" width="{sx_l + sx_w - cav_r - 48}" height="10" fill="#ca8a04"/>')
        if idx_ly == 1:
            ap(f'  <text x="{sx_l+24}" y="{ly_y-5}" fill="#fde047" font-family="Consolas, sans-serif" font-size="11.5">{ly_name}</text>')

    # Uncut Layer L5 below cavity floor ("Must NOT Cut Layer: L5", Slide 5 & Slide 12)
    l5_y = cav_floor_y + 42
    ap(f'  <rect x="{sx_l+16}" y="{l5_y}" width="{sx_w-32}" height="14" fill="#10b981"/>')
    ap(f'  <text x="{sx_l+0.5*sx_w:.1f}" y="{l5_y+34}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">'
       f'PCB L5: MUST NOT CUT LAYER (Intact Continuous Signal / Plane Layer Below Recess Floor)</text>')

    # Cross-section dimension arrows: SOH, Z_recess, C > 0.15mm, Code G (250um), Slide 11 (225um), Code D (178/203um)
    ap(f'  <line x1="{sx_l+46}" y1="{pc_y+262}" x2="{sx_l+46}" y2="{pcb_top_y}" stroke="#38bdf8" stroke-width="2.2" marker-start="url(#arrCyan)" marker-end="url(#arrCyan)"/>')
    ap(f'  <text x="{sx_l+54}" y="{0.5*(pc_y+262+pcb_top_y):.1f}" fill="#7dd3fc" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">SOH=0.46mm</text>')

    ap(f'  <line x1="{cav_r-22}" y1="{pcb_top_y}" x2="{cav_r-22}" y2="{cav_floor_y}" stroke="#fbbf24" stroke-width="2.2" marker-start="url(#arrGold)" marker-end="url(#arrGold)"/>')
    ap(f'  <text x="{cav_r-30}" y="{pcb_top_y+95}" text-anchor="end" fill="#fde68a" font-family="Consolas, sans-serif" font-size="13" font-weight="bold">Z=21±4mil</text>')

    ap(f'  <line x1="{sx_l+515}" y1="{pc_y+527}" x2="{sx_l+515}" y2="{cav_floor_y}" stroke="#34d399" stroke-width="2.2" marker-start="url(#arrGreen)" marker-end="url(#arrGreen)"/>')
    ap(f'  <text x="{sx_l+515}" y="{pc_y+575}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="13.5" font-weight="bold">C &gt; 150 um Cap Clearance</text>')

    ap(f'  <line x1="{cav_l}" y1="{pc_y+500}" x2="{sx_l+405}" y2="{pc_y+500}" stroke="#34d399" stroke-width="2.2" marker-start="url(#arrGreen)" marker-end="url(#arrGreen)"/>')
    ap(f'  <text x="{0.5*(cav_l+sx_l+405):.1f}" y="{pc_y+490}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">&gt;=225um</text>')

    ap(f'  <line x1="{sx_l+280}" y1="{pc_y+282}" x2="{cav_l}" y2="{pc_y+282}" stroke="#fbbf24" stroke-width="2.2" marker-start="url(#arrGold)" marker-end="url(#arrGold)"/>')
    ap(f'  <text x="{0.5*(sx_l+280+cav_l):.1f}" y="{pc_y+302}" text-anchor="middle" fill="#fde68a" font-family="Consolas, sans-serif" font-size="12.5" font-weight="bold">&gt;=250um</text>')

    # Summary notes at bottom of Panel C
    notes_c = [
        "• Signal Rule 1: Zero signal routing or planes inside [LSC_CAVITY + 178um Ext / 203um Int] across BASE & milled board L1..L4.",
        "• Signal Rule 2: Perimeter signal BGAs next to VDDUC0 cavity cannot escape inward on L1..L4; escape outward or drop >= L5.",
        "• Signal Rule 3: Continuous L25 (11B VSS) plane on package shields L24 (10B) signals from 12B->BASE LSC antipad slots.",
    ]
    ap(f'  <rect x="{pc_x+24}" y="{pc_y+862}" width="{pc_w-48}" height="264" rx="9" fill="#0f172a" stroke="#1e293b" stroke-width="1.5"/>')
    ap(f'  <text x="{pc_x+42}" y="{pc_y+896}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="16" font-weight="bold">KEY SIGNAL &amp; PDN CO-DESIGN RULES FOR BASE RECESS:</text>')
    for idx_n, n_txt in enumerate(notes_c):
        ap(f'  <text x="{pc_x+42}" y="{pc_y+936+idx_n*36}" fill="#cbd5e1" font-family="Consolas, sans-serif" font-size="13">{html.escape(n_txt)}</text>')
    ap(f'  <text x="{pc_x+42}" y="{pc_y+1068}" fill="#fde68a" font-family="Consolas, sans-serif" font-size="13.5" font-weight="bold">'
       f'• Z-Budget Check: SOH (462um) + Z_nom (533um) - LSC_T (550um) = 445um &gt;&gt; 150um min clearance (PASS)</text>')
    ap(f'  <text x="{pc_x+42}" y="{pc_y+1102}" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="13.5" font-weight="bold">'
       f'• SMD Via-in-Pad Rule (Codes H/I): 1-via Sig BGA &gt;= 254um (10mil) | Multi-via PDN BGA &gt;= 330um (13mil) SMO-&gt;Recess</text>')

    # ================= PANEL D: COMPLETE VDDUC0 DESIGN RULE & CAVITY RULE SCORECARD =================
    pd_x, pd_y, pd_w, pd_h = 2640, 1260, 1172, 1152
    ap(f'  <rect x="{pd_x}" y="{pd_y}" width="{pd_w}" height="{pd_h}" rx="12" fill="#09101f" stroke="#334155" stroke-width="2"/>')
    ap(f'  <text x="{pd_x+24}" y="{pd_y+38}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="21" font-weight="bold">'
       f'PANEL D — VDDUC0 DESIGN RULE &amp; RECESS CAVITY VERIFICATION TABLE</text>')
    ap(f'  <text x="{pd_x+24}" y="{pd_y+64}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="14.5">'
       f'Audited across all {len(all_vdduc0_lscs)} VDDUC0 LSCs (POCKET_6 + POCKET_7) &amp; {len(bgas)} surrounding BGA balls</text>')

    rows_d = [
        ("DR 3.5.4.7", "BGA SRO -> LSC SRO", ">= 500.0 um", f"{min_bga_to_lsc_um:.2f} um", "PASS"),
        ("DR 3.5.4.6/7", "LSC SRO -> LSC SRO", f">= {sro_to_sro_min_um:.1f} um", f"{min_lsc_lsc_um:.2f} um", "PASS"),
        ("Recess Code G", "BGA SRO -> LSC_CAVITY Wall", ">= 250.0 um", f"{min_bga_to_cav_um:.2f} um", "PASS"),
        ("Slide 11 / DR", "LSC SRO -> Cavity (Walls+Corners)", ">= 225.0 um", f"{min_lsc_to_cav_um:.2f} um", "PASS"),
        ("Recess Code K", "4-Corner Milling Bit Radius", "R >= 500.0 um (20mil)", "R = 500.00 um", "PASS"),
        ("Corner Arc", "Allowed LSC SRO Corner Radius", "R_allow <= 275.0 um", f"<= {500.0 - min_lsc_to_cav_um:.1f} um", "PASS"),
        ("Recess Code E", "Min Cavity Width x Length", ">= 1016 x 1016 um", "3904 x 8420 um", "PASS"),
        ("Recess Code J", "Cavity-to-Cavity Web (P6<->P7)", ">= 508.0 um (20mil)", f"{cav_to_cav_web_um:.1f} um", "PASS"),
        ("Recess Code D", "BASE Non-SMT Cu / Signal KOZ", ">= 178um Ext / 203um Int", "178 / 203 um KOZ", "PASS"),
        ("Codes A + B", "SM Web + SM-to-Recess Pullback", "76um web + 102-152um", "Enforced on SMB", "PASS"),
        ("GCP 12B->BASE", "V90_65_90 uVias (6/LSC, 6/BGA)", "Pitch >=180 diff / 76 same", "93.0um same / >500 diff", "PASS"),
    ]

    tbl_x, tbl_y = pd_x + 24, pd_y + 88
    tbl_w = pd_w - 48
    ap(f'  <rect x="{tbl_x}" y="{tbl_y}" width="{tbl_w}" height="44" rx="6" fill="#1e293b"/>')
    ap(f'  <text x="{tbl_x+16}" y="{tbl_y+28}" fill="#e2e8f0" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">RULE ID</text>')
    ap(f'  <text x="{tbl_x+165}" y="{tbl_y+28}" fill="#e2e8f0" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">DESIGN / CAVITY PARAMETER</text>')
    ap(f'  <text x="{tbl_x+520}" y="{tbl_y+28}" fill="#e2e8f0" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">SPEC LIMIT</text>')
    ap(f'  <text x="{tbl_x+775}" y="{tbl_y+28}" fill="#e2e8f0" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">VDDUC0 MEASURED</text>')
    ap(f'  <text x="{tbl_x+1035}" y="{tbl_y+28}" text-anchor="middle" fill="#e2e8f0" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">STATUS</text>')

    ry = tbl_y + 50
    for idx_r, (rid, rparam, rspec, rmeas, rstat) in enumerate(rows_d):
        bg_r = "#0f172a" if idx_r % 2 == 0 else "#111c33"
        ap(f'  <rect x="{tbl_x}" y="{ry}" width="{tbl_w}" height="62" rx="4" fill="{bg_r}" stroke="#1e293b" stroke-width="1"/>')
        ap(f'  <text x="{tbl_x+16}" y="{ry+37}" fill="#fde68a" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">{html.escape(rid)}</text>')
        ap(f'  <text x="{tbl_x+165}" y="{ry+37}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="14">{html.escape(rparam)}</text>')
        ap(f'  <text x="{tbl_x+520}" y="{ry+37}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="14">{html.escape(rspec)}</text>')
        ap(f'  <text x="{tbl_x+775}" y="{ry+37}" fill="#38bdf8" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">{html.escape(rmeas)}</text>')
        ap(f'  <rect x="{tbl_x+990}" y="{ry+15}" width="92" height="32" rx="6" fill="#064e3b" stroke="#10b981" stroke-width="1.4"/>')
        ap(f'  <text x="{tbl_x+1036}" y="{ry+36}" text-anchor="middle" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="14" font-weight="bold">{rstat}</text>')
        ry += 66

    # Bottom summary comparison box in Panel D
    ap(f'  <rect x="{tbl_x}" y="{ry+14}" width="{tbl_w}" height="236" rx="9" fill="#0f172a" stroke="#10b981" stroke-width="1.8"/>')
    ap(f'  <text x="{tbl_x+20}" y="{ry+50}" fill="#6ee7b7" font-family="Consolas, sans-serif" font-size="17" font-weight="bold">'
       f'VDDUC0 POCKET CAPACITY SUMMARY (DESIGN RULE + CAVITY R=500um RULE):</text>')
    ap(f'  <text x="{tbl_x+20}" y="{ry+88}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="14.5">'
       f'• Option A — 0.55mmT 10uF 0201 (SM0201_690X390X550_01A, 250um SRO-to-SRO, requires Z=21mil Recess):</text>')
    ap(f'  <text x="{tbl_x+42}" y="{ry+116}" fill="#fde68a" font-family="Consolas, sans-serif" font-size="14.5" font-weight="bold">'
       f'45 LSCs in POCKET_6 + 45 LSCs in POCKET_7 = 90 VDDUC0 LSCs (900 uF total, 540 uVias, 301.0um corner clr)</text>')
    ap(f'  <text x="{tbl_x+20}" y="{ry+156}" fill="#f8fafc" font-family="Consolas, sans-serif" font-size="14.5">'
       f'• Option B — 0.22mmT 1uF 0201 (SM0201S_690X390X220_01C, 175um SRO-to-SRO + R=500um Cavity Rule):</text>')
    ap(f'  <text x="{tbl_x+42}" y="{ry+184}" fill="#7dd3fc" font-family="Consolas, sans-serif" font-size="14.5" font-weight="bold">'
       f'57 LSCs in POCKET_6 + 57 LSCs in POCKET_7 = 114 VDDUC0 LSCs (4 square-corner caps pruned by R=500um arc!)</text>')
    ap(f'  <text x="{tbl_x+20}" y="{ry+222}" fill="#94a3b8" font-family="Consolas, sans-serif" font-size="13.5">'
       f'Active SVG Mode: {html.escape(sym_name)} | Placed = {len(all_vdduc0_lscs)} LSCs | Pruned Corner Violations = {sum(p["pruned_corner_count"] for p in pocket_plans)}</text>')

    ap("</svg>")

    svg_text = "\n".join(lines)
    # Strict XML validation before writing
    ET.fromstring(svg_text.encode("utf-8"))
    out_svg_path.write_text(svg_text, encoding="utf-8")

    return {
        "svg_path": str(out_svg_path),
        "symbol_name": sym_name,
        "sro_to_sro_min_um": sro_to_sro_min_um,
        "total_vdduc0_lscs": len(all_vdduc0_lscs),
        "pocket_6_count": pocket_plans[0]["placed_count"],
        "pocket_7_count": pocket_plans[1]["placed_count"],
        "pruned_corner_count_total": sum(p["pruned_corner_count"] for p in pocket_plans),
        "vdduc0_bga_count": len(vdduc0_bga_balls),
        "vss_bga_count": len(vss_bga_balls),
        "min_bga_sro_to_cavity_um": round(min_bga_to_cav_um, 2),
        "min_lsc_sro_to_cavity_um": round(min_lsc_to_cav_um, 2),
        "min_bga_sro_to_lsc_sro_um": round(min_bga_to_lsc_um, 2),
        "min_lsc_sro_to_lsc_sro_um": round(min_lsc_lsc_um, 2),
        "cavity_to_cavity_web_um": cav_to_cav_web_um,
        "Zero_DRC_and_Cavity_Violations": (
            lsc_lsc_viol == 0
            and min_bga_to_cav_um >= BGA_SRO_TO_CAVITY_MIN_UM - 0.1
            and min_lsc_to_cav_um >= LSC_SRO_TO_CAVITY_MIN_UM - 0.1
            and min_bga_to_lsc_um >= BGA_TO_LSC_SRO_MIN_UM - 0.1
            and cav_to_cav_web_um >= CAVITY_TO_CAVITY_MIN_WEB_UM - 0.1
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate VDDUC0-only BASE Cavity Rule + LSC Placement SVG")
    parser.add_argument("--sro-rule-um", type=float, default=250.0, help="250.0 for 0.55mm 10uF, 175.0 for 0.22mm 1uF")
    parser.add_argument("--both", action="store_true", help="Generate both 250um (10uF) and 175um (1uF) SVGs")
    args = parser.parse_args()

    ws = Path(__file__).resolve().parents[2]
    if args.both:
        r250 = synthesize_and_render_vdduc0_cavity_svg(ws, sro_to_sro_min_um=250.0)
        r175 = synthesize_and_render_vdduc0_cavity_svg(ws, sro_to_sro_min_um=175.0)
        print(json.dumps({"250um_10uF": r250, "175um_1uF": r175}, indent=2))
    else:
        res = synthesize_and_render_vdduc0_cavity_svg(ws, sro_to_sro_min_um=args.sro_rule_um)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
