# Method 1 Team Rollout & Onboarding TODO List (`substrate_PDN_builder`)

> **Goal:** Roll out **Method 1 (Local Workstation + GitHub + `AIstudio`)** cleanly to all packaging engineers with zero infra blockers.  
> **See also:** [USER_GUIDELINE.md](USER_GUIDELINE.md) · [TEMPLATE.md](TEMPLATE.md) · [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md)

---

## Part 1 — Repo Owner (`nptran`) Pre-Share Checklist (Complete Before Sharing)

- [ ] **1.1 Confirm Team Docs & Templates Are Present:** Verify [README.md](README.md), [USER_GUIDELINE.md](USER_GUIDELINE.md), [TODO.md](TODO.md), [TEMPLATE.md](TEMPLATE.md), and [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) contain zero internal/broken local paths and clearly document `<working_dir>/MCM_template/<design>.mcm`.
- [ ] **1.2 Run Safety & Cleanliness Audit:** Execute `audit_repo_safety.py` against `substrate_PDN_builder` and confirm `Audit Result : PASS` (`0` `.mcm` files, `0` secrets, `0` hardcoded user paths, all `19` skills valid).
- [ ] **1.3 Run Unit & Studio Verification Tests:**
  ```powershell
  python -m unittest AIstudio.tests.test_studio AIstudio.tests.test_linux_direct_studio AIstudio.tests.test_pdn_8step -v
  ```
- [ ] **1.4 Push Latest Docs/Templates to GitHub (`origin/main`):**
  ```powershell
  git add -A
  git commit -m "docs: add Method 1 user guideline, rollout TODO, prompt/skill templates"
  git push origin main
  ```
- [ ] **1.5 Prepare Shared Golden Starter `.mcm` Location:** Place the team's baseline read-only `.mcm` (plus padstack library if needed on shared drive/Linux EDA disk) and note its copy path in your team announcement (do **not** commit `.mcm` files to GitHub).
- [ ] **1.6 Send Team Kickoff Message:** Share:
  1. Repo URL: `https://github.com/nptran-cmd/substrate_PDN_builder.git`
  2. Start link: `USER_GUIDELINE.md`
  3. Where to copy their starter `.mcm` into `<working_dir>/MCM_template/`
  4. Support channel / office hours for first-run Q&A.

---

## Part 2 — Team Member First-Time Setup Checklist (~10 Minutes)

Complete once on your Windows or Linux workstation:

- [ ] **2.1 Verify Prerequisites:**
  - `git --version` works.
  - `python --version` (Windows) or `python3 --version` (Linux) is `3.10+`.
  - Cadence APD works (`apd.exe` on Windows or `run_apd.sh` / `apd` + `xvfb-run` on Linux).
- [ ] **2.2 Clone the Repository:**
  ```bash
  git clone https://github.com/nptran-cmd/substrate_PDN_builder.git
  cd substrate_PDN_builder
  ```
- [ ] **2.3 Install & Start `AIstudio`:**
  - **Windows:** `python -m pip install -r AIstudio/requirements.txt` → `.\AIstudio\start_studio.ps1`
  - **Linux:** `chmod +x AIstudio/start_linux_studio.sh && ./AIstudio/start_linux_studio.sh --bootstrap`
  - **Windows Laptop -> Linux Server:** Run `./AIstudio/start_linux_studio.sh --bootstrap` on Linux, then run `.\AIstudio\open_linux_tunnel.ps1 -LinuxHost <linux-host> -OpenBrowser` on Windows (`http://127.0.0.1:8766`).
- [ ] **2.4 Create Your Isolated Working Folder:**
  - Create `C:\PDN_builde\MCM_template\` (Windows) or `~/pdn_workspaces/MCM_template/` (Linux).
  - Copy your starting `.mcm` into `MCM_template/<design>.mcm` (or upload via **Upload .mcm** in `AIstudio`).
- [ ] **2.5 Select Working Folder in `AIstudio`:**
  - Enter your Working Folder path in the top bar → click **Apply** → confirm your `.mcm` count badge updates.
- [ ] **2.6 *(Optional)* Enable Jetski / Gemini Skills Globally:**
  - Copy `skills/*` into `~/.gemini/config/skills/` if you want Agent 04 skills outside this folder (otherwise launch `jetski`/`gemini` inside the repo root, or just use **Run Direct** in `AIstudio` with zero AI login).

---

## Part 3 — Per-Design PDN Execution Checklist (Steps 0–8 + Stage 4 Build)

Run in order for each substrate `.mcm` design:

- [ ] **3.1 Step 0 — Extract Design Inputs (`.mcm` -> `stage1_inputs/`):**
  - Click **Direct** on Card `0. Extract Data from .mcm` in your target Rail Group tab.
  - Confirm `stage1_inputs/stage1_data_summary.svg` renders in **SVG Preview** and CSVs (`bga_map.csv`, `bump_map.csv`, `edtc_symbols.csv`, `lsc_placed_map.csv`, `stackup_53layers.csv`) exist.
- [ ] **3.2 Step 1 — `SURFACE` (`L01`) Routing:**
  - Choose `FULL` or `M:N` ratio (`4:2`, `5:2`, `3:1`) and strapping (`HORIZONTAL`, `VERTICAL`, `BOTH`).
  - Gate: `0` floating bumps, `>= 18.0 um` opposite-net trace clearance.
- [ ] **3.3 Step 2 — Frontside Build-Up Transition (`SURFACE -> 6F/7F`):**
  - Gate: `<= 7` stacked BU vias (`<= 3` in EMIB HSIO void), `0` pad overlap.
- [ ] **3.4 Step 3 — Core `PTH` (`4FCO <-> 4BCO`) & `eDTC` KOZ:**
  - Select density (`4..11 PTH/mm²`), topology (`STAGGERED` or `ORTHOGONAL_90DEG_*`), and pkg rule (`PKG0.8` / `PKG0.1`).
  - Gate: `300 um` `eDTC` cavity KOZ + `150 um` Guard Metal respected (`0` Core vias inside `eDTC` KOZ).
- [ ] **3.5 Step 4 — Prepreg (`PP`) Patterns & DR Check:**
  - Select `1_VIA_CENTER`, `2_VIA_ON_PTH`, or `4_VIA_PER_PTH`; verify max vias/PTH pad (`1` for `PKG0.1`, `2` for `PKG0.8`) and `>= 67.5 um` Core L/S.
- [ ] **3.6 Step 5 — BGA Via Clusters (`12B <-> BASE`):**
  - Select Option 1–3 or `OPTION4_4VIA_CENTER_ZERO_OVERLAP` (`±45.5 um`, `0.0 um` pad overlap) across all `VDD` + `VSS` BGAs.
- [ ] **3.7 Step 6 — `BASE` (`L27`) `0201` LSC & Curved `LSC_CAVITY` Recess:**
  - Gate: `100%` `CONDUCTOR/BASE` pads (`0` on `SURFACE`), `Pin 1 = VDD` / `Pin 2 = VSS`, `180°` cap-to-cap alternation, `R=508 um` curved cavity clearances (`BGA->Cav >= 254 um`, `LSC->Cav >= 225 um`), `0` LSCs under EMIB shadow.
- [ ] **3.8 Step 7 — Backside Build-Up Climb (`BASE -> 6B/7B`):**
  - Gate: `<= 7` BU stack depth, `0.0 um` pad overlap.
- [ ] **3.9 Step 8 — Full 27-Layer Bridge & Continuity Audit:**
  - Verify `9F->5F` and `9B->5B` unbroken `VSS` and `VDD` trunks, `audit_via_continuity_and_zero_overlap` passes with `0` pad overlaps and `0` dangling vias.
- [ ] **3.10 Stage 4 — Build New Output `.mcm` & Sign Off:**
  - Run Stage 4 import into a **new** `.mcm` (`MCM_template/<design>.mcm` remains untouched).
  - Verify `apd.jrl` / report shows `ERRORS=0` and download deliverables from **Outputs**.

---

## Part 4 — Ongoing Team Updates & Contributing New Skills

- [ ] **4.1 Weekly Sync:** Run `git pull origin main` (and `--bootstrap` on Linux if `requirements.txt` updated).
- [ ] **4.2 Contributing a New Skill:** Start from [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md), keep any `.mcm`/`.csv`/logs outside the repo, and verify with `audit_repo_safety.py` before opening a PR.
