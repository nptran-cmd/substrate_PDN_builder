---
name: step2_frontside_bu_transition
description: >
  Step 2 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Stacks same-net Build-Up (BU) vias downward from SURFACE (12Cu) to user target
  transition layers (default 6F for VDD, 7F for VSS) while strictly enforcing
  Substrate Design Rules (Max Stacked Via in BU <= 7 normal, <= 3 inside EMIB HSIO void)
  and per-conductor-layer zero via pad overlap.
---

# Step 2: Frontside Transition Layer Routing (`SURFACE -> 6F/7F`)

## 1. Frontside Stackup Span Chain & Limits
- **Span sequence** (`padstack_library_index.csv`):
  1. `SURFACE -> 12F`: `V77_49_77_SURFACE_12F_01A`
  2. `12F -> 11F`: `V77_49_77_12F_11F_01A`
  3. `11F -> 10F`: `V77_49_77_11F_10F_01A`
  4. `10F -> 9F`: `V77_49_77_10F_9F_01A`
  5. `9F -> 8F`: `V90_65_90_9F_8F_01A`
  6. `8F -> 7F`: `V90_65_90_8F_7F_01A` (`6` BU spans -> `VSS` default `7F`)
  7. `7F -> 6F`: `V90_65_90_7F_6F_01A` (`7` BU spans -> `VDD` default `6F`, exact BU ceiling!)
- **Hard Rules (`Via Rules_gid_107930080.csv` & `Substrate Design Rules_gid_1425021083.csv`)**:
  - `Max Stacked Via Landing on Trace/Shape (in BU) <= 7` (`<= 3` inside EMIB/HSIO void).
  - Never exceed `7` stacked spans (`6F` is 7 spans below `SURFACE`; dropping straight to `5F` would be 8 spans and violates BU stacking).
  - `EMIB` `157.5 um` cavity KOZ enforced on `12F/11F/10F`.

## 2. Execution Command
```powershell
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow `
  --rail-group core `
  --step 2 `
  --vdd-top-layer 6F `
  --vss-top-layer 7F `
  --max-bu-stack 7
```
