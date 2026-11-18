---
name: emib_csb_and_hbm_surface_router
description: >-
  Step 2 Bifurcated HBM Fine-Pitch SURFACE Gang-Bar & EMIB C0 / 10F CSB Escape
  Router for Agent 04 (pdn_architect). Routes East EMIB overlap bumps onto C0
  (VU30_19_60 / VU30_19_39 / VU30_19_35 with strict C0 exclusivity), groups West
  non-EMIB HBM 21 um fine-pitch paired double-rows into 84-90 um horizontal
  SURFACE copper gang-bars split cleanly around OBS_*/NC_*/Signal bumps (>=18.5 um
  clearance) with centerline V77_49_77_SURFACE_12F_01A drop vias, and escapes
  10F CSB (C77_10F_DP_01A) pins within the max 2-stacked-via EMIB Rule #14 limit
  using lateral 8F dogbone step-overs into 6F power strips.
---

# Step 2: `HBM` `SURFACE` Gang-Bar & `EMIB` `C0` / `10F CSB` Escape Router (`emib_csb_and_hbm_surface_router`)

## 1. Core Architectural Capabilities

1. **East `EMIB` Overlap `SURFACE -> C0` Exclusivity (`EMIB Rules #15–#18`):**
   - Drops `HBM4E` (`U13..U24`) bumps over `LAVA_BRIDGE` (`U41..U52`) via `VU30_19_60_SURFACE_C0_01B`, `LDB` (`U5..U8`) shared bumps via `VU30_19_39_SURFACE_C0_01B`, and `LDA` (`U9..U10`) bridge bumps via `VU30_19_35_SURFACE_C0_01B`, with **`0` shapes, clines, or vias on `C0` outside EMIB silicon bridges**.
2. **West Non-EMIB `HBM` Paired Double-Row `SURFACE` Gang-Bars (`x <= U41_x0 - 157.5 µm`):**
   - Pairs JEDEC HBM4E `55 µm` double-rows of `21 µm` (`C21_7_DP_01A`) bumps per rail (`VDDQ`, `VDDC`, `VDDQL`, `VPP`, `VSS`), splits horizontal runs around `OBS_*` / `NC_*` / Signal bumps (`>= 18.5 µm` clearance), emits `SURFACE` copper gang-bars, and places `V77_49_77_SURFACE_12F_01A` centerline drop vias climbing atomically to `12F` (`VDDC`), `11F` (`VSS`), `10F` (`VDDQ`), and `8F`/`6F` (`VDDQL`, `VPP`).
3. **`10F` Isolated `150 µm` Guard Ring & `CSB` Max-`2-Stack` Step-Over (`EMIB Rules #5–#14`):**
   - Preserves the `150.0 µm` isolated copper Guard Ring (`__ISOLATED__`) around EMIB dies on `10F` (`>= 372.0 µm` C4 plane-to-`CSB` clearance), terminates `VSS` `CSB` pins in `1` via onto `9F`, and drops power `CSB` pins in **at most `2` stacked vias (`10F->9F->8F`)**, stepping laterally (`115 µm` `40 µm`-wide dogbone cline on `8F`) where deeper `8F->7F->6F` transition is needed.

## 2. CLI & SKILL Execution
```powershell
python -m agent04_pdn_architect.cad_cli.step1_step2_u9_u13_validator --dry-run
```
* **Python Engine:** [`hbm_surface_and_csb_router.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/hbm_surface_and_csb_router.py)
* **Combined Validator:** [`step1_step2_u9_u13_validator.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/step1_step2_u9_u13_validator.py)
