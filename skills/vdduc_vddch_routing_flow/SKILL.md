---
name: vdduc_vddch_routing_flow
description: End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) PDN routing flow for `VDDUC*` (`VDDUC0..3` on `LDB` dies `U5..U8`) and `VDDCH*` (`VDDCH0..3` on `LDC` dies `U1..U4`) with `VSS` return. Enforces parameterized `M:N` `SURFACE` bump-via ratios (`FULL`, `4:2`, `5:2`, `3:1`) with pure `HORIZONTAL`/`VERTICAL`/`BOTH` strapping, concentric `4FCO` `eDTC` & Core `PTH`/`PP` alignment, strict `4FCO..4BCO` `eDTC` KOZ (`300 um` cavity + `150 um` guard metal + `67.5 um` spacing), atomic `2-via` net-matched plane stack pruning (`0` overlaps, `0` dangling vias), `BASE` Mechanical Recess (`LSC_CAVITY` `R=500 um`, `250 um` BGA->Cav, `225 um` LSC->Cav, `178/203 um` Signal/Cu KOZ) `0201` LSC packing, and headless Cadence APD `.mcm` instantiation.
---

# `VDDUC` and `VDDCH` All-Layer (27-Layer) PDN Routing Flow

## 1. Scope & Target Power Domains (`Hutton Hill` / `HFC` 9-8-9 Stackup)

This skill standardizes the complete **Single-Power-Rail + `VSS` Return** 27-layer substrate PDN architecture (`SURFACE` L01 $\rightarrow$ `BASE` L27) validated on `PDN_test_mock1.mcm` and `PDN_test_mock2.mcm`:

| Domain Family | Rail Names | Connected Compute Die (`RefDes` & Symbol) | C4 Bumps (`VDD` / `VSS`) | `4FCO` `eDTC` Symbols | `BASE` BGAs (`C480` / `C560`) | Golden `BASE` `0201` LSCs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`VDDUC*`** | `VDDUC0`, `VDDUC1`, `VDDUC2`, `VDDUC3` | `U7`, `U8`, `U5`, `U6` (`HUTTON_HILL_LDB_BC_A0`) | `7,584` `VDD` / `7,962` `VSS` | `5` per die (`2 × 144`-pin `018` + `3 × 24`-pin `016`, e.g. `C2238, C2239, C2209..C2211`) | `107` `VDD` + surrounding `VSS` | `90` (`2` core pockets × `45` `10uF`) |
| **`VDDCH*`** | `VDDCH0`, `VDDCH1`, `VDDCH2`, `VDDCH3` | `U2`, `U4`, `U3`, `U1` (`HUTTON_HILL_LDC_BC_A0`) | `6,976–6,978` `VDD` / `~5,830` `VSS` | `2` per die (`2 × 48`-pin `017`, e.g. `C2277, C2278` for `VDDCH0`) | `98–109` `VDD` + surrounding `VSS` | `67` (`0201 10uF` in `LDC` north/south pockets) |

---

## 2. 27-Layer Alternating Polarity & Zone Architecture

All 24 inner plane layers (`12F` L03 through `12B` L26) alternate strictly between **`VDD` (`VDDUCx` / `VDDCHx`)** and **`VSS`** to minimize loop inductance and enforce atomic net-matched via stack termination:

| Zone | Layers (`L01..L27`) | Layer Polarity Assignment | Via Padstacks & Routing Rules |
| :--- | :--- | :--- | :--- |
| **Zone 1A (`SURFACE` + `C0` EMIB)** | `L01: SURFACE` (`TOP`) $\rightarrow$ `L02: C0` (EMIB Only) / `L03: 12F` (C4) | C4 Die Bumps + `24 um` `SURFACE` Straps + EMIB uBumps | **C4 Region:** `V77_49_77_SURFACE_12F_01A` (`FULL` or `M:N` w/ pure `HORIZONTAL` `dy=0` / `VERTICAL` `dx=0` / `BOTH` `24 um` straps, `>=18 um` space, `0` floating bumps). **EMIB Rules #15–#18:** `C0` allowed **only** inside EMIB-T bridge die (`U28, U32, U35, U38, U47..U49` on `U7`; `U35, U39` on `U2`) via `VU30_19_35_SURFACE_C0_01B`; zero non-EMIB shapes/traces/vias on `C0`. |
| **Zone 1B (Upper BU + EMIB Cavity/CSB)** | `12F (VDD)`, `11F (VSS)`, `10F (VDD)`, `9F (VSS)`, `8F (VDD)`, `7F (VSS)`, `6F (VDD)`, `5F (VSS)` | Even `F` = `VDD` Planes<br>Odd `F` = `VSS` Planes<br>+ **EMIB KOZ Voiding on `12F/11F/10F`** | **EMIB Rules #2–#14 (`12F/11F/10F`):**<br>• `12F` (`Surface-1`) & `11F` (`Surface-2`): Void all planes/vias/traces inside `EMIB_Die + 75 um (cavity) + 82.5 um = 157.5 um` KOZ.<br>• `10F` (`Surface-3` CSB floor): Zero plane/trace under EMIB die (`Rule #7`); **`150 um` isolated copper Guard Ring** starting at EMIB die edge (`Rules #6,#22,#23`); C4 via/plane `>= 50 um` from Guard Ring (`= 200 um` from EMIB die, `Rule #8`) & **`>= 372 um` from `CSB` pads (`Rule #5`)**; active `CSB` pads (`77 um` @ `>=130 um` pitch) drop via `77_49_77` to `9F` (max `2-stack` under CSB, `Rules #13,#14`).<br>• **Atomic `2-via` net-matched pruning** at `10F/9F` (`0` overlaps, `0` dangling vias). |
| **Zone 2 (`4FCO` `eDTC`)** | `L11: 4FCO` (`S200M_0_4FCO_01A` / `C200M_0_4FCO_01A`) | Co-planar `VDD` Plane + `eDTC` Terminal Pads | **`100%` concentric (`0.0 um` offset)** `V90_65_121_5F_4FCO_01A` / `V90_65_90` on every `eDTC` pin (`6F->5F->4FCO` `2-stack` for `VDD`, `5F->4FCO` `1-stack` for `VSS`). **eDTC-to-EMIB Rules:** DTC prohibited under EMIB die (`Rule #14`); **DTC Cavity to EMIB Cavity `>= 1,000 um`** (`Rule #5`). **Strict `4FCO..4BCO` `eDTC` KOZ:** `300 um` cavity + `150 um` guard metal + `67.5 um` spacing (`0` PTHs, `0` PP vias, and `0` `4BCO->5B` vias inside `eDTC` KOZ; closed plane voids on `4FCO..4BCO`; continuous solid `VSS` plane on `5B`). |
| **Zone 3 (Core + PP)** | `4FCO (VDD)` $\rightarrow$ `3FCI (VSS)` $\rightarrow$ `2FCI..2BCI` $\rightarrow$ `3BCI (VSS)` $\rightarrow$ `4BCO (VDD)` | `2FCI/2BCI/4FCO/4BCO` = `VDD`<br>`3FCI/1FCI/1BCI/3BCI` = `VSS` | Core PTH `V282_5_150_282_5_2FCI_2BCI_01B` (`VDD`) / `02A` (`VSS`) at **`5.0..8.0 PTH/mm²`** (`STAGGERED`, `ORTHO_V`, `ORTHO_H`; same-net pitch `>= 270 um`, diff-net `>= 432.5 um`). **`100%` concentric (`0.0 um` offset)** Prepreg (`V175_85_175_*`, `85 um` drill) & adjacent `5F->4FCO` / `4BCO->5B` BU vias on PTH centers. |
| **Zone 4 (Backside BU)** | `5B (VSS)`, `6B (VDD)`, `7B (VSS)`, `8B (VDD)`, `9B (VSS)`, `10B (VDD)`, `11B (VSS)`, `12B (VDD)` | Odd `B` = `VSS` Planes<br>Even `B` = `VDD` Planes | `V121_65_90_4BCO_5B_01A`, `V90_65_90` (`5B..9B`), `V77_49_77` / `V83_55_83` (`9B..12B`). Atomic `2-via` net-matched pruning on `9B/10B` (`0` overlaps, `0` dangling vias). Continuous `11B` (`L25`) `VSS` plane shields `10B` signals from `12B->BASE` antipads. |
| **Zone 5 (`BASE` + EMIB Shadow + Cavity Recess + `180°` LSC Alternation)** | `L27: BASE` (`BOTTOM`) + `40 um GX92 GCP` (`12B -> BASE`) | `BGA` (`C480`/`C560`) + `0201` `LSC` (`S300_24_01B` on `CONDUCTOR/BASE`) + `LSC_CAVITY` | `V90_65_90_12B_BASE_01A` (`6` vias/LSC = `3`/pad; `4/5/6-via` clusters on BGA). **Mandatory `CONDUCTOR/BASE` Layer, Pin-Net & `180°` Cap-to-Cap Rule:** Place LSCs strictly on `CONDUCTOR/BASE` (`mir=nil` first + `pin->startEnd` verification; `0` on `SURFACE`), instantiate logical discrete components (`Pin "1" = VDDUCx/VDDCHx`, `Pin "2" = VSS`), and **rotate adjacent side-by-side LSCs by `180°` cap-to-cap** (`Col 2k = 0°` [`N=VDD/S=VSS`] $\leftrightarrow$ `Col 2k+1 = 180°` [`N=VSS/S=VDD`] across X-columns; `rot = 90°` [`W=VDD/E=VSS`] on horizontal bottom/top rows bridging `(Col 2k, Col 2k+1)` pairs). **EMIB Rule #19:** **`LSC` strictly prohibited inside any EMIB-T bridge die shadow on `BASE`**. **Mechanical Recess (`SUBSTRATE GEOMETRY/LSC_CAVITY`) Rule:** `BGA SRO->Cav >= 250 um` (`Code G`; `SMD1 >= 254 um`, `SMD8 >= 330.2 um` `Codes H/I`), `LSC SRO->Cav >= 225 um` (`Slide 11`), `4-Corner Radius R >= 500 um` (`Code K` $\rightarrow$ `R_allow <= 275 um`), `Min Cavity >= 1016x1016 um` (`Code E`), `Web >= 508 um` (`Code J`), `SM web >= 76 um + 102..152 um pullback` (`Codes A/B`), `Signal/Cu KOZ >= 178 um Ext / 203 um Int` (`Code D`). |

---

## 3. Step-by-Step Execution Commands

### Step 1: Generate & Inspect Layer-by-Layer SVG Mockups (Visual Gate)
```powershell
# 1A. Layer 1 (SURFACE) — e.g. 3:1 VDD:VSS Ratio with Pure HORIZONTAL Floating-Bump Straps:
python -m agent04_pdn_architect.cad_cli.surface_layer1_router --ratio 3:1 --direction HORIZONTAL --cell-period 3

# 1B. Core + Prepreg (4FCO <-> 4BCO) — e.g. 7.0 PTH/mm² Staggered with 5-eDTC KOZ:
python -m agent04_pdn_architect.cad_cli.pth_4fco_4bco_router --density 7.0 --pattern STAGGERED

# 1C. Bottom (BASE) — VDDUC0 / VDDCHx LSC Placement + R=500um Mechanical Recess Cavity Rule SVG:
python -m agent04_pdn_architect.cad_cli.vdduc0_base_cavity_lsc_svg_generator --both
```

### Step 2: Export Complete 27-Layer Master Recipe & Verify `0` Overlaps / `0` Dangling Vias
```powershell
python -m agent04_pdn_architect.cad_cli.apd_27layer_master_exporter `
  --surface-ratio "3:1" `
  --surface-dir "HORIZONTAL" `
  --pth-density 7.0 `
  --pth-pattern "STAGGERED" `
  --bga-option "OPTION3_6VIA_HEX_RING" `
  --lsc-sro-um 250.0
```

### Step 3: Instantiate Headlessly into Target `.mcm` Database via Cadence APD
```powershell
# Uses C:\Cadence\SPB_25.1\tools\bin\apd.exe -product Allegro_Adv_Packaging_Plus -nographic
python -c "
from pathlib import Path
from agent09_via_routing.cad_cli.runner import CadenceBatchRunner
runner = CadenceBatchRunner()
res = runner.run_scr(
    mcm_path=Path('agent04_pdn_architect/MCM_test/PDN_test.mcm'),
    scr_path=Path('agent04_pdn_architect/MCM_test/run_implement_mock2.scr'),
    timeout_sec=600,
)
print(res)
"
```

---

## 4. Reference Files in This Skill Package
- [`TEMPLATE.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/vdduc_vddch_routing_flow/TEMPLATE.md) — Input JSON Configuration Contract & Pipe-Delimited Master Recipe Format
- [`templates/vdduc_vddch_all_layer_template.il`](file:///<agent_workspace>/agent04_pdn_architect/skills/vdduc_vddch_routing_flow/templates/vdduc_vddch_all_layer_template.il) — Reusable Cadence APD SKILL All-Layer Importer Template
- [`TODO.md`](file:///<agent_workspace>/agent04_pdn_architect/skills/vdduc_vddch_routing_flow/TODO.md) — Gate-Checked Execution Checklist for `VDDUC*` and `VDDCH*` Domains
