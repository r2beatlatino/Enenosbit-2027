# -*- coding: utf-8 -*-
r"""lobby_metodos.py (M24, 27-nov) — los pedidos POR NOMBRE del lobby que en el VPS quedaban sin contestar, con la forma que mandaba el
oficial en las grabaciones del dueño (tools/net/grabaciones, 29-oct..08-nov; fuera de git).

MEDIDO en las 8 grabaciones (scratchpad de la sesion de maduracion, `grab/ids.py`; detalle en
docs/tablero_maduracion/M24_lobby_metodos_del_oficial.md). Aca no se copia ningun JSON del oficial (el guardia de datos compara de a 16 B):
  - modAct.getActList: objeto vacio en FF255 (con el SELLO de 36 B, 45 de 45 validos) y en FF26F (47 de 47); en FF246 el oficial
    mandaba sus dos eventos.
  - gift.info: registro de compras vacio y la marca de cargado (82 de 82).
  - vip.info: la ficha VIP en cero con el gsn/usn del que pide (78).
  - gardenRankAct.getMyInfo: puntos 0 y experiencia 0 con el usn del que pide (2 de 4; los otros 2 eran jugadores con jardin).
En TODAS el sobre es [u64 A][u64 id del pedido][s nombre][s JSON] + cola (u32 0, o [u32 36][36 B sello] en FF255). Es el mismo sobre
de jardin.sobre (medido con el juego) y de liga.sobre (el sello).

En prod (registros 23..27-nov) el cliente pidio modAct.getActList 86.631 veces sin respuesta (hasta 360 por minuto).

DECISION: en FF246 el getActList va como {} (ningun evento), la forma que el oficial usaba en los otros dos canales. Los dos eventos
del oficial (familySys = familias/circulos, inviteAct) piden despues getActInfoByKey con la config del oficial: sin medir, no van.
Sin contestar todavia: getdiamondInfoCS (otro formato), rankedMatchRank.getPlayerInfo (el oficial no contesto en las grabaciones),
vip.buy, vip.switchUI.

Llave LOBBY_METODOS (1 por omision). 0 = como antes (sin contestar).
"""
import json
import os
import struct

import estado
import sello

LLAVES_OMISION = {"LOBBY_METODOS": "1"}

VACIO = "{}"
GIFT_INFO = {"buyRecord": {}, "_loaded": True}
VIP_CAMPOS = ("lastSettle", "p100", "vipui", "expire", "p30", "vipsw", "cost", "gsn", "p365", "_loaded", "p100d", "exp", "p365d",
              "p30d", "usn", "actkey")   # el orden del oficial
VIP_FIJOS = {"lastSettle": 0, "p100": 0, "vipui": 0, "expire": 0, "p30": 0, "vipsw": 256, "cost": 0, "p365": 0, "_loaded": True,
             "p100d": 0, "exp": 0, "p365d": 0, "p30d": 0, "actkey": "vipsys_001"}   # MEDIDO: iguales en las 78 respuestas


def llave(nombre="LOBBY_METODOS"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]).strip().lower() in ("1", "si")


def anotar(txt):
    estado.anotar(txt)


def leer_pedido(cuerpo):
    """(nombre, args) de un C2S [u64 id][s nombre][s JSON]; None si no encaja."""
    if len(cuerpo) < 16:
        return None
    nl = struct.unpack_from("<I", cuerpo, 8)[0]
    if not 3 <= nl <= 64 or 12 + nl + 4 > len(cuerpo):
        return None
    nombre = cuerpo[12:12 + nl]
    if not all(32 < c < 127 for c in nombre):
        return None
    jl = struct.unpack_from("<I", cuerpo, 12 + nl)[0]
    if 16 + nl + jl != len(cuerpo):
        return None
    try:
        return nombre.decode(), json.loads(cuerpo[16 + nl:].decode("utf-8") or "null")
    except ValueError:
        return nombre.decode(), None


def _contador(canal):
    a = getattr(estado, "_lobby_A", None)
    if a is None:
        a = {}
        estado._lobby_A = a
    a[canal] = a.get(canal, 0x30000) + 1
    return a[canal]


def sobre(canal, cuerpo_pedido, nombre, js, sellado=False):
    """S2C [u64 A][u64 id del pedido][s nombre][s JSON] + [u32 0], o + [u32 36][36 B sello] si `sellado`."""
    nb = nombre.encode("ascii")
    jb = js.encode("utf-8") if isinstance(js, str) else js
    cola = struct.pack("<I", 0)
    if sellado:
        s = sello.sellar(jb)
        cola = struct.pack("<I", len(s)) + s
    return (struct.pack("<Q", _contador(canal)) + cuerpo_pedido[:8] + struct.pack("<I", len(nb)) + nb
            + struct.pack("<I", len(jb)) + jb + cola)


def _json(obj):
    return obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def vip_info(cuenta):
    """La ficha VIP del oficial (todo en 0) con el gsn y el usn de la cuenta, en el orden del oficial."""
    c = cuenta or {}
    d = dict(VIP_FIJOS, gsn=int(c.get("gsn") or 0), usn=int(c.get("usn") or 0))
    return "{" + ",".join("%s:%s" % (json.dumps(k), json.dumps(d[k])) for k in VIP_CAMPOS) + "}"


def respuesta(cmd, nombre, cuenta):
    """(JSON, sellado) para ese pedido y canal, o None si no se contesta aca."""
    if nombre == "modAct.getActList" and cmd in (0x246, 0x255, 0x26F):
        return VACIO, cmd == 0x255
    if nombre == "gift.info" and cmd == 0x246:
        return _json(GIFT_INFO), False
    if nombre == "vip.info" and cmd == 0x246:
        return vip_info(cuenta), False
    if nombre == "gardenRankAct.getMyInfo" and cmd == 0x26F:
        return _json({"p": 0, "u": int((cuenta or {}).get("usn") or 0), "e": 0}), False
    return None


def _manejador(cmd):
    def f(con, seq, cuerpo):
        if not llave():
            return False
        p = leer_pedido(cuerpo)
        if p is None:
            return False
        r = respuesta(cmd, p[0], con.cuenta)
        if r is None:
            return False
        js, sellado = r
        con.mandar_interno(cmd, seq, sobre("%X" % cmd, cuerpo, p[0], js, sellado))
        cuenta = con.cuenta or {}
        # getActList llega muy seguido: se anota solo la primera de cada conexion
        n = getattr(con, "_lobby_n", {})
        n[p[0]] = n.get(p[0], 0) + 1
        con._lobby_n = n
        if p[0] != "modAct.getActList" or n[p[0]] == 1:
            anotar("   S2C FF%X %s de %s: %s%s (M24, forma del oficial)" % (cmd, p[0], cuenta.get("nick"), js[:80],
                                                                         " + sello" if sellado else ""))
        return True
    return f


MANEJADORES = {0x246: _manejador(0x246), 0x255: _manejador(0x255), 0x26F: _manejador(0x26F)}
