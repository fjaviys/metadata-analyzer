#!/usr/bin/env bash
# Genera un certificado SSL autofirmado para DESARROLLO.
# Uso:  bash docker/nginx/gen-certs.sh [hostname]
# Produce docker/nginx/certs/server.crt y server.key
#
# NO usar en producción con exposición pública. Para producción, usa un
# certificado real (Let's Encrypt / reverse proxy con TLS gestionado).

set -euo pipefail

HOST="${1:-localhost}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs"
mkdir -p "$DIR"

if [[ -f "$DIR/server.crt" && -f "$DIR/server.key" ]]; then
  echo "Ya existen certificados en $DIR (no se sobreescriben)."
  exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$DIR/server.key" \
  -out "$DIR/server.crt" \
  -days 825 \
  -subj "/C=ES/ST=Local/L=Local/O=MetadataAnalyzer/CN=${HOST}" \
  -addext "subjectAltName=DNS:${HOST},DNS:localhost,IP:127.0.0.1"

chmod 600 "$DIR/server.key"
echo "Certificado autofirmado generado en $DIR para CN=${HOST}."
echo "El navegador avisará de que no es de confianza (normal en desarrollo)."
