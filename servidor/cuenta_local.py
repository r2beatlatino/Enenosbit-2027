# -*- coding: utf-8 -*-
r"""cuenta_local.py (ficha 38) — lo que el servidor contesta COPIANDO o RECONSTRUYENDO de la captura, para una cuenta LOCAL:
crear personaje (FF06) y lo que el cliente pide justo despues (FF07, FF7F, FF137, FF05), y la sala grabada del oficial
(FF1F5 / FF15 / FF0C) cuando salas.py no la contesta. Estaba en juego.py (`responder_locales`, `responder_comandos`,
`responder_crear_sala`); ahora es un modulo recargable con su tabla MANEJADORES.

Se prueban DESPUES de los manejadores con logica propia (manejadores.py los pone al final): si salas.py, tienda.py, etc. contestan
un comando, estos no se llaman. Con MANEJADORES_STEAM=0 son los unicos que quedan (el servidor de la captura).
⚠⚠ RECONSTRUIDO: la sesion capturada es de una cuenta que ya tenia personaje, asi que estas respuestas son las capturadas de esos
mismos comandos (o su eco), no las de un alta.
"""
import os
import struct

import ajustes
import captura
import cuentas
import estado
import fichas
import neutro

FF07_CAP = captura.cuerpo_capturado(0x07)      # 5 B, lote 7 de la rafaga
FF05_CAP = captura.cuerpo_capturado(0x05)      # 20 B


def anotar(txt):
    estado.anotar(txt)


# ---------- crear personaje ----------
def crear_personaje(con, seq, cuerpo):
    """29-oct: CREAR PERSONAJE (RECONSTRUIDO). C2S FF06 SendDefaultChar -> S2C FF06 CmdDefaultChar (0x027834a0), medido en el
    exe: [u32 resultado] y, si no es 0 ni -1, [u8 n][n x u32 partes]. El resultado ES el char_id (el cliente lo compara con
    0x1ff54/0x1ff55); 0 = "el nombre ya existe" y -1 = otro cartel, como el FF04 del 2013 (lobby_menu.h_01_ff04). Con eso arma
    el personaje (0x004ec040) y llama a SendJoinChannel (0x02764420). Solo para una cuenta local."""
    if con.cuenta is None:
        return False
    try:
        pj = cuentas.leer_default_char(cuerpo)
    except (ValueError, IndexError, struct.error) as e:
        anotar("   ⛔ C2S FF06 SendDefaultChar que no se lee (%s): %s" % (e, cuerpo.hex()))
        return True
    anotar("   C2S FF06 CREAR PERSONAJE: char_id %d, nick %r, partes %s" % (pj["char_id"], pj["nick"], pj["partes"]))
    # ficha 42: el apodo ya es de OTRA cuenta (de cuenta o de personaje) -> resultado 0 = "el nombre ya existe" y no se guarda nada.
    # Medido en el exe (CmdDefaultChar 0x027834a0): con 0 lee solo el u32 y muestra el cartel (0x027836d5 -> 0x0278373d ->
    # 0x02783985, el fin); no lee la lista de partes ni arma el personaje, asi que el cliente vuelve a la pantalla de crear.
    if cuentas.apodo_ocupado(pj["nick"], con.cuenta["steamid"], excepto_usn=con.cuenta.get("usn")):
        con.mandar_interno(0x06, seq, struct.pack("<I", 0))
        anotar("   S2C FF06 CmdDefaultChar: resultado 0 (el nombre %r ya existe); no se guarda nada" % pj["nick"])
        return True
    guardada = cuentas.guardar_personaje(con.cuenta["usn"], pj)
    if guardada is None:
        con.mandar_interno(0x06, seq, struct.pack("<i", -1))
        anotar("   ⛔ S2C FF06 CmdDefaultChar: resultado -1 (tope de %d personajes o sin slot)" % cuentas.MAX_PERSONAJES)
        return True
    con.cuenta = guardada
    con.mandar_interno(0x06, seq, struct.pack("<IB", pj["char_id"], len(pj["partes"]))
                       + struct.pack("<%dI" % len(pj["partes"]), *pj["partes"]))
    anotar("   S2C FF06 CmdDefaultChar: personaje %d (%r, usn %d) creado y guardado en cuenta.json"
           % (pj["char_id"], pj["nick"], con.cuenta["usn"]))
    return True


# ---------- lo que pide una cuenta local despues de CREAR su personaje ----------
# Medido el 01-nov: tras el FF06 el cliente manda FF7F (17 B), FF07 (1 B) y FF05 (0 B), y despues FF137 (0 B) cada ~2,5 s,
# quieto en la pantalla de crear.
def entrar_canal(con, seq, cuerpo):
    """C2S FF07: CNetwork::CmdJoinChannel (0x02783f80; lee un u8 y sigue en una pieza repatriada). Despues de crear,
    CmdDefaultChar llama a SendJoinChannel(0) (0x02764420), el MISMO llamado que hace CmdLogin en un login normal (0x0277bda3);
    en la captura la respuesta a ese fue el FF07 de 5 B de la rafaga (lote 7). Y la ficha otra vez, ya CON el personaje."""
    if con.cuenta is None:
        return False
    r = FF07_CAP if FF07_CAP is not None else b"\x00"
    con.mandar_interno(0x07, seq, r)
    anotar("   S2C FF07 CmdJoinChannel: %s (%s)" % (r.hex(), "el capturado" if FF07_CAP else "armado"))
    # y la ficha otra vez, ya CON el personaje recien creado (el cliente la pidio con SendMyRecord al entrar)
    c = cuentas.por_usn(con.cuenta["usn"]) or con.cuenta
    con.cuenta = c
    if c.get("personaje"):
        nuevo = fichas.ficha_nueva(c)
        if nuevo:
            con.mandar_claro(nuevo)
            anotar("   S2C FF00 la ficha de nuevo, con el personaje %d" % c["personaje"]["char_id"])
        # 01-nov, medido y descartado: despues de crear el cliente pide FF1BE, FF13B y musicMedalNet.onInit y se queda en la
        # pantalla de crear. Reenviarle el resto de la rafaga de la entrada (lotes 7..59, ya con su ficha) NO lo saca de ahi.
        # Lo que anda: cerrar y volver a entrar (FF0B con el personaje).
    return True


def avatar_eco(con, seq, cuerpo):
    """C2S FF7F -> S2C FF7F: CNetwork::CmdEditAvatarMult: [u8 n][n x u32 partes]. En la captura el oficial devolvio las mismas 4
    partes que trae la ficha de esa cuenta: es el eco del pedido. (tienda.avatar contesta antes si la cuenta tiene personaje.)"""
    if con.cuenta is None:
        return False
    con.mandar_interno(0x7F, seq, cuerpo)
    anotar("   S2C FF7F CmdEditAvatarMult: eco de las %d partes" % (cuerpo[0] if cuerpo else 0))
    return True


def favoritas(con, seq, cuerpo):
    """C2S FF137 -> S2C FF137 CNetwork::CmdGetFavoriteSongs: [u16 n][n x u16 songid]. Un personaje nuevo no tiene favoritas.
    19-nov: la sesion capturada (con.cuenta None) tampoco recibia respuesta desde el 16-nov: el cliente repite el FF137
    cada ~2,5 s y el boton Modo Baile no abre (con cuenta nueva, que si recibe esta respuesta, abre: ficha 174, A1_CLUB_4).
    A la sesion capturada se le contesta 0 favoritas: INVENTADO (no hay favoritas grabadas del oficial). Llave
    FAVORITAS_CAPTURADA=0 vuelve a lo de antes."""
    if con.cuenta is None:
        if os.environ.get("FAVORITAS_CAPTURADA", "1") == "0":
            return False
        con.mandar_interno(0x137, seq, struct.pack("<H", 0))
        anotar("   S2C FF137 CmdGetFavoriteSongs: 0 favoritas (sesion capturada, INVENTADO)")
        return True
    con.mandar_interno(0x137, seq, struct.pack("<H", 0))
    anotar("   S2C FF137 CmdGetFavoriteSongs: 0 favoritas")
    return True


def latido(con, seq, cuerpo):
    """C2S FF05 -> S2C FF05 CNetwork::CmdAck (el latido): el capturado, con la llave de hardware de esta maquina."""
    if con.cuenta is None or FF05_CAP is None:
        return False
    con.mandar_interno(0x05, seq, FF05_CAP)
    return True


# ---------- la sala grabada del oficial ----------
def mandar_sala_grabada(con, solo=None):
    """01-nov: la respuesta del oficial a crear sala, tal cual la grabo GrabadorR2Beat (herramientas/preparar_crear_sala.py ->
    datos/crear_sala_S2C.bin): FFFD, FF12D, FF0C, FF232, FF1C x2, FF10, FF167, FF246 room.createRoom, FF15, FF246. ⚠⚠
    RECONSTRUIDO / COPIADO: el FF1F5 llega CIFRADO (lo arma Lua, no se descifro), asi que la sala sale con el MODO, el titulo
    y la lista de jugadores de la sala grabada, no con los elegidos. True si contesto."""
    claros = captura.claros_crear_sala()
    if claros is None:
        anotar("   ⚠ sin datos/crear_sala_S2C.bin (correr herramientas/preparar_crear_sala.py): no contesto")
        return False
    n = 0
    for claro in claros:
        internos = captura.internos_todos(claro)
        if solo is not None and not any(c == solo for c, _s, _c in internos):
            continue
        if con.cuenta is not None and len(internos) == 1 and internos[0][0] == 0x0C:
            # el FF0C (RoomUserList) con el jugador de esta cuenta, no el grabado
            _c, sq, cu = internos[0]
            cu = fichas.sala_para(cu, con.cuenta)
            claro = b"\xff\x56\x00\x00" + struct.pack("<BBHI", 0xFF, 0x0C, sq, len(cu)) + cu
        con.mandar_claro(claro)
        n += 1
    if solo is not None:
        anotar("   S2C FF%X de la sala grabada (%d)" % (solo, n))
    else:
        anotar("   S2C CREAR SALA: %d mensajes grabados del oficial (FF0C, FF232, FF1C, FF10, FF167, FF246, FF15...)" % n)
    return n > 0


def crear_sala(con, seq, cuerpo):
    """C2S FF1F5 CREAR SALA que salas.crear no pudo leer. 01-nov: se anota entero para atar cada modo de la ventana
    赛场创建 a sus bytes (docs/FF_HANDLERS_CHINO.md §6)."""
    anotar("   C2S FF1F5 CREAR SALA (%d B): %s" % (len(cuerpo), cuerpo.hex(" ")))
    return mandar_sala_grabada(con)


def info_sala(con, seq, cuerpo):
    """C2S FF15 (0 B): al cargar la escena de la sala el cliente pide FF15 RoomInfo y espera."""
    return not cuerpo and mandar_sala_grabada(con, solo=0x15)


def lista_sala(con, seq, cuerpo):
    """C2S FF0C (1 B): despues, la lista de jugadores de la sala."""
    return len(cuerpo) == 1 and mandar_sala_grabada(con, solo=0x0C)


# ---------- ficha 91: la entrada completa (FF133, FF247, FF267) ----------
# Leido en el exe y medido en 9 conexiones de juego del oficial (docs/tablero/layouts/FF133.md, FF247.md, FF267.md):
#  - FF133 (S2C sin pedido, 1 B, siempre 00): objetos de Mi Casa vencidos [u8 n]; con n = 0 el manejador 0x027f7d40 solo baja un
#    campo y no saca cartel. El oficial lo manda justo despues de FF16D. Llave FF133_ENTRADA.
#  - FF247 (C2S 0 B -> S2C 1 B, siempre 01): 0x028713f0 guarda el byte en 0x03a35a2f; se pide al entrar y cada vez que se vuelve
#    al lobby, pegado a FF97. Se contesta CADA pedido; el 1.o de la conexion se salta si la rafaga de entrada ya trajo el suyo
#    (si no, saldrian dos). Llave FF247_RESPUESTA.
#  - FF267 (C2S 4 B -> S2C 59 B): la respuesta es una direccion web del OFICIAL (igual en 9 de 9 y en la captura del 22-oct): NO se
#    manda (regla: no tocar el oficial). Sin respuesta A PROPOSITO; queda anotado para que no figure como pendiente.
# Las llaves se leen del entorno en cada uso (FF133_ENTRADA=0/1, FF247_RESPUESTA=0/1); LLAVES_OMISION dice la de omision.
LLAVES_OMISION = {"FF133_ENTRADA": "1", "FF247_RESPUESTA": "1", "HORA_REAL": "1", "MEDALLAS_CANCION": "1", "SALDOS_AL_DIA": "1"}


def llave(nombre):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def _cuerpo_de_respuestas(cmd):
    """El cuerpo del primer marco `cmd` de datos/respuestas_S2C.bin (la captura del 22-oct). None si no esta."""
    for claro in captura.lotes_capturados(10 ** 6, ajustes.RUTA_RESPUESTAS):
        for c, _s, cu in captura.internos_todos(claro):
            if c == cmd:
                return cu
    return None


FF133_CAP = _cuerpo_de_respuestas(0x133)      # 1 B: 00 (n = 0 objetos vencidos)
FF247_CAP = _cuerpo_de_respuestas(0x247)      # 1 B: 01


def tras_lote(con, claro):
    """juego.mandar_lote lo llama despues de cada lote de la rafaga. Anota que comandos ya salieron y, justo despues del FF16D
    (donde lo manda el oficial: FF267, FF120, FF133, FF214), manda el FF133 vacio."""
    cmds = captura.internos_todos(claro)
    vistos = getattr(con, "rafaga_cmds", None)
    if vistos is None:
        vistos = con.rafaga_cmds = set()
    vistos.update(c for c, _s, _cu in cmds)
    if llave("FF133_ENTRADA") and FF133_CAP is not None and len(FF133_CAP) == 1 and not getattr(con, "ff133_mandado", False):
        for c, seq, _cu in cmds:
            if c == 0x16D:
                con.ff133_mandado = True
                con.mandar_interno(0x133, seq, FF133_CAP)
                anotar("   S2C FF133 objetos de Mi Casa vencidos: %d (1 B, justo despues del FF16D de la rafaga)" % FF133_CAP[0])
                break


def pedido_funcion(con, seq, cuerpo):
    """C2S FF247 (0 B) -> S2C FF247 (1 B): CNetwork::CmdFunction. Cada pedido tiene su respuesta (33 de 33 en las grabaciones)."""
    if not llave("FF247_RESPUESTA") or FF247_CAP is None or len(FF247_CAP) != 1:
        return False
    n = getattr(con, "ff247_pedidos", 0)
    con.ff247_pedidos = n + 1
    if n == 0 and 0x247 in getattr(con, "rafaga_cmds", ()):
        anotar("   C2S FF247 (1.o de la conexion): ya salio dentro de la rafaga de entrada, no se repite")
        return False
    con.mandar_interno(0x247, seq, FF247_CAP)
    anotar("   S2C FF247 CmdFunction: %02x (pedido %d de esta conexion)" % (FF247_CAP[0], n + 1))
    return False        # False a proposito: el resto del camino de hoy (seguir_patron) queda igual; con la rafaga ya mandada no hace nada


def pedido_hora(con, seq, cuerpo):
    """C2S FF97 (0 B) -> S2C FF97 (23 B) con la hora de AHORA (ficha 44; el oficial contesta cada pedido: 25 de 27 a menos de 1 s en la
    grabacion 20261108_151138). El FF97 es el reloj del cliente (fichas.reloj_cuerpo). Con HORA_REAL=0 no se manda nada, como antes."""
    if cuerpo or not fichas.hora_real_activa():
        return False
    con.mandar_interno(0x97, seq, fichas.reloj_cuerpo())
    anotar("   S2C FF97 hora real: %s" % fichas.reloj_cuerpo()[1:15].decode())
    return False        # False a proposito (como el FF247): el resto del camino de hoy (seguir_patron) queda igual


def popup_entrada(con, seq, cuerpo):
    """C2S FF267 (4 B, u32 = 0) SendGetPopupInfo. El oficial contesta con una direccion web suya; NO se manda."""
    anotar("   C2S FF267 popup de entrada: sin respuesta A PROPOSITO (la del oficial es una direccion web suya; el cliente sigue sin ventana)")
    return False        # False a proposito: no cambia nada del camino de hoy (seguir_patron), solo deja la linea en el registro


# Ficha 85 (11-nov): `musicMedalNet.onInit` (FF246, metodo por nombre). El cliente lo pide al terminar el FF00 (`[1,100]`, 0x027811bd) y el oficial
# lo contesto 9 de 9 (grabaciones). Aca SOLO la respuesta VACIA `{"l":{},"max":0}` (16 B; 3 de 9 conexiones), el mensaje en claro entero de la
# conexion 20261029_213306 (84 B: sobre FF56 + marco `fd 46`, 8 bytes del servidor, id = 0 (el oficial NO repite el id del pedido en este metodo),
# nombre, JSON y cola), mandado TAL CUAL (con su seq de marco). Sin `update`, sin filas por cancion. Llave MEDALLAS_CANCION (prendida por omision desde la prueba con juego del 11-nov; 0 = como antes).
# (cerebro, 11-nov) Los 84 B salen de una grabacion del oficial: van FUERA de git, en datos/medallas_oninit.hex (como las demas
# capturas). Si el archivo falta, no se contesta (igual que con la llave en 0).
RUTA_ONINIT = os.path.join(ajustes.DATOS, "medallas_oninit.hex")


def _leer_oninit():
    try:
        with open(RUTA_ONINIT, encoding="ascii") as f:
            b = bytes.fromhex(f.read().strip())
        return b if len(b) == 84 and b"musicMedalNet.onInit" in b else None
    except (OSError, ValueError):
        return None


ONINIT_VACIO = _leer_oninit()


def pedido_medallas_cancion(con, seq, cuerpo):
    """C2S FF246 con `musicMedalNet.onInit`: manda la respuesta vacia grabada. Siempre False: el resto del camino de hoy queda igual."""
    if not llave("MEDALLAS_CANCION") or len(cuerpo) < 12:
        return False
    nl = struct.unpack_from("<I", cuerpo, 8)[0]
    if cuerpo[12:12 + nl] != b"musicMedalNet.onInit":
        return False
    if ONINIT_VACIO is None:
        if os.path.exists(RUTA_ONINIT):
            return False  # presente pero invalido: se conserva la conducta previa
        con._medallas_neutras = getattr(con, '_medallas_neutras', 0) + 1
        con.mandar_interno(0x246, seq, neutro.medallas_oninit(cuerpo, con._medallas_neutras))
        anotar("   S2C musicMedalNet.onInit: respuesta vacia neutra")
        return True
    con.mandar_claro(ONINIT_VACIO)
    anotar("   S2C musicMedalNet.onInit: respuesta VACIA grabada del oficial (%d B)" % len(ONINIT_VACIO))
    return False


MANEJADORES = {
    0x06: crear_personaje,
    0x07: entrar_canal,
    0x7F: avatar_eco,
    0x137: favoritas,
    0x05: latido,
    0x1F5: crear_sala,
    0x15: info_sala,
    0x0C: lista_sala,
    0x247: pedido_funcion,
    0x97: pedido_hora,
    0x267: popup_entrada,
    0x246: pedido_medallas_cancion,
}
