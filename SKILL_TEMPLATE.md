# Reusable Skill Authoring Template (`SKILL_TEMPLATE.md`)

Use this template whenever adding a new PDN or CAD skill to `substrate_PDN_builder`.  
Copy the skeleton below into **`skills/<new_skill_name>/SKILL.md`** (lowercase `snake_case` folder name) and follow the registration checklist at the bottom.

> **Safety Rule:** Keep `skills/<new_skill_name>/SKILL.md` free of `.mcm` files, local user paths (`C:\Users\<name>`), internal shortlinks, or secrets so `audit_repo_safety.py` stays green (`PASS`).

---

## 1. Copy-Paste `SKILL.md` Skeleton

````markdown
---
name: <new_skill_name>
description: >
  <One-paragraph summary of what this skill automates, which substrate layers
  (e.g., SURFACE..12F, 4FCO..4BCO, BASE) and rail groups it targets, and the
  key design rules / verification gates it enforces.>
---

# <Human-Readable Skill Title> (`<new_skill_name>`)

## 1. Scope & Supported Targets
- **Rail Groups / Dies:** <e.g., Core (`U9`), Uncore (`U7`), Chiplet (`U2`), HBM (`U13`)>
- **Layer Span:** `<START_LAYER>` &harr; `<END_LAYER>`
- **Required Stage 1 Inputs (in `<working_dir>/stage1_inputs/`):**
  - `stackup_53layers.csv`, `bump_map.csv`, `bga_map.csv`, `edtc_symbols.csv`

## 2. Mandatory Design Rules & Guardrails
- **Rule 1:** <Exact numeric clearance, pitch, or stack limit (e.g., `>= 18.0 um` gap, `<= 7` BU stack)>
- **Rule 2:** <Keepout / net-ownership / polarity rule (e.g., `CONDUCTOR/BASE` only, `180°` alternation)>
- **Safety Gate:** Treat `<working_dir>/MCM_template/*.mcm` as **100% read-only**. Write all SVGs, CSVs, and recipes to `SUBSTRATE_WORK_DIR` (`pdn_paths.py`).

## 3. Execution Commands

### Direct CLI / `AIstudio` Direct Runner
```powershell
# Sandbox + SVG verification (no .mcm mutation)
python -m agent04_pdn_architect.cad_cli.<module_name> --rail-group <uncore> --step <1>
```

### Optional Stage 4 `.mcm` Implementation
```powershell
# Only run after SVG visual inspection passes
python -m agent04_pdn_architect.cad_cli.<module_name> --rail-group <uncore> --implement-mcm
```

## 4. Expected Outputs & Verification Gates
- **SVG Visual Gate:** `<working_dir>/pdn_sandbox/<output_name>.svg` (must be XML-valid)
- **Audit Gate:** `<working_dir>/pdn_sandbox/<audit_name>.json` confirming:
  - `non_concentric_pad_overlap_count == 0`
  - `floating_bumps == 0` (if `SURFACE`)
  - `dangling_vias == 0`
````

---

## 2. Checklist After Creating `skills/<new_skill_name>/SKILL.md`

1. **Mirror & Frontmatter Check:**
   - Ensure YAML frontmatter starts at line 1 with `---` and defines both `name:` and `description:`.
   - Keep `skills/<new_skill_name>/SKILL.md` and `agent04_pdn_architect/skills/<new_skill_name>/SKILL.md` synchronized.
2. **Register for Discovery:**
   - Add a 1-line bullet to [`.gemini/GEMINI.md`](.gemini/GEMINI.md) and a row to [`README.md`](README.md).
   - *(Optional)* Add a card entry in [`AIstudio/backend/prompts_catalog.py`](AIstudio/backend/prompts_catalog.py) and allowlist any new CLI module in [`AIstudio/backend/direct_runner.py`](AIstudio/backend/direct_runner.py) if it should appear in the `AIstudio` UI.
3. **Run Verification Before Pushing:**
   - Run `python -m unittest AIstudio.tests.test_studio AIstudio.tests.test_linux_direct_studio AIstudio.tests.test_pdn_8step -v`.
   - Run `audit_repo_safety.py --repo-dir .` and confirm `Audit Result : PASS`.
