from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from agent.settings import load_settings
from mock_company.seed import seed


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    mock_db = tmp_path / "mock_company.sqlite3"
    operator_db = tmp_path / "operator.sqlite3"
    workspace = tmp_path / "workspace"
    logs = tmp_path / "logs"
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("DATABASE_PATH", str(operator_db))
    monkeypatch.setenv("MOCK_DATABASE_PATH", str(mock_db))
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("LOGS_PATH", str(logs))
    monkeypatch.setenv("MAX_RETRIES", "2")
    monkeypatch.setenv("MAX_STEPS", "80")
    monkeypatch.setenv("REFUND_APPROVAL_THRESHOLD", "10000")
    seed(mock_db, reset=True)
    settings = load_settings()
    return {"settings": settings, "tmp": tmp_path}


@pytest.fixture
def mock_server(tmp_env):
    port = _free_port()
    tmp_env["settings"]
    import os

    os.environ["MOCK_COMPANY_URL"] = f"http://127.0.0.1:{port}"
    from mock_company.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            response = httpx.get(f"{url}/health", timeout=0.5)
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        raise RuntimeError("mock company server failed to start")
    yield url
    server.should_exit = True
    thread.join(timeout=2)


@pytest.fixture
def operator(tmp_env, mock_server, monkeypatch):
    monkeypatch.setenv("MOCK_COMPANY_URL", mock_server)
    from agent.orchestrator import Orchestrator
    from agent.state import TaskStore

    settings = load_settings()
    orch = Orchestrator(settings=settings, store=TaskStore(settings.database_path))
    return orch
