#!/bin/sh
set -eu

RAIZ="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PASE="${PASE:-si}"
export HOSTS="${HOSTS:-0.0.0.0}"
export PUERTOS="${PUERTOS:-28004}"
export PUERTOS_JUEGO="${PUERTOS_JUEGO:-28008}"
export PUERTO_CUENTAS="${PUERTO_CUENTAS:-28101}"
export CUENTA_DATOS="${CUENTA_DATOS:-$RAIZ/datos_vps}"
export R2_PASE_JUEGO="${R2_PASE_JUEGO:-r2beat-moderno}"
# 21-nov (fichas 175 y 179): lo que el cliente de los amigos espera
export MUSICA_2013="${MUSICA_2013:-1}"          # catalogo 2013 (datos/musica_2013); SOLO con el cliente que trae sus paks
export SIN_CANAL_BAILE="${SIN_CANAL_BAILE:-1}"  # Modo Baile abre en el servidor de siempre
export GESTOS_TODOS="${GESTOS_TODOS:-1}"        # hola, po, gracias... en todos los idiomas

if [ -z "${IP_JUEGO:-}" ]; then
  echo "ERROR: falta definir IP_JUEGO=<IP publica del VPS>" >&2
  exit 1
fi
if [ -z "${R2_CUENTAS_CLAVE_PUBLICA:-}" ] && [ -z "${R2_CUENTAS_URL:-}" ]; then
  echo "ERROR: falta R2_CUENTAS_CLAVE_PUBLICA (JWK/hex/b64u) o R2_CUENTAS_URL" >&2
  exit 1
fi

if ! python3 -c "from Crypto.Cipher import AES" 2>/dev/null; then
  echo "ERROR: falta pycryptodome (pip install -r vps/requisitos.txt): sin eso CREAR SALA tira el servidor" >&2
  exit 1
fi

mkdir -p "$CUENTA_DATOS" "$RAIZ/registros"
cd "$RAIZ/servidor"

python3 -u login.py &
PID_LOGIN=$!
python3 -u juego.py &
PID_JUEGO=$!

parar() {
  kill -TERM "$PID_LOGIN" "$PID_JUEGO" 2>/dev/null || true
}
trap parar INT TERM

wait "$PID_LOGIN" "$PID_JUEGO"
