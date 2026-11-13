---
name: vddc_vddram_routing_flow
description: End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) Co-Resident Dual-Power-Rail PDN routing flow for `VDDC*` (`VDDC0..3`) and `VDDSRAM` (`VDD_0P8_SRAM_CC0..3` + Kelvin `OBS_*`/`SNS_*` pairs) with `VSS` return on the `LDA` compute dies (`U9, U12, U88, U10` — `HUTTON_HILL_LDA_BC_A0`), learned directly from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt` and enforcing full EMIB-T Design Rules (`C0` exclusivity, `12F/11F` `157.5 um` cavity KOZ, `10F` `150 um` guard ring + `372 um` CSB clearance, `4FCO` `1,000 um` `eDTC`-to-EMIB, and `BASE` Rule #19 `LSC` outside EMIB bridge shadow) plus `BASE` Mechanical Cavity Recess (`LSC_CAVITY` `Codes A–K` + `Slide 11`) rules.
---

# `VDDC*` and `VDDRAM` (`VDD_0P8_SRAM_CC*`) All-Layer (27-Layer) PDN Routing Flow

## 1. Overview & What Was Learned from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt`

Unlike `VDDUC*` and `VDDCH*` (which route a **single** power domain + `VSS` inside an isolated die island), each **`LDA` compute die (`HUTTON_HILL_LDA_BC_A0`)** co-routes **two overlapping power rails + Kelvin observability/sense pairs + `VSS`** across the exact same `34.1 mm × 16.9 mm` die shadow:

| `LDA` Die `RefDes` | Rotation / Center `(x, y)` `um` | Primary Core Rail (`VDDC*`) | Co-Resident SRAM Rail (`SRAM*`) | Kelvin Sense / Observability Nets | `4FCO` `eDTC`s (`6 × 144`-pin `018`) | `BASE` `0201 10uF` LSCs |
| :---: | :---: | :--- | :--- | :--- | :--- | :--- |
| **`U9`** *(Reference)* | `90°` @ `(0, +23,914)` | **`VDDC0`** (`10,664` bumps, `202` BGAs) | **`VDD_0P8_SRAM_CC0`** (`1,007` bumps, `22` BGAs) | `OBS_VDD_0P8_SRAM_CC0_0/1` (`+ _VSS`), `SNS_VDD_0P8_SRAM_CC0` (`+ _VSS`) | `4` pure `VDDC0` (`C2215,17,19,20`) + **`2` shared** (`C2216`, `C2218`) | `156 VDDC0` + `40 SRAM0` (`= 196`) |
| **`U12`** | `270°` @ `(0, +7,971)` | **`VDDC1`** (`10,664` bumps, `200` BGAs) | **`VDD_0P8_SRAM_CC1`** (`1,007` bumps, `22` BGAs) | `OBS_VDD_0P8_SRAM_CC1_0/1`, `SNS_VDD_0P8_SRAM_CC1` | `4` pure (`C2221,24,27,28`) + **`2` shared** (`C2225`, `C2222`) | `156 VDDC1` + `40 SRAM1` (`= 196`) |
| **`U88`** | `90°` @ `(0, -7,971)` | **`VDDC2`** (`10,664` bumps, `200` BGAs) | **`VDD_0P8_SRAM_CC2`** (`1,007` bumps, `22` BGAs) | `OBS_VDD_0P8_SRAM_CC2_0/1`, `SNS_VDD_0P8_SRAM_CC2` | `4` pure (`C2230,31,33,34`) + **`2` shared** (`C2232`, `C2229`) | `156 VDDC2` + `40 SRAM2` (`= 196`) |
| **`U10`** | `270°` @ `(0, -23,914)` | **`VDDC3`** (`10,664` bumps, `204` BGAs) | **`VDD_0P8_SRAM_CC3`** (`1,007` bumps, `22` BGAs) | `OBS_VDD_0P8_SRAM_CC3_0/1`, `SNS_VDD_0P8_SRAM_CC3` | `4` pure (`C2235,36,40,45`) + **`2` shared** (`C2237`, `C2246`) | `156 VDDC3` + `40 SRAM3` (`= 196`) |

---

## 2. Key Architectural Differences: `VDDC* + VDDRAM` (`LDA`) vs. `VDDUC / VDDCH`

1. **Dedicated Full-Span `SRAM` Collection Planes on `10F` (Top BU) and `10B` (Bottom BU):**
   - Because `VDD_0P8_SRAM_CC0`'s `1,007` C4 bumps are distributed across SRAM macro blocks over the entire `31.1 mm × 15.4 mm` `U9` die (`x = [-15,513 .. +15,635] um`), **`100%` (`1,007 / 1,007`) of `SRAM` bumps drop via a 3-level microvia stack (`SURFACE -> 12F -> 11F -> 10F`) through antipads in `12F` (`VDDC0`) and `11F` (`VSS`) into a dedicated full-die `VDD_0P8_SRAM_CC0` plane on `10F`!**
   - Symmetrically on the backside, **`10B` (`L24`) is a dedicated full-span `VDD_0P8_SRAM_CC0` plane** (`[-15,205 .. +15,048] um`) that redistributes SRAM current laterally between the West/East Core PTH corridors and the `22` `SRAM` BGAs + `40` `SRAM` LSCs.
2. **Co-Planar Carved Voltage Islands on `6F, 4FCO, 2FCI, 2BCI, 4BCO, 6B, 8B, 12B`:**
   - Rather than wasting half of all even layers on `SRAM` (`1,007` bumps vs `10,664` `VDDC0` bumps = `~1:10.6` current ratio), **`10F` funnels `VDD_0P8_SRAM_CC0` into two compact vertical SRAM corridors** — **West Corridor (`x ≈ [-5,520 .. -1,895] um`)** and **East Corridor (`x ≈ [+8,058 .. +13,159] um`)** — carved as co-planar voltage islands inside the main `VDDC0` planes on `6F, 4FCO, 2FCI, 2BCI, 4BCO, 6B, 8B, 12B` (`>= 50 um` BU / `>= 67.5 um` Core/PP/GCP split-plane gap).
3. **Shared Dual-Rail `4FCO` `eDTC` Capacitors (`C2216` & `C2218`):**
   - Out of `U9`'s `6` `144`-pin `eDTC`s (`N24792-018_LIVE_BUG_4FCO_02A`), `4` (`C2215, C2217, C2219, C2220`) are `100%` `VDDC0` (`72 VDDC0 + 72 VSS`), while **2 are shared between `VDDC0` and `VDD_0P8_SRAM_CC0`**:
     - **`C2216` (West Corridor):** `48 VDD_0P8_SRAM_CC0` + `24 VDDC0` + `72 VSS` pins (`144` total).
     - **`C2218` (East Corridor):** `24 VDD_0P8_SRAM_CC0` + `48 VDDC0` + `72 VSS` pins (`144` total).
4. **Core `PTH` Dual-PP Spider-Web (`Case 2`) + `1FCI/1BCI` `350 um` Power Fingers:**
   - In the golden dump, `VDDC0` (`965` PTHs) and `VDD_0P8_SRAM_CC0` (`179` PTHs) combine **`1` concentric PP via/PTH** (`466 VDDC0`, `82 SRAM0`) with **`2` spider-web PP vias/PTH** (`499×2 VDDC0`, `97×2 SRAM0` connected by `175 um` H/V/45° straps on `3FCI/3BCI`), plus `350 um`-wide vertical power fingers on `1FCI`/`1BCI` (`len = 316 um`). *(User-configurable in `TEMPLATE.md`: can keep hybrid `Case 2` or switch to `100%` concentric `1-via/PTH` like `VDDUC`!)*
5. **Backside High-Current `V83_55_83` Microvias (`10B -> 11B -> 12B`) & `8-Via` Octagonal BGA Rings (`12B -> BASE`):**
   - On `10B -> 11B -> 12B`, `VDDC0` (`3,291` vias) and `VDD_0P8_SRAM_CC0` (`425` vias) upgrade from `V77_49_77` to **`V83_55_83_10B_11B_01A` / `V83_55_83_11B_12B_01A`** (`55 um` drill / `83 um` pad).
   - On `12B -> BASE`, every `VDDC0` (`202`) and `VDD_0P8_SRAM_CC0` (`22`) `C480_60_01B` BGA pad uses an **`8-via` octagonal `V90_65_90_12B_BASE_01A` ring at `R = 195.0 um`**:
     `[(±195.0, 0.0), (0.0, ±195.0), (±137.9, ±137.9)]` (`Recess Code I: SMD8 >= 330 um` SMO-to-recess!).
6. **Co-Inhabited `BASE` `LSC_CAVITY` Pockets (`VDDC0` + `VDD_0P8_SRAM_CC0`) & EMIB Bridge Shadow Split (`U25, U32, U39`):**
   - In both the **West LSC Pocket (`x = [-3,817 .. -1,067] um, y = [20,995 .. 27,415] um`)** and **East LSC Pocket (`x = [9,208 .. 11,958] um, y = [19,650 .. 28,210] um`)**, `VDDC0` and `VDD_0P8_SRAM_CC0` `0201 10uF` LSCs (`SM0201_690X390X550_01A`) **share the same milled `LSC_CAVITY` pocket**, landing directly onto their respective carved `12B` `VDDC0` / `SRAM0` sub-planes above!
   - Meanwhile, along `U9`'s north/west/east borders sit **5 adjacent EMIB-T silicon bridges** (`U25` West `[-18,817..-13,158]`, `U32` East `[+13,158..+18,817]`, `U39` North `[-2,817..+2,817, 33,035.7..39,305.9]`, plus corner bridges `U29`, `U28`). Because **EMIB Rule #19 prohibits `LSC` inside any EMIB-T bridge die shadow on `BASE` (tangent `>= 0 um` allowed)**, `U9`'s north LSC pockets (`U9_POCKET_5` NW `x <= -1,826.6 um` & `U9_POCKET_6` NE `x >= +1,826.6 um`, `y_top = 33,035.7 um` tangent to `U39`!) split cleanly around `U39`.

---

## 3. Complete 27-Layer (`L01..L27`) Learned Layer-by-Layer Architecture Table (`U9` Reference)

| Layer (`#`) | Polarity / Partition in `HH_TO_v8` | `VDDC0` Vias (Down) | `SRAM_CC0` Vias (Down) | `VSS` Vias (`U9` Region) | Padstack (`Down`) & Key Routing / EMIB / Cavity Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`L01: SURFACE`** | C4 Bumps + `14/50 um` Straps | `10,515` (`98.6%`) | `1,007` (`100%`) | `12,246` (`72.9%`) + `C0` | `V77_49_77_SURFACE_12F_01A` (`VU30_19_35_SURFACE_C0_01B` on `4,994` EMIB `VSS` uBumps); customizable to `M:N` V/H/Both |
| **`L02: C0`** | **EMIB Bridge RDL Only (`Rules #15–#18`)** | `0` *(skip)* | `0` *(skip)* | *(EMIB uBumps)* | Zero shapes/traces/vias allowed on `C0` outside EMIB-T dies (`U25, U29, U32, U28, U39`); `VDDC*` & `SRAM*` skip `C0` directly `SURFACE -> 12F` |
| **`L03: 12F`** | **`VDDC0` Full-Die Plane (`EMIB KOZ`)** | `4,590` | `1,007` *(thru)* | `25,814` | `V77_49_77_12F_11F_01A`; `SRAM0` thru `1,007` antipads; **void `157.5 um` (`75 um` cav + `82.5 um` space) around all EMIB dies (`Rules #2–#4`)** |
| **`L04: 11F`** | **`VSS` Continuous Plane (`EMIB KOZ`)** | `4,589` | `1,007` *(thru)* | `13,680` | `V77_49_77_11F_10F_01A`; **void `157.5 um` around all EMIB dies (`Rules #2–#4`)** |
| **`L05: 10F`** | **`SRAM_CC0` Full-Die Plane (`CSB` Floor)** | `3,886` *(thru)* | `749` | `17,355` | `V77_49_77_10F_9F_01A`; **EMIB Rules #5–#14:** `0` plane/trace under EMIB die (`#7`), **`150 um` isolated Guard Ring** + `50 um` space (`= 200 um` KOZ, `#6,#8`), **`>= 372 um` from `CSB` pads (`#5`)**, max `2-stack` under `CSB` (`#14`) |
| **`L06: 9F`** | **`VSS` Continuous Plane** | `3,886` | `748` | `9,645` | `V90_65_90_9F_8F_01A` (`CSB` `10F->9F` `77_49_77` termination layer) |
| **`L07: 8F`** | **`VDDC0` Full-Die Plane** | `3,410` | `748` *(90um pads)* | `9,287` | `V90_65_90_8F_7F_01A` |
| **`L08: 7F`** | **`VSS` Continuous Plane** | `3,410` | `748` | `7,748` | `V90_65_90_7F_6F_01A` |
| **`L09: 6F`** | **Split: `VDDC0` + W/E `SRAM0`** | `1,830` | `348` | `7,748` | `V90_65_90_6F_5F_01A` (`2-stack` transition to `4FCO` `eDTC` & `PP`) |
| **`L10: 5F`** | **`VSS` Continuous Plane** | `1,830` | `348` | `5,655` | `V90_65_121_5F_4FCO_01A` (`100%` concentric on `360 VDDC0 + 72 SRAM0 + 432 VSS` `eDTC` pins) |
| **`L11: 4FCO`** | **Split: `VDDC0` + `SRAM0` + `6 eDTC`s** | `1,470` | `276` | `4,416` | `V175_85_175_4FCO_3FCI_01A`; strict `300+150+67.5 um` `eDTC` KOZ + **`>= 1,000 um` `eDTC` Cavity to EMIB Cavity (`eDTC Rules #5,#14`)** |
| **`L12: 3FCI`** | **`VSS` Plane + `175 um` PP Straps** | `1,470` | `276` | `4,258` | `V175_85_175_3FCI_2FCI_01A` (`466/82` concentric + `499/97` dual-PP pairs) |
| **`L13: 2FCI`** | **Split: `VDDC0` + `SRAM0` + Guard** | **`965` PTH** | **`179` PTH** | **`3,039` PTH** | `V282_5_150_282_5_2FCI_2BCI_01B` (`02A` for `OBS_*` sense pairs) |
| **`L14–15: 1FCI/1BCI`** | **`VSS` Plane + `350 um` V-Fingers** | *(Thru PTH)* | *(Thru PTH)* | *(Thru PTH)* | `889 VDDC0` + `141 SRAM0` `350 um` vertical core straps (`len=316 um`) |
| **`L16: 2BCI`** | **Split: `VDDC0` + `SRAM0` + Guard** | `1,470` | `276` | `4,189` | `V175_85_175_2BCI_3BCI_01A` |
| **`L17: 3BCI`** | **`VSS` Plane + `175 um` PP Straps** | `1,470` | `276` | `4,337` | `V175_85_175_3BCI_4BCO_01A` |
| **`L18: 4BCO`** | **Split: `VDDC0` + `SRAM0` (`0` in KOZ)** | `2,466` | `470` | `6,308` | `V121_65_90_4BCO_5B_01A` (`0` vias inside any `eDTC` cavity + guard KOZ!) |
| **`L19: 5B`** | **`VSS` Solid Plane under `eDTC`s** | `2,466` | `470` | `7,736` | `V90_65_90_5B_6B_01A` + `67.5 um` escape straps |
| **`L20: 6B`** | **Split: `VDDC0` + W/E `SRAM0`** | `2,894` | `588` | `7,736` | `V90_65_90_6B_7B_01A` |
| **`L21: 7B`** | **`VSS` Plane + `90 um` H-Busbars** | `2,894` | `588` | `10,660` | `V90_65_90_7B_8B_01A` |
| **`L22: 8B`** | **Split: `VDDC0` + W/E `SRAM0`** | `3,309` | `738` | `10,662` | `V90_65_90_8B_9B_01A` |
| **`L23: 9B`** | **`VSS` Plane + `90 um` H-Busbars** | `3,291` | `738` | `10,650` | `V77_49_77_9B_10B_01A` |
| **`L24: 10B`** | **`SRAM_CC0` Full-Span Plane** | `3,291` *(thru)* | `425` | `10,649` | **`V83_55_83_10B_11B_01A`** (`55 um` high-current drill!) |
| **`L25: 11B`** | **`VSS` Continuous Shield Plane** | `3,292` | `425` | `6,905` | **`V83_55_83_11B_12B_01A`** |
| **`L26: 12B`** | **Split: `VDDC0` + `SRAM0` (`40um GCP`)** | `2,644` | `406` | `6,911` | `V90_65_90_12B_BASE_01A` (`8`/BGA ring + `6`/LSC) |
| **`L27: BASE`** | **`BGA` (`8-Via`) + `LSC` + `LSC_CAVITY`** | `202 BGA / 156 LSC` | `22 BGA / 40 LSC` | `457 BGA / 196 LSC` | **EMIB Rule #19 (`0` LSC under EMIB die)** + **`LSC_CAVITY` (`Codes A–K` + `Slide 11`):** `R=500 um`, `250 um` BGA (`330.2 um` `SMD8`!), `225 um` LSC, `178/203 um` Signal/Cu KOZ |

---

## 4. Strict DRC & Customization Hooks (Ready for User Modification)

All strict rules established in `vdduc_vddch_routing_flow` carry over directly, including full **EMIB-T** + **`BASE` Cavity Recess** + **Multi-Rail** enforcement:
1. **EMIB-T Bridge Design Rules Across `C0, 12F, 11F, 10F, 4FCO, BASE` (`U25, U29, U32, U28, U39` on `U9`):**
   - **`C0` (`L02` Rules #15–#18):** Zero non-EMIB shapes, traces, or vias on `C0` outside the EMIB-T silicon bridge die; only `VU30_19_35_SURFACE_C0_01B` allowed inside the bridge die.
   - **`12F` (`L03`) & `11F` (`L04`) Cavity KOZ (`Rules #2–#4`):** Void `VDDCx` (`12F`) and `VSS` (`11F`) planes/vias within **`157.5 um`** of every EMIB-T die edge (`75.0 um` EMIB cavity wall + `82.5 um` C4 pad/plane spacing).
   - **`10F` (`L05`) `SRAM_CCx` Funnel Plane & `CSB` / Guard Ring KOZ (`Rules #5–#8, #10, #12–#14, #22–#23`):** Zero `SRAM_CCx` plane or trace under any EMIB-T die (`Rule #7`); preserve the **`150.0 um` isolated copper Guard Ring** starting at the EMIB die edge (`0` vias/traces/adhesion voids inside guard ring); keep `SRAM_CCx` plane/vias **`>= 50.0 um` outside the Guard Ring (`= 200.0 um` from EMIB die edge, `Rule #8`)** AND **`>= 372.0 um` from active `CSB` pads (`Rule #5`)**; cap `CSB` vias (`10F->9F` `77_49_77`) at max `2` stacked vias (`Rule #14`).
   - **`4FCO` (`L11`) `eDTC`-to-EMIB Clearance (`eDTC Rules #5, #14`):** Zero `eDTC` under EMIB die; **`eDTC` Cavity Edge to EMIB Cavity Edge `>= 1,000.0 um`**.
   - **`BASE` (`L27`) `LSC` Under EMIB Prohibition (`EMIB Rule #19`):** Zero `0201` LSCs inside any EMIB-T bridge die shadow on `BASE` (tangent `>= 0.0 um` allowed — governing the `U9_POCKET_5` / `U9_POCKET_6` split around `U39`).
2. **Co-Planar Voltage-Island Split Clearance (`VDDCx` vs. `VDD_0P8_SRAM_CCx`):**
   - `>= 50.0 um` shape-to-shape spacing on `15Cu / 18Cu` Build-Up layers (`10F, 6F, 6B, 8B`), and `>= 67.5 um` on `25Cu / 35Cu` Core & Prepreg layers (`4FCO, 2FCI, 2BCI, 4BCO`) and `40 um GX92 GCP` (`12B`).
3. **Atomic Net-Matched Via Stack Termination Across 3 Nets (`VDDCx`, `SRAMx`, `VSS`):**
   - A `VDDCx` column may only start/end on a layer where `VDDCx` owns the copper island at `(x, y)` (`12F, 8F`, or `VDDCx` region of `6F/4FCO/4BCO/6B/8B/12B`) — **never** on `10F` or `10B` (`SRAMx` full-span layers) or odd `VSS` layers!
   - An `SRAMx` column may only start/end on `10F`, `10B`, or inside its carved W/E corridor island on `6F/4FCO/4BCO/6B/8B/12B` (`0` dangling vias!).
4. **`4FCO..4BCO` Shared `eDTC` KOZ (`C2215..C2220`):**
   - `100%` concentric pin landing on all `864` `eDTC` pins (`360 VDDC0 + 72 SRAM0 + 432 VSS`), `0` routing/vias on `4FCO..4BCO` (including `4BCO->5B`) inside `300 um` cavity + `150 um` guard metal + `67.5 um` spacing, and solid `5B` `VSS` plane underneath.
5. **`BASE` Mechanical Recess Cavity (`LSC_CAVITY`, `Recess PCB Design rules.pdf` `Codes A–K` + `Slide 11`) + `SMD8` `8-Via` BGA Rule:**
   - Recess depth `Z = 21 ± 4 mil` (`533 ± 102 um`, `L5` uncut, `C > 150 um` cap-to-floor); `Min Cavity >= 1,016 × 1,016 um` (`Code E`); `Cavity-to-Cavity Web >= 508.0 um` (`Code J`); `4-Corner Radius R >= 500.0 um` (`Code K` $\rightarrow$ `R_allow <= 275.0 um` at corners).
   - Co-pocket `VDDC0` + `SRAM0` LSCs must stay **`>= 225.0 um` (`Slide 11`)** inside the milled cavity wall (`SM web >= 76.0 um` + `102..152 um` pullback `Codes A/B`).
   - BGA pads bordering a cavity must obey `Code G` (`>= 250.0 um` for `NSMD` `C480_60_01B` SRO; `SMD1 >= 254.0 um` `Code H`; **`SMD8 >= 330.2 um = 13 mil` `Code I` SMO-to-recess for `8-via` SMD pads**), plus **`Code D` (`>= 178.0 um` Ext `BASE` / `>= 203.0 um` Int Signal & Non-SMT Cu KOZ)**.
6. **Mandatory `CONDUCTOR/BASE` LSC Placement, Logical Pin-Net & `180°` Cap-to-Cap Alternation (`VDDC*` & `SRAM*` / `VDDRAM*`):**
   - **Strict `CONDUCTOR/BASE` Layer Placement:** Place `100%` of `VDDCx` and `VDD_0P8_SRAM_CCx` LSCs on **`CONDUCTOR/BASE`** (`0` on `CONDUCTOR/SURFACE`) by placing with `mir = nil` first and checking `pin->startEnd` (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir = nil`; `SM0201S_690X390X220_01C` uses `mir = t`).
   - **Logical Component + Pin Nets:** Instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = VDDCx` (or `VDD_0P8_SRAM_CCx`) and `Pin "2" = VSS` via `axlChangeNet` matching `pin->number`.
   - **`180°` Cap-to-Cap Polarity Alternation (Including Co-Pocket `VDDCx` + `SRAMx`):** Across all X-columns (`550 um` pitch), rotate adjacent columns by **`180°`** (`Col 2k = 0°` [`N=VDD/S=VSS`] $\leftrightarrow$ `Col 2k+1 = 180°` [`N=VSS/S=VDD`], preserving anti-parallel `(Col 2k, Col 2k+1)` pairs even where `SRAMx` occupies outer/middle column pairs inside a shared `VDDCx + SRAMx` pocket!), and use `rot = 90°` (`W=VDDCx/SRAMx, E=VSS`) on horizontal bottom/top remainder rows bridging `(Col 2k, Col 2k+1)` pairs (or `90°` $\leftrightarrow$ `270°` across stacked horizontal rows).

---

## 5. Reference Files in This Skill Package
- [`references/lda_vddc0_sram0_learned_profile.json`](file:///<agent_workspace>/agent04_pdn_architect/skills/vddc_vddram_routing_flow/references/lda_vddc0_sram0_learned_profile.json) — Complete Ground-Truth Metrics Learned from `HH_Nguyen_2026-1023_1900_TO_v8_dump.txt`
- [`TEMPLATE.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/vddc_vddram_routing_flow/TEMPLATE.md) — Multi-Rail Configuration JSON & Pipe-Delimited Master Recipe Schema (User-Customizable)
- [`templates/vddc_vddram_all_layer_template.il`](file:///<agent_workspace>/agent04_pdn_architect/skills/vddc_vddram_routing_flow/templates/vddc_vddram_all_layer_template.il) — Reusable Multi-Rail Cadence APD SKILL Importer Template
- [`TODO.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/vddc_vddram_routing_flow/TODO.md) — Gate-Checked Execution & Customization Checklist for `VDDC*` + `VDDRAM`
