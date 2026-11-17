---
name: step8_transition_pp_core_connection
description: >
  Step 8 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Connects Frontside (6F/7F -> 5F -> 4FCO) and Backside (6B/7B -> 5B -> 4BCO) transition
  planes into the Prepreg (PP) and Core PTH layers using strict FastXYClearanceGrid
  protection and audits all 27 conductor layers via audit_via_continuity_and_zero_overlap
  (0 duplicate spans, 0 non-concentric pad overlaps, 0 diff-net concentric shorts).
---

# Step 8: Transition-to-PP & Core Connection (`0` Overlaps Across 27 Layers)

## 1. Bridging Mechanics & DRC Guarantees
- **Frontside Bridge**: Connects `Step 2` transition layers (`6F` VDD / `7F` VSS) through `V90_65_90_6F_5F_01A` & `V90_65_121_5F_4FCO_01A` (`<= 3` BU spans) onto `4FCO` / PP copper planes (`4FCO -> 3FCI -> 2FCI`) without landing inside `eDTC` KOZ (`700 um`) or `EMIB` KOZ (`200 um`).
- **Backside Bridge**: Connects `Step 7` transition layers (`6B` VDD / `7B` VSS) through `V90_65_90_5B_6B_01A` & `V121_65_90_4BCO_5B_01A` (`<= 3` BU spans) onto `4BCO` / PP copper planes (`2BCI -> 3BCI -> 4BCO`).
- **Zero-Overlap Clearance Offset**: Places transition bridge vias at conflict-free offsets (`±185 um` around Core PTH sites) checked across every touched conductor layer (`4FCO` / `4BCO` `121 um` pad vs `282.5 um` PTH lid) and verified with `audit_via_continuity_and_zero_overlap` (`non_concentric_pad_overlap_count == 0`).

## 2. Execution Command
```powershell
# Complete 8-Step End-to-End Verification (Step 1..Step 8):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group core `
  --step all `
  --vdd-top-layer 6F `
  --vss-top-layer 7F `
  --vdd-bot-layer 6B `
  --vss-bot-layer 7B
```
