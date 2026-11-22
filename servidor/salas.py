# -*- coding: utf-8 -*-
r"""salas.py (01-nov) — las SALAS del cliente de Steam con logica propia: crear, salir (y de a poco: la lista, unirse,
el anfitrion). Plan: docs/PLAN_STEAM_COMPLETO.md, Fase 2. Las salas viven en estado.SALAS (compartidas por todas las
conexiones).

⭐ EL PEDIDO DE CREAR SALA (C2S FF1F5), MEDIDO el 01-nov (tools/modern-client/sonda_crear_sala.py):
  - lo arma 0x028469e0 (codigo legible): u32 modo · u8 n + titulo (GBK, <= 32) · u8 n + clave (<= 12) · u8 bandera ·
    u8 · u32 n + texto · u32 n + texto;
  - y 0x028a6970 lo cifra con **AES-256-CBC**: clave = el texto `3388ce10f3da39d1ade400938a4a25fe` (0x037340a4, los 32
    caracteres tal cual), IV = base64 `QtHzrOYWadpeVhDjUMNXow==` (0x03734088), relleno con ceros hasta 16. En el cable:
    [cifrado][16 B][24 B fijos][8 B en 0][u32 largo en claro]["fe cd df bd"].
  - Tres testigos que se leen enteros (sin sobrar un byte): la sala de hoy ("hola", modo 0x2a), una sin titulo (0x12) y
    la del OFICIAL de la grabacion del 22-oct (0x12, titulo GBK "跟我比试吧!").
  - ⚠ El armador cambia el modo 0x0a por 0x2a (y las dos banderas ^0x20) cuando una "version" hecha con 4 globales
    ([0x03a6612c] [0x03a6611c] [0x03a35b7c] [0x03a66120]) no da 0x911. En nuestro exe da 0x052f (5 y 0x2f; el oficial
    tendria 9 y 0x11): ⏳ sin medir de donde salen (parece el canal).

C2S FF14 SendExitRoom (0 B)  ->  S2C FF14 CmdExitRoom `0000` (2 B; la grabacion del 29-oct, §6 de FF_HANDLERS_CHINO.md)
"""
import base64
import os
import struct
import time

import captura
import estado
import fichas
import textos
import neutro
import ajustes

CLAVE_AES = b"3388ce10f3da39d1ade400938a4a25fe"
IV_AES = base64.b64decode("QtHzrOYWadpeVhDjUMNXow==")


def anotar(txt):
    estado.anotar(txt)


def jugadores(sala):
    """Las conexiones sentadas en la sala, por numero de asiento (una vista de `sala.asientos`)."""
    return [sala.asientos[k] for k in sorted(sala.asientos)]


def descifrar_cuerpo(cifrado):
    """El cuerpo AES de un comando cifrado del cliente (hoy: FF1F5). El largo en claro va 8 B antes del final."""
    from Crypto.Cipher import AES
    n = struct.unpack_from("<I", cifrado, len(cifrado) - 8)[0]
    m = (n + 15) // 16 * 16
    if n == 0 or m + 16 > len(cifrado):
        raise ValueError("largo en claro %d con %d B cifrados" % (n, len(cifrado)))
    return AES.new(CLAVE_AES, AES.MODE_CBC, IV_AES).decrypt(cifrado[:m])[:n]


def leer_crear_sala(claro):
    o = 0
    modo = struct.unpack_from("<I", claro, o)[0]
    o += 4
    titulo = claro[o + 1:o + 1 + claro[o]]
    o += 1 + claro[o]
    clave = claro[o + 1:o + 1 + claro[o]]
    o += 1 + claro[o]
    bandera, u8 = claro[o], claro[o + 1]
    o += 2
    textos = []
    for _ in range(2):
        n = struct.unpack_from("<I", claro, o)[0]
        textos.append(claro[o + 4:o + 4 + n])
        o += 4 + n
    if o != len(claro):
        raise ValueError("sobran %d B" % (len(claro) - o))
    return {"modo": modo, "titulo": titulo, "clave": clave, "bandera": bandera, "u8": u8, "textos": textos}


ORDEN_ASIENTOS = (2, 3, 1, 4, 0, 5)      # el 2013 (salas.ORDEN_ASIENTOS): el anfitrion en el 2, despues 3, 1, 4, 0, 5

# ⭐ 08-nov, MEDIDO en la grabacion del oficial R2Beat_grabacion_20261108_130830 (el usuario creo una sala de heroe, una de
# gloton y una individual, en ese orden):
#  - el MODO viaja como u32 = modo | 0x40000 en el FF10 (byte 5) y en el FF15 (cola, despues del titulo, byte 61):
#    heroe 0x00060000, gloton 0x00040200, individual 0x0004000c. Antes se escribia u16: el heroe (0x20000) llegaba como
#    0x00040000 = una sala comun (sin el heroe de los lugares 3-4, con mapa y obstaculos en el panel).
#  - HEROE (0x20000): el anfitrion en el asiento 1 (FF15 byte 2, FF10 byte 4, FF232 byte 0 y FF0C, todos 01), su equipo
#    2 (FF0C pre[20]), la cola del FF15 empieza 0xf3 (los lugares 2 y 3 los ocupa el heroe; los otros 0xff) y la
#    cabeza trae byte 7 = 0x0a (0x0c en los otros) y byte 10 = 0x0b (0 en los otros).
#  - GLOTON (0x200): la cola del FF15 trae un 1 en el byte 56 (0 en individual y en heroe).
#  El u8 del FF1F5 vale 3 en las TRES (el oficial tambien): no era el problema del gloton.
MODO_HEROE, MODO_GLOTON = 0x20000, 0x200
ORDEN_ASIENTOS_HEROE = (1, 0, 4, 5)      # ⏳ el orden de los que entran despues, sin medir (los lugares libres)


ESPERA_REUSO = 120   # s: carrera.py guarda el numero en temporizadores; un numero reusado pronto podria tocar la sala nueva


def numero_libre():
    """El numero de sala visible: el MENOR libre desde 0 (MEDIDO en el oficial, 5 de 5: sala 0 con el canal vacio, 1 con la 0
    ocupada, 2 con la 0 y la 1; el numero 0 se reusa al cerrarse). HIPOTESIS: el oficial cuenta POR CANAL o en total (la
    grabacion solo tiene salas del canal 0, y las del canal 3 estaban solas): aca es uno solo para todos, asi la clave de
    estado.SALAS sigue siendo el numero (carrera.py y social.py la usan). Aca ademas no se reusa uno cerrado hace < 120 s."""
    ahora = time.time()
    for k in [k for k, t in estado.CERRADAS.items() if ahora - t >= ESPERA_REUSO]:
        del estado.CERRADAS[k]
    n = 0
    while n in estado.SALAS or n in estado.CERRADAS:
        n += 1
    return n


def orden_asientos(modo):
    return ORDEN_ASIENTOS_HEROE if modo & MODO_HEROE else ORDEN_ASIENTOS


# La clase Sala (solo datos) vive en estado.py; aca esta lo que se hace con ella. Reciben la sala, asi una sala creada
# antes de recargar este archivo usa siempre el codigo de ahora.
def nueva_sala(numero, pedido, anfitrion, canal=0):
    """Una sala nueva con el anfitrion sentado en el primer asiento de su modo."""
    sala = estado.Sala(numero, pedido, anfitrion, canal)
    sala.orden = orden_asientos(sala.modo)
    sala.asientos = {sala.orden[0]: anfitrion}
    return sala


def poner_estado(sala, v):
    """El byte de estado de la lista (bit 0x02 = 游戏中, en carrera)."""
    if v & 0x02:                       # carrera.empezar lo prende: ya se jugo, vuelve a valer un cambio de modo
        sala.cambio_sin_jugar = False
    sala.estado = v


def sentar(sala, con):
    for a in sala.orden:
        if a not in sala.asientos:
            sala.asientos[a] = con
            return a
    return None


def levantar(sala, con):
    for a, c in list(sala.asientos.items()):
        if c is con:
            del sala.asientos[a]
    if sala.anfitrion is con:
        # el anfitrion se hereda por orden de asiento (nota 01 §5.4 de S-2013)
        sala.anfitrion = next((sala.asientos[a] for a in sala.orden if a in sala.asientos), None)


# ⭐ LA LISTA DE SALAS (S2C FF6E RoomList2), MEDIDA en tres grabaciones del oficial (29-oct: 212916, 215530, 224249;
# las tres con el mismo molde):
#   [u8 01][u16 cantidad] y por sala:
#     [u16 numero][u8 ESTADO][u16 ?][u16 ?][u8 ocupantes][u8 espectadores][u8 lugares][u8 n][titulo GBK]
#     [u8 ?01][u8 icono S 02][u8 00][u8 04][20 B: iconos de la sala (4Key, bot, fuego...)][u8 06]
#     6 lugares de 51 B: [u8 asiento][u8 ocupado][u8 abierto][u8 ?02] [24 B en 0] [nick 13 B GBK, relleno 0]
#                        [u32 id][u16 0][u16 nivel?][u16 0]      (vacio: [asiento][0][1][0] + 47 en 0)
#     [u16 modo][u16 0004]   (bit 0 del u32 = el candado Image_비밀)
#   ESTADO: bit 0x02 = el cartel 游戏中 (Image_게임중; 0x027b7c91 -> campo +0x50, lo dibujan 0x009f0370 y 0x009f7a40,
#   leido del exe por un subagente). El byte de "espectadores" (+11) se midio en vivo: con 1, la lista dice «0/6 [1]».
# El pedido (C2S FF1F6, 7 B): [u8 canal?][u16 pagina][u32 mascara de modos] (0x0022fabe = todos los bits de modo).
_CABEZA_PLANTILLA = bytes.fromhex("3800" "561d")      # los dos u16 sin medir, los de la sala grabada (en 0 no cambia la
# lista; ⏳ sin medir si sirven al entrar)
_COLA_TITULO = bytes.fromhex("01020004") + bytes(20) + b"\x06"      # los 25 B despues del titulo (grabados)


def _lugar(asiento, con):
    if con is None:
        return bytes([asiento, 0, 1, 0]) + bytes(47)
    nick = textos.codificar((con.cuenta or {}).get("nick", "Jugador"), 12)
    usn = (con.cuenta or {}).get("usn", 0)
    return (bytes([asiento, 1, 0, 2]) + bytes(24) + nick.ljust(13, b"\0")
            + struct.pack("<IHHH", usn & 0xFFFFFFFF, 0, 1, 0))


def ff6e(salas):
    out = b"\x01" + struct.pack("<H", len(salas))
    for s in salas:
        out += (struct.pack("<HB", s.numero & 0xFFFF, s.estado) + _CABEZA_PLANTILLA
                + bytes([len(s.asientos), 0, min(s.max, len(orden_asientos(s.modo))), len(s.titulo)]) + s.titulo + _COLA_TITULO)
        out += b"".join(_lugar(a, s.asientos.get(a)) for a in range(6))
        out += struct.pack("<I", (s.modo | 0x40000) & 0xFFFFFFFF)     # 08-nov: u32 (el heroe es 0x20000)
    return out


def lista(con, seq, cuerpo):
    """C2S FF1F6 SendRoomList3 (7 B) -> S2C FF6E con las salas abiertas cuyo modo entra en la mascara."""
    if len(cuerpo) != 7:
        return False
    canal, pagina, mascara = struct.unpack("<BHI", cuerpo)
    # 10-nov (ficha 13): solo las salas de ESE canal (el u8 del FF1F5 con que se crearon; las viejas sin canal = 0). La
    # pagina no se respeta (siempre 1 en lo grabado, y no se sabe cuantas entran por pagina); la mascara, como antes.
    salas_ = [x for x in estado.SALAS.values() if x.canal == canal and ((x.modo & mascara) or not mascara)]
    con.mandar_interno(0x6E, seq, ff6e(salas_))
    anotar("   S2C FF6E lista de salas (canal %d, pagina %d, mascara 0x%x): %d salas" % (canal, pagina, mascara, len(salas_)))
    return True


def _plantilla():
    """Los mensajes grabados del oficial al crear sala: [(cmd, seq, cuerpo)] en orden (datos/crear_sala_S2C.bin)."""
    return captura.plantilla_crear_sala()


def ff10_para(cuerpo, sala):
    """FF10 CreateRoom grabado: `00000000 02 [modo u16] 0400 00000000 00` (el 0x12 grabado en el byte 5)."""
    # 08-nov: el modo es u32 (modo | 0x40000) y el byte 4 es el asiento del anfitrion (1 en el heroe; ver MODO_HEROE)
    nuevo = bytearray(cuerpo[:5] + struct.pack("<I", (sala.modo | 0x40000) & 0xFFFFFFFF) + cuerpo[9:])
    # 10-nov (ficha 13, MEDIDO en el oficial, 5 de 5): bytes 1-2 = numero | canal << 11 y byte 3 = el canal
    canal = sala.canal
    nuevo[1:3] = struct.pack("<H", (sala.numero | canal << 11) & 0xFFFF)
    nuevo[3] = canal
    host = _asiento_anfitrion(sala)
    if host is not None:
        nuevo[4] = host
    return bytes(nuevo)


def _asiento_anfitrion(sala):
    return next((a for a, c in sala.asientos.items() if c is sala.anfitrion), None)


def ff15_para(cuerpo, sala):
    """FF15 RoomInfo grabado: el titulo va en el byte 15 (u8 largo + GBK) y el modo, como `[u16 modo] 0400`, mas
    adelante (el mismo par que el FF10)."""
    n = cuerpo[15]
    resto = cuerpo[16 + n:]
    i = resto.find(b"\x12\x00\x04\x00")
    if i >= 0:
        # 08-nov: u32 (modo | 0x40000); con u16 el heroe (0x20000) quedaba en 0x40000 (ver MODO_HEROE)
        resto = resto[:i] + struct.pack("<I", (sala.modo | 0x40000) & 0xFFFFFFFF) + resto[i + 4:]
    resto = bytearray(resto)
    if sala.modo & MODO_HEROE:
        resto[0] = 0xF3                  # los lugares 2 y 3 son del heroe (grabacion del 08-nov)
    if sala.modo & MODO_GLOTON and i >= 5:
        resto[i - 5] = 1                 # gloton: el 1 del byte 56 de la cola (modo en el 61; grabacion del 08-nov)
    resto = bytes(resto)
    nuevo = bytearray(cuerpo[:15] + bytes([len(sala.titulo)]) + sala.titulo + resto)
    # 10-nov (ficha 13, MEDIDO: 18 de 18 FF15 del oficial): bytes 0-1 = numero de sala | canal << 11
    nuevo[0:2] = struct.pack("<H", (sala.numero | sala.canal << 11) & 0xFFFF)
    # 10-nov (ficha 12, MEDIDO en el oficial del 08-nov): bytes 13-14 = la cancion elegida con FF1C y byte 12 = 0 (2 si es
    # al azar); bytes 10-11 = la pista: la del FF1B, o 9 / 10 segun el grupo del coop (FF132 1 / 2; 3 de 3)
    cancion = sala.cancion
    nuevo[12] = 0 if cancion else 2
    nuevo[13:15] = struct.pack("<H", cancion or 0)
    pista = sala.pista
    if sala.modo & 0x8000 and sala.grupo in (1, 2):
        pista = {1: 9, 2: 10}[sala.grupo]
    if pista is not None:               # 0 vale (tras un cambio de modo el oficial la vuelve a 0)
        nuevo[10:12] = struct.pack("<H", pista & 0xFFFF)
    if sala.modo & MODO_HEROE:
        nuevo[7], nuevo[10] = 0x0A, 0x0B   # cabeza del heroe en el oficial (08-nov; ⏳ que son, sin medir)
    # 2-nov: el byte 2 = el ASIENTO DEL ANFITRION [H fuerte]: vale 2 (el del creador) en el FF15 de crear sala Y en el de
    # unirse, donde el que entra se sienta en el 1 (no es "mi asiento"). Es el @6 del FF13 del 2013 (ANFITRION_DE_SALA.md:
    # el que manda es ESE campo, a toda la sala). Sin esto, al irse el anfitrion la sala quedaba sin 房主 y trabada.
    host = next((a for a, c in sala.asientos.items() if c is sala.anfitrion), None)
    if host is not None:
        nuevo[2] = host
    # 07-nov: el 67 se midio con el titulo "coop" (4 letras): el titulo va en el medio (byte 16) y corre todo lo que
    # sigue. Con "cooperativo" (11) el 1 caia 7 bytes antes, el gorila no se cargaba y las copias caian en 0x00b60f77
    # (2 de 2, las dos juntas). La posicion va contada desde el final del titulo: 16 + largo + 47 (= 67 con "coop").
    pos_gorila = 16 + len(sala.titulo) + 47
    if sala.modo & 0x8000 and len(nuevo) > pos_gorila:
        # cooperativo: el byte 67 del cuerpo (posicion 75 del lector, con los 8 B de cabecera; lo lee 0x0278c3e6 a
        # [ebp-0x191] y pasa a [ebp-0x1a1]; MEDIDO en vivo el 02-nov con una sonda) es el que mira CmdRoomInfo en
        # 0x0278d543: 1 -> 0x00841c70 -> 0x00d2ab10 pone el
        # modo grupal del cliente en 0x3a98 = gorila. Sin eso el HUD del gorila (gorilla_gage.spr) no se carga y la
        # carrera cae a los 7 s en 0x00b60f77.
        nuevo[pos_gorila] = sala.grupo if sala.grupo in (1, 2) else 1
    return bytes(nuevo)


def mandar_sala(con, sala, solo=None):
    """La respuesta de crear sala: la grabada del oficial, con el MODO y el TITULO de esta sala y la ficha del jugador.
    ⚠ El resto de los campos (lugares, escenario, cancion) siguen siendo los grabados: se miden de a uno."""
    if not os.path.exists(ajustes.RUTA_CREAR_SALA):
        mensajes = neutro.mensajes_crear_sala(sala, ff0c(sala, con))
        for cmd, sq, cu in mensajes:
            if solo is None or cmd == solo:
                con.mandar_interno(cmd, sq, cu)
        return sum(solo is None or cmd == solo for cmd, _, _ in mensajes)
    n = 0
    for cmd, seq, cuerpo in _plantilla():
        if solo is not None and cmd != solo:
            continue
        if cmd == 0x10:
            cuerpo = ff10_para(cuerpo, sala)
        elif cmd == 0x15:
            cuerpo = ff15_para(cuerpo, sala)
        elif cmd == 0x232 and cuerpo and _asiento_anfitrion(sala) is not None:
            cuerpo = bytes([_asiento_anfitrion(sala)]) + cuerpo[1:]     # 08-nov: 01 en el heroe, 02 en los otros
        elif cmd == 0x0C and con.cuenta is not None:
            cuerpo = ff0c(sala, con)       # ficha 37: la rama vieja (j.sala_para) era para una sala sin `asientos`; estado.Sala siempre los tiene
        con.mandar_interno(cmd, seq, cuerpo)
        n += 1
    return n


def crear(con, seq, cuerpo):
    """C2S FF1F5 SendCreateRoom2 (cifrado AES): se abre la sala y se contesta con su modo y su titulo."""
    try:
        pedido = leer_crear_sala(descifrar_cuerpo(cuerpo))
    except (ValueError, IndexError, struct.error) as e:
        anotar("   ⛔ C2S FF1F5 que no se descifra (%s): %s" % (e, cuerpo.hex()))
        return False
    sacar_de_su_sala(con)     # el cliente puede mandar el crear dos veces: nunca dos salas vivas del mismo jugador
    numero = numero_libre()
    if pedido["modo"] == 0x2A and pedido["bandera"] & 0x20:
        # la rareza del armador (docstring): con la "version" != 0x911 el individual-velocidad 0x0a sale 0x2a y las dos
        # banderas ^0x20. Sin deshacerlo, la lista lo muestra como 竞速/接力 (relevo), medido el 01-nov.
        pedido = dict(pedido, modo=0x0A, bandera=pedido["bandera"] ^ 0x20, u8=pedido["u8"] ^ 0x20)
    canal = pedido["u8"]
    # 20-nov (ficha 178): el Club (modo baile) crea con u8 13 y su lista pide el canal 13 (FF1F6, MEDIDO con dos copias:
    # con el canal pasado a 0 la otra copia veia 0 salas). Solo con la llave BAILE=1; sin ella, todo como antes.
    import baile as _baile
    if canal == _baile.CANAL_CLUB and _baile.activo():
        pass
    elif canal > 3:
        anotar("   ⛔ FF1F5 con u8 %d (el canal va de 0 a 3): se usa el canal 0" % canal)
        canal = 0
    sala = nueva_sala(numero, pedido, con, canal)
    estado.SALAS[numero] = sala
    con.sala = numero
    anotar("   C2S FF1F5 CREAR SALA en claro: modo 0x%x, titulo %r (%s), clave %r, bandera 0x%x, u8 0x%x -> sala %d canal %d"
           % (pedido["modo"], pedido["titulo"], textos.decodificar(pedido["titulo"]), pedido["clave"],
              pedido["bandera"], pedido["u8"], numero, canal))
    n = mandar_sala(con, sala)
    anotar("   S2C CREAR SALA: %d mensajes (plantilla del oficial con el modo y el titulo de la sala %d)" % (n, numero))
    return True


def info(con, seq, cuerpo):
    """C2S FF15 SendRequestRoomInfo (0 B) -> FF15 de la sala del jugador."""
    sala = estado.SALAS.get(con.sala)
    if cuerpo or sala is None:
        return False
    mandar_sala(con, sala, solo=0x15)
    con.pidio_sala = time.time()          # el cooperativo mira esto para no empujarle la vuelta (carrera.revisar)
    return True


def equipo_de(sala, con):
    """El equipo (pre[20] del FF0C; el START del cliente exige equipos parejos contando `usuario+0x20 == 1` contra el
    resto: analisis del 02-nov de 0x00a24ed0). En modo equipo (bit 0x10 del modo) cada uno entra al equipo con menos
    gente; en los otros modos, 1 (como la plantilla del oficial)."""
    # 3-nov: el RELEVO (0x22 / 0xa0) tambien va por equipos: el START del cliente pide equipos parejos en equipo y relevo
    # (CooperationMode 0 y 2; 2013 0x58BFF0). Con todos en el 1, el START no salia (medido en la sala 11, 4 copias).
    # (0x2a = individual con la bandera 0x20: no es relevo; ver crear)
    # 3-nov: y el CAPITAN (队长战, 0x4000): con todos en el equipo 1 el START daba el cartel «队员人数不对称» (sala 16)
    if sala.modo & MODO_HEROE:
        return 2                         # 08-nov: el oficial pone al anfitrion del heroe en el equipo 2 (FF0C pre[20])
    if sala.modo & 0x2000 and not sala.modo & 0x20:
        # PAREJA (玩伴, 0x2000): cada pareja su grupo (el START 0xa24ed0 con CooperationMode 3 agrupa por este byte y
        # pide que cada valor usado 1..3 tenga 2 o mas). La pareja comparte el numero; el resto va al 1.
        import social
        eq = sala.equipos
        if eq is None:
            eq = sala.equipos = {}
        if id(con) not in eq:
            yo = (con.cuenta or {}).get("usn")
            otro = next((c for c in jugadores(sala) if (c.cuenta or {}).get("usn") == social.PAREJAS.get(yo)), None)
            if otro is not None and id(otro) in eq:
                eq[id(con)] = eq[id(otro)]
            else:
                usados = set(eq.values())
                eq[id(con)] = next((n for n in (1, 2, 3) if n not in usados), 1)
        return eq[id(con)]
    if not (sala.modo & 0x10 or (sala.modo & 0x20 and not sala.modo & 0x08) or sala.modo & 0x4000):
        return 1
    eq = sala.equipos
    if eq is None:
        eq = sala.equipos = {}
    if id(con) not in eq:
        unos = sum(1 for c in jugadores(sala) if eq.get(id(c)) == 1)
        dos = sum(1 for c in jugadores(sala) if eq.get(id(c)) == 2)
        eq[id(con)] = 1 if unos <= dos else 2
    return eq[id(con)]


def _exp_de(con):
    """La exp del jugador para su ficha del FF0C (pre[0:4]: sube carrera a carrera, nota 06/11); 0 si no se puede leer."""
    try:
        import tienda
        return tienda.exp_de(con)
    except Exception:                                                    # noqa: BLE001
        return 0


def ficha_ff0c(con, asiento, propio, equipo=1):
    """Un jugador del FF0C: junta los datos de la conexion y lo arma fichas.ficha_ff0c (`propio` ya no se usa)."""
    cuerpo = fichas.ficha_ff0c(con.cuenta, _exp_de(con), con.listo, asiento, equipo)
    if not os.path.exists(ajustes.RUTA_CREAR_SALA):
        cuerpo = cuerpo[:-fichas.FF0C_COLA] + neutro.cola_jugador_sala()
    return cuerpo


def ff0c(sala, para):
    """El FF0C RoomUserList de la sala (fichas.lista_ff0c), con el equipo de cada asiento."""
    jug = sorted(sala.asientos.items())
    return fichas.lista_ff0c([ficha_ff0c(c, a, c is para, equipo_de(sala, c)) for a, c in jug])


def mandar_ff0c_a_todos(sala, seq=0):
    for c in jugadores(sala):
        c.mandar_interno(0x0C, seq, ff0c(sala, c))


# Ficha 67 (11-nov): el FF0C que llega a alguien que YA tenia sentado al otro NO le repinta el muneco (medido con dos copias en la
# misma sala: la 2 se puso un gorro y la 1 la siguio viendo sin el). Lo que si repinta es sacar el asiento y volver a sentarlo
# (FF0E + FF0C, el mismo camino de cuando alguien se va y vuelve; el 2013 lo documenta: «cRoom::Leave destruye los ocupantes y se
# re-dibujan»). Llave: False = como antes (solo el FF0C).
# APAGADA por decision del cerebro (11-nov, Eñeños durmiendo): prendida, los demas VEN la ropa nueva (visto con 2 copias), pero su chat
# imprime «<apodo> ha entrado a la sala» en cada cambio (un aviso falso) y no se probo con 3 o mas, ni en salas de equipo, capitan o
# pareja. El oficial manda FF13 (CmdRoomUserInfo) tras el FF0C: ese es el camino a medir (ficha 68). Prenderla es decision de Eñeños.
REVESTIR_CON_FF0E = False

# Ficha 69 (11-nov): el camino del oficial (FF0C + FF13 del asiento, sin sacar el asiento ni aviso falso en el chat). Llave: False = como
# antes (solo FF0C). PRENDIDA por omision: visto con el juego (copias 1/3/5: 2 y 3 jugadores, sala individual y por equipos, dueno
# invitado y anfitrion; los demas ven la prenda al ponerla y al sacarla, sin aviso de chat, equipos quietos; carrera individual
# OK despues). Sin probar: 4 o mas, coop/capitan/pareja, carrera en curso (ahi no se manda). El C2S FF270 que el cliente contesta
# al FF13 NO se atiende (no rompio nada). Ignorada si REVESTIR_CON_FF0E esta prendida.
REVESTIR_CON_FF13 = True


def mandar_ropa_a_todos(sala, dueno, seq=0):
    """La ropa de `dueno` cambio: a el, el FF0C de siempre (su muneco ya cambio solo); a los DEMAS de la sala, FF0E del asiento
    de `dueno` + el FF0C nuevo + el FF17 con su `listo` (el asiento vuelve a nacer) + los equipos si la sala va por equipos.
    No se hace con carrera en curso, ni si `dueno` es el anfitrion (sacarle el asiento a quien manda la sala no se probo)."""
    asiento = next((a for a, c in sala.asientos.items() if c is dueno), None)
    if (REVESTIR_CON_FF13 and not REVESTIR_CON_FF0E and asiento is not None and sala.carrera is None
            and len(sala.asientos) >= 2 and ((dueno.cuenta or {}).get("personaje") or {}).get("partes")):
        # (cerebro, 11-nov) sin prendas propias no se manda FF13: uno con n = 0 desvestiria al muneco en la pantalla de los demas.
        # ficha 69: como el oficial, a los DEMAS el FF0C de siempre y despues el FF13 del asiento que cambio (reviste sin sacar el
        # asiento ni avisar en el chat); al dueno, solo el FF0C. Sirve tambien si el dueno es el anfitrion (no se le saca el asiento).
        pj = (dueno.cuenta or {}).get("personaje") or {}
        ficha = fichas.ff13(asiento, pj.get("char_id", 0x1FF54), pj.get("partes", []), _exp_de(dueno),
                           equipo_de(sala, dueno))
        for c in jugadores(sala):
            c.mandar_interno(0x0C, seq, ff0c(sala, c))
            if c is not dueno:
                c.mandar_interno(0x13, 0, ficha)
        anotar("   S2C FF0C+FF13: la ropa del asiento %d cambio; la sala %d lo repinta (%d B)" % (asiento, sala.numero, len(ficha)))
        return
    if (not REVESTIR_CON_FF0E or asiento is None or sala.carrera is not None or sala.anfitrion is dueno
            or len(sala.asientos) < 2):
        mandar_ff0c_a_todos(sala, seq)
        return
    for c in jugadores(sala):
        if c is not dueno:
            c.mandar_interno(0x0E, 0, bytes([asiento]))
        c.mandar_interno(0x0C, seq, ff0c(sala, c))
        if c is not dueno:
            c.mandar_interno(0x17, 0, bytes([0, asiento, dueno.listo]))
    avisar_equipos(sala)
    anotar("   S2C FF0E+FF0C+FF17: la ropa del asiento %d cambio; la sala %d lo vuelve a sentar" % (asiento, sala.numero))


def lista_jugadores(con, seq, cuerpo):
    """C2S FF0C SendRequestRoomUserList (1 B) -> FF0C con todos los de la sala."""
    sala = estado.SALAS.get(con.sala)
    if len(cuerpo) != 1 or sala is None:
        return False
    con.mandar_interno(0x0C, seq, ff0c(sala, con))
    # 2-nov: y el listo de cada asiento DESPUES de la lista. Tras el coop los invitados se veian con READY aunque el FF17
    # [0][a][0] ya habia salido (con el FF15, antes de que el cliente pidiera esta lista y rearmara la sala)
    if sala.carrera is None:
        for a, x in sorted(sala.asientos.items()):
            con.mandar_interno(0x17, 0, bytes([0, a, x.listo]))
        avisar_equipos(sala, solo=con)          # el FF0C rearma el padron: los capitanes van despues
    return True


def _plantilla_unirse():
    """La respuesta grabada del oficial a ENTRAR a una sala (herramientas/preparar_unirse.py -> datos/unirse_S2C.bin)."""
    return captura.plantilla_unirse()


def es_capitan(sala):
    return bool(sala.modo & 0x4000)


def capitanes(sala):
    """{equipo: asiento} del modo CAPITAN: el primero de cada equipo por orden de entrada (ORDEN_ASIENTOS). ⏳ el 2013
    lo sortea al volver de cada carrera (MODO_JEFE_EXPEDIENTE.md §C); aca, fijo y simple."""
    caps = {}
    for a in ORDEN_ASIENTOS:
        c = sala.asientos.get(a)
        if c is not None:
            caps.setdefault(equipo_de(sala, c), a)
    return caps


def avisar_equipos(sala, solo=None):
    """CAPITAN (3-nov, analisis estatico de un subagente sobre el exe de Steam):
    FF37 CmdEditTeamResponse 3 B = [equipo][asientoA][asientoB] (A == B: no intercambia) -> 0xa255b0 pinta el asiento y
    pone el EQUIPO en el padron (+0x20), que es lo que cuenta el START (0xa24ed0: con GameMode 5 pide >= 4 y lados
    iguales). FF175 CmdChangeCaptain 2 B = [capitan del equipo 1][capitan del equipo 2] (6 = ninguno): sin capitanes la
    carrera arranca vacia (sin barra ni duelo). Se manda a todos (o a `solo`)."""
    if not es_capitan(sala):
        return
    caps = capitanes(sala)
    for c in ([solo] if solo is not None else jugadores(sala)):
        for a, x in sorted(sala.asientos.items()):
            c.mandar_interno(0x37, 0, bytes([equipo_de(sala, x), a, a]))
        c.mandar_interno(0x175, 0, bytes([caps.get(1, 6), caps.get(2, 6)]))
    anotar("   CAPITAN: equipos %s, capitanes %s (FF37 x%d + FF175 a %s)"
           % ({a: equipo_de(sala, x) for a, x in sala.asientos.items()}, caps, len(sala.asientos),
              "todos" if solo is None else (solo.cuenta or {}).get("nick")))


def sentar_y_avisar(con, sala, seq):
    """Lo comun de unirse (clic en la sala o entrada rapida). Orden medido en la grabacion 213306 (nota 06 §6):
    FF12D, FF0C, FF232, FF0F [asiento][tipo 0][0]x6, FF167, FF246 room.joinRoom, FF15 la sala, FF0C, FF17 por asiento.
    A los que ya estaban: el FF0C nuevo."""
    sacar_de_su_sala(con)
    asiento = sentar(sala, con)
    if asiento is None:
        con.mandar_interno(0x0F, seq, bytes([0x28, 0, 0, 0]) + bytes(4))     # 0x28: lugares llenos (nota 05 §1)
        anotar("   S2C FF0F 0x28: la sala %d esta llena" % sala.numero)
        return True
    con.sala = sala.numero
    plantilla = {cmd: cu for cmd, _s, cu in _plantilla_unirse()}
    if not os.path.exists(ajustes.RUTA_UNIRSE):
        plantilla = neutro.mensajes_unirse(asiento)
    for cmd in (0x12D, 0x0C, 0x232, 0x0F, 0x167, 0x246):
        if cmd == 0x0C:
            cu = ff0c(sala, con)
        elif cmd == 0x0F:
            # 20-nov (ficha 178): el byte 1 es el CANAL: el RX CmdJoinRoom hace SetChannel(byte 1) (LEIDO en dos
            # binarios: el 2019 0xcfee90 -> 0x8c0950 'SetChannel Start%d', y el chino 0x02789a90 -> 0x8c1700, 2.a
            # lectura). Con 0 el que se une al Club queda en canal de carrera y carga carrera. La grabacion del oficial
            # tenia 0 porque era una sala del canal 0. Solo para el Club con BAILE=1: las carreras siguen como estaban.
            import baile as _baile
            canal_ff0f = sala.canal if (_baile.activo() and sala.canal == _baile.CANAL_CLUB) else 0
            cu = bytes([asiento, canal_ff0f, 0, 0]) + bytes(4)
        elif cmd in plantilla:
            cu = plantilla[cmd]
        else:
            continue
        con.mandar_interno(cmd, seq, cu)
    mandar_sala(con, sala, solo=0x15)
    for a, c in sorted(sala.asientos.items()):
        con.mandar_interno(0x17, seq, bytes([0, a, c.listo]))
    for c in jugadores(sala):
        if c is not con:
            c.mandar_interno(0x0C, 0, ff0c(sala, c))
            # 2-nov: sin esto el anfitrion veia al recien llegado con READY puesto sin que lo apretara (foto
            # escenario_copia2.png): el FF0C solo no le dice que esta sin listo
            c.mandar_interno(0x17, 0, bytes([0, asiento, 0]))
    avisar_equipos(sala)
    anotar("   S2C UNIRSE: %s entra a la sala %d en el asiento %d (%d en la sala), FF0F canal %d"
           % ((con.cuenta or {}).get("nick"), sala.numero, asiento, len(sala.asientos), sala.canal))
    return True


def rapida(con, seq, cuerpo):
    """C2S FF1F7 SendQuickJoin3 (6 B: [u8][u32 mascara de modos][u8]). Sin sala que sirva: FF72 `0d` (lo que mando el
    oficial en la grabacion 215530 sin salas)."""
    if len(cuerpo) != 6:
        return False
    mascara = struct.unpack_from("<I", cuerpo, 1)[0]
    sala = next((s for s in estado.SALAS.values() if (s.modo & mascara or not mascara) and len(s.asientos) < s.max
                 and s.estado & 0x02 == 0 and con not in jugadores(s)), None)
    if sala is None:
        con.mandar_interno(0x72, seq, b"\x0d")
        anotar("   S2C FF72 0d: entrada rapida sin sala libre")
        return True
    return sentar_y_avisar(con, sala, seq)


def unirse(con, seq, cuerpo):
    """C2S FF0F SendJoinRoom (6 B en la grabacion: `0000 01000000`, `da63 00000000`): [u16 A][u32 ?]. A & 0x7FF = la
    sala, A >> 11 = el tipo de lugar (nota 05 §2)."""
    if len(cuerpo) < 2:
        return False
    numero = struct.unpack_from("<H", cuerpo, 0)[0] & 0x7FF
    sala = estado.SALAS.get(numero)
    if sala is None:
        con.mandar_interno(0x0F, seq, bytes([0x1A, 0, 0, 0]) + bytes(4))     # 0x1A: no se puede entrar
        anotar("   S2C FF0F 0x1A: la sala %d no existe (pedido %s)" % (numero, cuerpo.hex()))
        return True
    return sentar_y_avisar(con, sala, seq)


def info_por_numero(con, seq, cuerpo):
    """C2S FF41 SendGetRoomInfo (2 B = [u16 A], al aceptar una invitacion FF52 desde el lobby: medido 03-nov). El RX
    0x027a3020 lee 1,2,1,1,1,4,1,1 (11 B). PRUEBA [H]: [u8 resultado 0][u16 A][u8 ocupantes][u8 lugares][u8 estado]
    [u32 modo][u8 clave 0][u8 0]; se mira si despues el cliente manda el FF0F de unirse. Sala que no existe: resultado 1."""
    if len(cuerpo) != 2:
        return False
    a = struct.unpack_from("<H", cuerpo, 0)[0]
    sala = estado.SALAS.get(a & 0x7FF)
    # 3-nov (subagente, 0x027a3020): [u8 r: 1 = OK][u16 A][u8 x][u8 f: bit 0 = pide clave][u8 g: != 0][u32 modo][u8 L]
    # [L B titulo, L < 0x30][u8 h]. Con r == 1 el cliente sigue a 0x8c12a0 -> SendJoinRoom FF0F (la pieza 0x0f2be615)
    if sala is None:
        con.mandar_interno(0x41, seq, bytes([0]) + struct.pack("<H", a) + bytes(9))
    else:
        tit = sala.titulo[:0x2f]
        con.mandar_interno(0x41, seq, bytes([1]) + struct.pack("<HBBBIB", a, 0, 1 if sala.clave else 0, 1, sala.modo,
                                                                len(tit)) + tit + b"\x00")
    anotar("   FF41 info de la sala %d para %s (%s)" % (a & 0x7FF, (con.cuenta or {}).get("nick"),
                                                       "existe" if sala else "no existe"))
    return True


def listo(con, seq, cuerpo):
    """C2S FF17 (listo). S2C FF17 [resultado 0][asiento][listo] a TODOS, incluido el que apreto (nota 06 §3).
    ⚠ El C2S no esta medido: se toma el ultimo byte como listo."""
    sala = estado.SALAS.get(con.sala)
    if sala is None or not cuerpo:
        return False
    con.listo = 1 if cuerpo[-1] else 0
    asiento = next(a for a, c in sala.asientos.items() if c is con)
    for c in jugadores(sala):
        c.mandar_interno(0x17, seq if c is con else 0, bytes([0, asiento, con.listo]))
    anotar("   FF17 listo=%d del asiento %d (C2S %s) a los %d de la sala" % (con.listo, asiento, cuerpo.hex(),
                                                                          len(sala.asientos)))
    return True


def sacar_de_su_sala(con):
    """Saca al jugador de la sala donde este (salir, crear otra, conexion caida). Devuelve el numero o None."""
    numero = con.sala
    s = estado.SALAS.get(numero)
    if s is not None:
        asiento = next((a for a, c in s.asientos.items() if c is con), None)
        era_anfitrion = s.anfitrion is con
        levantar(s, con)
        if not s.asientos:
            del estado.SALAS[numero]
            estado.CERRADAS[numero] = time.time()
            anotar("   sala %d cerrada (no queda nadie)" % numero)
        else:
            # los que quedan: FF0E CmdRemovUser [asiento] (lee 1 byte, como el 2013 y el 2019) y la lista nueva. Con el
            # FF0C solo, el que quedaba seguia viendo al que se fue (medido el 01-nov)
            for c in jugadores(s):
                if asiento is not None:
                    c.mandar_interno(0x0E, 0, bytes([asiento]))
                c.mandar_interno(0x0C, 0, ff0c(s, c))
            anotar("   FF0E: el asiento %s se fue de la sala %d; quedan %d" % (asiento, numero, len(s.asientos)))
            if s.carrera is None:
                avisar_equipos(s)
            if era_anfitrion and s.anfitrion is not None:
                # el nuevo anfitrion, a toda la sala, con el FF15 (byte 2). En carrera NO (el 2013 lo difiere: rearmar la
                # sala en la carrera o en el cartel tumbaba al cliente); llega con la vuelta a la sala, que manda FF15
                nuevo = next(a for a, c in s.asientos.items() if c is s.anfitrion)
                if s.carrera is None:
                    for c in jugadores(s):
                        mandar_sala(c, s, solo=0x15)
                anotar("   la sala %d pasa al asiento %d (%s)%s" % (numero, nuevo, (s.anfitrion.cuenta or {}).get("nick"),
                       "" if s.carrera is None else ", aviso diferido: corre una carrera"))
    con.sala = None
    con.listo = 0
    return numero


def salir(con, seq, cuerpo):
    """C2S FF14 SendExitRoom. Respuesta medida en la grabacion: `0000`. ⚠ Solo si esta en una sala (nota 01 §5.4: en el
    2013 el lobby manda el mismo comando cada ~2 min, y contestarlo lo saca a la pantalla anterior)."""
    if con.sala is None:
        return False
    numero = sacar_de_su_sala(con)
    con.mandar_interno(0x14, seq, struct.pack("<H", 0))
    anotar("   S2C FF14 CmdExitRoom 0000: sale de la sala %s" % numero)
    return True


def expulsar(con, seq, cuerpo):
    """Ficha 150. C2S FF20 [asiento]. RX chino CmdKick 0x02792bd0 consume 0 B."""
    if len(cuerpo) != 1:
        return False
    sala = _de_anfitrion(con, "FF20")
    if sala is None:
        return True
    victima = sala.asientos.get(cuerpo[0])
    if sala.carrera is not None or victima is None or victima is con:
        return True
    victima.mandar_interno(0x20, 0, b"")
    sacar_de_su_sala(victima)
    anotar("   FF20 expulsar asiento %d de sala %d -> CmdKick vacio, quedan %d"
           % (cuerpo[0], sala.numero, len(sala.asientos)))
    return True


def cambiar_equipo(con, seq, cuerpo):
    """Ficha 150. C2S FF18 [equipo], mudanza por FF6B y colores por FF37."""
    if len(cuerpo) != 1 or cuerpo[0] not in (1, 2):
        return False
    sala = estado.SALAS.get(con.sala)
    if sala is None or sala.carrera is not None or not sala.modo & 0x10 or sala.modo & MODO_HEROE:
        return True
    origen = next((a for a, c in sala.asientos.items() if c is con), None)
    if origen is None:
        return True
    anterior = equipo_de(sala, con)
    equipo = cuerpo[0]
    if anterior == equipo:
        return True
    # El 2013 busca desde el centro y, con el lado lleno, permuta con el primero.
    lado = (2, 1, 0) if equipo == 1 else (3, 4, 5)
    destino = next((a for a in lado if a not in sala.asientos), lado[0])
    otro = sala.asientos.pop(destino, None)
    del sala.asientos[origen]
    sala.asientos[destino] = con
    sala.equipos[id(con)] = equipo
    con.listo = 0
    if otro is not None:
        sala.asientos[origen] = otro
        sala.equipos[id(otro)] = anterior
        otro.listo = 0
    for c in jugadores(sala):
        # CmdSwap actualiza mi asiento solo si soy el primer par (0x027b4fe3).
        pares = [destino, equipo, origen, anterior] if c is otro else [origen, anterior, destino, equipo]
        c.mandar_interno(0x6B, seq if c is con else 0, bytes(pares))
        for a, x in sorted(sala.asientos.items()):
            c.mandar_interno(0x37, 0, bytes([equipo_de(sala, x), a, a]))
        c.mandar_interno(0x17, 0, bytes([0, destino, 0]))
        if otro is not None:
            c.mandar_interno(0x17, 0, bytes([0, origen, 0]))
    _mandar_ff15_a_todos(sala)
    anotar("   FF18 equipo %d, asiento %d -> %d, permuta=%s en sala %d -> FF6B y FF37 a %d"
           % (equipo, origen, destino, otro is not None, sala.numero, len(sala.asientos)))
    return True


def _de_anfitrion(con, nombre):
    """La sala de `con` si el es el anfitrion; si no, None (y se anota). Solo el anfitrion elige cancion, pista y grupo."""
    sala = estado.SALAS.get(con.sala)
    if sala is None or sala.anfitrion is not con:
        anotar("   C2S %s de quien no es el anfitrion (o sin sala): no se cambia nada" % nombre)
        return None
    return sala


def _mandar_ff15_a_todos(sala):
    """El FF15 nuevo a toda la sala (el oficial lo manda tras un FF1B y un FF132; a los DEMAS, HIPOTESIS: la grabacion
    es del anfitrion). En carrera no: llega con la vuelta a la sala (como el aviso del nuevo anfitrion)."""
    if sala.carrera is None:
        for c in jugadores(sala):
            mandar_sala(c, sala, solo=0x15)


def elegir_pista(con, seq, cuerpo):
    """C2S FF1B [u16 pista] = la pista que eligio el anfitrion en 选择地图 (se manda al cerrar el selector). MEDIDO en el
    oficial (08-nov, 1 caso: pista 58): al anfitrion le llega un FF15 nuevo con la pista (bytes 10-11) y despues FF1B
    `00` (acuse; el cliente lo lee y no lo usa: layouts/FF1B.md). Se guarda en sala.pista y carrera.empezar la usa."""
    if len(cuerpo) < 2:
        return False
    sala = _de_anfitrion(con, "FF1B")
    if sala is None:
        return True
    pista = struct.unpack_from("<H", cuerpo)[0]
    sala.pista = pista
    anotar("   C2S FF1B pista elegida %d (0x%x) en la sala %s" % (pista, pista, sala.numero))
    _mandar_ff15_a_todos(sala)
    con.mandar_interno(0x1B, seq, bytes(1))
    return True


def elegir_cancion(con, seq, cuerpo):
    """C2S FF1C CmdEditMusic `[u8 sub][u16 valor][u8][u8]` (5 B). MEDIDO en el oficial (08-nov, 9 pedidos): el anfitrion manda
    DOS al elegir (sub 0 y sub 1) y uno solo para «al azar» (sub 5 valor 0). Contesta SOLO el primero, igual (eco): a
    sub 0 y a sub 5; a sub 1 no contesta. La cancion del FF25 de la carrera es la ultima del sub 0 (4 de 4) y el FF15
    la trae en los bytes 13-14 (ff15_para). Ficha 150: los demas reciben ese FF15 inmediatamente."""
    if len(cuerpo) != 5 or cuerpo[0] not in (0, 1, 5):
        return False
    sala = _de_anfitrion(con, "FF1C")
    if sala is None:
        return True
    sub, valor = cuerpo[0], struct.unpack_from("<H", cuerpo, 1)[0]
    if sub == 1:
        return True
    sala.cancion = valor if sub == 0 and valor else None
    con.mandar_interno(0x1C, seq, cuerpo)
    if sala.carrera is None:
        for c in jugadores(sala):
            if c is not con:
                mandar_sala(c, sala, solo=0x15)
    anotar("   C2S FF1C sub %d cancion %s (0x%x) en la sala %s -> eco y FF15 a los demas" % (sub, sala.cancion, valor, sala.numero))
    return True


def grupo_coop(con, seq, cuerpo):
    """C2S FF132 `[u8 grupo]` 1 o 2 (grupo del cooperativo). MEDIDO en el oficial (3 de 3, en este orden): FF1C
    `0400000200`, FF132 `00` y un FF15 nuevo con el grupo en el byte 16+n+47 y la pista 9 (grupo 1) o 10 (grupo 2).
    El FF132 de vuelta el cliente lo lee y no lo usa. HIPOTESIS: el FF15 tambien a los demas."""
    if len(cuerpo) != 1 or cuerpo[0] not in (1, 2):
        return False
    sala = _de_anfitrion(con, "FF132")
    if sala is None:
        return True
    sala.grupo = cuerpo[0]
    con.mandar_interno(0x1C, 0, bytes.fromhex("0400000200"))
    con.mandar_interno(0x132, seq, bytes(1))
    _mandar_ff15_a_todos(sala)
    anotar("   C2S FF132 grupo %d en la sala %s -> FF1C 04, FF132 00 y FF15 (pista %d)"
           % (sala.grupo, sala.numero, {1: 9, 2: 10}[sala.grupo]))
    return True


def selector(con, seq, cuerpo):
    """C2S FF79 `[u8 x][06]` (x = 1 abre el selector de cancion, 2 el de pista/grupo, 0 cierra). MEDIDO: el oficial
    contesta FF79 con el mismo byte (17 de 18 con respuesta; el cliente lo guarda en [juego+0x77cf]). Solo al que pidio."""
    if len(cuerpo) != 2:
        return False
    con.mandar_interno(0x79, seq, bytes([cuerpo[0]]))
    return True


def records_cancion(con, seq, cuerpo):
    """C2S FF139 `[u16 cancion]` (el anfitrion se para sobre una cancion del selector) -> S2C FF139 de 19 B:
    `[u16 cancion][u8 marca][u16 a][u16 b][u32 c][u32 d][u32 e]` (layouts/FF139.md; 0xa111a0 pone a, b y min(c, 999999) en
    pantalla). MEDIDO: las canciones nunca jugadas (10 de 13) vienen con todo en 0 menos d = 999. Nosotros no guardamos
    records: SIEMPRE mandamos ese «sin record». HIPOTESIS: a, b, c son records personales (las jugadas traen 157/94/2, etc.)."""
    if len(cuerpo) != 2:
        return False
    cancion = struct.unpack_from("<H", cuerpo)[0]
    con.mandar_interno(0x139, seq, struct.pack("<HBHHIII", cancion, 0, 0, 0, 0, 999, 0))
    return True


# ⭐ 10-nov: CAMBIO DE MODO EN LA SALA, C2S FF1F8 -> S2C FF4B (CmdChangeRoomMode, 0x027a7030). MEDIDO en la grabacion del
# oficial del 08-nov a la tarde (7 pedidos, todos en claro; layout del FF4B de nuestro exe, docs/tablero/layouts/FF4B.md):
#   C2S: [u32 modo][u8 n][titulo][u8 m][clave]   (docs/tablero/layouts/FF1F8.md)
#   S2C a cada uno (en este orden): FF17 [0][asiento][0] de cada asiento (de menor a mayor; el FF4B va justo DESPUES del
#   FF17 del asiento del que lo recibe), y al final un FF0C nuevo.
#   FF4B OK: [1][A][n][titulo][m][clave][u32 modo SIN 0x40000][x1=0][x2=0]
#            (heroe: [cant] cant x [asiento viejo][asiento nuevo][equipo], 6 x [asiento abierto], [asiento del anfitrion],
#             [mi asiento])  [grupo 0][velocidad 3] 9 B de banderas  [u32 mascara de lugares: 0x0fff, heroe 0x0ff3]
#   RECHAZO (un segundo cambio sin jugar en medio): FF4B `000000` + FF0C, solo al que pidio.
# HIPOTESIS (un solo testigo, no medidas): A segun el modo (el cliente no lo usa); lo que recibe un jugador que no es el
# anfitrion (se supone lo mismo con su asiento); el reparto del heroe (2->4, 3->0 salio de UN caso: los que estan en 2 y 3
# pasan a los libres 0, 4, 5, de atras para adelante); salir del heroe (los asientos quedan donde estan); el rechazo por
# otros motivos (familia, pareja, espectadores, mas de 4 en heroe: codigos 2-16 del manejador, sin grabar -> no se manda
# nada); FF37/FF175 al pasar a capitan (el oficial no los mando en la ventana medida).
def _categoria_a(modo):
    """Byte A del FF4B (= estado de la lista y byte 4 del FF15): 0x10 heroe/equipo, 0x04 capitan/coop, 0x08 en 0x88."""
    if modo & MODO_HEROE or modo & 0x10:
        return 0x10
    if modo & 0x4000 or modo & 0x8000:
        return 0x04
    if modo & 0x80:
        return 0x08
    return 0


def _repartir_heroe(sala):
    """Los lugares 2 y 3 son del heroe: los que estan ahi pasan a los libres 0, 4, 5 (de atras para adelante).
    Devuelve [(viejo, nuevo)] por asiento viejo, o None si no entran (mas de 4)."""
    permitidos = (0, 1, 4, 5)
    if len(sala.asientos) > len(permitidos):
        return None
    mover = sorted((a for a in sala.asientos if a not in permitidos), reverse=True)
    libres = [a for a in permitidos if a not in sala.asientos]
    destino = {a: a for a in sala.asientos if a in permitidos}
    for a in mover:
        destino[a] = libres.pop(0)
    return sorted(destino.items())


def ff4b_para(sala, con, movidas):
    modo, tit, clave = sala.modo, sala.titulo, sala.clave
    heroe = bool(modo & MODO_HEROE)
    mascara = 0x0FF3 if heroe else 0x0FFF
    cu = (bytes([1, _categoria_a(modo), len(tit)]) + tit + bytes([len(clave)]) + clave
          + struct.pack("<I", modo & 0xFFFFFFFF) + b"\0\0")
    if heroe:
        yo = next(a for a, c in sala.asientos.items() if c is con)
        cu += (bytes([len(movidas)]) + b"".join(bytes([v, n, equipo_de(sala, sala.asientos[n])]) for v, n in movidas)
               + bytes((mascara >> i) & 1 for i in range(6)) + bytes([_asiento_anfitrion(sala), yo]))
    banderas = [0] * 9
    banderas[0] = 1 if modo & 0x4000 else 0       # medidas: capitan -> 1.o, 0x200000 -> 4.o, 0x800 -> 8.o (lado)
    banderas[3] = 1 if modo & 0x200000 else 0
    banderas[7] = 1 if modo & 0x800 else 0
    return cu + bytes([0, 3]) + bytes(banderas) + struct.pack("<I", mascara)


def cambiar_modo(con, seq, cuerpo):
    """C2S FF1F8 SendChangeRoomMode2: el anfitrion cambia el modo y el titulo sin salir de la sala."""
    sala = estado.SALAS.get(con.sala)
    if sala is None or sala.anfitrion is not con:
        anotar("   C2S FF1F8 de quien no es el anfitrion (o sin sala): no se cambia nada")
        return True
    try:
        if cuerpo[-4:] == bytes.fromhex("fecddfbd"):
            cuerpo = descifrar_cuerpo(cuerpo)
        modo = struct.unpack_from("<I", cuerpo, 0)[0]
        n = cuerpo[4]
        titulo = cuerpo[5:5 + n]
        m = cuerpo[5 + n]
        clave = cuerpo[6 + n:6 + n + m]
        if len(titulo) != n or len(clave) != m or 6 + n + m != len(cuerpo):
            raise ValueError("largos")
    except (ValueError, IndexError, struct.error) as e:
        anotar("   ⛔ C2S FF1F8 que no se lee (%s): %s" % (e, cuerpo.hex()))
        return True
    if sala.cambio_sin_jugar:
        # medido: texto 0x76 "hay que jugar al menos una partida antes de volver a cambiar la sala"
        con.mandar_interno(0x4B, seq, b"\0\0\0")
        con.mandar_interno(0x0C, 0, ff0c(sala, con))
        anotar("   S2C FF4B 000000: segundo cambio de modo sin jugar (modo pedido 0x%x), rechazado" % modo)
        return True
    movidas = None
    if modo & MODO_HEROE:
        movidas = _repartir_heroe(sala)
        if movidas is None:
            anotar("   FF1F8 heroe con %d en la sala: el oficial rechaza (codigo 16, sin grabar); no se contesta"
                   % len(sala.asientos))
            return True
        sala.asientos = {n: sala.asientos[v] for v, n in movidas}
    sala.modo, sala.titulo, sala.clave = modo, titulo, clave
    sala.orden = orden_asientos(modo)
    sala.equipos = {}                      # los equipos se recalculan con el modo nuevo (capitan 1,1,2; heroe 2)
    sala.cambio_sin_jugar = True
    sala.pista = 0                         # 10-nov (ficha 12, medido 9 de 9): tras un FF1F8 el oficial vuelve la pista a 0
    for c in jugadores(sala):
        c.listo = 0
    for c in jugadores(sala):
        propio = next(a for a, x in sala.asientos.items() if x is c)
        for a in sorted(sala.asientos):
            c.mandar_interno(0x17, 0, bytes([0, a, 0]))
            if a == propio:
                c.mandar_interno(0x4B, seq if c is con else 0, ff4b_para(sala, c, movidas))
        c.mandar_interno(0x0C, 0, ff0c(sala, c))
    anotar("   S2C FF4B cambio de modo: 0x%x, titulo %r, %d en la sala %d%s"
           % (modo, titulo, len(sala.asientos), sala.numero, ", asientos %s" % movidas if movidas else ""))
    return True


MANEJADORES = {
    0x20: expulsar,
    0x18: cambiar_equipo,
    0x1F6: lista,
    0x1B: elegir_pista,
    0x79: selector,
    0x139: records_cancion,
    0x1C: elegir_cancion,
    0x132: grupo_coop,
    0x1F5: crear,
    0x1F8: cambiar_modo,
    0x15: info,
    0x0C: lista_jugadores,
    0x14: salir,
    0x1F7: rapida,
    0x0F: unirse,
    0x17: listo,
    0x41: info_por_numero,
}
