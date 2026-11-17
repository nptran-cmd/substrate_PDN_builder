# Agent 04 (`pdn_architect`) — 4-Stage Implementation TODO List

> [!IMPORTANT]
> **Hard Constraint:** Never modify any file in `<pcbenv_skill_dir>/`. All refactored SKILL `.il` scripts, Python indexers, SVG sandbox exporters, and pipe-delimited recipe files live in `agent04_pdn_architect/`.

---

## Phase 1: Architecture, Documentation & 4-Stage Plan (COMPLETED)
- [x] Inspect `<pcbenv_skill_dir>/` PDN scripts (`pdn_via_placement.il`, `addvia_onbump_HFC.il`, `PTH_generation_and_PPvia_HFC_case2/case2_mod/case3.il`, `BGA_routing/ver2/ver3.il`, `HFC_change_pin_net_edtc.il`, `PDN_spider_web_routing.il`, `pdn_jog_routing.il`).
- [x] Extract quantitative design rules from `specs_and_docs/design_rules/` (`Via Rules`, `eDTC DR`, `BGALSC Rules`, `Substrate Design Rules`).
- [x] Create [`agent04_pdn_architect/SKILL.md`](file:///<agent_workspace>/agent04_pdn_architect/SKILL.md) with the 4-Stage architecture (`Pre-Learn` $\rightarrow$ `5-Zone Synthesis` $\rightarrow$ `SVG Visual Sandbox` $\rightarrow$ `Pipe-Delimited Text Recipe & .mcm Import`).
- [x] Create [`agent04_pdn_architect/TEMPLATE.md`](file:///<agent_workspace>/agent04_pdn_architect/TEMPLATE.md) defining the JSON request/response schemas and `pdn_import_recipe.txt` pipe-delimited record format.
- [x] Create [`agent04_pdn_architect/TODO.md`](file:///<agent_workspace>/agent04_pdn_architect/TODO.md) and [`agent04_pdn_architect/AGENTS.md`](file:///<agent_workspace>/agent04_pdn_architect/AGENTS.md).

---

## Phase 2: Stage 1 (`Pre-Learn`) & Stage 2/4 Headless SKILL `.il` Scripts (COMPLETED)
- [x] **Task 2.1 — Shared Core Library ([`pdn_core_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_core_batch.il))**
- [x] **Task 2.2 — Stage 1C Padstack Library & `.mcm` Geometry Learner ([`padstack_learner_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/padstack_learner_batch.il)):** Verified live on `HH_full_Main_Drawing_Nguyen_2026-0916_2000_CORE_TO_R3.mcm` (`53` conductor layers, `105` padstacks, `2,348` symbols, `2,500` BGA pins learned).
- [x] **Task 2.3 — Stage 2 Zone Modules (Headless SKILL):**
  - [`pdn_above_bu_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_above_bu_batch.il)
  - [`edtc_pdn_guard_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/edtc_pdn_guard_batch.il)
  - [`PTH_and_PPvia_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/PTH_and_PPvia_batch.il)
  - [`pdn_below_bu_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_below_bu_batch.il)
  - [`lsc_pocket_placer_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/lsc_pocket_placer_batch.il)
- [x] **Task 2.4 — Stage 4 Pipe-Delimited Text Importer ([`pdn_import_from_txt_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_import_from_txt_batch.il)) & Master Dispatcher ([`pdn_Pipeline_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pdn_Pipeline_batch.il))**

---

## Phase 3: Stage 1 Multi-Format Indexer, Stage 3 SVG Visual Sandbox & Stage 4 CLI/MCP (COMPLETED)
- [x] **Task 3.1 — Stage 1 Multi-Format Pre-Learn Indexer ([`pdn_prelearn.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/pdn_prelearn.py))**
- [x] **Task 3.2 — Stage 2 & Stage 3 Sandbox Synthesizer & SVG ("VSG") Exporter ([`pdn_svg_sandbox.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/pdn_svg_sandbox.py)):** Exports 6 XML-validated SVG files in [`agent04_pdn_architect/svg_sandbox/`](file:///<agent_workspace>/agent04_pdn_architect/svg_sandbox) and [`pdn_import_recipe.txt`](file:///<agent_workspace>/agent04_pdn_architect/reports/pdn_import_recipe.txt).
- [x] **Task 3.3 — Stage 4 CLI ([`pdn_architect.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/pdn_architect.py)), MCP Tool ([`pdn_architect_tool.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/mcp/pdn_architect_tool.py)) & Unit Test Suite ([`test_agent04_suite.py`](file:///<agent_workspace>/agent04_pdn_architect/tests/test_agent04_suite.py) — `3/3` passing)**
