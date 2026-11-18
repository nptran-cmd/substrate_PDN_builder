"""Starlette + Uvicorn ASGI backend for Substrate AI Design Studio."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import string
import subprocess
import sys
from typing import Any, Dict, List, Optional
import uuid

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

from .conpty import ConPtyManager, find_jetski_exe, shell_quote_arg
from .direct_runner import (
    handle_studio_mcp,
    list_downloadable_files,
    resolve_prompt_argv,
    run_direct_argv,
    safe_resolve_workspace_file,
    stream_upload_to_mcm_template,
)
from .prompts_catalog import (
    PROMPT_BUTTONS,
    PROMPT_CATEGORIES,
    discover_mcm_designs,
    discover_pdn_svgs,
    find_mcm_template_dir,
    relocate_agent_svgs_to_working_dir,
    snapshot_agent_svgs,
)

STUDIO_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = STUDIO_DIR / "frontend"
WORKSPACE_ROOT = STUDIO_DIR.parent


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Ensure browser refreshes always pick up Studio UI edits and enforce optional access token."""

    async def dispatch(self, request, call_next):
        expected = os.environ.get("AISTUDIO_ACCESS_TOKEN", "").strip()
        path = request.url.path
        if expected and path not in ("/api/health",):
            q_tok = request.query_params.get("token", "").strip()
            hdr_tok = request.headers.get("X-AIStudio-Token", "").strip()
            auth_hdr = request.headers.get("Authorization", "")
            bearer_tok = auth_hdr[7:].strip() if auth_hdr.startswith("Bearer ") else ""
            cookie_tok = (request.cookies.get("aistudio_token") or "").strip()

            supplied = hdr_tok or bearer_tok or q_tok or cookie_tok
            if not supplied or not hmac.compare_digest(expected, supplied):
                if path.startswith("/api/") or path == "/mcp":
                    return JSONResponse({"ok": False, "error": "Unauthorized: set ?token=... or X-AIStudio-Token"}, status_code=401)
                return HTMLResponse(
                    "<html><body style='background:#0b1120;color:#e2e8f0;font-family:sans-serif;padding:40px;'>"
                    "<h2>Substrate AI Design Studio — Access Token Required</h2>"
                    "<p>Open with <code>?token=YOUR_TOKEN</code> or ask the host owner for the invite URL.</p>"
                    "</body></html>",
                    status_code=401,
                )
            if q_tok and path == "/":
                resp = RedirectResponse(url="/", status_code=302)
                resp.set_cookie("aistudio_token", q_tok, httponly=True, samesite="lax")
                return resp

        response = await call_next(request)
        if not path.startswith("/vendor/"):
            response.headers["Cache-Control"] = "no-store"
        return response

JETSKI_MODELS = [
    {"id": "auto", "label": "Auto (Jetski Default)"},
    {"id": "gemini-flash-next", "label": "Gemini Flash Next"},
    {"id": "gemini-4-carbon-high", "label": "Gemini 4 Carbon (High)"},
    {"id": "gemini-pro-coordinator", "label": "Gemini Pro Orchestrator"},
    {"id": "gemini-3.8-flash-high", "label": "Gemini 3.8 Flash (High)"},
    {"id": "opus-5.5-high", "label": "Claude Opus 5.5 (High)"},
]

pty_manager = ConPtyManager(WORKSPACE_ROOT)


def _is_allowed_origin(origin: Optional[str], host_header: Optional[str] = None) -> bool:
    """Block cross-origin WebSocket hijacking while supporting optional corp remote host."""
    if not origin:
        return True
    lower = origin.lower().rstrip("/")
    if (
        lower.startswith("http://127.0.0.1:")
        or lower.startswith("http://localhost:")
        or lower in ("http://127.0.0.1", "http://localhost")
    ):
        return True
    if host_header:
        h_low = host_header.lower()
        if lower in (f"http://{h_low}", f"https://{h_low}"):
            return True
    if os.environ.get("AISTUDIO_ALLOW_REMOTE", "").strip() == "1":
        host_part = lower.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        raw_suffixes = os.environ.get("AISTUDIO_ALLOWED_DOMAIN_SUFFIXES", "")
        for sfx in [s.strip().lower() for s in raw_suffixes.split(",") if s.strip()]:
            if host_part.endswith(sfx):
                return True
    return False


@asynccontextmanager
async def lifespan(app: Starlette):
    yield
    pty_manager.close_all()


async def index_page(request) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


def _workspace_payload() -> Dict[str, Any]:
    work_dir = pty_manager.working_dir
    agent_root = pty_manager.agent_root
    is_custom = work_dir != agent_root
    designs = discover_mcm_designs(agent_root, work_dir)
    tpl_dir = find_mcm_template_dir(work_dir)
    wd_templates = [d for d in designs if d.get("source") == "working_dir"] if is_custom else designs
    origin_templates = [d for d in designs if d.get("is_mcm_template")]
    return {
        "agent_root": str(agent_root),
        "working_dir": str(work_dir),
        "is_custom_dir": is_custom,
        "mcm_template_dir": str(tpl_dir) if tpl_dir else None,
        "has_master_tag": bool(
            (work_dir / "master.tag").is_file() or (tpl_dir and (tpl_dir / "master.tag").is_file())
        ),
        "origin_templates": origin_templates,
        "working_templates": wd_templates,
        "designs": designs,
    }


async def health(request) -> JSONResponse:
    jetski_exe = find_jetski_exe()
    return JSONResponse(
        {
            "ok": True,
            "os_name": os.name,
            "direct_run_ready": True,
            "workspace": str(WORKSPACE_ROOT),
            "working_dir": str(pty_manager.working_dir),
            "agent_root": str(pty_manager.agent_root),
            "jetski_found": bool(jetski_exe),
            "jetski_exe": jetski_exe,
            "sessions_active": sum(1 for s in pty_manager.list_sessions() if s["alive"]),
        }
    )


def _sync_and_discover_svgs() -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    relocated: List[Dict[str, str]] = []
    wd = pty_manager.working_dir
    ar = pty_manager.agent_root
    if wd.resolve() != ar.resolve() and pty_manager.custom_work_since_ns > 0:
        relocated = relocate_agent_svgs_to_working_dir(
            ar,
            wd,
            pty_manager.agent_svg_baseline,
            pty_manager.custom_work_since_ns,
        )
    svgs = discover_pdn_svgs(WORKSPACE_ROOT, wd)
    return svgs, relocated


async def catalog(request) -> JSONResponse:
    ws = _workspace_payload()
    svgs, _ = _sync_and_discover_svgs()
    return JSONResponse(
        {
            "categories": PROMPT_CATEGORIES,
            "prompts": PROMPT_BUTTONS,
            "workspace": ws,
            "designs": ws["designs"],
            "svgs": svgs,
            "models": JETSKI_MODELS,
            "jetski_found": bool(find_jetski_exe()),
        }
    )


async def get_workspace(request) -> JSONResponse:
    return JSONResponse({"ok": True, "workspace": _workspace_payload()})


async def select_workspace(request) -> JSONResponse:
    body = await request.json()
    raw_path = str(body.get("path", "")).strip()
    if not raw_path:
        return JSONResponse({"ok": False, "error": "Missing folder path"}, status_code=400)
    target = Path(raw_path).expanduser()
    if not target.is_dir():
        return JSONResponse({"ok": False, "error": f"Folder does not exist: {raw_path}"}, status_code=400)
    baseline = snapshot_agent_svgs(pty_manager.agent_root) if target.resolve() != pty_manager.agent_root.resolve() else {}
    pty_manager.set_working_dir(target, sync_shells=True, svg_baseline=baseline)
    svgs, _ = _sync_and_discover_svgs()
    return JSONResponse(
        {
            "ok": True,
            "workspace": _workspace_payload(),
            "svgs": svgs,
        }
    )


def _open_native_folder_dialog(initial_dir: str) -> str:
    """Run Windows native folder picker in a dedicated process on its own GUI main thread."""
    code = (
        "import tkinter as tk; from tkinter import filedialog; "
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
        f"p = filedialog.askdirectory(initialdir={initial_dir!r}, "
        "title='Select Working Folder (MCM Template & Output Path)'); "
        "r.destroy(); print(p or '', end='')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.stdout.strip()


async def browse_workspace(request) -> JSONResponse:
    initial = str(pty_manager.working_dir)
    try:
        chosen = await asyncio.to_thread(_open_native_folder_dialog, initial)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"Folder dialog failed: {exc}"}, status_code=500)
    if not chosen:
        return JSONResponse({"ok": True, "cancelled": True, "workspace": _workspace_payload()})
    target = Path(chosen)
    if not target.is_dir():
        return JSONResponse({"ok": False, "error": f"Selected path is not a folder: {chosen}"}, status_code=400)
    baseline = snapshot_agent_svgs(pty_manager.agent_root) if target.resolve() != pty_manager.agent_root.resolve() else {}
    pty_manager.set_working_dir(target, sync_shells=True, svg_baseline=baseline)
    svgs, _ = _sync_and_discover_svgs()
    return JSONResponse(
        {
            "ok": True,
            "cancelled": False,
            "workspace": _workspace_payload(),
            "svgs": svgs,
        }
    )


async def list_workspace_dirs(request) -> JSONResponse:
    """Safe in-browser directory navigator endpoint (fallback for headless/remote sessions)."""
    raw = request.query_params.get("path", "").strip()
    if not raw:
        cur = pty_manager.working_dir
    else:
        cur = Path(raw).expanduser().resolve()
    if not cur.is_dir():
        return JSONResponse({"ok": False, "error": "Directory not found"}, status_code=404)
    dirs: List[Dict[str, str]] = []
    mcms: List[str] = []
    tpl_dir = find_mcm_template_dir(cur)
    if tpl_dir:
        try:
            for tp in sorted(tpl_dir.glob("*.mcm"), key=lambda p: p.name.lower()):
                mcms.append(f"{tpl_dir.name}/{tp.name}")
        except PermissionError:
            pass
    try:
        for entry in sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.suffix.lower() == ".mcm":
                mcms.append(entry.name)
    except PermissionError:
        pass
    if os.name == "nt":
        drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        cands = [str(Path.home()), "/tmp", "/"]
        drives = []
        for c in cands:
            if c not in drives and Path(c).is_dir():
                drives.append(c)
    parent = str(cur.parent) if cur.parent != cur else None
    return JSONResponse(
        {
            "ok": True,
            "path": str(cur),
            "parent": parent,
            "drives": drives,
            "dirs": dirs[:200],
            "mcm_files": mcms[:50],
            "has_mcm_template_dir": bool(tpl_dir),
            "has_master_tag": bool(
                (cur / "master.tag").is_file() or (tpl_dir and (tpl_dir / "master.tag").is_file())
            ),
        }
    )


async def list_svgs(request) -> JSONResponse:
    svgs, relocated = _sync_and_discover_svgs()
    return JSONResponse({"svgs": svgs, "relocated": relocated})


def _resolve_allowed_svg_path(rel_path: str) -> Optional[Path]:
    """Strictly serve SVGs ONLY inside an active custom working_dir (excluding MCM_template and agent repo)."""
    if not rel_path:
        return None
    wd = pty_manager.working_dir.resolve()
    if wd == pty_manager.agent_root.resolve():
        return None
    try:
        sub = rel_path[len("work://"):] if rel_path.startswith("work://") else rel_path
        candidate = (wd / sub).resolve()
    except Exception:
        return None
    if candidate.suffix.lower() != ".svg" or not candidate.is_file():
        return None
    if not candidate.is_relative_to(wd):
        return None
    rel_parts_lower = [part.lower() for part in candidate.relative_to(wd).parts]
    if "mcm_template" in rel_parts_lower:
        return None
    return candidate


async def serve_svg_file(request) -> FileResponse | JSONResponse:
    rel = request.query_params.get("path", "")
    resolved = _resolve_allowed_svg_path(rel)
    if not resolved:
        return JSONResponse({"ok": False, "error": "SVG not found or outside allowed workspace"}, status_code=404)
    return FileResponse(resolved, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


async def list_sessions(request) -> JSONResponse:
    sessions = pty_manager.list_sessions()
    return JSONResponse({"sessions": sessions})


async def create_session(request) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        raw = await request.body()
        if raw:
            body = json.loads(raw)
    except Exception:
        body = {}
    cols = int(body.get("cols", 120))
    rows = int(body.get("rows", 34))
    title = body.get("title")
    sess = pty_manager.create_session(title=title, cols=cols, rows=rows)
    return JSONResponse({"session": sess.foreground_status()}, status_code=201)


async def delete_session(request) -> JSONResponse:
    sid = request.path_params["session_id"]
    closed = pty_manager.close_session(sid)
    if not closed:
        return JSONResponse({"ok": False, "error": "Session not found"}, status_code=404)
    return JSONResponse({"ok": True})


async def dispatch_prompt(request) -> JSONResponse:
    sid = request.path_params["session_id"]
    sess = pty_manager.get_session(sid)
    if not sess or not sess.alive:
        return JSONResponse({"ok": False, "error": "Terminal session not active"}, status_code=404)

    body = await request.json()
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "Empty prompt"}, status_code=400)

    mode = str(body.get("mode", "auto"))
    model = str(body.get("model", ""))
    cli_command = body.get("cli_command")

    work_context = ""
    if pty_manager.working_dir != pty_manager.agent_root:
        ws_info = _workspace_payload()
        origins = ws_info.get("origin_templates") or ws_info["working_templates"]
        tpl_names = ", ".join(d["rel_path"] for d in origins[:5]) or "none detected yet"
        tpl_hint = ws_info.get("mcm_template_dir") or str(pty_manager.working_dir / "MCM_template")
        work_context = (
            f"[Studio Workspace Context | Agent Repo: {pty_manager.agent_root} | "
            f"Active Working & Output Folder: {pty_manager.working_dir} | "
            f"MCM Origine Folder: {tpl_hint} | "
            f"Origin MCM Template(s): {tpl_names} | "
            f"CRITICAL OUTPUT RULE: Read .mcm templates from MCM_template (read-only) and run scripts from Agent Repo, "
            f"set SUBSTRATE_WORK_DIR='{pty_manager.working_dir}', and save EVERY generated .svg, .csv, .json, .txt, .mcm, "
            f"and report file ONLY inside '{pty_manager.working_dir}' (e.g. '{pty_manager.working_dir}/pdn_sandbox/' or "
            f"'{pty_manager.working_dir}/reports/'). NEVER write .svg or output files inside Agent Repo (`agent04_pdn_architect/` or `agent*/`).]"
        )

    plan = pty_manager.build_dispatch_payload(
        sess,
        prompt=prompt,
        mode=mode,
        model=model,
        cli_command=str(cli_command) if cli_command else None,
        work_context=work_context,
    )
    sess.write(str(plan["write_text"]))
    if plan["needs_enter_delay"]:
        await asyncio.sleep(0.06)
        sess.write("\r")

    return JSONResponse(
        {
            "ok": True,
            "session_id": sid,
            "effective_mode": plan["effective_mode"],
            "status": sess.foreground_status(),
        }
    )


async def session_action(request) -> JSONResponse:
    sid = request.path_params["session_id"]
    sess = pty_manager.get_session(sid)
    if not sess or not sess.alive:
        return JSONResponse({"ok": False, "error": "Terminal session not active"}, status_code=404)

    body = await request.json()
    action = str(body.get("action", "")).strip()
    model = str(body.get("model", "")).strip()
    status = sess.foreground_status()

    model_flag = f" --model {shell_quote_arg(model)}" if model and model != "auto" else ""
    dir_flag = (
        f" --add-dir {shell_quote_arg(str(pty_manager.agent_root))}"
        if pty_manager.working_dir != pty_manager.agent_root
        else ""
    )

    if action == "launch_jetski":
        if not status["jetski_active"]:
            sess.write(f"jetski{dir_flag}{model_flag}\r")
    elif action == "login_jetski_oauth":
        if status["jetski_active"]:
            sess.write("/login\r")
        else:
            sess.write(f"jetski --standalone{dir_flag}{model_flag}\r")
    elif action == "login_jetski_loas":
        if not status["jetski_active"]:
            sess.write(f"jetski --standalone --use_stubby_auth{dir_flag}{model_flag}\r")
    elif action == "launch_gemini":
        sess.write("gemini\r")
    elif action == "ctrl_c":
        sess.write("\x03")
    elif action == "clear":
        if status["jetski_active"]:
            sess.write("\x0c")
        else:
            sess.write("Clear-Host\r" if os.name == "nt" else "clear\r")
    else:
        return JSONResponse({"ok": False, "error": f"Unknown action: {action}"}, status_code=400)

    await asyncio.sleep(0.05)
    return JSONResponse({"ok": True, "action": action, "status": sess.foreground_status()})


async def upload_mcm_file(request) -> JSONResponse:
    """Stream uploaded .mcm / input file straight to `<working_dir>/MCM_template/`."""
    form = await request.form()
    try:
        up = form.get("file")
        if up is None or not hasattr(up, "read"):
            return JSONResponse({"ok": False, "error": "Missing multipart 'file' field."}, status_code=400)
        info = await stream_upload_to_mcm_template(pty_manager.working_dir, up)
        return JSONResponse({**info, "workspace": _workspace_payload()})
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    finally:
        await form.close()


async def list_downloads_endpoint(request) -> JSONResponse:
    return JSONResponse({"ok": True, "files": list_downloadable_files(pty_manager.working_dir)})


async def download_workspace_file(request) -> FileResponse | JSONResponse:
    rel = request.query_params.get("path", "")
    resolved = safe_resolve_workspace_file(pty_manager.working_dir, rel)
    if not resolved:
        return JSONResponse({"ok": False, "error": "File not found inside working folder."}, status_code=404)
    return FileResponse(resolved, filename=resolved.name)


async def direct_run_endpoint(request) -> JSONResponse:
    """Run an allowlisted catalog prompt directly via Python / Cadence APD without Jetski."""
    body = await request.json()
    prompt_id = str(body.get("prompt_id", "")).strip()
    implement_mcm = bool(body.get("implement_mcm", False))
    mcm_rel_path = str(body.get("mcm_rel_path", "")).strip() or None
    try:
        argv = resolve_prompt_argv(
            prompt_id,
            pty_manager.working_dir,
            pty_manager.agent_root,
            implement_mcm=implement_mcm,
            mcm_rel_path=mcm_rel_path,
        )
        res = await run_direct_argv(
            argv,
            pty_manager.working_dir,
            pty_manager.agent_root,
            pty_manager.work_dir_file,
        )
        svgs, relocated = _sync_and_discover_svgs()
        return JSONResponse({**res, "svgs": svgs, "relocated": relocated}, status_code=200 if res["ok"] else 500)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


async def mcp_endpoint(request) -> JSONResponse:
    try:
        rpc = await request.json()
        return JSONResponse(await handle_studio_mcp(rpc, pty_manager))
    except Exception as exc:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}, status_code=400)


async def terminal_ws(websocket: WebSocket) -> None:
    expected_tok = os.environ.get("AISTUDIO_ACCESS_TOKEN", "").strip()
    if expected_tok:
        ws_tok = (websocket.cookies.get("aistudio_token") or websocket.query_params.get("token") or "").strip()
        if not ws_tok or not hmac.compare_digest(expected_tok, ws_tok):
            await websocket.close(code=1008)
            return

    if not _is_allowed_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008)
        return

    sid = websocket.path_params["session_id"]
    sess = pty_manager.get_or_create_default() if sid == "default" else pty_manager.get_session(sid)
    if not sess:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    sub_id = uuid.uuid4().hex[:10]
    loop = asyncio.get_running_loop()
    replay, queue = sess.subscribe(sub_id, loop)

    try:
        await websocket.send_json({"type": "meta", "status": sess.foreground_status()})
        if replay:
            await websocket.send_json({"type": "output", "data": replay})

        async def pump_output() -> None:
            while True:
                msg = await queue.get()
                await websocket.send_json(msg)

        async def poll_status() -> None:
            last_tool = None
            last_alive = None
            while True:
                await asyncio.sleep(1.0)
                st = sess.foreground_status()
                if st["active_tool"] != last_tool or st["alive"] != last_alive:
                    last_tool = st["active_tool"]
                    last_alive = st["alive"]
                    await websocket.send_json({"type": "meta", "status": st})
                if not st["alive"]:
                    break

        async def pump_input() -> None:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    sess.write(raw)
                    continue
                mtype = msg.get("type")
                if mtype == "input":
                    sess.write(str(msg.get("data", "")))
                elif mtype == "resize":
                    sess.resize(int(msg.get("cols", 120)), int(msg.get("rows", 34)))

        tasks = [
            asyncio.create_task(pump_output()),
            asyncio.create_task(poll_status()),
            asyncio.create_task(pump_input()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        sess.unsubscribe(sub_id)


app = Starlette(
    debug=False,
    lifespan=lifespan,
    routes=[
        Route("/", endpoint=index_page),
        Route("/api/health", endpoint=health, methods=["GET"]),
        Route("/api/catalog", endpoint=catalog, methods=["GET"]),
        Route("/api/workspace", endpoint=get_workspace, methods=["GET"]),
        Route("/api/workspace/select", endpoint=select_workspace, methods=["POST"]),
        Route("/api/workspace/browse", endpoint=browse_workspace, methods=["POST"]),
        Route("/api/workspace/ls", endpoint=list_workspace_dirs, methods=["GET"]),
        Route("/api/workspace/upload-mcm", endpoint=upload_mcm_file, methods=["POST"]),
        Route("/api/workspace/downloads", endpoint=list_downloads_endpoint, methods=["GET"]),
        Route("/api/workspace/download", endpoint=download_workspace_file, methods=["GET"]),
        Route("/api/direct/run", endpoint=direct_run_endpoint, methods=["POST"]),
        Route("/api/svgs", endpoint=list_svgs, methods=["GET"]),
        Route("/api/svg-file", endpoint=serve_svg_file, methods=["GET"]),
        Route("/api/sessions", endpoint=list_sessions, methods=["GET"]),
        Route("/api/sessions", endpoint=create_session, methods=["POST"]),
        Route("/api/sessions/{session_id}", endpoint=delete_session, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/dispatch", endpoint=dispatch_prompt, methods=["POST"]),
        Route("/api/sessions/{session_id}/action", endpoint=session_action, methods=["POST"]),
        Route("/mcp", endpoint=mcp_endpoint, methods=["POST"]),
        WebSocketRoute("/ws/terminal/{session_id}", endpoint=terminal_ws),
        Mount("/", app=StaticFiles(directory=str(FRONTEND_DIR)), name="frontend"),
    ],
)
app.add_middleware(NoCacheMiddleware)


def main() -> None:
    parser = argparse.ArgumentParser(description="Substrate AI Design Studio Web Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--work-dir", default=os.environ.get("SUBSTRATE_WORK_DIR", ""))
    parser.add_argument("--access-token", default=os.environ.get("AISTUDIO_ACCESS_TOKEN", ""))
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.access_token:
        os.environ["AISTUDIO_ACCESS_TOKEN"] = args.access_token
    if args.allow_remote or args.host not in ("127.0.0.1", "localhost"):
        os.environ["AISTUDIO_ALLOW_REMOTE"] = "1"
    if args.work_dir:
        wd = Path(args.work_dir).expanduser().resolve()
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "MCM_template").mkdir(parents=True, exist_ok=True)
        baseline = snapshot_agent_svgs(pty_manager.agent_root) if wd != pty_manager.agent_root else {}
        pty_manager.set_working_dir(wd, sync_shells=False, svg_baseline=baseline)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
