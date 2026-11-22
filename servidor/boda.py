# -*- coding: utf-8 -*-
r"""boda.py (12-nov, ficha 76) — la boda, PASO 1: pedir matrimonio (usar el anillo de compromiso 11000103), aceptar o rechazar, y el
bloque de boda de 129 B (FF1BE / FF1BF). Solo cuentas LOCALES que ya son PAREJA (social.py, ficha 74). LEIDO en el exe (un testigo,
docs/tablero/BODA_LECTURA.md "Lectura de la ficha 79" y "Medido con el juego, ficha 76"); NADA de misiones, compras, reserva ni salon.

  C2S FFA8 [u32 0xFFFFFFFF][u32 11000103][u32 X]   usar el anillo (el cliente exige pareja y estado 0 ANTES: si no, cartel 1339; confirma con
                                                   el cartel 1484; MEDIDO: se manda al apretar 确认, 12 B)
  S2C FFA8 CmdUse [u32 item][u8 res]               (0x027f38c0) con el 11000103 el u8 elige un cartel (tabla 0x027f3c50): 13 -> 1352 "Registro de
                                                   mision de compromiso completado", 12/14/15 -> 1339, 18 -> 1420 (nivel 6), 1 -> 1353; 3,4,6,7,10,11,
                                                   16,17 -> sin cartel; 0, 2, 5, 8, 9 son carteles de la LLAVE de casa (no usar con el anillo)
  S2C FF1BC [u32]            al otro: cartel 1405 con Si / No (el u32 se lee y no se usa)
  C2S FF1BD [u8 1|2]         el otro contesta: 1 acepta, 2 rechaza (emisor 0x0282faa0)
  S2C FF1BD [u8]             1 -> cartel 1407 ; 2 -> cartel 1408 y refresca la hoja de pareja
  S2C FF1BF [129 B]          el bloque de boda (sin res); C2S FF1BE (0 B) -> S2C FF1BE [u8 res][129 B] (res 1 + bloque del constructor = lo
                                                   que contesto el oficial a las 9 cuentas sin boda; res 0 con boda: SetWeddingState por +0x22)

BLOQUE (LEIDO, BODA_LECTURA.md §1): el constructor 0x48fd30 deja todo en 0 salvo +0x59 = 0x30 y +0x74 = 3 (sala 3 = ninguna). Aca solo se llenan
  +0x22 ESTADO (0 nada, 1 espera consentimiento, 4 misiones = `Wedding_Step1`) y +0x2f MISION ACTUAL (1 al entrar a "misiones": INVENTADO el
  valor inicial; 0 significa "todas hechas"). El resto queda en 0.
ESTADO (seccion `boda` de cada cuenta, la MISMA en las dos de la pareja, escrita con UN candado de cuenta.py):
  {"estado": 4, "otro": usn de la pareja, "mision": 1, "anillo_de": usn de quien uso el anillo, "inventado": true}
  El estado 1 (esperando) NO se guarda: vive en memoria (estado.PEDIDOS_BODA) y se pierde con la desconexion.
INVENTADO (marcado): (a) el anillo se GASTA al ACEPTAR, no al usarlo (el texto 1484 dice "desaparece en cuanto se registra"; el exe no lo
  descuenta: el cliente muestra el inventario hasta que pide el FF49); (b) un pedido pendiente se CANCELA si alguno se desconecta (el que
  quedo conectado vuelve a estado 0 con un FF1BF); (c) con el otro desconectado o sin anillo, el pedido se rechaza con el cartel 1339;
  (d) el valor X del C2S no se usa; (e) la forma de la respuesta del FFA8 (variantes en VARIANTES); (f) que la boda se borre si la pareja
  cambia (el estado guardado solo vale mientras `otro` sea la pareja actual).
FICHA 112 (12-nov): PASO 2 = las 6 MISIONES de `Wedding_Step1` (estado 4). MEDIDO con el juego (copias 2 y 3, fotos en el scratchpad ficha112):
  el icono del mensajero se prende con el registro tipo 1 de social.py (llave PAREJA_EN_MENSAJERO) y la ventana 誓约任务 abre con
  `+0x2f` (mision actual) y `+0x30` (u32, progreso). LEIDO (0x00bb19a0..): objetivos 40, 500, 25, 40, 50, 20 (constantes del cliente); costo de saltar
  = tabla de 6 u32 en 0x03746e30 (50, 120, 210, 320) + 450 + 600 indexada por 6 - mision (MEDIDO: 600 con mision 1); FF1C1 res 0 -> cartel 1409
  + refresca + FF51; res 2 -> 1410; res 3 -> 2018 (texto que no esta en idioma_es); FF1C2 res 0 -> cartel 1411 + reabre el administrador con el bloque
  (el boton de premio con mision != 0 pone el cartel 1412 SIN mandar nada: MEDIDO). Que CUENTA cada mision (titulos MEDIDOS en pantalla):
    1 参加竞速个人模式 "participar en el modo individual de carrera" (40)  -> cuenta carreras individuales (INVENTADO: con la pareja en la misma sala)
    2 收集爱意值 "reunir valor de amor" (500)                                -> el servidor no tiene esa cuenta: NO AVANZA
    3 获得接力模式胜利 "ganar en relevo" (25)                                -> victorias en relevo (INVENTADO: gana uno de los dos)
    4 获得道具模式胜利 "ganar en modo objetos" (40)                          -> victorias en modo Item (INVENTADO: gana uno de los dos)
    5 收集玩伴模式稀有道具 "reunir objetos raros en el modo pareja" (50)      -> el servidor no cuenta objetos recogidos: NO AVANZA
    6 享受食神模式 "disfrutar del modo gloton" (20)                           -> carreras en modo gloton (INVENTADO: jugarlas, con la pareja en la misma sala)
  El progreso es UNO solo (el bloque trae una mision y un u32): INVENTADO que las misiones van EN ORDEN, que el progreso de la pareja es COMPARTIDO
  (se guarda igual en las dos cuentas) y que al llegar al objetivo pasa a la siguiente con progreso 0; tras la 6.a, mision 0 ("todas hechas").
  Saltar (FF1C1) cobra el costo de la tabla en G (INVENTADO la moneda: el texto chino dice G) y deja mision 0. FF1C2 con mision 0: ver `premio`.
Llave por entorno BODA (omision 1 en LLAVES_OMISION; =0 y FFA8 / FF1BD / FF1BE quedan como antes: sin contestar). BODA_FFA8 = a|b|c|d (omision b).
FICHA 113 (12-nov): PASO 3 = FF1C2 (premio: 4 -> 5, SIN entregar el 30812: no existe en ninguna tabla del cliente), Step2 (estado 5: FF1C4 transferir el permiso, FF274 canje del cupon,
  FF194 compra del salon y de adornos; el salon y el permiso van en +0x4d / +0x3c / +0x40 del bloque) y Step3 (estados 6 y 7: FF1C5 horas libres del dia, FF1DB salas libres de la hora,
  FF1C6 reservar, FF1C7 cancelar, FF1DD "no es momento"). Todo con las llaves BODA y BODA_PREMIO. El detalle MEDIDO / LEIDO / INVENTADO esta en cada funcion y en BODA_LECTURA.md.
  NO esta: entrar al salon (FF1DC / FF1C8) ni la ceremonia, el divorcio, el calendario de casados ni el estado 8.
FICHA 114 (12-nov): PASO 4 = entrar al salon el dia y la hora reservados, la ceremonia y "casados" (llave BODA_SALON, 1 por omision: con 2 copias, 2 corridas completas: los dos entraron, la ceremonia
  termino, quedaron en estado 8 y salieron). Todo MEDIDO / LEIDO / INVENTADO en BODA_LECTURA.md "Medido con el juego, ficha 114". En corto:
  - C2S FF1DD (Step3, 进入婚礼场): dentro de la ventana [fecha - 10 min, fecha + 30 min] (INVENTADA la de antes; la de despues LEIDA: la escena calcula el fin como fecha + 30 min) contesta [1]; el cliente
    manda FF1DC -> S2C FF1DC [3][3 x 66 B] con los novios en la fila de su sala -> C2S FF1C8 [sala] -> S2C FF0F + FF61 (asiento 0x26 / 0x27) y FF1C8 [u16][asiento][canal 5]; con ticket 11000102 (INVENTADO que se exige a los
    dos y que no se gasta) o 0x40; fuera de hora / otra sala 0x41. El cliente pide FF15 y FF0C: se contestan con una Sala de DATOS (casa.py las enruta aqui) y el FF0C trae SOLO al propio.
  - A la HORA de la boda (INVENTADO: la fecha reservada) FF1C9 (los dos novios) + FF1CA: la ceremonia la corre el cliente solo (~4 min) y termina con un cartel.
  - A fecha + 30 min (temporizador de estado.mas_tarde, o al pedir el bloque si el temporizador se perdio) y solo si LOS DOS entraron: estado 8 en las dos cuentas (UN candado) + FF1BF. Salir: FF181 / FF14 (casa.py -> salir_14).
  - INVENTADO: ticket, orden de asientos (menor usn en el 0x26), que no se echa a nadie al cerrar, que si uno solo entra no se casan, sin vencimiento de la reserva. Invitados: NO estan hechos (la fila se manda cerrada, +0x34 = 1).
"""
import os
import struct
import threading
import time

import cuenta as _cta
import estado
import social

LLAVES_OMISION = {"BODA": "1", "BODA_FFA8": "b", "BODA_PREMIO": "1", "BODA_SALON": "1", "BODA_CASADOS": "1"}   # ficha 113 (12-nov): BODA_PREMIO PRENDIDA: Step2 (transferir el permiso, canjear el cupon o comprar el salon) y Step3 (fecha, hora, sala, privacidad, reservado, cancelar) se recorrieron con el juego en las DOS copias hasta "reservado" sin trabas (ver BODA_LECTURA.md). La ficha 112 la dejo en 0 porque el estado 5 era una puerta sin salida.
SECCION = "boda"
ANILLO = 11000103
CMD_USO, CMD_PEDIDO, CMD_RESPUESTA, CMD_INFO, CMD_ACTUALIZA = 0xA8, 0x1BC, 0x1BD, 0x1BE, 0x1BF
LARGO_BLOQUE = 129
OFS_ESTADO, OFS_MISION, OFS_PROGRESO = 0x22, 0x2F, 0x30
OFS_PERMISO, OFS_APODO, OFS_SALON, OFS_FECHA, OFS_SALA, OFS_PRIVADO = 0x3C, 0x40, 0x4D, 0x51, 0x73, 0x74
# +0x3c .. +0x51: LEIDO ficha 75 (BODA_LECTURA.md §1). MEDIDO ficha 113 con el juego (Step3 estado 7): el panel muestra como NOMBRE DE LA SALA el texto 2997 + [+0x73] (0 浪漫起航,
# 1 情牵一线, 2 爱意永恒) y como PRIVACIDAD el candado segun [+0x74] (0 公开, 1 非公开): al reves de lo que decia la ficha 75 (que daba +0x73 privacidad y +0x74 sala).
OBJETIVOS = (40, 500, 25, 40, 50, 20)                          # LEIDO: constantes del cliente (0x00bb19d5, 0x00bb19dc y la tabla 0x03746cb0)
COSTO_SALTAR = {6: 50, 5: 120, 4: 210, 3: 320, 2: 450, 1: 600}  # LEIDO: tabla 0x03746e30 + 450 + 600 por (6 - mision); MEDIDO 600 con mision 1
RES_SALTO_OK, RES_SALTO_NADA, RES_SALTO_SIN_SALDO = 0, 2, 3    # FF1C1 (LEIDO 0x028309f0): 0 -> cartel 1409, 2 -> 1410, 3 -> 2018 (HIPOTESIS: sin saldo; el texto 2018 no esta en idioma_es)
ESTADO_COMPRAS = 5
CMD_SALTAR, CMD_PREMIO = 0x1C1, 0x1C2
RES_NO_PUEDE = 12            # CmdUse res 12 -> cartel 1339 con el anillo (LEIDO 0x027f3c50)
RES_HECHO = 13               # CmdUse res 13 -> cartel 1352 (LEIDO)
ESTADO_ESPERA, ESTADO_MISIONES = 1, 4
ESTADO_RESERVA, ESTADO_RESERVADO, ESTADO_CASADOS = 6, 7, 8      # LEIDO ficha 75 (§1): 6 / 7 / 9 abren Step3; 7 = reservada. INVENTADO el orden 5 -> 6 -> 7
# VARIANTES de la respuesta al FFA8 (medidas con el juego, ver el Informe de la ficha 76):
#   a = nada (solo el FF1BC al otro)             b = CmdUse res 13 (cartel 1352) + FF1BF estado 1
#   c = CmdUse res 13 solo                       d = FF1BF estado 1 solo
VARIANTES = "abcd"


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="BODA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def variante():
    v = os.environ.get("BODA_FFA8", LLAVES_OMISION["BODA_FFA8"]).lower()
    return v if v in VARIANTES else LLAVES_OMISION["BODA_FFA8"]


def pedidos():
    """{usn del que pidio: {"otro": usn, "hora": t}} (memoria; sobrevive a las recargas)."""
    if not hasattr(estado, "PEDIDOS_BODA"):
        estado.PEDIDOS_BODA = {}
    return estado.PEDIDOS_BODA


def candado():
    if not hasattr(estado, "BODA_CANDADO"):
        estado.BODA_CANDADO = threading.RLock()
    return estado.BODA_CANDADO


def _usn(con):
    return (con.cuenta or {}).get("usn")


def _nick(con):
    return (con.cuenta or {}).get("nick")


def _conectado(usn):
    return next((c for c in list(estado.CONEXIONES.values()) if (c.cuenta or {}).get("usn") == usn), None)


def _pareja_de(usn):
    return (social.parejas().get(usn) or {}).get("usn")


def _saldos_al_dia(usn, g=False, diamantes=False):
    """Ficha 131 (llave SALDOS_AL_DIA, tienda.refrescar_saldos): al que PAGO fuera de la tienda se le manda su saldo nuevo (FF5B el G, FF51 los
    diamantes) para que la barra y la ventana de compra no queden viejas. Solo si esta conectado. Con la llave en 0 no hace nada."""
    try:
        import tienda
        c = _conectado(usn)
        if c is not None:
            tienda.refrescar_saldos(c, g=g, diamantes=diamantes)
    except Exception as e:                                                  # noqa: BLE001
        anotar("   ⛔ boda._saldos_al_dia: %r" % e)


def tiene_anillo(usn):
    return any(reg[0] == ANILLO for reg in (_cta.leer_seccion(usn, "tienda").get("items") or []))


def guardado(usn):
    """(estado, mision) guardados de la cuenta, y solo si siguen valiendo (la pareja actual es `otro`). (0, 0) si no hay boda."""
    s = _cta.leer_seccion(usn, SECCION)
    if not s or not s.get("estado"):
        return 0, 0
    if _pareja_de(usn) != s.get("otro"):
        return 0, 0
    return int(s["estado"]), int(s.get("mision", 0))


def progreso_de(usn):
    """Progreso (u32) de la mision actual guardado de esa cuenta; 0 si no hay boda valida."""
    est, _mis = guardado(usn)
    if not est:
        return 0
    return int((_cta.leer_seccion(usn, SECCION) or {}).get("progreso", 0))


def bloque(est, mision=0, progreso=0, permiso=0, nick="", salon=0, fecha=None, sala=0, privado=0):
    """Los 129 B de boda: el constructor 0x48fd30 (+0x59 = 0x30, +0x74 = 3) con el estado, la mision actual y su progreso (u32 en +0x30).
    Ficha 113 (LEIDO, BODA_LECTURA.md): +0x3c u32 usn con el PERMISO DE RESERVA y +0x40 su apodo (13 B, C), +0x4d u32 salon, +0x51 fecha-hora de 7 B,
    +0x73 sala (nombre) y +0x74 privacidad (MEDIDO ficha 113; la ficha 75 los daba al reves). Sin reserva el resultado es byte a byte el de la ficha 112."""
    b = bytearray(LARGO_BLOQUE)
    b[0x59] = 0x30
    b[0x74] = 3
    b[OFS_ESTADO] = est & 0xFF
    b[OFS_MISION] = mision & 0xFF
    struct.pack_into("<I", b, OFS_PROGRESO, progreso & 0xFFFFFFFF)
    if permiso:
        struct.pack_into("<I", b, OFS_PERMISO, permiso & 0xFFFFFFFF)
        n = social._gbk(nick or "", 12)
        b[OFS_APODO:OFS_APODO + len(n)] = n
    if salon:
        struct.pack_into("<I", b, OFS_SALON, salon & 0xFFFFFFFF)
    if fecha:
        b[OFS_FECHA:OFS_FECHA + 7] = fecha_a_bytes(fecha)
        b[OFS_SALA] = sala & 0xFF
        b[OFS_PRIVADO] = privado & 0xFF
    return bytes(b)


def fecha_a_bytes(f):
    """[anio, mes, dia, hora, min, seg] -> 7 B `{u16 anio, u8 mes, dia, hora, min, seg}` (LEIDO 0x02732e20, BODA_LECTURA.md §1)."""
    return struct.pack("<HBBBBB", f[0], f[1], f[2], f[3], f[4], f[5])


def datos_boda(usn):
    """La seccion `boda` de la cuenta si sigue valiendo (la pareja actual es `otro`), si no {}."""
    s = _cta.leer_seccion(usn, SECCION)
    if not s or not s.get("estado") or _pareja_de(usn) != s.get("otro"):
        return {}
    return s


def permiso_de(s):
    """usn con el permiso de reserva: el guardado, o (INVENTADO) quien uso el anillo."""
    return int(s.get("permiso") or s.get("anillo_de") or 0)


def bloque_de(usn):
    """(bloque, estado) que ve esa cuenta AHORA: el guardado, o estado 1 si tiene un pedido suyo en espera."""
    if llave("BODA_SALON"):
        cerrar_si_toca(usn)            # ficha 114: si la sala ya cerro (fecha + 30 min) y los dos entraron, estan casados (estado 8)
    est, mis = guardado(usn)
    if est == 0 and usn in pedidos():
        return bloque(ESTADO_ESPERA), ESTADO_ESPERA
    if est < ESTADO_COMPRAS:
        return bloque(est, mis, progreso_de(usn)), est
    s = datos_boda(usn)
    perm = permiso_de(s)
    return bloque(est, mis, int(s.get("progreso", 0)), perm, social._nick(perm) if perm else "", int(s.get("salon", 0)),
                  s.get("fecha"), int(s.get("sala", 0)), int(s.get("privado", 0))), est


def info(con, seq, cuerpo):
    """C2S FF1BE (0 B) -> S2C FF1BE [res][129 B]. Sin boda = lo que contesto el oficial (res 1 y el bloque del constructor)."""
    usn = _usn(con)
    if cuerpo or usn is None or not llave():
        return False
    b, est = bloque_de(usn)
    con.mandar_interno(CMD_INFO, seq, bytes([0 if est else 1]) + b)
    anotar("   S2C FF1BE de %s: res %d, estado %d" % (_nick(con), 0 if est else 1, est))
    return True


def _mandar_ff1bf(usn):
    """S2C FF1BF con el bloque ACTUAL de esa cuenta, si esta conectada."""
    c = _conectado(usn)
    if c is not None:
        b, _est = bloque_de(usn)
        c.mandar_interno(CMD_ACTUALIZA, 0, b)


def _cmduse(con, seq, res):
    con.mandar_interno(CMD_USO, seq, struct.pack("<IB", ANILLO, res))


def usar(con, seq, cuerpo):
    """C2S FFA8 [u32 -1][u32 item][u32 X] con el anillo de compromiso: pide matrimonio a la pareja."""
    if len(cuerpo) != 12:
        return False
    menos1, item, x = struct.unpack("<III", cuerpo)
    if item != ANILLO:
        return False
    yo = _usn(con)
    if yo is None:
        return False
    if not llave():
        anotar("   FFA8 anillo de %s: BODA=0, sin atender (cuerpo %s)" % (_nick(con), cuerpo.hex(" ")))
        return False
    anotar("   FFA8 anillo de %s: [%08x][%d][X=%d]" % (_nick(con), menos1, item, x))
    with candado():
        otro = _pareja_de(yo)
        motivo = None
        if menos1 != 0xFFFFFFFF:
            motivo = "el primer u32 no es -1"
        elif otro is None:
            motivo = "no tiene pareja"
        elif not tiene_anillo(yo):
            motivo = "no tiene el anillo"
        elif guardado(yo)[0] != 0 or guardado(otro)[0] != 0:
            motivo = "la boda ya esta en marcha (estado %d)" % guardado(yo)[0]
        elif yo in pedidos() or any(p["otro"] == yo for p in pedidos().values()):
            motivo = "ya hay un pedido pendiente"
        elif otro in pedidos():
            motivo = "su pareja ya tiene un pedido pendiente"
        elif _conectado(otro) is None:
            motivo = "su pareja no esta conectada"
        if motivo is None:
            pedidos()[yo] = {"otro": otro, "hora": time.time()}
    if motivo is not None:
        _cmduse(con, seq, RES_NO_PUEDE)
        anotar("   BODA: %s pide matrimonio y NO se puede: %s (CmdUse res %d, cartel 1339)" % (_nick(con), motivo, RES_NO_PUEDE))
        return True
    v = variante()
    if v in "bc":
        _cmduse(con, seq, RES_HECHO)
    if v in "bd":
        con.mandar_interno(CMD_ACTUALIZA, 0, bloque(ESTADO_ESPERA))
    _conectado(otro).mandar_interno(CMD_PEDIDO, 0, struct.pack("<I", yo))
    anotar("   BODA: %s pide matrimonio a %s (variante %s): FF1BC al otro" % (_nick(con), _nick(_conectado(otro)), v))
    return True


def _gastar_anillo(acc):
    """Dentro de cuenta.cambiar_todas: quita UN anillo de la bolsa de `acc`. True si lo tenia."""
    items = (acc.get("tienda") or {}).get("items") or []
    for i, reg in enumerate(items):
        if reg[0] == ANILLO:
            if len(reg) > 2 and reg[2] > 1:
                reg[2] -= 1
            else:
                del items[i]
            return True
    return False


def _aceptar(a, b):
    """UN candado: las dos cuentas pasan a estado 4 y a `a` se le gasta el anillo. -> None si salio bien, o el motivo."""
    def f(dd):
        cu = dd["cuentas"]
        if str(a) not in cu or str(b) not in cu:
            return "falta una cuenta"
        if (cu[str(a)].get("pareja") or {}).get("usn") != b or (cu[str(b)].get("pareja") or {}).get("usn") != a:
            return "ya no son pareja"
        if not _gastar_anillo(cu[str(a)]):
            return "ya no tiene el anillo"
        for u, otro in ((a, b), (b, a)):
            cu[str(u)][SECCION] = {"estado": ESTADO_MISIONES, "otro": otro, "mision": 1, "progreso": 0, "anillo_de": a, "permiso": a, "inventado": True}
        return None
    return _cta.cambiar_todas(f)


def responder(con, seq, cuerpo):
    """C2S FF1BD [u8 1 = acepta | 2 = rechaza] del que recibio el FF1BC."""
    if len(cuerpo) != 1 or not llave():
        return False
    yo = _usn(con)
    if yo is None:
        return False
    cod = cuerpo[0]
    with candado():
        a = next((u for u, p in pedidos().items() if p["otro"] == yo), None)
        if a is not None and cod in (1, 2):
            del pedidos()[a]
    if a is None or cod not in (1, 2):
        anotar("   BODA: %s contesta FF1BD %d pero no hay pedido para el%s: no se hace nada" % (_nick(con), cod, "" if cod in (1, 2) else " (valor raro)"))
        return True
    quien = _conectado(a)
    if cod == 2:
        if quien is not None:
            quien.mandar_interno(CMD_RESPUESTA, 0, b"\x02")
            _mandar_ff1bf(a)
        anotar("   BODA: %s RECHAZA el pedido de %s (estado sin cambio)" % (_nick(con), _nick(quien) if quien else a))
        return True
    motivo = _aceptar(a, yo)
    if motivo is not None:
        _mandar_ff1bf(a)
        _mandar_ff1bf(yo)
        anotar("   BODA: %s acepta el pedido de %s pero NO se registra: %s" % (_nick(con), _nick(quien) if quien else a, motivo))
        return True
    for u in (a, yo):
        c = _conectado(u)
        if c is not None:
            c.mandar_interno(CMD_RESPUESTA, 0, b"\x01")
            c.mandar_interno(CMD_ACTUALIZA, 0, bloque(ESTADO_MISIONES, 1, 0))
    anotar("   BODA: %s acepta el pedido de %s: las dos cuentas pasan a estado %d (misiones); anillo gastado" % (
        _nick(con), _nick(quien) if quien else a, ESTADO_MISIONES))
    return True


def desconectado(con):
    """manejadores.desconectado: un pedido pendiente de esta conexion se CANCELA (INVENTADO); el que sigue conectado vuelve a estado 0."""
    yo = _usn(con)
    if yo is None:
        return
    avisar = []
    with candado():
        for u in [u for u, p in pedidos().items() if u == yo or p["otro"] == yo]:
            p = pedidos().pop(u)
            avisar.append(p["otro"] if u == yo else u)
    for u in avisar:
        if u != yo:
            _mandar_ff1bf(u)
    if avisar:
        anotar("   BODA: %s se desconecta con un pedido pendiente: cancelado" % _nick(con))


# ---------------------------------------------------------------------------------------------------------------------------------
# Ficha 112: las misiones (ver la cabecera). Todo con la llave BODA y solo con la boda en estado 4 y la pareja vigente.
def _avanzar(dd, a, b, cuanto):
    """Dentro de cuenta.cambiar_todas: suma `cuanto` al progreso compartido de la pareja a-b y pasa de mision al llegar al objetivo.
    -> (mision, progreso, completo) nuevos, o None si no hay boda en estado 4 valida en las dos."""
    cu = dd["cuentas"]
    sa, sb = (cu.get(str(a)) or {}).get(SECCION) or {}, (cu.get(str(b)) or {}).get(SECCION) or {}
    if sa.get("estado") != ESTADO_MISIONES or sb.get("estado") != ESTADO_MISIONES or sa.get("otro") != b or sb.get("otro") != a:
        return None
    mis = int(sa.get("mision", 0))
    if not 1 <= mis <= len(OBJETIVOS):
        return None
    prog = int(sa.get("progreso", 0)) + cuanto
    completo = False
    if prog >= OBJETIVOS[mis - 1]:
        mis, prog, completo = (mis + 1 if mis < len(OBJETIVOS) else 0), 0, True
    for u in (a, b):
        cu[str(u)][SECCION]["mision"] = mis
        cu[str(u)][SECCION]["progreso"] = prog
    return mis, prog, completo


def que_cuenta(mision, modo, gano):
    """1 si una carrera de `modo` (sala.modo) suma a la `mision` actual, 0 si no. `gano` = alguno de la pareja quedo 1.o.
    INVENTADO el criterio (el texto de cada mision es lo MEDIDO); la 2 y la 5 no se pueden contar con lo que el servidor sabe."""
    try:
        import progresion
        cm = progresion.condicion_de_modo(modo)
    except Exception:                                                   # noqa: BLE001
        cm = None
    if cm is None:
        return 0
    what1, what2 = cm
    if mision == 1:
        return 1 if what1 == "Single" else 0
    if mision == 3:
        return 1 if what1 == "Relay" and gano else 0
    if mision == 4:
        return 1 if what2 == "Item" and gano else 0
    if mision == 6:
        return 1 if what1 == "Pigrace" else 0
    return 0


def tras_carrera(sala, puesto):
    """carrera.mandar_cartel lo llama tras el cartel: cada pareja con la boda en estado 4 cuyos DOS miembros corrieron en esta sala suma
    una carrera a la mision actual (que_cuenta). `puesto` = {asiento: puesto}."""
    try:
        if not llave():
            return
        por_usn = {_usn(c): a for a, c in sala.asientos.items() if _usn(c) is not None}
        for yo in sorted(por_usn):
            otro = _pareja_de(yo)
            if otro is None or otro not in por_usn or otro < yo:       # cada pareja una sola vez (por el menor usn)
                continue
            est, mis = guardado(yo)
            if est != ESTADO_MISIONES:
                continue
            gano = puesto.get(por_usn[yo]) == 1 or puesto.get(por_usn[otro]) == 1
            cuanto = que_cuenta(mis, sala.modo, gano)
            if not cuanto:
                anotar("   BODA: mision %d de %s y %s: esta carrera (modo 0x%x) no suma" % (mis, yo, otro, sala.modo))
                continue
            with candado():
                r = _cta.cambiar_todas(lambda dd: _avanzar(dd, yo, otro, cuanto))
            if r is None:
                continue
            anotar("   BODA: %s y %s suman 1 a la mision %d: ahora mision %d, progreso %d%s" % (
                yo, otro, mis, r[0], r[1], " (completada)" if r[2] else ""))
            _mandar_ff1bf(yo)
            _mandar_ff1bf(otro)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ boda.tras_carrera: %r" % e)


def saltar(con, seq, cuerpo):
    """C2S FF1C1 (0 B, "saltar todas las misiones"): cobra COSTO_SALTAR[mision] en G (INVENTADO la moneda) y deja mision 0 en las dos
    cuentas. S2C FF1C1 [u8 res][129 B]: 0 -> el cliente copia el bloque, cartel 1409 y refresca; 3 (HIPOTESIS sin saldo) -> cartel 2018."""
    yo = _usn(con)
    if cuerpo or yo is None or not llave():
        return False
    import tienda
    with candado():
        est, mis = guardado(yo)
        otro = _pareja_de(yo)
        if est != ESTADO_MISIONES or otro is None or not 1 <= mis <= len(OBJETIVOS):
            b, _e = bloque_de(yo)
            con.mandar_interno(0x1C1, seq, bytes([RES_SALTO_NADA]) + b)
            anotar("   BODA: %s salta las misiones pero no hay nada que saltar (estado %d, mision %d): res %d" % (_nick(con), est, mis, RES_SALTO_NADA))
            return True
        costo = COSTO_SALTAR[mis]

        def cobrar(bolsa):
            if bolsa.get("g", 0) < costo:
                return None
            bolsa["g"] = bolsa.get("g", 0) - costo
            return bolsa["g"]
        quedan = tienda._con_bolsa(con, cobrar)
        if quedan is None:
            b, _e = bloque_de(yo)
            con.mandar_interno(0x1C1, seq, bytes([RES_SALTO_SIN_SALDO]) + b)
            anotar("   BODA: %s salta las misiones: no le alcanzan los %d G (res %d)" % (_nick(con), costo, RES_SALTO_SIN_SALDO))
            return True

        def f(dd):
            cu = dd["cuentas"]
            for u in (yo, otro):
                cu[str(u)][SECCION]["mision"] = 0
                cu[str(u)][SECCION]["progreso"] = 0
        _cta.cambiar_todas(f)
        b, _e = bloque_de(yo)
        con.mandar_interno(0x1C1, seq, bytes([RES_SALTO_OK]) + b)
    _mandar_ff1bf(otro)
    tienda.refrescar_saldos(con, g=True)                       # ficha 131: la barra de G baja en el momento
    anotar("   BODA: %s salta las misiones (cobrados %d G, quedan %d): mision 0 en las dos cuentas" % (_nick(con), costo, quedan))
    return True


def premio(con, seq, cuerpo):
    """C2S FF1C2 (0 B): con mision 0 (todas hechas) pasa las dos cuentas a estado 5 ("compras", `Wedding_Step2`) y contesta
    FF1C2 [0][129 B] (el cliente pone el cartel 1411 y reabre el administrador con el bloque). INVENTADO el paso 4 -> 5 y que NO se entrega ningun
    objeto (el premio dibujado es el 30812, que no esta en catalogo.json). Con mision != 0 el cliente ni lo manda (cartel 1412 local, MEDIDO).
    Llave BODA_PREMIO (omision 1 desde la ficha 113): con ella apagada el boton del premio no hace nada (como antes). Premio: el cliente dibuja el objeto 30812 y al recibir res 0 pone
    el cartel 1411 "recibis el Anillo de boda", pero 30812 NO existe en el catalogo ni en ninguna tabla del cliente (ficha 113): no se entrega nada."""
    yo = _usn(con)
    if cuerpo or yo is None or not llave() or not llave("BODA_PREMIO"):
        return False
    with candado():
        est, mis = guardado(yo)
        otro = _pareja_de(yo)
        if est != ESTADO_MISIONES or mis != 0 or otro is None:
            b, _e = bloque_de(yo)
            con.mandar_interno(0x1C2, seq, bytes([2]) + b)      # res 2 -> cartel 1412 "no completaste todas" (LEIDO 0x02830de0)
            anotar("   BODA: %s pide el premio sin tener todas las misiones (estado %d, mision %d): res 2" % (_nick(con), est, mis))
            return True

        def f(dd):
            cu = dd["cuentas"]
            for u in (yo, otro):
                cu[str(u)][SECCION]["estado"] = ESTADO_COMPRAS
        _cta.cambiar_todas(f)
        b, _e = bloque_de(yo)
        con.mandar_interno(0x1C2, seq, bytes([0]) + b)
    _mandar_ff1bf(otro)
    anotar("   BODA: %s reclama el premio: las dos cuentas pasan a estado %d (compras); sin objeto de premio" % (_nick(con), ESTADO_COMPRAS))
    return True


# ---------------------------------------------------------------------------------------------------------------------------------
# Ficha 113: PASO 3 de la boda: Step2 (estado 5: elegir y pagar el salon) y Step3 (estados 6 / 7: reservar la fecha). Ver BODA_LECTURA.md "Medido con el
# juego, ficha 113". Lo LEIDO / MEDIDO esta en cada funcion; lo INVENTADO va marcado.
SALONES = (11000129, 11000130, 11000418, 11000600)     # LEIDO: tabla de 4 salones del cliente @0x360fbe4 (con el digito 6 de "por cantidad": 11006129...)
CUPON = 11000114
ID_SALON = 6000     # MEDIDO ficha 113: el cliente manda el ID del objeto (codigo + 6000: 11006130 = 11000130 教堂婚礼场), no el indice
CMD_TRANSFERIR, CMD_CANJE, CMD_COMPRA = 0x1C4, 0x274, 0x194


def _datos_de(con):
    """(yo, otro, seccion) si `con` es de una pareja con la boda vigente, si no None."""
    yo = _usn(con)
    if yo is None:
        return None
    s = datos_boda(yo)
    otro = _pareja_de(yo)
    return (yo, otro, s) if s and otro is not None else None


def _s_cadena(t):
    """[u32 largo][bytes]: la cadena de FF274 (LEIDO ficha 95)."""
    b = t.encode("utf-8")
    return struct.pack("<I", len(b)) + b


def tiene_objeto(usn, item):
    return any(reg[0] == item for reg in (_cta.leer_seccion(usn, "tienda").get("items") or []))


def _gastar_objeto(acc, item):
    """Dentro de cuenta.cambiar_todas: quita UNA unidad de `item` de la bolsa de `acc`. True si la tenia."""
    items = (acc.get("tienda") or {}).get("items") or []
    for i, reg in enumerate(items):
        if reg[0] == item:
            if len(reg) > 2 and reg[2] > 1:
                reg[2] -= 1
            else:
                del items[i]
            return True
    return False


def _pareja_vigente(cu, yo, sy):
    """Dentro de cuenta.cambiar_todas: (otro, seccion del otro) si la boda de `yo` vale (la pareja actual es `otro` y los dos se apuntan), si no (None, {})."""
    otro = sy.get("otro")
    so = (cu.get(str(otro)) or {}).get(SECCION) or {}
    if otro is None or so.get("otro") != yo or ((cu.get(str(yo)) or {}).get("pareja") or {}).get("usn") != otro:
        return None, {}
    return otro, so


def canjear(con, seq, cuerpo):
    """C2S FF274 [u32 11000114][u32 id del salon] (LEIDO 0x02882f00; MEDIDO: el id es codigo + 6000, 11006130 = 11000130): canjea el cupon de reserva por el
    salon elegido. S2C FF274 [s]: "ok" -> el cliente sigue con un FF194 de las filas marcadas (MEDIDO: `[1][0]` sin adornos); otro texto -> cartel con ese
    texto. INVENTADO: se gasta el cupon, el salon queda guardado y el estado pasa a 6 (reserva) ahi mismo; solo con el permiso de reserva."""
    if not llave() or not llave("BODA_PREMIO") or len(cuerpo) != 8:
        return False
    cup, fila = struct.unpack("<II", cuerpo)
    yo = _usn(con)
    if yo is None:
        return False
    salon = fila - ID_SALON
    anotar("   BODA: FF274 de %s: cupon %d, salon %d" % (_nick(con), cup, salon))

    def f(dd):
        cu = dd["cuentas"]
        sy = (cu.get(str(yo)) or {}).get(SECCION) or {}
        otro, so = _pareja_vigente(cu, yo, sy)
        if cup != CUPON:
            return "no es el cupon"
        if otro is None or sy.get("estado") != ESTADO_COMPRAS or so.get("estado") != ESTADO_COMPRAS:
            return "la boda no esta en el paso de las compras"
        if permiso_de(sy) != yo:
            return "no tiene el permiso de reserva"
        if salon not in SALONES:
            return "la fila %d no es uno de los salones" % fila
        if not _gastar_objeto(cu[str(yo)], CUPON):
            return "no tiene el cupon"
        for u in (yo, otro):
            cu[str(u)][SECCION].update({"estado": ESTADO_RESERVA, "salon": salon, "permiso": yo, "pago": "cupon"})
        return None
    with candado():
        motivo = _cta.cambiar_todas(f)
    if motivo is not None:
        con.mandar_interno(CMD_CANJE, seq, _s_cadena(MENSAJE_ERROR))
        anotar("   BODA: FF274 rechazado: %s" % motivo)
        return True
    con.mandar_interno(CMD_CANJE, seq, _s_cadena("ok"))
    _mandar_ff1bf(yo)
    _mandar_ff1bf(_pareja_de(yo))
    anotar("   BODA: FF274 ok: cupon gastado, salon %d guardado, las dos cuentas pasan a estado %d (reserva)" % (salon, ESTADO_RESERVA))
    return True


MENSAJE_ERROR = "No se puede"
ADORNOS = (11000419, 11000420, 11000424, 11000601, 11000602, 11000603, 11000604, 11000609, 11000610)   # LEIDO ficha 79 (§B: adornos y oficiantes de wd_item.xml / wd_mc.txt)
RES_COMPRA_OK, RES_COMPRA_FALLA, RES_COMPRA_SIN_SALDO = 0, 1, 4    # FF194 S2C #1 (LEIDO 0x02816180: 0 = bien; 1 -> texto 1365; 4 -> 1364 con 0x2ab: HIPOTESIS sin saldo)


def _filas_ff194(cuerpo):
    """C2S FF194 (LEIDO 0x028176c0, MEDIDO sin adornos = `01 00000000`): [u8 tipo][u32 n][n x {u32 id, u8}]. -> (tipo, [(id, u8)]) o None si no cuadra."""
    if len(cuerpo) < 5:
        return None
    tipo, n = struct.unpack_from("<BI", cuerpo, 0)
    if n > 64 or len(cuerpo) != 5 + 5 * n:
        return None
    return tipo, [struct.unpack_from("<IB", cuerpo, 5 + 5 * i) for i in range(n)]


def _responder_ff194(con, seq, res, tipo=1):
    con.mandar_interno(CMD_COMPRA, seq, struct.pack("<IBI", res, tipo, 0))


def comprar(con, seq, cuerpo):
    """C2S FF194 SendBuyBatchItem: compra por lote. Ficha 113: las filas son ids (codigo + 6000: por cantidad, precio `n` del catalogo, moneda por Cash). Con
    el permiso de reserva: la fila de SALONES (una sola) elige y paga el salon (estado 5 -> 6) y las de ADORNOS se compran y quedan en la mochila
    (tienda.py). Todo valida ANTES de cobrar (el saldo de cada moneda alcanza para el lote). S2C FF194 `[u32 res][u8 tipo][u32 0]` (sin filas)."""
    if not llave() or not llave("BODA_PREMIO"):
        return False
    yo = _usn(con)
    fi = _filas_ff194(cuerpo)
    anotar("   BODA: FF194 de %s (%d B): %s" % (_nick(con), len(cuerpo), cuerpo.hex(" ")))
    if yo is None or fi is None:
        return False
    tipo, filas = fi
    import catalogo
    import tienda
    codigos = [i - ID_SALON for i, _x in filas]
    cobrado = {}

    def f(dd):
        cu = dd["cuentas"]
        sy = (cu.get(str(yo)) or {}).get(SECCION) or {}
        otro, _so = _pareja_vigente(cu, yo, sy)
        if otro is None or sy.get("estado") not in (ESTADO_COMPRAS, ESTADO_RESERVA):
            return "la boda no esta en el paso de las compras"
        if permiso_de(sy) != yo:
            return "no tiene el permiso de reserva"
        salones = [c for c in codigos if c in SALONES]
        extras = [c for c in codigos if c not in SALONES]
        if len(salones) > 1:
            return "mas de un salon en el lote"
        if salones and sy.get("estado") != ESTADO_COMPRAS:
            return "el salon ya esta elegido"
        if not salones and sy.get("estado") == ESTADO_COMPRAS:
            return "falta elegir el salon"
        if any(c not in ADORNOS for c in extras):
            return "hay filas que no son adornos de boda"
        if len(set(extras)) != len(extras):
            return "adornos repetidos"
        total = {"diamantes": 0, "g": 0}
        for c in salones + extras:
            if not catalogo.existe(c) or not catalogo.se_vende(c) or catalogo.ficha(c).get("n") is None:
                return "el objeto %d no se vende" % c
            total["diamantes" if catalogo.moneda(c) == "cash" else "g"] += catalogo.ficha(c)["n"]
        b = (cu[str(yo)].get("tienda") or {})
        if not b:
            return "sin bolsa de la cuenta"
        for mon, monto in total.items():
            if b.get(mon, 0) < monto:
                cobrado["sin_saldo"] = mon
                return "saldo de %s %d menor que %d" % (mon, b.get(mon, 0), monto)
        for mon, monto in total.items():
            b[mon] = b.get(mon, 0) - monto
        for c in extras:
            tienda._agregar(b["items"], c, 1, tienda.PERMANENTE, tienda._es_de_cantidad(catalogo.ficha(c)))
        if salones:
            for u in (yo, otro):
                cu[str(u)][SECCION].update({"estado": ESTADO_RESERVA, "salon": salones[0], "permiso": yo, "pago": "compra"})
        cobrado.update({"total": total, "salon": salones[0] if salones else 0, "extras": extras})
        return None
    with candado():
        motivo = _cta.cambiar_todas(f)
    if motivo is not None:
        res = RES_COMPRA_SIN_SALDO if cobrado.get("sin_saldo") else RES_COMPRA_FALLA
        _responder_ff194(con, seq, res, tipo)
        anotar("   BODA: FF194 rechazado: %s (res %d)" % (motivo, res))
        return True
    _responder_ff194(con, seq, RES_COMPRA_OK, tipo)
    try:
        con.mandar_interno(0x51, 0, b"\x01" + struct.pack("<I", tienda._con_bolsa(con, lambda b: b["diamantes"])))
    except Exception as e:                                                  # noqa: BLE001
        anotar("   ⛔ boda.comprar: FF51 %r" % e)
    if cobrado["total"]["g"]:
        tienda.refrescar_saldos(con, g=True)                    # ficha 131: lo cobrado en G (el FF51 de arriba ya cubre los diamantes)
    if cobrado.get("salon"):
        _mandar_ff1bf(yo)
        _mandar_ff1bf(_pareja_de(yo))
    anotar("   BODA: %s compro %s: cobrado %s" % (_nick(con), "el salon %d" % cobrado["salon"] if cobrado.get("salon") else "adornos %s" % cobrado.get("extras"), cobrado["total"]))
    return True


def transferir(con, seq, cuerpo):
    """C2S FF1C4 (0 B, boton 转让预约权限, cartel 1598): pasa el permiso de reserva a la pareja. S2C FF1C4 `[u8 res][129 B]` a LOS DOS (LEIDO 0x028311e0: res 0 = el
    cliente copia el bloque, refresca Step2 y avisa: 1414 al que recibe (bloque+0x3c == su usn), 1413 al otro; 1 -> 1415; 2 -> 1416). INVENTADO: solo con el
    permiso y en estados 5 y 6."""
    if cuerpo or not llave() or not llave("BODA_PREMIO"):
        return False
    yo = _usn(con)
    if yo is None:
        return False

    def f(dd):
        cu = dd["cuentas"]
        sy = (cu.get(str(yo)) or {}).get(SECCION) or {}
        otro, _so = _pareja_vigente(cu, yo, sy)
        if otro is None or sy.get("estado") not in (ESTADO_COMPRAS, ESTADO_RESERVA):
            return "la boda no esta en el paso de las compras o la reserva"
        if permiso_de(sy) != yo:
            return "no tiene el permiso de reserva"
        for u in (yo, otro):
            cu[str(u)][SECCION]["permiso"] = otro
        return None
    with candado():
        motivo = _cta.cambiar_todas(f)
    if motivo is not None:
        b, _e = bloque_de(yo)
        con.mandar_interno(CMD_TRANSFERIR, seq, bytes([1]) + b)
        anotar("   BODA: FF1C4 de %s rechazado: %s" % (_nick(con), motivo))
        return True
    for u in (yo, _pareja_de(yo)):
        c = _conectado(u)
        if c is not None:
            b, _e = bloque_de(u)
            c.mandar_interno(CMD_TRANSFERIR, 0, bytes([0]) + b)
            c.mandar_interno(CMD_ACTUALIZA, 0, b)        # MEDIDO ficha 113: FF1C4 refresca Step2 SI esta abierta pero no el bloque de la cuenta: el FF1BF si
    anotar("   BODA: %s pasa el permiso de reserva a su pareja" % _nick(con))
    return True


# ---------------------------------------------------------------------------------------------------------------------------------
# Step3 (estados 6 / 7): reservar la fecha. LEIDO en el exe (ficha 113; direcciones en BODA_LECTURA.md): el dia se elige en una lista y el cliente manda FF1C5
# `[u64 {u16 anio, u8 mes, u8 dia, 0, 0, 0}]`; el S2C FF1C5 `[u8 res][u8 n][n x {u8, u8 b}]` (0x02831b70) llama por CADA fila i a 0x00bb81a0(i, b): el boton de la hora i
# (48 de media hora, 00:00 a 23:30) queda habilitado si b == 0 y apagado si no (la i es la POSICION en la lista; el primer byte de cada par se lee y se tira); res 1 -> texto 1415.
# Al elegir la hora el cliente manda FF1DB `[u64 fecha][u8 hora]` (solo si bloque+0x3c es mi usn: si no, texto 3386); el S2C FF1DB `[u8 n][n x {u8 sala, u8 b}]` (0x028388a0)
# llama a 0x00bb82c0(sala, b): la sala queda disponible si b == 0 y apagada si b == 1. Al confirmar (cartel 1605) manda FF1C6 `[u64 fecha][u8][u8][u8]` y el S2C FF1C6 `[u8 cod]`
# (0x02832520): 0 -> texto 1417 "Reserva hecha", 1 y 3 -> 1421, 2 -> 1422, 4 -> 1423, 5 -> 1719 (la pareja reservo o cambio la fecha).
HORAS = 48                    # LEIDO: la grilla de Step3 tiene 48 botones, 00:00 .. 23:30
SALAS = 3                     # LEIDO: 3 salas (Check_Hall_%d, RoomJoin Check_Room_%d)
CMD_FECHAS, CMD_HORARIO, CMD_RESERVA, CMD_CANCELAR, CMD_EN_CURSO = 0x1C5, 0x1DB, 0x1C6, 0x1C7, 0x1DD
RES_RESERVA_OK, RES_RESERVA_FALTA_HORA, RES_RESERVA_NO, RES_RESERVA_PAREJA = 0, 2, 4, 5


def _fecha_de_u64(cuerpo8):
    """8 B -> (anio, mes, dia) o None si no es una fecha de calendario."""
    anio, mes, dia = struct.unpack_from("<HBB", cuerpo8, 0)
    try:
        import datetime
        datetime.date(anio, mes, dia)
    except ValueError:
        return None
    return anio, mes, dia


def _en_pasado(anio, mes, dia, hora):
    """True si la hora `hora` (0..47) de ese dia ya paso o es la de ahora, con el reloj del servidor (INVENTADO: cualquier fecha futura vale)."""
    import datetime
    limite = datetime.datetime(anio, mes, dia, hora // 2, 30 * (hora % 2))
    return limite <= datetime.datetime.now()


def _ocupadas(anio, mes, dia, excepto=None):
    """{(hora, sala)} con las salas ya reservadas por OTRAS parejas ese dia (INVENTADO: una sola boda por sala y hora). Mira las secciones `boda` en estado 7."""
    r = set()
    for usn, acc in _cta.todas().items():
        s = (acc or {}).get(SECCION) or {}
        f = s.get("fecha")
        if s.get("estado") != ESTADO_RESERVADO or not f or excepto in (int(usn), s.get("otro")):
            continue
        if tuple(f[:3]) == (anio, mes, dia):
            r.add((f[3] * 2 + f[4] // 30, int(s.get("sala", 3))))
    return r


def fechas(con, seq, cuerpo):
    """C2S FF1C5 `[u64 fecha]` -> S2C FF1C5 `[0][48][48 x {i, b}]`: b = 0 si la hora esta libre (alguna sala), 1 si ya paso o ya no queda sala (INVENTADO)."""
    if len(cuerpo) != 8 or not llave() or not llave("BODA_PREMIO"):
        return False
    d = _datos_de(con)
    f = _fecha_de_u64(cuerpo)
    anotar("   BODA: FF1C5 de %s: %s" % (_nick(con), f))
    if d is None or d[2].get("estado") not in (ESTADO_RESERVA, ESTADO_RESERVADO, 9) or f is None:
        con.mandar_interno(CMD_FECHAS, seq, bytes([1, 0]))
        return True
    ocup = _ocupadas(*f, excepto=d[0])
    filas = bytearray()
    for i in range(HORAS):
        llenas = sum(1 for s in range(SALAS) if (i, s) in ocup)
        filas += bytes([i, 1 if (_en_pasado(*f, i) or llenas >= SALAS) else 0])
    con.mandar_interno(CMD_FECHAS, seq, bytes([0, HORAS]) + bytes(filas))
    return True


def horario(con, seq, cuerpo):
    """C2S FF1DB `[u64 fecha][u8 hora]` -> S2C FF1DB `[3][3 x {sala, b}]`: b = 1 si la sala esta tomada esa hora (INVENTADO), 0 si no. Sin el permiso: n = 0 (el cliente
    pone 3386 si el permiso no es suyo; MEDIDO)."""
    if len(cuerpo) != 9 or not llave() or not llave("BODA_PREMIO"):
        return False
    d = _datos_de(con)
    f = _fecha_de_u64(cuerpo)
    hora = cuerpo[8]
    anotar("   BODA: FF1DB de %s: %s hora %d" % (_nick(con), f, hora))
    if d is None or f is None or hora >= HORAS or permiso_de(d[2]) != d[0] or d[2].get("estado") not in (ESTADO_RESERVA, ESTADO_RESERVADO, 9):
        con.mandar_interno(CMD_HORARIO, seq, bytes([0]))
        return True
    ocup = _ocupadas(*f, excepto=d[0])
    con.mandar_interno(CMD_HORARIO, seq, bytes([SALAS]) + b"".join(bytes([s, 1 if (hora, s) in ocup else 0]) for s in range(SALAS)))
    return True


def reservar(con, seq, cuerpo):
    """C2S FF1C6 `[u64 fecha][u8][u8][u8]` (LEIDO 0x02832020): reserva fecha, hora, sala y privacidad. Con el permiso, en estado 6 (o 7: cambiar la fecha), hora futura y
    sala libre ese dia y hora; guarda en la seccion `boda` de las DOS cuentas la fecha (+0x51), la sala (+0x74) y la privacidad (+0x73), pasa a estado 7, S2C FF1C6 `[0]` al
    que reserva y `[5]` a la pareja (HIPOTESIS: es el cartel 1719 de la pareja), y FF1BF con el bloque a los dos."""
    if len(cuerpo) != 11 or not llave() or not llave("BODA_PREMIO"):
        return False
    d = _datos_de(con)
    f = _fecha_de_u64(cuerpo[:8])
    a, b, c = cuerpo[8], cuerpo[9], cuerpo[10]
    anotar("   BODA: FF1C6 de %s (%s): %s, bytes %d %d %d" % (_nick(con), cuerpo.hex(" "), f, a, b, c))
    return _reservar(con, seq, d, f, (a, b, c))


def _reservar(con, seq, d, f, abc):
    """Aca se interpreta `abc`: ver BODA_LECTURA.md (ficha 113: que es cada byte)."""
    hora, sala, privado = abc[CAMPO_HORA], abc[CAMPO_SALA], abc[CAMPO_PRIVADO]
    if d is None or f is None or privado > 1:
        con.mandar_interno(CMD_RESERVA, seq, bytes([RES_RESERVA_NO]))
        return True
    yo, otro, s = d
    if permiso_de(s) != yo or s.get("estado") not in (ESTADO_RESERVA, ESTADO_RESERVADO) or hora >= HORAS or sala >= SALAS:
        con.mandar_interno(CMD_RESERVA, seq, bytes([RES_RESERVA_NO]))
        anotar("   BODA: FF1C6 rechazado (permiso, estado, hora %d o sala %d)" % (hora, sala))
        return True
    if _en_pasado(*f, hora):
        con.mandar_interno(CMD_RESERVA, seq, bytes([RES_RESERVA_NO]))
        anotar("   BODA: FF1C6 rechazado: esa hora ya paso")
        return True

    def g(dd):
        cu = dd["cuentas"]
        sy = (cu.get(str(yo)) or {}).get(SECCION) or {}
        o2, _so = _pareja_vigente(cu, yo, sy)
        if o2 is None or (hora, sala) in _ocupadas_en(cu, f, yo):
            return "esa sala y hora ya estan tomadas"
        fecha = [f[0], f[1], f[2], hora // 2, 30 * (hora % 2), 0]
        for u in (yo, otro):
            cu[str(u)][SECCION].update({"estado": ESTADO_RESERVADO, "fecha": fecha, "sala": sala, "privado": privado, "reservado_por": yo})
            cu[str(u)][SECCION].pop("entro", None)
        return None
    with candado():
        motivo = _cta.cambiar_todas(g)
    if motivo is not None:
        con.mandar_interno(CMD_RESERVA, seq, bytes([1]))
        anotar("   BODA: FF1C6 rechazado: %s" % motivo)
        return True
    con.mandar_interno(CMD_RESERVA, seq, bytes([RES_RESERVA_OK]))
    c2 = _conectado(otro)
    if c2 is not None:
        c2.mandar_interno(CMD_RESERVA, 0, bytes([RES_RESERVA_PAREJA]))
    _mandar_ff1bf(yo)
    _mandar_ff1bf(otro)
    anotar("   BODA: %s reserva %s hora %d sala %d (privado %d): las dos cuentas pasan a estado %d (reservado)" % (_nick(con), f, hora, sala, privado, ESTADO_RESERVADO))
    return True


def _ocupadas_en(cu, f, yo):
    """Como _ocupadas pero sobre el diccionario de cuentas de cuenta.cambiar_todas (dentro del candado)."""
    r = set()
    for usn, acc in cu.items():
        s = (acc or {}).get(SECCION) or {}
        fe = s.get("fecha")
        if s.get("estado") != ESTADO_RESERVADO or not fe or yo in (int(usn), s.get("otro")):
            continue
        if tuple(fe[:3]) == tuple(f):
            r.add((fe[3] * 2 + fe[4] // 30, int(s.get("sala", 3))))
    return r


def cancelar(con, seq, cuerpo):
    """C2S FF1C7 (0 B, boton 取消预约, cartel 1606): cancela la reserva. S2C FF1C7 `[u8]` (LEIDO 0x02832b80: 0 = el cliente reinicia Step3 (0x00bb71f0); 1, 2, 3, 4 -> textos
    0x58e / 0x590 / 0x591 / 0x6bf). INVENTADO: cualquiera de los dos, en estado 7, vuelve a 6 (la fecha, la sala y la privacidad se borran) en las dos cuentas; FF1BF a los dos."""
    if cuerpo or not llave() or not llave("BODA_PREMIO"):
        return False
    d = _datos_de(con)
    if d is None or d[2].get("estado") != ESTADO_RESERVADO:
        con.mandar_interno(CMD_CANCELAR, seq, bytes([1]))
        anotar("   BODA: FF1C7 de %s rechazado (sin reserva)" % _nick(con))
        return True
    yo, otro, _s = d

    def g(dd):
        cu = dd["cuentas"]
        for u in (yo, otro):
            sec = cu[str(u)][SECCION]
            sec["estado"] = ESTADO_RESERVA
            for k in ("fecha", "sala", "privado", "reservado_por", "entro"):
                sec.pop(k, None)
    with candado():
        _cta.cambiar_todas(g)
    con.mandar_interno(CMD_CANCELAR, seq, bytes([0]))
    c2 = _conectado(otro)
    if c2 is not None:
        c2.mandar_interno(CMD_CANCELAR, 0, bytes([4]))           # res 4 -> texto 1727 "la pareja cancelo el programa de la boda" (LEIDO 0x02832d20: push 0x6bf)
    _mandar_ff1bf(yo)
    _mandar_ff1bf(otro)
    anotar("   BODA: %s cancela la reserva: las dos cuentas vuelven a estado %d" % (_nick(con), ESTADO_RESERVA))
    return True


def en_curso(con, seq, cuerpo):
    """C2S FF1DD (0 B, boton 进入婚礼场 de Step3 con estado 7, LEIDO 0x00bb6e82 -> SendWeddingIsProgress): "¿hay una boda en curso para mi?". S2C FF1DD `[u8]`: 0 -> texto 1454
    "Ahora no es el momento de celebrar la boda" (LEIDO 0x028398b0); distinto de 0 el cliente cambia de canal o manda FF1DC / FF14. INVENTADO: siempre 0 (la ceremonia y el
    salon son de la ficha siguiente), para que el boton no deje al jugador esperando una respuesta."""
    if cuerpo or not llave() or not llave("BODA_PREMIO"):
        return False
    d = _datos_de(con)
    if d is None or d[2].get("estado") != ESTADO_RESERVADO:
        return False
    if llave("BODA_SALON") and momento(d[2]) == 0:        # ficha 114: dentro de la ventana de entrada (INVENTADA, ver `ventana_min`) el salon esta abierto
        con.mandar_interno(CMD_EN_CURSO, seq, bytes([1]))
        anotar("   BODA: FF1DD de %s: hay ceremonia (S2C [1])" % _nick(con))
        return True
    con.mandar_interno(CMD_EN_CURSO, seq, bytes([0]))
    anotar("   BODA: FF1DD de %s: todavia no hay ceremonia (S2C [0], texto 1454)" % _nick(con))
    return True


# ---------------------------------------------------------------------------------------------------------------------------------
# Ficha 114: PASO 4 = entrar al salon el dia y la hora reservados (llave BODA_SALON). LEIDO en el exe (BODA_LECTURA.md "Medido con el juego, ficha 114"):
# C2S FF1DC (0 B, SendWeddingSlotInfoListGet 0x02838d00) -> S2C FF1DC [u8 n][n x 66 B] (0x028390e0; el cliente usa 3 filas: Check_Room_%d); fila: +0 u32 usn A,
# +0x11 u32 usn B, +0x33 u8 VIP (0 = sala normal), +0x34 u8 (0 = el boton Check_Room_i queda habilitado, si no solo para los novios, 0x00bb102b..0x00bb1089);
# C2S FF1C8 [u8 sala] (0x028333f0) -> S2C FF1C8 [u16][u8 cod][u8 canal] (0x02833600): 0x40 -> cartel 1431 (sin entrada), 0x41 -> 1432 (no es la hora), 0x3f -> 1433
# (llena), cod <= 0x28 entra (cod = ESCENA: 0x26 / 0x27 son las de boda, 0x00a3829a).
TICKET = 11000102                       # LEIDO: el cliente NO lo mira (0x00b6...); lo dice el servidor con FF1C8 cod 0x40
COD_SIN_TICKET, COD_NO_ES_HORA, COD_LLENO = 0x40, 0x41, 0x3F
CANAL_SALON = 5
ASIENTO_A, ASIENTO_B = 0x26, 0x27       # LEIDO 0x02834624 / 0x0283468c (FF1C9: la 1.a entrada es el asiento 0x26, la 2.a el 0x27) y 0x00523735: el cod del FF1C8 es el ASIENTO del
                                        # que entra ([[0x3a7cf54]+0x14], u8, 0x02833881; <= 0x28) y los novios se sientan en el 0x26 y el 0x27 (INVENTADO: el de menor usn en el 0x26)
FILA = 66
CMD_SALA_FILAS, CMD_SALA_ENTRAR = 0x1DC, 0x1C8


def ventana_min():
    """(minutos antes, minutos despues) de la fecha reservada en que el salon esta abierto. INVENTADO: 10 antes (el cliente 2013 / oficial no se leyo);
    30 despues = LEIDO: la escena de boda (0x26 / 0x27) calcula la hora de FIN como fecha + 0x1e minutos (0x00a382bc). Se puede cambiar con BODA_VENTANA="a,d"."""
    try:
        a, d = os.environ.get("BODA_VENTANA", "10,30").split(",")
        return int(a), int(d)
    except ValueError:
        return 10, 30


def momento(s, ahora=None):
    """-1 si todavia no es la hora del salon, 0 dentro de la ventana, 1 si ya paso. `s` = seccion `boda` con `fecha` (reloj del servidor = hora real)."""
    import datetime
    f = s.get("fecha")
    if not f:
        return 1
    ahora = ahora or datetime.datetime.now()
    ini = datetime.datetime(f[0], f[1], f[2], f[3], f[4], f[5] if len(f) > 5 else 0)
    a, d = ventana_min()
    if ahora < ini - datetime.timedelta(minutes=a):
        return -1
    if ahora > ini + datetime.timedelta(minutes=d):
        return 1
    return 0


def _fila(a=0, b=0, cerrada=1):
    """Una fila de 66 B de FF1DC. a / b = usn de los novios (0 = salon vacio, el cliente no ofrece el boton). `cerrada` = +0x34 (INVENTADO 1: solo los novios
    pueden entrar; los invitados no estan hechos). Los apodos (+4 y +0x15, HIPOTESIS) y el resto quedan en 0: el cliente no los lee."""
    f = bytearray(FILA)
    struct.pack_into("<I", f, 0x00, a)
    struct.pack_into("<I", f, 0x11, b)
    f[0x34] = cerrada
    return bytes(f)


def _parejas_en_hora():
    """{sala: (usnA, usnB)} de las bodas reservadas (estado 7) cuya ventana esta abierta ahora (si dos coinciden en la misma sala, la de fecha mas temprana)."""
    r = {}
    for usn, acc in sorted(_cta.todas().items(), key=lambda kv: (((kv[1] or {}).get(SECCION) or {}).get("fecha") or [0])):
        s = (acc or {}).get(SECCION) or {}
        otro = s.get("otro")
        if s.get("estado") != ESTADO_RESERVADO or otro is None or int(usn) > int(otro) or momento(s) != 0:
            continue
        r.setdefault(int(s.get("sala", 3)), (int(usn), int(otro)))
    return r


def filas(con, seq, cuerpo):
    """C2S FF1DC (0 B) -> S2C FF1DC [3][3 x 66 B]: una fila por salon; con novios (usn A y B) si hay una boda reservada en esa sala con la ventana abierta ahora."""
    if cuerpo or not llave() or not llave("BODA_SALON"):
        return False
    pp = _parejas_en_hora()
    out = bytearray([SALAS])
    for i in range(SALAS):
        a, b = pp.get(i, (0, 0))
        out += _fila(a, b)
    con.mandar_interno(CMD_SALA_FILAS, seq, bytes(out))
    anotar("   BODA: FF1DC de %s: filas %s" % (_nick(con), {i: v for i, v in pp.items()} or "todas vacias"))
    return True


def _asiento_de(yo, otro):
    """Asiento 0x26 para el novio de menor usn, 0x27 para el otro (INVENTADO el orden; LEIDO que son esos dos)."""
    return ASIENTO_A if yo < otro else ASIENTO_B


def entrar_sala(con, seq, cuerpo):
    """C2S FF1C8 [u8 sala] -> S2C FF1C8 [u16 0][u8 cod][u8 canal]. Solo los novios, en su sala, dentro de la ventana y con el ticket 11000102 en la mochila (INVENTADO que lo
    exigen los dos y que no se gasta); 0x41 fuera de hora o sin boda reservada, 0x40 sin ticket."""
    if len(cuerpo) != 1 or not llave() or not llave("BODA_SALON"):
        return False
    d = _datos_de(con)
    yo = _usn(con)
    sala = cuerpo[0]
    anotar("   BODA: FF1C8 de %s: sala %d" % (_nick(con), sala))

    def r(cod, canal=0):
        con.mandar_interno(CMD_SALA_ENTRAR, seq, struct.pack("<HBB", 0, cod, canal))
    if d is None or d[2].get("estado") != ESTADO_RESERVADO or int(d[2].get("sala", 3)) != sala or momento(d[2]) != 0:
        r(COD_NO_ES_HORA)
        anotar("   BODA: FF1C8 -> 0x41 (no es la hora o no es su sala)")
        return True
    if not tiene_objeto(yo, TICKET):
        r(COD_SIN_TICKET)
        anotar("   BODA: FF1C8 -> 0x40 (sin el ticket %d)" % TICKET)
        return True
    asiento = _asiento_de(yo, d[1])
    _marcar_entrada(yo, d[1], d[2])
    con.salon_boda = sala                  # MEDIDO ficha 114: tras el FF1C8 el cliente pide FF246 vip.info, FF15 y FF0C; con los de una sala de carrera se CIERRA solo
    def ff0f_ff61():
        # MEDIDO: sin FF0F + FF61 el cliente se CIERRA SOLO (lectura nula en 0x029ae663) ~1 s despues del FF0C; el FF1C8 deja el estado del cuarto en 8 y un FF0F que llegue DESPUES lo
        # vuelve a 4 (el ciclo de la ceremonia, 0x008417d7, solo corre con 8): por eso van ANTES del FF1C8. HIPOTESIS: el A, el asiento y el u32.
        import casa
        slot = asiento
        con.mandar_interno(0x0F, seq, bytes([slot, CANAL_SALON, 0, 0]))
        con.mandar_interno(0x61, seq, casa.ff61((CANAL_SALON << 11) | (0x100 + sala), slot, CANAL_SALON, yo))
        anotar("   BODA: S2C FF0F + FF61 del salon (asiento %d, tipo %d)" % (slot, CANAL_SALON))
    ff0f_ff61()
    r(asiento, CANAL_SALON)
    anotar("   BODA: FF1C8 -> asiento 0x%X canal %d" % (asiento, CANAL_SALON))
    return True


def _marcar_entrada(yo, otro, s):
    """INVENTADO: guarda en la seccion `boda` de `yo` que entro al salon (`entro`: hora) y programa el cierre de la sala a las fecha + `despues` minutos (LEIDO: el cartel del final
    dice "al cerrar la sala a las hh:mm quedaran registrados como matrimonio", con hh:mm = fecha + 30 min, 0x00a382bc)."""
    import datetime
    with candado():
        _cta.cambiar_seccion(str(yo), SECCION, lambda sec: sec.update(entro=time.time()) if sec else None)
    f = s.get("fecha")
    ini = datetime.datetime(f[0], f[1], f[2], f[3], f[4], f[5] if len(f) > 5 else 0)
    fin = ini + datetime.timedelta(minutes=ventana_min()[1])
    clave = (min(yo, otro), tuple(f))
    hechos = getattr(estado, "BODA_CIERRES", None)
    if hechos is None:
        hechos = estado.BODA_CIERRES = set()
    if clave not in hechos:
        hechos.add(clave)
        estado.mas_tarde(max(1.0, (fin - datetime.datetime.now()).total_seconds() + 2), "boda.cerrar_salon", yo)


def cerrar_si_toca(usn):
    """Cierra la sala de la boda de `usn` SI ya paso su hora y los DOS novios entraron: estado 8 (casados) en las dos cuentas, con UN candado. True si cerro ahora."""
    d = _datos_de_usn(usn)
    if d is None or d[2].get("estado") != ESTADO_RESERVADO or momento(d[2]) != 1:
        return False
    yo, otro, _s = d

    def g(dd):
        cu = dd["cuentas"]
        sy = (cu.get(str(yo)) or {}).get(SECCION) or {}
        o2, so = _pareja_vigente(cu, yo, sy)
        if o2 is None or sy.get("estado") != ESTADO_RESERVADO or so.get("estado") != ESTADO_RESERVADO or not (sy.get("entro") and so.get("entro")):
            return "no"
        for u in (yo, otro):
            cu[str(u)][SECCION]["estado"] = ESTADO_CASADOS
        return None
    with candado():
        r = _cta.cambiar_todas(g)
    if r is not None:
        return False
    anotar("   BODA: la sala cerro: %s y %s quedan CASADOS (estado %d en las dos cuentas)" % (yo, otro, ESTADO_CASADOS))
    return True


def cerrar_salon(usn):
    """Temporizador (estado.mas_tarde): a la hora de cierre, casa a la pareja y avisa con FF1BF a los que esten conectados."""
    d = _datos_de_usn(usn)
    if d is None:
        return
    if cerrar_si_toca(usn):
        _mandar_ff1bf(d[0])
        _mandar_ff1bf(d[1])
        if casados_activo():                                  # ficha 117: el registro tipo 1 de la pareja ya trae la fecha de la boda (结婚纪念日)
            social.pareja_al_mensajero(d[0], d[1])


def _datos_de_usn(usn):
    s = datos_boda(usn)
    otro = _pareja_de(usn)
    return (usn, otro, s) if s and otro is not None else None


def _sala_datos(con):
    """Una Sala de DATOS (no se registra en estado.SALAS: no es una sala de carrera) para armar el FF15 / FF0C con las funciones de salas.py, como casa.py: los
    novios conectados que estan en el salon, canal 5 (el del FF1C8). El titulo va vacio (no se sabe cual poner)."""
    import estado as _e
    idx = con.salon_boda
    d = _datos_de(con)
    # MEDIDO: con DOS novios en la lista del FF0C el cliente se cierra solo (EIP 0x029ae663, la misma lectura nula); con UNO (el propio, en su asiento 0x26 o 0x27) no. El otro novio
    # lo dibuja el FF1C9. Por eso cada uno ve solo su propio asiento en el FF0C.
    sala = _e.Sala(0x100 + idx, {"modo": 0, "titulo": b"", "clave": b""}, con, CANAL_SALON)
    sala.asientos = {_asiento_de(_usn(con), d[1]): con}
    sala.orden = tuple(sala.asientos)
    sala.max = 2
    return sala


def pedido_de_sala(con, seq, cmd):
    """C2S FF15 (info de sala) / FF0C (lista de jugadores) estando en el salon: se contestan con las funciones de salas.py sobre una Sala de datos (lo llama casa.py)."""
    import salas
    sala = _sala_datos(con)
    if cmd == 0x15:
        base = next((cu for c, _s, cu in salas._plantilla() if c == 0x15), None)
        con.mandar_interno(0x15, seq, salas.ff15_para(base, sala))
    else:
        con.mandar_interno(0x0C, seq, salas.ff0c(sala, con))
    anotar("   BODA: S2C FF%X del salon %d (%d en el salon)" % (cmd, con.salon_boda, len(sala.asientos)))
    if cmd == 0x0C:
        _empezar_para(con)
    return True


def _entrada_ff1c9(usn):
    """Una entrada del S2C FF1C9 (LEIDO 0x02833960, layout en layouts/FF1C9.md): [u32 #2][u32 #3][u8 #4][44 B = 11 u32 de prendas (el cliente las reparte por la categoria del
    codigo: los 3 primeros digitos de `%08d`)][u32 #6][u32 #7][u32 #8][u16 L][apodo][u8 #11][u16 m][m x u32]. INVENTADO / HIPOTESIS el significado de cada numero: #2 = usn, el resto en 0."""
    c = _cta.leer(usn) or {}
    partes = ((c.get("personaje") or {}).get("partes") or [])[:11]
    nick = social._gbk((c.get("cuenta") or {}).get("nick") or "", 12)
    return (struct.pack("<IIB", usn, 0, 0) + struct.pack("<11I", *(list(partes) + [0] * (11 - len(partes)))) + struct.pack("<III", 0, 0, 0)
            + struct.pack("<H", len(nick)) + nick + bytes([0]) + struct.pack("<H", 0))


def _empezar_para(con):
    """La ceremonia empieza a la HORA de la boda (INVENTADO: la fecha reservada; antes de esa hora se espera en el salon): si ya es la hora se manda ahora, si no se
    programa para la hora (estado.mas_tarde). Un solo FF1C9 + FF1CA por entrada."""
    import datetime
    d = _datos_de(con)
    if d is None or getattr(con, "boda_empezada", None) == tuple(d[2].get("fecha") or ()):
        return
    f = d[2]["fecha"]
    ini = datetime.datetime(f[0], f[1], f[2], f[3], f[4], f[5] if len(f) > 5 else 0)
    falta = (ini - datetime.datetime.now()).total_seconds()
    if falta > 1:
        estado.mas_tarde(falta, "boda.empezar_con", _usn(con), tuple(f))
        anotar("   BODA: la ceremonia de %s empieza a las %02d:%02d (en %d s)" % (_nick(con), f[3], f[4], falta))
    else:
        empezar_con(_usn(con), tuple(f))


def empezar_con(usn, f):
    """Manda a `usn` (si sigue en el salon) FF1C9 (los dos novios: HIPOTESIS el contenido) y FF1CA (empieza: LEIDO sin datos). El cliente corre solo toda la ceremonia (~4 min)."""
    con = _conectado(usn)
    d = _datos_de(con) if con is not None else None
    if con is None or d is None or getattr(con, "salon_boda", None) is None or tuple(d[2].get("fecha") or ()) != tuple(f) or getattr(con, "boda_empezada", None) == tuple(f):
        return
    con.boda_empezada = tuple(f)
    a, b = sorted((d[0], d[1]))
    con.mandar_interno(0x1C9, 0, bytes([2]) + _entrada_ff1c9(a) + _entrada_ff1c9(b))
    con.mandar_interno(0x1CA, 0, b"")
    anotar("   BODA: S2C FF1C9 (los 2 novios) + FF1CA a %s: empieza la ceremonia (la corre el cliente)" % _nick(con))


def salir_14(con, seq, cuerpo):
    """C2S FF14 estando en el salon (lo llama casa.py): se contesta 0000 como al salir de la casa (MEDIDO: la flecha manda FF181, FF14, FF181)."""
    con.salon_boda = None
    con.boda_empezada = None
    con.mandar_interno(0x14, seq, struct.pack("<H", 0))
    anotar("   BODA: S2C FF14 0000: %s sale del salon" % _nick(con))
    return True


CAMPO_HORA, CAMPO_PRIVADO, CAMPO_SALA = 0, 1, 2      # MEDIDO ficha 113 (3 variantes con el juego): FF1C6 = [u64 fecha][u8 hora 0..47 (= el byte 4 del u64)][u8 privacidad 0 publica / 1 privada][u8 sala 0..2]


# ---------------------------------------------------------------------------------------------------------------------------------
# Ficha 117: LA VIDA DE CASADOS = el calendario (夫妻日历), el aniversario (结婚纪念日) y el DIVORCIO (llave BODA_CASADOS, 1 por omision desde el cierre de la ficha 117: calendario, aniversario y los dos divorcios se vieron en las dos copias y se volvio a pedir matrimonio con la interfaz).
# LEIDO en el exe (BODA_LECTURA.md "Lectura estatica de la ficha 117"; direcciones VA):
#  * C2S FF1D2 (0 B, BTN_부부캘린더 0x008741d8) -> S2C FF1D2 [u16 a][u16 b][u32 n][n x 15 B] (0x02835db0); con a = 0, b = 0, n = 0 abre la ventana vacia sin fallar y solo
#    sale si el bloque de la CUENTA tiene +0x22 == 8. Los premios los manda el servidor (no hay tabla en el cliente): INVENTADO nada, calendario VACIO.
#  * Divorcio unilateral C2S FF1D0 (0 B, cartel 1203 "cuesta 500 G") -> S2C FF1D0 [1] = cartel 1441 "estado del matrimonio no activo", [2] = cartel en blanco.
#    Mutuo C2S FF1CE (0 B, cartel 1204 "cada uno pierde 10000 monedas") -> S2C FF1CE [0] = Si/No para el OTRO (1435), [1] desconectado (1436), [2] estado incompleto (1437),
#    [3] y [4] "enviaste la solicitud" (1438), [5] sin monedas el que pide (1439), [6] sin monedas el otro (1440); el otro contesta C2S FF1CF [1 acepta | 2 rechaza] ->
#    S2C FF1CF [2] = 1654 "tu pareja rechazo", [3] = 1436 desconectado, [1] nada. NINGUNO de esos S2C toca el bloque ni la pareja: quien TERMINA el divorcio es FF40 0A 07 (al otro)
#    y 0A 0B (al que rompe) con el usn del otro: con el bloque en estado 8 el cliente muestra 1330 "Divorcio completado" y, solo, se pone el bloque de boda por defecto (estado 0),
#    cierra la ventana de boda, borra la pareja y la saca del mensajero. O sea: DIVORCIARSE TAMBIEN SEPARA la pareja, y CUALQUIER 0A 07 / 0A 0B borra la boda en el cliente.
#  * Costos: el cliente no compara ni descuenta nada. "RC" del castellano = 金币 = el G de la barra (MEDIDO fichas 45 y 65). INVENTADO: el "G币" de la unilateral = tambien el G.
# INVENTADO (marcado): 500 G la unilateral y 10000 G cada uno la mutua, cobrados al CERRAR (la mutua valida a los dos al pedir Y al aceptar); el unilateral sin saldo se avisa con el FF1CE [5]
#  (1439 "no tienes suficientes monedas": FF1D0 no tiene codigo con texto); el mutuo solo si los dos estan conectados; el que pidio recibe el 0A 0B; el aniversario = el dia de la boda
#  reservada (`fecha`) en el registro de 97 B tipo 1 del mensajero (+0x3e, texto AAAAMMDD, LEIDO 0x00871ec1 / 0x02732c60); el 玩伴纪念日 (+0x2f) queda vacio (no guardamos desde cuando son pareja).
CMD_DIV_MUTUO, CMD_DIV_RESP, CMD_DIV_UNI, CMD_CALENDARIO = 0x1CE, 0x1CF, 0x1D0, 0x1D2
COSTO_UNILATERAL, COSTO_MUTUO = 500, 10000
RES_MUTUO_PIDE, RES_MUTUO_DESCONECTADO, RES_MUTUO_ESTADO, RES_MUTUO_ENVIADA, RES_MUTUO_SIN_MI, RES_MUTUO_SIN_OTRO = 0, 1, 2, 3, 5, 6
RES_RESP_RECHAZO, RES_RESP_DESCONECTADO = 2, 3
RES_UNI_ESTADO = 1


def casados_activo():
    return llave() and llave("BODA_CASADOS")


def divorcios():
    """{usn del que pidio el divorcio MUTUO: {"otro": usn, "hora": t}} (memoria; sobrevive a las recargas)."""
    if not hasattr(estado, "DIVORCIOS_BODA"):
        estado.DIVORCIOS_BODA = {}
    return estado.DIVORCIOS_BODA


def aniversario(usn_a, usn_b):
    """Texto AAAAMMDD (8 B ASCII, LEIDO 0x02732c60) del dia de la boda de la pareja a-b si estan CASADOS (estado 8) y la boda vale; si no b"". Solo con BODA_CASADOS."""
    if not casados_activo():
        return b""
    s = datos_boda(usn_a)
    if not s or s.get("estado") != ESTADO_CASADOS or s.get("otro") != usn_b or not s.get("fecha"):
        return b""
    f = s["fecha"]
    return ("%04d%02d%02d" % (f[0], f[1], f[2])).encode()


def casados(usn):
    """El usn de la pareja si esa cuenta esta CASADA (estado 8, boda vigente), si no None."""
    est, _m = guardado(usn)
    return _pareja_de(usn) if est == ESTADO_CASADOS else None


def calendario(con, seq, cuerpo):
    """C2S FF1D2 (0 B) -> S2C FF1D2 [u16 a = 0][u16 b = 0][u32 n = 0]: el calendario de casados abre VACIO (LEIDO 0x02835db0; sin premios inventados). Solo con estado 8: con otro
    estado el cliente abriria la ventana de ese estado (ficha 110: no usarlo), asi que sin boda vigente no se contesta."""
    yo = _usn(con)
    if cuerpo or yo is None or not casados_activo():
        return False
    if casados(yo) is None:
        anotar("   BODA: FF1D2 de %s pero no esta casado en el servidor: sin respuesta" % _nick(con))
        return True
    con.mandar_interno(CMD_CALENDARIO, seq, struct.pack("<HHI", 0, 0, 0))
    anotar("   BODA: FF1D2 de %s: calendario vacio (a=0, b=0, n=0)" % _nick(con))
    return True


def _saldo_g(acc):
    return int(((acc or {}).get("tienda") or {}).get("g", 0))


def _divorciar(a, b, costos):
    """UN candado: si a y b siguen CASADOS (estado 8 en las dos, pareja vigente) y cada uno tiene su costo en G ({usn: G}), lo cobra, y borra la boda Y la pareja de las dos cuentas.
    -> None si salio bien, o el motivo ("estado" / "sin saldo a" / "sin saldo b")."""
    def f(dd):
        cu = dd["cuentas"]
        if str(a) not in cu or str(b) not in cu:
            return "estado"
        sa, sb = cu[str(a)].get(SECCION) or {}, cu[str(b)].get(SECCION) or {}
        if (sa.get("estado") != ESTADO_CASADOS or sb.get("estado") != ESTADO_CASADOS or sa.get("otro") != b or sb.get("otro") != a
                or (cu[str(a)].get("pareja") or {}).get("usn") != b or (cu[str(b)].get("pareja") or {}).get("usn") != a):
            return "estado"
        for u, nombre in ((a, "sin saldo a"), (b, "sin saldo b")):
            if _saldo_g(cu[str(u)]) < costos.get(u, 0):
                return nombre
        for u in (a, b):
            if costos.get(u):
                cu[str(u)]["tienda"]["g"] = _saldo_g(cu[str(u)]) - costos[u]
            cu[str(u)][SECCION] = {}
            cu[str(u)]["pareja"] = {}
        return None
    with candado():
        return _cta.cambiar_todas(f)


def _terminar(rompe, otro):
    """Tras _divorciar: FF40 0A 0B [usn del otro] al que rompe y 0A 07 [usn del que rompe] al otro, si esta conectado (LEIDO: con estado 8 los dos clientes muestran 1330 y borran
    boda, pareja e icono por su cuenta). Sin FF1BF antes (el 1330 solo sale si el cliente aun tiene estado 8)."""
    c = _conectado(rompe)
    if c is not None:
        c.mandar_interno(0x40, 0, bytes([0x0A, 0x0B]) + struct.pack("<I", otro))
    c = _conectado(otro)
    if c is not None:
        c.mandar_interno(0x40, 0, bytes([0x0A, 0x07]) + struct.pack("<I", rompe))


def divorcio_unilateral(con, seq, cuerpo):
    """C2S FF1D0 (0 B): cobra 500 G (INVENTADO la moneda) al que pide y separa a la pareja y borra la boda en las dos cuentas (un candado), esten conectadas o no. Estado no 8: S2C FF1D0 [1]
    (cartel 1441); sin saldo: S2C FF1CE [5] (cartel 1439, INVENTADO el uso: FF1D0 no tiene un codigo con texto de monedas)."""
    yo = _usn(con)
    if cuerpo or yo is None or not casados_activo():
        return False
    otro = casados(yo)
    anotar("   BODA: FF1D0 (divorcio unilateral) de %s" % _nick(con))
    if otro is None:
        con.mandar_interno(CMD_DIV_UNI, seq, bytes([RES_UNI_ESTADO]))
        anotar("   BODA: FF1D0 -> res 1 (no esta casado: cartel 1441)")
        return True
    motivo = _divorciar(yo, otro, {yo: COSTO_UNILATERAL})
    if motivo is not None:
        if motivo == "estado":
            con.mandar_interno(CMD_DIV_UNI, seq, bytes([RES_UNI_ESTADO]))
        else:
            con.mandar_interno(CMD_DIV_MUTUO, seq, bytes([RES_MUTUO_SIN_MI]))
        anotar("   BODA: FF1D0 rechazado: %s" % motivo)
        return True
    separadas(yo, otro)
    _terminar(yo, otro)
    _saldos_al_dia(yo, g=True)                                  # ficha 131: el que pago ve su G nuevo
    anotar("   BODA: divorcio unilateral: %s paga %d G; la boda y la pareja de %d y %d borradas (0A 0B / 0A 07)" % (_nick(con), COSTO_UNILATERAL, yo, otro))
    return True


def divorcio_mutuo(con, seq, cuerpo):
    """C2S FF1CE (0 B): pide el divorcio de mutuo acuerdo. El otro conectado: S2C FF1CE [3] al que pide (1438) y [0] al otro (Si / No, 1435). Desconectado [1], estado [2], sin monedas
    el que pide [5] o el otro [6] (cada uno con 10000 G, INVENTADO el momento: al pedir)."""
    yo = _usn(con)
    if cuerpo or yo is None or not casados_activo():
        return False
    otro = casados(yo)
    anotar("   BODA: FF1CE (divorcio mutuo) de %s" % _nick(con))

    def r(res):
        con.mandar_interno(CMD_DIV_MUTUO, seq, bytes([res]))
    if otro is None:
        r(RES_MUTUO_ESTADO)
        anotar("   BODA: FF1CE -> res 2 (no esta casado)")
        return True
    c2 = _conectado(otro)
    if c2 is None:
        r(RES_MUTUO_DESCONECTADO)
        anotar("   BODA: FF1CE -> res 1 (el otro no esta conectado)")
        return True
    cuentas = _cta.todas()
    if _saldo_g(cuentas.get(str(yo))) < COSTO_MUTUO:
        r(RES_MUTUO_SIN_MI)
        anotar("   BODA: FF1CE -> res 5 (%s no tiene %d G)" % (_nick(con), COSTO_MUTUO))
        return True
    if _saldo_g(cuentas.get(str(otro))) < COSTO_MUTUO:
        r(RES_MUTUO_SIN_OTRO)
        anotar("   BODA: FF1CE -> res 6 (el otro no tiene %d G)" % COSTO_MUTUO)
        return True
    with candado():
        divorcios()[yo] = {"otro": otro, "hora": time.time()}
    r(RES_MUTUO_ENVIADA)
    c2.mandar_interno(CMD_DIV_MUTUO, 0, bytes([RES_MUTUO_PIDE]))
    anotar("   BODA: FF1CE -> res 3 a %s y res 0 (Si / No) a %s" % (_nick(con), _nick(c2)))
    return True


def divorcio_respuesta(con, seq, cuerpo):
    """C2S FF1CF [u8 1 = acepta | 2 = rechaza] del que recibio el Si / No. 1: cobra 10000 G a cada uno (si los dos siguen con saldo y casados) y separa + borra la boda (un candado);
    2: S2C FF1CF [2] al que pidio (1654). Si el que pidio ya no esta: S2C FF1CF [3] al que contesta (1436)."""
    yo = _usn(con)
    if len(cuerpo) != 1 or yo is None or not casados_activo():
        return False
    cod = cuerpo[0]
    with candado():
        a = next((u for u, p in divorcios().items() if p["otro"] == yo), None)
        if a is not None and cod in (1, 2):
            del divorcios()[a]
    if a is None or cod not in (1, 2):
        anotar("   BODA: %s contesta FF1CF %d pero no hay pedido de divorcio para el%s: nada" % (_nick(con), cod, "" if cod in (1, 2) else " (valor raro)"))
        return True
    pide = _conectado(a)
    if pide is None:
        con.mandar_interno(CMD_DIV_RESP, seq, bytes([RES_RESP_DESCONECTADO]))
        anotar("   BODA: FF1CF de %s: quien pidio ya no esta conectado (res 3)" % _nick(con))
        return True
    if cod == 2:
        pide.mandar_interno(CMD_DIV_RESP, 0, bytes([RES_RESP_RECHAZO]))
        anotar("   BODA: %s RECHAZA el divorcio de mutuo acuerdo de %s (nada cambia)" % (_nick(con), _nick(pide)))
        return True
    motivo = _divorciar(a, yo, {a: COSTO_MUTUO, yo: COSTO_MUTUO})
    if motivo is not None:
        if motivo == "estado":
            pide.mandar_interno(CMD_DIV_MUTUO, 0, bytes([RES_MUTUO_ESTADO]))
            con.mandar_interno(CMD_DIV_MUTUO, seq, bytes([RES_MUTUO_ESTADO]))
        else:
            sin_a = motivo == "sin saldo a"
            pide.mandar_interno(CMD_DIV_MUTUO, 0, bytes([RES_MUTUO_SIN_MI if sin_a else RES_MUTUO_SIN_OTRO]))
            con.mandar_interno(CMD_DIV_MUTUO, seq, bytes([RES_MUTUO_SIN_OTRO if sin_a else RES_MUTUO_SIN_MI]))
        anotar("   BODA: FF1CF acepta pero NO se divorcian: %s" % motivo)
        return True
    separadas(a, yo)
    _terminar(a, yo)
    _saldos_al_dia(a, g=True)                                   # ficha 131: los dos pagaron
    _saldos_al_dia(yo, g=True)
    anotar("   BODA: divorcio de mutuo acuerdo: %d y %d pagan %d G cada uno; boda y pareja borradas (0A 0B a %s, 0A 07 a %s)" % (a, yo, COSTO_MUTUO, _nick(pide), _nick(con)))
    return True


def separadas(a, b):
    """Llamado por social.py (y por el divorcio) cuando la pareja a-b SE SEPARO por cualquier camino: se olvidan los pedidos en memoria de esa pareja (el estado 1 de la boda y el divorcio
    mutuo pendiente). La seccion `boda` de las cuentas ya la borro el mismo candado que borro la pareja (social._cambiar_parejas / _divorciar). El cliente se resetea solo con el
    0A 07 / 0A 0B (LEIDO): no se manda FF1BF."""
    with candado():
        for u in [u for u, p in pedidos().items() if {u, p["otro"]} & {a, b}]:
            pedidos().pop(u, None)
        for u in [u for u, p in divorcios().items() if {u, p["otro"]} & {a, b}]:
            divorcios().pop(u, None)


def borrar_boda_de_las_que_cambian(dd, antes):
    """Para social._cambiar_parejas, DENTRO de su candado: `antes` = {usn: usn de su pareja antes}. Toda cuenta cuya pareja cambio (se separo, o la dejaron por otra) pierde la
    seccion `boda`, y la del que era su pareja tambien: el cliente borra la boda con CUALQUIER 0A 07 / 0A 0B (LEIDO 0x0279fef8 / 0x027a0079) y el servidor tiene que quedar igual
    (FICHA 117; antes la seccion quedaba y reaparecia si volvian a ser pareja). -> lista de las cuentas que perdieron una boda."""
    cu = dd["cuentas"]
    perdieron = []
    for k, a in cu.items():
        u = int(k)
        ahora = (a.get("pareja") or {}).get("usn")
        if antes.get(u) and ahora != antes[u]:
            for v in (u, antes[u]):
                x = cu.get(str(v))
                if x is not None and x.get(SECCION):
                    x[SECCION] = {}
                    perdieron.append(v)
    return perdieron


MANEJADORES = {
    CMD_USO: usar,
    CMD_RESPUESTA: responder,
    CMD_INFO: info,
    CMD_SALTAR: saltar,
    CMD_PREMIO: premio,
    CMD_CANJE: canjear,
    CMD_COMPRA: comprar,
    CMD_TRANSFERIR: transferir,
    CMD_FECHAS: fechas,
    CMD_HORARIO: horario,
    CMD_RESERVA: reservar,
    CMD_CANCELAR: cancelar,
    CMD_EN_CURSO: en_curso,
    CMD_SALA_FILAS: filas,
    CMD_SALA_ENTRAR: entrar_sala,
    CMD_CALENDARIO: calendario,
    CMD_DIV_UNI: divorcio_unilateral,
    CMD_DIV_MUTUO: divorcio_mutuo,
    CMD_DIV_RESP: divorcio_respuesta,
}
