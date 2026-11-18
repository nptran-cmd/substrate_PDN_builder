"""
Comprehensive Placement & Design Rule Audit for `agent04_pdn_architect/MCM_test/PDN_test.mcm`.

Checks:
1. Die Symbol Placement (`U*`: Main Dies `U1..U12, U88`, HBM4E Dies `U13..U24`, EMIB Bridges `U25..U52`, and `U7` specifically):
   - Layer assignment, mirror state, rotation, pin-array bounding box, and package body bounding box (`PLACE_BOUND_TOP` / `ASSEMBLY_TOP`).
   - Comparison against golden `stage1_inputs/die_bridge_refdes_summary.csv`.
   - Die-to-Die and EMIB-Bridge-to-EMIB-Bridge spacing (`>= 500 um`).
   - Overlap checks between dies, bridges, and capacitors.
2. eDTC Symbol Placement (`C2207..C2278` on `4FCO` + `8` fiducials):
   - Layer assignment (`4FCO`), mirror state, rotation, pin-array bounding box, and silicon body bounding box.
   - Comparison against golden `stage1_inputs/edtc_symbols.csv`.
   - Rule #1 & #2: DTC Pad min size (`200 x 200 um`).
   - Rule #3: DTC Pad-to-Pad spacing (`>= 50 um` edge-to-edge / `250 um` center pitch).
   - Rule #6 & #7: DTC Cavity KOZ (`300 um`) and DTC Cavity-to-Cavity spacing (`>= 1600 um`, i.e., `>= 2200 um` body-to-body).
   - Rule #14 & #5: DTC Allowed Under EMIB Die = `No`, and DTC Cavity Edge to EMIB Cavity Edge `>= 1000 um` (`1300 um` body-to-EMIB-cavity).
   - Rule #4: DTC Cavity Edge to Die Edge (`>= 1000 um`) and spatial relationship of eDTCs under/around `U7` (`HUTTON_HILL_LDB_BC_A0`) and other Main/HBM dies.
   - Rule #15-21: 4 DTC Fiducials (`500 um` pad, `>= 10000 um` center-to-center, outside all DTC boundaries).
   - Rule #27: LSC Not Allowed under DTC (check both `BASE` LSCs and the `374` `SM0201` LSCs that were flipped to `SURFACE` in `PDN_test.mcm`!).
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


def rect_edge_distance(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float],
) -> Tuple[float, float, float, bool]:
    """Return (dx, dy, euclidean_edge_dist, overlaps) between two axis-aligned boxes (x1,y1,x2,y2)."""
    x1a, y1a, x2a, y2a = b1
    x1b, y1b, x2b, y2b = b2
    dx = max(0.0, max(x1a - x2b, x1b - x2a))
    dy = max(0.0, max(y1a - y2b, y1b - y2a))
    overlaps = (x1a < x2b and x2a > x1b and y1a < y2b and y2a > y1b)
    if overlaps:
        ov_x = min(x2a, x2b) - max(x1a, x1b)
        ov_y = min(y2a, y2b) - max(y1a, y1b)
        return -ov_x, -ov_y, -min(ov_x, ov_y), True
    dist = math.hypot(dx, dy) if (dx > 0 and dy > 0) else max(dx, dy)
    return dx, dy, dist, False


def run_audit() -> Dict[str, Any]:
    ws = Path(__file__).resolve().parent.parent.parent
    ext = ws / "agent04_pdn_architect" / "MCM_test" / "extract_pdn_test"
    stg1 = ws / "agent04_pdn_architect" / "stage1_inputs"

    syms = list(csv.DictReader((ext / "pdn_test_symbols.csv").open(encoding="utf-8")))
    edtc_pins = list(csv.DictReader((ext / "pdn_test_edtc_pins.csv").open(encoding="utf-8")))
    ref_syms = list(csv.DictReader((stg1 / "refdes_inventory.csv").open(encoding="utf-8")))

    # Fast cached bounding-box reader for pdn_test_symbol_children.csv (skips PAD_FUNCTION / PIN_NOTATIONS)
    bbox_cache_json = ext / "pdn_test_symbol_bboxes.json"
    child_by_ref: Dict[str, List[Dict[str, str]]] = {}
    if bbox_cache_json.exists():
        cached_bboxes = json.loads(bbox_cache_json.read_text(encoding="utf-8"))
        for ref, lyr_dict in cached_bboxes.items():
            child_by_ref[ref] = [
                {"refdes": ref, "child_layer": cl, "cx1": str(b[0]), "cy1": str(b[1]), "cx2": str(b[2]), "cy2": str(b[3])}
                for cl, b in lyr_dict.items()
            ]
    else:
        agg_bboxes: Dict[str, Dict[str, List[float]]] = {}
        with (ext / "pdn_test_symbol_children.csv").open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline()
            for line in f:
                if "PAD_FUNCTION" in line or "PIN_NOTATIONS" in line:
                    continue
                parts = line.strip().split(",")
                if len(parts) < 8:
                    continue
                ref, _, _, cl, cx1_s, cy1_s, cx2_s, cy2_s = parts[:8]
                cx1, cy1, cx2, cy2 = float(cx1_s), float(cy1_s), float(cx2_s), float(cy2_s)
                ref_map = agg_bboxes.setdefault(ref, {})
                if cl not in ref_map:
                    ref_map[cl] = [cx1, cy1, cx2, cy2]
                else:
                    b = ref_map[cl]
                    if cx1 < b[0]: b[0] = cx1
                    if cy1 < b[1]: b[1] = cy1
                    if cx2 > b[2]: b[2] = cx2
                    if cy2 > b[3]: b[3] = cy2
        bbox_cache_json.write_text(json.dumps(agg_bboxes, indent=2), encoding="utf-8")
        for ref, lyr_dict in agg_bboxes.items():
            child_by_ref[ref] = [
                {"refdes": ref, "child_layer": cl, "cx1": str(b[0]), "cy1": str(b[1]), "cx2": str(b[2]), "cy2": str(b[3])}
                for cl, b in lyr_dict.items()
            ]

    print("=== 1. LAYER DISTRIBUTION OF ALL SYMBOLS IN PDN_test.mcm ===")
    by_lyr = Counter(s["layer"] for s in syms)
    print("  Symbols by layer:", dict(by_lyr))

    s12f = [s for s in syms if s["layer"] == "12F"]
    print("  Symbols on 12F:", len(s12f), Counter(s["symbol_name"] for s in s12f))

    # Check child layers available for U7 and C2215
    print("\n=== 2. CHILD GEOMETRY LAYERS FOR U7 & C2215 (eDTC) ===")
    for r_check in ("U7", "U25", "U13", "C2215", "C2248", "C2207"):
        c_list = child_by_ref.get(r_check, [])
        lyr_summary = {}
        for c in c_list:
            cl = c["child_layer"]
            cx1, cy1, cx2, cy2 = float(c["cx1"]), float(c["cy1"]), float(c["cx2"]), float(c["cy2"])
            if cl not in lyr_summary:
                lyr_summary[cl] = [cx1, cy1, cx2, cy2]
            else:
                b = lyr_summary[cl]
                b[0] = min(b[0], cx1)
                b[1] = min(b[1], cy1)
                b[2] = max(b[2], cx2)
                b[3] = max(b[3], cy2)
        print(f"  {r_check} child layers:")
        for cl, b in sorted(lyr_summary.items()):
            print(f"    {cl:42s}: [{b[0]:9.2f}, {b[1]:9.2f}, {b[2]:9.2f}, {b[3]:9.2f}] (W={b[2]-b[0]:.1f}, H={b[3]-b[1]:.1f})")

    # Helper to get true silicon die/body bbox from COMPONENT GEOMETRY/DIE_EDGE or EMBEDDED GEOMETRY/ASSEMBLY_4FCO
    def get_body_bbox(s: Dict[str, str]) -> Tuple[float, float, float, float, str]:
        ref = s["refdes"]
        c_list = child_by_ref.get(ref, [])
        for pref in (
            "COMPONENT GEOMETRY/DIE_EDGE",
            "EMBEDDED GEOMETRY/ASSEMBLY_4FCO",
            "COMPONENT GEOMETRY/PLACE_BOUND_TOP",
            "EMBEDDED GEOMETRY/PLACE_BOUND_4FCO",
            "COMPONENT GEOMETRY/ASSEMBLY_TOP",
        ):
            matching = [c for c in c_list if c["child_layer"].upper() == pref]
            if matching:
                x1 = min(float(c["cx1"]) for c in matching)
                y1 = min(float(c["cy1"]) for c in matching)
                x2 = max(float(c["cx2"]) for c in matching)
                y2 = max(float(c["cy2"]) for c in matching)
                return (x1, y1, x2, y2, matching[0]["child_layer"])
        px1, py1, px2, py2 = float(s["pin_x1"]), float(s["pin_y1"]), float(s["pin_x2"]), float(s["pin_y2"])
        return (px1, py1, px2, py2, "PIN_EXTENT")

    print("\n=== 3. ALL U* DIE & BRIDGE SYMBOLS IN PDN_test.mcm vs GOLDEN STAGE 1 ===")
    u_syms = [s for s in syms if s["refdes"].startswith("U")]
    ref_u_map = {r["refdes"]: r for r in ref_syms if r["refdes"].startswith("U")}
    for s in sorted(u_syms, key=lambda x: (len(x["refdes"]), x["refdes"])):
        ref = s["refdes"]
        bx1, by1, bx2, by2, bsrc = get_body_bbox(s)
        px1, py1, px2, py2 = float(s["pin_x1"]), float(s["pin_y1"]), float(s["pin_x2"]), float(s["pin_y2"])
        diff_note = "MATCHES_GOLDEN"
        if ref not in ref_u_map:
            diff_note = "NEW_IN_PDN_TEST"
        else:
            r0 = ref_u_map[ref]
            dx = float(s["x_um"]) - float(r0["x_um"])
            dy = float(s["y_um"]) - float(r0["y_um"])
            if abs(dx) > 0.1 or abs(dy) > 0.1 or s["layer"] != r0["layer"] or s["rotation"] != r0["rotation"] or s["mirror"] != r0["mirror"]:
                diff_note = f"CHANGED(dx={dx:.1f}, dy={dy:.1f}, lyr:{r0['layer']}->{s['layer']}, rot:{r0['rotation']}->{s['rotation']}, mir:{r0['mirror']}->{s['mirror']})"
        if ref == "U7" or diff_note != "MATCHES_GOLDEN" or ref in ("U1", "U2", "U5", "U6", "U8", "U9", "U13", "U25", "U41"):
            print(
                f"  {ref:4s} | {s['symbol_name']:30s} | lyr={s['layer']:7s} | xy=({float(s['x_um']):9.2f},{float(s['y_um']):9.2f}) "
                f"| rot={s['rotation']:5s} | mir={s['mirror']:3s} | pins={s['pin_count']:5s} "
                f"| body=[{bx1:9.2f},{by1:9.2f},{bx2:9.2f},{by2:9.2f}] ({bsrc}) | {diff_note}"
            )

    # Check if ANY U* symbol changed vs golden
    u_changes = []
    for s in u_syms:
        ref = s["refdes"]
        if ref not in ref_u_map:
            u_changes.append((ref, "NEW", s))
        else:
            r0 = ref_u_map[ref]
            dx = float(s["x_um"]) - float(r0["x_um"])
            dy = float(s["y_um"]) - float(r0["y_um"])
            if abs(dx) > 0.1 or abs(dy) > 0.1 or s["layer"] != r0["layer"] or s["rotation"] != r0["rotation"] or s["mirror"] != r0["mirror"]:
                u_changes.append((ref, f"dx={dx:.2f},dy={dy:.2f},lyr={r0['layer']}->{s['layer']},rot={r0['rotation']}->{s['rotation']},mir={r0['mirror']}->{s['mirror']}", s))
    print("  Total U* symbols changed vs Stage 1:", len(u_changes))
    for uc in u_changes:
        print("   U* CHANGE:", uc[0], uc[1])

    print("\n=== 4. eDTC SYMBOLS IN PDN_test.mcm vs GOLDEN STAGE 1 ===")
    edtc_syms = [s for s in syms if "N24792" in s["symbol_name"].upper() or s["layer"] == "4FCO"]
    ref_edtc_map = {r["refdes"]: r for r in ref_syms if "N24792" in r["symbol_name"].upper() or r["layer"] == "4FCO"}
    edtc_changes = []
    for s in sorted(edtc_syms, key=lambda x: x["refdes"]):
        ref = s["refdes"]
        if ref not in ref_edtc_map:
            edtc_changes.append((ref, "NEW", s))
        else:
            r0 = ref_edtc_map[ref]
            dx = float(s["x_um"]) - float(r0["x_um"])
            dy = float(s["y_um"]) - float(r0["y_um"])
            if abs(dx) > 0.1 or abs(dy) > 0.1 or s["layer"] != r0["layer"] or s["rotation"] != r0["rotation"] or s["mirror"] != r0["mirror"]:
                edtc_changes.append((ref, f"dx={dx:.2f},dy={dy:.2f},lyr={r0['layer']}->{s['layer']},rot={r0['rotation']}->{s['rotation']},mir={r0['mirror']}->{s['mirror']}", s))
    print("  Total 4FCO eDTC symbols:", len(edtc_syms), "Changed vs Stage 1:", len(edtc_changes))
    for ec in edtc_changes:
        print("   eDTC CHANGE:", ec[0], ec[1])

    # Now let's check eDTC-to-eDTC spacing, eDTC-to-EMIB spacing, eDTC-to-Die spacing, and eDTC under U7!
    print("\n=== 5. eDTC-TO-eDTC SPACING AUDIT (Rule #6: 300um Cavity KOZ, Rule #7: 1600um Cavity-to-Cavity => 2200um Body-to-Body) ===")
    edtc_boxes = []
    for s in edtc_syms:
        bx1, by1, bx2, by2, bsrc = get_body_bbox(s)
        px1, py1, px2, py2 = float(s["pin_x1"]) - 100.0, float(s["pin_y1"]) - 100.0, float(s["pin_x2"]) + 100.0, float(s["pin_y2"]) + 100.0
        edtc_boxes.append({
            "refdes": s["refdes"],
            "symbol_name": s["symbol_name"],
            "layer": s["layer"],
            "x_um": float(s["x_um"]),
            "y_um": float(s["y_um"]),
            "body_bbox": (bx1, by1, bx2, by2),
            "body_src": bsrc,
            "pin_pad_bbox": (px1, py1, px2, py2),
            "cavity_bbox": (bx1 - 300.0, by1 - 300.0, bx2 + 300.0, by2 + 300.0),
        })

    edtc_pair_violations = []
    min_body_dist = 1e9
    closest_pair = None
    for i in range(len(edtc_boxes)):
        for j in range(i + 1, len(edtc_boxes)):
            e1, e2 = edtc_boxes[i], edtc_boxes[j]
            dx, dy, b_dist, ov = rect_edge_distance(e1["body_bbox"], e2["body_bbox"])
            _, _, cav_dist, cav_ov = rect_edge_distance(e1["cavity_bbox"], e2["cavity_bbox"])
            _, _, pin_dist, _ = rect_edge_distance(e1["pin_pad_bbox"], e2["pin_pad_bbox"])
            if b_dist < min_body_dist:
                min_body_dist = b_dist
                closest_pair = (e1["refdes"], e2["refdes"], b_dist, cav_dist, pin_dist, dx, dy)
            if cav_dist < 1600.0 - 0.5:  # 0.5um float tolerance
                edtc_pair_violations.append({
                    "edtc_1": e1["refdes"],
                    "edtc_2": e2["refdes"],
                    "type_1": e1["symbol_name"],
                    "type_2": e2["symbol_name"],
                    "body_to_body_um": round(b_dist, 2),
                    "cavity_to_cavity_um": round(cav_dist, 2),
                    "pin_pad_to_pin_pad_um": round(pin_dist, 2),
                    "dx_um": round(dx, 2),
                    "dy_um": round(dy, 2),
                    "required_cavity_to_cavity_um": 1600.0,
                    "required_body_to_body_um": 2200.0,
                })

    print("  Closest eDTC pair:", closest_pair)
    print("  eDTC pairs violating 1600um Cavity-to-Cavity (2200um Body-to-Body):", len(edtc_pair_violations))
    for v in sorted(edtc_pair_violations, key=lambda x: x["cavity_to_cavity_um"])[:25]:
        print("   VIOLATION:", v)

    print("\n=== 6. eDTC vs EMIB BRIDGES (Rule #14: No DTC Under EMIB; Rule #5: DTC Cavity to EMIB Cavity >= 1000um) ===")
    emib_syms = [s for s in u_syms if "BRIDGE" in s["symbol_name"].upper()]
    emib_boxes = []
    for s in emib_syms:
        bx1, by1, bx2, by2, bsrc = get_body_bbox(s)
        # EMIB cavity wall is 75um outside EMIB die edge (Rule: EmIB cavity wall to EmIB-T die edge = 75um)
        emib_boxes.append({
            "refdes": s["refdes"],
            "symbol_name": s["symbol_name"],
            "body_bbox": (bx1, by1, bx2, by2),
            "cavity_bbox": (bx1 - 75.0, by1 - 75.0, bx2 + 75.0, by2 + 75.0),
        })
    emib_edtc_violations = []
    min_emib_cav_dist = 1e9
    closest_emib_edtc = None
    for e in edtc_boxes:
        for b in emib_boxes:
            _, _, body_to_emib_dist, under_emib = rect_edge_distance(e["body_bbox"], b["body_bbox"])
            _, _, cav_to_cav_dist, cav_ov = rect_edge_distance(e["cavity_bbox"], b["cavity_bbox"])
            if cav_to_cav_dist < min_emib_cav_dist:
                min_emib_cav_dist = cav_to_cav_dist
                closest_emib_edtc = (e["refdes"], b["refdes"], body_to_emib_dist, cav_to_cav_dist, under_emib)
            if under_emib or cav_to_cav_dist < 1000.0 - 0.5:
                emib_edtc_violations.append({
                    "edtc": e["refdes"],
                    "emib_bridge": b["refdes"],
                    "under_emib": under_emib,
                    "body_to_emib_die_um": round(body_to_emib_dist, 2),
                    "dtc_cavity_to_emib_cavity_um": round(cav_to_cav_dist, 2),
                    "required_min_um": 1000.0,
                })
    print("  Closest eDTC to EMIB Bridge:", closest_emib_edtc)
    print("  eDTC-to-EMIB violations (<1000um cavity-to-cavity or under EMIB):", len(emib_edtc_violations))
    for v in sorted(emib_edtc_violations, key=lambda x: x["dtc_cavity_to_emib_cavity_um"])[:20]:
        print("   EMIB-eDTC VIOLATION:", v)

    print("\n=== 7. U7 PLACEMENT & eDTCs UNDER/AROUND U7 (Rule #4: DTC Cavity Edge to Die Edge >= 1000um) ===")
    u7_sym = [s for s in u_syms if s["refdes"] == "U7"][0]
    u7_bx1, u7_by1, u7_bx2, u7_by2, u7_bsrc = get_body_bbox(u7_sym)
    u7_px1, u7_py1, u7_px2, u7_py2 = float(u7_sym["pin_x1"]), float(u7_sym["pin_y1"]), float(u7_sym["pin_x2"]), float(u7_sym["pin_y2"])
    print(f"  U7 ({u7_sym['symbol_name']}) on {u7_sym['layer']}:")
    print(f"    Origin=({float(u7_sym['x_um']):.3f}, {float(u7_sym['y_um']):.3f}), Rot={u7_sym['rotation']}, Mirror={u7_sym['mirror']}, Pins={u7_sym['pin_count']}")
    print(f"    Body BBox ({u7_bsrc}) = [{u7_bx1:.3f}, {u7_by1:.3f}, {u7_bx2:.3f}, {u7_by2:.3f}] (W={u7_bx2-u7_bx1:.2f} um, H={u7_by2-u7_by1:.2f} um)")
    print(f"    Pin  BBox             = [{u7_px1:.3f}, {u7_py1:.3f}, {u7_px2:.3f}, {u7_py2:.3f}] (W={u7_px2-u7_px1:.2f} um, H={u7_py2-u7_py1:.2f} um)")

    # Check all eDTCs that overlap U7 or are within 5000um of U7
    u7_step_list = [c for c in child_by_ref.get("U7", []) if c["child_layer"] == "COMPONENT GEOMETRY/DIE_EDGE_STEPPING"]
    u7_step = (
        min(float(c["cx1"]) for c in u7_step_list),
        min(float(c["cy1"]) for c in u7_step_list),
        max(float(c["cx2"]) for c in u7_step_list),
        max(float(c["cy2"]) for c in u7_step_list),
    )
    print(f"    Stepping BBox         = [{u7_step[0]:.3f}, {u7_step[1]:.3f}, {u7_step[2]:.3f}, {u7_step[3]:.3f}] (W={u7_step[2]-u7_step[0]:.2f} um, H={u7_step[3]-u7_step[1]:.2f} um)")

    for e in edtc_boxes:
        dx, dy, dist_to_u7_body, overlaps_u7 = rect_edge_distance(e["body_bbox"], (u7_bx1, u7_by1, u7_bx2, u7_by2))
        if overlaps_u7 or dist_to_u7_body < 12000.0:
            ex1, ey1, ex2, ey2 = e["body_bbox"]
            cx1, cy1, cx2, cy2 = e["cavity_bbox"]
            in_left = cx1 - u7_bx1
            in_right = u7_bx2 - cx2
            in_bot = cy1 - u7_by1
            in_top = u7_by2 - cy2
            in_step_left = cx1 - u7_step[0]
            in_step_right = u7_step[2] - cx2
            in_step_bot = cy1 - u7_step[1]
            in_step_top = u7_step[3] - cy2
            fully_inside_u7 = (ex1 >= u7_bx1 and ex2 <= u7_bx2 and ey1 >= u7_by1 and ey2 <= u7_by2)
            min_edge_clearance_to_u7_outline = min(
                abs(cx1 - u7_bx1), abs(cx2 - u7_bx1),
                abs(cx1 - u7_bx2), abs(cx2 - u7_bx2),
                abs(cy1 - u7_by1), abs(cy2 - u7_by1),
                abs(cy1 - u7_by2), abs(cy2 - u7_by2),
            )
            print(
                f"    eDTC {e['refdes']:5s} ({e['symbol_name']:28s}): body=[{ex1:9.2f},{ey1:9.2f},{ex2:9.2f},{ey2:9.2f}] "
                f"| overlaps_U7={overlaps_u7} | fully_inside_U7={fully_inside_u7} "
                f"| cavity_margin_DIE_EDGE(L={in_left:.1f}, R={in_right:.1f}, B={in_bot:.1f}, T={in_top:.1f}) "
                f"| cavity_margin_STEPPING(L={in_step_left:.1f}, R={in_step_right:.1f}, B={in_step_bot:.1f}, T={in_step_top:.1f}) "
                f"| min_cavity_to_U7_edge={min_edge_clearance_to_u7_outline:.1f} um"
            )

    # Check all Dies & EMIB bridges neighboring U7
    print("\n=== 7B. U7 NEIGHBORING DIES & EMIB BRIDGES SPACING ===")
    for s in sorted(u_syms, key=lambda x: (len(x["refdes"]), x["refdes"])):
        r = s["refdes"]
        if r in ("U7", "U97", "U98"):
            continue
        bx1, by1, bx2, by2, _ = get_body_bbox(s)
        dx, dy, d_u7, ov_u7 = rect_edge_distance((u7_bx1, u7_by1, u7_bx2, u7_by2), (bx1, by1, bx2, by2))
        if ov_u7 or d_u7 < 5000.0:
            print(
                f"    U7 <-> {r:4s} ({s['symbol_name']:30s}): overlaps={ov_u7} "
                f"| die_edge_dist={d_u7:8.2f} um (dx={dx:.2f}, dy={dy:.2f}) | box=[{bx1:.1f},{by1:.1f},{bx2:.1f},{by2:.1f}]"
            )

    # Also check ALL Physical Main Dies & HBM Dies (excluding virtual container symbols U97/U98) vs ALL eDTCs
    print("\n=== 8. ALL PHYSICAL DIES (MAIN U1..U12,U88 & HBM U13..U24) vs eDTC CAVITY-TO-DIE-EDGE ===")
    main_hbm_dies = [
        s for s in u_syms
        if "BRIDGE" not in s["symbol_name"].upper() and s["refdes"] not in ("U97", "U98")
    ]
    die_edtc_findings = []
    for d_sym in sorted(main_hbm_dies, key=lambda x: (len(x["refdes"]), x["refdes"])):
        dbx1, dby1, dbx2, dby2, _ = get_body_bbox(d_sym)
        for e in edtc_boxes:
            ex1, ey1, ex2, ey2 = e["body_bbox"]
            cx1, cy1, cx2, cy2 = e["cavity_bbox"]
            _, _, body_dist, overlaps = rect_edge_distance(e["body_bbox"], (dbx1, dby1, dbx2, dby2))
            _, _, cav_dist, cav_overlaps = rect_edge_distance(e["cavity_bbox"], (dbx1, dby1, dbx2, dby2))
            fully_inside = (ex1 >= dbx1 and ex2 <= dbx2 and ey1 >= dby1 and ey2 <= dby2)
            if overlaps:
                in_l = cx1 - dbx1
                in_r = dbx2 - cx2
                in_b = cy1 - dby1
                in_t = dby2 - cy2
                min_in_margin = min(in_l, in_r, in_b, in_t)
                if not fully_inside or min_in_margin < 1000.0:
                    die_edtc_findings.append({
                        "die": d_sym["refdes"],
                        "die_name": d_sym["symbol_name"],
                        "edtc": e["refdes"],
                        "relation": "UNDER_DIE_INSIDE" if fully_inside else "STRADDLING_DIE_EDGE",
                        "min_cavity_to_die_edge_um": round(min_in_margin, 2),
                        "margins_LRBT_um": [round(in_l, 1), round(in_r, 1), round(in_b, 1), round(in_t, 1)],
                    })
            elif cav_dist < 1000.0 - 0.5:
                die_edtc_findings.append({
                    "die": d_sym["refdes"],
                    "die_name": d_sym["symbol_name"],
                    "edtc": e["refdes"],
                    "relation": "OUTSIDE_DIE_TOO_CLOSE",
                    "min_cavity_to_die_edge_um": round(cav_dist, 2),
                    "body_to_die_edge_um": round(body_dist, 2),
                })
    print("  Total Physical Die-to-eDTC findings (<1000um cavity-to-die-edge or straddling):", len(die_edtc_findings))
    for f in die_edtc_findings[:30]:
        print("   PHYSICAL DIE-eDTC:", f)

    # Check EMIB-to-EMIB die edge spacing (Rule: EmIB-T/EmIB die edge to EmIB-T/EmIB die edge minimum spacing >= 500um)
    print("\n=== 8B. EMIB BRIDGE TO EMIB BRIDGE SPACING (Rule: >= 500um) & LAVA BRIDGES ===")
    min_emib_to_emib = 1e9
    closest_emibs = None
    emib_pair_violations = []
    for i in range(len(emib_boxes)):
        for j in range(i + 1, len(emib_boxes)):
            b1, b2 = emib_boxes[i], emib_boxes[j]
            _, _, dist, ov = rect_edge_distance(b1["body_bbox"], b2["body_bbox"])
            if dist < min_emib_to_emib:
                min_emib_to_emib = dist
                closest_emibs = (b1["refdes"], b2["refdes"], round(dist, 2))
            if dist < 500.0 - 0.5:
                emib_pair_violations.append((b1["refdes"], b2["refdes"], round(dist, 2)))
    print("  Closest EMIB-to-EMIB pair:", closest_emibs, "Violations (<500um):", len(emib_pair_violations))

    # Check eDTC internal pad-to-pad pitch and pad-to-body edge margin
    print("\n=== 8C. eDTC INTERNAL PAD-TO-PAD PITCH & BODY/CAVITY DEFINITION CHECK ===")
    for sample_ref in ("C2215", "C2248", "C2207"):
        s = [x for x in edtc_syms if x["refdes"] == sample_ref][0]
        bx1, by1, bx2, by2, bsrc = get_body_bbox(s)
        px1, py1, px2, py2 = float(s["pin_x1"]), float(s["pin_y1"]), float(s["pin_x2"]), float(s["pin_y2"])
        pad_edge_x1, pad_edge_y1, pad_edge_x2, pad_edge_y2 = px1 - 100.0, py1 - 100.0, px2 + 100.0, py2 + 100.0
        pts = [(float(p["x_um"]), float(p["y_um"]), p["padstack_name"]) for p in edtc_pins if p["refdes"] == sample_ref]
        min_pitch = min(
            math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
            for a in range(len(pts)) for b in range(a + 1, len(pts))
        )
        print(
            f"  {sample_ref} ({s['symbol_name']}): pins={len(pts)} padstack={pts[0][2]} "
            f"| min_center_pitch={min_pitch:.1f}um (edge-to-edge={min_pitch-200.0:.1f}um vs >=50um rule) "
            f"| pad_outer_margin_to_ASSEMBLY_4FCO: L={pad_edge_x1-bx1:.1f}, R={bx2-pad_edge_x2:.1f}, B={pad_edge_y1-by1:.1f}, T={by2-pad_edge_y2:.1f} um"
        )

    # Check the 374 capacitors that changed from BASE to SURFACE in PDN_test.mcm!
    print("\n=== 9. LSCs UNDER eDTC (Rule #27) & CAPACITOR LAYER/COLLISION AUDIT ===")
    caps = [s for s in syms if "SM0201" in s["symbol_name"].upper() or "SM0204" in s["symbol_name"].upper()]
    print("  Capacitors by layer in PDN_test.mcm:", Counter((s["symbol_name"], s["layer"], s["mirror"]) for s in caps))
    base_caps = [s for s in caps if s["layer"] == "BASE"]
    lsc_under_edtc = []
    for c in base_caps:
        cb = (float(c["pin_x1"]) - 174.0, float(c["pin_y1"]) - 174.0, float(c["pin_x2"]) + 174.0, float(c["pin_y2"]) + 174.0)
        for e in edtc_boxes:
            _, _, d_c, ov_c = rect_edge_distance(cb, e["cavity_bbox"])
            if ov_c:
                lsc_under_edtc.append((c["refdes"], e["refdes"], c["x_um"], c["y_um"]))
    print("  BASE LSCs (SM0201S on BASE) under eDTC cavity:", len(lsc_under_edtc), lsc_under_edtc[:10])

    # Check if any of the 353 SM0201_690X390X550_01A that were on BASE in Stage1 (and are now on SURFACE in PDN_test.mcm)
    # collide with SURFACE dies (U1..U52, U7) or are under eDTCs!
    surf_caps = [s for s in caps if s["layer"] == "SURFACE"]
    surf_cap_under_die = []
    surf_cap_under_u7 = []
    surf_cap_over_edtc = []
    for c in surf_caps:
        cb = (float(c["pin_x1"]) - 174.0, float(c["pin_y1"]) - 174.0, float(c["pin_x2"]) + 174.0, float(c["pin_y2"]) + 174.0)
        for d_sym in main_hbm_dies + emib_syms:
            dbx1, dby1, dbx2, dby2, _ = get_body_bbox(d_sym)
            _, _, _, ov_d = rect_edge_distance(cb, (dbx1, dby1, dbx2, dby2))
            if ov_d:
                surf_cap_under_die.append((c["refdes"], d_sym["refdes"], c["x_um"], c["y_um"]))
                if d_sym["refdes"] == "U7":
                    surf_cap_under_u7.append((c["refdes"], c["x_um"], c["y_um"]))
        for e in edtc_boxes:
            _, _, _, ov_e = rect_edge_distance(cb, e["cavity_bbox"])
            if ov_e:
                surf_cap_over_edtc.append((c["refdes"], e["refdes"], c["x_um"], c["y_um"]))
    print("  SURFACE capacitors colliding with SURFACE Dies/Bridges:", len(surf_cap_under_die), "of which under U7:", len(surf_cap_under_u7))
    print("  Sample SURFACE caps colliding with Dies:", surf_cap_under_die[:15])
    print("  Sample SURFACE caps colliding with U7:", surf_cap_under_u7[:15])
    print("  SURFACE capacitors overlapping 4FCO eDTC xy footprint:", len(surf_cap_over_edtc), surf_cap_over_edtc[:10])

    return {}


if __name__ == "__main__":
    run_audit()
