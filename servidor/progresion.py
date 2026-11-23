# -*- coding: utf-8 -*-
r"""progresion.py (11-nov, ficha 83) — misiones de HOY (diarias, FF1FE) y SEMANALES (FF1F9) con estado propio por cuenta LOCAL.
M07 (22-nov): COBRO con llave MISIONES_COBRO (por omision \"1\"): FF1FF (diaria: 1 cupon 乐游券 11000246 por mision cumplida)
  y FF1FA (semanal: Reward_coin/Reward_exp de wmission_info.txt + Item_bonus de wmission_reward.txt). Los C2S van en 0 B (el
  exe no los cifra: el set 0x03a67de0 solo tiene 0x02 y 0x1F5). FF201 no se atiende (el exe no lo llama nunca) ni FF118.

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
LLAVES_OMISION = {"MISIONES_PROPIAS": "1", "MISIONES_COBRO": "1"}
GRADO = 1
GRUPO_SEMANA = 8          # HIPOTESIS: sin regla conocida (muestras: 5, 8)
RELOJ = time.time         # las pruebas lo cambian
PERIODO = 60.0            # el oficial empuja ~cada minuto (HIPOTESIS: los volcados no traen hora)
RELOJ_FIJOS = (119, 120, 121, 219, 220, 221)
DM_FIJOS = (10001, 10002, 10003)
CUPON_DIARIO = 11000246   # shop.txt Index de 乐游券 (items_tbitems.json id 11006246)
CUPON_SEMANAL = 11000226  # shop.txt Index de 每周任务券 (items_tbitems.json id 11006226)

_tablas = None
_avisado = False


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="MISIONES_PROPIAS"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def cobro_activo():
    return activo() and llave("MISIONES_COBRO")


def cargar(ruta=None):
    """(Re)lee las tablas. Si falla deja None y avisa una sola vez."""
    global _tablas, _avisado
    candidata = ruta or RUTA
    if ruta is None and not os.path.exists(candidata):
        alt = os.path.join(ajustes.carpeta_cuenta(), "progresion_tablas.json")
        if os.path.exists(alt):
            candidata = alt
    try:
        with open(candidata, "r", encoding="utf-8") as f:
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
            sec[k] = {"sello": s, "p": {}, "c": []}
        else:
            sec[k].setdefault("p", {})
            sec[k].setdefault("c", [])


def _leer_estado(usn, t):
    """(p_dia, c_dia, p_sem, c_sem) vigentes SIN escribir (si un sello es viejo, vacio)."""
    sec = _cta.leer_seccion(usn, "progresion") or {}
    d, s = sec.get("dia") or {}, sec.get("sem") or {}
    ok_d = d.get("sello") == sello_dia(t)
    ok_s = s.get("sello") == sello_semana(t)
    return (
        dict(d.get("p") or {}) if ok_d else {},
        set(str(x) for x in (d.get("c") or ())) if ok_d else set(),
        dict(s.get("p") or {}) if ok_s else {},
        set(str(x) for x in (s.get("c") or ())) if ok_s else set(),
    )


def _leer(usn, t):
    """(dia, sem) = ({id: progreso}, {id: progreso}) vigentes SIN escribir (si un sello viejo, vacio)."""
    p_dia, _c_dia, p_sem, _c_sem = _leer_estado(usn, t)
    return p_dia, p_sem


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


def _fila_ff1fe(t, p, c=()):
    ids = ids_dia(t)
    g = grupo_dia(t)
    cobradas = {str(x) for x in (c or ())}
    cuerpo = bytes([14]) + sello_dia(t).encode("ascii") + bytes([10, len(RELOJ_FIJOS) + len(ids)])
    for i in RELOJ_FIJOS:
        cuerpo += struct.pack("<I", i) + bytes([0]) + struct.pack("<II", i, 0) + bytes([1, 0])
    for i in ids:
        meta = _meta("dm_info", i) or 0
        v = min(meta, int(p.get(str(i), 0)))
        est = (3 if str(i) in cobradas else 2) if (meta and v >= meta) else 1
        cuerpo += struct.pack("<I", i) + bytes([g]) + struct.pack("<II", i, v) + bytes([est, 0])
    return cuerpo


def cuerpos(cuenta, t=None):
    """(FF1F9, FF1FE) para esta cuenta local, o None si el modulo esta apagado."""
    if not activo() or not cuenta or not cuenta.get("usn"):
        return None
    t = RELOJ() if t is None else t
    dia, c_dia, sem, _c_sem = _leer_estado(cuenta["usn"], t)
    return _fila_ff1f9(t, sem), _fila_ff1fe(t, dia, c_dia)


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


def _claro_c2s(cuerpo):
    """Cuerpo en claro de un C2S de mision: vacio/directo (el set 0x03a67de0 del exe solo cifra 0x02 y 0x1F5), o descifrado
    con el AES-256-CBC de 0x028a6970 si trae la cola fecddfbd. None si viene malformado."""
    if not cuerpo:
        return b""
    if len(cuerpo) >= 32 and cuerpo[-4:] == b"\xfe\xcd\xdf\xbd":
        n = struct.unpack_from("<I", cuerpo, len(cuerpo) - 8)[0]
        m = (n + 15) // 16 * 16
        if m + 16 > len(cuerpo):
            return None
        if n == 0:
            return b""
        return captura._aes_cbc_descifrar(captura.CLAVE_AES_FF02, captura.IV_AES_FF02, cuerpo[:m])[:n]
    return cuerpo


def _codigo_shop(item_id):
    """Convierte un id de items_tbitems.json (con digito de plazo/cantidad en los miles, p.ej. 11006226 -> 11000226) al Index
    de shop.txt, igual que hace el exe en 0x00bbd6ae y tienda._comprar."""
    item_id = int(item_id)
    if item_id >= 1000:
        dig = (item_id // 1000) % 10
        cand = item_id - dig * 1000
        if cand > 0:
            return cand
    return item_id


def cobrar_diaria(con, seq, cuerpo):
    """C2S FF1FF SendMyDMRecordReward (0 B en el exe; acepta tambien [u32 dmid] o cuerpo cifrado por 0x028a6970) ->
    cobra las misiones diarias del dia cumplidas (progreso >= meta) y NO cobradas. Da los cupones 乐游券 (11000246) con
    tienda.dar_objeto (y EXP/G con tienda.acreditar si la fila los define), contesta S2C FF1FF [u8 res][u8 B][u8 C] y
    empuja FF1FE con estado 3 en las cobradas."""
    if not cobro_activo():
        return False
    usn = _usn(con)
    if not usn:
        return False
    claro = _claro_c2s(cuerpo)
    if claro is None or len(claro) not in (0, 4):
        return False
    pedido = struct.unpack_from("<I", claro, 0)[0] if len(claro) == 4 else None
    t = RELOJ()
    vigentes = ids_dia(t)
    candidatas = [pedido] if (pedido is not None and pedido in vigentes) else ([] if pedido is not None else vigentes)
    premios_cfg = _tablas.get("premios") or {}
    dm_cupon = int(premios_cfg.get("dm_cupon", CUPON_DIARIO))
    cup_por_mision = int(premios_cfg.get("dm_cupones_por_mision", 1))

    def f(sec):
        _normalizar(sec, t)
        p = sec["dia"]["p"]
        c = sec["dia"]["c"]
        cobradas, cupones, g_tot, exp_tot = [], 0, 0, 0
        for i in candidatas:
            k = str(i)
            if k in c:
                continue
            fi = _fila_info("dm_info", i)
            if not fi:
                continue
            meta = int(fi[4])
            if meta <= 0 or int(p.get(k, 0)) < meta:
                continue
            c.append(k)
            cobradas.append(int(i))
            cupones += int(fi[8]) if len(fi) > 8 else cup_por_mision
            g_tot += int(fi[6]) if len(fi) > 6 else 0
            exp_tot += int(fi[7]) if len(fi) > 7 else 0
        return {"cobradas": cobradas, "cupones": cupones, "g": g_tot, "exp": exp_tot}

    r = _cta.cambiar_seccion(usn, "progresion", f)
    if not r["cobradas"]:
        con.mandar_interno(0x1FF, seq, bytes([1, 0, 0]))
        anotar("   C2S FF1FF cobrar diaria de %s: sin misiones cumplidas pendientes -> S2C FF1FF res=1"
               % (con.cuenta or {}).get("nick"))
        return True
    import tienda
    if r["cupones"] > 0:
        tienda.dar_objeto(usn, dm_cupon, r["cupones"], con=con)
    if r["exp"] > 0 or r["g"] > 0:
        tienda.acreditar(con, exp=r["exp"], g=r["g"])
        tienda.refrescar_saldos(con, g=bool(r["g"]))
    con.mandar_interno(0x1FF, seq, bytes([0, min(255, r["cupones"]), 0]))
    empujar(con, t)
    anotar("   C2S FF1FF cobrar diaria de %s: cobradas=%s -> +%d cupon(es) %d, +%d exp, +%d G"
           % ((con.cuenta or {}).get("nick"), r["cobradas"], r["cupones"], dm_cupon, r["exp"], r["g"]))
    return True


def cobrar_semanal(con, seq, cuerpo):
    """C2S FF1FA SendMyWMRecordNextGrade (0 B en el exe; acepta tambien [u32 wmid] o cuerpo cifrado por 0x028a6970) ->
    cobra las misiones semanales vigentes cumplidas (progreso >= meta) y NO cobradas. Acredita Reward_exp y Reward_coin de
    wmission_info.txt con tienda.acreditar (+ items de wmission_reward.txt con tienda.dar_objeto), refresca G (FF5B) y
    contesta S2C FF1FA [u8 res=1][u32 exp][u8 0][u8 0]."""
    if not cobro_activo():
        return False
    usn = _usn(con)
    if not usn:
        return False
    claro = _claro_c2s(cuerpo)
    if claro is None or len(claro) not in (0, 4):
        return False
    pedido = struct.unpack_from("<I", claro, 0)[0] if len(claro) == 4 else None
    t = RELOJ()
    vigentes = ids_semana()
    candidatas = [pedido] if (pedido is not None and pedido in vigentes) else ([] if pedido is not None else vigentes)
    wm_rew = _tablas.get("wm_reward") or {}

    def f(sec):
        _normalizar(sec, t)
        p = sec["sem"]["p"]
        c = sec["sem"]["c"]
        antes_n = len(c)
        cobradas, g_tot, exp_tot, items_bonus = [], 0, 0, []
        for i in candidatas:
            k = str(i)
            if k in c:
                continue
            fi = _fila_info("wm_info", i)
            if not fi:
                continue
            meta = int(fi[4])
            if meta <= 0 or int(p.get(k, 0)) < meta:
                continue
            c.append(k)
            cobradas.append(int(i))
            g_tot += int(fi[5]) if len(fi) > 5 else 10
            exp_tot += int(fi[6]) if len(fi) > 6 else 100
        if cobradas:
            despues_n = len(c)
            fila_r = wm_rew.get("%d,%d" % (GRADO, despues_n))
            if fila_r and len(fila_r) >= 3:
                ya_dados = int(sec["sem"].get("items_dados", 0))
                nuevos_items = list(fila_r[2])[ya_dados:] if len(fila_r[2]) > ya_dados else []
                if nuevos_items:
                    items_bonus = [_codigo_shop(it) for it in nuevos_items]
                    sec["sem"]["items_dados"] = len(fila_r[2])
        return {"cobradas": cobradas, "g": g_tot, "exp": exp_tot, "items": items_bonus, "antes": antes_n}

    r = _cta.cambiar_seccion(usn, "progresion", f)
    if not r["cobradas"]:
        con.mandar_interno(0x1FA, seq, struct.pack("<BIBB", 2, 0, 0, 0))
        anotar("   C2S FF1FA cobrar semanal de %s: sin misiones cumplidas pendientes -> S2C FF1FA res=2"
               % (con.cuenta or {}).get("nick"))
        return True
    import tienda
    if r["exp"] > 0 or r["g"] > 0:
        tienda.acreditar(con, exp=r["exp"], g=r["g"])
        tienda.refrescar_saldos(con, g=bool(r["g"]))
    conteo_items = {}
    for it in r["items"]:
        conteo_items[it] = conteo_items.get(it, 0) + 1
    for it, cant in conteo_items.items():
        tienda.dar_objeto(usn, it, cant, con=con)
    con.mandar_interno(0x1FA, seq, struct.pack("<BIBB", 1, r["exp"] & 0xFFFFFFFF, 0, 0))
    empujar(con, t)
    anotar("   C2S FF1FA cobrar semanal de %s: cobradas=%s -> +%d exp, +%d G, items=%s"
           % ((con.cuenta or {}).get("nick"), r["cobradas"], r["exp"], r["g"], r["items"]))
    return True


MANEJADORES = {
    0x1FF: cobrar_diaria,
    0x1FA: cobrar_semanal,
}
