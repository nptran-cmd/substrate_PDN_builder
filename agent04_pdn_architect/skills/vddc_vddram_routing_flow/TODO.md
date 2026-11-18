# `VDDC*` and `VDDRAM` (`LDA` Die) All-Layer Routing Flow — Execution & Customization TODO List

Use this checklist to review, customize, synthesize, and instantiate the 27-layer (`SURFACE` L01 $\rightarrow$ `BASE` L27) co-resident dual-power-rail PDN architecture for any `LDA` compute die (`U9`: `VDDC0 + VDD_0P8_SRAM_CC0`, `U12`: `VDDC1 + SRAM_CC1`, `U88`: `VDDC2 + SRAM_CC2`, `U10`: `VDDC3 + SRAM_CC3`).

---

## Phase 0: Baseline Review & User Architecture Customization (Pre-Synthesis Gate)
- [ ] **0.1 Select Target `LDA` Die Instance:** Choose `U9` (`VDDC0`/`VDD_0P8_SRAM_CC0`), `U12` (`VDDC1`/`SRAM_CC1`), `U88` (`VDDC2`/`SRAM_CC2`), or `U10` (`VDDC3`/`SRAM_CC3`) + Kelvin `OBS_*`/`SNS_*` sense pairs.
- [ ] **0.2 Confirm or Customize 27-Layer Plane Partitioning (`TEMPLATE.md`):**
  - Default learned baseline: `10F` & `10B` dedicated full-span `SRAM`, `12F` & `8F` dedicated `VDDC`, and co-planar carved West/East `SRAM` islands inside `VDDC` on `6F, 4FCO, 2FCI, 2BCI, 4BCO, 6B, 8B, 12B` (`>= 50 um` BU / `>= 67.5 um` Core/PP/GCP split gap).
  - *(User customization hook: modify layer assignments or corridor bounds in `vddc_vddram_config.json` before synthesis).*
- [ ] **0.3 Confirm Per-Zone Routing Options:**
  - `SURFACE` (`L01`): `VDDC:VSS` ratio (`FULL`, `4:2`, `5:2`, `3:1`) + `HORIZONTAL`/`VERTICAL`/`BOTH` straps (`SRAM` defaults to `100%` 3-stack `SURFACE->12F->11F->10F`).
  - `4FCO <-> 4BCO` Core/PP: `100%` concentric `1-via/PTH` clean mode vs. golden hybrid `1-via + 2-via` `175 um` spider-web mode.
  - `10B -> 12B` Backside BU: High-current `V83_55_83` (`55 um` drill) vs. `V77_49_77`.
  - `BASE` (`L27`): `8-via` octagonal `R=195 um` BGA ring (`SMD8`) vs. `4/5/6-via` BGA options + `0.55 mmT 10uF` (`250 um`) vs. `0.22 mmT 1uF` (`175 um`) LSCs.

---

## Phase 1: Layer 1 (`SURFACE` -> `12F` / `10F` / `C0`) & EMIB Upper-BU (`12F/11F/10F`) Gate
- [ ] **1.1 Route `VDD_0P8_SRAM_CCx` Bumps (`1,007`):** Place `100%` 3-stacked vias (`SURFACE -> 12F -> 11F -> 10F`) through `12F` (`VDDCx`) and `11F` (`VSS`) antipads into the dedicated `10F` `SRAM` collection plane.
- [ ] **1.2 Route `VDDCx` (`10,664`) & `VSS` (`16,797`) Bumps + `C0` Exclusivity (`EMIB Rules #15–#18`):** Apply user-selected `M:N` ratio and pure 1D `HORIZONTAL`/`VERTICAL` strapping (`0` floating bumps, `>= 18.0 um` clearance to all `SRAM`, `VDDC`, `VSS`, and Signal pads); restrict `C0` strictly to `VU30_19_35_SURFACE_C0_01B` inside adjacent EMIB-T bridges (`U25, U29, U32, U28, U39` on `U9`, zero non-EMIB shapes/traces/vias on `C0`).
- [ ] **1.3 Enforce EMIB Cavity & `10F` `SRAM` Funnel / `CSB` / Guard Ring Keepouts (`EMIB Rules #2–#14`):**
  - Void `12F` (`VDDCx`) and `11F` (`VSS`) planes/vias within **`157.5 um`** of any EMIB-T die edge (`75.0 um` cavity + `82.5 um` C4 pad/shape spacing).
  - On `10F` (`VDD_0P8_SRAM_CCx` funnel plane): prohibit `SRAM` plane/traces under EMIB-T dies (`Rule #7`), preserve the **`150.0 um` isolated copper Guard Ring** starting at EMIB die edge (`Rules #6,#22,#23`), void `SRAM` plane/vias within **`200.0 um` of EMIB die edge** (`150 um` Guard Ring + `50 um` space, `Rule #8`) AND within **`372.0 um` of active `CSB` pads (`Rule #5`)**, and cap `CSB` vias (`10F->9F`) at max `2-stack` (`Rule #14`).
- [ ] **1.4 Route Differential Kelvin Sense Pairs (`OBS_*`):** Route matched differential traces (`14–21 um` width) with `VSS` shielding down to `A1` sense BGAs.
- [ ] **1.5 SVG Visual Gate:** Generate and inspect `mockup_LDA_L1_SURFACE_*.svg`.

---

## Phase 2: Shared `4FCO` `eDTC` (`6 × 144`-Pin) & Core `PTH` (`4FCO <-> 4BCO`) Synthesis
- [ ] **2.1 Concentric Dual-Rail `eDTC` Pin Landing:** Place `100%` concentric (`0.0 um` offset) `5F -> 4FCO` vias on all `4` pure `VDDCx` `eDTC`s (`C2215,17,19,20`) AND the `2` shared `VDDCx + SRAMx` `eDTC`s (`C2216`: `48 SRAM + 24 VDDC + 72 VSS`; `C2218`: `24 SRAM + 48 VDDC + 72 VSS`).
- [ ] **2.2 Strict `4FCO..4BCO` `eDTC` KOZ & `eDTC`-to-EMIB Enforcement:** Verify `0` `eDTC`s under any EMIB-T die (`eDTC Rule #14`) and **`eDTC` Cavity Edge to EMIB Cavity Edge `>= 1,000.0 um` (`eDTC Rule #5`)**; exclude `100%` of PTHs, PP vias, traces, and `4BCO -> 5B` vias from `[eDTC body + 300 um cavity + 150 um guard metal + 67.5 um spacing]`; close all `6 × 8 = 48` `eDTC` KOZ plane voids across `4FCO..4BCO`; maintain continuous solid `5B` `VSS` plane underneath.
- [ ] **2.3 Partitioned `VDDCx` & `SRAMx` Core PTH Grid:** Synthesize `VDDCx` PTHs inside main `VDDCx` core islands and `SRAMx` PTHs inside carved West/East `SRAMx` core islands (`>= 270 um` same-net, `>= 432.5 um` diff-net, `>= 67.5 um` island-to-island gap).
- [ ] **2.4 SVG Visual Gate:** Generate and inspect `mockup_LDA_4FCO_4BCO_DualRail_Core.svg`.

---

## Phase 3: 3-Net Spatial Plane Matching & Atomic Via Stack Pruning (`12F..5F` & `5B..12B`)
- [ ] **3.1 Generate Co-Planar Split Shapes & Cutout Voids:** Create outer `VDDCx` planes with expanded `PLANE_VOID` cutouts (`island_bbox + 50.0 / 67.5 um`) and inner `PLANE_ISLAND` shapes for `VDD_0P8_SRAM_CCx`.
- [ ] **3.2 Spatial `(x, y, layer)` Net-Ownership Lookup:** Before terminating any pruned via stack on layer `L`, verify that `(x, y)` lies strictly inside a copper shape owned by **that exact net** (`VDDCx`, `SRAMx`, or `VSS`) — preventing `VDDCx` stacks from accidentally terminating on `10F`/`10B` (`SRAMx`) or inside a carved `SRAMx` sub-island!
- [ ] **3.3 Zero Overlap & Zero Dangling Via Gate:** Assert `0` via overlaps on `9F/10F` and `9B/10B` and `0` dangling via columns across all 3 nets.

---

## Phase 4: Bottom (`BASE` L27) `8-Via` BGA Rings + EMIB Shadow Exclusion + Co-Pocket `LSC_CAVITY` Rule
- [ ] **4.1 Generate `SUBSTRATE GEOMETRY/LSC_CAVITY` & `Code D` (`178 / 203 um`) Keepouts:** Build `R = 500.0 um` (`Code K`) rounded-corner cavities obeying `BGA SRO -> Cavity >= 250.0 um` (`Code G`; `SMD1 >= 254.0 um` `Code H` / `>= 330.2 um` `Code I` for `SMD8` SMO-to-recess), `Min 1016x1016 um` (`Code E`), `Web >= 508.0 um` (`Code J`), `SM web >= 76.0 um + 102..152 um pullback` (`Codes A/B`), and `178.0 um` Ext (`ROUTE KEEPOUT/BASE`) / `203.0 um` Int Signal & Non-SMT Cu KOZ (`Code D`).
- [ ] **4.2 Co-Pocket `VDDCx` + `SRAMx` `0201` LSC Placement on `CONDUCTOR/BASE` with `180°` Cap-to-Cap Alternation, Pin Nets & EMIB Rule #19:**
  - Place `100%` of LSC pads on **`CONDUCTOR/BASE` (bottom layer, `0` on `CONDUCTOR/SURFACE`)** via `mir=nil` first + `pin->startEnd` check (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir=nil`).
  - Instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = VDDCx / VDD_0P8_SRAM_CCx` and `Pin "2" = VSS` via `axlChangeNet`.
  - **Rotate adjacent side-by-side LSCs by `180°` cap-to-cap** (`Col 2k = 0°` [`N=VDD/S=VSS`] $\leftrightarrow$ `Col 2k+1 = 180°` [`N=VSS/S=VDD`] across all `VDDCx` and `SRAMx` column pairs; `rot = 90°` [`W=VDD/E=VSS`] on horizontal remainder rows bridging `(Col 2k, Col 2k+1)` pairs).
  - Enforce **EMIB Rule #19 (`0` LSCs inside any EMIB-T bridge die shadow `U25, U29, U32, U28, U39` on `BASE`, tangent `>= 0.0 um` allowed — splitting `U9_POCKET_5` & `U9_POCKET_6` cleanly around `U39`)**, `LSC SRO -> Cavity >= 225.0 um` (`R_allow <= 275.0 um` at all 4 rounded corners), and `LSC SRO -> LSC SRO >= 250.0 / 175.0 um`.
- [ ] **4.3 Place `12B -> BASE` Microvias:** Place `6` `V90_65_90_12B_BASE_01A` vias per LSC (`3`/pad) and `8` octagonal ring vias (`R = 195.0 um`) per `VDDCx`/`SRAMx` BGA pad.
- [ ] **4.4 SVG Visual Gate:** Generate and inspect `mockup_LDA_BASE_CoPocket_Cavity_LSC.svg`.

---

## Phase 5: Master Recipe Export & Headless Cadence APD `.mcm` Implementation
- [ ] **5.1 Export Multi-Rail Master Recipe:** Generate `U9_LDA_27Layer_APD_Master_Recipe.txt` and JSON DRC manifest.
- [ ] **5.2 Headless APD Run:** Execute `pdnRunVddcVddramMasterRecipe` via `apd.exe -product Allegro_Adv_Packaging_Plus -nographic` into `<design>_lda_mock*.mcm`.
- [ ] **5.3 Final Verification:** Confirm `ERRORS=0` and run unit test suite.
