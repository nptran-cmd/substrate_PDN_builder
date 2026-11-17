"""Shared working-space path resolution helpers for PDN Architect & Studio CLI tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_PREFIXES = (
    "agent04_pdn_architect",
    "agent08_serdes_da_gpio_routing",
    "agent03_decap_placement",
    "agent01_bga_symbol_creation",
    "agent09_via_routing",
)


def _norm_path(raw: Union[str, Path]) -> Path:
    return Path(raw).expanduser().resolve()


def resolve_active_work_dir(
    explicit_work_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Path, bool]:
    """
    Resolve active working/output directory and whether it is a custom working folder.

    Precedence:
      1. Explicit `explicit_work_dir` argument
      2. Live pointer file referenced by `SUBSTRATE_WORK_DIR_FILE` (set by AIstudio)
      3. Environment variable `SUBSTRATE_WORK_DIR`
      4. Process CWD when CWD is outside the agent repository root
      5. Fallback to `REPO_ROOT` (custom=False)
    """
    if explicit_work_dir is not None and str(explicit_work_dir).strip():
        eff = _norm_path(explicit_work_dir)
        return eff, (eff != REPO_ROOT)

    ptr_raw = os.environ.get("SUBSTRATE_WORK_DIR_FILE", "").strip()
    if ptr_raw:
        try:
            ptr_file = Path(ptr_raw).expanduser()
            if ptr_file.is_file():
                ptr_txt = ptr_file.read_text(encoding="utf-8", errors="ignore").strip()
                if ptr_txt:
                    cand = Path(ptr_txt.splitlines()[0].strip()).expanduser()
                    if cand.is_dir():
                        eff = cand.resolve()
                        return eff, (eff != REPO_ROOT)
        except OSError:
            pass

    env_wd = os.environ.get("SUBSTRATE_WORK_DIR", "").strip()
    if env_wd:
        eff = _norm_path(env_wd)
        return eff, (eff != REPO_ROOT)

    try:
        cwd = Path.cwd().resolve()
        if cwd != REPO_ROOT and not cwd.is_relative_to(REPO_ROOT):
            return cwd, True
    except OSError:
        pass

    return REPO_ROOT, False


def strip_agent_prefix(rel_path: Union[str, Path]) -> Path:
    """Map `<agentXX_...>/<subpath>` to `<subpath>` so outputs stay clean inside a custom working dir."""
    parts = Path(rel_path).parts
    if parts and parts[0] in _AGENT_PREFIXES:
        return Path(*parts[1:]) if len(parts) > 1 else Path(".")
    return Path(rel_path)


def resolve_output_dir(
    default_repo_rel: Union[str, Path],
    explicit_work_dir: Optional[Union[str, Path]] = None,
    explicit_out_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Resolve an output directory so custom working folders receive all SVGs/reports/sandbox files
    while standalone repo runs keep their backwards-compatible repository paths.
    """
    eff_wd, is_custom = resolve_active_work_dir(explicit_work_dir)
    if explicit_out_dir is not None and str(explicit_out_dir).strip():
        out_p = Path(explicit_out_dir).expanduser()
        if out_p.is_absolute():
            return out_p.resolve()
        base = eff_wd if is_custom else REPO_ROOT
        cand = (base / out_p).resolve()
        if is_custom and cand.is_relative_to(REPO_ROOT):
            return (eff_wd / strip_agent_prefix(out_p)).resolve()
        return cand

    if is_custom:
        return (eff_wd / strip_agent_prefix(default_repo_rel)).resolve()
    return (REPO_ROOT / Path(default_repo_rel)).resolve()


def resolve_output_file(
    default_repo_rel: Union[str, Path],
    explicit_work_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve a default output file path inside active working dir or agent repo."""
    eff_wd, is_custom = resolve_active_work_dir(explicit_work_dir)
    if is_custom:
        return (eff_wd / strip_agent_prefix(default_repo_rel)).resolve()
    return (REPO_ROOT / Path(default_repo_rel)).resolve()


def resolve_stage1_inputs_dir(
    explicit_work_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Prefer populated `<working_dir>/stage1_inputs`, falling back read-only to repo `stage1_inputs`."""
    eff_wd, is_custom = resolve_active_work_dir(explicit_work_dir)
    if is_custom:
        cand = (eff_wd / "stage1_inputs").resolve()
        if cand.is_dir() and any(cand.glob("*.csv")):
            return cand
    return (REPO_ROOT / "agent04_pdn_architect" / "stage1_inputs").resolve()
