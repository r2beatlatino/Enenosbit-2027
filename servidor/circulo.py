# -*- coding: utf-8 -*-
r"""circulo.py (M12, 22-nov) — circulos (clanes) reales, primera parte (membresia, chat y aviso).

Medicion (docs/tablero_maduracion/M12_circulos.md):
  - En el cliente moderno NO existe ventana ni paquete FFxx medido para crear, invitar, unirse, salir o echar
    (los metodos `familySys.*` no tienen JSON medido y el cliente clasico hacia esto en la web).
    Por eso la gestion entra por chat (`.circulo ...`, enganchado en `charla.py`), respondiendo con `gm.cuerpo_anuncio`
    (S2C FF1F4 tipo 1 de 161 B, forma medida) solo al que lo pidio.
  - Formas medidas en el tunel FF40 (`docs/tablero/layouts/FF40.md` + `docs/tablero/BODA_LECTURA.md:356`):
      C2S FF40 0x21 `SendGetGuildInfo`: `[0x21]` (1 B).
      S2C FF40 0x21 GuildInfo (`#175..#198`, `@0x027a0e80..0x027a118a`):
        `[0x21][u8 res=0][u8 L][nombre]` + por cada miembro conectado (sin el propio):
        `[u32 uid][u8 a][u8 b][u8 c][6 x u32][u8 L][apodo][u8 extra]` +
        `[u32 0xFFFFFFFF][u16 total][u8 L][aviso][u8 lider][u8 extra][u8 L_extra=0]` (sin circulo = 13 B exactos).
      C2S FF40 0x22 `SendGuildChat`: `[0x22][u8 L][texto]` ->
      S2C FF40 0x24 (`#153..#158`, `@0x027a156d..0x027a15e7`): `[0x24][u8 L1][apodo][u8 L2][texto][u8 color][u8 extra]`
        a los miembros conectados del mismo circulo (sin eco al que escribe, como en 2013).
      C2S FF40 0x23 `SendChangeGuildNotifier`: `[0x23][u8 L][aviso]` (solo lider) ->
      S2C FF40 0x25 (`#151..#152`, `@0x027a1702..0x027a1718`): `[0x25][u8 L][aviso]` a todos los miembros conectados.
  - FFD4 (245 B), FFD7 (4807 B), FFE3 (108 B/fila) y demas opcodes de economia/tienda NO tienen layout medido en el
    cliente moderno: se dejan sin atender como hoy.

Guardado (compatible con CUENTA_SQLITE=0 y CUENTA_SQLITE=1):
  - Clave de arriba `"circulos"` (via `cuenta.leer_arriba` / `cuenta.cambiar_arriba` / `cuenta.cambiar_todas`, tabla
    `arriba` en SQLite): `{"<id>": {"id": int, "nombre": str, "lider": usn, "miembros": {"<usn>": rango}, "aviso": str, "fecha": str}}`.
  - En cada cuenta (`d["cuentas"][str(usn)]`): `"circulo": id` (o sin la clave si no pertenece a ninguno).

Llave `CIRCULOS` (entorno, leida en el momento, por omision `"1"`): con `"0"` todo queda exactamente como antes.
"""
import os
import re
import struct
import threading
import time

import cuenta
import estado
import gm
import textos

REMITENTE = "Circulo"
RANGO_LIDER = 0x5A
RANGO_JEFE = 0x50
RANGO_MIEMBRO = 0x0A

NOMBRE_MIN = 2
NOMBRE_MAX = 12
APODO_MAX = 13
AVISO_MAX = 120
CHAT_MAX = 200
CHAT_COLOR = 2                  # 2 = verde (tabla de colores del cliente en 2013)
MAX_MIEMBROS = 50
INVITACION_TTL = 300.0          # segundos que dura una invitacion pendiente en memoria

_NOMBRE_OK = re.compile(r"^[A-Za-z0-9_\-.*&]+$")
SIN_CIRCULO_FF40_21 = b"\x21\x00\x00" + b"\xff" * 4 + bytes(6)

# Estado vivo en estado.py para sobrevivir a recargas en caliente.
_INVITACIONES = estado.__dict__.setdefault("CIRCULO_INVITACIONES", {})   # target_usn -> {"cid", "por", "ts"}
_CANDADO = estado.__dict__.setdefault("CIRCULO_CANDADO", threading.RLock())

# Reloj del modulo (las pruebas pueden reemplazarlo).
reloj = time.time


def anotar(txt):
    estado.anotar(txt)


def activo():
    """Llave CIRCULOS (entorno, leida en el momento, por omision '1')."""
    return os.environ.get("CIRCULOS", "1").strip().lower() not in ("0", "no", "false", "")


def _usn_de(con):
    u = (getattr(con, "cuenta", None) or {}).get("usn")
    return int(u) if u else None


def _nick_de_acc(acc, defecto=""):
    if not isinstance(acc, dict):
        return defecto
    pj = acc.get("personaje") or {}
    cta = acc.get("cuenta") or {}
    return str(pj.get("nick") or cta.get("nick") or defecto).strip()


def _nick_de_con(con):
    cta = getattr(con, "cuenta", None) or {}
    pj = cta.get("personaje") or {}
    return str(pj.get("nick") or cta.get("nick") or "").strip()


def _quien_de(con):
    nick = _nick_de_con(con) or "?"
    usn = _usn_de(con)
    return "%s (usn %d)" % (nick, usn) if usn else nick


def _circulos_leer():
    """Copia del diccionario de arriba 'circulos' ({str(id): dict})."""
    datos = cuenta.leer_arriba("circulos", {})
    return datos if isinstance(datos, dict) else {}


def circulo_de(usn):
    """El dict del circulo al que pertenece `usn`, o None si no esta en ninguno."""
    if not usn:
        return None
    acc = cuenta.leer(usn)
    if not acc:
        return None
    cid = acc.get("circulo")
    if not cid:
        return None
    c = _circulos_leer().get(str(cid))
    if not isinstance(c, dict):
        return None
    if str(int(usn)) not in (c.get("miembros") or {}):
        return None
    return c


def _conectados_del_circulo(c, excluir_usn=None):
    """Lista de (usn, con) de los miembros actualmente conectados del circulo `c`."""
    miembros = c.get("miembros") or {}
    vistos = set()
    out = []
    for con in list(estado.CONEXIONES.values()):
        if getattr(con, "cerrada", False):
            continue
        u = _usn_de(con)
        if u is None or u in vistos:
            continue
        if excluir_usn is not None and u == int(excluir_usn):
            continue
        if str(u) in miembros:
            vistos.add(u)
            out.append((u, con))
    return out


def _conexion_de(usn):
    if not usn:
        return None
    u_obj = int(usn)
    for con in list(estado.CONEXIONES.values()):
        if getattr(con, "cerrada", False):
            continue
        if _usn_de(con) == u_obj:
            return con
    return None


def _avisar_uno(con, texto):
    """Manda S2C FF1F4 tipo 1 (161 B, forma medida) SOLO al jugador indicado."""
    if con is None or getattr(con, "cerrada", False):
        return False
    try:
        con.mandar_interno(0x1F4, 0, gm.cuerpo_anuncio(texto, remitente=REMITENTE))
        return True
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ circulo aviso a uno: %r" % e)
        return False


# ====================================================================================================================
# FORMAS MEDIDAS EN FF40 (docs/tablero/layouts/FF40.md + BODA_LECTURA.md:356)
# ====================================================================================================================

def armar_ff40_21(nombre="", miembros=(), total=0, aviso="", lider=0):
    """S2C FF40 0x21 GuildInfo (`#175..#198`, `@0x027a0e80..0x027a118a`):
      [0x21][u8 res=0][u8 L][nombre]
      por miembro conectado (sin el propio): [u32 uid][u8 a][u8 b][u8 c][6 x u32][u8 L][apodo<=13][u8 extra]
      [u32 0xFFFFFFFF][u16 total][u8 L][aviso][u8 lider][u8 extra=0][u8 L_extra=0]
    Sin circulo devuelve exactamente los 13 B del oficial (`SIN_CIRCULO_FF40_21`).
    """
    nom_b = textos.codificar(str(nombre or ""), NOMBRE_MAX)
    out = bytearray(bytes([0x21, 0, len(nom_b)]) + nom_b)
    for uid, rango, apodo in miembros:
        ap_b = textos.codificar(str(apodo or ""), APODO_MAX)
        out += struct.pack("<IBBB6I", int(uid) & 0xFFFFFFFF, 1, int(rango) & 0xFF, 0, 0, 0, 0, 0, 0, 0)
        out += bytes([len(ap_b)]) + ap_b + b"\x00"
    av_b = textos.codificar(str(aviso or ""), AVISO_MAX)
    out += struct.pack("<IH", 0xFFFFFFFF, int(total) & 0xFFFF)
    out += bytes([len(av_b)]) + av_b
    out += bytes([1 if lider else 0, 0, 0])
    return bytes(out)


def armar_ff40_24(apodo, texto, color=CHAT_COLOR, extra=0):
    """S2C FF40 0x24 chat del circulo (`#153..#158`, `@0x027a156d..0x027a15e7`):
      [0x24][u8 L1][apodo<=13][u8 L2][texto<=200][u8 color][u8 extra]
    """
    ap_b = textos.codificar(str(apodo or ""), APODO_MAX)
    if isinstance(texto, (bytes, bytearray)):
        tx_b = bytes(texto)[:CHAT_MAX]
    else:
        tx_b = textos.codificar(str(texto or ""), CHAT_MAX)
    return bytes([0x24, len(ap_b)]) + ap_b + bytes([len(tx_b)]) + tx_b + bytes([color & 0xFF, extra & 0xFF])


def armar_ff40_25(aviso):
    """S2C FF40 0x25 aviso del circulo (`#151..#152`, `@0x027a1702..0x027a1718`):
      [0x25][u8 L][aviso<=120]
    """
    av_b = textos.codificar(str(aviso or ""), AVISO_MAX)
    return bytes([0x25, len(av_b)]) + av_b


def guildinfo_de(usn):
    """Arma el cuerpo S2C FF40 0x21 real para `usn` (o `SIN_CIRCULO_FF40_21` si no tiene circulo)."""
    c = circulo_de(usn) if (usn and activo()) else None
    # 22-nov (cerebro): los campos intermedios por miembro (3*u8 + 6*u32 + u8) y la cola NO estan medidos con el juego; el
    # cliente lee esto al abrir el panel del circulo. Hasta el 2.o testigo va APAGADO: CIRCULO_PANEL=1 lo prende.
    if not c or os.environ.get("CIRCULO_PANEL", "0").strip().lower() not in ("1", "si"):
        return SIN_CIRCULO_FF40_21
    miembros_map = c.get("miembros") or {}
    conectados = []
    for u_m, con_m in _conectados_del_circulo(c, excluir_usn=usn):
        rango = int(miembros_map.get(str(u_m), RANGO_MIEMBRO))
        conectados.append((u_m, rango, _nick_de_con(con_m)))
    conectados.sort(key=lambda x: (0 if x[1] == RANGO_LIDER else (1 if x[1] == RANGO_JEFE else 2), x[0]))
    es_lider = 1 if int(c.get("lider", 0)) == int(usn) else 0
    return armar_ff40_21(
        nombre=c.get("nombre", ""),
        miembros=conectados,
        total=len(miembros_map),
        aviso=c.get("aviso", ""),
        lider=es_lider,
    )


def enviar_info(con, seq=0):
    """Contesta C2S FF40 0x21 (o refresca el panel) con el circulo real."""
    usn = _usn_de(con)
    cu = guildinfo_de(usn)
    con.mandar_interno(0x40, seq, cu)
    return True


def _refrescar_usns(usns):
    """Re-envia FF40 0x21 a los usn conectados indicados."""
    for u in set(int(x) for x in usns if x):
        c = _conexion_de(u)
        if c is not None:
            try:
                enviar_info(c, 0)
            except Exception as e:                                       # noqa: BLE001
                anotar("   ⛔ circulo refrescar usn %d: %r" % (u, e))


def chat_circulo(con, seq, cuerpo):
    """C2S FF40 0x22 [0x22][u8 L][texto]: difunde S2C FF40 0x24 a los miembros conectados del mismo circulo."""
    if not activo():
        return False
    if len(cuerpo) < 2:
        return False
    L = cuerpo[1]
    if len(cuerpo) < 2 + L:
        return False
    usn = _usn_de(con)
    if usn is None:
        return True
    if gm.esta_silenciado(con):
        anotar("   CIRCULO chat bloqueado (silenciado): %s" % _quien_de(con))
        return True
    c = circulo_de(usn)
    if not c:
        anotar("   CIRCULO chat de %s sin circulo: ignorado" % _quien_de(con))
        return True
    msg_b = cuerpo[2:2 + L].split(b"\0", 1)[0]
    if not msg_b.strip():
        return True
    apodo = _nick_de_con(con) or _nick_de_acc(cuenta.leer(usn), "#%d" % usn)
    paquete = armar_ff40_24(apodo, msg_b, CHAT_COLOR, 0)
    enviados = 0
    for _u_m, con_m in _conectados_del_circulo(c, excluir_usn=usn):
        try:
            con_m.mandar_interno(0x40, 0, paquete)
            enviados += 1
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ circulo chat a miembro: %r" % e)
    anotar("   CIRCULO %r chat de %s -> %d miembro(s)" % (c.get("nombre"), apodo, enviados))
    return True


def poner_aviso(con, texto_aviso):
    """Guarda el aviso del circulo (solo el lider) y difunde S2C FF40 0x25 a todos los miembros conectados.
    Devuelve (ok, mensaje)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local"
    c = circulo_de(usn)
    if not c:
        return False, "no estas en ningun circulo"
    if int(c.get("lider", 0)) != usn:
        return False, "solo el lider puede cambiar el aviso"
    cid_s = str(c["id"])
    limpio = str(texto_aviso or "").strip()[:AVISO_MAX]

    def actualizar(circulos_d):
        reg = circulos_d.get(cid_s)
        if not isinstance(reg, dict) or int(reg.get("lider", 0)) != usn:
            return None
        reg["aviso"] = limpio
        return dict(reg)

    try:
        reg_nuevo = cuenta.cambiar_arriba("circulos", actualizar, {})
    except cuenta.CuentaError as e:
        anotar("   ⛔ circulo aviso %s: %s" % (_quien_de(con), e))
        return False, "circulo: error al guardar el aviso"
    if reg_nuevo is None:
        return False, "solo el lider puede cambiar el aviso"

    paquete = armar_ff40_25(limpio)
    enviados = 0
    for _u_m, con_m in _conectados_del_circulo(reg_nuevo):
        try:
            con_m.mandar_interno(0x40, 0, paquete)
            enviados += 1
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ circulo aviso 0x25: %r" % e)
    anotar("   CIRCULO %r aviso de %s: %r -> %d miembro(s)" % (reg_nuevo.get("nombre"), _quien_de(con), limpio, enviados))
    return True, ("aviso actualizado: %s" % limpio) if limpio else "aviso borrado"


def aviso_desde_cliente(con, seq, cuerpo):
    """C2S FF40 0x23 [0x23][u8 L][aviso]: cambia el aviso si es el lider y difunde S2C FF40 0x25."""
    if not activo():
        return False
    if len(cuerpo) < 2:
        return False
    L = cuerpo[1]
    if len(cuerpo) < 2 + L:
        return False
    texto = textos.decodificar(cuerpo[2:2 + L].split(b"\0", 1)[0])
    poner_aviso(con, texto)
    return True


# ====================================================================================================================
# OPERACIONES DE MEMBRESIA (atomicas via cuenta.cambiar_todas)
# ====================================================================================================================

def _buscar_usn_en_cuentas(cuentas_map, apodo):
    """Busca el usn (int) de una cuenta por apodo (primero exacto, luego sin distinguir mayusculas)."""
    obj = str(apodo or "").strip()
    if not obj:
        return None
    obj_low = obj.casefold()
    exacto = None
    aprox = None
    for k, acc in cuentas_map.items():
        nick = _nick_de_acc(acc)
        if not nick:
            continue
        if nick == obj:
            exacto = int((acc.get("cuenta") or {}).get("usn") or k)
            break
        if aprox is None and nick.casefold() == obj_low:
            aprox = int((acc.get("cuenta") or {}).get("usn") or k)
    return exacto if exacto is not None else aprox


def crear(con, nombre):
    """Crea un circulo nuevo y deja al creador como lider. Devuelve (ok, mensaje, cid)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local", None
    nom = str(nombre or "").strip()
    nom_b = textos.codificar(nom, NOMBRE_MAX + 1)
    if not (NOMBRE_MIN <= len(nom) <= NOMBRE_MAX) or len(nom_b) > NOMBRE_MAX or not _NOMBRE_OK.match(nom):
        return False, "nombre invalido (2..%d caracteres: letras, numeros y _ - . * &)" % NOMBRE_MAX, None

    fecha = time.strftime("%Y-%m-%d %H:%M:%S")

    def op(d):
        cuentas_map = d.get("cuentas") or {}
        acc = cuentas_map.get(str(usn))
        if acc is None:
            return False, "circulo: cuenta local no encontrada", None
        circulos_d = d.setdefault("circulos", {})
        cid_actual = acc.get("circulo")
        if cid_actual and str(cid_actual) in circulos_d and str(usn) in (circulos_d[str(cid_actual)].get("miembros") or {}):
            return False, "ya estas en un circulo (.circulo salir para dejarlo)", None
        nom_low = nom.casefold()
        for reg in circulos_d.values():
            if isinstance(reg, dict) and str(reg.get("nombre") or "").casefold() == nom_low:
                return False, "ya existe un circulo con el nombre %s" % nom, None
        cid = max((int(k) for k in circulos_d if str(k).isdigit()), default=0) + 1
        circulos_d[str(cid)] = {
            "id": cid,
            "nombre": nom,
            "lider": usn,
            "miembros": {str(usn): RANGO_LIDER},
            "aviso": "",
            "fecha": fecha,
        }
        acc["circulo"] = cid
        return True, "circulo %s creado: sos el lider" % nom, cid

    try:
        ok, msg, cid = cuenta.cambiar_todas(op)
    except cuenta.CuentaError as e:
        anotar("   ⛔ circulo crear %s: %s" % (_quien_de(con), e))
        return False, "circulo: error al guardar", None
    if ok:
        anotar("   CIRCULO CREADO: %r (id=%d) lider %s" % (nom, cid, _quien_de(con)))
        _refrescar_usns([usn])
    return ok, msg, cid


def invitar(con, apodo):
    """El lider invita a un jugador por apodo (guardado en memoria hasta `.circulo aceptar`). Devuelve (ok, mensaje)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local"
    c = circulo_de(usn)
    if not c:
        return False, "no estas en ningun circulo"
    if int(c.get("lider", 0)) != usn:
        return False, "solo el lider puede invitar"
    miembros = c.get("miembros") or {}
    if len(miembros) >= MAX_MIEMBROS:
        return False, "el circulo %s esta lleno (%d miembros)" % (c["nombre"], MAX_MIEMBROS)

    todas = cuenta.todas()
    target_usn = _buscar_usn_en_cuentas(todas, apodo)
    if target_usn is None:
        return False, "no existe el jugador %s" % apodo
    if target_usn == usn:
        return False, "no te podes invitar a vos mismo"
    if str(target_usn) in miembros:
        return False, "%s ya esta en tu circulo" % apodo
    acc_t = todas.get(str(target_usn)) or {}
    cid_t = acc_t.get("circulo")
    if cid_t:
        c_otro = _circulos_leer().get(str(cid_t))
        if isinstance(c_otro, dict) and str(target_usn) in (c_otro.get("miembros") or {}):
            return False, "%s ya pertenece a otro circulo" % _nick_de_acc(acc_t, apodo)

    with _CANDADO:
        _INVITACIONES[target_usn] = {"cid": int(c["id"]), "por": usn, "ts": float(reloj())}
    nick_t = _nick_de_acc(acc_t, apodo)
    anotar("   CIRCULO %r: %s invito a %s (usn %d)" % (c["nombre"], _quien_de(con), nick_t, target_usn))
    return True, "invitacion enviada a %s (debe escribir .circulo aceptar)" % nick_t


def aceptar(con):
    """Acepta la invitacion pendiente del jugador y lo suma como miembro. Devuelve (ok, mensaje)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local"
    ahora = float(reloj())
    with _CANDADO:
        inv = _INVITACIONES.get(usn)
        if inv is not None and (ahora - float(inv.get("ts", 0))) > INVITACION_TTL:
            _INVITACIONES.pop(usn, None)
            inv = None
    if inv is None:
        return False, "no tenes ninguna invitacion pendiente"
    cid = int(inv["cid"])

    def op(d):
        cuentas_map = d.get("cuentas") or {}
        acc = cuentas_map.get(str(usn))
        if acc is None:
            return False, "circulo: cuenta local no encontrada", []
        circulos_d = d.get("circulos") or {}
        cid_actual = acc.get("circulo")
        if cid_actual and str(cid_actual) in circulos_d and str(usn) in (circulos_d[str(cid_actual)].get("miembros") or {}):
            return False, "ya estas en un circulo", []
        reg = circulos_d.get(str(cid))
        if not isinstance(reg, dict):
            return False, "ese circulo ya no existe", []
        miembros = reg.setdefault("miembros", {})
        if len(miembros) >= MAX_MIEMBROS:
            return False, "el circulo %s esta lleno" % reg.get("nombre", ""), []
        miembros[str(usn)] = RANGO_MIEMBRO
        acc["circulo"] = cid
        return True, "ahora sos miembro de %s" % reg.get("nombre", ""), [int(u) for u in miembros]

    try:
        ok, msg, usns_ref = cuenta.cambiar_todas(op)
    except cuenta.CuentaError as e:
        anotar("   ⛔ circulo aceptar %s: %s" % (_quien_de(con), e))
        return False, "circulo: error al guardar"
    with _CANDADO:
        if _INVITACIONES.get(usn) is inv:
            _INVITACIONES.pop(usn, None)
    if ok:
        anotar("   CIRCULO id=%d: %s acepto y es miembro" % (cid, _quien_de(con)))
        _refrescar_usns(usns_ref)
    return ok, msg


def salir(con):
    """Saca al jugador de su circulo. Si era el lider, pasa el mando o cierra si no queda nadie. Devuelve (ok, mensaje)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local"

    def op(d):
        cuentas_map = d.get("cuentas") or {}
        acc = cuentas_map.get(str(usn))
        if acc is None:
            return False, "circulo: cuenta local no encontrada", []
        circulos_d = d.get("circulos") or {}
        cid = acc.get("circulo")
        reg = circulos_d.get(str(cid)) if cid else None
        if not isinstance(reg, dict) or str(usn) not in (reg.get("miembros") or {}):
            acc.pop("circulo", None)
            return False, "no estas en ningun circulo", []
        nombre = reg.get("nombre", "")
        miembros = reg["miembros"]
        todos_antes = [int(u) for u in miembros]
        miembros.pop(str(usn), None)
        acc.pop("circulo", None)
        if not miembros:
            circulos_d.pop(str(cid), None)
            return True, "saliste y el circulo %s se cerro (no quedaba nadie)" % nombre, todos_antes
        if int(reg.get("lider", 0)) == usn:
            jefes = [int(u) for u, r in miembros.items() if int(r) == RANGO_JEFE]
            nuevo_lider = jefes[0] if jefes else int(next(iter(miembros)))
            reg["lider"] = nuevo_lider
            miembros[str(nuevo_lider)] = RANGO_LIDER
        return True, "saliste del circulo %s" % nombre, todos_antes

    try:
        ok, msg, usns_ref = cuenta.cambiar_todas(op)
    except cuenta.CuentaError as e:
        anotar("   ⛔ circulo salir %s: %s" % (_quien_de(con), e))
        return False, "circulo: error al guardar"
    if ok:
        anotar("   CIRCULO: %s salio (%s)" % (_quien_de(con), msg))
        _refrescar_usns(usns_ref)
    return ok, msg


def echar(con, apodo):
    """Echa a un miembro del circulo (SOLO el lider). Devuelve (ok, mensaje)."""
    usn = _usn_de(con)
    if usn is None:
        return False, "circulo: requiere cuenta local"
    obj = str(apodo or "").strip()
    if not obj:
        return False, "uso: .circulo echar <apodo>"

    def op(d):
        cuentas_map = d.get("cuentas") or {}
        acc = cuentas_map.get(str(usn))
        if acc is None:
            return False, "circulo: cuenta local no encontrada", []
        circulos_d = d.get("circulos") or {}
        cid = acc.get("circulo")
        reg = circulos_d.get(str(cid)) if cid else None
        if not isinstance(reg, dict) or str(usn) not in (reg.get("miembros") or {}):
            return False, "no estas en ningun circulo", []
        if int(reg.get("lider", 0)) != usn:
            return False, "solo el lider puede echar miembros", []
        miembros = reg.get("miembros") or {}
        # Buscar objetivo SOLO entre los miembros del circulo
        sub_cuentas = {u: cuentas_map[u] for u in miembros if u in cuentas_map}
        target_usn = _buscar_usn_en_cuentas(sub_cuentas, obj)
        if target_usn is None:
            return False, "no se encontro a %s en el circulo" % obj, []
        if target_usn == usn:
            return False, "para irte usa .circulo salir", []
        todos_antes = [int(u) for u in miembros]
        miembros.pop(str(target_usn), None)
        acc_t = cuentas_map.get(str(target_usn))
        if isinstance(acc_t, dict):
            acc_t.pop("circulo", None)
        nick_t = _nick_de_acc(acc_t, obj)
        return True, "%s fue echado de %s" % (nick_t, reg.get("nombre", "")), todos_antes

    try:
        ok, msg, usns_ref = cuenta.cambiar_todas(op)
    except cuenta.CuentaError as e:
        anotar("   ⛔ circulo echar %s: %s" % (_quien_de(con), e))
        return False, "circulo: error al guardar"
    if ok:
        anotar("   CIRCULO: %s echo a %s (%s)" % (_quien_de(con), obj, msg))
        _refrescar_usns(usns_ref)
    return ok, msg


def _resumen(con):
    usn = _usn_de(con)
    c = circulo_de(usn) if usn else None
    if not c:
        return "sin circulo | uso: .circulo crear <nombre> | aceptar | invitar <apodo> | salir | echar <apodo>"
    rango = int((c.get("miembros") or {}).get(str(usn), RANGO_MIEMBRO))
    cargo = "lider" if int(c.get("lider", 0)) == usn else ("jefe" if rango == RANGO_JEFE else "miembro")
    base = "circulo %s (%s, %d/%d)" % (c.get("nombre", ""), cargo, len(c.get("miembros") or {}), MAX_MIEMBROS)
    av = str(c.get("aviso") or "").strip()
    return "%s | aviso: %s" % (base, av) if av else base


def atender(con, texto):
    """Enganche para el camino del chat (FF1F4 y FF08). Devuelve True si se atendio `.circulo` (no se difunde
    como chat); False si la llave CIRCULOS esta en 0 o el texto no es `.circulo`."""
    if not activo():
        return False
    if isinstance(texto, (bytes, bytearray)):
        txt = textos.decodificar(bytes(texto)).strip()
    else:
        txt = str(texto or "").strip()
    if not txt.startswith("."):
        return False
    partes = txt[1:].split()
    if not partes or partes[0].lower() != "circulo":
        return False
    if len(partes) == 1:
        _avisar_uno(con, _resumen(con))
        return True
    sub = partes[1].lower()
    if sub == "crear":
        if len(partes) < 3:
            _avisar_uno(con, "uso: .circulo crear <nombre>")
            return True
        _ok, msg, _cid = crear(con, partes[2])
        _avisar_uno(con, msg)
        return True
    if sub == "invitar":
        if len(partes) < 3:
            _avisar_uno(con, "uso: .circulo invitar <apodo>")
            return True
        _ok, msg = invitar(con, partes[2])
        _avisar_uno(con, msg)
        return True
    if sub == "aceptar":
        _ok, msg = aceptar(con)
        _avisar_uno(con, msg)
        return True
    if sub == "salir":
        _ok, msg = salir(con)
        _avisar_uno(con, msg)
        return True
    if sub == "echar":
        if len(partes) < 3:
            _avisar_uno(con, "uso: .circulo echar <apodo>")
            return True
        _ok, msg = echar(con, partes[2])
        _avisar_uno(con, msg)
        return True
    if sub == "aviso":
        trozos = txt.split(None, 2)
        _ok, msg = poner_aviso(con, trozos[2] if len(trozos) >= 3 else "")
        _avisar_uno(con, msg)
        return True
    _avisar_uno(con, "uso: .circulo crear <nombre> | invitar <apodo> | aceptar | salir | echar <apodo> | aviso <texto>")
    return True
