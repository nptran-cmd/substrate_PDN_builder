# Agent 09 (`via_routing`) — Cadence & Environment Dependencies

This document defines the exact Cadence Allegro Package Designer (APD) 25.1 paths, license settings, and headless batch execution conventions for **Agent 09 (`via_routing`)**.

---

## 1. Cadence Allegro Package Designer (APD) 25.1

- **Tool Name:** Cadence Allegro Package Designer (APD)
- **Version:** SPB 25.1
- **Primary Batch Executable:** `C:\Cadence\SPB_25.1\tools\bin\apd.exe`
- **Product License Argument:** `-product Allegro_Adv_Packaging_Plus`
- **CDSROOT Path:** `C:\Cadence\SPB_25.1`
- **Read-Only Reference SKILL Directory (DO NOT MODIFY):** `<cadence_library_dir>`

---

## 2. Cadence APD 25.1 Batch Mode Execution Protocol

### CLI Invocation Pattern
```powershell
& "C:\Cadence\SPB_25.1\tools\bin\apd.exe" -product Allegro_Adv_Packaging_Plus -nographic "<design_path>.mcm" -s "<script_path>.scr"
```

### Cadence Script (`.scr`) Structure
```text
skill load("<agent_workspace>/agent09_via_routing/scripts/vr_core_batch.il")
skill load("<agent_workspace>/agent09_via_routing/scripts/vr_via_routing_batch.il")
skill vrDispatchBatchJob("<agent_workspace>/agent09_via_routing/reports/via_job_config.txt")
exit
```
