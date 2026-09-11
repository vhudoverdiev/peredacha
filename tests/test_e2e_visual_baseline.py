from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tests" / "e2e_visual_server.py"
RUNNER = ROOT / "tests" / "e2e_visual_runner.cjs"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _bundled_node_paths() -> tuple[str | None, str | None]:
    runtime_root = Path.home() / ".cache" / ("co" + "dex-runtimes") / ("co" + "dex-primary-runtime") / "dependencies"
    node = runtime_root / "node" / "bin" / ("node.exe" if os.name == "nt" else "node")
    modules = runtime_root / "node" / "node_modules"
    node_executable = str(node) if node.exists() else shutil.which("node")
    node_modules = str(modules) if modules.exists() else os.environ.get("NODE_PATH")
    return node_executable, node_modules


def _browser_executable() -> str | None:
    explicit_browser = os.environ.get("E2E_VISUAL_BROWSER_EXECUTABLE")
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    if explicit_browser:
        candidates.insert(0, Path(explicit_browser))
    for candidate in candidates:
        if str(candidate) not in {"", "."} and candidate.exists():
            return str(candidate)
    return None


def _visual_env(temp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "E2E_VISUAL_DATABASE_URL": f"sqlite:///{(temp_path / 'e2e_visual.sqlite').as_posix()}",
            "E2E_VISUAL_UPLOAD_FOLDER": str(temp_path / "uploads"),
            "E2E_VISUAL_EXPORT_FOLDER": str(temp_path / "exports"),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _runner_env(
    env: dict[str, str],
    *,
    base_url: str,
    browser_executable: str,
    node_modules: str,
    viewport_name: str,
) -> dict[str, str]:
    runner_env = env.copy()
    runner_env.update(
        {
            "E2E_VISUAL_BASE_URL": base_url,
            "E2E_VISUAL_MAX_DIFF_PIXELS": "1000",
            "E2E_VISUAL_THRESHOLD": "0.1",
            "E2E_VISUAL_BROWSER_EXECUTABLE": browser_executable,
            "E2E_VISUAL_VIEWPORTS": viewport_name,
            "NODE_PATH": node_modules,
        }
    )
    return runner_env


def _stop_server(server: subprocess.Popen) -> None:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)
    if server.stdout:
        server.stdout.close()


class E2EVisualBaselineTests(unittest.TestCase):
    def test_browser_e2e_visual_baseline(self):
        node, node_modules = _bundled_node_paths()
        if not node or not node_modules:
            self.skipTest(
                "Browser e2e/visual runner requires Node.js and Playwright modules. "
                "Use the bundled runtime or set NODE_PATH to a Playwright installation."
            )

        browser_executable = _browser_executable()
        if not browser_executable:
            self.skipTest(
                "Browser e2e/visual runner requires a Chromium executable. "
                "Install Playwright browsers or set E2E_VISUAL_BROWSER_EXECUTABLE."
            )

        with tempfile.TemporaryDirectory(prefix="peredacha-e2e-visual-", ignore_cleanup_errors=True) as temp_dir:
            temp_path = Path(temp_dir)
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"
            env = _visual_env(temp_path)

            for viewport_name in ("desktop", "tablet", "mobile"):
                server = subprocess.Popen(
                    [sys.executable, str(SERVER), "--port", str(port)],
                    cwd=str(ROOT),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    self._wait_for_server(base_url, server)
                    runner_env = _runner_env(
                        env,
                        base_url=base_url,
                        browser_executable=browser_executable,
                        node_modules=node_modules,
                        viewport_name=viewport_name,
                    )
                    result = subprocess.run(
                        [node, str(RUNNER)],
                        cwd=str(ROOT),
                        env=runner_env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=120,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout)
                finally:
                    _stop_server(server)

    def _wait_for_server(self, base_url: str, server: subprocess.Popen) -> None:
        deadline = time.monotonic() + 30
        last_output = ""
        while time.monotonic() < deadline:
            if server.poll() is not None:
                if server.stdout:
                    last_output += server.stdout.read() or ""
                self.fail(f"E2E visual server exited early with code {server.returncode}:\n{last_output}")
            try:
                with urlopen(f"{base_url}/login", timeout=1) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.25)
        if server.stdout:
            last_output += server.stdout.read() or ""
        self.fail(f"E2E visual server did not become ready:\n{last_output}")


if __name__ == "__main__":
    unittest.main()
