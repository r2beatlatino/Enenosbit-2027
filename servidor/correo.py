# -*- coding: utf-8 -*-
r"""correo.py (11-nov, ficha 73) — el CORREO del cliente de Steam: cartas entre amigos. Layouts leidos del exe (un solo
testigo, salvo la lista vacia FF218 que tiene 4 pares grabados): docs/tablero/layouts/FF218.md, FF219.md, FF21A.md,
FF21B.md, FF21C.md.

  C2S FF218 [u32 pagina][u8 caja][u32 cant]    -> S2C FF218 [u8 res][u8 caja][u32 total][u32 cursor][u32 n][n x 61 B]
  C2S FF21A [u32 id][u8 caja]                  -> S2C FF21A [u8 res][201 B: u32 id, u8 caja, 21 B, texto NUL desde +0x1a]
  C2S FF21B [u8 caja][u32 n][n x {u8 x,u32 id}]  -> S2C FF21B [u8 res][u8 modo][u32 n][n x 5 B]
  C2S FF21C [u32 usn destino][u8 L][L bytes]   -> S2C FF21C [u8 res][u8 0]     (res 0 enviada, 2 no es amigo, otro = DB_ERROR)
  C2S FF219 [u8 L][apodo]                      -> S2C FF219 [u8 res][u32 usn][13 B apodo]   (0 amigo, 1 no existe, 2 existe)

NO atiende (HIPOTESIS / sin leer): adjuntos (FF21D, FF24D), FF21E, plantillas `$`, aviso por empuje, "borrar todo" (ids 0/1).

Guardado: seccion `correo` de la cuenta DESTINATARIA en cuenta.json (solo via cuenta.py):
  {"sig_id": N, "cartas": [{id, caja, de_usn, de_nick, leida, adjunto, retirado, enviada, vence, texto, cat}]}
`texto` son los bytes tal cual llegaron, guardados como latin-1 (vuelven identicos). Sin la seccion = buzon vacio y no se escribe nada
hasta la primera carta. La sesion capturada (sin cuenta local) contesta lista vacia y no puede mandar.
Decisiones LOCALES (el oficial no se conoce): vencen a los 30 dias; tope 10000 por caja; orden: la mas nueva primero; las ids
empiezan en 100 (para no chocar con los ids 0/1 del "borrar todo").
CORREO=0 apaga todo (vuelve a "sin atender").
"""
import os
import struct
import time

import cuenta as _cta
import estado
import textos

CORREO = os.environ.get("CORREO", "1") == "1"
TOPE = 10000
DIAS = 30
ID_INICIAL = 100
RES_OK, RES_NO_AMIGO, RES_ERROR = 0, 2, 3


def anotar(txt):
    estado.anotar(txt)


def _yo(con):
    return (con.cuenta or {}).get("usn")


def _nick_de(usn):
    c = next((c for c in _cta.todas_planas() if c.get("usn") == usn), None)
    return (c or {}).get("nick", "")


def _gbk(t, n):
    return textos.codificar(t, n)


def _cartas(usn, caja=None):
    cs = list((_cta.leer_seccion(usn, "correo") or {}).get("cartas") or [])
    return [c for c in cs if caja is None or c["caja"] == caja]


def _fila(c):
    """La fila de 61 B (layouts/FF218.md): solo lo leido; adjunto/retirado y los sin uso en 0; +5 (avisada) siempre 1."""
    f = bytearray(61)
    struct.pack_into("<I", f, 0, c["id"])
    f[4] = c["caja"]
    f[5] = 1
    struct.pack_into("<I", f, 6, c["de_usn"])
    n = _gbk(c["de_nick"], 12)
    f[0x0e:0x0e + len(n)] = n
    f[0x1b] = 1 if c["leida"] else 0
    f[0x1c] = 0
    f[0x1d] = 0
    e = c["enviada"].encode("ascii")[:14]
    f[0x1e:0x1e + len(e)] = e
    v = c["vence"].encode("ascii")[:8]
    f[0x2d:0x2d + len(v)] = v
    assert len(f) == 61
    return bytes(f)


def lista(con, seq, cuerpo):
    """FF218: pagina de la caja pedida. Sin cuenta local o sin la seccion: lista vacia (los 14 B de las grabaciones)."""
    if not CORREO or len(cuerpo) != 9:
        return False
    pag, caja, cant = struct.unpack("<IBI", cuerpo)
    yo = _yo(con)
    cs = sorted(_cartas(yo, caja), key=lambda c: -c["id"]) if yo is not None else []
    cant = max(0, min(cant, 512))
    parte = cs[pag * cant:(pag + 1) * cant] if cant else []
    con.mandar_interno(0x218, seq, struct.pack("<BBIII", 0, caja, len(cs), 0, len(parte)) + b"".join(_fila(c) for c in parte))
    anotar("   FF218 correo de %s: caja %d pagina %d -> %d de %d cartas" % ((con.cuenta or {}).get("nick"), caja, pag, len(parte), len(cs)))
    return True


def leer(con, seq, cuerpo):
    """FF21A: el texto de una carta; la marca leida. Id inexistente: res generico y 201 B en cero."""
    if not CORREO or len(cuerpo) != 5:
        return False
    cid, caja = struct.unpack("<IB", cuerpo)
    yo = _yo(con)

    def f(sec):
        for c in sec.get("cartas") or []:
            if c["id"] == cid:
                c["leida"] = 1
                return dict(c)
        return None
    c = None
    if yo is not None and _cartas(yo):
        c = _cta.cambiar_seccion(yo, "correo", f)
    if c is None:
        con.mandar_interno(0x21A, seq, bytes([RES_ERROR]) + bytes(201))
        anotar("   FF21A leer %d de %s: no existe" % (cid, (con.cuenta or {}).get("nick")))
        return True
    cu = bytearray(201)
    struct.pack_into("<I", cu, 0, c["id"])
    cu[4] = c["caja"]
    t = c["texto"].encode("latin-1")[:175]
    cu[0x1a:0x1a + len(t)] = t
    con.mandar_interno(0x21A, seq, b"\x00" + bytes(cu))
    anotar("   FF21A leer %d de %s: %d B" % (cid, (con.cuenta or {}).get("nick"), len(t)))
    return True


def borrar(con, seq, cuerpo):
    """FF21B: borra por ids reales. Ids 0/1 (el 'borrar todo' sin leer) -> sin atender (False)."""
    if not CORREO or len(cuerpo) < 5:
        return False
    n = struct.unpack_from("<I", cuerpo, 1)[0]
    if n > 50 or len(cuerpo) != 5 + 5 * n:
        return False
    items = [struct.unpack_from("<BI", cuerpo, 5 + 5 * i)[::-1] for i in range(n)]       # elemento de 5 B = [u8 x][u32 id] (MEDIDO con juego)
    if n == 0 or any(i < 2 for i, _x in items):
        return False
    yo = _yo(con)
    ids = {i for i, _x in items}

    def f(sec):
        cs = sec.get("cartas") or []
        hechos = [c["id"] for c in cs if c["id"] in ids]
        if hechos:
            sec["cartas"] = [c for c in cs if c["id"] not in ids]
        return hechos
    hechos = _cta.cambiar_seccion(yo, "correo", f) if yo is not None and _cartas(yo) else []
    if not hechos:
        con.mandar_interno(0x21B, seq, struct.pack("<BBI", RES_ERROR, 0, 0))
        anotar("   FF21B borrar de %s: ninguna de %d existia" % ((con.cuenta or {}).get("nick"), n))
        return True
    echo = list(dict.fromkeys((i, x) for i, x in items if i in hechos))     # el cliente manda la misma id dos veces
    con.mandar_interno(0x21B, seq, struct.pack("<BBI", 0, 0, len(echo)) + b"".join(struct.pack("<BI", x, i) for i, x in echo))
    anotar("   FF21B borrar de %s: %d carta(s)" % ((con.cuenta or {}).get("nick"), len(hechos)))
    return True


def escribir(con, seq, cuerpo):
    """FF21C: manda una carta a un AMIGO (la lista de social.py). Si no es amigo: res 2. Cualquier otra falla: res 3."""
    if not CORREO or len(cuerpo) < 5:
        return False
    import social
    dest = struct.unpack_from("<I", cuerpo, 0)[0]
    L = cuerpo[4]
    yo = _yo(con)

    def resp(res, que):
        con.mandar_interno(0x21C, seq, bytes([res, 0]))
        anotar("   FF21C de %s a %d: res %d (%s)" % ((con.cuenta or {}).get("nick"), dest, res, que))
        return True
    if yo is None:
        return resp(RES_ERROR, "sesion sin cuenta local")
    if not 1 <= L <= 80 or len(cuerpo) != 5 + L or dest == 0 or dest == yo:
        return resp(RES_ERROR, "datos invalidos L=%d" % L)
    if dest not in (social._amigos().get(yo) or {}).get("amigos", []) or _cta.leer(dest) is None:
        return resp(RES_NO_AMIGO, "no es amigo")
    ahora = time.time()
    carta = {"caja": 0, "de_usn": yo, "de_nick": (con.cuenta or {}).get("nick") or _nick_de(yo), "leida": 0, "adjunto": 0,
             "retirado": 0, "enviada": time.strftime("%Y%m%d%H%M%S", time.localtime(ahora)),
             "vence": time.strftime("%Y%m%d", time.localtime(ahora + DIAS * 86400)),
             "texto": cuerpo[5:].decode("latin-1"), "cat": 0}

    def f(sec):
        cs = sec.setdefault("cartas", [])
        if sum(1 for c in cs if c["caja"] == 0) >= TOPE:
            return None
        cid = max(sec.get("sig_id", ID_INICIAL), ID_INICIAL)
        sec["sig_id"] = cid + 1
        cs.append(dict(carta, id=cid))
        return cid
    cid = _cta.cambiar_seccion(dest, "correo", f)
    if cid is None:
        return resp(RES_ERROR, "buzon lleno")
    return resp(RES_OK, "carta %d" % cid)


def buscar_apodo(con, seq, cuerpo):
    """FF219: apodo -> usn (el MISMO criterio que social._por_nick: la primera cuenta con ese apodo). 0 amigo, 1 no existe, 2 existe."""
    if not CORREO or len(cuerpo) < 1 or len(cuerpo) != 1 + cuerpo[0]:
        return False
    import social
    nick = textos.decodificar(cuerpo[1:])
    yo = _yo(con)
    c = social._por_nick(nick)
    if c is None or yo is None or c.get("usn") == yo:
        con.mandar_interno(0x219, seq, bytes([1]) + bytes(17))
        anotar("   FF219 buscar %r: no existe" % nick)
        return True
    u = c["usn"]
    res = 0 if u in (social._amigos().get(yo) or {}).get("amigos", []) else 2
    con.mandar_interno(0x219, seq, bytes([res]) + struct.pack("<I", u) + _gbk(c.get("nick", ""), 12).ljust(13, b"\x00"))
    anotar("   FF219 buscar %r -> usn %d res %d" % (nick, u, res))
    return True


MANEJADORES = {
    0x218: lista,
    0x219: buscar_apodo,
    0x21A: leer,
    0x21B: borrar,
    0x21C: escribir,
}
