# SECURITY — Modelo de seguridad y decisiones

Este documento describe cómo Metadata Analyzer evita corromper o perder archivos,
y las decisiones tomadas ante situaciones ambiguas (siempre eligiendo la opción
**más segura**).

## Principios

1. **Análisis obligatorio antes de corregir.** No se puede corregir una carpeta que
   no ha sido analizada primero.
2. **Ninguna escritura sin confirmación explícita.** Una corrección REAL requiere
   `confirm_real_write=true`; si falta, el backend responde **428 Precondition
   Required** y no escribe nada. El modo **dry-run** está siempre disponible.
3. **Backup antes de escribir.** Cada archivo se copia a `data/backups/<run>/`
   (preservando su ruta) antes de modificarlo. Rotación de los últimos N runs.
4. **Escritura verificada.** Tras escribir con exiftool, el archivo se **re-lee** y
   se comprueba que el valor es el esperado. Si no, se **revierte** ese archivo.
5. **Abort + restore por umbral de error.** Si el ratio de archivos fallidos supera
   `CORRECTION_ERROR_ABORT_RATIO` (10% por defecto), la ejecución se **aborta** y se
   **restauran** todos los cambios ya aplicados desde el backup.
6. **Fail-closed.** Ante cualquier duda de validación, se rechaza.

## Validación de rutas (`backend/core/security.py`)

- **Rutas de sistema prohibidas** siempre: `/etc /sys /proc /root /boot /dev /bin
  /sbin /lib /lib64 /usr /var /run /opt /snap` y componentes como `.ssh`, `.git`,
  `.gnupg`, `node_modules`.
- **Allowlist**: toda ruta debe estar dentro de `ALLOWED_MEDIA_ROOTS`. Fuera de ahí
  se rechaza (403).
- **Anti-traversal**: se resuelven symlinks y `..` con `realpath`; una subcarpeta
  seleccionada debe estar contenida en la raíz analizada.
- **Existencia y permisos**: se comprueba lectura (y escritura cuando la operación
  la requiere) antes de actuar.
- **Profundidad**: se limita la profundidad de recorrido (`MAX_WALK_DEPTH`).
- **Sanitización**: las API keys se enmascaran en logs (solo últimos 4 caracteres) y
  los hostnames se validan antes de usarse.

## Montaje de medios en solo lectura

En `docker-compose.yml`, la carpeta de medios se monta en el backend como
`read_only: true` por defecto. Mientras esté en `:ro`, **es físicamente imposible**
que una corrección escriba en tus archivos (fallará el backup/escritura y se
registrará como error). Ver `docs/DEPLOYMENT.md` para pasar a `:rw` de forma
deliberada solo cuando vayas a corregir.

## Registro y trazabilidad (`backend/core/logger.py`)

- `data/logs/operations.log`: todas las operaciones (análisis, conexiones,
  correcciones) con rotación.
- `data/logs/errors.log`: solo WARNING/ERROR.
- Cada corrección registra: ruta, tipo (`set_date`/`cleanup`), valor **original** y
  **nuevo**, estado y si se **verificó**. También se persiste en la tabla
  `corrections` de SQLite (dry-run y real).

## Decisiones ante ambigüedad (opción más segura)

| Situación | Decisión |
|-----------|----------|
| `FileModifyDate` como única "fecha" | **No** se considera fecha de captura fiable (`has_exif_date=false`). Es la fecha del sistema, no del disparo. |
| Fecha EXIF corrupta (fuera de rango) y **sin** otra referencia | Recomendación `cleanup`: se **elimina** la fecha corrupta. **Nunca** se inventa una fecha. |
| Sin fecha en EXIF, nombre ni carpeta | **No** se corrige; se reporta. No se fabrica ninguna fecha. |
| Precisión parcial | Se completa "hasta donde se pueda": año→`YYYY-01-01`, año+mes→`YYYY-MM-01`, fecha→`…00:00:00`; si hay hora, se respeta. |
| Año coincide entre EXIF y nombre | Se considera coherente y **no** se corrige. |
| Escritura que no verifica | Se **revierte** ese archivo inmediatamente desde backup. |
| Demasiados errores | Se **aborta** y se **restaura** todo el run. |

## Acciones prohibidas

- No se borran archivos originales (los duplicados solo se **reportan**; el borrado
  es decisión manual del usuario fuera de esta herramienta).
- No se ejecutan escrituras destructivas sin verificación previa.
- No se exponen secretos en logs.

## Recuperación manual

Cada run de backup guarda un `manifest.json` con el mapeo original→backup. Si fuera
necesario, `BackupManager.restore_run_from_manifest("<run_dir>")` restaura todos los
archivos de ese run. Los backups están en `data/backups/`.
