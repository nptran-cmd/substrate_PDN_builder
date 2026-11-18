---
name: base_lsc_bga_routing
description: >
  Step 3 (BASE / BOTTOM Layer) Empty-BGA Pocket 0201 LSC Max-Packing Placer &
  3-Option BGA/LSC Via-Cluster Routing Skill for Agent 04 (PDN Architect).
  Learns empty BGA pockets on BASE, maximizes 0201 LSC placement (evaluating
  0-deg and 90-deg grids + mixed-orientation remainder strips) while strictly
  enforcing BGA-SRO-to-LSC-SRO (>=500um) and LSC-SRO-to-LSC-SRO (>=175um or
  >=250um) rules, places 6 (12B->BASE) GCP uVias per 0201 LSC (3 per terminal
  pad), and routes BGA via clusters across 3 selectable patterns (Option 1:
  4-Via Square 2x2, Option 2: 5-Via Quincunx, Option 3: 6-Via Hex Ring).
---

# Step 3 (`BASE` / `BOTTOM` Layer) Empty-BGA Pocket `0201` LSC & 3-Option BGA Via Skill

## 1. The 3 Enforced Architectural Constraints

1. **Empty BGA Pocket Learning & `500 µm` BGA-to-LSC SRO Safe Boundary:**
   - Identifies all `8` depopulated BGA pocket rectangles (`POCKET_1` .. `POCKET_8`) on `BASE` bounded by surrounding BGA ball centers `[b_left, b_bot, b_right, b_top]`.
   - Enforces **`BGA SRO to LSC SRO >= 500.0 µm`** (`R_BGA_SRO = 240.0 µm [C480] / 280.0 µm [C560] + 500.0 µm = 740.0..780.0 µm` clearance from surrounding BGA centers to the outer `0201` LSC SRO edge).
2. **Mixed-Orientation (`0° + 90°`) Max-Packing `0201` LSC Optimizer Meeting `SRO-to-SRO` Rules:**
   - Each `0201` LSC (`S300_24_01B` pads: `348 x 348 µm` Cu pad, `300 x 300 µm` SRO, pins at `±260 µm`) has a total SRO envelope of **`300 x 820 µm`** (`0°` vertical) or **`820 x 300 µm`** (`90°` horizontal).
   - Evaluates `0°/180° Vertical Grid + 90° Horizontal Remainder Strip` vs. `90°/270° Horizontal Grid + 0° Vertical Remainder Strip` inside each pocket:
     - **At `250.0 µm` SRO-to-SRO rule (`10 uF` `0.5 mm` tall `SM0201_690X390X550_01A`, pitch = `550 x 1070 µm`):** Packs **`161` `0201` LSCs** across the 8 `U7` pockets (including `42 vertical [21 @ 0° + 21 @ 180°] + 3 horizontal @ 90° = 45` caps in `POCKET_6` and `POCKET_7`, matching the golden layout).
     - **At `175.0 µm` SRO-to-SRO rule (`1 uF` `0.2 mm` tall `SM0201S_690X390X220_01C`, pitch = `475 x 995 µm`):** Packs **`205` `0201` LSCs** across the 8 `U7` pockets (`+27.3%` more decoupling capacitance with **`0` SRO violations**!).
   - **Mandatory `CONDUCTOR/BASE` Layer, Logical Pin-Net & `180°` Cap-to-Cap Alternation Rule (`VDDUC*`/`VDDCH*`, `VDDC*`/`SRAM*`, `HBM`):**
     - **Bottom Layer (`CONDUCTOR/BASE`) Only:** Place with `mir = nil` first and check `pin->startEnd` (`SM0201_690X390X550_01A` lands on `CONDUCTOR/BASE` at `mir = nil` and flips onto `SURFACE` if `mir = t`; `SM0201S_690X390X220_01C` uses `mir = t` for `CONDUCTOR/BASE`).
     - **Logical Component + Pin Nets:** Instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) with `Pin "1" = <VDD_RAIL>` and `Pin "2" = VSS` via `axlChangeNet`.
     - **`180°` Cap-to-Cap Rotation:** Alternate `0°` (`N=VDD/S=VSS`) $\leftrightarrow$ `180°` (`N=VSS/S=VDD`) across adjacent X-columns (`Col 0, 1, 2, ...`), use `90°` (`W=VDD/E=VSS`) on horizontal bottom/top remainder rows bridging `(Col 2k, Col 2k+1)` pairs, and alternate `90°` $\leftrightarrow$ `270°` across stacked horizontal rows.
3. **`12B -> BASE` (`V90_65_90_12B_BASE_01A` `40 µm` `GX92` GCP uVia) on `LSC` Pads & 3 Selectable `BGA` Via Pattern Options:**
   - **Via on `0201` LSC Pad (`6` vias per LSC = `3` vias per `348 x 348 µm` pad):**
     - Places a 3-via bar (`±93.0 µm` spacing) on Pin 1 (`VDDUC0`) and Pin 2 (`VSS`).
   - **3 Selectable BGA Via Cluster Pattern Options (`12B -> BASE` on `C560_35_01B` / `C480_60_01B`):**
     - **`OPTION1_4VIA_SQUARE_2X2`:** `4` vias per BGA pad at `(±110.0, ±110.0) µm` (`220.0 µm` pitch).
     - **`OPTION2_5VIA_QUINCUNX`:** `5` vias per BGA pad (`1` center `(0,0)` + `4` corners `(±135.0, ±135.0) µm`, `190.9 µm` pitch).
     - **`OPTION3_6VIA_HEX_RING`:** `6` vias per BGA pad in an `R = 195.0 µm` ring (`(0, ±195.0)` & `(±137.9, ±137.9) µm`).

---

## 2. CLI & SKILL Execution Commands
```powershell
python -m agent04_pdn_architect.cad_cli.base_lsc_bga_router --sro-space 175.0
```
In Cadence Allegro / APD SKILL ([`base_lsc_bga_router_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/base_lsc_bga_router_batch.il)):
- **Mode 1 — Pipe-Delimited Recipe Stream Import:**
  ```lisp
  pdnDispatchBatchJob("BASE_LSC_BGA_ROUTE" "FALSE")
  ```
- **Mode 2 — Direct Standalone SKILL Call:**
  ```lisp
  pdn_route_base_lsc_and_bga_full_skill("OPTION2_5VIA_QUINCUNX" 175.0)
  ```
