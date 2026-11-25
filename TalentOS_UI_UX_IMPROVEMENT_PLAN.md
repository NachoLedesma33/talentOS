# TalentOS — UI/UX Redesign & Design System Implementation Plan

> **Documento:** `TalentOS_UI_UX_IMPROVEMENT_PLAN.md`  
> **Tipo:** Plan de rediseño visual, experiencia de usuario y sistema de componentes  
> **Producto:** TalentOS — Intelligent Recruitment Workspace  
> **Stack objetivo:** Next.js + TypeScript + Tailwind CSS + shadcn/ui  
> **Audiencia:** agentes de código, frontend engineers, product designers y reviewers  
> **Relación con otros documentos:** el SDD define el producto y sus reglas; el ROADMAP define el orden de construcción; este documento define cómo debe verse, sentirse y comportarse la experiencia de usuario.

---

## 1. Objetivo

Transformar la interfaz actual de TalentOS —hoy una pantalla básica con navegación mediante enlaces, escasa jerarquía visual y ausencia de patrones consistentes— en una aplicación SaaS B2B de reclutamiento inteligente, moderna, coherente, accesible y lista para demostración profesional.

El rediseño debe abarcar:

1. Una **landing pública** que presente TalentOS y conduzca al usuario hacia el registro o inicio de sesión.
2. Un **workspace autenticado** con navegación lateral, encabezado contextual y estructura consistente.
3. El diseño de **todas las áreas funcionales y rutas** de la aplicación, no solamente el dashboard.
4. Una experiencia completa de **vacantes, candidatos, pipeline, documentos, evaluación IA, agentes, automatizaciones, integraciones, entrevistas y analítica**.
5. Los estados vacíos, carga, error, permisos insuficientes, ausencia de resultados y páginas inexistentes.
6. Una página **404** propia, con recuperación de navegación.
7. Un sistema de diseño reutilizable basado en **shadcn/ui**, sin duplicar componentes ni introducir estilos particulares por pantalla.
8. Una implementación responsive, accesible y preparada para datos reales.

El rediseño es principalmente de presentación y experiencia. No debe alterar contratos API, reglas de negocio, modelo de permisos, lógica de matching ni comportamiento de los agentes.

---

## 2. Dirección visual aprobada

### 2.1 Concepto

**Minimal Enterprise SaaS — Neutral Workspace**

La referencia visual elegida utiliza una estética sobria, monocromática y de alta legibilidad:

- Fondo general claro.
- Superficies blancas o casi blancas.
- Bordes finos en lugar de sombras fuertes.
- Texto oscuro de alto contraste.
- Sidebar persistente y discreta.
- Navegación con iconos lineales.
- Acciones principales oscuras.
- Colores semánticos reservados para estados.
- Espaciado generoso, pero sin desperdiciar espacio útil.

La interfaz debe transmitir precisión, orden, confianza y madurez empresarial. No debe parecer un template genérico de administración ni una aplicación experimental de IA.

### 2.2 Paleta principal

Los siguientes valores son los tokens de marca y deben mantenerse como referencia principal:

| Token | Color | Uso |
|---|---|---|
| `primary` | `#18181B` | Botones principales, títulos, navegación activa, acciones de alto énfasis |
| `surface` | `#FAFAFA` | Fondo de superficies, paneles y áreas secundarias |
| `border` | `#E4E4E7` | Bordes, divisores, contornos de inputs y tablas |
| `muted-foreground` | `#71717A` | Texto secundario, descripciones, metadatos |
| `success` | `#16A34A` | Procesos correctos, validaciones, estados positivos |
| `warning` | `#D97706` | Advertencias, revisiones pendientes y estados parciales |

Colores complementarios funcionales:

| Token | Color | Uso |
|---|---|---|
| `background` | `#FFFFFF` | Fondo principal de páginas |
| `foreground` | `#18181B` | Texto principal |
| `card` | `#FFFFFF` | Tarjetas y diálogos |
| `input` | `#E4E4E7` | Bordes de controles |
| `secondary` | `#F4F4F5` | Superficies secundarias y hover |
| `accent` | `#F4F4F5` | Hover de elementos interactivos |
| `destructive` | `#DC2626` | Errores destructivos, eliminación y fallos |
| `info` | `#2563EB` | Información neutral y enlaces informativos |
| `ring` | `#A1A1AA` | Focus visible |
| `sidebar` | `#FAFAFA` | Fondo de navegación lateral |

**Reglas de uso:**

- `#18181B` es el color de acción primaria. No introducir índigo o violeta como segundo color de marca.
- El color `success` no debe utilizarse como decoración; representa un estado real.
- El color `warning` no debe confundirse con un error.
- Los estados `destructive` e `info` son complementarios de interfaz, no sustituyen la paleta principal.
- No comunicar estados únicamente mediante color: acompañar con texto, icono o descripción.
- Evitar gradientes decorativos, glassmorphism, sombras grandes, neón y fondos saturados.
- Las sombras deben ser sutiles y reservarse para popovers, menús, diálogos y superficies elevadas.

### 2.3 Modo oscuro

Preparar tokens para modo oscuro, pero no retrasar el rediseño principal por esta funcionalidad. El modo claro es la experiencia predeterminada.

La implementación debe utilizar variables semánticas de CSS y no colores hardcodeados en componentes. Así se podrá incorporar el tema oscuro sin reescribir cada pantalla.

---

## 3. Principios UX

1. **Orientación inmediata:** el usuario debe saber dónde está, qué puede hacer y cuál es el siguiente paso.
2. **Densidad controlada:** las pantallas de trabajo pueden mostrar mucha información, pero deben conservar jerarquía y legibilidad.
3. **Acciones previsibles:** crear, editar, archivar y eliminar deben tener ubicaciones y patrones consistentes.
4. **Progresive disclosure:** mostrar primero lo importante y dejar información avanzada en tabs, drawers o secciones expandibles.
5. **Feedback explícito:** toda acción asíncrona debe comunicar progreso, éxito o error.
6. **IA explicable:** mostrar evidencias, criterios, limitaciones y estado de revisión humana; nunca presentar un score como una verdad absoluta.
7. **Human-in-the-loop:** decisiones sensibles de selección no deben ejecutarse automáticamente sin la intervención y autorización que defina el producto.
8. **Accesibilidad:** teclado, foco visible, etiquetas, contraste y semántica correctos.
9. **Consistencia:** un mismo patrón debe resolver el mismo tipo de problema en todas las áreas.
10. **Responsive real:** adaptar la estructura, no simplemente reducir el ancho de escritorio.

---

## 4. Arquitectura de información y navegación

### 4.1 Estructura autenticada

Usar una aplicación con sidebar izquierda persistente y área principal.

**Sidebar propuesta:**

- Logo y nombre TalentOS.
- Workspace / organización activa.
- Resumen.
- Recruitment:
  - Vacantes
  - Candidatos
  - Pipeline
  - Documentos
  - Entrevistas
- Intelligence:
  - Evaluación
  - Agentes
  - Automatizaciones
- Operaciones:
  - Integraciones
  - Analítica
- Configuración:
  - Organización
  - Miembros y roles
  - Preferencias
  - Auditoría (si está disponible para el rol)

La navegación debe agruparse por secciones, con separadores y labels pequeños. La página activa debe tener fondo `secondary`, texto `foreground` y un indicador accesible. No depender solo del cambio de color.

### 4.2 Header contextual

El encabezado superior debe incluir:

- Breadcrumb o título contextual.
- Búsqueda global / command menu con `Ctrl+K` o `⌘K`.
- Notificaciones, solo si existe funcionalidad real.
- Selector de organización cuando el usuario pertenezca a más de una.
- Menú de usuario con perfil, preferencias y cerrar sesión.

No mostrar controles que todavía no tengan comportamiento funcional. Si una característica no está implementada, no simularla como operativa.

### 4.3 Responsive

- Desktop: sidebar expandida.
- Tablet: sidebar colapsable o icon rail, con tooltip accesible.
- Mobile: navegación lateral en `Sheet`; header compacto.
- Tablas anchas: scroll horizontal controlado o vistas compactas por filas/tarjetas cuando la legibilidad lo requiera.
- Formularios largos: una columna en mobile, dos columnas solo cuando la relación entre campos sea clara.

---

## 5. Mapa completo de rutas y pantallas

Los paths siguientes son una propuesta de organización de frontend. Antes de implementarlos, contrastar con el router existente y conservar las rutas públicas ya utilizadas por enlaces, tests o integraciones. Si el proyecto ya tiene convenciones diferentes, adaptar el mapa sin romper compatibilidad.

### 5.1 Rutas públicas

| Ruta sugerida | Pantalla | Objetivo |
|---|---|---|
| `/` | Landing | Presentar TalentOS y convertir visitas en registros o accesos |
| `/login` | Iniciar sesión | Autenticación |
| `/register` | Crear cuenta | Alta de usuario |
| `/forgot-password` | Recuperar contraseña | Solicitar recuperación |
| `/reset-password` | Restablecer contraseña | Completar recuperación |
| `/invite/[token]` | Aceptar invitación | Unirse a una organización |
| `/terms` | Términos | Información legal |
| `/privacy` | Privacidad | Tratamiento de datos |

### 5.2 Workspace autenticado

| Ruta sugerida | Pantalla | Elementos principales |
|---|---|---|
| `/app` | Resumen | KPIs, actividad, evaluaciones recientes, acciones rápidas |
| `/app/vacancies` | Listado de vacantes | Data table, filtros, búsqueda, crear vacante |
| `/app/vacancies/new` | Crear vacante | Formulario por secciones y vista previa |
| `/app/vacancies/[id]` | Detalle de vacante | Resumen, requisitos, candidatos, actividad |
| `/app/vacancies/[id]/edit` | Editar vacante | Formulario precompletado |
| `/app/candidates` | Listado de candidatos | Tabla, filtros, tags y acciones |
| `/app/candidates/new` | Alta manual | Formulario de perfil |
| `/app/candidates/[id]` | Perfil de candidato | Resumen, CV, experiencia, evaluaciones, actividad |
| `/app/pipeline` | Pipeline | Kanban por etapas, filtros y acciones |
| `/app/documents` | Documentos | CVs, archivos, estado de procesamiento |
| `/app/evaluations` | Evaluaciones | Resultados, criterios, evidencias y revisiones |
| `/app/evaluations/[id]` | Detalle de evaluación | Desglose de matching, evidencia y auditoría |
| `/app/agents` | Centro de agentes | Agentes disponibles, estado y ejecuciones |
| `/app/agents/[id]` | Detalle de agente | Configuración, herramientas permitidas, historial |
| `/app/automations` | Automatizaciones | Flujos, disparadores, estado y ejecuciones |
| `/app/automations/new` | Crear automatización | Constructor guiado |
| `/app/automations/[id]` | Detalle de automatización | Pasos, historial, fallos y configuración |
| `/app/integrations` | Integraciones | Catálogo, conexión y estado |
| `/app/integrations/[provider]` | Detalle de integración | Configuración, permisos, eventos y webhooks |
| `/app/interviews` | Entrevistas | Calendario/listado y próximos pasos |
| `/app/interviews/[id]` | Detalle de entrevista | Participantes, guía, notas y feedback |
| `/app/analytics` | Analítica | Métricas, tendencias, filtros y exportación |
| `/app/settings` | Preferencias | Perfil y preferencias personales |
| `/app/settings/organization` | Organización | Datos y configuración de workspace |
| `/app/settings/members` | Miembros | Invitaciones, roles y estados |
| `/app/settings/security` | Seguridad | Sesiones y controles disponibles |
| `/app/settings/audit-log` | Auditoría | Eventos relevantes y filtros |

No todas las rutas tienen que estar habilitadas en el primer release. La lista es el inventario de diseño objetivo. Ocultar o marcar como no disponible cualquier sección que aún no tenga backend funcional.

### 5.3 Rutas de sistema

| Ruta / estado | Tratamiento |
|---|---|
| `not-found.tsx` / 404 | Página de recurso o ruta inexistente |
| 401 | Sesión ausente o expirada |
| 403 | Usuario autenticado sin permisos |
| 500 | Error inesperado |
| Error boundary | Recuperación ante error de renderizado |
| Loading | Skeleton correspondiente a la pantalla |
| Empty state | Explicación y acción siguiente |
| Offline / network error | Mensaje y reintento cuando corresponda |

---

## 6. Landing pública

### 6.1 Objetivo

La landing debe ser una entrada convincente al producto. Tiene que explicar en pocos segundos qué resuelve TalentOS, para quién está pensado y cómo la IA ayuda al proceso de reclutamiento sin quitar el control a las personas.

No debe ser un dashboard público ni una página con texto genérico de marketing. Debe comunicar una propuesta concreta y conducir a una acción principal.

### 6.2 Estructura

#### A. Navbar

- Logo TalentOS.
- Enlaces: Producto, Capacidades, Cómo funciona, Seguridad.
- Acción secundaria: Iniciar sesión.
- Acción primaria: Comenzar / Crear cuenta.
- Mobile: menú en Sheet.
- Navbar sticky solo si aporta orientación; evitar ocupar demasiado alto.

#### B. Hero

Propuesta de copy inicial, editable por producto:

**Eyebrow:** `RECRUITMENT, WITH INTELLIGENCE`

**Título:**  
`Encontrá el talento correcto. Con mejores decisiones.`

**Descripción:**  
`TalentOS centraliza vacantes, candidatos y evaluaciones en un solo workspace. Utilizá IA para organizar información, encontrar coincidencias basadas en evidencias y mantener cada decisión bajo control humano.`

**CTA primaria:** `Crear mi workspace`

**CTA secundaria:** `Explorar la plataforma`

El CTA debe llevar a una ruta funcional. No prometer pruebas gratuitas, integraciones o capacidades que no existan.

#### C. Hero visual

Crear una composición de producto, no una ilustración abstracta de cerebro o robot:

- Mockup realista del dashboard.
- Una tarjeta de vacante activa.
- Un perfil de candidato.
- Una evaluación con criterios y evidencias.
- Un pequeño indicador de estado del proceso.

El mockup debe usar datos ficticios claramente demostrativos. No utilizar información personal real. Si se implementa como componentes HTML, mantenerlo responsive y accesible; no convertirlo en una imagen estática que parezca interactiva.

#### D. Problema y propuesta de valor

Tres bloques:

1. **Todo el proceso en un lugar:** vacantes, candidatos, documentos y entrevistas.
2. **Evaluaciones explicables:** coincidencias justificadas mediante requisitos y evidencias.
3. **Automatización con supervisión:** agentes y flujos que ayudan al equipo sin ocultar qué acciones se ejecutan.

#### E. Cómo funciona

Presentar un flujo de cuatro pasos:

1. Crear una vacante y definir criterios.
2. Incorporar candidatos y procesar sus documentos.
3. Revisar coincidencias y evidencias.
4. Coordinar entrevistas y seguir el pipeline.

#### F. Capacidades

Cards para:

- Recruitment Core.
- Document Intelligence.
- Evidence-Based Matching.
- Agent Workspace.
- Automations & Integrations.
- Analytics & Auditability.

Cada card debe enlazar a una sección o explicación real. No crear enlaces decorativos.

#### G. Confianza y control

Explicar con precisión:

- Revisión humana de resultados.
- Evidencias asociadas a las evaluaciones.
- Permisos por organización y rol, si están implementados.
- Registro de actividad y trazabilidad, si están implementados.
- Tratamiento responsable de información personal.

No afirmar certificaciones, cumplimiento normativo ni garantías de seguridad que no hayan sido verificadas.

#### H. CTA final

Título sugerido: `Un proceso de selección más claro empieza acá.`

Botón: `Crear mi workspace`

#### I. Footer

- Marca y descripción breve.
- Producto.
- Recursos.
- Legal: Privacidad y Términos.
- Contacto, solo con un canal real.
- Copyright dinámico.

### 6.3 Diseño del hero

- Fondo `#FFFFFF` o `#FAFAFA`.
- Texto principal `#18181B`.
- CTA oscuro `#18181B` con texto blanco.
- CTA secundario outline con borde `#E4E4E7`.
- Acentos de éxito y aviso únicamente dentro de la demostración de producto.
- Evitar gradientes saturados, blobs, brillos y efectos futuristas.
- El hero debe tener una jerarquía tipográfica fuerte y un ancho de lectura controlado.
- Desktop: composición de dos columnas, copy a la izquierda y visual del producto a la derecha.
- Mobile: copy, CTA y mockup apilados.

### 6.4 SEO y metadata

- Metadata por página.
- Título y descripción específicos.
- Open Graph básico.
- Favicon y manifest.
- Heading hierarchy semántica.
- Sitemap y robots cuando corresponda.
- No incluir datos sensibles ni información privada en metadata.

---

## 7. Diseño de cada módulo autenticado

### 7.1 Resumen / Dashboard

**Objetivo:** dar una visión accionable del estado del proceso de selección.

Estructura:

1. Título `Resumen` y descripción breve.
2. Selector de período si la métrica lo soporta.
3. CTA contextual `Nueva vacante`.
4. KPI cards:
   - Vacantes activas.
   - Candidatos en proceso.
   - Evaluaciones pendientes.
   - Entrevistas próximas.
5. Evaluaciones recientes en tabla.
6. Actividad reciente.
7. Atajos a tareas pendientes.

Reglas:

- Mostrar únicamente métricas respaldadas por datos reales.
- Evitar números inventados en producción.
- Diferenciar cero datos de error de carga.
- Skeletons durante carga.
- Empty state que invite a crear la primera vacante o incorporar candidatos.

### 7.2 Vacantes

**Listado:**

- Título y CTA `Nueva vacante`.
- Búsqueda por nombre, equipo o identificador.
- Filtros por estado, ubicación, modalidad y fecha, solo si existen esos campos.
- Tabla con nombre, estado, candidatos, responsable, fecha y menú de acciones.
- Paginación real y ordenamiento consistente.
- Vistas de tabla y tarjetas solo si ambas aportan valor.

**Crear / editar:**

Organizar el formulario por bloques:

1. Información general.
2. Descripción del puesto.
3. Responsabilidades.
4. Requisitos obligatorios.
5. Requisitos deseables.
6. Ubicación y modalidad.
7. Configuración del proceso.
8. Criterios de evaluación.

UX:

- Validación inline.
- Campos obligatorios identificados.
- Guardado y confirmación.
- Confirmación al abandonar si hay cambios sin guardar.
- No utilizar un único textarea enorme para toda la definición de la vacante.

**Detalle:**

- Header con título, estado y acciones.
- Tabs: Overview, Candidatos, Requisitos, Actividad.
- Resumen de requisitos.
- Pipeline asociado.
- Actividad reciente.
- CTA para incorporar candidatos.

### 7.3 Candidatos

**Listado:**

- Búsqueda por nombre, email o habilidades.
- Filtros por etapa, vacante, origen y estado de evaluación, si están disponibles.
- Tabla con candidato, experiencia/resumen, vacante asociada, etapa, evaluación y última actividad.
- Acciones por fila mediante DropdownMenu.
- Selección múltiple únicamente para acciones masivas seguras y permitidas.

**Perfil:**

- Header con nombre, contacto y estado.
- Acciones: editar, mover de etapa, asociar a vacante, agregar nota.
- Tabs:
  - Resumen.
  - Experiencia.
  - Documentos.
  - Evaluaciones.
  - Entrevistas.
  - Actividad.
- Timeline de eventos.
- CV visible mediante preview seguro o descarga autorizada.
- Separar información declarada por el candidato de información extraída automáticamente.

**Alta manual:**

- Datos personales mínimos necesarios.
- Experiencia.
- Skills.
- Fuente del candidato.
- Adjuntar CV.
- Consentimiento y base de tratamiento según las reglas del producto y jurisdicción aplicable.

### 7.4 Pipeline

- Kanban por etapas configuradas.
- Columnas con cantidad de candidatos.
- Tarjetas compactas con nombre, vacante, fecha y estado relevante.
- Filtros por vacante, responsable y período.
- Drag-and-drop solo si la API soporta cambios de etapa y permisos.
- Al mover una tarjeta, mostrar confirmación o feedback y revertir visualmente si falla.
- No ejecutar acciones externas como rechazos o notificaciones sin confirmación y autorización.
- Alternativa accesible al drag-and-drop: menú `Mover a etapa`.

### 7.5 Documentos

- Listado de CVs y archivos.
- Estado de procesamiento: pendiente, procesando, completado, fallido.
- Nombre, candidato, tipo, fecha, tamaño y resultado.
- Filtros por estado y tipo.
- Preview con controles de zoom y descarga autorizada.
- Errores de extracción con explicación y posibilidad de reintento.
- No renderizar HTML o archivos no confiables sin sanitización y controles apropiados.

### 7.6 Evaluación / Matching

Esta es una de las áreas que más debe diferenciar TalentOS.

**Listado:**

- Candidato.
- Vacante.
- Estado de evaluación.
- Nivel de coincidencia, solo si el motor lo calcula.
- Fecha.
- Estado de revisión humana.

**Detalle:**

- Resumen del resultado.
- Criterios evaluados.
- Evidencias que respaldan cada criterio.
- Información faltante o no verificable.
- Señales de incertidumbre.
- Fuente del dato.
- Versión del modelo o configuración de evaluación, cuando esté disponible.
- Historial y estado de revisión.

No presentar el score como una recomendación automática definitiva. No ocultar criterios, ni inferir atributos sensibles. Incluir una advertencia contextual sobre la necesidad de revisión humana cuando corresponda.

### 7.7 Agentes

**Listado / centro de agentes:**

- Nombre y descripción.
- Función.
- Estado habilitado/deshabilitado.
- Última ejecución.
- Resultado de última ejecución.
- Herramientas permitidas.
- CTA para ver detalle.

**Detalle:**

- Resumen y propósito.
- Configuración visible y editable según permisos.
- Herramientas y scopes autorizados.
- Historial de ejecuciones.
- Inputs y outputs sanitizados.
- Tokens, latencia o costo solo cuando se midan realmente.
- Errores y trazas relevantes.
- Acción para habilitar/deshabilitar con confirmación.

No mostrar chain-of-thought ni razonamiento privado del modelo. Mostrar resultados, decisiones operativas, evidencias, logs y explicaciones aptas para el usuario.

### 7.8 Automatizaciones

**Listado:**

- Nombre.
- Disparador.
- Última ejecución.
- Estado.
- Resultado.
- Responsable.

**Constructor inicial:**

Implementar primero un builder guiado y legible antes de un editor visual complejo:

1. Elegir trigger.
2. Definir condiciones.
3. Seleccionar acciones.
4. Revisar permisos.
5. Probar con datos de ejemplo.
6. Guardar y activar.

**Detalle:**

- Pasos y conexiones.
- Historial de ejecuciones.
- Estado por paso.
- Errores y reintentos.
- Pausar, activar y duplicar según permisos.

Las acciones externas deben requerir scopes y confirmaciones apropiadas. Diferenciar claramente simulación de ejecución real.

### 7.9 Integraciones

- Catálogo de proveedores realmente soportados.
- Estado: conectado, desconectado, requiere atención.
- Última sincronización.
- Permisos concedidos.
- Acciones conectar, configurar y desconectar.
- Configuración de webhooks con secreto oculto.
- No mostrar tokens completos luego de guardarlos.
- Confirmación antes de desconectar o regenerar credenciales.
- Pantalla de error que explique cómo recuperar la conexión sin exponer datos sensibles.

### 7.10 Entrevistas

- Vista de agenda/listado.
- Próximas entrevistas.
- Candidato, vacante, fecha, participantes y estado.
- Detalle con guía, notas y feedback.
- Formulario de feedback con criterios definidos.
- Zona horaria visible.
- No afirmar que existe sincronización con calendarios si no está implementada.

### 7.11 Analítica

- Filtros por rango temporal y vacante.
- KPIs con definición y período.
- Gráficos con leyendas, unidades y tooltips.
- Embudo por etapas.
- Tiempo por etapa.
- Fuentes de candidatos.
- Evolución de vacantes y entrevistas.
- Exportación solo cuando exista implementación real.

Cada visualización debe incluir estados loading, empty y error. Evitar gráficos 3D, efectos decorativos y métricas sin definición.

### 7.12 Organización y miembros

- Datos de organización.
- Lista de miembros.
- Estado de invitaciones.
- Roles y permisos.
- Acciones según rol.
- Confirmación para revocar acceso.
- Mostrar claramente a qué organización se aplican los cambios.

### 7.13 Auditoría

- Tabla de eventos relevantes.
- Actor, acción, recurso, fecha y resultado.
- Filtros por usuario, tipo de evento y rango temporal.
- Detalle expandible con metadata no sensible.
- No permitir modificar o eliminar eventos de auditoría desde la UI.

---

## 8. Autenticación y onboarding

### 8.1 Login

- Layout centrado, limpio y consistente con la marca.
- Logo y nombre.
- Título y explicación breve.
- Email y contraseña.
- Mostrar/ocultar contraseña.
- Recordarme solo si existe soporte.
- Recuperar contraseña.
- CTA de acceso.
- Mensajes de error claros, sin filtrar si una cuenta existe cuando eso pueda facilitar enumeración.
- Loading y bloqueo temporal según respuesta del backend.

### 8.2 Registro

- Nombre.
- Email.
- Contraseña y requisitos.
- Confirmación legal.
- Estado de envío.
- Confirmación de cuenta según el mecanismo implementado.

### 8.3 Onboarding

Después de autenticarse:

1. Verificar si el usuario pertenece a una organización.
2. Si tiene organizaciones, permitir elegir workspace.
3. Si no tiene, ofrecer crear organización o aceptar invitación.
4. Completar configuración inicial mínima.
5. Mostrar checklist de primeros pasos.

No dejar al usuario en un dashboard vacío sin explicación. Si no hay organización disponible, mostrar un estado dedicado con acciones reales.

### 8.4 Sesión expirada

- Explicar que la sesión expiró.
- Ofrecer volver a iniciar sesión.
- Preservar el destino original cuando sea seguro.
- No mostrar errores internos ni tokens.

---

## 9. Página 404 y estados de error

### 9.1 Página 404

Diseño propuesto:

- Marca TalentOS.
- Ilustración tipográfica discreta `404`.
- Título: `No encontramos esta página`.
- Descripción: `El enlace puede estar desactualizado o la página ya no existe.`
- CTA primaria: `Volver al resumen`.
- CTA secundaria: `Ir al inicio`.
- Link opcional: `Volver a la página anterior`.
- No mostrar stack traces, rutas internas ni identificadores sensibles.

La página debe funcionar tanto para visitantes como para usuarios autenticados:

- Visitante: `Ir al inicio` lleva a `/`.
- Usuario autenticado: `Volver al resumen` lleva a `/app`.
- Si el contexto de sesión no está disponible, usar una ruta pública segura.

### 9.2 401 — No autenticado

- Mensaje breve.
- CTA para iniciar sesión.
- Conservar return URL validada.
- No realizar loops de redirección.

### 9.3 403 — Sin permisos

- Título: `No tenés acceso a esta sección`.
- Explicar que el usuario no cuenta con permisos suficientes.
- CTA para volver al workspace.
- No sugerir que puede resolverlo si no tiene un administrador disponible.

### 9.4 500 — Error inesperado

- Mensaje claro.
- ID de incidente si el backend lo proporciona.
- Acción reintentar.
- Acción volver al resumen.
- Detalles técnicos únicamente en logs protegidos.

### 9.5 Error de red

- Avisar que no se pudo conectar.
- Reintentar.
- Mantener datos de formulario no sensibles cuando sea seguro.
- No informar falsamente que una operación se guardó.

---

## 10. Sistema de diseño con shadcn/ui

### 10.1 Instalación y configuración

Usar shadcn/ui como base de componentes, no como una plantilla visual que deba aceptarse sin adaptación.

Verificar la configuración real del repositorio antes de instalar o actualizar dependencias. No reemplazar archivos de configuración sin revisar su contenido.

Base prevista:

- Next.js App Router, si coincide con la arquitectura actual.
- TypeScript strict.
- Tailwind CSS.
- shadcn/ui.
- Radix UI a través de los componentes de shadcn.
- Lucide React.
- React Hook Form.
- Zod.
- TanStack Table para tablas complejas.
- Recharts para gráficos si ya forma parte de la estrategia del proyecto.
- Sonner para notificaciones toast.

No instalar una segunda librería que resuelva lo mismo sin justificación técnica.

### 10.2 Componentes base

**Layout:**

- `AppSidebar`
- `AppHeader`
- `AppShell`
- `PageHeader`
- `PageContainer`
- `Breadcrumbs`
- `OrganizationSwitcher`
- `UserMenu`
- `MobileNavigation`

**Datos:**

- `DataTable`
- `DataTableToolbar`
- `DataTablePagination`
- `FilterBar`
- `SearchInput`
- `EmptyState`
- `LoadingState`
- `ErrorState`
- `StatusBadge`
- `MetricCard`

**Formularios:**

- `FormField`
- `FormSection`
- `FormActions`
- `ConfirmDialog`
- `UnsavedChangesDialog`
- `FileUploader`

**Recruitment:**

- `CandidateAvatar`
- `CandidateCard`
- `CandidateProfileHeader`
- `VacancyStatusBadge`
- `PipelineColumn`
- `PipelineCard`
- `EvaluationScore`
- `EvidenceList`
- `ActivityTimeline`
- `InterviewCard`

**AI Operations:**

- `AgentStatus`
- `AgentRunCard`
- `ExecutionTimeline`
- `AutomationStatus`
- `IntegrationStatus`
- `EvidencePanel`
- `HumanReviewBanner`

### 10.3 Componentes shadcn recomendados

Instalar solo los que se utilicen:

- Button
- Card
- Badge
- Avatar
- Separator
- Sheet
- Dialog
- AlertDialog
- DropdownMenu
- NavigationMenu
- Sidebar (si la versión instalada de shadcn la ofrece y encaja con el layout)
- Breadcrumb
- Command
- Input
- Textarea
- Select
- Checkbox
- RadioGroup
- Switch
- Tabs
- Tooltip
- Popover
- Calendar
- Table
- Skeleton
- Alert
- Progress
- ScrollArea
- Collapsible
- Accordion
- Form
- Sonner

### 10.4 Reglas de componentes

- Preferir composición a componentes gigantes.
- Separar componentes de dominio de componentes genéricos.
- No duplicar variantes de botones, badges o inputs.
- Mantener props tipadas y acotadas.
- Evitar `any`.
- No acoplar componentes visuales directamente a fetches o servicios.
- La UI recibe estados y callbacks; los hooks y servicios gestionan datos.
- Evitar componentes genéricos con decenas de props condicionales.
- No crear abstracciones prematuras: extraer cuando exista reutilización real.
- Los componentes compartidos deben tener ejemplos de uso y tests cuando su complejidad lo amerite.

---

## 11. Tokens y configuración visual

Definir variables semánticas CSS en un único punto y mapearlas a Tailwind/shadcn.

Ejemplo conceptual de tokens:

```css
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;

  --card: 0 0% 100%;
  --card-foreground: 240 10% 3.9%;

  --primary: 240 3.7% 11%;
  --primary-foreground: 0 0% 98%;

  --secondary: 240 4.8% 95.9%;
  --secondary-foreground: 240 5.9% 10%;

  --muted: 240 4.8% 95.9%;
  --muted-foreground: 240 3.8% 46.1%;

  --accent: 240 4.8% 95.9%;
  --accent-foreground: 240 5.9% 10%;

  --destructive: 0 72.2% 50.6%;
  --border: 240 5.9% 90%;
  --input: 240 5.9% 90%;
  --ring: 240 3.8% 46.1%;

  --radius: 0.625rem;
}
```

Los valores anteriores son una traducción HSL aproximada de la paleta indicada. Los valores hex originales de la sección 2.2 son la referencia de marca. Validar el resultado visual en navegador y ajustar las variables para que los colores renderizados coincidan con la paleta objetivo.

Tokens de estado adicionales:

```css
:root {
  --success: #16A34A;
  --warning: #D97706;
  --info: #2563EB;
  --danger: #DC2626;
}
```

No repetir hex en decenas de componentes. Usar tokens semánticos.

---

## 12. Tipografía, iconografía y espaciado

### Tipografía

- Geist Sans o Inter.
- Una sola familia principal.
- Pesos 400, 500, 600 y 700.
- Títulos con jerarquía clara.
- Texto secundario con contraste suficiente.
- Números tabulares para métricas, fechas y scores.

### Iconografía

- Lucide React.
- Trazo consistente.
- Tamaños normalizados: 16, 18 y 20 px según contexto.
- Los iconos decorativos deben ser `aria-hidden`.
- No usar emoji como iconos de navegación o estados.

### Espaciado

Definir escala coherente basada en múltiplos de 4 px:

- 4 px: micro separación.
- 8 px: elementos relacionados.
- 12–16 px: controles y contenido interno.
- 20–24 px: secciones.
- 32 px: separación de bloques principales.
- 40–48 px: encabezados y grandes secciones.

### Bordes y radios

- Bordes finos `#E4E4E7`.
- Radios moderados y consistentes.
- Cards con radio medio.
- Inputs con radio moderado.
- Pills solo para estados y etiquetas.
- No encerrar cada pequeño bloque en una card; usar divisores y espacio cuando sea suficiente.

---

## 13. Patrones de interacción

### 13.1 Botones

- Primary: fondo `#18181B`, texto blanco.
- Secondary: fondo `#F4F4F5`.
- Outline: fondo transparente y borde `#E4E4E7`.
- Ghost: sin fondo permanente.
- Destructive: rojo semántico.
- Estados: default, hover, focus-visible, active, disabled y loading.

Cada botón debe tener una acción real. No incluir CTAs visuales sin destino o callback.

### 13.2 Tablas

- Header distinguible.
- Filas con altura consistente.
- Hover sutil.
- Selección visible.
- Columnas prioritarias adaptadas a viewport.
- Acciones de fila agrupadas.
- Ordenamiento con indicador.
- Filtros persistentes en URL cuando sea apropiado.
- Paginación conectada al backend, no simulada.

### 13.3 Formularios

- Label visible.
- Texto de ayuda cuando haga falta.
- Error debajo del campo.
- Validación en cliente y servidor.
- Botón de guardar con loading.
- Evitar formularios largos sin agrupación.
- Confirmar acciones irreversibles.

### 13.4 Modales y drawers

- Dialog para confirmaciones o tareas pequeñas.
- Sheet para formularios laterales y detalles rápidos.
- Página completa para flujos complejos.
- Cerrar con Escape cuando sea apropiado.
- Gestionar foco y devolverlo al disparador.

### 13.5 Notificaciones

- Sonner para feedback breve.
- Alert inline para errores que requieren contexto.
- No utilizar toast como único canal para información crítica.
- Evitar mensajes genéricos como `Algo salió mal` cuando se pueda explicar el problema sin filtrar datos internos.

---

## 14. Estados universales por pantalla

Cada pantalla conectada a datos debe definir explícitamente:

1. **Initial loading:** skeleton con la forma de la UI final.
2. **Refreshing:** indicador discreto sin borrar todo el contenido si no es necesario.
3. **Success:** datos visibles.
4. **Empty:** explicación y acción útil.
5. **Filtered empty:** aclarar que los filtros no devolvieron resultados y permitir limpiarlos.
6. **Error:** mensaje y reintento.
7. **Unauthorized:** acceso denegado o sesión expirada.
8. **Partial failure:** mostrar qué parte falló y qué sigue disponible.
9. **Mutation pending:** bloquear duplicación de acciones.
10. **Mutation success/failure:** feedback y actualización coherente.

No utilizar datos mock como si fueran datos reales. Los datos de demostración deben estar aislados, etiquetados y ser fácilmente reemplazables.

---

## 15. Accesibilidad

Objetivo: WCAG 2.2 AA en los flujos principales, sujeto a validación.

- Contraste de texto y controles.
- Navegación completa por teclado.
- Focus visible.
- Orden lógico de tabulación.
- Labels asociados a controles.
- Errores anunciados correctamente.
- Dialogs con foco gestionado.
- No depender solo de color.
- Tablas con headers semánticos.
- Gráficos con resumen textual o tabla equivalente.
- Respetar `prefers-reduced-motion`.
- Targets táctiles suficientes.
- Evitar texto demasiado pequeño.
- Alt text útil en imágenes informativas.

---

## 16. Responsive y breakpoints

Diseñar mobile-first, validando al menos:

- Mobile: 360–390 px.
- Mobile amplio: 430 px.
- Tablet: 768 px.
- Desktop: 1280 px.
- Desktop amplio: 1440 px o superior.

No fijar anchos que provoquen overflow. Las tablas complejas pueden tener scroll horizontal dentro de su contenedor, pero el documento completo no debe desbordarse.

---

## 17. Arquitectura frontend recomendada

Adaptar esta organización al repositorio existente, sin mover archivos masivamente antes de entender la estructura real.

```text
src/
  app/
    (marketing)/
      page.tsx
      terms/
      privacy/
    (auth)/
      login/
      register/
      forgot-password/
      reset-password/
    (workspace)/
      app/
        layout.tsx
        page.tsx
        vacancies/
        candidates/
        pipeline/
        documents/
        evaluations/
        agents/
        automations/
        integrations/
        interviews/
        analytics/
        settings/
    not-found.tsx
    error.tsx
    global-error.tsx

  components/
    ui/                  # shadcn/ui
    layout/
    navigation/
    feedback/
    data-display/
    forms/

  features/
    dashboard/
    vacancies/
    candidates/
    pipeline/
    documents/
    evaluations/
    agents/
    automations/
    integrations/
    interviews/
    analytics/
    organization/

  hooks/
  lib/
    api/
    auth/
    schemas/
    utils/
  styles/
```

Si el repositorio utiliza otra estructura, preservar su arquitectura y adaptar las responsabilidades. No crear un segundo sistema de routing.

### Separación de responsabilidades

- `app`: routing, layouts y composición de páginas.
- `features`: componentes, hooks y lógica de presentación específica de cada dominio.
- `components/ui`: primitivas visuales reutilizables.
- `components/layout`: shell y navegación.
- `lib/api`: cliente HTTP y manejo de errores.
- `lib/schemas`: esquemas compartidos de validación cuando corresponda.
- Backend: conserva validación, autorización y reglas de negocio como fuente de verdad.

---

## 18. Seguridad de UX

- Ocultar acciones no autorizadas, pero validar siempre permisos en backend.
- Nunca confiar en la UI como mecanismo de autorización.
- No exponer tokens, secretos ni datos sensibles en pantalla o logs del navegador.
- Sanitizar contenido externo.
- No ejecutar contenido arbitrario recibido desde documentos.
- Confirmar operaciones destructivas.
- No incluir PII en URLs, analytics ni mensajes de error.
- Restringir previews y descargas a usuarios autorizados.
- Evitar que el command menu revele recursos que el usuario no puede consultar.
- Mantener separación entre organizaciones en todas las vistas.

---

## 19. Performance

- Evitar cargar todos los módulos en el primer render.
- Lazy-load de pantallas y visualizaciones pesadas.
- Paginación y filtros server-side cuando el volumen lo requiera.
- Debounce en búsqueda.
- Skeletons para evitar saltos de layout.
- Evitar renders innecesarios en tablas y Kanban.
- Optimizar previews de documentos.
- Usar imágenes optimizadas.
- No cargar bibliotecas de gráficos en rutas que no las utilizan.
- Medir antes de optimizar prematuramente.

---

## 20. Testing y validación visual

### 20.1 Tests de componentes

- Estados de Button.
- FormField y validaciones.
- StatusBadge.
- EmptyState, LoadingState y ErrorState.
- Sidebar y navegación.
- Dialogs y Sheets.
- DataTable: sorting, filtering y pagination.

### 20.2 Tests de rutas

Verificar:

- Landing pública.
- Login y registro.
- Acceso a workspace.
- Redirect sin sesión.
- Protección por rol.
- Navegación a cada módulo.
- 404.
- 401 / 403.
- Error boundary.

### 20.3 Tests E2E

Flujos mínimos:

1. Visitante abre landing y llega a login.
2. Usuario inicia sesión.
3. Usuario sin organización completa onboarding.
4. Usuario crea una vacante.
5. Usuario incorpora candidato.
6. Usuario consulta documento procesado.
7. Usuario revisa una evaluación y sus evidencias.
8. Usuario mueve candidato en pipeline.
9. Usuario revisa ejecución de agente.
10. Usuario consulta automatización.
11. Usuario abre una ruta inexistente y recupera navegación.

Usar fixtures y datos sintéticos. No utilizar datos personales reales en pruebas.

### 20.4 Visual QA

Capturar screenshots en desktop, tablet y mobile para:

- Landing.
- Dashboard.
- Listado de vacantes.
- Detalle de candidato.
- Pipeline.
- Evaluación.
- Agentes.
- Automatizaciones.
- Integraciones.
- Analítica.
- Login.
- 404.

Comparar consistencia de spacing, tipografía, alineación, contraste, overflow y estados.

---

## 21. Estrategia de implementación

No rediseñar todo en un único cambio gigante. Trabajar por entregas pequeñas y verificables.

### Entrega A — Fundaciones

- Inspeccionar stack, router y estructura actual.
- Inventariar todas las rutas existentes.
- Configurar tokens de diseño.
- Configurar shadcn/ui.
- Crear primitives y layout base.
- Definir responsive y tipografía.

### Entrega B — Landing y autenticación

- Landing completa.
- Login.
- Registro.
- Recuperación de contraseña.
- Invitaciones.
- Onboarding.
- Metadata y estados de formularios.

### Entrega C — Workspace

- Sidebar.
- Header.
- Breadcrumbs.
- Command menu.
- Organización activa.
- Menú de usuario.
- Responsive navigation.

### Entrega D — Recruitment Core

- Dashboard.
- Vacantes.
- Candidatos.
- Pipeline.
- Documentos.

### Entrega E — AI Workspace

- Evaluaciones.
- Evidencias.
- Agentes.
- Ejecuciones.
- Automatizaciones.

### Entrega F — Operaciones

- Integraciones.
- Webhooks.
- Entrevistas.
- Analítica.
- Organización.
- Miembros.
- Auditoría.

### Entrega G — Estados globales y hardening

- 404.
- 401 / 403 / 500.
- Error boundaries.
- Empty, loading y error states.
- Accesibilidad.
- Responsive QA.
- Performance.
- E2E y visual QA.

---

## 22. Criterios de aceptación globales

El rediseño se considera aceptado cuando:

- [ ] La landing comunica el producto y tiene CTAs funcionales.
- [ ] Existe una identidad visual coherente basada en la paleta aprobada.
- [ ] El workspace tiene navegación consistente y responsive.
- [ ] Todas las rutas existentes fueron inventariadas y tienen tratamiento visual.
- [ ] Cada módulo tiene listado, detalle y formularios necesarios según sus capacidades reales.
- [ ] No existen enlaces de navegación muertos.
- [ ] No existen botones decorativos sin acción.
- [ ] Todos los estados de carga, vacío y error están contemplados.
- [ ] Existe una página 404 propia.
- [ ] 401, 403 y 500 tienen experiencias diferenciadas.
- [ ] Los componentes compartidos utilizan shadcn/ui y tokens centralizados.
- [ ] No se duplican patrones visuales sin motivo.
- [ ] Las pantallas funcionan en mobile, tablet y desktop.
- [ ] Los flujos principales son utilizables por teclado.
- [ ] Las evaluaciones IA muestran evidencias y límites, no solo puntuaciones.
- [ ] La UI no reemplaza ni debilita la autorización del backend.
- [ ] Los datos mock están claramente aislados de los datos reales.
- [ ] Los tests existentes siguen pasando.
- [ ] Se agregaron tests para los nuevos componentes y flujos críticos.
- [ ] Se realizó revisión visual de todas las rutas implementadas.

---

## 23. Reglas de trabajo para OpenCode / coding agents

### Antes de modificar

1. Leer SDD, ROADMAP y este documento.
2. Inspeccionar el repositorio y detectar stack real, router, componentes y estilos.
3. Identificar rutas implementadas y rutas planificadas.
4. Inspeccionar contratos API y modelos antes de diseñar formularios o tablas.
5. Elaborar un inventario de gaps entre la UI actual y este documento.
6. Proponer cambios por lotes y detectar riesgos de regresión.

### Durante la implementación

- No reemplazar el proyecto por una plantilla nueva.
- No migrar de router o framework sin autorización y justificación.
- No cambiar contratos API para facilitar el frontend sin documentar y validar el impacto.
- No inventar datos ni funcionalidades.
- No crear botones falsos.
- No duplicar componentes shadcn.
- No agregar dependencias sin revisar mantenimiento, compatibilidad y necesidad.
- Mantener TypeScript estricto.
- Mantener la separación entre UI, hooks, servicios y backend.
- Implementar una ruta o grupo de rutas por vez.
- Ejecutar lint, typecheck y tests luego de cada lote.

### Al cerrar cada entrega

Informar:

- Rutas modificadas.
- Componentes creados o reutilizados.
- Dependencias agregadas.
- Funcionalidades visuales implementadas.
- Estados contemplados.
- Tests ejecutados y resultados.
- Problemas pendientes.
- Capturas o evidencia de revisión visual cuando sea posible.

No declarar una entrega completa si solo se implementó el estado visual ideal y faltan loading, empty, error o responsive.

---

## 24. Prompt maestro para iniciar la implementación

```text
Necesito implementar el rediseño UI/UX de TalentOS siguiendo estrictamente:

- SDD del producto.
- ROADMAP de implementación.
- TalentOS_UI_UX_IMPROVEMENT_PLAN.md.

La dirección visual aprobada es Minimal Enterprise SaaS — Neutral Workspace.
La paleta principal es:
- Primary: #18181B
- Surface: #FAFAFA
- Border: #E4E4E7
- Muted text: #71717A
- Success: #16A34A
- Warning: #D97706

Usar Next.js, TypeScript, Tailwind CSS y shadcn/ui de acuerdo con el stack real del repositorio.

Primero inspeccioná el proyecto. No modifiques archivos todavía.
Necesito:
1. Inventario del stack y arquitectura frontend.
2. Inventario de rutas existentes.
3. Componentes y estilos actuales.
4. Integración existente con backend y contratos API.
5. Gaps respecto del plan UI/UX.
6. Riesgos de regresión.
7. Propuesta de implementación dividida en entregas pequeñas.

No inventes endpoints, campos, estados ni capacidades. Cuando una pantalla dependa de una funcionalidad que todavía no existe, identificá la dependencia y diseñá un estado no disponible honesto.

Después de presentar el diagnóstico, esperá aprobación para comenzar la primera entrega.
```

---

## 25. Resultado esperado

TalentOS debe pasar de una interfaz funcional mínima a una experiencia de producto SaaS profesional:

- Landing clara, convincente y alineada con el producto.
- Workspace consistente y fácil de navegar.
- Módulos completos y reconocibles.
- Datos densos presentados con claridad.
- IA explicable y supervisable.
- Componentes reutilizables.
- Experiencia responsive y accesible.
- Estados de sistema bien resueltos.
- Identidad visual sobria y memorable.

**Principio final:** la interfaz debe hacer que la complejidad técnica de TalentOS resulte comprensible y controlable. El diseño no debe ocultar cómo funciona el sistema; debe ayudar a las personas a entenderlo y tomar mejores decisiones.
