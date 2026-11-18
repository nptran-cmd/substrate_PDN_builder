# Designer-Editable Full 27-Layer PDN Design Templates (`Tasks 1, 2 & 3`)

Modify any parameter in the 3 JSON files below and run `pdn_27layer_template_runner.py` to generate a full, DRC-verified 27-layer (`L01 SURFACE` -> `L27 BASE`) PDN design:

1. **Task 1 (`VDDUC*` & `VDDCH*` on `LDB` `U7..U5` & `LDC` `U2..U1`):**
   - Config: `task1_vdduc_vddch_27layer_template.json`
   - Compile: `python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json`
2. **Task 2 (`VDDC0..3` + `VDD_0P8_SRAM_CC0..3` on `LDA` `U9, U12, U88, U10`):**
   - Config: `task2_vddc_sram_27layer_template.json`
   - Compile: `python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json`
3. **Task 3 (`HBM4E` 4-Rail `VDDQ + VDDC + VDDQL + VPP` on `U13..U24` + `U41..U52`):**
   - Config: `task3_hbm_4rail_27layer_template.json`
   - Compile: `python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json`
4. **Compile & Validate All 3 Tasks (Sandbox Mode — Zero `.mcm` Changes):**
   - `python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --all-3-tasks --stage sandbox`
5. **Final Confirmation Gate -> Build New `.mcm`:**
   - `python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json --stage implement-mcm`
6. **Full Step-by-Step Tutorial:**
   - Read [../TUTORIAL_BUILD_MCM_FROM_MCM.md](../TUTORIAL_BUILD_MCM_FROM_MCM.md) for the complete 5-phase Extract -> Customize -> Sandbox -> Final Confirmation -> `.mcm` Build & Sign-Off workflow.
