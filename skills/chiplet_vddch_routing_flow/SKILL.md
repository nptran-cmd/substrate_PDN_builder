---
name: chiplet_vddch_routing_flow
description: >
  End-to-End 8-Step PDN Routing Flow for the Chiplet (VDDCH0..3 + VSS) Rail Group on LDC dies
  (U2, U4, U3, U1), covering Surface ratio/full VIA (Step 1), Front BU 6F/7F transition (Step 2),
  Core PTH 4..11/mm2 + eDTC KOZ/Guard Metal (Step 3), PP 1/2/4-via + DR audit (Step 4), BGA
  Options 1..4 incl. 0-overlap center 4-via (Step 5), LSC + curved L-pocket recess (Step 6),
  Back BU 6B/7B cluster climb (Step 7), and Transition-to-PP/Core zero-overlap bridge (Step 8).
---

# Chiplet (`VDDCH0..3`) 8-Step PDN Routing Flow (`LDC`: `U2, U4, U3, U1`)

## 1. Domain Parameters
- **Target Dies**: `U2` (`VDDCH0`), `U4` (`VDDCH1`), `U3` (`VDDCH2`), `U1` (`VDDCH3`) + `VSS` return
- **Key `eDTC`s (`U2`)**: `C2277, C2278` (`4FCO`, `300 um` cavity KOZ + `150 um` guard metal)
- **EMIB Bridges (`U2`)**: `U39, U35` (plus diagonally notched L-shaped `LSC_CAVITY` pocket `U2_VDDCH0_North2_L`)

## 2. Full 8-Step Execution Command
```powershell
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group chiplet `
  --step all `
  --ratio 5:2 `
  --direction HORIZONTAL `
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
