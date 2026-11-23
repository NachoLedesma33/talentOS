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

- [ ] Modelar `User`, `Organization` y `Membership`.
- [ ] Crear migraciones.
- [ ] Implementar registro.
- [ ] Implementar login y logout.
- [ ] Elegir y documentar estrategia de sesión/token.
- [ ] Implementar hash seguro de contraseñas.
- [ ] Implementar usuario actual (`/me`).
- [ ] Implementar creación de organización.
- [ ] Implementar selección de organización activa.
- [ ] Implementar roles `owner`, `admin`, `recruiter`, `reviewer`, `viewer`.
- [ ] Crear dependencias de autorización en FastAPI.
- [ ] Aplicar scoping de organización en servicios y repositorios.
- [ ] Crear interfaz de login y registro.
- [ ] Crear selector de organización.
- [ ] Crear gestión básica de miembros.
- [ ] Registrar eventos relevantes en auditoría.

## Pruebas obligatorias

- [ ] Usuario no autenticado no accede a endpoints privados.
- [ ] Un usuario no puede leer recursos de otra organización.
- [ ] Un usuario no puede modificar `organization_id` para escalar acceso.
- [ ] Los roles tienen permisos diferenciados.
- [ ] Las tareas asíncronas preservan el contexto de organización.
- [ ] Las sesiones inválidas o expiradas se rechazan.

## Criterio de salida

Dos organizaciones con usuarios y datos distintos pueden utilizar la aplicación simultáneamente sin filtración de recursos.

---

# 6. Fase 3 — Recruitment Core

**Objetivo:** disponer de la gestión central de vacantes, candidatos y procesos, todavía sin depender de IA.

## 6.1 Vacantes

- [ ] Modelar `Job`, `JobRequirement` y `JobVersion`.
- [ ] Crear migraciones, constraints e índices.
- [ ] Implementar CRUD de vacantes.
- [ ] Implementar estados: draft, open, paused, closed, archived.
- [ ] Implementar requisitos obligatorios y deseables.
- [ ] Implementar tipos de requisitos.
- [ ] Implementar versionado de requisitos.
- [ ] Crear formularios frontend.
- [ ] Crear listado, filtros y detalle de vacante.

## 6.2 Candidatos

- [ ] Modelar `Candidate`.
- [ ] Implementar alta, edición y consulta.
- [ ] Implementar búsqueda y paginación.
- [ ] Implementar notas internas con permisos.
- [ ] Implementar historial de actividad.
- [ ] Crear perfil de candidato.

## 6.3 Postulaciones y pipeline

- [ ] Modelar `Application`.
- [ ] Definir etapas configuradas por el sistema.
- [ ] Implementar transiciones válidas.
- [ ] Implementar asociación candidato-vacante.
- [ ] Evitar duplicados de postulación según regla de negocio.
- [ ] Implementar vista de pipeline.
- [ ] Registrar cada cambio de etapa.

## Criterios de aceptación

- [ ] Crear una vacante con requisitos.
- [ ] Crear un candidato.
- [ ] Asociarlo a la vacante.
- [ ] Moverlo por etapas permitidas.
- [ ] Consultar el historial.
- [ ] Verificar aislamiento por organización.
- [ ] Completar tests de reglas de dominio y API.

**Hito demostrable:** gestión básica de un proceso de selección sin IA.

---

# 7. Fase 4 — Document Intelligence

**Objetivo:** recibir currículums de forma segura, extraer texto y producir información estructurada revisable.

## Tareas

### Recepción y almacenamiento
- [ ] Definir formatos permitidos: PDF y DOCX.
- [ ] Definir límite de tamaño y cantidad de páginas.
- [ ] Validar extensión, MIME y firma del archivo.
- [ ] Generar nombre interno no predecible.
- [ ] Almacenar en bucket privado o storage local de desarrollo.
- [ ] Calcular checksum.
- [ ] Crear metadatos y estado del documento.
- [ ] Implementar acceso mediante autorización y URLs temporales si aplica.

### Extracción de texto
- [ ] Implementar extractor PDF.
- [ ] Implementar extractor DOCX.
- [ ] Detectar documentos vacíos, corruptos o no compatibles.
- [ ] Preservar páginas y offsets cuando sea posible.
- [ ] Definir límites de memoria y tiempo.
- [ ] Ejecutar extracción en background.

### Interpretación con IA
- [ ] Crear interfaz `LLMProvider`.
- [ ] Implementar proveedor mock determinista.
- [ ] Implementar adaptador de proveedor real configurable.
- [ ] Definir schema Pydantic de extracción.
- [ ] Crear prompt versionado.
- [ ] Extraer experiencia, formación, skills, proyectos e idiomas.
- [ ] Asociar cada dato con evidencia fuente.
- [ ] Marcar campos faltantes.
- [ ] Validar respuesta estructurada.
- [ ] Enviar resultados dudosos a revisión.

### Interfaz
- [ ] Crear componente de carga.
- [ ] Mostrar progreso del procesamiento.
- [ ] Mostrar error y opción de reintento.
- [ ] Mostrar datos extraídos.
- [ ] Permitir corregir y confirmar.
- [ ] Registrar quién confirmó los datos.

## Pruebas obligatorias

- [ ] PDF válido.
- [ ] DOCX válido.
- [ ] Archivo vacío.
- [ ] Archivo corrupto.
- [ ] Extensión falsa.
- [ ] Archivo excesivo.
- [ ] Timeout del proveedor.
- [ ] JSON inválido.
- [ ] Datos faltantes.
- [ ] Documento con instrucciones maliciosas.
- [ ] Acceso a documento de otra organización.

## Criterio de salida

Un usuario carga un CV sintético, el worker lo procesa, la IA produce información estructurada con referencias al documento y el usuario puede revisarla y confirmarla.

---

# 8. Fase 5 — Evidence-Based Matching

**Objetivo:** comparar candidatos con vacantes mediante criterios transparentes y evidencias verificables.

## Tareas

- [ ] Definir schema de evaluación por requisito.
- [ ] Definir estados `supported`, `partial`, `not_found`, `needs_review`.
- [ ] Obtener versión inmutable de requisitos de la vacante.
- [ ] Obtener perfil y documentos confirmados del candidato.
- [ ] Crear contexto mínimo para el modelo.
- [ ] Implementar evaluación criterio por criterio.
- [ ] Asociar citas o referencias a fragmentos fuente.
- [ ] Verificar que las referencias existan.
- [ ] Detectar contradicciones y evidencia insuficiente.
- [ ] Generar resumen de fortalezas y brechas.
- [ ] Generar preguntas para información faltante.
- [ ] Crear pantalla de evaluación.
- [ ] Implementar revisión humana.
- [ ] Guardar versión del modelo, prompt y evaluación.
- [ ] Permitir comparar evaluaciones de versiones distintas.

## Reglas

- No usar atributos protegidos ni proxies.
- No inferir personalidad, inteligencia o compromiso.
- No presentar una puntuación agregada como verdad objetiva.
- No descartar candidatos automáticamente.
- No inventar evidencia.
- Separar hechos, inferencias y datos no encontrados.

## Pruebas obligatorias

- [ ] Requisito claramente respaldado.
- [ ] Evidencia parcial.
- [ ] Requisito no encontrado.
- [ ] Documento contradictorio.
- [ ] Referencia de evidencia inexistente.
- [ ] Requisito modificado después de una evaluación.
- [ ] Revisión humana que corrige un resultado.
- [ ] Evaluación repetible con mock.

## Criterio de salida

Cada requisito de una vacante tiene un resultado explicable, una referencia verificable o una marca explícita de información insuficiente.

**Hito demostrable:** análisis de un candidato contra una vacante, con evidencias visibles.

---

# 9. Fase 6 — Agent Runtime

**Objetivo:** implementar workflows de IA con estado, herramientas limitadas, checkpoints y trazabilidad.

## Tareas

### Fundamentos
- [ ] Definir contrato común de workflow.
- [ ] Definir estados de ejecución.
- [ ] Definir schema de eventos.
- [ ] Integrar LangGraph en el módulo de agentes.
- [ ] Implementar persistencia/checkpointing.
- [ ] Ejecutar workflows desde workers.
- [ ] Implementar cancelación y timeout.
- [ ] Implementar límites de reintentos.
- [ ] Propagar correlation ID.

### Herramientas
- [ ] Crear registry de tools.
- [ ] Definir permisos por tool.
- [ ] Implementar tools de lectura de vacantes y candidatos.
- [ ] Implementar tool de creación de borradores.
- [ ] Implementar tool de solicitud de aprobación.
- [ ] Validar inputs con Pydantic.
- [ ] Registrar invocaciones.
- [ ] Aplicar idempotencia en tools de escritura.

### Agentes
Implementar de manera incremental, no todos a la vez:

- [ ] Job Analyst.
- [ ] CV Analyst.
- [ ] Matching Analyst.
- [ ] Quality Auditor.
- [ ] Recruitment Orchestrator.

Los agentes de entrevistas y automatización pueden utilizarse desde fases específicas posteriores.

### Human-in-the-loop
- [ ] Definir puntos de interrupción.
- [ ] Persistir el estado antes de esperar aprobación.
- [ ] Exponer aprobación/rechazo mediante API.
- [ ] Reanudar workflow tras decisión.
- [ ] Registrar actor, fecha y decisión.

## Pruebas obligatorias

- [ ] Salida válida.
- [ ] Salida malformada.
- [ ] Tool no autorizada.
- [ ] Organización incorrecta.
- [ ] Timeout.
- [ ] Reintento.
- [ ] Ejecución duplicada.
- [ ] Pausa y reanudación.
- [ ] Aprobación y rechazo.
- [ ] Fallo de proveedor.
- [ ] Prompt injection en documento.

## Criterio de salida

Un workflow completo puede iniciarse, inspeccionarse, pausarse para aprobación, reanudarse y finalizar sin perder su trazabilidad.

---

# 10. Fase 7 — Interview Assistant

**Objetivo:** transformar brechas y requisitos de la vacante en guías de entrevista útiles.

## Tareas

- [ ] Definir entidades de entrevista y preguntas.
- [ ] Crear preguntas asociadas a requisitos.
- [ ] Generar preguntas técnicas y de profundización.
- [ ] Explicar qué evidencia o competencia busca explorar cada pregunta.
- [ ] Validar preguntas contra políticas de selección.
- [ ] Permitir editar, ordenar y eliminar preguntas.
- [ ] Crear guía de entrevista.
- [ ] Registrar feedback humano estructurado.
- [ ] Vincular feedback con requisitos, sin convertirlo en una decisión automática.

## Criterios de aceptación

- [ ] Crear guía desde una vacante.
- [ ] Generar preguntas vinculadas a requisitos concretos.
- [ ] Editar y guardar guía.
- [ ] Registrar feedback.
- [ ] Ver historial de cambios.
- [ ] Evitar preguntas discriminatorias o irrelevantes mediante reglas y revisión.

---

# 11. Fase 8 — Automation Engine

**Objetivo:** automatizar procesos repetitivos mediante eventos, condiciones, acciones y aprobaciones.

## MVP: motor estructurado

- [ ] Definir schema de automatización.
- [ ] Implementar triggers por eventos de dominio.
- [ ] Implementar condiciones deterministas.
- [ ] Implementar acciones permitidas.
- [ ] Definir límites y validaciones de cada acción.
- [ ] Implementar modo dry-run.
- [ ] Crear ejecución persistida.
- [ ] Crear historial y detalle de ejecución.
- [ ] Implementar aprobación humana.
- [ ] Implementar reintentos e idempotencia.
- [ ] Prevenir ciclos infinitos.
- [ ] Implementar activar/desactivar.
- [ ] Versionar configuraciones.

## Acciones iniciales

- [ ] Crear tarea interna.
- [ ] Crear borrador de correo.
- [ ] Solicitar aprobación.
- [ ] Registrar nota.
- [ ] Proponer cambio de etapa.
- [ ] Ejecutar análisis autorizado.

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

- [ ] Definir interfaz de integración.
- [ ] Definir ciclo de vida de credenciales.
- [ ] Cifrar configuración sensible.
- [ ] Implementar proveedor de correo en sandbox.
- [ ] Implementar envío real solo después de aprobación.
- [ ] Implementar webhooks entrantes.
- [ ] Validar firma y timestamp cuando aplique.
- [ ] Implementar protección anti-replay.
- [ ] Deduplicar eventos.
- [ ] Implementar webhooks salientes firmados.
- [ ] Implementar reintentos y registro de entrega.
- [ ] Añadir pantalla de estado de integraciones.
- [ ] Documentar límites y permisos de cada proveedor.

## Criterios de aceptación

- [ ] Credenciales nunca aparecen en logs ni respuestas API.
- [ ] Webhook inválido se rechaza.
- [ ] Evento duplicado no duplica la operación.
- [ ] Fallo temporal se reintenta según política.
- [ ] El usuario puede diagnosticar una integración fallida.

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
- [ ] Añadir correlación con vacante, candidato y organización.
- [ ] Añadir política de retención de logs.

No exponer razonamiento interno privado del modelo. Mostrar pasos de workflow, decisiones operativas, entradas/salidas permitidas, herramientas y resultados.

## Criterio de salida

Un usuario autorizado puede explicar qué ocurrió en una ejecución, dónde falló, qué herramienta utilizó y cómo se resolvió.

---

# 14. Fase 11 — Simulation Lab & AI Evaluation

**Objetivo:** medir la calidad de extracción, matching y workflows antes de cambios relevantes.

## Dataset sintético

- [ ] Crear perfiles ficticios variados.
- [ ] Crear CVs PDF y DOCX sintéticos.
- [ ] Incluir datos incompletos.
- [ ] Incluir trayectorias ambiguas.
- [ ] Incluir requisitos ausentes.
- [ ] Incluir contradicciones.
- [ ] Incluir prompt injection.
- [ ] Versionar dataset y etiquetas esperadas.

## Evaluaciones

- [ ] Medir exactitud de extracción por campo.
- [ ] Medir fidelidad de evidencias.
- [ ] Medir validez de esquemas.
- [ ] Medir consistencia de matching.
- [ ] Medir robustez ante entradas adversariales.
- [ ] Medir latencia.
- [ ] Medir consumo/costo cuando sea posible.
- [ ] Comparar versiones de prompts y modelos.
- [ ] Generar reporte de regresión.

## Simulación operativa

- [ ] Crear escenario de contratación.
- [ ] Ejecutar varios candidatos sintéticos.
- [ ] Simular proveedor lento.
- [ ] Simular proveedor caído.
- [ ] Simular tool fallida.
- [ ] Simular aprobación rechazada.
- [ ] Simular reintento.
- [ ] Separar por completo entorno y datos demo.

## Criterio de salida

Se puede ejecutar el mismo experimento nuevamente y comparar resultados con métricas y versiones identificables.

---

# 15. Fase 12 — Analytics

**Objetivo:** convertir los eventos operativos en métricas útiles para el equipo de selección.

## Indicadores iniciales

- [ ] Vacantes abiertas y cerradas.
- [ ] Candidatos por etapa.
- [ ] Conversión entre etapas.
- [ ] Tiempo medio por etapa.
- [ ] Tiempo total de proceso.
- [ ] Evaluaciones pendientes de revisión.
- [ ] Ejecuciones de agentes exitosas y fallidas.
- [ ] Automatizaciones ejecutadas.
- [ ] Tiempo estimado ahorrado, con metodología explícita.

## Criterios

- [ ] Las métricas tienen definición documentada.
- [ ] Los filtros respetan organización y permisos.
- [ ] Los datos se calculan desde fuentes verificables.
- [ ] Se distingue dato real de estimación.
- [ ] Los gráficos tienen estados vacíos y accesibilidad.

---

# 16. Fase 13 — UX hardening & accessibility

**Objetivo:** elevar la interfaz a un estándar B2B profesional y coherente.

## Tareas

- [ ] Revisar navegación global.
- [ ] Unificar tokens de diseño.
- [ ] Unificar formularios, tablas, modales y feedback.
- [ ] Revisar responsive desktop/tablet/mobile.
- [ ] Implementar navegación por teclado.
- [ ] Revisar labels y nombres accesibles.
- [ ] Revisar contraste.
- [ ] Revisar focus states.
- [ ] Revisar mensajes de error.
- [ ] Revisar loading, empty, disabled y success states.
- [ ] Reducir renders innecesarios.
- [ ] Revisar tablas con grandes volúmenes.
- [ ] Realizar pruebas de usabilidad con tareas concretas.

## Criterio de salida

Los flujos principales pueden completarse sin ayuda externa, en desktop y mobile, y los componentes críticos cumplen criterios de accesibilidad acordados.

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
| 2 — Identidad | NOT_STARTED | — | — | — |
| 3 — Recruitment Core | NOT_STARTED | — | — | — |
| 4 — Document Intelligence | NOT_STARTED | — | — | — |
| 5 — Matching | NOT_STARTED | — | — | — |
| 6 — Agent Runtime | NOT_STARTED | — | — | — |
| 7 — Interview Assistant | NOT_STARTED | — | — | — |
| 8 — Automation Engine | NOT_STARTED | — | — | — |
| 9 — Integrations | NOT_STARTED | — | — | — |
| 10 — Control Center | NOT_STARTED | — | — | — |
| 11 — Simulation Lab | NOT_STARTED | — | — | — |
| 12 — Analytics | NOT_STARTED | — | — | — |
| 13 — UX & Accessibility | NOT_STARTED | — | — | — |
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
