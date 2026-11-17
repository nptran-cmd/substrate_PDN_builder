---
name: step1_surface_bump_routing
description: >
  Step 1 PDN Routing Skill (All Rail Groups: Core VDDC/SRAM, Uncore VDDUC, Chiplet VDDCH, HBM):
  Routes C4 die bumps on SURFACE (TOP / 12Cu) with either FULL via-in-pad (100% VIP) or any
  user-specified VDD:VSS ratio (e.g., 4:2, 5:2, 3:1, M:N) and strapping direction
  (VERTICAL, HORIZONTAL, BOTH), jogging/strapping every floating bump to an adjacent via'd
  same-net neighbor (0 floating bumps, >= 18.0 um SURFACE trace clearance).
---

# Step 1: Route on `SURFACE` (`FULL` or `VDD:VSS` Ratio + Floating-Bump Jogging)

## 1. Supported Rail Groups
- **Core (`core`)**: `U9` (`VDDC0`, `VDD_0P8_SRAM_CC0`, `VSS`)
- **Uncore (`uncore`)**: `U7` (`VDDUC0`, `VSS`)
- **Chiplet (`chiplet`)**: `U2` (`VDDCH0`, `VSS`)
- **HBM (`hbm`)**: `U13` (`VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5`, `VDDQL5`, `VPP_1P8_HBM_MEM5`, `VSS`)

## 2. Design Rules & Solver Behavior
- **Full Via-in-Pad (`--ratio FULL`)**: Drops `V77_49_77_SURFACE_12F_01A` (`77 um` pad / `49 um` drill) on every VDD and VSS C4 bump (`0` SURFACE CLINEs).
- **Ratio Mode (`--ratio 4:2`, `5:2`, `3:1`, `M:N`)**: Solves unit-cell period $P = \max(M+1, N+1, 6)$ so un-via'd bumps are always within 1 hop (`<= 260 um`) of a same-net via'd bump, strapping every floating bump via `24 um` `SURFACE` CLINEs (`>= 40 um` edge gap vs adjacent opposite-net bumps `>= 18.0 um` rule). Supports `VERTICAL`, `HORIZONTAL`, or `BOTH` (`0` floating bumps).
- **Core U9 3:1 C/S Jog Engine**: Also available via `u9_vddc_sram_surface_3to1_jog_router.py` (`>= 15 um` clearance around intervening `77 um` C4 bumps).

## 3. Execution Commands
```powershell
# Unified 8-Step CLI (Step 1 only, any rail group):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group uncore --step 1 --ratio 4:2 --direction VERTICAL

# Parameterized Step 1 Standalone Comparison (FULL vs 4:2 vs 5:2 + Custom):
python -m agent04_pdn_architect.cad_cli.surface_layer1_router --ratio 5:2 --direction HORIZONTAL
```
