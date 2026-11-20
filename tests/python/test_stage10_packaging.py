"""Stage 10 Windows Desktop Packaging, Offline Daemon, Version & Resource Staging Tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import URLError
from urllib.request import Request, urlopen

from core.nexus_core.config import APP_VERSION
from core.nexus_core.logging_config import configure_structured_logging


REPO_ROOT = Path(__file__).resolve().parents[2]


class Stage10PackagingTests(unittest.IsolatedAsyncioTestCase):
    def test_synced_application_version_across_manifests(self) -> None:
        expected = "0.10.0"
        self.assertEqual(APP_VERSION, expected)

        pkg_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg_json["version"], expected)

        pyproject_text = (REPO_ROOT / "core" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{expected}"', pyproject_text)

        cargo_text = (REPO_ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'version = "{expected}"', cargo_text)

        tauri_conf = json.loads(
            (REPO_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(tauri_conf["version"], expected)

    def test_offline_daemon_cli_version_health_and_rotating_log_redaction(self) -> None:
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("GEMINI") and not k.startswith("AI_STUDIO")
        }
        clean_env["PYTHONPATH"] = str(REPO_ROOT)

        ver_proc = subprocess.run(
            [sys.executable, "-m", "core.nexus_core", "--version"],
            cwd=str(REPO_ROOT),
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(ver_proc.returncode, 0, msg=ver_proc.stderr)
        ver_payload = json.loads(ver_proc.stdout.strip())
        self.assertEqual(ver_payload["version"], APP_VERSION)
        self.assertEqual(ver_payload["service"], "nexus-python-daemon")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "logs" / "nexus-daemon.log"
            health_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "core.nexus_core",
                    "--health-once",
                    "--data-dir",
                    str(tmp_path),
                    "--log-file",
                    str(log_path),
                ],
                cwd=str(REPO_ROOT),
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(health_proc.returncode, 0, msg=health_proc.stderr)
            health_payload = json.loads(health_proc.stdout)
            self.assertEqual(health_payload["version"], APP_VERSION)
            self.assertTrue(health_payload["sqliteInitialized"])
            self.assertTrue((tmp_path / "nexus.db").is_file())
            self.assertTrue((tmp_path / "daemon.token").is_file())
            self.assertTrue(log_path.is_file())

            # Verify structured logger redacts tokens even when logged to file handler
            secret_token = "nxs_super_secret_token_should_never_leak"
            logger = configure_structured_logging(level="INFO", log_file=log_path)
            logger.info(
                "Authorization: Bearer %s x-api-key=secret-demo",
                secret_token,
            )
            for handler in list(logger.handlers):
                handler.flush()
                if getattr(handler, "baseFilename", None) == str(log_path.resolve()):
                    handler.close()
                    logger.removeHandler(handler)
            log_contents = log_path.read_text(encoding="utf-8")
            self.assertNotIn(secret_token, log_contents)
            self.assertIn("[REDACTED]", log_contents)

    def test_independent_daemon_serve_and_authenticated_shutdown(self) -> None:
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("GEMINI") and not k.startswith("AI_STUDIO")
        }
        clean_env["PYTHONPATH"] = str(REPO_ROOT)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "logs" / "independent-daemon.log"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "core.nexus_core",
                    "--serve",
                    "--data-dir",
                    str(tmp_path),
                    "--bind-host",
                    "127.0.0.1",
                    "--rest-port",
                    "47129",
                    "--log-file",
                    str(log_path),
                ],
                cwd=str(REPO_ROOT),
                env={
                    **clean_env,
                    "NEXUS_WS_PORT": "0",
                    "NEXUS_MCP_PORT": "0",
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                import time

                health_data = None
                for _ in range(40):
                    if proc.poll() is not None:
                        break
                    try:
                        with urlopen("http://127.0.0.1:47129/health", timeout=1.0) as resp:
                            health_data = json.loads(resp.read().decode("utf-8"))
                            break
                    except (URLError, ConnectionError, OSError):
                        time.sleep(0.1)

                self.assertIsNotNone(health_data, "Independent daemon did not listen in time")
                assert health_data is not None
                self.assertEqual(health_data["version"], APP_VERSION)
                self.assertEqual(health_data["daemonState"], "Running")

                token = (tmp_path / "daemon.token").read_text(encoding="utf-8").strip()
                diag_req = Request(
                    "http://127.0.0.1:47129/api/v1/diagnostics",
                    headers={"Authorization": f"Bearer {token}"},
                    method="GET",
                )
                with urlopen(diag_req, timeout=2.0) as resp:
                    diag = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(diag["version"], APP_VERSION)
                self.assertEqual(diag["storage"]["integrity"], "ok")
                self.assertTrue(diag["logging"]["logFileExists"])

                shutdown_req = Request(
                    "http://127.0.0.1:47129/api/v1/daemon/shutdown",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    data=b"{}",
                    method="POST",
                )
                with urlopen(shutdown_req, timeout=2.0) as resp:
                    self.assertEqual(resp.status, 202)
                    body = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body["shuttingDown"])

                exit_code = proc.wait(timeout=8)
                self.assertEqual(exit_code, 0)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)

    def test_tauri_config_and_rust_ipc_commands(self) -> None:
        tauri_conf = json.loads(
            (REPO_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )
        bundle = tauri_conf["bundle"]
        self.assertTrue(bundle["active"])
        self.assertIn("nsis", bundle["targets"])
        self.assertIn("msi", bundle["targets"])
        self.assertIn("binaries/nexus-daemon", bundle["externalBin"])
        self.assertIn("resources/**/*", bundle["resources"])

        csp = tauri_conf["app"]["security"]["csp"]
        self.assertIn("http://127.0.0.1:*", csp)
        self.assertIn("ws://127.0.0.1:*", csp)
        self.assertNotIn("aistudio.google.com", csp)

        lib_rs = (REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        for cmd in (
            "get_desktop_runtime_info",
            "get_application_version_info",
            "probe_daemon_health",
            "start_background_daemon",
            "stop_background_daemon",
            "restart_background_daemon",
            "get_daemon_lifecycle_status",
            "get_daemon_auth_token",
            "load_desktop_configuration",
            "save_desktop_configuration",
            "collect_desktop_diagnostics",
            "get_adapter_install_instructions",
        ):
            self.assertIn(cmd, lib_rs)

        daemon_rs = (
            REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "daemon_manager.rs"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", daemon_rs)
        self.assertIn("/api/v1/daemon/shutdown", daemon_rs)

        config_rs = (
            REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "config_store.rs"
        ).read_text(encoding="utf-8")
        self.assertIn("LOCALAPPDATA", config_rs)
        self.assertIn("daemon.token", config_rs)

    def test_stage_adapter_resources_bundles_unity_and_godot(self) -> None:
        proc = subprocess.run(
            ["node", "scripts/stage-adapter-resources.mjs"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        staged_root = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "resources" / "adapters"
        self.assertTrue((staged_root / "unity" / "package.json").is_file())
        self.assertTrue((staged_root / "unity" / "nexus-adapter.manifest.json").is_file())
        self.assertTrue(
            (staged_root / "unity" / "Editor" / "NexusUnityBridgeEntrypoint.cs").is_file()
        )
        self.assertFalse((staged_root / "unity" / "test_project").exists())
        self.assertTrue(
            (staged_root / "godot" / "addons" / "nexus_bridge" / "plugin.cfg").is_file()
        )
        self.assertTrue(
            (staged_root / "godot" / "addons" / "nexus_bridge" / "plugin.gd").is_file()
        )
        self.assertTrue((staged_root / "godot" / "nexus-adapter.manifest.json").is_file())

    def test_windows_packaging_scripts_and_docs_exist(self) -> None:
        required_files = [
            "scripts/build-desktop.ps1",
            "scripts/build-python-sidecar.ps1",
            "scripts/setup-python.ps1",
            "scripts/install-windows-service.ps1",
            "scripts/uninstall-nexus.ps1",
            "scripts/verify-windows-install.ps1",
            "scripts/stage-adapter-resources.mjs",
            "docs/WINDOWS_PACKAGING_AND_INSTALL.md",
            "docs/TAURI_BUILD.md",
        ]
        for rel in required_files:
            path = REPO_ROOT / rel
            self.assertTrue(path.is_file(), f"Missing packaging artifact: {rel}")
            self.assertGreater(path.stat().st_size, 100, f"File unexpectedly empty: {rel}")

    def test_offline_frontend_dist_contains_no_cloud_lockin(self) -> None:
        dist_dir = REPO_ROOT / "dist"
        if not dist_dir.exists():
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        index_html = (dist_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("NEXUS", index_html)
        self.assertNotIn("aistudio.google.com", index_html)


if __name__ == "__main__":
    unittest.main()
