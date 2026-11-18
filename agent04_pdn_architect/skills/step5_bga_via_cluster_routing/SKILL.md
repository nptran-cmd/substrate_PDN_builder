---
name: step5_bga_via_cluster_routing
description: >
  Step 5 PDN Routing Skill (All Rail Groups: Core, Uncore, Chiplet, HBM):
  Routes 12B <-> BASE BGA via clusters (V90_65_90_12B_BASE_01A, 90 um pad / r=45.0 um)
  across ALL Power BGAs and VSS BGAs using 4 selectable patterns: Option 1 (4-Via 2x2
  Square +-110 um), Option 2 (5-Via Quincunx), Option 3 (6-Via Hex Ring R=195 um), and
  Option 4 (4-Via Center Cluster at +-45.5 um, 91.0 um pitch, +1.0 um gap / 0.0 um pad overlap).
---

# Step 5: BGA Via Cluster Routing (Options 1–4, All VDD + VSS BGAs)

## 1. Supported BGA Via Cluster Patterns (`V90_65_90_12B_BASE_01A`, `r = 45.0 um`)
Applied uniformly across **all domain Power BGA pads and all `VSS` BGA pads** on `12B -> BASE`:

| Pattern Option | Coordinate Offsets `(dx, dy)` in `um` | Vias / BGA | Pitch (`um`) | Pad Overlap |
| :--- | :--- | :---: | :---: | :--- |
| **`OPTION1_4VIA_SQUARE_2X2`** | `(±110.0, ±110.0)` | `4` | `220.0` | `0.0 um` (`130.0 um` gap) |
| **`OPTION2_5VIA_QUINCUNX`** | `(0, 0)` + `(±135.0, ±135.0)` | `5` | `190.9` | `0.0 um` (`100.9 um` gap) |
| **`OPTION3_6VIA_HEX_RING`** | `(0, ±195.0)` + `(±137.9, ±137.9)` | `6` | `195.0` | `0.0 um` (`105.0 um` gap) |
| **`OPTION4_4VIA_CENTER_ZERO_OVERLAP`** | `(±45.5, ±45.5)` | `4` | `91.0` | **`0.0 um` (`+1.0 um` edge gap, centered!)** |

## 2. Execution Commands
```powershell
# Unified 8-Step CLI (Pattern 4: 4 vias centered at ~0 overlap on ALL VDD + VSS BGAs):
python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group core --step 5 --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP

# Standalone 4-Option Comparison & SVG Generator:
python -m agent04_pdn_architect.cad_cli.base_lsc_bga_router --sro-space 175.0
```
