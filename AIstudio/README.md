# Substrate AI Design Studio (`AIstudio`)

A focused engineering web workstation for **Substrate Routing & PDN Automation (`MASC` Agents 01–17)** with an integrated live **Windows ConPTY + `xterm.js` terminal** wired for **Jetski CLI** (`jetski-cli.exe`).

## Directory Layout

- [`PLAN.md`](PLAN.md) — Phased architecture & roadmap (Phase 1 implemented; Phases 2–4 planned).
- [`backend/conpty.py`](backend/conpty.py) — Native Win32 `CreatePseudoConsole` PTY wrapper & foreground `jetski-cli.exe` detector.
- [`backend/prompts_catalog.py`](backend/prompts_catalog.py) — Curated Agent 01 / 03 / 04 / 08 / 09 / 10+16 prompt templates & workspace `.mcm` discovery.
- [`backend/server.py`](backend/server.py) — ASGI web + WebSocket server (`Starlette` + `Uvicorn`).
- [`frontend/`](frontend/index.html) — Self-contained HTML/CSS/JS UI + locally bundled `xterm.js` 6.0 & `FitAddon`.
- [`tests/test_studio.py`](tests/test_studio.py) — Backend, ConPTY, REST & WebSocket integration tests.

## Quick Start

From the repository root (`substrate_routing_agent/`):

```powershell
.\AIstudio\start_studio.ps1
```

Or launch directly with Uvicorn:

```powershell
python -m uvicorn AIstudio.backend.server:app --host 127.0.0.1 --port 8765
```

Then open **http://127.0.0.1:8765** in Chrome or Edge.

## Logging In & Using Jetski in the Studio Terminal

1. Inside the right-hand terminal pane, click **Launch Jetski** (or type `jetski` directly — `C:\Program Files\Google\jetski-cli` is pre-loaded on the terminal session `PATH`).
2. Complete Jetski sign-in if prompted (OAuth browser flow, or use the **Jetski (LOAS / Stubby Auth)** quick-login dropdown item if on internal corporate auth).
3. Click any prompt button on the left panel (or edit parameters in the composer and press `Ctrl+Enter`) to execute that prompt directly inside the Jetski terminal.

## Running Tests

```powershell
python -m unittest AIstudio.tests.test_studio -v
```
