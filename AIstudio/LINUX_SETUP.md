# AIstudio — Linux Direct Execution Guide

Run **AIstudio Web UI + Agent 04 Python + Cadence APD (`run_apd.sh` / `apd`)** directly on your licensed Linux workstation:

## 1. Quick Start on Linux
```bash
git clone https://github.com/nptran-cmd/substrate_PDN_builder.git
cd substrate_PDN_builder
chmod +x AIstudio/start_linux_studio.sh
./AIstudio/start_linux_studio.sh --bootstrap
```

- Set `CADENCE_RUN_APD_SH` (defaults to `$HOME/cadence/installs/run_apd.sh`) if your Cadence wrapper lives elsewhere, or ensure `apd` is on `$PATH` / `$CDSROOT/tools/bin/apd`.
- Headless execution automatically prepends `xvfb-run -a` when `DISPLAY` is unset.

## 2. Accessing From a Laptop Browser
- Open `http://127.0.0.1:8765` directly in Linux Chrome, **or**
- Open an SSH tunnel from Windows/macOS:
  ```powershell
  .\AIstudio\open_linux_tunnel.ps1 -LinuxHost <your-linux-host> -OpenBrowser
  ```
  Then browse to `http://127.0.0.1:8766`.
