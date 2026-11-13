---
name: full_27layer_apd_implementation
description: End-to-end 27-layer (`SURFACE` L01 to `BASE` L27) PDN Architect Exporter and Cadence APD / Allegro SKILL Master Implementer (`apd_27layer_master_exporter.py` + `full_27layer_apd_implementer_batch.il`). Exports every single via (`166,223` instances across all 26 dielectric spans), `CLINE` trace (`7,169` instances), `0201` LSC symbol (`254` instances), and inner-layer copper plane (`24` shapes + `eDTC` cavity voids) with exact `.mcm` database padstack names, layer spans, and `(x_um, y_um)` locations for direct instantiation in Cadence APD.
---

# Full 27-Layer (`SURFACE` L01 to `BASE` L27) APD Master Implementation Skill

## 1. Overview & User-Selectable Architecture Options

Once you inspect the SVG mockups in `pdn_sandbox/` and choose your preferred options across the 27 layers:
- **`--surface-ratio`**: `"FULL"` (`100%` Full Via on Bump for `U7` `VDDUC0` & `VSS`) or any `"M:N"` ratio (`"4:2"`, `"5:2"`, `"3:1"`)
- **`--surface-dir`**: `"VERTICAL"`, `"HORIZONTAL"`, or `"BOTH"` (`2D Mesh`)
- **Top `BUA` Stack (`L01 -> L09`) + `L09/L10` Transition (`6F -> 5F -> 4FCO`):**
  - `7-Stacked Via` (`V77_49_77_SURFACE_12F_01A` .. `V90_65_90_7F_6F_01A`) with automatic `6-Stack` (`L01 -> L08`) stop within `< 108 µm` of any `L09 -> L11` `2-stack` transition via (`0` via overlap!)
  - `2-Stacked Via` (`V90_65_90_6F_5F_01A` + `V90_65_121_5F_4FCO_01A`) on all `336` `4FCO` `eDTC` pins and all `2,584` Core PTH columns
- **`--pth-density` & `--pth-pattern` (`L11: 4FCO` $\leftrightarrow$ `L18: 4BCO`):**
  - `7.0 PTH/mm²` (or `5, 6, 7, 8`), `"STAGGERED"`, `"ORTHOGONAL_90DEG_VERTICAL"`, or `"ORTHOGONAL_90DEG_HORIZONTAL"`, with `0` PTHs inside `C1373`/`C1374` `eDTC` KOZs
- **Bottom `BUB` & `BASE` (`L18: 4BCO` $\leftrightarrow$ `L27: BASE`):**
  - **BGA Cluster B (`2-Stack Inner Transition`, `4BCO -> 5B -> 6B`):** `4-Via Rotated Diamond` at `(±185, 0) & (0, ±185) µm` (`133.14 µm` center-to-center / `43.14 µm` edge clearance to Cluster A — `0` via overlap!)
  - **BGA Cluster A (`7-Stack`, `6B -> ... -> BOTTOM`):** `"OPTION1_4VIA_SQUARE_2X2"` at `(±110, ±110) µm` (or `OPTION2_5VIA_QUINCUNX` / `OPTION3_6VIA_HEX_RING`)
  - **`0201` LSC Placement & Dual-Bar Vias (`254` LSCs in 8 Empty BGA Pockets):** Outer `3-Via Bar` at `±355 µm` (`7-Stack` `6B -> BOTTOM`) + Inner `3-Via Bar` at `±235 µm` (`2-Stack` `4BCO -> 6B`, `120.0 µm` center pitch / `30.0 µm` edge clearance — `0` via overlap!)

---

## 2. Exported APD Implementation Files (`pdn_sandbox/apd_implementation_out/`)

Running `python agent04_pdn_architect/cad_cli/apd_27layer_master_exporter.py` outputs:
1. **`U7_27Layer_APD_Master_Recipe.txt`** — Single pipe-delimited SKILL recipe (`LSC_SYM|...`, `PLANE|...`, `PLANE_VOID|...`, `VIA|...`, `CLINE|...`) containing all `173,670` objects across all 27 layers.
2. **`U7_27Layer_APD_Vias_All_Layers.csv`** — All `166,223` via instances with `via_id, net_name, padstack_name, start_layer, end_layer, x_um, y_um, drill_um, pad_um, zone_tag`.
3. **`U7_27Layer_APD_Traces_CLINEs.csv`** — All `7,169` `CLINE` traces/straps (`4FCO`, `6B`, `TOP`) with `trace_id, net_name, layer, width_um, x1_um, y1_um, x2_um, y2_um, zone_tag`.
4. **`U7_27Layer_APD_LSC_Symbols.csv`** — All `254` `0201` LSC symbols on `BOTTOM` (`BASE`) with exact `(x_um, y_um, rotation_deg)` and Pin 1 / Pin 2 coordinates.
5. **`U7_27Layer_APD_Planes.csv`** — All `24` inner-layer copper planes (`12F`..`12B`) and `eDTC` cavity voids.
6. **`U7_27Layer_APD_Layer_Manifest.json`** — Complete layer-by-layer padstack breakdown and DRC report.

---

## 3. Executing in Cadence APD / Allegro (Interactive or Headless Batch)

### Interactive SKILL Console inside APD:
```lisp
load("agent04_pdn_architect/scripts/full_27layer_apd_implementer_batch.il")

; Option A: Stream-load the pre-generated Master Recipe directly into the active .mcm
pdnImplementFull27LayerFromMasterRecipe("pdn_sandbox/apd_implementation_out/U7_27Layer_APD_Master_Recipe.txt" t)

; Option B: Run Python Exporter with your chosen options + instantiate in APD in one call
pdnRunFull27LayerArchitectAndImplement("FULL" "VERTICAL" 7.0 "STAGGERED" "OPTION1_4VIA_SQUARE_2X2" 175.0)
```
