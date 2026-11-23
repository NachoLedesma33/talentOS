---
name: technical-documentation
description: Mantiene ADRs, README, contratos y documentación de TalentOS sincronizados con el código, con decisiones justificadas, rutas verificables y referencias oficiales del SDD 26.
---

# Documentación Técnica — TalentOS

## Objetivo

Que cualquier desarrollador o evaluador entienda qué decidió el proyecto, por qué, dónde está implementado y cómo validarlo. Documentar es parte de la tarea; la documentación desactualizada cuenta como deuda.

## Cuándo activarla

- Antes de implementar cambios de arquitectura, stack, contratos o comportamiento observable.
- Al crear módulos, endpoints, variables de entorno o migraciones nuevas.
- Al cerrar una tarea o fase según `docs/DEVELOPMENT_WORKFLOW.md`.
- Al corregir una contradicción entre SDD, roadmap, AGENTS.md, código y entorno.
- Al adoptar una skill externa o cambiar las skills del proyecto.

## Contexto TalentOS

- Fuentes de verdad: `TalentOS_SDD.md` y `TalentOS_ROADMAP.md`; `AGENTS.md` rige a todo agente de código. Si se contradicen, se detiene la parte afectada y se propone resolución.
- `TalentOS_ROADMAP.md` sección 3 exige `AGENTS.md`, skills, `docs/decisions/`, ADR-001 a ADR-009, `docs/DEVELOPMENT_WORKFLOW.md` y `docs/ENVIRONMENTS.md` en Fase 0.
- `TalentOS_SDD.md` sección 24 lista ADR-001 a ADR-009; cada ADR incluye contexto, decisión, alternativas, consecuencias y fecha.
- `TalentOS_SDD.md` sección 18.4 exige a las skills frontmatter válido y contenido accionable; 18.6 exige verificar skills externas y no copiar documentación de frameworks.
- La sección 26 del SDD es el índice de referencias oficiales; citar allí, no pegar tutoriales completos.
- `docs/DEVELOPMENT_WORKFLOW.md` define plantillas de tarea y cierre de fase, estados y política de evidencia; `docs/ENVIRONMENTS.md` registra versiones y configuración real.

## Procedimiento

1. Leer `AGENTS.md`, secciones afectadas del SDD y roadmap, `docs/DEVELOPMENT_WORKFLOW.md` y el ADR vigente en `docs/decisions/`.
2. Declarar supuestos y detectar contradicciones antes de escribir; si hay conflicto, documentarlo y proponer resolución en lugar de silenciarlo.
3. Si hay decisión arquitectónica, crear `docs/decisions/ADR-NNN-slug.md` con contexto, decisión, alternativas, consecuencias y fecha; numerar sin reutilizar IDs.
4. Si la decisión se revierte, marcar el ADR como reemplazado por el nuevo y enlazarlo; no borrar el historial.
5. Actualizar en el mismo cambio: README con pasos reproducibles, `docs/ENVIRONMENTS.md` si cambian entorno o variables, `docs/DEVELOPMENT_WORKFLOW.md` si cambia el flujo o los comandos, `AGENTS.md` si cambian reglas o stack.
6. Documentar contratos en `packages/contracts/` y esquemas Pydantic; indicar versión, productor, consumidor y cambios incompatibles.
7. Describir límites conocidos: mocks, modo demo, latencia no medida, proveedores no verificados y decisiones humanas requeridas.
8. Usar rutas relativas verificables y nombres reales de archivos, comandos y variables; no inventar endpoints, tablas ni flags.
9. Para skills, mantener `name` en `kebab-case` igual al directorio y `description` específica en español; cargar y releer el archivo tras editarlo.
10. Citar documentación oficial del stack desde la sección 26 del SDD, con versión cuando aplique; no copiar guías extensas de frameworks.
11. Registrar en el roadmap el estado y la evidencia real del cambio, con comandos ejecutados y resultado observado.

## Convenciones

- Un ADR = una decisión; título claro, fecha real y alternativas descartadas con motivo.
- Español técnico, frases cortas y términos exactos del código (`organization_id`, `correlation_id`, `request_id`).
- Rutas relativas al raíz del repo entre backticks; comandos copiables tal cual aparecen en `docs/DEVELOPMENT_WORKFLOW.md`.
- Contratos versionados; cambio incompatible = nueva versión y consumidores actualizados.
- Sin valores secretos, correos reales, CV reales ni tokens en ejemplos; usar datos sintéticos.
- Sin marcadores pendientes vacíos ni texto de relleno; si algo no está resuelto, explicar impacto y plan concreto.
- Documentación y código se actualizan en el mismo cambio, nunca “después”.

## Anti-patrones

- Escribir un ADR después de implementar para justificar una decisión ya tomada sin alternativas.
- Copiar documentación completa de FastAPI, Next.js o LangGraph dentro del repo.
- Cambiar un endpoint o variable y olvidar `.env.example`, `docs/ENVIRONMENTS.md` y tests.
- Usar rutas que no existen o comandos que no se ejecutaron.
- Documentar secretos “para que el equipo pueda probar” o pegarlos en issues.
- Marcar `DONE` apoyándose solo en que el archivo existe.
- Reescribir el SDD o el roadmap para que encajen con un cambio fuera de fase sin aprobación.
- Dejar skills con `description` genérica que no permita al agente elegirlas.

## Validación

- Releer cada archivo creado o editado; comprobar frontmatter YAML y que `name` coincide con el directorio en `.opencode/skills/<skill-id>/SKILL.md`.
- Verificar que toda ruta citada existe o está planificada explícitamente en el SDD/roadmap para la fase activa.
- Comprobar que comandos y variables documentados coinciden con `AGENTS.md` y `docs/DEVELOPMENT_WORKFLOW.md`.
- Si el cambio también tocó código, ejecutar los checks aplicables: `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`, `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`, `cd apps/web && npm test -- --run`, `npx playwright test`.
- Revisar el diff en busca de secretos, datos personales reales, placeholders y enlaces rotos.
- Adjuntar evidencia real al roadmap; en Fase 0, la relectura de archivos y el chequeo de rutas es la evidencia.

## Checklist

- [ ] Decisión registrada en `docs/decisions/` cuando aplica, con cinco secciones obligatorias.
- [ ] README, `AGENTS.md`, `docs/ENVIRONMENTS.md` y `docs/DEVELOPMENT_WORKFLOW.md` sincronizados.
- [ ] Contratos versionados con productor, consumidor y tests actualizados.
- [ ] Limitaciones y supuestos documentados.
- [ ] Sin secretos, PII ni placeholders.
- [ ] Referencias oficiales citadas desde SDD 26, sin copiar docs de frameworks.
- [ ] Skills con frontmatter válido y `name` igual al directorio.
- [ ] Evidencia de validación registrada en el roadmap.

## Referencias

- `TalentOS_SDD.md` secciones 18.4, 18.6, 24, 25 y 26; `TalentOS_ROADMAP.md` sección 3.
- `AGENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, `docs/ENVIRONMENTS.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: OpenCode Skills <https://opencode.ai/docs/skills/>, OpenCode Documentation <https://opencode.ai/docs/>, FastAPI <https://fastapi.tiangolo.com/>, LangGraph <https://docs.langchain.com/oss/python/langgraph/overview>.
