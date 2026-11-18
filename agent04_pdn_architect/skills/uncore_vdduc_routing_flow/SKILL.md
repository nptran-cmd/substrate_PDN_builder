---
name: uncore_vdduc_routing_flow
description: >
  End-to-End 8-Step PDN Routing Flow for the Uncore (VDDUC0..3 + VSS) Rail Group on LDB dies
  (U7, U5, U8, U6), covering Surface ratio/full VIA (Step 1), Front BU 6F/7F transition (Step 2),
  Core PTH 4..11/mm2 + eDTC KOZ/Guard Metal (Step 3), PP 1/2/4-via + DR audit (Step 4), BGA
  Options 1..4 incl. 0-overlap center 4-via (Step 5), LSC + curved recess (Step 6), Back BU
  6B/7B cluster climb (Step 7), and Transition-to-PP/Core zero-overlap bridge (Step 8).
---

# Uncore (`VDDUC0..3`) 8-Step PDN Routing Flow (`LDB`: `U7, U5, U8, U6`)

## 1. Domain Parameters
- **Target Dies**: `U7` (`VDDUC0`), `U5` (`VDDUC1`), `U8` (`VDDUC2`), `U6` (`VDDUC3`) + `VSS` return
- **Key `eDTC`s (`U7`)**: `C2238, C2239, C2209, C2210` (`4FCO`, `300 um` cavity KOZ + `150 um` guard metal)
- **EMIB Bridges (`U7`)**: `U28, U32, U35, U38, U47, U48, U49`

## 2. Full 8-Step Execution Command
```powershell
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group uncore `
  --step all `
  --ratio 4:2 `
  --direction VERTICAL `
  --vdd-top-layer 6F `
  --vss-top-layer 7F `
  --pth-density 8.0 `
  --pth-pattern STAGGERED `
  --pkg-rule PKG0.8 `
  --pp-pattern 1_VIA_CENTER `
  --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP `
  --vdd-bot-layer 6B `
  --vss-bot-layer 7B
```

See also: [`vdduc_vddch_routing_flow`](file:///<agent_workspace>/agent04_pdn_architect/skills/vdduc_vddch_routing_flow/SKILL.md) and Steps 1–8 (`step1_surface_bump_routing` .. `step8_transition_pp_core_connection`).
