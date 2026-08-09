# DEPLOYMENT — Despliegue con Docker

## Opción A (recomendada para NAS/OMV): imágenes desde GHCR, sin construir

Usa `docker-compose.nas.yml`, que descarga las imágenes ya publicadas en GitHub
Container Registry. No necesitas el código fuente en el NAS ni construir nada, ni
tampoco Nginx (el frontend habla con el backend directamente por su puerto).

Las imágenes se publican automáticamente (GitHub Actions) en cada push a `master`
y en cada tag `vX.Y.Z`:
- `ghcr.io/fjaviys/metadata-analyzer-backend:latest`
- `ghcr.io/fjaviys/metadata-analyzer-frontend:latest`

> Las imágenes son **públicas**, así que el NAS puede hacer `pull` sin
> `docker login`. (Si alguna vez el paquete apareciera como privado, hazlo público
> en GitHub → Packages → *Package settings* → *Change visibility*.)

### Pasos en OMV / Portainer

1. En el plugin **Compose** de OMV (o un stack de Portainer), pega el contenido de
   [`docker-compose.nas.yml`](../docker-compose.nas.yml).
2. Define las variables (en el propio gestor o en un `.env` junto al compose):
   ```env
   NAS_HOST=192.168.1.50           # IP/host del NAS accesible desde tu navegador
   MEDIA_HOST_PATH=/srv/dev-disk-by-uuid-XXXX/fotos
   BACKEND_PORT=8000
   FRONTEND_PORT=4321
   MEDIA_READ_ONLY=true            # solo lectura por defecto
   ```
3. Despliega. Accesos:
   - UI:     `http://NAS_HOST:4321`
   - API:    `http://NAS_HOST:8000/api`  ·  Health: `http://NAS_HOST:8000/health`
4. Para correcciones reales: cambia `MEDIA_READ_ONLY=false` y recrea el backend
   (empieza siempre por dry-run en la interfaz). Vuelve a `true` al terminar.

> Estado: **BETA (v0.1.0-beta)**. Prueba primero en dry-run y con backups.

Actualizar a la última versión:
```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

## Opción B: construir localmente (con Nginx + TLS)

Requiere el código fuente y usa `docker-compose.yml` (backend + frontend + Nginx
como proxy inverso con HTTPS y WebSocket unificados en un solo origen).

## Requisitos

- Docker + Docker Compose v2.
- La carpeta de medios accesible en el host (p. ej. el share de OMV montado).

## 1. Configurar el entorno

```bash
cp .env.example .env
```
Edita `.env`:
- `MEDIA_HOST_PATH` → ruta en el host a tus fotos/vídeos (p. ej. `/srv/dev-disk-by-.../fotos`).
- `HTTP_PORT` / `HTTPS_PORT` si 80/443 están ocupados.
- Opcional: `IMMICH_*`, `OMV_*` (también se pueden introducir desde la UI).

> Nota: el frontend usa internamente el puerto 4321. Si ya tienes **otro** proyecto
> Astro en 4321 en el host, no hay conflicto: aquí 4321 vive dentro de la red Docker
> y solo se expone a través de Nginx (80/443).

## 2. Certificado SSL (desarrollo)

```bash
bash docker/nginx/gen-certs.sh localhost
```
Genera `docker/nginx/certs/server.{crt,key}` autofirmados. El navegador mostrará un
aviso de confianza (normal en desarrollo). Para producción usa un certificado real.

## 3. Levantar

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

Accesos:
- UI:      `https://localhost/`
- API:     `https://localhost/api`  ·  OpenAPI: `https://localhost/docs`
- Health:  `https://localhost/health`  (también en HTTP)

## 4. Solo lectura → lectura/escritura (¡importante!)

Por defecto los medios se montan **solo lectura** (`MEDIA_READ_ONLY=true`). Con esto
puedes analizar y simular correcciones (dry-run) sin ningún riesgo.

Cuando **de verdad** quieras aplicar correcciones reales:

1. Haz (o confirma que tienes) una copia de seguridad de tus medios.
2. En `.env`:
   ```env
   MEDIA_READ_ONLY=false
   ```
3. Recrea el backend:
   ```bash
   docker compose up -d backend
   ```
4. En la UI (Correcciones): empieza con **dry-run**, revisa, y solo entonces marca
   la casilla de confirmación para la corrección real.
5. Cuando termines, vuelve a `MEDIA_READ_ONLY=true` y recrea el backend.

## 5. Datos persistentes

Volumen `ma-data` montado en `/app/backend/data`:
- `data/db/metadata_analyzer.db` — base de datos.
- `data/backups/` — backups por run (rotación `BACKUP_KEEP_LAST`).
- `data/logs/` — `operations.log`, `errors.log`.
- `data/reports/` — informes PDF.

## 6. Migración a PostgreSQL (opcional)

1. Descomenta el servicio `postgres` y el volumen `ma-pgdata` en `docker-compose.yml`.
2. Instala el driver: añade `psycopg[binary]` a `backend/requirements.txt`.
3. Implementa un `DatabaseManager` equivalente para Postgres (el actual usa `sqlite3`
   de stdlib; el esquema SQL es portable casi al 100%: revisa `AUTOINCREMENT` →
   `SERIAL/IDENTITY`).
4. Cambia `DATABASE_URL` a `postgresql://usuario:pass@postgres:5432/metadata_analyzer`.

SQLite es suficiente para uso personal; PostgreSQL aporta concurrencia alta y acceso
remoto.

## 7. Actualizar

```bash
git pull
docker compose up -d --build
```

## Solución de problemas

- **exiftool no disponible**: `GET /health` muestra `"exiftool": false`. Reconstruye
  el backend (la imagen instala `libimage-exiftool-perl`).
- **403 al analizar**: la ruta no está dentro de `/media` (allowlist del contenedor)
  o es una ruta de sistema. Ajusta `MEDIA_HOST_PATH`.
- **WebSocket no conecta**: comprueba que Nginx tiene los `Upgrade`/`Connection`
  (ya incluidos en `docker/nginx/nginx.conf`).
