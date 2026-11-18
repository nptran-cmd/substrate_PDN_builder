# `HBM` (`U13` / `U13..U24`) Multi-Rail `VDD*` Routing Flow — Execution & Enhancement TODO List

Use this gate-checked checklist to configure, synthesize, review, and instantiate the 27-layer (`SURFACE` L01 $\rightarrow$ `BASE` L27) PDN routing for **`U13` (`MEM5`)** or clone/remap it across any of the 12 `HBM4E` sites (`U13..U24`, `MEM0..MEMB`).

---

## Phase 0: Target HBM Channel Selection & Architecture Customization
- [ ] **0.1 Select Target HBM Site(s):** Choose reference `U13` (`MEM5`, paired with `U41` `LAVA_BRIDGE_22` + `U5` `LDB` + `C2258`/`C2257` `eDTC`s) or a multi-site list (`U13..U24`) for `'Targeted Multi-RefDes Copy & Net Map'`.
- [ ] **0.2 Confirm All 4 Power Rails + Sense Pairs + `VSS`:**
  - `VDDQ_0P85_HBM_MEM<CH>`, `VDDC_1P0_HBM_MEM<CH>`, `VDDQL<CH>`, `VPP_1P8_HBM_MEM<CH>`, `VSS`, and Kelvin sense pairs (`OBS_*` / `SNS_*` on corner sites `U13` / `U19`).
- [ ] **0.3 Review Customizable Per-Zone Options (`TEMPLATE.md`):**
  - `SURFACE` West non-EMIB escape: `90 um` horizontal copper gang-stripes + `35 um` straps *(learned baseline)* vs. parameterized `M:N` (`3:1`, `4:2`) pure horizontal row strapping.
  - Backside `10B -> 12B` `VDDQ` delivery: `10B` full-die plane + `285` stacked `10B->12B->BASE` dogbone columns *(learned baseline)* vs. carved `12B` `VDDQ` sub-island above Pocket A & `VDDQ` BGAs.
  - `BASE` BGA cluster: `6-via` (`VDDQ`) + `4-via` (`VDDC/VDDQL/VPP`) *(learned baseline)* vs. uniform `6-via` hex rings on `C560_35_01B`.

---

## Phase 1: Bifurcated `SURFACE` (`L01`) & EMIB Upper-BU (`C0 / 12F / 11F / 10F`) Gate
- [ ] **1.1 East EMIB Overlap Zone (`x >= -35,795.9 um` on `U13` / `U41`):**
  - Drop `U13` bumps over `U41` onto `C0` via `VU30_19_60_SURFACE_C0_01B` (`VDDQ`, `VDDQL`, `VDDC`, `VPP`, `VSS`) and `U5` (`LDB`) shared bumps (`VDDQL5`, `VDDQ`) via `VU30_19_39_SURFACE_C0_01B`.
  - Enforce **`C0` Exclusivity (`EMIB Rules #15–#18`)**: zero shapes, traces, or vias on `C0` outside `U41`.
- [ ] **1.2 West Non-EMIB HBM Zone (`x <= -35,962.0 um`):**
  - Gang `C21_7_DP_01A` (`21 um`) bumps per rail using horizontal `SURFACE` gang-stripes/straps (`>= 18.0 um` clearance) and drop through `V77_49_77_SURFACE_12F_01A` vias (`0` floating bumps).
- [ ] **1.3 Enforce `12F / 11F / 10F` EMIB Cavity, Guard Ring & `CSB` Rules (`EMIB Rules #2–#14`):**
  - Void `12F` (`VDDC`) and `11F` (`VSS`) planes/vias within **`157.5 um`** of `U41` (`75 um` cavity + `82.5 um` C4 spacing).
  - On `10F` (`VDDQ` plane + `U41` `CSB` floor): prohibit `VDDQ` plane/traces under `U41` (`Rule #7`), preserve **`150.0 um` isolated copper Guard Ring** + `50.0 um` spacing (`= 200.0 um` KOZ, `Rules #6,#8,#22,#23`), maintain **`>= 372.0 um` C4 plane/via clearance to active `CSB` (`C77_10F_DP_01A`) pads (`Rule #5`)**, and cap `CSB` breakout vias (`10F->9F`, `588 VDDQL5 + 543 VDDQ + 54 VDDC + 14 VPP + 1,855 VSS`) at **max `2` stacked vias (`Rule #14`)** before stepping laterally on `9F/8F`!
- [ ] **1.4 Differential Kelvin `OBS_*` Escape:** Route `18–20 um` `VSS`-shielded differential pairs (`OBS_VDDQ/VDDC/VPP` from `U13` West on `12F`; `OBS_VDDQL5` from `U41` `10F CSB` on `8F`).
- [ ] **1.5 SVG Visual Gate:** Generate and inspect `mockup_HBM_U13_L1_SURFACE_and_10F_CSB.svg`.

---

## Phase 2: Dual `4FCO` `eDTC` (`C2258` + `C2257`) & 4-Strip Core `PTH` (`4FCO <-> 4BCO`) Gate
- [ ] **2.1 Concentric `4FCO` `eDTC` Pin Landing:**
  - Place `100%` concentric (`0.0 um` offset) `5F -> 4FCO` vias on **`C2258`** (`48`-pin `017`: `24 VDDC + 24 VSS`) and **`C2257`** (`24`-pin `016`: `12 VDDQ + 12 VSS`).
- [ ] **2.2 `eDTC`-to-EMIB (`>= 1,000 um`) & `4FCO..4BCO` `eDTC` KOZ Gate:**
  - Verify `0` `eDTC`s under `U41` (`eDTC Rule #14`) and **`eDTC` Cavity Edge to `U41` EMIB Cavity Edge `>= 1,000.0 um` (`eDTC Rule #5`)** (`C2257` `= 1,474.6 um` sym / `~1,700+ um` cav; `C2258` `= 3,019.9 um`).
  - Exclude `100%` of PTHs, PP vias, traces, and `4BCO -> 5B` vias from `[eDTC body + 300 um cavity + 150 um guard metal + 67.5 um spacing]`; close all `2 × 8 = 16` `eDTC` plane voids across `4FCO..4BCO`; maintain continuous solid `5B` `VSS` plane underneath.
- [ ] **2.3 4-Strip `100%` Concentric Core PTH + PP Grid (`VPP | VDDQ | VDDC | VDDQL5`):**
  - Place `VPP` (Far West), `VDDQ` & `VDDC` (Center-West outside `C2257/C2258` KOZs), and `VDDQL5` (East under `U41/U5`) PTHs (`>= 270 um` same-net, `>= 432.5 um` diff-net, `>= 67.5 um` strip split gap) with **`100%` concentric `1-PP-via/PTH`** (`V282_5_85_175_4FCO_3FCI_01A` / `V175_85_282_5_3BCI_4BCO_01A`).
- [ ] **2.4 SVG Visual Gate:** Generate and inspect `mockup_HBM_U13_4FCO_4BCO_4Rail_Core.svg`.

---

## Phase 3: 5-Net (`VDDQ, VDDC, VDDQL5, VPP, VSS`) Spatial Plane Matching & Stack Pruning
- [ ] **3.1 Co-Planar Strip & Cutout Generation (`8F, 6F, 4FCO, 2FCI, 2BCI, 4BCO, 6B, 8B, 10B, 12B`):**
  - Enforce `>= 50.0 um` (`15Cu/18Cu` BU) and `>= 67.5 um` (`25Cu/35Cu` Core/PP & `40um GCP` `12B`) split clearances between adjacent voltage strips; keep all odd layers (`11F, 9F, 7F, 5F, 3FCI, 3BCI, 5B, 7B, 9B, 11B`) continuous `VSS`.
- [ ] **3.2 Spatial `(x, y, layer)` Net-Ownership Stack Pruning:**
  - Verify every pruned BU column starts and ends strictly inside a copper shape owned by **its exact rail** (`0` overlaps across all 26 dielectric spans, `0` dangling via columns!).

---

## Phase 4: Bottom (`BASE` L27) `C560` BGA Clusters + EMIB Rule #19 + `LSC_CAVITY` Recess Gate
- [ ] **4.1 Generate `SUBSTRATE GEOMETRY/LSC_CAVITY` & `Code D` (`178 / 203 um`) Keepouts:**
  - Build `R = 500.0 um` (`Code K`) rounded-corner cavities for **Pocket A** (`West of U41`, `[-40,173 .. -36,349] × [25,205 .. 31,195] um`) and **Pocket B** (`North of U41`), obeying `BGA SRO (C560_35_01B) -> Cavity >= 250.0 um` (`Code G`), `Min 1016×1016 um` (`Code E`), `Web >= 508.0 um` (`Code J`), `SM web >= 76.0 um` (`Codes A/B`), and `178.0 um` Ext / `203.0 um` Int Signal & Cu KOZ (`Code D`).
- [ ] **4.2 Place Co-Pocket `0201` LSCs on `CONDUCTOR/BASE` with `180°` Cap-to-Cap Alternation, Pin Nets, EMIB Rule #19 & Corner Arc Pruning:**
  - Place `100%` of LSC pads on **`CONDUCTOR/BASE` (bottom layer, `0` on `CONDUCTOR/SURFACE`)** via `mir=nil` first + `pin->startEnd` check (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir=nil`).
  - Instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = VDDQ_0P85_HBM_MEMx / VDDC_1P0_HBM_MEMx / VDDQLx` and `Pin "2" = VSS` via `axlChangeNet`.
  - **Rotate adjacent side-by-side LSCs by `180°` cap-to-cap** (`0°` [`N=VDD*/S=VSS`] $\leftrightarrow$ `180°` [`N=VSS/S=VDD*`] across X-columns in Pocket A and Pocket B; `rot = 90°` [`W=VDD*/E=VSS`] on horizontal remainder rows bridging `(Col 2k, Col 2k+1)` pairs).
  - Enforce **EMIB Rule #19 (`0` LSCs inside `U41` EMIB die shadow `[-35,795.9 .. -26,676.4] × [22,484.9 .. 32,118.6] um`)**.
  - Pack `16 VDDC + 11 VDDQ = 27` LSCs in Pocket A and `6 VDDQL5` LSCs in Pocket B obeying **`LSC SRO -> Cavity >= 225.0 um`** (`R_allow <= 275.0 um` at all 4 rounded corners) and `LSC SRO -> LSC SRO >= 250.0 / 175.0 um`.
- [ ] **4.3 Place `12B -> BASE` (`V90_65_90_12B_BASE_01A`) Microvias:**
  - Place `6` vias/LSC (`3`/pad), `6-via` clusters on `42 VDDQ` BGAs, and `4-via` `R = 200 um` clusters on `36 VDDC`, `9 VDDQL5`, and `8 VPP` BGAs.
- [ ] **4.4 SVG Visual Gate:** Generate and inspect `mockup_HBM_U13_BASE_Cavity_LSC_BGA.svg`.

---

## Phase 5: Master Recipe Export, Multi-Site (`U13..U24`) Remap & Headless APD Run
- [ ] **5.1 Export `U13` Master Recipe:** Generate `U13_HBM_27Layer_APD_Master_Recipe.txt` and verify `0` DRC/overlap/dangling violations.
- [ ] **5.2 Optional 12-Site Clone (`U13..U24`):** Apply SKILL `makeTable` net remapping + mirror/translation across `U14..U24` (`MEM0..MEMB`).
- [ ] **5.3 Headless APD Instantiation & Verification:** Run `pdnRunHbmVddMasterRecipe` via `apd.exe -nographic` into `<design>_hbm_mock*.mcm`, confirm `ERRORS=0`, and run `python -m unittest discover -s agent04_pdn_architect/tests -v`.
