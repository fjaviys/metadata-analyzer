# ARCHITECTURE — Diseño y componentes

## Visión general

```
Navegador
   │  HTTPS + WebSocket
   ▼
┌──────────────────────────────────────────────┐
│ Nginx (proxy inverso, TLS, WS)               │
│   /            → frontend (Astro SSR :4321)   │
│   /api/*       → backend (FastAPI :8000)      │
│   /ws/*        → backend (WebSocket)          │
│   /docs        → OpenAPI                       │
└──────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
  Frontend (Astro+Vue)      Backend (FastAPI async)
                                  │
                                  │ importa
                                  ▼
                          shared/python (lógica)
                          ├─ date_detector
                          ├─ metadata_analyzer (exiftool)
                          ├─ report_generator (reportlab)
                          ├─ database_manager (SQLite)
                          └─ correction_engine (exiftool)
                                  │
                                  ▼
             SQLite  +  data/backups  +  data/logs  +  data/reports
```

## Capas

### `shared/python` — lógica reutilizable (sin framework)
- **date_detector**: detecta fechas en nombre y en estructura de carpetas; clasifica
  por precisión (`NONE/YEAR/YEAR_MONTH/FULL_DATE/DATETIME`), confianza y valida rangos.
- **metadata_analyzer**: lee EXIF/QuickTime con exiftool (JSON en lote), prioriza
  `DateTimeOriginal > CreateDate/DateTime > MediaCreateDate/CreationDate/CreationTime
  > FileModifyDate`, detecta inconsistencias, marca corruptos y agrega estadísticas
  por carpeta (nivel 1 y 2, orden descendente).
- **report_generator**: informe PDF (reportlab) con portada, resumen, recomendaciones
  y tablas por carpeta. Regla: sub/superíndices con `<sub>/<super>`, nunca Unicode.
- **database_manager**: SQLite (`analysis_sessions`, `analyzed_files`, `duplicates`,
  `corrections`) con índices y árbol de carpetas para el selector.
- **correction_engine**: corrección transaccional (backup → escribir → verificar),
  dry-run, y abort+restore por umbral de error.

### `backend` — FastAPI async
- **core/**: `config` (env), `security` (validación/allowlist/sanitización),
  `backup` (runs + rotación + restore), `logger` (operations/errors), `exceptions`.
- **services/**: `analysis_service` (análisis en background + hash de duplicados +
  PDF), `correction_service` (guard de confirmación, backup, orquesta el engine),
  `immich_service`/`omv_service` (test de conexión), `progress_hub` (bus WebSocket).
- **api/**: routers REST bajo `/api` (`config`, `analysis`, `results`, `corrections`)
  y WebSocket (`progress`).
- **schemas/**: modelos Pydantic. **database/**: proveedor del `DatabaseManager`.

### `frontend` — Astro + Vue + Tailwind (SSR con adaptador Node)
- **layouts/MainLayout.astro**, páginas `index/config/analysis/results/[id]/corrections`.
- **components/** Vue: formularios, selector de carpetas en árbol, progreso en vivo,
  tabla de resultados, tarjetas y gráficos.
- **api/client.ts**: cliente REST + suscripción WebSocket con reconexión.

## Flujo de datos (análisis)

1. `POST /api/analysis` valida la ruta y crea una sesión (`running`).
2. El análisis corre en un hilo (`asyncio.to_thread`) y publica progreso al
   `ProgressHub` → WebSocket `/ws/progress/session/{id}`.
3. Al terminar: se insertan ficheros y duplicados en SQLite, se genera el PDF y la
   sesión pasa a `completed`.

## Flujo de datos (corrección)

1. `POST /api/corrections` valida la sesión y las subcarpetas. Si es real sin
   confirmar → 428.
2. Se crea un run de backup (solo en modo real) y el `CorrectionEngine` procesa cada
   candidato (backup → exiftool → re-lectura/verificación), publicando progreso en
   `/ws/progress/run/{run_id}`.
3. Cada resultado se registra en `corrections` y en los logs.

## Concurrencia

- El backend es async; el trabajo pesado (exiftool, IO) se delega a hilos.
- SQLite en modo WAL con conexión por hilo (`check_same_thread=False`).
- El `ProgressHub` conserva el último evento por canal para clientes que se
  conectan tarde.
