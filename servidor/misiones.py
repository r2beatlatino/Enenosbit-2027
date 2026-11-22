# -*- coding: utf-8 -*-
r"""misiones.py — tutoriales y cartas de historia (panel rosa) del cliente de Steam. ENGANCHADO (ficha 51, manejadores.MODULOS).

Testigos: la guia del amigo (docs/aportes/IMPLEMENTAR_MISIONES_CN.md, build CN distinta: vale la FORMA) y los layouts
de NUESTRO exe (docs/tablero/layouts/FF81, FF3A, FF63, FF9F). Lo que sale de uno solo va marcado HIPOTESIS.
  FF81 (guia §7.1)  C2S [u8 tipo 0 entrada | 1 final][u8 leccion 1..5]([u8 superada] si final)
                    S2C [u8 leccion][u8 resultado 0 ok | 5 no][u32 rcoin de ESTE cierre][u32 objeto]
  FF3A (guia §7.2)  C2S [u8 subtipo 4 entrada | 1 final][u32 codigo]    S2C [u8 subtipo][u8 ok][u32 rcoin total][u16 codigo]
  FF63 (guia §7.3)  C2S [u8 0 entrada | 1 final][u32 n][u16][u32 tiempo][10 B]   S2C [u8 fallo][u32 n][u32 exp][u32 rcoin]
  FF9F (guia §7.4)  S2C 172 B (el exe no tiene emisor C2S: restaurar() lo manda, no se contesta a nadie)
Guardado: SOLO por cuenta.py, en cuenta["personaje"]["misiones"] = {"tutorial": {"1": fila}, "historia": {"16": fila}}.
Premios (ficha 51 y 61): el Rcoin entra como G por tienda.acreditar (HIPOTESIS: Rcoin de la guia = G del servidor); el objeto
entra por tienda.dar_objeto. Si no se pudo entregar queda en la fila como `item_pendiente` y se reintenta al entrar al lobby
(restaurar); entregado, la fila guarda su codigo en `item_entregado` y `item_pendiente` vuelve a 0.
Enganche: 0x57 (op 87) anota la cancion y NO contesta; 0x7F (el lobby, tras elegir personaje) manda el FF9F + las marcas 58/10
solo si la cuenta ya hizo alguna mision.
"""
import copy
import struct
import time

import captura
import cuenta
import estado

# ---------- DATOS (guia §4) ----------
FAMILIA_TUTORIAL = "tutorial"
FAMILIA_HISTORIA = "historia"
SEGUNDOS_MINIMOS = 30                       # guia §4.1 y §8.3: tiempo minimo del intento para cerrar con exito
CODIGO_GUIA_INICIAL = 1                     # historia 1: se deriva de los 5 tutoriales (guia §4.2)
OBJETO_MASCOTA = 600001                     # Item=1 del tutorial 5 es un INDICE de mascota -> 600001 (guia §4.3)

# id de red -> premio. El tutorial 5 paga una mascota y 0 Rcoin.
TUTORIALES = {
    1: {"rcoin": 500, "objeto": 0},
    2: {"rcoin": 700, "objeto": 0},
    3: {"rcoin": 1000, "objeto": 0},
    4: {"rcoin": 1500, "objeto": 0},
    5: {"rcoin": 0, "objeto": OBJETO_MASCOTA},
}

# codigo -> premio y canciones admitidas (Music de cada bloque <Mission>, guia §4.2 notas * y **).
# "objeto_mujer": variante para personaje femenino (guia nota ***). Nivel minimo/rango de la guia: NO se imponen (guia §15.1).
HISTORIA = {
    1: {"rcoin": 0, "objeto": 0, "musicas": (50,)},
    0xF001: {"rcoin": 0, "objeto": 0, "musicas": (311,)},
    0xF002: {"rcoin": 0, "objeto": 0, "musicas": (53,)},
    0xF004: {"rcoin": 0, "objeto": 0, "musicas": (209,)},
    0xF008: {"rcoin": 0, "objeto": 0, "musicas": (278, 54, 109, 55)},
    2: {"rcoin": 500, "objeto": 600008, "musicas": (51,)},
    3: {"rcoin": 700, "objeto": 0, "musicas": (52,)},
    4: {"rcoin": 0, "objeto": 30009, "musicas": (207,)},
    16: {"rcoin": 0, "objeto": 0, "musicas": (130,)},
    32: {"rcoin": 0, "objeto": 830009, "musicas": (330,)},
    48: {"rcoin": 0, "objeto": 910003, "objeto_mujer": 920003, "musicas": (145,)},
    256: {"rcoin": 0, "objeto": 0, "musicas": (185,)},
}
# Grupos de contadores consecutivos del campo de tarjetas del FF9F (guia §9.1): nibble bajo, medio, alto.
GRUPOS_CONTADOR = ((1, 2, 3, 4), (16, 32, 48), (256,))
# Tarjetas que se restauran con 58/subtipo 10. HIPOTESIS: las adicionales (0xF00n) no entran (la guia no lo dice).
RESTAURABLES = (1, 2, 3, 4, 16, 32, 48, 256)

TUTORIAL_ENTRADA, TUTORIAL_FINAL = 0, 1
HISTORIA_FINAL, HISTORIA_ENTRADA, HISTORIA_RESTAURAR = 1, 4, 10    # 10: guia §7.2; el exe no lo confirma (HIPOTESIS)
RESULTADO_OK, RESULTADO_NO = 0, 5
ADICIONAL_ENTRADA, ADICIONAL_FINAL = 0, 1
ADICIONALES = (1, 2, 4, 8)
BASE_ADICIONAL = 0xF000
TIEMPO_ABANDONO = 0xFFFFFFFF
LARGO_ENTRADA_TUTORIAL, LARGO_FINAL_TUTORIAL = 2, 3
LARGO_PEDIDO_HISTORIA, LARGO_PEDIDO_ADICIONAL = 5, 21
LARGO_FF9F = 172
OFS_G, OFS_CONTADORES, OFS_TUTORIALES = 128, 132, 168
OFS_RCOIN = OFS_G                              # nombre viejo: +128 NO es el Rcoin de las misiones, es el G TOTAL de la cuenta (ficha 81)
OFS_EXP_BAJA, OFS_EXP_DANCE = 136, 140       # los pone restaurar() solo si el que lo engancha da la EXP real
RELOJ = time.monotonic                        # las pruebas lo cambian


def anotar(txt):
    estado.anotar(txt)


# ---------- REGLAS (puras: reciben y devuelven el progreso) ----------
def fila_vacia():
    return {"intentos": 0, "completada": 0, "recompensa_cobrada": 0, "rcoin_entregado": 0,
            "item_entregado": 0, "item_pendiente": 0, "ultimo_resultado": ""}


def fila(progreso, familia, codigo):
    """La fila de esa mision con todos sus campos (vacia si nunca se jugo)."""
    f = fila_vacia()
    f.update((progreso or {}).get(familia, {}).get(str(codigo), {}))
    return f


def con_fila(progreso, familia, codigo, nueva):
    """Copia del progreso con esa fila reemplazada."""
    p = copy.deepcopy(progreso or {})
    p.setdefault(familia, {})[str(codigo)] = nueva
    return p


def codigo_valido(familia, codigo):
    return codigo in (TUTORIALES if familia == FAMILIA_TUTORIAL else HISTORIA)


def hecha(progreso, familia, codigo):
    return bool(fila(progreso, familia, codigo)["completada"])


def tutoriales_seguidos(progreso):
    """Cuantos tutoriales hechos seguidos desde el 1 (0..5): el byte 168 del FF9F (guia §7.4)."""
    n = 0
    while n < len(TUTORIALES) and hecha(progreso, FAMILIA_TUTORIAL, n + 1):
        n += 1
    return n


def contadores_tarjetas(progreso):
    """Los tres contadores consecutivos de 4 bits (guia §9.1). HIPOTESIS: el grupo 1 va en el nibble bajo."""
    valor = 0
    for pos, grupo in enumerate(GRUPOS_CONTADOR):
        n = 0
        while n < len(grupo) and hecha(progreso, FAMILIA_HISTORIA, grupo[n]):
            n += 1
        valor |= n << (4 * pos)
    return valor


def rcoin_total(progreso):
    """Rcoin que las misiones dieron (suma de lo anotado). El servidor no guarda un saldo de Rcoin (ficha 50 §3)."""
    return sum(f.get("rcoin_entregado", 0) for fam in (progreso or {}).values() for f in fam.values())


def empezar(progreso, familia, codigo):
    """Una entrada mas en esa mision. No completa nada ni paga (guia §8.2)."""
    f = fila(progreso, familia, codigo)
    f["intentos"] += 1
    f["ultimo_resultado"] = "Iniciada"
    return con_fila(progreso, familia, codigo, f)


def objeto_de(premio, mujer=False):
    """El objeto del premio, con la variante femenina si la hay."""
    return premio.get("objeto_mujer", premio["objeto"]) if mujer else premio["objeto"]


def premio_de(familia, codigo, mujer=False):
    p = (TUTORIALES if familia == FAMILIA_TUTORIAL else HISTORIA)[codigo]
    return {"rcoin": p["rcoin"], "objeto": objeto_de(p, mujer)}


def puede_cerrar(progreso, familia, codigo):
    """Tutorial N exige hechos los anteriores (guia §8.3). La historia no tiene dependencias que imponer (guia §15.1)."""
    if familia == FAMILIA_TUTORIAL:
        return codigo == 1 or hecha(progreso, familia, codigo - 1)
    return codigo != CODIGO_GUIA_INICIAL      # HIPOTESIS: la guia inicial no se cierra por 58 (no tiene carta 50)


def cerrar_con_exito(progreso, familia, codigo, mujer=False):
    """(progreso nuevo, premio a pagar). Nueva = no estaba hecha; se paga solo si ademas no estaba cobrada (guia §8.4).
    El tutorial 5 deja ademas la historia 1 hecha y cobrada, sin pagar otra vez (guia §8.4 paso 8)."""
    f = fila(progreso, familia, codigo)
    nueva = not f["completada"]
    pagar = nueva and not f["recompensa_cobrada"]
    premio = premio_de(familia, codigo, mujer) if pagar else {"rcoin": 0, "objeto": 0}
    f["ultimo_resultado"] = "Superada"
    if nueva:
        f["completada"] = 1
        f["recompensa_cobrada"] = 1
    if pagar:
        f["rcoin_entregado"] += premio["rcoin"]
        f["item_pendiente"] = premio["objeto"] or f["item_pendiente"]     # debido; pasa a item_entregado cuando se entregue
    nuevo = con_fila(progreso, familia, codigo, f)
    if familia == FAMILIA_TUTORIAL and codigo == len(TUTORIALES) and nueva:
        guia = fila(nuevo, FAMILIA_HISTORIA, CODIGO_GUIA_INICIAL)
        guia.update(completada=1, recompensa_cobrada=1, ultimo_resultado="Superada")
        nuevo = con_fila(nuevo, FAMILIA_HISTORIA, CODIGO_GUIA_INICIAL, guia)
    return nuevo, premio


def cerrar_sin_exito(progreso, familia, codigo):
    """Abandono o fallo: anota el resultado y conserva la marca que hubiera (guia §13.2)."""
    f = fila(progreso, familia, codigo)
    f["ultimo_resultado"] = "Abandono"
    return con_fila(progreso, familia, codigo, f)


def motivo_rechazo(intento, usn, familia, codigo, ahora, exito):
    """'' si el final se puede aceptar; si no, el motivo (guia §8.3): mismo personaje, familia y codigo; para el exito
    ademas 30 s desde la entrada y, en historia, una cancion admitida."""
    if not intento or intento["usn"] != usn or intento["familia"] != familia or intento["codigo"] != codigo:
        return "sin entrada de esa mision"
    if not exito:
        return ""
    if ahora - intento["t0"] < SEGUNDOS_MINIMOS:
        return "menos de %d s desde la entrada" % SEGUNDOS_MINIMOS
    if familia == FAMILIA_HISTORIA and intento["musica"] not in HISTORIA[codigo]["musicas"]:
        return "cancion %r no admitida" % (intento["musica"],)
    return ""


# ---------- ARMADO DE BYTES ----------
def cuerpo_tutorial(leccion, resultado, rcoin, objeto):
    """FF81 S2C [u8][u8][u32][u32] (layout FF81)."""
    return struct.pack("<BBII", leccion, resultado, rcoin, objeto)


def cuerpo_historia(subtipo, ok, rcoin_acumulado, codigo):
    """FF3A S2C [u8][u8][u32][u16] (layout FF3A). Rcoin = TOTAL, no incremento (guia §7.2)."""
    return struct.pack("<BBIH", subtipo, ok, rcoin_acumulado & 0xFFFFFFFF, codigo & 0xFFFF)


def cuerpo_adicional(fallo, numero, exp, rcoin):
    """FF63 S2C [u8][u32][u32][u32] (layout FF63)."""
    return struct.pack("<BIII", fallo, numero, exp, rcoin)


def cuerpo_ff9f(progreso, exp_baja=0, exp_dance=0, g_total=0):
    """FF9F S2C de 172 B (CmdGetUserTable, 0x027ef730; MEDIDO en el exe, ficha 80/81). Cada campo deja en el cliente el MISMO
    campo que dejo el FF00: +128 u32 -> G TOTAL de la cuenta ([C+0x968]; el cliente lo guarda con xor 0x2efd, por el cable va
    el numero PLANO, igual que el u32@17 del FF00); +132 u16 contadores de tarjetas; +136 u32 -> EXP TOTAL ([C+0x960], plana,
    la mitad alta queda en 0); +140 u32 -> [C+0x9c4] (la 2.a experiencia; con xor al guardar, plana por el cable, el mismo
    campo que el FF00 llena en su campo #66; 0 = lo que trae la plantilla capturada); +168 u8 tutoriales.
    El premio de una mision (Rcoin) ya esta SUMADO en el G de la cuenta (pagar -> tienda.acreditar): aca va el total, no
    el premio. Con 0 en la EXP o el G el cliente BAJARIA lo que muestra: quien lo mande tiene que dar los reales."""
    b = bytearray(LARGO_FF9F)
    struct.pack_into("<I", b, OFS_G, min(0xFFFFFFFF, max(0, int(g_total))))
    struct.pack_into("<I", b, OFS_CONTADORES, contadores_tarjetas(progreso))
    struct.pack_into("<I", b, OFS_EXP_BAJA, min(0xFFFFFFFF, max(0, int(exp_baja))))
    struct.pack_into("<I", b, OFS_EXP_DANCE, exp_dance & 0xFFFFFFFF)
    b[OFS_TUTORIALES] = tutoriales_seguidos(progreso)
    return bytes(b)


# ---------- GUARDADO Y PAGO ----------
def usn_de(con):
    c = con.cuenta or {}
    return c.get("usn") or None


def progreso_de(usn):
    """El progreso de misiones de esa cuenta ({} si no tiene personaje o la seccion). Lee por cuenta.py."""
    acc = cuenta.leer(usn) if usn else None
    return copy.deepcopy(((acc or {}).get("personaje") or {}).get("misiones") or {})


def guardar(usn, funcion):
    """Cambia el progreso con el candado de cuenta.py. funcion(progreso) -> (progreso nuevo, resultado).
    Devuelve el resultado, o None si la cuenta no tiene personaje (no se escribe nada)."""
    salida = []

    def en_cuenta(acc):
        pj = acc.get("personaje")
        if not pj:
            return
        nuevo, res = funcion(copy.deepcopy(pj.get("misiones") or {}))
        pj["misiones"] = nuevo
        salida.append(res)
    cuenta.cambiar(usn, en_cuenta)
    return salida[0] if salida else None


def mujer_de(con):
    """Genero del personaje: char_id = 0x1FF54 + (sexo != 0) (cuentas.py / juego.ficha_para). Sin personaje: varon."""
    pj = (con.cuenta or {}).get("personaje") or {}
    return bool(pj) and ((pj.get("char_id", 0x1FF54) - 0x1FF54) & 1) == 1


def marcar_entregado(usn, objeto, mision=None):
    """Pasa `objeto` de item_pendiente a item_entregado en la(s) fila(s) que lo debian: la de `mision` = (familia, codigo) si
    se da, o cualquiera que lo tenga pendiente. Con el candado de cuenta.py; NO llamar desde dentro de otro cambio de cuenta."""
    def en_progreso(p):
        for fam, filas in p.items():
            for cod, f in filas.items():
                if f.get("item_pendiente") == objeto and (mision is None or mision == (fam, cod)):
                    f["item_pendiente"], f["item_entregado"] = 0, objeto
        return p, True
    guardar(usn, en_progreso)


def entregar_objeto(con, usn, objeto):
    """Da `objeto` por tienda.dar_objeto. True si la cuenta lo tiene (dado o ya estaba); False si no, y lo anota."""
    try:
        import tienda
        res = tienda.dar_objeto(usn, objeto, con=con)
    except Exception as e:                                               # noqa: BLE001
        anotar("   MISION objeto FALLO usn %s: %d (%r); sigue pendiente" % (usn, objeto, e))
        return False
    if res["estado"] == "rechazado":
        anotar("   MISION objeto RECHAZADO usn %s: %d (%s); sigue pendiente" % (usn, objeto, res["motivo"]))
        return False
    return True


def pagar(con, usn, premio, mision=None):
    """UNICO lugar del pago (se llama UNA vez por mision: cerrar() ya marco la fila como cobrada). El Rcoin entra como G
    por tienda.acreditar (HIPOTESIS: Rcoin de la guia = G). El objeto entra por tienda.dar_objeto y la fila `mision`
    (familia, codigo) pasa de item_pendiente a item_entregado; si falla queda pendiente. Devuelve lo REALMENTE entregado:
    {"rcoin": n, "objeto": codigo o 0}."""
    entregado = {"rcoin": 0, "objeto": 0}
    if premio["rcoin"]:
        try:
            import tienda
            tienda.acreditar(con, g=premio["rcoin"])
            entregado["rcoin"] = premio["rcoin"]
        except Exception as e:                                           # noqa: BLE001
            anotar("   MISION pago FALLO usn %s: %d Rcoin sin acreditar (%r); la fila ya figura cobrada" % (usn, premio["rcoin"], e))
    if premio["objeto"]:
        if entregar_objeto(con, usn, premio["objeto"]):
            entregado["objeto"] = premio["objeto"]
            _marcar_sin_romper(usn, premio["objeto"], mision)
        else:
            anotar("   MISION objeto PENDIENTE usn %s: %d (queda en la fila como item_pendiente)" % (usn, premio["objeto"]))
    return entregado


def _marcar_sin_romper(usn, objeto, mision):
    """marcar_entregado sin dejar que un error de guardado tire el pago (el objeto ya esta en el inventario)."""
    try:
        marcar_entregado(usn, objeto, mision)
    except Exception as e:                                               # noqa: BLE001
        anotar("   MISION no se pudo marcar entregado usn %s: %d (%r)" % (usn, objeto, e))


def entregar_pendientes(con):
    """Entrega los item_pendiente que ya esten guardados en la cuenta (premios de antes de la ficha 61) y borra la marca.
    Devuelve cuantos entrego. Si falla uno, sigue pendiente y se reintenta en la proxima entrada."""
    usn = usn_de(con)
    if usn is None:
        return 0
    debidos = {f["item_pendiente"] for fam in progreso_de(usn).values() for f in fam.values() if f.get("item_pendiente")}
    hechos = 0
    for objeto in sorted(debidos):
        if entregar_objeto(con, usn, objeto):
            _marcar_sin_romper(usn, objeto, None)
            hechos += 1
    if hechos:
        anotar("   MISION pendientes usn %s: %d objeto(s) entregado(s) al entrar" % (usn, hechos))
    return hechos


# ---------- INTENTO DE LA CONEXION ----------
def abrir_intento(con, usn, familia, codigo):
    con.intento_mision = {"usn": usn, "familia": familia, "codigo": codigo, "t0": RELOJ(),
                          "musica": None, "cerrada": False, "aceptada": False}


def observar_musica(con, musica):
    """Para el enganche: la cancion pedida (op 87) entra al intento abierto (guia §8.2)."""
    intento = con.intento_mision
    if intento and not intento["cerrada"]:
        intento["musica"] = musica


def entrar(con, familia, codigo):
    """Registra la entrada (una fila mas, intento abierto). False si no hay personaje o falla el guardado."""
    usn = usn_de(con)
    try:
        ok = usn is not None and guardar(usn, lambda p: (empezar(p, familia, codigo), True)) is True
    except cuenta.CuentaError as e:
        anotar("   MISION entrada sin guardar: %s" % e)
        return False
    if ok:
        abrir_intento(con, usn, familia, codigo)
    return ok


def cerrar(con, familia, codigo, exito, mujer=None):
    """Un final. Devuelve {"aceptada", "premio", "rcoin_total"}. Repetir el final de un intento ya cerrado devuelve su
    resultado con premio en 0 (guia §8.3). Un exito rechazado deja el intento abierto; abandono/fallo y exito aceptado lo cierran."""
    usn = usn_de(con)
    mujer = mujer_de(con) if mujer is None else mujer
    intento = con.intento_mision
    sin_premio = {"rcoin": 0, "objeto": 0}
    rechazo = {"aceptada": False, "premio": sin_premio, "rcoin_total": 0}
    if usn is None:
        return rechazo
    try:
        total = rcoin_total(progreso_de(usn))
        rechazo["rcoin_total"] = total
        if intento and intento["cerrada"] and (intento["usn"], intento["familia"], intento["codigo"]) == (usn, familia, codigo):
            return {"aceptada": intento["aceptada"] and exito, "premio": sin_premio, "rcoin_total": total}
        motivo = motivo_rechazo(intento, usn, familia, codigo, RELOJ(), exito)
        if motivo:
            anotar("   MISION final rechazado (%s %s): %s" % (familia, codigo, motivo))
            return rechazo
        if exito:
            res = guardar(usn, lambda p: _cerrar_exito(p, familia, codigo, mujer))
        else:
            res = guardar(usn, lambda p: (cerrar_sin_exito(p, familia, codigo), {"aceptada": False, "premio": sin_premio}))
    except cuenta.CuentaError as e:
        anotar("   MISION final sin guardar: %s" % e)
        return rechazo
    if res is None or not res["aceptada"] and exito:
        return rechazo
    intento["cerrada"], intento["aceptada"] = True, res["aceptada"]
    res["premio"] = pagar(con, usn, res["premio"], (familia, str(codigo)))        # lo que la respuesta al cliente cuenta es lo ENTREGADO
    res["rcoin_total"] = rcoin_total(progreso_de(usn))
    return res


def _cerrar_exito(progreso, familia, codigo, mujer):
    if not puede_cerrar(progreso, familia, codigo):
        return progreso, {"aceptada": False, "premio": {"rcoin": 0, "objeto": 0}}
    nuevo, premio = cerrar_con_exito(progreso, familia, codigo, mujer)
    return nuevo, {"aceptada": True, "premio": premio}


# ---------- MANEJADORES (con, seq, cuerpo) -> bool ----------
def tutorial(con, seq, cuerpo):
    """C2S FF81 (guia §7.1). Entrada: se registra y no se contesta. Final: S2C FF81 con el premio de ESTE cierre."""
    if len(cuerpo) not in (LARGO_ENTRADA_TUTORIAL, LARGO_FINAL_TUTORIAL) or cuerpo[0] > TUTORIAL_FINAL:
        return False
    tipo, leccion = cuerpo[0], cuerpo[1]
    if leccion not in TUTORIALES or (tipo == TUTORIAL_FINAL) != (len(cuerpo) == LARGO_FINAL_TUTORIAL):
        return False
    if tipo == TUTORIAL_ENTRADA:
        entrar(con, FAMILIA_TUTORIAL, leccion)
        return True
    if cuerpo[2] > 1:
        return False
    res = cerrar(con, FAMILIA_TUTORIAL, leccion, bool(cuerpo[2]))
    con.mandar_interno(0x81, seq, cuerpo_tutorial(
        leccion, RESULTADO_OK if res["aceptada"] else RESULTADO_NO, res["premio"]["rcoin"], res["premio"]["objeto"]))
    return True


def historia(con, seq, cuerpo):
    """C2S FF3A de 5 B, subtipo 4 (entrada) o 1 (final) (guia §7.2). Otros subtipos y largos: False (los toma otro).
    HIPOTESIS: la entrada no se contesta (la guia no dice que si).
    ⚠ El "empezar cancion" de juego.py TAMBIEN mide 5 B: [dificultad][songid u32] (medido: dificultad 2 y 3; una vez 4 con
    songid 4 = en realidad la entrada de la carta 4, 23-oct). Por eso el subtipo 1 (final) solo se toma si esta conexion tiene
    una mision de historia con ESE codigo (abierta o ya cerrada); si no, va a juego.py como siempre. El subtipo 4 solo con
    un codigo de la tabla (la dificultad 4 no existe como dificultad medida)."""
    if len(cuerpo) != LARGO_PEDIDO_HISTORIA or cuerpo[0] not in (HISTORIA_ENTRADA, HISTORIA_FINAL):
        return False
    subtipo, codigo = cuerpo[0], struct.unpack_from("<I", cuerpo, 1)[0]
    intento = con.intento_mision
    if subtipo == HISTORIA_FINAL and not (intento and intento["familia"] == FAMILIA_HISTORIA and intento["codigo"] == codigo):
        return False
    if subtipo == HISTORIA_ENTRADA and not codigo_valido(FAMILIA_HISTORIA, codigo):
        return False
    if subtipo == HISTORIA_ENTRADA:
        entrar(con, FAMILIA_HISTORIA, codigo)
        return True
    res = cerrar(con, FAMILIA_HISTORIA, codigo, True) if codigo_valido(FAMILIA_HISTORIA, codigo) else \
        {"aceptada": False, "rcoin_total": rcoin_total(progreso_de(usn_de(con)))}
    # rechazo = subtipo 0, nunca subtipo 1 con ok falso (guia §7.2)
    resp = (HISTORIA_FINAL, 1) if res["aceptada"] else (0, 0)
    con.mandar_interno(0x3A, seq, cuerpo_historia(resp[0], resp[1], res["rcoin_total"], codigo))
    return True


def adicional(con, seq, cuerpo):
    """C2S FF63 de 21 B (guia §7.3). Entrada: se registra y no se contesta. Final: S2C FF63 con numero 1/2/4/8 si hubo exito.
    Exito = tiempo distinto de 0 y de 0xFFFFFFFF. No paga nada (guia §7.3)."""
    if len(cuerpo) != LARGO_PEDIDO_ADICIONAL or cuerpo[0] > ADICIONAL_FINAL:
        return False
    tipo = cuerpo[0]
    numero, _, tiempo = struct.unpack_from("<IHI", cuerpo, 1)
    if numero not in ADICIONALES:
        return False
    codigo = BASE_ADICIONAL | numero
    if tipo == ADICIONAL_ENTRADA:
        entrar(con, FAMILIA_HISTORIA, codigo)
        return True
    exito = tiempo not in (0, TIEMPO_ABANDONO)
    res = cerrar(con, FAMILIA_HISTORIA, codigo, exito)
    ok = exito and res["aceptada"]
    con.mandar_interno(0x63, seq, cuerpo_adicional(0 if ok else 1, numero if ok else 0, 0, 0))
    return True


def estado_progreso(con, seq, cuerpo):
    """FF9F: el exe no lo manda (layout FF9F). Un pedido vacio se contesta con el estado; cualquier otro cuerpo: False."""
    if cuerpo:
        return False
    restaurar(con, seq)
    return True


def hay_progreso(progreso):
    """True si la cuenta ya completo alguna mision (si no, no hay nada que restaurar)."""
    return any(f.get("completada") for fam in (progreso or {}).values() for f in fam.values())


def _exp_g_capturados():
    """(exp, g) de la ficha FF00 CAPTURADA (u32@5 + u64@9, y u32@17 plano), o None. Es lo que el cliente de la sesion capturada
    (sin cuenta local) recibe del FF00, que no se toca."""
    cu = captura.cuerpo_capturado(0x00)
    if not cu or len(cu) < 21:
        return None
    return (struct.unpack_from("<I", cu, 5)[0] + struct.unpack_from("<Q", cu, 9)[0], struct.unpack_from("<I", cu, 17)[0])


def exp_g_de_ficha(con):
    """(exp, g) que el cliente de esta conexion YA tiene por su FF00: los de la cuenta local (tienda.exp_g_de_cuenta, la
    misma fuente que arma la ficha y el FF0C) o, sin cuenta local, los de la captura. None si no se pueden leer."""
    try:
        if usn_de(con):
            import tienda
            return tienda.exp_g_de_cuenta(con.cuenta)
        return _exp_g_capturados()
    except Exception:                                                    # noqa: BLE001
        return None


def exp_de_ficha(con):
    """La EXP que el cliente YA tiene (ficha 81: antes leia el u32@17 del FF00 de la captura, que es el G). None si no se
    puede leer."""
    r = exp_g_de_ficha(con)
    return None if r is None else r[0]


def g_de_ficha(con):
    """El G que el cliente YA tiene por el FF00 de esta conexion (ver exp_g_de_ficha). None si no se puede leer."""
    r = exp_g_de_ficha(con)
    return None if r is None else r[1]


def entregar_pendientes_sin_romper(con):
    """entregar_pendientes para el enganche del lobby: un error se anota y no impide el resto de restaurar."""
    try:
        entregar_pendientes(con)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ MISION entregar pendientes: %r" % (e,))


def restaurar(con, seq=0, exp_baja=None, exp_dance=0, g_total=None):
    """Manda el FF9F y las marcas exactas 58/subtipo 10 de las tarjetas hechas (guia §7.2, §7.4, §9.2). Lo llama el
    enganche tras elegir personaje. exp_baja/g_total: la EXP y el G REALES de la cuenta (con 0 bajarian).
    Sin ellos (modo automatico, el del enganche): salen de la MISMA fuente que la ficha FF00 (exp_g_de_ficha); NO manda
    nada si la cuenta no hizo ninguna mision (hoy tampoco sale FF9F) ni si no se sabe la EXP o el G que ya tiene el cliente.
    exp_dance queda en 0 (= lo que trae el FF00 de la plantilla en ese campo; HIPOTESIS para otra plantilla). Devuelve True si mando."""
    usn = usn_de(con)
    if exp_baja is None:
        entregar_pendientes_sin_romper(con)
    progreso = progreso_de(usn)
    if exp_baja is None:
        if not hay_progreso(progreso):
            return False
    if exp_baja is None:
        exp_baja = exp_de_ficha(con)
    if g_total is None:
        g_total = g_de_ficha(con)
    if exp_baja is None or g_total is None:
        anotar("   MISION restaurar NO mandado (usn %s): no se sabe la EXP o el G que ya tiene el cliente" % usn)
        return False
    con.mandar_interno(0x9F, seq, cuerpo_ff9f(progreso, exp_baja, exp_dance, g_total))
    total = rcoin_total(progreso)
    for codigo in RESTAURABLES:
        if hecha(progreso, FAMILIA_HISTORIA, codigo):
            con.mandar_interno(0x3A, seq, cuerpo_historia(HISTORIA_RESTAURAR, 0, total, codigo))
    anotar("   MISION restaurar usn %s: FF9F (EXP %d, G %d, Rcoin de misiones %d, tutoriales %d, tarjetas 0x%03x)"
           % (usn, exp_baja, g_total, total, tutoriales_seguidos(progreso), contadores_tarjetas(progreso)))
    return True


def al_entrar_al_lobby(con, seq, cuerpo):
    """C2S FF7F (el lobby al entrar con el personaje elegido, guia §7.5: opcodes 6 y 127). Restaura y devuelve False para
    que tienda.avatar conteste. No restaura dentro de una sala (el FF9F limpia el estado). El FF06 (personaje recien creado)
    no restaura: no tiene progreso."""
    if con.sala is None:
        try:
            restaurar(con, seq)
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ MISION restaurar: %r" % (e,))
    return False


def al_pedir_notas(con, seq, cuerpo):
    """C2S FF57 (op 87, notas de una cancion): anota la cancion en el intento abierto y devuelve False (la contesta juego.py)."""
    if len(cuerpo) >= 2:
        try:
            observar_musica(con, struct.unpack_from("<H", cuerpo, 0)[0])
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ MISION observar_musica: %r" % (e,))
    return False


MANEJADORES = {
    0x81: tutorial,
    0x3A: historia,
    0x63: adicional,
    0x9F: estado_progreso,
    0x7F: al_entrar_al_lobby,
    0x57: al_pedir_notas,
}
