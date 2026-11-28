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
- [x] Reducir renders innecesarios.
- [x] Revisar tablas con grandes volúmenes.
- [x] Realizar pruebas de usabilidad con tareas concretas.

## Criterio de salida

Los flujos principales pueden completarse sin ayuda externa, en desktop y mobile, y los componentes críticos cumplen criterios de accesibilidad acordados.

**Evidencia Fase 13 (2026-11-25):** skip link con test de primera parada de tabulación; `nav` con nombre accesible; todas las tablas con `caption` y `overflow-x-auto`; estados de evidencia con etiqueta y marca; mensajes de error de login, registro y feedback con prefijo `Error:`; contraste de texto 15.65/7.56/6.91, acento 6.67 y bordes 3.67/3.36 (WCAG 1.4.11); tokens semánticos de foco; `tsc`, `lint`, `vitest` 18 files/105 tests, `build` y E2E OK (3 passed / 1 skipped); A6–A11 migran la UI a primitivas shadcn bajo ADR-016; CI `45737722649` y `45738753726` success.

**Pendiente / limitaciones:** command menu implementado en `CommandMenu.tsx` (`Ctrl/Cmd+K`, filtro, Escape); menú de usuario y organización activa en el shell implementados con carga diferida (`apps/web/src/components/WorkspaceShell.tsx:38`, `:56`); recuperación de contraseña, invitaciones y estado de onboarding cerrados en backend con ADR-017 (`f4ea14e`, `a81218e`) y consumidos en frontend el 2026-11-26; `dev_token` solo en no producción, sin SMTP; renders medidos en `CandidatesPanel` con `Profiler` (`apps/web/tests/candidates.test.tsx:91`): 5 commits por ciclo carga/búsqueda/paginación y 0 commits extra al resolver respuesta obsoleta; sin optimización adicional necesaria; estados loading/empty/disabled/success auditados el 2026-11-26 (`docs/ui-ux-inventory.md:127`); pruebas de usabilidad por tareas automatizadas en `apps/web/e2e/smoke.spec.ts:135` (`desktop` y `mobile`), sin participantes humanos. Fase cerrada el 2026-11-26 con CI `45871700981` success.

**Evidencia cierre frontend (2026-11-26):** `/forgot-password` y `/reset-password` consumen recuperación con `dev_token` demo; `/invite/[token]` muestra preview público, login/registro y aceptación autenticada; `/dashboard` decide por `onboarding.step` (crear organización, aceptar invitación, completo) y muestra checklist de primeros pasos con enlaces reales. Gates: `tsc`, `lint`, `vitest` 18 files/115 tests, `build` y E2E 7 passed / 1 skipped. Pendiente: adaptador SMTP para producción.

**Auditoría de estados (2026-11-26):** tabla por estado (loading/empty/disabled/success/error de ruta) con evidencia en `docs/ui-ux-inventory.md:127`; convenciones `aria-busy`, `role="status"`, `role="alert"` con prefijo `Error:`, textos vacíos explícitos y botones inhabilitados durante envío. Complementada con pruebas de usabilidad por tareas en `apps/web/e2e/smoke.spec.ts` (ver abajo).

**Medición de renders (2026-11-26):** `apps/web/tests/candidates.test.tsx:91` cuenta commits con `Profiler`: carga → escritura → búsqueda → paginación = 5 commits, sin renders duplicados; `apps/web/tests/candidates.test.tsx:139` resuelve una respuesta obsoleta después de cambiar la búsqueda y confirma 0 commits extra y ningún dato viejo en pantalla. Los guards `active` + cleanup ya existentes bastan; no se añadió memoización. Gates: `tsc`, `lint`, `vitest` 18 files/117 tests, `build` y E2E 7 passed / 1 skipped.

**Shell de workspace (2026-11-26):** menú de cuenta con `/api/v1/auth/me` y logout `POST /api/v1/auth/logout`; organización activa con `/api/v1/organizations` y sincronía de `talentos:active-org`. Carga diferida al abrir cada control: analítica y otras vistas no disparan fetch de sesión u organizaciones al montar. Evidencia en `docs/ui-ux-inventory.md:141` y `apps/web/tests/organizations.test.tsx:229`. Gates: `tsc`, `lint`, `vitest` 18 files/118 tests, `build` y E2E 7 passed / 1 skipped.

**Usabilidad por tareas (2026-11-26):** cuatro recorridos en `apps/web/e2e/smoke.spec.ts:135` — recuperación de contraseña con token demo, aceptación de invitación, cambio de organización activa y cierre de sesión — ejecutados en `desktop` y `mobile` con API mockeada y datos sintéticos. `--disable-web-security` queda limitado al runner de Playwright para el preflight CORS hacia otro origen; no afecta producción. Sin participantes humanos: evidencia de completion, no de comprensión cualitativa. Tabla en `docs/ui-ux-inventory.md:150`. Gates: `tsc`, `lint`, `vitest` 18 files/118 tests, `build` y E2E 15 passed / 1 skipped.

**Mejora estética para reclutador (2026-11-26):** cierre posterior a Fase 13, documentado en `docs/ui-ux-inventory.md:163`. Referencias: Ashby, Lever y Greenhouse; patrón adoptado de una promesa, CTA único, cifras concretas, flujo visible y lenguaje de confianza. Landing, shell con acceso superior, 404/500, dashboard y links sin subrayado rediseñados. API ya cubre `404` con envelope consistente (`apps/api/tests/test_health.py:119`); sin endpoints ni dependencias nuevas. Gates: `tsc`, `lint`, `vitest` 19 files/120 tests, `build`, E2E 17 passed / 1 skipped; commits `6ed5c27`, `bd9e321`, `c5b10d4`, `269cd0c`, `e8b9f35`, `cd2c2d0`, `e3c7267`, `24dd155`, `99ba817`; CI `45884767966`–`45893865031` success. Limitación: revisión cualitativa sin participantes humanos.

---

# 17. Fase 14 — Security & privacy hardening

**Objetivo:** revisar la aplicación como un sistema que procesa datos personales y documentos sensibles.

## Revisión

- [x] Threat model actualizado (`docs/security-review.md`).
- [x] Matriz de roles y permisos revisada (`identity/dependencies.py:1-12,104-118`).
- [x] Tests cross-tenant completos (`test_authorization.py` y `test_*_api.py`; 515 passed).
- [x] Revisión de autenticación y sesiones (bcrypt, token SHA-256, cookie `HttpOnly`/`SameSite`).
- [x] Revisión de CORS y CSRF (`app/main.py:38-44`, `identity/dependencies.py:133-149`).
- [x] Rate limiting revisado; global HTTP pendiente (`RM-01`).
- [x] Revisión de upload y parsing (`documents/validation.py:8-14,50-71`).
- [x] Revisión de storage y URLs firmadas (`documents/storage.py`, `documents/tokens.py`; `RM-02`).
- [x] Revisión de secretos y cifrado (ADR-013; TLS/reposo en despliegue, `RM-03`).
- [x] Revisión de prompt injection (`test_cv_analyst.py:337-352`, `test_documents_review.py:424-469`).
- [x] Revisión de herramientas de agentes (`agents/tools.py:145-152,504-554,622-673`).
- [x] Revisión de webhooks (`integrations/webhooks.py:130-142,202`).
- [x] Revisión de logs y datos personales (tests de redacción en API).
- [x] Política de retención y eliminación revisada; exportación/borrado de candidatos pendiente (`RM-04`).
- [x] Escaneo de dependencias (`npm audit` + `pip-audit` en CI).
- [x] Backup y restauración revisados; procedimiento pendiente (`RM-05`).
- [x] Checklist OWASP aplicable (ASVS V2/V3/V4/V5/V6/V8/V10/V12/V14).
- [x] Documentación de riesgos pendientes (`docs/security-review.md`).

## Criterio de salida

No quedan vulnerabilidades críticas conocidas sin mitigación o aceptación explícita de riesgo. Los riesgos residuales están documentados.

**Evidencia Fase 14 (2026-11-26):** revisión completa en `docs/security-review.md` con threat model, checklist y riesgos `RM-01`–`RM-05` aceptados para alcance demo/local. `npm audit --audit-level=high` = 0 vulnerabilidades. `pip-audit` corre en CI sobre venv aislada: 0 vulnerabilidades tras subir `cryptography` a `>=50,<51`. Gates locales: `ruff=0`, `mypy=0` (124 archivos), `pytest` 515 passed; CI `45880065546` success. Antes de producción: cerrar `RM-01`–`RM-05` o firmar nueva aceptación de riesgo.

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
| 13 — UX & Accessibility | DONE | 2026-11-25 | 2026-11-26 | Commits locales `7f20ccb` `eecf39c` `c5c9c75` `bcb0d0b` `ffaaca4` `5e9b801` `bed67e1` `bf8ef48` `0745a29` `08d0c1a` `78f1278` `d860647` `cc51a61` `51524b5` `1e47f45` `6121fbc` `a1b8625`; skip link y landmark `nav`, test de primera parada de tabulación; errores de formularios con prefijo `Error:`; bordes con contraste 3.67:1 / 3.36:1; errores de login y registro con prefijo `Error:` y `aria-live` assertivo; todas las tablas con scroll horizontal y nombre accesible; estados de evidencia con etiqueta y marca; tokens semánticos de foco y contraste verificado; tsc/lint/vitest 105 passed/build/E2E OK; shadcn A6–A11 cerrado; push `09f23679fb55cd968fc5461842d4b52768d417da`, CI `45738753726` success. Entrega B cerrada con push `97bd342c67e3612da462212ceaeb565b35716efd`, CI `45742414595` success; command menu implementado en Entrega C. Menú de usuario, organización activa, re-renders, auditoría de estados y usabilidad por tareas (`apps/web/e2e/smoke.spec.ts:135`) cerrados; push `cfaa950f7fc5842d961af1448575bd7e67975b6c`, CI `45871700981` success (compose/backend/frontend). |
| 14 — Security & Privacy | DONE | 2026-11-26 | 2026-11-26 | Commits `6be89f4`, `21277e3`, `567f3d2`. Revisión en `docs/security-review.md`: threat model, 18 ítems y riesgos `RM-01`–`RM-05` aceptados para demo/local. `npm audit` y `pip-audit` en CI con venv aislada; `cryptography>=50,<51`. Gates: `ruff=0`, `mypy=0`, `pytest` 515 passed, `npm audit=0`. CI runs `45875729010`, `45880065546`, `45881352978` success. Antes de producción: cerrar riesgos residuales o firmar nueva aceptación. |
| 15 — Release | NOT_STARTED | — | — | — |
| 16 — Hardening, demo e i18n | IN_PROGRESS | 2026-11-26 | — | Backlog en §26; lotes ≤2 archivos con gates y CI verde por lote. |

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

---

# 26. Fase 16 — Hardening, demo e i18n (2026-11-26)

**Estado:** `IN_PROGRESS`. **Origen:** petición del usuario 2026-11-26. **Dependencia:** Fases 0–15; Fase 15 sigue `NOT_STARTED` salvo los ítems que esta fase cierra explícitamente.

## 26.1 Reglas del loop

1. Cada lote toca **≤2 archivos**; si un cambio necesita más, se divide.
2. Antes de editar: leer archivos, comprobar estado real y elegir el lote siguiente del roadmap.
3. Gates del lote: backend `ruff` + `mypy` + `pytest`; frontend `typecheck` + `lint` + `vitest`; si cambia UI, `build` y E2E con `CI=1` + `WEB_BASE_URL` en puerto libre; si cambia esquema, `alembic check`.
4. Commit + push solo con gates verdes; vigilar CI hasta `success`. Si falla, corregir causa real en el mismo lote o siguiente antes de continuar. Nunca desactivar checks.
5. Registrar evidencia real (commit, CI run, comando, test) en la tabla 26.3 y en §23. Sin evidencia, el lote queda `IN_REVIEW`.
6. Supuestos conservadores documentados aquí; no inventar endpoints, tablas ni variables de entorno sin documentarlas.
7. Datos sintéticos y secretos fuera del repo; ningún dato personal real en fixtures, docs ni logs.

## 26.2 Supuestos

- **Localización:** se entregan dos paquetes, `es` e `en`, con selector persistente; traducción de strings de producto, no traducción automática de contenido de candidatos. `lang` del documento sigue al selector.
- **"Hashear endpoints":** se interpreta como IDs públicos no enumerables (UUID ya vigente), URLs firmadas HMAC con `exp` y firma de webhooks. No se cambia el formato de las rutas REST documentadas.
- **"Registrar la base de datos":** ya existe Alembic con migraciones versionadas y auditoría de dominio. No se crea un registro nuevo; se documenta su estado y se comprueba `alembic check`.
- **RLS:** no se habilita mientras todo acceso pase por la API con `organization_id` de sesión; se documenta la decisión y el punto de revisión si aparece acceso directo a PostgreSQL.
- **Google login:** se implementa con configuración por entorno y modo demo sin credenciales; queda deshabilitado si faltan variables. Requiere ADR antes de tocar autenticación.
- **Imagen hero y favicon:** hero `apps/web/public/hero-talentos.jpg` propio; favicon `apps/web/public/icon.svg` propio; sin recursos de terceros ni licencia de foto que revisar.

## 26.3 Backlog y estado

| Lote | Pedido | Unidad prevista | Estado | Evidencia |
|---|---|---|---|---|
| 16-01 | Roadmap y loop | `TalentOS_ROADMAP.md` | `DONE` | Commits `70c2667`, `1b96d65`; CI `45899845419` success. |
| 16-02 | Logout vuelve a landing | logout en shell + test E2E/unit | `DONE` | Commit `1adbe42`; CI `45901374970` success; `vitest` 120 passed, `build` OK, E2E OK. |
| 16-03 | Imagen hero propia | SVG propio + `apps/web/src/app/page.tsx` | `DONE` | Commits `ca27081`, `2870178`; CI `45903296474`, `46028725638` success; hero JPG propio con `build` y E2E OK. |
| 16-04 | Favicon característico | icon SVG + metadata | `DONE` | Commit `c8ae354`; CI `45904442600` success; ruta `/icon.svg` generada. |
| 16-05 | Sitemap y `robots` | rutas Next `sitemap.ts`/`robots.ts` | `DONE` | Commit `f938b2d`; CI `45905612312` success; rutas `/sitemap.xml` y `/robots.txt` generadas. |
| 16-06 | Idioma `es`/`en` + botón | módulo de textos + selector + `lang` | `IN_REVIEW` | Commits `5d52c7e`, `ddf10aa`, `4a8a850`, `dd798b1`, `8008b9e`; CI `45937828805` success; landing, shell, encabezado de panel y menú de comandos traducidos; faltan paneles de negocio. |
| 16-07 | Política de privacidad | `docs/privacy-policy.md` | `DONE` | Commit `4a8a850`; CI `45911085332` success; enlace en footer del workspace. |
| 16-08 | Términos y condiciones | `docs/terms-of-service.md` | `DONE` | Commit `4a8a850`; CI `45911085332` success; enlace en footer del workspace. |
| 16-09 | Consentimiento informado | formularios de alta y recuperación | `DONE` | Commits `a290fa7`, `fd2cb4e`, `b7b543d`, `902f645`, `4d4aed7`, `7fe2132`, `100f168`, `907b3b3`, `65b82c7`; CI `45958045628`, `45959329932`, `45960491271`, `45961566726`, `45964236168`, `45965598613`, `45967026729` success; `45962611490` falló en E2E por checkbox ausente, corregido en `7fe2132`. |
| 16-10 | Borrado de datos de usuario | exportación y borrado tenant-scoped + tests + auditoría | `DONE` | Commits `b4c4e99`, `bfdd0ab`, `fcf400f`, `e92465f`; CI `45951468264`, `45952486615`, `45953481519`, `45954654670` success. |
| 16-11 | Audit de vulnerabilidades | revisión de hallazgos y correcciones | `DONE` | Verificado en `8008b9e`; CI `45937828805` success; checklist y riesgos en `docs/security-review.md:19-54`; riesgos `RM-01`–`RM-05` aceptados solo para demo/local. |
| 16-12 | Claves expuestas y secretos en git | escaneo + `.gitignore`/docs | `DONE` | Commit `008d2ce`; CI `45943801440` success; job `secrets` en `.github/workflows/ci.yml` con `git grep` de patrones AWS/GitHub/Slack/JWT/claves privadas; YAML validado; sin dependencias nuevas. |
| 16-13 | Cifrado de datos sensibles | verificar Fernet + ampliar campos si aplica | `DONE` | Verificado en `8008b9e`; `apps/api/app/integrations/crypto.py:16-60`; Fernet por organización; `RM-03` queda como condición de staging/producción. |
| 16-14 | Autorización del lado del servidor | revisión de endpoints y tests negativos | `DONE` | Verificado en `8008b9e`; `apps/api/app/identity/dependencies.py:48-119`; tests negativos en `apps/api/tests/test_authorization.py:78,89,113,147,177,205,227`. |
| 16-15 | Acceso a registros restringido | roles + tenant en cada recurso | `DONE` | Verificado en `8008b9e`; membresía y roles en `apps/api/app/identity/dependencies.py:48-119`; tests cross-tenant en `apps/api/tests/test_authorization.py`. |
| 16-16 | Google login | ADR + configuración + endpoint + UI | `IN_REVIEW` | `docs/decisions/ADR-018.md`: OIDC code + PKCE, deshabilitado sin `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI` en `staging`/`production`, sin dependencias nuevas; faltan endpoint, UI y tests. |
| 16-17 | Campos manipulables | schemas estrictos y `extra=forbid` | `DONE` | Commit `82a9a58`; CI `45922837838` success; `extra=forbid` en identidad (registro, login, organización, invitación, reset, cambio de rol); 525 tests. |
| 16-18 | Cookies de sesión | `HttpOnly`/`Secure`/`SameSite`/expiry | `DONE` | Verificado en `8008b9e`; `apps/api/app/api/routes/auth.py:87-95`; tests en `apps/api/tests/test_auth.py:130-144`. |
| 16-19 | Hash de contraseñas | verificar bcrypt + coste | `DONE` | Verificado en `8008b9e`; bcrypt con tope 72 bytes en `apps/api/app/identity/security.py:8-21`; tests en `apps/api/tests/test_auth.py:121-128`. |
| 16-20 | Límite de login y bots | rate limit por IP/usuario + eventos | `DONE` | Commit `0b2bac3`; CI `45919600293` success; 60 intentos/minuto por IP en `login`/`forgot-password`/`reset-password` solo en `staging`/`production`; 429 con `Retry-After`; 519 tests. |
| 16-21 | Consultas DB parametrizadas/monitorizadas | ORM + logging sin PII | `DONE` | Verificado en `8008b9e`; ORM SQLAlchemy en todo `apps/api/app`; sin `text(` en dominio; `apps/api/app/core/logging.py:12-24`. |
| 16-22 | Validación y saneado de entradas | Pydantic + escapes antes de persistir | `DONE` | Verificado en `8008b9e`; `apps/api/app/documents/validation.py:8-14,50-71`; saneado en `apps/api/app/integrations/schemas.py:168-179,258-273`. |
| 16-23 | Límite de respuestas de API | paginación y cotas de salida | `DONE` | Verificado en `8008b9e`; paginación en rutas de `jobs`, `candidates`, `applications` y `documents`; tests en `apps/api/tests/test_applications_api.py:218-234`. |
| 16-24 | Cabeceras de seguridad, HTTPS y HSTS | middleware + tests | `DONE` | Commit `edb42db`; CI `45915102956` success; `nosniff`, `DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP en producción, redirect 307 y HSTS; 518 tests. |
| 16-25 | CSRF | tokens/origen según estrategia | `DONE` | Commits `b7ddfed`/`c45a046`; CI `45932408840`/`45933203449` success; `Origin` obligatorio en mutaciones bajo `staging`/`production`, orígenes permitidos por configuración; 530 tests. |
| 16-26 | Sesiones al cambiar contraseña | invalidación + test | `DONE` | Verificado en `8008b9e`; `apps/api/app/identity/service.py:140-167`; test en `apps/api/tests/test_auth.py:367-384`. |
| 16-27 | Caducidad de enlaces | URLs firmadas con TTL y test | `DONE` | Verificado en `8008b9e`; `apps/api/app/documents/tokens.py:42-96` con HMAC, `exp` y tenant; tests en `apps/api/tests/test_documents_api.py:366-386`; `RM-02` sigue para producción. |
| 16-28 | Sin numeración de usuarios | UUID y respuestas uniformes | `DONE` | Verificado en `8008b9e`; UUID en `apps/api/app/identity/models.py:49,92,106`; respuesta uniforme en `apps/api/tests/test_auth.py:353-364`. |
| 16-29 | Webhooks verificados | firma, replay y dedupe con tests | `DONE` | Verificado en `8008b9e`; `apps/api/app/integrations/webhooks.py:130-142,202`; dedupe por organización; tests en `apps/api/tests/test_inbound_webhooks.py`. |
| 16-30 | Prompt injection y límite de IA | defensas + cuotas + tests | `DONE` | Verificado en `8008b9e`; defensas en `apps/api/app/agents/cv_analyst.py`; cuota de llamadas por tool en `apps/api/app/agents/tools.py:640,707-757`; tests en `test_cv_analyst.py` y `test_agent_tools.py`. No mide gasto LLM. |
| 16-31 | Tamaño de solicitudes | límite global y por upload | `DONE` | Commit `f9ba3da`; CI `45925962276` success; 2 MiB global para `POST`/`PUT`/`PATCH` no multipart, 413 con envelope; uploads siguen limitados a 10 MiB; 527 tests. |
| 16-32 | Límite de recuperación de contraseña | rate limit + auditoría | `DONE` | Commit `4b7f6ce`; CI `45941003001` success; eventos `auth_password_reset_requested`, `auth_password_reset_succeeded`, `auth_password_reset_failed` con `request_id`/`correlation_id`, sin email/token/password; 531 tests. |
| 16-33 | CORS restrictivo | orígenes por entorno + tests | `DONE` | Commit `951daf2`; CI `45941805680` success; preflight solo para `WEB_BASE_URL`, credenciales permitidas y origen externo sin header; `ruff`/`mypy`/`pytest` OK. |
| 16-34 | Rutas de administrador por defecto | revisión de rutas y cierre | `DONE` | Verificado en `8008b9e`; docs y esquema deshabilitados en producción (`apps/api/app/main.py:37-44`); sin rutas `/admin` en `apps/api/app/api/routes`. |
| 16-35 | Eventos de seguridad | logging de fallos y correlación | `DONE` | Commit `7dc55ff`; CI `45929163932` success; `auth_login_failed` y `auth_password_reset_failed` con `request_id`/`correlation_id`, sin email/token/password; 529 tests. |
| 16-36 | Datos estructurados | JSON-LD y metadatos | `DONE` | Commit `01075ea`; CI `45942842954` success; `metadataBase`, OpenGraph, Twitter y JSON-LD escapado en `apps/web/src/app/layout.tsx`; `NEXT_PUBLIC_WEB_BASE_URL` documentado en `.env.example`; `tsc`/`lint`/121 tests/`build` OK. |
| 16-37 | Escaneo de dependencias | `npm audit` + `pip-audit` | `DONE` | Verificado en `8008b9e`; `.github/workflows/ci.yml:45-50,83-85` ejecuta `pip-audit` y `npm audit --audit-level=high`. |
| 16-38 | Sin sourcemaps | configuración de build + verificación | `DONE` | Verificado en `8008b9e`; build `8008b9e`/CI `45937828805`; 0 `.map` en `.next/static` y 0 `sourceMappingURL` en assets públicos. |
| 16-39 | APIs y secretos en servidor | revisión de cliente y servidor | `DONE` | Verificado en `8008b9e`; `apps/web/src/lib/api.ts` sin secretos; `apps/api/app/core/config.py:21-29` solo entorno; `.gitignore:1-5`. |
| 16-40 | Demo completa | seed sintético reproducible + reset | `DONE` | Commit `dff215d`; CI `45946044427` success; `apps/api/scripts/seed_demo.py` con `seed`/`reset` solo en `local`/`test`; `tests/test_demo_seed.py` verifica idempotencia y preservación de otros tenants; `ruff`/`mypy`/`pytest` OK. |
| 16-41 | Empty states | pantallas con lista vacía | `DONE` | Verificado en `8008b9e`; inventario en `docs/ui-ux-inventory.md:132`; estados vacíos en paneles de `apps/web/src/components`. |
| 16-42 | Loading states | pantallas con carga | `DONE` | Verificado en `8008b9e`; `apps/web/src/app/loading.tsx:4-9`; `role="status"`/`aria-busy` en paneles. |
| 16-43 | Hover states | controles interactivos | `DONE` | Verificado en `8008b9e`; variantes en `apps/web/src/components/ui/shadcn/button.tsx:12-18`; inventario en `docs/ui-ux-inventory.md:173`. |
| 16-44 | Licencias de imágenes | verificación documentada | `DONE` | Verificado en `8008b9e`; `apps/web/public/hero-talentos.svg` e `icon.svg` propios; sin assets de terceros. |
| 16-46 | Superadmin de demo | bandera global + seed por env + ADR-019 | `DONE` | Commit `ba9a305`; CI `46034226576` success; `ruff`/`mypy`/`pytest` 543 passed, `alembic check` OK; sin login bypass ni contraseña fija. |
| 16-45 | Cierre y evidencia final | docs + CI final verde | `NOT_STARTED` | — |

## 26.4 Progreso del loop

| Fecha | Lote | Commit | CI run | Resultado |
|---|---|---|---|---|
| 2026-11-26 | 16-01 | `1b96d65` | `45899845419` | Roadmap y loop publicados. |
| 2026-11-26 | 16-02 | `1adbe42` | `45901374970` | Logout limpia `talentos:active-org` y vuelve a `/`. |
| 2026-11-26 | 16-03 | `ca27081` | `45903296474` | Hero usa ilustración SVG original. |
| 2026-11-26 | 16-04 | `c8ae354` | `45904442600` | Icono propio disponible en `/icon.svg`. |
| 2026-11-26 | 16-05 | `f938b2d` | `45905612312` | `sitemap.xml` y `robots.txt` derivan del host de la petición. |
| 2026-11-26 | 16-06 | `dd798b1` | `45912168237` | Selector `es`/`en`, `lang` y textos de landing/shell; cobertura parcial. |
| 2026-11-26 | 16-07 | `4a8a850` | `45911085332` | Política de privacidad enlazada desde el workspace. |
| 2026-11-26 | 16-08 | `4a8a850` | `45911085332` | Términos enlazados desde el workspace. |
| 2026-11-26 | 16-24 | `edb42db` | `45915102956` | Cabeceras de seguridad, CSP, redirect HTTPS y HSTS en producción. |
| 2026-11-26 | 16-20 | `0b2bac3` | `45919600293` | Rate limit de 60/min por IP en endpoints de autenticación desplegada. |
| 2026-11-26 | 16-17 | `82a9a58` | `45922837838` | Rechazo de campos desconocidos en esquemas de identidad. |
| 2026-11-26 | 16-31 | `f9ba3da` | `45925962276` | Límite global de 2 MiB por solicitud con 413 uniforme. |
| 2026-11-26 | 16-35 | `7dc55ff` | `45929163932` | Eventos de seguridad de autenticación con correlación y sin PII. |
| 2026-11-27 | 16-25 | `b7ddfed` | `45932408840` | `Origin` obligatorio en mutaciones desplegadas y rechazo de orígenes externos. |
| 2026-11-27 | 16-06 | `8008b9e` | `45937828805` | Menú de comandos traducido; i18n sigue parcial. |
| 2026-11-27 | 16-11/13/14/15/18/19/21/22/23/26/27/28/29/30/34/37/38/39/41/42/43/44 | `8008b9e` | `45937828805` | Auditoría de controles ya presentes; estados y evidencia actualizados. |
| 2026-11-27 | 16-32 | `4b7f6ce` | `45941003001` | Auditoría de recuperación de contraseña sin PII; 531 tests. |
| 2026-11-27 | 16-33 | `951daf2` | `45941805680` | Test de preflight CORS con origen permitido y externo. |
| 2026-11-27 | 16-36 | `01075ea` | `45942842954` | Metadatos OpenGraph/Twitter y JSON-LD con `<` escapado. |
| 2026-11-27 | 16-12 | `008d2ce` | `45943801440` | Escaneo de secretos en archivos versionados, sin dependencias nuevas. |
| 2026-11-27 | 16-40 | `dff215d` | `45946044427` | Seed/reset de demo sintética; idempotente y limitado a `local`/`test`. |
| 2026-11-27 | 16-12/32/33/36/40 | `0e1bbc3` | `45946928309` | Estados, evidencia y checklist de seguridad sincronizados. |
| 2026-11-27 | 16-06 | `9835bbe` | `45947918916` | Panel de vacantes traducido; `tsc`/`lint`/121 tests/`build`/E2E OK. |
| 2026-11-27 | — | `6e8bd7a` | `45948670139` | Reglas generadas por `next dev` versionadas para árbol limpio. |
| 2026-11-27 | 16-16 | `def051f` | `45949479351` | ADR-018: Google OIDC con PKCE y activación solo con env en `staging`/`production`. |
| 2026-11-27 | — | `8e85a8e` | `45950237843` | Sincronización de memoria y evidencia del loop. |
| 2026-11-27 | 16-10 | `b4c4e99`, `bfdd0ab` | `45951468264`, `45952486615` | Exportación tenant-scoped de candidatos, notas, postulaciones y documentos; auditoría y test. |
| 2026-11-27 | 16-10 | `fcf400f`, `e92465f` | `45953481519`, `45954654670` | Borrado tenant-scoped con roles, borrado de bytes y auditoría; test cross-tenant. |
| 2026-11-27 | 16-10 | `e88a0c6` | `45955716802` | Política de privacidad y revisión de seguridad sincronizadas. |
| 2026-11-27 | 16-10 | `8c6bfea` | `45956748498` | Roadmap `16-10` cerrado con evidencia. |
| 2026-11-27 | 16-09 | `a290fa7`, `fd2cb4e` | `45958045628`, `45959329932` | `accept_privacy` estricto en backend; rechazo de `false` y consentimiento explícito en `staging`/`production`. |
| 2026-11-27 | 16-09 | `b7b543d`, `902f645`, `4d4aed7` | `45960491271`, `45961566726`, `45962611490` | DTOs y checkbox en registro, invitación y recuperación; E2E de recuperación falló por checkbox ausente. |
| 2026-11-27 | 16-09 | `7fe2132`, `100f168`, `907b3b3`, `65b82c7` | `45964236168`, `45965598613`, `45967026729` | E2E corregido; checkbox en reset e invitación; `tsc`/`lint`/121 tests/`build`/E2E OK. |
| 2026-11-27 | 16-06/UI polish | `200ca5a`, `848e972`, `5357251` | `46023858586`, `46026836911` | IntegrationsPanel y AutomationRulePanel traducidos; UI polish cerrado. |
| 2026-11-27 | 16-03 | `2870178` | `46028725638` | Hero JPG propio; `naturalWidth=1200`, `naturalHeight=896`, sin console errors. |
| 2026-11-27 | 16-46 | `ba9a305` | `46034226576` | Superadmin de demo con bandera persistida, seed por `TALENTOS_SUPERADMIN_PASSWORD`; elevación solo en `local`/`test`. |

---

# 27. Fase 17 — Asistente virtual de workspace (2026-11-27)

**Estado:** `IN_PROGRESS`. **Origen:** petición del usuario 2026-11-27; `docs/decisions/ADR-020-asistente-virtual.md` aceptado. **RF:** `RF-ASSIST-001`. **Dependencia:** cierre de Fase 16 (`16-45`) con CI verde (`46048508076`).

## 27.1 Reglas del loop

1. Misma disciplina de §26.1: ≤2 archivos por lote, gates reales, commit/push solo con CI verde y evidencia en tabla.
2. Backend autoridad: `organization_id` de sesión; sin lectura entre cuentas; superadmin no amplía tenant.
3. LLM solo en capa de agentes; salidas validadas con Pydantic; herramientas cerradas; sin SQL, shell, filesystem ni navegación arbitraria.
4. Toda escritura queda como borrador o acción propuesta; aplicar requiere confirmación explícita; efectos externos requieren `Approval` resuelta.
5. Sin dependencias nuevas sin ADR; demo usa `LLM_PROVIDER=mock` y datos sintéticos de la organización demo.

## 27.2 Supuestos

- Superadmin demo: `superadmin.demo@example.test`, membresía `viewer`; ve solo la organización activa.
- Sin RAG, sin historial persistente y sin búsqueda semántica en este alcance.
- Formularios permitidos: `job.create`, `candidate.create`, `assessment.criterion`, `interview.guide`, `automation.rule`, `message.draft`; campos sensibles quedan para la persona.
- Acciones permitidas: `explain`, `navigate`, `fill_form`, `create_draft`, `request_approval`; fuera de allowlist → `unsupported_reason`.
- Workflow `workspace_assistant`, versión `1.0.0`, con interrupt en `propose_actions`.
- `RF-ASSIST-001` registrado en `TalentOS_SDD.md` §4.9; sin dependencias nuevas.

## 27.3 Backlog y estado

| Lote | Pedido | Unidad prevista | Estado | Evidencia |
|---|---|---|---|---|
| 17-01 | Roadmap y ADR | `TalentOS_ROADMAP.md`, `docs/decisions/ADR-020-asistente-virtual.md` | `DONE` | `f52a938`; CI `46058799763` success; RF en SDD §4.9 (`aa5fb9a`). |
| 17-02 | Contratos y schemas | `apps/api/app/agents/contracts.py`, `apps/api/tests/test_assistant_contracts.py` | `DONE` | `a1900ff`; CI `46058799763` success; `pytest` 552. |
| 17-03 | Tools de lectura y capabilities | `apps/api/app/agents/tools.py`, `apps/api/tests/test_assistant_tools.py` | `DONE` | `b609ae1`; CI `46061944047` success; `pytest` 558; 13 tests nuevos, `ruff`/`mypy` limpios. |
| 17-04 | Workflow y LLM mock | `apps/api/app/agents/assistant.py`, `apps/api/tests/test_assistant_workflow.py` | `DONE` | `224237b`; CI `46066121679` success; 9 tests nuevos; `pytest` 567 passed; `ruff`/`mypy` limpios. |
| 17-05 | Endpoint de mensajes y ack | `apps/api/app/api/routes/agents.py`, `apps/api/tests/test_assistant_api.py` | `DONE` | `8c959d1`; CI `46069838247` success; 6 tests nuevos; `pytest` 573 passed; `ruff`/`mypy` limpios; `401`, `403`, `not_available`, ack sin efectos no confirmados. |
| 17-06 | Panel UI y acciones | `apps/web/src/components/AssistantPanel.tsx`, `apps/web/tests/assistant_panel.test.tsx` | `DONE` | `113e411`; CI `46071440022` success; 5 tests nuevos; `npm test -- --run` 126 passed; `tsc`/`lint` limpios; citas, `Aplicar`/`Descartar`, sin JS arbitrario. |
| 17-07 | Integración en shell e i18n | `apps/web/src/components/WorkspaceShell.tsx`, `apps/web/src/lib/i18n.tsx` | `DONE` | `0f92d70`; CI `46072892199` success; panel montado en 11 superficies permitidas; claves `assistant.title`/`assistant.note` en `es`/`en`; `npm test -- --run` 126 passed; `tsc`/`lint` limpios. |
| 17-08 | Seed demo ampliado | `apps/api/scripts/seed_demo.py`, `apps/api/tests/test_demo_seed.py` | `DONE` | `bf8ca85`; CI `46077876061` success; 1 test nuevo (3 en el archivo); `pytest` 574 passed; `ruff`/`mypy` limpios; 2 versiones, 3 requisitos, 5 candidatos, 4 estados de evidencia, borradores, regla `draft`, 1 aprobación resuelta y 1 rechazada. |
| 17-09 | Evaluación con mock | `apps/api/tests/test_assistant_evaluations.py` | `DONE` | `f5e640a`; CI `46080547217` success; 7 tests nuevos; `pytest` 581 passed; `ruff`/`mypy` limpios; dataset versionado `assistant-eval-1.0.0`; groundedness, off-scope, inyección, timeout determinista y tokens sin PII. |
| 17-10 | E2E y cierre | `apps/web/e2e/assistant.spec.ts`, `TalentOS_ROADMAP.md` | `DONE` | `8c2c4da`; CI `46082047742` success; 3 tests E2E nuevos (evidencia citada + ack aprobado, descarte con confirmación, error 403 sin respuesta simulada); `tsc`/`lint` limpios; `vitest` 126 passed; `build` OK; E2E local `CI=1` 23 passed/1 skipped; Fase 17 cerrada. |

## 27.4 Criterios de cierre

- Sin sesión → `401`; `resource_ref` de otra organización → `not_available` sin revelar existencia.
- `viewer` puede explicar y navegar; escritura → `permission_denied`.
- Toda cita pertenece al documento, candidato y organización del contexto.
- `fill_form` pasa el schema de `form_id`; sin campos sensibles; sin confirmación no hay cambio de dominio.
- Efecto externo queda `waiting_approval` hasta `Approval` resuelta.
- Prompt injection no amplía tools, permisos ni rutas.
- Misma `idempotency_key` no crea dos `AgentRun` ni dos borradores.
- Logs y `AgentEvent.payload` sin contraseñas, tokens, emails completos ni CV completo.
- Gates del lote en verde antes de marcar `DONE`; sin evidencia real, estado `IN_REVIEW`.

## 27.5 Evidencia

| Fecha | Lote | Commits | CI | Resultado |
|---|---|---|---|---|
| 2026-11-27 | 17-01/17-02 | `f52a938`, `a1900ff`, `aa5fb9a` | `46058799763` | success; ADR + contratos + RF en SDD. |
| 2026-11-27 | 17-03 | `b609ae1` | `46061944047` | success; registry de solo lectura con capabilities, tenant, roles, cotas y traza; `pytest` 558. |
| 2026-11-27 | 17-04 | `224237b` | `46066121679` | success; grafo `workspace_assistant` con citas verificadas, políticas, reintentos e interrupt; 9 tests nuevos; `pytest` 567 passed. |
| 2026-11-27 | 17-05 | `8c959d1` | `46069838247` | success; endpoints de mensaje y ack con aislamiento por tenant, idempotencia y aprobación persistida; 6 tests nuevos; `pytest` 573 passed. |
| 2026-11-27 | 17-06 | `113e411` | `46071440022` | success; panel con citas verificables, ack confirmado y sin JS arbitrario; 5 tests nuevos; `vitest` 126 passed. |
| 2026-11-27 | 17-07 | `0f92d70` | `46072892199` | success; panel integrado en shell con superficies permitidas y textos `es`/`en` centralizados; `vitest` 126 passed. |
| 2026-11-27 | 17-08 | `bf8ca85` | `46077876061` | success; seed sintético con evidencia verificable, borradores, regla `draft` y aprobaciones resueltas; 1 test nuevo; `pytest` 574 passed. |
| 2026-11-27 | 17-09 | `f5e640a` | `46080547217` | success; evaluación determinista con dataset `assistant-eval-1.0.0`, 7 tests nuevos; `pytest` 581 passed. |
| 2026-11-27 | 17-10 | `8c2c4da` | `46082047742` | success; E2E del asistente en shell real con evidencia citada, ack aprobado, descarte confirmado y error 403 sin respuesta simulada; `vitest` 126 passed; 23 passed/1 skipped. |

---

# 28. Fase 18 — Proveedor LLM local y demo limitada (2026-11-28)

**Estado:** `DONE`. **Origen:** petición del usuario 2026-11-27/28; `docs/decisions/ADR-021-proveedor-local-y-demo-limitada.md` aceptado. **RF:** extensión de `RF-ASSIST-001`. **Alcance:** solo proveedor local y aviso de demo limitada; planes, suscripciones, facturación y fine-tuning quedan para fases futuras.

## 28.1 Reglas del loop

1. Misma disciplina de §27.1: ≤2 archivos de implementación por lote, gates reales y evidencia antes de marcar `DONE`.
2. `LLMProvider` sigue siendo el único contrato; dominio, permisos y reglas de negocio no cambian.
3. Sin dependencias Python nuevas: se reutiliza `httpx`.
4. Pesos, blobs, adapters y datasets del modelo quedan fuera del repositorio.
5. Backend decide la limitación `demo_mock`; la UI solo la traduce a texto visible.

## 28.2 Backlog y estado

| Lote | Pedido | Unidad prevista | Estado | Evidencia |
|---|---|---|---|---|
| 18-01 | ADR y entorno | `ADR-021`, `.env.example`, `docs/ENVIRONMENTS.md`, `TalentOS_ROADMAP.md` | `DONE` | `2b48d3f`; define `local`, demo limitada y artefactos fuera del repo. |
| 18-02 | Adaptador local | `apps/api/app/llm/local.py`, `apps/api/app/core/config.py` | `DONE` | `ce45d96`; `/api/chat` nativo con JSON schema, sin `Authorization`. |
| 18-03 | Registro y tests | `apps/api/app/llm/registry.py`, `apps/api/tests/test_llm_provider.py` | `DONE` | `01427a5`; registry `mock|local|remote`; `ruff`/`mypy` limpios; 12 tests en archivo. |
| 18-04 | Demo limitada en API | `apps/api/app/agents/assistant.py`, `apps/api/tests/test_assistant_api.py` | `DONE` | `100ce64`; `demo_mock` aparece solo con `LLM_PROVIDER=mock`. |
| 18-05 | Aviso en UI | `apps/web/src/components/AssistantPanel.tsx`, `apps/web/tests/assistant_panel.test.tsx` | `DONE` | `f6d7bc8`; aviso visible sin código técnico; `tsc`/`lint`/`vitest`/`build`/E2E en verde. |
| 18-06 | Resiliencia local | `apps/api/app/llm/local.py`, `apps/api/tests/test_llm_provider.py` | `DONE` | `2ca2946`; `keep_alive=30m` y timeout mínimo de 180 s para carga fría; smoke real `qwen3:4b` en 2.76 s con modelo cargado. |
| 18-07 | E2E del aviso | `apps/web/e2e/assistant.spec.ts` | `DONE` | `04b6269`; aviso `Demo limitada:` visible en navegador con API mockeada; `tsc`/ESLint limpios; Playwright 25 passed/1 skipped. |
| 18-08 | Cierre | `TalentOS_ROADMAP.md`, `docs/ENVIRONMENTS.md`, `.env.example`, `ADR-021` | `DONE` | `a30f4ed`, `f04a06c`; CI `46097505327` success: backend (`ruff`, `mypy`, `pytest`, `alembic`), compose, secret scan y frontend (typecheck, lint, unit, build, E2E) en verde. |

## 28.3 Evidencia

| Fecha | Lote | Commits | CI | Resultado |
|---|---|---|---|---|
| 2026-11-28 | 18-01/18-08 | `2b48d3f`, `ce45d96`, `01427a5`, `100ce64`, `f6d7bc8`, `2ca2946`, `a30f4ed`, `04b6269`, `f04a06c` | `46097505327` success | Local: `ruff`, `mypy`, `pytest` completo 588 passed, `tsc`, ESLint, `vitest` 131 passed, `next build` y Playwright 25 passed/1 skipped. CI: backend, compose, secret scan y frontend verdes. Latencia real: 2.76 s cargado, 108 s en frío, 144 s con thinking. Sin pesos ni secretos en el repo. |
