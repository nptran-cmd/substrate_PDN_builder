"""Native Windows ConPTY (CreatePseudoConsole) terminal session implementation."""

from __future__ import annotations

import asyncio
import collections
import ctypes
from ctypes import wintypes
import msvcrt
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Dict, List, Optional, Set

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HPCON = ctypes.c_void_p
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

kernel32.CreatePseudoConsole.argtypes = [
    wintypes.DWORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(HPCON),
]
kernel32.CreatePseudoConsole.restype = ctypes.c_long
kernel32.ResizePseudoConsole.argtypes = [HPCON, wintypes.DWORD]
kernel32.ResizePseudoConsole.restype = ctypes.c_long
kernel32.ClosePseudoConsole.argtypes = [HPCON]
kernel32.ClosePseudoConsole.restype = None

kernel32.InitializeProcThreadAttributeList.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t),
]
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t,
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
]
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.DeleteProcThreadAttributeList.restype = None

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL

DEFAULT_JETSKI_EXE = Path(r"C:\Program Files\Google\jetski-cli\jetski-cli.exe")
DEFAULT_GEMINI_DIR = Path(r"C:\Program Files\Google\gemini-cli")


def find_win_jetski_exe() -> Optional[str]:
    if DEFAULT_JETSKI_EXE.exists():
        return str(DEFAULT_JETSKI_EXE)
    return shutil.which("jetski-cli") or shutil.which("jetski")


def find_win_shell() -> str:
    for candidate in ("pwsh.exe", "powershell.exe", "cmd.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    return "cmd.exe"


def _list_descendant_process_names(root_pid: int) -> List[tuple[int, str]]:
    if not root_pid:
        return []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or snap is None:
        return []
    children_map: Dict[int, List[tuple[int, str]]] = {}
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            children_map.setdefault(int(pe.th32ParentProcessID), []).append(
                (int(pe.th32ProcessID), pe.szExeFile.lower())
            )
            ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        kernel32.CloseHandle(snap)

    descendants: List[tuple[int, str]] = []
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


class ConPtySession:
    """Single interactive ConPTY terminal session backed by pwsh.exe + Win32 pipes."""

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
        self._hpc: Optional[HPCON] = None
        self._attr_buf = None
        self._pi: Optional[PROCESS_INFORMATION] = None
        self._in_write: Optional[int] = None
        self._out_read: Optional[int] = None
        self._closed = False
        self._exit_code: Optional[int] = None

        self._history = collections.deque(maxlen=256)
        self._subscribers: Dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._waiter_thread: Optional[threading.Thread] = None
        self.shell_pid: int = 0

    @property
    def alive(self) -> bool:
        return not self._closed and self._exit_code is None

    def start(self) -> None:
        in_read, in_write = os.pipe()
        out_read, out_write = os.pipe()

        h_in_read = msvcrt.get_osfhandle(in_read)
        h_out_write = msvcrt.get_osfhandle(out_write)

        hpc = HPCON()
        coord = ((self.rows & 0xFFFF) << 16) | (self.cols & 0xFFFF)
        hr = kernel32.CreatePseudoConsole(
            coord, wintypes.HANDLE(h_in_read), wintypes.HANDLE(h_out_write), 0, ctypes.byref(hpc),
        )
        if hr != 0:
            os.close(in_read)
            os.close(in_write)
            os.close(out_read)
            os.close(out_write)
            raise OSError(f"CreatePseudoConsole failed with HRESULT 0x{hr & 0xFFFFFFFF:08X}")

        attr_sz = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attr_sz))
        attr_buf = ctypes.create_string_buffer(attr_sz.value)
        if not kernel32.InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(attr_sz)):
            kernel32.ClosePseudoConsole(hpc)
            raise OSError(f"InitializeProcThreadAttributeList failed: {ctypes.get_last_error()}")

        if not kernel32.UpdateProcThreadAttribute(
            ctypes.cast(attr_buf, ctypes.c_void_p),
            0,
            PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
            hpc,
            ctypes.sizeof(HPCON),
            None,
            None,
        ):
            kernel32.DeleteProcThreadAttributeList(attr_buf)
            kernel32.ClosePseudoConsole(hpc)
            raise OSError(f"UpdateProcThreadAttribute failed: {ctypes.get_last_error()}")

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        si.lpAttributeList = ctypes.addressof(attr_buf)
        pi = PROCESS_INFORMATION()

        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTIGRAVITY_")}
        extra_paths: List[str] = []
        jetski_exe = find_win_jetski_exe()
        if jetski_exe:
            extra_paths.append(str(Path(jetski_exe).parent))
        if DEFAULT_GEMINI_DIR.exists():
            extra_paths.append(str(DEFAULT_GEMINI_DIR))
        if extra_paths:
            env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["SUBSTRATE_STUDIO"] = "1"
        env["SUBSTRATE_AGENT_ROOT"] = str(self.agent_root)
        env["SUBSTRATE_WORK_DIR"] = str(self.cwd)
        if self.work_dir_file is not None:
            env["SUBSTRATE_WORK_DIR_FILE"] = str(self.work_dir_file)
        env["PYTHONPATH"] = str(self.agent_root)

        env_block = "\0".join(f"{k}={v}" for k, v in sorted(env.items())) + "\0\0"
        env_buf = ctypes.create_unicode_buffer(env_block)

        shell_exe = find_win_shell()
        if shell_exe.lower().endswith(("pwsh.exe", "powershell.exe")):
            if jetski_exe:
                cmd = (
                    f'"{shell_exe}" -NoLogo -NoExit -Command '
                    f'"Set-Alias -Name jetski -Value \'{jetski_exe}\' -Scope Global"'
                )
            else:
                cmd = f'"{shell_exe}" -NoLogo'
        else:
            cmd = f'"{shell_exe}"'

        ok = kernel32.CreateProcessW(
            None,
            ctypes.create_unicode_buffer(cmd),
            None,
            None,
            False,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            ctypes.byref(env_buf),
            str(self.cwd),
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        os.close(in_read)
        os.close(out_write)

        if not ok:
            err = ctypes.get_last_error()
            os.close(in_write)
            os.close(out_read)
            kernel32.DeleteProcThreadAttributeList(attr_buf)
            kernel32.ClosePseudoConsole(hpc)
            raise OSError(f"CreateProcessW failed: {err}")

        self._hpc = hpc
        self._attr_buf = attr_buf
        self._pi = pi
        self._in_write = in_write
        self._out_read = out_read
        self.shell_pid = int(pi.dwProcessId)

        self._reader_thread = threading.Thread(
            target=self._read_loop, name=f"conpty-read-{self.session_id[:6]}", daemon=True
        )
        self._waiter_thread = threading.Thread(
            target=self._wait_exit_loop, name=f"conpty-wait-{self.session_id[:6]}", daemon=True
        )
        self._reader_thread.start()
        self._waiter_thread.start()

    def _emit_event(self, payload: dict) -> None:
        with self._lock:
            subs = list(self._subscribers.values())
        for loop, queue in subs:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, payload)

    def _read_loop(self) -> None:
        while not self._closed:
            fd = self._out_read
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
        pi = self._pi
        if not pi:
            return
        kernel32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)
        code = wintypes.DWORD(0)
        kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
        self._exit_code = int(code.value)
        self._emit_event({"type": "exit", "code": self._exit_code})

    def subscribe(self, sub_id: str, loop: asyncio.AbstractEventLoop) -> tuple[str, asyncio.Queue]:
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
            if self._closed or self._in_write is None:
                return
            fd = self._in_write
        os.write(fd, data.encode("utf-8", errors="replace"))

    def resize(self, cols: int, rows: int) -> None:
        cols = max(20, min(int(cols), 400))
        rows = max(5, min(int(rows), 200))
        with self._lock:
            if self._closed or self._hpc is None:
                return
            self.cols = cols
            self.rows = rows
            coord = ((rows & 0xFFFF) << 16) | (cols & 0xFFFF)
            kernel32.ResizePseudoConsole(self._hpc, coord)

    def foreground_status(self) -> Dict[str, object]:
        desc = _list_descendant_process_names(self.shell_pid) if self.alive else []
        names = [name for _, name in desc]
        jetski_running = any("jetski" in n for n in names)
        gemini_running = any("gemini" in n for n in names)
        apd_running = any(n in ("apd.exe", "allegro.exe") for n in names)
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
            hpc = self._hpc
            pi = self._pi
            in_write = self._in_write
            out_read = self._out_read
            attr_buf = self._attr_buf
            self._hpc = None
            self._pi = None
            self._in_write = None
            self._out_read = None
            self._attr_buf = None

        if self.shell_pid:
            for pid, _ in reversed(_list_descendant_process_names(self.shell_pid)):
                h = kernel32.OpenProcess(1, False, pid)
                if h:
                    kernel32.TerminateProcess(h, 0)
                    kernel32.CloseHandle(h)

        if pi:
            kernel32.TerminateProcess(pi.hProcess, 0)
        if hpc is not None:
            kernel32.ClosePseudoConsole(hpc)
        if in_write is not None:
            try:
                os.close(in_write)
            except OSError:
                pass
        if out_read is not None:
            try:
                os.close(out_read)
            except OSError:
                pass
        if pi:
            kernel32.CloseHandle(pi.hThread)
            kernel32.CloseHandle(pi.hProcess)
        if attr_buf is not None:
            kernel32.DeleteProcThreadAttributeList(attr_buf)
