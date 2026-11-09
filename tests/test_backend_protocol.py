from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


class BackendProtocolTests(unittest.TestCase):
    def test_backend_boot_login_project_and_shutdown(self) -> None:
        test_root = ROOT / ".test-data"
        test_root.mkdir(exist_ok=True)
        temporary = tempfile.mkdtemp(prefix="protocol-", dir=test_root)
        self.addCleanup(shutil.rmtree, temporary, True)
        environment = os.environ.copy()
        ffmpeg_dir = environment.get("YJJ_FFMPEG_DIR", "")
        environment.update(
            {
                "AIVE_DATA_DIR": temporary,
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "YJJ_ADMIN_USER": "local-owner",
                "YJJ_ADMIN_PASSWORD": "A-test-password-123!",
            }
        )
        if ffmpeg_dir:
            environment["YJJ_FFMPEG_DIR"] = ffmpeg_dir
        process = subprocess.Popen(
            [sys.executable, str(BACKEND / "run_ui2_backend.py")],
            cwd=BACKEND,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            ready_line = process.stdout.readline()
            if not ready_line:
                stderr = process.stderr.read()
                self.fail(f"backend exited before readiness: {stderr}")
            ready = json.loads(ready_line)
            self.assertEqual("backend.ready", ready["event"])

            def request(identifier: str, action: str, data: dict) -> dict:
                process.stdin.write(
                    json.dumps({"id": identifier, "action": action, "data": data})
                    + "\n"
                )
                process.stdin.flush()
                while True:
                    response = json.loads(process.stdout.readline())
                    if "id" in response:
                        self.assertEqual(identifier, response["id"])
                        return response
                    self.assertIn("event", response)

            bootstrap = request("1", "app.bootstrap", {})
            self.assertTrue(bootstrap["success"], bootstrap.get("error"))
            self.assertEqual("羊剪剪", bootstrap["data"]["name"])
            self.assertTrue(bootstrap["data"]["license"]["required"])

            login = request(
                "2",
                "license.login",
                {"username": "local-owner", "password": "A-test-password-123!"},
            )
            self.assertTrue(login["success"])
            self.assertFalse(login["data"]["required"])

            project = request(
                "3",
                "project.create",
                {
                    "name": "协议验收项目",
                    "path": str(Path(temporary) / "projects"),
                    "ratio": "9:16",
                    "template": "blank",
                },
            )
            self.assertTrue(project["success"])
            self.assertEqual("协议验收项目", project["data"]["name"])

            if ffmpeg_dir:
                source = Path(temporary) / "probe-source.mp4"
                ffmpeg = Path(ffmpeg_dir) / "ffmpeg.exe"
                subprocess.run(
                    [
                        str(ffmpeg),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=blue:s=320x240:d=1",
                        "-f",
                        "lavfi",
                        "-i",
                        "sine=frequency=440:duration=1",
                        "-shortest",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-y",
                        str(source),
                    ],
                    check=True,
                    timeout=30,
                )
                probe = request("4", "video.probe", {"path": str(source)})
                self.assertTrue(probe["success"], probe.get("error"))
                self.assertEqual(320, probe["data"]["width"])
                self.assertEqual(240, probe["data"]["height"])
                self.assertGreater(probe["data"]["duration"], 0.5)
                self.assertTrue(
                    probe["data"]["preview"].startswith("data:image/jpeg;base64,")
                )
                shutdown_id = "5"
            else:
                shutdown_id = "4"

            shutdown = request(shutdown_id, "app.shutdown", {})
            self.assertTrue(shutdown["success"])
            self.assertTrue(shutdown["data"])
            process.stdin.close()
            self.assertEqual(0, process.wait(timeout=10))
        finally:
            self._terminate(process)
            if not process.stdout.closed:
                process.stdout.close()
            if not process.stderr.closed:
                process.stderr.close()

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

if __name__ == "__main__":
    unittest.main()
