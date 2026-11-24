"""Políticas deterministas de selección para preguntas de entrevista.

Las reglas viven aquí, en código: la salida del modelo, el CV y cualquier texto
del documento son datos no confiables y no pueden cambiar tools, permisos ni
políticas. Una pregunta rechazada fuerza revisión humana y se persiste fuera de
la lista publicable de la guía. Sin score, inferencias ni decisión automática.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from app.interviews.schemas import InterviewQuestionDraft

POLICY_VERSION = "selection-policy-v1"

_TermGroup = tuple[str, tuple[str, ...]]
_PROTECTED_TERMS: tuple[_TermGroup, ...] = (
    (
        "protected_age",
        (
            "edad",
            "age",
            "birthdate",
            "birth date",
            "date of birth",
            "cumpleanos",
            "how old",
            "years old",
            "born in",
            "mayor de edad",
            "menor de edad",
        ),
    ),
    (
        "protected_health",
        (
            "salud",
            "health",
            "discapacidad",
            "disability",
            "disabled",
            "enfermedad",
            "illness",
            "disease",
            "medical",
            "medico",
            "hospital",
            "salud mental",
            "mental health",
        ),
    ),
    (
        "protected_religion",
        (
            "religion",
            "religioso",
            "religious",
            "credo",
            "creed",
            "iglesia",
            "church",
        ),
    ),
    (
        "protected_orientation",
        (
            "orientacion sexual",
            "sexual orientation",
            "gay",
            "lesbiana",
            "lesbian",
            "homosexual",
            "transgenero",
            "transgender",
            "genero",
            "gender",
        ),
    ),
    (
        "protected_ethnicity",
        (
            "etnia",
            "ethnicity",
            "raza",
            "race",
            "origen etnico",
            "ethnic origin",
            "nacionalidad",
            "nationality",
            "pais de origen",
            "country of origin",
            "acento",
            "accent",
        ),
    ),
    (
        "protected_family",
        (
            "embarazo",
            "pregnancy",
            "pregnant",
            "maternidad",
            "maternity",
            "paternidad",
            "paternity",
            "hijos",
            "children",
            "childcare",
            "familia",
            "family",
            "estado civil",
            "marital status",
            "casado",
            "married",
            "divorciado",
            "divorced",
        ),
    ),
    (
        "protected_economic",
        (
            "situacion economica",
            "economic status",
            "socioeconomic",
            "socioeconomico",
            "salario actual",
            "current salary",
            "ingresos",
            "income",
            "deudas",
            "debt",
        ),
    ),
    (
        "protected_ideology",
        (
            "ideologia",
            "ideology",
            "afiliacion politica",
            "political affiliation",
            "partido politico",
            "political party",
        ),
    ),
    (
        "sensitive_proxy",
        (
            "personalidad",
            "personality",
            "compatibilidad cultural",
            "cultural fit",
            "inteligencia",
            "intelligence",
            "compromiso",
            "commitment",
            "emociones",
            "emotions",
        ),
    ),
)


class PolicyDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class QuestionPolicyResult:
    decision: PolicyDecision
    reason_code: str | None = None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


def _compile(term: str) -> re.Pattern[str]:
    """Coincidencia con límites de palabra: `age` no empareja `management`."""
    return re.compile(rf"(?<!\w){re.escape(_normalize(term))}(?!\w)")


_COMPILED_TERMS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = tuple(
    (code, tuple(_compile(term) for term in terms)) for code, terms in _PROTECTED_TERMS
)


def matching_reason_code(text: str) -> str | None:
    """Devuelve el primer código de regla vulnerable; nunca interpreta instrucciones."""
    normalized = _normalize(text)
    for code, patterns in _COMPILED_TERMS:
        if any(pattern.search(normalized) for pattern in patterns):
            return code
    return None


def evaluate_question(
    draft: InterviewQuestionDraft, allowed_requirement_ids: Collection[uuid.UUID]
) -> QuestionPolicyResult:
    """Acepta solo preguntas ligadas a requisitos vigentes y sin términos sensibles."""
    if draft.requirement_id not in allowed_requirement_ids:
        return QuestionPolicyResult(PolicyDecision.REJECTED, "irrelevant_requirement")
    text = " ".join(
        [draft.question, draft.evidence_focus, draft.competency, *draft.limitations]
    )
    reason_code = matching_reason_code(text)
    if reason_code is not None:
        return QuestionPolicyResult(PolicyDecision.REJECTED, reason_code)
    return QuestionPolicyResult(PolicyDecision.ACCEPTED)
