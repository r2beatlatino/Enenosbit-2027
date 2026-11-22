# -*- coding: utf-8 -*-
r"""captura.py (ficha 37) — el UNICO que lee la sesion capturada del oficial y las plantillas de datos/*.bin.

SOLO LEE; no escribe nada. Se recarga en vivo (recarga.py). Las rutas y las variables salen de ajustes.py.
Antes esta lectura estaba en juego.py y repartida en salas, carrera, tienda, social y misiones.

Dos cosas se recuerdan (lru_cache) porque antes se calculaban UNA vez al arrancar juego.py: el FF02 de la captura y la
llave de hardware de esta maquina. Si este archivo se recarga se vuelven a calcular, y dan lo mismo.
"""
import base64
import functools
import json
import os
import struct

import ajustes

LLAVE_SAL = 0xCACB1112          # X ^ LLAVE_SAL = la llave de hardware (medido en CmdLogin/CmdAck del exe)
CLAVE_AES_FF02 = b"3388ce10f3da39d1ade400938a4a25fe"
IV_AES_FF02 = base64.b64decode("QtHzrOYWadpeVhDjUMNXow==")


def _aes_xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _aes_mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _aes_xt(a)
        b >>= 1
    return r


def _aes_tablas():
    sbox, inv = [0] * 256, [0] * 256
    p = q = 1
    while True:
        p ^= _aes_xt(p)
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q
        for s in (1, 2, 3, 4):
            x ^= ((q << s) | (q >> (8 - s))) & 0xFF
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


_AES_SBOX, _AES_INV = _aes_tablas()


def _aes_cbc_descifrar(clave, iv, datos):
    """AES-256-CBC puro Python (sin dependencias externas, apto para VPS Linux)."""
    nk = len(clave) // 4
    nr = nk + 6
    w = [list(clave[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_AES_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _aes_xt(rcon)
        elif nk > 6 and i % nk == 4:
            t = [_AES_SBOX[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    rk = [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)]
    out, prev = bytearray(), iv
    for off in range(0, len(datos), 16):
        blq = datos[off:off + 16]
        s = [x ^ k for x, k in zip(blq, rk[nr])]
        for r in range(nr - 1, -1, -1):
            s = [s[((i // 4 - i % 4) % 4) * 4 + i % 4] for i in range(16)]
            s = [_AES_INV[x] for x in s]
            s = [x ^ k for x, k in zip(s, rk[r])]
            if r:
                n = []
                for c in range(4):
                    a = s[4 * c:4 * c + 4]
                    n += [
                        _aes_mul(a[0], 14) ^ _aes_mul(a[1], 11) ^ _aes_mul(a[2], 13) ^ _aes_mul(a[3], 9),
                        _aes_mul(a[0], 9) ^ _aes_mul(a[1], 14) ^ _aes_mul(a[2], 11) ^ _aes_mul(a[3], 13),
                        _aes_mul(a[0], 13) ^ _aes_mul(a[1], 9) ^ _aes_mul(a[2], 14) ^ _aes_mul(a[3], 11),
                        _aes_mul(a[0], 11) ^ _aes_mul(a[1], 13) ^ _aes_mul(a[2], 9) ^ _aes_mul(a[3], 14),
                    ]
                s = n
        out.extend(a ^ b for a, b in zip(s, prev))
        prev = blq
    return bytes(out)


def llave_de_c2s_ff02(cuerpo):
    """Extrae la llave de hardware que manda el exe en C2S FF02 (0x02762c80 -> cifrado AES 0x028a6970). None si no vale."""
    if len(cuerpo) < 32 or cuerpo[-4:] != b"\xfe\xcd\xdf\xbd":
        return None
    n = struct.unpack_from("<I", cuerpo, len(cuerpo) - 8)[0]
    m = (n + 15) // 16 * 16
    if n < 25 or m + 16 > len(cuerpo):
        return None
    pt = _aes_cbc_descifrar(CLAVE_AES_FF02, IV_AES_FF02, cuerpo[:m])[:n]
    off = 13
    for _ in range(3):
        if off >= n:
            return None
        off += 1 + pt[off]
    if off + 5 > n:
        return None
    cruda = struct.unpack_from("<I", pt, off)[0]
    off += 4
    l4 = pt[off]
    if off + 1 + l4 + 4 != n:
        return None
    return cruda ^ 0xCCCCCCCC


# ---------- mensajes con el encuadre [largo:u32][claro] y marcos de adentro de un FF56 ----------
def lotes_capturados(n=None, ruta=None):
    """Los ultimos `n` mensajes de un archivo [largo:u32][claro]... de datos/ (por omision: los LOTES de la sesion
    capturada). [] si no esta."""
    n = ajustes.CUANTOS_LOTES if n is None else n
    ruta = ajustes.RUTA_LOTES if ruta is None else ruta
    if not os.path.exists(ruta):
        return []
    with open(ruta, "rb") as f:
        b = f.read()
    out, off = [], 0
    while off + 4 <= len(b):
        largo = struct.unpack_from("<I", b, off)[0]
        if off + 4 + largo > len(b):
            break
        out.append(b[off + 4:off + 4 + largo])
        off += 4 + largo
    return out[-n:]


def claros_del_volcado():
    """Los lotes de la sesion MAS todos los FF55 descifrados del volcado (de donde salen las respuestas por metodo)."""
    return list(lotes_capturados()) + lotes_capturados(10 ** 6, ajustes.RUTA_RESPUESTAS)


def internos_todos(claro):
    """Los marcos de adentro de un FF56: [(cmd con el byte alto, seq, cuerpo)] (0xFF -> FF0xx, 0xFE -> FF1xx, 0xFD -> FF2xx)."""
    if len(claro) < 4 or claro[:2] != b"\xff\x56":
        return []
    k, out = 4 + struct.unpack_from("<H", claro, 2)[0], []
    while k + 8 <= len(claro):
        fl, cmd = claro[k], claro[k + 1]
        seq, ln = struct.unpack_from("<HI", claro, k + 2)
        if k + 8 + ln > len(claro) or fl not in (0xFF, 0xFE, 0xFD):
            break
        out.append(({0xFF: 0, 0xFE: 0x100, 0xFD: 0x200}[fl] + cmd, seq, claro[k + 8:k + 8 + ln]))
        k += 8 + ln
    return out


def _claros_sin_cortar(ruta):
    """Los mensajes [largo:u32][claro]... de una plantilla, o None si no existe el archivo (no corta el ultimo si viene corto)."""
    if not os.path.exists(ruta):
        return None
    with open(ruta, "rb") as f:
        b = f.read()
    out, off = [], 0
    while off + 4 <= len(b):
        largo = struct.unpack_from("<I", b, off)[0]
        out.append(b[off + 4:off + 4 + largo])
        off += 4 + largo
    return out


# ---------- el saludo del oficial en el 28008 (FF04, FF02) y las llaves ----------
def cuerpo_del_oficial(cmd):
    """El cuerpo CRUDO que el servidor oficial mando para ese comando en el 28008 (datos/juego_S2C.bin). None si no esta."""
    if not os.path.exists(ajustes.RUTA_CAP_JUEGO):
        return None
    with open(ajustes.RUTA_CAP_JUEGO, "rb") as f:
        b = f.read()
    off = 0
    while off + 8 <= len(b) and b[off] == 0xFF:
        largo = struct.unpack_from("<I", b, off + 4)[0]
        if off + 8 + largo > len(b):
            break
        if b[off + 1] == cmd:
            return b[off + 8:off + 8 + largo]
        off += 8 + largo
    return None


@functools.lru_cache(maxsize=None)
def _ff02_de_la_captura():
    """El FF02 del oficial (>= 265 B) sin tocar, o None si falta, es corto o CLAVE_PROPIA=1."""
    cap = cuerpo_del_oficial(0x02)
    if cap is not None and len(cap) >= 265 and not ajustes.CLAVE_PROPIA:
        return cap
    return None


def clave():
    """La clave de cifrado de 256 bytes: la del FF02 capturado, o una inventada si no hay (o CLAVE_PROPIA=1)."""
    cap = _ff02_de_la_captura()
    return cap[9:9 + 256] if cap is not None else bytes((i * 7 + 13) & 0xFF for i in range(256))


def llave_de_la_captura():
    """La llave de hardware de la captura (0xdato local de captura el 22-oct), o None si no hay FF02 capturado."""
    cap = _ff02_de_la_captura()
    return (struct.unpack_from("<I", cap, 1)[0] ^ LLAVE_SAL) if cap is not None else None


def llave_de_hardware():
    """La llave como la arma 0x004740f0: Address[1]<<24 | Address[3]<<16 | Address[5]<<8 | Address[2] del primer
    IP_ADAPTER_INFO. None si no se puede leer."""
    import ctypes
    try:
        buf = ctypes.create_string_buffer(0x8000)
        n = ctypes.c_ulong(len(buf))
        if ctypes.windll.iphlpapi.GetAdaptersInfo(buf, ctypes.byref(n)) != 0:
            return None
    except (OSError, AttributeError):
        return None
    ptr = struct.calcsize("P")
    off = ptr + 4 + 260 + 132                        # Next, ComboIndex, AdapterName, Description
    off += (-off) % 4                                # AddressLength (UINT) va alineado
    largo = struct.unpack_from("<I", buf.raw, off)[0]
    a = buf.raw[off + 4:off + 12]
    if largo < 6:
        return None
    return (a[1] << 24) | (a[3] << 16) | (a[5] << 8) | a[2]


@functools.lru_cache(maxsize=None)
def llave_de_esta_maquina():
    """La llave que va en el FF02 y los FF05: LLAVE=<hex> si se fijo, None con LLAVE_CAPTURADA=1 (manda la de la captura),
    y si no la de hardware de esta maquina (None si no se puede leer)."""
    if ajustes.LLAVE:
        return int(ajustes.LLAVE, 16)
    if ajustes.LLAVE_CAPTURADA:
        return None
    return llave_de_hardware()


def ff02_cuerpo(llave=None):
    """El cuerpo del FF02 que se manda al cliente: el capturado con la llave de ESTA maquina (o `llave`) puesta. None si no hay captura."""
    cap = _ff02_de_la_captura()
    if cap is None:
        return None
    if llave is None:
        llave = llave_de_esta_maquina()
    llave_cap = llave_de_la_captura()
    if llave is not None and llave_cap is not None and llave != llave_cap:
        return cap[:1] + struct.pack("<I", llave ^ LLAVE_SAL) + cap[5:]
    return cap


def con_llave(lote, llave=None):
    """El lote con la llave de esta maquina (o `llave`) en cada FF05 (CmdAck) de adentro, solo donde estaba la de la captura."""
    if llave is None:
        llave = llave_de_esta_maquina()
    llave_cap = llave_de_la_captura()
    if llave is None or llave_cap is None or llave == llave_cap or len(lote) < 4 or lote[:2] != b"\xff\x56":
        return lote
    out, k = bytearray(lote), 4 + struct.unpack_from("<H", lote, 2)[0]
    while k + 8 <= len(lote):
        fl, cmd = lote[k], lote[k + 1]
        ln = struct.unpack_from("<I", lote, k + 4)[0]
        if k + 8 + ln > len(lote):
            break
        if fl == 0xFF and cmd == 0x05 and ln >= 4 and struct.unpack_from("<I", lote, k + 8)[0] ^ LLAVE_SAL == llave_cap:
            struct.pack_into("<I", out, k + 8, llave ^ LLAVE_SAL)
        k += 8 + ln
    return bytes(out)


# ---------- plantillas: un cuerpo o una lista de marcos ----------
def cuerpo_capturado(cmd):
    """El cuerpo del primer marco `cmd` (sin byte alto) de los lotes capturados, con la llave de esta maquina. None si no esta."""
    for l in lotes_capturados():
        for c, _s, cu in internos_todos(con_llave(l)):
            if c == cmd:
                return cu
    return None


def claros_crear_sala():
    """Los mensajes (claros) que el oficial mando al crear sala, en orden. None si falta datos/crear_sala_S2C.bin."""
    return _claros_sin_cortar(ajustes.RUTA_CREAR_SALA)


def _marcos_de_plantilla(ruta):
    claros = _claros_sin_cortar(ruta)
    out = []
    for claro in claros or []:
        out += internos_todos(claro)
    return out


def plantilla_crear_sala():
    """Los marcos grabados del oficial al crear sala: [(cmd, seq, cuerpo)] en orden. [] si falta el archivo."""
    return _marcos_de_plantilla(ajustes.RUTA_CREAR_SALA)


def plantilla_unirse():
    """Los marcos grabados del oficial al ENTRAR a una sala: [(cmd, seq, cuerpo)]. [] si falta el archivo."""
    return _marcos_de_plantilla(ajustes.RUTA_UNIRSE)


def fila_del_cartel():
    """Los 102 bytes de la fila de un jugador del cartel de resultados del oficial (+3 del archivo). None si falta."""
    if not os.path.exists(ajustes.RUTA_CARTEL):
        return None
    with open(ajustes.RUTA_CARTEL, "rb") as f:
        cu = f.read()
    return cu[3:3 + 102]


def ficha_examinar():
    """El cuerpo del FF77 (examinar) del oficial. None si falta datos/examinar_S2C.bin."""
    if not os.path.exists(ajustes.RUTA_EXAMINAR):
        return None
    with open(ajustes.RUTA_EXAMINAR, "rb") as f:
        return f.read()


# ---------- canciones y charts ----------
# Decision de Eñeños (20-nov, ficha 176/177): estas 9 tienen chart pero les falta la PISTA PRINCIPAL (BGM, `mr.mp3`) en
# todos los rnr_music*.pak de Steam, asi que no se ofrecen. Elegir la 972 cierra el juego en 0x00d399b1 (MEDIDO en la
# 173, dos corridas; `e_song970/mr.mp3` ok=0). 805/806, 832/833 y 970/971/972: dos testigos (indice de paks + juego).
# 1267/1268 (`e_song1267/mr.mp3`): solo LEIDO en las tablas de los paks (ficha 176), no probado con el juego.
# Se sacan de lo que manda el servidor (FF00 y carrera al azar). charts_1a1.json no se toca.
SIN_PISTA_PRINCIPAL = frozenset({805, 806, 832, 833, 970, 971, 972, 1267, 1268})


# 21-nov (ficha 179, pedido de Eñeños: "la musica ya 1 a 1 con el 2013"): llave MUSICA_2013 (omision vacia = como antes).
# =1 usa datos/musica_2013/, o una carpeta dada. Adentro: musica_2013.json (las canciones del catalogo propio del cliente:
# nombre, portada, XML y audio del 2013, armado con _fuera_git/ficha179/armar179.py) y charts/<songid>.bin (el chart del
# servidor 2013 de ESA cancion). SOLO con el cliente que trae rnr_musica2013.pak + rnr_music2013_*.pak: el de Steam no
# tiene las importadas (las descarta sin caerse) ni el audio de las SIN_PISTA_PRINCIPAL (esas lo cierran).
def _dir_musica_2013():
    v = os.environ.get("MUSICA_2013", "")
    if not v:
        return None
    d = os.path.join(ajustes.DATOS, "musica_2013") if v == "1" else v
    return d if os.path.exists(os.path.join(d, "musica_2013.json")) else None


@functools.lru_cache(maxsize=1)
def _musica_2013():
    d = _dir_musica_2013()
    if not d:
        return frozenset(), None
    with open(os.path.join(d, "musica_2013.json"), encoding="utf-8") as f:
        return frozenset(json.load(f)["jugables"]), os.path.join(d, "charts")


def jugables():
    """Los songid con chart 1 a 1, de mayor a menor, sin SIN_PISTA_PRINCIPAL (salvo las que el catalogo 2013 trae con
    su audio). [] si falta datos/charts_1a1.json y no hay MUSICA_2013."""
    del2013, _ = _musica_2013()
    base = []
    if os.path.exists(ajustes.RUTA_CHARTS):
        with open(ajustes.RUTA_CHARTS, encoding="utf-8") as f:
            base = json.load(f)["jugables"]
    return sorted({s for s in base if s not in SIN_PISTA_PRINCIPAL or s in del2013} | del2013, reverse=True)


def chart(songid):
    """Los bytes del chart de esa cancion (datos/charts/<songid>.bin). None si no tiene. Con MUSICA_2013, primero el del
    2013 (su XML del catalogo propio es el del 2013: chart y XML van juntos)."""
    del2013, dir2013 = _musica_2013()
    ruta = os.path.join(ajustes.DIR_CHARTS, "%d.bin" % songid)
    if songid in del2013 and os.path.exists(os.path.join(dir2013, "%d.bin" % songid)):
        ruta = os.path.join(dir2013, "%d.bin" % songid)
    if not os.path.exists(ruta):
        return None
    with open(ruta, "rb") as f:
        return f.read()
