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
# 22-nov (maduracion M09): cuentas en SQLite WAL (cuentas.db). La 1.a vez migra cuenta.json y lo deja intacto de respaldo.
export CUENTA_SQLITE="${CUENTA_SQLITE:-1}"
# 23-nov (maduracion M19): nombre del canal en la lista (la ñ no se dibuja en esa parte del cliente: medido)
export CANAL="${CANAL:-N2server}"
# 23-nov (pedido del dueño): el modo gorila (cooperativo) en Glitchland = escenario 56 (stage.txt 无尽的黑; antes 10 = Halloween)
export MAPA_COOP="${MAPA_COOP:-56}"

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
