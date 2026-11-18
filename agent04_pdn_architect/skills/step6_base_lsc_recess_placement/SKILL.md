---
name: step6_base_lsc_recess_placement
description: >
  Step 6 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Places 0201 LSCs (SM0201_690X390X550_01A / SM0201S_690X390X220_01C) strictly on
  CONDUCTOR/BASE (0 on SURFACE) inside non-rectangular/curved depopulated BGA pockets,
  meeting SRO-to-SRO (>=175/250 um), BGA-to-LSC SRO (>=500 um), EMIB shadow KOZ,
  180-deg cap-to-cap polarity alternation, and LSC_CAVITY mechanical recess rules
  (R>=500/508 um, BGA SRO->Cav >= 254 um, LSC SRO->Cav >= 225 um, Ext Cu KOZ >= 178 um).
---

# Step 6: LSC Placement (Design Rules + Curved Recess Compliant)

## 1. Mandatory Invariants (`AGENTS.md`)
1. **Strict `CONDUCTOR/BASE`**: Every LSC pin lands on `CONDUCTOR/BASE` (`mir=nil` for `SM0201_690X390X550_01A`; `mir=t` for `SM0201S_690X390X220_01C`), never `SURFACE`.
2. **`Pin 1 = <VDD_RAIL>` / `Pin 2 = VSS` + `180°` Alternation**: Adjacent columns alternate `0° <-> 180°`; horizontal remainder rows use `90° <-> 270°`.
3. **Curved BGA Recess (`LSC_CAVITY`)**: Exact Euclidean Distance Transform opening (`R_mill >= 508 um`), `BGA SRO -> Cavity >= 254 um`, `LSC SRO -> Cavity >= 225 um`, `External Cu KOZ >= 178 um`, and aligned non-zigzag packing (`u9_vddc_sram_lsc_new_rule_sandbox.py`).

## 2. Execution Commands
```powershell
# Unified 8-Step CLI (any Rail Group):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group core --step 6

# Dedicated U9 Aligned Recess Comparison & Curved All-3-Tasks Engines:
python -m agent04_pdn_architect.cad_cli.u9_vddc_sram_lsc_new_rule_sandbox
python -m agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine --all-3-tasks
```
