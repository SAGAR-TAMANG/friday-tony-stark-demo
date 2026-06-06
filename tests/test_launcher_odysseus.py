import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from friday.desktop import launcher


class LauncherOdysseusTests(unittest.TestCase):
    def test_odysseus_health_uses_configured_base_url(self):
        with patch.dict(os.environ, {"ODYSSEUS_BASE_URL": "http://127.0.0.1:7891"}, clear=False):
            with patch("friday.desktop.launcher.httpx.get") as get:
                get.return_value = Mock(status_code=200)

                self.assertTrue(launcher.odysseus_is_running())

        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], "http://127.0.0.1:7891/api/health")

    def test_ensure_odysseus_running_reuses_healthy_server(self):
        with patch("friday.desktop.launcher.odysseus_is_running", return_value=True):
            result = launcher.ensure_odysseus_running()

        self.assertEqual(result["status"], "already_running")

    def test_ensure_odysseus_running_starts_repo_venv_uvicorn(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "app.py").write_text("# fake app")
            venv_python = repo / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("# fake")

            with (
                patch.dict(
                    os.environ,
                    {
                        "ODYSSEUS_REPO": str(repo),
                        "ODYSSEUS_BASE_URL": "http://127.0.0.1:7892",
                    },
                    clear=False,
                ),
                patch("friday.desktop.launcher.odysseus_is_running", return_value=False),
                patch("friday.desktop.launcher.subprocess.Popen") as popen,
            ):
                popen.return_value = Mock(pid=12345)
                result = launcher.ensure_odysseus_running()

        self.assertEqual(result["status"], "launched")
        args = popen.call_args.args[0]
        self.assertEqual(args[0], str(venv_python.resolve()))
        self.assertEqual(args[1:4], ["-m", "uvicorn", "app:app"])
        self.assertIn("--port", args)
        self.assertEqual(args[args.index("--port") + 1], "7892")
        self.assertEqual(popen.call_args.kwargs["cwd"], str(repo.resolve()))
        self.assertEqual(popen.call_args.kwargs["env"]["AUTH_ENABLED"], "false")


if __name__ == "__main__":
    unittest.main()
