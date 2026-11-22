# -*- coding: utf-8 -*-
r"""practica.py (ficha 38) — EMPEZAR UNA CANCION (FF3A) y MANDAR SUS NOTAS (FF57): lo que el cliente pide al jugar, en practica o
en carrera. Estaba dentro de juego.py (`responder_comandos`); ahora es un modulo recargable con su tabla MANEJADORES.

Del oficial chino (cosecha del 17-sep, `tools/net/proxy_mitm.log.cosecha-20260917`):
    C2S FF3A  02 fe2d 0000                [dificultad][songid:u16][...]
    S2C FF3A  02 01 3d0f0000 fe2d          [dificultad][01][partida:u32][songid:u16]
    C2S FF57  fe2d                         [songid:u16]
    S2C FF57  01 fe2d 8c05 <chart>         [01][songid:u16][largo:u16][chart]  (igual que el 2013)

El orden de despacho no cambia: manejadores.py los pone DESPUES de misiones (cuyo 0x3A de 5 B es la historia y cuyo 0x57 solo
observa) y estos contestan lo que las misiones dejaron pasar.
"""
import struct

import captura
import estado

JUGABLES = captura.jugables()          # los songid con chart 1 a 1 (herramientas/emparejar_charts.py)


def anotar(txt):
    estado.anotar(txt)


def empezar_cancion(con, seq, cuerpo):
    """C2S FF3A [dificultad][songid:u16]... -> S2C FF3A [dificultad][01][partida:u32][songid:u16]. La partida cuenta de a una
    por conexion (con.partida)."""
    if len(cuerpo) < 3:
        return False
    dif, sid = cuerpo[0], struct.unpack_from("<H", cuerpo, 1)[0]
    con.partida += 1
    con.mandar_interno(0x3A, seq, bytes([dif, 1]) + struct.pack("<IH", con.partida, sid))
    anotar("   S2C FF3A EMPEZAR cancion %d dificultad %d (partida %d)%s"
           % (sid, dif, con.partida, "" if sid in JUGABLES else "  ⚠ NO tiene chart 1 a 1"))
    return True


def notas(con, seq, cuerpo):
    """C2S FF57 [songid:u16] -> S2C FF57 con el chart 1 a 1 del servidor 2013; sin chart, [00] y un aviso fuerte."""
    if len(cuerpo) < 2:
        return False
    sid = struct.unpack_from("<H", cuerpo, 0)[0]
    import baile                      # 20-nov (ficha 178): ids del Club (bit 0x4000), otro formato; solo con BAILE=1
    club = baile.notas_club(sid)
    if club is not None:
        con.mandar_interno(0x57, seq, club)
        return True
    chart = captura.chart(sid)
    if chart is not None:
        con.mandar_interno(0x57, seq, b"\x01" + struct.pack("<HH", sid, len(chart)) + chart)
        anotar("   S2C FF57 NOTAS de la cancion %d: %d B (chart 1 a 1 del servidor 2013)" % (sid, len(chart)))
    else:
        # ⛔ en el 2013, un result=0 termina matando al cliente; aca se avisa fuerte
        con.mandar_interno(0x57, seq, b"\x00")
        anotar("   ⛔ S2C FF57 SIN NOTAS para la cancion %d: no tiene chart 1 a 1 (el cliente puede cerrarse)" % sid)
    return True


MANEJADORES = {
    0x3A: empezar_cancion,
    0x57: notas,
}
