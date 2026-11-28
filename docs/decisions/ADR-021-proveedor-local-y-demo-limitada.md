# ADR-021 — Proveedor LLM local y demo limitada

Fecha: 2026-11-28
Estado: Aceptado

## Contexto

TalentOS ya define `LLMProvider` como contrato único (`apps/api/app/llm/provider.py`) y el registro solo acepta `mock` y `remote` (`apps/api/app/llm/registry.py`). El proveedor `mock` permite arrancar la demo sin credenciales; el proveedor `remote` exige `LLM_BASE_URL` y `LLM_API_KEY` y habla un contrato HTTP propio, no el de Ollama.

El usuario quiere ejecutar un modelo open weights en su propia máquina, sin subir pesos ni artefactos de entrenamiento al repositorio, y que el chat siga visible en la demo pero indique explícitamente que está limitado cuando no hay modelo cargado. También quiere poder habilitar el modelo local después sin cambiar reglas de negocio ni permisos.

Entorno medido en esta máquina: Ollama `0.40.3` en `127.0.0.1:11434`, con `qwen3:4b` instalado fuera del repo (`C:\Users\nacho\.ollama\models`). `ollama show qwen3:4b` declara licencia Apache-2.0, 4.0B parámetros, cuantización Q4_K_M y 2.5 GB en disco. Una petición `/api/chat` con `format` JSON y `think:false` tardó 2.2 s con el modelo cargado y 108 s tras descarga; una petición sin formato y con thinking por defecto tardó 144 s. La latencia depende del hardware y no es una promesa de producto.

El SDD excluye del MVP la facturación real, los planes comerciales y el fine-tuning de modelos propios (`TalentOS_SDD.md` §2.2). Esta decisión no los incorpora.

## Decisión

### 1. Proveedor local detrás de `LLMProvider`

Se añade `LocalLLMProvider` en `apps/api/app/llm/local.py`. Usa `httpx`, ya presente en el proyecto, contra el endpoint nativo de Ollama `/api/chat`:

- Sin cabecera `Authorization`.
- `stream: false`.
- `think: false`.
- `keep_alive: "30m"` para evitar recargas frecuentes del modelo.
- `format` con el JSON Schema de la respuesta estructurada para forzar salida válida y evitar razonamiento largo.
- `options.temperature: 0`.
- Timeout mínimo de 180 s, porque la carga fría medida fue de 108 s; `LLM_TIMEOUT_SECONDS` puede aumentarlo.
- Salida parseada como JSON y validada por el llamador con el esquema Pydantic correspondiente.
- Errores mapeados a `ProviderError` sin payload, texto de candidato ni credenciales en mensajes o logs.

`generate_text` también usa un esquema mínimo `{text: string}` para no caer en modo pensamiento.

`LLM_PROVIDER` pasa a aceptar `mock`, `local` y `remote`. El modo `local` exige `LLM_BASE_URL` y `LLM_MODEL`, reutilizando variables ya documentadas. No se añaden variables nuevas.

### 2. Artefactos fuera del repositorio

Los pesos, blobs, adapters, checkpoints y datasets de Qwen u otros modelos viven fuera del repo, por defecto en `%USERPROFILE%\.ollama\models` o en la ruta que defina `OLLAMA_MODELS`. No se versionan archivos `*.gguf`, `*.safetensors`, ni directorios de modelos. El repositorio solo contiene código, configuración sin secretos y documentación.

No se entrena ni se hace fine-tuning en este corte. Se usa el modelo preentrenado existente. Cualquier fine-tuning futuro requerirá ADR propio, datos sintéticos o con base legal, evaluación y artefactos privados.

### 3. Demo limitada visible

Cuando `LLM_PROVIDER=mock`, el estado del asistente incluye el código estable `demo_mock` en `limitations`. El frontend traduce ese código a un aviso visible: la demo usa respuestas simuladas y no tiene un modelo cargado. El aviso lo produce el backend; la UI no decide el modo ni esconde limitaciones reales.

Cuando `LLM_PROVIDER=local` o `remote`, no se añade `demo_mock`. La salida del modelo sigue sujeta a validación, citas verificables, permisos y aprobación humana.

### 4. Fuera de alcance

No se implementa facturación, suscripciones, cuotas por plan, entrenamiento ni fine-tuning. Tampoco se expone el modelo local como servicio público: Ollama escucha en loopback y depende de la máquina del usuario.

## Alternativas descartadas

- Entrenar un modelo desde cero: coste computacional alto, sin beneficio demostrado para el MVP y explícitamente fuera del SDD.
- Subir pesos al repo: tamaño innecesario, licencias y trazabilidad difíciles, y contradice la política de secretos/artefactos.
- Usar el adaptador `remote` actual contra Ollama: sus rutas `/v1/structured-output` y `/v1/text` no coinciden con la API local; obligaría a falsificar un contrato ajeno.
- Mostrar el aviso solo en frontend: rompería backend como autoridad y podría mentir si el modo cambiara por entorno.
- Habilitar suscripciones ahora: fuera del MVP según SDD §2.2; además exigiría webhooks, idempotencia, reconciliación y diseño de entitlements.

## Consecuencias

- El mismo contrato `LLMProvider` sirve para mock, local y remoto; dominio y agentes no conocen Ollama.
- Sin dependencias Python nuevas: se reutiliza `httpx`.
- La demo deja de parecer IA real cuando usa mock.
- El modo local depende de que Ollama esté levantado y de la latencia de la máquina.
- Los datos enviados al modelo local no salen a un proveedor externo, pero siguen siendo manejados por el backend con los límites de contexto ya existentes.
- Los planes y el cobro quedan para una decisión posterior con ADR y roadmap propios.

## Validación

- Tests unitarios del adaptador con `httpx.MockTransport`: selección por registry, petición sin `Authorization`, uso de `format`, parseo JSON, errores tipados y `health_check`.
- Test de API: respuesta del asistente incluye `demo_mock` cuando el proveedor configurado es `mock`.
- Test de UI: aviso traducido visible y código técnico no mostrado como texto suelto.
- Gates reales: `ruff`, `mypy`, `pytest`, `tsc`, ESLint, Vitest, build de Next.js y Playwright.
- Evidencia de latencia local registrada sin datos personales ni prompts de candidatos.
