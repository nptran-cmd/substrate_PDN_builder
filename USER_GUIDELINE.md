# Team Onboarding & User Guideline — Method 1 (`substrate_PDN_builder` + Local `AIstudio`)

> **Who this is for:** All package & substrate PDN engineers cloning [`substrate_PDN_builder`](https://github.com/nptran-cmd/substrate_PDN_builder) onto their own **Windows** or **Linux** workstation.  
> **Related Docs:** [README.md](README.md) · [TODO.md](TODO.md) · [TEMPLATE.md](TEMPLATE.md) · [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) · [AIstudio/LINUX_SETUP.md](AIstudio/LINUX_SETUP.md)

---

## 1. Architecture Overview (How Method 1 Works)

Method 1 keeps **100% of proprietary `.mcm` design files on your own workstation/workspace**, while syncing shared PDN skills, Python solvers, SKILL scripts, and the `AIstudio` Web UI from GitHub:

```text
+-------------------------------------------------------------------------+
| GitHub Repository: https://github.com/nptran-cmd/substrate_PDN_builder  |
|  - 19 PDN Skills (skills/*) + .gemini/GEMINI.md                         |
|  - 4-Rail x 8-Step Python Engines (agent04_pdn_architect/cad_cli/)      |
|  - Headless Cadence APD SKILL Importers (.il) & 27-Layer JSON Templates |
|  - Local Cross-Platform AIstudio Web UI (AIstudio/)                     |
+------------------------------------+------------------------------------+
                                     |  git clone / git pull
                                     v
+-------------------------------------------------------------------------+
| Engineer's Workstation (Windows or Linux)                               |
|                                                                         |
|  [1] Repo Folder (e.g., C:\tools\substrate_PDN_builder)                 |
|      └─ AIstudio Web UI (http://127.0.0.1:8765)                         |
|           ├─ "Direct" Mode -> Runs Python/APD directly (no AI login)    |
|           └─ "Run" Mode    -> Embedded ConPTY/PTY + Jetski / Gemini CLI |
|                                    |                                    |
|                                    v  SUBSTRATE_WORK_DIR                |
|  [2] Isolated Working Folder (e.g., C:\PDN_builde or ~/pdn_workspaces)  |
|      ├─ MCM_template/<design>.mcm   (100% Read-Only input)              |
|      ├─ stage1_inputs/              (Step 0 extracted CSV/JSON + SVG)   |
|      ├─ pdn_sandbox/                (Steps 1..8 SVGs, recipes, audits)  |
|      └─ outputs/                    (New DRC-checked output .mcm)       |
|                                    |                                    |
|                                    v  Headless Batch                    |
|  [3] Local Cadence APD (apd.exe on Windows OR run_apd.sh on Linux)      |
+-------------------------------------------------------------------------+
```

### Why Working Folder Isolation Matters
- **Your `.mcm` binaries never go inside the Git repo.** Every output (`.svg`, `.csv`, `.json`, `pdn_import_recipe.txt`, and `output.mcm`) writes strictly to your selected **Working Folder** (`SUBSTRATE_WORK_DIR`).
- **`AIstudio` SVG Preview is strictly scoped** to your selected Working Folder (on initial load before selecting a Working Folder, repo SVGs are intentionally hidden).

---

## 2. Prerequisites (Check Once Per Machine)

| Requirement | Windows Workstation | Linux Workstation |
| :--- | :--- | :--- |
| **Git** | `git --version` | `git --version` |
| **Python** | Python `3.10+` (`python --version`) | Python `3.10+` (`python3 --version`) |
| **Cadence APD** *(for Step 0 `.mcm` extract & Stage 4 `.mcm` build)* | `apd.exe` installed (e.g., `C:\Cadence\SPB_25.1\tools\bin\apd.exe` or `SPB_26.1`) with valid license | `run_apd.sh` (set `CADENCE_RUN_APD_SH` or `$HOME/cadence/installs/run_apd.sh`) or `apd` on `$PATH`, plus `xvfb-run` if headless |
| **AI CLI** *(optional — only needed for `Run` / Terminal mode; `Direct` mode works without it)* | `jetski` or `gemini` CLI installed & signed in | `jetski` or `gemini` CLI installed & signed in |

> **Important:** Even if Cadence APD is only on your Linux server (not your Windows laptop), you can still run **all Python Steps 1–8 + SVG Preview locally on Windows**, or launch `AIstudio` on your Linux workstation and connect from your laptop browser via SSH tunnel (see **Path C** below).

---

## 3. First-Time Setup (Choose Your Platform)

### Path A — Windows Workstation (Local `AIstudio`)

```powershell
# 1. Clone the repository into a clean tools folder (outside your .mcm workspace)
mkdir C:\tools -Force
cd C:\tools
git clone https://github.com/nptran-cmd/substrate_PDN_builder.git
cd substrate_PDN_builder

# 2. Install AIstudio Python dependencies
python -m pip install -r AIstudio/requirements.txt

# 3. Create your isolated PDN working folder and drop in a read-only .mcm
mkdir C:\PDN_builde\MCM_template -Force
# Copy your source <design>.mcm into C:\PDN_builde\MCM_template\<design>.mcm

# 4. Launch AIstudio (opens http://127.0.0.1:8765 automatically)
.\AIstudio\start_studio.ps1
```

---

### Path B — Linux Workstation (with Native Cadence `run_apd.sh` / `apd`)

```bash
# 1. Clone the repository
mkdir -p ~/tools && cd ~/tools
git clone https://github.com/nptran-cmd/substrate_PDN_builder.git
cd substrate_PDN_builder

# 2. Optional: point to your Cadence launch wrapper if not at ~/cadence/installs/run_apd.sh
# export CADENCE_RUN_APD_SH="/path/to/cadence/installs/run_apd.sh"

# 3. Bootstrap virtual environment (.venv_linux) and launch AIstudio
chmod +x AIstudio/start_linux_studio.sh
./AIstudio/start_linux_studio.sh --bootstrap
```
* Open **`http://127.0.0.1:8765`** in Linux Chrome.
* Your default working folder on Linux is **`~/pdn_workspaces`** (override with `--work-dir /path/to/work`).

---

### Path C — Windows/macOS Laptop Controlling `AIstudio` on a Linux Cadence Server

If Cadence APD runs on your Linux workstation/server while you work from a Windows laptop:

1. Start `AIstudio` on the Linux host (inside `tmux` so it stays alive):
   ```bash
   tmux new -s aistudio
   cd ~/tools/substrate_PDN_builder
   ./AIstudio/start_linux_studio.sh --bootstrap
   ```
2. On your Windows laptop (from your local clone of `substrate_PDN_builder`), open the SSH tunnel on local port **`8766`** (avoids colliding with local Windows Studio on `8765`):
   ```powershell
   .\AIstudio\open_linux_tunnel.ps1 -LinuxHost <your-linux-host> -OpenBrowser
   ```
3. Browse to **`http://127.0.0.1:8766`** — click **Upload .mcm** in the top bar to stream multi-GB `.mcm` files directly into Linux `~/pdn_workspaces/MCM_template/`.

---

### Path D — Pure CLI / Terminal Agent Usage (Without Opening `AIstudio`)

If you prefer running directly with `jetski` or `gemini` in a terminal:

```powershell
# PowerShell: isolate outputs to C:\PDN_builde and optionally install skills globally
$env:SUBSTRATE_WORK_DIR = "C:\PDN_builde"
Copy-Item -Path ".\skills\*" -Destination "$HOME\.gemini\config\skills\" -Recurse -Force
```

```bash
# Linux/macOS Bash:
export SUBSTRATE_WORK_DIR="$HOME/pdn_workspaces"
mkdir -p ~/.gemini/config/skills
cp -r skills/* ~/.gemini/config/skills/
```

Then start `gemini` or `jetski` inside the repo folder and paste any prompt from [TEMPLATE.md](TEMPLATE.md) or [prompts/EXAMPLE_PROMPTS.md](prompts/EXAMPLE_PROMPTS.md).

---

## 4. Step-by-Step Daily Workflow in `AIstudio`

Follow these 8 steps in order for any new substrate `.mcm`:

1. **Set Your Working Folder (Top Bar)**
   * Type `C:\PDN_builde` (Windows) or `~/pdn_workspaces` (Linux) into **Working Folder** and click **Apply** (or **Browse...** / **Folders**).
   * Confirm the status badge detects your `.mcm` inside `<working_dir>/MCM_template/`. *(If you don't have one copied yet, click **Upload .mcm**.)*
2. **Select Your Rail Group Tab**
   * `1. Core (VDDC/SRAM)` — `U9 / U12 / U88 / U10` (`VDDC* + VDD_0P8_SRAM_CC* + VSS`)
   * `2. Uncore (VDDUC)` — `U7 / U5 / U8 / U6` (`VDDUC0..3 + VSS`)
   * `3. Chiplet (VDDCH)` — `U2 / U4 / U3 / U1` (`VDDCH0..3 + VSS`)
   * `4. HBM` — `U13..U24` (`VDDQ + VDDC + VDDQL + VPP + HBMPHY + EMIB + VSS`)
   * `5. Full A-Z & Stage 1` — Full-package and Stage 1 utilities
3. **Run Step 0 — Extract Data from `.mcm`**
   * Click **Direct** (runs deterministic Python + headless Cadence APD without needing Jetski) or **Run** (sends to the Jetski terminal) on **`0. Extract Data from .mcm (Stage 1 -> Working Folder)`**.
   * Verify `<working_dir>/stage1_inputs/` contains extracted CSVs (`bga_map.csv`, `bump_map.csv`, `edtc_symbols.csv`, `lsc_placed_map.csv`, `stackup_53layers.csv`) and `stage1_data_summary.svg` appears in **SVG Preview**.
4. **Run Steps 1–8 & Inspect Every SVG**
   * Work top-to-bottom (`Step 1` `SURFACE` → `Step 2` Front BU → `Step 3` Core `PTH` → `Step 4` `PP` → `Step 5` `BGA` → `Step 6` `BASE` `LSC` → `Step 7` Back BU → `Step 8` Full 27-Layer Core Bridge).
   * Click **Edit** on any card to adjust CLI flags (`--ratio`, `--direction`, `--pth-density`, `--bga-pattern`) in the **Prompt Composer**, then click **Run Direct** or **Run in Terminal**.
   * Keep **Auto-Watch** enabled on **SVG Preview** so every run updates live; use **Fit**, `+`, `-`, and drag-pan to verify keepouts, `180°` LSC alternations, and `9F->5F` / `9B->5B` continuity.
5. **Run Sandbox & Zero-Overlap Audit Before `.mcm` Mutation**
   * Verify `audit_via_continuity_and_zero_overlap` reports `0` pad overlaps across all 27 conductor layers and `0` dangling vias.
6. **Build Your New `.mcm` & Download Outputs**
   * Execute Stage 4 `.mcm` build (using `pdn_27layer_template_runner.py --stage implement-mcm` or `full_package_all_dies_pdn.py`).
   * **Rule:** Always write to a **new** `.mcm` filename — never overwrite `MCM_template/<design>.mcm`.
   * Use **Outputs** in the top bar to list or download generated `.mcm`, `.svg`, `.csv`, and recipe files.

---

## 5. Staying Up to Date (`git pull`)

Whenever new PDN rules, bug fixes, or skills are announced:

```bash
cd <your-clone>/substrate_PDN_builder
git pull origin main
```

* **Windows:** If `AIstudio/requirements.txt` changed, re-run `python -m pip install -r AIstudio/requirements.txt`, then restart `.\AIstudio\start_studio.ps1`.
* **Linux:** Run `./AIstudio/start_linux_studio.sh --bootstrap` to update `.venv_linux` and restart.
* **Global Skills:** If you copied skills into `~/.gemini/config/skills/`, re-run the copy command from Path D.

---

## 6. Troubleshooting Quick Reference

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **SVG Preview says `"Select a Working Folder (repo SVGs hidden)"`** | Default startup hides internal repo SVGs so you never confuse sample SVGs with your own design | Enter your working folder (`C:\PDN_builde` or `~/pdn_workspaces`) and click **Apply** |
| **`Run` fails in terminal ("jetski not found" or not logged in)** | Jetski CLI not installed or not authenticated | Use **Direct** / **Run Direct** button (runs pure Python + Cadence APD with zero AI login), or click **Launch Jetski** -> **Login (LOAS)** / **Login (Browser)** |
| **Step 0 / Stage 4 fails with `apd` not found** | Cadence APD binary path differs from default | On Windows, check `C:\Cadence\SPB_25.1` / `26.1` on `PATH`; on Linux, export `CADENCE_RUN_APD_SH=/path/to/run_apd.sh` |
| **Linux startup fails with missing `starlette` / `python-multipart`** | Virtual environment not bootstrapped | Re-run `./AIstudio/start_linux_studio.sh --bootstrap` |
| **Port `8765` already in use** | Another `AIstudio` instance is running | Pass `-Port 8770` (Windows) or `--port 8770` (Linux) |
| **Linux headless APD complains about `DISPLAY`** | No X server attached in SSH/`tmux` session | Install/verify `xvfb-run` (`which xvfb-run`); `CadenceBatchRunner` auto-prepends `xvfb-run -a` |
