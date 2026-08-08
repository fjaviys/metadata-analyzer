"""
services/immich_service.py — Prueba de conexión con Immich.

Usa httpx async. Sanitiza hostname y enmascara la API key en logs. Solo lectura:
comprueba el ping del servidor y (si es posible) la validez de la API key.
"""

from __future__ import annotations

import httpx

from core.logger import get_logger
from core.security import sanitize_api_key, sanitize_hostname

log = get_logger("immich")


async def test_connection(base_url: str, api_key: str, timeout: float = 8.0) -> dict:
    host = sanitize_hostname(base_url)
    log.info(f"probando Immich host={host} key={sanitize_api_key(api_key)}")
    base = base_url.rstrip("/")
    headers = {"x-api-key": api_key, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            # 1) ping público del servidor
            ping = await client.get(f"{base}/api/server/ping", headers=headers)
            if ping.status_code == 404:
                ping = await client.get(f"{base}/api/server-info/ping", headers=headers)
            if ping.status_code >= 400:
                return {"ok": False,
                        "message": f"El servidor respondió {ping.status_code} al ping",
                        "details": {"status": ping.status_code}}

            # 2) validar API key con un endpoint autenticado
            details: dict = {"ping": ping.status_code}
            for path in ("/api/users/me", "/api/user/me"):
                r = await client.get(f"{base}{path}", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    details["user"] = data.get("email") or data.get("name")
                    return {"ok": True, "message": "Conexión con Immich correcta",
                            "details": details}
                if r.status_code in (401, 403):
                    return {"ok": False,
                            "message": "API key inválida o sin permisos",
                            "details": {"status": r.status_code}}
            # ping ok pero no pudimos validar la key (versión distinta)
            return {"ok": True,
                    "message": "Servidor Immich accesible (API key no verificada)",
                    "details": details}
    except httpx.HTTPError as e:
        log.error(f"error conectando a Immich: {e}")
        return {"ok": False, "message": f"No se pudo conectar: {e}", "details": {}}
