# -*- coding: utf-8 -*-
r"""ranking.py (11-nov, ficha 84) — la solapa 1 del ranking (排行榜) por EXP, con las cuentas LOCALES. Solo LEE cuenta.json.
Layouts leidos del exe (docs/tablero/layouts/FF1A3.md, FF1A4.md, seccion "Lectura de la ficha 84"):

  C2S FF1A4 [u16 pagina, desde 1]  -> S2C FF1A4 [u8 estado 0][u8 n][n x 56 B]
  C2S FF1A3 (sin cuerpo)           -> S2C FF1A3 [u8 estado 0][u8 n][n x 56 B][u32 EXP bajo][u64 EXP alto]   ("mi lugar")
  fila 56 B: +0 u32 id | +4 u32 EXP bajo | +8 apodo NUL (28 B, gbk) | +0x24 u32 puesto | +0x28 u32 puesto anterior |
             +0x30 u64 EXP alto | el resto (+0x2c) NO LEIDO = 0.  El cliente SUMA +4 y +0x30 y calcula el nivel solo.
  FF1A3: n = 3 -> filas [de arriba, yo, de abajo]; con n != 3 el cliente reconoce "yo" comparando el id de la fila con el
         propio (0x028215bc..0x028215e7) y manda las otras a "anterior"/"siguiente" por orden (el primero que no soy yo = anterior).

HIPOTESIS (anotadas): filas por pagina (se usan 10: hay 10 botones Page0..9); el id es el usn (unico por cuenta; el cliente lo
  compara con uno propio que no se identifico en el exe); puesto anterior = puesto actual (no hay historial).
Orden: EXP de mayor a menor; a igual EXP, el usn menor primero (puestos 1..n sin empates). Entran las cuentas locales CON personaje.
SOLAPA 0 (FF1A1/FF1A2, record de partidas por licencia, que el servidor NO guarda): MEDIDO con juego (11-nov) que sin respuesta
  la ventana del ranking NO SE VE (llegan los pedidos y no aparece nada), asi que no se podria llegar a la solapa de EXP. Se contesta
  VACIO: FF1A1 = [0] + 3 x 126 B en cero (id 0 = "sin datos"), FF1A2 = [0][u32 n=0] (lista vacia, sin cartel). No se inventa ninguna cifra.
SOLAPA 3, G (ficha 86, 11-nov; docs/tablero/layouts/FF1A6.md y FF1A7.md, seccion "Lectura de la ficha 86"):
  C2S FF1A7 [u16 pagina, desde 1] -> S2C FF1A7 [u8 estado 0][u8 n][n x 40 B]      (CmdGetCoinRankByPage, 0x028288d0)
  C2S FF1A6 (sin cuerpo)          -> S2C FF1A6 [u8 estado 0][u8 n][n x 40 B]      ("mi lugar", CmdGetMyCoinRank, 0x02827cf0; SIN cola)
  fila 40 B (LEIDA en 0x028288d0 -> 0x009a03b0 -> pintor 0x009a4cc0): +0 u32 id | +4 u32 G | +8 apodo NUL (24 B, gbk) |
             +0x20 u32 puesto | +0x24 u32 puesto anterior (0 = el cliente usa el puesto).  El G va PLANO (se dibuja con "%u"
             sin xor: 0x009a4ed1). Mismas reglas que la EXP para n = 3 y para reconocer "yo" por el id (xor 0xd350 con el usn).
  HIPOTESIS: 10 filas por pagina; puesto anterior = puesto.  Orden: G de mayor a menor, a igual G el usn menor primero.
  RANKING_G=0 deja la solapa sin atender (el cliente no pinta nada y no se cuelga).
NO atiende: pareja, discipulos, encanto, VIP, salon de la fama, busquedas por apodo.
La sesion capturada (sin cuenta local) recibe la lista (FF1A4) pero no "mi lugar" (FF1A3 sin atender).
RANKING_EXP=0 apaga la EXP (y la solapa 0 vacia, si RANKING_G tambien es 0); vuelve a "sin atender".
"""
import os
import struct

import cuenta as _cta
import estado
import tienda
import textos

LLAVES_OMISION = {"RANKING_EXP": "1", "RANKING_G": "1"}
POR_PAGINA = 10       # HIPOTESIS
MAX_APODO = 27        # el campo es de 28 B con el NUL
MAX_APODO_G = 23      # el campo de la fila de G es de 24 B con el NUL (+8..+0x1f)


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="RANKING_EXP"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def _tabla(indice):
    filas = []
    for k, acc in _cta.todas().items():
        pj = acc.get("personaje")
        if not pj:
            continue
        usn = int((acc.get("cuenta") or {}).get("usn", k))
        nick = pj.get("nick") or (acc.get("cuenta") or {}).get("nick") or ""
        v = tienda.exp_g_de_cuenta({"usn": usn})[indice]
        filas.append((-v, usn, nick, v))
    filas.sort(key=lambda f: (f[0], f[1]))
    return [(i + 1, usn, nick, v) for i, (_n, usn, nick, v) in enumerate(filas)]


def tabla():
    """[(puesto, usn, apodo, exp)] de las cuentas locales con personaje, de mayor a menor EXP (SOLO LECTURA)."""
    return _tabla(0)


def tabla_g():
    """[(puesto, usn, apodo, g)] de las cuentas locales con personaje, de mayor a menor G (SOLO LECTURA; la misma fuente que la FF00)."""
    return _tabla(1)


def _partes(exp):
    bajo = min(exp, 0xFFFFFFFF)
    return bajo, exp - bajo


def fila(puesto, usn, nick, exp):
    """La fila de 56 B (solo lo leido; el resto en 0)."""
    f = bytearray(56)
    bajo, alto = _partes(exp)
    struct.pack_into("<II", f, 0, usn, bajo)
    t = textos.codificar(nick, MAX_APODO)
    f[8:8 + len(t)] = t
    struct.pack_into("<II", f, 0x24, puesto, puesto)
    struct.pack_into("<Q", f, 0x30, alto)
    return bytes(f)


def cuerpo_pagina(t, pagina):
    """[u8 0][u8 n][n x 56 B] de la pagina (desde 1). Fuera de rango = n 0."""
    ini = (max(1, pagina) - 1) * POR_PAGINA
    parte = t[ini:ini + POR_PAGINA]
    return bytes([0, len(parte)]) + b"".join(fila(*x) for x in parte)


def fila_g(puesto, usn, nick, g):
    """La fila de 40 B de la solapa de G (todo LEIDO; el G va plano, tope u32)."""
    f = bytearray(40)
    struct.pack_into("<II", f, 0, usn, min(g, 0xFFFFFFFF))
    t = textos.codificar(nick, MAX_APODO_G)
    f[8:8 + len(t)] = t
    struct.pack_into("<II", f, 0x20, puesto, puesto)
    return bytes(f)


def cuerpo_pagina_g(t, pagina):
    """[u8 0][u8 n][n x 40 B] de la pagina (desde 1). Fuera de rango = n 0."""
    ini = (max(1, pagina) - 1) * POR_PAGINA
    parte = t[ini:ini + POR_PAGINA]
    return bytes([0, len(parte)]) + b"".join(fila_g(*x) for x in parte)


def cuerpo_mi_lugar_g(t, usn):
    """[u8 0][u8 n][n x 40 B] (sin cola) o None si esa cuenta no esta en la tabla."""
    i = next((k for k, x in enumerate(t) if x[1] == usn), None)
    if i is None:
        return None
    parte = t[max(0, i - 1):i + 2]
    return bytes([0, len(parte)]) + b"".join(fila_g(*x) for x in parte)


def cuerpo_mi_lugar(t, usn):
    """[u8 0][u8 n][n x 56 B][u32][u64] o None si esa cuenta no esta en la tabla."""
    i = next((k for k, x in enumerate(t) if x[1] == usn), None)
    if i is None:
        return None
    parte = t[max(0, i - 1):i + 2]
    exp = t[i][3]
    bajo, alto = _partes(exp)
    return bytes([0, len(parte)]) + b"".join(fila(*x) for x in parte) + struct.pack("<IQ", bajo, alto)


def por_pagina(con, seq, cuerpo):
    """C2S FF1A4 [u16 pagina]."""
    if not llave() or len(cuerpo) != 2:
        return False
    pagina = struct.unpack("<H", cuerpo)[0]
    r = cuerpo_pagina(tabla(), pagina)
    con.mandar_interno(0x1A4, seq, r)
    anotar("   S2C FF1A4 ranking EXP pagina %d: %d fila(s) (%d B)" % (pagina, r[1], len(r)))
    return True


def mi_lugar(con, seq, cuerpo):
    """C2S FF1A3 (0 B)."""
    if not llave() or cuerpo:
        return False
    usn = (con.cuenta or {}).get("usn")
    r = cuerpo_mi_lugar(tabla(), usn) if usn is not None else None
    if r is None:
        anotar("   FF1A3 ranking EXP: %s no esta en la tabla (sin atender)" % ((con.cuenta or {}).get("nick") or "sesion sin cuenta local"))
        return False
    con.mandar_interno(0x1A3, seq, r)
    anotar("   S2C FF1A3 mi lugar de %s: %d fila(s) (%d B)" % ((con.cuenta or {}).get("nick"), r[1], len(r)))
    return True


def por_pagina_g(con, seq, cuerpo):
    """C2S FF1A7 [u16 pagina]."""
    if not llave("RANKING_G") or len(cuerpo) != 2:
        return False
    pagina = struct.unpack("<H", cuerpo)[0]
    r = cuerpo_pagina_g(tabla_g(), pagina)
    con.mandar_interno(0x1A7, seq, r)
    anotar("   S2C FF1A7 ranking G pagina %d: %d fila(s) (%d B)" % (pagina, r[1], len(r)))
    return True


def mi_lugar_g(con, seq, cuerpo):
    """C2S FF1A6 (0 B)."""
    if not llave("RANKING_G") or cuerpo:
        return False
    usn = (con.cuenta or {}).get("usn")
    r = cuerpo_mi_lugar_g(tabla_g(), usn) if usn is not None else None
    if r is None:
        anotar("   FF1A6 ranking G: %s no esta en la tabla (sin atender)" % ((con.cuenta or {}).get("nick") or "sesion sin cuenta local"))
        return False
    con.mandar_interno(0x1A6, seq, r)
    anotar("   S2C FF1A6 mi lugar G de %s: %d fila(s) (%d B)" % ((con.cuenta or {}).get("nick"), r[1], len(r)))
    return True


def _alguna():
    return llave() or llave("RANKING_G")


def solapa0_mi(con, seq, cuerpo):
    """C2S FF1A1 [u32] -> S2C FF1A1 [u8 0][3 x 126 B en cero] (379 B, la forma de las 3 muestras del oficial con estado 0)."""
    if not _alguna() or len(cuerpo) != 4:
        return False
    con.mandar_interno(0x1A1, seq, bytes(1 + 3 * 126))
    anotar("   S2C FF1A1 solapa 0 VACIA (379 B)")
    return True


def solapa0_lista(con, seq, cuerpo):
    """C2S FF1A2 [u32][u8][u8] -> S2C FF1A2 [u8 0][u32 0]."""
    if not _alguna() or len(cuerpo) != 6:
        return False
    con.mandar_interno(0x1A2, seq, bytes(5))
    anotar("   S2C FF1A2 solapa 0 lista VACIA (5 B)")
    return True


MANEJADORES = {
    0x1A1: solapa0_mi,
    0x1A2: solapa0_lista,
    0x1A3: mi_lugar,
    0x1A4: por_pagina,
    0x1A6: mi_lugar_g,
    0x1A7: por_pagina_g,
}
