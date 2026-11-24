from __future__ import annotations

import base64
import json
import math
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
    writes_sort_key,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from sqlalchemy.orm import Session as DBSession

from app.agents import repositories
from app.agents.models import (
    AgentCheckpoint,
    AgentTenantMismatchError,
    UnsafeAgentPayloadError,
    thread_id_for,
)
from app.agents.schemas import validate_safe_payload

SessionFactory = Callable[[], DBSession]


class _JsonOnlySerializer:
    """Serde estricto: solo JSON; rechaza ORM, clientes LLM y tipos arbitrarios."""

    def dumps_typed(self, obj: object) -> tuple[str, bytes]:
        return "json", json.dumps(
            self._to_json(obj), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")

    def loads_typed(self, data: tuple[str, bytes]) -> object:
        type_name, raw = data
        if type_name != "json":
            raise UnsafeAgentPayloadError("Formato de checkpoint no permitido")
        return json.loads(raw.decode("utf-8"))

    def _to_json(self, value: object) -> object:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise UnsafeAgentPayloadError("Float no finito en checkpoint")
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "value"):
            enum_value = cast(Any, value).value
            if isinstance(enum_value, (str, int, float)):
                return enum_value
        if isinstance(value, Mapping):
            return {
                str(key): self._to_json(item)
                for key, item in validate_safe_payload(
                    {str(key): item for key, item in value.items()}
                ).items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [self._to_json(item) for item in value]
        raise UnsafeAgentPayloadError("Valor no serializable como JSON en checkpoint")


def _parse_thread(thread_id: object) -> tuple[uuid.UUID, uuid.UUID]:
    raw = str(thread_id)
    if not raw.startswith("org:"):
        raise AgentTenantMismatchError("Thread de checkpoint mal formado")
    org_part, _, remainder = raw[4:].partition(":run:")
    if not org_part or not remainder:
        raise AgentTenantMismatchError("Thread de checkpoint mal formado")
    try:
        organization_id = uuid.UUID(org_part)
        agent_run_id = uuid.UUID(remainder)
    except (ValueError, AttributeError) as exc:
        raise AgentTenantMismatchError("Thread de checkpoint mal formado") from exc
    if thread_id_for(organization_id, agent_run_id) != raw:
        raise AgentTenantMismatchError("Thread de checkpoint no coincide con su organización")
    return organization_id, agent_run_id


class SQLAgentCheckpointSaver(BaseCheckpointSaver[str]):
    """Checkpointer LangGraph real respaldado por `AgentCheckpoint` (tenant-scoped)."""

    def __init__(
        self, session_factory: SessionFactory, *, serde: SerializerProtocol | None = None
    ) -> None:
        super().__init__(serde=serde or _JsonOnlySerializer())
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[DBSession]:
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _require_run(
        self, db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
    ) -> None:
        run = repositories.get_agent_run(db, organization_id, agent_run_id)
        if run is None:
            raise AgentTenantMismatchError("Ejecución no disponible para la organización")

    def _scope(self, config: RunnableConfig) -> tuple[uuid.UUID, uuid.UUID, str, str, str | None]:
        configurable = config.get("configurable")
        if not isinstance(configurable, Mapping):
            raise AgentTenantMismatchError("Config de checkpoint sin contexto de organización")
        try:
            organization_id = uuid.UUID(str(configurable.get("organization_id")))
        except ValueError as exc:
            raise AgentTenantMismatchError("Config sin organization_id válido") from exc
        thread_id = str(configurable.get("thread_id"))
        parsed_org, agent_run_id = _parse_thread(thread_id)
        if parsed_org != organization_id:
            raise AgentTenantMismatchError("Organization_id no coincide con el thread_id")
        run_claim = configurable.get("agent_run_id")
        if run_claim is not None:
            try:
                claimed_run = uuid.UUID(str(run_claim))
            except ValueError as exc:
                raise AgentTenantMismatchError("Config sin agent_run_id válido") from exc
            if claimed_run != agent_run_id:
                raise AgentTenantMismatchError("Agent_run_id no coincide con el thread_id")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        checkpoint_id = configurable.get("checkpoint_id")
        return (
            organization_id,
            agent_run_id,
            thread_id,
            checkpoint_ns,
            None if checkpoint_id is None else str(checkpoint_id),
        )

    def _encode(self, value: object) -> list[object]:
        type_name, raw = self.serde.dumps_typed(value)
        return [type_name, base64.b64encode(raw).decode("ascii")]

    def _decode(self, encoded: object) -> object:
        if not isinstance(encoded, (list, tuple)) or len(encoded) != 2:
            raise UnsafeAgentPayloadError("Blob de checkpoint mal formado")
        type_name, raw_text = encoded
        if type_name != "json" or not isinstance(raw_text, str):
            raise UnsafeAgentPayloadError("Tipo de blob no permitido en checkpoint")
        return self.serde.loads_typed((type_name, base64.b64decode(raw_text.encode("ascii"))))

    def _dump_checkpoint(self, checkpoint: Checkpoint) -> dict[str, object]:
        return validate_safe_payload(
            {
                "v": checkpoint["v"],
                "id": checkpoint["id"],
                "ts": checkpoint["ts"],
                "channel_values": {
                    str(key): self._encode(value)
                    for key, value in checkpoint["channel_values"].items()
                },
                "channel_versions": dict(checkpoint["channel_versions"]),
                "versions_seen": dict(checkpoint["versions_seen"]),
                "updated_channels": checkpoint.get("updated_channels"),
            }
        )

    def _load_checkpoint(self, raw: object) -> Checkpoint:
        if not isinstance(raw, Mapping):
            raise UnsafeAgentPayloadError("Checkpoint persistido mal formado")
        channel_values = raw.get("channel_values")
        if not isinstance(channel_values, Mapping):
            raise UnsafeAgentPayloadError("Channel values mal formados")
        return Checkpoint(
            v=int(raw["v"]),
            id=str(raw["id"]),
            ts=str(raw["ts"]),
            channel_values={str(k): self._decode(v) for k, v in channel_values.items()},
            channel_versions=dict(cast(ChannelVersions, raw["channel_versions"])),
            versions_seen=dict(cast(dict[str, ChannelVersions], raw["versions_seen"])),
            updated_channels=cast(list[str] | None, raw.get("updated_channels")),
        )

    def _dump_writes(
        self, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str
    ) -> list[dict[str, object]]:
        encoded: list[dict[str, object]] = []
        for idx, (channel, value) in enumerate(writes):
            encoded.append(
                {
                    "task_path": task_path,
                    "task_id": task_id,
                    "idx": idx,
                    "channel": str(channel),
                    "value": self._encode(value),
                }
            )
        return encoded

    def _load_writes(self, raw: object) -> list[PendingWrite]:
        if not isinstance(raw, list):
            return []
        entries = [item for item in raw if isinstance(item, Mapping)]
        entries.sort(
            key=lambda item: writes_sort_key(
                str(item.get("task_path", "")),
                str(item.get("task_id", "")),
                int(cast(int, item.get("idx", 0))),
            )
        )
        return [
            (str(item["task_id"]), str(item["channel"]), self._decode(item["value"]))
            for item in entries
        ]

    def _config_for(
        self, scope: tuple[uuid.UUID, uuid.UUID, str, str, str | None], checkpoint_id: str
    ) -> RunnableConfig:
        organization_id, agent_run_id, thread_id, checkpoint_ns, _ = scope
        configurable: dict[str, object] = {
            "organization_id": str(organization_id),
            "agent_run_id": str(agent_run_id),
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
        }
        return cast(RunnableConfig, {"configurable": configurable})

    def _tuple_from_row(
        self, row: AgentCheckpoint, scope: tuple[uuid.UUID, uuid.UUID, str, str, str | None]
    ) -> CheckpointTuple:
        payload = row.payload
        if not payload.get("has_checkpoint"):
            raise UnsafeAgentPayloadError("Checkpoint sin estado persistido")
        checkpoint = self._load_checkpoint(payload["checkpoint"])
        parent = payload.get("parent_config")
        pending = self._load_writes(payload.get("pending_writes", []))
        return CheckpointTuple(
            config=self._config_for(scope, checkpoint["id"]),
            checkpoint=checkpoint,
            metadata=cast(
                CheckpointMetadata,
                dict(cast(Mapping[str, object], payload.get("metadata") or {})),
            ),
            parent_config=cast(RunnableConfig | None, parent),
            pending_writes=pending,
        )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        scope = self._scope(config)
        organization_id, agent_run_id, thread_id, checkpoint_ns, _ = scope
        checkpoint_id = str(checkpoint["id"])
        with self._session() as db:
            self._require_run(db, organization_id, agent_run_id)
            existing = repositories.get_checkpoint(
                db, organization_id, thread_id, checkpoint_ns, checkpoint_id
            )
            writes = (
                existing.payload.get("pending_writes", []) if existing is not None else []
            )
            payload = validate_safe_payload(
                {
                    "has_checkpoint": True,
                    "checkpoint": self._dump_checkpoint(checkpoint),
                    "metadata": dict(metadata),
                    "new_versions": dict(cast(Mapping[str, object], new_versions)),
                    "parent_config": {
                        "configurable": dict(
                            cast(Mapping[str, object], config.get("configurable") or {})
                        )
                    },
                    "pending_writes": writes,
                }
            )
            repositories.upsert_checkpoint(
                db,
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                payload=payload,
            )
        return self._config_for(scope, checkpoint_id)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        scope = self._scope(config)
        organization_id, agent_run_id, thread_id, checkpoint_ns, checkpoint_id = scope
        if checkpoint_id is None:
            raise AgentTenantMismatchError("put_writes exige checkpoint_id")
        with self._session() as db:
            self._require_run(db, organization_id, agent_run_id)
            existing = repositories.get_checkpoint(
                db, organization_id, thread_id, checkpoint_ns, checkpoint_id
            )
            previous = existing.payload.get("pending_writes", []) if existing is not None else []
            if not isinstance(previous, list):
                raise UnsafeAgentPayloadError("Writes persistidos mal formados")
            payload = validate_safe_payload(
                {
                    "has_checkpoint": bool(
                        existing is not None and existing.payload.get("has_checkpoint")
                    ),
                    "checkpoint": (
                        existing.payload.get("checkpoint") if existing is not None else None
                    ),
                    "metadata": existing.payload.get("metadata") if existing is not None else {},
                    "new_versions": (
                        existing.payload.get("new_versions") if existing is not None else {}
                    ),
                    "parent_config": (
                        existing.payload.get("parent_config") if existing is not None else None
                    ),
                    "pending_writes": [*previous, *self._dump_writes(writes, task_id, task_path)],
                }
            )
            repositories.upsert_checkpoint(
                db,
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                payload=payload,
            )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        scope = self._scope(config)
        organization_id, _, thread_id, checkpoint_ns, checkpoint_id = scope
        with self._session() as db:
            self._require_run(db, organization_id, _parse_thread(thread_id)[1])
            if checkpoint_id is None:
                rows = repositories.list_checkpoints(db, organization_id, thread_id, checkpoint_ns)
                rows_with_state = [row for row in rows if row.payload.get("has_checkpoint")]
                row = rows_with_state[-1] if rows_with_state else None
            else:
                row = repositories.get_checkpoint(
                    db, organization_id, thread_id, checkpoint_ns, checkpoint_id
                )
                if row is not None and not row.payload.get("has_checkpoint"):
                    row = None
            if row is None:
                return None
            return self._tuple_from_row(row, scope)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if config is None:
            raise AgentTenantMismatchError("List exige contexto de organización")
        scope = self._scope(config)
        organization_id, _, thread_id, checkpoint_ns, _ = scope
        before_id = None
        if before is not None:
            before_id = self._scope(before)[4]
        with self._session() as db:
            self._require_run(db, organization_id, _parse_thread(thread_id)[1])
            rows = repositories.list_checkpoints(db, organization_id, thread_id, checkpoint_ns)
            yielded = 0
            for row in rows:
                if limit is not None and yielded >= limit:
                    break
                if not row.payload.get("has_checkpoint"):
                    continue
                if before_id is not None and row.checkpoint_id >= before_id:
                    continue
                metadata = row.payload.get("metadata") or {}
                if isinstance(metadata, Mapping) and filter and any(
                    metadata.get(key) != value for key, value in filter.items()
                ):
                    continue
                yield self._tuple_from_row(row, scope)
                yielded += 1

    def delete_thread(self, thread_id: str) -> None:
        organization_id, agent_run_id = _parse_thread(thread_id)
        with self._session() as db:
            self._require_run(db, organization_id, agent_run_id)
            repositories.delete_checkpoints_for_thread(db, organization_id, thread_id)
