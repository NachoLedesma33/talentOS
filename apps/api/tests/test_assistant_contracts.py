from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    WORKSPACE_ASSISTANT_WORKFLOW,
    AssistantAction,
    AssistantActionAck,
    AssistantActionType,
    AssistantFormId,
    AssistantMessageRequest,
    AssistantMessageResponse,
    AssistantNode,
    AssistantSurface,
    EvidenceRef,
)


def test_workspace_assistant_contract_is_closed() -> None:
    contract = WORKSPACE_ASSISTANT_WORKFLOW

    assert contract.workflow == "workspace_assistant"
    assert contract.version == "1.0.0"
    assert tuple(node.name for node in contract.nodes) == (
        AssistantNode.RECEIVE_REQUEST,
        AssistantNode.RESOLVE_CONTEXT,
        AssistantNode.RETRIEVE_ALLOWED_FACTS,
        AssistantNode.DRAFT_RESPONSE,
        AssistantNode.VALIDATE_POLICY,
        AssistantNode.PROPOSE_ACTIONS,
        AssistantNode.FINALIZE,
    )
    assert "get_platform_capabilities" in contract.allowed_tools
    assert "shell" not in contract.allowed_tools
    assert contract.interrupt_before_effects is AssistantNode.PROPOSE_ACTIONS
    assert contract.approval_action_type == "assistant_external_effect"
    assert contract.node(AssistantNode.DRAFT_RESPONSE).timeout_seconds == 8.0


def test_message_request_is_strict_and_tenant_free() -> None:
    payload = {
        "message": "Resume la vacante actual",
        "surface": "jobs",
        "idempotency_key": "assistant-msg-001",
    }

    request = AssistantMessageRequest.model_validate(payload)

    assert request.surface is AssistantSurface.JOBS
    assert request.recent_messages == []
    with pytest.raises(ValidationError):
        AssistantMessageRequest.model_validate(
            {**payload, "organization_id": str(uuid.uuid4())}
        )


def test_message_request_limits_history() -> None:
    payload = {
        "message": "Resume la vacante actual",
        "surface": "jobs",
        "idempotency_key": "assistant-msg-002",
    }
    too_many = [{"role": "user", "content": "x"} for _ in range(9)]
    too_long = [
        {"role": "user", "content": "x" * 1500},
        {"role": "assistant", "content": "y" * 1500},
        {"role": "user", "content": "z" * 1500},
    ]

    with pytest.raises(ValidationError):
        AssistantMessageRequest.model_validate({**payload, "recent_messages": too_many})
    with pytest.raises(ValidationError):
        AssistantMessageRequest.model_validate({**payload, "recent_messages": too_long})


def test_evidence_ref_requires_tenant_and_source() -> None:
    org_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        EvidenceRef.model_validate({"quote": "texto sintético", "organization_id": org_id})
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(
            {"quote": "texto sintético", "document_id": str(uuid.uuid4())}
        )

    evidence = EvidenceRef.model_validate(
        {
            "quote": "texto sintético",
            "organization_id": org_id,
            "document_id": str(uuid.uuid4()),
            "page": 1,
        }
    )

    assert evidence.organization_id == org_id
    assert evidence.page == 1


def test_fill_form_action_blocks_untracked_and_sensitive_fields() -> None:
    action_id = uuid.uuid4()
    payload = {
        "action_id": action_id,
        "type": "fill_form",
        "form_id": "job.create",
        "patch": {"title": "Analista de selección · demo"},
        "field_origins": {"title": "user_request"},
    }

    action = AssistantAction.model_validate(payload)

    assert action.action_id == action_id
    assert action.form_id is AssistantFormId.JOB_CREATE
    with pytest.raises(ValidationError):
        AssistantAction.model_validate({**payload, "field_origins": {}})
    with pytest.raises(ValidationError):
        AssistantAction.model_validate(
            {
                **payload,
                "patch": {"email": "synthetic@example.test"},
                "field_origins": {"email": "user_request"},
            }
        )
    with pytest.raises(ValidationError):
        AssistantAction.model_validate({**payload, "requires_confirmation": False})


def test_navigate_requires_internal_route() -> None:
    payload = {
        "action_id": uuid.uuid4(),
        "type": "navigate",
        "route": "/automations",
    }

    action = AssistantAction.model_validate(payload)

    assert action.type is AssistantActionType.NAVIGATE
    assert action.route == "/automations"
    with pytest.raises(ValidationError):
        AssistantAction.model_validate(
            {**payload, "route": "https://externo.example/automations"}
        )


def test_response_and_ack_are_strict() -> None:
    ack = AssistantActionAck.model_validate(
        {
            "action_id": uuid.uuid4(),
            "decision": "applied",
            "idempotency_key": "assistant-ack-001",
        }
    )

    assert ack.decision == "applied"
    with pytest.raises(ValidationError):
        AssistantActionAck.model_validate(
            {
                "action_id": uuid.uuid4(),
                "decision": "ignored",
                "idempotency_key": "assistant-ack-002",
            }
        )

    response_payload = {
        "run_id": uuid.uuid4(),
        "answer": "Vacante en borrador; faltan requisitos.",
        "status": "completed",
    }
    response = AssistantMessageResponse.model_validate(response_payload)

    assert response.status == "completed"
    with pytest.raises(ValidationError):
        AssistantMessageResponse.model_validate({**response_payload, "debug": True})
