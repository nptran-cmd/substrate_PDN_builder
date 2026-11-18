"""
Cadence APD 25.1 Headless Batch Runner for Agent 09 (via_routing).

Follows the exact `apd.exe -product Allegro_Adv_Packaging_Plus -nographic` protocol
established in `test_mcp/cad_cli/cadence_runner.py`, enhanced with:
  1. Pipe-delimited `via_job_config.txt` generation for O(1) SKILL `makeTable` loading.
  2. Zero-copy NTFS hardlink (`os.link`) lock-bypass for read-only via reporting/auditing
     when a target `.mcm` has an active `.lck` file open in Cadence APD GUI.
  3. Process-tree timeout termination (`taskkill /F /T /PID`) and journal (`apd.jrl`) parsing.
"""

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class CadenceRunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool
    journal_path: Optional[Path]
    scr_path: Optional[Path]
    config_path: Optional[Path]
    success: bool
    error_message: Optional[str]


class CadenceBatchRunner:
    """
    Engine for running Cadence Allegro Package Designer (APD 25.1) headlessly in batch mode:
      & "C:\\Cadence\\SPB_25.1\\tools\\bin\\apd.exe" -product Allegro_Adv_Packaging_Plus -nographic "<design>.mcm" -s "<script>.scr"
    """

    def __init__(
        self,
        apd_path: Union[Path, str, None] = None,
        product: str = "Allegro_Adv_Packaging_Plus",
        default_timeout: int = 1800,
    ):
        self.product = product
        self.default_timeout = default_timeout
        self.apd_path = self._resolve_apd_path(apd_path)

    def _resolve_apd_path(self, user_path: Union[Path, str, None]) -> Optional[Path]:
        if user_path:
            return Path(user_path).resolve()

        if "CDS_APD_BIN" in os.environ and os.environ["CDS_APD_BIN"].strip():
            return Path(os.environ["CDS_APD_BIN"])

        if os.name == "nt":
            cdsroot = os.environ.get("CDSROOT", "C:/Cadence/SPB_25.1")
            default_path = Path(cdsroot) / "tools" / "bin" / "apd.exe"
            if default_path.exists():
                return default_path
        else:
            run_apd_sh = Path(
                os.environ.get("CADENCE_RUN_APD_SH", str(Path.home() / "cadence" / "installs" / "run_apd.sh"))
            )
            if run_apd_sh.is_file():
                return run_apd_sh
            for cand_root in (
                os.environ.get("CDSROOT", ""),
                str(Path.home() / "cadence" / "installs" / "SPB261"),
            ):
                if cand_root:
                    cand_apd = Path(cand_root) / "tools" / "bin" / "apd"
                    if cand_apd.exists():
                        return cand_apd

        which_apd = shutil.which("apd")
        if which_apd:
            return Path(which_apd)

        return None

    def check_environment(self) -> Dict[str, Any]:
        """Validates Cadence APD binary, CDSROOT, and license configuration."""
        status: Dict[str, Any] = {
            "binary_found": False,
            "binary_path": None,
            "cdsroot_found": False,
            "cdsroot_path": None,
            "license_configured": False,
            "warnings": [],
            "errors": [],
        }

        if self.apd_path and self.apd_path.exists():
            status["binary_found"] = True
            status["binary_path"] = str(self.apd_path)
        else:
            status["errors"].append("Cadence APD executable not found.")

        default_root = "C:/Cadence/SPB_25.1" if os.name == "nt" else str(Path.home() / "cadence" / "installs" / "SPB261")
        cdsroot = os.environ.get("CDSROOT", default_root)
        if cdsroot and Path(cdsroot).exists():
            status["cdsroot_found"] = True
            status["cdsroot_path"] = cdsroot
        elif self.apd_path and self.apd_path.name == "run_apd.sh":
            status["cdsroot_found"] = True
            status["cdsroot_path"] = str(self.apd_path.parent)
        else:
            status["errors"].append("CDSROOT directory missing or invalid.")

        lic_file = os.environ.get("CDS_LIC_FILE") or os.environ.get("LM_LICENSE_FILE")
        if lic_file:
            status["license_configured"] = True
        else:
            status["warnings"].append("No CDS_LIC_FILE or LM_LICENSE_FILE environment variable set.")

        return status

    @staticmethod
    def to_skill_path(p: Union[Path, str]) -> str:
        """Converts a filesystem path to forward-slash SKILL format."""
        return str(Path(p).resolve()).replace("\\", "/")

    def create_job_config_file(
        self,
        params: Dict[str, Any],
        output_cfg_path: Union[Path, str, None] = None,
    ) -> Path:
        """
        Writes a pipe-delimited `KEY|VALUE` config file for `vrLoadConfig` in `vr_core_batch.il`.
        """
        if output_cfg_path is None:
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="via_job_config_")
            os.close(fd)
            output_cfg_path = Path(path)
        else:
            output_cfg_path = Path(output_cfg_path).resolve()
            output_cfg_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# Agent 09 (via_routing) Headless Batch Job Configuration"]
        for key, value in params.items():
            k_norm = str(key).strip().upper()
            if isinstance(value, bool):
                v_norm = "TRUE" if value else "FALSE"
            elif isinstance(value, (list, tuple)):
                v_norm = ",".join(str(item).strip() for item in value)
            elif value is None:
                v_norm = ""
            else:
                v_norm = str(value).strip()
            if k_norm in ("OUT_DIR", "OUT_MCM", "RECIPE_CSV", "MCM_INPUT"):
                v_norm = v_norm.replace("\\", "/")
            lines.append(f"{k_norm}|{v_norm}")

        with open(output_cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return output_cfg_path

    def create_scr_file(
        self,
        skill_loads: List[Union[str, Path]],
        skill_calls: List[str],
        output_scr_path: Union[Path, str, None] = None,
    ) -> Path:
        """
        Generates a Cadence `.scr` replay script matching `test_mcp`:
          skill load("<path>.il")
          skill <FunctionCall>(...)
          exit
        """
        if output_scr_path is None:
            fd, path = tempfile.mkstemp(suffix=".scr", prefix="apd_via_batch_")
            os.close(fd)
            output_scr_path = Path(path)
        else:
            output_scr_path = Path(output_scr_path).resolve()
            output_scr_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        for sl in skill_loads:
            normalized_path = self.to_skill_path(sl)
            lines.append(f'skill load("{normalized_path}")')

        for sc in skill_calls:
            lines.append(f"skill {sc}")

        lines.append("exit")
        lines.append("fillin no")

        with open(output_scr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return output_scr_path

    def _find_journal_file(
        self, working_dir: Path, mcm_dir: Optional[Path] = None, min_mtime: float = 0.0
    ) -> Optional[Path]:
        candidates = ["apd.jrl", "apd.jrl,1", "apd.jrl.1", "allegro.jrl", "allegro.jrl.1"]
        search_dirs = [working_dir]
        if mcm_dir and mcm_dir != working_dir:
            search_dirs.append(mcm_dir)

        best_path: Optional[Path] = None
        best_mtime: float = -1.0
        for d in search_dirs:
            for cand in candidates:
                cand_path = d / cand
                if cand_path.exists():
                    mtime = cand_path.stat().st_mtime
                    if mtime >= min_mtime - 2.0 and mtime > best_mtime:
                        best_mtime = mtime
                        best_path = cand_path
        return best_path

    def _check_license_or_skill_errors(
        self, stdout: str, stderr: str, journal_path: Optional[Path]
    ) -> Optional[str]:
        content = (stdout + "\n" + stderr).lower()
        if journal_path and journal_path.exists():
            try:
                with open(journal_path, "r", encoding="utf-8", errors="ignore") as f:
                    content += "\n" + f.read().lower()
            except Exception:
                pass

        if "could not get a license" in content or "checkout failed" in content or "license server" in content:
            return "Failed to acquire Cadence product license."
        if "command not found" in content or "eval err" in content or "*error*" in content:
            return "SKILL evaluation or execution error detected in journal."

        return None

    @staticmethod
    def _terminate_process(process: Any, platform_name: Optional[str] = None) -> None:
        """Terminate a timed-out APD process cleanly on Windows (`taskkill`) or Linux/POSIX (`kill`)."""
        plat = os.name if platform_name is None else platform_name
        if plat == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
        else:
            process.kill()

    def run(
        self,
        mcm_path: Union[Path, str],
        scr_path: Union[Path, str],
        working_dir: Union[Path, str, None] = None,
        timeout: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
        config_path: Optional[Path] = None,
        bypass_lock_readonly: bool = False,
    ) -> CadenceRunResult:
        """
        Executes Cadence APD 25.1 headlessly using `apd.exe -product Allegro_Adv_Packaging_Plus -nographic`.
        If `bypass_lock_readonly=True` and `<design>.mcm.lck` exists, creates a temporary 0-byte NTFS
        hardlink (`os.link`) so read-only reporting/auditing runs without lock contention.
        """
        if not self.apd_path or not self.apd_path.exists():
            return CadenceRunResult(
                exit_code=-1,
                stdout="",
                stderr="",
                duration_sec=0.0,
                timed_out=False,
                journal_path=None,
                scr_path=Path(scr_path),
                config_path=config_path,
                success=False,
                error_message="Cadence APD executable (apd.exe) not found.",
            )

        mcm_path = Path(mcm_path).resolve()
        if not mcm_path.exists():
            return CadenceRunResult(
                exit_code=-1,
                stdout="",
                stderr="",
                duration_sec=0.0,
                timed_out=False,
                journal_path=None,
                scr_path=Path(scr_path),
                config_path=config_path,
                success=False,
                error_message=f"Design file not found: {mcm_path}",
            )

        scr_path = Path(scr_path).resolve()
        working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        working_dir.mkdir(parents=True, exist_ok=True)
        timeout = timeout if timeout is not None else self.default_timeout

        temp_link_mcm: Optional[Path] = None
        target_mcm_for_cmd = mcm_path
        lck_file = mcm_path.with_name(mcm_path.name + ".lck")

        if bypass_lock_readonly and lck_file.exists():
            temp_link_mcm = working_dir / f"_readonly_hardlink_{int(time.time())}_{mcm_path.name}"
            try:
                os.link(str(mcm_path), str(temp_link_mcm))
                target_mcm_for_cmd = temp_link_mcm
            except OSError:
                temp_link_mcm = None
                target_mcm_for_cmd = mcm_path

        cmd = [
            str(self.apd_path),
            "-product",
            self.product,
            "-nographic",
            str(target_mcm_for_cmd),
            "-s",
            str(scr_path),
        ]

        if extra_args:
            cmd.extend(extra_args)
        if os.name != "nt" and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a", *cmd]

        start_wall = time.time()
        start_time = time.perf_counter()
        timed_out = False
        stdout_data, stderr_data = "", ""
        exit_code = -1

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )

            try:
                stdout_data, stderr_data = process.communicate(timeout=timeout)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_process(process)
                stdout_data, stderr_data = process.communicate()
                exit_code = -1

        except Exception as e:
            return CadenceRunResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_sec=time.perf_counter() - start_time,
                timed_out=False,
                journal_path=None,
                scr_path=scr_path,
                config_path=config_path,
                success=False,
                error_message=f"Failed to launch Cadence APD subprocess: {e}",
            )
        finally:
            if temp_link_mcm and temp_link_mcm.exists():
                try:
                    temp_link_mcm.unlink()
                except OSError:
                    pass
                temp_lck = temp_link_mcm.with_name(temp_link_mcm.name + ".lck")
                if temp_lck.exists():
                    try:
                        temp_lck.unlink()
                    except OSError:
                        pass

        duration = time.perf_counter() - start_time
        journal_path = self._find_journal_file(
            working_dir, mcm_dir=target_mcm_for_cmd.parent, min_mtime=start_wall
        )

        lic_or_skill_err = self._check_license_or_skill_errors(stdout_data, stderr_data, journal_path)
        success = (exit_code == 0) and (not timed_out) and (lic_or_skill_err is None)
        error_msg = None

        if timed_out:
            error_msg = f"Execution timed out after {timeout} seconds."
        elif lic_or_skill_err:
            error_msg = lic_or_skill_err
        elif not success:
            error_msg = f"Cadence APD execution failed with exit code {exit_code}."

        return CadenceRunResult(
            exit_code=exit_code,
            stdout=stdout_data,
            stderr=stderr_data,
            duration_sec=duration,
            timed_out=timed_out,
            journal_path=journal_path,
            scr_path=scr_path,
            config_path=config_path,
            success=success,
            error_message=error_msg,
        )
