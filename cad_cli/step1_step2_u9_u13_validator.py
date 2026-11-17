"""
Step 1 + Step 2 End-to-End Synthesizer, Zero-Via-Overlap Verifier, SVG Visual Gate Generator &
Headless `.mcm` Builder for BOTH `U9` (`LDA`: `VDDC0` + `VDD_0P8_SRAM_CC0` + `VSS`) AND
`U13` (`HBM MEM5`: 4-Rail + `VSS`).

Enforces:
  1. Complete `VSS` vertical via continuity across `9F -> 8F -> 7F -> 6F -> 5F` AND `9B -> 8B -> 7B -> 6B -> 5B`
     (plus `10B/11B`), as well as multi-rail `VDD*` middle-BU trunks (`8F->6F`, `10F->6F`, `6B->8B/10B/12B`).
  2. Strict **Zero Via Overlap (`0` Same-Span & `0` Staggered/Adjacent-Span Pad Overlap)** across all 27
     conductor layers (`SURFACE, C0, 12F..1FCI, 1BCI..BASE`), verified by `audit_via_continuity_and_zero_overlap`.
  3. Brand-new `.mcm` output from `PDN_test.mcm` (`PDN_test.mcm` is never modified).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .cadence_runner import CadenceBatchRunner
from .curved_recess_and_lsc_engine import (
    PlacedLscItem,
    synthesize_curved_bga_recess_and_pack_lscs,
)
from .hbm_surface_and_csb_router import (
    connect_u9_sram0_10f_backbone,
    route_u13_emib_csb_and_c0_pins,
    route_u13_hbm_surface_and_10f_csb,
    route_u9_emib_csb_and_c0_pins,
    route_u9_lda_surface_and_emib,
)
from .multi_rail_polygon_engine import (
    BBox,
    CavityRecord,
    ClineRecord,
    FastXYClearanceGrid,
    MultiRailLayerOwnershipIndex,
    PolygonIsland,
    U13_DOMAIN_BBOX,
    U13_EDTC_BODIES,
    U41_EMIB_BBOX,
    U9_DOMAIN_BBOX,
    U9_EDTC_BODIES,
    U9_EMIB_BRIDGES,
    U9_SRAM0_SUB_ISLANDS_12B,
    ViaRecord,
    audit_via_continuity_and_zero_overlap,
    build_u13_hbm_27layer_polygons,
    build_u9_lda_27layer_polygons,
    compute_real_edtc_profiles,
    route_bottom_bga_and_lsc_with_atomic_pruning,
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays,
    synthesize_concentric_edtc_stacks,
    synthesize_multi_rail_core_pth_and_pp,
)

ORDERED_STACK_SPANS: List[Tuple[str, str]] = [
    ("SURFACE", "C0"),
    ("SURFACE", "12F"),
    ("12F", "11F"),
    ("11F", "10F"),
    ("10F", "9F"),
    ("9F", "8F"),
    ("8F", "7F"),
    ("7F", "6F"),
    ("6F", "5F"),
    ("5F", "4FCO"),
    ("4FCO", "3FCI"),
    ("3FCI", "2FCI"),
    ("2FCI", "2BCI"),
    ("2BCI", "3BCI"),
    ("3BCI", "4BCO"),
    ("4BCO", "5B"),
    ("5B", "6B"),
    ("6B", "7B"),
    ("7B", "8B"),
    ("8B", "9B"),
    ("9B", "10B"),
    ("10B", "11B"),
    ("11B", "12B"),
    ("12B", "BASE"),
]


def _octagonal_8via_offsets(r_um: float = 195.0) -> List[Tuple[float, float]]:
    offs: List[Tuple[float, float]] = []
    for k in range(8):
        ang = math.radians(22.5 + 45.0 * k)
        offs.append((round(r_um * math.cos(ang), 2), round(r_um * math.sin(ang), 2)))
    return offs


def _hexagonal_6via_offsets(r_um: float = 165.0) -> List[Tuple[float, float]]:
    """6-via regular hexagon inside `550 um` BGA pad: adjacent pitch = `165.0 um` (`75.0 um` gap, `0` overlap!)."""
    offs: List[Tuple[float, float]] = []
    for k in range(6):
        ang = math.radians(60.0 * k)
        offs.append((round(r_um * math.cos(ang), 2), round(r_um * math.sin(ang), 2)))
    return offs


def _compute_cavities_from_lscs(
    lscs: Sequence[Dict[str, str]],
    bga_balls: Sequence[Dict[str, str]],
    target_nets: Sequence[str],
    prefix: str,
    ownership: MultiRailLayerOwnershipIndex | None = None,
    emib_boxes: Sequence[BBox] = (),
) -> Tuple[List[CavityRecord], List[PlacedLscItem], List[str]]:
    """
    Cluster placed LSCs by proximity (`<= 2100 um`), synthesize exact curved BGA-following
    mechanical recess contours (`R_mill = 508 um` Code K, `>= 254 um` BGA SRO->Cav Code G/H,
    `+178 um` Ext Cu KOZ Code D, `-225 um` LSC SRO safe zone Slide 11), and place/repair
    `CONDUCTOR/BASE` `180 deg` LSCs strictly inside the curved safe zone!
    """
    tset = set(target_nets)
    target_rows = [r for r in lscs if r["pin1_net"] in tset or r["pin2_net"] in tset]
    other_rows = [r for r in lscs if r["pin1_net"] not in tset and r["pin2_net"] not in tset]

    def _rail_resolver(cx: float, cy: float, rot: float) -> str | None:
        if ownership is None:
            return target_nets[0]
        tmp = PlacedLscItem("TMP", "SM0201_690X390X550_01A", cx, cy, rot, target_nets[0], "VSS", "P")
        (p1x, p1y), _ = tmp.pin_coords
        own12 = ownership.owner_at("12B", p1x, p1y, min_edge_margin_um=40.0)
        if own12 in tset:
            if "VDD_0P8_SRAM_CC0" in tset and any(
                sb[0] + 40.0 <= p1x <= sb[2] - 40.0 and sb[1] + 40.0 <= p1y <= sb[3] - 40.0
                for sb in U9_SRAM0_SUB_ISLANDS_12B
            ):
                if ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0) == "VDD_0P8_SRAM_CC0":
                    return "VDD_0P8_SRAM_CC0"
            if "VDDQ_0P85_HBM_MEM5" in tset and -37950.0 <= p1x <= -36200.0 and 25000.0 <= p1y <= 31500.0:
                if ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0) == "VDDQ_0P85_HBM_MEM5":
                    return "VDDQ_0P85_HBM_MEM5"
            return own12
        own10 = ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0)
        return own10 if own10 in tset else None

    visited = [False] * len(target_rows)
    cavs: List[CavityRecord] = []
    built_polys: List[List[Tuple[float, float]]] = []
    all_placed: List[PlacedLscItem] = []
    all_delete: List[str] = []
    p_idx = 1

    for i in range(len(target_rows)):
        if visited[i]:
            continue
        comp_rows = [target_rows[i]]
        visited[i] = True
        q = [target_rows[i]]
        while q:
            cur = q.pop()
            cx, cy = float(cur["x_um"]), float(cur["y_um"])
            for j in range(len(target_rows)):
                if not visited[j]:
                    jx, jy = float(target_rows[j]["x_um"]), float(target_rows[j]["y_um"])
                    if abs(jx - cx) <= 2100.0 and abs(jy - cy) <= 2100.0:
                        visited[j] = True
                        comp_rows.append(target_rows[j])
                        q.append(target_rows[j])

        # Find any shared-pocket neighbor LSCs of other rails (e.g. U13 Pocket B HBMPHY/UCIE)
        c_xs = [float(r["x_um"]) for r in comp_rows]
        c_ys = [float(r["y_um"]) for r in comp_rows]
        nb_box = (min(c_xs) - 2200.0, min(c_ys) - 2200.0, max(c_xs) + 2200.0, max(c_ys) + 2200.0)
        fixed_nbs = [
            r for r in other_rows
            if nb_box[0] <= float(r["x_um"]) <= nb_box[2] and nb_box[1] <= float(r["y_um"]) <= nb_box[3]
        ]
        seeds = [(float(r["x_um"]), float(r["y_um"])) for r in comp_rows]
        pk_id = f"{prefix}_CAV_{p_idx}"
        res_pk = synthesize_curved_bga_recess_and_pack_lscs(
            pocket_id=pk_id,
            seed_points=seeds,
            bga_balls=bga_balls,
            default_vdd_net=target_nets[0],
            rail_resolver_fn=_rail_resolver,
            existing_pocket_lscs=comp_rows,
            fixed_neighbor_lscs=fixed_nbs,
            emib_shadow_boxes=emib_boxes,
            other_cavity_polys=built_polys,
            refdes_prefix=f"CLSC_{prefix}_P{p_idx}",
            start_index=1,
        )
        cb = res_pk.bbox if res_pk.cavity_poly else (min(c_xs) - 300.0, min(c_ys) - 300.0, max(c_xs) + 300.0, max(c_ys) + 300.0)
        if res_pk.cavity_poly:
            built_polys.append(res_pk.cavity_poly)
        cavs.append(
            CavityRecord(
                pocket_id=pk_id,
                x1=round(cb[0], 2),
                y1=round(cb[1], 2),
                x2=round(cb[2], 2),
                y2=round(cb[3], 2),
                corner_r_um=508.0,
                ext_koz_um=178.0,
                lsc_safe_in_um=225.0,
                cavity_poly=res_pk.cavity_poly,
                outer_koz_poly=res_pk.outer_koz_poly,
                inner_safe_poly=res_pk.inner_safe_poly,
                is_non_rectangular=res_pk.is_non_rectangular,
            )
        )
        used_refs = {it.refdes for it in res_pk.placed_lscs}
        for old_r in res_pk.replaced_refdes:
            if old_r and old_r not in used_refs:
                all_delete.append(old_r)
        all_placed.extend(res_pk.placed_lscs)
        p_idx += 1

    return cavs, all_placed, all_delete


def _render_multirail_svg(
    svg_path: Path,
    title: str,
    domain_bbox: BBox,
    islands: Sequence[PolygonIsland],
    vias: Sequence[ViaRecord],
    cavities: Sequence[CavityRecord],
    net_colors: Dict[str, str],
) -> Path:
    """
    Render an XML-validated 6-panel CAD blueprint SVG (`SURFACE/10F`, **`9F->5F` VSS+VDD**, `6F/4FCO`,
    `2FCI Core`, **`9B->5B` VSS+VDD**, `12B/BASE`) + a **24-Span Vertical Continuity Bar Chart** (`VSS` vs `VDD`).
    """
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    W, H = 2100, 1480
    panels = [
        ("Panel A: Top Escape (SURFACE + 10F Guard Ring)",      ("10F", "SURFACE"), ("SURFACE", "12F"),  36,   85, 656, 480),
        ("Panel B: Frontside Mid-BU 9F -> 5F (VSS + VDD)",      ("8F", "7F"),       ("9F", "8F"),       722,   85, 656, 480),
        ("Panel C: Co-Planar Split & eDTC KOZ (4FCO / 6F)",     ("4FCO", "6F"),     ("5F", "4FCO"),    1408,   85, 656, 480),
        ("Panel D: Multi-Rail Core Partition & PTHs (2FCI)",    ("2FCI",),          ("2FCI", "2BCI"),    36,  590, 656, 480),
        ("Panel E: Backside Mid-BU 9B -> 5B (VSS + VDD)",       ("8B", "7B"),       ("6B", "7B"),       722,  590, 656, 480),
        ("Panel F: Backside GCP Split & LSC Cavities (12B)",    ("12B",),           ("12B", "BASE"),   1408,  590, 656, 480),
    ]
    dx_dom = max(1.0, domain_bbox[2] - domain_bbox[0])
    dy_dom = max(1.0, domain_bbox[3] - domain_bbox[1])

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="#0b1120"/>',
        f'<text x="36" y="46" fill="#f8fafc" font-family="Segoe UI, Arial" font-size="23" font-weight="bold">{html.escape(title)}</text>',
        '<text x="36" y="70" fill="#38bdf8" font-family="Segoe UI, Arial" font-size="14">Zero Via Pad Overlap Verified Across All 27 Conductor Layers | Complete VSS &amp; VDD Continuity on 9F-&gt;5F and 9B-&gt;5B</text>',
    ]

    for ptitle, lyrs, via_span_pair, px, py, pw, ph in panels:
        out.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" fill="#111827" stroke="#334155" stroke-width="1.5"/>')
        out.append(f'<text x="{px+14}" y="{py+26}" fill="#e2e8f0" font-family="Segoe UI, Arial" font-size="14" font-weight="bold">{html.escape(ptitle)}</text>')
        pad = 30.0
        scale = min((pw - 2 * pad) / dx_dom, (ph - 48.0 - pad) / dy_dom)
        ox = px + 0.5 * (pw - dx_dom * scale)
        oy = py + 40.0 + 0.5 * (ph - 40.0 - dy_dom * scale)

        def tx(x: float) -> float:
            return round(ox + (x - domain_bbox[0]) * scale, 2)

        def ty(y: float) -> float:
            return round(oy + (domain_bbox[3] - y) * scale, 2)

        for lyr in lyrs:
            for isl in islands:
                if isl.layer != lyr:
                    continue
                col = net_colors.get(isl.net_name, "#64748b")
                pts_s = " ".join(f"{tx(vx)},{ty(vy)}" for vx, vy in isl.vertices)
                op = "0.85" if lyr == "SURFACE" else ("0.18" if isl.net_name == "VSS" else "0.38")
                out.append(f'<polygon points="{pts_s}" fill="{col}" fill-opacity="{op}" stroke="{col}" stroke-width="1.1"/>')
                for vd in isl.voids:
                    vpts_s = " ".join(f"{tx(vx)},{ty(vy)}" for vx, vy in vd)
                    out.append(f'<polygon points="{vpts_s}" fill="#111827" stroke="#f59e0b" stroke-width="0.9" stroke-dasharray="3,2"/>')

        if "12B" in lyrs:
            for cv in cavities:
                if cv.cavity_poly:
                    if cv.outer_koz_poly:
                        k_pts = " ".join(f"{tx(vx)},{ty(vy)}" for vx, vy in cv.outer_koz_poly)
                        out.append(f'<polygon points="{k_pts}" fill="none" stroke="#f43f5e" stroke-width="1.3" stroke-dasharray="2,2"/>')
                    c_pts = " ".join(f"{tx(vx)},{ty(vy)}" for vx, vy in cv.cavity_poly)
                    out.append(f'<polygon points="{c_pts}" fill="none" stroke="#22d3ee" stroke-width="1.8" stroke-dasharray="5,3"/>')
                else:
                    kx, ky = tx(cv.x1 - cv.ext_koz_um), ty(cv.y2 + cv.ext_koz_um)
                    kw, kh = max(2.0, (cv.x2 - cv.x1 + 2 * cv.ext_koz_um) * scale), max(2.0, (cv.y2 - cv.y1 + 2 * cv.ext_koz_um) * scale)
                    kr = round((cv.corner_r_um + cv.ext_koz_um) * scale, 2)
                    out.append(f'<rect x="{kx}" y="{ky}" width="{kw:.2f}" height="{kh:.2f}" rx="{kr}" fill="none" stroke="#f43f5e" stroke-width="1.3" stroke-dasharray="2,2"/>')
                    rx, ry = tx(cv.x1), ty(cv.y2)
                    rw, rh = max(2.0, (cv.x2 - cv.x1) * scale), max(2.0, (cv.y2 - cv.y1) * scale)
                    rr = round(cv.corner_r_um * scale, 2)
                    out.append(f'<rect x="{rx}" y="{ry}" width="{rw:.2f}" height="{rh:.2f}" rx="{rr}" fill="none" stroke="#22d3ee" stroke-width="1.8" stroke-dasharray="5,3"/>')

        # Draw BOTH VSS and Power vias for the panel's target span (with explicit 9F->5F & 9B->5B visibility!)
        if via_span_pair == ("9F", "8F"):
            match_spans = {("9F", "8F"), ("8F", "7F"), ("7F", "6F"), ("6F", "5F")}
        elif via_span_pair == ("6B", "7B"):
            match_spans = {("5B", "6B"), ("6B", "7B"), ("7B", "8B"), ("8B", "9B")}
        else:
            match_spans = {via_span_pair}

        # Deduplicate (x, y, net) per panel so concentric 4-span columns draw once cleanly, balanced VSS + VDD
        seen_xy = set()
        vss_pts: List[Tuple[float, float]] = []
        pwr_pts: List[Tuple[float, float, str]] = []
        for v in vias:
            if (v.start_layer, v.end_layer) in match_spans:
                key_xy = (round(v.x, 1), round(v.y, 1), v.net_name)
                if key_xy in seen_xy:
                    continue
                seen_xy.add(key_xy)
                if v.net_name == "VSS":
                    vss_pts.append((v.x, v.y))
                else:
                    pwr_pts.append((v.x, v.y, v.net_name))

        step_v = max(1, len(vss_pts) // 1400)
        step_p = max(1, len(pwr_pts) // 1400)
        for vx, vy in vss_pts[::step_v]:
            out.append(f'<circle cx="{tx(vx)}" cy="{ty(vy)}" r="2.0" fill="#38bdf8"/>')
        for vx, vy, vnet in pwr_pts[::step_p]:
            col = net_colors.get(vnet, "#f87171")
            out.append(f'<circle cx="{tx(vx)}" cy="{ty(vy)}" r="2.0" fill="{col}"/>')

        out.append(
            f'<text x="{px+14}" y="{py+ph-12}" fill="#94a3b8" font-family="Consolas, monospace" font-size="12">'
            f'Unique columns: VSS={len(vss_pts)} | VDD={len(pwr_pts)}</text>'
        )

    # --- Bottom 24-Span Vertical Via Continuity Audit Chart (SURFACE -> BASE) ---
    bx0, by0, bw, bh = 36, 1095, 2028, 315
    out.append(f'<rect x="{bx0}" y="{by0}" width="{bw}" height="{bh}" rx="8" fill="#111827" stroke="#334155" stroke-width="1.5"/>')
    out.append(f'<text x="{bx0+16}" y="{by0+26}" fill="#f8fafc" font-family="Segoe UI, Arial" font-size="15" font-weight="bold">27-Layer Vertical Dielectric Span Continuity Audit (VSS Blue vs. Power Orange — Note Highlighted 9F-&gt;5F &amp; 9B-&gt;5B Zones)</text>')

    vss_by_sp: Dict[Tuple[str, str], int] = {}
    pwr_by_sp: Dict[Tuple[str, str], int] = {}
    for v in vias:
        sp = (v.start_layer, v.end_layer)
        if v.net_name == "VSS":
            vss_by_sp[sp] = vss_by_sp.get(sp, 0) + 1
        else:
            pwr_by_sp[sp] = pwr_by_sp.get(sp, 0) + 1

    col_w = (bw - 40.0) / len(ORDERED_STACK_SPANS)
    max_log = 4.5  # log10 scale up to 31,600 vias
    chart_base_y = by0 + bh - 58.0
    max_bar_h = 190.0

    mid_highlight = {("9F", "8F"), ("8F", "7F"), ("7F", "6F"), ("6F", "5F"), ("5B", "6B"), ("6B", "7B"), ("7B", "8B"), ("8B", "9B")}
    for i, sp in enumerate(ORDERED_STACK_SPANS):
        cx = bx0 + 24.0 + i * col_w
        vc = vss_by_sp.get(sp, 0)
        pc = pwr_by_sp.get(sp, 0)
        if sp in mid_highlight:
            out.append(f'<rect x="{cx-2:.1f}" y="{by0+38}" width="{col_w-4:.1f}" height="{bh-52}" rx="4" fill="#1e293b"/>')

        vh = 0.0 if vc == 0 else min(max_bar_h, (math.log10(vc + 1) / max_log) * max_bar_h)
        ph_bar = 0.0 if pc == 0 else min(max_bar_h, (math.log10(pc + 1) / max_log) * max_bar_h)

        out.append(f'<rect x="{cx+4:.1f}" y="{chart_base_y - vh:.1f}" width="{0.38*col_w:.1f}" height="{vh:.1f}" rx="2" fill="#38bdf8"/>')
        out.append(f'<rect x="{cx+4+0.42*col_w:.1f}" y="{chart_base_y - ph_bar:.1f}" width="{0.38*col_w:.1f}" height="{ph_bar:.1f}" rx="2" fill="#f97316"/>')
        out.append(f'<text x="{cx+3:.1f}" y="{chart_base_y - vh - 4:.1f}" fill="#7dd3fc" font-family="Consolas, monospace" font-size="9">{vc}</text>')
        out.append(f'<text x="{cx+3+0.42*col_w:.1f}" y="{chart_base_y - ph_bar - 14:.1f}" fill="#fdba74" font-family="Consolas, monospace" font-size="9">{pc}</text>')
        lbl = f"{sp[0]}-{sp[1]}".replace("SURFACE", "SURF")
        lbl_col = "#fde047" if sp in mid_highlight else "#cbd5e1"
        out.append(f'<text x="{cx+4:.1f}" y="{chart_base_y + 18:.1f}" fill="{lbl_col}" font-family="Consolas, monospace" font-size="10" font-weight="bold">{html.escape(lbl)}</text>')

    # Legend
    lx = 36
    for nname, col in net_colors.items():
        out.append(f'<rect x="{lx}" y="{H-38}" width="16" height="16" rx="3" fill="{col}"/>')
        out.append(f'<text x="{lx+22}" y="{H-25}" fill="#cbd5e1" font-family="Segoe UI, Arial" font-size="13">{html.escape(nname)}</text>')
        lx += 235

    out.append("</svg>")
    svg_txt = "\n".join(out)
    ET.fromstring(svg_txt.encode("utf-8"))
    svg_path.write_text(svg_txt, encoding="utf-8")
    return svg_path


def write_master_recipe(
    recipe_path: Path,
    polygons: Sequence[PolygonIsland],
    cavities: Sequence[CavityRecord],
    vias: Sequence[ViaRecord],
    clines: Sequence[ClineRecord],
    placed_lscs: Sequence[PlacedLscItem] = (),
    delete_lsc_refdes: Sequence[str] = (),
) -> Path:
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step 1 + Step 2 Multi-Rail Master Recipe (U9 VDDC0+SRAM0 & U13 HBM 4-Rail | Curved Recess & 180-deg LSC | 0 Via Overlap)",
        "# Generated by step1_step2_u9_u13_validator.py",
    ]
    for cv in cavities:
        if cv.cavity_poly:
            c_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.cavity_poly)
            k_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.outer_koz_poly)
            s_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.inner_safe_poly)
            lines.append(f"POLY_CAVITY|{cv.pocket_id}|{c_str}|{k_str}|{s_str}")
        else:
            lines.append(
                f"CAVITY|{cv.pocket_id}|{cv.x1:.3f}|{cv.y1:.3f}|{cv.x2:.3f}|{cv.y2:.3f}|"
                f"{cv.corner_r_um:.1f}|{cv.ext_koz_um:.1f}|{cv.lsc_safe_in_um:.1f}"
            )

    for del_ref in delete_lsc_refdes:
        lines.append(f"LSC_DELETE|{del_ref}")
    for cap in placed_lscs:
        lines.append(
            f"LSC_PLACE|{cap.refdes}|{cap.symbol_name}|{cap.x:.3f}|{cap.y:.3f}|"
            f"{cap.rot_deg:.1f}|{cap.pin1_net}|{cap.pin2_net}"
        )

    for poly in polygons:
        vstr = ";".join(f"{x:.3f},{y:.3f}" for x, y in poly.vertices)
        has_v = "YES" if poly.voids else "NO"
        mode_s = (
            "DYNAMIC"
            if (poly.is_dynamic and poly.net_name != "__ISOLATED__")
            else ("STATIC_GUARD" if poly.net_name == "__ISOLATED__" else "STATIC_NET")
        )
        lines.append(f"POLY_SHAPE|{poly.layer}|{poly.net_name}|{mode_s}|{has_v}|{vstr}")
        if poly.voids:
            for vd in poly.voids:
                vd_str = ";".join(f"{x:.3f},{y:.3f}" for x, y in vd)
                lines.append(f"POLY_VOID|{vd_str}")
            lines.append("POLY_CLOSE")

    for v in vias:
        lines.append(f"VIA|{v.net_name}|{v.padstack}|{v.start_layer}|{v.end_layer}|{v.x:.3f}|{v.y:.3f}|{v.tag}")

    for cl in clines:
        lines.append(f"CLINE|{cl.net_name}|{cl.layer}|{cl.width_um:.2f}|{cl.x1:.3f}|{cl.y1:.3f}|{cl.x2:.3f}|{cl.y2:.3f}|{cl.tag}")

    recipe_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return recipe_path


def synthesize_and_validate_step1_step2_u9_u13(
    base_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test.mcm",
    out_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test_Step1_Step2_U9_U13_DynPlanes_RealEDTC_RecessKOZ.mcm",
    vddc_vss_ratio: str = "3:1",
    dry_run: bool = False,
    timeout_sec: int = 1200,
) -> Dict[str, Any]:
    """
    Synthesize Step 1 + Step 2 across all 27 layers for BOTH `U9` and `U13` with:
      1. Exact per-family real `eDTC` die/cavity/KOZ sizes (`N24792-018` 144p, `N24792-017` 48p, `N24792-016` 24p)
      2. True Dynamic Power & `VSS` Plane Shapes (`axlShapeChangeDynamicType`) + Static Guard Band Metal (`10F`, `4FCO`, `4BCO`)
      3. LSC Recess KOZ drawn on `SUBSTRATE GEOMETRY/recess_cavity_pdn`
      4. Complete `VSS` & `VDD` `9F -> 5F` and `9B -> 5B` middle-BU continuity + `0` via pad overlap across all 27 layers
      5. Post-route 3D connectivity & open/short verification!
    """
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import resolve_output_dir, resolve_stage1_inputs_dir
    except ImportError:
        from pdn_paths import resolve_output_dir, resolve_stage1_inputs_dir  # type: ignore

    ws = Path(__file__).resolve().parent.parent.parent
    s1 = resolve_stage1_inputs_dir()
    out_dir = resolve_output_dir("agent04_pdn_architect/reports/step1_step2_u9_u13")
    svg_dir = resolve_output_dir("agent04_pdn_architect/pdn_sandbox")
    svg_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _read_csv_rows(p: Path) -> List[Dict[str, str]]:
        with p.open("r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    edtc_pins = _read_csv_rows(s1 / "edtc_pin_map.csv")
    edtc_syms = _read_csv_rows(s1 / "edtc_symbols.csv")
    bga_balls = _read_csv_rows(s1 / "bga_map.csv")
    lsc_caps  = _read_csv_rows(s1 / "lsc_placed_map.csv")
    u9_pins   = _read_csv_rows(s1 / "u9_full_pins.csv")
    u13_pins  = _read_csv_rows(s1 / "u13_u41_u5_full_pins.csv")

    u9_edtc_profs  = compute_real_edtc_profiles(edtc_pins, edtc_syms, list(U9_EDTC_BODIES.keys()))
    u13_edtc_profs = compute_real_edtc_profiles(edtc_pins, edtc_syms, list(U13_EDTC_BODIES.keys()))

    # Single unified per-conductor zero-overlap spatial grid shared across the entire package!
    global_grid = FastXYClearanceGrid(cell_um=250.0)

    # =========================================================================
    # A. Synthesize U9 (`VDDC0` + `VDD_0P8_SRAM_CC0` + `VSS`)
    # =========================================================================
    u9_polys = build_u9_lda_27layer_polygons(edtc_profiles=u9_edtc_profs)
    u9_own = MultiRailLayerOwnershipIndex(u9_polys)
    u9_vias: List[ViaRecord] = []
    u9_clines: List[ClineRecord] = []

    # Priority 1: Fixed eDTC 4FCO pins & EMIB C0 / 10F CSB pins
    u9_edtc_landed = synthesize_concentric_edtc_stacks(
        edtc_pins=edtc_pins,
        target_refdes=list(U9_EDTC_BODIES.keys()),
        allowed_nets=("VDDC0", "VDD_0P8_SRAM_CC0", "VSS"),
        ownership=u9_own,
        vias_out=u9_vias,
        grid=global_grid,
    )
    u9_emib_stats = route_u9_emib_csb_and_c0_pins(
        u9_pins=u9_pins,
        ownership=u9_own,
        vias_out=u9_vias,
        grid=global_grid,
    )

    # Priority 2: Core PTH + Prepreg Trunks (5F..5B VSS & 6F..6B VDD)
    u9_pth_counts = synthesize_multi_rail_core_pth_and_pp(
        domain_bbox=U9_DOMAIN_BBOX,
        power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
        ownership=u9_own,
        edtc_bodies=U9_EDTC_BODIES,
        emib_boxes=U9_EMIB_BRIDGES,
        vias_out=u9_vias,
        grid=global_grid,
        pth_pitch_x_um=520.0,
        pth_pitch_y_um=480.0,
        tag_prefix="U9",
        edtc_profiles=u9_edtc_profs,
    )

    # Priority 3: Curved BGA-Following Recesses + `180 deg` BASE LSC Placement + BGA/LSC Climbs (12B->BASE up to 11B/10B)
    u9_cavs, u9_placed_lscs, u9_del_lscs = _compute_cavities_from_lscs(
        lscs=lsc_caps,
        bga_balls=bga_balls,
        target_nets=("VDDC0", "VDD_0P8_SRAM_CC0"),
        prefix="U9",
        ownership=u9_own,
        emib_boxes=list(U9_EMIB_BRIDGES.values()),
    )
    oct8 = _octagonal_8via_offsets(195.0)
    u9_bot_stats = route_bottom_bga_and_lsc_with_atomic_pruning(
        bga_balls=bga_balls,
        lsc_caps=[it.to_cap_dict() for it in u9_placed_lscs],
        target_power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
        vss_bbox=(-15200.0, 16800.0, 15200.0, 33150.0),
        ownership=u9_own,
        bga_offsets_by_rail={"VDDC0": oct8, "VDD_0P8_SRAM_CC0": oct8, "VSS": [(-135.0, -135.0), (135.0, -135.0), (-135.0, 135.0), (135.0, 135.0)]},
        vias_out=u9_vias,
        grid=global_grid,
        tag_prefix="U9_BOT",
    )

    # Priority 4a: Fixed U9 SRAM0 Die SURFACE VIPs & 10F Backbone (1,007/1,007 bumps before mid-BU stitch grid!)
    u9_shared_bump_obs = FastXYClearanceGrid(cell_um=160.0)
    u9_sram_top = route_u9_lda_surface_and_emib(
        u9_pins=u9_pins,
        ownership=u9_own,
        vias_out=u9_vias,
        clines_out=u9_clines,
        grid=global_grid,
        vddc_vss_ratio=vddc_vss_ratio,
        emib_already_routed=True,
        only_nets=("VDD_0P8_SRAM_CC0",),
        shared_bump_obs=u9_shared_bump_obs,
    )

    # Priority 4b: Dedicated 9F -> 5F & 9B -> 5B Middle-Buildup Stitch Arrays (3,100+ VSS 9F->5F & 9B->5B cols, 0 Overlap!)
    u9_mid_bu_stats = synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(
        domain_bbox=U9_DOMAIN_BBOX,
        power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
        ownership=u9_own,
        vias_out=u9_vias,
        grid=global_grid,
        pitch_um=285.0,
        tag_prefix="U9_MID",
    )

    # Priority 5: U9 VDDC0 & VSS SURFACE C4 Bump Drops & Horizontal/Collar Strapping (sharing bump_obs with SRAM0 = 0 shorts!)
    u9_top_stats = route_u9_lda_surface_and_emib(
        u9_pins=u9_pins,
        ownership=u9_own,
        vias_out=u9_vias,
        clines_out=u9_clines,
        grid=global_grid,
        vddc_vss_ratio=vddc_vss_ratio,
        emib_already_routed=True,
        only_nets=("VDDC0", "VSS"),
        shared_bump_obs=u9_shared_bump_obs,
    )
    # Priority 6: Build U9 SRAM0 10F cline backbone AFTER all U9 VDDC0/VSS/MID 10F vias exist (0 10F shorts!)
    connect_u9_sram0_10f_backbone(u9_own, u9_vias, u9_clines, global_grid)

    u9_top_stats["sram0_vip_columns"] = u9_sram_top["sram0_vip_columns"]
    u9_top_stats["surface_horizontal_straps"] += u9_sram_top["surface_horizontal_straps"]
    u9_top_stats["upper_bu_vias_total"] += u9_sram_top["upper_bu_vias_total"]
    u9_top_stats["emib_c0_vias"] = u9_emib_stats["emib_c0_vias"]
    u9_top_stats["emib_csb_vss_1stack"] = u9_emib_stats["emib_csb_vss_1stack"]

    # =========================================================================
    # B. Synthesize U13 (`MEM5`: `VDDQ` + `VDDC` + `VDDQL5` + `VPP` + `VSS`)
    # =========================================================================
    u13_polys = build_u13_hbm_27layer_polygons(edtc_profiles=u13_edtc_profs)
    u13_own_box = [MultiRailLayerOwnershipIndex(u13_polys)]
    u13_vias: List[ViaRecord] = []
    u13_clines: List[ClineRecord] = []
    u13_gang_polys: List[PolygonIsland] = []
    hbm_pwr = ("VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5", "VPP_1P8_HBM_MEM5")

    # Priority 1: Fixed eDTC 4FCO pins & U41 EMIB C0 / 100% 10F->9F CSB pins
    u13_edtc_landed = synthesize_concentric_edtc_stacks(
        edtc_pins=edtc_pins,
        target_refdes=list(U13_EDTC_BODIES.keys()),
        allowed_nets=list(hbm_pwr) + ["VSS"],
        ownership=u13_own_box[0],
        vias_out=u13_vias,
        grid=global_grid,
    )
    u13_emib_stats = route_u13_emib_csb_and_c0_pins(
        u13_u41_u5_pins=u13_pins,
        u13_polys=u13_polys,
        ownership_ref=u13_own_box,
        vias_out=u13_vias,
        clines_out=u13_clines,
        grid=global_grid,
    )
    u13_own = u13_own_box[0]

    # Priority 2: Core PTH + Prepreg Trunks (5F..5B VSS & 6F..6B VDD)
    u13_pth_counts = synthesize_multi_rail_core_pth_and_pp(
        domain_bbox=U13_DOMAIN_BBOX,
        power_rails=hbm_pwr,
        ownership=u13_own,
        edtc_bodies=U13_EDTC_BODIES,
        emib_boxes={"U41": U41_EMIB_BBOX},
        vias_out=u13_vias,
        grid=global_grid,
        pth_pitch_x_um=460.0,
        pth_pitch_y_um=430.0,
        tag_prefix="U13",
        edtc_profiles=u13_edtc_profs,
    )

    # Priority 3: Curved BGA-Following Recesses + `180 deg` BASE LSC Placement + BGA/LSC Climbs
    u13_cavs, u13_placed_lscs, u13_del_lscs = _compute_cavities_from_lscs(
        lscs=lsc_caps,
        bga_balls=bga_balls,
        target_nets=hbm_pwr,
        prefix="U13",
        ownership=u13_own,
        emib_boxes=[U41_EMIB_BBOX],
    )
    vddq_6offs = _hexagonal_6via_offsets(165.0)
    card_4offs = [(-200.0, 0.0), (200.0, 0.0), (0.0, -200.0), (0.0, 200.0)]
    u13_bot_stats = route_bottom_bga_and_lsc_with_atomic_pruning(
        bga_balls=bga_balls,
        lsc_caps=[it.to_cap_dict() for it in u13_placed_lscs],
        target_power_rails=hbm_pwr,
        vss_bbox=(-45800.0, 22400.0, -29500.0, 34650.0),
        ownership=u13_own,
        bga_offsets_by_rail={
            "VDDQ_0P85_HBM_MEM5": vddq_6offs,
            "VDDC_1P0_HBM_MEM5": card_4offs,
            "VDDQL5": card_4offs,
            "VPP_1P8_HBM_MEM5": card_4offs,
            "VSS": card_4offs,
        },
        vias_out=u13_vias,
        grid=global_grid,
        tag_prefix="U13_BOT",
    )

    # Priority 4: West & North U13 Fine-Pitch HBM4E SURFACE Gang-Bars & Drop Columns (before background grid stitches!)
    u13_top_stats = route_u13_hbm_surface_and_10f_csb(
        u13_u41_u5_pins=u13_pins,
        ownership=u13_own,
        surface_gang_islands_out=u13_gang_polys,
        vias_out=u13_vias,
        clines_out=u13_clines,
        grid=global_grid,
        u13_polys=u13_polys,
        emib_already_routed=True,
    )

    # Priority 5: Dedicated 9F -> 5F & 9B -> 5B Middle-Buildup Stitch Arrays (VSS + VDD, 0 Overlap!)
    u13_mid_bu_stats = synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(
        domain_bbox=U13_DOMAIN_BBOX,
        power_rails=hbm_pwr,
        ownership=u13_own,
        vias_out=u13_vias,
        grid=global_grid,
        pitch_um=235.0,
        tag_prefix="U13_MID",
    )
    u13_top_stats.update(u13_emib_stats)
    u13_top_stats["interplane_stitch_vias"] = u13_mid_bu_stats["total_mid_bu_vias"]

    # =========================================================================
    # C. Independent Zero-Via-Overlap & 9F->5F / 9B->5B Continuity Audit Gate!
    # =========================================================================
    all_polys  = list(u9_polys) + list(u13_polys) + list(u13_gang_polys)
    all_cavs   = list(u9_cavs) + list(u13_cavs)
    all_vias   = list(u9_vias) + list(u13_vias)
    all_clines = list(u9_clines) + list(u13_clines)
    all_placed_lscs = list(u9_placed_lscs) + list(u13_placed_lscs)
    all_del_lscs    = list(u9_del_lscs) + list(u13_del_lscs)

    u9_audit  = audit_via_continuity_and_zero_overlap(u9_vias)
    u13_audit = audit_via_continuity_and_zero_overlap(u13_vias)
    pkg_audit = audit_via_continuity_and_zero_overlap(all_vias)

    if not pkg_audit["zero_via_overlap_pass"]:
        raise RuntimeError(f"ZERO-VIA-OVERLAP GATE FAILED: {pkg_audit['overlap_samples']}")

    mandatory_vss_mid_spans = ["9F:8F", "8F:7F", "7F:6F", "6F:5F", "5B:6B", "6B:7B", "7B:8B", "8B:9B"]
    for dom_lbl, dom_aud in (("U9", u9_audit), ("U13", u13_audit)):
        vmap = dom_aud["vss_span_counts"]
        assert isinstance(vmap, dict)
        missing_sp = [sp for sp in mandatory_vss_mid_spans if vmap.get(sp, 0) == 0]
        if missing_sp:
            raise RuntimeError(f"{dom_lbl} MISSING MANDATORY VSS MID-BU SPANS: {missing_sp}")

    # =========================================================================
    # D. Render XML-Validated SVG Visual Gates
    # =========================================================================
    u9_svg = _render_multirail_svg(
        svg_path=svg_dir / "mockup_Step1_Step2_U9_MultiRail.svg",
        title="Step 1 + Step 2 Validation: U9 (LDA) Multi-Rail 27-Layer PDN (VDDC0 + SRAM0 + VSS | 9F->5F & 9B->5B)",
        domain_bbox=U9_DOMAIN_BBOX,
        islands=u9_polys,
        vias=u9_vias,
        cavities=u9_cavs,
        net_colors={"VDDC0": "#ef4444", "VDD_0P8_SRAM_CC0": "#f59e0b", "VSS": "#38bdf8", "__ISOLATED__": "#10b981"},
    )
    u13_svg = _render_multirail_svg(
        svg_path=svg_dir / "mockup_Step1_Step2_U13_HBM_4Rail.svg",
        title="Step 1 + Step 2 Validation: U13 (HBM MEM5) 4-Rail 27-Layer PDN + U41 CSB + 9F->5F & 9B->5B VSS",
        domain_bbox=U13_DOMAIN_BBOX,
        islands=list(u13_polys) + list(u13_gang_polys),
        vias=u13_vias,
        cavities=u13_cavs,
        net_colors={
            "VDDC_1P0_HBM_MEM5": "#ef4444",
            "VDDQ_0P85_HBM_MEM5": "#a855f7",
            "VDDQL5": "#eab308",
            "VPP_1P8_HBM_MEM5": "#ec4899",
            "VSS": "#38bdf8",
            "__ISOLATED__": "#10b981",
        },
    )

    # =========================================================================
    # E. Write Combined Master Recipe & Run Headless Cadence APD Batch Import
    # =========================================================================
    recipe_file = write_master_recipe(
        recipe_path=out_dir / "step1_step2_U9_U13_master_recipe.txt",
        polygons=all_polys,
        cavities=all_cavs,
        vias=all_vias,
        clines=all_clines,
        placed_lscs=all_placed_lscs,
        delete_lsc_refdes=all_del_lscs,
    )

    il_script = ws / "agent04_pdn_architect" / "scripts" / "multi_rail_step1_step2_implementer_batch.il"
    report_file = out_dir / "step1_step2_u9_u13_apd_report.txt"
    scr_file = out_dir / "run_step1_step2_u9_u13.scr"

    il_s = str(il_script).replace("\\", "/")
    rec_s = str(recipe_file).replace("\\", "/")
    rep_s = str(report_file).replace("\\", "/")

    summary: Dict[str, Any] = {
        "status": "DRY_RUN_READY" if dry_run else "PENDING",
        "recipe_file": str(recipe_file),
        "u9_svg": str(u9_svg),
        "u13_svg": str(u13_svg),
        "zero_via_overlap_audit": {
            "zero_via_overlap_pass": pkg_audit["zero_via_overlap_pass"],
            "duplicate_same_span_count": pkg_audit["duplicate_same_span_count"],
            "non_concentric_pad_overlap_count": pkg_audit["non_concentric_pad_overlap_count"],
            "concentric_diff_net_short_count": pkg_audit["concentric_diff_net_short_count"],
        },
        "totals": {
            "polygon_shapes": len(all_polys),
            "cavities": len(all_cavs),
            "vias": len(all_vias),
            "clines": len(all_clines),
        },
        "u9_metrics": {
            "polygon_shapes": len(u9_polys),
            "edtc_pins_landed": u9_edtc_landed,
            "core_pth_columns": u9_pth_counts,
            "mid_bu_9f_5f_and_9b_5b": u9_mid_bu_stats,
            "top_escape": u9_top_stats,
            "bottom_escape": u9_bot_stats,
            "cavities": len(u9_cavs),
            "vss_span_counts": u9_audit["vss_span_counts"],
            "pwr_span_counts": u9_audit["pwr_span_counts"],
        },
        "u13_metrics": {
            "polygon_shapes": len(u13_polys),
            "surface_gang_bars": len(u13_gang_polys),
            "edtc_pins_landed": u13_edtc_landed,
            "core_pth_columns": u13_pth_counts,
            "mid_bu_9f_5f_and_9b_5b": u13_mid_bu_stats,
            "top_and_csb_escape": u13_top_stats,
            "bottom_escape": u13_bot_stats,
            "cavities": len(u13_cavs),
            "vss_span_counts": u13_audit["vss_span_counts"],
            "pwr_span_counts": u13_audit["pwr_span_counts"],
        },
    }

    if dry_run:
        dry_scr = out_dir / "run_step1_step2_u9_u13_dry.scr"
        dry_scr.write_text(
            f'skill load("{il_s}")\nskill pdnImplementMultiRailStep1Step2Batch("{rec_s}" nil "" "{rep_s}")\nexit\nfillin no\n',
            encoding="utf-8",
        )
        (out_dir / "step1_step2_u9_u13_dry_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    base_abs = (ws / base_mcm_path).resolve()
    out_abs = (ws / out_mcm_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_abs, out_abs)
    lck = out_abs.with_name(out_abs.name + ".lck")
    if lck.exists():
        lck.unlink()

    scr_file.write_text(
        f'skill load("{il_s}")\nskill pdnImplementMultiRailStep1Step2Batch("{rec_s}" t "" "{rep_s}")\nexit\nfillin no\n',
        encoding="utf-8",
    )

    runner = CadenceBatchRunner(default_timeout=timeout_sec)
    run_res = None
    for _attempt in range(2):
        if report_file.exists():
            report_file.unlink()
        run_res = runner.run(mcm_path=out_abs, scr_path=scr_file, working_dir=out_dir, timeout=timeout_sec, bypass_lock_readonly=False)
        if report_file.exists():
            break

    kv: Dict[str, str] = {}
    if report_file.exists():
        for ln in report_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                kv[k.strip()] = v.strip()

    summary["status"] = kv.get("STATUS", "ERROR")
    summary["out_mcm_path"] = str(out_abs)
    summary["duration_sec"] = run_res.duration_sec if run_res else 0.0
    summary["apd_report"] = kv
    (out_dir / "step1_step2_u9_u13_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Step 1 + Step 2 on U9 and U13 into a new .mcm")
    parser.add_argument("--base-mcm", type=str, default="agent04_pdn_architect/MCM_test/PDN_test.mcm")
    parser.add_argument("--out-mcm", type=str, default="agent04_pdn_architect/MCM_test/PDN_test_Step1_Step2_U9_U13_DynPlanes_RealEDTC_RecessKOZ.mcm")
    parser.add_argument("--ratio", type=str, default="3:1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    res = synthesize_and_validate_step1_step2_u9_u13(
        base_mcm_path=args.base_mcm,
        out_mcm_path=args.out_mcm,
        vddc_vss_ratio=args.ratio,
        dry_run=args.dry_run,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
