# Substrate AI Design Studio — Architecture & Implementation Plan (`AIstudio/`)

## Vision
Build **Substrate AI Design Studio**, a technical web-based CAD + AI engineering workstation inside `AIstudio/` that brings the **Multi-Agent Substrate Co-Design (MASC)** workflow (`Agent 01`–`Agent 17`) into a single focused browser interface — centered around an **authentic interactive Jetski terminal** identical to VS Code's integrated terminal, paired with **1-click structured prompt buttons** tuned for Cadence Allegro / APD 25.1 `.mcm` workflows.

---

## Architecture Overview

```
Browser (Vanilla HTML5 + CSS + ES6 + xterm.js 6.0 / FitAddon)
  │
  ├── Left Rail: Curated Agent Prompt Deck + Parameterized Composer
  │     • Agent 08 (SerDes TX/RX, HBM DA, GPIO)
  │     • Agent 04 (27-Layer PDN, LSC, PTH)
  │     • Agent 01 & 03 (BGA Symbols, 0201/0402 Decap)
  │     • Agent 09 (Via Processing & DRC Clean)
  │     • Agent 10 & 16 (Pre-CAD Audit, Design Rules RAG)
  │
  └── Right Canvas: Live Interactive Jetski Terminal (Multi-Session Tabs)
        ▲
        │ Full-duplex WebSocket (/ws/terminal/{session_id}) + REST (/api/*)
        ▼
Python ASGI Server (Uvicorn + Starlette + Native Win32 ConPTY)
  │
  ├── Windows CreatePseudoConsole (ConPTY) -> pwsh.exe (with `jetski` & `gemini` ready on PATH)
  ├── Live Process Tree Probe -> Detects `PS Shell` vs active `jetski-cli.exe` REPL
  └── Prompt Dispatcher -> Injects into active Jetski session OR runs `jetski -i "<prompt>"`
```

---

## Phased Delivery Roadmap

### Phase 1 — Core Studio & Interactive Jetski Terminal *(Implemented Now)*
1. **Native Windows ConPTY Terminal Engine (`AIstudio/backend/conpty.py`):**
   - Zero C++ build dependencies: spawns `pwsh.exe` attached to a real Windows `CreatePseudoConsole` (`HPCON`) supporting full VT100/xterm-256color escape sequences, terminal resize (`ResizePseudoConsole`), `Ctrl+C` signals, clean child environment (strips nested `ANTIGRAVITY_*` metadata so `jetski-cli.exe` behaves identically to a standalone VS Code terminal), and live Win32 child process detection (`is_jetski_active`).
2. **Jetski Authentication & Launch Workflow:**
   - Exposes `jetski` (`C:\Program Files\Google\jetski-cli\jetski-cli.exe`) directly inside every shell session.
   - Dedicated toolbar button (**"Login / Launch Jetski"**) supports standard OAuth browser login, internal `--use_stubby_auth`, or `--standalone` mode right inside the browser terminal.
3. **1-Click Prompt Buttons -> Jetski Terminal Execution:**
   - Structured catalog across substrate agents (`AIstudio/backend/prompts_catalog.py`) with active `.mcm` design file injection (`@<design.mcm>` placeholder substitution).
   - Smart delivery modes:
     - **Auto:** Injects prompt + Enter directly if `jetski-cli.exe` is already running inside the active terminal tab; otherwise launches `jetski --prompt-interactive "<prompt>"` (with chosen `--model`) in the shell.
     - **Inject Active TUI:** Sends prompt directly to stdin (supports interactive REPLs / logins / confirmations).
     - **Launch Interactive (`-i`):** Starts a fresh Jetski interactive turn with the prompt.
     - **One-Shot (`-p`) / Shell:** Non-interactive print turn or direct Python/PowerShell CLI execution.
4. **Minimalist Engineering UX/UI (`AIstudio/frontend/`):**
   - Warm obsidian charcoal surfaces + copper-etch accents tailored for substrate hardware engineers; distraction-free 2-pane split with multi-session terminal tabs and an editable quick-prompt composer.

### Phase 2 — Inline SVG Sandbox & Stackup Visualizer *(Planned)*
- Embed live pan/zoom viewer inside a toggleable right drawer for generated `.svg` verification gates (e.g., `TX0_12Pairs_BGA_Structure_and_Keepouts.svg`, PDN 27-layer cross-sections) triggered whenever an agent completes a sandbox run.
- Add `.mcm` metadata quick-inspector (via read-only `apd.exe` query) showing die count, nets, conductor layers, and baseline DRCs.

### Phase 3 — Headless `apd.exe` Telemetry & DRC Diff Viewer *(Planned)*
- Monitor `reports/**/tx0_bga_apd_import_report.txt` and `batch_drc.log` in real time to stream structured pass/fail pills (`ERRORS=0`, `TOUCHED_NET_DRCS=0`) alongside terminal output.
- Side-by-side comparison table between baseline `.mcm` and generated output `.mcm`.

### Phase 4 — Shared Team Workspace, Auth & Saved Runbooks *(Planned)*
- Role-safe per-user authentication gateway and workspace lock coordination (`master.tag` awareness) for multi-engineer team hosting on shared Windows build servers.
- Save/export custom team prompt sequences as reusable JSON runbooks.
