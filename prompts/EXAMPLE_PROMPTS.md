# 💬 Example Prompts Cookbook — Substrate PDN Builder (Agent 04: PDN Architect)

Copy and paste any of the prompts below into your AI agent session (**Gemini CLI**, **Antigravity / Jetski**, or **IDE Copilot**) to trigger the corresponding 27-layer IC package substrate PDN routing, DRC verification, SVG sandbox visualization, or headless Cadence Allegro / APD (`.mcm`) build workflow.

---

## 📋 Quick-Reference Scenario Index

| # | Scenario / Workflow | Primary Skill / Engine | Target Layers | Output Deliverables |
| :- | :--- | :--- | :--- | :--- |
| **1** | [Full-Package 24-Die, 76-Rail 27-Layer `.mcm` Build](#1-full-package-24-die-76-rail-27-layer-pdn-synthesis--mcm-build) | `full_package_all_dies_pdn.py` | `SURFACE` (`L01`) → `BASE` (`L27`) | `PDN_test_AllDies_AllRails_27Layer.mcm`, 3 SVGs, JSON DRC Audit |
| **2** | [Quadrant / Corner Subset `.mcm` Build from `master.tag`](#2-quadrant--corner-subset-mcm-build-from-mastertag-parallel-execution) | `upper_left_corner_pdn.py` | `SURFACE` (`L01`) → `BASE` (`L27`) | `PDN_test_UpperLeft_*.mcm`, Fast-Ordered Recipe, DRC Audit |
| **3** | [`VDDUC*` & `VDDCH*` Single-Rail 27-Layer Flow](#3-single-rail-vdduc-u5u8--vddch-u1u4-27-layer-pdn-routing) | `vdduc_vddch_routing_flow` | All 27 Layers | Per-die 27-layer recipe, SVG cross-section & top/bottom views |
| **4** | [Co-Resident Dual-Rail `VDDC*` + `VDDSRAM*` Flow](#4-co-resident-dual-rail-compute-dies-vddc03--vdd_0p8_sram_cc03) | `vddc_vddram_routing_flow` | All 27 Layers | Carved W/E `SRAM` islands, `10F` bridge backbone, `3:1` jog straps |
| **5** | [`HBM4E` 4-Rail + `HBMPHY` + `EMIB` 27-Layer Flow](#5-hbm4e-multi-rail-vddq-vddc-vddql-vpp-hbmphy--emib-routing) | `hbm_vdd_routing_flow` | All 27 Layers | West `SURFACE` gang-bars, East `EMIB` `C0`, `10F CSB` dogbones |
| **6** | [`BASE` (`L27`) Curved Recess Cavity & `180°` `0201` LSCs](#6-base-l27-curved-mechanical-recess-cavity--180-0201-lsc-placement) | `base_lsc_bga_routing` | `10B..BASE` + `LSC_CAVITY` | `R=500 um` filleted cavities, `CONDUCTOR/BASE` LSCs, BGA clusters |
| **7** | [Layer 1 (`SURFACE`) Bump-Via Ratio & Strapping Sweep](#7-layer-1-surface-parameterized-bump-via-ratios--strapping-directions) | `surface_layer1_routing` | `SURFACE` (`L01`) → `12F` (`L03`) | `FULL`, `4:2`, `5:2`, `3:1` VIP + `H`/`V`/`BOTH` 24 um straps |
| **8** | [Core `PTH` (`4FCO ↔ 4BCO`) Density & `eDTC` KOZ Sweep](#8-core-pth-4fco--4bco-density-sweep--real-multi-family-edtc-koz) | `pth_4fco_4bco_routing` | `6F..4FCO` ↔ `4BCO..6B` | `5..8 PTH/mm²`, Staggered vs `90°` Ortho H/V, `eDTC` KOZ voids |
| **9** | [Multi-Rail Co-Planar Polygon Splitter & Stack Pruner](#9-multi-rail-co-planar-polygon-splitter--atomic-via-stack-pruner) | `multi_rail_plane_polygon_splitter` | `12F` (`L03`) → `12B` (`L26`) | Dynamic planes, Static `150 um` guard bands, `0` dangling vias |
| **10** | [Zero-Via-Overlap (`27` Layers) & `9F→5F`/`9B→5B` Audit](#10-strict-zero-via-overlap-27-conductor-layers--vertical-continuity-audit) | `full_package_all_dies_pdn.py` | All 27 Conductor Layers | Per-conductor pad clearance audit (`0` overlaps) & trunk check |
| **11** | [Designer-Editable 27-Layer Recipe Template Runner](#11-designer-editable-27-layer-recipe-template-runner--headless-apd-batch) | `pdn_27layer_template_runner.py` | All 27 Layers | Custom `.mcm` from edited JSON/TXT templates |
| **12** | [Stage 3 Visual Gate SVGs & 18-Test Regression Suite](#12-stage-3-visual-gate-svg-inspection--automated-regression-test-suite) | `test_agent04_suite.py` | Sandbox + Unit Tests | XML-validated SVGs + 18-test verification report |

---

## 1. Full-Package 24-Die, 76-Rail 27-Layer PDN Synthesis & `.mcm` Build

**What it does:** Synthesizes all 24 dies across the entire package (`VDDUC0..3` on `U7, U5, U8, U6`; `VDDCH0..3` on `U2, U4, U3, U1`; `VDDC0..3` + `VDD_0P8_SRAM_CC0..3` on `U9, U12, U88, U10`; and all 12 HBM4E sites `MEM0..MEMB` on `U13..U24` + `U41..U52` EMIB bridges + `U98` anchors + `VSS`), generates Stage 3 Visual Gate SVGs and DRC audits (`8,176` polygons, `2,024,138` vias, `154,758` clines, `68` curved cavities, `1,919` `180°` `BASE` LSCs), and builds a brand-new `.mcm` in headless Cadence APD 25.1 while keeping `PDN_test.mcm` strictly read-only.

### Copy-Paste Prompts:

```text
I want to route VDDUC0..3, VDDCH0..3, VDDC0..3, SRAM0..3, and all 12 HBM rails across all 24 dies based on @agent04_pdn_architect/MCM_test/PDN_test.mcm and create a new .mcm file. Run the Stage 3 sandbox and DRC audit first, then proceed to Stage 4 .mcm creation.
```

```text
Run the full-package 24-die 27-layer PDN synthesis in sandbox mode (--sandbox-only), verify 0 via pad overlaps across all 27 conductor layers and unbroken 9F->5F / 9B->5B VSS and VDD continuity, and generate the 3 full-package Visual Gate SVGs.
```

```text
Execute Stage 4 headless Cadence APD .mcm build (--reuse-sandbox) from the verified 24-die master recipe into agent04_pdn_architect/MCM_test/PDN_test_AllDies_AllRails_27Layer.mcm and report the final database object and net-branch audit.
```

### Direct CLI Commands:
```powershell
# Stage 3 Sandbox Synthesis + Full DRC Audit + 3 Visual Gate SVGs (~3 min)
$env:PYTHONPATH="."; python -m agent04_pdn_architect.cad_cli.full_package_all_dies_pdn --sandbox-only

# Stage 4 Headless Cadence APD 25.1 .mcm Build reusing verified recipe
$env:PYTHONPATH="."; python -m agent04_pdn_architect.cad_cli.full_package_all_dies_pdn --reuse-sandbox --timeout 7200
```

---

## 2. Quadrant / Corner Subset `.mcm` Build from `master.tag` (Parallel Execution)

**What it does:** Resolves the baseline `.mcm` from `@agent04_pdn_architect/MCM_test/master.tag`, synthesizes a targeted corner/quadrant subset of dies (e.g., Upper-Left Corner: `U1` [`VDDCH3`], `U5` [`VDDUC1`], `U12` [`VDDC1` + `VDD_0P8_SRAM_CC1`], and `U13` [`MEM5` upper-left HBM rails] or `U13,U14,U15`), reorders `VIA` and `CLINE` commands before `POLY_SHAPE` with deferred dynamic plane pouring (`axlShapeChangeDynamicType(shpObj t nil)`), and builds an isolated `.mcm` in parallel (~7–9 minutes) without conflicting with any other running `.mcm` build.

### Copy-Paste Prompts:

```text
Can you create another MCM based on @agent04_pdn_architect/MCM_test/master.tag only for 1 VDDCH3 (U1), VDDUC1 (U5), VDDC1 and SRAM1 (U12), and the HBM on the upper-left corner rails (U13 / MEM5)? Run it in parallel in its own isolated output folder.
```

```text
Create a new .mcm based on @agent04_pdn_architect/MCM_test/master.tag for the entire upper-left quadrant including U1 (VDDCH3), U5 (VDDUC1), U12 (VDDC1 + VDD_0P8_SRAM_CC1), and all 3 upper-left HBM dies (U13 MEM5, U14 MEM4, U15 MEM3).
```

### Direct CLI Commands:
```powershell
# Upper-Left Corner (U1 + U5 + U12 + U13 [MEM5]) — Sandbox + Fast Parallel .mcm Build (~8 min)
$env:PYTHONPATH="."; python -m agent04_pdn_architect.cad_cli.upper_left_corner_pdn --hbm-dies U13

# Upper-Left Quadrant with all 3 Left-Top HBMs (U13, U14, U15)
$env:PYTHONPATH="."; python -m agent04_pdn_architect.cad_cli.upper_left_corner_pdn --hbm-dies U13,U14,U15 `
  --out-dir agent04_pdn_architect/reports/upper_left_3hbm `
  --out-mcm agent04_pdn_architect/MCM_test/PDN_test_UpperLeft_3HBM.mcm
```

---

## 3. Single-Rail `VDDUC*` (`U5..U8`) & `VDDCH*` (`U1..U4`) 27-Layer PDN Routing

**What it does:** Executes the `vdduc_vddch_routing_flow` skill across all 27 layers (`SURFACE` `L01` → `BASE` `L27`) for any `LDB` (`U7: VDDUC0`, `U5: VDDUC1`, `U8: VDDUC2`, `U6: VDDUC3`) or `LDC` (`U2: VDDCH0`, `U4: VDDCH1`, `U3: VDDCH2`, `U1: VDDCH3`) die, including `100%` `SURFACE` VIP + `VSS` perimeter collar, `9F->5F` and `9B->5B` middle-buildup stitch trunks, concentric `4FCO` `eDTC` stacks, Core `PTH`/`PP` columns, and `BASE` curved recess `0201` LSCs.

### Copy-Paste Prompts:

```text
Use the `vdduc_vddch_routing_flow` skill to route the full 27-layer PDN for U7 (VDDUC0 and VSS) and U2 (VDDCH0 and VSS) with 100% SURFACE VIP, concentric 4FCO eDTC stacks, unbroken 9F->5F / 9B->5B trunks, and 180-degree alternating CONDUCTOR/BASE LSCs.
```

```text
Route U5 (VDDUC1) and U1 (VDDCH3) across all 27 layers using a 5:2 VDD:VSS bump-via ratio with HORIZONTAL 24 um SURFACE strapping, 7 PTH/mm² Core PTH density, and generate the cross-section and top/bottom transition SVGs.
```

---

## 4. Co-Resident Dual-Rail Compute Dies `VDDC0..3` + `VDD_0P8_SRAM_CC0..3`

**What it does:** Executes the `vddc_vddram_routing_flow` skill on the `LDA` compute dies (`U9: VDDC0 + VDD_0P8_SRAM_CC0`, `U12: VDDC1 + VDD_0P8_SRAM_CC1`, `U88: VDDC2 + VDD_0P8_SRAM_CC2`, `U10: VDDC3 + VDD_0P8_SRAM_CC3`), carving West and East `VDDSRAM` islands out of the main `VDDC` planes (`>=50 um` BU / `>=67.5 um` Core/PP/GCP split gaps), bridging West-to-East `VDDSRAM` on `10F`, routing `3:1` vertical jog straps on `SURFACE`, and splitting `BASE` recess pockets between `VDDC` and `VDDSRAM` LSCs.

### Copy-Paste Prompts:

```text
Use the `vddc_vddram_routing_flow` skill to synthesize the 27-layer co-resident dual-rail PDN for U9 (VDDC0 + VDD_0P8_SRAM_CC0 + VSS), including the 3:1 vertical jog SURFACE strapping, 10F West-to-East SRAM bridge backbone, real N24792-018 eDTC keepout voids, and co-pocket BASE LSCs.
```

```text
Route all 4 LDA compute dies (U9, U12, U88, U10) for VDDC0..3 and VDD_0P8_SRAM_CC0..3, verify >=50 um BU and >=67.5 um Core/PP/GCP polygon split clearances, and export the per-layer SVG overview.
```

---

## 5. `HBM4E` Multi-Rail (`VDDQ`, `VDDC`, `VDDQL`, `VPP`, `HBMPHY` + `EMIB`) Routing

**What it does:** Combines `hbm_vdd_routing_flow` and `emib_csb_and_hbm_surface_router` to route any or all 12 `HBM4E` sites (`U13..U24`, `MEM0..MEMB`) and their `EMIB` bridges (`U41..U52`):
- **West non-EMIB `21 um` fine-pitch bumps:** Grouped into `84–90 um` horizontal `SURFACE` copper gang-bars split cleanly around `OBS_*`/`NC_*`/Signal bumps (`>=18.5 um` gap) with centerline `SURFACE->12F` drop vias.
- **East `EMIB` overlap bumps:** Routed onto `C0` (`VU30_19_60_SURFACE_C0_01B` / `VU30_19_35_SURFACE_C0_01B`) with strict `C0` exclusivity and `157.5 um` `12F/11F` bridge cavity keepouts.
- **`10F CSB` (`C77_10F_DP_01A`) pins:** Escaped within the max 2-stacked-via EMIB Rule #14 limit via lateral `8F` dogbones into `6F` power strips.
- **4-Strip Co-Planar Inner Planes:** `VPP | VDDC | VDDQ | VDDQL` + `8F` E-comb `VPP` collector + `VDD_0P75_HBMPHY_UC*` tabs.

### Copy-Paste Prompts:

```text
Use `hbm_vdd_routing_flow` and `emib_csb_and_hbm_surface_router` to route U13 (MEM5: VDDQ_0P85_HBM_MEM5, VDDC_1P0_HBM_MEM5, VDDQL5, VPP_1P8_HBM_MEM5, VDD_0P75_HBMPHY_UC5, and VSS) with West SURFACE copper gang-bars, East U41 EMIB C0 routing, and 10F CSB lateral 8F dogbone escapes.
```

```text
Synthesize Step 1 + Step 2 for both U9 (VDDC0 + SRAM0) and U13 (HBM MEM5 4-Rail) together, verify 0 open 10F CSB pins and 0 EMIB KOZ violations, and generate a new Cadence APD .mcm file.
```

---

## 6. `BASE` (`L27`) Curved Mechanical Recess Cavity & `180°` `0201` LSC Placement

**What it does:** Learns non-rectangular empty BGA pockets on `BASE` (`L27`), synthesizes `R = 500 um` filleted curved mechanical recess cavities (`CAVITY/BASE` and `SUBSTRATE GEOMETRY/recess_cavity_pdn`) enforcing `>=250 um` BGA-pad-to-cavity, `>=225 um` LSC-body-to-cavity, and `178/203 um` outer copper KOZ rules, instantiates logical discrete `0201` LSC components strictly on `CONDUCTOR/BASE` (`Pin 1 = VDD_RAIL`, `Pin 2 = VSS`) with **`180°` cap-to-cap polarity alternation** (`0° <-> 180°` across vertical columns, `90° <-> 270°` on horizontal remainder strips), and routes 3-option BGA via clusters (`4-Via Square 2x2`, `5-Via Quincunx`, or `6-Via Hex Ring`).

### Copy-Paste Prompts:

```text
Use the `base_lsc_bga_routing` skill and `curved_recess_and_lsc_engine.py` to synthesize all curved BASE mechanical recess cavities (R=500 um, >=250 um BGA-to-cavity, >=225 um LSC-to-cavity) and pack 0201 LSCs on CONDUCTOR/BASE with 180-degree cap-to-cap polarity alternation and Pin 1 = VDD* / Pin 2 = VSS net assignments.
```

```text
Run a full BASE curved recess cavity and 180-degree LSC placement audit across all 68 package pockets, generate the high-resolution BASE inspection SVG showing BGA SROs, cavity contours, and LSC Pin-1/Pin-2 polarities, and verify 0 DRC violations.
```

### Direct CLI Command:
```powershell
$env:PYTHONPATH="."; python -m agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine
```

---

## 7. Layer 1 (`SURFACE`) Parameterized Bump-Via Ratios & Strapping Directions

**What it does:** Routes any die on `SURFACE` (`L01`) with either **Full Via-on-Bump (`FULL` 100% VIP)** or any user-specified **`M:N` (`VDD:VSS`) bump-via ratio** (`4:2`, `5:2`, `3:1`) and strapping direction (`HORIZONTAL`, `VERTICAL`, or `BOTH` 2D orthogonal grid), strapping un-via'd bumps to adjacent same-net via'd bumps with `24 um` `SURFACE` `CLINE` traces while maintaining `>=16.5 um` edge-to-edge clearance to opposite-net bumps.

### Copy-Paste Prompts:

```text
Use the `surface_layer1_routing` skill on U7 (VDDUC0 and VSS) to compare 100% Full VIP against a 5:2 VDD:VSS bump-via ratio with HORIZONTAL, VERTICAL, and BOTH 2D 24 um SURFACE strapping, and generate side-by-side comparison SVGs.
```

```text
Route U9 (VDDC0, VDD_0P8_SRAM_CC0, and VSS) on SURFACE using a 3:1 vertical jog strapping pattern so every un-via'd bump is strapped to a same-net SURFACE->12F microvia with >=16.5 um clearance.
```

---

## 8. Core `PTH` (`4FCO ↔ 4BCO`) Density Sweep & Real Multi-Family `eDTC` KOZ

**What it does:** Sweeps Core Plated-Through-Hole (`PTH`, `V210_110_210_4FCO_4BCO_01A`) densities (`5, 6, 7, 8 PTH/mm²`) and grid topologies (**Staggered Hexagonal** vs. **`90°` Orthogonal Horizontal/Vertical Aligned**) across `4FCO <-> 4BCO`, enforces Same-Net (`>=270 um`) and Diff-Net (`>=432.5 um`) pitch rules, carves exact multi-family `eDTC` keepout voids (`N24792-018` `144p`, `N24792-017` `48p`, `N24792-016` `24p`: silicon die + `300 um` cavity + `150 um` guard band + `67.5 um` gap), and synthesizes 1-Stack or 2-Stack Prepreg (`4FCO->3FCI->2FCI` & `2BCI->3BCI->4BCO`) transitions.

### Copy-Paste Prompts:

```text
Use the `pth_4fco_4bco_routing` skill on U7 (VDDUC0 / VSS) to sweep Core PTH densities of 5, 6, 7, and 8 PTH/mm² across both Staggered and 90-degree Orthogonal H/V patterns, subtract all 4FCO eDTC keepouts, and generate a 4-panel density comparison SVG and summary table.
```

```text
Compare 1-Stack vs. 2-Stack Prepreg via transitions (4FCO->3FCI->2FCI and 2BCI->3BCI->4BCO) at 6 PTH/mm² and verify that no Core PTH has more than 5 stacked buildup/prepreg vias landing on it.
```

---

## 9. Multi-Rail Co-Planar Polygon Splitter & Atomic Via Stack Pruner

**What it does:** Synthesizes `N`-rail co-planar voltage islands across all 24 inner layers (`C0, 12F..12B`), distinguishes **Dynamic** power/ground copper planes (`DYNAMIC`) from isolated **Static** `150 um` guard band rings (`STATIC_NET`) around `10F` EMIB cavities and `4FCO/4BCO` `eDTC` cavities, and builds an $O(1)$ `(x, y, layer)` net-ownership spatial index that atomically prunes every vertical via stack (`0` wrong-rail plane landings, `0` dangling vias).

### Copy-Paste Prompts:

```text
Use `multi_rail_plane_polygon_splitter` to generate the 24 inner-layer co-planar polygons for U9 (VDDC0 + VDD_0P8_SRAM_CC0 + VSS) and U13 (VDDQ + VDDC + VDDQL + VPP + VSS), including Dynamic copper planes, Static 150 um EMIB/eDTC guard bands, and atomic via stack pruning.
```

---

## 10. Strict Zero-Via-Overlap (`27` Conductor Layers) & Vertical Continuity Audit

**What it does:** Runs `audit_via_continuity_and_zero_overlap` and `check_inter_domain_polygon_clearances` across every conductor layer (`SURFACE`, `C0`, `12F..1F`, `4FCO..4BCO`, `1B..12B`, `BASE`) using true per-layer padstack copper radii (`PADSTACK_CONDUCTOR_RADII`) so neither same-span duplicate vias nor staggered adjacent-span vias sharing a boundary conductor layer (`9F`, `8F`, `7F`, `6F`, `5F`, `5B`, `6B`, `7B`, `8B`, `9B`, `10B`, `11B`, `12B`) can ever overlap (`non_concentric_pad_overlap_count == 0`, `concentric_diff_net_short_count == 0`), and confirms unbroken `9F->5F` and `9B->5B` `VSS`/`VDD` vertical trunks across all domains.

### Copy-Paste Prompts:

```text
Run a strict 27-conductor-layer zero-via-overlap and polygon clearance audit on my synthesized PDN recipe. Verify that duplicate_same_span_count == 0, non_concentric_pad_overlap_count == 0, concentric_diff_net_short_count == 0, and every domain has unbroken 9F->5F and 9B->5B VSS and VDD stitch columns.
```

---

## 11. Designer-Editable 27-Layer Recipe Template Runner & Headless APD Batch

**What it does:** Allows package designers to inspect or edit human-readable JSON/TXT 27-layer PDN templates (`task1_vdduc_vddch_27layer_template.json`, `task2_vddc_sram_27layer_template.json`, `task3_hbm_4rail_27layer_template.json`) and compile them directly into a new Cadence APD `.mcm` database using `pdn_27layer_template_runner.py` and `apd_unified_27layer_template_importer.il`.

### Copy-Paste Prompts:

```text
Compile the 3 designer-editable 27-layer PDN templates (Task 1 VDDUC0+VDDCH0, Task 2 U9 VDDC0+SRAM0, and Task 3 U13 HBM 4-Rail) using `pdn_27layer_template_runner.py` and build a verified Cadence APD .mcm file.
```

### Direct CLI Command:
```powershell
$env:PYTHONPATH="."; python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --task all --run-apd
```

---

## 12. Stage 3 Visual Gate SVG Inspection & Automated Regression Test Suite

**What it does:** Runs the 18-test automated verification suite (`test_agent04_suite.py`) covering Stage 1 input extraction, Stage 2 5-zone synthesis, Stage 3 XML-validated SVG generation, curved `BASE` recess cavity DRC, `180°` `CONDUCTOR/BASE` LSC alternation, multi-rail polygon splitting, and zero-via-overlap invariants.

### Copy-Paste Prompts:

```text
Run the complete Agent 04 unit and integration test suite (`agent04_pdn_architect.tests.test_agent04_suite`) and report the pass/fail status of all 18 tests.
```

### Direct CLI Command:
```powershell
$env:PYTHONPATH="."; python -m unittest agent04_pdn_architect.tests.test_agent04_suite -v
```
