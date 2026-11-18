"""
Headless LSC (Land-Side Capacitor) Pin Net Assignment Engine & CLI for Agent 04 (`pdn_architect`).

Supports 3 deterministic modes on Cadence APD 25.1 (`.mcm`) databases:
  1. `MAP_FILE`         : Streams a pipe-delimited `LSC_PIN_MAP|<refdes>|<pin1_net>|<pin2_net>[|<x>|<y>|<rot>|<sym>|<create>]`
                          table into SKILL `makeTable` for O(1) pin-net re-mapping (following the global SKILL memory rule).
  2. `AUTO_FROM_LAYOUT` : Automatically detects Pin 1 (`VDD*`) & Pin 2 (`VSS`) nets on placed `BASE` LSCs
                          from touching `12B->BASE` vias or underlying `CONDUCTOR/12B` / `10B` copper islands!
  3. `REGION_RULE`      : Assigns all `BASE` LSCs inside an optional `(x1, y1, x2, y2)` pocket/polygon bounding box
                          to `vdd_net` & `vss_net` (headless equivalent of legacy `HFC_change_pin_net_bga_lsc.il`).

Also automatically upgrades any unattached mechanical/package LSC symbols (`sym->component == nil`)
into true logical components (`axlDBCreateComponent` + `axlDBCreateSymbol` + `axlChangeNet`) so
100% of LSC pins hold real electrical nets in Allegro / APD!
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .cadence_runner import CadenceBatchRunner


def export_lsc_pin_map_file(
    records: Iterable[Dict[str, Any]],
    output_map_path: Path,
    create_if_missing: bool = False,
) -> Path:
    """
    Write a flat pipe-delimited LSC pin-net mapping file for O(1) SKILL `makeTable` ingestion:
      LSC_PIN_MAP|<refdes>|<pin1_net>|<pin2_net>|<x_um>|<y_um>|<rot_deg>|<symbol_name>|<YES/NO>
    """
    out_p = Path(output_map_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    create_flag = "YES" if create_if_missing else "NO"

    lines = [
        "# Pipe-delimited LSC Pin Net Mapping Table for Headless Cadence APD 25.1",
        "# Format: LSC_PIN_MAP|refdes|pin1_net|pin2_net|x_um|y_um|rot_deg|symbol_name|create_if_missing",
    ]
    count = 0
    for rec in records:
        ref = str(rec.get("refdes") or rec.get("ref") or f"C_LSC_{count + 1:04d}").strip()
        p1 = str(rec.get("pin1_net") or rec.get("vdd_net") or "VDDUC0").strip()
        p2 = str(rec.get("pin2_net") or rec.get("vss_net") or "VSS").strip()
        x = float(rec.get("x_um", rec.get("x", 0.0)))
        y = float(rec.get("y_um", rec.get("y", 0.0)))
        rot = float(rec.get("rotation", rec.get("rot", 0.0)))
        sym = str(rec.get("symbol_name") or rec.get("symbol") or "SM0201_690X390X550_01A").strip()
        c_row = str(rec.get("create_if_missing", create_flag)).upper()
        c_str = "YES" if c_row in ("YES", "TRUE", "1") else create_flag
        lines.append(f"LSC_PIN_MAP|{ref}|{p1}|{p2}|{x:.3f}|{y:.3f}|{rot:.1f}|{sym}|{c_str}")
        count += 1

    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_p


def build_lsc_pin_map_from_csv(
    csv_path: Path,
    output_map_path: Path,
    refdes_filter: Optional[Sequence[str]] = None,
    default_vdd_net: str = "VDDUC0",
    default_vss_net: str = "VSS",
    create_if_missing: bool = False,
) -> Tuple[Path, int]:
    """
    Parse a large CSV (e.g. `lsc_placed_map.csv`, `U7_27Layer_APD_LSC_Symbols.csv`, or `cap_placement_shifted.csv`)
    in Python, optionally filter by `refdes_filter`, and emit a clean pipe-delimited `LSC_PIN_MAP` file.
    """
    allow_refs = {r.strip().upper() for r in refdes_filter} if refdes_filter else None
    parsed: List[Dict[str, Any]] = []
    with Path(csv_path).open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            ref = (row.get("refdes") or row.get("RefDes") or f"C_LSC_{idx + 1:04d}").strip()
            if allow_refs and ref.upper() not in allow_refs:
                continue
            p1 = (row.get("pin1_net") or row.get("vdd_net") or default_vdd_net).strip()
            p2 = (row.get("pin2_net") or row.get("vss_net") or default_vss_net).strip()
            x = float(row.get("x_um") or row.get("x") or 0.0)
            y = float(row.get("y_um") or row.get("y") or 0.0)
            rot = float(row.get("rotation_deg") or row.get("rotation") or row.get("rot") or 0.0)
            sym = (row.get("symbol_name") or row.get("symbol") or "SM0201_690X390X550_01A").strip()
            parsed.append({
                "refdes": ref,
                "pin1_net": p1,
                "pin2_net": p2,
                "x_um": x,
                "y_um": y,
                "rot": rot,
                "symbol_name": sym,
            })

    map_p = export_lsc_pin_map_file(parsed, output_map_path, create_if_missing=create_if_missing)
    return map_p, len(parsed)


def _parse_kv_file(path: Path) -> Dict[str, str]:
    kv: Dict[str, str] = {}
    if not path.exists():
        return kv
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def assign_lsc_pin_nets(
    mcm_path: Optional[str] = None,
    mode: str = "AUTO_FROM_LAYOUT",
    map_file: Optional[str] = None,
    source_csv: Optional[str] = None,
    refdes_filter: Optional[Sequence[str]] = None,
    region_bbox_um: Optional[Tuple[float, float, float, float]] = None,
    vdd_net: str = "VDDUC0",
    vss_net: str = "VSS",
    ref_layers: Sequence[str] = ("12B", "10B"),
    create_if_missing: bool = False,
    save_design: bool = False,
    out_mcm_path: Optional[str] = None,
    out_dir: Optional[str] = None,
    dry_run: bool = False,
    timeout_sec: int = 900,
) -> Dict[str, Any]:
    """
    Assign or re-map Pin 1 (`VDD*`) and Pin 2 (`VSS`) net names on `BASE` LSC capacitors in `.mcm`.
    """
    mode_u = mode.strip().upper()
    if mode_u not in ("MAP_FILE", "AUTO_FROM_LAYOUT", "REGION_RULE"):
        raise ValueError(f"Unsupported mode '{mode}'. Choose from MAP_FILE, AUTO_FROM_LAYOUT, REGION_RULE.")

    agent_dir = Path(__file__).resolve().parent.parent
    work_dir = Path(out_dir).resolve() if out_dir else (agent_dir / "reports" / "lsc_pin_net_assign")
    work_dir.mkdir(parents=True, exist_ok=True)

    resolved_map_path = ""
    mapped_rows_count = 0
    if source_csv:
        mp, cnt = build_lsc_pin_map_from_csv(
            csv_path=Path(source_csv),
            output_map_path=work_dir / "lsc_pin_net_map.txt",
            refdes_filter=refdes_filter,
            default_vdd_net=vdd_net,
            default_vss_net=vss_net,
            create_if_missing=create_if_missing,
        )
        resolved_map_path = str(mp).replace("\\", "/")
        mapped_rows_count = cnt
        mode_u = "MAP_FILE"
    elif map_file:
        mp = Path(map_file).resolve()
        resolved_map_path = str(mp).replace("\\", "/")
        if mp.exists():
            mapped_rows_count = sum(
                1 for ln in mp.read_text(encoding="utf-8").splitlines() if ln.startswith("LSC_PIN_MAP|")
            )

    il_script = agent_dir / "scripts" / "lsc_pin_net_assign_batch.il"
    report_file = work_dir / "lsc_pin_net_assign_report.txt"
    scr_file = work_dir / "run_lsc_pin_net_assign.scr"

    bbox_skill = (
        f"list({region_bbox_um[0]:.3f} {region_bbox_um[1]:.3f} {region_bbox_um[2]:.3f} {region_bbox_um[3]:.3f})"
        if region_bbox_um is not None
        else "nil"
    )
    layers_skill = "list(" + " ".join(f'"{lyr}"' for lyr in ref_layers) + ")"
    save_flag = "t" if (save_design or bool(out_mcm_path)) else "nil"
    out_mcm_skill = str(Path(out_mcm_path).resolve()).replace("\\", "/") if out_mcm_path else ""
    rep_skill = str(report_file).replace("\\", "/")
    il_skill = str(il_script).replace("\\", "/")

    if dry_run or not mcm_path:
        skill_call_dry = (
            f'pdnAssignLscPinNetsBatch("{mode_u}" "{resolved_map_path}" {bbox_skill} '
            f'"{vdd_net}" "{vss_net}" {layers_skill} {save_flag} "{out_mcm_skill}" "{rep_skill}")'
        )
        scr_file.write_text(f'skill load("{il_skill}")\nskill {skill_call_dry}\nexit\nfillin no\n', encoding="utf-8")
        return {
            "status": "DRY_RUN_READY",
            "mode": mode_u,
            "map_file": resolved_map_path or None,
            "mapped_rows_count": mapped_rows_count,
            "scr_file": str(scr_file),
            "il_script": str(il_script),
            "report_file": str(report_file),
        }

    import shutil

    mcm_abs = Path(mcm_path).resolve()
    target_open_mcm = mcm_abs
    in_place_out_skill = ""
    if out_mcm_path:
        out_abs = Path(out_mcm_path).resolve()
        out_abs.parent.mkdir(parents=True, exist_ok=True)
        if out_abs != mcm_abs:
            shutil.copy2(mcm_abs, out_abs)
            lck_cand = out_abs.with_name(out_abs.name + ".lck")
            if lck_cand.exists():
                lck_cand.unlink()
        target_open_mcm = out_abs
    elif save_design:
        in_place_out_skill = ""

    skill_call = (
        f'pdnAssignLscPinNetsBatch("{mode_u}" "{resolved_map_path}" {bbox_skill} '
        f'"{vdd_net}" "{vss_net}" {layers_skill} {save_flag} "{in_place_out_skill}" "{rep_skill}")'
    )
    scr_file.write_text(f'skill load("{il_skill}")\nskill {skill_call}\nexit\nfillin no\n', encoding="utf-8")

    runner = CadenceBatchRunner(default_timeout=timeout_sec)
    run_res = None
    for _attempt in range(2):
        if report_file.exists():
            report_file.unlink()
        run_res = runner.run(
            mcm_path=target_open_mcm,
            scr_path=scr_file,
            working_dir=work_dir,
            timeout=timeout_sec,
            bypass_lock_readonly=not (save_design or bool(out_mcm_path)),
        )
        if report_file.exists():
            break

    kv = _parse_kv_file(report_file)
    final_status = kv.get("STATUS", "ERROR") if report_file.exists() else "ERROR_NO_REPORT_LICENSE_OR_LOCK"
    return {
        "status": final_status,
        "mode": mode_u,
        "mcm_path": str(mcm_abs),
        "out_mcm_path": str(target_open_mcm) if (out_mcm_path or save_design) else None,
        "map_file": resolved_map_path or None,
        "scr_file": str(scr_file),
        "report_file": str(report_file),
        "duration_sec": run_res.duration_sec,
        "lsc_scanned": int(kv.get("LSC_SCANNED", "0")),
        "lsc_cleared_preexisting": int(kv.get("LSC_CLEARED_PREEXISTING", "0")),
        "lsc_cavities_drawn": int(kv.get("LSC_CAVITIES_DRAWN", "0")),
        "lsc_pins_updated": int(kv.get("LSC_PINS_UPDATED", "0")),
        "lsc_unattached_upgraded": int(kv.get("LSC_UNATTACHED_UPGRADED", "0")),
        "lsc_newly_created_with_nets": int(kv.get("LSC_NEWLY_CREATED_WITH_NETS", "0")),
        "lsc_already_matched_skipped": int(kv.get("LSC_ALREADY_MATCHED_SKIPPED", "0")),
        "lsc_failed": int(kv.get("LSC_FAILED", "0")),
        "verified_target_lscs_in_db": int(kv.get("VERIFIED_TARGET_LSCS_IN_DB", "0")),
        "verified_on_base_layer": int(kv.get("VERIFIED_ON_BASE_LAYER", "0")),
        "verified_on_surface_layer": int(kv.get("VERIFIED_ON_SURFACE_LAYER", "0")),
        "verified_pin1_net_matched": int(kv.get("VERIFIED_PIN1_NET_MATCHED", "0")),
        "verified_pin2_net_matched": int(kv.get("VERIFIED_PIN2_NET_MATCHED", "0")),
        "verified_rot_0_count": int(kv.get("VERIFIED_ROT_0_COUNT", "0")),
        "verified_rot_90_count": int(kv.get("VERIFIED_ROT_90_COUNT", "0")),
        "verified_rot_180_count": int(kv.get("VERIFIED_ROT_180_COUNT", "0")),
        "verified_rot_270_count": int(kv.get("VERIFIED_ROT_270_COUNT", "0")),
    }


def place_vdduc0_lscs_with_pin_nets_to_new_mcm(
    base_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test.mcm",
    out_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test_VDDUC0_LSC_BASE_180Alt.mcm",
    sro_to_sro_min_um: float = 250.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Create a brand-new `.mcm` from `base_mcm_path` (leaving `base_mcm_path` untouched),
    draw the 2 `R = 500 um` `SUBSTRATE GEOMETRY/LSC_CAVITY` pockets + `178 um` `Code D` keepouts,
    place all `VDDUC0` `0201` LSCs (`90` @ `250 um` `10uF` or `114` @ `175 um` `1uF`) on `BASE`,
    and assign electrical nets (`Pin 1 = VDDUC0`, `Pin 2 = VSS`) on every single LSC pin!
    """
    from .vdduc0_base_cavity_lsc_svg_generator import (
        U7_LEARNED_BGA_POCKETS,
        VDDUC0_POCKET_IDS,
        load_vdduc0_region_bga_balls,
        pack_vdduc0_pocket_with_cavity_rule,
    )

    ws = Path(__file__).resolve().parent.parent.parent
    bgas = load_vdduc0_region_bga_balls(ws)
    vdduc0_pockets = [p for p in U7_LEARNED_BGA_POCKETS if p["pocket_id"] in VDDUC0_POCKET_IDS]
    sym_name = "SM0201_690X390X550_01A" if sro_to_sro_min_um >= 200.0 else "SM0201S_690X390X220_01C"

    work_dir = ws / "agent04_pdn_architect" / "reports" / "vdduc0_lsc_mcm_build"
    work_dir.mkdir(parents=True, exist_ok=True)
    map_path = work_dir / "vdduc0_lsc_cavity_and_pin_map.txt"

    lines = [
        "# VDDUC0 BASE Cavity + LSC Placement & Pin Net Assignment Recipe",
        "# Clears any partial pre-existing BASE LSCs inside Pocket 6 & Pocket 7, draws R=500um LSC_CAVITY,",
        "# places all VDDUC0 0201 logical LSC components, and assigns Pin1=VDDUC0 / Pin2=VSS.",
    ]
    cap_seq = 1
    for p in vdduc0_pockets:
        res = pack_vdduc0_pocket_with_cavity_rule(p, bgas, sro_to_sro_min_um=sro_to_sro_min_um)
        w_l, w_b, w_r, w_t = p["bga_walls"]
        lines.append(f"CLEAR_BASE_LSC_BBOX|{w_l:.3f}|{w_b:.3f}|{w_r:.3f}|{w_t:.3f}")
        cx0, cy0, cx1, cy1 = res["cavity_info"]["cavity_bbox"]
        rc = res["cavity_info"]["corner_radius_um"]
        lines.append(f"CAVITY_OUTLINE|{p['pocket_id']}|{cx0:.3f}|{cy0:.3f}|{cx1:.3f}|{cy1:.3f}|{rc:.1f}|178.0")
        for c in res["placed_lscs"]:
            ref = f"C_VDDUC0_{cap_seq:03d}"
            cap_seq += 1
            lines.append(
                f"LSC_PIN_MAP|{ref}|VDDUC0|VSS|{c['x']:.3f}|{c['y']:.3f}|{c['rot']:.1f}|{sym_name}|YES"
            )

    map_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return assign_lsc_pin_nets(
        mcm_path=str((ws / base_mcm_path).resolve()),
        mode="MAP_FILE",
        map_file=str(map_path),
        vdd_net="VDDUC0",
        vss_net="VSS",
        create_if_missing=True,
        save_design=True,
        out_mcm_path=str((ws / out_mcm_path).resolve()),
        out_dir=str(work_dir),
        dry_run=dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless Cadence APD LSC Pin Net Assignment CLI")
    parser.add_argument("--mcm", type=str, default=None, help="Target .mcm database path")
    parser.add_argument(
        "--mode",
        type=str,
        default="AUTO_FROM_LAYOUT",
        choices=["MAP_FILE", "AUTO_FROM_LAYOUT", "REGION_RULE"],
        help="Pin-net assignment mode",
    )
    parser.add_argument("--map-file", type=str, default=None, help="Pipe-delimited LSC_PIN_MAP file")
    parser.add_argument("--source-csv", type=str, default=None, help="CSV file to convert into LSC_PIN_MAP")
    parser.add_argument("--vdd-net", type=str, default="VDDUC0", help="Default/target VDD net for Pin 1")
    parser.add_argument("--vss-net", type=str, default="VSS", help="Default/target VSS net for Pin 2")
    parser.add_argument("--bbox", type=str, default=None, help="Optional x1,y1,x2,y2 in um for REGION_RULE / filtering")
    parser.add_argument("--create-missing", action="store_true", help="Create missing logical LSCs from MAP_FILE")
    parser.add_argument("--out-mcm", type=str, default=None, help="Save updated design to a new .mcm file")
    parser.add_argument("--save", action="store_true", help="Save .mcm in-place")
    parser.add_argument("--dry-run", action="store_true", help="Generate .scr and map file without invoking apd.exe")
    args = parser.parse_args()

    bbox_tuple = None
    if args.bbox:
        vals = [float(v.strip()) for v in args.bbox.split(",")]
        if len(vals) == 4:
            bbox_tuple = (vals[0], vals[1], vals[2], vals[3])

    res = assign_lsc_pin_nets(
        mcm_path=args.mcm,
        mode=args.mode,
        map_file=args.map_file,
        source_csv=args.source_csv,
        region_bbox_um=bbox_tuple,
        vdd_net=args.vdd_net,
        vss_net=args.vss_net,
        create_if_missing=args.create_missing,
        save_design=args.save,
        out_mcm_path=args.out_mcm,
        dry_run=args.dry_run,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
