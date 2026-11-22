# -*- coding: utf-8 -*-
r"""casa.py (11-nov, ficha 94) — Mi Casa (小窝) de una cuenta LOCAL: entrar a la casa PROPIA vacia, verla y salir. Todo lo que
se sabe sale de docs/tablero/layouts/FF11B.md ("Lectura de la ficha 94") y de la traza con el juego (ver la ficha 94, Informe).
No hay muebles todavia (ficha siguiente).

Mensajes (todos adentro de un FF55; el numero de cada uno es el del exe de Steam). SECUENCIA MEDIDA con el juego (copia 2, 11-nov):
  1. el cliente toca 我的空间 > 我的小窝 (Lua `GOTO_Myroom` 0x007b7a30) y manda C2S FF181 SendMiniGameExit (0 B)
  2. S2C FF181 vacio  ->  el cliente manda C2S FF0F SendJoinRoom [u16 A][u32] con A = (0xA<<11)|n  (SIN FF233 para la casa propia)
     (la primera vez despues del login hay que tocar el boton DOS veces: el 1.o solo manda FF181 y no sigue; HIPOTESIS 0x008c1700
      cMultiplay::SetChannel(5) falla esa vez; lo mide el informe de la ficha 94)
  3. S2C FF0F [u8 slot][u8 tipo 0xA][u8][u8], FF61 [u16 A][u8 slot < 0x28][u8 tipo][u32], FF120 [0][0], FF11B (casa vacia)
  4. el cliente pide C2S FF15 (info de sala) y FF0C (lista de jugadores): se contestan con las funciones de salas.py sobre una Sala de
     DATOS (no registrada en estado.SALAS); sin eso queda esperando en la pantalla de carga, y contestadas con la sala de carrera
     grabada el cliente se cierra solo
  5. salir: el boton de la flecha o el icono de la casa mandan C2S FF181 (se contesta), C2S FF14 (se contesta 0000), C2S FF181 otra vez.
     OJO: contestar FF14 con un S2C FF14 sin que el cliente lo pida lo hace repetir FF181 sin fin (medido).
  C2S FF233 SendCheckMyRoomJoin [u8 L][apodo] / S2C [u8 res][u8 L][apodo][u8 x]: LEIDO, el cliente NO lo manda para la casa propia (visitar
     a otro: sin probar con el juego). res 0 = bien; 1 = no existe; 2 = sin llave; 3.. = sin permiso (carteles 0x39f / 0x93 / 0x3c2).
  S2C FF11B CmdMyRoomInventory  [u8 L][L B][i32 n1][268 B bloque][n1 x 44 B][i32 n2][n2 x 44 B]   (casa vacia: L = 0, n1 = n2 = 0)
  S2C FF120 (sin nombre)        [u8 0][u8 0]  (las dos listas de llaves, vacias)

El bloque de 268 B (LEIDO en 0x008d35a0 y FF121): +0 u8 publica · +1..3 relleno · +4 u32 fecha de la intro empaquetada (anio 12 bits,
mes 4 bits <<12, dia 5 bits <<16; 0 = sin fecha) · +8.. 256 B de texto de intro (255 + NUL) · +264 u32 (sin uso conocido).
INVENTADO y marcado en la seccion `casa` de la cuenta (`inventado: true`): publica = 1, fecha 0, intro vacia, el u32 de FF61, el u8 x de
FF233, el orden de los mensajes de entrada (ver ORDEN en la ficha).

ESTADO (seccion `casa` de la cuenta, solo via cuenta.py): se crea la primera vez que entra. Sin muebles.

CASA_VACIA (llave de entorno, omision 1): 0 = todo como antes (esto no contesta nada). 1 = entrar a la casa propia vacia.
"""
import os
import struct
import time

import cuenta as _cta
import estado
import textos

# CASA_VACIA: 1 desde que con el juego entro, se vio y se salio 3 de 3 (ficha 94). CASA_MUEBLES y CASA_COMPRA: 1 desde la ficha 109 (con el juego: 装扮
# habilitado con el FF61 = usn, colocar / girar / mover / guardar y comprar, 3 de 3, tambien tras reiniciar el servidor).
# CASA_PRIMER_TOQUE (ficha 128): 0 = el 1.er toque de 我的小窝 solo manda el FF181 (hace falta tocar dos veces, como hasta hoy);
# 1 = el servidor refuerza el 1.er toque (ver `salida_181` y `_refuerzo_toque`).
LLAVES_OMISION = {"CASA_VACIA": "1", "CASA_MUEBLES": "1", "CASA_COMPRA": "1", "CASA_PRIMER_TOQUE": "1", "CASA_FECHA": "1", "CASA_VISITAR": "0"}
# Refuerzo del 1.er toque (HIPOTESIS armada con la lectura de la ficha 127 y lo medido en la ficha 124; ver CASA_LECTURA.md):
DEMORA_VER_FF0F = 0.4        # s que se espera el FF0F del cliente antes de reforzar (con el canal logico ya en 5 llega en el mismo ms)
DEMORA_FF169 = 1.5           # s desde el FF7 hasta el FF169 de refuerzo
CON_FF7 = True               # mandar el FF7 [00] antes del FF169
VENTANA_FF14 = 5.0           # s despues de un FF14 (la salida manda FF181, FF14, FF181 a ~2,1 s) sin armar nada
UNA_VEZ_CADA = 30.0          # s minimos entre dos refuerzos de la misma conexion
# Revision 128b (13-nov): el FF181 NO es solo de Mi Casa (abrir la granja manda FF181 + FF14C 04, cerrarla FF150 x2 + FF181 x2; MEDIDO: el refuerzo
# le mandaba FF7 + FF169 a una copia fresca que entraba a la granja). El 1.er toque de Mi Casa manda SOLO el FF181. Por eso `otro_destino` observa (y
# devuelve False: no contesta) los pedidos de OTRO destino de la misma conexion: si llega uno despues del FF181 el refuerzo se anula, y si hubo uno en
# los VENTANA_OTRO s anteriores no se arma. Si se anula, el usuario toca dos veces (el comportamiento seguro de antes).
VENTANA_OTRO = 3.0
DESTINOS_OTROS = (0x14C, 0x150, 0x26F, 0x167, 0x1DD, 0x1DC, 0x1C8)      # granja, cerrar granja, jardin (gardenSys.*), sala magica, boda
VERSION_ESTADO = 1
TIPO_CASA = 0xA              # [cRoom+0x5d74]^0xFD == 0xA: IsChannelMyRoom (0x00a69430), LEIDO
LARGO_BLOQUE = 268
ANCHO_BASE = 30              # myroom.xml circlemap width (MEDIDO en la tabla)
RES_OK, RES_NO_EXISTE, RES_SIN_LLAVE, RES_SIN_PERMISO = 0, 1, 2, 3     # FF233 S2C (carteles 0x39f / 0x93 / 0x3c2, LEIDO)


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="CASA_VACIA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


# ---------------------------------------------------------------- estado
def _inicial(ahora):
    return {"version": VERSION_ESTADO, "inventado": True, "creada": ahora, "publica": 1, "fecha_intro": 0, "intro": "",
            "ancho": ANCHO_BASE, "objetos": [], "guardados": [], "entradas": 0}


def estado_de(usn, ahora=None):
    """La seccion `casa` de ese usn; si no tiene (o es de otra version) la crea INVENTADA y la guarda. Devuelve copia."""
    ahora = int(time.time()) if ahora is None else ahora

    def f(c):
        if c.get("version") != VERSION_ESTADO:
            c.clear()
            c.update(_inicial(ahora))
        return dict(c)
    return _cta.cambiar_seccion(usn, "casa", f)


def contar_entrada(usn):
    def f(c):
        if c.get("version") != VERSION_ESTADO:
            c.clear()
            c.update(_inicial(int(time.time())))
        c["entradas"] = int(c.get("entradas", 0)) + 1
        return c["entradas"]
    return _cta.cambiar_seccion(usn, "casa", f)


# ---------------------------------------------------------------- cuerpos
def fecha_de(c):
    """La fecha de 小窝信息 (小窝更新日期). Sin la llave CASA_FECHA: `fecha_intro` tal cual (0 = `-`, como hasta la ficha 127). Con la llave: la
    `fecha_intro` si la hay; si no la de la ultima decoracion (`fecha_mod`, la que ya devuelve el FF11D) y si no la de creacion de la casa
    (`creada`, guardada la primera vez que entra). INVENTADO que esa sea la fecha: el oficial no se sabe (ficha 128)."""
    f = int(c.get("fecha_intro", 0))
    if f or not llave("CASA_FECHA"):
        return f
    f = int(c.get("fecha_mod", 0))
    if not f and c.get("creada"):
        f = empaquetar_fecha(int(c["creada"]))
    return f


def bloque_268(c):
    """El bloque de informacion de la casa (268 B), forma LEIDA (ver el encabezado)."""
    intro = textos.codificar(c.get("intro") or "", 255)
    b = bytearray(LARGO_BLOQUE)
    b[0] = 1 if c.get("publica", 1) else 0
    struct.pack_into("<I", b, 4, fecha_de(c) & 0xFFFFFFFF)
    b[8:8 + len(intro)] = intro
    return bytes(b)


def ff11b(c):
    """Inventario de la casa: sin objetos ni guardados (n1 = n2 = 0). El texto inicial va vacio: el manejador `0x027eec80` lo lee y no
    lo usa; con el apodo adentro el dialogo 小窝信息 seguia mostrando el nombre en blanco (medido, variante 6)."""
    objs = c.get("objetos", []) if muebles() else []
    return (bytes([0]) + struct.pack("<i", len(objs)) + bloque_268(c) + b"".join(reg_bytes(o) for o in objs)
            + struct.pack("<i", 0))


def ff233(res, nick):
    nb = textos.codificar(nick, 12)
    return bytes([res, len(nb)]) + nb + bytes([0])


def ff61(a, slot, tipo, u32=0):
    """S2C FF61 [u16 A][u8 slot][u8 tipo][u32]. El u32 (LEIDO ficha 107: lo guarda 0x0278a7e6 en cRoom+0x1bbd8) habilita 装扮 si es igual al id propio."""
    return struct.pack("<HBBI", a & 0xFFFF, slot, tipo, u32 & 0xFFFFFFFF)


def _nick_usn(con):
    c = con.cuenta or {}
    return c.get("usn"), c.get("nick") or ""


def _a_casa(usn):
    """A = (tipo<<11)|numero; el numero de la casa propia = el usn en 11 bits (INVENTADO: solo debe ser estable)."""
    return (TIPO_CASA << 11) | (int(usn) & 0x7FF)


# ---------------------------------------------------------------- muebles (ficha 103; llave CASA_MUEBLES)
# Registro de 44 B (LEIDO, docs/tablero/layouts/FF11B.md "Lectura de la ficha 103" s.3):
#   +0 clave u32 · +4 Index u32 · +8 u32 (sin uso hallado) · +0xc estado u8 ('X' guardado / '0'+giro colocado) · +0xd u8 ·
#   +0x10/14/18 x,y,z (u32 tal cual, signo-magnitud: NO se reinterpreta) · +0x1c vencimiento · +0x20 u32 (basura del cliente: se manda 0) ·
#   +0x24 enganche u8 · +0x28 clave del padre u32.
REG = struct.Struct("<3I2B2x5IB3xI")          # 44 B: clave, index, b8, estado, bd, x, y, z, venc, b20, enganche, padre
ESTADO_GUARDADO = 0x58                          # 'X'
# Muebles de la siembra (INVENTADO que una casa nueva los traiga). Elegidos de myroomshop.xml: ShopIndex 2204 (muebles), a la venta
# (sin Show=0), con Width/Height/Depth, PI = 100 (el precio mas bajo de los que se ven en la tienda) y los Index mas chicos: 3300001
# (2x2x2), 3300011 (2x4x2) y 3300028 (2x2x2): comunes y chicos (caben en el cuarto de 30 x 24 x 22).
SIEMBRA = (3300001, 3300011, 3300028)


def muebles():
    return llave("CASA_MUEBLES")


def empaquetar_fecha(t=None):
    """Fecha empaquetada de 小窝信息 (LEIDO 0x008d3645 / 0x00a67340): anio 12 bits, mes 4 bits <<12, dia 5 bits <<16."""
    tm = time.localtime(time.time() if t is None else t)
    return (tm.tm_year & 0xFFF) | (tm.tm_mon << 12) | (tm.tm_mday << 16)


def reg_bytes(o):
    return REG.pack(o["clave"] & 0xFFFFFFFF, o["index"] & 0xFFFFFFFF, o.get("b8", 0) & 0xFFFFFFFF, o["estado"] & 0xFF,
                    o.get("bd", 0) & 0xFF, o.get("x", 0) & 0xFFFFFFFF, o.get("y", 0) & 0xFFFFFFFF, o.get("z", 0) & 0xFFFFFFFF,
                    o.get("venc", 0) & 0xFFFFFFFF, 0, o.get("enganche", 0) & 0xFF, o.get("padre", 0) & 0xFFFFFFFF)


def reg_dict(b):
    clave, index, b8, estado, bd, x, y, z, venc, _b20, enganche, padre = REG.unpack(b)
    return {"clave": clave, "index": index, "b8": b8, "estado": estado, "bd": bd, "x": x, "y": y, "z": z, "venc": venc,
            "enganche": enganche, "padre": padre}


def sembrar(usn):
    """Casa que nunca se sembro: 3 muebles GUARDADOS ('X') si no tiene ninguno. INVENTADO (`sembrada` / `inventado`). True si sembro."""
    def f(c):
        if c.get("sembrada"):
            return False
        c["sembrada"] = True
        c["inventado"] = True
        if not c.get("objetos"):
            c["objetos"] = [{"clave": i + 1, "index": ix, "b8": 0, "estado": ESTADO_GUARDADO, "bd": 0, "x": 0, "y": 0, "z": 0,
                             "venc": 0, "enganche": 0, "padre": 0} for i, ix in enumerate(SIEMBRA)]
            c["sig_clave"] = len(SIEMBRA) + 1
        return True
    return _cta.cambiar_seccion(usn, "casa", f)


def guardar_registros(usn, regs):
    """Upsert por clave de lo que manda el cliente (FF11D): estado, x, y, z, padre, enganche, b8, bd TAL CUAL. Una clave que no existe
    (o con otro Index) se ignora: no se inventan muebles desde la red. Devuelve (registros aplicados con lo que quedo, fecha)."""
    def f(c):
        por = {o["clave"]: o for o in c.get("objetos", [])}
        ok = []
        for r in regs:
            o = por.get(r["clave"])
            if o is None or o["index"] != r["index"]:
                continue
            for k in ("estado", "x", "y", "z", "padre", "enganche", "b8", "bd"):
                o[k] = r[k]
            ok.append(dict(o))
        if ok:
            c["fecha_mod"] = empaquetar_fecha()
        return ok, c.get("fecha_mod", 0)
    return _cta.cambiar_seccion(usn, "casa", f)


# ---------------------------------------------------------------- manejadores
def otro_destino(con, seq, cuerpo, _cmd=None):
    """Solo OBSERVA (devuelve False, el pedido sigue su camino): anota que esta conexion pidio otro destino (ver VENTANA_OTRO)."""
    con.casa_n_otro = getattr(con, "casa_n_otro", 0) + 1
    con.casa_t_otro = time.time()
    return False


def _observador(cmd):
    def f(con, seq, cuerpo):
        if cmd == 0x26F and b"gardenSys" not in cuerpo:          # el FF26F tambien lleva modAct.getActList y otros del lobby
            return False
        return otro_destino(con, seq, cuerpo)
    return f


def _refuerzo_toque(con, marca, n_otro, cmd, cuerpo):
    """Se dispara con un Timer: manda el refuerzo SOLO si la conexion sigue como en el toque (misma marca, sin casa, sin sala, sin cuarto, sin
    boda). Si el cliente ya pidio su FF0F (entrar_f puso `con.casa`) no se manda nada: mandarselo a quien ya entro lo hace salir (ficha 124)."""
    if getattr(con, "casa_marca", None) != marca or getattr(con, "casa", None) is not None:
        return
    if getattr(con, "casa_n_otro", 0) != n_otro:                     # llego un pedido de otro destino (granja, jardin...): no era Mi Casa
        anotar("   refuerzo del 1.er toque ANULADO: la conexion pidio otro destino despues del FF181")
        return
    if con.sala is not None:
        return
    if any(getattr(con, a, None) is not None for a in ("magica", "cuarto", "salon_boda")):
        return
    try:
        con.mandar_interno(cmd, 0, cuerpo)
        anotar("   REFUERZO del 1.er toque a %s: S2C FF%X %s" % (_nick_usn(con)[1], cmd, cuerpo.hex() or "vacio"))
    except Exception as e:                                                   # noqa: BLE001
        anotar("   ⛔ refuerzo del 1.er toque, FF%X: %r" % (cmd, e))


def _armar_refuerzo(con):
    """Tras un FF181 de una conexion que no esta en sala ni en casa: si en DEMORA_VER_FF0F s no llega el FF0F, el cliente esta en el pendiente
    del 1.er toque (canal logico 2 -> SetChannel(5) deja `[cMultiplay+0x211e] = 1` y vuelve sin FF0F) y se manda FF7 [00] + FF169 [0x03DA][0xA].
    Guardas: una vez cada UNA_VEZ_CADA s por conexion, nunca en los VENTANA_FF14 s despues de un FF14, nunca si ya entro a un lugar 5..0xC por
    la casa propia (`con.canal5`: el canal ya es 5 y el cliente pide su FF0F solo)."""
    import threading
    ahora = time.time()
    if getattr(con, "canal5", False) or getattr(con, "casa", None) is not None:
        return
    if getattr(con, "magica", None) is not None or getattr(con, "cuarto", None) is not None or getattr(con, "salon_boda", None) is not None:
        return
    if ahora - getattr(con, "casa_t14", 0.0) < VENTANA_FF14 or ahora - getattr(con, "casa_t_refuerzo", 0.0) < UNA_VEZ_CADA:
        return
    if ahora - getattr(con, "casa_t_otro", 0.0) < VENTANA_OTRO:       # viene de cerrar la granja (FF150 antes del FF181) u otro destino
        return
    n_otro = getattr(con, "casa_n_otro", 0)
    marca = ahora
    con.casa_marca = marca
    con.casa_t_refuerzo = ahora
    t = DEMORA_VER_FF0F
    if CON_FF7:
        threading.Timer(t, _refuerzo_toque, (con, marca, n_otro, 0x07, b"\x00")).start()
        t += DEMORA_FF169
    threading.Timer(t, _refuerzo_toque, (con, marca, n_otro, 0x169, struct.pack("<HB", 0x03DA, TIPO_CASA))).start()
    anotar("   1.er toque de %s: si no llega el FF0F en %.1f s, FF7 [00]%s + FF169 [0x03DA][0xA] (INVENTADO el orden y los tiempos)" % (
        _nick_usn(con)[1], DEMORA_VER_FF0F, "" if CON_FF7 else " (sin)"))


def salida_181(con, seq, cuerpo):
    """C2S FF181 (SendMiniGameExit, 0 B): lo manda el cliente al tocar 我的小窝 y, dos veces, al salir de la casa. Se contesta con un
    FF181 vacio (sin eso 我的小窝 se queda en el menu). Con la conexion EN una sala de carrera no se toca (las salas no cambian)."""
    if not llave():
        return False
    usn, nick = _nick_usn(con)
    if usn is None or con.sala is not None:
        return False
    con.mandar_interno(0x181, seq, b"")
    anotar("   C2S FF181 (%d B) de %s -> S2C FF181 vacio" % (len(cuerpo), nick))
    if llave("CASA_PRIMER_TOQUE"):
        _armar_refuerzo(con)
    return True


def chequear_233(con, seq, cuerpo):
    """C2S FF233 [u8 L][apodo]: la casa propia sale bien; la de otro, con el cartel leido (sin permiso)."""
    if not llave():
        return False
    usn, nick = _nick_usn(con)
    if usn is None or len(cuerpo) < 1 or 1 + cuerpo[0] > len(cuerpo):
        return False
    pedido = textos.decodificar(cuerpo[1:1 + cuerpo[0]])
    if pedido == nick:
        con.mandar_interno(0x233, seq, ff233(RES_OK, nick))
        anotar("   S2C FF233 res 0 (casa propia de %s)" % nick)
    elif visitar():
        usn_d, nick_d = _por_nick(pedido)
        if usn_d is None:
            con.mandar_interno(0x233, seq, ff233(RES_NO_EXISTE, pedido))
            anotar("   S2C FF233 res %d: no existe %r (cartel 0x39f)" % (RES_NO_EXISTE, pedido))
        elif not int((_cta.leer_seccion(usn_d, "casa") or {}).get("publica", 1)):
            con.mandar_interno(0x233, seq, ff233(RES_SIN_LLAVE, nick_d))
            anotar("   S2C FF233 res %d: la casa de %s no es publica (cartel 0x93)" % (RES_SIN_LLAVE, nick_d))
        else:
            con.casa_objetivo = (usn_d, nick_d, time.time())
            con.mandar_interno(0x233, seq, ff233(RES_OK, nick_d))
            anotar("   S2C FF233 res 0: %s puede ir a la casa de %s (INVENTADO: sin exigir amistad ni llave)" % (nick, nick_d))
    else:
        con.mandar_interno(0x233, seq, ff233(RES_SIN_PERMISO, pedido))
        anotar("   S2C FF233 res %d: la casa de otro (%r) todavia no se visita (cartel 0x3c2)" % (RES_SIN_PERMISO, pedido))
    return True


def entrar_f(con, seq, cuerpo):
    """C2S FF0F con A de tipo 0xA: entrar a la casa propia. Otros tipos: no se toca (salas.py)."""
    if not llave() or len(cuerpo) < 2:
        return False
    usn, nick = _nick_usn(con)
    if usn is None:
        return False
    a = struct.unpack_from("<H", cuerpo, 0)[0]
    if a >> 11 != TIPO_CASA:
        return False
    anotar("   C2S FF0F de %s: A=0x%04X u32=%d (%d B%s)" % (nick, a, struct.unpack_from("<I", cuerpo, 2)[0] if len(cuerpo) >= 6 else -1, len(cuerpo),
                                                       ": " + cuerpo.hex() if len(cuerpo) != 6 else ""))
    dueno = _dueno_de_la_visita(con, cuerpo, usn, nick) if visitar() else None
    if dueno is not None:
        return _entrar_visita(con, seq, dueno)
    import salas
    salas.sacar_de_su_sala(con)
    _dejar_casa_ajena(con)
    c = estado_de(usn)
    if muebles() and sembrar(usn):
        anotar("   casa de %s: sembrados %d muebles guardados (INVENTADO: %s)" % (nick, len(SIEMBRA), list(SIEMBRA)))
        c = estado_de(usn)
    n = contar_entrada(usn)
    propia = _a_casa(usn)
    con.casa = propia
    con.canal5 = True                 # el FF0F de un lugar 5..0xC deja el canal logico del cliente en 5 (LEIDO 0x0278a14a): no hace falta reforzar
    con.mandar_interno(0x0F, seq, bytes([0, TIPO_CASA, 0, 0]))
    con.mandar_interno(0x61, seq, ff61(propia, 0, TIPO_CASA, usn))
    con.mandar_interno(0x120, seq, ff120(usn))
    con.mandar_interno(0x11B, seq, ff11b(c))
    if visitar():
        con.casa_dueno, con.casa_slot, con.casa_avisado = usn, 0, False
        _adentro(usn)[0] = con
    anotar("   S2C casa de %s: FF0F + FF61 + FF120 + FF11B con %d muebles (entrada %d; A=0x%04X; INVENTADO publica=1 fecha %s)" % (
        nick, len(c.get("objetos", [])) if muebles() else 0, n, propia, "de hoy" if llave("CASA_FECHA") else 0))
    return True


# ---------------------------------------------------------------- visitar la casa de otro (ficha 128; llave CASA_VISITAR)
# LEIDO (CASA_LECTURA.md §2 y la lectura de la ficha 128): el boton 前往小窝 de la lista de amigos y el BTN_MYROOM de la tarjeta de un jugador
# solo se habilitan para otro si su apodo esta en la lista de LLAVES RECIBIDAS (la 2.a lista del S2C FF120, `0x027f0da0` -> `0x00477250` flag 0
# -> `0x00477500` agrega el apodo a [player+0x11bc]; el que consulta es `0x00477600`). INVENTADO: sin exigir amistad ni llave real, el servidor le
# manda a cada jugador una llave "recibida" de CADA otra cuenta local (hasta MAX_LLAVES), con los tres u32 en 1, 0, 0 (sin saber que son).
MAX_LLAVES = 20
FRESCO_OBJETIVO = 20.0       # s que vale el objetivo de un FF233 res 0 para el FF0F que llega despues
_CASAS = {}                  # {usn del dueño: {asiento: con}} en memoria: los que estan adentro de esa casa (0 = el dueño, 1..5 = visitas)


def visitar():
    return llave("CASA_VISITAR")


def _por_nick(nick):
    """(usn, apodo exacto) de la primera cuenta local con ese apodo, o (None, None)."""
    for k, acc in sorted(_cta.todas().items(), key=lambda kv: int(kv[0])):
        n = (acc.get("cuenta") or {}).get("nick")
        if n and n == nick:
            return int(k), n
    return None, None


def _nick_de(usn):
    return ((_cta.leer(usn) or {}).get("cuenta") or {}).get("nick") or "casa"


def ff120(usn):
    """S2C FF120: sin la llave `[0][0]` (como hasta la ficha 127). Con ella: `[n1 = 0][n2]` y n2 filas `[u32][u32][u32][u8 L][apodo][u8 0]` = llaves
    RECIBIDAS de las demas cuentas locales (ver arriba)."""
    if not visitar():
        return bytes([0, 0])
    filas, n = b"", 0
    for k, acc in sorted(_cta.todas().items(), key=lambda kv: int(kv[0])):
        nb = textos.codificar((acc.get("cuenta") or {}).get("nick") or "", 12)
        if int(k) == int(usn) or not nb:
            continue
        filas += struct.pack("<III", 1, 0, 0) + bytes([len(nb)]) + nb + b"\x00"
        n += 1
        if n >= MAX_LLAVES:
            break
    return bytes([0, n]) + filas


def temprano_120(con, seq, cuerpo):
    """Una vez por conexion, con el 1.er C2S FF137 (la carga del lobby): manda el FF120 con las llaves recibidas para que 前往小窝 y el boton de la
    casa de la tarjeta salgan habilitados desde el lobby. Siempre devuelve False (otro modulo contesta el FF137)."""
    if visitar() and not getattr(con, "casa_120", False) and (con.cuenta or {}).get("usn") is not None:
        con.casa_120 = True
        try:
            con.mandar_interno(0x120, 0, ff120(con.cuenta["usn"]))
            anotar("   S2C FF120 con %d llaves recibidas a %s (INVENTADO)" % (ff120(con.cuenta["usn"])[1], con.cuenta.get("nick")))
        except Exception as e:                                               # noqa: BLE001
            anotar("   ⛔ FF120 temprano: %r" % (e,))
    return False


def _vivo(c):
    return estado.CONEXIONES.get(getattr(c, "puerto", None)) is c


def _adentro(usn_d):
    """Los que estan adentro de la casa de usn_d, {asiento: con}, sin los que ya no estan conectados ni los que se fueron."""
    d = _CASAS.setdefault(usn_d, {})
    for s in [s for s, c in d.items() if not _vivo(c) or getattr(c, "casa_dueno", None) != usn_d or getattr(c, "casa", None) is None]:
        del d[s]
    return d


def _dueno_de_la_visita(con, cuerpo, usn, nick):
    """(usn, apodo) del dueño al que va este FF0F, o None si va a su casa. El apodo sale del final del FF0F `[u8 L][apodo]` si lo trae (asi lo hace
    el cliente 2018; en Steam la propia mide 6 B: LEIDO, y lo que traiga la de otro se mide con el juego) y, si no, del ultimo FF233 res 0 (fresco)."""
    objetivo = None
    if len(cuerpo) > 6 and 7 + cuerpo[6] <= len(cuerpo):
        nick_d = textos.decodificar(cuerpo[7:7 + cuerpo[6]])
        objetivo = _por_nick(nick_d)
    o = getattr(con, "casa_objetivo", None)
    con.casa_objetivo = None
    if objetivo is None and o is not None and time.time() - o[2] <= FRESCO_OBJETIVO:
        objetivo = (o[0], o[1])
    if objetivo is None or objetivo[0] is None or objetivo[0] == usn:
        return None
    return objetivo


def _dejar_casa_ajena(con):
    """Si estaba adentro de una casa (propia o ajena) lo anota afuera y avisa a los que quedan."""
    d = getattr(con, "casa_dueno", None)
    if d is None:
        return
    slot = getattr(con, "casa_slot", None)
    con.casa_dueno = None
    adentro = _adentro(d)
    for s in [s for s, c in adentro.items() if c is con]:
        del adentro[s]
    for otro in list(adentro.values()):
        try:
            otro.mandar_interno(0x0E, 0, bytes([slot if slot is not None else 0]))
            _mandar_ff0c(otro, _sala_de(d, otro), 0)
        except Exception as e:                                               # noqa: BLE001
            anotar("   ⛔ aviso de salida de la casa: %r" % (e,))
    if adentro:
        anotar("   FF0E + FF0C: el asiento %s salio de la casa de %s; quedan %d" % (slot, _nick_de(d), len(adentro)))


def ff11b_visita(c):
    """FF11B de la casa de OTRO para el visitante (HIPOTESIS leida en la 127): solo los muebles COLOCADOS del dueño, n2 = 0."""
    objs = [o for o in c.get("objetos", []) if o["estado"] != ESTADO_GUARDADO] if muebles() else []
    return bytes([0]) + struct.pack("<i", len(objs)) + bloque_268(c) + b"".join(reg_bytes(o) for o in objs) + struct.pack("<i", 0)


def _entrar_visita(con, seq, dueno):
    """FF0F de una visita: S2C FF0F [asiento][0xA][0][0] + FF61 con el usn DEL DUEÑO (el visitante no decora: control causal de la ficha 109) +
    FF120 + FF11B de la casa del dueño con sus muebles colocados."""
    usn_d, nick_d = dueno
    usn, nick = _nick_usn(con)
    import salas
    salas.sacar_de_su_sala(con)
    _dejar_casa_ajena(con)
    adentro = _adentro(usn_d)
    slot = next((s for s in range(1, 6) if s not in adentro), None)
    if slot is None:
        anotar("   la casa de %s esta llena (5 visitas): %s no entra" % (nick_d, nick))
        return True
    c = estado_de(usn_d)
    a = _a_casa(usn_d)
    con.casa, con.casa_dueno, con.casa_slot, con.casa_avisado, con.canal5 = a, usn_d, slot, False, True
    adentro[slot] = con
    con.mandar_interno(0x0F, seq, bytes([slot, TIPO_CASA, 0, 0]))
    con.mandar_interno(0x61, seq, ff61(a, slot, TIPO_CASA, usn_d))
    con.mandar_interno(0x120, seq, ff120(usn))
    con.mandar_interno(0x11B, seq, ff11b_visita(c))
    anotar("   S2C VISITA de %s a la casa de %s: FF0F [asiento %d] + FF61 (u32 = usn del dueno) + FF120 + FF11B con %d muebles colocados (A=0x%04X)" % (
        nick, nick_d, slot, len([o for o in c.get("objetos", []) if o["estado"] != ESTADO_GUARDADO]) if muebles() else 0, a))
    return True


def _es_visita(con):
    """True si esta adentro de la casa de otro (no puede decorar ni comprar ahi)."""
    d = getattr(con, "casa_dueno", None)
    return d is not None and d != (con.cuenta or {}).get("usn")


def _sala_casa(con):
    """Una Sala de datos para armar el FF15 / FF0C con las funciones de salas.py (NO se registra en estado.SALAS: no es una sala)."""
    if visitar() and getattr(con, "casa_dueno", None) is not None:
        return _sala_de(con.casa_dueno, con)
    nick = (con.cuenta or {}).get("nick") or "casa"
    sala = estado.Sala(con.casa & 0x7FF, {"modo": 0, "titulo": textos.codificar(nick, 24), "clave": b""}, con, TIPO_CASA)
    sala.asientos = {0: con}
    sala.orden = (0,)
    sala.max = 1
    return sala


def _sala_de(usn_d, con):
    """La Sala de datos de la casa de usn_d con los que estan adentro (titulo = el apodo del dueño); `con` va en su asiento aunque ya no figure."""
    sala = estado.Sala(_a_casa(usn_d) & 0x7FF, {"modo": 0, "titulo": textos.codificar(_nick_de(usn_d), 24), "clave": b""}, con, TIPO_CASA)
    sala.asientos = dict(_adentro(usn_d))
    sala.orden = tuple(sorted(sala.asientos))
    sala.max = 6
    return sala


def _mandar_ff0c(para, sala, seq):
    """El FF0C para `para`: UN mensaje por jugador, el propio primero (ficha 122: dos jugadores en un mensaje dejan vacio el segundo nodo)."""
    import fichas
    import salas
    jug = sorted(sala.asientos.items())
    jug = [x for x in jug if x[1] is para] + [x for x in jug if x[1] is not para]
    for i, (a, c) in enumerate(jug):
        para.mandar_interno(0x0C, seq if i == 0 else 0, fichas.lista_ff0c([salas.ficha_ff0c(c, a, c is para, salas.equipo_de(sala, c))]))


def _pedido_de_sala(cmd):
    def f(con, seq, cuerpo):
        """C2S FF15 (info de sala) / FF0C (lista de jugadores) estando en la casa: se contestan con las funciones de salas.py sobre una
        Sala de datos. salas.py (la sala de carrera grabada) haria caer al cliente."""
        if getattr(con, "salon_boda", None) is not None:             # ficha 114: el salon de la boda (boda.py)
            import boda
            return boda.pedido_de_sala(con, seq, cmd)
        if not llave() or getattr(con, "casa", None) is None:
            return False
        import salas
        sala = _sala_casa(con)
        if cmd == 0x15:
            base = next((cu for c, _s, cu in salas._plantilla() if c == 0x15), None)
            con.mandar_interno(0x15, seq, salas.ff15_para(base, sala))
        elif visitar() and len(sala.asientos) > 1:
            _mandar_ff0c(con, sala, seq)
            if not getattr(con, "casa_avisado", False):          # al que ya estaba adentro le llega la lista nueva (como el cuarto oscuro)
                con.casa_avisado = True
                for otro in [x for x in sala.asientos.values() if x is not con]:
                    try:
                        _mandar_ff0c(otro, sala, 0)
                    except Exception as e:                                       # noqa: BLE001
                        anotar("   ⛔ FF0C nuevo a un ocupante de la casa: %r" % (e,))
                anotar("   S2C FF0C nuevo a los que ya estaban (ahora %d adentro)" % len(sala.asientos))
        else:
            con.mandar_interno(0x0C, seq, salas.ff0c(sala, con))
        anotar("   S2C FF%X de la casa (titulo = el apodo del dueno)" % cmd)
        return True
    return f


def salir_14(con, seq, cuerpo):
    con.casa_t14 = time.time()          # lo mira _armar_refuerzo: la salida manda FF181, FF14 y otro FF181 a ~2 s
    if getattr(con, "salon_boda", None) is not None:                 # ficha 114: el salon de la boda (boda.py)
        import boda
        return boda.salir_14(con, seq, cuerpo)
    if not llave() or getattr(con, "casa", None) is None:
        return False
    con.casa = None
    con.mandar_interno(0x14, seq, struct.pack("<H", 0))
    anotar("   S2C FF14 0000: sale de la casa")
    _dejar_casa_ajena(con)
    return True


def editar_11d(con, seq, cuerpo):
    """C2S FF11D SendEditMyRoom [u8 n][n x 44B] (tandas de 16): upsert por clave, eco S2C FF11D [u8 n][n x 44B][u32 fecha] y FFDE [1][0]
    (cartel 0x3b8 + rearmar la casa + salir del modo decorar; LEIDO 0x00a1ebd0)."""
    if not muebles() or not llave() or getattr(con, "casa", None) is None:
        return False
    if visitar() and _es_visita(con):
        anotar("   C2S FF11D de una VISITA: no se toca la casa del dueno")
        return True
    usn, nick = _nick_usn(con)
    if usn is None or len(cuerpo) < 1:
        return False
    n = cuerpo[0]
    if len(cuerpo) != 1 + 44 * n:
        anotar("   ⛔ C2S FF11D de %s con largo %d (n=%d): no se toca" % (nick, len(cuerpo), n))
        return False
    regs = [reg_dict(cuerpo[1 + 44 * i:45 + 44 * i]) for i in range(n)]
    ok, fecha = guardar_registros(usn, regs)
    con.mandar_interno(0x11D, seq, bytes([len(ok)]) + b"".join(reg_bytes(o) for o in ok) + struct.pack("<I", fecha))
    con.mandar_interno(0xDE, seq, bytes([1, 0]))
    anotar("   C2S FF11D de %s: %d registros (%d aplicados) -> S2C FF11D + FFDE [1][0]; %s" % (
        nick, n, len(ok), "; ".join("clave %d estado %s x/y/z %d/%d/%d padre %d" % (
            r["clave"], chr(r["estado"]) if 32 <= r["estado"] < 127 else r["estado"], r["x"], r["y"], r["z"], r["padre"])
            for r in regs)))
    return True


def confirmar_sin_cambios(con, seq, cuerpo):
    """C2S FFF5 vacio (confirmar el modo decorar sin cambios): S2C FFF5 [0] (n = 0)."""
    if not muebles() or not llave() or getattr(con, "casa", None) is None or cuerpo:
        return False
    if visitar() and _es_visita(con):
        return True
    con.mandar_interno(0xF5, seq, bytes([0]))
    anotar("   C2S FFF5 vacio de %s en la casa -> S2C FFF5 [0]" % (_nick_usn(con)[1],))
    return True


def lista_de_casas(con, seq, cuerpo):
    """C2S FF65 SendRequestChatRoomList (1 B, el boton 选择 de la casa): S2C FF65 [u16 0] (LEIDO: el camino sin entradas)."""
    if not muebles() or not llave() or getattr(con, "casa", None) is None:
        return False
    con.mandar_interno(0x65, seq, struct.pack("<H", 0))
    anotar("   C2S FF65 (%d B) en la casa -> S2C FF65 [u16 0]" % len(cuerpo))
    return True


# ---------------------------------------------------------------- comprar muebles (ficha 103; llave CASA_COMPRA, ademas de CASA_MUEBLES)
# C2S FF11E [u32 articulo][u32 b][u8 L][apodo L B][u8 flag] (LEIDO 0x027f15e0). S2C FF11E [u8 r] y con r = 0: [44B nuevo][u32 saldo]
# (LEIDO 0x027f1b40: el cliente guarda el u32 `^ 0x2efd` en [player+0x968] = G; FF51 refresca los diamantes). r: 0 ok, 4 saldo, 6 jugador,
# 7 no se pudo leer el item (carteles 0x3b3 / 0x2ab / 0x39f / 0x3a0).
PLAZO_PERMANENTE = 9
RES_COMPRA_OK, RES_COMPRA_SIN_SALDO, RES_COMPRA_JUGADOR, RES_COMPRA_ITEM = 0, 4, 6, 7
_TABLA = {}


def tabla_muebles():
    """{Index (str): {s, cash, show, pi, p30, p7}} de datos/casa_tablas.json (herramientas/preparar_casa.py). {} si falta."""
    if not _TABLA:
        import json
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "casa_tablas.json")
        try:
            _TABLA.update(json.load(open(ruta, encoding="utf-8")).get("muebles", {}))
        except (OSError, ValueError):
            pass
    return _TABLA


def compra_activa():
    return muebles() and llave("CASA_COMPRA") and bool(tabla_muebles())


def _r_compra(con, seq, r, extra=b""):
    con.mandar_interno(0x11E, seq, bytes([r]) + extra)


def comprar_11e(con, seq, cuerpo):
    """C2S FF11E: comprar un mueble en la tienda de la casa. Se VALIDA todo antes de cobrar; se cobra con el candado de tienda.py
    (diamantes si la fila trae Cash=1, G si no; precio = PI, INVENTADO que `b` no cambie el precio: se anota); el mueble nuevo entra
    GUARDADO ('X') con clave nueva (sin limite de copias: la tabla no dice lo contrario). Si guardar falla se devuelve lo cobrado."""
    if not compra_activa() or not llave() or getattr(con, "casa", None) is None:
        return False
    if visitar() and _es_visita(con):
        anotar("   C2S FF11E de una VISITA: no se compra para la casa del dueno (sin respuesta)")
        return True
    usn, nick = _nick_usn(con)
    if usn is None or len(cuerpo) < 9 or 9 + cuerpo[8] > len(cuerpo):
        return False
    art, b = struct.unpack_from("<II", cuerpo, 0)
    ap = textos.decodificar(cuerpo[9:9 + cuerpo[8]])
    flag = cuerpo[9 + cuerpo[8]] if len(cuerpo) > 9 + cuerpo[8] else 0
    # MEDIDO con el juego (12-nov): el cliente manda articulo = Index + 1000 * codigo de plazo (3300001 -> 3309001); 9 = permanente (PI).
    # Ningun Index de la tabla tiene distinto de 0 el digito de los miles (1775 de 1775), asi que se separa sin ambiguedad. Los codigos de
    # P30 / P7: sin medir (se rechazan con r = 7).
    plazo = (art // 1000) % 10
    index = art - plazo * 1000
    fila = tabla_muebles().get(str(index)) if plazo == PLAZO_PERMANENTE else None
    anotar("   C2S FF11E de %s: articulo %d b=%d apodo=%r flag=0x%02X (%d B)" % (nick, art, b, ap, flag, len(cuerpo)))
    if fila is None or not fila.get("show") or "pi" not in fila:
        _r_compra(con, seq, RES_COMPRA_ITEM)
        anotar("   S2C FF11E r=%d: el articulo %d no esta a la venta" % (RES_COMPRA_ITEM, art))
        return True
    if ap != nick:
        _r_compra(con, seq, RES_COMPRA_JUGADOR)
        anotar("   S2C FF11E r=%d: regalo a %r (todavia no)" % (RES_COMPRA_JUGADOR, ap))
        return True
    import tienda
    campo = "diamantes" if fila["cash"] else "g"
    precio = int(fila["pi"])

    def cobrar(bolsa):
        if bolsa.get(campo, 0) < precio:
            return None
        bolsa[campo] = bolsa.get(campo, 0) - precio
        return dict(bolsa)
    quedan = tienda._con_bolsa(con, cobrar)
    if quedan is None:
        _r_compra(con, seq, RES_COMPRA_SIN_SALDO)
        anotar("   S2C FF11E r=%d: %s insuficiente para %d" % (RES_COMPRA_SIN_SALDO, campo, precio))
        return True

    def agregar(c):
        n = int(c.get("sig_clave") or (max([o["clave"] for o in c.get("objetos", [])] or [0]) + 1))
        o = {"clave": n, "index": index, "b8": 0, "estado": ESTADO_GUARDADO, "bd": 0, "x": 0, "y": 0, "z": 0, "venc": 0,
             "enganche": 0, "padre": 0}
        c.setdefault("objetos", []).append(o)
        c["sig_clave"] = n + 1
        c["inventado"] = True
        return dict(o)
    try:
        o = _cta.cambiar_seccion(usn, "casa", agregar)
    except BaseException:
        tienda._con_bolsa(con, lambda bolsa: bolsa.__setitem__(campo, bolsa.get(campo, 0) + precio))
        raise
    _r_compra(con, seq, RES_COMPRA_OK, reg_bytes(o) + struct.pack("<I", int(quedan.get("g", 0)) & 0xFFFFFFFF))
    if campo == "diamantes":
        tienda.refrescar_saldos(con, diamantes=True)         # ficha 131: el FF11E lleva el G nuevo pero no los diamantes (LEIDO: 0x027f1b40 solo escribe [C+0x968])
    anotar("   S2C FF11E r=0: %s compro %d (articulo %d, clave %d) por %d %s; quedan %d %s" % (nick, index, art, o["clave"], precio, campo, quedan.get(campo, 0), campo))
    return True


MANEJADORES = {
    0x137: temprano_120,
    0x181: salida_181,
    0x233: chequear_233,
    0x0F: entrar_f,
    0x14: salir_14,
    0x15: _pedido_de_sala(0x15),
    0x0C: _pedido_de_sala(0x0C),
    0x11D: editar_11d,
    0xF5: confirmar_sin_cambios,
    0x65: lista_de_casas,
    0x11E: comprar_11e,
}
for _c in DESTINOS_OTROS:
    MANEJADORES.setdefault(_c, _observador(_c))
