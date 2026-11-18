"""Cross-platform terminal session manager (Windows ConPTY + Linux POSIX PTY) for Substrate AI Studio."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import tempfile
import threading
import time
from typing import Dict, List, Optional
import uuid

if os.name == "nt":
    from .win_conpty import ConPtySession, find_win_jetski_exe, find_win_shell
else:
    from .posix_pty import PosixPtySession as ConPtySession, find_posix_shell


def find_jetski_exe() -> Optional[str]:
    """Return full path to jetski-cli / jetski if installed on Windows or Linux."""
    if os.name == "nt":
        return find_win_jetski_exe()
    for cand in (
        shutil.which("jetski-cli"),
        shutil.which("jetski"),
        str(Path.home() / ".local" / "bin" / "jetski-cli"),
        str(Path.home() / ".local" / "bin" / "jetski"),
    ):
        if cand and Path(cand).is_file():
            return cand
    return None


def find_shell_executable() -> str:
    """Resolve active interactive shell for current OS."""
    if os.name == "nt":
        return find_win_shell()
    return find_posix_shell()


def ps_single_quote(text: str) -> str:
    """Safely wrap text in PowerShell single quotes with embedded quotes doubled."""
    return "'" + text.replace("'", "''") + "'"


def shell_quote_arg(text: str, platform_name: Optional[str] = None) -> str:
    """Quote a command argument cleanly for Windows PowerShell (`nt`) or POSIX bash."""
    plat = os.name if platform_name is None else platform_name
    if plat == "nt":
        return ps_single_quote(text)
    return shlex.quote(text)


class ConPtyManager:
    """Registry managing multiple concurrent terminal sessions across Windows and Linux."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.agent_root = self.workspace_root
        env_wd = os.environ.get("SUBSTRATE_WORK_DIR", "").strip()
        init_wd = Path(env_wd).expanduser().resolve() if env_wd and Path(env_wd).expanduser().is_dir() else self.agent_root
        self.working_dir = init_wd
        self._lock = threading.Lock()
        self._sessions: Dict[str, ConPtySession] = {}
        self._counter = 0
        self.work_dir_file = Path(tempfile.gettempdir()) / f"aistudio_workdir_{os.getpid()}_{uuid.uuid4().hex[:8]}.txt"
        self.custom_work_since_ns: int = time.time_ns() if self.working_dir != self.agent_root else 0
        self.agent_svg_baseline: Dict[str, int] = {}

    def _sync_work_dir_file(self, target: Path) -> None:
        try:
            self.work_dir_file.write_text(str(target), encoding="utf-8")
        except OSError:
            pass

    def set_working_dir(
        self,
        new_dir: Path,
        sync_shells: bool = True,
        svg_baseline: Optional[Dict[str, int]] = None,
    ) -> Path:
        """Switch active design/output working folder while keeping agent_root fixed."""
        resolved = new_dir.resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"Working directory does not exist: {resolved}")
        with self._lock:
            self.working_dir = resolved
            if resolved != self.agent_root:
                self.custom_work_since_ns = time.time_ns()
                if svg_baseline is not None:
                    self.agent_svg_baseline = dict(svg_baseline)
            else:
                self.custom_work_since_ns = 0
                self.agent_svg_baseline = {}
            sessions = list(self._sessions.values())
        self._sync_work_dir_file(resolved)
        if sync_shells:
            for sess in sessions:
                if sess.alive:
                    st = sess.foreground_status()
                    if not st["jetski_active"]:
                        quoted = shell_quote_arg(str(resolved))
                        if os.name == "nt":
                            sess.write(f"$env:SUBSTRATE_WORK_DIR={quoted}; Set-Location {quoted}\r")
                        else:
                            sess.write(f"export SUBSTRATE_WORK_DIR={quoted}; cd {quoted}\r")
        return resolved

    def create_session(
        self, title: Optional[str] = None, cols: int = 120, rows: int = 34
    ) -> ConPtySession:
        with self._lock:
            self._counter += 1
            sid = uuid.uuid4().hex[:12]
            label = title or f"Terminal {self._counter}"
            work_dir = self.working_dir
            agent_root = self.agent_root
            wd_file = self.work_dir_file
        self._sync_work_dir_file(work_dir)
        session = ConPtySession(
            sid,
            label,
            work_dir,
            cols=cols,
            rows=rows,
            agent_root=agent_root,
            work_dir_file=wd_file,
        )
        session.start()
        with self._lock:
            self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConPtySession]:
        with self._lock:
            return self._sessions.get(session_id)

    def get_or_create_default(self, cols: int = 120, rows: int = 34) -> ConPtySession:
        with self._lock:
            alive = [s for s in self._sessions.values() if s.alive]
            if alive:
                return alive[0]
        return self.create_session(title="Jetski Terminal 1", cols=cols, rows=rows)

    def list_sessions(self) -> List[Dict[str, object]]:
        with self._lock:
            items = list(self._sessions.values())
        return [s.foreground_status() for s in items]

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            sess = self._sessions.pop(session_id, None)
        if not sess:
            return False
        sess.close()
        return True

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.values())
            self._sessions.clear()
        for sess in items:
            sess.close()
        try:
            if self.work_dir_file.exists():
                self.work_dir_file.unlink()
        except OSError:
            pass

    def build_dispatch_payload(
        self,
        session: ConPtySession,
        prompt: str,
        mode: str = "auto",
        model: str = "",
        cli_command: Optional[str] = None,
        work_context: str = "",
    ) -> Dict[str, object]:
        """Compute exact text/command to write into terminal stdin for button prompt execution."""
        clean_prompt = " ".join(line.strip() for line in prompt.strip().splitlines() if line.strip())
        if work_context and mode != "shell":
            clean_prompt = f"{work_context} {clean_prompt}"
        status = session.foreground_status()
        jetski_active = bool(status["jetski_active"])

        if mode == "shell":
            cmd = cli_command.strip() if cli_command else clean_prompt
            return {"effective_mode": "shell", "write_text": cmd + "\r", "needs_enter_delay": False}

        if mode == "inject" or (mode == "auto" and jetski_active):
            return {
                "effective_mode": "inject_jetski",
                "write_text": clean_prompt,
                "needs_enter_delay": True,
            }

        extra_dir_flags: List[str] = []
        if self.working_dir != self.agent_root:
            extra_dir_flags = ["--add-dir", shell_quote_arg(str(self.agent_root))]

        if mode == "jetski_print":
            parts = ["jetski", *extra_dir_flags, "-p", shell_quote_arg(clean_prompt)]
            if model and model != "auto":
                parts.extend(["--model", shell_quote_arg(model)])
            return {
                "effective_mode": "jetski_print",
                "write_text": " ".join(parts) + "\r",
                "needs_enter_delay": False,
            }

        parts = ["jetski", *extra_dir_flags, "-i", shell_quote_arg(clean_prompt)]
        if model and model != "auto":
            parts.extend(["--model", shell_quote_arg(model)])
        return {
            "effective_mode": "jetski_interactive",
            "write_text": " ".join(parts) + "\r",
            "needs_enter_delay": False,
        }
