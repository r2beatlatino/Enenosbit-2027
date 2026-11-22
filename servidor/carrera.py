# -*- coding: utf-8 -*-
r"""carrera.py (02-nov) — la CARRERA DE VARIOS del cliente de Steam (Fase 3). Contrato: notas 03 y 06 de S-2013.

Medido en Steam (02-nov): con el invitado listo y sin carteles abiertos, el START del anfitrion manda C2S FF24 (0 B,
SendStartGame 0x02769fe0; las condiciones del boton en 0x00a5da50, ver docs/PLAN_STEAM_COMPLETO.md). Lo que sigue sale
de la grabacion 213306 (el oficial, una carrera de 5) y de la nota 06:
  S2C FF25 LoadGame a TODOS: [u32 cantidad][cantidad x (u8 asiento, u32)][u32 magic][u16 mapa][u8 N][N x u16 cancion]
      (el oficial: `00000000 9d980000 3a00 01 300c` = 0 asientos, magic 0x989d, mapa 58, 1 cancion: 3120). N=0 mata al
      cliente. La magic es la misma para todos y cambia en cada carrera.
  cada uno pide FF57 (las notas; juego.py ya lo contesta con los charts 1 a 1) y avisa que cargo (⏳ el C2S se anota)
  S2C FF24 GO (0 B) a todos, UNA vez, cuando cargaron todos o a los 30 s (nota 03 §3)
  ⏳ en carrera (FF23 posicion, FF4E sincronia re-cifrada) y el cartel (FF28): de a uno, midiendo.
"""
import os
import random
import struct
import time

import ajustes
import captura
import estado
import neutro
import salas

ESPERA_GO = 30.0
MAPA = 58          # el de la grabacion (0x3a): ⏳ sin medir de donde lo elige el oficial


def anotar(txt):
    estado.anotar(txt)


def sala_de(con):
    return estado.SALAS.get(con.sala)


PRUEBAS = ajustes.RUTA_PRUEBAS


def pruebas():
    """2-nov: ajustes de PRUEBA, leidos en cada START (se cambian sin reiniciar): `datos/pruebas.json`, p. ej.
    {"cancion": 316, "canciones_coop": 1}. `cancion` = la de todas las carreras (316 无限挑战: de las mas cortas y la
    mas densa, 697 notas); `canciones_coop` = cuantas rondas del gorila (el 2013 juega 3). Sin archivo: lo normal."""
    try:
        import json
        with open(PRUEBAS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def cancion_para(sala, elegida=None, ya=()):
    """Una cancion con chart 1 a 1 (una sin chart mata al cliente: nota 03 §2). Orden: `cancion` de pruebas.json; la
    `elegida` (sala.cancion, la ultima del FF1C del anfitrion; 10-nov, MEDIDO 4 de 4 en el oficial) si tiene chart; el azar
    de JUGABLES (sin repetir las de `ya`: las 5 canciones de los 2 cooperativos del oficial eran distintas entre si)."""
    jugables = sorted(captura.jugables())
    fija = pruebas().get("cancion")
    if fija and (not jugables or fija in jugables):
        return fija
    if elegida and elegida not in ya:
        if not jugables or elegida in jugables:
            return elegida
        anotar("   ⚠ la cancion elegida %s no tiene chart 1 a 1: se sortea otra" % elegida)
    if not jugables:
        return 3120
    libres = [c for c in jugables if c not in ya]
    return random.choice(libres or jugables)


def empezar(con, seq, cuerpo):
    """C2S FF24 SendStartGame del anfitrion -> FF25 LoadGame a todos."""
    sala = sala_de(con)
    if sala is None:
        return False
    if sala.anfitrion is not con:
        anotar("   ⚠ FF24 de alguien que no es el anfitrion: se ignora")
        return True
    if len(sala.asientos) < 2:
        # FF36 CmdGameStartResponse [codigo]: 3 = «no puede iniciar solo en Multi» (2013; nota 03 §1). Le devuelve el
        # boton al anfitrion. ⏳ el layout de Steam lee 1,1,1: se manda [codigo][0][0]
        con.mandar_interno(0x36, seq, bytes([3, 0, 0]))
        anotar("   S2C FF36 3: no se puede arrancar solo")
        return True
    magic = random.randint(0x1000, 0xFFFF)
    # cooperativo (0x8000): TRES canciones, una por ronda del gorila (CHASE_RONDAS = 3 del 2013, nota 12 de S-2013).
    # ⏳ la pista del coop en Steam no esta medida (el 2013 manda 102, el bosque): MAPA_COOP para probar.
    coop = bool(sala.modo & 0x8000)
    # 10-nov (ficha 15, MEDIDO en el oficial, 1 carrera de cada grupo): grupo 1 (FF132 `01`) -> pista 9 con 3 canciones;
    # grupo 2 -> pista 10 con 2 canciones. `sala.grupo` lo guarda salas.py (puede no estar: entonces lo de antes, 3 y pista 10).
    # pruebas.json "canciones_coop" / "mapa_coop" y MAPA_COOP lo pisan. Fuera del coop: SIEMPRE 1 cancion (8 de 8 carreras).
    grupo = sala.grupo if coop else None
    n_canc = 1
    if coop:
        n_canc = int(pruebas().get("canciones_coop", {2: 2}.get(grupo, 3)))
    # la elegida (FF1C) va primero. En coop no esta medida (las 2 carreras de coop del oficial no tuvieron FF1C): HIPOTESIS.
    elegida = sala.cancion
    canciones = []
    for _ in range(n_canc):
        canciones.append(cancion_para(sala, elegida if not canciones else None, canciones))
    # 20-nov (ficha 178, llave BAILE): en una sala del Club, la cancion que el anfitrion eligio (FF83 `06 <u16>`, ver
    # baile.cmd_edit_club_music). El resto del FF25 queda con el formato de carrera: el del Club NO CONSTA (sin grabacion).
    import baile
    if baile.activo() and sala.canal == baile.CANAL_CLUB and getattr(sala, "club_cancion", None):
        canciones = [sala.club_cancion]
        anotar("   FF25 del Club: cancion %d (la del FF83 del anfitrion)" % sala.club_cancion)
    # 3-nov (nota 15 de S-2013): la 102 es un escenario de MISION (el 2013 nunca la mando: CHASE_MAP solo con
    # CHASE_EXPERIMENTAL); con 100..103 la barra de avance corre los marcadores dos cortes y sale «6P». El 2013 mandaba
    # CHASE_MAP_FIJO = 10 (antes 9) y despues la del anfitrion; el gorila sale en cualquier pista. pruebas.json:
    # "mapa_coop" para cambiarla. ⏳ la que elige el anfitrion en Steam (su paquete) sin medir.
    mapa = MAPA
    if coop:
        mapa = int(pruebas().get("mapa_coop", ajustes.MAPA_COOP if ajustes.MAPA_COOP is not None else {1: 9, 2: 10}.get(grupo, 10)))
    # 07-nov: la pista que eligio el anfitrion (FF1B, salas.elegir_pista); "mapa" en pruebas.json la pisa (barrido)
    if not coop:
        mapa = int(pruebas().get("mapa", sala.pista or MAPA))
    cancion = canciones[0]
    sala.carrera = {"magic": magic, "cancion": cancion, "cargados": set(), "go": False}
    salas.poner_estado(sala, sala.estado | 0x02)          # la lista la muestra 游戏中
    ff25 = (struct.pack("<I", 0) + struct.pack("<IHB", magic, mapa, len(canciones))
            + struct.pack("<%dH" % len(canciones), *canciones))
    # 20-nov (ficha 178): con el canal del Club (13/14/15) el RX CmdDoLoadGame lee OTRA cola despues de [u32][u16]:
    # [u8 bandera]; bandera != 0 -> [u8 N][N x u16 id] (cada id a la lista del Club); bandera 0 -> [u8][u16 id].
    # LEIDO en dos binarios: el 2019 0xd031a0 (club 0x7f6100 + 0x7f5090) y el chino 0x027935a0 (0x818ba0 + 0x818030).
    # Con la cola de carrera el anfitrion leia N como bandera y el byte bajo de la cancion como N: ids basura (el 0 de
    # la lista [obj+0x2fe0] que lo tiraba en 0x0080621b). La bandera = 1 es ELECCION nuestra (NO CONSTA cual usa el oficial).
    if baile.activo() and sala.canal == baile.CANAL_CLUB:
        ff25 = (struct.pack("<I", 0) + struct.pack("<IHBB", magic, mapa, 1, len(canciones))
                + struct.pack("<%dH" % len(canciones), *canciones))
        anotar("   FF25 con la cola del Club: [1][%d]%s" % (len(canciones), canciones))
    for c in salas.jugadores(sala):
        c.mandar_interno(0x25, seq if c is con else 0, ff25)
    anotar("   S2C FF25 LoadGame a %d: magic 0x%x, mapa %d, canciones %s (sala %d)"
           % (len(sala.asientos), magic, mapa, canciones, sala.numero))
    numero = sala.numero
    estado.mas_tarde(ESPERA_GO, "carrera.dar_go", numero, "pasaron %d s" % ESPERA_GO)
    return True


def dar_go(numero, motivo):
    sala = estado.SALAS.get(numero)
    car = sala.carrera if sala is not None else None
    if car is None or car["go"]:
        return
    car["go"] = True
    for c in salas.jugadores(sala):
        c.mandar_interno(0x24, 0, b"")
    anotar("   S2C FF24 GO a %d (sala %d): %s" % (len(sala.asientos), numero, motivo))


def cargado(con, seq, cuerpo):
    """C2S FF25 (cargue). ⏳ El cuerpo no esta medido en Steam: se anota."""
    sala = sala_de(con)
    car = sala.carrera if sala is not None else None
    if car is None:
        return False
    car["cargados"].add(id(con))
    anotar("   C2S FF25 cargue (%d B: %s): %d de %d" % (len(cuerpo), cuerpo.hex(), len(car["cargados"]),
                                                       len(sala.asientos)))
    if len(car["cargados"]) >= len(sala.asientos):
        dar_go(sala.numero, "cargaron todos")
    return True


def asiento_de(sala, con):
    return next((a for a, c in sala.asientos.items() if c is con), None)


def posicion(con, seq, cuerpo):
    """C2S FF23 (12 B, la posicion). En la grabacion 213306 el oficial la reparte a los demas como S2C FF23 de 13 B:
    [asiento][los 12 B del que la mando] (46 en una carrera de 5)."""
    sala = sala_de(con)
    if sala is None or len(cuerpo) != 12:
        return False
    a = asiento_de(sala, con)
    for c in salas.jugadores(sala):
        if c is not con:
            c.mandar_interno(0x23, 0, bytes([a]) + cuerpo)
    return True


CAPITAN_CARGA = (10, 15)       # (a los compañeros, al capitan) por cada item usado; tope 100 (la regla del 2013, elegida
                               # por Eñeños el 07-sep: MODO_JEFE_EXPEDIENTE.md; no es de los coreanos)


def barra_capitan(sala, con):
    """CAPITAN (0x4000): la barra del impulsor de capitan la carga el SERVER (el cliente no la carga sola, como el jefe
    del 2013). Cada FF26 sub 0x01 (usar un item) suma CAPITAN_CARGA al equipo del que lo uso. S2C FF176
    CmdPlusSpecialBooster: [u32 n] + n x [u32 0][u8 0][u8 asiento][u8 valor] (0x02812e80 FIJA [jugador+0x3d0] = valor,
    tope 100; solo con la bandera 0x2000 de la carrera de capitan; layout leido del exe por un subagente, 03-nov)."""
    if not salas.es_capitan(sala):
        return
    car = sala.carrera
    barra = car.setdefault("barra", {})
    eq = salas.equipo_de(sala, con)
    caps = salas.capitanes(sala)
    regs = []
    for a, x in sorted(sala.asientos.items()):
        if salas.equipo_de(sala, x) != eq:
            continue
        barra[a] = min(100, barra.get(a, 0) + (CAPITAN_CARGA[1] if caps.get(eq) == a else CAPITAN_CARGA[0]))
        regs.append(struct.pack("<IBBB", 0, 0, a, barra[a]))
    cuerpo = struct.pack("<I", len(regs)) + b"".join(regs)
    for c in salas.jugadores(sala):
        c.mandar_interno(0x176, 0, cuerpo)


JEFE_GOLPE = 13          # vida que baja el jefe del heroe por cada 4.o item (100 -> 87 -> ... -> 9 -> 0: 8 de 8 en el oficial)


def vida_del_jefe(sala, con, a):
    """HEROE (0x20000): el S2C FF22C CmdEnemyInfo `[u32 n][u8 vida][u8 item][f32]` (10 B; el exe 0x0285ed00 lee u32,u8,u8,u32
    y NO usa el f32; layouts/FF22C.md). MEDIDO en el oficial (1 carrera, 44 FF22C): el dispara cada FF26 sub 0x01 con
    t = 04 (A = [0][item][asiento][t]; los 11 del que grabo tuvieron su FF22C 0,24-1,19 s despues, con su item; los de t = 02
    no) de CUALQUIERA de la sala. La cuenta n va 1, 2, 3 y al 4.o item el jefe recibe el golpe: vida -13 y dos FF22C, n = 5
    y n = 0 (7 de 8 ciclos; en el 8.o hubo n = 4 tras un item 0x31). f = 1.3 x n (casi siempre; el cliente no lo usa).
    Con la vida en 0 no sale mas (0 de 4 items despues de la muerte del jefe). Se manda al instante: la demora del oficial
    (0,24-1,19 s) no esta explicada. SIN MEDIR: el item 0x31 (t = 02; 2 muestras, n = 0 una vez y 1 otra, no encajan en una regla:
    aca no hace nada). pruebas.json {"jefe_heroe": false} lo apaga. Solo modo heroe."""
    if not sala.modo & 0x20000 or pruebas().get("jefe_heroe", True) is False:
        return
    # 10-nov, CORREGIDO con el cliente vivo (2.o testigo): el byte alto de A no es un 'tipo 4', es el ASIENTO del que
    # usa el item sobre si mismo. En la grabacion el que grabo estaba en el asiento 4 (por eso 04, 14 de 14); en vivo
    # los asientos 0 y 1 mandan 00 y 01 con los mismos items (05 0a 0d 34: 17 y 17) y el servidor no contaba ninguno.
    # Los items 31 32 33 van con 02 en los dos testigos (el 2 no es asiento de jugador en heroe: 1,0,4,5) y no cuentan.
    if (a >> 24) & 0xFF != asiento_de(sala, con):
        return
    jefe = sala.carrera.setdefault("jefe", {"n": 0, "vida": 100})
    if jefe["vida"] <= 0:
        return
    item = (a >> 8) & 0xFF
    jefe["n"] += 1
    if jefe["n"] < 4:
        envios = [jefe["n"]]
    else:
        jefe["vida"] = max(0, jefe["vida"] - JEFE_GOLPE)
        jefe["n"] = 0
        envios = [5, 0]
    for n in envios:
        cuerpo = struct.pack("<IBBf", n, jefe["vida"], item, round(1.3 * n, 1))
        for c in salas.jugadores(sala):
            c.mandar_interno(0x22C, 0, cuerpo)
    anotar("   S2C FF22C jefe del heroe: item %02x -> envios %s, vida %d" % (item, envios, jefe["vida"]))


def sincronia(con, seq, cuerpo):
    """C2S FF26 (10 B, unas 290 por carrera en la grabacion 213306). El oficial NO lo reparte (ni un S2C FF26 en esa
    carrera): se consume sin contestar (si no, caeria en la reproduccion de la captura). ⏳ que lleva: se mide."""
    sala = sala_de(con)
    if sala is None:
        return False
    car = sala.carrera
    if car is not None:
        car.setdefault("ff26", {}).setdefault(id(con), []).append(cuerpo)
        if len(cuerpo) == 10:
            # nota 09 §1 de S-2013: [0][sub^magic^0xCA][A^magic^0xEF u32][B^magic^0xAB u32]
            m = car["magic"]
            sub = cuerpo[1] ^ (m & 0xFF) ^ 0xCA
            a = struct.unpack_from("<I", cuerpo, 2)[0] ^ m ^ 0xEF
            bb = struct.unpack_from("<I", cuerpo, 6)[0] ^ m ^ 0xAB
            cuenta = car.setdefault("subs", {}).setdefault((con.cuenta or {}).get("nick"), {})
            cuenta[sub] = cuenta.get(sub, 0) + 1
            if sub == 0x01:
                # solo registro (ficha 19): cuantos sub 0x01 por jugador y por (t, item)
                ti = car.setdefault("golpes", {}).setdefault((con.cuenta or {}).get("nick"), {})
                clave = ((a >> 24) & 0xFF, (a >> 8) & 0xFF)
                ti[clave] = ti.get(clave, 0) + 1
                barra_capitan(sala, con)
                vida_del_jefe(sala, con, a)
            # 3-nov, MEDIDO (sala 8): con "todo" el master mando su 0x84 (arranca la CUERDA) y su 0x86, los 3 jugaron
            # el minijuego y mandaron FF10F; con solo los del master se pasaba de largo al gorila (como el 2013 sin
            # relevo). Por omision en coop: "todo" (el 2013 releva todo sin preguntar); false lo apaga.
            relevo = pruebas().get("relevo_ff26", "todo")
            # 2-nov, medido (sala 7): SOLO el anfitrion manda los subs del gorila (83:8 85:9 87:53, y 00:19 contra 00:1
            # de los otros); los demas solo 05/66/fa. El FF26 S2C del cliente (0x02795060) lee 1,4,4 = los 9 B del 2013.
            # "relevo_ff26": true -> los del master (00 y 0x80..0x8f); "todo" -> todos, como el 2013.
            # 3-nov: en TODOS los modos (Eñeños: en la carrera normal tampoco estaban sincronizados; medido: los clientes
            # no mandan ni un FF23, solo FF26, asi que sin relevo nadie recibe el avance de los otros). El 2013 releva en
            # todos los modos; el oficial de Steam no lo hacia en la carrera normal grabada (nota 09 §1) [contradiccion
            # abierta: ahi si viajaban FF23].
            if relevo and (relevo == "todo" or sub == 0 or 0x80 <= sub <= 0x8F):
                # 2-nov, PRUEBA [H]: el coop del 2013 reparte la sincronia (el master maneja al gorila con los subs
                # 0x83..0x87, nota 14 §2.1-2.2) a la sala MENOS al emisor, en claro, 9 B [sub][A][B]. El oficial de
                # Steam no la reparte en la carrera normal (nota 09 §1); en coop no esta grabado.
                claro = bytes([sub]) + struct.pack("<II", a, bb)
                for c in salas.jugadores(sala):
                    if c is not con:
                        c.mandar_interno(0x26, 0, claro)
    return True


# ⭐ EL CARTEL (S2C FF28), medido en la grabacion 213306 (nota 09 de S-2013 + la fila contra el C2S del mismo jugador):
#   [b0 0][b1 0][cantidad] + una fila por jugador + cola `46 00 64`
#   fila: [0] asiento [1] puesto (7 = no llego) [2:4] bono u16 [4:6] exp u16 [6:8] combo (C2S [4:6]) [8] pd (C2S [6])
#         [9] (C2S [11]) [10] star (C2S [7]) [11:20] 0 + u32 [16:20] (27 en la plantilla) [20:24] frame (C2S [0:4])
#         [24:28] 0 | [28:57] = C2S[48:77] tal cual | [57:67] 10 B del server (`03 00 2c 01 ...`, ¿bonos? los de la
#         plantilla) | los grupos de 8 B del C2S desde [77] hasta uno que empiece en 00 (2 -> fila de 102, 3 -> 110)
#         | cola fija de 19 B (`00`x8 + `01 63 ff ff ff ff 00 00 00 00 00`)
#   C2S FF28 (119 B): [frame u32][combo u16][pd][star][u16][u16][u32][md5 ascii 32][resto 71 B con los grupos]
ESPERA_CARTEL = 12.0       # nota 03 §5: a los 12 s del primero se arma con los que haya (solo si NADIE cruzo y en RELEVO)
# 10-nov (ficha 14, grabacion del oficial del 8-nov, 8 carreras): el FF27 sale a TODOS apenas llega el PRIMER FF28 con
# frame valido (0,2-0,8 s despues); el que no llego manda su FF28 `FFFFFFFF` 5,0 s despues del FF27 (2 de 2) y el cartel
# sale cuando estan todos (0,4-1,6 s despues del ultimo). TOPE_DESDE_FF27 es NUESTRO (no esta medido): doble de los 5 s
# del cliente, por si un cliente no manda nunca su FF28 (cerrado, caido); pasado el tope el cartel sale con los que haya.
TOPE_DESDE_FF27 = 10.0


def _plantilla_fila():
    if not os.path.exists(ajustes.RUTA_CARTEL):
        return neutro.fila_cartel()
    return captura.fila_del_cartel()


# Lo que pone el SERVER en la fila (nota 11 de S-2013, medido en 3 carteles y los FF0C de antes/despues):
#   [2:4] bono por puesto (500/400/300; 0 si no termino) · [4:6] exp ganada (= lo que sube la exp en el FF0C de la
#   vuelta; el bono NO se suma) · [16:20] monedas G (1.o ~27, 2.o ~24, 3.o 19, no termino 0-4; el cliente las suma).
# El resto lo copia del C2S de cada uno. ⚠ La formula de exp del oficial no sale de los paquetes: la de abajo es la
# del 2013 (pd x 10 + combo + star), una DECISION local, no una medicion.
BONO = {1: 500, 2: 400, 3: 300}          # lo que habia (grabacion 213306, 5 jugadores: 500/400/300): vale para N != 3
# 10-nov, MEDIDO en las carreras de 3 jugadores del oficial (7 de 7): bono 300/200/100 por puesto; el heroe (0x20000)
# suma +300 (600/500/400, 1 carrera); el cooperativo (0x8000) 0 (2 carreras). Con 2, 4, 6 jugadores no hay medicion
# (la de 2 solo dice que el 1.o sacó 300): ahi sigue la regla de antes. [H sin probar: 100 x (max(N,3) - puesto + 1)]
BONO_3 = {1: 300, 2: 200, 3: 100}
MONEDAS = {1: 27, 2: 24, 3: 19}


def bono_de(puesto, n_jugadores, modo=0):
    """Bono del cartel por puesto. Solo con 3 jugadores esta medido contra el oficial; con otra cantidad, la regla de antes."""
    if puesto == 7:
        return 0
    if n_jugadores != 3:
        return BONO.get(puesto, 200)
    if modo & 0x8000:                        # cooperativo
        return 0
    return BONO_3.get(puesto, 100) + (300 if modo & 0x20000 else 0)


def puestos_por_frame(filas, empates=True):
    """{asiento: puesto} de [(frame, asiento, c2s)...]: menor frame = mejor; con `empates` el mismo frame comparte puesto y
    el siguiente salta (1,1,3; medido en 1 empate del oficial, pista 0x88); FFFFFFFF = no llego = 7. Sin `empates` el
    desempate es el asiento (lo de antes). En Rnote (0x800) los 3 frames salieron IGUALES y el oficial los puso 1,2,3 (por
    asiento): ahi el puesto no sale del frame, y como no se sabe de que, se deja lo de antes."""
    orden = sorted((fr, a) for fr, a, _c in filas if fr != 0xFFFFFFFF)
    puesto = {}
    for i, (fr, a) in enumerate(orden):
        puesto[a] = puesto[orden[i - 1][1]] if empates and i and orden[i - 1][0] == fr else i + 1
    return puesto


def ganado(puesto, c2s, n_jugadores=0, modo=0):
    """(bono, exp, monedas) de un jugador segun su puesto y su FF28 C2S."""
    if puesto == 7:
        return 0, 0, 0
    combo, pd, star = struct.unpack_from("<H", c2s, 4)[0], c2s[6], c2s[7]
    return bono_de(puesto, n_jugadores, modo), min(0xFFFF, pd * 10 + combo + star), MONEDAS.get(puesto, 15)


def fila_de(asiento, puesto, c2s, plantilla, bono=0, exp=0, monedas=0):
    # SIEMPRE 3 grupos de 8 B (el lector los lee fijos en G+2, G+10, G+18; analisis del 02-nov de 0x02795740): cortar
    # en el primer grupo que empezara en 00 achicaba la fila del cooperativo y el cartel salia con una sola fila loca
    grupos = c2s[77:101].ljust(24, b"\0")
    cabeza = (bytes([asiento, puesto]) + struct.pack("<HH", bono, exp) + c2s[4:6] + bytes([c2s[6], c2s[11]])
              + c2s[7:9] + bytes(4) + struct.pack("<I", monedas) + c2s[0:4] + bytes(4))
    # el bloque del server entre C2S[48:77] y los grupos: `00 00` sin bonos (las 5 filas del cartel 3 de la grabacion),
    # 10 B con uno (`03 00 2c 01` + 6 ceros, cartel 1). ⏳ Los bonos (mascota, pareja...) todavia no se dan: va `00 00`.
    # 3-nov: los bytes 55-56 de la fila (= C2S[75:77]) son un u16 `n` y el lector (0x02795740, [ebp-0xd0] en 0x027966f0)
    # lee despues n x (u16,u16,u32). En la carrera normal el cliente manda 00 00; en el COOP manda `00 08` (n = 2048):
    # copiado tal cual, el lector se desfasaba, las filas siguientes heredaban el asiento de la primera y cResultGroup
    # las descartaba por repetidas (0x00d3fafe): UNA sola fila (analisis de un subagente, medido en los C2S del coop).
    # 10-nov (ficha 14, 8 de 8 carreras del oficial): tres campos de la fila se COPIAN del C2S de cada jugador: c1 = C2S[76]
    # (justo tras la lista de bonos), d0 = C2S[101] y d1 = C2S[103:105] (despues de los grupos). Antes salian de la plantilla (ceros).
    # c0 (la letra de nota del coop) y d3 siguen en 0: sin medir como los calcula el oficial.
    # Ficha 171: el lector consume 98 B sin bonos/listas. La base vieja
    # agregaba cuatro ceros al final de CADA fila, desplazando la segunda.
    # Con captura se conserva exactamente el camino anterior.
    cola = plantilla[-8:] if not os.path.exists(ajustes.RUTA_CARTEL) else plantilla[-19:][7:]
    return (cabeza + c2s[48:75] + b"\x00\x00" + bytes([0, c2s[76]]) + grupos + bytes([c2s[101]]) + c2s[103:105]
            + bytes(4) + cola)


def es_relevo(sala):
    return bool(sala.modo & 0x20 and not sala.modo & 0x08 and not sala.modo & 0x10)


def unificar_relevo(sala, filas):
    """El cartel de RELEVO (2013 unificar_cartel_de_relevo, portado del CBT y verificado contra el original 3v3): el equipo
    puntua como UN jugador. Dentro del equipo: frame = el minimo de los que cruzaron, combo = el MAXIMO, pd/star =
    promedio; gana el TIEMPO; puesto 1 el ganador, tamano(ganador)+1 el perdedor, 7 si no llego nadie. exp/monedas
    individuales. Devuelve (filas con el C2S unificado, {asiento: puesto})."""
    equipos = {}
    for fr, a, c2s in filas:
        equipos.setdefault(salas.equipo_de(sala, sala.asientos[a]), []).append((fr, a, c2s))
    fin = {eq: min([fr for fr, _a, _c in ms if fr != 0xFFFFFFFF] or [0xFFFFFFFF]) for eq, ms in equipos.items()}
    orden = sorted([eq for eq in equipos if fin[eq] != 0xFFFFFFFF], key=lambda e: fin[e])
    puesto_eq, acum = {}, 1
    for eq in orden:
        puesto_eq[eq] = acum
        acum += len(equipos[eq])
    nuevas, puesto = [], {}
    for eq, ms in equipos.items():
        combo = max(struct.unpack_from("<H", c, 4)[0] for _f, _a, c in ms)
        pd = round(sum(c[6] for _f, _a, c in ms) / len(ms))
        star = round(sum(c[7] for _f, _a, c in ms) / len(ms))
        for _fr, a, c2s in ms:
            u = bytearray(c2s)
            struct.pack_into("<I", u, 0, fin[eq])
            struct.pack_into("<H", u, 4, combo)
            u[6], u[7] = pd, star
            nuevas.append((fin[eq], a, bytes(u)))
            puesto[a] = puesto_eq.get(eq, 7)
    anotar("   RELEVO: equipos %s, llegada %s -> puestos %s"
           % ({eq: [a for _f, a, _c in ms] for eq, ms in equipos.items()}, fin, puesto))
    return sorted(nuevas, key=lambda f: f[1]), puesto


def mandar_cartel(numero, motivo):
    sala = estado.SALAS.get(numero)
    car = sala.carrera if sala is not None else None
    if car is None or car.get("cartel"):
        return
    car["cartel"] = True
    plantilla = _plantilla_fila()
    if plantilla is None:
        anotar("   ⛔ sin datos/cartel_S2C.bin (herramientas/preparar_cartel.py): no hay cartel")
        return
    llegaron = car.get("ff28", {})
    filas = []
    for a, c in sorted(sala.asientos.items()):
        c2s = llegaron.get(id(c)) or (b"\xff\xff\xff\xff" + bytes(115))      # el que no llego: frame FFFFFFFF
        filas.append((struct.unpack_from("<I", c2s, 0)[0], a, c2s))
    puesto = puestos_por_frame(filas, empates=not sala.modo & 0x800)
    if es_relevo(sala):
        filas, puesto = unificar_relevo(sala, filas)
    import tienda
    partes = []
    # 10-nov (ficha 15, 6 de 6 carteles no cooperativos del oficial): las filas van por PUESTO, no por asiento; con el mismo
    # puesto, el asiento mayor primero (2 de 2 empates; HIPOTESIS: tambien podria ser el orden de llegada del FF28). En
    # cooperativo (2 carteles) el orden no es el del puesto y no se entiende: queda por asiento. Relevo: como estaba.
    if not sala.modo & 0x8000 and not es_relevo(sala):
        filas = sorted(filas, key=lambda f: (puesto.get(f[1], 7), -f[1]))
    for _fr, a, c2s in filas:
        p = puesto.get(a, 7)
        bono, exp, monedas = ganado(p, c2s, len(filas), sala.modo)
        partes.append(fila_de(a, p, c2s, plantilla, bono, exp, monedas))
        try:
            tienda.acreditar(sala.asientos[a], exp=exp, g=monedas)     # dibujar no es acreditar: va a la base
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ no se pudo acreditar al asiento %d: %r" % (a, e))
    # la cola `46 00 64`: el 0x46 = 'F' es el GRADO del cooperativo (nota 14 §4.3, H fuerte: el handler del FF28 del 2013
    # arranca con 'F'). Atrapado en la ronda 1 -> S, 2 -> B, 3 -> D (el medallon del 2013, pedido de Eñeños 15-sep)
    grado = {1: b"S", 2: b"B", 3: b"D"}.get(car.get("captura"), b"F") if sala.modo & 0x8000 else b"F"
    # 3-nov: el byte 0 de la cabecera = el EQUIPO GANADOR en equipo y relevo (2013, medido en 3 de 3 carteles de equipo
    # del referente: b0 = el equipo del puesto 1); en solo/coop 0. Con 0 el relevo marcaba WIN al que perdio (sala 13)
    b0 = 0
    if sala.modo & 0x10 or es_relevo(sala):
        primero = next((a for a, p in sorted(puesto.items(), key=lambda x: x[1]) if p == 1), None)
        b0 = salas.equipo_de(sala, sala.asientos[primero]) if primero is not None else 0
    elif salas.es_capitan(sala):
        # CAPITAN: gana el equipo cuyo CAPITAN llega primero (2013 MODO_JEFE: «el capitan que llegue primero gana»).
        # Con b0 = 0 el cliente le daba WIN al otro equipo aunque el capitan rojo llego 1.o (sala 19)
        caps = salas.capitanes(sala)
        llegada = {eq: puesto.get(a, 7) for eq, a in caps.items()}
        if llegada and min(llegada.values()) < 7:
            b0 = min(llegada, key=lambda eq: llegada[eq])
    reservados = neutro.reservados_cartel() if not os.path.exists(ajustes.RUTA_CARTEL) else b""
    cuerpo = bytes([b0, 0, len(filas)]) + b"".join(partes) + reservados + grado + b"\x00\x64"
    for c in salas.jugadores(sala):
        if not car.get("ff27"):
            c.mandar_interno(0x27, 0, b"\x00")      # FF27 CmdTimeOver, una vez antes del cartel (nota 09 §3)
        c.mandar_interno(0x28, 0, cuerpo)
    anotar("   S2C FF27 + FF28 CARTEL a %d (sala %d, %s): puestos %s" % (len(sala.asientos), numero, motivo, puesto))
    try:
        import progresion
        progresion.tras_carrera(list(salas.jugadores(sala)), sala.modo)     # ficha 83: +1 al modo y los FF1F9/FF1FE propios
    except Exception as e:                                                   # noqa: BLE001
        anotar("   ⛔ progresion.tras_carrera: %r" % e)
    try:
        import boda
        boda.tras_carrera(sala, puesto)          # ficha 112: las misiones de la boda (llave BODA; solo parejas con la boda en estado 4)
    except Exception as e:                                                   # noqa: BLE001
        anotar("   ⛔ boda.tras_carrera: %r" % e)
    try:
        salas.anotar_records_carrera(sala, car.get("cancion"), filas, puesto)   # M08: record propio por cancion (llave RECORDS)
    except Exception as e:                                                   # noqa: BLE001
        anotar("   ⛔ salas.anotar_records_carrera: %r" % e)
    for nick, cuenta in sorted(car.get("subs", {}).items(), key=lambda x: str(x[0])):
        anotar("      FF26 de %s por sub: %s" % (nick, " ".join("%02x:%d" % kv for kv in sorted(cuenta.items()))))
    for nick, ti in sorted(car.get("golpes", {}).items(), key=lambda x: str(x[0])):
        anotar("      FF26 sub 01 de %s por t:item: %s" % (nick, " ".join("%02x:%02x=%d" % (k[0], k[1], v) for k, v in sorted(ti.items()))))
    sala.carrera = None
    salas.poner_estado(sala, sala.estado & ~0x02)
    # 2-nov: tras la carrera nadie queda listo. Si volvian con READY puesto, el cliente del anfitrion veia "todos
    # listos" y a los 20 s se sacaba solo de la sala (regla del cliente, 0x00a5da50; medido en el coop de la sala 4)
    for c in salas.jugadores(sala):
        c.listo = 0
    if sala.modo & 0x8000:
        # cooperativo: tras el cartel vienen las CAJAS (nota 14 de S-2013 §3.3). Cada cliente pide [02][ff] ~14 s
        # despues; el cierre va en cajas() y la vuelta a la sala NO se empuja: el 2013 la deja pedir al cliente (FF13 +
        # FF0C, ~12 s tras el [06]). Steam nunca mando FF13: si a los VUELTA_COOP s del cierre no pidio, se empuja.
        sala.vuelta_pendiente = {id(c) for c in salas.jugadores(sala)}
        sala.vuelta_desde = time.time()
        sala.cerradas = {}
        sala.premio = None
        if car.get("captura"):
            ap = car.get("aporte", {})
            orden = sorted(sala.asientos, key=lambda a: (-ap.get(a, 0), puesto.get(a, 7), a))
            sala.premio = {"cajas": tablero(), "abiertas": {}, "orden": orden, "turno": None, "arranco": False,
                           "revelado": False}
            anotar("   GORILA ATRAPADO en la ronda %d: grado %s, tablero %s, orden de las cajas %s"
                   % (car["captura"], grado.decode(), sala.premio["cajas"], orden))
        return
    for c in salas.jugadores(sala):
        vuelta_a_sala(c, sala)


VUELTA_COOP = 15          # s tras el [06][00] (o tras el cartel, si el cliente no pidio sus cajas en 30 s)


def vuelta_a_sala(c, sala):
    """La vuelta a la sala (nota 09 §6): FF15 + FF0C + FF17 por asiento, cada uno con su estado de listo."""
    salas.mandar_sala(c, sala, solo=0x15)
    c.mandar_interno(0x0C, 0, salas.ff0c(sala, c))
    for a, x in sorted(sala.asientos.items()):
        c.mandar_interno(0x17, 0, bytes([0, a, x.listo]))


CAJA_PREMIO = (50, 1000)        # (G, exp) por caja: lo del referente del 2013 (50 RCoin + 1000 del tipo 2 = EXP)
TOPE_APERTURA = 8.0             # s por turno (GORILA_TOPE_APERTURA del 2013): si no elige, se le elige


def tablero():
    """Las 6 cajas (el FF28 crea siempre 6): todas iguales por ahora (decision: el sorteo del 2013 vendra despues)."""
    return [CAJA_PREMIO] * 6


def avanzar_turno(sala):
    """El turno al siguiente de la fila (por aporte al gorila); si ya abrieron todos, el REVELADO: el [06][N] con las
    cajas abiertas y su contenido, AL FINAL y una sola vez (nota 14 §0.2: si va antes, el cliente no paga)."""
    pr = sala.premio
    for a in pr["orden"]:
        if a in pr["abiertas"] or a not in sala.asientos:
            continue
        pr["turno"] = a
        for c in salas.jugadores(sala):
            c.mandar_interno(0x10E, 0, bytes([0x03, a]))
        anotar("   FF10E [03]: turno de elegir caja del asiento %d (sala %d)" % (a, sala.numero))
        numero, abiertas = sala.numero, len(pr["abiertas"])
        estado.mas_tarde(TOPE_APERTURA, "carrera._vencio_turno", numero, a, abiertas)
        return
    pr["revelado"] = True
    cajas_ab = sorted(set(pr["abiertas"].values()))
    paquete = bytes([0x06, len(cajas_ab)])
    for k in cajas_ab:
        g, xp = pr["cajas"][k]
        lista = ([(1, g)] if g else []) + ([(2, xp)] if xp else [])
        paquete += bytes([k, 0, len(lista)]) + b"".join(struct.pack("<III", t, v, 0) for t, v in lista)
    ahora = time.time()
    for c in salas.jugadores(sala):
        c.mandar_interno(0x10E, 0, paquete)
        sala.cerradas[id(c)] = ahora          # para la vuelta a la sala (revisar)
    anotar("   FF10E [06][%d] REVELADO de las cajas %s (sala %d)" % (len(cajas_ab), pr["abiertas"], sala.numero))


def _vencio_turno(numero, a, abiertas_antes):
    sala = estado.SALAS.get(numero)
    pr = sala.premio if sala is not None else None
    if not pr or pr["revelado"] or pr["turno"] != a or len(pr["abiertas"]) != abiertas_antes:
        return
    libres = [k for k in range(len(pr["cajas"])) if k not in pr["abiertas"].values()]
    anotar("   GORILA: el asiento %d no eligio en %d s -> se le abre la caja %s" % (a, TOPE_APERTURA, libres[:1]))
    abrir_caja(sala, a, libres[0] if libres else 0)


def abrir_caja(sala, a, caja):
    pr = sala.premio
    libres = [k for k in range(len(pr["cajas"])) if k not in pr["abiertas"].values()]
    if a in pr["abiertas"]:
        return
    if caja not in libres:
        caja = libres[0] if libres else caja
    pr["abiertas"][a] = caja
    g, xp = pr["cajas"][caja]
    con = sala.asientos.get(a)
    if con is not None:
        import tienda
        try:
            tienda.acreditar(con, exp=xp, g=g)
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ no se pudo acreditar la caja al asiento %d: %r" % (a, e))
    for c in salas.jugadores(sala):
        c.mandar_interno(0x10E, 0, bytes([0x05, a, caja]))
    anotar("   FF10E [05]: el asiento %d abre la caja %d (+%d G, +%d exp)" % (a, caja, g, xp))
    avanzar_turno(sala)


def cerrar_cajas(c, sala, seq=0):
    """Cajas sin premio, la DERROTA del 2013 (nota 14 §0.1, lobby_carrera.py:3860-3872): [09] «no hay premio», ★ [03]
    [asiento AJENO] (instala la maquina de la pantalla: sin el, el [06] no la cierra nunca = el cuelgue del 04-ago del
    2013 y el nuestro del 02-nov) y [06][00] (las cajas vuelan, 8 s, cierra sola). Ajeno = otro asiento que este en la
    sala: con el propio el cliente elige caja (y manda un [04] que hay que contestar). Una vez por jugador."""
    cerradas = sala.cerradas
    if cerradas is None:
        sala.cerradas = cerradas = {}
    if id(c) in cerradas:
        return False
    mio = next((a for a, x in sala.asientos.items() if x is c), None)
    ajeno = next((a for a in sorted(sala.asientos) if a != mio), mio)
    c.mandar_interno(0x10E, seq, b"\x09")
    c.mandar_interno(0x10E, 0, bytes([0x03, ajeno]))
    c.mandar_interno(0x10E, 0, b"\x06\x00")
    cerradas[id(c)] = time.time()
    return True


def revisar():
    """Se llama con cada paquete (manejadores.despachar): un cartel que quedo pendiente (p. ej. llegaron todos los FF28
    antes de que este codigo se recargara) se manda."""
    ahora = time.time()
    for numero, sala in list(estado.SALAS.items()):
        pend = sala.vuelta_pendiente
        if not pend:
            continue
        for c in [c for c in salas.jugadores(sala) if id(c) in pend]:
            nick = (c.cuenta or {}).get("nick")
            cerrada = sala.cerradas.get(id(c))
            if cerrada is None and sala.premio:
                if ahora - sala.vuelta_desde > 120:       # victoria trabada: se cierra igual, a los 2 min
                    sala.cerradas[id(c)] = ahora
                continue
            if cerrada is None and ahora - sala.vuelta_desde > 30:
                cerrar_cajas(c, sala)                 # no pidio sus cajas: se le cierran igual
                anotar("   S2C FF10E [09] [03] [06][00] a %s (sala %d): no pidio las cajas en 30 s" % (nick, numero))
            elif cerrada is not None and c.pidio_sala > cerrada:
                # la pidio el (FF15 + FF0C, ~13 s tras el [06], como el 2013): solo falta el listo de cada asiento
                pend.discard(id(c))
                for a, x in sorted(sala.asientos.items()):
                    c.mandar_interno(0x17, 0, bytes([0, a, x.listo]))
                anotar("   %s volvio solo a la sala %d (pidio FF15): + FF17 por asiento" % (nick, numero))
            elif cerrada is not None and ahora - cerrada > VUELTA_COOP:
                pend.discard(id(c))
                vuelta_a_sala(c, sala)
                anotar("   S2C vuelta a la sala %d para %s (no la pidio en %d s tras el [06])" % (numero, nick, VUELTA_COOP))
        car = sala.carrera
        if car and not car.get("cartel") and len(car.get("ff28", {})) >= len(sala.asientos) > 0:
            mandar_cartel(numero, "pendiente")


def resultado(con, seq, cuerpo):
    """C2S FF28 (119 B): se guarda; con todos (o a los 12 s del primero) va el cartel."""
    sala = sala_de(con)
    if sala is None:
        return False
    anotar("   C2S FF28 RESULTADO de %s (%d B): %s" % ((con.cuenta or {}).get("nick"), len(cuerpo), cuerpo.hex(" ")))
    car = sala.carrera
    if car is None or len(cuerpo) != 119:
        return True
    primero = not car.get("ff28")
    car.setdefault("ff28", {})[id(con)] = cuerpo
    valido = cuerpo[:4] != b"\xff\xff\xff\xff"
    if valido and not car.get("ff27") and not es_relevo(sala):
        # 10-nov (ficha 14): FF27 `00` a TODOS (tambien al que cruzo) al primer FF28 con frame valido, en todos los modos
        # menos relevo (que tiene su camino de abajo). x = 0 en 7 de 8 carreras; el `01` del gloton no se entiende (sin medir).
        for c in salas.jugadores(sala):
            c.mandar_interno(0x27, 0, b"\x00")
        car["ff27"] = True
        numero = sala.numero
        estado.mas_tarde(TOPE_DESDE_FF27, "carrera.mandar_cartel", numero, "tope de %d s tras el FF27" % TOPE_DESDE_FF27)
    if primero and es_relevo(sala):
        # 3-nov (2013 MODO_RELEVO §2.2): el FF27 a TODOS apenas cruza el primero: es lo que hace que cada cliente cierre
        # su tramo y mande su FF28 (los del primer tramo no lo mandaban: salian FAIL en 0 en el cartel, sala 12)
        for c in salas.jugadores(sala):
            if id(c) not in car["ff28"]:
                c.mandar_interno(0x27, 0, b"\x00")
        car["ff27"] = True
    if len(car["ff28"]) >= len(sala.asientos):
        mandar_cartel(sala.numero, "llegaron todos")
    elif primero and not (valido and car.get("ff27") and not es_relevo(sala)):
        # nadie cruzo todavia (el primero es un FFFFFFFF) o es relevo: la espera de antes. Si ya hay FF27, manda su tope.
        numero = sala.numero
        estado.mas_tarde(ESPERA_CARTEL, "carrera.mandar_cartel", numero, "pasaron %d s" % ESPERA_CARTEL)
    return True


# ⭐ EL GORILA (cooperativo; nota 13 de S-2013, la regla del 2013 en prod; en Steam FF10F CmdCatchNPC lee 1,1 como el
# 2019 y el 2013, FF10E CmdCheckGroupReward 1,1,1,1,1,1,1,12):
#   C2S FF10F [puntaje crudo 0..100]  -> S2C FF10F [asiento][puntaje] a TODOS (tambien al que lo mando)
#   cuando reportaron todos (o a los 6 s, con 0 para el que falta): S2C FF10F [06][00] a todos = el disparador (sin el,
#   la ronda no termina). ⛔ Antes del [06] tiene que haber llegado algun puntaje (map vacio = captura regalada).
#   Un token por ronda para que un reloj viejo no dispare un segundo [06].
#   Las cajas (FF10E): C2S [02] -> sin premio: S2C [09] y despues [06][00] (el tablero vacio cierra; nota 13 §5).
#   ⏳ el tablero con premios (6 -> 3 -> [04] -> 5) queda para despues.
ESPERA_GORILA = 6.0


def gorila(con, seq, cuerpo):
    sala = sala_de(con)
    car = sala.carrera if sala is not None else None
    if car is None or len(cuerpo) != 1:
        return False
    a = asiento_de(sala, con)
    g = car.setdefault("gorila", {"token": 0, "puntajes": {}})
    g["puntajes"][a] = cuerpo[0]
    for c in salas.jugadores(sala):
        c.mandar_interno(0x10F, seq if c is con else 0, bytes([a, cuerpo[0]]))
    anotar("   FF10F gorila: asiento %d puntaje %d (%d de %d)" % (a, cuerpo[0], len(g["puntajes"]), len(sala.asientos)))
    token = g["token"]
    if len(g["puntajes"]) >= len(sala.asientos):
        cerrar_gorila(sala.numero, token, "reportaron todos")
    elif len(g["puntajes"]) == 1:
        numero = sala.numero
        estado.mas_tarde(ESPERA_GORILA, "carrera.cerrar_gorila", numero, token, "pasaron 6 s")
    return True


def cerrar_gorila(numero, token, motivo):
    sala = estado.SALAS.get(numero)
    car = sala.carrera if sala is not None else None
    g = (car or {}).get("gorila")
    if g is None or g["token"] != token:
        return
    for a, c in sorted(sala.asientos.items()):
        if a not in g["puntajes"]:
            g["puntajes"][a] = 0
            for x in salas.jugadores(sala):
                x.mandar_interno(0x10F, 0, bytes([a, 0]))
    for c in salas.jugadores(sala):
        c.mandar_interno(0x10F, 0, b"\x06\x00")
    car.setdefault("rondas", []).append(dict(g["puntajes"]))
    # 3-nov: el server hace la MISMA cuenta que el cliente (nota 13 §2.3 de S-2013, 0x570E30): acierto = puntaje >= 70,
    # captura si aciertos * 2 >= tamano del map (con el map vacio no se llega aca: el relleno de arriba lo completa)
    puntos = g["puntajes"]
    aporte = car.setdefault("aporte", {})
    for a, v in puntos.items():
        aporte[a] = aporte.get(a, 0) + v
    atrapado = bool(puntos) and sum(1 for v in puntos.values() if v >= 70) * 2 >= len(puntos)
    if atrapado and not car.get("captura"):
        car["captura"] = len(car["rondas"])
    anotar("   S2C FF10F [06][00] fin de ronda %d del gorila (sala %d, %s): %s -> %s"
           % (len(car["rondas"]), numero, motivo, g["puntajes"], "ATRAPADO" if atrapado else "se escapo"))
    car["gorila"] = {"token": token + 1, "puntajes": {}}


def cajas(con, seq, cuerpo):
    sala = sala_de(con)
    if sala is None or not cuerpo:
        return False
    pr = sala.premio
    if pr:
        a = asiento_de(sala, con)
        if cuerpo[0] == 4 and len(cuerpo) > 1:
            if a == pr["turno"] and not pr["revelado"]:
                abrir_caja(sala, a, cuerpo[1])
            else:
                # ⛔ al [04] SIEMPRE se contesta: fuera de turno se le repite el turno vigente
                con.mandar_interno(0x10E, seq, bytes([0x03, pr["turno"] if pr["turno"] is not None else a]))
            anotar("   FF10E cajas: %s mando %s" % ((con.cuenta or {}).get("nick"), cuerpo.hex()))
        elif not pr["arranco"]:
            pr["arranco"] = True
            anotar("   FF10E cajas: %s mando %s -> arranca la fila de las cajas" % ((con.cuenta or {}).get("nick"), cuerpo.hex()))
            avanzar_turno(sala)
        elif pr["revelado"]:
            anotar("   FF10E cajas: %s mando %s tras el revelado -> nada" % ((con.cuenta or {}).get("nick"), cuerpo.hex()))
        else:
            con.mandar_interno(0x10E, seq, bytes([0x03, pr["turno"]]))   # el turno vigente, solo a el (su FSM)
            anotar("   FF10E cajas: %s mando %s -> turno vigente %d" % ((con.cuenta or {}).get("nick"), cuerpo.hex(), pr["turno"]))
        return True
    # ⛔ al [04][caja] SIEMPRE se contesta (la pantalla no tiene reloj): sin tablero, el mismo cierre que al [02]
    nuevo = cerrar_cajas(con, sala, seq)
    if not nuevo:
        con.mandar_interno(0x10E, seq, b"\x09")       # ya cerrado: igual se contesta (sin otro [03])
    anotar("   FF10E cajas: %s mando %s -> %s"
           % ((con.cuenta or {}).get("nick"), cuerpo.hex(), "[09] [03][ajeno] [06][00]" if nuevo else "[09] (ya cerrado)"))
    return True


MANEJADORES = {
    0x10F: gorila,
    0x10E: cajas,
    0x24: empezar,
    0x25: cargado,
    0x23: posicion,
    0x26: sincronia,
    0x28: resultado,
}
