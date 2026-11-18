#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${AISTUDIO_HOST:-127.0.0.1}"
PORT="${AISTUDIO_PORT:-8765}"
WORK_DIR="${SUBSTRATE_WORK_DIR:-$HOME/pdn_workspaces}"
ACCESS_TOKEN="${AISTUDIO_ACCESS_TOKEN:-}"
ALLOW_REMOTE=0
BOOTSTRAP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --work-dir)
      WORK_DIR="$2"
      shift 2
      ;;
    --access-token)
      ACCESS_TOKEN="$2"
      shift 2
      ;;
    --allow-remote|--remote)
      ALLOW_REMOTE=1
      if [[ "$HOST" == "127.0.0.1" ]]; then
        HOST="0.0.0.0"
      fi
      shift
      ;;
    --bootstrap)
      BOOTSTRAP=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./AIstudio/start_linux_studio.sh [options]
  --host <ip>            Bind host (default: 127.0.0.1)
  --port <port>          Bind port (default: 8765)
  --work-dir <path>      PDN workspace directory (default: ~/pdn_workspaces)
  --access-token <tok>   Require X-AIStudio-Token / ?token= auth (recommended for remote)
  --allow-remote         Bind 0.0.0.0 and allow non-loopback Origin/Host headers
  --bootstrap            Create .venv_linux if missing and install AIstudio/requirements.txt
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$WORK_DIR/MCM_template"

# Keep cadence_env.sh isolated inside apd subprocesses invoked by run_apd.sh,
# so Cadence shared libraries do not pollute Python's LD_LIBRARY_PATH.
export CADENCE_RUN_APD_SH="${CADENCE_RUN_APD_SH:-$HOME/cadence/installs/run_apd.sh}"
export SUBSTRATE_WORK_DIR="$WORK_DIR"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

VENV_DIR="$REPO_ROOT/.venv_linux"
if [[ "$BOOTSTRAP" -eq 1 && ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[AIstudio] Creating virtual environment at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[AIstudio] ERROR: python3 not found." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import starlette, uvicorn, websockets; import importlib.util; assert importlib.util.find_spec('python_multipart') or importlib.util.find_spec('multipart')" 2>/dev/null; then
  if [[ "$BOOTSTRAP" -eq 1 ]]; then
    echo "[AIstudio] Installing AIstudio dependencies into $PYTHON_BIN..."
    "$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt"
  else
    echo "[AIstudio] Missing Python deps (starlette/uvicorn/websockets/python-multipart)." >&2
    echo "[AIstudio] Re-run with --bootstrap or run: $PYTHON_BIN -m pip install -r AIstudio/requirements.txt" >&2
    exit 1
  fi
fi

if [[ ! -x "$CADENCE_RUN_APD_SH" ]]; then
  echo "[AIstudio] WARNING: CADENCE_RUN_APD_SH not executable at $CADENCE_RUN_APD_SH" >&2
fi
if ! command -v xvfb-run >/dev/null 2>&1 && [[ -z "${DISPLAY:-}" ]]; then
  echo "[AIstudio] WARNING: Neither xvfb-run nor DISPLAY is set; Cadence APD batch calls may require xvfb-run." >&2
fi

cd "$REPO_ROOT"
ARGS=(
  -m AIstudio.backend.server
  --host "$HOST"
  --port "$PORT"
  --work-dir "$WORK_DIR"
)
if [[ "$ALLOW_REMOTE" -eq 1 ]]; then
  ARGS+=(--allow-remote)
fi
if [[ -n "$ACCESS_TOKEN" ]]; then
  export AISTUDIO_ACCESS_TOKEN="$ACCESS_TOKEN"
fi

echo "[AIstudio] Starting Substrate AI Design Studio on Linux..."
echo "  Repo Root : $REPO_ROOT"
echo "  Work Dir  : $WORK_DIR"
echo "  run_apd.sh: $CADENCE_RUN_APD_SH"
echo "  Listen    : http://$HOST:$PORT"
exec "$PYTHON_BIN" "${ARGS[@]}"
