---
name: multi_rail_plane_polygon_splitter
description: >-
  Step 1 Multi-Rail Co-Planar Polygon Splitter & (x, y, layer) Net-Ownership
  Stack Pruner for Agent 04 (pdn_architect). Synthesizes N-rail co-planar
  voltage islands across all 24 inner layers (e.g., LDA VDDC0 + carved W/E
  VDD_0P8_SRAM_CC0 islands, and HBM 4-strip VPP | VDDC | VDDQ | VDDQL5 + E-comb
  8F VPP collector), enforces >=50.0 um BU and >=67.5 um Core/PP/GCP split
  clearances, subtracts EMIB (157.5 / 200 / 372 um) & 4FCO..4BCO eDTC (517.5 um)
  keepout voids, builds an O(1) point-in-polygon net-ownership index for atomic
  via stack pruning (0 wrong-rail landings, 0 dangling vias), and maps co-pocket
  CONDUCTOR/BASE LSCs with 180-deg cap-to-cap alternation.
---

# Step 1: Multi-Rail Co-Planar Polygon Splitter (`multi_rail_plane_polygon_splitter`)

## 1. Core Architectural Capabilities

1. **Co-Planar Multi-Rail Polygon Carving (`>= 50.0 µm` BU / `>= 67.5 µm` Core, PP & `12B` GCP):**
   - Generates rectilinear / L-shaped / E-comb `PolygonIsland` shapes with automatic perimeter notch carving (`subtract_edge_notches_from_rect`) and interior `POLY_VOID` cutouts so `axlDBCreateVoid` never crosses an open shape's outer edge.
   - Supports hierarchical carved sub-islands (`LDA`: `VDDC0` main plane + West-South, West-North & East-Middle `VDD_0P8_SRAM_CC0` islands) and multi-strip partitions (`HBM`: `VPP | VDDC | VDDQ | VDDQL5`).
2. **Automatic EMIB-T & `4FCO..4BCO` `eDTC` Keepout Voiding:**
   - Punches `157.5 µm` EMIB cavity voids on `12F` / `11F`, `372.0 µm` `CSB` / `200.0 µm` Guard-Ring voids + `150.0 µm` isolated floating copper Guard Rings (`__ISOLATED__`) on `10F`, and `517.5 µm` (`300 + 150 + 67.5 µm`) `eDTC` KOZ voids across `4FCO..4BCO` while keeping `5B` solid `VSS`.
3. **Spatial `(x, y, layer)` Net-Ownership Stack Pruner (`MultiRailLayerOwnershipIndex`):**
   - Queries exact polygon + void + edge-margin ownership at `(x, y)` on every layer before placing Core `PTH`/`PP` trunks (`synthesize_multi_rail_core_pth_and_pp`), concentric `eDTC` landings (`synthesize_concentric_edtc_stacks`), or top/bottom Build-Up via stacks (`route_bottom_bga_and_lsc_with_atomic_pruning`), guaranteeing `0` wrong-rail landings and `0` dangling vias.
4. **Co-Pocket `CONDUCTOR/BASE` LSC & `LSC_CAVITY` Integration:**
   - Projects `12B` multi-rail sub-islands onto `CONDUCTOR/BASE` (`0` on `SURFACE`), preserving `180°` cap-to-cap polarity alternation (`0°` $\leftrightarrow$ `180°` across X-columns; `90°` on horizontal remainder strips) and `R = 500.0 µm` `SUBSTRATE GEOMETRY/LSC_CAVITY` contours.

## 2. CLI & SKILL Execution
```powershell
python -m agent04_pdn_architect.cad_cli.step1_step2_u9_u13_validator --dry-run
python -m agent04_pdn_architect.cad_cli.step1_step2_u9_u13_validator --out-mcm agent04_pdn_architect/MCM_test/PDN_test_Step1_Step2_U9_U13.mcm
```
* **Python Engine:** [`multi_rail_polygon_engine.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/multi_rail_polygon_engine.py)
* **Headless APD SKILL Importer:** [`multi_rail_step1_step2_implementer_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/multi_rail_step1_step2_implementer_batch.il) (`pdnImplementMultiRailStep1Step2Batch`)
