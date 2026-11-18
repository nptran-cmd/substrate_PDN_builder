---
name: step4_prepreg_pp_routing
description: >
  Step 4 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Routes Prepreg (PP) layers (4FCO <-> 3FCI <-> 2FCI and 2BCI <-> 3BCI <-> 4BCO) using
  selectable PP via patterns (1_VIA_CENTER, 2_VIA_ON_PTH, 4_VIA_PER_PTH) and performs
  exact Design Rule auditing against Substrate Design Rules (max vias on single PTH pad,
  PP-PP <= 45 um overlap, 67.5 um min Core/PP L/S, and <= 5 stacked on PTH through PP).
---

# Step 4: Prepreg (`PP`) Pattern Routing & Design Rule Check

## 1. Prepreg Patterns & Design Rule Audit Results
Prepreg via padstack is `175_85_175` (`r = 87.5 um`, `85 um` drill) on Core PTH outer lid (`282.5 um`, `r = 141.25 um`):

| Pattern | Offsets per PTH (um) | Vias / PTH | `PKG 0.1` (`<= 1`) | `PKG 0.8` (`<= 2`) | `PP-PP` Max Overlap (`<= 45 um`) | Diff-Net Gap (`>= 67.5 um`) |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- |
| **`1_VIA_CENTER`** | `(0.0, 0.0)` | `1` | **PASS** (`1 <= 1`) | **PASS** (`1 <= 2`) | `0.0 um` (**PASS**) | `>= 175 um` (**PASS**) |
| **`2_VIA_ON_PTH`** | `(0, ±65)` / `(±65, 0)` along same-net axis | `2` | **FAIL** (`2 > 1`, Waiver) | **PASS w/ teardrop** (`2 <= 2`, outer `152.5 > 141.25 um`) | `45.0 um` (**PASS**) | `>= 175 um` (**PASS**) |
| **`4_VIA_PER_PTH`** | `(±65.0, ±65.0)` | `4` | **FAIL DR** (`4 > 1`) | **FAIL DR** (`4 > 2`, extends `38.2 um` past `282.5 um` lid) | `45.0 um` ortho | `127.5 um` (`PKG0.8`) / `45.0 um` (`PKG0.1` FAIL) |

## 2. Execution Commands
```powershell
# Compare 1-Via vs 2-Via vs 4-Via Prepreg Patterns + Export DRC SVG:
python -m agent04_pdn_architect.cad_cli.pth_4fco_4bco_router --density 8.0 --pkg-rule PKG0.8 --pp-pattern 2_VIA_ON_PTH

# Unified 8-Step CLI (any Rail Group):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group core --step 4 --pp-pattern 1_VIA_CENTER --pkg-rule PKG0.8
```
