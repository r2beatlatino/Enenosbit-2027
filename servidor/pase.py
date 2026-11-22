# -*- coding: utf-8 -*-
"""pase.py (ficha 166) — verificacion unica de pases Ed25519 emitidos por Cuenta Eñeños.

Adaptado de `C:/Users/benja/Desktop/R2beat-2013/servidor/pase.py` y `firma_ed25519.py` (RFC 8032 en Python puro,
sin dependencias externas).

Que comprueba `verificar_pase(pase_txt, aud)`:
  1. Firma Ed25519 valida con la clave publica de Cuenta Eñeños (`comprobar_firma`);
  2. `iss == "r2beat-portero"` y `aud` coincide con `juego()` (`R2_PASE_JUEGO`, por omision `"r2beat-moderno"`);
  3. No vencio (`exp`, con tolerancia chica);
  4. `sub` es un `uid` entero positivo;
  5. Uso unico (`jti`): recuerda cada `jti` hasta su vencimiento (`exp`), con tope `MAX_PASES_RECORDADOS`.

Regla: verificar un pase NUNCA llama a Cuenta Eñeños por cada login. La clave publica sale de
`R2_CUENTAS_CLAVE_PUBLICA` (JWK/JWKS/hex/base64url) o se pide UNA vez al arrancar a `R2_CUENTAS_URL`.
"""
import base64
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

import ajustes

EMISOR = "r2beat-portero"
AUD_OMISION = "r2beat-moderno"
MAX_PASES_RECORDADOS = 50_000
TOLERANCIA_OMISION = 5

_lock = threading.Lock()
_clave_pub = None            # bytes (32) o None
_clave_env_vista = None      # ultimo valor visto de R2_CUENTAS_CLAVE_PUBLICA
_url_intentada = None        # ultimo R2_CUENTAS_URL al que ya se le pidio /clave-publica
_aviso_sin_clave = False
_usados = {}                 # jti -> exp (epoch en segundos)

# ---------- Ed25519 en Python puro (RFC 8032 §6, coordenadas extendidas) ----------
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_RAIZ_M1 = pow(2, (_P - 1) // 4, _P)


def _recuperar_x(y, signo):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if signo else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _RAIZ_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != signo:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recuperar_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_CERO = (0, 1, 1, 0)


def _sumar(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _por(s, pt):
    r = _CERO
    while s > 0:
        if s & 1:
            r = _sumar(r, pt)
        pt = _sumar(pt, pt)
        s >>= 1
    return r


def _iguales(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _comprimir(pt):
    zi = _inv(pt[2])
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    signo = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, signo)
    return None if x is None else (x, y, 1, x * y % _P)


def _h_mod_q(*partes):
    return int.from_bytes(hashlib.sha512(b"".join(partes)).digest(), "little") % _Q


def _expandir(semilla):
    if len(semilla) != 32:
        raise ValueError("la clave privada Ed25519 mide 32 bytes")
    h = hashlib.sha512(semilla).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publica_ed25519(semilla):
    """La clave publica (32 bytes) de una semilla Ed25519 de 32 bytes."""
    a, _ = _expandir(semilla)
    return _comprimir(_por(a, _G))


def firmar_ed25519(semilla, mensaje):
    """Firma Ed25519 de 64 bytes (para pruebas con clave de prueba)."""
    a, prefijo = _expandir(semilla)
    pub = _comprimir(_por(a, _G))
    r = _h_mod_q(prefijo, mensaje)
    R = _comprimir(_por(r, _G))
    s = (r + _h_mod_q(R, pub, mensaje) * a) % _Q
    return R + int.to_bytes(s, 32, "little")


def verificar_ed25519(pub, mensaje, firma):
    """True solo si la firma Ed25519 es valida para esa clave publica y mensaje."""
    if len(pub) != 32 or len(firma) != 64:
        return False
    A = _descomprimir(pub)
    R = _descomprimir(firma[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(firma[32:], "little")
    if s >= _Q:
        return False
    h = _h_mod_q(firma[:32], pub, mensaje)
    return _iguales(_por(s, _G), _sumar(R, _por(h, A)))


# ---------- configuracion y clave publica ----------
def modo_pase():
    """True cuando `PASE=si` (o `1`); False por omision."""
    return ajustes.pase_activo()


def juego():
    """El `aud` esperado en el pase (`R2_PASE_JUEGO`, por omision `r2beat-moderno`)."""
    return (os.environ.get("R2_PASE_JUEGO") or "").strip() or AUD_OMISION


def _de_b64u(s):
    s = s.encode("ascii") if isinstance(s, str) else s
    return base64.urlsafe_b64decode(s + b"=" * (-len(s) % 4))


def parsear_clave_publica(valor):
    """Convierte JWK, JWKS (`/clave-publica`), hex de 64 chars o base64url en 32 bytes, o None."""
    if isinstance(valor, (bytes, bytearray)):
        return bytes(valor) if len(valor) == 32 else None
    txt = (valor or "").strip()
    if not txt:
        return None
    if txt.startswith("{"):
        try:
            d = json.loads(txt)
            if isinstance(d.get("keys"), list) and d["keys"]:
                k0 = d["keys"][0]
                if k0.get("kty", "OKP") != "OKP" or k0.get("crv", "Ed25519") != "Ed25519":
                    return None
                txt = str(k0.get("x") or "").strip()
            elif d.get("x"):
                if d.get("kty", "OKP") != "OKP" or d.get("crv", "Ed25519") != "Ed25519":
                    return None
                txt = str(d["x"]).strip()
            else:
                return None
        except Exception:                                                # noqa: BLE001
            return None
    if len(txt) == 64:
        try:
            b = bytes.fromhex(txt)
            if len(b) == 32:
                return b
        except ValueError:
            pass
    try:
        b = _de_b64u(txt)
        if len(b) == 32:
            return b
    except Exception:                                                    # noqa: BLE001
        return None
    return None


def _rutas_cuenta(url_base, sufijo):
    base = (url_base or "").strip().rstrip("/")
    if not base:
        return []
    if base.endswith("/cuentas"):
        return [base + sufijo, base[:-len("/cuentas")] + sufijo]
    return [base + sufijo, base + "/cuentas" + sufijo]


def cargar_clave_desde_url(url_base, timeout=3.0):
    """Pide `/clave-publica` una vez a `url_base`. -> `(pub_bytes, kid)` o `(None, None)`."""
    for u in _rutas_cuenta(url_base, "/clave-publica"):
        try:
            req = urllib.request.Request(u, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    continue
                d = json.loads(r.read().decode("utf-8"))
                k = (d.get("keys") or [{}])[0]
                pub = parsear_clave_publica(k.get("x") or "")
                if pub:
                    return pub, str(k.get("kid") or "")
        except Exception:                                                # noqa: BLE001
            continue
    return None, None


def _avisar(log, msg):
    if callable(log):
        log(msg)
    else:
        print(msg, flush=True)


def inicializar(timeout=3.0, log=None):
    """Carga la clave publica al arrancar (de `R2_CUENTAS_CLAVE_PUBLICA` o una vez de `R2_CUENTAS_URL`).
    Nunca llama por red en cada login."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    with _lock:
        env_k = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
        _clave_env_vista = env_k
        if env_k:
            pub = parsear_clave_publica(env_k)
            _clave_pub = pub
            if pub:
                _aviso_sin_clave = False
                _avisar(log, "   PASE=si: clave publica Ed25519 cargada de R2_CUENTAS_CLAVE_PUBLICA")
                return pub
            _avisar(log, "   ⚠ PASE=si: R2_CUENTAS_CLAVE_PUBLICA no es una clave Ed25519 valida de 32 bytes")
        url = (os.environ.get("R2_CUENTAS_URL") or "").strip()
        _url_intentada = url
        if url:
            pub, kid = cargar_clave_desde_url(url, timeout=timeout)
            _clave_pub = pub
            if pub:
                _aviso_sin_clave = False
                _avisar(log, "   PASE=si: clave publica Ed25519 obtenida de %s (kid=%s)" % (url, kid))
                return pub
        _clave_pub = None
        if modo_pase():
            _aviso_sin_clave = True
            _avisar(log, "   ⚠ PASE=si: sin clave publica (ni R2_CUENTAS_CLAVE_PUBLICA ni responde R2_CUENTAS_URL); "
                         "se rechazaran todos los logins hasta tener clave")
        return None


def poner_clave_publica(pub):
    """Fija en memoria la clave publica (para pruebas o configuracion directa)."""
    global _clave_pub, _clave_env_vista, _aviso_sin_clave
    with _lock:
        _clave_pub = parsear_clave_publica(pub)
        _clave_env_vista = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
        if _clave_pub:
            _aviso_sin_clave = False
        return _clave_pub


def clave_publica():
    """Devuelve los 32 bytes de clave publica en memoria, o None.
    Nunca llama por red en cada login: a `R2_CUENTAS_URL` solo se le pregunta una vez por configuracion."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    env_k = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
    url = (os.environ.get("R2_CUENTAS_URL") or "").strip()
    with _lock:
        if env_k != _clave_env_vista:
            _clave_env_vista = env_k
            _clave_pub = parsear_clave_publica(env_k) if env_k else None
            if not env_k:
                _url_intentada = None
        if _clave_pub is not None:
            return _clave_pub
        if not env_k and url and _url_intentada != url:
            _url_intentada = url
            pub, _kid = cargar_clave_desde_url(url)
            if pub:
                _clave_pub = pub
                _aviso_sin_clave = False
                return _clave_pub
        if modo_pase() and not _aviso_sin_clave:
            _aviso_sin_clave = True
        return None


# ---------- verificacion del pase JWS ----------
def comprobar_firma(pase_txt, pub, aud, ahora=None, tolerancia=30):
    """Firma EdDSA, emisor (`iss`), `aud`, `jti` presente y vencimiento (`exp`). -> dict de carga o None."""
    try:
        partes = pase_txt.split(".")
        if len(partes) != 3 or not all(partes):
            return None
        a, b, c = partes
        cab = json.loads(_de_b64u(a))
        carga = json.loads(_de_b64u(b))
        if not isinstance(cab, dict) or cab.get("alg") != "EdDSA":
            return None
        if not verificar_ed25519(pub, f"{a}.{b}".encode("ascii"), _de_b64u(c)):
            return None
    except (ValueError, TypeError, AttributeError, UnicodeEncodeError):
        return None
    ahora = time.time() if ahora is None else ahora
    if not isinstance(carga, dict) or carga.get("iss") != EMISOR or carga.get("aud") != aud or not carga.get("jti"):
        return None
    exp = carga.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int) or exp + tolerancia < ahora:
        return None
    return carga


def _uid_positivo(sub):
    if isinstance(sub, (bool, float)):
        return None
    if isinstance(sub, str):
        s = sub.strip()
        if not s.isdigit():
            return None
        u = int(s)
    elif isinstance(sub, int):
        u = sub
    else:
        return None
    return u if u > 0 else None


def verificar_pase(pase_txt, aud=None, ahora=None, tolerancia=TOLERANCIA_OMISION):
    """Comprueba firma Ed25519, `iss`, `aud`, vencimiento (`exp`), `sub` entero positivo y uso unico (`jti`).
    -> el dict de la carga si el pase vale, o `None` si rebota."""
    aud = aud or juego()
    if not isinstance(pase_txt, str) or not pase_txt or not aud:
        return None
    pub = clave_publica()
    if not pub:
        return None
    ahora_i = int(time.time() if ahora is None else ahora)
    carga = comprobar_firma(pase_txt, pub, aud, ahora=ahora_i, tolerancia=tolerancia)
    if not carga:
        return None
    uid = _uid_positivo(carga.get("sub"))
    if uid is None:
        return None
    jti = str(carga.get("jti") or "")
    if not jti:
        return None
    vence = int(carga["exp"]) + max(0, int(tolerancia))
    with _lock:
        if _usados:
            for k in [k for k, exp_k in _usados.items() if exp_k < ahora_i]:
                del _usados[k]
        if jti in _usados:
            return None
        if len(_usados) >= MAX_PASES_RECORDADOS:
            del _usados[min(_usados, key=_usados.get)]
        _usados[jti] = vence
    return carga


def limpiar_usados():
    """Vacia la memoria de pases ya usados (para pruebas)."""
    with _lock:
        _usados.clear()


def reiniciar():
    """Limpia clave en memoria y pases usados (para pruebas)."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    with _lock:
        _clave_pub = None
        _clave_env_vista = None
        _url_intentada = None
        _aviso_sin_clave = False
        _usados.clear()
