---
name: hbm_vdd_routing_flow
description: End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) Multi-Rail HBM4E PDN routing flow for `U13` (`MEM5`: `VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5`, `VDDQL5`, `VPP_1P8_HBM_MEM5` + Kelvin `OBS_*`/`SNS_*` pairs + `VSS`) and all 12 `HBM4E_MICRON_NOMINAL_BC_A0` sites (`U13..U24`, `MEM0..MEMB`). Learned directly from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt` and enforcing full EMIB-T Design Rules (`U41..U52` `LAVA_BRIDGE_22/23` `C0` exclusivity, `12F/11F` `157.5 um` cavity KOZ, `10F` `150 um` guard ring + `372 um` `CSB` clearance, `4FCO` `1,000 um` `eDTC`-to-EMIB, and `BASE` Rule #19 `LSC` outside EMIB die shadow) plus `BASE` Mechanical Cavity Recess (`LSC_CAVITY` `Codes A–K` + `Slide 11`) rules.
---

# `HBM` (`U13` / `U13..U24`) Multi-Rail `VDD*` (+ `VPP*` & `VSS`) All-Layer (27-Layer) PDN Routing Flow

## 1. Overview & What Was Learned from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt`

Every **`HBM4E_MICRON_NOMINAL_BC_A0`** memory stack (`14.18 mm × 10.98 mm`, `18,236` fine-pitch `C21_7_DP_01A` `21 um` microbumps) is powered by **4 distinct voltage rails** (`3` `VDD*` rails + `1` `VPP*` wordline pump rail), **Kelvin observability/sense pairs (`OBS_*` / `SNS_*`)**, and **`VSS`**, while its inner `5.42 mm` (`38%`) footprint overlaps a **`LAVA_BRIDGE_22/23_BC_A0` EMIB-T silicon bridge** connecting to an adjacent **`LDB` (`U5..U8`)** host die:

### Reference Instance `U13` (`Channel MEM5` — NW Top Site, `rot = 180°`, `mirror = YES`)

| Rail Name on `U13` | Role / Nominal V | `U13` `SURFACE` Bumps (`Over U41` / `West`) | Shared on `U41` EMIB (`C0` / `10F CSB`) & `U5` (`LDB`) | `4FCO` `eDTC` (`S200M_0`) | Core PTHs (`100%` Concentric PP) | `BASE` BGAs (`C560_35_01B`) & Via Cluster | `BASE` `0201 10uF` LSCs |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`VDDQ_0P85_HBM_MEM5`** | HBM I/O Core (`0.85V`) | **`3,717`** (`1,334` / `2,383`) | `U41`: `1,383 C0` + `543 CSB`<br>`U5`: **`65` bumps** | **`C2257`** (`24`-pin `016`: `12 VDDQ + 12 VSS`) | **`114`** (`114/114` `1-PP/PTH`) | **`42` BGAs** × **`6-via` cluster** (`252` vias) | **`11` LSCs** (`Pocket A` East, `33` vias) |
| **`VDDC_1P0_HBM_MEM5`** | HBM DRAM Core (`1.0V`) | **`2,627`** (`208` / `2,419`) | `U41`: `160 C0` + `54 CSB`<br>`U5`: `0` | **`C2258`** (`48`-pin `017`: `24 VDDC + 24 VSS`) | **`103`** (`103/103` `1-PP/PTH`) | **`36` BGAs** × **`4-via` `R=200` diamond** (`144` vias) | **`16` LSCs** (`Pocket A` West, `48` vias) |
| **`VDDQL5`** | Low-Swing PHY I/O (`0.4–0.6V`) | **`1,476`** (`1,010` / `466`) | `U41`: **`1,733 C0` + `588 CSB`**<br>`U5`: **`780` bumps** | `0` *(Bridge-coupled)* | **`84`** (`84/84` `1-PP/PTH`) | **`9` BGAs** × **`4-via` `R=200` diamond** (`36` vias) | **`6` LSCs** (`Pocket B` NE of `U41`, `18` vias) |
| **`VPP_1P8_HBM_MEM5`** | Wordline Pump (`1.8V`) | **`774`** (`122` / `652`) | `U41`: `67 C0` + `14 CSB`<br>`U5`: `0` | `0` | **`60`** (`60/60` `1-PP/PTH`) | **`8` BGAs** × **`4-via` `R=200` cluster** (`32` vias) | `0` |
| **`OBS_*` & `SNS_*` (`6` pairs)** | Differential Kelvin Sense | `3` pairs on `U13` West (`6` pins) | `OBS_VDDQL5` pair on `U41` `10F CSB` (`2` pins); `2` `SNS_*` pairs on `10F/10B` | `0` | **`10` sense PTHs** (`02A`/`01B` `1-via` cols) | **`10` sense BGAs** (`1` concentric via/BGA) | `0` |
| **`VSS`** *(Regional)* | Common Ground Return | **`5,481`** (`1,394` / `4,087`) | `U41`: `3,355 C0` + `1,855 CSB`<br>`U5`: `4,473` bumps | `C2257` (`12`) + `C2258` (`24`) | **`1,085`** regional PTHs | **`135–314`** regional BGAs | Co-paired (`11+16+6 = 33`) |

### Complete 12-Site HBM4E Package Mapping (`U13..U24` — Ready for Multi-RefDes Cloning!)

| HBM `RefDes` | Channel ID (`<CH>`) | Center `(x, y)` `um` / `Rot` | Paired EMIB Bridge (`LAVA_BRIDGE`) | Host `LDB` | `48`-Pin `VDDC` `eDTC` (`017`) | `24`-Pin `VDDQ` `eDTC` (`016`) | `VDD*` / `VPP*` Rail Naming Pattern |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`U13`** *(Ref)* | **`5` (`MEM5`)** | `(-37,465.6, +27,687.5)` / `180°` | `U41` (`LAVA_22`) | `U5` | `C2258` | `C2257` | `VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5`, `VDDQL5`, `VPP_1P8_HBM_MEM5` |
| **`U14`** | **`4` (`MEM4`)** | `(-37,465.6, +16,612.5)` / `180°` | `U42` (`LAVA_22`) | `U5` | `C2256` | `C2255` | `VDDQ_0P85_HBM_MEM4`, `VDDC_1P0_HBM_MEM4`, `VDDQL4`, `VPP_1P8_HBM_MEM4` |
| **`U15`** | **`3` (`MEM3`)** | `(-37,465.6, +5,537.5)` / `180°` | `U43` (`LAVA_22`) | `U5` | `C2254` | `C2253` | `VDDQ_0P85_HBM_MEM3`, `VDDC_1P0_HBM_MEM3`, `VDDQL3`, `VPP_1P8_HBM_MEM3` |
| **`U16`** | **`B` (`MEMB`)** | `(-37,465.6, -5,537.5)` / `180°` | `U44` (`LAVA_23`) | `U6` | `C2270` | `C2269` | `VDDQ_0P85_HBM_MEMB`, `VDDC_1P0_HBM_MEMB`, `VDDQLB`, `VPP_1P8_HBM_MEMB` |
| **`U17`** | **`A` (`MEMA`)** | `(-37,465.6, -16,612.5)` / `180°` | `U45` (`LAVA_23`) | `U6` | `C2268` | `C2267` | `VDDQ_0P85_HBM_MEMA`, `VDDC_1P0_HBM_MEMA`, `VDDQLA`, `VPP_1P8_HBM_MEMA` |
| **`U18`** | **`9` (`MEM9`)** | `(-37,465.6, -27,687.5)` / `180°` | `U46` (`LAVA_23`) | `U6` | `C2266` | `C2265` | `VDDQ_0P85_HBM_MEM9`, `VDDC_1P0_HBM_MEM9`, `VDDQL9`, `VPP_1P8_HBM_MEM9` |
| **`U19`** | **`0` (`MEM0`)** | `(+37,465.6, +27,687.5)` / `0°` | `U47` (`LAVA_23`) | `U7` | `C2248` | `C2247` | `VDDQ_0P85_HBM_MEM0`, `VDDC_1P0_HBM_MEM0`, `VDDQL0`, `VPP_1P8_HBM_MEM0` |
| **`U20`** | **`1` (`MEM1`)** | `(+37,465.6, +16,612.5)` / `0°` | `U48` (`LAVA_BRIDGE_23`) | `U7` | `C2250` | `C2249` | `VDDQ_0P85_HBM_MEM1`, `VDDC_1P0_HBM_MEM1`, `VDDQL1`, `VPP_1P8_HBM_MEM1` |
| **`U21`** | **`2` (`MEM2`)** | `(+37,465.6, +5,537.5)` / `0°` | `U49` (`LAVA_23`) | `U7` | `C2252` | `C2251` | `VDDQ_0P85_HBM_MEM2`, `VDDC_1P0_HBM_MEM2`, `VDDQL2`, `VPP_1P8_HBM_MEM2` |
| **`U22`** | **`6` (`MEM6`)** | `(+37,465.6, -5,537.5)` / `0°` | `U50` (`LAVA_22`) | `U8` | `C2260` | `C2259` | `VDDQ_0P85_HBM_MEM6`, `VDDC_1P0_HBM_MEM6`, `VDDQL6`, `VPP_1P8_HBM_MEM6` |
| **`U23`** | **`7` (`MEM7`)** | `(+37,465.6, -16,612.5)` / `0°` | `U51` (`LAVA_22`) | `U8` | `C2262` | `C2261` | `VDDQ_0P85_HBM_MEM7`, `VDDC_1P0_HBM_MEM7`, `VDDQL7`, `VPP_1P8_HBM_MEM7` |
| **`U24`** | **`8` (`MEM8`)** | `(+37,465.6, -27,687.5)` / `0°` | `U52` (`LAVA_22`) | `U8` | `C2264` | `C2263` | `VDDQ_0P85_HBM_MEM8`, `VDDC_1P0_HBM_MEM8`, `VDDQL8`, `VPP_1P8_HBM_MEM8` |

*(Note: `OBS_VDDQ/VDDC/VPP` & `SNS_VDDC/VDDQL` external BGA sense pins are populated on the top corner sites `U13` (`MEM5`) and `U19` (`MEM0`).)*

---

## 2. Six Unique Architectural Features of HBM PDN Routing (`U13` vs. `VDDUC` & `LDA`)

1. **Dual-Zone Bifurcated `SURFACE` (`L01`) Escape (Ganged `SURFACE` Stripes West of `U41` vs. Direct `C0`/`10F CSB` Over `U41`):**
   - `U41` (`LAVA_BRIDGE_22_BC_A0`, `x = [-35,795.9 .. -26,676.4] um`) overlaps **`5.42 mm` (`38%`)** of `U13`'s east side (`x = [-44,553.1 .. -30,378.1] um`), and `U13` uses `21 um` `C21_7_DP_01A` microbumps (smaller than `77 um` `V77_49_77_SURFACE_12F_01A` vias).
   - **East Zone (Over `U41` EMIB, `x >= -35,795.9 um`):** `U13` power/ground microbumps drop **directly onto `C0` (`U41`)** via `VU30_19_60_SURFACE_C0_01B` (`1,318 VDDQ + 953 VDDQL5 + 160 VDDC + 67 VPP + 1,316 VSS`), tie across `U41` to `U5`'s `VU30_19_39_SURFACE_C0_01B` bumps (`780 VDDQL5 + 65 VDDQ`), and exit the bottom of the EMIB cavity through **`U41`'s `10F` `CSB` (`C77_10F_DP_01A`) pads** (`588 VDDQL5 + 543 VDDQ + 54 VDDC + 14 VPP + 1,855 VSS`) directly into `10F -> 9F` via `V77_49_77_10F_9F_01A`!
   - **West Zone (Outside `U41` + `157.5 um` EMIB KOZ, `x <= -35,962 um`):** Horizontal **`~90 um`-tall `SURFACE` copper gang-bars (`SHP`) + `35 um` straps** gang rows of fine-pitch `C21_7_DP_01A` bumps together (`48 VDDQ`, `72 VDDC`, `18 VDDQL5`, `17 VPP` shapes) and drop via shared `V77_49_77_SURFACE_12F_01A` vias (`614 VDDC + 337 VDDQ + 81 VDDQL5 + 80 VPP + 704 VSS`).
2. **Die-to-Bridge-to-Host Shared Rails (`VDDQL5` & `VDDQ_0P85_HBM_MEM5`):**
   - `VDDQL5` (`1,476` bumps on `U13` + `1,733 C0 / 588 CSB` on `U41` + `780` bumps on `U5`) and `VDDQ_0P85_HBM_MEM5` (`3,717` on `U13` + `1,383 C0 / 543 CSB` on `U41` + `65` on `U5`) power **both** the HBM4E PHY and the `LDB` HBM PHY across `U41`! Therefore, `VDDQL5` planes on `6F, 2FCI, 4BCO, 8B, 12B` extend east to `x ≈ -27,100 um` under `U5`'s west edge.
3. **Natural 4-Strip `West-to-East` Spatial Partitioning (`VPP -> VDDC -> VDDQ -> VDDQL5`):**
   - Matches the `BASE` BGA & die consumer geography from West to East:
     - **Strip 1 (Far West `x ∈ [-45,836 .. -44,522] um`):** `VPP_1P8_HBM_MEM5` (`8` BGAs, `60` PTHs).
     - **Strip 2 (West-Center `x ∈ [-44,500 .. -35,550] um`):** `VDDC_1P0_HBM_MEM5` (`36` BGAs, `103` PTHs, `C2258` `48`-pin `eDTC`, `16` LSCs) & `VDDQ_0P85_HBM_MEM5` (`42` BGAs, `114` PTHs, `C2257` `24`-pin `eDTC`, `11` LSCs) alternating full-span planes (`12F = VDDC`, `10F = VDDQ`, `10B = VDDQ`, `12B = VDDC + VDDQL + VPP`) and co-planar splits (`8F, 6F, 4FCO, 2FCI, 6B, 8B`).
     - **Strip 3 (East Bridge Corridor `x ∈ [-35,550 .. -26,850] um`):** `VDDQL5` (`9` BGAs at `x = -30,934.4 um`, `84` PTHs, `6` LSCs in NE Pocket B).
4. **`100%` Concentric `1-PP-Via/PTH` Core Transitions (`V282_5_85_175`):**
   - Unlike `LDA`, all 4 HBM power rails in the golden dump use **`100%` concentric (`0.0 um` offset) `1-PP-via/PTH`** (`114/114 VDDQ`, `103/103 VDDC`, `84/84 VDDQL5`, `60/60 VPP`) with large-capture-pad `V282_5_85_175_4FCO_3FCI_01A` / `V175_85_282_5_3BCI_4BCO_01A` prepreg vias (`0` `3FCI/3BCI` spider-web traces!).
5. **Dual `4FCO` `eDTC`s (`C2258` `48`-Pin `VDDC` + `C2257` `24`-Pin `VDDQ`) & `>= 1,000 um` EMIB Clearance:**
   - `C2258` (`N24792-017`: `24 VDDC + 24 VSS` concentric pins) sits `3,019.9 um` west of `U41`; `C2257` (`N24792-016`: `12 VDDQ + 12 VSS` concentric pins) sits `1,474.6 um` (symbol) / `2,654.6 um` (pin) west of `U41` — cleanly meeting **`eDTC` Cavity to EMIB Cavity `>= 1,000.0 um` (`eDTC Rule #5`)**, `0` routing on `4FCO..4BCO` in KOZ, and solid `5B` `VSS` plane underneath.
6. **Rail-Matched `BASE` (`L27`) BGA Clusters (`6-Via` on `VDDQ` vs. `4-Via` on `VDDC/VDDQL/VPP`) + EMIB Rule #19 + Co-Pocket `LSC_CAVITY`:**
   - All `BASE` HBM BGAs use `C560_35_01B` (`560 um` SRO): `VDDQ` (`42` BGAs) uses a **compact `6-via` cluster** `[(-45, ±45), (0, ±123), (+45, ±45)]` dropping directly from `10B` (`252` vias), while `VDDC` (`36`), `VDDQL5` (`9`), and `VPP` (`8`) use a **`4-via` `R = 200 um` cardinal diamond** `[(±200, 0), (0, ±200)]`.
   - **Pocket A** (`[-40,173 .. -36,349] × [25,205 .. 31,195] um` `LSC_CAVITY`, strictly `779.6 um` west of `U41` $\rightarrow$ `0` EMIB shadow overlap!) co-houses **`16 VDDC + 11 VDDQ = 27` `0201 10uF` LSCs**, and **Pocket B** (`NE of U41`, `y >= 32,300.7 um > U41 y_max 32,118.6 um` $\rightarrow$ `0` EMIB overlap!) co-houses **`6 VDDQL5` LSCs** alongside `7 VDD_0P75_HBMPHY_UC5` + `2 UCIE_W` LSCs.

---

## 3. Complete 27-Layer (`L01..L27`) Learned Architecture Table (`U13` / `MEM5` Reference)

| Layer (`#`) | Plane / Partition Architecture | `VDDQ` Vias (Dn) | `VDDC` Vias (Dn) | `VDDQL5` Vias (Dn) | `VPP` Vias (Dn) | Key Routing, EMIB & Cavity Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`L01: SURFACE`** | West `90um` Gang-Stripes + East `U41` uBumps | `1,383 C0` + `337 12F` | `160 C0` + `614 12F` | `1,733 C0` + `81 12F` | `67 C0` + `80 12F` | `VU30_19_60`/`39` over `U41`; `V77_49_77_SURFACE_12F_01A` West of `U41` |
| **`L02: C0`** | **EMIB Exclusive (`U41` `LAVA_BRIDGE_22`)** | *(In `U41`)* | *(In `U41`)* | *(In `U41`)* | *(In `U41`)* | **EMIB Rules #15–#18:** `0` non-EMIB shapes/traces/vias outside `U41` |
| **`L03: 12F`** | **`VDDC` Plane (`West of U41 KOZ`)** | `337` *(thru)* | `304` | `81` *(thru)* | `79` *(thru)* | **Void `157.5 um` (`75+82.5`) around `U41` (`Rules #2–#4`)**; `18 um` `OBS_*` diff traces |
| **`L04: 11F`** | **`VSS` Continuous Plane (`EMIB KOZ`)** | `337` *(thru)* | `303` | `81` *(thru)* | `79` *(thru)* | **Void `157.5 um` around `U41`** |
| **`L05: 10F`** | **`VDDQ` Plane + `U41` `CSB` Floor** | **`739`** (`+543 CSB`) | `357` (`+54 CSB`) | **`669`** (`+588 CSB`) | `93` (`+14 CSB`) | **EMIB Rules #5–#14:** `0` plane under `U41`, **`150+50=200 um` Guard KOZ**, **`>=372 um` to `CSB`**, max `2-stack` under `CSB` |
| **`L06: 9F`** | **`VSS` Continuous Plane (`CSB` Term)** | `739` | `352` | `669` | `93` | `V90_65_90_9F_8F_01A` (`1,855 VSS` `CSB` vias terminate on `9F`!) |
| **`L07: 8F`** | **Split: West `VDDC` \| East `VDDQ`** | `438` | `220` | `668` *(thru)* | `84` *(thru)* | `50 um` `15Cu` co-planar split gap at `x ≈ -35.85 mm` |
| **`L08: 7F`** | **`VSS` Continuous Plane** | `438` | `229` | `668` | `84` | `V90_65_90_7F_6F_01A` |
| **`L09: 6F`** | **Split: `VPP` \| `VDDQ` \| `VDDC` \| `VDDQL5`** | `390` | `227` | `219` | `118` | `VDDQL5` spans `[-39,068 .. -27,125]` gathering all `U13`+`U41`+`U5` columns |
| **`L10: 5F`** | **`VSS` Continuous Plane** | `388` | `229` | `220` | `118` | `V90_65_121_5F_4FCO_01A` (`100%` concentric on `C2257` & `C2258` `eDTC` pins) |
| **`L11: 4FCO`** | **Split: `VPP` \| `VDDQ+C2257` \| `VDDC+C2258` \| `VDDQL`** | `114` | `103` | `85` | `60` | `V282_5_85_175_4FCO_3FCI_01A`; `517.5 um` `eDTC` KOZ & **`>=1,000 um` `eDTC`-to-`U41` Cav** |
| **`L12: 3FCI`** | **`VSS` Continuous Plane (`0` Spider Segs)** | `114` | `103` | `85` | `60` | `V175_85_175_3FCI_2FCI_01A` (`100%` concentric `1-PP/PTH`!) |
| **`L13: 2FCI`** | **4-Strip Core Top: `VPP` \| `VDDQ` \| `VDDC` \| `VDDQL`** | **`114` PTH** | **`103` PTH** | **`84` PTH** | **`60` PTH** | `V282_5_150_282_5_2FCI_2BCI_01B` (`02A` on `OBS_*` sense PTHs) |
| **`L14–15: 1FCI/1BCI`** | **`VSS` Plane + `230 um` `VDDC` V-Fingers** | *(Thru PTH)* | *(Thru PTH)* | *(Thru PTH)* | *(Thru PTH)* | `14` (`1FCI`) / `13` (`1BCI`) `230 um` vertical `VDDC` core straps |
| **`L16: 2BCI`** | **Core Bot: `VPP` \| `VDDC` \| `VDDQ` \| `VDDQL`** | `114` | `103` | `84` | `60` | `V282_5_85_175_2BCI_3BCI_01A` (`100%` concentric) |
| **`L17: 3BCI`** | **`VSS` Continuous Plane (`0` Spider Segs)** | `114` | `103` | `84` | `60` | `V175_85_282_5_3BCI_4BCO_01A` |
| **`L18: 4BCO`** | **Split: `VPP` \| `VDDC` \| `VDDQL5` (`0` in KOZ)** | `364` | `280` | `238` | `164` | `V121_65_90_4BCO_5B_01A` (`0` vias inside `C2257`/`C2258` `eDTC` KOZs!) |
| **`L19: 5B`** | **`VSS` Mandatory Solid Plane under `eDTC`s** | `364` | `280` | `238` | `160` | Continuous solid `VSS` under `C2257` & `C2258` cavities + guard rings |
| **`L20: 6B`** | **Split: `VPP` \| `VDDC` \| `VDDQ` (`Full`) \| `VDDQL`** | `416` | `280` | `238` | `160` | `VDDQ` main backside collector `[-43,278 .. -30,792]` |
| **`L21: 7B`** | **`VSS` Continuous Plane** | `408` | `280` | `236` | `160` | `V90_65_90_7B_8B_01A` |
| **`L22: 8B`** | **Split: `VPP` \| `VDDC` \| `VDDQL5`** | `408` | `320` | `312` | `160` | `VDDC` (`[-44,472..-31,857]`) + `VDDQL5` (`[-38,504..-27,075]`) |
| **`L23: 9B`** | **`VSS` Continuous Plane** | `408` | `321` | `312` | `160` | `V77_49_77_9B_10B_01A` |
| **`L24: 10B`** | **Split: `VPP` (West) \| `VDDQ` (Full Die)** | `285` | `321` *(thru)* | `312` *(thru)* | `130` | `VDDQ` full-die plane `[-44,520..-30,373]`; `16.5 um` `SNS_*` diff traces |
| **`L25: 11B`** | **`VSS` Continuous Shield Plane** | `285` | `315` | `312` | `130` | `V77_49_77_11B_12B_01A` (`V83_55_83` optional high-current upgrade) |
| **`L26: 12B`** | **Split (`40um GCP`): `VPP` \| `VDDC` \| `VDDQL5`** | `285` *(dogbone)* | `192` | `54` | `32` | `V90_65_90_12B_BASE_01A` (`6`/BGA on `VDDQ`; `4`/BGA on `VDDC/VDDQL/VPP`; `6`/LSC) |
| **`L27: BASE`** | **`C560` BGAs + `2` `LSC_CAVITY` Pockets** | `42 BGA / 11 LSC` | `36 BGA / 16 LSC` | `9 BGA / 6 LSC` | `8 BGA / 0 LSC` | **EMIB Rule #19 (`0` LSC in `U41` shadow)** + **`LSC_CAVITY` `Codes A–K` (`R=500`, `250`, `225`, `178/203 um`)** |

---

## 4. Strict DRC & Customization Hooks (Ready for Future Enhancement)

1. **EMIB-T Bridge Rules (`U41..U52` `LAVA_BRIDGE_22/23`):**
   - `C0` (`L02`): Zero shapes/traces/vias outside `LAVA_BRIDGE` die (`Rules #15–#18`).
   - `12F` (`L03`) & `11F` (`L04`): Void all `VDDC`/`VSS` planes, gang-via pads, and `OBS_*` traces within **`157.5 um`** (`75 um` cavity + `82.5 um` space) of `U41` (`Rules #2–#4`).
   - `10F` (`L05`): Zero `VDDQ` plane/trace under `U41` (`Rule #7`); **`150.0 um` isolated copper Guard Ring** + `50.0 um` space (`= 200.0 um` plane KOZ, `Rules #6,#8,#22,#23`); **`>= 372.0 um` C4 plane/via spacing to `CSB` pads (`Rule #5`)**; max **`2` stacked vias (`10F->9F->8F`) under `CSB` pads (`Rule #14` — note how `VDDQL5`'s `588` `CSB` vias step on `9F/8F` before continuing to `6F`!)**.
   - `4FCO` (`L11`): `eDTC` (`C2257`, `C2258`) cavity to `U41` EMIB cavity **`>= 1,000.0 um`** (`eDTC Rule #5`; zero `eDTC` under `U41` `Rule #14`).
   - `BASE` (`L27`): **Zero `0201` LSCs inside `U41` EMIB die shadow (`EMIB Rule #19`)** — strictly satisfied by both Pocket A (`x <= -36,575.5 um < -35,795.9 um`) and Pocket B (`y >= 32,300.7 um > 32,118.6 um`).
2. **4-Rail Spatial `(x, y, layer)` Ownership & Atomic Stack Pruning (`0` Overlaps, `0` Dangling Vias):**
   - Every pruned BU via stack must terminate only on a copper island owned by **its exact rail** (`VDDQ`, `VDDC`, `VDDQL5`, `VPP`, or `VSS`) at `(x, y)`.
3. **`BASE` Mechanical Recess (`SUBSTRATE GEOMETRY/LSC_CAVITY`, `Codes A–K` + `Slide 11`):**
   - `Z = 21 ± 4 mil` (`533 ± 102 um`), `BGA SRO (C560_35_01B) -> Cavity >= 250.0 um` (`Code G`; `SMD1 >= 254 um`, `SMD8 >= 330.2 um`), `LSC SRO -> Cavity >= 225.0 um` (`Slide 11`), `4-Corner Radius R >= 500.0 um` (`Code K` $\rightarrow$ `R_allow <= 275.0 um`), `Min 1016×1016 um` (`Code E`), `Web >= 508.0 um` (`Code J`), `SM web >= 76.0 um` (`Codes A/B`), and `178.0 um` Ext / `203.0 um` Int Signal & Non-SMT Cu KOZ (`Code D`).
4. **Mandatory `CONDUCTOR/BASE` LSC Placement, Logical Pin-Net & `180°` Cap-to-Cap Alternation (`HBM` Rails: `VDDQ`, `VDDC`, `VDDQL`):**
   - **Strict `CONDUCTOR/BASE` Layer Placement:** Place `100%` of `HBM` LSCs (`16 VDDC_1P0_HBM_MEMx + 11 VDDQ_0P85_HBM_MEMx` in Pocket A and `6 VDDQLx` in Pocket B) onto **`CONDUCTOR/BASE` (`0` on `CONDUCTOR/SURFACE`)** by placing with `mir = nil` first and checking `pin->startEnd` (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir = nil`; `SM0201S_690X390X220_01C` uses `mir = t`).
   - **Logical Component + Pin Nets:** Instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = <HBM_VDD_RAIL>` (`VDDQ_0P85_HBM_MEMx`, `VDDC_1P0_HBM_MEMx`, or `VDDQLx`) and `Pin "2" = VSS` via `axlChangeNet`.
   - **`180°` Cap-to-Cap Polarity Alternation:** Rotate adjacent side-by-side LSCs by **`180°` cap-to-cap** (`0°` [`N=VDD*/S=VSS`] $\leftrightarrow$ `180°` [`N=VSS/S=VDD*`] across adjacent X-columns in both Pocket A and Pocket B; `rot = 90°` [`W=VDD*/E=VSS`] on horizontal remainder rows bridging `(Col 2k, Col 2k+1)` pairs, or `90°` $\leftrightarrow$ `270°` across stacked horizontal rows).

---

## 5. Reference Files in This Skill Package
- [`references/hbm_u13_learned_profile.json`](file:///<agent_workspace>/agent04_pdn_architect/skills/hbm_vdd_routing_flow/references/hbm_u13_learned_profile.json) — Complete Ground-Truth Metrics for `U13` (`MEM5`) & All 12 `HBM4E` Sites Learned from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt`
- [`TEMPLATE.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/hbm_vdd_routing_flow/TEMPLATE.md) — Customizable 4-Rail HBM JSON Config & Pipe-Delimited Master Recipe Schema
- [`templates/hbm_vdd_all_layer_template.il`](file:///<agent_workspace>/agent04_pdn_architect/skills/hbm_vdd_routing_flow/templates/hbm_vdd_all_layer_template.il) — Reusable Multi-Rail + `SURFACE` Gang-Stripe Cadence APD SKILL Importer Template
- [`TODO.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/hbm_vdd_routing_flow/TODO.md) — Gate-Checked Execution & Enhancement Checklist for `HBM` (`U13..U24`) Routing
