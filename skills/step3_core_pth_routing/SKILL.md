---
name: step3_core_pth_routing
description: >
  Step 3 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Routes Core PTH (2FCI <-> 2BCI, V282_5_150_282_5_2FCI_2BCI_01B) across a configurable
  4 to 11 PTH/mm² density sweep in 3 patterns (STAGGERED, ORTHOGONAL_90DEG_VERTICAL,
  ORTHOGONAL_90DEG_HORIZONTAL), enforcing 4FCO eDTC 300 um Cavity KOZ + 150 um Guard Metal
  + 67.5 um Core L/S (700.0 um PTH center KOZ) and PKG 0.8 vs PKG 0.1 pitch rules.
---

# Step 3: Core PTH Routing (`4 to 11 PTH/mm²`, Pattern + `eDTC` KOZ & Guard Metal)

## 1. Pitch Rules & Density Sweep (`4..11 PTH/mm²`)
- **`PKG 0.8` (`--pkg-rule PKG0.8`)**: Same-net PTH min pitch `>= 270.0 um`, diff-net `>= 432.5 um` (`365 um` inner pad + `67.5 um` space). Supports `4..8 PTH/mm²` IDS compliant and caps gracefully at `9.01 PTH/mm²` (`STAGGERED`) / `8.56 PTH/mm²` (`ORTHOGONAL 90° H/V`).
- **`PKG 0.1` (`--pkg-rule PKG0.1`)**: Same-net PTH min pitch `>= 216.5 um`, diff-net `>= 350.0 um`. Supports full **`4, 5, 6, 7, 8, 9, 10, 11 PTH/mm²`** cleanly with `0` pitch DRC violations (`Staggered` ceiling `13.88/mm²`, `90° Ortho` ceiling `13.20/mm²`).
- **`eDTC` KOZ & Guard Metal (`4FCO..4BCO`)**: Excludes every PTH within `700.0 um` of `eDTC` body edge (`300 um` Cavity KOZ + `150 um` Guard Metal + `182.5 um` PTH inner pad radius + `67.5 um` min Core space), ensuring `0` PTHs in KOZ.

## 2. Execution Commands
```powershell
# Full 4..11 PTH/mm² Standalone Suite (PKG 0.1 enables 9..11 PTH/mm²):
python -m agent04_pdn_architect.cad_cli.pth_4fco_4bco_router --density 10.0 --pattern STAGGERED --pkg-rule PKG0.1

# Unified 8-Step CLI (any Rail Group):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group uncore --step 3 --pth-density 10.0 --pth-pattern STAGGERED --pkg-rule PKG0.1
```
