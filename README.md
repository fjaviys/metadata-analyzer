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

## Estado

En construcción por bloques (ver historial de commits). El código de corrección
**no** escribe sobre archivos reales hasta confirmación explícita del usuario.

## Licencia

Uso personal.
