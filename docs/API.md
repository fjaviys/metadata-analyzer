# API — Endpoints REST y WebSocket

Base: `/api` (a través de Nginx). Documentación interactiva: `/docs`
(OpenAPI en `/openapi.json`).

## Salud

### `GET /health`
```json
{ "status": "ok", "exiftool": true, "allowed_media_roots": ["/media"] }
```

## Configuración / conexiones

### `GET /api/config/roots`
Devuelve las raíces permitidas y si exiftool está disponible.
```json
{ "allowed_media_roots": ["/media"], "exiftool_available": true }
```

### `POST /api/config/test`
Prueba una conexión en vivo. Cuerpo según el tipo:
```jsonc
// local
{ "type": "local", "root_path": "/media/fotos" }
// immich
{ "type": "immich", "base_url": "http://immich:2283", "api_key": "..." }
// omv
{ "type": "omv", "base_url": "http://omv.local", "username": "u", "password": "p" }
```
Respuesta:
```json
{ "ok": true, "message": "Carpeta accesible: /media/fotos", "details": { "sample_media_found": 25 } }
```

## Análisis

### `POST /api/analysis`
```json
{ "root_path": "/media/fotos", "connection_type": "local", "detect_duplicates": true }
```
```json
{ "session_id": 12, "status": "running", "root_path": "/media/fotos" }
```

### `GET /api/analysis/sessions` · `GET /api/analysis/sessions/{id}`
Lista / detalle de sesiones.

## Resultados

- `GET /api/results/{id}/summary` — resumen de la sesión.
- `GET /api/results/{id}/files?needs_correction=true&folder=2020/07&limit=50&offset=0`
  — ficheros analizados (paginado).
- `GET /api/results/{id}/tree` — árbol de carpetas (nivel 1 → 2) para el selector.
- `GET /api/results/{id}/duplicates` — grupos de duplicados.
- `GET /api/results/{id}/report` — descarga el informe PDF.

## Correcciones

### `POST /api/corrections`
```json
{ "session_id": 12, "subfolders": ["2020/07"], "dry_run": true, "confirm_real_write": false }
```
- `dry_run: true` → simula, no escribe.
- `dry_run: false` **requiere** `confirm_real_write: true`, si no → **428**.

```json
{ "run_id": "a1b2c3d4e5f6", "dry_run": true, "total_candidates": 42, "status": "running" }
```

### `GET /api/corrections/{run_id}`
Estado y registro de una ejecución:
```json
{ "run_id": "a1b2c3d4e5f6", "stats": { "verified": 40, "failed": 1, "skipped": 1 },
  "corrections": [ { "path": "...", "original_value": "...", "new_value": "...", "status": "verified" } ] }
```

## WebSocket de progreso

- `GET /ws/progress/session/{session_id}` — progreso del análisis.
- `GET /ws/progress/run/{run_id}` — progreso de la corrección.

Eventos JSON:
```jsonc
{ "phase": "analysis", "current_file": "...", "processed": 120, "total": 300,
  "percent": 40.0, "inconsistencies": 55, "needs_correction": 60 }

{ "phase": "correction", "status": "completed", "dry_run": false,
  "verified": 40, "failed": 1, "reverted": 0, "aborted": false }
```
Al conectar se recibe el último evento conocido del canal. El servidor envía
`{ "type": "ping" }` como keep-alive.

## Códigos de error

| Código | Significado |
|--------|-------------|
| 403 | Ruta de sistema o fuera de la allowlist |
| 404 | Ruta/sesión/informe no encontrado |
| 428 | Corrección real sin confirmación explícita |
| 502 | Fallo al conectar con Immich/OMV |
| 503 | exiftool no disponible |
