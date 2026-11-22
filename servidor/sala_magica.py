# -*- coding: utf-8 -*-
r"""sala_magica.py (12-nov, ficha 96) — la sala magica (小黑屋, "cita a ciegas") de las cuentas LOCALES: anotarse en la cola, cancelar, y
cuando hay DOS anotados juntarlos en una sala de carrera comun. Layouts LEIDOS del exe: docs/tablero/layouts/FF167.md, FF169.md,
FF16A.md, FF16F.md (secciones "Lectura de la ficha 96") y el Informe de la ficha 96 (lo MEDIDO con el juego).

  C2S FF167 SendMagicRoomRegister [u32 id][u8 modo]    modo 1 = anotarse, 0 = cancelar (LEIDO 0x028045e0; el boton lo manda: MEDIDO 12-nov)
  S2C FF167 CmdMagicRoomRegister  [u8 res][u32 t]      res != 0 alterna "en cola"; t == 0 arranca el cronometro del cartel de buscar (LEIDO)
                                                       anotarse = [01][00000000] ; cancelar = [01][01]
  S2C FF169 CmdMagicRoomMatchRoom [u16 n][u8 tipo]     "ir al lugar (tipo<<11)+n" (LEIDO 0x02804a70 -> 0x00a361e0)

  S2C FF7  CmdJoinChannel [u8 res]                     res 0 = "canal confirmado": el cliente que esperaba el canal sigue (MEDIDO)

SECUENCIA MEDIDA con el juego (copias 2 y 3, 12-nov): FF169 [n][0xb] a los dos -> (0.5 s) S2C FF7 [00] -> (4 s) FF169 otra vez -> los dos
mandan C2S FF0F A=0x5BDB (el A fijo del tipo 0xb, LEIDO 0x008c21c5) -> salas.sentar_y_avisar: los dos quedan en la misma sala de carrera.
Con UN solo FF169 el cliente deja "ir al lugar 0xb" pendiente (cMultiplay+0x211e = 1) y no manda nada.

INVENTADO (marcado): el emparejamiento es POR ORDEN DE LLEGADA (el oficial quiza juntaba por sexo; no se sabe); la sala de los dos es
una Sala de carrera individual normal (modo 0xA, titulo "magica") hecha con salas.nueva_sala, y el FF0F se contesta como cualquier
sala (tipo de lugar 0, no 0xb); los tiempos 0.5 s / 4 s; los campos no leidos de FF16A/FF16F no se mandan. NO hecho: el cuarto oscuro
(FF16A, FF16F), el "jugamos juntos?" (FF170) y los premios.
FICHA 121 (12-nov): llave SALA_MAGICA_CUARTO (omision 1): con 1 los dos emparejados entran al CUARTO OSCURO (lugar de tipo 0xB: FF0F + FF61 propios,
FF15 / FF0C de una Sala de datos, FF16A sub 0, lampara FF16F, relevo del chat FF170, salir con FF14) en vez de la sala de carrera comun. Ver el Informe de la
ficha 121 y docs/tablero/SALA_MAGICA_LECTURA.md ("Medido con el juego, ficha 121"). Con 0 todo queda como en la ficha 96.
FICHA 130 (13-nov): llave SALA_MAGICA_JUGAR (omision 1; solo con el cuarto): "jugamos juntos" (开始游戏). El FF170 WITHGAME / WITHGAME_YES / WITHGAME_NO ya se releva (ficha 121).
Tras el SI el cliente del que toco el boton abre el dialogo de crear sala (赛场创建) y al apretar 创建 manda C2S FF170 CREATEROOM + C2S FF14 pegados (MEDIDO), pero NO manda
el FF1F5 (crear sala) solo (MEDIDO: queda en el lobby con cRoom+0x77a1 = 2; un S2C FF7 [00] solo recarga el lobby). Entonces el SERVIDOR crea la sala por el (INVENTADO: modo
individual 0x0A, titulo 'magica', canal 0: lo que se eligio en el dialogo no llega al servidor) y se la manda con salas.mandar_sala (el cliente la acepta y queda de anfitrion:
MEDIDO), y al otro le manda la invitacion S2C FF52 [01][A][0][0] (la de social.invitar): dentro del cuarto no se ve (MEDIDO), asi que se repite cuando sale al lobby (a los ~25 s,
cuenta del cliente tras el CREATEROOM: cartel "el otro esta creando la sala"); su 确认 manda FF0F A=n y entra por salas.unirse. Con 0: CREATEROOM se releva y el FF14 se contesta
como siempre (bytes de hoy; el creador queda en el lobby sin sala).
Solo cuentas LOCALES. Llave por entorno SALA_MAGICA (omision en LLAVES_OMISION; =0 y todo queda como antes: el FF167 sigue sin contestar
con logica propia y el FF0F sigue siendo de salas.py).
"""
import os
import struct
import time

import estado

LLAVES_OMISION = {"SALA_MAGICA": "1", "SALA_MAGICA_CUARTO": "1", "SALA_MAGICA_JUGAR": "1"}      # SALA_MAGICA 1 desde que dos copias terminaron juntas y salieron 3 veces sin trabarse (ficha 96); SALA_MAGICA_CUARTO 1 desde que, con el juego, los dos entraron al cuarto, se vieron y salieron 3 de 3 veces con el codigo final (ficha 121); SALA_MAGICA_JUGAR 1 desde que, con el juego, 2 de 2 veces los dos terminaron en la misma sala de carrera tras el SI de 开始游戏 y corrieron una carrera hasta el cartel de resultados (ficha 130)
TIPO_MAGICA = 0xB            # [cRoom+0x5d74]^0xFD == 0xB: el lugar "cuarto" (LEIDO 0x00a5.. / 0x007b3e80)
A_FIJO = 0x5BDB              # el A que arma el cliente para el tipo 0xB (LEIDO 0x008c21c5: tipo*0x801+0x3d0)
DEMORA_FF7 = 0.5            # s despues del 1.o FF169 (MEDIDO: con 0.5 / 6 s anduvo; ver el Informe de la ficha 96)
DEMORA_FF169 = 4.0
VENTANA_FF167 = 20.0         # s: el FF167 [id][0] automatico del cuarto llega ~3 s despues del FF0F (MEDIDO); mas tarde = cancelar desde el lobby
VENCE = 120                 # s: una sala armada a la que no entro nadie se borra


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="SALA_MAGICA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def cola():
    if not hasattr(estado, "COLA_MAGICA"):
        estado.COLA_MAGICA = []          # conexiones anotadas, en orden de llegada
    return estado.COLA_MAGICA


def pendientes():
    if not hasattr(estado, "PAREJAS_MAGICAS"):
        estado.PAREJAS_MAGICAS = {}      # numero de sala -> hora en que se armo (todavia sin entrar)
    return estado.PAREJAS_MAGICAS


def _nick(con):
    return (con.cuenta or {}).get("nick")


def ff167(res, t):
    return struct.pack("<BI", res, t)


def _limpiar():
    ahora = time.time()
    for n, h in list(pendientes().items()):
        s = estado.SALAS.get(n)
        if s is None:
            del pendientes()[n]
        elif s.asientos:
            del pendientes()[n]          # ya entro alguien: es una sala normal
        elif ahora - h > VENCE:
            del estado.SALAS[n]
            estado.CERRADAS[n] = ahora
            del pendientes()[n]
            anotar("   sala magica %d borrada: no entro nadie en %d s" % (n, VENCE))


def _mandar(conexiones, cmd, cuerpo):
    for c in conexiones:
        try:
            c.mandar_interno(cmd, 0, cuerpo)
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ sala magica, FF%X a %s: %r" % (cmd, _nick(c), e))


def _refuerzo(n, par, cmd, cuerpo):
    """FICHA 124: el FF7 [00] y el 2.o FF169 solo a los que TODAVIA no pidieron su FF0F del cuarto n (con.magica sigue en n)."""
    _mandar([c for c in par if getattr(c, "magica", None) == n], cmd, cuerpo)


def _armar(a, b):
    """La sala de los dos (vacia: entran con su FF0F) y la secuencia MEDIDA con el juego (ficha 96, variante 5):
    FF169 [n][0xb] -> el cliente deja pendiente "ir al lugar 0xb" y espera la confirmacion del canal; S2C FF7 [00] (CmdJoinChannel
    resultado 0) -> el cliente vuelve a pedir lo de entrada al lobby (FF49/FF40/FF97/FF4A, ya contestados por otros modulos);
    un SEGUNDO FF169 -> el cliente manda C2S FF0F con A = 0x5bdb. Con un solo FF169 el cliente queda con el pendiente y no manda nada."""
    import threading

    import salas
    if cuarto_activo():
        n = _numero_cuarto()
        cuartos()[n] = {"cons": [a, b], "hora": time.time()}
        for c in (a, b):
            c.magica = n
        ff169 = struct.pack("<HB", n & 0xFFFF, TIPO_MAGICA)
        _mandar((a, b), 0x169, ff169)
        # FICHA 124: FF7 y 2.o FF169 solo al que todavia no pidio su FF0F (MEDIDO: con el canal logico ya en 5 el cliente contesta el 1.er FF169 de inmediato y el FF7 / 2.o FF169 lo hacian salir)
        threading.Timer(DEMORA_FF7, _refuerzo, (n, (a, b), 0x07, b"\x00")).start()
        threading.Timer(DEMORA_FF169, _refuerzo, (n, (a, b), 0x169, ff169)).start()
        anotar("   S2C FF169 [n=%d][tipo 0x%x] a %s y %s (+FF7 00 y FF169 otra vez): CUARTO %d armado (INVENTADO: por orden de llegada)" % (
            n, TIPO_MAGICA, _nick(a), _nick(b), n))
        return
    n = salas.numero_libre()
    pedido = {"modo": 0x0A, "titulo": b"magica", "clave": b"", "bandera": 0, "u8": 2, "textos": [b"", b""]}
    sala = salas.nueva_sala(n, pedido, None, 2)
    sala.asientos = {}
    sala.anfitrion = None
    estado.SALAS[n] = sala
    pendientes()[n] = time.time()
    par = (a, b)
    for c in par:
        c.magica = n
    ff169 = struct.pack("<HB", n & 0xFFFF, TIPO_MAGICA)
    _mandar(par, 0x169, ff169)
    threading.Timer(DEMORA_FF7, _mandar, (par, 0x07, b"\x00")).start()
    threading.Timer(DEMORA_FF169, _mandar, (par, 0x169, ff169)).start()
    anotar("   S2C FF169 [n=%d][tipo 0x%x] a %s y %s (+FF7 00 a los %.1f s y FF169 otra vez a los %.1f s): sala %d armada "
           "(INVENTADO: por orden de llegada)" % (n, TIPO_MAGICA, _nick(a), _nick(b), DEMORA_FF7, DEMORA_FF169, n))


def registrar_167(con, seq, cuerpo):
    """C2S FF167 [u32 id][u8 modo]."""
    if not llave() or con.cuenta is None or len(cuerpo) != 5:
        return False
    _limpiar()
    modo = cuerpo[4]
    q = cola()
    if modo == 0 and cuarto_activo() and getattr(con, "cuarto", None) is not None and time.time() - getattr(con, "cuarto_hora", 0) > VENTANA_FF167:
        # FICHA 124: el FF167 [id][0] automatico llega ~3 s despues del FF0F; uno MUCHO mas tarde es el cliente en el lobby cancelando la cola
        # (el cuarto quedo "abierto" porque ese cliente salio sin mandar FF14): se limpia y se trata como cancelar.
        anotar("   C2S FF167 modo 0 de %s tarde (cuarto %s viejo): se limpia" % (_nick(con), con.cuarto))
        salio_del_cuarto(con)
    if modo == 0 and cuarto_activo() and getattr(con, "cuarto", None) is not None:
        # el cliente lo manda solo al armar el cuarto (LEIDO 0x00a71df0): [00][0] no toca la bandera de cola (HIPOTESIS: lo del oficial, 27 de 27)
        con.mandar_interno(0x167, seq, ff167(0, 0))
        anotar("   C2S FF167 modo 0 de %s ESTANDO en el cuarto %s -> S2C FF167 [00][0]" % (_nick(con), con.cuarto))
        return True
    if modo == 1:
        if getattr(con, "cuarto", None) is not None or getattr(con, "magica", None) is not None:
            salio_del_cuarto(con)        # FICHA 124: anotarse de nuevo = esta en el lobby; limpia lo que quedo de un cuarto sin FF14
        if con.sala is not None:
            import salas
            salas.sacar_de_su_sala(con)
        if con not in q:
            q.append(con)
        con.mandar_interno(0x167, seq, ff167(1, 0))
        anotar("   C2S FF167 modo 1 de %s: anotado (%d en la cola) -> S2C FF167 [01][0]" % (_nick(con), len(q)))
        if len(q) >= 2:
            a, b = q[0], q[1]
            del q[:2]
            _armar(a, b)
    else:
        if con in q:
            q.remove(con)
        con.mandar_interno(0x167, seq, ff167(1, 1))
        anotar("   C2S FF167 modo %d de %s: fuera de la cola -> S2C FF167 [01][01]" % (modo, _nick(con)))
    return True


def entrar_f(con, seq, cuerpo):
    """C2S FF0F [u16 A][u32]: el que fue emparejado entra a la sala de la pareja (A de tipo 0xB, o el que se mando en el FF169)."""
    if not llave() or con.cuenta is None or len(cuerpo) < 2 or getattr(con, "magica", None) is None:
        return False
    if cuarto_activo() and con.magica in cuartos():
        return entrar_cuarto(con, seq, cuerpo)
    a = struct.unpack_from("<H", cuerpo, 0)[0]
    n = con.magica
    sala = estado.SALAS.get(n)
    if sala is None:
        con.magica = None
        return False
    tipo = TIPO_MAGICA
    if a >> 11 != tipo and a != A_FIJO:
        return False
    import salas
    con.magica = None
    pendientes().pop(n, None)
    if not sala.asientos:
        sala.anfitrion = con
    anotar("   C2S FF0F A=0x%04X de %s: entra a la sala magica %d" % (a, _nick(con), n))
    return salas.sentar_y_avisar(con, sala, seq)


def desconectado(con):
    q = cola()
    if con in q:
        q.remove(con)
        anotar("   %s se desconecto: sale de la cola de la sala magica" % _nick(con))
    con.cuarto_muerto = True             # FICHA 130: los temporizadores de "jugamos juntos" no le mandan nada a una conexion caida
    if getattr(con, "cuarto", None) is not None or getattr(con, "magica", None) in cuartos():
        salio_del_cuarto(con, desconexion=True)
    con.magica = None
    _limpiar()


# ======================================================================== el CUARTO OSCURO (ficha 121; llave SALA_MAGICA_CUARTO)
# Con la llave en 1 los dos emparejados NO van a una sala de carrera: van a un LUGAR de tipo 0xB (LEIDO / MEDIDO, SALA_MAGICA_LECTURA.md).
# MEDIDO con 2 copias (12-nov, ficha 121): tras el FF0F A=0x5BDB el cliente pide FF15, y ~2 s despues manda C2S FF167 [id][0] y C2S FF0C;
# el cuarto se arma (tipo 0xb, estado de escena 7, menu en modo 6), cuenta 30 s ("30秒后可以看到对方"), muestra 开灯; con el C2S FF16F y el
# S2C FF16F [1] se enciende (la barra de abajo trae 开始游戏 / 示好 = BTN_ADDCOUPLE_M / 添加好友 / 添加挚友 / 我的物品); salir = BTN_BACK
# (C2S FF170 CANCLE, FF181, FF14 0000, FF181) y el otro recibe el CANCLE relevado (cuenta 5 s y sale solo).
ASIENTOS = (1, 3)      # MEDIDO (12-nov, 8 corridas): con asientos 0/1, 1/2 o 2/3 el que tiene asiento PAR no dibuja al otro (ni el retrato); con 1 y 3 los dos se ven
                       # (HIPOTESIS: algo del cliente mira el bit bajo del asiento; no leido). El FF61 lleva este asiento (es el "propio" del cliente).


def cuarto_activo():
    return llave() and llave("SALA_MAGICA_CUARTO")


def cuartos():
    if not hasattr(estado, "CUARTOS_MAGICOS"):
        estado.CUARTOS_MAGICOS = {}      # numero -> {"cons": [a, b] (asiento ASIENTOS[0] y ASIENTOS[1]), "hora", "lampara": set(id(con))}
    return estado.CUARTOS_MAGICOS


def _numero_cuarto():
    n = 1
    while n in cuartos():
        n += 1
    return n


def _ff61(slot, u32=0):
    return struct.pack("<HBBI", A_FIJO, slot, TIPO_MAGICA, u32 & 0xFFFFFFFF)


def _cuarto_de(con):
    n = getattr(con, "cuarto", None)
    return (n, cuartos().get(n)) if n is not None else (None, None)


def _otro(con):
    n, c = _cuarto_de(con)
    if c is None:
        return None
    return next((x for x in c["cons"] if x is not con and getattr(x, "cuarto", None) == n), None)


def _asiento_de(con):
    n, c = _cuarto_de(con)
    return ASIENTOS[c["cons"].index(con)] if c and con in c["cons"] else ASIENTOS[0]


def entrar_cuarto(con, seq, cuerpo):
    """C2S FF0F A=0x5BDB de uno de los dos emparejados: S2C FF0F [slot][0xB][0][0] + FF61 [A][slot][0xB][u32 0] (calco de la casa; el cliente
    lo acepto: MEDIDO 8 de 8). El u32 del FF61 va en 0 (INVENTADO: solo lo usa la casa)."""
    n = con.magica
    c = cuartos()[n]
    slot = ASIENTOS[c["cons"].index(con) if con in c["cons"] else 0]
    con.magica = None
    con.cuarto = n
    con.cuarto_hora = time.time()
    con.cuarto_avisado = False
    con.cuarto_16a = False
    import salas
    salas.sacar_de_su_sala(con)
    con.mandar_interno(0x0F, seq, bytes([slot, TIPO_MAGICA, 0, 0]))
    con.mandar_interno(0x61, seq, _ff61(slot, 0))
    anotar("   C2S FF0F A=0x%04X de %s: entra al CUARTO %d en el asiento %d -> S2C FF0F %02x0b0000 + FF61" % (
        struct.unpack_from("<H", cuerpo, 0)[0], _nick(con), n, slot, slot))
    return True


def _sala_datos(con):
    """Sala de DATOS (no se registra en estado.SALAS) con los que ya estan adentro, en sus asientos."""
    n, c = _cuarto_de(con)
    sala = estado.Sala(n & 0x7FF, {"modo": 0, "titulo": b"", "clave": b""}, con, TIPO_MAGICA)
    sala.asientos = {ASIENTOS[i]: x for i, x in enumerate(c["cons"]) if getattr(x, "cuarto", None) == n}
    sala.orden = tuple(sorted(sala.asientos))
    sala.max = 2
    return sala


def ff0c_para(sala, para):
    """El FF0C del cuarto para `para`, con el PROPIO PRIMERO. MEDIDO: con la lista por asiento el cliente de asiento mayor se cerraba (EIP
    0x029ae663, lectura de 0x470; la misma caida de la ficha 114); con el propio primero, 0 caidas en 8 corridas. LEIDO (HIPOTESIS de la
    causa): ese codigo (tick de un ocupante) busca el asiento PROPIO en el mapa de ocupantes cRoom+0x7e0 (0x029ae605..0x029ae62b) y, si todavia
    no esta, compara contra la clave del fin del arbol (ecx = 0x470)."""
    import fichas
    import salas
    jug = sorted(sala.asientos.items())
    jug = [x for x in jug if x[1] is para] + [x for x in jug if x[1] is not para]
    return fichas.lista_ff0c([salas.ficha_ff0c(c, a, c is para, salas.equipo_de(sala, c)) for a, c in jug])


def _mandar_ff0c(para, sala, seq):
    """El FF0C del cuarto para `para`: UN mensaje por jugador, el propio primero (ficha 122).
    MEDIDO (ficha 122, 3 variantes): con los dos jugadores en UN mismo FF0C el cliente solo llena el registro del primero; el segundo deja un
    nodo vacio de clave 0 (en cRoom+0x7e0 y en el mapa de jugadores [[0x3a7cf54]+4]: +0x469 = 0, apodo en +0x54 vacio). Entonces el clic de
    示好 / 添加好友 (0x00a224b0 / 0x00a22390: saltan el nodo propio y el de apodo vacio) no encuentra a nadie y no pasa NADA, y la ficha de usuario
    sale apilada. Con un FF0C de un jugador por mensaje (propio primero: sigue sin caer, EIP 0x029ae663) los dos nodos quedan llenos. HIPOTESIS
    (no leida) de por que: el segundo registro de un mismo mensaje no llega a su nodo en el bucle de 0x02786900."""
    import fichas
    import salas
    jug = sorted(sala.asientos.items())
    jug = [x for x in jug if x[1] is para] + [x for x in jug if x[1] is not para]
    for i, (a, c) in enumerate(jug):
        para.mandar_interno(0x0C, seq if i == 0 else 0, fichas.lista_ff0c([salas.ficha_ff0c(c, a, c is para, salas.equipo_de(sala, c))]))


def pedido_de_sala(cmd):
    def f(con, seq, cuerpo):
        """C2S FF15 / FF0C estando en el cuarto: se contestan con una Sala de datos (como la casa)."""
        if not cuarto_activo() or getattr(con, "cuarto", None) is None:
            return False
        import salas
        sala = _sala_datos(con)
        if cmd == 0x15:
            base = next((cu for c, _s, cu in salas._plantilla() if c == 0x15), None)
            con.mandar_interno(0x15, seq, salas.ff15_para(base, sala))
            anotar("   S2C FF15 del cuarto %d" % con.cuarto)
            return True
        _mandar_ff0c(con, sala, seq)
        anotar("   S2C FF0C del cuarto %d a %s (%d en la lista: asientos %s)" % (con.cuarto, _nick(con), len(sala.asientos), sorted(sala.asientos)))
        _tras_ff0c(con)
        return True
    return f


def _ff16a(n):
    """S2C FF16A sub 0 minimo (LEIDO el formato): [0][A u32 = 1][B u32 = 0][C u16 = n][D = 0][E = 0]. MEDIDO: no abre popup ni premio; INVENTADO que A sea 1."""
    return struct.pack("<BIIHBB", 0, 1, 0, n & 0xFFFF, 0, 0)


def _tras_ff0c(con):
    """Despues de contestar el FF0C: al que ya estaba adentro le llega el FF0C nuevo con los dos, y al recien llegado el FF16A."""
    n, c = _cuarto_de(con)
    otro = _otro(con)
    if otro is not None and not getattr(con, "cuarto_avisado", False):
        con.cuarto_avisado = True
        sala = _sala_datos(otro)
        _mandar_ff0c(otro, sala, 0)
        anotar("   S2C FF0C nuevo a %s (ahora con %d)" % (_nick(otro), len(sala.asientos)))
    if not getattr(con, "cuarto_16a", False):
        con.cuarto_16a = True
        con.mandar_interno(0x16A, 0, _ff16a(n))
        anotar("   S2C FF16A sub 0 [A=1 B=0 C=%d D=0 E=0] a %s" % (n, _nick(con)))


def lampara_16f(con, seq, cuerpo):
    """C2S FF16F (vacio): la lampara. S2C FF16F [1] a los DOS (regla INVENTADA: la primera pulsacion de cualquiera la prende para ambos)."""
    n, c = _cuarto_de(con)
    if not cuarto_activo() or c is None:
        return False
    anotar("   C2S FF16F (%d B) de %s en el cuarto %d" % (len(cuerpo), _nick(con), n))
    c.setdefault("lampara", set()).add(id(con))
    for x in c["cons"]:
        if getattr(x, "cuarto", None) == n:
            x.mandar_interno(0x16F, seq if x is con else 0, bytes([1]))
    anotar("   S2C FF16F [1] a los del cuarto %d (INVENTADO: la prende el primero)" % n)
    return True


def chat_170(con, seq, cuerpo):
    """C2S FF170 [u8 largo][texto]: se releva TAL CUAL al otro del cuarto (MEDIDO con CANCLE: el otro cuenta 5 s y sale solo; el resto, HIPOTESIS)."""
    n, c = _cuarto_de(con)
    if not cuarto_activo() or c is None or len(cuerpo) < 1 or 1 + cuerpo[0] > len(cuerpo):
        return False
    texto = cuerpo[1:1 + cuerpo[0]]
    otro = _otro(con)
    anotar("   C2S FF170 %r de %s en el cuarto %d%s" % (texto, _nick(con), n, " -> al otro" if otro is not None else " (solo)"))
    if otro is not None:
        otro.mandar_interno(0x170, 0, cuerpo)
    if texto == b"CREATEROOM" and jugar_activo():
        c["creador"] = con                   # FICHA 130: el que apreto 创建 en el dialogo; su FF14 viene pegado (MEDIDO)
        c["invitar"] = otro
        c["creador_hora"] = time.time()
        anotar("   FICHA 130: %s crea la sala de carrera desde el cuarto %d" % (_nick(con), n))
    return True


def salio_del_cuarto(con, desconexion=False):
    """Uno sale (FF14) o se cae: si fue desconexion el otro recibe el FF170 CLOSE (HIPOTESIS: LEIDO que el cliente lo entiende y nadie lo manda);
    el cuarto se borra cuando no queda nadie (ni adentro ni con la entrada pendiente)."""
    n, c = _cuarto_de(con)
    if c is None:
        n = getattr(con, "magica", None)
        c = cuartos().get(n)
    if c is None:
        return
    con.cuarto = None
    con.magica = None
    con.cuarto_avisado = False
    con.cuarto_16a = False
    quedan = [x for x in c["cons"] if x is not con and (getattr(x, "cuarto", None) == n or getattr(x, "magica", None) == n)]
    if desconexion and quedan:
        for x in [y for y in quedan if getattr(y, "cuarto", None) == n]:
            try:
                x.mandar_interno(0x170, 0, bytes([5]) + b"CLOSE")
            except Exception as e:                                       # noqa: BLE001
                anotar("   ⛔ FF170 CLOSE: %r" % (e,))
    if not quedan:
        cuartos().pop(n, None)
        anotar("   cuarto %d cerrado (no queda nadie)" % n)


def salir_14(con, seq, cuerpo):
    """C2S FF14 estando en el cuarto: S2C FF14 0000 (como la casa; MEDIDO 2 de 2 desde el boton de volver)."""
    if not cuarto_activo() or getattr(con, "cuarto", None) is None:
        return False
    con.mandar_interno(0x14, seq, struct.pack("<H", 0))
    anotar("   S2C FF14 0000: %s sale del cuarto %s" % (_nick(con), con.cuarto))
    n, c = _cuarto_de(con)
    if jugar_activo() and c is not None and c.get("creador") is con and time.time() - c.get("creador_hora", 0) < VENTANA_CREAR:
        import threading
        c["creador"] = None
        threading.Timer(DEMORA_CREAR, _tras_salir_creador, (con, c)).start()
    elif jugar_activo() and c is not None and c.get("sala_invitada") is not None and c.get("invitar") is con:
        import threading
        threading.Timer(DEMORA_REINVITAR, _reinvitar, (con, c["sala_invitada"])).start()
    salio_del_cuarto(con)
    return True


def jugar_activo():
    return cuarto_activo() and llave("SALA_MAGICA_JUGAR")


DEMORA_CREAR = 3.0
VENTANA_CREAR = 30.0         # s: el FF14 del creador viene pegado a su CREATEROOM (MEDIDO, 0 s); uno mucho mas tarde es una salida comun
DEMORA_REINVITAR = 3.5       # s despues del FF14 del invitado: ya esta en el lobby (el FF181 llega ~2 s despues del FF14, MEDIDO)


def _crear_sala_para(con, c):
    """FICHA 130 variante V2 (INVENTADA): el cliente del creador, tras CREATEROOM + FF14, NO manda FF1F5 solo (MEDIDO: queda en el lobby con
    cRoom+0x77a1 = 2 y canal logico 0; ni con un S2C FF7 [00] a +4 s, variante V1, que solo recarga el lobby). Entonces el servidor crea la
    sala por el (modo individual, titulo 'magica': lo que eligio en el dialogo NO llega al servidor), se la manda como la respuesta de crear
    (salas.mandar_sala) y le avisa al otro con la invitacion de siempre (S2C FF52 [01][A u16][0][0], social.invitar)."""
    import salas
    if getattr(con, "cuarto_muerto", False):
        anotar("   FICHA 130: %s se desconecto antes de crear la sala: no se crea" % _nick(con))
        return
    otro = c.get("invitar")
    if getattr(otro, "cuarto_muerto", False):
        otro = None
    numero = salas.numero_libre()
    pedido = {"modo": 0x0A, "titulo": b"magica", "clave": b"", "bandera": 0, "u8": 0, "textos": [b"", b""]}
    salas.sacar_de_su_sala(con)
    sala = salas.nueva_sala(numero, pedido, con, 0)
    estado.SALAS[numero] = sala
    con.sala = numero
    c["sala_invitada"] = numero
    m = salas.mandar_sala(con, sala)
    anotar("   FICHA 130 V2: sala %d creada por el servidor para %s (%d mensajes; INVENTADO: modo individual, titulo 'magica')" % (numero, _nick(con), m))
    if otro is not None:
        otro.mandar_interno(0x52, 0, b"\x01" + struct.pack("<H", numero & 0x7FF) + b"\x00\x00")
        anotar("   FICHA 130 V2: S2C FF52 [01][A=%d][0][0] (invitacion) a %s" % (numero, _nick(otro)))


def _reinvitar(con, numero):
    """FICHA 130 V3 (INVENTADA): el FF52 mandado cuando el invitado todavia estaba en el cuarto no se vio (MEDIDO: ningun cartel); se repite
    cuando ya salio al lobby (donde social.invitar lo manda siempre)."""
    if numero in estado.SALAS and con.sala is None and not getattr(con, "cuarto_muerto", False):
        con.mandar_interno(0x52, 0, b"\x01" + struct.pack("<H", numero & 0x7FF) + b"\x00\x00")
        anotar("   FICHA 130 V3: S2C FF52 [01][A=%d] otra vez a %s (ya en el lobby)" % (numero, _nick(con)))


def _tras_salir_creador(con, c):
    try:
        _crear_sala_para(con, c)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ ficha 130 crear sala: %r" % (e,))


MANEJADORES = {
    0x167: registrar_167,
    0x0F: entrar_f,
    0x15: pedido_de_sala(0x15),
    0x0C: pedido_de_sala(0x0C),
    0x16F: lampara_16f,
    0x170: chat_170,
    0x14: salir_14,
}
