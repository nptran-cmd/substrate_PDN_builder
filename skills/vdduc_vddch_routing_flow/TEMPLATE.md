# Task 1 (`VDDUC*` & `VDDCH*`) — Designer-Editable Full 27-Layer PDN Design Template

> [!IMPORTANT]
> **Live Editable Template File:** [`task1_vdduc_vddch_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json)
> **27-Layer Compiler CLI:** [`pdn_27layer_template_runner.py`](file:///<agent_workspace>/agent04_pdn_architect/templates/pdn_27layer_template_runner.py)
> **Unified Cadence APD SKILL Importer:** [`apd_unified_27layer_template_importer.il`](file:///<agent_workspace>/agent04_pdn_architect/templates/apd_unified_27layer_template_importer.il)

---

## 1. Quick-Start Workflow for Designers

1. **Open & Modify Inputs:** Edit [`task1_vdduc_vddch_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json):
   - **`design_io`:** Point to your input `bga_map.csv`, `edtc_pin_map.csv`, `edtc_symbols.csv`, `lsc_placed_map.csv`, readonly source `.mcm`, and target `output_mcm_path`.
   - **`target_domains`:** Set `LDB` (`U7 -> U8, U6, U5` `VDDUC0..3`) and `LDC` (`U2 -> U4, U3, U1` `VDDCH0..3`) RefDes, net names, adjacent EMIBs, and `eDTC` lists.
   - **`padstack_library`:** Swap any via padstack across all 24 dielectric spans (`SURFACE_C0`, `SURFACE_12F`, `12F_11F` .. `12B_BASE`).
   - **`zone_routing_parameters`:**
     - `zone1_surface_escape`: Choose `surface_via_ratio` (`"FULL"`, `"3:1"`, `"4:2"`, `"5:2"`) and `strap_direction` (`"VERTICAL"`, `"HORIZONTAL"`, `"BOTH"`).
     - `zone3_edtc_and_core_pth`: Adjust real per-part-number `eDTC` KOZs (`N24792-018` `96p`, `017` `48p`, `016` `24p`), `core_pth_density_per_mm2` (`5..8`), and `core_pth_pattern` (`"STAGGERED"` / `"ORTHOGONAL_90DEG_*"`).
     - `zone4_middle_bu_continuity_and_stack_limits`: Control `9F->5F` & `9B->5B` stitch pitch (`285 µm`) and stack limits (`<=7` BU, `<=5` on PTH).
     - `zone5_base_bga_curved_recess_and_lsc`: Select BGA cluster (`OPTION1_4VIA_SQUARE_2X2`, `OPTION2_5VIA_QUINCUNX`, `OPTION3_6VIA_HEX_RING`), LSC SRO rule (`175` or `250 µm`), and Curved BGA-Following Recess rules (`mill_tool_radius_um: 508.0`, `bga_sro_to_cavity_min_um: 254.0`, `ext_cu_to_cavity_koz_um: 178.0`, `lsc_sro_to_cavity_min_um: 225.0`).
   - **`stackup_all_27_layers`:** Customize copper thickness, `DYNAMIC` vs. `DYNAMIC_PLUS_STATIC_GUARD` shape mode, nets, and split clearances on any layer `L01 SURFACE` .. `L27 BASE`.
2. **Compile & Validate All 27 Layers:**
   ```powershell
   python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task1_vdduc_vddch_27layer_template.json
   ```
3. **Inspect & Build `.mcm`:**
   - Review `Task1_VDDUC_VDDCH_27Layer_Stackup_Summary.svg`, `Task1_VDDUC_VDDCH_BASE_Curved_Recess_LSC.svg`, and `Task1_VDDUC_VDDCH_27Layer_Layer_By_Layer_Summary.json`.
   - Run `Task1_VDDUC_VDDCH_run_apd_headless.bat` to generate the new `.mcm` database without modifying `PDN_test.mcm`.

---

## 2. 27-Layer Stackup Summary (`L01 SURFACE` $\rightarrow$ `L27 BASE`)

| Order | Layer | Shape Mode | Primary Nets | Key Routing & DRC Rules |
| :---: | :---: | :--- | :--- | :--- |
| `L01` | `SURFACE` | `CLINE_AND_PADS` | `VDDUC*`, `VDDCH*`, `VSS` | `FULL` or `3:1` VIA + `24 µm` straps; EMIB uBumps drop to `C0` |
| `L02` | `C0` | `DYNAMIC` | `VSS` | Strictly inside EMIB bridge die outlines (`0` copper outside) |
| `L03..L04` | `12F, 11F` | `DYNAMIC` | `VDD` / `VSS` | `157.5 µm` EMIB cavity+pad KOZ voided |
| `L05` | `10F` | `DYNAMIC_PLUS_STATIC_GUARD` | `VDD`, `VSS` | Static `150 µm` isolated EMIB guard ring; `<=2` stacked vias below CSB |
| `L06..L10` | `9F..5F` | `DYNAMIC` | Alternating `VSS`/`VDD` | Unbroken `9F->5F` `VSS` & `8F->6F` `VDD` stitch (`0` via overlap) |
| `L11` | `4FCO` | `DYNAMIC_PLUS_STATIC_GUARD` | `VDD`, `VSS` | Real per-part `eDTC` KOZ + Static `150 µm` guard band + `0.0 µm` concentric landing |
| `L12..L18` | `3FCI..4BCO` | `DYNAMIC` (+ `4BCO` Guard) | Alternating `VDD`/`VSS` | `7 PTH/mm²` concentric `1-PP/PTH` Core (`2FCI<->2BCI`); `eDTC` KOZ voided |
| `L19` | `5B` | `DYNAMIC` | `VSS` | Mandatory solid unbroken `VSS` shield under all `eDTC` shadows |
| `L20..L25` | `6B..11B` | `DYNAMIC` | Alternating `VDD`/`VSS` | Unbroken `5B->9B` `VSS` & `6B->12B` `VDD` stitch; `11B` full `VSS` shield |
| `L26` | `12B` | `DYNAMIC` | `VDDUC*`, `VDDCH*` | Heavy `40 µm` GCP plane (`>=67.5 µm` split) directly feeding `BASE` LSCs |
| `L27` | `BASE` | `PADS_AND_CAVITY` | `VDDUC*`, `VDDCH*`, `VSS` | `4/5/6-via` BGA clusters + Curved `POLY_CAVITY` (`recess_cavity_pdn`) + `180°` `SM0201` LSCs on `CONDUCTOR/BASE` |
