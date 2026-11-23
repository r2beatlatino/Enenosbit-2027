# -*- coding: utf-8 -*-
r"""charla.py (02-nov) — el CHAT del cliente de Steam (C2S/S2C FF1F4 CmdChatImprove). Plan: Fase 6.

MEDIDO en la grabacion 20261029_215530 (el oficial):
  C2S FF1F4 (130 B): [u8 canal? 03][u8 0x80][texto: buffer de 128 B, terminado en 0 y con basura del cliente detras]
  S2C FF1F4 (592 B): registros de 157 B: [u32 usn del que habla][u32 0][los 130 B del pedido, tal cual][u32 0]
                     [u8 n][apodo en 14 B], y relleno en 0 hasta 592 (⏳ la grabacion tiene 2 registros iguales + ceros:
                     sin medir si es una lista con tope o un eco doble).
  Otra forma S2C de 161 B en la grabacion 213306 ([8 B en 0][01 00][texto][apodo]): ⏳ sin medir cuando va.
Lo que se hace: se reparte un registro (con relleno a 592) a los de la sala del que habla, o a todos los conectados si
esta en el lobby.
"""
import os
import struct

import circulo
import cupon
import estado
import gm
import salas
import textos


def anotar(txt):
    estado.anotar(txt)


def registro(con, cuerpo):
    cuenta = con.cuenta or {}
    nick = textos.codificar(cuenta.get("nick", "Jugador"), 13)
    return (struct.pack("<II", cuenta.get("usn", 0) & 0xFFFFFFFF, 0) + cuerpo[:130].ljust(130, b"\0")
            + struct.pack("<I", 0) + bytes([len(nick)]) + nick.ljust(14, b"\0"))


SUSURRO_CHAT = os.environ.get("SUSURRO_CHAT", "1") == "1"      # ficha 72: susurro por la linea de chat (FF1F4 tipo 4 / 5)


def _registro_susurro(tipo, sub, nick, texto, u4=0, dir=0):
    """S2C FF1F4 de 157 B para el susurro (LEIDO en el manejador 0x02845d80: los tipos 3, 4, 5 y 7 leen solo 157 B):
    [u32 0][u32 u4][u8 tipo][u8 0][texto 129][u8 0][u8 0][u8 dir][u8 0][apodo GBK 13][u8 sub]. El 'sub' (+156, @0x02846044
    y siguientes) decide que hace el cliente; `dir` (+141, @0x0051c5e6..0x0051c606 de 0x0051c4e0 con ch 3 = "Check_Wis"): 1 = linea
    "你对[apodo]" (la que manda), 2 = "apodo对你" (la que recibe), 0 = sin marca (sale como [公开]; MEDIDO con el juego). Tipo 4: 1 = muestra el susurro, 0 = texto 92 (no es amigo), 3 = texto 507 con `u4` en %d, 4 = 460
    (lenguaje), 5 = 1308 (silenciado). Tipo 5: 0 = muestra el susurro, 2 = texto 507 con el apodo (+143), 4 y 5 como arriba."""
    return (struct.pack("<II", 0, u4 & 0xFFFFFFFF) + bytes([tipo, 0]) + texto[:128].ljust(129, b"\0") + bytes([0, 0, dir, 0])
            + nick[:13].ljust(13, b"\0") + bytes([sub]))


def susurrar(con, seq, cuerpo):
    """C2S FF1F4 de la linea de chat en la solapa 悄悄话 (LEIDO @0x0051fced..0x0051fd91 y SendChatImprove 0x02846470):
    tipo 4 = a un AMIGO: [04][b][128 texto][u32 usn]; tipo 5 = por APODO: [05][b][128 texto][u8 L][apodo]. Al destino un
    registro con el mismo tipo y el apodo de quien habla; al que habla, el eco con el apodo del destino (HIPOTESIS que se
    prueba con el juego). Sin conectar: tipo 4 sub 3, tipo 5 sub 2; no es amigo (tipo 4): sub 0."""
    import social
    yo = con.cuenta or {}
    tipo = cuerpo[0]
    texto = cuerpo[2:130].split(b"\0", 1)[0]
    if not yo.get("usn") or not texto:
        return False
    if gm.esta_silenciado(con):
        anotar("   FF1F4 susurro bloqueado (silenciado): %s" % yo.get("nick"))
        return True
    mi_nick = social._gbk(yo.get("nick", ""), 13)
    if tipo == 4:
        if len(cuerpo) != 134:
            return False
        usn = struct.unpack_from("<I", cuerpo, 130)[0]
        me = social._de(social._amigos(), yo["usn"])
        if usn not in me["amigos"]:
            con.mandar_interno(0x1F4, seq, _registro_susurro(4, 0, b"", texto))
            anotar("   FF1F4 susurro tipo 4 de %s: el destino no es su amigo (sub 0)" % yo.get("nick"))
            return True
        otro = social._conectado(usn)
        if otro is None:
            con.mandar_interno(0x1F4, seq, _registro_susurro(4, 3, b"", texto, usn))
            anotar("   FF1F4 susurro tipo 4 de %s: el amigo no esta conectado (sub 3)" % yo.get("nick"))
            return True
        su_nick = social._gbk((otro.cuenta or {}).get("nick", ""), 13)
        otro.mandar_interno(0x1F4, 0, _registro_susurro(4, 1, mi_nick, texto, 0, 2))
        con.mandar_interno(0x1F4, seq, _registro_susurro(4, 1, su_nick, texto, 0, 1))
    elif tipo == 5:
        if len(cuerpo) < 131 or len(cuerpo) != 131 + cuerpo[130]:
            return False
        nick = cuerpo[131:131 + cuerpo[130]]
        c = social._por_nick(textos.decodificar(nick))
        otro = social._conectado(c["usn"]) if c else None
        if otro is None or otro is con:
            con.mandar_interno(0x1F4, seq, _registro_susurro(5, 2, nick, texto))
            anotar("   FF1F4 susurro tipo 5 de %s: sin destino conectado (sub 2)" % yo.get("nick"))
            return True
        su_nick = social._gbk((otro.cuenta or {}).get("nick", ""), 13)
        otro.mandar_interno(0x1F4, 0, _registro_susurro(5, 0, mi_nick, texto, 0, 2))
        con.mandar_interno(0x1F4, seq, _registro_susurro(5, 0, su_nick, texto, 0, 1))
    else:
        return False
    anotar("   FF1F4 susurro tipo %d de %s: %d B de texto entregado" % (tipo, yo.get("nick"), len(texto)))
    return True


def hablar(con, seq, cuerpo):
    if SUSURRO_CHAT and cuerpo[:1] in (b"\x04", b"\x05") and len(cuerpo) > 130:
        return susurrar(con, seq, cuerpo)
    if len(cuerpo) != 130:
        return False
    texto = cuerpo[2:130].split(b"\0", 1)[0]
    if gm.atender(con, texto):
        return True
    if cupon.atender(con, texto):
        return True
    if circulo.atender(con, texto):
        return True
    sala = estado.SALAS.get(con.sala)
    destinos = salas.jugadores(sala) if sala is not None else list(estado.CONEXIONES.values())
    r = registro(con, cuerpo).ljust(592, b"\0")
    for c in destinos:
        c.mandar_interno(0x1F4, seq if c is con else 0, r)
    anotar("   FF1F4 CHAT de %s (canal %02x %02x): %r [hex %s] -> %d destinos (%s)"
           % ((con.cuenta or {}).get("nick"), cuerpo[0], cuerpo[1], textos.decodificar(texto), texto.hex(), len(destinos),
              "sala %d" % sala.numero if sala is not None else "lobby"))
    return True


def registro161(con, tipo, texto):
    """S2C FF1F4 de 161 B como lo manda el oficial (MEDIDO 08-nov, 127 de 127; layout de leer_manejador FF1F4):
    [8 B en 0][u8 tipo][u8 0][texto hasta 128 B, relleno de ceros hasta 129][4 B en 0][apodo GBK en 13 B][u8 0][u32 0].
    Sin basura del cliente, sin el 0x80, usn en 0."""
    nick = textos.codificar((con.cuenta or {}).get("nick", "Jugador"), 12)
    return (bytes(8) + bytes([tipo, 0]) + texto[:128].ljust(129, b"\0") + bytes(4) + nick.ljust(13, b"\0")
            + b"\0" + bytes(4))


def de_la_sala(con):
    """La sala del que habla, o None si no esta en ninguna (en carrera/gestos no se reparte a nadie fuera de una sala)."""
    return estado.SALAS.get(con.sala)


def hablar_en_carrera(con, seq, cuerpo):
    """C2S FF8 SendChat [u8 L][texto, sin 0 final] (MEDIDO 15 de 15) -> S2C FF1F4 tipo 1 a TODA la sala, tambien al que
    habla (MEDIDO 15 de 15: el oficial no contesta con FF8). HIPOTESIS: a la sala y no a todo el lobby (los 3 testigos
    siempre estuvieron juntos)."""
    if len(cuerpo) < 1 or len(cuerpo) != cuerpo[0] + 1:
        return False
    texto = cuerpo[1:].split(b"\0", 1)[0]
    if gm.atender(con, texto):
        return True
    if cupon.atender(con, texto):
        return True
    if circulo.atender(con, texto):
        return True
    sala = de_la_sala(con)
    if sala is None:
        anotar("   FF8 CHAT en carrera de alguien sin sala: no se reparte")
        return True
    r = registro161(con, 1, texto)
    for c in list(salas.jugadores(sala)):
        c.mandar_interno(0x1F4, 0, r)
    anotar("   FF8 -> FF1F4 tipo 1 de %s: %d B de texto -> %d destinos (sala %d)"
           % ((con.cuenta or {}).get("nick"), len(texto), len(salas.jugadores(sala)), sala.numero))
    return True


# FFCB: palabra clave -> animacion (CP949). MEDIDO 08-nov: hi -> 인사 (x4), no -> 싫어 (x4), me -> 저요 (x1).
# Las demas palabras que vio el oficial (의문, 하이야, 웃음, 레디, 징글벨, 액션AC1083B) NO se conoce su palabra: sin tabla.
GESTOS = {b"hi": "인사", b"no": "싫어", b"me": "저요"}

# 13-nov (ficha 133): GESTOS_TODOS=1 (apagada por omision) suma la tabla de TODOS los idiomas (servidor_local/datos/palabras_gestos.json,
# la arma tools/modern-client/generar_palabras_gestos.py de los emoticon*.txt de C, L, S, J, D y K). MEDIDO con el juego: el cliente
# solo manda FFCB para las palabras que estan en SU emoticon.txt (hola, gracias, obrigado no llegaron; hi y no si): para palabras
# de otros idiomas el cliente necesita ademas el emoticon_union.txt (VOCES_PALABRAS=1, ver voces.js). Con 0 todo es como hoy.
GESTOS_TODOS = os.environ.get("GESTOS_TODOS", "0") == "1"
ARCHIVO_PALABRAS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "palabras_gestos.json")
CODIFICACIONES = ("gb18030", "cp949", "cp1252", "utf-8")       # la palabra llega en la pagina del cliente: GBK/GB18030, 949, 1252 o UTF-8
_TABLA = {}


def _norm(p):
    import unicodedata
    return unicodedata.normalize("NFC", p).strip().casefold()


def _sin_acentos(p):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", p) if not unicodedata.combining(c))


def _tabla():
    """{palabra normalizada: animacion} de palabras_gestos.json (se lee una vez; vacia si falta el archivo)."""
    if not _TABLA:
        try:
            import json
            with open(ARCHIVO_PALABRAS, encoding="utf-8") as f:
                datos = json.load(f)["palabras"]
        except (OSError, ValueError, KeyError):
            datos = {}
        _TABLA["pal"] = datos
        _TABLA["sin"] = {}
        for k, a in datos.items():
            _TABLA["sin"].setdefault(_sin_acentos(k), a)
    return _TABLA


def animacion_de(palabra):
    """La animacion (str, CP949 al mandarla) de una palabra del C2S FFCB, o None. Sin GESTOS_TODOS: solo hi / no / me, como hoy."""
    anim = GESTOS.get(palabra)
    if anim is not None or not GESTOS_TODOS:
        return anim
    t = _tabla()
    for enc in CODIFICACIONES:
        try:
            s = palabra.decode(enc)
        except UnicodeDecodeError:
            continue
        k = _norm(s)
        if k in t["pal"]:
            return t["pal"][k]
        if _sin_acentos(k) in t["sin"]:
            return t["sin"][_sin_acentos(k)]
    return None


def gesto(con, seq, cuerpo):
    """C2S FFCB SendMessageCheck [u8 L][palabra][u8 marca] (MEDIDO 9 de 9, L=2, marca 0) -> S2C FFCB
    [u8 asiento][u8 L'][animacion CP949][u8 marca] a toda la sala, tambien al que lo pidio (MEDIDO 9 de 9).
    Palabra fuera de la tabla: no se contesta (HIPOTESIS: el oficial tampoco). El asiento es el del FF17."""
    if len(cuerpo) < 2 or len(cuerpo) != cuerpo[0] + 2:
        return False
    palabra, marca = cuerpo[1:1 + cuerpo[0]], cuerpo[-1]
    sala = de_la_sala(con)
    anim = animacion_de(palabra)
    if sala is None or anim is None:
        return True
    asiento = next((a for a, c in sala.asientos.items() if c is con), None)
    if asiento is None:
        return True
    a = anim.encode("cp949")
    r = bytes([asiento, len(a)]) + a + bytes([marca])
    for c in list(salas.jugadores(sala)):
        c.mandar_interno(0xCB, 0, r)
    anotar("   FFCB gesto %r (asiento %d) -> %d destinos (sala %d)" % (palabra, asiento, len(salas.jugadores(sala)), sala.numero))
    return True


MANEJADORES = {
    0x08: hablar_en_carrera,
    0xCB: gesto,
    0x1F4: hablar,
}
