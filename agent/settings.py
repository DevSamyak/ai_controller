from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _path(name: str, default: str) -> Path:
    value = os.getenv(name, default).strip()
    path = Path(value)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_api_key: str
    llm_model: str
    mock_company_url: str
    operator_url: str
    max_retries: int
    max_steps: int
    refund_approval_threshold: int
    database_path: Path
    mock_database_path: Path
    workspace_path: Path
    logs_path: Path
    frontend_origin: str
    root: Path = ROOT

    @property
    def drafts_path(self) -> Path:
        return self.workspace_path / "drafts"

    @property
    def reports_path(self) -> Path:
        return self.workspace_path / "reports"

    def ensure_dirs(self) -> None:
        for path in (
            self.database_path.parent,
            self.mock_database_path.parent,
            self.drafts_path,
            self.reports_path,
            self.logs_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def require_live_llm(self) -> None:
        if not self.llm_api_key:
            raise RuntimeError(
                "No LLM API key configured. Set LLM_API_KEY (or GEMINI_API_KEY) in .env. "
                "Copy .env.example to .env and add your Gemini key. Deterministic tests "
                "and the mock company do not require a key."
            )
        if not self.llm_model:
            raise RuntimeError(
                "LLM_MODEL is empty. Set LLM_MODEL in .env to a Gemini model available "
                "to your key, for example gemini-2.0-flash or gemini-2.5-flash."
            )


def load_settings() -> Settings:
    _load_env()
    key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    settings = Settings(
        llm_provider=(os.getenv("LLM_PROVIDER") or "google").strip().lower(),
        llm_api_key=key.strip(),
        llm_model=(os.getenv("LLM_MODEL") or "").strip(),
        mock_company_url=(os.getenv("MOCK_COMPANY_URL") or "http://127.0.0.1:8001").rstrip("/"),
        operator_url=(os.getenv("OPERATOR_URL") or "http://127.0.0.1:8000").rstrip("/"),
        max_retries=_as_int("MAX_RETRIES", 2),
        max_steps=_as_int("MAX_STEPS", 40),
        refund_approval_threshold=_as_int("REFUND_APPROVAL_THRESHOLD", 10000),
        database_path=_path("DATABASE_PATH", "./data/operator.sqlite3"),
        mock_database_path=_path("MOCK_DATABASE_PATH", "./data/mock_company.sqlite3"),
        workspace_path=_path("WORKSPACE_PATH", "./workspace"),
        logs_path=_path("LOGS_PATH", "./logs/runs"),
        frontend_origin=(os.getenv("FRONTEND_ORIGIN") or "http://127.0.0.1:5173").rstrip("/"),
    )
    settings.ensure_dirs()
    return settings
