# -*- coding: utf-8 -*-
"""baile.py (ficha 178) — manejadores de Modo Baile (Club) para cuentas LOCALES.

Todo queda detras de la llave BAILE (=1 para activar; omision 0 para no alterar la sesion capturada de Benja).
"""
import os
import struct

import cuenta
import estado

LLAVES_OMISION = {"BAILE": "0"}
# 20-nov: el canal de las salas del Club (u8 del FF1F5 y canal del FF1F6 que manda el cliente, MEDIDO con dos copias)
CANAL_CLUB = 13


def anotar(txt):
    estado.anotar(txt)


def activo():
    return os.environ.get("BAILE", LLAVES_OMISION["BAILE"]) == "1"


def tutorial_hecho(cuenta_o_usn):
    if not activo() or cuenta_o_usn is None:
        return 0
    usn = cuenta_o_usn.get("usn") if isinstance(cuenta_o_usn, dict) else cuenta_o_usn
    if not usn:
        return 0
    acc = cuenta.leer(usn)
    return int(((acc or {}).get("baile") or {}).get("tutorial", 0))


def marcar_tutorial(usn, valor=1):
    def _upd(acc):
        b = acc.setdefault("baile", {})
        b["tutorial"] = int(valor)
    return cuenta.cambiar(usn, _upd)


def cmd_tutorial(con, seq, cuerpo):
    if not activo() or getattr(con, "cuenta", None) is None:
        return False
    usn = con.cuenta.get("usn")
    if not usn:
        return False
    modo = struct.unpack_from("<I", cuerpo, 0)[0] if len(cuerpo) >= 4 else 1
    marcar_tutorial(usn, 1)
    con.mandar_interno(0xE7, seq, struct.pack("<BII", 0, 1, 0))
    anotar("   S2C FFE7 tutorial baile de %s: marcado hecho (modo=%d, flag=1)" % (con.cuenta.get("nick"), modo))
    return True


def cmd_edit_club_music(con, seq, cuerpo):
    """20-nov (ficha 178 + 77): C2S FF83 CmdEditClubMusic. El cliente lo manda al crear la sala del Club y al abrir el
    selector 选择音乐 (que sale VACIO); su manejador S2C (0x02791f70) salta enseguida a la pieza que falta 0x0f2c272a.
    No hay grabacion del oficial. Llave CLUB_FF83 (omision vacia = no se atiende, como antes):
      anotar -> solo anota los bytes y no contesta;
      eco    -> ademas devuelve el MISMO cuerpo como S2C FF83 (INVENTADO: solo para que el cliente entre a su manejador y
                se pueda cazar la pieza; no es un arreglo);
      sala   -> lo reparte a todos los de la sala (INVENTADO, HIPOTESIS: asi se fija la cancion del Club en cada cliente);
      lista  -> ante el tipo 6 manda [u8 1][u16 cancion] a la sala (INVENTADO, HIPOTESIS 2: el S2C es una lista)."""
    llave = os.environ.get("CLUB_FF83", "")
    if not activo() or llave not in ("anotar", "eco", "sala", "lista"):
        return False
    anotar("   C2S FF83 CmdEditClubMusic (%d B): %s" % (len(cuerpo), cuerpo.hex()))
    # 20-nov, MEDIDO: al crear la sala manda `03 0000`; al apretar START, con la cancion 16706 elegida, `06 4241`
    # = [u8 6][u16 16706]. El servidor la guarda en la sala y carrera.empezar la pone en el FF25 (en vez de sortear una
    # de carrera, que el anfitrion del Club no encuentra: cae en 0x0080621b leyendo una tabla vacia).
    if len(cuerpo) >= 3 and cuerpo[0] == 6:
        import carrera
        sala = carrera.sala_de(con)
        if sala is not None:
            sala.club_cancion = struct.unpack_from("<H", cuerpo, 1)[0]
            anotar("   FF83: cancion del Club %d guardada en la sala %d" % (sala.club_cancion, sala.numero))
    if llave == "eco":
        con.mandar_interno(0x83, seq, bytes(cuerpo))
        anotar("   S2C FF83 eco INVENTADO (%d B) para cazar 0x0f2c272a" % len(cuerpo))
    elif llave == "sala":
        # 20-nov: HIPOTESIS (sin grabacion): el anfitrion espera el FF83 de vuelta para fijar la cancion de la sala; sin
        # eso la carga lee la cancion 0 (0x00826d50 recibe 0) y cae en 0x0080621b. Se reparte el mismo cuerpo a la sala.
        import carrera, salas
        sala = carrera.sala_de(con)
        destinos = salas.jugadores(sala) if sala is not None else [con]
        for c in destinos:
            c.mandar_interno(0x83, seq if c is con else 0, bytes(cuerpo))
        anotar("   S2C FF83 INVENTADO (%d B) repartido a %d de la sala" % (len(cuerpo), len(destinos)))
    elif llave == "lista" and len(cuerpo) >= 3 and cuerpo[0] == 6:
        # 20-nov: HIPOTESIS 2 (sin grabacion): el S2C es [u8 n][n x u16 cancion]. Repartir `06 4241` hizo que el cliente
        # cargara 16706 y despues una cancion 0 (0x00826d50 recibe 0): como si leyera 6 canciones. La pieza 0x0f2c272a
        # hace lo MISMO con tipo 3 y tipo 6 (MEDIDO: 5 tramos iguales, mismos pasos). Se manda [1][cancion] a la sala.
        import carrera, salas
        sala = carrera.sala_de(con)
        destinos = salas.jugadores(sala) if sala is not None else [con]
        nuevo = struct.pack("<BH", 1, struct.unpack_from("<H", cuerpo, 1)[0])
        for c in destinos:
            c.mandar_interno(0x83, seq if c is con else 0, nuevo)
        anotar("   S2C FF83 INVENTADO [1][%d] repartido a %d de la sala" % (struct.unpack_from("<H", cuerpo, 1)[0], len(destinos)))
    return True


def notas_club(sid):
    """20-nov: cuerpo del S2C FF57 para un id del Club (bit 0x4000), o None.

    Formato LEIDO en dos binarios (2019 CmdGetNoteData 0xd12b70, rama `sid & 0x4000`; chino 0x027acd00, misma prueba en
    0x027ad008 y el mismo tope 0x30 del texto): [u8 resultado][u16 id][u8 L][L B: MD5 en hex '%02x' de los T bytes]
    [u32 T][T B = u16 N, N x (u32 largo, trozo)]. Si la huella coincide el cliente manda FFE9 SendGetClubNoteSuccess.
    Cada trozo es zlib (2019 0x7c5860 '[Club] ClubNote uncompress failed'): [3 B indice "001"][u8 0][u8 nivel][u8 0]
    [u8 M][M x 21 B nota] — el mismo formato que los .dat del tutorial (rnr_club_mission/mission_1/cn1_0001.dat).

    Llave de DIAGNOSTICO CLUB_NOTAS=<carpeta>: manda los *.dat de esa carpeta (fuera de git; p.ej. los del tutorial)
    como notas de CUALQUIER id del Club. INVENTADO: las notas reales de cada cancion del Club NO CONSTAN (las da el
    servidor oficial; no hay grabacion)."""
    import glob
    import hashlib
    carpeta = os.environ.get("CLUB_NOTAS")
    if not activo() or not carpeta or not (sid & 0x4000):
        return None
    trozos = [open(p, "rb").read() for p in sorted(glob.glob(os.path.join(carpeta, "*.dat")))]
    if not trozos:
        return None
    datos = struct.pack("<H", len(trozos)) + b"".join(struct.pack("<I", len(t)) + t for t in trozos)
    huella = hashlib.md5(datos).hexdigest().encode()
    anotar("   S2C FF57 notas del Club %d: %d trozos de %s (INVENTADO, llave CLUB_NOTAS), md5 %s"
           % (sid, len(trozos), carpeta, huella.decode()))
    # el RX copia T+4 bytes para la huella (2019 0xd12cd2, chino 0x027ad168: si quedan menos no copia nada y la huella
    # no coincide -> vuelve a pedir sin fin, NOTAS_CLUB_A) pero la calcula sobre T: van 4 bytes de cola (ceros: su valor
    # NO CONSTA)
    return (b"\x01" + struct.pack("<HB", sid, len(huella)) + huella + struct.pack("<I", len(datos)) + datos
            + bytes(4))


def cmd_club_nota_ok(con, seq, cuerpo):
    """C2S FFE9 SendGetClubNoteSuccess: el cliente acepto las notas del Club. Se anota; sin respuesta."""
    anotar("   C2S FFE9 SendGetClubNoteSuccess (%d B): %s" % (len(cuerpo), bytes(cuerpo).hex()))
    return True


MANEJADORES = {
    0xE7: cmd_tutorial,
    0x83: cmd_edit_club_music,
    0xE9: cmd_club_nota_ok,
}
