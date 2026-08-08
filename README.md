# Metadata Analyzer

Herramienta web para **analizar y corregir de forma segura** los metadatos de fecha
(captura/creación) de fotos y vídeos gestionados con **Immich** sobre un NAS
**OpenMediaVault**. Detecta fechas incorrectas, metadatos corruptos y duplicados,
genera un **informe PDF**, y aplica correcciones **transaccionales y verificadas**
—siempre con backup previo y modo *dry-run* disponible.

> ⚠️ **Filosofía de seguridad**: el análisis es obligatorio antes de corregir. Toda
> corrección hace backup, se verifica re-leyendo el archivo, y puede simularse en
> *dry-run*. La carpeta de medios se monta en Docker en **solo lectura (`:ro`)** por
> defecto. Ver [docs/SECURITY.md](docs/SECURITY.md).

## Arquitectura

```
Navegador
   │  HTTP/HTTPS + WebSocket
   ▼
Nginx (proxy inverso, TLS, WS)
   ├──► Frontend  (Astro + Vue + TailwindCSS)   :4321
   └──► Backend   (FastAPI async + WebSocket)   :8000
             │
             ├── shared/python  (lógica reutilizable)
             │     ├── date_detector.py
             │     ├── metadata_analyzer.py   (exiftool)
             │     ├── report_generator.py    (reportlab → PDF)
             │     ├── database_manager.py    (SQLite)
             │     └── correction_engine.py   (exiftool + verificación)
             │
             └── SQLite  (data/db)   +  backups (data/backups)  +  logs (data/logs)
```

Detalle completo en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

| Capa        | Tecnología                                   |
|-------------|----------------------------------------------|
| Frontend    | Astro + Vue 3 + TailwindCSS                  |
| Backend     | FastAPI (Python 3.11+), async, WebSocket     |
| BD          | SQLite (migrable a PostgreSQL — documentado) |
| Metadatos   | exiftool                                     |
| Informes    | reportlab                                    |
| Orquestación| Docker + docker-compose + Nginx              |

## Flujo funcional

1. **Configurar** conexión (local / Immich / OMV) desde la UI y probarla en vivo.
2. **Analizar** una carpeta (obligatorio). Progreso en vivo por WebSocket →
   informe PDF + BD local con todo el detalle.
3. **Revisar** estadísticas, gráficos (por carpeta nivel 1 y 2) y duplicados.
4. **Seleccionar** carpetas en un árbol y **corregir** de forma segura (dry-run
   disponible; backup automático previo).

## Puesta en marcha rápida

```bash
cp .env.example .env      # ajusta rutas, Immich/OMV, MEDIA_HOST_PATH
# Genera certs autofirmados para desarrollo (ver docs/DEPLOYMENT.md):
#   bash docker/nginx/gen-certs.sh
docker-compose up -d
```

- UI:      https://localhost/
- API:     https://localhost/api  ·  docs OpenAPI: https://localhost/api/docs
- Health:  https://localhost/api/health

### Desarrollo local (sin Docker)

```bash
# Backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Tests de la lógica compartida
python -m pytest tests/ -v
```

## Documentación

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — diseño y componentes
- [docs/API.md](docs/API.md) — endpoints REST y WebSocket
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, certs SSL, ro→rw
- [docs/SECURITY.md](docs/SECURITY.md) — modelo de seguridad y decisiones

## Checklist de verificación

Tras `docker compose up -d --build`:

```bash
# 1) Healthcheck del backend (debe devolver exiftool: true)
curl -k https://localhost/health

# 2) Raíces permitidas
curl -k https://localhost/api/config/roots

# 3) Probar conexión local (debe rechazar rutas de sistema)
curl -k -X POST https://localhost/api/config/test \
  -H 'Content-Type: application/json' -d '{"type":"local","root_path":"/etc"}'   # ok:false

# 4) Lanzar un análisis de ejemplo
curl -k -X POST https://localhost/api/analysis \
  -H 'Content-Type: application/json' -d '{"root_path":"/media","detect_duplicates":true}'
#   -> {"session_id": N, ...}   Observa el progreso en la UI (WebSocket)

# 5) Ver resumen y descargar el informe PDF
curl -k https://localhost/api/results/N/summary
curl -k https://localhost/api/results/N/report -o informe.pdf

# 6) Corrección en DRY-RUN (no escribe nada)
curl -k -X POST https://localhost/api/corrections \
  -H 'Content-Type: application/json' -d '{"session_id":N,"dry_run":true}'

# 7) Corrección REAL sin confirmar -> debe responder 428
curl -k -i -X POST https://localhost/api/corrections \
  -H 'Content-Type: application/json' -d '{"session_id":N,"dry_run":false,"confirm_real_write":false}'
```

Tests de la lógica (local, sin Docker):

```bash
python -m pytest tests/ -v      # 47 tests (date/metadata/db/correction/report/api)
```

Comprobaciones de seguridad esperadas:
- `docker-compose.yml` monta los medios en `:ro` (`MEDIA_READ_ONLY=true`) por defecto.
- La corrección real exige confirmación explícita (428 sin ella).
- Cada corrección real hace backup previo y verifica por re-lectura.

## Estado

Implementado por bloques (ver historial de commits): lógica compartida con tests,
backend FastAPI, frontend Astro+Vue, Docker/Nginx y documentación. El código de
corrección **no** escribe sobre archivos reales hasta confirmación explícita del
usuario, y admite dry-run en todo el flujo.

## Licencia

Uso personal.
