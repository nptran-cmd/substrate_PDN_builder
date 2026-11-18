# User Prompt, Request & 27-Layer Config Templates (`substrate_PDN_builder`)

Use these copy-paste templates in **AIstudio Prompt Composer**, **Jetski**, **Gemini CLI**, or the **27-Layer JSON Template Runner** so every team member gets consistent, working-folder-isolated results without touching the Git repo.

> **Prerequisite:** Place your read-only starting `.mcm` inside `<working_dir>/MCM_template/<design>.mcm` and set `Working Folder` in `AIstudio` (or `$env:SUBSTRATE_WORK_DIR` / `export SUBSTRATE_WORK_DIR`) before running any template below.

---

## 1. Universal User Request Template (Fill-in-the-Blank Prompt)

Copy this block into `AIstudio` **Prompt Composer** (or your AI CLI), replace `<BRACKETED>` fields, and press **`Ctrl+Enter`**:

```text
Working Directory: <C:\PDN_builde or ~/pdn_workspaces>
Source .mcm (read-only): <working_dir>/MCM_template/<design>.mcm
Target Rail Group: <core | uncore | chiplet | hbm>
Target RefDes & Nets: <e.g., U7 (VDDUC0 + VSS) | U9 (VDDC0 + VDD_0P8_SRAM_CC0 + VSS)>

Task:
1. Ensure Stage 1 CSVs exist in `<working_dir>/stage1_inputs/` (run `stage1_input_builder` first if missing).
2. Run PDN synthesis (`pdn_8step_flow`) for steps `<all | 1..8>` with:
   - Step 1 SURFACE ratio: <FULL | 4:2 | 5:2 | 3:1>, direction: <VERTICAL | HORIZONTAL | BOTH>
   - Step 3 Core PTH: density `<7.0>` PTH/mm2, pattern `<STAGGERED | ORTHOGONAL_90DEG_VERTICAL | ORTHOGONAL_90DEG_HORIZONTAL>`, rule `<PKG0.8 | PKG0.1>`
   - Step 4 Prepreg PP: pattern `<1_VIA_CENTER | 2_VIA_ON_PTH | 4_VIA_PER_PTH>`
   - Step 5 BGA cluster: `<OPTION4_4VIA_CENTER_ZERO_OVERLAP | OPTION1_4VIA_SQUARE_2X2 | OPTION2_5VIA_QUINCUNX | OPTION3_6VIA_HEX_RING>`
   - Step 6 BASE LSC: `CONDUCTOR/BASE`, `180°` cap-to-cap alternation, curved `LSC_CAVITY` recess rules
3. Export XML-validated SVGs into `<working_dir>/pdn_sandbox/` and report DRC + zero-overlap audit counts.
4. Sandbox only — do NOT build or overwrite `.mcm` until I review SVGs and explicitly approve Stage 4.
```

---

## 2. Ready-to-Use Rail Group Presets (Copy & Paste)

### Preset A — Uncore (`VDDUC0..3` on `U7, U5, U8, U6`)
```text
Use skills `uncore_vdduc_routing_flow` and `step1_surface_bump_routing`..`step8_transition_pp_core_connection`:
Extract Stage 1 inputs from `<working_dir>/MCM_template/` if missing, then run all 8 PDN steps in sandbox mode for U7 (VDDUC0 + VSS) with SURFACE ratio 4:2 VERTICAL, Core PTH 7.0 PTH/mm2 STAGGERED (PKG0.8), PP 1_VIA_CENTER, BGA OPTION4_4VIA_CENTER_ZERO_OVERLAP, and BASE curved recess 180-deg LSCs. Export SVGs and audits into `<working_dir>/pdn_sandbox/`. Do not create a new .mcm yet.
```

### Preset B — Core Dual-Rail (`VDDC0 + VDD_0P8_SRAM_CC0` on `U9, U12, U88, U10`)
```text
Use skill `vddc_vddram_routing_flow` for U9 (VDDC0 + VDD_0P8_SRAM_CC0 + VSS):
Synthesize all 8 steps across 27 layers using 3:1 vertical jog SURFACE strapping, carved W/E SRAM planes (>=50um BU / >=67.5um Core split gap), 10F SRAM bridge backbone, N24792-018 eDTC KOZ voids, and co-pocket CONDUCTOR/BASE 180-deg alternating LSCs. Save SVGs and audit JSON strictly inside `<working_dir>/pdn_sandbox/`.
```

### Preset C — Chiplet (`VDDCH0..3` on `U2, U4, U3, U1`)
```text
Use skill `chiplet_vddch_routing_flow` for U2 (VDDCH0 + VSS):
Run Steps 1..8 in sandbox mode with SURFACE 5:2 HORIZONTAL, 6F VDD / 7F VSS frontside BU, 8.0 PTH/mm2 STAGGERED (PKG0.8), OPTION4_4VIA_CENTER_ZERO_OVERLAP BGA clusters, and curved BASE LSC_CAVITY placement. Verify 0 via pad overlaps across all 27 conductor layers and write outputs to `<working_dir>/pdn_sandbox/`.
```

### Preset D — `HBM4E` Multi-Rail (`VDDQ, VDDC, VDDQL, VPP, HBMPHY` on `U13..U24`)
```text
Use skills `hbm_vdd_routing_flow` and `emib_csb_and_hbm_surface_router` for U13 (MEM5 + U41 EMIB):
Route West 21um fine-pitch paired rows with 84-90um SURFACE gang-bars, East EMIB bumps exclusively onto C0, 10F CSB lateral 8F dogbone escapes (<=2 stacked vias), 4-strip co-planar inner planes (VPP | VDDC | VDDQ | VDDQL5), and BASE LSCs outside the EMIB shadow. Export SVGs and DRC audits to `<working_dir>/pdn_sandbox/`.
```

---

## 3. Direct CLI Parameter Template (`pdn_8step_flow`)

Run any step directly in PowerShell/Bash (or via **Direct** in `AIstudio`):

```powershell
# Set working directory first so all CSVs/SVGs/recipes isolate cleanly
$env:SUBSTRATE_WORK_DIR = "C:\PDN_builde"   # Linux: export SUBSTRATE_WORK_DIR="$HOME/pdn_workspaces"

# Step 0: Extract Stage 1 inputs from <working_dir>/MCM_template/*.mcm
python -m agent04_pdn_architect.cad_cli.stage1_input_builder --work-dir "$env:SUBSTRATE_WORK_DIR"

# Steps 1..8: Run any single step (--step 1..8) or full pipeline (--step all)
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group uncore `
  --step all `
  --ratio 4:2 `
  --direction VERTICAL `
  --pth-density 7.0 `
  --pth-pattern STAGGERED `
  --pkg-rule PKG0.8 `
  --pp-pattern 1_VIA_CENTER `
  --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP
```

---

## 4. Designer-Editable 27-Layer JSON Config Templates

Customize parameters directly in JSON before running a full 27-layer build:

| Task | Domain / Rails | Template File |
| :--- | :--- | :--- |
| **Task 1** | Uncore `VDDUC*` & Chiplet `VDDCH*` | [`agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json`](agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json) |
| **Task 2** | Core Dual-Rail `VDDC*` + `VDDSRAM` | [`agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json`](agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json) |
| **Task 3** | `HBM4E` 4-Rail + `EMIB` | [`agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json`](agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json) |

```powershell
# Phase A: Mandatory Sandbox Validation + SVG Visual Gate (zero .mcm changes)
python -m agent04_pdn_architect.templates.pdn_27layer_template_runner `
  --config agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json `
  --stage sandbox

# Phase B: Final Confirmation Gate -> Build New Output .mcm
python -m agent04_pdn_architect.templates.pdn_27layer_template_runner `
  --config agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json `
  --stage implement-mcm
```

---

## 5. Stage 4 Pipe-Delimited Recipe Record Format (`pdn_import_recipe.txt`)

Reference schema consumed by the O(1) `makeTable` Cadence SKILL batch importer (`pdn_import_from_txt_batch.il`):

```text
# AGENT04_PDN_RECIPE_V1|REFDES=U7|NETS=VDDUC0,VSS
VIA|PADSTACK=V77_49_77_SURFACE_12F_01A|X=120.010|Y=0.000|NET=VDDUC0|START=SURFACE|END=12F|ZONE=STEP1_SURFACE
CLINE|LAYER=CONDUCTOR/SURFACE|NET=VDDUC0|WIDTH=24.0|X1=0.000|Y1=0.000|X2=120.010|Y2=0.000|ZONE=STEP1_SURFACE
EDTC_GUARD|LAYER=CONDUCTOR/2FCI|NET=VSS|WIDTH=150.0|X1=-2500.0|Y1=-2500.0|X2=2500.0|Y2=2500.0|SYM=EDTC_1
KOZ|LAYER=CORE_ALL|TYPE=EDTC_CAVITY_300UM|X1=-2350.0|Y1=-2350.0|X2=2350.0|Y2=2350.0|SYM=EDTC_1
LSC_SYM|REFDES=C_LSC_001|SYM=SM0201_690X390X550_01A|X=1200.000|Y=-800.000|ROT=0.0|MIRROR=NO|LAYER=BASE
```
