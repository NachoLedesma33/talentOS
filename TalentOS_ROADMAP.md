# TalentOS — Implementation Roadmap
## Plan maestro por fases, entregables y criterios de aceptación

**Versión:** 1.0  
**Estado:** Plan de ejecución  
**Documento relacionado:** `TalentOS_SDD.md`  
**Objetivo:** convertir la especificación de TalentOS en una secuencia de entregas pequeñas, verificables y demostrables.

---

# 1. Cómo utilizar este roadmap

Este documento organiza el desarrollo. No reemplaza el SDD: el SDD define qué es el producto y sus restricciones; este roadmap define en qué orden construirlo y cómo comprobar que cada etapa está terminada.

## 1.1 Reglas de ejecución

1. Ejecutar una fase por vez.
2. No iniciar una fase si sus dependencias no están satisfechas.
3. Dividir cada fase en tareas pequeñas y verticales.
4. Antes de implementar una tarea, revisar el SDD, las skills aplicables y el estado real del repositorio.
5. Antes de cerrar una tarea, ejecutar las pruebas y checks relevantes.
6. No marcar tareas como completadas sin evidencia de validación.
7. Actualizar este roadmap al finalizar cada tarea o fase.
8. Registrar cambios arquitectónicos en ADRs.
9. Mantener la rama principal funcional.
10. No implementar funcionalidades futuras “por adelantado” salvo que una dependencia técnica lo justifique.

## 1.2 Estados de seguimiento

Usar exclusivamente estos estados:

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `IN_REVIEW`
- `DONE`
- `DEFERRED`

Una tarea `DONE` debe tener evidencia: test, comando ejecutado, captura, endpoint verificado o comportamiento reproducible.

## 1.3 Política de alcance

- **MVP:** lo necesario para demostrar el flujo principal de reclutamiento asistido.
- **Portfolio differentiators:** funciones que hacen destacar la implementación técnica.
- **Post-MVP:** mejoras que no deben bloquear una demo funcional.

No confundir “completo” con “grande”. Cada fase debe producir un incremento funcional y estable.

---

# 2. Vista ejecutiva

| Fase | Nombre | Resultado principal | Prioridad |
|---|---|---|---|
| 0 | Descubrimiento y baseline | Repositorio y plan técnico validados | P0 |
| 1 | Fundación del monorepo | Web, API, PostgreSQL, Redis y CI levantan localmente | P0 |
| 2 | Identidad y multi-tenancy | Usuarios, organizaciones, membresías y permisos | P0 |
| 3 | Recruitment Core | Vacantes, requisitos, candidatos y postulaciones | P0 |
| 4 | Document Intelligence | Upload seguro y extracción estructurada de CV | P0 |
| 5 | Evidence-Based Matching | Evaluación explicable y revisión humana | P0 |
| 6 | Agent Runtime | Workflows LangGraph, tools limitadas y trazabilidad | P0 |
| 7 | Interview Assistant | Preguntas de entrevista basadas en requisitos | P1 |
| 8 | Automation Engine | Triggers, condiciones, acciones y aprobaciones | P0 |
| 9 | Integrations & Webhooks | Adaptadores externos y webhooks seguros | P1 |
| 10 | Agent Control Center | Observabilidad de ejecuciones y operaciones | P0 |
| 11 | Simulation & AI Evaluation | Dataset sintético y evaluación repetible | P1 |
| 12 | Analytics | Indicadores operativos de reclutamiento | P1 |
| 13 | UX hardening & accessibility | Experiencia consistente, responsive y accesible | P0 |
| 14 | Security & privacy hardening | Revisión integral de amenazas y datos personales | P0 |
| 15 | Deployment & portfolio release | Demo desplegada y presentación técnica | P0 |

**Orden recomendado:** las fases 7, 9 y 12 pueden avanzar después del núcleo, pero no deben retrasar la finalización de los flujos críticos de las fases 3 a 6, 8 y 10.

---

# 3. Fase 0 — Descubrimiento y baseline

**Objetivo:** comprender el entorno y cerrar decisiones técnicas antes de generar estructura o código.

## Tareas

- [x] Inspeccionar el repositorio y detectar si ya existe código.
- [x] Inspeccionar versiones de Python, Node.js, npm, Git y Docker.
- [x] Confirmar compatibilidad de dependencias.
- [x] Revisar el SDD completo.
- [x] Crear `AGENTS.md` con reglas generales de desarrollo.
- [x] Definir las skills iniciales del proyecto.
- [x] Definir agentes de desarrollo y sus límites.
- [x] Crear carpeta `docs/decisions/`.
- [x] Redactar ADRs iniciales.
- [x] Definir convenciones de nombres, imports, errores y testing.
- [x] Definir estrategia de configuración y secretos.
- [x] Definir alcance exacto de la Fase 1.

## Entregables

- `AGENTS.md`
- Skills esenciales en `.opencode/skills/`
- Agentes de desarrollo en `.opencode/agents/` si la configuración elegida lo requiere
- ADR-001 a ADR-009, ajustados a las decisiones reales
- `docs/DEVELOPMENT_WORKFLOW.md`
- `docs/ENVIRONMENTS.md`

## Criterios de aceptación

- [ ] El entorno y sus versiones están documentados.
- [ ] Las decisiones tienen justificación y alternativas.
- [ ] Las skills tienen frontmatter válido y contenido accionable.
- [ ] El coding agent entiende el flujo de trabajo.
- [ ] No se agregaron dependencias innecesarias.
- [ ] No se implementaron funcionalidades de negocio.

---

# 4. Fase 1 — Fundación del monorepo

**Objetivo:** crear una base ejecutable, reproducible y verificable.

## Tareas

### Repositorio y estructura
- [x] Crear estructura monorepo según el SDD.
- [x] Configurar `.gitignore`.
- [x] Configurar `.editorconfig`.
- [x] Configurar archivos de formato y lint.
- [x] Crear README con instrucciones iniciales.
- [x] Crear `.env.example` sin secretos.

### Backend
- [x] Crear aplicación FastAPI.
- [x] Configurar settings tipados.
- [x] Agregar endpoint `/health`.
- [x] Agregar endpoint `/ready` con chequeos de dependencias cuando corresponda.
- [x] Configurar manejo centralizado de errores.
- [x] Configurar logs estructurados y request ID.
- [x] Configurar Ruff y type checking.

### Persistencia e infraestructura local
- [x] Crear Docker Compose.
- [x] Levantar PostgreSQL.
- [x] Configurar SQLAlchemy.
- [x] Configurar Alembic.
- [x] Levantar Redis.
- [x] Verificar conectividad entre servicios.
- [x] Crear comando documentado para iniciar y detener el entorno.

### Frontend
- [x] Crear aplicación Next.js con TypeScript.
- [x] Configurar lint y typecheck.
- [x] Crear layout base.
- [x] Crear página inicial y pantalla de error.
- [x] Definir tokens iniciales del design system.

### Calidad y CI
- [x] Configurar GitHub Actions.
- [x] Ejecutar lint, typecheck y tests en CI.
- [x] Agregar tests smoke para API.
- [x] Verificar build de frontend y backend.

## Entregables

- Monorepo ejecutable.
- Docker Compose funcional.
- API y web accesibles localmente.
- PostgreSQL y Redis conectados.
- Migración inicial.
- CI verde.

## Criterios de aceptación

- [ ] Un clon limpio puede levantarse siguiendo el README.
- [ ] `/health` responde correctamente.
- [ ] `/ready` detecta dependencias no disponibles.
- [ ] Una migración se aplica y se revierte en entorno de prueba.
- [ ] Web y API compilan.
- [ ] CI se ejecuta en un pull request.
- [ ] No hay secretos versionados.

---

# 5. Fase 2 — Identidad y multi-tenancy

**Objetivo:** establecer autenticación, organizaciones y aislamiento de datos.

## Tareas

- [x] Modelar `User`, `Organization` y `Membership`.
- [x] Crear migraciones.
- [x] Implementar registro.
- [x] Implementar login y logout.
- [x] Elegir y documentar estrategia de sesión/token.
- [x] Implementar hash seguro de contraseñas.
- [x] Implementar usuario actual (`/me`).
- [x] Implementar creación de organización.
- [x] Implementar selección de organización activa.
- [x] Implementar roles `owner`, `admin`, `recruiter`, `reviewer`, `viewer`.
- [x] Crear dependencias de autorización en FastAPI.
- [x] Aplicar scoping de organización en servicios y repositorios.
- [x] Crear interfaz de login y registro.
- [x] Crear selector de organización.
- [x] Crear gestión básica de miembros.
- [x] Registrar eventos relevantes en auditoría.

## Pruebas obligatorias

- [x] Usuario no autenticado no accede a endpoints privados.
- [x] Un usuario no puede leer recursos de otra organización.
- [x] Un usuario no puede modificar `organization_id` para escalar acceso.
- [x] Los roles tienen permisos diferenciados.
- [ ] Las tareas asíncronas preservan el contexto de organización. (N/A en Fase 2: no existen workers; verificar en Fase 4 al crearlos.)
- [x] Las sesiones inválidas o expiradas se rechazan.

## Criterio de salida

Dos organizaciones con usuarios y datos distintos pueden utilizar la aplicación simultáneamente sin filtración de recursos.

---

# 6. Fase 3 — Recruitment Core

**Objetivo:** disponer de la gestión central de vacantes, candidatos y procesos, todavía sin depender de IA.

## 6.1 Vacantes

- [x] Modelar `Job`, `JobRequirement` y `JobVersion`.
- [x] Crear migraciones, constraints e índices.
- [x] Implementar CRUD de vacantes.
- [x] Implementar estados: draft, open, paused, closed, archived.
- [x] Implementar requisitos obligatorios y deseables.
- [x] Implementar tipos de requisitos.
- [x] Implementar versionado de requisitos.
- [x] Crear formularios frontend.
- [x] Crear listado, filtros y detalle de vacante.

## 6.2 Candidatos

- [x] Modelar `Candidate`.
- [x] Implementar alta, edición y consulta.
- [x] Implementar búsqueda y paginación.
- [x] Implementar notas internas con permisos.
- [x] Implementar historial de actividad.
- [x] Crear perfil de candidato.

## 6.3 Postulaciones y pipeline

- [x] Modelar `Application`.
- [x] Definir etapas configuradas por el sistema.
- [x] Implementar transiciones válidas.
- [x] Implementar asociación candidato-vacante.
- [x] Evitar duplicados de postulación según regla de negocio.
- [x] Implementar vista de pipeline.
- [x] Registrar cada cambio de etapa.

## Criterios de aceptación

- [x] Crear una vacante con requisitos.
- [x] Crear un candidato.
- [x] Asociarlo a la vacante.
- [x] Moverlo por etapas permitidas.
- [x] Consultar el historial.
- [x] Verificar aislamiento por organización.
- [x] Completar tests de reglas de dominio y API.

**Hito demostrable:** gestión básica de un proceso de selección sin IA.

---

# 7. Fase 4 — Document Intelligence

**Objetivo:** recibir currículums de forma segura, extraer texto y producir información estructurada revisable.

## Tareas

### Recepción y almacenamiento
- [x] Definir formatos permitidos: PDF y DOCX.
- [x] Definir límite de tamaño y cantidad de páginas.
- [x] Validar extensión, MIME y firma del archivo.
- [x] Generar nombre interno no predecible.
- [x] Almacenar en bucket privado o storage local de desarrollo.
- [x] Calcular checksum.
- [x] Crear metadatos y estado del documento.
- [x] Implementar acceso mediante autorización y URLs temporales si aplica.

### Extracción de texto
- [x] Implementar extractor PDF.
- [x] Implementar extractor DOCX.
- [x] Detectar documentos vacíos, corruptos o no compatibles.
- [x] Preservar páginas y offsets cuando sea posible.
- [x] Definir límites de memoria y tiempo.
- [x] Ejecutar extracción en background.

### Interpretación con IA
- [x] Crear interfaz `LLMProvider`.
- [x] Implementar proveedor mock determinista.
- [x] Implementar adaptador de proveedor real configurable.
- [x] Definir schema Pydantic de extracción.
- [x] Crear prompt versionado.
- [x] Extraer experiencia, formación, skills, proyectos e idiomas.
- [x] Asociar cada dato con evidencia fuente.
- [x] Marcar campos faltantes.
- [x] Validar respuesta estructurada.
- [x] Enviar resultados dudosos a revisión.

### Interfaz
- [x] Crear componente de carga.
- [x] Mostrar progreso del procesamiento.
- [x] Mostrar error y opción de reintento.
- [x] Mostrar datos extraídos.
- [x] Permitir corregir y confirmar.
- [x] Registrar quién confirmó los datos.

## Pruebas obligatorias

- [x] PDF válido.
- [x] DOCX válido.
- [x] Archivo vacío.
- [x] Archivo corrupto.
- [x] Extensión falsa.
- [x] Archivo excesivo.
- [x] Timeout del proveedor.
- [x] JSON inválido.
- [x] Datos faltantes.
- [x] Documento con instrucciones maliciosas.
- [x] Acceso a documento de otra organización.

## Criterio de salida

Un usuario carga un CV sintético, el worker lo procesa, la IA produce información estructurada con referencias al documento y el usuario puede revisarla y confirmarla.

---

# 8. Fase 5 — Evidence-Based Matching

**Objetivo:** comparar candidatos con vacantes mediante criterios transparentes y evidencias verificables.

## Tareas

- [x] Definir schema de evaluación por requisito.
- [x] Definir estados `supported`, `partial`, `not_found`, `needs_review`.
- [x] Obtener versión inmutable de requisitos de la vacante.
- [x] Obtener perfil y documentos confirmados del candidato.
- [x] Crear contexto mínimo para el modelo.
- [x] Implementar evaluación criterio por criterio.
- [x] Asociar citas o referencias a fragmentos fuente.
- [x] Verificar que las referencias existan.
- [x] Detectar contradicciones y evidencia insuficiente.
- [x] Generar resumen de fortalezas y brechas.
- [x] Generar preguntas para información faltante.
- [x] Crear pantalla de evaluación.
- [x] Implementar revisión humana.
- [x] Guardar versión del modelo, prompt y evaluación.
- [x] Permitir comparar evaluaciones de versiones distintas.

## Reglas

- No usar atributos protegidos ni proxies.
- No inferir personalidad, inteligencia o compromiso.
- No presentar una puntuación agregada como verdad objetiva.
- No descartar candidatos automáticamente.
- No inventar evidencia.
- Separar hechos, inferencias y datos no encontrados.

## Pruebas obligatorias

- [x] Requisito claramente respaldado.
- [x] Evidencia parcial.
- [x] Requisito no encontrado.
- [x] Documento contradictorio.
- [x] Referencia de evidencia inexistente.
- [x] Requisito modificado después de una evaluación.
- [x] Revisión humana que corrige un resultado.
- [x] Evaluación repetible con mock.

## Criterio de salida

Cada requisito de una vacante tiene un resultado explicable, una referencia verificable o una marca explícita de información insuficiente.

**Hito demostrable:** análisis de un candidato contra una vacante, con evidencias visibles.

---

# 9. Fase 6 — Agent Runtime

**Objetivo:** implementar workflows de IA con estado, herramientas limitadas, checkpoints y trazabilidad.

## Tareas

### Fundamentos
- [x] Definir contrato común de workflow.
- [x] Definir estados de ejecución.
- [x] Definir schema de eventos.
- [x] Integrar LangGraph en el módulo de agentes.
- [x] Implementar persistencia/checkpointing.
- [x] Ejecutar workflows desde workers.
- [x] Implementar cancelación y timeout.
- [x] Implementar límites de reintentos.
- [x] Propagar correlation ID.

### Herramientas
- [x] Crear registry de tools.
- [x] Definir permisos por tool.
- [x] Implementar tools de lectura de vacantes y candidatos.
- [x] Implementar tool de creación de borradores.
- [x] Implementar tool de solicitud de aprobación.
- [x] Validar inputs con Pydantic.
- [x] Registrar invocaciones.
- [x] Aplicar idempotencia en tools de escritura.

### Agentes
Implementar de manera incremental, no todos a la vez:

- [x] Job Analyst.
- [x] CV Analyst.
- [x] Matching Analyst.
- [x] Quality Auditor.
- [x] Recruitment Orchestrator.

Los agentes de entrevistas y automatización pueden utilizarse desde fases específicas posteriores.

### Human-in-the-loop
- [x] Definir puntos de interrupción.
- [x] Persistir el estado antes de esperar aprobación.
- [x] Exponer aprobación/rechazo mediante API.
- [x] Reanudar workflow tras decisión.
- [x] Registrar actor, fecha y decisión.

## Pruebas obligatorias

- [x] Salida válida.
- [x] Salida malformada.
- [x] Tool no autorizada.
- [x] Organización incorrecta.
- [x] Timeout.
- [x] Reintento.
- [x] Ejecución duplicada.
- [x] Pausa y reanudación.
- [x] Aprobación y rechazo.
- [x] Fallo de proveedor.
- [x] Prompt injection en documento.

## Criterio de salida

Un workflow completo puede iniciarse, inspeccionarse, pausarse para aprobación, reanudarse y finalizar sin perder su trazabilidad.

---

# 10. Fase 7 — Interview Assistant

**Objetivo:** transformar brechas y requisitos de la vacante en guías de entrevista útiles.

## Tareas

- [x] Definir entidades de entrevista y preguntas.
- [x] Crear preguntas asociadas a requisitos.
- [x] Generar preguntas técnicas y de profundización.
- [x] Explicar qué evidencia o competencia busca explorar cada pregunta.
- [x] Validar preguntas contra políticas de selección.
- [x] Permitir editar, ordenar y eliminar preguntas.
- [x] Crear guía de entrevista.
- [x] Registrar feedback humano estructurado.
- [x] Vincular feedback con requisitos, sin convertirlo en una decisión automática.

## Criterios de aceptación

- [x] Crear guía desde una vacante.
- [x] Generar preguntas vinculadas a requisitos concretos.
- [x] Editar y guardar guía.
- [x] Registrar feedback.
- [x] Ver historial de cambios.
- [x] Evitar preguntas discriminatorias o irrelevantes mediante reglas y revisión.

---

# 11. Fase 8 — Automation Engine

**Objetivo:** automatizar procesos repetitivos mediante eventos, condiciones, acciones y aprobaciones.

## MVP: motor estructurado

- [x] Definir schema de automatización.
- [x] Implementar triggers por eventos de dominio.
- [x] Implementar condiciones deterministas.
- [x] Implementar acciones permitidas.
- [x] Definir límites y validaciones de cada acción.
- [x] Implementar modo dry-run.
- [x] Crear ejecución persistida.
- [x] Crear historial y detalle de ejecución.
- [x] Implementar aprobación humana.
- [x] Implementar reintentos e idempotencia.
- [x] Prevenir ciclos infinitos.
- [x] Implementar activar/desactivar.
- [x] Versionar configuraciones.

## Acciones iniciales

- [x] Crear tarea interna.
- [x] Crear borrador de correo.
- [x] Solicitar aprobación.
- [x] Registrar nota.
- [x] Proponer cambio de etapa.
- [x] Ejecutar análisis autorizado.

No habilitar envío de correos ni cambios sensibles sin aprobación en el MVP.

## Ejemplo end-to-end

1. Una postulación cambia a etapa `interview`.
2. Se publica evento de dominio.
3. El motor encuentra automatizaciones activas.
4. Evalúa condiciones.
5. Genera borrador de correo.
6. Crea aprobación pendiente.
7. Recruiter revisa y aprueba.
8. El adaptador ejecuta o simula el envío.
9. Se registra resultado y auditoría.

## Criterio de salida

Una automatización completa puede probarse sin efectos externos, aprobarse y ejecutarse de forma idempotente.

---

# 12. Fase 9 — Integrations & Webhooks

**Objetivo:** conectar TalentOS con servicios externos mediante adaptadores seguros y sustituibles.

## Tareas

- [x] Definir interfaz de integración.
- [x] Definir ciclo de vida de credenciales.
- [x] Cifrar configuración sensible.
- [x] Implementar proveedor de correo en sandbox.
- [x] Implementar envío real solo después de aprobación.
- [x] Implementar webhooks entrantes.
- [x] Validar firma y timestamp cuando aplique.
- [x] Implementar protección anti-replay.
- [x] Deduplicar eventos.
- [x] Implementar webhooks salientes firmados.
- [x] Implementar reintentos y registro de entrega.
- [x] Añadir pantalla de estado de integraciones.
- [x] Documentar límites y permisos de cada proveedor.

## Criterios de aceptación

- [x] Credenciales nunca aparecen en logs ni respuestas API.
- [x] Webhook inválido se rechaza.
- [x] Evento duplicado no duplica la operación.
- [x] Fallo temporal se reintenta según política.
- [x] El usuario puede diagnosticar una integración fallida.

---

# 13. Fase 10 — Agent Control Center

**Objetivo:** hacer observable el comportamiento de los agentes y workflows.

## Tareas

- [ ] Crear listado de `AgentRun`.
- [ ] Crear detalle de ejecución.
- [ ] Mostrar estado y duración.
- [ ] Mostrar timeline de eventos.
- [ ] Mostrar nodos del workflow.
- [ ] Mostrar tools invocadas y resultado resumido.
- [ ] Mostrar errores y reintentos.
- [ ] Mostrar aprobaciones pendientes.
- [ ] Mostrar proveedor y modelo configurado.
- [ ] Mostrar tokens/costo solo si hay datos confiables.
- [ ] Añadir filtros.
- [x] Añadir correlación con vacante, candidato y organización.
- [x] Añadir política de retención de logs.

No exponer razonamiento interno privado del modelo. Mostrar pasos de workflow, decisiones operativas, entradas/salidas permitidas, herramientas y resultados.

## Criterio de salida

Un usuario autorizado puede explicar qué ocurrió en una ejecución, dónde falló, qué herramienta utilizó y cómo se resolvió.

---

# 14. Fase 11 — Simulation Lab & AI Evaluation

**Objetivo:** medir la calidad de extracción, matching y workflows antes de cambios relevantes.

## Dataset sintético

- [x] Crear perfiles ficticios variados.
- [x] Crear CVs PDF y DOCX sintéticos.
- [x] Incluir datos incompletos.
- [x] Incluir trayectorias ambiguas.
- [x] Incluir requisitos ausentes.
- [x] Incluir contradicciones.
- [x] Incluir prompt injection.
- [x] Versionar dataset y etiquetas esperadas.

## Evaluaciones

- [x] Medir exactitud de extracción por campo.
- [x] Medir fidelidad de evidencias.
- [x] Medir validez de esquemas.
- [x] Medir consistencia de matching.
- [x] Medir robustez ante entradas adversariales.
- [x] Medir latencia.
- [x] Medir consumo/costo cuando sea posible.
- [x] Comparar versiones de prompts y modelos.
- [x] Generar reporte de regresión.

## Simulación operativa

- [x] Crear escenario de contratación.
- [x] Ejecutar varios candidatos sintéticos.
- [x] Simular proveedor lento.
- [x] Simular proveedor caído.
- [x] Simular tool fallida.
- [x] Simular aprobación rechazada.
- [x] Simular reintento.
- [x] Separar por completo entorno y datos demo.

## Criterio de salida

Se puede ejecutar el mismo experimento nuevamente y comparar resultados con métricas y versiones identificables. Coste monetario no se reporta: `estimate_usage` es heurístico y no dato confiable del proveedor (RF-065).

---

# 15. Fase 12 — Analytics

**Objetivo:** convertir los eventos operativos en métricas útiles para el equipo de selección.

## Indicadores iniciales

- [x] Vacantes abiertas y cerradas.
- [x] Candidatos por etapa.
- [x] Conversión entre etapas.
- [x] Tiempo medio por etapa.
- [x] Tiempo total de proceso.
- [x] Evaluaciones pendientes de revisión.
- [x] Ejecuciones de agentes exitosas y fallidas.
- [x] Automatizaciones ejecutadas.
- [x] Tiempo estimado ahorrado, con metodología explícita.

## Criterios

- [x] Las métricas tienen definición documentada.
- [x] Los filtros respetan organización y permisos.
- [x] Los datos se calculan desde fuentes verificables.
- [x] Se distingue dato real de estimación.
- [x] Los gráficos tienen estados vacíos y accesibilidad.

## Implementación

`GET /api/v1/analytics/overview` devuelve `pipeline` y `operational` del tenant activo. El servicio calcula métricas desde tablas operativas, declara definiciones y marca `is_estimate`. Tiempo ahorrado = 5 minutos por automatización live completada: supuesto declarado, no medición ni coste monetario. UI en `/analytics` con consulta explícita, estados vacío/carga/error y tablas accesibles.

---

# 16. Fase 13 — UX hardening & accessibility

**Objetivo:** elevar la interfaz a un estándar B2B profesional y coherente.

## Tareas

- [x] Revisar navegación global.
- [x] Unificar tokens de diseño.
- [x] Unificar formularios, tablas y feedback con shadcn/ui (A6–A11; no hay modales en la UI actual).
- [x] Revisar responsive desktop/tablet/mobile.
- [x] Implementar navegación por teclado.
- [x] Revisar labels y nombres accesibles.
- [x] Revisar contraste.
- [x] Revisar focus states.
- [x] Revisar mensajes de error.
- [x] Revisar loading, empty, disabled y success states.
- [ ] Reducir renders innecesarios.
- [x] Revisar tablas con grandes volúmenes.
- [ ] Realizar pruebas de usabilidad con tareas concretas.

## Criterio de salida

Los flujos principales pueden completarse sin ayuda externa, en desktop y mobile, y los componentes críticos cumplen criterios de accesibilidad acordados.

**Evidencia Fase 13 (2026-11-25):** skip link con test de primera parada de tabulación; `nav` con nombre accesible; todas las tablas con `caption` y `overflow-x-auto`; estados de evidencia con etiqueta y marca; mensajes de error de login, registro y feedback con prefijo `Error:`; contraste de texto 15.65/7.56/6.91, acento 6.67 y bordes 3.67/3.36 (WCAG 1.4.11); tokens semánticos de foco; `tsc`, `lint`, `vitest` 18 files/105 tests, `build` y E2E OK (3 passed / 1 skipped); A6–A11 migran la UI a primitivas shadcn bajo ADR-016; CI `45737722649` y `45738753726` success.

**Pendiente / limitaciones:** command menu implementado en `CommandMenu.tsx` (`Ctrl/Cmd+K`, filtro, Escape); menú de usuario y organización activa en el shell sin implementar; recuperación de contraseña, invitaciones y estado de onboarding cerrados en backend con ADR-017 (`f4ea14e`, `a81218e`) y consumidos en frontend el 2026-11-26; `dev_token` solo en no producción, sin SMTP; renders revisados en `CandidatesPanel` y `IntegrationsPanel` (guards de `active` y cleanup presentes) sin evidencia de re-render medible; estados loading/empty/disabled/success auditados el 2026-11-26 (`docs/ui-ux-inventory.md:127`); pruebas de usabilidad con tareas concretas pendientes. Fase sigue `IN_PROGRESS` hasta cerrar estos puntos.

**Evidencia cierre frontend (2026-11-26):** `/forgot-password` y `/reset-password` consumen recuperación con `dev_token` demo; `/invite/[token]` muestra preview público, login/registro y aceptación autenticada; `/dashboard` decide por `onboarding.step` (crear organización, aceptar invitación, completo) y muestra checklist de primeros pasos con enlaces reales. Gates: `tsc`, `lint`, `vitest` 18 files/115 tests, `build` y E2E 7 passed / 1 skipped. Pendiente: adaptador SMTP para producción.

**Auditoría de estados (2026-11-26):** tabla por estado (loading/empty/disabled/success/error de ruta) con evidencia en `docs/ui-ux-inventory.md:127`; convenciones `aria-busy`, `role="status"`, `role="alert"` con prefijo `Error:`, textos vacíos explícitos y botones inhabilitados durante envío. No incluye medición de re-render ni pruebas de usabilidad: siguen pendientes.

---

# 17. Fase 14 — Security & privacy hardening

**Objetivo:** revisar la aplicación como un sistema que procesa datos personales y documentos sensibles.

## Revisión

- [ ] Threat model actualizado.
- [ ] Matriz de roles y permisos revisada.
- [ ] Tests cross-tenant completos.
- [ ] Revisión de autenticación y sesiones.
- [ ] Revisión de CORS y CSRF.
- [ ] Rate limiting.
- [ ] Revisión de upload y parsing.
- [ ] Revisión de storage y URLs firmadas.
- [ ] Revisión de secretos y cifrado.
- [ ] Revisión de prompt injection.
- [ ] Revisión de herramientas de agentes.
- [ ] Revisión de webhooks.
- [ ] Revisión de logs y datos personales.
- [ ] Política de retención y eliminación.
- [ ] Escaneo de dependencias.
- [ ] Backup y restauración probados.
- [ ] Checklist OWASP aplicable.
- [ ] Documentación de riesgos pendientes.

## Criterio de salida

No quedan vulnerabilidades críticas conocidas sin mitigación o aceptación explícita de riesgo. Los riesgos residuales están documentados.

---

# 18. Fase 15 — Deployment & portfolio release

**Objetivo:** convertir el proyecto en una demostración pública, reproducible y fácil de evaluar.

## Infraestructura

- [ ] Seleccionar hosting compatible con Next.js.
- [ ] Seleccionar hosting para API Python y worker.
- [ ] Seleccionar PostgreSQL gestionado o autoalojado.
- [ ] Seleccionar Redis si la cola lo requiere.
- [ ] Configurar storage privado.
- [ ] Configurar variables de entorno.
- [ ] Configurar dominio y HTTPS si están disponibles.
- [ ] Configurar health checks.
- [ ] Configurar backups.
- [ ] Configurar logs y alertas.
- [ ] Documentar costos y límites del free tier.
- [ ] Validar que la demo no dependa de servicios gratuitos ilimitados.

No asumir que Vercel puede alojar por sí solo todos los componentes de una API Python con workers persistentes. Elegir cada servicio según sus límites reales y documentar cualquier costo.

## Demo

- [ ] Crear organización demo.
- [ ] Crear usuarios demo con roles distintos.
- [ ] Crear vacantes ficticias.
- [ ] Crear candidatos sintéticos.
- [ ] Cargar CVs ficticios.
- [ ] Preparar escenario end-to-end.
- [ ] Implementar reset seguro de datos demo.
- [ ] Desactivar acciones externas reales en demo.
- [ ] Verificar que no haya secretos ni datos personales reales.

## Portfolio

- [ ] README profesional.
- [ ] Descripción del problema y propuesta de valor.
- [ ] Diagrama de arquitectura.
- [ ] Stack y justificación.
- [ ] Instrucciones de ejecución local.
- [ ] Capturas de pantalla.
- [ ] Video de 3–5 minutos.
- [ ] Ejemplo de workflow multiagente.
- [ ] Ejemplo de webhook/integración.
- [ ] Resultados de testing y AI evaluation.
- [ ] Decisiones y limitaciones conocidas.
- [ ] Enlaces a demo y repositorio.

## Criterio de salida

Una persona externa puede abrir la demo, completar el escenario principal y consultar el repositorio para entender cómo está construido el sistema.

---

# 19. Hitos de demostración

Estos hitos permiten mostrar progreso incluso antes de terminar el producto.

| Hito | Demo | Qué demuestra |
|---|---|---|
| H1 | Login y dos organizaciones aisladas | Backend, auth y multi-tenancy. |
| H2 | Crear vacante y candidato | Modelado de dominio y CRUD profesional. |
| H3 | Cargar CV y revisar extracción | Archivos, workers, IA y validación. |
| H4 | Matching con evidencias | Structured output, evaluación y criterio de producto. |
| H5 | Workflow pausado y reanudado | Agentes, estado y human-in-the-loop. |
| H6 | Automatización aprobada | Eventos, tools e idempotencia. |
| H7 | Webhook simulado | Integración y seguridad. |
| H8 | Agent Control Center | Observabilidad y debugging. |
| H9 | Simulation Lab | Evaluación sistemática de IA. |
| H10 | Demo pública completa | Producto integrado y capacidad de entrega. |

---

# 20. Orden recomendado para trabajar con agentes de código

Para cada tarea:

1. `planner`: descompone la tarea y define criterios.
2. `architect`: revisa límites y contratos cuando haya impacto estructural.
3. `backend` o `frontend`: implementa la unidad de trabajo.
4. `ai-engineer`: participa solo en funcionalidades de IA.
5. `qa`: agrega y ejecuta pruebas.
6. `security-reviewer`: revisa autenticación, datos, archivos, tools o integraciones.
7. `reviewer`: inspecciona el diff y verifica calidad.

No invocar todos los agentes en cada tarea. Seleccionar únicamente los roles que agreguen valor. Evitar que dos agentes modifiquen los mismos archivos simultáneamente.

---

# 21. Plantilla de tarea de implementación

Usar esta plantilla para convertir cada checkbox en una tarea concreta:

```markdown
# TASK-XXX — Nombre de la tarea

## Objetivo
Qué resultado observable se necesita.

## Contexto
Fase y requerimiento del SDD relacionado.

## Alcance
Qué incluye.

## Fuera de alcance
Qué no se debe implementar.

## Dependencias
Tareas, módulos o contratos requeridos.

## Diseño propuesto
Archivos, componentes, servicios y endpoints afectados.

## Criterios de aceptación
- [ ] Criterio observable 1.
- [ ] Criterio observable 2.

## Pruebas
- [ ] Unitarias.
- [ ] Integración.
- [ ] E2E si corresponde.
- [ ] Seguridad si corresponde.

## Validación
Comandos y resultado esperado.

## Riesgos
Riesgos técnicos o de producto.

## Resultado
Resumen de cambios, pruebas ejecutadas y pendientes.
```

---

# 22. Plantilla de cierre de fase

Al terminar cada fase, el agente debe entregar:

```markdown
# Cierre de fase — Fase X

## Estado
DONE / BLOCKED

## Entregables completados
Lista concreta.

## Criterios de aceptación
Checklist con evidencia.

## Pruebas ejecutadas
Comandos y resultados.

## Decisiones tomadas
ADRs nuevos o modificados.

## Deuda técnica
Pendientes conocidos y justificación.

## Riesgos
Riesgos abiertos.

## Cambios en documentación
Archivos actualizados.

## Próxima fase
Dependencias y primer conjunto de tareas.
```

No avanzar si existen fallos críticos, migraciones inconsistentes o criterios de aceptación sin verificar.

---

# 23. Registro de progreso

Actualizar esta tabla durante el desarrollo.

| Fase | Estado | Fecha de inicio | Fecha de cierre | Evidencia / notas |
|---|---|---|---|---|
| 0 — Descubrimiento | DONE | 2026-11-23 | 2026-11-23 | `AGENTS.md`, 9 ADRs en `docs/decisions/`, 15 skills en `.opencode/skills/`, `docs/DEVELOPMENT_WORKFLOW.md`, `docs/ENVIRONMENTS.md`; entorno medido; sin dependencias nuevas; sin código de negocio. |
| 1 — Fundación | DONE | 2026-11-23 | 2026-11-23 | Commits ce4f218, aacea0c, adf5ebd, 7ded81a; compose OK; postgres healthy y redis PONG; ruff/mypy OK; pytest 12 passed; npm typecheck/lint/test/build OK; alembic upgrade/downgrade OK en harness SQLite; CI run 45260245209 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45260245209). |
| 2 — Identidad | DONE | 2026-11-23 | 2026-11-23 | Commits 6100629, 173d976, f900157, 4ecc26e; 46 tests pytest (incluye cross-tenant, sesión expirada y matriz de roles); ruff/mypy OK; npm typecheck/lint/test/build OK; CI run 45268242607 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45268242607). Única excepción: contexto org en tareas asíncronas, N/A sin workers y diferido a Fase 4. |
| 3 — Recruitment Core | DONE | 2026-11-23 | 2026-11-23 | Commits 7199f96, efd89a4, e27aed7, 6b957d8, 7b1e740; dominio y API de jobs/candidates/applications; 119 tests pytest (cross-tenant, roles, transiciones, duplicados, auditoría); ruff/mypy OK; npm typecheck/lint/test/build OK; alembic upgrade/downgrade OK en harness SQLite; CI run 45283604138 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45283604138). Sin IA, sin entrevistas. |
| 4 — Document Intelligence | DONE | 2026-11-23 | 2026-11-23 | Commits eae1ca8, db7c737, fe9342b, a85d036, c7ce1a9, 58b8e33; upload PDF/DOCX validado y storage local privado; worker Celery tenant-aware (contexto de organización verificado en tarea); LLMProvider mock/remoto, cv_analyst v1 y evidencia verificada; revisión/corrección humana con auditoría; ADR-010; 191 tests pytest, ruff/mypy OK, npm typecheck/lint/test/build OK, alembic upgrade/downgrade OK en harness SQLite; CI run 45298709917 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45298709917). |
| 5 — Matching | DONE | 2026-11-23 | 2026-11-24 | Commits d72ab25, a60231f, 315985a, 4684a44, eea6895; Assessment y RequirementEvaluation tenant-scoped; matching_analyst v1 con versión inmutable, evidencia verificada, contradicciones y needs_review; API run/detalle/comparación/revisión humana; UI de evaluación; sin score ni descarte automático; fix de test flaky de firma base64; 228 tests pytest, ruff/mypy OK, npm typecheck/lint/test/build OK, alembic upgrade/downgrade OK en harness SQLite; CI run 45315963988 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45315963988). |
| 6 — Agent Runtime | DONE | 2026-11-24 | 2026-11-24 | Commits 8206317, 911b892, bee28ab, e4d825d, 19b96f4, aaff1e5; langgraph 1.2.24; `AgentRun`/`AgentEvent`/`Approval`/`AgentCheckpoint` tenant-scoped + migración `0010_agent_runtime.py`; registry de 6 tools con permisos, Pydantic, idempotencia y traza; workflow `matching_review` v1.0.0 con `interrupt()` real, checkpoint y reanudación vía Celery solo con aprobación persistida; API `/api/v1/agents` + UI de timeline; sin autoaprobación, score ni acciones externas; cierre incremental: `job_analyst` v1 (`ee6a67f`) con esquema estricto y revisión obligatoria, sin publicar `JobVersion`; `cv_analyst` como nodo `extract_cv_evidence` de `matching_review` v1.1.0 (`1e3284e`) reutilizando extracción confirmada, sin texto de CV ni nueva llamada LLM; `recruitment_orchestration` v1.0.0 (`930fe71`) con selección determinista, `interrupt()` real y delegación solo tras aprobación; 397 tests pytest, npm typecheck/lint/test 78/build OK, ruff/mypy OK; CI run 45444117810 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45444117810), CI cierre run 45504960133 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45504960133). |
| 7 — Interview Assistant | DONE | 2026-11-24 | 2026-11-24 | Commits 1ace088, 7a3cc89, 2ffcabb, ed78821; `InterviewGuide`/`InterviewGuideRevision`/`InterviewQuestion`/`InterviewFeedback` tenant-scoped + migración `0011`; `interview_assistant` v1 con prompt `interview-v1`, generación idempotente por requisito/brecha y políticas deterministas ES/EN anti-discriminación; CRUD API con publicación bloqueada si hay `review_required`, historial y feedback vinculado a requisito sin score ni decisión; UI de editor y feedback; ADR-011; sin calendario externo (RF-044 P2 fuera de alcance); 318 tests pytest, npm typecheck/lint/test 58/build OK, ruff/mypy OK; CI run 45463076157 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45463076157). Anotación no bloqueante: Node.js 20 deprecated forzado a 24 en actions. |
| 8 — Automation Engine | DONE | 2026-11-24 | 2026-11-24 | Commits 8cd672e, cd797a0, c4d7fe4, 4ec542d, d01fba7; ADR-012 + migración `0012`; `Automation`/`AutomationVersion`/`AutomationRun`/`AutomationRunEvent`/`AutomationApproval` tenant-scoped; motor determinista con trigger `application.stage_changed`, condiciones cerradas, seis acciones sin efectos externos, dry-run, idempotencia, reintento único con timeout y anti-ciclos; aprobación humana separada de agentes, sin envío de correos ni cambio de etapa sin decisión; API `/api/v1/automations` + worker Celery y UI de reglas/ejecuciones; RF-054 editor visual implementado en `baf478b` con toggle de nodos y mismo payload; tarea interna y borrador se registran como evidencia saneada en el run, sin adaptador de correo real (Fase 9); 397 tests pytest, npm typecheck/lint/test 78/build OK, ruff/mypy OK; CI run 45485260077 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45485260077), CI cierre run 45504960133 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45504960133). Known issue: `tests/test_matching_workflow.py` intermitente con SQLite StaticPool + hilos LangGraph/reloj parcheado; no reapareció en el cierre. |
| 9 — Integrations | DONE | 2026-11-24 | 2026-11-24 | Commits `a67d40f`, `045f0b2`, `c187d00`, `aec6a05`, `f205ac0`, `6301e7e`; ADR-013 y migraciones `0013`-`0016`; `Integration` tenant-scoped con Fernet, webhooks entrantes HMAC/anti-replay/dedupe, outbox saliente firmado con reintentos, correo sandbox con aprobación separada y envío explícito, UI `/integrations`; ruff/mypy OK, pytest 467 passed / 1 failed flaky conocido de LangGraph/SQLite (aislado 4/5 passed), npm typecheck/lint/test 86/build OK, alembic harness upgrade/check/downgrade OK; CI run 45531304759 success (https://github.com/NachoLedesma33/talentOS/actions/runs/45531304759). |
| 10 — Control Center | DONE | 2026-11-25 | 2026-11-25 | Commits `f3cd3d2` `520e795` `ef1c7b1` `1071b3f` `ae44f93` `7146839` `633da9b` `3294e2d` `0b03201` `83b2a6d` `c96a89e` `0e58183`; traza con `attempts`, listado filtrable, correlación vacante/candidato y retención automática de 30 días con purga tenant-scoped; ruff/mypy OK; pytest 472 passed; npm typecheck/lint/test 87/build OK; CI run `45652701849` success (https://github.com/NachoLedesma33/talentOS/actions/runs/45652701849). |
| 11 — Simulation Lab | DONE | 2026-11-25 | 2026-11-25 | Commits `977c7b0` `3f83d92` `b25f050` `e7f4558` `8fbb268` `46d07c9` `781d5b1`; dataset sintético v1.0.0 con PDF/DOCX y etiquetas verificadas; evaluadores de extracción y matching sobre proveedor mock; métricas de esquema, evidencia, injector/revisión, latencia y tokens; comparación de regresiones por prompt/proveedor; simulación de proveedor lento/caído, tool fallida, aprobación rechazada y reintento; sin coste monetario por `estimate_usage` heurístico (RF-065); ruff/mypy OK; pytest 492 passed. |
| 12 — Analytics | DONE | 2026-11-25 | 2026-11-25 | Commits `78ee0dd` `30e51c5` `75aaa2e` `381f9aa` `40fd5e3` `0d95499` `a9f7dbb` `12c8bd0`; servicio tenant-scoped con definiciones y estimación declarada; endpoint `/api/v1/analytics/overview` con autorización por membresía y tests cross-tenant; UI `/analytics` con estados vacío/carga/error y accesibilidad; ruff/mypy OK (124 archivos), pytest 500 passed, npm typecheck/lint OK, vitest 90 passed. Push `9e71f5a..12c8bd0`; CI run `45667294069` success para `12c8bd004b211e67d464492144e0e534c135507a` (https://github.com/NachoLedesma33/talentOS/actions/runs/45667294069). CI Fase 11 `45659663690` failure en `test_matching_workflow.py`; fix `40fd5e3` verificado en CI. |
| 13 — UX & Accessibility | IN_PROGRESS | 2026-11-25 | — | Commits locales `7f20ccb` `eecf39c` `c5c9c75` `bcb0d0b` `ffaaca4` `5e9b801` `bed67e1` `bf8ef48` `0745a29` `08d0c1a` `78f1278` `d860647` `cc51a61` `51524b5` `1e47f45` `6121fbc` `a1b8625`; skip link y landmark `nav`, test de primera parada de tabulación; errores de formularios con prefijo `Error:`; bordes con contraste 3.67:1 / 3.36:1; errores de login y registro con prefijo `Error:` y `aria-live` assertivo; todas las tablas con scroll horizontal y nombre accesible; estados de evidencia con etiqueta y marca; tokens semánticos de foco y contraste verificado; tsc/lint/vitest 105 passed/build/E2E OK; shadcn A6–A11 cerrado; push `09f23679fb55cd968fc5461842d4b52768d417da`, CI `45738753726` success. Entrega B cerrada con push `97bd342c67e3612da462212ceaeb565b35716efd`, CI `45742414595` success; command menu implementado en Entrega C. Faltan menú de usuario, organización activa en el shell, re-renders, auditoría de estados y usabilidad. |
| 14 — Security & Privacy | NOT_STARTED | — | — | — |
| 15 — Release | NOT_STARTED | — | — | — |

---

# 24. Prompt maestro para ejecutar este roadmap

Usar este prompt al comenzar una sesión de desarrollo con OpenCode:

```text
Vamos a desarrollar TalentOS siguiendo estos documentos:

- TalentOS_SDD.md: especificación funcional y técnica.
- TalentOS_ROADMAP.md: secuencia de implementación y criterios de aceptación.
- AGENTS.md: reglas generales del repositorio.
- .opencode/skills/: estándares especializados.

Primero inspeccioná el estado real del repositorio y determiná cuál es la primera tarea pendiente del roadmap.

No supongas que una tarea está completa porque exista un archivo o porque una implementación anterior lo afirme. Verificá código, pruebas y comportamiento.

Trabajá únicamente en la fase activa y en una unidad de trabajo pequeña. Antes de modificar archivos:
1. Explicá el objetivo.
2. Identificá dependencias.
3. Indicá archivos que cambiarán.
4. Definí criterios de aceptación y pruebas.
5. Señalá riesgos.

Después implementá, ejecutá los checks pertinentes, corregí errores y actualizá el roadmap con evidencia real.

No avances a otra fase por iniciativa propia. No desactives tests, lint, typecheck ni controles de seguridad para conseguir una validación artificial.

Al terminar, informá:
- qué se implementó;
- qué archivos cambiaron;
- qué pruebas se ejecutaron y sus resultados;
- qué queda pendiente;
- si la tarea puede marcarse DONE según sus criterios.

Si encontrás una contradicción entre documentos, código y entorno, detené la parte afectada, explicá el conflicto y proponé una resolución antes de continuar.
```

---

# 25. Definición de éxito del proyecto

TalentOS está listo para presentarse como portfolio cuando:

- El flujo principal funciona de punta a punta.
- La aplicación tiene autenticación y aislamiento multi-tenant.
- Los documentos se procesan de manera segura.
- La extracción y el matching producen resultados verificables.
- Los agentes utilizan herramientas acotadas y contratos validados.
- Los workflows pueden pausarse, reanudarse y auditarse.
- Las automatizaciones son idempotentes y requieren aprobación para acciones externas.
- Existe una demostración reproducible con datos sintéticos.
- La calidad se respalda con tests y evaluaciones.
- La arquitectura y las decisiones están documentadas.
- El despliegue tiene instrucciones y límites conocidos.
- El desarrollador puede explicar qué construyó, por qué y cómo verificó que funciona.

**Regla final:** priorizar una cadena vertical completa —vacante → candidato → CV → extracción → matching → revisión → automatización aprobada → auditoría— antes de ampliar el producto con funcionalidades secundarias.
