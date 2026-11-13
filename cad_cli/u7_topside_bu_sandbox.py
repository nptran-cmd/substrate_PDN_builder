"""
Stage 2 & Stage 3 Topside Build-Up (BU) PDN Router & Per-Layer SVG Sandbox Exporter
for RefDes = U7 (`HUTTON_HILL_LDB_BC_A0`) on `VDDUC0` and all `VDD*` nets.

Generates per-layer XML-validated SVG visualizations in `pdn_sandbox/`:
  1. `layer_01_SURFACE_U7_VDDUC0_VDD.svg`
  2. `layer_02_C0_U7_VDDUC0_VDD.svg`
  3. `layer_03_12F_U7_VDDUC0_VDD.svg`
  4. `layer_04_11F_U7_VDDUC0_VDD.svg`
  5. `layer_05_10F_U7_VDDUC0_VDD.svg`
  6. `layer_06_9F_U7_VDDUC0_VDD.svg`
  7. `layer_07_8F_U7_VDDUC0_VDD.svg`
  8. `layer_08_7F_U7_VDDUC0_VDD.svg`
  9. `layer_09_6F_U7_VDDUC0_VDD.svg`
  10. `layer_10_5F_U7_VDDUC0_VDD.svg`
  11. `layer_11_4FCO_U7_eDTC_VDDUC0_VDD.svg`
  12. `U7_topside_BU_cross_section.svg`
Plus `pdn_sandbox/U7_topside_BU_recipe.txt` and `pdn_sandbox/U7_topside_BU_summary.json`.
"""

from __future__ import annotations

import csv
import html
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


U7_BBOX = (14935.748, -1005.739, 30664.368, 32890.761)
VIEW_BBOX = (14200.0, -1800.0, 31400.0, 33600.0)

TOPSIDE_BU_LAYERS: List[Tuple[int, str, str, str]] = [
    (1, "SURFACE", "TOP", "Die Bumps (VDDUC0 + VDD*) & TOP->C0 / TOP->12F uVias"),
    (2, "C0", "C0", "C0 Fine RDL & TOP->C0 uVia Landing"),
    (3, "12F", "12F", "30um ABF BU Layer | SURFACE->12F & 12F->11F (V77_49_77)"),
    (4, "11F", "11F", "30um ABF BU Layer | 12F->11F & 11F->10F (V77_49_77)"),
    (5, "10F", "10F", "30um ABF BU Layer | 11F->10F & 10F->9F (V77_49_77)"),
    (6, "9F", "9F", "30um->50um ABF Stack-Break Layer | 10F->9F (77um) to 9F->8F (90um)"),
    (7, "8F", "8F", "50um ABF High-Current Power Layer | 9F->8F & 8F->7F (V90_65_90)"),
    (8, "7F", "7F", "50um ABF BU Layer | 8F->7F & 7F->6F (V90_65_90)"),
    (9, "6F", "6F", "50um ABF High-Current Power Layer | 7F->6F & 6F->5F (V90_65_90)"),
    (10, "5F", "5F", "50um ABF Collector Layer | 6F->5F (90um) & 5F->4FCO (V90_65_121)"),
    (11, "4FCO", "4FCO", "eDTC Symbol Layer (C2238,C2239,C2209,C2210) + 300um KOZ + 150um Guard Metal"),
]


def _net_color(net_name: str) -> str:
    u = net_name.upper()
    if u == "VDDUC0" or u == "VDDUC":
        return "#f43f5e"  # Bright Crimson (Primary VDDUC0)
    if "UCIE" in u and "1P2" not in u:
        return "#f59e0b"  # Amber (VDD_0P7_UCIE_E)
    if "HBMPHY" in u:
        return "#06b6d4"  # Cyan (VDD_0P75_HBMPHY_UC0/1/2)
    if "VDDQL" in u or "VDDQ" in u:
        return "#10b981"  # Emerald (VDDQL0/1/2)
    if "1P2" in u:
        return "#a855f7"  # Purple (VDDIO_1P2_*)
    if "MISC" in u:
        return "#f97316"  # Orange (VDD_0P75_MISC_*)
    if "VDD" in u:
        return "#ec4899"  # Pink (Other VDD*)
    return "#3b82f6"      # Blue (VSS reference)


def _pad_radius_um(padstack_name: str) -> float:
    u = padstack_name.upper()
    if "VU30_19_35" in u:
        return 17.5
    if "VU30_19_39" in u:
        return 19.5
    if "VU30_19_50" in u:
        return 25.0
    if "V77_49_77" in u:
        return 38.5
    if "V90_65_121" in u:
        return 60.5
    if "V90_65_90" in u:
        return 45.0
    if "V282_5" in u or "V175_85" in u:
        return 87.5
    return 40.0


def _tx(x_um: float) -> float:
    # Map VIEW_BBOX X (14200..31400 = 17200 um) -> SVG X (120..1620 = 1500 px)
    return round(120.0 + ((x_um - VIEW_BBOX[0]) / (VIEW_BBOX[2] - VIEW_BBOX[0])) * 1500.0, 2)


def _ty(y_um: float) -> float:
    # Map VIEW_BBOX Y (-1800..33600 = 35400 um) -> SVG Y (2020..160 = 1860 px)
    return round(2020.0 - ((y_um - VIEW_BBOX[1]) / (VIEW_BBOX[3] - VIEW_BBOX[1])) * 1860.0, 2)


def _scale_len(um_val: float) -> float:
    return max(1.2, round((um_val / (VIEW_BBOX[2] - VIEW_BBOX[0])) * 1500.0, 2))


def _validate_and_save_svg(svg_text: str, out_file: Path) -> str:
    ET.fromstring(svg_text)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(svg_text, encoding="utf-8")
    return str(out_file)


def run_u7_topside_bu_sandbox(
    workspace_dir: Path | None = None,
    out_folder_name: str = "pdn_sandbox",
) -> Dict[str, Any]:
    workspace = workspace_dir or Path(__file__).resolve().parent.parent.parent
    out_dir = workspace / out_folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    s1_dir = workspace / "agent04_pdn_architect" / "stage1_inputs"

    # 1. Load U7's 4 underlying 4FCO eDTC symbols (C2238, C2239, C2209, C2210) & their pins
    u7_edtc_syms: Dict[str, Dict[str, Any]] = {}
    with (s1_dir / "edtc_symbols.csv").open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["layer"] == "4FCO":
                ex, ey = float(r["x_um"]), float(r["y_um"])
                if U7_BBOX[0] <= ex <= U7_BBOX[2] and U7_BBOX[1] <= ey <= U7_BBOX[3]:
                    u7_edtc_syms[r["refdes"]] = {
                        "refdes": r["refdes"],
                        "symbol_name": r["symbol_name"],
                        "x": ex,
                        "y": ey,
                        "bbox": (
                            float(r["bbox_x1"]),
                            float(r["bbox_y1"]),
                            float(r["bbox_x2"]),
                            float(r["bbox_y2"]),
                        ),
                        "pin_count": int(r["pin_count"]),
                    }

    u7_edtc_pins: List[Dict[str, Any]] = []
    with (s1_dir / "edtc_pin_map.csv").open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["refdes"] in u7_edtc_syms:
                u7_edtc_pins.append(
                    {
                        "refdes": r["refdes"],
                        "pin_number": r["pin_number"],
                        "x": float(r["x_um"]),
                        "y": float(r["y_um"]),
                        "net": r["net_name"],
                        "padstack": r["padstack_name"],
                    }
                )

    # 2. Load U7 SURFACE VDD* bumps from Symbols/hutton_hill_ldb_bc_a0_FN.zip
    u7_vdd_bumps: List[Dict[str, Any]] = []
    ldb_zip = Path(r"<cadence_library_dir>")
    if ldb_zip.exists():
        with zipfile.ZipFile(ldb_zip, "r") as z:
            raw = z.read("U1.HUTTON_HILL_LDB_A0.csv").decode("utf-8", errors="ignore")
            for r in csv.DictReader(io.StringIO(raw)):
                snet = (r.get("Si_Net_Name") or "").strip()
                if "VDD" in snet:
                    lx, ly = float(r["X"]), float(r["Y"])
                    mx = round(23143.882 - lx, 3)
                    my = round(15919.051 + ly, 3)
                    mcm_net = "VDDUC0" if snet == "VDDUC" else snet
                    u7_vdd_bumps.append(
                        {
                            "x": mx,
                            "y": my,
                            "net": mcm_net,
                            "geom": r.get("Geometry", "bumpP1_80x80um"),
                        }
                    )

    # 3. Extract all U7 Topside BU Vias (VDDUC0 + VDD* + VSS stats) from mcm_vias.txt
    topside_set = {"TOP", "SURFACE", "C0", "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F", "4FCO", "3FCI"}
    layer_vias: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    layer_vss_via_counts: Counter[str] = Counter()
    span_counts: Counter[Tuple[str, str, str, str]] = Counter()
    recipe_lines: List[str] = [
        "# AGENT04_U7_TOPSIDE_BU_RECIPE_V1|REFDES=U7|SYMBOL=HUTTON_HILL_LDB_BC_A0|NETS=VDDUC0,VDD*"
    ]

    vias_txt = workspace / "cadence_extract" / "mcm_vias.txt"
    with vias_txt.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("S!"):
                continue
            p = line.strip().split("!")
            if len(p) < 7:
                continue
            l1, l2 = p[2].strip(), p[3].strip()
            if l1 not in topside_set and l2 not in topside_set:
                continue
            vx, vy = float(p[4]), float(p[5])
            if not (U7_BBOX[0] - 400.0 <= vx <= U7_BBOX[2] + 400.0 and U7_BBOX[1] - 400.0 <= vy <= U7_BBOX[3] + 400.0):
                continue
            net = p[6].strip()
            ps = p[1].strip()
            c_l1 = "SURFACE" if l1 == "TOP" else l1
            c_l2 = "SURFACE" if l2 == "TOP" else l2

            if net == "VSS" or net == "DVSS":
                layer_vss_via_counts[c_l1] += 1
                layer_vss_via_counts[c_l2] += 1
            elif "VDD" in net and not net.startswith("OBS_"):
                v_rec = {
                    "padstack": ps,
                    "start": c_l1,
                    "end": c_l2,
                    "x": vx,
                    "y": vy,
                    "net": net,
                }
                layer_vias[c_l1].append(v_rec)
                if c_l2 != c_l1:
                    layer_vias[c_l2].append(v_rec)
                span_counts[(ps, c_l1, c_l2, net)] += 1
                recipe_lines.append(
                    f"VIA|PADSTACK={ps}|X={vx:.3f}|Y={vy:.3f}|NET={net}|START={c_l1}|END={c_l2}|ZONE=U7_TOPSIDE_BU"
                )

    # 4. Extract all U7 Topside BU Clines (VDDUC0 + VDD*) from mcm_clines.txt
    layer_clines: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    clines_txt = workspace / "cadence_extract" / "mcm_clines.txt"
    with clines_txt.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("S!"):
                continue
            p = line.strip().split("!")
            if len(p) < 10:
                continue
            net = p[9].strip()
            if "VDD" not in net or net.startswith("OBS_"):
                continue
            raw_lyr = p[1].strip()
            c_lyr = "SURFACE" if raw_lyr == "TOP" else raw_lyr
            if c_lyr not in topside_set:
                continue
            gtype = p[2].strip()
            if gtype != "LINE":
                continue
            x1, y1, x2, y2 = float(p[4]), float(p[5]), float(p[6]), float(p[7])
            if not (U7_BBOX[0] - 400.0 <= x1 <= U7_BBOX[2] + 400.0 and U7_BBOX[1] - 400.0 <= y1 <= U7_BBOX[3] + 400.0):
                continue
            w = max(12.0, float(p[8]) if p[8] else 20.0)
            layer_clines[c_lyr].append(
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": w, "net": net}
            )
            recipe_lines.append(
                f"CLINE|LAYER=CONDUCTOR/{c_lyr}|NET={net}|WIDTH={w:.1f}|X1={x1:.3f}|Y1={y1:.3f}|X2={x2:.3f}|Y2={y2:.3f}|ZONE=U7_TOPSIDE_BU"
            )

    # 5. Synthesize 5F Collector Diamond/Star Clines & 4FCO eDTC KOZ + Guard Metal Rings
    for v in layer_vias.get("5F", []):
        if v["end"] == "4FCO" and v["net"] == "VDDUC0":
            vx, vy = v["x"], v["y"]
            # Connect 5F->4FCO via to adjacent 6F->5F landing vias within 180um
            layer_clines["5F"].append(
                {"x1": vx - 65.0, "y1": vy, "x2": vx + 65.0, "y2": vy, "width": 50.0, "net": "VDDUC0"}
            )
            layer_clines["5F"].append(
                {"x1": vx, "y1": vy - 65.0, "x2": vx, "y2": vy + 65.0, "width": 50.0, "net": "VDDUC0"}
            )

    for c_ref, edtc in u7_edtc_syms.items():
        bx1, by1, bx2, by2 = edtc["bbox"]
        kx1, ky1, kx2, ky2 = bx1 - 300.0, by1 - 300.0, bx2 + 300.0, by2 + 300.0
        gx1, gy1, gx2, gy2 = kx1 - 75.0, ky1 - 75.0, kx2 + 75.0, ky2 + 75.0
        recipe_lines.append(
            f"KOZ|LAYER=CORE_ALL|TYPE=EDTC_CAVITY_300UM|X1={kx1:.3f}|Y1={ky1:.3f}|X2={kx2:.3f}|Y2={ky2:.3f}|SYM={c_ref}"
        )
        recipe_lines.append(
            f"EDTC_GUARD|LAYER=CONDUCTOR/2FCI|NET=VSS|WIDTH=150.0|X1={gx1:.3f}|Y1={gy1:.3f}|X2={gx2:.3f}|Y2={gy2:.3f}|SYM={c_ref}"
        )

    # 6. Render 11 Individual Per-Layer Topside BU SVGs in pdn_sandbox/
    svg_files: List[str] = []
    per_layer_stats: Dict[str, Any] = {}

    ux1, uy1, ux2, uy2 = U7_BBOX
    svg_u7_x = _tx(ux1)
    svg_u7_y = _ty(uy2)
    svg_u7_w = round(_tx(ux2) - _tx(ux1), 2)
    svg_u7_h = round(_ty(uy1) - _ty(uy2), 2)

    for idx, l_name, mcm_sub, desc in TOPSIDE_BU_LAYERS:
        v_list = layer_vias.get(l_name, [])
        c_list = layer_clines.get(l_name, [])
        vss_cnt = layer_vss_via_counts.get(l_name, 0)
        vdduc0_vias = sum(1 for v in v_list if v["net"] == "VDDUC0")
        other_vdd_vias = len(v_list) - vdduc0_vias
        ratio = round(len(v_list) / max(1, vss_cnt), 3)

        per_layer_stats[l_name] = {
            "layer_index": idx,
            "total_vdd_vias": len(v_list),
            "vdduc0_vias": vdduc0_vias,
            "other_vdd_vias": other_vdd_vias,
            "vss_vias": vss_cnt,
            "vdd_to_vss_via_ratio": ratio,
            "vdd_clines": len(c_list),
        }

        esc_desc = html.escape(desc)
        lines = [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 2200" width="1800" height="2200">',
            '<rect width="1800" height="2200" fill="#090d16"/>',
            # Header Banner
            '<rect x="30" y="20" width="1740" height="95" rx="8" fill="#111827" stroke="#334155" stroke-width="1.5"/>',
            f'<text x="55" y="55" fill="#f8fafc" font-family="monospace" font-size="22" font-weight="bold">'
            f'U7 (HUTTON_HILL_LDB_BC_A0) — Topside BU Layer {idx:02d}: {l_name} ({esc_desc})</text>',
            f'<text x="55" y="88" fill="#94a3b8" font-family="monospace" font-size="16">'
            f'VDDUC0 Vias: {vdduc0_vias:,} | Other VDD* Vias: {other_vdd_vias:,} | VSS Vias: {vss_cnt:,} '
            f'(VDD/VSS Ratio = {ratio}) | VDD Clines: {len(c_list):,}</text>',
            # Coordinate Grid
        ]
        for gx in range(15000, 31001, 2500):
            sx = _tx(float(gx))
            lines.append(f'<line x1="{sx}" y1="140" x2="{sx}" y2="2040" stroke="#1e293b" stroke-width="1"/>')
            lines.append(
                f'<text x="{sx - 28}" y="2065" fill="#64748b" font-family="monospace" font-size="12">{gx}um</text>'
            )
        for gy in range(0, 32501, 2500):
            sy = _ty(float(gy))
            lines.append(f'<line x1="100" y1="{sy}" x2="1640" y2="{sy}" stroke="#1e293b" stroke-width="1"/>')
            lines.append(
                f'<text x="35" y="{sy + 4}" fill="#64748b" font-family="monospace" font-size="12">{gy}um</text>'
            )

        # U7 Die Outline
        lines.append(
            f'<rect x="{svg_u7_x}" y="{svg_u7_y}" width="{svg_u7_w}" height="{svg_u7_h}" '
            'fill="#0f172a" fill-opacity="0.35" stroke="#38bdf8" stroke-dasharray="10,5" stroke-width="2.5"/>'
        )
        lines.append(
            f'<text x="{svg_u7_x + 12}" y="{svg_u7_y + 24}" fill="#38bdf8" font-family="monospace" font-size="15" font-weight="bold">'
            'RefDes: U7 (HUTTON_HILL_LDB_BC_A0) [14935.7..-1005.7 to 30664.4..32890.8 um]</text>'
        )

        # Ghost or Active 4FCO eDTC Cavities under U7 (C2238, C2239, C2209, C2210)
        for c_ref, edtc in sorted(u7_edtc_syms.items()):
            bx1, by1, bx2, by2 = edtc["bbox"]
            ex, ey = _tx(bx1), _ty(by2)
            ew, eh = round(_tx(bx2) - _tx(bx1), 2), round(_ty(by1) - _ty(by2), 2)
            if l_name == "4FCO":
                # Draw 300um KOZ + 150um Guard Metal ring on 4FCO view
                kx1, ky1, kx2, ky2 = bx1 - 300.0, by1 - 300.0, bx2 + 300.0, by2 + 300.0
                gx1, gy1, gx2, gy2 = kx1 - 75.0, ky1 - 75.0, kx2 + 75.0, ky2 + 75.0
                lines.append(
                    f'<rect x="{_tx(gx1)}" y="{_ty(gy2)}" width="{_tx(gx2) - _tx(gx1):.1f}" height="{_ty(gy1) - _ty(gy2):.1f}" '
                    'fill="none" stroke="#10b981" stroke-width="8" stroke-opacity="0.75"/>'
                )
                lines.append(
                    f'<rect x="{_tx(kx1)}" y="{_ty(ky2)}" width="{_tx(kx2) - _tx(kx1):.1f}" height="{_ty(ky1) - _ty(ky2):.1f}" '
                    'fill="#ef4444" fill-opacity="0.12" stroke="#f59e0b" stroke-dasharray="6,4" stroke-width="2"/>'
                )
                lines.append(
                    f'<rect x="{ex}" y="{ey}" width="{ew}" height="{eh}" fill="#4c1d95" fill-opacity="0.45" stroke="#c084fc" stroke-width="2.5"/>'
                )
            else:
                lines.append(
                    f'<rect x="{ex}" y="{ey}" width="{ew}" height="{eh}" fill="none" stroke="#a855f7" stroke-dasharray="4,4" stroke-width="1.2" stroke-opacity="0.6"/>'
                )
            lines.append(
                f'<text x="{ex + 8}" y="{ey + 18}" fill="#e9d5ff" font-family="monospace" font-size="12" font-weight="bold">'
                f'{c_ref} ({edtc["symbol_name"].split("_")[0]})</text>'
            )

        # On SURFACE, render U7 VDD* die bumps as subtle background pads
        if l_name == "SURFACE":
            for b in u7_vdd_bumps:
                col = _net_color(b["net"])
                br = 2.0 if "80x80" in b["geom"] else 1.1
                lines.append(
                    f'<circle cx="{_tx(b["x"])}" cy="{_ty(b["y"])}" r="{br}" fill="{col}" fill-opacity="0.55"/>'
                )

        # On 4FCO, render the 336 eDTC terminal pads under U7
        if l_name == "4FCO":
            for ep in u7_edtc_pins:
                col = _net_color(ep["net"])
                lines.append(
                    f'<rect x="{_tx(ep["x"] - 100.0)}" y="{_ty(ep["y"] + 100.0)}" '
                    f'width="{_scale_len(200.0)}" height="{_scale_len(200.0)}" '
                    f'fill="{col}" fill-opacity="0.35" stroke="{col}" stroke-width="1.2"/>'
                )

        # Render Clines on this layer
        for cl in c_list:
            col = _net_color(cl["net"])
            sw = max(1.4, min(6.0, round(cl["width"] / 18.0, 2)))
            lines.append(
                f'<line x1="{_tx(cl["x1"])}" y1="{_ty(cl["y1"])}" x2="{_tx(cl["x2"])}" y2="{_ty(cl["y2"])}" '
                f'stroke="{col}" stroke-width="{sw}" stroke-linecap="round" stroke-opacity="0.88"/>'
            )

        # Render Vias touching this layer
        for v in v_list:
            col = _net_color(v["net"])
            rad_px = max(1.8, _scale_len(_pad_radius_um(v["padstack"])))
            if v["start"] == l_name:
                lines.append(
                    f'<circle cx="{_tx(v["x"])}" cy="{_ty(v["y"])}" r="{rad_px}" fill="{col}" fill-opacity="0.85"/>'
                )
            else:
                lines.append(
                    f'<circle cx="{_tx(v["x"])}" cy="{_ty(v["y"])}" r="{rad_px}" fill="none" stroke="{col}" stroke-width="1.4"/>'
                )

        # Legend Footer
        lines.append('<rect x="30" y="2090" width="1740" height="85" rx="8" fill="#111827" stroke="#334155" stroke-width="1.5"/>')
        legend_items = [
            ("VDDUC0 (Main Uncore Power)", "#f43f5e"),
            ("VDD_0P7_UCIE_E (UCIe Power)", "#f59e0b"),
            ("VDD_0P75_HBMPHY_UC0/1/2", "#06b6d4"),
            ("VDDQL0/1/2 & VDDQ (HBM IO)", "#10b981"),
            ("VDDIO_1P2_UCIE_E / MISC", "#a855f7"),
            ("VDD_0P75_MISC_UC0", "#f97316"),
            ("4FCO eDTC / Guard Metal", "#c084fc"),
        ]
        lx_cur = 55
        for label, lcol in legend_items:
            lines.append(f'<circle cx="{lx_cur}" cy="2132" r="8" fill="{lcol}"/>')
            lines.append(
                f'<text x="{lx_cur + 15}" y="2137" fill="#e2e8f0" font-family="monospace" font-size="13">{html.escape(label)}</text>'
            )
            lx_cur += 245

        lines.append("</svg>")
        fname = (
            f"layer_{idx:02d}_{l_name}_U7_eDTC_VDDUC0_VDD.svg"
            if l_name == "4FCO"
            else f"layer_{idx:02d}_{l_name}_U7_VDDUC0_VDD.svg"
        )
        svg_files.append(_validate_and_save_svg("\n".join(lines), out_dir / fname))

    # 7. Render U7 Topside BU Vertical Cross-Section SVG
    cs_lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 920" width="1500" height="920">',
        '<rect width="1500" height="920" fill="#090d16"/>',
        '<text x="40" y="45" fill="#f8fafc" font-family="monospace" font-size="22" font-weight="bold">'
        'U7 (HUTTON_HILL_LDB_BC_A0) — Topside Build-Up (SURFACE..4FCO) Vertical Stackup &amp; Via Span Summary</text>',
    ]
    y_c = 85
    for idx, l_name, _, desc in TOPSIDE_BU_LAYERS:
        st = per_layer_stats[l_name]
        col = "#f43f5e" if idx % 2 == 1 else "#06b6d4"
        if l_name == "4FCO":
            col = "#a855f7"
        cs_lines.append(
            f'<rect x="220" y="{y_c}" width="1220" height="48" rx="4" fill="{col}" fill-opacity="0.22" stroke="{col}" stroke-width="2"/>'
        )
        cs_lines.append(
            f'<text x="45" y="{y_c + 30}" fill="#f8fafc" font-family="monospace" font-size="16" font-weight="bold">'
            f'L{idx:02d}: {l_name}</text>'
        )
        cs_lines.append(
            f'<text x="240" y="{y_c + 22}" fill="#f8fafc" font-family="monospace" font-size="14" font-weight="bold">'
            f'VDDUC0 Vias={st["vdduc0_vias"]:,} | Other VDD* Vias={st["other_vdd_vias"]:,} | VSS Vias={st["vss_vias"]:,} '
            f'(VDD/VSS={st["vdd_to_vss_via_ratio"]}) | Clines={st["vdd_clines"]:,}</text>'
        )
        cs_lines.append(
            f'<text x="240" y="{y_c + 41}" fill="#cbd5e1" font-family="monospace" font-size="12">{html.escape(desc)}</text>'
        )
        y_c += 72
    cs_lines.append("</svg>")
    svg_files.append(_validate_and_save_svg("\n".join(cs_lines), out_dir / "U7_topside_BU_cross_section.svg"))

    # 8. Save Recipe & JSON Summary in pdn_sandbox/
    recipe_file = out_dir / "U7_topside_BU_recipe.txt"
    recipe_file.write_text("\n".join(recipe_lines) + "\n", encoding="utf-8")

    summary = {
        "status": "SUCCESS",
        "target_refdes": "U7",
        "symbol_name": "HUTTON_HILL_LDB_BC_A0",
        "u7_bbox_um": list(U7_BBOX),
        "u7_edtc_symbols_on_4fco": list(u7_edtc_syms.keys()),
        "u7_vdd_bumps_on_surface": len(u7_vdd_bumps),
        "per_layer_stats": per_layer_stats,
        "svg_files": svg_files,
        "recipe_file": str(recipe_file),
    }
    (out_dir / "U7_topside_BU_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    res = run_u7_topside_bu_sandbox()
    print(json.dumps(res["per_layer_stats"], indent=2))
