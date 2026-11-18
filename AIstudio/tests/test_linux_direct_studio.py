"""Tests for Linux / cross-platform AIstudio, Direct Runner, Upload/Download, MCP, and Cadence APD POSIX support."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from starlette.testclient import TestClient

from AIstudio.backend import server
from AIstudio.backend.conpty import shell_quote_arg
from AIstudio.backend.direct_runner import (
    list_downloadable_files,
    resolve_prompt_argv,
    safe_resolve_workspace_file,
)
from AIstudio.backend.posix_pty import PosixPtySession, find_posix_shell
from agent09_via_routing.cad_cli.cadence_runner import CadenceBatchRunner


class TestLinuxAndDirectStudio(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_wd = server.pty_manager.working_dir
        self._orig_since = server.pty_manager.custom_work_since_ns
        self._orig_token = os.environ.get("AISTUDIO_ACCESS_TOKEN")
        self._orig_remote = os.environ.get("AISTUDIO_ALLOW_REMOTE")
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        server.pty_manager.working_dir = self.work_dir
        server.pty_manager.custom_work_since_ns = 0
        os.environ.pop("AISTUDIO_ACCESS_TOKEN", None)
        os.environ.pop("AISTUDIO_ALLOW_REMOTE", None)

    def tearDown(self) -> None:
        server.pty_manager.working_dir = self._orig_wd
        server.pty_manager.custom_work_since_ns = self._orig_since
        if self._orig_token is not None:
            os.environ["AISTUDIO_ACCESS_TOKEN"] = self._orig_token
        else:
            os.environ.pop("AISTUDIO_ACCESS_TOKEN", None)
        if self._orig_remote is not None:
            os.environ["AISTUDIO_ALLOW_REMOTE"] = self._orig_remote
        else:
            os.environ.pop("AISTUDIO_ALLOW_REMOTE", None)
        self._tmp.cleanup()

    def test_posix_pty_imports_cleanly_and_quotes_per_platform(self) -> None:
        self.assertTrue(hasattr(PosixPtySession, "foreground_status"))
        self.assertTrue(callable(find_posix_shell))
        self.assertEqual(shell_quote_arg("a b'c", platform_name="nt"), "'a b''c'")
        self.assertEqual(shell_quote_arg("a b'c", platform_name="posix"), "'a b'\"'\"'c'")

    def test_cadence_runner_resolves_linux_run_apd_and_xvfb(self) -> None:
        fake_run_apd = self.work_dir / "run_apd.sh"
        fake_run_apd.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        fake_mcm = self.work_dir / "demo.mcm"
        fake_mcm.write_bytes(b"FAKE")
        fake_scr = self.work_dir / "run.scr"
        fake_scr.write_text("exit\n", encoding="utf-8")

        captured_cmd = []

        class _FakeProc:
            pid = 99999
            returncode = 0

            def communicate(self, timeout=None):
                return ("OK", "")

            def kill(self):
                self.killed = True

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return _FakeProc()

        with mock.patch("agent09_via_routing.cad_cli.cadence_runner.os.name", "posix"), mock.patch(
            "agent09_via_routing.cad_cli.cadence_runner.Path", type(self.work_dir)
        ), mock.patch.dict(
            os.environ, {"CADENCE_RUN_APD_SH": str(fake_run_apd), "DISPLAY": ""}, clear=False
        ), mock.patch(
            "agent09_via_routing.cad_cli.cadence_runner.shutil.which",
            side_effect=lambda tool: "/usr/bin/xvfb-run" if tool == "xvfb-run" else None,
        ):
            runner = CadenceBatchRunner()
            self.assertEqual(runner.apd_path, fake_run_apd)
            env_info = runner.check_environment()
            self.assertTrue(env_info["binary_found"])
            self.assertEqual(env_info["binary_path"], str(fake_run_apd))

            with mock.patch("agent09_via_routing.cad_cli.cadence_runner.subprocess.Popen", side_effect=fake_popen):
                res = runner.run(fake_mcm, fake_scr, working_dir=self.work_dir)
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(captured_cmd[:2], ["xvfb-run", "-a"])
            self.assertEqual(captured_cmd[2], str(fake_run_apd))

            proc = _FakeProc()
            CadenceBatchRunner._terminate_process(proc, platform_name="posix")
            self.assertTrue(getattr(proc, "killed", False))

    def test_direct_runner_allowlist_and_path_traversal_guard(self) -> None:
        agent_root = server.pty_manager.agent_root
        argv = resolve_prompt_argv("pdn_a_prelearn", self.work_dir, agent_root)
        self.assertEqual(argv[0], sys.executable)
        self.assertIn("agent04_pdn_architect.cad_cli.stage1_input_builder", argv)

        with self.assertRaises(ValueError):
            resolve_prompt_argv("pdn_f_vdduc_vddch", self.work_dir, agent_root)
        with self.assertRaises(ValueError):
            resolve_prompt_argv("unknown_prompt_xyz", self.work_dir, agent_root)

        self.assertIsNone(safe_resolve_workspace_file(self.work_dir, "../outside.txt"))

    def test_upload_mcm_list_and_download_roundtrip(self) -> None:
        client = TestClient(server.app)
        payload = b"ALLEGRO_MCM_STREAM_TEST_123456"
        up_resp = client.post(
            "/api/workspace/upload-mcm",
            files={"file": ("unit_test_pkg.mcm", payload, "application/octet-stream")},
        )
        self.assertEqual(up_resp.status_code, 200)
        up_data = up_resp.json()
        self.assertTrue(up_data["ok"])
        self.assertEqual(up_data["rel_path"], "MCM_template/unit_test_pkg.mcm")
        self.assertEqual((self.work_dir / "MCM_template" / "unit_test_pkg.mcm").read_bytes(), payload)

        list_resp = client.get("/api/workspace/downloads")
        self.assertEqual(list_resp.status_code, 200)
        names = [f["rel_path"] for f in list_resp.json()["files"]]
        self.assertIn("MCM_template/unit_test_pkg.mcm", names)

        dl_resp = client.get("/api/workspace/download", params={"path": "MCM_template/unit_test_pkg.mcm"})
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp.content, payload)

        bad_dl = client.get("/api/workspace/download", params={"path": "../etc/passwd"})
        self.assertEqual(bad_dl.status_code, 404)

    def test_direct_run_endpoint_and_mcp_and_access_token_auth(self) -> None:
        client = TestClient(server.app)

        async def fake_direct_argv(argv, work_dir, agent_root, work_dir_file=None, timeout_s=1800):
            return {"ok": True, "returncode": 0, "argv": argv, "stdout": "DIRECT_OK\n", "stderr": ""}

        with mock.patch.object(server, "run_direct_argv", side_effect=fake_direct_argv):
            ok_resp = client.post("/api/direct/run", json={"prompt_id": "pdn_a_prelearn", "implement_mcm": False})
            self.assertEqual(ok_resp.status_code, 200)
            self.assertTrue(ok_resp.json()["ok"])
            self.assertIn("DIRECT_OK", ok_resp.json()["stdout"])

            bad_resp = client.post("/api/direct/run", json={"prompt_id": "no_such_card"})
            self.assertEqual(bad_resp.status_code, 400)
            self.assertFalse(bad_resp.json()["ok"])

        init_rpc = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init_rpc.status_code, 200)
        self.assertEqual(init_rpc.json()["result"]["serverInfo"]["name"], "substrate-aistudio-direct")

        list_rpc = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = [t["name"] for t in list_rpc.json()["result"]["tools"]]
        self.assertIn("pdn_run_step", tool_names)
        self.assertIn("pdn_list_workspace_files", tool_names)

        os.environ["AISTUDIO_ACCESS_TOKEN"] = "secret-linux-tok"
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/catalog").status_code, 401)
        self.assertEqual(client.get("/api/catalog", headers={"X-AIStudio-Token": "secret-linux-tok"}).status_code, 200)

        redir = client.get("/?token=secret-linux-tok", follow_redirects=False)
        self.assertEqual(redir.status_code, 302)
        self.assertEqual(redir.cookies.get("aistudio_token"), "secret-linux-tok")
        os.environ["AISTUDIO_ALLOW_REMOTE"] = "1"
        os.environ["AISTUDIO_ALLOWED_DOMAIN_SUFFIXES"] = ".example.com"
        self.assertTrue(server._is_allowed_origin("https://linux-host.example.com:8765", "linux-host.example.com:8765"))

    def test_start_linux_script_flags_match_server_cli(self) -> None:
        sh_path = Path(server.pty_manager.agent_root) / "AIstudio" / "start_linux_studio.sh"
        sh_text = sh_path.read_text(encoding="utf-8")
        self.assertNotIn("--no-browser", sh_text)
        with mock.patch("uvicorn.run") as fake_uv, mock.patch.object(
            sys,
            "argv",
            ["server.py", "--host", "127.0.0.1", "--port", "8765", "--work-dir", str(self.work_dir), "--no-browser"],
        ):
            server.main()
            self.assertEqual(fake_uv.call_count, 1)


if __name__ == "__main__":
    unittest.main()
