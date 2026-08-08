"""
services/omv_service.py — Prueba de conexión con OpenMediaVault (API JSON-RPC).

OMV expone /rpc.php. Hacemos un login de sesión para validar credenciales.
Sanitiza hostname y enmascara la contraseña en logs. Solo comprueba credenciales;
no realiza cambios en el NAS.
"""

from __future__ import annotations

import httpx

from core.logger import get_logger
from core.security import sanitize_api_key, sanitize_hostname

log = get_logger("omv")


async def test_connection(base_url: str, username: str, password: str,
                          timeout: float = 8.0) -> dict:
    host = sanitize_hostname(base_url)
    log.info(f"probando OMV host={host} user={username} pass={sanitize_api_key(password)}")
    base = base_url.rstrip("/")
    payload = {
        "service": "Session",
        "method": "login",
        "params": {"username": username, "password": password},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.post(f"{base}/rpc.php", json=payload)
            if r.status_code >= 400:
                return {"ok": False,
                        "message": f"El servidor respondió {r.status_code}",
                        "details": {"status": r.status_code}}
            data = r.json()
            err = data.get("error")
            if err:
                return {"ok": False,
                        "message": f"OMV rechazó el login: {err.get('message', 'error')}",
                        "details": {}}
            resp = data.get("response") or {}
            if resp.get("authenticated"):
                return {"ok": True, "message": "Conexión con OMV correcta",
                        "details": {"user": resp.get("username", username)}}
            return {"ok": False, "message": "Credenciales no autenticadas",
                    "details": {}}
    except httpx.HTTPError as e:
        log.error(f"error conectando a OMV: {e}")
        return {"ok": False, "message": f"No se pudo conectar: {e}", "details": {}}
    except ValueError:
        return {"ok": False, "message": "Respuesta de OMV no válida (¿es la URL correcta?)",
                "details": {}}
