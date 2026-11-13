# Substrate PDN Builder (Agent 04 — PDN Architect)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/Bundled_Skills-9-brightgreen.svg)](#bundled-skills)
[![Agent Ready](https://img.shields.io/badge/Agent-Gemini_CLI_%7C_Antigravity-orange.svg)](#quickstart--installation)

> **Autonomous 27-layer IC package substrate Power Delivery Network (PDN) synthesis, Dynamic/Static copper shape builder, multi-family eDTC & LSC recess cavity engine, and headless Cadence Allegro / APD SKILL automation agent.**

---

## 📖 Overview

This repository packages the **Substrate PDN Builder (Agent 04 — PDN Architect)** with all required agent instructions (`.gemini/GEMINI.md`), modular skills (`skills/<name>/SKILL.md`), reusable automation scripts, and ready-to-use **Example Prompts** (`prompts/EXAMPLE_PROMPTS.md`).

### Key Architectural Highlights
- **Multi-Domain 27-Layer PDN Synthesis (`SURFACE` -> `BASE`)**: Supports single-rail (`VDDUC*`, `VDDCH*`), dual co-resident (`LDA` `VDDC*` + `VDD_0P8_SRAM_CC*`), and 4-rail HBM4E + EMIB (`VDDQ`, `VDDC`, `VDDQL`, `VPP` + `VSS`) domains.
- **Dynamic Power/`VSS` Planes vs. Static Guard Band Metal**: Creates true Cadence APD Dynamic copper planes (`axlShapeChangeDynamicType` + `axlShapeDynamicUpdate`) while preserving `150 um` isolated Static Guard Band frames around `10F` EMIB silicon bridges and `4FCO`/`4BCO` embedded deep-trench capacitors (`eDTC`).
- **Real Multi-Family `eDTC` Silicon Die & KOZ Engine**: Computes exact per-family silicon die, `+300 um` cavity, `+150 um` inner-core KOZ, and `+67.5 um` `4FCO`/`4BCO` plane KOZ boundaries (`N24792-018` `144p`, `N24792-017` `48p`, `N24792-016` `24p`).
- **`BASE` LSC Placement, `180 deg` Cap-to-Cap Alternation & `recess_cavity_pdn` KOZ**: Places discrete LSCs strictly on `CONDUCTOR/BASE` with logical pin net assignments (`Pin 1 = VDD*`, `Pin 2 = VSS`), `180 deg` cap-to-cap polarity alternation, and designer-checkable mechanical recess KOZ contours (`+178 um` outer / `-225 um` inner / `R = 500 um`) on `SUBSTRATE GEOMETRY/recess_cavity_pdn`.
- **Zero-Via-Overlap 27-Conductor Continuity (`9F -> 5F` & `9B -> 5B`)**: Enforces positive copper-to-copper pad clearance on every shared conductor layer (`0` duplicate or staggered pad overlaps) and verifies post-route 3D open/short connectivity (`0` rats, `0` open `10F` bridge pins, `0` floating branches, `0` copper shorts).

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
│   ├── full_27layer_u7_vdduc_vss_mockup.py
│   ├── hbm_surface_and_csb_router.py
│   ├── lsc_pin_net_assigner.py
│   ├── multi_rail_polygon_engine.py
│   ├── pdn_architect.py
│   ├── pdn_prelearn.py
│   ├── pdn_svg_sandbox.py
│   ├── pth_4fco_4bco_router.py
│   ├── stage1_input_builder.py
│   ├── step1_step2_u9_u13_validator.py
│   ├── surface_layer1_router.py
│   ├── u7_topside_bu_sandbox.py
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

## 🛠️ Bundled Skills

| Skill | Description | Bundled Scripts |
| :--- | :--- | :--- |
| [`base_lsc_bga_routing`](skills/base_lsc_bga_routing/SKILL.md) | Step 3 (BASE / BOTTOM Layer) Empty-BGA Pocket 0201 LSC Max-Packing Placer & 3-Option BGA/LSC Via-Cluster Routing Skill for Agent 04 (PDN Architect). Learns e... | *(Markdown Runbook)* |
| [`emib_csb_and_hbm_surface_router`](skills/emib_csb_and_hbm_surface_router/SKILL.md) | Step 2 Bifurcated HBM Fine-Pitch SURFACE Gang-Bar & EMIB C0 / 10F CSB Escape Router for Agent 04 (pdn_architect). Routes East EMIB overlap bumps onto C0 (VU3... | *(Markdown Runbook)* |
| [`full_27layer_apd_implementation`](skills/full_27layer_apd_implementation/SKILL.md) | End-to-end 27-layer (`SURFACE` L01 to `BASE` L27) PDN Architect Exporter and Cadence APD / Allegro SKILL Master Implementer (`apd_27layer_master_exporter.py`... | *(Markdown Runbook)* |
| [`hbm_vdd_routing_flow`](skills/hbm_vdd_routing_flow/SKILL.md) | End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) Multi-Rail HBM4E PDN routing flow for `U13` (`MEM5`: `VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5... | *(Markdown Runbook)* |
| [`multi_rail_plane_polygon_splitter`](skills/multi_rail_plane_polygon_splitter/SKILL.md) | Step 1 Multi-Rail Co-Planar Polygon Splitter & (x, y, layer) Net-Ownership Stack Pruner for Agent 04 (pdn_architect). Synthesizes N-rail co-planar voltage is... | *(Markdown Runbook)* |
| [`pth_4fco_4bco_routing`](skills/pth_4fco_4bco_routing/SKILL.md) | Step 2 (4FCO <-> 4BCO) Core PTH & Prepreg Via-Stack Routing Skill for Agent 04 (PDN Architect). Solves staggered or 90-degree orthogonal (H&V aligned) same-n... | *(Markdown Runbook)* |
| [`surface_layer1_routing`](skills/surface_layer1_routing/SKILL.md) | Layer 1 (SURFACE / TOP) Parameterized Die Bump-Via & Trace-Ganging Skill for Agent 04 (PDN Architect). Routes any target RefDes (e.g., U7) on SURFACE (12Cu)... | *(Markdown Runbook)* |
| [`vddc_vddram_routing_flow`](skills/vddc_vddram_routing_flow/SKILL.md) | End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) Co-Resident Dual-Power-Rail PDN routing flow for `VDDC*` (`VDDC0..3`) and `VDDSRAM` (`VDD_0P8... | *(Markdown Runbook)* |
| [`vdduc_vddch_routing_flow`](skills/vdduc_vddch_routing_flow/SKILL.md) | End-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) PDN routing flow for `VDDUC*` (`VDDUC0..3` on `LDB` dies `U5..U8`) and `VDDCH*` (`VDDCH0..3`... | *(Markdown Runbook)* |

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

Once the agent or skills are loaded, try asking any of the following prompts (see [prompts/EXAMPLE_PROMPTS.md](prompts/EXAMPLE_PROMPTS.md) for the full prompt library):

### 🔹 `base_lsc_bga_routing`
- *"Use the `base_lsc_bga_routing` skill to step 3 (BASE / BOTTOM Layer) Empty-BGA Pocket 0201 LSC Max-Packing Placer & 3-Option BGA/LSC Via-Cluster Routing Skill for Agent 04 (PDN Architect) on my input files."*
- *"Run `base_lsc_bga_routing` and summarize the key findings and generated outputs in a markdown table."*

### 🔹 `emib_csb_and_hbm_surface_router`
- *"Run `emib_csb_and_hbm_surface_router` to audit die placement coordinates, bump pitch compliance, and HBM/C4 offset alignment."*

### 🔹 `full_27layer_apd_implementation`
- *"Use the `full_27layer_apd_implementation` skill to end-to-end 27-layer (`SURFACE` L01 to `BASE` L27) PDN Architect Exporter and Cadence APD / Allegro SKILL Master Implementer (`apd_27layer_master_exporter on my input files."*
- *"Run `full_27layer_apd_implementation` and summarize the key findings and generated outputs in a markdown table."*

### 🔹 `hbm_vdd_routing_flow`
- *"Run `hbm_vdd_routing_flow` to audit die placement coordinates, bump pitch compliance, and HBM/C4 offset alignment."*

### 🔹 `multi_rail_plane_polygon_splitter`
- *"Use the `multi_rail_plane_polygon_splitter` skill to step 1 Multi-Rail Co-Planar Polygon Splitter & (x, y, layer) Net-Ownership Stack Pruner for Agent 04 (pdn_architect) on my input files."*
- *"Run `multi_rail_plane_polygon_splitter` and summarize the key findings and generated outputs in a markdown table."*

### 🔹 `pth_4fco_4bco_routing`
- *"Use the `pth_4fco_4bco_routing` skill to step 2 (4FCO <-> 4BCO) Core PTH & Prepreg Via-Stack Routing Skill for Agent 04 (PDN Architect) on my input files."*
- *"Run `pth_4fco_4bco_routing` and summarize the key findings and generated outputs in a markdown table."*

### 🔹 `surface_layer1_routing`
- *"Use the `surface_layer1_routing` skill to run a full Open/Short and 3D Die/Bridge/BGA connectivity DRC check on `path/to/design.mcm` and build an interactive HTML5 DRC viewer."*
- *"Check `path/to/design.mcm` for degassing-hole copper overlap and reference-plane split crossings, and inject DRC bowtie markers into Allegro."*

### 🔹 `vddc_vddram_routing_flow`
- *"Use the `vddc_vddram_routing_flow` skill to end-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) Co-Resident Dual-Power-Rail PDN routing flow for `VDDC*` (`VDDC0 on my input files."*
- *"Run `vddc_vddram_routing_flow` and summarize the key findings and generated outputs in a markdown table."*

### 🔹 `vdduc_vddch_routing_flow`
- *"Use the `vdduc_vddch_routing_flow` skill to end-to-end (A-to-Z) 27-layer (`SURFACE` L01 through `BASE` L27) PDN routing flow for `VDDUC*` (`VDDUC0 on my input files."*
- *"Run `vdduc_vddch_routing_flow` and summarize the key findings and generated outputs in a markdown table."*


---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
