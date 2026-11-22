# -*- coding: utf-8 -*-
r"""progresion.py (11-nov, ficha 83) — misiones de HOY (diarias, FF1FE) y SEMANALES (FF1F9) con estado propio por cuenta LOCAL.
SIN PREMIOS: FF118, FF1FF, FF1FA y FF201 siguen sin atender (no hay montos del oficial).

LEIDO / MEDIDO (docs/tablero/layouts/FF1F9.md, FF1FE.md, seccion "Lectura de la ficha 83"):
  FF1F9 = [u8 14][sello 14 cifras][u8 grado][u8 grupo][u8 n=10][n x {u32 id, fila 12 B}][u8 0]
          fila = [u8 grado][u8 grupo][u32 WMID][u32 progreso][u8 estado 1|2][u8 0]      (179 B en 49 de 49 muestras)
  FF1FE = [u8 14][sello][u8 10][u8 n=11][n x {u32 id, fila 11 B}]
          fila = [u8 grupo del dia o 0][u32 DMID][u32 progreso][u8 estado][u8 0]          (182 B en 38 de 38)
  El cliente compara progreso con `Goal` de la tabla y si progreso > meta escribe un error: se corta SIEMPRE en la meta.
  Estado 2 = progreso >= meta (46/46 y 29/29 en las muestras). Los 10 ids del FF1F9 son wmission_list[grado,grupo] (49/49).
  El sello del dia es las 00:00 del dia siguiente; el de la semana, el lunes 05:00 (inicio de semana) (muestras).
HIPOTESIS (anotadas): el GRUPO SEMANAL no tiene regla conocida (5 y 8 en dos semanas): se manda siempre GRUPO_SEMANA = 8.
  El GRUPO DIARIO casa con "dia de la semana + 2" (domingo=0; 3 de 3 jornadas: dom 2, mar 4, jue 6); para que siempre exista en
  dmission_info.txt (grupos 1..7) se usa ((dom0 + 1) % 7) + 1, que da 2, 4 y 6 en esos tres dias. Los 6 ids fijos 119..121 y
  219..221 se mandan como en las muestras (progreso 0, estado 1; HIPOTESIS: premios de reloj de las 19/20/21 h).
QUE SE CUENTA (lo que el servidor YA sabe): Stay (segundos conectado, +lo transcurrido en cada empujon de ~60 s), monedas y EXP
  de tienda.acreditar (Login/Coin, Login/Exp), y carreras por modo segun sala.modo (nombres de los modos por el texto chino de
  las tablas: Team/Single/Relay/Couplematch x Speed/Item/Original; Leader=队长战, Pigrace=食神, Rnote=节奏达人, Coop=合作).
  QUEDA EN 0: Fortune (占卜), los 6 ids de reloj, y los modos que ninguna fila nombra (persecucion, heroe).
Guardado: seccion `progresion` de la cuenta en cuenta.json (solo via cuenta.py): {"dia": {"sello", "p": {id: n}}, "sem": {...}}.
  Cuando el sello cambia, esa parte vuelve a 0 y nada mas. La sesion capturada (sin cuenta local) NO pasa por aqui: recibe la captura.
Llave MISIONES_PROPIAS=0 apaga todo (vuelve a la captura). Si falta datos/progresion_tablas.json (herramientas/preparar_progresion.py)
  el modulo se apaga solo y avisa UNA vez.
"""
import json
import os
import struct
import time

import ajustes
import captura
import cuenta as _cta
import estado

RUTA = os.path.join(ajustes.DATOS, "progresion_tablas.json")
LLAVES_OMISION = {"MISIONES_PROPIAS": "1"}
GRADO = 1
GRUPO_SEMANA = 8          # HIPOTESIS: sin regla conocida (muestras: 5, 8)
RELOJ = time.time         # las pruebas lo cambian
PERIODO = 60.0            # el oficial empuja ~cada minuto (HIPOTESIS: los volcados no traen hora)
RELOJ_FIJOS = (119, 120, 121, 219, 220, 221)
DM_FIJOS = (10001, 10002, 10003)

_tablas = None
_avisado = False


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="MISIONES_PROPIAS"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def cargar(ruta=None):
    """(Re)lee las tablas. Si falla deja None y avisa una sola vez."""
    global _tablas, _avisado
    try:
        with open(ruta or RUTA, "r", encoding="utf-8") as f:
            _tablas = json.load(f)
        _avisado = False
    except (OSError, ValueError):
        _tablas = {}
        if not _avisado:
            anotar("   progresion: no puedo leer %s (correr herramientas/preparar_progresion.py): misiones de la captura" % (ruta or RUTA))
            _avisado = True
    return bool(_tablas)


def activo():
    if not llave():
        return False
    if _tablas is None:
        cargar()
    return bool(_tablas)


# ---------- sellos y grupos ----------
def sello_dia(t):
    """00:00 del dia siguiente (muestras: 38 de 38 FF1FE)."""
    lt = time.localtime(t)
    sig = time.localtime(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1, 0, 0, 0, 0, 0, -1)))
    return time.strftime("%Y%m%d%H%M%S", sig)


def sello_semana(t):
    """El lunes 05:00 de esta semana (muestras: 49 de 49 FF1F9; si es antes del lunes 05:00, el de la semana anterior)."""
    lt = time.localtime(t)
    dias = lt.tm_wday                                  # lunes = 0
    if dias == 0 and lt.tm_hour < 5:
        dias = 7
    lunes = time.localtime(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - dias, 5, 0, 0, 0, 0, -1)))
    return time.strftime("%Y%m%d%H%M%S", lunes)


def grupo_dia(t):
    """HIPOTESIS 'dia de la semana + 2' (domingo=0) llevado a 1..7: dom 2, lun 3, mar 4, mie 5, jue 6, vie 7, sab 1."""
    dom0 = (time.localtime(t).tm_wday + 1) % 7
    return ((dom0 + 1) % 7) + 1


def ids_semana():
    return list((_tablas.get("wm_list") or {}).get("%d,%d" % (GRADO, GRUPO_SEMANA)) or [])


def ids_dia(t):
    g = grupo_dia(t)
    dia = sorted(int(k) for k, v in (_tablas.get("dm_info") or {}).items() if v[0] == g)
    return list(DM_FIJOS) + dia


def _meta(tabla, i):
    f = (_tablas.get(tabla) or {}).get(str(i))
    return f[4] if f else None


def _fila_info(tabla, i):
    return (_tablas.get(tabla) or {}).get(str(i))


# ---------- estado ----------
def _normalizar(sec, t):
    """Dentro de cambiar_seccion: si un sello cambio, esa parte vuelve a 0 (y nada mas)."""
    for k, s in (("dia", sello_dia(t)), ("sem", sello_semana(t))):
        if (sec.get(k) or {}).get("sello") != s:
            sec[k] = {"sello": s, "p": {}}


def _leer(usn, t):
    """(dia, sem) = ({id: progreso}, {id: progreso}) vigentes SIN escribir (si un sello viejo, vacio)."""
    sec = _cta.leer_seccion(usn, "progresion") or {}
    d, s = sec.get("dia") or {}, sec.get("sem") or {}
    return (dict(d.get("p") or {}) if d.get("sello") == sello_dia(t) else {},
            dict(s.get("p") or {}) if s.get("sello") == sello_semana(t) else {})


def _suma(usn, t, cond, cantidad):
    """Suma `cantidad` a todas las filas de hoy y de la semana que cuentan la condicion `cond` = (Mtype, What1, What2),
    cortado en la meta. Una sola escritura con el candado."""
    dia, sem = ids_dia(t), ids_semana()

    def f(sec):
        _normalizar(sec, t)
        for parte, ids, tabla in (("dia", dia, "dm_info"), ("sem", sem, "wm_info")):
            p = sec[parte]["p"]
            for i in ids:
                fi = _fila_info(tabla, i)
                if fi is None:
                    continue
                if (fi[1], fi[2], fi[3]) == cond:
                    p[str(i)] = min(fi[4], int(p.get(str(i), 0)) + cantidad)
    _cta.cambiar_seccion(usn, "progresion", f)


def _usn(con):
    c = getattr(con, "cuenta", None)
    return c.get("usn") if c else None


# ---------- los cuerpos ----------
def _fila_ff1f9(t, p):
    ids = ids_semana()
    h = GRUPO_SEMANA
    cuerpo = bytes([14]) + sello_semana(t).encode("ascii") + bytes([GRADO, h, len(ids)])
    for i in ids:
        meta = _meta("wm_info", i) or 0
        v = min(meta, int(p.get(str(i), 0)))
        cuerpo += struct.pack("<I", i) + bytes([GRADO, h]) + struct.pack("<II", i, v) + bytes([2 if meta and v >= meta else 1, 0])
    return cuerpo + b"\x00"


def _fila_ff1fe(t, p):
    ids = ids_dia(t)
    g = grupo_dia(t)
    cuerpo = bytes([14]) + sello_dia(t).encode("ascii") + bytes([10, len(RELOJ_FIJOS) + len(ids)])
    for i in RELOJ_FIJOS:
        cuerpo += struct.pack("<I", i) + bytes([0]) + struct.pack("<II", i, 0) + bytes([1, 0])
    for i in ids:
        meta = _meta("dm_info", i) or 0
        v = min(meta, int(p.get(str(i), 0)))
        cuerpo += struct.pack("<I", i) + bytes([g]) + struct.pack("<II", i, v) + bytes([2 if meta and v >= meta else 1, 0])
    return cuerpo


def cuerpos(cuenta, t=None):
    """(FF1F9, FF1FE) para esta cuenta local, o None si el modulo esta apagado."""
    if not activo() or not cuenta or not cuenta.get("usn"):
        return None
    t = RELOJ() if t is None else t
    dia, sem = _leer(cuenta["usn"], t)
    return _fila_ff1f9(t, sem), _fila_ff1fe(t, dia)


# ---------- la rafaga de entrada ----------
def lote_para(lote, cuenta):
    """El lote capturado con SUS FF1F9 y FF1FE (los internos se rearman; el largo de cada uno va en su cabecera propia)."""
    try:
        if not cuenta or not (b"\xfe\xf9" in lote or b"\xfe\xfe" in lote):
            return lote
        nuevos = cuerpos(cuenta)
        if nuevos is None:
            return lote
        if lote[:2] != b"\xff\x56":
            return lote
        k = 4 + struct.unpack_from("<H", lote, 2)[0]
        out, cambios = lote[:k], 0
        while k + 8 <= len(lote):
            fl, cmd = lote[k], lote[k + 1]
            seq, ln = struct.unpack_from("<HI", lote, k + 2)
            if k + 8 + ln > len(lote):
                break
            cu = lote[k + 8:k + 8 + ln]
            if fl == 0xFE and cmd in (0xF9, 0xFE):
                cu = nuevos[0] if cmd == 0xF9 else nuevos[1]
                cambios += 1
            out += bytes([fl, cmd]) + struct.pack("<HI", seq, len(cu)) + cu
            k += 8 + ln
        out += lote[k:]
        if cambios:
            anotar("   progresion: %d mision(es) propias en la rafaga de entrada de %s" % (cambios, cuenta.get("nick")))
        return out
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ progresion.lote_para: %r" % e)
        return lote


# ---------- lo que se cuenta ----------
def ganancia(con, exp=0, g=0):
    """tienda.acreditar lo llama: monedas y EXP ganadas (Login/Coin, Login/Exp). Cuenta sin usn = no hace nada."""
    try:
        usn = _usn(con)
        if not usn or not activo():
            return
        t = RELOJ()
        if exp:
            _suma(usn, t, ("Login", "Exp", ""), int(exp))
        if g:
            _suma(usn, t, ("Login", "Coin", ""), int(g))
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ progresion.ganancia: %r" % e)


def condicion_de_modo(modo):
    """(What1, What2) de la carrera segun sala.modo, o None si ninguna fila lo nombra. Los especiales primero."""
    for bit, what1 in ((0x200, "Pigrace"), (0x800, "Rnote"), (0x4000, "Leader"), (0x8000, "Coop")):
        if modo & bit:
            return what1, ""
    if modo & (0x20000 | 0x200000):
        return None                                   # heroe y persecucion: ninguna fila los nombra
    if modo & 0x2000:
        what1 = "Couplematch"
    elif modo & 0x20:
        what1 = "Relay"
    elif modo & 0x10:
        what1 = "Team"
    elif modo & 0x08:
        what1 = "Single"
    else:
        return None
    what2 = "Speed" if modo & 0x02 else "Item" if modo & 0x04 else "Original" if modo & 0x80 else None
    return (what1, what2) if what2 else None


def tras_carrera(jugadores, modo):
    """carrera.mandar_cartel lo llama despues del FF28: +1 al modo de cada jugador local y empuja sus FF1F9/FF1FE."""
    try:
        if not activo():
            return
        cm = condicion_de_modo(modo)
        t = RELOJ()
        for con in jugadores:
            usn = _usn(con)
            if not usn:
                continue
            _stay(con, usn, t)
            if cm is not None:
                _suma(usn, t, ("Game",) + cm, 1)
            empujar(con, t)
        if cm is None:
            anotar("   progresion: el modo 0x%x no lo nombra ninguna mision: solo monedas, EXP y Stay" % modo)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ progresion.tras_carrera: %r" % e)


def empujar(con, t=None):
    """Manda FF1F9 y FF1FE con el estado actual a una conexion local."""
    t = RELOJ() if t is None else t
    nuevos = cuerpos(con.cuenta, t)
    if nuevos is None:
        return False
    con.mandar_interno(0x1F9, 0, nuevos[0])
    con.mandar_interno(0x1FE, 0, nuevos[1])
    con.prog_t = t
    anotar("   S2C FF1F9 + FF1FE (misiones propias de %s)" % (con.cuenta or {}).get("nick"))
    return True


def _stay(con, usn, t):
    """Suma a Stay los segundos desde el ultimo empujon (tope 3 minutos: un cliente dormido no regala horas)."""
    antes = getattr(con, "prog_t", None)
    if antes is None or t <= antes:
        return
    _suma(usn, t, ("Login", "Stay", ""), int(min(t - antes, 3 * PERIODO)))
    con.prog_t = t


def tick(con):
    """manejadores.despachar lo llama en cada comando: cada PERIODO s de conexion suma el tiempo a Stay y empuja los dos."""
    try:
        usn = _usn(con)
        if not usn or not activo():
            return
        t = RELOJ()
        antes = getattr(con, "prog_t", None)
        if antes is None:
            con.prog_t = t
            return
        if t - antes < PERIODO:
            return
        _stay(con, usn, t)
        empujar(con, t)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ progresion.tick: %r" % e)


MANEJADORES = {}          # no atiende comandos del cliente (los premios FF118/FF1FF/FF1FA/FF201 siguen sin atender)
