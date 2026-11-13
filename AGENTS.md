# Agent 04 (`pdn_architect`) — Multi-Agent Handoff & Orchestration Protocol

## 1. Upstream Inputs to Agent 04
- **From User / Spec Repository (`specs_and_docs/`):**
  - Stackup file (`.xlsx`, `.csv`, or `.pdf`)
  - Design Rule file(s) (`.xlsx`, `.csv`, or `.pdf`)
  - Padstack Input Library folder (`.pad` files + `.mcm` database)
  - Routing targets: `RefDes` (`U1`, `U2`, ...), `Net Names` (`VDDC0`, `VSS`, `VDDSRAM`, ...), and `VDD`/`VSS` layer polarity assignments.
- **From Agent 01 ([`agent01_bga_symbol_creation`](file:///<agent_workspace>/agent01_bga_symbol_creation/SKILL.md)):**
  - `BASE` (`Bottom`) BGA ball map and net assignments (`c560_35_01a`) used by Zone 4 (BGA-Aligned 4–5 Via Clusters) and Zone 5 (Empty Pocket Learner).
- **From Agent 02 (`floorplan_manager`):**
  - Die bump locations on `SURFACE` (`U1`, `U2`) and `4FCO` embedded component (`eDTC`) placements.

## 2. Internal Sub-Agent / Skill Delegation
- **To Agent 03 ([`agent03_decap_placement`](file:///<agent_workspace>/agent03_decap_placement/SKILL.md)):**
  - Zone 5 (`BASE` Empty Pocket LSC Placement) delegates rectangle-packing and centroid centering of `0201`/`0204` LSCs inside the learned empty BGA pockets (after subtracting `4FCO` `eDTC` shadow keepouts).
- **To Agent 09 ([`agent09_via_routing`](file:///<agent_workspace>/agent09_via_routing/SKILL.md)):**
  - Invokes low-level via counting (`count_via_by_net_batch.il`), stacked via depth verification (`stacked_via_report_batch.il`), and DRC via cleanup (`removeviaDRC_v2_batch.il`).

## 3. Downstream Handoffs from Agent 04
- **Stage 3 Visual Gate (`svg_sandbox/*.svg`):**
  - Presents XML-validated SVG visualizations of all 5 routing zones and the vertical cross-section for user review before committing changes to `.mcm`.
- **Stage 4 `.mcm` Batch Import (`pdn_import_recipe.txt` $\rightarrow$ `pdn_import_from_txt_batch.il`):**
  - Streams the pipe-delimited recipe into the `.mcm` layout and hands off the updated `.mcm` to **Agent 10 (`dfm_checker`)** and **Agent 11 (`sipi_extractor`)** for post-route DRC and PowerDC/PowerSI loop-inductance verification.

## 4. Mandatory `BASE` LSC Layer, Pin-Net & `180°` Cap-to-Cap Alternation Invariants (All Domains: `VDDUC*`/`VDDCH*`, `VDDC*`/`SRAM*`, `HBM` Rails)
1. **Strict `CONDUCTOR/BASE` (Bottom Layer) Pad Placement:**
   - Every LSC pin must land on `CONDUCTOR/BASE` (`0` pins on `CONDUCTOR/SURFACE`). In SKILL, place with `mir = nil` first and inspect `pin->startEnd` (`SM0201_690X390X550_01A` is natively `CONDUCTOR/BASE` at `mir = nil`, whereas `mir = t` flips it onto `CONDUCTOR/SURFACE`; `SM0201S_690X390X220_01C` flips to `CONDUCTOR/BASE` at `mir = t`).
2. **Logical Component + Electrical Pin Nets:**
   - Unattached package symbols reject `axlChangeNet`. Always instantiate logical discrete components (`LSC_DEV_<symName>.txt` + `axlDBCreateComponent` + `axlDBCreateSymbol`) and assign `Pin "1" = <VDD_RAIL>` and `Pin "2" = VSS` matching `pin->number`.
3. **`180°` Cap-to-Cap Polarity Alternation:**
   - Rotate adjacent side-by-side LSCs by `180°` (`Col 2k = 0°` [`N=VDD / S=VSS`] $\leftrightarrow$ `Col 2k+1 = 180°` [`N=VSS / S=VDD`] across vertical columns; `rot = 90°` [`W=VDD / E=VSS`] on horizontal bottom/top remainder rows bridging `(Col 2k, Col 2k+1)` pairs, or `90°` $\leftrightarrow$ `270°` across stacked horizontal rows) across all `VDDUC*`, `VDDCH*`, `VDDC*`, `VDD_0P8_SRAM_CC*`, and `HBM` (`VDDQ_0P85_HBM_MEM*`, `VDDC_1P0_HBM_MEM*`, `VDDQL*`) pockets.

## 5. Mandatory `9F -> 5F` & `9B -> 5B` Vertical Continuity & Strict Zero Via Pad Overlap Invariants
1. **Unbroken `VSS` & `VDD` Middle-Buildup Trunks (`9F -> 5F` and `9B -> 5B`):**
   - Never leave `VSS` or `VDD` open between upper buildup (`SURFACE..9F`/`8F`) and Core/eDTC (`6F`/`5F`) or between Core (`5B`/`6B`) and lower backside buildup (`8B`/`9B..BASE`). Always synthesize dedicated `VSS` (`9F->8F->7F->6F->5F` and `5B->6B->7B->8B->9B[->10B->11B]`) and `VDD` (`10F/8F->6F` and `6B->8B/10B/12B`) stitch arrays across every domain (`<= 7` stacked BU vias, `<= 5` landing on PTH, `<= 2` under `10F CSB` and `4FCO eDTC`).
2. **Strict Per-Conductor-Layer Zero Via Pad Overlap (`0` Overlap Allowed):**
   - Check clearance on **every conductor layer (`COND_<layer>`)** touched by a padstack (`PADSTACK_CONDUCTOR_RADII`), never only per dielectric span (`start_end`), so neither same-span vias nor staggered adjacent-span vias sharing a conductor layer (`9F`, `8F`, `7F`, `6F`, `5F`, `5B`, `6B`, `7B`, `8B`, `9B`, `10B`, `11B`, `12B`, `BASE`, `SURFACE`) can ever overlap (`dist >= r1 + r2 + min_edge_gap`). Always run `audit_via_continuity_and_zero_overlap` (`non_concentric_pad_overlap_count == 0`) before `.mcm` generation.
