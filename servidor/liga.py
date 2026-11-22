# -*- coding: utf-8 -*-
r"""liga.py (12-nov, ficha 97 parte B) — el boton de la liga (排位赛; en el lobby es `BTN_RANKING`, clic en 0x02a88e5b): contesta lo MISMO que
contesto el oficial en la grabacion: `match.signin` con el codigo 1095 = "liga cerrada" (cartel de la fila 3414 "排位赛暂未开放").

  C2S FF24C SendMatchSignin [u32]                        (LEIDO 0x028760f0; grabado 1 vez, 4 B)
  S2C FF255 CmdRankedMatchForward  (LEIDO 0x0286bde0; docs/tablero/layouts/rankedMatch.md §1 y §3):
      [u64 A][u64 id][u32 12]["match.signin"][u32 4]["1095"][u32 36][36 B sello]      = 80 B (MEDIDO: 16+4+12+4+4+4+36)

QUE CAMBIA POR MENSAJE (todo lo demas es igual al del oficial, byte a byte):
  - A: contador por canal que solo crece (el oficial: 27764 despues de otros FF255; aqui estado._liga_A, arranca en 0x30000, como jardin.py).
  - nonce del sello (4 ultimos bytes) y los 32 B que dependen de el: al azar en cada mensaje, como el oficial (sello.py).
  - id: 0 (el `match.signin` del oficial NO contesta a un pedido FF255: viene suelto y lleva id = 0). No cambia.
  - el `seq` del marco interno: 0 (el oficial: 0 en FF255).
NO se abre la ventana (codigo 1013) ni se empareja: no hay respuesta buena del oficial con que contrastar.
Llave por entorno LIGA_CERRADA (omision en LLAVES_OMISION; =0 y el FF24C queda sin contestar, como antes). Vale para toda conexion.
"""
import os
import struct

import estado
import sello

LLAVES_OMISION = {"LIGA_CERRADA": "1"}      # 1 desde que con el juego salio el cartel "clasificatorias todavia no abiertas" 3 de 3 y nada se trabo (ficha 97)
CODIGO = "1095"                             # 0x447: "liga cerrada" (LEIDO 0x028ee3f5 -> cartel fila 3414); el unico que dio el oficial
NOMBRE = "match.signin"


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="LIGA_CERRADA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def _contador():
    a = getattr(estado, "_liga_A", None)
    if a is None:
        a = {"255": 0x30000}
        estado._liga_A = a
    return a


def sobre(codigo=CODIGO, a=None, nonce=None):
    """El cuerpo S2C de `match.signin`. `a` y `nonce` None = los elige el modulo (contador y al azar)."""
    if a is None:
        c = _contador()
        c["255"] += 1
        a = c["255"]
    nb = NOMBRE.encode("ascii")
    jb = codigo.encode("ascii")
    s = sello.sellar(jb, nonce)
    return (struct.pack("<QQ", a, 0) + struct.pack("<I", len(nb)) + nb + struct.pack("<I", len(jb)) + jb
            + struct.pack("<I", len(s)) + s)


def signin_24c(con, seq, cuerpo):
    """C2S FF24C [u32]: contesta el match.signin 'liga cerrada' por FF255."""
    if not llave() or len(cuerpo) != 4:
        return False
    cu = sobre()
    con.mandar_interno(0x255, 0, cu)
    anotar("   C2S FF24C -> S2C FF255 match.signin %s (liga cerrada, %d B, sello propio) a %s" % (CODIGO, len(cu), (con.cuenta or {}).get("nick")))
    return True


MANEJADORES = {0x24C: signin_24c}
