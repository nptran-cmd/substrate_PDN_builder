---
name: surface_layer1_routing
description: >
  Layer 1 (SURFACE / TOP) Parameterized Die Bump-Via & Trace-Ganging Skill for
  Agent 04 (PDN Architect). Routes any target RefDes (e.g., U7) on SURFACE (12Cu)
  with either Full Via-on-Bump (100% VIA) or any user-specified M:N VDD:VSS via
  ratio (e.g., 4:2, 5:2, 3:1) and strapping direction (VERTICAL, HORIZONTAL, or
  BOTH 2D H+V), connecting un-via'd bumps to adjacent same-net via'd bumps via
  DRC-clean 24um SURFACE CLINE straps, exporting XML-validated SVGs and
  executing O(N) SKILL batch creation in Cadence Allegro / APD (.mcm).
---

# Layer 1 (`SURFACE` / `TOP`) Parameterized Bump-Via & Trace-Ganging Skill

## 1. Architectural Purpose
On the `SURFACE` (`TOP`, `12Cu`) layer under a flip-chip die (such as `U7` `HUTTON_HILL_LDB_BC_A0`), power (`VDDUC0`) and ground (`VSS`) C4 bumps (`C35_21_DP_01A`, `77 µm` Cu pad, `35 µm` SRO) sit on a staggered checkerboard column lattice:
- **Vertical Same-Net Pitch (along a column):** $\Delta x = 0\,\mu\text{m},\;\Delta y = 180.99\,\mu\text{m}$ (adjacent opposite-polarity column is at $\Delta x = \pm 93.79\,\mu\text{m}$).
- **Horizontal Same-Net Pitch (along a row):** $\Delta y = 0\,\mu\text{m},\;\Delta x = 187.58\,\mu\text{m}$ (adjacent opposite-polarity row is at $\Delta y = \pm 90.50\,\mu\text{m}$).

When the architect chooses **not** to drop a `SURFACE -> 12F` via (`V77_49_77_SURFACE_12F_01A`, `77 µm` pad / `49 µm` laser drill) on every bump—for example, to enforce a **`4:2`** or **`5:2`** `VDD:VSS` via ratio and open antipad-free routing channels on `12F`—every un-via'd bump must be electrically strapped on `SURFACE` (`12Cu`) to an adjacent via'd bump of the same net using a `24.0 µm` wide `CLINE` (`>= 18.0 µm` `12Cu` Unrestricted minimum width):
- **`VERTICAL` Straps (`dy = 180.99 µm`):** Edge-to-edge clearance to opposite-net `77 µm` pads/vias = $93.79 - 38.50 - 12.00 = \mathbf{43.29\,\mu\text{m}} \ge 18.0\,\mu\text{m}$ (`Rule 3.4.1.41`, **`+25.29 µm` margin**).
- **`HORIZONTAL` Straps (`dx = 187.58 µm`):** Edge-to-edge clearance to opposite-net `77 µm` pads/vias = $90.50 - 38.50 - 12.00 = \mathbf{40.00\,\mu\text{m}} \ge 18.0\,\mu\text{m}$ (`Rule 3.4.1.41`, **`+22.00 µm` margin**).
- **`BOTH` (`2D H+V` Straps):** Connects each un-via'd bump to both its vertical and horizontal 1-hop via'd neighbors (`L`-strap / `T`-strap) with $\ge 40.00\,\mu\text{m}$ DRC clearance.

---

## 2. Parameterized `M:N` Unit-Cell Solver
Given any user-input ratio string (`--ratio FULL | 4:2 | 5:2 | 3:1 | M:N`) and direction (`--direction VERTICAL | HORIZONTAL | BOTH`):
1. Determines unit-cell period $P = \max(M + 1, N + 1, 6)$ (or user `--cell-period P`) so both `VDD` and `VSS` have strapped bumps on `SURFACE` while achieving an exact **`M:N` via ratio** per cell:
   - **`FULL` (`1:1`):** `6 VDD vias : 6 VSS vias` (`0` straps).
   - **`4:2` (`2.0:1`):** `4 VDD vias + 2 strapped VDD bumps` (indices `{0,1,3,4}` kept, `{2,5}` strapped) : `2 VSS vias + 4 strapped VSS bumps` (indices `{1,4}` kept, `{0,2,3,5}` strapped).
   - **`5:2` (`2.5:1`):** `5 VDD vias + 1 strapped VDD bump` (indices `{0,1,2,3,4}` kept, `{5}` strapped) : `2 VSS vias + 4 strapped VSS bumps` (indices `{1,4}` kept, `{0,2,3,5}` strapped).
2. Any isolated die-edge bump without a 1-hop neighbor (`<= 260 µm`) automatically receives a fallback via so **0 bumps ever float**.

---

## 3. CLI & SKILL Execution Commands

### A. Python Sandbox SVG & Recipe Generator ([`surface_layer1_router.py`](file:///<agent_workspace>/agent04_pdn_architect/cad_cli/surface_layer1_router.py))
```powershell
python -m agent04_pdn_architect.cad_cli.surface_layer1_router --ratio 5:2 --direction HORIZONTAL --trace-width 24.0
```

### B. Cadence Allegro / APD SKILL Router ([`surface_bump_router_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/surface_bump_router_batch.il))
- **Mode 1 — Pipe-Delimited Recipe Stream Import (`O(1)` `makeTable` lookup):**
  ```lisp
  pdnDispatchBatchJob("SURFACE_BUMP_ROUTE" "FALSE")
  ```
- **Mode 2 — Direct Parameterized SKILL Call on Any `RefDes`:**
  ```lisp
  pdn_route_surface_refdes_by_ratio("U7" "VDDUC0" "VSS" "5:2" "HORIZONTAL" 24.0)
  ```
