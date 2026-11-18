---
name: step7_backside_bu_transition
description: >
  Step 7 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Climbs every BGA cluster (including Option 4's 4 center 0-overlap vias at +-45.5 um)
  and LSC terminal via upward from BASE (12B) to user transition layers below core
  (default 6B for VDD = 7 spans, 7B for VSS = 6 spans) while strictly obeying
  Max Stacked Via in BU <= 7 and 0.0 um pad overlap across BASE..6B.
---

# Step 7: Backside Transition Cluster Climb (`BASE -> 6B/7B`)

## 1. Backside Stackup Span Chain & Option 4 Compatibility
- **Climb sequence** (`padstack_library_index.csv`):
  1. `12B -> BASE`: `V90_65_90_12B_BASE_01A` (`r = 45.0 um`)
  2. `11B -> 12B`: `V83_55_83_11B_12B_01A-1` (`r = 41.5 um`)
  3. `10B -> 11B`: `V83_55_83_10B_11B_01A-1` (`r = 41.5 um`)
  4. `9B -> 10B`: `V77_49_77_9B_10B_01A` (`r = 38.5 um`)
  5. `8B -> 9B`: `V90_65_90_8B_9B_01A` (`r = 45.0 um`)
  6. `7B -> 8B`: `V90_65_90_7B_8B_01A` (`r = 45.0 um` -> `6` BU spans total to **`7B`** [`VSS`])
  7. `6B -> 7B`: `V90_65_90_6B_7B_01A` (`r = 45.0 um` -> `7` BU spans total to **`6B`** [`VDD`], exact BU ceiling!)
- All backside BU vias from `BASE` to `6B` have pad radius `<= 45.0 um` (`<= 90.0 um` diameter), so Option 4's `(±45.5, ±45.5) um` cluster (`91.0 um` pitch) climbs cleanly all the way to `6B` / `7B` with `0.0 um` pad overlap and `<= 7` stacked spans!

## 2. Execution Command
```powershell
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group hbm `
  --step 7 `
  --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP `
  --vdd-bot-layer 6B `
  --vss-bot-layer 7B `
  --max-bu-stack 7
```
