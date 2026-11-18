# Task 2 (`VDDC*` & `VDD_0P8_SRAM_CC*`) — Designer-Editable Full 27-Layer PDN Design Template

> [!IMPORTANT]
> **Live Editable Template File:** [`task2_vddc_sram_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json)
> **27-Layer Compiler CLI:** [`pdn_27layer_template_runner.py`](file:///<agent_workspace>/agent04_pdn_architect/templates/pdn_27layer_template_runner.py)
> **Unified Cadence APD SKILL Importer:** [`apd_unified_27layer_template_importer.il`](file:///<agent_workspace>/agent04_pdn_architect/templates/apd_unified_27layer_template_importer.il)

---

## 1. Quick-Start Workflow for Designers

1. **Open & Modify Inputs:** Edit [`task2_vddc_sram_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json):
   - **`target_domains`:** Set `LDA` die (`U9 -> U12, U88, U10`), `VDDC0..3` & `VDD_0P8_SRAM_CC0..3` rails, EMIB bridges (`U25, U29, U32, U28, U39`), pure `VDDC` `eDTC`s (`C2215, C2217, C2219, C2220`), shared `VDDC+SRAM` `eDTC`s (`C2216, C2218`), and Kelvin sense pairs.
   - **`zone1_surface_escape`:**
     - `surface_routing_mode`: Choose `"PARTIAL_3_TO_1_VERTICAL_C_S_JOG"` (`75%` VIA on BOTH `VDDC0` & `SRAM_CC0`, `25%` VIA on `VSS`, `15 µm` vertical C-Jogs & S-Jogs), `"PARTIAL_3_TO_1_HORIZONTAL_COLLAR"`, or `"FULL_VIA"`.
   - **`zone3_edtc_and_core_pth`:** Customize `96-pin` `N24792-018` KOZ dimensions (`2,240 × 5,680 µm`), `150 µm` static guard bands, and Core PTH pitch (`520 × 480 µm`).
   - **`zone4_middle_bu_continuity_and_stack_limits`:** Configure `285 µm` `9F->5F` & `9B->5B` zero-overlap stitch arrays.
   - **`zone5_base_bga_curved_recess_and_lsc`:** Configure `8-via` `R = 195 µm` `C480` BGA octagon clusters, `250 µm` LSC SRO-to-SRO spacing, and Curved Non-Rectangular `POLY_CAVITY` rules (`R_mill = 508 µm`, `BGA SRO >= 254 µm`, `+178 µm` Ext Cu KOZ, `-225 µm` LSC safe envelope on `SUBSTRATE GEOMETRY/recess_cavity_pdn`).
   - **`stackup_all_27_layers`:** Customize co-planar `VDDC`/`SRAM` split clearances (`>= 50 µm` BU, `>= 67.5 µm` Core/PP/GCP) and `DYNAMIC`/`STATIC_GUARD` modes across `L01 SURFACE` .. `L27 BASE`.
2. **Compile & Validate All 27 Layers:**
   ```powershell
   python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json
   ```
3. **Inspect & Build `.mcm`:**
   - Review `Task2_U9_VDDC0_SRAM0_27Layer_Blueprint.svg`, `Task2_U9_SURFACE_3to1_VerticalJog.svg`, `Task2_U9_VDDC0_SRAM0_BASE_Curved_Recess_LSC.svg`, and `Task2_U9_VDDC0_SRAM0_27Layer_Layer_By_Layer_Summary.json`.
   - Run `Task2_U9_VDDC0_SRAM0_run_apd_headless.bat` to create the new `.mcm` database.

---

## 2. 27-Layer Co-Planar Dual-Rail Stackup Summary (`L01 SURFACE` $\rightarrow$ `L27 BASE`)

| Order | Layer | Shape Mode | Co-Planar Partition | Key Routing & DRC Rules |
| :---: | :---: | :--- | :--- | :--- |
| `L01` | `SURFACE` | `CLINE_AND_PADS` | `VDDC0` + `SRAM_CC0` + `VSS` | `3:1` Partial VIA (`75%` VDD / `25%` VSS) + `15 µm` Vertical C-Jogs & S-Jogs |
| `L02` | `C0` | `DYNAMIC` | `VSS` (EMIB Only) | `U25, U29, U32, U28, U39` `C18` uBumps (`0` `C0` copper outside bridges) |
| `L03..L04` | `12F, 11F` | `DYNAMIC` | `12F=VDDC0` / `11F=VSS` | `157.5 µm` EMIB KOZ voided |
| `L05` | `10F` | `DYNAMIC_PLUS_STATIC_GUARD` | `SRAM_CC0` + East `VDDC0` | `3-stack` `SRAM_CC0` collector + Static `150 µm` EMIB guard rings + `10F CSB` |
| `L06..L08` | `9F, 8F, 7F` | `DYNAMIC` | `9F/7F=VSS`, `8F=VDDC0` | `9F->5F` `VSS` stitch (`>3,100` cols, `0` via overlap) |
| `L09..L10` | `6F, 5F` | `DYNAMIC` | `6F=VDDC0+6xSRAM`, `5F=VSS` | `50 µm` co-planar split feeding `C2215..C2220` |
| `L11` | `4FCO` | `DYNAMIC_PLUS_STATIC_GUARD` | `VDDC0` + `SRAM_CC0` + Guards | `6x` `N24792-018` (`2,240×5,680 µm` KOZ) + `6x` Static `150 µm` guard bands |
| `L12..L18` | `3FCI..4BCO` | `DYNAMIC` (+ `4BCO` Guards) | `2FCI/2BCI/4BCO` Split; `3FCI/1FCI/1BCI/3BCI=VSS` | `67.5 µm` Core/PP split + concentric Core PTHs |
| `L19..L23` | `5B..9B` | `DYNAMIC` | `5B/7B/9B=VSS`, `6B/8B=Split` | Solid `5B` `VSS` under `eDTC`s + unbroken `5B->9B` `VSS` stitch |
| `L24..L25` | `10B, 11B` | `DYNAMIC` | `10B=Full SRAM_CC0`, `11B=VSS` | Dedicated `10B` `SRAM_CC0` lateral redistribution + `V83_55_83` uVias |
| `L26` | `12B` | `DYNAMIC` | `VDDC0` + East/West `SRAM_CC0` | `40 µm` GCP (`67.5 µm` split) directly feeding co-pocket LSCs |
| `L27` | `BASE` | `PADS_AND_CAVITY` | `VDDC0` + `SRAM_CC0` + `VSS` | `8-via` `R=195 µm` BGA rings + `6` Curved `POLY_CAVITY` pockets (incl. Inverted-T `U9_CAV_5`) + `196` `180°` LSCs |
