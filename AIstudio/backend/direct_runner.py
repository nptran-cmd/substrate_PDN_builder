"""Direct Agent 04 Python/APD runner, streamed .mcm file transfer, and /mcp handler for AIstudio."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shlex
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from .prompts_catalog import PROMPT_BUTTONS

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_PROMPT_BY_ID: Dict[str, Dict[str, Any]] = {str(p["id"]): p for p in PROMPT_BUTTONS}
_ALLOWED_FLAG_VALUES: Dict[str, Tuple[str, ...]] = {
    "--rail-group": ("core", "uncore", "chiplet", "hbm"),
    "--direction": ("VERTICAL", "HORIZONTAL", "BOTH"),
    "--pth-pattern": ("STAGGERED", "ORTHOGONAL_90DEG_VERTICAL", "ORTHOGONAL_90DEG_HORIZONTAL"),
    "--pkg-rule": ("PKG0.8", "PKG0.1"),
    "--pp-pattern": ("1_VIA_CENTER", "2_VIA_ON_PTH", "4_VIA_PER_PTH"),
}


def safe_filename(raw_name: str) -> str:
    clean = Path(str(raw_name or "").strip()).name
    if not clean or clean in (".", "..") or not _SAFE_NAME_RE.fullmatch(clean):
        raise ValueError(f"Invalid filename: {raw_name!r}")
    return clean


def resolve_prompt_argv(
    prompt_id: str,
    work_dir: Path,
    agent_root: Path,
    implement_mcm: bool = False,
    mcm_rel_path: Optional[str] = None,
) -> List[str]:
    """Resolve an allowlisted catalog prompt_id into a safe subprocess argv (no shell=True)."""
    card = _PROMPT_BY_ID.get(str(prompt_id or "").strip())
    if not card or not card.get("cli_command"):
        raise ValueError(f"Prompt '{prompt_id}' has no direct CLI runner configured.")
    tokens = shlex.split(str(card["cli_command"]))
    if not tokens:
        raise ValueError(f"Empty CLI command for '{prompt_id}'.")
    if tokens[0] in ("python", "python3"):
        tokens[0] = sys.executable
    else:
        raise ValueError(f"Only Python module invocations are permitted via direct runner (got {tokens[0]!r}).")
    if implement_mcm and "pdn_8step_flow" in " ".join(tokens) and "--implement-mcm" not in tokens:
        tokens.append("--implement-mcm")
    if mcm_rel_path and "stage1_input_builder" in " ".join(tokens):
        cand = (work_dir / mcm_rel_path).resolve()
        if cand.is_file() and cand.is_relative_to(work_dir.resolve()):
            tokens.extend(["--mcm", str(cand)])
    return tokens


async def run_direct_argv(
    argv: List[str],
    work_dir: Path,
    agent_root: Path,
    work_dir_file: Optional[Path] = None,
    timeout_s: int = 1800,
) -> Dict[str, Any]:
    """Run an Agent 04 Python/APD subprocess directly on the Studio host cleanly."""
    env = os.environ.copy()
    env["SUBSTRATE_WORK_DIR"] = str(work_dir)
    if work_dir_file is not None:
        env["SUBSTRATE_WORK_DIR_FILE"] = str(work_dir_file)
    cur_pp = env.get("PYTHONPATH", "")
    if str(agent_root) not in cur_pp.split(os.pathsep):
        env["PYTHONPATH"] = f"{agent_root}{os.pathsep}{cur_pp}".strip(os.pathsep)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(agent_root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"ok": False, "returncode": -1, "error": f"Timed out after {timeout_s}s", "stdout": "", "stderr": ""}

    out_s = out_b.decode("utf-8", errors="replace")
    err_s = err_b.decode("utf-8", errors="replace")
    return {
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode or 0),
        "argv": argv,
        "stdout": out_s[-12000:],
        "stderr": err_s[-6000:],
    }


async def stream_upload_to_mcm_template(work_dir: Path, upload_file: Any) -> Dict[str, Any]:
    """Stream multipart file upload in 1 MB chunks to `<work_dir>/MCM_template/<filename>`."""
    fname = safe_filename(str(getattr(upload_file, "filename", "") or ""))
    dest_dir = (work_dir.resolve() / "MCM_template")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / fname).resolve()
    if not dest.is_relative_to(dest_dir.resolve()):
        raise ValueError("Invalid target path.")

    total = 0
    with dest.open("wb") as out_fh:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            out_fh.write(chunk)
            total += len(chunk)
    return {"ok": True, "filename": fname, "rel_path": f"MCM_template/{fname}", "size": total}


def list_downloadable_files(work_dir: Path) -> List[Dict[str, Any]]:
    """List downloadable artifacts (.mcm, .svg, .csv, .txt) generated inside working_dir."""
    wd = work_dir.resolve()
    exts = {".mcm", ".svg", ".csv", ".txt", ".json"}
    rows: List[Dict[str, Any]] = []
    for p in sorted(wd.rglob("*"), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        rel = p.relative_to(wd).as_posix()
        if any(part.startswith(".") for part in Path(rel).parts):
            continue
        rows.append({"name": p.name, "rel_path": rel, "size": p.stat().st_size})
        if len(rows) >= 200:
            break
    return rows


def safe_resolve_workspace_file(work_dir: Path, rel_path: str) -> Optional[Path]:
    wd = work_dir.resolve()
    cand = (wd / str(rel_path or "")).resolve()
    if not cand.is_file() or not cand.is_relative_to(wd):
        return None
    return cand


def _inspect_svg_summary(svg_path: Path) -> Dict[str, Any]:
    raw = svg_path.read_text(encoding="utf-8", errors="replace")
    root = ET.fromstring(raw)
    counts: Dict[str, int] = {}
    labels: List[str] = []
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        counts[tag] = counts.get(tag, 0) + 1
        if tag == "text" and elem.text and len(labels) < 30:
            labels.append(" ".join(elem.text.split()))
    return {
        "filename": svg_path.name,
        "xml_valid": True,
        "viewBox": root.attrib.get("viewBox", ""),
        "element_counts": counts,
        "labels_sample": labels,
    }


async def handle_studio_mcp(rpc: Dict[str, Any], manager: Any) -> Dict[str, Any]:
    """Handle JSON-RPC 2.0 MCP requests directly on AIstudio (Linux or Windows)."""
    rpc_id = rpc.get("id")
    method = str(rpc.get("method", ""))
    params = rpc.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "substrate-aistudio-direct", "version": "2.0.0"},
            },
        }
    if method == "notifications/initialized":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {}}
    if method == "tools/list":
        tools = [
            {
                "name": "pdn_list_workspace_files",
                "description": "List .mcm, .csv, .svg, and recipe files inside the active Studio working_dir.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "pdn_inspect_svg",
                "description": "Validate XML and summarize element counts / labels for an SVG in working_dir.",
                "inputSchema": {"type": "object", "properties": {"rel_path": {"type": "string"}}, "required": ["rel_path"]},
            },
            {
                "name": "pdn_run_step",
                "description": "Run Agent 04 pdn_8step_flow cleanly inside the active working_dir.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rail_group": {"type": "string", "enum": ["core", "uncore", "chiplet", "hbm"], "default": "uncore"},
                        "step": {"type": "string", "default": "3"},
                        "refdes": {"type": "string"},
                        "pth_density": {"type": "number"},
                        "pth_pattern": {"type": "string"},
                        "pkg_rule": {"type": "string"},
                        "pp_pattern": {"type": "string"},
                    },
                },
            },
            {
                "name": "pdn_extract_stage1",
                "description": "Run Stage 1 extraction (stage1_input_builder) on the active .mcm using local Cadence APD.",
                "inputSchema": {"type": "object", "properties": {"mcm_rel_path": {"type": "string"}}},
            },
        ]
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": tools}}

    if method == "tools/call":
        tname = str(params.get("name", ""))
        args = dict(params.get("arguments") or {})
        wd = manager.working_dir
        is_err = False
        try:
            if tname == "pdn_list_workspace_files":
                payload: Any = {"working_dir": str(wd), "files": list_downloadable_files(wd)}
            elif tname == "pdn_inspect_svg":
                fp = safe_resolve_workspace_file(wd, str(args["rel_path"]))
                if not fp or fp.suffix.lower() != ".svg":
                    raise FileNotFoundError(f"SVG not found in workspace: {args.get('rel_path')}")
                payload = _inspect_svg_summary(fp)
            elif tname == "pdn_run_step":
                rg = str(args.get("rail_group") or "uncore")
                if rg not in _ALLOWED_FLAG_VALUES["--rail-group"]:
                    raise ValueError(f"Invalid rail_group: {rg}")
                argv = [
                    sys.executable,
                    "-m",
                    "agent04_pdn_architect.cad_cli.pdn_8step_flow",
                    "--rail-group",
                    rg,
                    "--step",
                    str(args.get("step") or "3"),
                ]
                if args.get("refdes"):
                    argv.extend(["--refdes", safe_filename(str(args["refdes"]))])
                if args.get("pth_density") is not None:
                    argv.extend(["--pth-density", str(float(args["pth_density"]))])
                for key, flag in (
                    ("pth_pattern", "--pth-pattern"),
                    ("pkg_rule", "--pkg-rule"),
                    ("pp_pattern", "--pp-pattern"),
                ):
                    if args.get(key):
                        val = str(args[key])
                        if val not in _ALLOWED_FLAG_VALUES[flag]:
                            raise ValueError(f"Invalid {key}: {val}")
                        argv.extend([flag, val])
                payload = await run_direct_argv(argv, wd, manager.agent_root, manager.work_dir_file)
            elif tname == "pdn_extract_stage1":
                argv = resolve_prompt_argv("pdn_a_prelearn", wd, manager.agent_root, mcm_rel_path=args.get("mcm_rel_path"))
                payload = await run_direct_argv(argv, wd, manager.agent_root, manager.work_dir_file)
            else:
                payload = {"error": f"Unknown tool: {tname}"}
                is_err = True
        except Exception as exc:
            payload = {"error": str(exc)}
            is_err = True
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": is_err},
        }
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Unsupported: {method}"}}
