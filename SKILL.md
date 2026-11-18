---
name: agent04-pdn-architect
description: >
  End-to-End 27-Layer Power Delivery Network (PDN) Architect across all 4 Rail Groups
  (Core VDDC/SRAM, Uncore VDDUC, Chiplet VDDCH, HBM4E) and all 8 PDN Routing Steps
  (Step 0 Stage 1 Extract -> Steps 1..8 Surface, BU, Core PTH, PP, BGA, BASE LSC &
  Curved Recess, Backside BU, Core Bridge) with strict working-folder isolation
  (SUBSTRATE_WORK_DIR), XML-validated SVG Visual Sandbox, and headless Cadence APD
  (.mcm) SKILL automation.
---

# Agent 04: Substrate PDN Builder (`agent04_pdn_architect`)

> **Team Onboarding & Rollout Docs:** [USER_GUIDELINE.md](USER_GUIDELINE.md) · [TODO.md](TODO.md) · [TEMPLATE.md](TEMPLATE.md) · [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md)

---

## 1. Mission & 4-Rail × 8-Step Architecture

`agent04_pdn_architect` automates full-stackup 27-layer (`SURFACE` L01 $\rightarrow$ `BASE` L27) PDN synthesis across **Core (`VDDC* + VDDSRAM`)**, **Uncore (`VDDUC*`)**, **Chiplet (`VDDCH*`)**, and **HBM4E (`VDDQ + VDDC + VDDQL + VPP + HBMPHY + EMIB`)**, keeping all `.mcm` inputs read-only in `<working_dir>/MCM_template/` and isolating all outputs into `SUBSTRATE_WORK_DIR`.

```text
Step 0 (Extract):  <working_dir>/MCM_template/*.mcm -> stage1_inputs/*.csv + stage1_data_summary.svg
   │
   ▼
Steps 1..8 (pdn_8step_flow.py — Sandbox & SVG Visual Gate in <working_dir>/pdn_sandbox/):
  Step 1: SURFACE (L01)   — FULL VIA or M:N (4:2, 5:2, 3:1) H/V/BOTH 24 um straps (0 floating bumps)
  Step 2: Frontside BU    — SURFACE -> 6F (VDD) / 7F (VSS), <= 7 BU stack (<= 3 in EMIB HSIO void)
  Step 3: Core PTH        — 4..11 PTH/mm² (PKG0.8 / PKG0.1), Staggered / 90° H/V, eDTC 300um KOZ + 150um Guard
  Step 4: Prepreg (PP)    — 1_VIA_CENTER / 2_VIA_ON_PTH / 4_VIA_PER_PTH + Substrate DR audit
  Step 5: BGA Clusters    — 12B <-> BASE Options 1..3 + Option 4 (4 center vias ±45.5um, 0.0um overlap)
  Step 6: BASE LSC/Recess — CONDUCTOR/BASE 0201 LSCs, Pin1=VDD/Pin2=VSS, 180° alternation, R=508um LSC_CAVITY
  Step 7: Backside BU     — BASE -> 6B (VDD) / 7B (VSS), <= 7 BU stack, 0.0um overlap
  Step 8: 27-Layer Bridge — 6F/7F -> 5F -> 4FCO & 6B/7B -> 5B -> 4BCO + 9F->5F / 9B->5B continuity (0 overlaps)
   │
   ▼
Stage 4 (Build New .mcm): pdn_import_recipe.txt -> headless apd.exe / run_apd.sh -> new DRC-clean .mcm
```

---

## 2. Core Python & Headless Cadence SKILL Modules

| Module / Directory | Location | Role |
| :--- | :--- | :--- |
| **Unified 8-Step Engine** | [`agent04_pdn_architect/cad_cli/pdn_8step_flow.py`](agent04_pdn_architect/cad_cli/pdn_8step_flow.py) | Orchestrates Steps 1–8 across `core`, `uncore`, `chiplet`, and `hbm` rail groups. |
| **Working-Dir Isolation** | [`agent04_pdn_architect/cad_cli/pdn_paths.py`](agent04_pdn_architect/cad_cli/pdn_paths.py) | Routes all Stage 1 CSVs, SVGs, recipes, and `.mcm` outputs into `SUBSTRATE_WORK_DIR`. |
| **Stage 1 Extractor** | [`agent04_pdn_architect/cad_cli/stage1_input_builder.py`](agent04_pdn_architect/cad_cli/stage1_input_builder.py) | Extracts BGA, bumps, `eDTC`, `LSC`, stackup, and padstacks from `<working_dir>/MCM_template/*.mcm`. |
| **Domain Routers** | [`agent04_pdn_architect/cad_cli/`](agent04_pdn_architect/cad_cli) | Specialized routers for `SURFACE`, `Core PTH/PP`, `Multi-Rail Polygon Splitter`, `EMIB/HBM`, `BASE Recess/LSC`, and `27-Layer Exporter`. |
| **Headless SKILL (`.il`)** | [`agent04_pdn_architect/scripts/`](agent04_pdn_architect/scripts) | `O(1)` `makeTable` pipe-delimited importer (`pdn_import_from_txt_batch.il`) and Cadence extraction/verification scripts. |
| **27-Layer Templates** | [`agent04_pdn_architect/templates/`](agent04_pdn_architect/templates) | Designer-editable JSON configs (`task1`, `task2`, `task3`) + `pdn_27layer_template_runner.py`. |
| **Cross-Platform APD Runner** | [`agent09_via_routing/cad_cli/cadence_runner.py`](agent09_via_routing/cad_cli/cadence_runner.py) | Resolves Windows `apd.exe` or Linux `run_apd.sh` + `xvfb-run` automatically. |
| **Local Studio Web UI** | [`AIstudio/`](AIstudio) | Browser UI (`http://127.0.0.1:8765`) with Working Folder picker, `.mcm` upload, Direct Runner, SVG Preview, and terminal. |

---

## 3. Mandatory Design & Safety Invariants

1. **Read-Only Source `.mcm`:** Never overwrite `<working_dir>/MCM_template/*.mcm`. Always generate a new output `.mcm` filename.
2. **Strict `CONDUCTOR/BASE` LSC Placement:** `100%` of `0201` LSCs land on `CONDUCTOR/BASE` (`Pin 1 = VDD_RAIL`, `Pin 2 = VSS`) with **`180°` cap-to-cap polarity alternation** and `R = 508 um` curved `LSC_CAVITY` clearances (`BGA -> Cavity >= 254 um`, `LSC -> Cavity >= 225 um`, `0` under EMIB shadow).
3. **Unbroken Middle-Buildup & Zero Via Overlap:** Enforce continuous `9F->5F` and `9B->5B` `VSS`/`VDD` stitch trunks and run `audit_via_continuity_and_zero_overlap` (`non_concentric_pad_overlap_count == 0`, `concentric_diff_net_short_count == 0`) across all 27 conductor layers before Stage 4 `.mcm` creation.
