"""POSIX (Linux / macOS) pseudo-terminal (`pty`) session manager matching Win32 ConPtySession."""

from __future__ import annotations

import asyncio
import collections
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

if os.name != "nt":
    import fcntl
    import pty
    import termios


def find_posix_shell() -> str:
    """Resolve interactive POSIX login shell."""
    for cand in (os.environ.get("SHELL", ""), shutil.which("bash") or "", shutil.which("sh") or ""):
        if cand and Path(cand).exists():
            return cand
    return "/bin/sh"


def _list_posix_descendants(root_pid: int) -> List[Tuple[int, str]]:
    """Inspect Linux /proc tree under root_pid cleanly without external tools."""
    if not root_pid or not Path("/proc").is_dir():
        return []
    children_map: Dict[int, List[Tuple[int, str]]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat_txt = (entry / "stat").read_text(encoding="utf-8", errors="ignore")
            rparen = stat_txt.rfind(")")
            if rparen == -1:
                continue
            comm = stat_txt[stat_txt.find("(") + 1 : rparen].lower()
            rest = stat_txt[rparen + 2 :].split()
            ppid = int(rest[1]) if len(rest) > 1 else 0
            pid = int(entry.name)
            children_map.setdefault(ppid, []).append((pid, comm))
        except Exception:
            continue

    descendants: List[Tuple[int, str]] = []
    queue = list(children_map.get(root_pid, []))
    seen: Set[int] = {root_pid}
    while queue:
        pid, name = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        descendants.append((pid, name))
        queue.extend(children_map.get(pid, []))
    return descendants


class PosixPtySession:
    """Single interactive Linux POSIX PTY session backed by bash + pty.openpty()."""

    def __init__(
        self,
        session_id: str,
        title: str,
        cwd: Path,
        cols: int = 120,
        rows: int = 34,
        agent_root: Optional[Path] = None,
        work_dir_file: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.title = title
        self.cwd = cwd.resolve()
        self.agent_root = (agent_root or cwd).resolve()
        self.work_dir_file = work_dir_file
        self.cols = max(20, min(cols, 400))
        self.rows = max(5, min(rows, 200))
        self.created_at = time.time()

        self._lock = threading.Lock()
        self._master_fd: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None
        self._closed = False
        self._exit_code: Optional[int] = None
        self.shell_pid: int = 0

        self._history = collections.deque(maxlen=256)
        self._subscribers: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._waiter_thread: Optional[threading.Thread] = None

    @property
    def alive(self) -> bool:
        return not self._closed and self._exit_code is None

    def start(self) -> None:
        """Open PTY pair and launch interactive shell in working directory."""
        if os.name == "nt":
            raise RuntimeError("PosixPtySession is only supported on POSIX systems.")
        master_fd, slave_fd = pty.openpty()
        self._set_winsize(master_fd, self.rows, self.cols)

        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTIGRAVITY_")}
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["SUBSTRATE_WORK_DIR"] = str(self.cwd)
        if self.work_dir_file is not None:
            env["SUBSTRATE_WORK_DIR_FILE"] = str(self.work_dir_file)
        cur_py = env.get("PYTHONPATH", "")
        if str(self.agent_root) not in cur_py.split(os.pathsep):
            env["PYTHONPATH"] = f"{self.agent_root}{os.pathsep}{cur_py}".strip(os.pathsep)

        shell_exe = find_posix_shell()
        try:
            proc = subprocess.Popen(
                [shell_exe],
                cwd=str(self.cwd),
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)

        self._master_fd = master_fd
        self._proc = proc
        self.shell_pid = int(proc.pid)

        self._reader_thread = threading.Thread(
            target=self._read_loop, name=f"pty-read-{self.session_id[:6]}", daemon=True
        )
        self._waiter_thread = threading.Thread(
            target=self._wait_exit_loop, name=f"pty-wait-{self.session_id[:6]}", daemon=True
        )
        self._reader_thread.start()
        self._waiter_thread.start()

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _emit_event(self, payload: dict) -> None:
        with self._lock:
            subs = list(self._subscribers.values())
        for loop, queue in subs:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, payload)

    def _read_loop(self) -> None:
        while not self._closed:
            fd = self._master_fd
            if fd is None:
                break
            try:
                data = os.read(fd, 8192)
            except OSError:
                break
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            with self._lock:
                self._history.append(text)
            self._emit_event({"type": "output", "data": text})

    def _wait_exit_loop(self) -> None:
        proc = self._proc
        if not proc:
            return
        code = proc.wait()
        self._exit_code = int(code)
        self._emit_event({"type": "exit", "code": self._exit_code})

    def subscribe(self, sub_id: str, loop: asyncio.AbstractEventLoop) -> Tuple[str, asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            replay = "".join(self._history)
            self._subscribers[sub_id] = (loop, queue)
        return replay, queue

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def write(self, data: str) -> None:
        with self._lock:
            if self._closed or self._master_fd is None:
                return
            fd = self._master_fd
        os.write(fd, data.encode("utf-8", errors="replace"))

    def resize(self, cols: int, rows: int) -> None:
        cols = max(20, min(int(cols), 400))
        rows = max(5, min(int(rows), 200))
        with self._lock:
            if self._closed or self._master_fd is None:
                return
            self.cols = cols
            self.rows = rows
            self._set_winsize(self._master_fd, rows, cols)

    def foreground_status(self) -> Dict[str, object]:
        desc = _list_posix_descendants(self.shell_pid) if self.alive else []
        names = [name for _, name in desc]
        jetski_running = any("jetski" in n for n in names)
        gemini_running = any("gemini" in n for n in names)
        apd_running = any(n in ("apd", "apd.exe", "allegro") for n in names)
        if jetski_running:
            active_tool = "jetski"
        elif apd_running:
            active_tool = "apd"
        elif gemini_running:
            active_tool = "gemini"
        elif any("python" in n for n in names):
            active_tool = "python"
        else:
            active_tool = "shell"
        return {
            "session_id": self.session_id,
            "title": self.title,
            "alive": self.alive,
            "exit_code": self._exit_code,
            "shell_pid": self.shell_pid,
            "jetski_active": jetski_running,
            "active_tool": active_tool,
            "child_processes": names,
            "cols": self.cols,
            "rows": self.rows,
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            fd = self._master_fd
            proc = self._proc
            self._master_fd = None
            self._proc = None

        if self.shell_pid:
            try:
                os.killpg(os.getpgid(self.shell_pid), signal.SIGTERM)
            except OSError:
                pass
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
