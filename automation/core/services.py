"""Start, probe and stop the license server and the website server."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

from config import (
    LOG_DIR,
    SERVER_DIR,
    SERVER_PORT,
    SERVER_URL,
    WEBSITE_DIR,
    WEBSITE_PORT,
    WEBSITE_URL,
)


def port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _npm_env() -> dict:
    """
    Node is installed per-machine; a shell started before the installer ran
    won't have it on PATH, so the machine PATH is re-read here.
    """
    env = os.environ.copy()
    node_dir = r"C:\Program Files\nodejs"
    if os.path.isdir(node_dir) and node_dir.lower() not in env.get("PATH", "").lower():
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
    return env


class ManagedService:
    """A background process this suite owns and must clean up."""

    def __init__(self, name: str, args: list[str], cwd: Path, port: int,
                 health_url: str, logger=None, env: dict | None = None):
        self.name = name
        self.args = args
        self.cwd = Path(cwd)
        self.port = port
        self.health_url = health_url
        self.log = logger
        self.env = env
        self.process: subprocess.Popen | None = None
        self.log_path = LOG_DIR / f"{name}.out.log"
        self.adopted = False          # already running when we arrived

    def _say(self, message: str) -> None:
        if self.log:
            self.log.info(message)
        else:
            print(f"    {message}")

    def start(self, wait_seconds: float = 30.0) -> bool:
        if port_is_open(self.port):
            self.adopted = True
            self._say(f"{self.name}: port {self.port} already serving — reusing it")
            return self.wait_healthy(wait_seconds=8.0)

        self._say(f"{self.name}: starting {' '.join(self.args)}")
        handle = open(self.log_path, "a", encoding="utf-8")
        handle.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        handle.flush()

        self.process = subprocess.Popen(
            self.args,
            cwd=str(self.cwd),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=self.env or os.environ.copy(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return self.wait_healthy(wait_seconds)

    def wait_healthy(self, wait_seconds: float = 30.0) -> bool:
        deadline = time.time() + wait_seconds
        last = ""
        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                tail = self.tail_log(12)
                raise RuntimeError(
                    f"{self.name} exited with code {self.process.returncode}:\n{tail}")
            try:
                response = requests.get(self.health_url, timeout=2.5)
                if response.status_code < 500:
                    self._say(f"{self.name}: healthy at {self.health_url}")
                    return True
                last = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last = str(exc)[:90]
            time.sleep(0.5)

        self._say(f"{self.name}: not healthy within {wait_seconds}s ({last})")
        return False

    def tail_log(self, lines: int = 25) -> str:
        try:
            content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-lines:])
        except OSError:
            return "(no log)"

    def stop(self) -> None:
        if self.adopted or self.process is None:
            return
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self._say(f"{self.name}: stopped")
        except Exception as exc:                   # noqa: BLE001
            self._say(f"{self.name}: stop failed: {exc}")
        finally:
            self.process = None


def license_server(logger=None) -> ManagedService:
    node = r"C:\Program Files\nodejs\node.exe"
    args = [node if Path(node).exists() else "node", "server.js"]
    return ManagedService(
        name="license-server",
        args=args,
        cwd=SERVER_DIR,
        port=SERVER_PORT,
        health_url=f"{SERVER_URL}/health",
        logger=logger,
        env=_npm_env(),
    )


def website_server(logger=None) -> ManagedService:
    # Python's http.server avoids a network fetch for `npx serve` and starts faster.
    args = [sys.executable, "-m", "http.server", str(WEBSITE_PORT), "--bind", "127.0.0.1"]
    return ManagedService(
        name="website-server",
        args=args,
        cwd=WEBSITE_DIR,
        port=WEBSITE_PORT,
        health_url=f"{WEBSITE_URL}/index.html",
        logger=logger,
    )


class ServiceGroup:
    """Context manager that starts both services and always tears them down."""

    def __init__(self, logger=None):
        self.log = logger
        self.server = license_server(logger)
        self.website = website_server(logger)

    def start_all(self) -> tuple[bool, bool]:
        return self.server.start(), self.website.start()

    def stop_all(self) -> None:
        self.website.stop()
        self.server.stop()

    def __enter__(self):
        self.start_all()
        return self

    def __exit__(self, *_exc):
        self.stop_all()
        return False


def server_health() -> dict:
    try:
        return requests.get(f"{SERVER_URL}/health", timeout=4).json()
    except (requests.RequestException, ValueError) as exc:
        return {"error": str(exc)}
