from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import email_validator
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session as DBSession

import app.agents.assistant as assistant
import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.models import AgentRun, AgentTenantMismatchError
from app.api.routes import agents as agents_routes
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_URL = "/api/v1/agents/assistant/messages"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME


class _Provider:
    """Proveedor determinista; sin red y con salida validada por el grafo."""

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema, context
        return {
            "answer": "Synthetic verified answer",
            "citations": [],
            "actions": [],
            "limitations": [],
            "needs_review": False,
        }

    def generate_text(self, prompt_version: str, context: Mapping[str, object]) -> str:
        del prompt_version, context
        return ""

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> dict[str, int]:
        del prompt_version, context
        return {}


class _SyncExecutor:
    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        del wait, cancel_futures
        return None


@contextmanager
def _sync_executor(_config: Any) -> Iterator[_SyncExecutor]:
    yield _SyncExecutor()


class _VisibilityCheckedMemorySaver(MemorySaver):
    """Falla igual que el checkpointer SQL si el run aún no es visible."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self._engine = engine

    def get_tuple(self, config: Any) -> Any:
        configurable = config.get("configurable") or {}
        organization_id = uuid.UUID(str(configurable.get("organization_id")))
        thread_id = str(configurable.get("thread_id"))
        agent_run_id = uuid.UUID(thread_id.rsplit(":run:", 1)[1])
        with DBSession(self._engine, expire_on_commit=False) as db:
            run = db.get(AgentRun, agent_run_id)
            if run is None or run.organization_id != organization_id:
                raise AgentTenantMismatchError(
                    "Ejecución no disponible para la organización"
                )
        return super().get_tuple(config)


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture(autouse=True)
def _sync_langgraph_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "langgraph.pregel._executor.get_executor_for_config", _sync_executor
    )


@pytest.fixture
def engines(tmp_path: Path) -> Iterator[tuple[Engine, Engine]]:
    """Dos conexiones reales: sin dirty reads entre request y checkpointer."""
    url = f"sqlite:///{tmp_path / 'assistant-visibility.sqlite3'}"
    writer = create_engine(url, connect_args={"check_same_thread": False})
    reader = create_engine(url, connect_args={"check_same_thread": False})
    for engine in (writer, reader):

        @event.listens_for(engine, "connect")
        def _foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(writer)
    yield writer, reader
    writer.dispose()
    reader.dispose()


@pytest.fixture
def client(engines: tuple[Engine, Engine]) -> Iterator[TestClient]:
    writer_engine, _ = engines

    def override_get_db() -> Iterator[DBSession]:
        with DBSession(writer_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_message_run_is_visible_to_checkpointer_connection(
    client: TestClient,
    engines: tuple[Engine, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, reader_engine = engines
    monkeypatch.setattr(agents_routes, "get_llm_provider", lambda: _Provider())
    monkeypatch.setattr(
        assistant,
        "_retrieve_allowed_facts",
        lambda _state, _deps: {"tool_facts": {}, "evidence": []},
    )
    monkeypatch.setattr(
        agents_routes,
        "_assistant_checkpointer",
        lambda: _VisibilityCheckedMemorySaver(reader_engine),
    )

    email = "assistant-visibility@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": "Synthetic Owner"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert _COOKIE in client.cookies

    response = client.post(
        _ORGS_URL, json={"name": "Assistant Visibility Org", "slug": "assistant-visibility"}
    )
    assert response.status_code == 201, response.text
    organization_id = str(response.json()["id"])
    response = client.get(
        "/api/v1/auth/me", headers={"X-Organization-ID": organization_id}
    )
    assert response.status_code == 200, response.text

    response = client.post(
        _URL,
        json={
            "schema_version": "1.0",
            "message": "¿Qué evidencia confirma el perfil?",
            "surface": "dashboard",
            "resource_ref": None,
            "recent_messages": [],
            "idempotency_key": "assistant-visibility-key",
        },
        headers={"X-Organization-ID": organization_id},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["answer"] == "Synthetic verified answer"
