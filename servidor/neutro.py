# -*- coding: utf-8 -*-
"""neutro.py (ficha 168) — plantillas neutras cuando faltan las capturas del oficial (VPS sin datos del dueño).

Reglas:
- Se usan SOLO si falta la captura correspondiente; en la PC del dueño, con las capturas presentes, no cambian ningun byte.
- Valores neutros (inventario vacio, sin amigos ni pareja, apodo y numeros de cuenta del servidor).
- Cada campo cuyo significado no se conoce va marcado con `INVENTADO` y el valor elegido.
"""
import os
import struct
import time

import ajustes
import captura
import estado
import textos

# ---------- Hueco 1: saludo FF04 y login del juego FF02 (sin juego_S2C.bin) ----------
FF02_SEMILLA = 0  # INVENTADO: semilla XOR del FF02 neutro (4 B en +5)



# ficha 183: los escenarios (pistas) del FF00 en modo VPS = los del oficial (ver ficha_cuenta)
ESCENARIOS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 56, 58, 0x4000, 0x4001, 0x4002, 0x4003, 0x4005)

def ff04_cabeza():
    """Cabeza de 21 B de S2C FF04 (antes del u32 timestamp). CmdCheckVer (0x0277b410) solo lee el byte 0 (0 = OK)."""
    # INVENTADO: bytes 1..20 en cero salvo version=4 en +1..+5; el cliente solo lee byte 0
    return bytes([0]) + struct.pack("<I", 4) + bytes(16)


def ff02_cuerpo(clave, llave):
    """S2C FF02 de 269 B: [u8 res=0][u32 X = llave ^ LLAVE_SAL][u32 semilla=0][256 B clave][4 B cola=0]."""
    x = (llave ^ captura.LLAVE_SAL) & 0xFFFFFFFF if llave is not None else 0
    # INVENTADO: semilla = 0 en +5..+9 y cola = 4 ceros al final
    return bytes([0]) + struct.pack("<II", x, FF02_SEMILLA) + clave + bytes(4)


def ff05_cuerpo(llave=None):
    """S2C FF05 CmdAck (0x0277b240) de 20 B: [u32 X = llave ^ LLAVE_SAL][16 B en 0]."""
    x = (llave ^ captura.LLAVE_SAL) & 0xFFFFFFFF if llave is not None else 0
    # INVENTADO: los 16 B restantes (otros dos u32 leidos en 0x0277b240 y 8 B de cola) en 0.
    return struct.pack("<I", x) + bytes(16)


def ff247_cuerpo():
    """S2C FF247 CmdFunction (0x028713f0) de 1 B: [u8 1] (33 de 33 en las grabaciones)."""
    return b"\x01"


def ff49_cabeza_cola(cuenta):
    """Cabeza y cola neutras de S2C FF49 CmdGetDressList (0x02781660, layouts/FF49.md) sin plantilla capturada."""
    pj = (cuenta or {}).get("personaje")
    if pj:
        partes = list(pj.get("partes") or [])
        cid = int(pj.get("char_id", 0)) & 0xFFFFFFFF
        cabeza = struct.pack("<IHIB", cid, 1, cid, len(partes)) + struct.pack("<%dI" % len(partes), *partes)
    else:
        # INVENTADO: sin personaje, char_id = 0 y lista de personajes vacia (n = 0).
        cabeza = struct.pack("<IH", 0, 0)
    # INVENTADO: cola de 35 B en 0 (#14 a=0, #15 b=0 sin lista #16-#17, #18 c=0 sin lista #19-#23, #24..#31 6x u32 + 2x u16 en 0).
    cola = bytes(35)
    return cabeza, cola


def envolver_ff56(cmd, seq, cuerpo):
    """Envuelve un comando S2C dentro de un marco FF56 sin relleno (0xFF -> FF0xx, 0xFE -> FF1xx, 0xFD -> FF2xx)."""
    alto = {0: 0xFF, 1: 0xFE, 2: 0xFD}[cmd >> 8]
    return b"\xff\x56\x00\x00" + struct.pack("<BBHI", alto, cmd & 0xFF, seq & 0xFFFF, len(cuerpo)) + cuerpo


# ---------- Hueco 2: ficha FF00 neutra (sin lotes_S2C.bin) ----------
def _items_ff00(cuenta):
    """Lista de registros de 17 B para FF00 de la cuenta local (vacio si no tiene personaje)."""
    import fichas
    pj = (cuenta or {}).get("personaje")
    if not pj:
        return []
    try:
        import cuenta as _cta
        bolsa = _cta.leer_seccion((cuenta or {}).get("usn", 0), "tienda") or {}
    except Exception:
        bolsa = {}
    ahora = int(time.time())
    puestas = list(pj.get("partes") or [])
    items = {}
    for it in list(bolsa.get("basicas", [])) + puestas:
        items.setdefault(it, [it, fichas.PERMANENTE, 0, ahora])
    for it, vence, cant, fecha in bolsa.get("items", []):
        items.setdefault(it, [it, vence, cant, fecha])
    return [
        # INVENTADO: u16 final reservado = 0; su significado no consta.
        struct.pack("<IIBHIH", it, fichas.vence_al_cable(vence), 1 if it in puestas else 0, cant, fecha, 0)
        for it, vence, cant, fecha in items.values()
    ]


def ff00_cuerpo(cuenta):
    """S2C FF00 CmdMyRecord (0x0277c3d0) armado por campos medidos con el exe, sin datos de captura."""
    import fichas
    cuenta = cuenta or {}
    pj = cuenta.get("personaje")
    nick = textos.codificar(cuenta.get("nick", "Jugador"), 12)
    sexo = ((pj["char_id"] - 0x1FF54) & 1) if pj else 0
    puesto = pj["char_id"] if pj else 0

    try:
        import tienda
        exp, g = tienda.exp_g_de_cuenta(cuenta)
        cash = tienda.diamantes_de_cuenta(cuenta) if tienda.saldos_al_dia() else 0
    except Exception:
        exp, g, cash = 0, 0, 0
    exp = max(0, int(exp))
    bajo = min(exp, 0xFFFFFFFF)
    alto = min(exp - bajo, 0xFFFFFFFFFFFFFFFF)
    g = min(0xFFFFFFFF, max(0, int(g)))
    cash = min(0xFFFFFFFF, max(0, int(cash)))

    lic = pj.get("licencia") if pj and pj.get("licencia") is not None else (ajustes.LICENCIA or 1)

    # #1..#8: sexo(1), puesto(4), exp_bajo(4), exp_alto(8), g(4), cash(4), licencia(2), u32(4)
    # INVENTADO: #8 u32 final = 0; significado no consta.
    out = bytearray(struct.pack("<BIIQIIHI", sexo, puesto, bajo, alto, g, cash, lic & 0xFFFF, 0))
    # #9..#10: UID (largo u8 + bytes)
    out += bytes([len(nick)]) + nick
    # #11..#27: textos vacios y ceros (INVENTADO: valores 0; en la ficha local no hay pareja ni club)
    # LEIDO 0x0277c606..0x0277c961: 2 textos vacios, u32, u8,
    # cuatro u32, tres u8 y ultimo texto vacio: 27 B, no 28.
    # Un byte extra desplaza la cantidad de personajes y rompe la lectura.
    try:
        import baile
        tut = baile.tutorial_hecho(cuenta) if baile.activo() else 0
    except Exception:
        tut = 0
    if tut:
        b27 = bytearray(27)
        struct.pack_into("<I", b27, 11, tut & 0xFFFFFFFF)
        out += bytes(b27)
    else:
        out += bytes(27)

    # #28..#31: lista de personajes [u16 n][char_id u32, u8 m, m x u32]
    if pj:
        partes = list(pj.get("partes") or [])
        out += struct.pack("<HIB", 1, pj["char_id"], len(partes))
        out += struct.pack("<%dI" % len(partes), *partes)
    else:
        out += struct.pack("<H", 0)

    # #32..#33: lista de canciones jugables (charts 1 a 1)
    canciones = fichas.JUGABLES if (ajustes.LISTA_CANCIONES and fichas.JUGABLES) else []
    # 20-nov (ficha 178): DIAGNOSTICO del selector del Club (选择音乐 sale vacio). CLUB_CANCIONES="16706,16433" agrega esos
    # Index de clubmusic.txt al principio (la lista va de mayor a menor). INVENTADO: no hay FF00 del oficial con canciones
    # del Club; solo con BAILE=1 y la llave puesta; sin ella, nada cambia.
    extra = [int(x) for x in os.environ.get("CLUB_CANCIONES", "").split(",") if x.strip().isdigit()]
    if extra and os.environ.get("BAILE") == "1":
        canciones = sorted(set(extra), reverse=True) + [c for c in canciones if c not in extra]
    out += struct.pack("<H", len(canciones))
    if canciones:
        out += struct.pack("<%dH" % len(canciones), *canciones)

    # #34..#35 NO son canciones: escenarios [u16 n][n x u16].
    # LEIDO 0x0277cb64..0x0277cbd6 -> 0x00472450 -> vector cuenta+0xcb0.
    # La lista vacia deja solo RANDOM: 0x029bd0cb divide por (n-1)=0.
    # 21-nov (ficha 183, Benja en Miami: "en las pistas solo me aparece mushroom"): antes iba solo el 1 (INVENTADO).
    # Ahora la lista que mandaba el oficial (MEDIDO en el FF00 capturado, 21 escenarios), la misma para todos:
    # 1..12, 14, 15, 56, 58 (pistas de carrera de stage.txt del cliente, con modelo) y 0x4000..0x4003, 0x4005
    # (escenarios del Club). Las de stage.txt que el oficial no mandaba (25, 26, 57, 100..103) no van.
    out += struct.pack("<H", len(ESCENARIOS)) + struct.pack("<%dH" % len(ESCENARIOS), *ESCENARIOS)

    # #36..#43: inventario [u16 k][k x 17 B]
    regs = _items_ff00(cuenta)
    out += struct.pack("<H", len(regs)) + b"".join(regs)

    # #44..#141: resto de listas y campos en cero (INVENTADO: todo 0 = sin amigos, mascota, pareja ni medallas previas)
    # Desglose exacto del layout 0x0277c3d0 (ver lectura estatica):
    #   #44(2) + #47(1) + #56(1) + #58(1) + #62..#66(20) + #67(1) + #68(1) + #70(1) + #72(1)
    #   + #73..#75(12) + #76(1) + #77..#78(8) + #79..#82,#84(5) + #86(4) + #87(2) + #89(1)
    #   + #90..#96(28) + #97(1) + #100..#103(10) + #105(2) + #111..#120(40) + #121(2) + #122(1)
    #   + #123(25) + #124(4) + #126(1) + #128..#130(12) + #131(61) + #132..#133(5)
    #   + #134..#135(8) + #136..#138(3) + #139..#141(12) = 276 bytes
    out += bytes(276)
    return bytes(out)


def ff00_lote(cuenta, seq=0):
    return envolver_ff56(0x00, seq, ff00_cuerpo(cuenta))


def lotes_entrada(cuenta):
    """Rafaga neutra de entrada cuando falta datos/lotes_S2C.bin (llave RAFAGA_NEUTRA_EXTRA)."""
    lotes = [ff00_lote(cuenta)]
    if os.environ.get("RAFAGA_NEUTRA_EXTRA", "1").lower() not in ("1", "si") or not cuenta:
        return lotes
    try:
        import tienda
        if tienda.saldos_al_dia():
            d = min(0xFFFFFFFF, max(0, int(tienda.diamantes_de_cuenta(cuenta))))
            lotes.append(envolver_ff56(0x51, 0, b"\x01" + struct.pack("<I", d)))
    except Exception as e:                                           # noqa: BLE001
        estado.anotar("   ⛔ neutro.lotes_entrada FF51: %r" % e)
    cuerpos_prog = None
    try:
        import progresion
        cuerpos_prog = progresion.cuerpos(cuenta)
        if cuerpos_prog is not None:
            lotes.append(envolver_ff56(0x1FE, 0, cuerpos_prog[1]))
    except Exception as e:                                           # noqa: BLE001
        estado.anotar("   ⛔ neutro.lotes_entrada FF1FE: %r" % e)
    try:
        import progresion
        if cuerpos_prog is None and progresion.activo():
            cuerpos_prog = progresion.cuerpos(cuenta)
        if cuerpos_prog is not None:
            lotes.append(envolver_ff56(0x1F9, 0, cuerpos_prog[0]))
    except Exception as e:                                           # noqa: BLE001
        estado.anotar("   ⛔ neutro.lotes_entrada FF1F9: %r" % e)
    try:
        import gemas
        cu_272 = gemas.cuerpo(cuenta)
        if cu_272 is not None:
            lotes.append(envolver_ff56(0x272, 0, cu_272))
    except Exception as e:                                           # noqa: BLE001
        estado.anotar("   ⛔ neutro.lotes_entrada FF272: %r" % e)
    return lotes


# ---------- Ficha 171: sala sin crear_sala_S2C.bin ----------
def cola_jugador_sala():
    """FF0C: 178 B fijos + once casillas vacias (44 B), fuera de canales 5..12."""
    cola = bytearray(222)  # INVENTADO: resto de campos/listas vacios.
    cola[26] = 255
    # LEIDO 0x02787610 -> 0x028870d0: #87/#88 u32, #89 cantidad
    # y cantidad x u32, #91 u32. Con cantidad=0 los 44 B extra se
    # interpretan como el jugador siguiente. INVENTADO: 11 casillas vacias.
    struct.pack_into('<I', cola, 170, 11)
    return bytes(cola)


def ff15_sala(sala):
    """RoomInfo por campos: layouts/FF15.md y fichas 12/13; nunca lee una captura."""
    host = next((a for a,c in sala.asientos.items() if c is sala.anfitrion), 2)
    # INVENTADO: todos los reservados = 0. Lista opcional sin entradas.
    cabeza = bytearray(16)
    struct.pack_into('<H', cabeza, 0, (sala.numero | sala.canal << 11) & 65535)
    cabeza[2] = host
    cabeza[5] = len(sala.asientos)
    cabeza[7] = 12  # INVENTADO: capacidad indicada por el camino comun conocido.
    struct.pack_into('<H', cabeza, 10, sala.pista or 0)
    cabeza[12] = 0 if sala.cancion else 2
    struct.pack_into('<H', cabeza, 13, sala.cancion or 0)
    cabeza[15] = len(sala.titulo)
    cola = bytearray(78)  # #15..#48, reservados INVENTADOS=0.
    struct.pack_into('<I', cola, 0, 63)  # INVENTADO: seis asientos abiertos, mascara 0x3f.
    struct.pack_into('<I', cola, 61, (sala.modo | 0x40000) & 0xffffffff)
    return bytes(cabeza) + sala.titulo + bytes(cola)


def mensajes_crear_sala(sala, jugador):
    """Orden LEIDO en FF_HANDLERS_CHINO §6. Campos ajenos desconocidos: INVENTADO=0."""
    host = next((a for a,c in sala.asientos.items() if c is sala.anfitrion), 2)
    creado = bytearray(13)
    struct.pack_into('<H', creado, 1, (sala.numero | sala.canal << 11) & 65535)
    creado[3], creado[4] = sala.canal, host
    struct.pack_into('<I', creado, 5, (sala.modo | 0x40000) & 0xffffffff)
    return [(0x0C,0,jugador), (0x232,0,bytes([host])+bytes(10)),
            (0x1C,0,struct.pack('<BHBB',4,0,2,0)),
            (0x1C,0,struct.pack('<BHBB',3,0,2,0)),
            (0x10,0,bytes(creado)), (0x167,0,bytes(5)),
            (0x15,0,ff15_sala(sala))]


def mensajes_unirse(asiento):
    """Avisos de union (orden en salas.sentar_y_avisar). Reservados INVENTADOS=0."""
    return {0x12D: bytes(2), 0x232: bytes([asiento])+bytes(10), 0x167: bytes(5)}


def fila_cartel():
    """Base sin datos de cuenta para carrera.fila_de (ficha 171).

    LEIDO: fila_de arma asiento, puesto, premios y resultados desde la
    carrera y el FF28 C2S; la rama neutra conserva los ultimos 8 B.
    LEIDO 0x02795740: sin listas opcionales cada fila ocupa 98 B.
    INVENTADO: esos campos finales, listas y reservados quedan en cero,
    sin premios adicionales. No se abre cartel_S2C.bin.
    """
    return bytes(98)


def reservados_cartel():
    """LEIDO FF28 #44..#47: cuatro u32 tras las filas. INVENTADO=0."""
    return bytes(16)


def medallas_oninit(cuerpo_pedido, contador):
    """Sobre FF246 leido en jardin.sobre y ficha 168: medallas vacias.

    No lee medallas_oninit.hex. Se conserva el id del pedido; contador
    creciente desde 1 y reservado final 0 son INVENTADOS para esta sesion.
    El JSON vacio es protocolo documentado en la revision de la 168.
    """
    nombre = b'musicMedalNet.onInit'
    js = b'{"l":{},"max":0}'
    return (struct.pack('<Q', contador) + cuerpo_pedido[:8]
            + struct.pack('<I', len(nombre)) + nombre
            + struct.pack('<I', len(js)) + js + bytes(4))


def ff77_examinar(cuenta):
    """Ficha minima de una cuenta NUEVA; layout FF77 y cueva propia leidos.

    LEIDO: la cueva 0x1da649d4 consume 4 B fijos en #4. El consumidor
    0x00b89e0d usa #6 como personaje y #8..#11 como cuatro partes.
    #19 es el apodo. No lee examinar_S2C.bin ni datos de otra cuenta.
    INVENTADO: reservados, textos y listas restantes vacios/cero; sin pareja.
    """
    pj = cuenta.get('personaje') or {}
    nick = textos.codificar(cuenta.get('nick', ''), 12)
    partes = (list(pj.get('partes') or []) + [0] * 6)[:6]
    lic = int(pj.get('licencia') or ajustes.LICENCIA or 1) & 65535
    # #1 resultado; #2 usn; #3..#5 INVENTADOS=0; #6 char; #7 licencia;
    # #8..#13 partes (las casillas no usadas, INVENTADAS=0).
    out = bytearray(struct.pack('<BII4sIIH6I', 0, cuenta['usn'], 0, bytes(4),
                                0, pj.get('char_id', 130900), lic, *partes))
    # #14 lista vacia; #16/#17 reservados; #18/#19 apodo.
    out += bytes(1) + struct.pack('<IHB', 0, 0, len(nick)) + nick
    # INVENTADO: todos los siguientes campos = 0 y listas/textos vacios.
    out += bytes(4)   # #20, #22, #24, #25; se omiten #21/#23 vacios
    out += bytes(20)  # #26..#30
    out += bytes(2)   # #31/#32
    out += bytes(8)   # #33/#34
    out += bytes(1)   # #35
    out += bytes(8)   # #36/#37
    out += bytes(2)   # #38
    out += bytes(16)  # #39..#42
    out += bytes(4)   # #43/#44, sin #45
    out += bytes(2)   # #46/#47
    out += bytes(4)   # #48
    out += bytes(1)   # #49, sin #50
    out += bytes(12)  # #51..#53
    out += bytes(3)   # #54..#56
    out += bytes(16)  # #57..#60, sin #61
    out += bytes(1)   # #62 sin pareja, se omiten #63..#85
    out += bytes(4)   # #86 lista final vacia
    return bytes(out)
