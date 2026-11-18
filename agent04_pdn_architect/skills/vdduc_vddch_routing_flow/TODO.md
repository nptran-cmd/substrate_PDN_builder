# `VDDUC` and `VDDCH` All-Layer Routing Flow — Execution TODO Checklist

Use this gate-checked checklist whenever routing `VDDUC0..3` (`LDB` dies `U5..U8`) or `VDDCH0..3` (`LDC` dies `U1..U4`) + `VSS` across all 27 layers (`SURFACE` L01 to `BASE` L27).

---

## Phase 0: Pre-Flight & Target Selection
- [ ] **0.1 Select Target Die & Power Net:** Confirm `RefDes` (`U5..U8` for `VDDUC*` or `U1..U4` for `VDDCH*`), power net (`VDDUCx` / `VDDCHx`), and ground return (`VSS`).
- [ ] **0.2 Verify `.mcm` Padstack Availability:** Confirm all required padstacks exist in the target `.mcm` (`V77_49_77_*`, `V90_65_90_*`, `V90_65_121_5F_4FCO_01A`, `V175_85_175_*`, `V282_5_150_282_5_2FCI_2BCI_01B/02A`, `V121_65_90_4BCO_5B_01A`, `V90_65_90_12B_BASE_01A`).
- [ ] **0.3 Confirm User Architecture Options:**
  - `SURFACE` `VDD:VSS` ratio (`FULL`, `4:2`, `5:2`, `3:1`) & floating-bump strap orientation (`HORIZONTAL`, `VERTICAL`, `BOTH`).
  - Core `PTH` density (`5.0..8.0 PTH/mm²`, default `7.0`) & grid pattern (`STAGGERED`, `ORTHOGONAL_90DEG_VERTICAL`, `ORTHOGONAL_90DEG_HORIZONTAL`).
  - `BASE` `0201` LSC height/type (`0.55 mmT 10uF` w/ `250 um` rule vs. `0.22 mmT 1uF` w/ `175 um` rule) & BGA cluster option (`4-via 2x2`, `5-via quincunx`, `6-via hex ring`).

---

## Phase 1: Layer 1 (`SURFACE` -> `12F` / `C0`) & EMIB Upper-BU (`12F/11F/10F`) Gate
- [ ] **1.1 Run `surface_layer1_router.py`:** Partition C4 bumps according to `M:N` ratio and connect `100%` of floating bumps along contiguous 1D chains (`dy = 0` for `HORIZONTAL`, `dx = 0` for `VERTICAL`); keep `C0` strictly restricted to EMIB bridge uBumps (`VU30_19_35_SURFACE_C0_01B`, EMIB Rules #15–#18).
- [ ] **1.2 Enforce EMIB Cavity & `10F` `CSB` / Guard Ring Keepouts (`EMIB Rules #2–#14`):**
  - Void `12F` (`Surface-1`) and `11F` (`Surface-2`) planes/vias within **`157.5 um`** of any EMIB-T die edge (`75 um` cavity + `82.5 um` C4 pad/shape clearance).
  - On `10F` (`Surface-3`): prohibit planes/traces under EMIB-T die (`Rule #7`), preserve the **`150 um` isolated Guard Ring** starting at EMIB die edge (`Rules #6,#22,#23`), maintain `>= 50 um` from Guard Ring (`200 um` from EMIB die) and **`>= 372 um` from `CSB` pads (`Rule #5`)**, and cap `CSB` vias (`10F->9F`) at max `2-stack` (`Rule #14`).
- [ ] **1.3 DRC Gate:** Verify **`0` unstrapped floating bumps** and **`>= 18.0 um` (`12Cu` rule)** trace-to-opposite-pad/via clearance (`40.0 um` horizontal / `43.3 um` vertical) + zero signal bump collisions.
- [ ] **1.4 SVG Review:** Inspect `mockup_L1_SURFACE_*.svg` in `pdn_sandbox/`.

---

## Phase 2: `4FCO` `eDTC` + Core `PTH` & Prepreg (`4FCO <-> 4BCO`) Synthesis
- [ ] **2.1 Concentric `4FCO` `eDTC` Landing:** Place `100%` concentric (`0.0 um` offset) vias on all `4FCO` `eDTC` pins (`6F->5F->4FCO` `2-stack` on `VDD`, `5F->4FCO` `1-stack` on `VSS`).
- [ ] **2.2 Enforce `4FCO..4BCO` `eDTC` KOZ & `eDTC`-to-EMIB Clearance:** Verify `0` `eDTC`s under any EMIB-T die (`eDTC Rule #14`) and **`eDTC` Cavity Edge to EMIB Cavity Edge `>= 1,000.0 um` (`eDTC Rule #5`)**; exclude all `PTH`s, `PP` vias, and `4BCO->5B` vias from `[eDTC body + 300 um cavity + 150 um guard metal + 67.5 um spacing]`, generate closed plane voids across `4FCO..4BCO`, and keep `5B` continuous solid `VSS` under `eDTC`.
- [ ] **2.3 Concentric `PTH` & `PP` Grid:** Place `5..8 PTH/mm²` Core PTHs (`>= 270 um` same-net, `>= 432.5 um` diff-net) with `100%` concentric `PP` (`85 um` drill) and `5F/4FCO` + `4BCO/5B` BU vias.
- [ ] **2.4 SVG Review:** Inspect `pth_4fco_4bco_*.svg` in `pdn_sandbox/`.

---

## Phase 3: Upper (`12F..5F`) & Lower (`5B..12B`) Build-Up Stack Pruning
- [ ] **3.1 Alternating Plane Assignment:** Populate `VDD` planes (`12F, 10F, 8F, 6F` and `6B, 8B, 10B, 12B`) and `VSS` planes (`11F, 9F, 7F, 5F` and `5B, 7B, 9B, 11B`).
- [ ] **3.2 Atomic Net-Matched Stack Pruning:** Where top `SURFACE` stacks meet `4FCO` `PTH`/`eDTC` columns (around `9F/10F`) or bottom `BASE` BGA/LSC stacks meet `4BCO` columns (around `9B/10B`), prune in **atomic `2-via` increments** so every `VDD` column terminates on an even `VDD` plane and every `VSS` column terminates on an odd `VSS` plane.
- [ ] **3.3 Zero Overlap & Zero Dangling Via Gate:** Assert `via_overlap_count == 0` across all 26 dielectric spans and `dangling_via_columns_count == 0`.

---

## Phase 4: Bottom (`BASE` L27) EMIB Shadow Exclusion, `LSC_CAVITY` Recess Rule & BGA Via Clusters
- [ ] **4.1 Empty BGA Pocket & `LSC_CAVITY` Generation:** Compute rounded-rectangle `SUBSTRATE GEOMETRY/LSC_CAVITY` contours (`BGA SRO -> Cavity >= 250.0 um` `Code G`; `SMD1 >= 254.0 um` / `SMD8 >= 330.2 um` `Codes H/I`; `4-Corner Milling Radius R = 500.0 um` `Code K`; `Min 1016x1016 um` `Code E`; `Web >= 508.0 um` `Code J`; `SM web >= 76.0 um + 102..152 um pullback` `Codes A/B`).
- [ ] **4.2 `0201` LSC Placement on `CONDUCTOR/BASE` with `180°` Cap-to-Cap Alternation, Pin Nets, EMIB Rule #19 & Corner Arc Pruning:**
  - Place `100%` of LSC pads on **`CONDUCTOR/BASE` (bottom layer, `0` on `CONDUCTOR/SURFACE`)** by testing `mir=nil` first and verifying `pin->startEnd` (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir=nil`; `SM0201S_690X390X220_01C` uses `mir=t`).
  - Instantiate true logical components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = VDDUCx/VDDCHx` and `Pin "2" = VSS` via `axlChangeNet`.
  - **Rotate adjacent side-by-side LSCs by `180°` cap-to-cap** (`Col 2k = 0°` [`N=VDD/S=VSS`] $\leftrightarrow$ `Col 2k+1 = 180°` [`N=VSS/S=VDD`] across X-columns; `rot = 90°` [`W=VDD/E=VSS`] on horizontal bottom/top remainder rows bridging `(Col 2k, Col 2k+1)` pairs).
  - Obey **EMIB Rule #19 (`0` LSCs inside any EMIB-T bridge die shadow `U28, U32, U35, U38, U47..U49` on `BASE`, tangent `>= 0.0 um` allowed)**, `BGA SRO -> LSC SRO >= 500.0 um`, `LSC SRO -> LSC SRO >= 250.0 / 175.0 um`, and **`LSC SRO -> Cavity >= 225.0 um`** (`R_allow = 275.0 um` at all 4 rounded corners).
- [ ] **4.3 Signal & Copper Keepout Halo (`Code D`):** Enforce `178.0 um` (`7 mil`) `BASE` external copper/signal keepout (`ROUTE KEEPOUT/BASE`) and `203.0 um` (`8 mil`) inner-layer keepout around `LSC_CAVITY`.
- [ ] **4.4 `12B -> BASE` GCP Microvias:** Place `6` `V90_65_90_12B_BASE_01A` vias per LSC (`3`/pad) and `4/5/6` vias per `VDD`/`VSS` BGA pad.
- [ ] **4.5 SVG Review:** Inspect `mockup_VDDUC0_BASE_Cavity_Rule_LSC_Placement.svg`.

---

## Phase 5: Stage 4 Master Recipe Export & Headless Cadence APD `.mcm` Run
- [ ] **5.1 Export Master Recipe:** Run `apd_27layer_master_exporter.py` and confirm `"Zero_DRC_and_Overlap_Violations": true` and `"Zero_Dangling_Vias": true`.
- [ ] **5.2 Headless APD Instantiation:** Execute `apd.exe -product Allegro_Adv_Packaging_Plus -nographic` into `<design>_mock*.mcm` (never overwrite golden input `.mcm`).
- [ ] **5.3 Post-Import Verification:** Confirm `ERRORS=0` in `*_implement_report.txt` and run unit tests (`python -m unittest discover -s agent04_pdn_architect/tests -v`).
