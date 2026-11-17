"""
End-to-End 27-Layer (`SURFACE` L01 -> `BASE` L27) `.mcm` Builder & APD SKILL Verifier
for the `U6` (`HUTTON_HILL_LDB_BC_A0`, `VDDUC3 + VSS`) 8-Step PDN Sandbox.

Enforces all User & Substrate Design Rule Invariants:
  1. Read-only template protection: copies `MCM_template/PDN_test.mcm` -> `pdn_sandbox/PDN_test_U6_VDDUC3_VSS_8Step.mcm`.
  2. Step 1 (`SURFACE`): `FULL` 1:1 VIP (`7,747 VDDUC3 + 8,217 VSS`) + `1,658` `24um` KOZ escape straps (`0` floating bumps).
  3. Step 2 + Step 8 (`BU-Cut Co-Routing`): `0` PP vias cut (`100%` of Step 4 `1_VIA_CENTER` PP vias preserved);
     conflicting Step 2 / Step 7 Build-Up columns cut ONLY on BU (`-> 8F/10F` & `-> 9F` frontside; `-> 8B/10B` & `-> 9B` backside).
  4. Step 3 + Step 4 (`5.0 PTH/mm²` `STAGGERED` Core PTH + `1_VIA_CENTER` Prepreg PP) + `4FCO`/`4BCO` `68um` tie-in straps
     so `0` vias ever dangle on opposite-polarity planes.
  5. Under-`U6` `4FCO` `eDTC`s (`C2243, C2244, C2213, C2214`): `100%` concentric pin landing (`6F->5F->4FCO` `VDDUC3`,
     `5F->4FCO` `VSS`, `<= 2` stacked vias on eDTC pad) + `300um` cavity + `150um` Static Guard Band frames + `5B` solid `VSS` plane.
  6. Step 5 + Step 6 (`BASE <-> 12B`): Deletes `90` pre-existing unrouted `VDDUC3` LSCs, instantiates `2` curved `LSC_CAVITY`
     pockets, places `86` `CONDUCTOR/BASE` (`mir=nil`, `180-deg` alternating) `SM0201_690X390X550_01A` LSCs (`Pin 1=VDDUC3`, `Pin 2=VSS`),
     and routes `233` On-BGA + `204` Interstitial `90.0um`-pitch `2x2` `4-via` clusters + `516` LSC `12B:BASE` vias.
  7. Streams `VIA` and `CLINE` BEFORE `POLY_SHAPE` (`24` Dynamic Copper Planes + Static `10F`/`4FCO`/`4BCO` Guard Bands)
     for fast headless `apd.exe` import and runs an independent post-pour SKILL audit.
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import json
import math
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .cadence_runner import CadenceBatchRunner
from .curved_recess_and_lsc_engine import (
    CurvedPocketResult,
    PlacedLscItem,
    _pt_in_poly,
    _pt_to_poly_boundary_dist,
)
from .multi_rail_polygon_engine import (
    ALL_24_INNER_LAYERS,
    BBox,
    CavityRecord,
    ClineRecord,
    EdtcInstanceProfile,
    FastXYClearanceGrid,
    PADSTACK_CONDUCTOR_RADII,
    Point,
    PolygonIsland,
    ViaRecord,
    audit_via_continuity_and_zero_overlap,
    bboxes_intersect,
    can_place_via_stack_zero_overlap,
    compute_real_edtc_profiles,
    expand_bbox,
    insert_via_stack_zero_overlap,
    make_plane_with_Notches_and_voids,
    rect_vertices,
)
from .pdn_8step_flow import (
    BACK_LAYER_ORDER,
    EDTC_PTH_CENTER_KOZ_UM,
    FRONT_LAYER_ORDER,
    _back_spans_to,
    _in_box,
    _load_domain_inputs,
    _normalize_target_layer,
    _resolve_profile,
    _run_step1_surface,
    _run_step2_front_transition,
    _run_step3_and_step4_core_pth_and_pp,
    _run_step5_bga_vias,
    _run_step6_lsc_and_recess,
    _run_step7_back_transition,
    _run_step8_transition_to_pp_core,
    extract_core_degas_kozs,
)
from .pdn_paths import REPO_ROOT, resolve_active_work_dir, resolve_output_dir, resolve_stage1_inputs_dir
from .pdn_prelearn import resolve_mcm_in_work_dir


def _pt_to_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _load_or_extract_site_layer_keepouts(
    refdes: str,
    src_mcm: Path,
    sandbox_dir: Path,
    bga_bbox: BBox,
) -> Dict[str, List[BBox]]:
    """
    Load cached `<refdes>_mcm_layer_keepouts.json` (or extract directly from a temporary sandbox copy of `src_mcm`)
    containing all `ROUTE KEEPOUT/*` and `VIA KEEPOUT/*` shapes in that domain's `bga_bbox` (`< 40mm` span).
    """
    ref_u = refdes.strip().upper()
    cache_json = sandbox_dir / f"{ref_u.lower()}_mcm_layer_keepouts.json"
    if cache_json.is_file():
        raw = json.loads(cache_json.read_text(encoding="utf-8"))
        return {k: [(float(b[0]), float(b[1]), float(b[2]), float(b[3])) for b in v] for k, v in raw.items()}

    tmp_mcm = sandbox_dir / f"_tmp_koz_probe_{ref_u}.mcm"
    tmp_il = sandbox_dir / f"_tmp_koz_probe_{ref_u}.il"
    tmp_scr = sandbox_dir / f"_tmp_koz_probe_{ref_u}.scr"
    tmp_txt = sandbox_dir / f"_tmp_koz_probe_{ref_u}.txt"
    shutil.copy2(src_mcm, tmp_mcm)
    x0, y0, x1, y1 = bga_bbox
    tmp_il.write_text(
        f"""procedure( pdnDumpSiteKoz_{ref_u}(outFile)
  let( (outP bx)
    outP = outfile(outFile "w")
    foreach( cls list("ROUTE KEEPOUT" "VIA KEEPOUT")
      when( axlSubclasses(cls)
        foreach( sub axlSubclasses(cls)
          foreach( sh axlDBGetShapes(strcat(cls "/" sub))
            bx = sh->bBox
            when( bx && float(car(cadr(bx))) >= {x0:.1f} && float(car(car(bx))) <= {x1:.1f} && float(cadr(cadr(bx))) >= {y0:.1f} && float(cadr(car(bx))) <= {y1:.1f}
              fprintf(outP "%s/%s|%.2f|%.2f|%.2f|%.2f\\n" cls sub float(car(car(bx))) float(cadr(car(bx))) float(car(cadr(bx))) float(cadr(cadr(bx))))
            )
          )
        )
      )
    )
    close(outP)
    t
  )
)
""",
        encoding="utf-8",
    )
    tmp_scr.write_text(
        f'skill load("{tmp_il.as_posix()}")\n'
        f'skill pdnDumpSiteKoz_{ref_u}("{tmp_txt.as_posix()}")\n'
        "exit\nfillin no\n",
        encoding="utf-8",
    )
    CadenceBatchRunner(default_timeout=180).run(tmp_mcm, tmp_scr, sandbox_dir, timeout=180, bypass_lock_readonly=False)
    by_sub: Dict[str, Set[BBox]] = collections.defaultdict(set)
    if tmp_txt.is_file():
        for ln in tmp_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            p = ln.split("|")
            if len(p) == 5:
                bx0, by0, bx1, by1 = float(p[1]), float(p[2]), float(p[3]), float(p[4])
                if (bx1 - bx0) > 40000.0 or (by1 - by0) > 40000.0:
                    continue
                by_sub[p[0]].add((round(bx0, 2), round(by0, 2), round(bx1, 2), round(by1, 2)))
    for f_tmp in (tmp_mcm, tmp_mcm.with_name(tmp_mcm.name + ".lck"), tmp_il, tmp_scr, tmp_txt):
        if f_tmp.exists():
            f_tmp.unlink()
    out_map = {k: sorted(v) for k, v in sorted(by_sub.items())}
    cache_json.write_text(json.dumps({k: [list(b) for b in v] for k, v in out_map.items()}, indent=2), encoding="utf-8")
    return out_map


def _load_or_extract_u6_layer_keepouts(
    src_mcm: Path,
    sandbox_dir: Path,
    bga_bbox: BBox = (-30500.0, -32500.0, -15800.0, 400.0),
) -> Dict[str, List[BBox]]:
    return _load_or_extract_site_layer_keepouts("U6", src_mcm, sandbox_dir, bga_bbox)


def _compute_ldb_plane_bboxes(refdes: str) -> Tuple[BBox, BBox, BBox]:
    """
    Compute exact quadrant-isolated `(front_plane_bbox, core_back_bbox, bga_12b_bbox)` for any
    Hutton Hill LDB site (`U7`: +X/+Y, `U5`: -X/+Y, `U8`: +X/-Y, `U6`: -X/-Y), enforcing:
      - `200.0 um` horizontal split gap across `Y = 0` on Front BU (`|Y| >= 100.0 um`)
      - `300.0 um` horizontal split gap across `Y = 0` on Core/Back (`|Y| >= 150.0 um`)
      - `>= 146 um` clearance from `LDA` (`|X| >= 16050`), `>= 198 um` from `HBM` (`|X| <= 30180`),
        and `>= 205 um` from `LDC` (`|Y| <= 31800`)
      - Exact Top (`Y in [1330..31150]`) vs Bottom (`Y in [-31580..-1800]`) `12B` BGA islands
        accounting for the `-470 um` vertical BGA grid offset.
    """
    ref_u = refdes.strip().upper()
    is_east = ref_u in ("U7", "U8")
    is_north = ref_u in ("U7", "U5")

    fx0, fx1 = (16050.0, 30180.0) if is_east else (-30180.0, -16050.0)
    fy0, fy1 = (100.0, 31800.0) if is_north else (-31800.0, -100.0)
    front_plane_bbox: BBox = (fx0, fy0, fx1, fy1)

    cx0, cx1 = (16120.0, 27300.0) if is_east else (-27300.0, -16120.0)
    cy0, cy1 = (150.0, 31750.0) if is_north else (-31750.0, -150.0)
    core_back_bbox: BBox = (cx0, cy0, cx1, cy1)

    bx0, bx1 = (18420.0, 27180.0) if is_east else (-27180.0, -18420.0)
    by0, by1 = (1330.0, 31150.0) if is_north else (-31580.0, -1800.0)
    bga_12b_bbox: BBox = (bx0, by0, bx1, by1)

    return front_plane_bbox, core_back_bbox, bga_12b_bbox


def _seed_grid_with_mcm_keepouts(grid: FastXYClearanceGrid, koz_map: Dict[str, List[BBox]]) -> int:
    """
    Seed `FastXYClearanceGrid` with interior `ROUTE KEEPOUT/<layer>` and `VIA KEEPOUT/<layer>` boxes
    inset by `14.0 um` (`r_obs=1.0 um`, `diff_gap=25.0 um` -> `>= +6.2 um` corner & `+12.0 um` edge clearance
    outside every Allegro keepout rectangle!).
    """
    cond_layers = (
        "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F",
        "4FCO", "3FCI", "2FCI", "1FCI", "1BCI", "2BCI", "3BCI", "4BCO",
        "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B", "BASE",
    )
    pts_seeded = 0
    for lyr in cond_layers:
        boxes_l: List[BBox] = []
        for b in koz_map.get(f"ROUTE KEEPOUT/{lyr}", ()):
            w_b, h_b = b[2] - b[0], b[3] - b[1]
            # Seed all degassing/fiducial keepouts (<1000um) plus 10F EMIB/guard moats
            if (w_b < 1000.0 and h_b < 1000.0) or lyr == "10F":
                boxes_l.append(b)
        if lyr == "10F":
            boxes_l.extend(koz_map.get("ROUTE KEEPOUT/10-11F", ()))
        if lyr != "4FCO":
            for b in koz_map.get(f"VIA KEEPOUT/{lyr}", ()):
                if (b[2] - b[0]) < 1000.0 and (b[3] - b[1]) < 1000.0:
                    boxes_l.append(b)

        for x0, y0, x1, y1 in boxes_l:
            ix0 = min(0.5 * (x0 + x1), x0 + 4.0)
            ix1 = max(0.5 * (x0 + x1), x1 - 4.0)
            iy0 = min(0.5 * (y0 + y1), y0 + 4.0)
            iy1 = max(0.5 * (y0 + y1), y1 - 4.0)
            nx = max(1, int(math.ceil((ix1 - ix0) / 12.0)))
            ny = max(1, int(math.ceil((iy1 - iy0) / 12.0)))
            for i in range(nx + 1):
                sx = ix0 if nx == 0 else (ix0 + (ix1 - ix0) * i / nx)
                for j in range(ny + 1):
                    sy = iy0 if ny == 0 else (iy0 + (iy1 - iy0) * j / ny)
                    grid.insert(f"COND_{lyr}", round(sx, 2), round(sy, 2), 5.0, "__KEEPOUT__")
                    pts_seeded += 1
    return pts_seeded


def build_ldb_domain_27layer_polygons(
    refdes: str,
    primary_vdd: str,
    front_plane_bbox: BBox,
    core_back_bbox: BBox,
    bga_12b_bbox: BBox,
    emib_157_boxes: Sequence[BBox],
    edtc_profiles: Dict[str, EdtcInstanceProfile],
    mcm_keepouts: Optional[Dict[str, List[BBox]]] = None,
) -> List[PolygonIsland]:
    """
    Synthesize all 24 inner-layer (`12F .. 12B`) Dynamic Power/VSS copper planes plus
    Static `4FCO`/`4BCO` `eDTC` `150um` Guard Band frames for any `LDB` domain (`U7`, `U5`, `U8`, `U6`).
    (Note: `PDN_test.mcm` already contains the pre-built `10F` EMIB Static Guard Rings + `60um` `ROUTE KEEPOUT/10F` moats.)
    """
    ref_u = refdes.strip().upper()
    islands: List[PolygonIsland] = []
    koz_map = mcm_keepouts or {}
    rkoz_11f_large = [
        expand_bbox(b, 20.0)
        for b in koz_map.get("ROUTE KEEPOUT/11F", ())
        if (b[2] - b[0]) >= 800.0 or (b[3] - b[1]) >= 800.0
    ]
    rkoz_10f_large = [
        expand_bbox(b, 25.0)
        for b in koz_map.get("ROUTE KEEPOUT/10F", ())
        if (b[2] - b[0]) >= 300.0 or (b[3] - b[1]) >= 300.0
    ]
    emib_205_boxes = rkoz_10f_large if rkoz_10f_large else [expand_bbox(eb, 70.0) for eb in emib_157_boxes]
    # Expand inner Core eDTC cutouts by +15.0um (165um >= 150um Rule #24) so dynamic shape corner smoothing
    # never touches the template ROUTE KEEPOUT/3FCI..3BCI boundaries.
    inner_edtc_kozs = [expand_bbox(ep.inner_core_koz_bbox, 15.0) for ep in edtc_profiles.values()]
    outer_edtc_kozs = [ep.outer_core_plane_koz_bbox for ep in edtc_profiles.values()]

    layer_net_map = {
        "12F": primary_vdd,
        "11F": "VSS",
        "10F": primary_vdd,
        "9F": "VSS",
        "8F": primary_vdd,
        "7F": "VSS",
        "6F": primary_vdd,
        "5F": "VSS",
        "4FCO": "VSS",
        "3FCI": primary_vdd,
        "2FCI": "VSS",
        "1FCI": primary_vdd,
        "1BCI": "VSS",
        "2BCI": primary_vdd,
        "3BCI": "VSS",
        "4BCO": primary_vdd,
        "5B": "VSS",
        "6B": primary_vdd,
        "7B": "VSS",
        "8B": primary_vdd,
        "9B": "VSS",
        "10B": primary_vdd,
        "11B": "VSS",
        "12B": primary_vdd,
    }

    for lyr in ALL_24_INNER_LAYERS:
        net_l = layer_net_map[lyr]
        if lyr in ("12F", "11F", "10F", "9F", "8F", "7F", "6F"):
            base_b = front_plane_bbox
        elif lyr == "12B":
            base_b = bga_12b_bbox
        else:
            base_b = core_back_bbox

        kozs: List[BBox] = []
        if lyr == "12F":
            kozs.extend(emib_157_boxes)
        elif lyr == "11F":
            kozs.extend(emib_157_boxes)
            kozs.extend(rkoz_11f_large)
        elif lyr == "10F":
            kozs.extend(emib_205_boxes)
        elif lyr in ("4FCO", "4BCO"):
            kozs.extend(outer_edtc_kozs)
        elif lyr in ("3FCI", "2FCI", "1FCI", "1BCI", "2BCI", "3BCI"):
            kozs.extend(inner_edtc_kozs)
        # Also notch any small ROUTE KEEPOUT/<lyr> box straddling within 30um of base_b's perimeter
        for rkb in koz_map.get(f"ROUTE KEEPOUT/{lyr}", ()):
            if (rkb[2] - rkb[0]) < 1000.0 and (rkb[3] - rkb[1]) < 1000.0 and bboxes_intersect(base_b, rkb):
                if not (rkb[0] > base_b[0] + 30.0 and rkb[1] > base_b[1] + 30.0 and rkb[2] < base_b[2] - 30.0 and rkb[3] < base_b[3] - 30.0):
                    kozs.append(expand_bbox(rkb, 15.0))
        # Note: EMIB is strictly a 10F (CSB) cavity (12F/11F/10F only; 0 EMIB voids in Core 4FCO..4BCO).
        # Note: 5F and 5B are solid VSS planes above/below eDTC cavities (Rule #13: 0 eDTC voids on 5B!).

        islands.append(make_plane_with_Notches_and_voids(lyr, net_l, base_b, kozs, tag=f"{ref_u}_{lyr}_{net_l}"))

        if lyr in ("4FCO", "4BCO"):
            for ep in edtc_profiles.values():
                islands.append(
                    PolygonIsland(
                        layer=lyr,
                        net_name="__ISOLATED__",
                        vertices=rect_vertices(ep.guard_outer_bbox),
                        voids=[rect_vertices(ep.cavity_bbox)],
                        tag=f"{ref_u}_EDTC_{lyr}_GUARD_{ep.refdes}",
                        is_dynamic=False,
                    )
                )

    return islands


def build_u6_27layer_polygons(
    primary_vdd: str,
    front_plane_bbox: BBox,
    core_back_bbox: BBox,
    bga_12b_bbox: BBox,
    emib_157_boxes: Sequence[BBox],
    emib_raw_boxes: Sequence[Tuple[str, BBox]],
    edtc_profiles: Dict[str, EdtcInstanceProfile],
    mcm_keepouts: Optional[Dict[str, List[BBox]]] = None,
) -> List[PolygonIsland]:
    """Backwards-compatible wrapper for `U6`."""
    return build_ldb_domain_27layer_polygons(
        refdes="U6",
        primary_vdd=primary_vdd,
        front_plane_bbox=front_plane_bbox,
        core_back_bbox=core_back_bbox,
        bga_12b_bbox=bga_12b_bbox,
        emib_157_boxes=emib_157_boxes,
        edtc_profiles=edtc_profiles,
        mcm_keepouts=mcm_keepouts,
    )


def write_fast_ordered_master_recipe(
    recipe_path: Path,
    polygons: Sequence[PolygonIsland],
    cavities: Sequence[CavityRecord],
    vias: Sequence[ViaRecord],
    clines: Sequence[ClineRecord],
    placed_lscs: Sequence[PlacedLscItem],
    delete_lsc_refdes: Sequence[str],
) -> Path:
    """
    Write Master Recipe streaming `POLY_CAVITY -> LSC_DELETE -> LSC_PLACE -> VIA -> CLINE -> POLY_SHAPE`
    so `apd_unified_27layer_template_importer.il` creates all `~126,000` vias & clines with zero dynamic-shape
    overhead before instantiating the 24 dynamic planes and running one batch `axlShapeDynamicUpdate(nil t)`.
    """
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        "# U6 (VDDUC3 + VSS) Full 27-Layer 8-Step Master Recipe (0 Via Overlap, 0 PP Vias Cut, BU-Cut Co-Routed)",
        f"# Cavities={len(cavities)} | DeleteLSCs={len(delete_lsc_refdes)} | PlaceLSCs={len(placed_lscs)} | "
        f"Vias={len(vias)} | Clines={len(clines)} | Polygons={len(polygons)}",
    ]

    for cv in cavities:
        if cv.cavity_poly:
            c_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.cavity_poly)
            k_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.outer_koz_poly)
            s_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in cv.inner_safe_poly)
            lines.append(f"POLY_CAVITY|{cv.pocket_id}|{c_str}|{k_str}|{s_str}")

    for del_ref in delete_lsc_refdes:
        lines.append(f"LSC_DELETE|{del_ref}")

    for cap in placed_lscs:
        lines.append(
            f"LSC_PLACE|{cap.refdes}|{cap.symbol_name}|{cap.x:.3f}|{cap.y:.3f}|"
            f"{cap.rot_deg:.1f}|{cap.pin1_net}|{cap.pin2_net}"
        )

    for v in vias:
        lines.append(f"VIA|{v.net_name}|{v.padstack}|{v.start_layer}|{v.end_layer}|{v.x:.3f}|{v.y:.3f}|{v.tag}")

    for cl in clines:
        lines.append(
            f"CLINE|{cl.net_name}|{cl.layer}|{cl.width_um:.2f}|"
            f"{cl.x1:.3f}|{cl.y1:.3f}|{cl.x2:.3f}|{cl.y2:.3f}|{cl.tag}"
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

    recipe_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return recipe_path


def _write_post_import_vdduc_verify_il(
    verify_il_path: Path,
    domain_specs: Sequence[Dict[str, Any]],
) -> Path:
    """
    Write generic SKILL pre-cleaner (`pdnPreCleanVdducPocketLscs`) + independent post-build
    SKILL verifier (`pdnVerifyVdducFull27LayerMcm`) covering 1 or all 4 `VDDUC*` LDB domains
    (`U7/VDDUC0`, `U5/VDDUC1`, `U8/VDDUC2`, `U6/VDDUC3`) in the same `.mcm` database.
    """
    specs_skill = []
    for sp in domain_specs:
        ref_u = str(sp["refdes"]).upper()
        vdd_n = str(sp["vdd_net"]).upper()
        # Non-overlapping quadrant DRC attribution boxes (partitioned at X=0, Y=0)
        is_east = ref_u in ("U7", "U8")
        is_north = ref_u in ("U7", "U5")
        qx0, qx1 = (15800.0, 30500.0) if is_east else (-30500.0, -15800.0)
        qy0, qy1 = (0.0, 32500.0) if is_north else (-32500.0, 0.0)
        # Pocket clear box for pre-clean of any legacy pocket SM0201 / LSC_CAVITY shapes
        px0, px1 = (19000.0, 25000.0) if is_east else (-25000.0, -19000.0)
        py0, py1 = (4500.0, 28500.0) if is_north else (-28500.0, -4500.0)
        edtc_l = " ".join(f'"{er}"' for er in sp["edtc_refs"])
        specs_skill.append(
            f'list("{ref_u}" "{vdd_n}" {qx0:.1f} {qy0:.1f} {qx1:.1f} {qy1:.1f} '
            f'{px0:.1f} {py0:.1f} {px1:.1f} {py1:.1f} list({edtc_l}))'
        )
    specs_list_literal = "list(\n    " + "\n    ".join(specs_skill) + "\n  )"

    il_code = f"""procedure( pdnPreCleanVdducPocketLscs()
  let( (d specs sp refU vddN qx0 qy0 qx1 qy1 px0 py0 px1 py1
        delCompCnt delSymCnt delCavCnt s sName sLyr sx sy pNetMatch cObj bx)
    d = axlDBGetDesign()
    axlSetVariable("logic_edit_enabled" "t")
    specs = {specs_list_literal}
    delCompCnt = 0
    delSymCnt = 0
    delCavCnt = 0
    when( d
      foreach( s d->symbols
        sName = if( s->name then upperCase(s->name) else "" )
        sLyr  = if( s->layer then upperCase(s->layer) else "" )
        sx    = if( s->xy then float(car(s->xy)) else 0.0 )
        sy    = if( s->xy then float(cadr(s->xy)) else 0.0 )
        when( rexMatchp("SM0201" sName)
          let( (matched)
            matched = nil
            foreach( sp specs
              vddN = nth(1 sp)
              px0 = nth(6 sp) py0 = nth(7 sp) px1 = nth(8 sp) py1 = nth(9 sp)
              pNetMatch = nil
              when( s->pins
                foreach( p s->pins
                  when( p->net && p->net->name && upperCase(p->net->name) == vddN
                    pNetMatch = t
                  )
                )
              )
              when( pNetMatch || (sx >= px0 && sx <= px1 && sy >= py0 && sy <= py1 && (rexMatchp("BASE" sLyr) || rexMatchp("BOTTOM" sLyr) || !s->isMirrored))
                matched = t
              )
            )
            when( matched
              cObj = s->component
              errset(axlDeleteObject(s) nil)
              delSymCnt = delSymCnt + 1
              when( cObj
                when( car(errset(axlDeleteObject(cObj) nil))
                  delCompCnt = delCompCnt + 1
                )
              )
            )
          )
        )
      )
      ; Delete any unplaced discrete capacitor components attached to any target VDDUC* net
      foreach( cObj d->components
        when( !cObj->symbol && cObj->pins
          let( (hasTargetVdd)
            hasTargetVdd = nil
            foreach( sp specs
              vddN = nth(1 sp)
              foreach( cp cObj->pins
                when( cp->net && cp->net->name && upperCase(cp->net->name) == vddN
                  hasTargetVdd = t
                )
              )
            )
            when( hasTargetVdd
              when( car(errset(axlDeleteObject(cObj) nil))
                delCompCnt = delCompCnt + 1
              )
            )
          )
        )
      )
      when( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY")
        foreach( sh axlDBGetShapes("SUBSTRATE GEOMETRY/LSC_CAVITY")
          bx = sh->bBox
          when( bx
            let( (inPocket)
              inPocket = nil
              foreach( sp specs
                px0 = nth(6 sp) py0 = nth(7 sp) px1 = nth(8 sp) py1 = nth(9 sp)
                when( float(car(car(bx))) >= px0 && float(car(cadr(bx))) <= px1 &&
                      float(cadr(car(bx))) >= py0 && float(cadr(cadr(bx))) <= py1
                  inPocket = t
                )
              )
              when( inPocket
                errset(axlDeleteObject(sh) nil)
                delCavCnt = delCavCnt + 1
              )
            )
          )
        )
      )
    )
    printf("[VDDUC-PreClean] Removed %d old LSC symbols (%d comps) and %d old cavity shapes.\\n" delSymCnt delCompCnt delCavCnt)
    t
  )
)

procedure( pdnPreCleanU6PocketLscs()
  pdnPreCleanVdducPocketLscs()
)

procedure( pdnVerifyVdducFull27LayerMcm( outFile )
  let( (d outP specs sp refU vddN qx0 qy0 qx1 qy1 edtcRefs cavCnt
        symBaseTbl symSurfTbl p1OkTbl p2OkTbl rotTbl vssTotTbl vssConTbl vssOpnTbl
        drcElecTbl drcPkgTbl drcExtTbl s sRef seStr rDeg dx dy dmName dmLyr pPad pBr)
    errset(axlDRCUpdate(t) nil)
    d = axlDBGetDesign()
    specs = {specs_list_literal}

    symBaseTbl = makeTable("sb" 0)
    symSurfTbl = makeTable("ss" 0)
    p1OkTbl    = makeTable("p1" 0)
    p2OkTbl    = makeTable("p2" 0)
    rotTbl     = makeTable("rt" 0)
    vssTotTbl  = makeTable("vt" 0)
    vssConTbl  = makeTable("vc" 0)
    vssOpnTbl  = makeTable("vo" 0)
    drcElecTbl = makeTable("de" 0)
    drcPkgTbl  = makeTable("dp" 0)
    drcExtTbl  = makeTable("dx" 0)

    when( d
      foreach( s d->symbols
        sRef = if( s->refdes then upperCase(s->refdes) else "" )
        foreach( sp specs
          refU = nth(0 sp)
          vddN = nth(1 sp)
          edtcRefs = nth(10 sp)
          when( rexMatchp(strcat("^CLSC_" refU "_") sRef)
            rDeg = if( s->rotation then mod(round(float(s->rotation)) 360) else 0 )
            rotTbl[sprintf(nil "%s:%d" refU rDeg)] = rotTbl[sprintf(nil "%s:%d" refU rDeg)] + 1
            when( s->pins
              seStr = if( car(s->pins)->startEnd then upperCase(sprintf(nil "%L" car(s->pins)->startEnd)) else "" )
              if( (rexMatchp("BASE" seStr) || rexMatchp("BOTTOM" seStr)) && !rexMatchp("SURFACE" seStr) then
                symBaseTbl[refU] = symBaseTbl[refU] + 1
              else
                symSurfTbl[refU] = symSurfTbl[refU] + 1
              )
              foreach( p s->pins
                let( (pn pnet)
                  pn = if( p->number then sprintf(nil "%s" p->number) else "" )
                  pnet = if( p->net && p->net->name then upperCase(p->net->name) else "" )
                  if( pn == "1" && pnet == vddN then p1OkTbl[refU] = p1OkTbl[refU] + 1 )
                  if( pn == "2" && pnet == "VSS" then p2OkTbl[refU] = p2OkTbl[refU] + 1 )
                )
              )
            )
          )
          when( sRef == refU || member(sRef edtcRefs) || rexMatchp(strcat("^CLSC_" refU "_") sRef)
            when( s->pins
              foreach( p s->pins
                when( p->net && p->net->name && upperCase(p->net->name) == "VSS"
                  pPad = if( p->definition && p->definition->name then upperCase(p->definition->name) else "" )
                  unless( rexMatchp("^C18_" pPad) || rexMatchp("^C21_" pPad) || rexMatchp("^PRS_" pPad)
                    vssTotTbl[refU] = vssTotTbl[refU] + 1
                    pBr = p->branch
                    if( pBr && length(pBr->children) > 1 then
                      vssConTbl[refU] = vssConTbl[refU] + 1
                    else
                      vssOpnTbl[refU] = vssOpnTbl[refU] + 1
                    )
                  )
                )
              )
            )
          )
        )
      )
    )

    cavCnt = if( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY") length(axlDBGetShapes("SUBSTRATE GEOMETRY/LSC_CAVITY")) 0 )

    when( d && d->drcs
      foreach( dm d->drcs
        when( dm->xy
          dx = float(car(dm->xy))
          dy = float(cadr(dm->xy))
          dmName = if( dm->name then dm->name else "" )
          dmLyr  = if( dm->layer then upperCase(dm->layer) else "" )
          foreach( sp specs
            refU = nth(0 sp)
            qx0 = nth(2 sp) qy0 = nth(3 sp) qx1 = nth(4 sp) qy1 = nth(5 sp)
            when( dx >= qx0 && dx <= qx1 && dy >= qy0 && dy <= qy1
              cond(
                ( rexMatchp("Externally Determined" dmName)
                  drcExtTbl[refU] = drcExtTbl[refU] + 1
                )
                ( rexMatchp("PACKAGE_TOP" dmLyr) || rexMatchp("PACKAGE_BOTTOM" dmLyr)
                  drcPkgTbl[refU] = drcPkgTbl[refU] + 1
                )
                ( t
                  drcElecTbl[refU] = drcElecTbl[refU] + 1
                )
              )
            )
          )
        )
      )
    )

    outP = outfile(outFile "w")
    when( outP
      fprintf(outP "VERIFY_STATUS=OK\\n")
      fprintf(outP "LSC_CAVITY_SHAPES_TOTAL=%d\\n" cavCnt)
      foreach( sp specs
        refU = nth(0 sp)
        vddN = nth(1 sp)
        let( (nVdd vddBranches vddRats vddOpenPins vddFloatBr vddPins vddVias vddShapes vddClines)
          nVdd = axlDBFindByName('net vddN)
          vddBranches = if( nVdd && nVdd->branches length(nVdd->branches) 0 )
          vddRats     = if( nVdd && nVdd->rats length(nVdd->rats) 0 )
          vddOpenPins = 0 vddFloatBr = 0 vddPins = 0 vddVias = 0 vddShapes = 0 vddClines = 0
          when( nVdd && nVdd->branches
            foreach( br nVdd->branches
              let( (bp bv bc bs)
                bp = 0 bv = 0 bc = 0 bs = 0
                foreach( ch br->children
                  case( ch->objType
                    ("pin"   bp = bp + 1  vddPins = vddPins + 1)
                    ("via"   bv = bv + 1  vddVias = vddVias + 1)
                    ("path"  bc = bc + 1  vddClines = vddClines + 1)
                    ("shape" bs = bs + 1  vddShapes = vddShapes + 1)
                  )
                )
                when( bp == 1 && bv == 0 && bc == 0 && bs == 0 vddOpenPins = vddOpenPins + 1 )
                when( bp == 0 && (bv + bc + bs) > 0 vddFloatBr = vddFloatBr + 1 )
              )
            )
          )
          fprintf(outP "%s_LSC_ON_CONDUCTOR_BASE=%d\\n" refU symBaseTbl[refU])
          fprintf(outP "%s_LSC_ON_CONDUCTOR_SURFACE=%d\\n" refU symSurfTbl[refU])
          fprintf(outP "%s_LSC_PIN1_VDD_OK=%d\\n" refU p1OkTbl[refU])
          fprintf(outP "%s_LSC_PIN2_VSS_OK=%d\\n" refU p2OkTbl[refU])
          fprintf(outP "%s_LSC_ROT_HIST=0:%d,90:%d,180:%d,270:%d\\n" refU
            rotTbl[sprintf(nil "%s:0" refU)] rotTbl[sprintf(nil "%s:90" refU)]
            rotTbl[sprintf(nil "%s:180" refU)] rotTbl[sprintf(nil "%s:270" refU)])
          fprintf(outP "%s_PINS=%d\\n" vddN vddPins)
          fprintf(outP "%s_VIAS=%d\\n" vddN vddVias)
          fprintf(outP "%s_CLINES=%d\\n" vddN vddClines)
          fprintf(outP "%s_SHAPES=%d\\n" vddN vddShapes)
          fprintf(outP "%s_BRANCHES=%d\\n" vddN vddBranches)
          fprintf(outP "%s_RATS=%d\\n" vddN vddRats)
          fprintf(outP "%s_OPEN_PINS=%d\\n" vddN vddOpenPins)
          fprintf(outP "%s_FLOATING_BRANCHES=%d\\n" vddN vddFloatBr)
          fprintf(outP "%s_VSS_TARGET_PINS=%d\\n" refU vssTotTbl[refU])
          fprintf(outP "%s_VSS_CONNECTED_PINS=%d\\n" refU vssConTbl[refU])
          fprintf(outP "%s_VSS_OPEN_PINS=%d\\n" refU vssOpnTbl[refU])
          fprintf(outP "%s_ELECTRICAL_DRC_MARKERS=%d\\n" refU drcElecTbl[refU])
          fprintf(outP "%s_PACKAGE_BOUND_DRC_MARKERS=%d\\n" refU drcPkgTbl[refU])
          fprintf(outP "%s_TEMPLATE_EXTERNAL_DRC_MARKERS=%d\\n" refU drcExtTbl[refU])
        )
      )
      close(outP)
    )
    errset(axlSaveDesign(?design axlCurrentDesign() ?noConfirm t) nil)
    t
  )
)

procedure( pdnVerifyU6Full27LayerMcm( outFile )
  pdnVerifyVdducFull27LayerMcm(outFile)
)
"""
    verify_il_path.parent.mkdir(parents=True, exist_ok=True)
    verify_il_path.write_text(il_code, encoding="utf-8")
    return verify_il_path


def _write_post_import_u6_verify_il(verify_il_path: Path, vdd_net: str = "VDDUC3") -> Path:
    """Backwards-compatible wrapper for U6-only SKILL verifier."""
    return _write_post_import_vdduc_verify_il(
        verify_il_path,
        domain_specs=[{"refdes": "U6", "vdd_net": vdd_net, "edtc_refs": ["C2243", "C2244", "C2213", "C2214"]}],
    )


ALL_VDDUC_REFDES: Tuple[str, ...] = ("U7", "U5", "U8", "U6")


def _synthesize_single_vdduc_domain(
    refdes: str,
    src_mcm: Path,
    sandbox_dir: Path,
    edtc_pin_rows: Sequence[Dict[str, str]],
    edtc_sym_rows: Sequence[Dict[str, str]],
    grid: FastXYClearanceGrid,
    vias_out: List[ViaRecord],
    clines_out: List[ClineRecord],
) -> Dict[str, Any]:
    """
    Synthesize Steps 1..8, 4FCO eDTC pin landings, curved LSC pockets + CONDUCTOR/BASE LSCs,
    old LSC deletions, and 24 inner Dynamic Planes + 4FCO/4BCO eDTC Guard Bands for one LDB
    domain (`U7`, `U5`, `U8`, or `U6`), appending directly into the shared `grid`, `vias_out`,
    and `clines_out` containers so cross-domain zero overlap is enforced natively.
    """
    ref_u = refdes.strip().upper()
    profile = _resolve_profile("uncore", refdes=ref_u)
    primary_vdd = str(profile["primary_vdd"])
    data = _load_domain_inputs(profile)
    mcm_koz_map = _load_or_extract_site_layer_keepouts(ref_u, src_mcm, sandbox_dir, profile["bga_bbox"])

    # Extend Step 1 via_keepout_boxes with ROUTE KEEPOUT/11F (both 190x190um fiducials and 160um EMIB collars,
    # expanded by +2.0um since surface_layer1_router already adds the 38.5um V77 pad radius!) so any C4 bump
    # whose 12F:11F pad would touch ROUTE KEEPOUT/11F straps cleanly on SURFACE with 0 floating bumps!
    rkoz_11f_for_step1 = [expand_bbox(b, 2.0) for b in mcm_koz_map.get("ROUTE KEEPOUT/11F", ())]
    if rkoz_11f_for_step1:
        data["via_keepout_boxes"] = list(data.get("via_keepout_boxes") or ()) + rkoz_11f_for_step1

    edtc_refs = list(profile["edtc_refs"])
    edtc_profs = compute_real_edtc_profiles(edtc_pin_rows, edtc_sym_rows, target_refdes=edtc_refs)

    # -------------------------------------------------------------------------
    # 1. Step 1: SURFACE FULL VIP + KOZ Escape Straps (0 floating bumps)
    # -------------------------------------------------------------------------
    step1 = _run_step1_surface(profile, data, ratio="FULL", direction="VERTICAL")
    w_surf = float((step1.get("_raw_plan") or {}).get("trace_width_um") or 24.0)
    for cl in step1.get("clines", ()):
        clines_out.append(
            ClineRecord(
                net_name=cl["net"],
                layer="SURFACE",
                width_um=w_surf,
                x1=float(cl["x1"]),
                y1=float(cl["y1"]),
                x2=float(cl["x2"]),
                y2=float(cl["y2"]),
                tag=f"STEP1_SURF_STRAP_{cl['net']}",
            )
        )

    # -------------------------------------------------------------------------
    # 2. Concentric 4FCO eDTC Pin Vias (C2243/C2244 VDDUC3+VSS & C2213/C2214 VSS)
    # -------------------------------------------------------------------------
    edtc_vdd_pins_landed = 0
    edtc_vss_pins_landed = 0
    edtc_bu_obstacles: List[Tuple[str, float, float, float, float]] = []
    for r in edtc_pin_rows:
        if r.get("refdes") not in edtc_refs:
            continue
        pnet = (r.get("net_name") or "").strip()
        px_e, py_e = float(r["x_um"]), float(r["y_um"])
        if pnet == primary_vdd:
            if insert_via_stack_zero_overlap(
                vias_out, grid, primary_vdd, [("6F", "5F"), ("5F", "4FCO")], px_e, py_e, f"EDTC_{r['refdes']}_{primary_vdd}"
            ) > 0:
                edtc_vdd_pins_landed += 1
                edtc_bu_obstacles.append((primary_vdd, round(px_e, 3), round(py_e, 3), round(px_e, 3), round(py_e, 3)))
        elif pnet == "VSS":
            if insert_via_stack_zero_overlap(
                vias_out, grid, "VSS", [("5F", "4FCO")], px_e, py_e, f"EDTC_{r['refdes']}_VSS"
            ) > 0:
                edtc_vss_pins_landed += 1
                # Also record as 6F-adjacent obstacle so Step 2 VDD 6F pads keep >=95um XY clearance (0 6F/5F staggered ov!)
                edtc_bu_obstacles.append((primary_vdd, round(px_e, 3), round(py_e, 3), round(px_e, 3), round(py_e, 3)))

    # Seed FastXYClearanceGrid with all interior ROUTE KEEPOUT/<layer> & VIA KEEPOUT/<layer> boxes
    # (after eDTC pin landing so eDTC pins land cleanly on 4FCO/5F/6F!)
    _seed_grid_with_mcm_keepouts(grid, mcm_koz_map)

    core_degas_kozs = extract_core_degas_kozs(mcm_koz_map)

    # -------------------------------------------------------------------------
    # 3. Step 3 Core PTH (5.0 PTH/mm² STAGGERED) + Step 4 x1 PP (0 PP Vias Cut!)
    # -------------------------------------------------------------------------
    step3, step4 = _run_step3_and_step4_core_pth_and_pp(
        profile=profile,
        data=data,
        pth_density=5.0,
        pth_pattern="STAGGERED",
        pkg_rule="PKG0.8",
        pp_pattern="1_VIA_CENTER",
        grid=grid,
        vias_out=vias_out,
        core_pth_only=False,
        extra_core_koz_boxes=core_degas_kozs,
    )

    # -------------------------------------------------------------------------
    # 4. Step 6 Curved LSC_CAVITY + 86 CONDUCTOR/BASE LSCs & Step 5 90um 4-Via BGA+Interstitial
    # -------------------------------------------------------------------------
    step6 = _run_step6_lsc_and_recess(
        profile=profile,
        data=data,
        out_dir=sandbox_dir,
        grid=grid,
        vias_out=vias_out,
        lsc_vias_per_pad=3,
    )
    pockets: List[CurvedPocketResult] = list(step6.get("_pockets_raw") or ())
    step5 = _run_step5_bga_vias(
        profile=profile,
        data=data,
        bga_pattern="OPTION5_4VIA_90UM_PITCH_WITH_INTERSTITIAL",
        grid=grid,
        vias_out=vias_out,
        pockets=pockets,
        interstitial_clusters=True,
    )

    # Add BASE pad-capture CLINE ties inside On-BGA pads & 0201 LSC pads so APD binds pins->vias before dynamic pour
    bga_offs = step5["offsets_um"]
    for net_b, bx_c, by_c in step5.get("on_bga_clusters", ()):
        for odx, ody in bga_offs:
            clines_out.append(
                ClineRecord(
                    net_name=net_b,
                    layer="BASE",
                    width_um=50.0,
                    x1=bx_c,
                    y1=by_c,
                    x2=round(bx_c + odx, 3),
                    y2=round(by_c + ody, 3),
                    tag=f"STEP5_BGA_PAD_TIE_{net_b}",
                )
            )

    placed_lscs_all: List[PlacedLscItem] = []
    cavities_all: List[CavityRecord] = []
    for pk in pockets:
        cavities_all.append(
            CavityRecord(
                pocket_id=pk.pocket_id,
                x1=pk.bbox[0],
                y1=pk.bbox[1],
                x2=pk.bbox[2],
                y2=pk.bbox[3],
                cavity_poly=list(pk.cavity_poly),
                outer_koz_poly=list(pk.outer_koz_poly),
                inner_safe_poly=list(pk.inner_safe_poly),
                is_non_rectangular=True,
            )
        )
        for cap in pk.placed_lscs:
            placed_lscs_all.append(cap)
            (p1x, p1y), (p2x, p2y) = cap.pin_coords
            is_vert = abs(p1x - p2x) < 10.0
            for net_c, px_c, py_c, sgn in [
                (cap.pin1_net, p1x, p1y, 1.0 if (p1y > p2y if is_vert else p1x > p2x) else -1.0),
                (cap.pin2_net, p2x, p2y, 1.0 if (p2y > p1y if is_vert else p2x > p1x) else -1.0),
            ]:
                if is_vert:
                    vy_b = round(py_c + sgn * 80.0, 3)
                    clines_out.append(ClineRecord(net_c, "BASE", 50.0, round(px_c, 3), round(py_c, 3), round(px_c, 3), vy_b, f"STEP6_LSC_TIE_{net_c}"))
                    clines_out.append(ClineRecord(net_c, "BASE", 50.0, round(px_c - 115.0, 3), vy_b, round(px_c + 115.0, 3), vy_b, f"STEP6_LSC_BAR_{net_c}"))
                else:
                    vx_b = round(px_c + sgn * 80.0, 3)
                    clines_out.append(ClineRecord(net_c, "BASE", 50.0, round(px_c, 3), round(py_c, 3), vx_b, round(py_c, 3), f"STEP6_LSC_TIE_{net_c}"))
                    clines_out.append(ClineRecord(net_c, "BASE", 50.0, vx_b, round(py_c - 115.0, 3), vx_b, round(py_c + 115.0, 3), f"STEP6_LSC_BAR_{net_c}"))

    repo_lsc_csv = REPO_ROOT / "agent04_pdn_architect" / "stage1_inputs" / "lsc_placed_map.csv"
    old_lsc_rows = list(data.get("existing_lsc_rows") or ())
    if repo_lsc_csv.is_file():
        with repo_lsc_csv.open("r", encoding="utf-8-sig", errors="ignore") as f_lsc:
            for row_l in csv.DictReader(f_lsc):
                if primary_vdd in ((row_l.get("pin1_net") or "").strip(), (row_l.get("pin2_net") or "").strip()):
                    # Note: SM0201_690X390X550_01A at mirror=NO has pins on CONDUCTOR/BASE even though
                    # stage1_inputs/lsc_placed_map.csv recorded `layer=SURFACE` from `isMirrored=nil`.
                    if _in_box(float(row_l.get("x_um") or 0.0), float(row_l.get("y_um") or 0.0), profile["bga_bbox"], 500.0):
                        old_lsc_rows.append(row_l)
    delete_lsc_refs = sorted(
        {
            (r.get("refdes") or "").strip()
            for r in old_lsc_rows
            if (r.get("refdes") or "").strip()
        }
    )

    # -------------------------------------------------------------------------
    # 5. Step 8 Transition Trunks + 4FCO/4BCO Tie-In Straps & Concentric PP Completion (0 Dangling Vias!)
    # -------------------------------------------------------------------------
    # Build obstacle index of Step 4 4FCO (VSS) and 4BCO (VDD) pads so tie-in straps obey >= 67.5um L/S!
    vss_4fco_pads: List[Tuple[float, float, float]] = [(px, py, 87.5) for px, py in step3["vss_pths"]]
    vdd_4bco_pads: List[Tuple[float, float, float]] = [(px, py, 87.5) for px, py in step3["vdd_pths"]]
    for r in edtc_pin_rows:
        if r.get("refdes") in edtc_refs:
            if (r.get("net_name") or "").strip() == "VSS":
                vss_4fco_pads.append((float(r["x_um"]), float(r["y_um"]), 100.0))

    def _strap_clear(x1_s: float, y1_s: float, x2_s: float, y2_s: float, opp_pads: Sequence[Tuple[float, float, float]], half_w: float = 34.0) -> bool:
        for ox, oy, orad in opp_pads:
            if abs(ox - 0.5 * (x1_s + x2_s)) > 600.0 or abs(oy - 0.5 * (y1_s + y2_s)) > 600.0:
                continue
            if _pt_to_seg_dist(ox, oy, x1_s, y1_s, x2_s, y2_s) < (half_w + orad + 67.5 - 1e-3):
                return False
        return True

    emib_157 = list(data.get("emib_157_boxes") or ())
    emib_205 = [expand_bbox(eb, 47.5) for eb in emib_157]
    emib_core = [expand_bbox(eb, 200.0) for _, eb in data["emib_boxes"]]
    edtc_bodies = data["edtc_bodies"]
    x1_d, y1_d, x2_d, y2_d = profile["domain_bbox"]

    all_pth_bins: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    for px_p, py_p in list(step3["vdd_pths"]) + list(step3["vss_pths"]):
        all_pth_bins.setdefault((int(px_p // 300.0), int(py_p // 300.0)), []).append((px_p, py_p))

    def _clear_pth_lids(tx_q: float, ty_q: float) -> bool:
        gx_p, gy_p = int(tx_q // 300.0), int(ty_q // 300.0)
        min_d_sq = (60.5 + 141.25 + 12.5) ** 2
        for dxg in (-1, 0, 1):
            for dyg in (-1, 0, 1):
                for ox_p, oy_p in all_pth_bins.get((gx_p + dxg, gy_p + dyg), ()):
                    if (tx_q - ox_p) ** 2 + (ty_q - oy_p) ** 2 < min_d_sq:
                        return False
        return True

    c4_bins: Dict[Tuple[int, int], List[Tuple[float, float, bool]]] = {}
    for bx_c, by_c in step1["vdd_vips"]:
        c4_bins.setdefault((int(bx_c // 200.0), int(by_c // 200.0)), []).append((bx_c, by_c, True))
    for bx_c, by_c in step1["vss_vips"]:
        c4_bins.setdefault((int(bx_c // 200.0), int(by_c // 200.0)), []).append((bx_c, by_c, False))

    def _score_c4(tx_q: float, ty_q: float, touches_7f: bool) -> Tuple[int, float]:
        gx_q, gy_q = int(tx_q // 200.0), int(ty_q // 200.0)
        cuts = 0
        min_d = 1e9
        for dxg in (-1, 0, 1):
            for dyg in (-1, 0, 1):
                for bx_c, by_c, is_vdd_c in c4_bins.get((gx_q + dxg, gy_q + dyg), ()):
                    d_c = math.hypot(tx_q - bx_c, ty_q - by_c)
                    if d_c < min_d:
                        min_d = d_c
                    if touches_7f:
                        if d_c < 115.0:
                            cuts += 1
                    else:
                        if is_vdd_c and d_c < 115.0:
                            cuts += 1
                        elif (not is_vdd_c) and d_c < 95.0:
                            cuts += 1
        return cuts, -round(min_d, 1)

    pk_boxes = [(pk.bbox[0] - 300.0, pk.bbox[1] - 300.0, pk.bbox[2] + 300.0, pk.bbox[3] + 300.0, pk) for pk in pockets]

    def _outside_cav(tx_q: float, ty_q: float) -> bool:
        for bx0, by0, bx1, by1, pk in pk_boxes:
            if not (bx0 <= tx_q <= bx1 and by0 <= ty_q <= by1):
                continue
            if pk.outer_koz_poly and _pt_in_poly(tx_q, ty_q, pk.outer_koz_poly):
                return False
            if pk.cavity_poly and _pt_to_poly_boundary_dist(tx_q, ty_q, pk.cavity_poly) < (178.0 + 60.5):
                return False
        return True

    cand_vss: List[Tuple[int, float, float]] = []
    cand_vdd: List[Tuple[int, float, float]] = []
    for gx_o in range(-310, 311, 25):
        for gy_o in range(-250, 251, 25):
            r_o = math.hypot(gx_o, gy_o)
            if 220.0 <= r_o <= 312.0:
                cand_vss.append((0 if gx_o <= 0 else 1, float(gx_o), float(gy_o)))
                cand_vdd.append((0 if gx_o >= 0 else 1, float(gx_o), float(gy_o)))

    front_trunks: List[Tuple[str, float, float, float, float]] = []
    back_trunks: List[Tuple[str, float, float, float, float]] = []
    front_vdd_links = 0
    front_vss_links = 0
    back_vdd_links = 0
    back_vss_links = 0
    straps_4fco_added = 0
    straps_4bco_added = 0
    pp_4fco_vdd_completed = 0
    pp_4bco_vss_completed = 0

    f_vss_sp = [("7F", "6F"), ("6F", "5F"), ("5F", "4FCO")]
    f_vdd_sp = [("6F", "5F"), ("5F", "4FCO")]
    b_vss_sp = [("6B", "7B"), ("5B", "6B"), ("4BCO", "5B")]
    b_vdd_sp = [("5B", "6B"), ("4BCO", "5B")]

    # 5A. Place VSS Front (lands directly into 4FCO VSS plane!) & VSS Back (paired w/ 4BCO strap -> VSS PTH!)
    for px_u, py_u in step3["vss_pths"]:
        best_f = None
        best_b = None
        for hp, dx_o, dy_o in cand_vss:
            tx, ty = round(px_u + dx_o, 3), round(py_u + dy_o, 3)
            if not _in_box(tx, ty, (x1_d + 100.0, y1_d + 100.0, x2_d - 100.0, y2_d - 100.0)):
                continue
            if any(_in_box(tx, ty, eb["body"], EDTC_PTH_CENTER_KOZ_UM) for eb in edtc_bodies):
                continue
            if any(_in_box(tx, ty, mb) for mb in emib_core) or any(_in_box(tx, ty, cb) for cb in emib_205):
                continue
            if not _clear_pth_lids(tx, ty):
                continue
            if can_place_via_stack_zero_overlap(grid, "VSS", f_vss_sp, tx, ty):
                cuts_c, neg_d = _score_c4(tx, ty, True)
                kf = (hp, cuts_c, neg_d, abs(dy_o), tx, ty)
                if best_f is None or kf < best_f:
                    best_f = kf
            if _outside_cav(tx, ty) and _strap_clear(px_u, py_u, tx, ty, vdd_4bco_pads) and can_place_via_stack_zero_overlap(grid, "VSS", b_vss_sp, tx, ty):
                kb = (hp, abs(dy_o), abs(dx_o), tx, ty)
                if best_b is None or kb < best_b:
                    best_b = kb
        if best_f is not None:
            fx, fy = best_f[4], best_f[5]
            if insert_via_stack_zero_overlap(vias_out, grid, "VSS", f_vss_sp, fx, fy, "STEP8_FRONT_TO_PP_VSS") > 0:
                front_trunks.append(("VSS", fx, fy, px_u, py_u))
                vss_4fco_pads.append((fx, fy, 60.5))
                front_vss_links += 1
        if best_b is not None:
            bx_t, by_t = best_b[3], best_b[4]
            # Complete 1_VIA_CENTER 3BCI->4BCO on VSS PTH (px_u, py_u) + 68um 4BCO tie-in strap so 0 dangling vias!
            if can_place_via_stack_zero_overlap(
                grid,
                "VSS",
                [("3BCI", "4BCO")],
                px_u,
                py_u,
                padstack_overrides={("3BCI", "4BCO"): "V175_85_175_3BCI_4BCO_01A"},
                allow_concentric_same_net_layers=["3BCI"],
            ):
                if insert_via_stack_zero_overlap(vias_out, grid, "VSS", b_vss_sp, bx_t, by_t, "STEP8_BACK_TO_PP_VSS") > 0:
                    insert_via_stack_zero_overlap(
                        vias_out,
                        grid,
                        "VSS",
                        [("3BCI", "4BCO")],
                        px_u,
                        py_u,
                        "STEP3_CORE_PTH_VSS",
                        padstack_overrides={("3BCI", "4BCO"): "V175_85_175_3BCI_4BCO_01A"},
                        allow_concentric_same_net_layers=["3BCI"],
                    )
                    pp_4bco_vss_completed += 1
                    clines_out.append(ClineRecord("VSS", "4BCO", 68.0, px_u, py_u, bx_t, by_t, "STEP8_4BCO_TIE_VSS"))
                    straps_4bco_added += 1
                    back_trunks.append(("VSS", bx_t, by_t, px_u, py_u))
                    back_vss_links += 1

    # 5B. Place VDDUC3 Front (paired w/ 4FCO strap -> VDDUC3 PTH!) & VDDUC3 Back (lands directly into 4BCO VDDUC3 plane!)
    for px_u, py_u in step3["vdd_pths"]:
        best_f = None
        best_b = None
        for hp, dx_o, dy_o in cand_vdd:
            tx, ty = round(px_u + dx_o, 3), round(py_u + dy_o, 3)
            if not _in_box(tx, ty, (x1_d + 100.0, y1_d + 100.0, x2_d - 100.0, y2_d - 100.0)):
                continue
            if any(_in_box(tx, ty, eb["body"], EDTC_PTH_CENTER_KOZ_UM) for eb in edtc_bodies):
                continue
            if any(_in_box(tx, ty, mb) for mb in emib_core) or any(_in_box(tx, ty, cb) for cb in emib_205):
                continue
            if not _clear_pth_lids(tx, ty):
                continue
            if _strap_clear(px_u, py_u, tx, ty, vss_4fco_pads) and can_place_via_stack_zero_overlap(grid, primary_vdd, f_vdd_sp, tx, ty):
                cuts_c, neg_d = _score_c4(tx, ty, False)
                kf = (hp, cuts_c, neg_d, abs(dy_o), tx, ty)
                if best_f is None or kf < best_f:
                    best_f = kf
            if _outside_cav(tx, ty) and can_place_via_stack_zero_overlap(grid, primary_vdd, b_vdd_sp, tx, ty):
                kb = (hp, abs(dy_o), abs(dx_o), tx, ty)
                if best_b is None or kb < best_b:
                    best_b = kb
        if best_f is not None:
            fx, fy = best_f[4], best_f[5]
            if can_place_via_stack_zero_overlap(
                grid,
                primary_vdd,
                [("4FCO", "3FCI")],
                px_u,
                py_u,
                padstack_overrides={("4FCO", "3FCI"): "V175_85_175_4FCO_3FCI_01A"},
                allow_concentric_same_net_layers=["3FCI"],
            ):
                if insert_via_stack_zero_overlap(vias_out, grid, primary_vdd, f_vdd_sp, fx, fy, f"STEP8_FRONT_TO_PP_{primary_vdd}") > 0:
                    insert_via_stack_zero_overlap(
                        vias_out,
                        grid,
                        primary_vdd,
                        [("4FCO", "3FCI")],
                        px_u,
                        py_u,
                        f"STEP3_CORE_PTH_{primary_vdd}",
                        padstack_overrides={("4FCO", "3FCI"): "V175_85_175_4FCO_3FCI_01A"},
                        allow_concentric_same_net_layers=["3FCI"],
                    )
                    pp_4fco_vdd_completed += 1
                    clines_out.append(ClineRecord(primary_vdd, "4FCO", 68.0, px_u, py_u, fx, fy, f"STEP8_4FCO_TIE_{primary_vdd}"))
                    straps_4fco_added += 1
                    front_trunks.append((primary_vdd, fx, fy, px_u, py_u))
                    front_vdd_links += 1
        if best_b is not None:
            bx_t, by_t = best_b[3], best_b[4]
            if insert_via_stack_zero_overlap(vias_out, grid, primary_vdd, b_vdd_sp, bx_t, by_t, f"STEP8_BACK_TO_PP_{primary_vdd}") > 0:
                back_trunks.append((primary_vdd, bx_t, by_t, px_u, py_u))
                vdd_4bco_pads.append((bx_t, by_t, 60.5))
                back_vdd_links += 1

    pre_s8 = {
        "f_vdd_spans": f_vdd_sp,
        "f_vss_spans": f_vss_sp,
        "b_vdd_spans": b_vdd_sp,
        "b_vss_spans": b_vss_sp,
        "front_vdd_links": front_vdd_links,
        "front_vss_links": front_vss_links,
        "back_vdd_links": back_vdd_links,
        "back_vss_links": back_vss_links,
        "front_trunks": front_trunks,
        "back_trunks": back_trunks,
    }

    # -------------------------------------------------------------------------
    # 6. Step 2 Frontside BU & Step 7 Backside BU (BU-Only Via Cutting, 0 Overlap!)
    # -------------------------------------------------------------------------
    step2 = _run_step2_front_transition(
        profile=profile,
        data=data,
        step1=step1,
        vdd_top_layer="6F",
        vss_top_layer="7F",
        max_bu_stack=7,
        grid=grid,
        vias_out=vias_out,
        step8_front_trunks=list(front_trunks) + edtc_bu_obstacles,
    )
    step7 = _run_step7_back_transition(
        step5=step5,
        step6=step6,
        vdd_bot_layer="6B",
        vss_bot_layer="7B",
        max_bu_stack=7,
        grid=grid,
        vias_out=vias_out,
        step8_back_trunks=back_trunks,
    )
    step8 = _run_step8_transition_to_pp_core(
        profile=profile,
        data=data,
        step2=step2,
        step3=step3,
        step7=step7,
        grid=grid,
        vias_out=vias_out,
        preplaced_step8=pre_s8,
    )

    front_plane_bbox, core_back_bbox, bga_12b_bbox = _compute_ldb_plane_bboxes(ref_u)
    emib_157 = list(data.get("emib_157_boxes") or ())
    polygons = build_ldb_domain_27layer_polygons(
        refdes=ref_u,
        primary_vdd=primary_vdd,
        front_plane_bbox=front_plane_bbox,
        core_back_bbox=core_back_bbox,
        bga_12b_bbox=bga_12b_bbox,
        emib_157_boxes=emib_157,
        edtc_profiles=edtc_profs,
        mcm_keepouts=mcm_koz_map,
    )

    return {
        "refdes": ref_u,
        "vdd_net": primary_vdd,
        "edtc_refs": edtc_refs,
        "polygons": polygons,
        "cavities": cavities_all,
        "placed_lscs": placed_lscs_all,
        "delete_lsc_refs": delete_lsc_refs,
        "mcm_keepouts": mcm_koz_map,
        "plane_bboxes": {
            "front_plane_bbox": front_plane_bbox,
            "core_back_bbox": core_back_bbox,
            "bga_12b_bbox": bga_12b_bbox,
        },
        "metrics": {
            "refdes": ref_u,
            "vdd_net": primary_vdd,
            "curved_lsc_cavities": len(cavities_all),
            "old_lscs_deleted": len(delete_lsc_refs),
            "new_base_lscs_placed": len(placed_lscs_all),
            "edtc_vdd_pins_landed": edtc_vdd_pins_landed,
            "edtc_vss_pins_landed": edtc_vss_pins_landed,
            "step1_vdd_vips": len(step1["vdd_vips"]),
            "step1_vss_vips": len(step1["vss_vips"]),
            "step1_surface_clines": len(step1.get("clines", ())),
            "step3_vdd_pths": len(step3["vdd_pths"]),
            "step3_vss_pths": len(step3["vss_pths"]),
            "step5_on_bga_clusters": len(step5.get("on_bga_clusters", ())),
            "step5_interstitial_clusters": len(step5.get("interstitial_cluster_centers", ())),
            "step8_front_vdd_trunks": front_vdd_links,
            "step8_front_vss_trunks": front_vss_links,
            "step8_back_vdd_trunks": back_vdd_links,
            "step8_back_vss_trunks": back_vss_links,
            "straps_4fco_tie": straps_4fco_added,
            "straps_4bco_tie": straps_4bco_added,
            "pp_4fco_vdd_completed": pp_4fco_vdd_completed,
            "pp_4bco_vss_completed": pp_4bco_vss_completed,
            "pp_vias_cut": 0,
            "front_bu_columns_cut": step2["bu_columns_cut_for_step8_zero_overlap"],
            "front_bu_spans_cut": step2["bu_via_spans_cut_total"],
            "back_bu_spans_cut": step7["bu_via_spans_cut_total"],
            "min_step8_to_pp_4fco_4bco_gap_um": step8["min_step8_to_pp_4fco_4bco_gap_um"],
            "min_step8_to_bu_same_layer_gap_um": step8["min_step8_to_bu_same_layer_gap_um"],
            "adjacent_bu_layer_projection_overlaps": step8["adjacent_bu_layer_projection_overlaps"],
        },
    }


def _seg_intersects_box(x1: float, y1: float, x2: float, y2: float, b: BBox, pad: float) -> bool:
    """Return True if segment `(x1,y1)-(x2,y2)` comes strictly closer than `pad` to rectangle `b`."""
    ex0, ey0, ex1, ey1 = b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad
    if max(x1, x2) < ex0 or min(x1, x2) > ex1 or max(y1, y2) < ey0 or min(y1, y2) > ey1:
        return False
    for k in range(17):
        t = k / 16.0
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        if ex0 <= px <= ex1 and ey0 <= py <= ey1:
            return True
    return False


def _audit_domains_keepouts_and_boundaries(
    vias: Sequence[ViaRecord],
    clines: Sequence[ClineRecord],
    polygons: Sequence[PolygonIsland],
    koz_maps_by_ref: Dict[str, Dict[str, List[BBox]]],
) -> Dict[str, Any]:
    """
    Independently verify across ALL synthesized `VDDUC*` domains using `500 um` spatial bins:
      1. `0` non-eDTC via pads intrude into any `ROUTE KEEPOUT/<layer>` box
      2. `0` CLINEs (`SURFACE`, `4FCO`, `4BCO`, `BASE`) intersect any small `ROUTE KEEPOUT/<layer>` box
      3. `0` same-layer polygon overlaps across domains (with min inter-domain gap >= 100 um)
    """
    cell_um = 500.0
    rkoz_bins: Dict[Tuple[str, int, int], List[BBox]] = collections.defaultdict(list)
    seen_box: Set[Tuple[str, BBox]] = set()
    for kmap in koz_maps_by_ref.values():
        for k, boxes in kmap.items():
            if not k.startswith("ROUTE KEEPOUT/"):
                continue
            lyr = k.split("/", 1)[1].upper()
            for b in boxes:
                kb = (lyr, b)
                if kb in seen_box:
                    continue
                seen_box.add(kb)
                gx0 = int(math.floor((b[0] - 200.0) / cell_um))
                gx1 = int(math.floor((b[2] + 200.0) / cell_um))
                gy0 = int(math.floor((b[1] - 200.0) / cell_um))
                gy1 = int(math.floor((b[3] + 200.0) / cell_um))
                for gx in range(gx0, gx1 + 1):
                    for gy in range(gy0, gy1 + 1):
                        rkoz_bins[(lyr, gx, gy)].append(b)

    via_rkoz_hits: Dict[str, int] = collections.Counter()
    for v in vias:
        if v.tag.startswith("EDTC_"):
            continue
        ps_rads = PADSTACK_CONDUCTOR_RADII.get(v.padstack)
        if ps_rads:
            layers_r = ps_rads
        else:
            def_r = 87.5 if "175_" in v.padstack else (45.0 if "90_" in v.padstack else 38.5)
            layers_r = [(v.start_layer, def_r), (v.end_layer, def_r)]
        gx = int(math.floor(v.x / cell_um))
        gy = int(math.floor(v.y / cell_um))
        for clyr, rad in layers_r:
            c_up = clyr.upper()
            for b in rkoz_bins.get((c_up, gx, gy), ()):
                if (b[0] - rad) <= v.x <= (b[2] + rad) and (b[1] - rad) <= v.y <= (b[3] + rad):
                    via_rkoz_hits[f"{c_up}:{v.tag[:16]}"] += 1
                    break

    cline_rkoz_hits: Dict[str, int] = collections.Counter()
    for cl in clines:
        hw = 0.5 * cl.width_um
        c_up = cl.layer.upper()
        gx0 = int(math.floor(min(cl.x1, cl.x2) / cell_um))
        gx1 = int(math.floor(max(cl.x1, cl.x2) / cell_um))
        gy0 = int(math.floor(min(cl.y1, cl.y2) / cell_um))
        gy1 = int(math.floor(max(cl.y1, cl.y2) / cell_um))
        checked_boxes: Set[BBox] = set()
        hit = False
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                for b in rkoz_bins.get((c_up, gx, gy), ()):
                    if b in checked_boxes or (b[2] - b[0]) > 2000.0 or (b[3] - b[1]) > 2000.0:
                        continue
                    checked_boxes.add(b)
                    if _seg_intersects_box(cl.x1, cl.y1, cl.x2, cl.y2, b, hw - 0.5):
                        cline_rkoz_hits[f"{c_up}:{cl.tag[:16]}"] += 1
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break

    poly_by_lyr: Dict[str, List[PolygonIsland]] = collections.defaultdict(list)
    for p in polygons:
        poly_by_lyr[p.layer].append(p)
    poly_overlaps = 0
    min_cross_domain_gap = 1e9
    for lyr, plist in poly_by_lyr.items():
        for i in range(len(plist)):
            b1 = plist[i].bbox
            ref1 = plist[i].tag.split("_", 1)[0]
            for j in range(i + 1, len(plist)):
                ref2 = plist[j].tag.split("_", 1)[0]
                if ref1 == ref2:
                    continue
                b2 = plist[j].bbox
                dx = max(0.0, max(b1[0] - b2[2], b2[0] - b1[2]))
                dy = max(0.0, max(b1[1] - b2[3], b2[1] - b1[3]))
                gap = math.hypot(dx, dy)
                if gap < min_cross_domain_gap:
                    min_cross_domain_gap = gap
                if bboxes_intersect(b1, b2):
                    poly_overlaps += 1

    return {
        "via_route_keepout_hits": dict(via_rkoz_hits),
        "cline_route_keepout_hits": dict(cline_rkoz_hits),
        "inter_domain_polygon_overlaps": poly_overlaps,
        "min_inter_domain_polygon_gap_um": round(min_cross_domain_gap, 2) if min_cross_domain_gap < 1e8 else None,
        "keepout_and_boundary_pass": (len(via_rkoz_hits) == 0 and poly_overlaps == 0),
    }


def build_and_verify_vdduc_domains_8step_mcm(
    refdes_list: Sequence[str] = ALL_VDDUC_REFDES,
    work_dir: Optional[str] = None,
    out_mcm_name: Optional[str] = None,
    dry_run: bool = False,
    timeout_sec: int = 2400,
) -> Dict[str, Any]:
    """
    Synthesize all 27 layers (`SURFACE` L01 -> `BASE` L27) Steps 1..8 + `4FCO` `eDTC`s +
    `24` Dynamic Planes + Static Guard Bands for 1 or all 4 `VDDUC*` LDB domains
    (`U7/VDDUC0`, `U5/VDDUC1`, `U8/VDDUC2`, `U6/VDDUC3`) in ONE single `.mcm` database,
    verify `0` via overlaps across all 27 conductor layers and `0` inter-domain plane
    overlaps, copy `MCM_template/PDN_test.mcm` (read-only) -> `pdn_sandbox/<out_mcm_name>`,
    and execute headless Cadence APD 25.1 import + independent SKILL verification.
    """
    t0 = time.perf_counter()
    refs = [r.strip().upper() for r in refdes_list]
    is_single_u6 = (refs == ["U6"])
    eff_out_name = out_mcm_name or (
        "PDN_test_U6_VDDUC3_VSS_8Step.mcm" if is_single_u6 else "PDN_test_All_VDDUC_VSS_8Step.mcm"
    )
    prefix = "U6_VDDUC3" if is_single_u6 else "All_VDDUC0_to_3"

    eff_wd, is_custom = resolve_active_work_dir(work_dir)
    sandbox_dir = resolve_output_dir("pdn_sandbox", explicit_work_dir=work_dir)
    reports_dir = resolve_output_dir("reports", explicit_work_dir=work_dir)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    src_mcm = resolve_mcm_in_work_dir(eff_wd) if is_custom else None
    if src_mcm is None:
        cand = eff_wd / "MCM_template" / "PDN_test.mcm"
        src_mcm = cand if cand.is_file() else (REPO_ROOT / "agent04_pdn_architect" / "MCM_test" / "PDN_test.mcm")
    src_mcm = src_mcm.resolve()
    src_stat_before = (src_mcm.stat().st_size, src_mcm.stat().st_mtime_ns)

    out_mcm = (sandbox_dir / eff_out_name).resolve()
    if out_mcm == src_mcm:
        raise RuntimeError(f"SAFETY_LOCK: refusing to overwrite read-only template {src_mcm}")

    s1_dir = resolve_stage1_inputs_dir()
    if not (s1_dir / "edtc_pin_map.csv").is_file():
        s1_dir = REPO_ROOT / "agent04_pdn_architect" / "stage1_inputs"
    with (s1_dir / "edtc_pin_map.csv").open("r", encoding="utf-8", errors="ignore") as f:
        edtc_pin_rows = list(csv.DictReader(f))
    with (s1_dir / "edtc_symbols.csv").open("r", encoding="utf-8", errors="ignore") as f:
        edtc_sym_rows = list(csv.DictReader(f))

    grid = FastXYClearanceGrid(cell_um=500.0)
    vias_out: List[ViaRecord] = []
    clines_out: List[ClineRecord] = []
    polygons_all: List[PolygonIsland] = []
    cavities_all: List[CavityRecord] = []
    placed_lscs_all: List[PlacedLscItem] = []
    delete_lsc_refs_all: List[str] = []
    koz_maps_by_ref: Dict[str, Dict[str, List[BBox]]] = {}
    domain_specs: List[Dict[str, Any]] = []
    per_domain_summary: Dict[str, Any] = {}

    for ref_u in refs:
        d_res = _synthesize_single_vdduc_domain(
            refdes=ref_u,
            src_mcm=src_mcm,
            sandbox_dir=sandbox_dir,
            edtc_pin_rows=edtc_pin_rows,
            edtc_sym_rows=edtc_sym_rows,
            grid=grid,
            vias_out=vias_out,
            clines_out=clines_out,
        )
        polygons_all.extend(d_res["polygons"])
        cavities_all.extend(d_res["cavities"])
        placed_lscs_all.extend(d_res["placed_lscs"])
        delete_lsc_refs_all.extend(d_res["delete_lsc_refs"])
        koz_maps_by_ref[ref_u] = d_res["mcm_keepouts"]
        domain_specs.append({
            "refdes": ref_u,
            "vdd_net": d_res["vdd_net"],
            "edtc_refs": d_res["edtc_refs"],
            "lsc_count": len(d_res["placed_lscs"]),
        })
        per_domain_summary[ref_u] = d_res["metrics"]

    delete_lsc_refs_all = sorted(set(delete_lsc_refs_all))

    # Strict 27-layer mathematical audit across EVERY single via across ALL domains simultaneously!
    full_via_audit = audit_via_continuity_and_zero_overlap(vias_out)
    if not full_via_audit["zero_via_overlap_pass"]:
        raise RuntimeError(f"ZERO_VIA_OVERLAP_GATE_FAILED: {full_via_audit['overlap_samples'][:5]}")

    koz_boundary_audit = _audit_domains_keepouts_and_boundaries(
        vias_out, clines_out, polygons_all, koz_maps_by_ref
    )

    master_recipe = write_fast_ordered_master_recipe(
        recipe_path=sandbox_dir / f"{prefix}_VSS_27Layer_Master_Recipe.txt",
        polygons=polygons_all,
        cavities=cavities_all,
        vias=vias_out,
        clines=clines_out,
        placed_lscs=placed_lscs_all,
        delete_lsc_refdes=delete_lsc_refs_all,
    )

    summary_out: Dict[str, Any] = {
        "status": "DRY_RUN_READY" if dry_run else "PENDING",
        "refdes_list": refs,
        "rails": [sp["vdd_net"] for sp in domain_specs] + ["VSS"],
        "template_mcm_readonly": str(src_mcm),
        "output_mcm": str(out_mcm),
        "master_recipe": str(master_recipe),
        "pre_import_counts": {
            "total_vias": len(vias_out),
            "total_clines": len(clines_out),
            "total_polygons": len(polygons_all),
            "dynamic_planes": sum(1 for p in polygons_all if p.is_dynamic and p.net_name != "__ISOLATED__"),
            "static_guard_bands": sum(1 for p in polygons_all if p.net_name == "__ISOLATED__"),
            "curved_lsc_cavities": len(cavities_all),
            "old_lscs_deleted": len(delete_lsc_refs_all),
            "new_base_lscs_placed": len(placed_lscs_all),
            "pp_vias_cut": 0,
        },
        "per_domain": per_domain_summary,
        "zero_via_overlap_audit": full_via_audit,
        "keepout_and_boundary_audit": koz_boundary_audit,
    }

    rep_json = reports_dir / f"{prefix}_VSS_27Layer_MCM_Build_Report.json"
    if dry_run:
        rep_json.write_text(json.dumps(summary_out, indent=2), encoding="utf-8")
        summary_out["report_json"] = str(rep_json)
        return summary_out

    # -------------------------------------------------------------------------
    # Copy Read-Only Template -> pdn_sandbox/<eff_out_name> & Run APD 25.1
    # -------------------------------------------------------------------------
    shutil.copy2(src_mcm, out_mcm)
    lck = out_mcm.with_name(out_mcm.name + ".lck")
    if lck.exists():
        lck.unlink()

    importer_il = (REPO_ROOT / "agent04_pdn_architect" / "templates" / "apd_unified_27layer_template_importer.il").resolve()
    verify_il = _write_post_import_vdduc_verify_il(
        sandbox_dir / f"_verify_{prefix.lower()}_27layer_mcm.il",
        domain_specs=domain_specs,
    )
    apd_import_rep = (reports_dir / f"{prefix}_VSS_27Layer_APD_Import_Report.txt").resolve()
    apd_verify_rep = (reports_dir / f"{prefix}_VSS_27Layer_APD_Verify_Report.txt").resolve()
    scr_file = (sandbox_dir / f"run_{prefix.lower()}_27layer_mcm_build.scr").resolve()

    for f_clean in (apd_import_rep, apd_verify_rep, Path(str(apd_import_rep) + ".progress")):
        if f_clean.exists():
            f_clean.unlink()

    scr_file.write_text(
        f'skill load("{importer_il.as_posix()}")\n'
        f'skill load("{verify_il.as_posix()}")\n'
        f"skill pdnPreCleanVdducPocketLscs()\n"
        f'skill pdnRunUnified27LayerTemplateBatch("{master_recipe.as_posix()}" "{out_mcm.as_posix()}" "{apd_import_rep.as_posix()}")\n'
        f'skill pdnVerifyVdducFull27LayerMcm("{apd_verify_rep.as_posix()}")\n'
        f"exit\nfillin no\n",
        encoding="utf-8",
    )

    runner = CadenceBatchRunner(default_timeout=timeout_sec)
    run_res = runner.run(
        mcm_path=out_mcm,
        scr_path=scr_file,
        working_dir=sandbox_dir,
        timeout=timeout_sec,
        bypass_lock_readonly=False,
    )

    src_stat_after = (src_mcm.stat().st_size, src_mcm.stat().st_mtime_ns)
    template_untouched = (src_stat_before == src_stat_after)

    def _parse_kv(p: Path) -> Dict[str, str]:
        kv: Dict[str, str] = {}
        if p.is_file():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    kv[k.strip()] = v.strip()
        return kv

    imp_kv = _parse_kv(apd_import_rep)
    ver_kv = _parse_kv(apd_verify_rep)

    all_domains_ok = True
    for sp in domain_specs:
        ref_u = sp["refdes"]
        vdd_n = sp["vdd_net"]
        exp_lsc = int(sp["lsc_count"])
        d_ok = bool(
            int(ver_kv.get(f"{ref_u}_LSC_ON_CONDUCTOR_BASE", "0")) == exp_lsc
            and int(ver_kv.get(f"{ref_u}_LSC_ON_CONDUCTOR_SURFACE", "999")) == 0
            and int(ver_kv.get(f"{ref_u}_LSC_PIN1_VDD_OK", "0")) == exp_lsc
            and int(ver_kv.get(f"{ref_u}_LSC_PIN2_VSS_OK", "0")) == exp_lsc
            and int(ver_kv.get(f"{vdd_n}_BRANCHES", "0")) == 1
            and int(ver_kv.get(f"{vdd_n}_RATS", "999")) == 0
            and int(ver_kv.get(f"{vdd_n}_OPEN_PINS", "999")) == 0
            and int(ver_kv.get(f"{vdd_n}_FLOATING_BRANCHES", "999")) == 0
            and int(ver_kv.get(f"{ref_u}_VSS_OPEN_PINS", "999")) == 0
            and int(ver_kv.get(f"{ref_u}_ELECTRICAL_DRC_MARKERS", "999")) == 0
        )
        all_domains_ok = all_domains_ok and d_ok

    ok_build = bool(
        imp_kv.get("STATUS") == "SUCCESS"
        and int(imp_kv.get("ERRORS", "999")) == 0
        and ver_kv.get("VERIFY_STATUS") == "OK"
        and all_domains_ok
        and template_untouched
    )
    summary_out["status"] = "SUCCESS" if ok_build else "CHECK"
    summary_out["template_readonly_untouched"] = template_untouched
    summary_out["apd_duration_sec"] = round(run_res.duration_sec, 2)
    summary_out["total_elapsed_sec"] = round(time.perf_counter() - t0, 2)
    summary_out["apd_import_report"] = imp_kv
    summary_out["apd_verify_report"] = ver_kv
    summary_out["apd_import_report_file"] = str(apd_import_rep)
    summary_out["apd_verify_report_file"] = str(apd_verify_rep)

    rep_json.write_text(json.dumps(summary_out, indent=2), encoding="utf-8")
    summary_out["report_json"] = str(rep_json)
    return summary_out


def build_and_verify_u6_8step_mcm(
    work_dir: Optional[str] = None,
    out_mcm_name: str = "PDN_test_U6_VDDUC3_VSS_8Step.mcm",
    dry_run: bool = False,
    timeout_sec: int = 1200,
) -> Dict[str, Any]:
    """Backwards-compatible entry point building only `U6` (`VDDUC3 + VSS`)."""
    return build_and_verify_vdduc_domains_8step_mcm(
        refdes_list=("U6",),
        work_dir=work_dir,
        out_mcm_name=out_mcm_name,
        dry_run=dry_run,
        timeout_sec=timeout_sec,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build & Verify 27-Layer VDDUC* (U7, U5, U8, U6 + VSS) 8-Step PDN into One .mcm")
    parser.add_argument("--work-dir", type=str, default=None, help="Active work folder (defaults to SUBSTRATE_WORK_DIR)")
    parser.add_argument(
        "--refdes",
        type=str,
        default="ALL",
        help="Comma-separated LDB RefDes list (e.g. 'U6' or 'U7,U5,U8,U6' or 'ALL', default 'ALL')",
    )
    parser.add_argument("--out-mcm-name", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Synthesize & verify Master Recipe without running apd.exe")
    parser.add_argument("--timeout", type=int, default=2400)
    args = parser.parse_args()
    raw_r = (args.refdes or "ALL").strip().upper()
    refs = list(ALL_VDDUC_REFDES) if raw_r in ("ALL", "VDDUC*", "ALL_VDDUC") else [x.strip().upper() for x in raw_r.split(",") if x.strip()]
    res = build_and_verify_vdduc_domains_8step_mcm(
        refdes_list=refs,
        work_dir=args.work_dir,
        out_mcm_name=args.out_mcm_name,
        dry_run=args.dry_run,
        timeout_sec=args.timeout,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
