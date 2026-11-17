---
name: agent04-pdn-architect
description: >
  End-to-End 4-Stage Power Distribution Network (PDN) Architect for Cadence Allegro
  Package Designer (apd.exe / .mcm). Stage 1 (Pre-Learn): Indexes multi-format
  Stackup & Design Rule files (.xlsx, .csv, .pdf) into 6 structural zones
  (Above-BU, Above-PP/4FCO, Core, Below-PP, Below-BU, Base) and learns the Padstack
  Input Library (.pad folder + .mcm DB). Stage 2 (Multi-Zone PDN Synthesis): Plans
  RefDes/Net targets, VDD/VSS layer polarity, Above-BU stacked/staggered vias &
  VDD/VSS ratio, 4FCO eDTC landing vias/KOZ/150um Guard Metal, Core PTH density
  (8/mm² IDS, 3.5/mm² ODS) & PP-on-PTH stack, Below-BU Mirror or 4-5 Via BGA
  Clusters, and BASE empty pocket LSC placement. Stage 3 (SVG Visual Sandbox):
  Simulates and exports XML-validated SVG routing visualizations (top-down per
  zone + vertical cross-section) before touching .mcm. Stage 4 (Text Recipe &
  .mcm Import): Exports a pipe-delimited pdn_import_recipe.txt and streams it
  into .mcm via O(1) SKILL makeTable batch import.
---

# Agent 04: PDN Architect (`agent04_pdn_architect`)

## 1. Mission & 4-Stage Architecture

`agent04_pdn_architect` automates full-stackup Power Distribution Network (PDN) synthesis from `SURFACE` die bumps down to `BASE` BGA balls and Land-Side Capacitors (LSCs) without ever modifying `<pcbenv_skill_dir>/`.

```
+---------------------------------------------------------------------------------------------------+
| STAGE 1: PRE-LEARN & MULTI-FORMAT DATA INDEXING (pdn_prelearn.py + padstack_learner_batch.il)     |
|  - Stackup Classifier (.xlsx / .csv / .pdf) -> 6 Zones: Above-BU, Above-PP (4FCO), Core,          |
|    Below-PP, Below-BU, Base                                                                       |
|  - Design Rule Indexer (.xlsx / .csv / .pdf) -> Via stack limits, PTH density/pitch, eDTC KOZ &   |
|    150um Guard Metal, LSC pocket spacing & eDTC shadow exclusion                                  |
|  - Parallel Padstack Library Learner (.pad folder + axlDBGetPad) -> Layer-span & via-type table   |
|  => Output: pdn_knowledge_index.json                                                              |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
| STAGE 2: INTERACTIVE PDN PLANNING & 5-ZONE SYNTHESIS ENGINE (pdn_synthesizer.py)                  |
|  - User Targets: RefDes (e.g., U1, U2), Power/Ground Nets (VDDC0, VSS, VDDSRAM), VDD/VSS Polarity |
|  - Zone 1 (Above-BU: SURFACE..5F): Bump drop, <=7 stack limit, configurable VDD/VSS via ratio     |
|  - Zone 2 (4FCO eDTC Layer): Identify eDTC symbols, 90_65_90 via (1/pad, <=2 stack), 300um KOZ,   |
|    150um Guard Metal ring on outermost Core layers (no holes/vias), solid 1st backside BU plane   |
|  - Zone 3 (Core PTH & PP: 4FCO..4BCO): 8 PTH/mm² (IDS) / 3.5 PTH/mm² (ODS), <=5 stacked on PTH,   |
|    <=2 PPvias per PTH pad + diamond/star clines (5F/3FCI/2FCI/2BCI/3BCI/5B)                       |
|  - Zone 4 (Below-BU: 5B..12B): Mode A (Mirror Above-BU) OR Mode B (4-5 Via Cluster aligned to BGA)|
|  - Zone 5 (BASE Empty Pocket & LSC): Learn empty BGA pockets (excl. 4FCO eDTC shadow) + place LSC |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
| STAGE 3: SANDBOX SIMULATION & SVG ("VSG") VISUAL ROUTING EXPORT (pdn_svg_sandbox.py)              |
|  - Executes synthesis in an isolated coordinate sandbox (zero .mcm mutation during testing)       |
|  - Exports XML-validated, high-resolution SVGs (svg_sandbox/*.svg):                               |
|    1. pdn_vertical_cross_section.svg (Full Z-stackup from SURFACE bumps to BASE BGA/LSC)          |
|    2. zone1_above_bu_routing.svg     (Bump-to-BU vias & VDD/VSS ratio distribution)               |
|    3. zone2_4fco_edtc_guard.svg      (4FCO eDTC symbols, 90_65_90 vias, 300um KOZ, 150um Guard)   |
|    4. zone3_core_pth_ppvia.svg       (IDS/ODS PTH grid + 5-point PPvia & diamond/star clines)     |
|    5. zone4_below_bu_clusters.svg    (Mirror pattern or 4-5 Via BGA-aligned clusters)             |
|    6. zone5_base_lsc_pockets.svg     (Empty BGA pockets, eDTC shadow keepout, packed 0201/0204)   |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
| STAGE 4: PIPE-DELIMITED TEXT RECIPE & HEADLESS .MCM BATCH IMPORT (pdn_import_from_txt_batch.il)   |
|  - Compiles verified sandbox objects into pipe-delimited pdn_import_recipe.txt in cwd             |
|  - Streams pdn_import_recipe.txt into SKILL makeTable structures (O(1) lookup, zero stack overflow)|
|  - Creates all Vias, Clines, Guard Metal Shapes, KOZ Shapes, and LSC Symbols inside .mcm          |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Source SKILL `.il` Mapping (`<pcbenv_skill_dir>/`)

All original `.il` files in `<pcbenv_skill_dir>/` remain **100% untouched**. Their algorithms are consolidated into headless batch modules under `agent04_pdn_architect/scripts/`:

| Zone / Stage | Source `.il` Files in `pcbenv` | Refactored Headless Module | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **Stage 1C (Padstack Learner)** | Native `axlDBGetDesign()->padstacks` + `axlDBGetPad` | [`padstack_learner_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/padstack_learner_batch.il) | Scans `.pad` folder & `.mcm` padstacks; maps `(start_layer, end_layer)`, drill, pad size, and via category (`BU_UVIA`, `PP_VIA`, `CORE_PTH`, `EDTC_VIA`, `BGA_PAD`). |
| **Stage 1/2 (Geometry & Symbol Extractor)** | `addvia_onbump_HFC.il`, `HFC_change_pin_net_edtc.il`, `HFC_change_pin_net_bga_lsc.il` | [`pdn_design_extractor_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_design_extractor_batch.il) | Extracts RefDes (`U1`, etc.) bump pins/bbox on `SURFACE`, `eDTC` symbols/pins on `4FCO`, and BGA pins on `BASE` into pipe-delimited text files in `cwd`. |
| **Zone 1 (Above-Core BU)** | `pdn_via_placement.il`, `addvia_onbump_HFC.il`, `PDN_spider_web_routing.il`, `pdn_jog_routing.il` | [`pdn_above_bu_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_above_bu_batch.il) | Drops BU microvias from RefDes bumps across `SURFACE..5F`, enforces `<= 7` stack depth (auto-staggering beyond limit), and controls `VDD:VSS` via ratio. |
| **Zone 2 (`4FCO` eDTC Engine)** | `HFC_change_pin_net_edtc.il` + eDTC Design Rules (`eDTC DR_gid_1708488908.csv`) | [`edtc_pdn_guard_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/edtc_pdn_guard_batch.il) | Identifies `eDTC` symbols on `4FCO`, places `90_65_90` landing vias (`1/pad`, `<= 2` stack), creates `300 µm` Core cavity KOZ, and draws `150 µm` Guard Metal on `2FCI`/`2BCI`. |
| **Zone 3 (Core PTH & PP)** | `PTH_generation_and_PPvia_HFC_case2.il`, `PTH_generation_and_PPvia_HFC_case2_mod.il`, `PTH_generation_and_PPvia_HFC_case3.il` | [`PTH_and_PPvia_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/PTH_and_PPvia_batch.il) | Solves `dx`/`dy` pitch for `8 PTH/mm²` (IDS) & `3.5 PTH/mm²` (ODS), places PTH + 5-point PP/BU cluster (`+/-120.01`, `+/-76.01`, `(0,0)`) and diamond/star clines on `5F`, `3FCI`, `2FCI`, `2BCI`, `3BCI`, `5B`. |
| **Zone 4 (Below-Core BU)** | `BGA_routing.il` (Broadcom), `BGA_routing_ver2.il` (Alcedo), `BGA_routing_ver3.il` (Google) | [`pdn_below_bu_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_below_bu_batch.il) | Supports `MIRROR_ABOVE_BU` or `BGA_CLUSTER_4_5` (**4 or 5 vias per cluster** aligned to BGA ball pitch/size with radial clines). |
| **Zone 5 (`BASE` Pocket & LSC)** | `HFC_BGA_map_island_creation_HFC.il`, `HFC_Decap_placement_algorithm.il`, `HFC_Cap_placement.il` | [`lsc_pocket_placer_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/lsc_pocket_placer_batch.il) | Learns depopulated BGA pockets on `BASE` (excluding `4FCO` eDTC shadow), packs & centers `0201`/`0204` LSCs obeying `175 µm` LSC-to-LSC and `500 µm` BGA-SRO clearance. |
| **Stage 4 (Text Recipe Importer)** | Unified Pipe-Delimited Importer (`makeTable` + `infile`) | [`pdn_import_from_txt_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_import_from_txt_batch.il) | Streams `pdn_import_recipe.txt` line-by-line into `.mcm` (`VIA`, `CLINE`, `PLANE_SHAPE`, `EDTC_GUARD`, `KOZ`, `LSC_SYM`) with $O(1)$ net/padstack lookup. |

---

## 3. Indexed Design Rules Summary (`specs_and_docs/design_rules/`)

| Rule Category | Parameter | Default Indexed Value | Source Rule Sheet |
| :--- | :--- | :--- | :--- |
| **Above/Below BU Stack** | Max stacked BU vias landing on trace/shape (`<=50 µm` antipad) | **`7` layers** (`3` Front / `6` Back for HSIO `>50 µm`) | `Via Rules_gid_107930080.csv` |
| **PP-on-PTH Stack** | Max stacked vias landing on PTH (through PP) | **`5` layers** | `Via Rules_gid_107930080.csv` |
| **PP Vias per PTH Pad** | Max vias on a single PTH pad in Prepreg | **`2` vias / PTH pad** (PKG 0.3/0.5/0.8) | `Substrate Design Rules_gid_1425021083.csv` |
| **Core PTH Geometry** | Core Thickness / PTH Drill / Outer Pad / Inner Pad | **`1570 µm` / `150 µm` / `282.5 µm` / `365 µm`** | `Substrate Design Rules_gid_1425021083.csv` |
| **Core PTH Pitch** | Diff-Net Pitch (w/ inner pad) / Same-Net Pitch | **`432.5 µm` / `216.5–270 µm`** | `Substrate Design Rules_gid_1425021083.csv` |
| **Core PTH Density** | Inside Die Shadow (**IDS**) / Outside Die Shadow (**ODS**) | **`8.0 PTH/mm²` (IDS) / `3.5 PTH/mm²` (ODS)** | `Substrate Design Rules_gid_1425021083.csv` |
| **`4FCO` eDTC Via** | Landing Via Drill/Pad / Max Stack on DTC / Vias per Pad | **`90_65_90` (`65/90 µm`) / Max `2` stack / `1` via per pad** | `eDTC DR_gid_1708488908.csv` |
| **`4FCO` eDTC KOZ & Guard** | DTC-to-Cavity KOZ / Outermost Core Guard Metal Width | **`300 µm` KOZ (no core metal/via) / `150 µm` Guard Metal (no holes/vias)** | `eDTC DR_gid_1708488908.csv` |
| **`BASE` LSC Pocket Rules** | LSC-to-LSC / LSC-SRO-to-BGA-SRO / Under-eDTC Restriction | **`175 µm` / `500 µm` / `LSC Not Allowed under DTC`** | `BGALSC Rules_gid_2099350359.csv` |

---

## 4. Stage 4 Pipe-Delimited Recipe Format (`pdn_import_recipe.txt`)

To prevent SKILL stack overflow on large package substrates (50,000+ vias/clines), Stage 2 & Stage 3 write all verified PDN objects to `<cwd>/pdn_import_recipe.txt` using the following pipe-delimited schema:

```text
# AGENT04_PDN_RECIPE_V1|REFDES=U1|NETS=VDDC0,VSS,VDDSRAM
PLANE_POLARITY|LAYER=12F|NET=VSS|ZONE=ABOVE_BU
VIA|PADSTACK=V90_65_90_01A_L09_L10|X=120.010|Y=0.000|NET=VDDC0|START=5F|END=4FCO|ZONE=ZONE1_ABOVE_BU|CLUSTER=PTH_001
CLINE|LAYER=CONDUCTOR/5F|NET=VDDC0|WIDTH=50.0|X1=0.000|Y1=0.000|X2=120.010|Y2=0.000|ZONE=ZONE3_CORE_PTH
EDTC_GUARD|LAYER=CONDUCTOR/2FCI|NET=VSS|WIDTH=150.0|X1=-2500.0|Y1=-2500.0|X2=2500.0|Y2=2500.0|SYM=EDTC_1
KOZ|LAYER=CORE_ALL|TYPE=EDTC_CAVITY_300UM|X1=-2350.0|Y1=-2350.0|X2=2350.0|Y2=2350.0|SYM=EDTC_1
LSC_SYM|REFDES=C_LSC_001|SYM=LSC_0201|X=1200.000|Y=-800.000|ROT=0.0|MIRROR=NO|LAYER=BASE
```
