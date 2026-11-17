# Task 3 (`HBM4E` 4-Rail + `EMIB`) — Designer-Editable Full 27-Layer PDN Design Template

> [!IMPORTANT]
> **Live Editable Template File:** [`task3_hbm_4rail_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json)
> **27-Layer Compiler CLI:** [`pdn_27layer_template_runner.py`](file:///<agent_workspace>/agent04_pdn_architect/templates/pdn_27layer_template_runner.py)
> **Unified Cadence APD SKILL Importer:** [`apd_unified_27layer_template_importer.il`](file:///<agent_workspace>/agent04_pdn_architect/templates/apd_unified_27layer_template_importer.il)

---

## 1. Quick-Start Workflow for Designers

1. **Open & Modify Inputs:** Edit [`task3_hbm_4rail_27layer_template.json`](file:///<agent_workspace>/agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json):
   - **`target_domains`:** Set reference `HBM4E` site (`U13` + `U41` + `U5`, `MEM5`), 4 power rails (`VDDQ_0P85_HBM_MEM*`, `VDDC_1P0_HBM_MEM*`, `VDDQL*`, `VPP_1P8_HBM_MEM*`), compact `eDTC`s (`C2258` `48p` `N24792-017`, `C2257` `24p` `N24792-016`), Kelvin sense pairs, and the 12-site replication table (`U13..U24` / `U41..U52`).
   - **`zone1_bifurcated_surface_escape`:** Tune West non-EMIB `90 µm` gang-stripe height, `35 µm` strap width, and East `U41` `C0` overlap boundary.
   - **`zone2_u41_emib_and_10f_csb_escape`:** Configure `150 µm` static `10F` guard ring and per-rail `100%` `U41` `10F CSB` breakout rules (`<= 2` stacked vias below `10F`, `0` open bridge pins).
   - **`zone3_compact_edtc_and_4strip_core_pth`:** Adjust `500 × 460 µm` 4-strip Core PTH pitches (`VPP | VDDQ | VDDC | VDDQL`).
   - **`zone5_base_bga_curved_recess_and_lsc`:** Configure `6-via` `R = 165 µm` hex clusters (`VDDQ`), `4-via` `R = 200 µm` diamonds (`VDDC`/`VDDQL`/`VPP`), and Curved Hex-Staggered `POLY_CAVITY` rules (`Pocket A`: `17 VDDC + 13 VDDQ`; `Pocket B`: `6 VDDQL5`).
   - **`stackup_all_27_layers`:** Customize any layer `L01 SURFACE` .. `L27 BASE` (`DYNAMIC` power/VSS shapes, `STATIC_GUARD` rings, and split clearances).
2. **Compile & Validate All 27 Layers:**
   ```powershell
   python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task3_hbm_4rail_27layer_template.json
   ```
3. **Inspect & Build `.mcm`:**
   - Review `Task3_U13_HBM_4Rail_27Layer_Blueprint.svg`, `Task3_U13_HBM_4Rail_BASE_Curved_Recess_LSC.svg`, `Task3_U13_HBM_4Rail_27Layer_Stackup_Summary.svg`, and `Task3_U13_HBM_4Rail_27Layer_Layer_By_Layer_Summary.json`.
   - Run `Task3_U13_HBM_4Rail_run_apd_headless.bat` to generate the new `.mcm` database.

---

## 2. 27-Layer 4-Rail + `EMIB` Stackup Summary (`L01 SURFACE` $\rightarrow$ `L27 BASE`)

| Order | Layer | Shape Mode | 4-Rail + `VSS` Partition | Key Routing & DRC Rules |
| :---: | :---: | :--- | :--- | :--- |
| `L01` | `SURFACE` | `SHAPES_CLINES_PADS` | `VDDQ, VDDC, VDDQL, VPP, VSS` | West: `90 µm` horizontal gang-stripes (`C21` bumps); East: `U13`/`U5` uBumps into `U41` `C0` |
| `L02` | `C0` | `DYNAMIC` | All 5 nets inside `U41` | Strictly inside `U41` `LAVA_BRIDGE_22` outline (`0` `C0` copper outside `U41`) |
| `L03..L04` | `12F, 11F` | `DYNAMIC` | `12F=VDDC+VPP`, `11F=VSS` | `157.5 µm` `U41` EMIB KOZ voided |
| `L05` | `10F` | `DYNAMIC_PLUS_STATIC_GUARD` | `VDDQ` + `U41` `CSB` Floor | Static `150 µm` `U41` guard ring + `3,054` `CSB` pads (`<=2-stack` escape, `0` opens) |
| `L06..L08` | `9F, 8F, 7F` | `DYNAMIC` | `9F=VSS+VDDQL/VDDC buses`; `8F=VDDC+VDDQ+VDDQL+VPP`; `7F=VSS+VPP spine` | `100%` `U41` `CSB` escape to `6F` + `9F->5F` `VSS` stitch |
| `L09..L10` | `6F, 5F` | `DYNAMIC` | `6F=4 Strips (VPP\|VDDQ\|VDDC\|VDDQL)`, `5F=VSS` | `50 µm` 4-rail split feeding `C2258` & `C2257` |
| `L11` | `4FCO` | `DYNAMIC_PLUS_STATIC_GUARD` | 4 Strips + Compact `eDTC` KOZs | Real compact KOZs: `C2258` (`2,050×4,240 µm`) & `C2257` (`2,080×2,580 µm`) + Static `150 µm` guards |
| `L12..L18` | `3FCI..4BCO` | `DYNAMIC` (+ `4BCO` Guards) | 4 West-to-East Core Strips (`2FCI/2BCI/4BCO`) + `VSS` | `67.5 µm` Core/PP split + concentric `1-PP/PTH` stacks |
| `L19..L23` | `5B..9B` | `DYNAMIC` | `5B/7B/9B=VSS`, `6B/8B=Multi-Rail` | Solid `5B` `VSS` under `C2257`/`C2258` + unbroken `5B->9B` `VSS` stitch |
| `L24..L25` | `10B, 11B` | `DYNAMIC` | `10B=VPP+Full VDDQ`, `11B=VSS` | Full-width `10B` `VDDQ` feeder + `11B` `VSS` shield |
| `L26` | `12B` | `DYNAMIC` | `VPP \| VDDC (+VDDQ sub) \| VDDQL` | `40 µm` GCP (`67.5 µm` split) feeding Pocket A & Pocket B LSCs |
| `L27` | `BASE` | `PADS_AND_CAVITY` | All 5 nets (`C560` BGAs + LSCs) | `6-via` hex `VDDQ` & `4-via` diamond BGAs + Curved Pocket A (`30` LSCs) & Pocket B (`6` LSCs) |
