---
name: pth_4fco_4bco_routing
description: >
  Step 2 (4FCO <-> 4BCO) Core PTH & Prepreg Via-Stack Routing Skill for Agent 04
  (PDN Architect). Solves staggered or 90-degree orthogonal (H&V aligned)
  same-net/diff-net PTH pitches for any user PTH density (5, 6, 7, 8 PTH/mm²),
  verifies Same-Net (>=270um) and Diff-Net (>=432.5um) pitch rules, strictly
  excludes PTHs/vias from all 4FCO eDTC Cavity/Guard/Inner-Core Keep-Out Zones
  (Body + 632.5um), and synthesizes 1-Stacked or 2-Stacked Prepreg vias
  (4FCO->3FCI->2FCI & 2BCI->3BCI->4BCO) matched to each layer's assigned
  VDD/VSS polarity.
---

# Step 2 (`4FCO` $\leftrightarrow$ `4BCO`) Core PTH & Prepreg Via-Stack Skill

## 1. The 5 Enforced Architectural Constraints

1. **User-Input PTH Density (`5, 6, 7, 8 PTH/mm²`):**
   - Solves exact grid pitches $(P_x, P_y)$ so that $D = \frac{10^6\,\mu\text{m}^2/\text{mm}^2}{P_x \times P_y}$ matches the user's target density in active (non-KOZ) silicon area.
2. **Strict Same-Net (`>= 270.0 µm`) & Different-Net (`>= 432.5 µm`) PTH Pitch Verification:**
   - **Same-Net PTH Pitch (`Rule`: $\ge 270.0\,\mu\text{m}$ PKG 0.8 / $216.5\,\mu\text{m}$ PKG 0.1)**
   - **Different-Net PTH Pitch (`Rule`: $\ge 432.5\,\mu\text{m}$ with `365 µm` inner pad + `67.5 µm` space)**
3. **Zero PTHs Inside `eDTC` Keep-Out Zones (`4FCO`..`2BCI`):**
   - Excludes all PTHs and Prepreg vias from the `4` under-`U7` `eDTC`s (`C2238`, `C2239`, `C2209`, `C2210`):
     - `DTC Cavity KOZ` = `Body + 300.0 µm` (Rules #6 & #18)
     - `2FCI`/`2BCI` `150 µm` Guard Metal Ring & Inner Core Keepout = `Body + 450.0 µm` (Rules #8, #24, #26)
     - `PTH Center KOZ` = `Body + 450.0 + 182.5 (inner pad radius) = Body + 632.5 µm` (**`0` PTHs inside KOZ**).
4. **`1-Stacked` vs. `2-Stacked` Prepreg Vias (`4FCO->3FCI->2FCI` & `2BCI->3BCI->4BCO`) Matched to Layer Polarity:**
   - Given layer net assignments (`4FCO=VSS, 3FCI=VDDUC0, 2FCI=VSS, 1FCI=VDDUC0, 1BCI=VSS, 2BCI=VDDUC0, 3BCI=VSS, 4BCO=VDDUC0`):
     - **`1_OR_2_STACK_BY_LAYER_NET`:** Places a **1-stack PP via** (`3FCI->2FCI` for `VDDUC0` on top; `2BCI->3BCI` for `VSS` on bottom) vs. **2-stack PP via** (`4FCO->3FCI->2FCI` for `VSS` on top; `2BCI->3BCI->4BCO` for `VDDUC0` on bottom).
     - **`2_STACK_FULL`:** Places a full **2-stack PP via** on both top (`4FCO->3FCI->2FCI`) and bottom (`2BCI->3BCI->4BCO`).
5. **User-Selectable PTH Pattern Topology (`--pattern`):**
   - **`STAGGERED`:** Alternating same-net vertical columns with odd columns shifted vertically by $\Delta y = P_y / 2$ ($P_y \ge 270.0\,\mu\text{m}$, $D_{\text{diff}} = \sqrt{P_x^2 + (P_y/2)^2} \ge 432.5\,\mu\text{m}$).
   - **`ORTHOGONAL_90DEG_VERTICAL`:** Strict **90° rectangular `(X, Y)` grid** ($\Delta y_{\text{offset}} = 0$) with same-net vertical columns (`Same-Net Vertical Pitch` $P_y \in [284.1, 400.0]\,\mu\text{m} \ge 270.0\,\mu\text{m}$, `Diff-Net Horizontal Pitch` $P_x \in [440.0, 500.0]\,\mu\text{m} \ge 432.5\,\mu\text{m}$).
   - **`ORTHOGONAL_90DEG_HORIZONTAL`:** Strict **90° rectangular `(X, Y)` grid** ($\Delta x_{\text{offset}} = 0$) with same-net horizontal rows (`Same-Net Horizontal Pitch` $P_x \in [284.1, 400.0]\,\mu\text{m} \ge 270.0\,\mu\text{m}$, `Diff-Net Vertical Pitch` $P_y \in [440.0, 500.0]\,\mu\text{m} \ge 432.5\,\mu\text{m}$).

---

## 2. CLI & SKILL Execution Commands
```powershell
python -m agent04_pdn_architect.cad_cli.pth_4fco_4bco_router --density 8 --pattern ORTHOGONAL_90DEG_VERTICAL --stack-mode 1_OR_2_STACK_BY_LAYER_NET
```
In Cadence Allegro / APD SKILL ([`pth_4fco_4bco_router_batch.il`](file:///<agent_workspace>/agent04_pdn_architect/scripts/pth_4fco_4bco_router_batch.il)):
- **Mode 1 — Pipe-Delimited Recipe Stream Import:**
  ```lisp
  pdnDispatchBatchJob("PTH_4FCO_4BCO_ROUTE" "FALSE")
  ```
- **Mode 2 — Direct Standalone SKILL Call by Pattern & Density:**
  ```lisp
  pdn_route_pth_4fco_4bco_by_pattern("U7" 8.0 "ORTHOGONAL_90DEG_VERTICAL" "1_OR_2_STACK_BY_LAYER_NET")
  ```
