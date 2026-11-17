# Substrate PDN Builder (Agent 04 — PDN Architect)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/Bundled_Skills-19-brightgreen.svg)](#bundled-skills)
[![Agent Ready](https://img.shields.io/badge/Agent-Gemini_CLI_%7C_Antigravity-orange.svg)](#quickstart--installation)

> **Autonomous 27-layer IC package substrate Power Delivery Network (PDN) synthesis across all 4 rail groups (`Core VDDC/SRAM`, `Uncore VDDUC`, `Chiplet VDDCH`, `HBM`) and all 8 PDN routing steps, with Dynamic/Static copper shapes, multi-family `eDTC` & curved `LSC_CAVITY` recess engines, and headless Cadence Allegro / APD SKILL automation.**

---

## 📖 Overview

This repository packages the **Substrate PDN Builder (Agent 04 — PDN Architect)** with all required agent instructions (`.gemini/GEMINI.md`), **19 modular skills** (`skills/<name>/SKILL.md`), reusable Python/SKILL automation engines, and ready-to-use **Example Prompts** (`prompts/EXAMPLE_PROMPTS.md`).

### Key Architectural Highlights
- **Unified 4-Rail-Group × 8-Step PDN Pipeline (`pdn_8step_flow.py`)**: End-to-end parameterized router across **`Core` (`VDDC* + SRAM`)**, **`Uncore` (`VDDUC*`)**, **`Chiplet` (`VDDCH*`)**, and **`HBM` (`VDDQ + VDDC + VDDQL + VPP`)**:
  - **Step 1 (`SURFACE`)**: `FULL` VIP or any `M:N` ratio (`4:2`, `5:2`, `3:1`) with H/V/BOTH strapping (`0` floating bumps).
  - **Step 2 (Front BU Transition)**: Same-net BU stack (`SURFACE -> 6F VDD / 7F VSS`, `<= 7` BU spans / `<= 3` in EMIB HSIO void).
  - **Step 3 (Core PTH `4–11 PTH/mm²`)**: `PKG 0.8` (`270/432.5 um`, ceiling `9.01/8.56`) & `PKG 0.1` (`216.5/350 um`, full `4..11 PTH/mm²`), Staggered & 90° H/V, plus `eDTC` `300 um` Cavity KOZ + `150 um` Guard Metal (`700.0 um` center KOZ).
  - **Step 4 (Prepreg `PP` Patterns + Substrate DR Audit)**: `1_VIA_CENTER`, `2_VIA_ON_PTH` (`45 um` PP-PP overlap), and `4_VIA_PER_PTH` audited against max vias/PTH pad (`1 [PKG0.1] / 2 [PKG0.8]`) & `67.5 um` Core/PP L/S.
  - **Step 5 (BGA Via Clusters Options 1–4)**: `OPTION1_4VIA_SQUARE_2X2`, `OPTION2_5VIA_QUINCUNX`, `OPTION3_6VIA_HEX_RING`, plus **`OPTION4_4VIA_CENTER_ZERO_OVERLAP`** (`(±45.5, ±45.5) um`, `91.0 um` pitch, `0.0 um` pad overlap) across all VDD + `VSS` BGAs.
  - **Step 6 (`BASE` LSC + Curved Recess)**: Aligned non-zigzag & curved EDT `LSC_CAVITY` (`R=508 um`, `254 um` BGA->Cav, `225 um` LSC->Cav) with `CONDUCTOR/BASE` `180°` alternation (`u9_vddc_sram_lsc_new_rule_sandbox.py`, `curved_recess_and_lsc_engine.py`).
  - **Step 7 (Back BU Cluster Climb)**: Concentric BGA/LSC cluster climb (`BASE -> 6B VDD / 7B VSS`, `<= 7` spans, `0.0 um` overlap).
  - **Step 8 (Transition ↔ PP & Core Bridge)**: Conflict-free `6F/7F -> 5F -> 4FCO` & `6B/7B -> 5B -> 4BCO` bridges verified with `audit_via_continuity_and_zero_overlap` (`0` overlaps across 27 layers).
- **Dynamic Power/`VSS` Planes vs. Static Guard Band Metal**: Creates true Cadence APD Dynamic copper planes (`axlShapeChangeDynamicType` + `axlShapeDynamicUpdate`) while preserving `150 um` isolated Static Guard Band frames around `10F` EMIB silicon bridges and `4FCO`/`4BCO` embedded deep-trench capacitors (`eDTC`).
- **Working-Directory Output Isolation (`pdn_paths.py`)**: Respects `SUBSTRATE_WORK_DIR` so SVGs, recipes, and `.mcm` build outputs write to the active user working folder without polluting the agent source tree.

> **Note on Clean Repository Structure:** Only reusable agent definitions, skills, scripts, templates, and documentation are published here. All runtime logs, temporary dumps, and proprietary design databases are excluded via `.gitignore`.

---

## 🗂️ Repository Architecture

```text
substrate_PDN_builder/
├── .gemini/
│   └── GEMINI.md
├── cad_cli/
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── pdn_architect_tool.py
│   ├── __init__.py
│   ├── __main__.py
│   ├── apd_27layer_master_exporter.py
│   ├── audit_pdn_test_placement.py
│   ├── base_lsc_bga_router.py
│   ├── cadence_runner.py
│   ├── curved_recess_and_lsc_engine.py
│   ├── full_27layer_u7_vdduc_vss_mockup.py
│   ├── full_package_all_dies_pdn.py
│   ├── hbm_surface_and_csb_router.py
│   ├── lsc_pin_net_assigner.py
│   ├── multi_rail_polygon_engine.py
│   ├── pdn_8step_flow.py
│   ├── pdn_architect.py
│   ├── pdn_paths.py
│   ├── pdn_prelearn.py
│   ├── pdn_svg_sandbox.py
│   ├── pth_4fco_4bco_router.py
│   ├── stage1_input_builder.py
│   ├── step1_step2_u9_u13_validator.py
│   ├── surface_layer1_router.py
│   ├── u6_8step_mcm_builder.py
│   ├── u7_topside_bu_sandbox.py
│   ├── u9_vddc_sram_lsc_new_rule_sandbox.py
│   ├── u9_vddc_sram_surface_3to1_jog_router.py
│   ├── upper_left_corner_pdn.py
│   └── vdduc0_base_cavity_lsc_svg_generator.py
├── examples/
│   ├── mockup_Step1_Step2_U13_HBM_4Rail.svg
│   └── mockup_Step1_Step2_U9_MultiRail.svg
├── prompts/
│   └── EXAMPLE_PROMPTS.md
├── scripts/
│   ├── base_lsc_bga_router_batch.il
│   ├── check_pdn_test_placement_batch.il
│   ├── edtc_pdn_guard_batch.il
│   ├── full_27layer_apd_implementer_batch.il
│   ├── lsc_pin_net_assign_batch.il
│   ├── lsc_pocket_placer_batch.il
│   ├── multi_rail_step1_step2_implementer_batch.il
│   ├── padstack_learner_batch.il
│   ├── pdn_above_bu_batch.il
│   ├── pdn_below_bu_batch.il
│   ├── pdn_core_batch.il
│   ├── pdn_import_from_txt_batch.il
│   ├── pdn_Pipeline_batch.il
│   ├── pth_4fco_4bco_router_batch.il
│   ├── PTH_and_PPvia_batch.il
│   ├── stage1_full_extractor_batch.il
│   └── surface_bump_router_batch.il
├── skills/
│   ├── base_lsc_bga_routing/
│   │   └── SKILL.md
│   ├── emib_csb_and_hbm_surface_router/
│   │   └── SKILL.md
│   ├── full_27layer_apd_implementation/
│   │   └── SKILL.md
│   ├── hbm_vdd_routing_flow/
│   │   ├── references/
│   │   │   └── hbm_u13_learned_profile.json
│   │   ├── templates/
│   │   │   └── hbm_vdd_all_layer_template.il
│   │   ├── SKILL.md
│   │   ├── TEMPLATE.md
│   │   └── TODO.md
│   ├── multi_rail_plane_polygon_splitter/
│   │   └── SKILL.md
│   ├── pth_4fco_4bco_routing/
│   │   └── SKILL.md
│   ├── surface_layer1_routing/
│   │   └── SKILL.md
│   ├── vddc_vddram_routing_flow/
│   │   ├── references/
│   │   │   └── lda_vddc0_sram0_learned_profile.json
│   │   ├── templates/
│   │   │   └── vddc_vddram_all_layer_template.il
│   │   ├── SKILL.md
│   │   ├── TEMPLATE.md
│   │   └── TODO.md
│   └── vdduc_vddch_routing_flow/
│       ├── templates/
│       │   └── vdduc_vddch_all_layer_template.il
│       ├── SKILL.md
│       ├── TEMPLATE.md
│       └── TODO.md
├── tests/
│   └── test_agent04_suite.py
├── .gitignore
├── __init__.py
├── AGENTS.md
├── LICENSE
├── README.md
├── SKILL.md
├── TEMPLATE.md
└── TODO.md
```

---

## 🛠️ Bundled Skills (19 Skills)

| Skill | Description | Bundled Scripts |
| :--- | :--- | :--- |
| [`step1_surface_bump_routing`](skills/step1_surface_bump_routing/SKILL.md) | Step 1 PDN Skill: `SURFACE` FULL VIP or `M:N` ratio (`4:2`, `5:2`, `3:1`) with H/V/BOTH floating-bump jogging (`0` floating bumps). | *(Markdown Runbook)* |
| [`step2_frontside_bu_transition`](skills/step2_frontside_bu_transition/SKILL.md) | Step 2 PDN Skill: Frontside BU stack (`SURFACE -> 6F VDD / 7F VSS`) obeying `<= 7` BU limit (`<= 3` in EMIB HSIO void). | *(Markdown Runbook)* |
| [`step3_core_pth_routing`](skills/step3_core_pth_routing/SKILL.md) | Step 3 PDN Skill: Core PTH (`4..11 PTH/mm²`) Staggered / 90° H/V with `PKG0.8`/`PKG0.1` and `700 um` `eDTC` KOZ + Guard Metal. | *(Markdown Runbook)* |
| [`step4_prepreg_pp_routing`](skills/step4_prepreg_pp_routing/SKILL.md) | Step 4 PDN Skill: Prepreg (`PP`) `1_VIA_CENTER`, `2_VIA_ON_PTH`, `4_VIA_PER_PTH` patterns + Substrate DR audit. | *(Markdown Runbook)* |
| [`step5_bga_via_cluster_routing`](skills/step5_bga_via_cluster_routing/SKILL.md) | Step 5 PDN Skill: BGA `12B<->BASE` clusters (`Options 1..3` + `OPTION4_4VIA_CENTER_ZERO_OVERLAP` at `±45.5 um`) for all VDD + VSS BGAs. | *(Markdown Runbook)* |
| [`step6_base_lsc_recess_placement`](skills/step6_base_lsc_recess_placement/SKILL.md) | Step 6 PDN Skill: `CONDUCTOR/BASE` `0201` LSC packing with `180°` alternation and curved `LSC_CAVITY` recess compliance. | *(Markdown Runbook)* |
| [`step7_backside_bu_transition`](skills/step7_backside_bu_transition/SKILL.md) | Step 7 PDN Skill: Backside BGA/LSC cluster climb (`BASE -> 6B VDD / 7B VSS`) obeying `<= 7` BU stack and `0.0 um` overlap. | *(Markdown Runbook)* |
| [`step8_transition_pp_core_connection`](skills/step8_transition_pp_core_connection/SKILL.md) | Step 8 PDN Skill: Connect `6F/7F` & `6B/7B` to PP/Core (`5F->4FCO`, `4BCO->5B`) with `0` overlaps across 27 layers. | *(Markdown Runbook)* |
| [`uncore_vdduc_routing_flow`](skills/uncore_vdduc_routing_flow/SKILL.md) | End-to-End 8-Step PDN flow for Uncore `VDDUC0..3 + VSS` (`LDB` `U7/U5/U8/U6`). | *(Markdown Runbook)* |
| [`chiplet_vddch_routing_flow`](skills/chiplet_vddch_routing_flow/SKILL.md) | End-to-End 8-Step PDN flow for Chiplet `VDDCH0..3 + VSS` (`LDC` `U2/U4/U3/U1`). | *(Markdown Runbook)* |
| [`base_lsc_bga_routing`](skills/base_lsc_bga_routing/SKILL.md) | BASE Empty-BGA Pocket 0201 LSC Max-Packing & 4-Option BGA/LSC Via-Cluster Routing Skill (`Options 1..4`). | *(Markdown Runbook)* |
| [`emib_csb_and_hbm_surface_router`](skills/emib_csb_and_hbm_surface_router/SKILL.md) | Bifurcated HBM Fine-Pitch SURFACE Gang-Bar & EMIB C0 / 10F CSB Escape Router (`VU30_19_*`, lateral `8F` dogbones). | *(Markdown Runbook)* |
| [`full_27layer_apd_implementation`](skills/full_27layer_apd_implementation/SKILL.md) | End-to-end 27-layer PDN Architect Exporter and Cadence APD / Allegro SKILL Master Implementer. | *(Markdown Runbook)* |
| [`hbm_vdd_routing_flow`](skills/hbm_vdd_routing_flow/SKILL.md) | End-to-end 27-layer Multi-Rail HBM4E PDN routing flow (`U13..U24` + `U41..U52`). | *(Markdown Runbook)* |
| [`multi_rail_plane_polygon_splitter`](skills/multi_rail_plane_polygon_splitter/SKILL.md) | Multi-Rail Co-Planar Polygon Splitter & `(x, y, layer)` Net-Ownership Stack Pruner. | *(Markdown Runbook)* |
| [`pth_4fco_4bco_routing`](skills/pth_4fco_4bco_routing/SKILL.md) | Core PTH (`4..11 PTH/mm²`) & Prepreg (`1/2/4-via`) Routing Skill with `eDTC` KOZ & DR verification. | *(Markdown Runbook)* |
| [`surface_layer1_routing`](skills/surface_layer1_routing/SKILL.md) | Layer 1 (`SURFACE`) Parameterized Die Bump-Via (`FULL` or `M:N`) & Trace-Ganging Skill. | *(Markdown Runbook)* |
| [`vddc_vddram_routing_flow`](skills/vddc_vddram_routing_flow/SKILL.md) | End-to-end 27-layer Co-Resident Dual-Rail Core `VDDC*` + `VDDSRAM` (`LDA` `U9/U12/U88/U10`) routing flow. | *(Markdown Runbook)* |
| [`vdduc_vddch_routing_flow`](skills/vdduc_vddch_routing_flow/SKILL.md) | Combined Single-Power-Rail `VDDUC*` & `VDDCH*` 27-layer PDN flow reference. | *(Markdown Runbook)* |

---

## 🚀 Quickstart & Installation

### Option 1: Use Directly as a Workspace Agent
Clone this repository and launch your AI agent inside the folder (it will automatically load `.gemini/GEMINI.md` and discover `skills/`):

```bash
git clone https://github.com/nptran-cmd/substrate_PDN_builder.git
cd substrate_PDN_builder
gemini
```

### Option 2: Install Skills Globally into Your Agent Config
Copy any skill from `skills/` into your global agent skills directory (`~/.gemini/config/skills/` or `~/.gemini/skills/`) so it is available across all your workspaces:

```powershell
# PowerShell (Windows)
Copy-Item -Path ".\skills\*" -Destination "$HOME\.gemini\config\skills\" -Recurse -Force
```

```bash
# Bash (Linux / macOS)
mkdir -p ~/.gemini/config/skills
cp -r skills/* ~/.gemini/config/skills/
```

---

## 💬 Example Prompts (How to Use the Agent)

Once the agent or skills are loaded, try asking any of the following prompts (see [prompts/EXAMPLE_PROMPTS.md](prompts/EXAMPLE_PROMPTS.md) for the full 12-scenario cookbook with CLI flags and expected deliverables):

### 🔹 1. Full-Package 24-Die, 76-Rail 27-Layer `.mcm` Build (`full_package_all_dies_pdn.py`)
- *"I want to route VDDUC0..3, VDDCH0..3, VDDC0..3, SRAM0..3, and all 12 HBM rails across all 24 dies based on `@agent04_pdn_architect/MCM_test/PDN_test.mcm` and create a new `.mcm` file. Run the Stage 3 sandbox and DRC audit first, then proceed to Stage 4 `.mcm` creation."*
- *"Run the full-package 24-die 27-layer PDN synthesis in sandbox mode (`--sandbox-only`), verify 0 via pad overlaps across all 27 conductor layers and unbroken `9F->5F` / `9B->5B` `VSS` and `VDD` continuity, and generate the 3 full-package Visual Gate SVGs."*

### 🔹 2. Quadrant / Corner Subset `.mcm` Build from `master.tag` (`upper_left_corner_pdn.py`)
- *"Can you create another MCM based on `@agent04_pdn_architect/MCM_test/master.tag` only for 1 `VDDCH3` (`U1`), `VDDUC1` (`U5`), `VDDC1` and `SRAM1` (`U12`), and the `HBM` on the upper-left corner rails (`U13` / `MEM5`)? Run it in parallel in its own isolated output folder."*
- *"Create a new `.mcm` based on `@agent04_pdn_architect/MCM_test/master.tag` for the entire upper-left quadrant including `U1` (`VDDCH3`), `U5` (`VDDUC1`), `U12` (`VDDC1` + `VDD_0P8_SRAM_CC1`), and all 3 upper-left HBM dies (`U13 MEM5`, `U14 MEM4`, `U15 MEM3`)."*

### 🔹 3. Single-Rail `VDDUC*` & `VDDCH*` 27-Layer Flow (`vdduc_vddch_routing_flow`)
- *"Use the `vdduc_vddch_routing_flow` skill to route the full 27-layer PDN for `U7` (`VDDUC0` and `VSS`) and `U2` (`VDDCH0` and `VSS`) with 100% `SURFACE` VIP, concentric `4FCO` `eDTC` stacks, unbroken `9F->5F` / `9B->5B` trunks, and `180°` alternating `CONDUCTOR/BASE` LSCs."*

### 🔹 4. Co-Resident Dual-Rail `VDDC0..3` + `VDD_0P8_SRAM_CC0..3` (`vddc_vddram_routing_flow`)
- *"Use the `vddc_vddram_routing_flow` skill to synthesize the 27-layer co-resident dual-rail PDN for `U9` (`VDDC0` + `VDD_0P8_SRAM_CC0` + `VSS`), including the `3:1` vertical jog `SURFACE` strapping, `10F` West-to-East `SRAM` bridge backbone, real `N24792-018` `eDTC` keepout voids, and co-pocket `BASE` LSCs."*

### 🔹 5. `HBM4E` Multi-Rail (`VDDQ`, `VDDC`, `VDDQL`, `VPP`, `HBMPHY` + `EMIB`) (`hbm_vdd_routing_flow`)
- *"Use `hbm_vdd_routing_flow` and `emib_csb_and_hbm_surface_router` to route `U13` (`MEM5`: `VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5`, `VDDQL5`, `VPP_1P8_HBM_MEM5`, `VDD_0P75_HBMPHY_UC5`, and `VSS`) with West `SURFACE` copper gang-bars, East `U41` `EMIB` `C0` routing, and `10F CSB` lateral `8F` dogbone escapes."*

### 🔹 6. `BASE` (`L27`) Curved Mechanical Recess Cavity & `180°` `0201` LSC Placement (`base_lsc_bga_routing`)
- *"Use the `base_lsc_bga_routing` skill and `curved_recess_and_lsc_engine.py` to synthesize all curved `BASE` mechanical recess cavities (`R=500 um`, `>=250 um` BGA-to-cavity, `>=225 um` LSC-to-cavity) and pack `0201` LSCs on `CONDUCTOR/BASE` with `180°` cap-to-cap polarity alternation and `Pin 1 = VDD*` / `Pin 2 = VSS` net assignments."*

### 🔹 7. Layer 1 (`SURFACE`) Bump-Via Ratios & Core `PTH` (`4FCO ↔ 4BCO`) Sweeps
- *"Use the `surface_layer1_routing` skill on `U7` (`VDDUC0` and `VSS`) to compare 100% Full VIP against a `5:2` `VDD:VSS` bump-via ratio with `HORIZONTAL`, `VERTICAL`, and `BOTH` 2D `24 um` `SURFACE` strapping."*
- *"Use the `pth_4fco_4bco_routing` skill on `U7` (`VDDUC0` / `VSS`) to sweep Core PTH densities of `5, 6, 7, and 8 PTH/mm²` across both Staggered and `90°` Orthogonal H/V patterns, subtract all `4FCO` `eDTC` keepouts, and generate a 4-panel density comparison SVG."*


---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
