"""Automated unit and integration tests for Substrate AI Design Studio (AIstudio)."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from AIstudio.backend.conpty import ConPtyManager, find_jetski_exe, ps_single_quote, shell_quote_arg
from AIstudio.backend.server import _is_allowed_origin, app, pty_manager


class _DummySession:
    def __init__(self, jetski_active: bool) -> None:
        self._jetski_active = jetski_active

    def foreground_status(self):
        return {"jetski_active": self._jetski_active}


class TestSubstrateAIStudio(unittest.TestCase):
    def test_origin_guard_and_quoting(self) -> None:
        self.assertTrue(_is_allowed_origin(None))
        self.assertTrue(_is_allowed_origin("http://127.0.0.1:8765"))
        self.assertTrue(_is_allowed_origin("http://localhost:8765"))
        self.assertFalse(_is_allowed_origin("https://evil.example.com"))

        quoted = ps_single_quote("Route @{design} with 'TX_0' & $var")
        self.assertEqual(quoted, "'Route @{design} with ''TX_0'' & $var'")

    def test_dispatch_modes(self) -> None:
        mgr = ConPtyManager(Path.cwd())
        shell_sess = _DummySession(jetski_active=False)
        jetski_sess = _DummySession(jetski_active=True)

        p1 = mgr.build_dispatch_payload(shell_sess, "Inspect @a.mcm", mode="auto", model="gemini-flash-next")
        self.assertEqual(p1["effective_mode"], "jetski_interactive")
        expected_model_arg = shell_quote_arg("gemini-flash-next")
        self.assertIn(f"jetski -i 'Inspect @a.mcm' --model {expected_model_arg}", str(p1["write_text"]))
        self.assertFalse(p1["needs_enter_delay"])

        p2 = mgr.build_dispatch_payload(jetski_sess, "Line1\nLine2", mode="auto")
        self.assertEqual(p2["effective_mode"], "inject_jetski")
        self.assertEqual(p2["write_text"], "Line1 Line2")
        self.assertTrue(p2["needs_enter_delay"])

        p3 = mgr.build_dispatch_payload(shell_sess, "ignored", mode="shell", cli_command="python --version")
        self.assertEqual(p3["effective_mode"], "shell")
        self.assertEqual(p3["write_text"], "python --version\r")

    def test_rest_catalog_and_static_assets(self) -> None:
        with TestClient(app) as client:
            health = client.get("/api/health").json()
            self.assertTrue(health["ok"])

            cat = client.get("/api/catalog").json()
            self.assertEqual(len(cat["categories"]), 5)
            self.assertEqual(
                [c["label"] for c in cat["categories"]],
                [
                    "1. Core (VDDC/SRAM)",
                    "2. Uncore (VDDUC)",
                    "3. Chiplet (VDDCH)",
                    "4. HBM",
                    "5. Full A-Z & Stage 1",
                ],
            )
            self.assertEqual(len(cat["prompts"]), 48)
            self.assertEqual(cat["prompts"][0]["category"], "core_vddc_sram")
            self.assertEqual(cat["prompts"][0]["code"], "0")
            for cat_id in ("core_vddc_sram", "uncore_vdduc", "chiplet_vddch", "hbm"):
                step_cards = [p for p in cat["prompts"] if p["category"] == cat_id]
                self.assertEqual(len(step_cards), 9)
                self.assertEqual([p["code"] for p in step_cards], [str(i) for i in range(0, 9)])
            # On startup with repo root as default (no custom working space), repo SVGs are hidden
            self.assertEqual(cat["svgs"], [])
            self.assertEqual(client.get("/api/svgs").json()["svgs"], [])
            self.assertEqual(
                client.get(
                    "/api/svg-file?path=agent04_pdn_architect/pdn_sandbox/u9_vddc0_sram0_lsc_new_rule_395_390_comparison.svg"
                ).status_code,
                404,
            )
            # Block traversal outside allowed PDN workspace directories
            self.assertEqual(client.get("/api/svg-file?path=../PLAN.md").status_code, 404)

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertNotIn("Filter prompts", home.text)
            self.assertIn("svgPreviewImg", home.text)

            for route in ("/", "/styles.css", "/app.js", "/vendor/xterm.js", "/vendor/addon-fit.js", "/vendor/xterm.css"):
                resp = client.get(route)
                self.assertEqual(resp.status_code, 200, f"Asset route failed: {route}")

    def test_working_folder_switch_keeps_agent_root_and_serves_working_svgs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            tpl_dir = work_dir / "MCM_template"
            tpl_dir.mkdir(parents=True, exist_ok=True)
            (tpl_dir / "origin_pkg.mcm").write_bytes(b"MOCK_MCM_ORIGIN")
            (work_dir / "built_output.mcm").write_bytes(b"MOCK_BUILT")

            with TestClient(app) as client:
                orig_root = client.get("/api/workspace").json()["workspace"]["agent_root"]
                try:
                    # Selecting an empty-of-SVG custom working folder returns 0 SVGs (no repo SVG leakage)
                    sel_empty = client.post("/api/workspace/select", json={"path": str(work_dir)})
                    self.assertEqual(sel_empty.status_code, 200)
                    data = sel_empty.json()
                    self.assertEqual(Path(data["workspace"]["working_dir"]), work_dir.resolve())
                    self.assertEqual(data["workspace"]["agent_root"], orig_root)
                    self.assertTrue(data["workspace"]["is_custom_dir"])
                    self.assertEqual(Path(data["workspace"]["mcm_template_dir"]), tpl_dir.resolve())
                    self.assertEqual(data["workspace"]["origin_templates"][0]["rel_path"], "MCM_template/origin_pkg.mcm")
                    self.assertEqual(data["workspace"]["working_templates"][0]["rel_path"], "MCM_template/origin_pkg.mcm")
                    self.assertEqual(data["svgs"], [])
                    self.assertEqual(client.get("/api/svgs").json()["svgs"], [])

                    # Template SVGs inside MCM_template must remain hidden & blocked; only working-space SVGs appear
                    tpl_svg = tpl_dir / "ignored_tpl_ref.svg"
                    tpl_svg.write_text(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect width="50" height="50"/></svg>',
                        encoding="utf-8",
                    )
                    svg_out = work_dir / "reports" / "custom_pdn_view.svg"
                    svg_out.parent.mkdir(parents=True, exist_ok=True)
                    svg_out.write_text(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100"/></svg>',
                        encoding="utf-8",
                    )

                    work_svgs = client.get("/api/svgs").json()["svgs"]
                    self.assertEqual(len(work_svgs), 1)
                    self.assertEqual(work_svgs[0]["source"], "working_dir")
                    self.assertEqual(work_svgs[0]["rel_path"], "work://reports/custom_pdn_view.svg")

                    svg_resp = client.get(f"/api/svg-file?path={work_svgs[0]['rel_path']}")
                    self.assertEqual(svg_resp.status_code, 200)
                    self.assertIn("<svg", svg_resp.text)
                    self.assertEqual(client.get("/api/svg-file?path=work://MCM_template/ignored_tpl_ref.svg").status_code, 404)
                    self.assertEqual(
                        client.get(
                            "/api/svg-file?path=agent04_pdn_architect/pdn_sandbox/u9_vddc0_sram0_lsc_new_rule_395_390_comparison.svg"
                        ).status_code,
                        404,
                    )

                    ls_resp = client.get(f"/api/workspace/ls?path={work_dir}")
                    self.assertEqual(ls_resp.status_code, 200)
                    self.assertTrue(ls_resp.json()["has_mcm_template_dir"])
                    self.assertEqual(ls_resp.json()["mcm_files"][0], "MCM_template/origin_pkg.mcm")

                    # New session starts in custom working_dir while preserving agent_root & --add-dir
                    sess = pty_manager.create_session(title="WD Test")
                    self.assertEqual(sess.cwd, work_dir.resolve())
                    self.assertEqual(sess.agent_root, Path(orig_root).resolve())
                    plan = pty_manager.build_dispatch_payload(
                        sess,
                        "Build PDN",
                        mode="auto",
                        work_context=f"[Active Working Folder: {work_dir.resolve()} | MCM Origine: MCM_template/origin_pkg.mcm]",
                    )
                    self.assertIn("--add-dir", str(plan["write_text"]))
                    self.assertIn(orig_root, str(plan["write_text"]))
                    self.assertIn("MCM_template/origin_pkg.mcm", str(plan["write_text"]))
                    pty_manager.close_session(sess.session_id)
                finally:
                    reset_resp = client.post("/api/workspace/select", json={"path": orig_root})
                    self.assertEqual(reset_resp.status_code, 200)
                    self.assertFalse(reset_resp.json()["workspace"]["is_custom_dir"])
                    self.assertEqual(reset_resp.json()["svgs"], [])

    def test_stage1_export_into_custom_working_folder(self) -> None:
        import json
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.full_package_all_dies_pdn import _resolve_pdn_io_context
        from agent04_pdn_architect.cad_cli.stage1_input_builder import run_stage1_full_input_preparation

        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            tpl_dir = work_dir / "MCM_template"
            tpl_dir.mkdir(parents=True, exist_ok=True)
            origin_mcm = tpl_dir / "origin_pkg_tpl.mcm"
            origin_mcm.write_bytes(b"MOCK_TEMPLATE_ORIGIN")
            # Even if a built output .mcm exists directly in work_dir with newer timestamp,
            # MCM_template/*.mcm MUST remain the resolved origin template.
            (work_dir / "newer_built_output.mcm").write_bytes(b"MOCK_BUILT_OUTPUT")
            stage1_dir = work_dir / "stage1_inputs"
            stage1_dir.mkdir(parents=True, exist_ok=True)
            (stage1_dir / "stackup_from_mcm.csv").write_text(
                "layer_index,subclass_name,layer_type\n1,TOP,CONDUCTOR\n2,4FCO,CONDUCTOR\n3,2FCI,CONDUCTOR\n4,BOTTOM,CONDUCTOR\n",
                encoding="utf-8",
            )
            (stage1_dir / "padstacks_from_mcm.csv").write_text(
                "padstack_name,is_through,start_layer,end_layer,drill_um\nV90_65_90_SURFACE_12F,FALSE,SURFACE,12F,65.0\n",
                encoding="utf-8",
            )

            res = run_stage1_full_input_preparation(
                padstack_lib_dir=str(work_dir / "no_padlib"),
                symbols_dir=str(work_dir / "no_symbols"),
                run_headless_apd_extract=False,
                work_dir=str(work_dir),
            )
            self.assertEqual(res["working_dir"], str(work_dir.resolve()))
            self.assertEqual(res["export_dir"], str(stage1_dir.resolve()))
            self.assertEqual(res["source_mcm"], str(origin_mcm.resolve()))

            eff_wd, is_custom_wd, pdn_src_mcm, pdn_s1 = _resolve_pdn_io_context(work_dir=str(work_dir))
            self.assertTrue(is_custom_wd)
            self.assertEqual(eff_wd, work_dir.resolve())
            self.assertEqual(pdn_src_mcm, origin_mcm.resolve())
            self.assertEqual(pdn_s1, stage1_dir.resolve())

            for fname in (
                "stackup_53layers.csv",
                "stackup_zones.json",
                "padstack_library_index.csv",
                "design_rules_indexed.json",
                "pdn_knowledge_index.json",
                "stage1_master_manifest.json",
                "stage1_data_summary.svg",
            ):
                self.assertTrue((stage1_dir / fname).is_file(), f"Missing exported Stage 1 file: {fname}")

            manifest = json.loads((stage1_dir / "stage1_master_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stackup_summary"]["total_stackup_layers"], 4)
            svg_root = ET.fromstring((stage1_dir / "stage1_data_summary.svg").read_text(encoding="utf-8"))
            self.assertTrue(svg_root.tag.endswith("svg"))

    def test_live_conpty_websocket_and_button_dispatch(self) -> None:
        with TestClient(app) as client:
            created = client.post("/api/sessions", json={"title": "QA Test Term", "cols": 110, "rows": 32})
            self.assertEqual(created.status_code, 201)
            sid = created.json()["session"]["session_id"]

            # Reject external origin on WebSocket
            with self.assertRaises(Exception):
                with client.websocket_connect(
                    f"/ws/terminal/{sid}", headers={"origin": "https://untrusted.example"}
                ):
                    pass

            with client.websocket_connect(
                f"/ws/terminal/{sid}", headers={"origin": "http://127.0.0.1:8765"}
            ) as ws:
                ws.send_json({"type": "resize", "cols": 100, "rows": 30})
                time.sleep(1.2)

                dispatch = client.post(
                    f"/api/sessions/{sid}/dispatch",
                    json={"prompt": "echo AISTUDIO_PTY_PASS", "mode": "shell"},
                )
                self.assertEqual(dispatch.status_code, 200)
                self.assertEqual(dispatch.json()["effective_mode"], "shell")

                collected = []
                deadline = time.time() + 12.0
                found = False

                def read_until_marker() -> None:
                    nonlocal found
                    while time.time() < deadline:
                        msg = ws.receive_json()
                        if msg.get("type") == "output":
                            collected.append(msg.get("data", ""))
                            if "AISTUDIO_PTY_PASS" in "".join(collected):
                                found = True
                                return

                t = threading.Thread(target=read_until_marker, daemon=True)
                t.start()
                t.join(timeout=13.0)
                self.assertTrue(found, f"Marker missing from ConPTY stream: {''.join(collected)[:400]}")

                if os.name == "nt" and find_jetski_exe():
                    # Verify Jetski alias is configured in the spawned PowerShell session and runs jetski --help
                    alias_dispatch = client.post(
                        f"/api/sessions/{sid}/dispatch",
                        json={"prompt": "jetski --help | Select-Object -First 1", "mode": "shell"},
                    )
                    self.assertEqual(alias_dispatch.status_code, 200)

                    alias_found = False
                    deadline2 = time.time() + 12.0

                    def read_until_jetski_help() -> None:
                        nonlocal alias_found
                        while time.time() < deadline2:
                            msg = ws.receive_json()
                            if msg.get("type") == "output":
                                collected.append(msg.get("data", ""))
                                if "Usage of jetski-cli.exe" in "".join(collected):
                                    alias_found = True
                                    return

                    t2 = threading.Thread(target=read_until_jetski_help, daemon=True)
                    t2.start()
                    t2.join(timeout=13.0)
                    self.assertTrue(alias_found, f"jetski alias failed inside ConPTY: {''.join(collected)[-400:]}")

                # Verify session action endpoint validation and ctrl_c
                act_ok = client.post(f"/api/sessions/{sid}/action", json={"action": "ctrl_c"})
                self.assertEqual(act_ok.status_code, 200)
                act_bad = client.post(f"/api/sessions/{sid}/action", json={"action": "invalid_action"})
                self.assertEqual(act_bad.status_code, 400)

                sess_obj = pty_manager.get_session(sid)
                self.assertIsNotNone(sess_obj)
                self.assertEqual(sess_obj.cols, 100)
                self.assertEqual(sess_obj.rows, 30)

            deleted = client.delete(f"/api/sessions/{sid}")
            self.assertEqual(deleted.status_code, 200)
            self.assertIsNone(pty_manager.get_session(sid))

    def test_agent_svg_relocated_to_working_folder_and_pdn_paths(self) -> None:
        import os
        import uuid
        from agent04_pdn_architect.cad_cli.pdn_paths import (
            REPO_ROOT,
            resolve_active_work_dir,
            resolve_output_dir,
            resolve_output_file,
        )

        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            wd1 = Path(td1).resolve()
            wd2 = Path(td2).resolve()
            probe_name = f"_qa_reloc_probe_{uuid.uuid4().hex[:8]}.svg"
            agent_probe = REPO_ROOT / "agent04_pdn_architect" / "pdn_sandbox" / probe_name

            with TestClient(app) as client:
                orig_root = client.get("/api/workspace").json()["workspace"]["agent_root"]
                try:
                    # 1. Switch to wd1 then wd2 and confirm live work_dir_file syncs without restart
                    r1 = client.post("/api/workspace/select", json={"path": str(wd1)})
                    self.assertEqual(r1.status_code, 200)
                    r2 = client.post("/api/workspace/select", json={"path": str(wd2)})
                    self.assertEqual(r2.status_code, 200)

                    self.assertTrue(pty_manager.work_dir_file.is_file())
                    self.assertEqual(Path(pty_manager.work_dir_file.read_text(encoding="utf-8").strip()), wd2)

                    # Verify pdn_paths resolves SUBSTRATE_WORK_DIR_FILE -> wd2 -> outputs under wd2
                    prev_file = os.environ.get("SUBSTRATE_WORK_DIR_FILE")
                    prev_wd = os.environ.get("SUBSTRATE_WORK_DIR")
                    try:
                        os.environ["SUBSTRATE_WORK_DIR_FILE"] = str(pty_manager.work_dir_file)
                        os.environ["SUBSTRATE_WORK_DIR"] = str(wd1)  # stale env should yield to live file
                        eff_wd, is_custom = resolve_active_work_dir()
                        self.assertTrue(is_custom)
                        self.assertEqual(eff_wd, wd2)
                        self.assertEqual(
                            resolve_output_dir("agent04_pdn_architect/pdn_sandbox"),
                            wd2 / "pdn_sandbox",
                        )
                        self.assertEqual(
                            resolve_output_dir("agent04_pdn_architect/reports/curved_recess_lsc"),
                            wd2 / "reports" / "curved_recess_lsc",
                        )
                        self.assertEqual(
                            resolve_output_file("agent04_pdn_architect/svg_sandbox/z.svg"),
                            wd2 / "svg_sandbox" / "z.svg",
                        )
                    finally:
                        if prev_file is None:
                            os.environ.pop("SUBSTRATE_WORK_DIR_FILE", None)
                        else:
                            os.environ["SUBSTRATE_WORK_DIR_FILE"] = prev_file
                        if prev_wd is None:
                            os.environ.pop("SUBSTRATE_WORK_DIR", None)
                        else:
                            os.environ["SUBSTRATE_WORK_DIR"] = prev_wd

                    # 2. Simulate an ad-hoc agent writing a new SVG inside agent04_pdn_architect/pdn_sandbox/
                    agent_probe.parent.mkdir(parents=True, exist_ok=True)
                    agent_probe.write_text(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect width="50" height="50"/></svg>',
                        encoding="utf-8",
                    )

                    resp = client.get("/api/svgs").json()
                    expected_dest = wd2 / "pdn_sandbox" / probe_name
                    self.assertFalse(agent_probe.exists(), "Agent-created SVG should be moved out of agent repo")
                    self.assertTrue(expected_dest.is_file(), "Agent-created SVG should land in working folder")
                    self.assertEqual(resp["relocated"][0]["action"], "moved")
                    self.assertEqual(resp["relocated"][0]["to"], f"work://pdn_sandbox/{probe_name}")
                    self.assertTrue(any(s["rel_path"] == f"work://pdn_sandbox/{probe_name}" for s in resp["svgs"]))
                finally:
                    if agent_probe.exists():
                        agent_probe.unlink()
                    client.post("/api/workspace/select", json={"path": orig_root})


if __name__ == "__main__":
    unittest.main()
