# -*- coding: utf-8 -*-
r"""cuentas.py (29-oct; multi-personaje ficha 163) — las cuentas Eñeños del servidor local: hasta 4 personajes por SteamID,
en datos/cuenta.json (fuera de git: son datos de cuentas). Las usan login.py (28004) y juego.py (28008, 28101..28109).

⚠⚠ ESTE REGISTRO ES RECONSTRUIDO, NO COPIADO. El servidor oficial ya no deja registrar cuentas: medido el 29-oct con una
cuenta de Steam nueva, con y sin el grabador, el CmdAccountLogin vuelve con 1002 (VALOFE_LOGIN_DBERROR). No hay ninguna
captura de un alta, asi que el alta, el USN nuevo y el personaje nuevo salen de LEER el exe (docs/FF_HANDLERS_CHINO.md
§5) y de la plantilla capturada de la cuenta de la sesion del 22-oct (dato local de captura), que sigue entrando como siempre.

Una cuenta Eñeños (`usuarios[steamid]`):
    steamid        el que manda el cliente en su FF01 (texto). La copia n de LANZAR_VARIOS.bat lo trae de cuenta_steam.js.
    gsn            el numero de la cuenta: va en el FF01 de vuelta y el cliente lo devuelve en cada FF02 / FF0C.
    puerto         el del servidor de juego que le toca en la lista de canales (FF03). ⭐ Es lo que le dice a juego.py QUE
                   cuenta se conecta: el FF02 del 28008 viene cifrado y no se sabe leer (ver juego.py).
    usns           lista ordenada de hasta 4 usn de personajes creados (cada personaje vive por su usn en cuentas[usn]).
    activo_usn     el usn elegido en el ultimo FF02 (o pedido en FF0C), para que juego.py sepa QUE personaje entra.
    pendiente_usn  usn reservado por FF0C que todavia no termino de crear su personaje (FF06).
    borrados       lista de usn borrados (no se borran sus datos).
    capturada      True para la cuenta capturada del oficial (slot 1 usn dato local de captura entra por 28008 como siempre; slots 2-4
                   crean con usn nuevo y entran por PUERTO_CAPTURADA 28109).
"""
import os
import struct
import time

import ajustes
import textos
import cuenta as _cuenta     # el unico que abre los archivos (datos/cuenta.json); aca solo se traduce al formato de siempre

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 8 cuentas locales a la vez (28101..28108) + 28109 para personajes 2-4 de la cuenta capturada
PUERTO_BASE = ajustes.PUERTO_CUENTAS
MAX_CUENTAS = 8
MAX_PERSONAJES = 4
PUERTO_CAPTURADA = PUERTO_BASE + MAX_CUENTAS
PUERTOS = list(range(PUERTO_BASE, PUERTO_BASE + MAX_CUENTAS + 1))
GSN_BASE = 900001          # lejos del de la cuenta capturada (dato local de captura)
USN_BASE = 2000001         # lejos del de su personaje (dato local de captura)
USN_CAPTURADA = ajustes.numero_capturado(ajustes.RUTA_LOGIN_CAP, 2, 1)
GSN_CAPTURADA = ajustes.numero_capturado(ajustes.RUTA_LOGIN_CAP, 1, 4)
# cuenta_steam.js pone la parte baja del SteamID en 0x52420000 + n: de ahi sale el nick "Jugador<n>"
MARCA_COPIA = 0x52420000


def identidad_ff02():
    """True si pase_activo() y la llave IDENTIDAD_FF02 esta prendida."""
    return ajustes.identidad_ff02()


def cargar():
    """{"cuentas": [...]} en el formato viejo, solo lectura. Si el archivo esta roto: CuentaError."""
    return {"cuentas": _cuenta.todas_planas()}


def _busca(campo, valor):
    """La cuenta (formato viejo) cuyo campo vale valor, o None."""
    _, acc = _cuenta.buscar("cuenta", campo, valor)
    return _cuenta.plana(acc) if acc else None


def por_steamid(s):
    u = _cuenta.usuario(s)
    if u:
        usn = u.get("activo_usn") or (u.get("usns") or [0])[0] or u.get("pendiente_usn") or 0
        acc = _cuenta.leer(usn) if usn else None
        if acc:
            return _cuenta.plana(acc)
    return _busca("steamid", s)


def por_gsn(g):
    u = _cuenta.usuario_por_gsn(g)
    if u:
        usn = u.get("activo_usn") or (u.get("usns") or [0])[0] or u.get("pendiente_usn") or 0
        acc = _cuenta.leer(usn) if usn else None
        if acc:
            return _cuenta.plana(acc)
    return _busca("gsn", g)


def por_usn(usn):
    """El personaje de ese usn en formato plano, o None."""
    acc = _cuenta.leer(usn) if usn else None
    return _cuenta.plana(acc) if acc else None


def por_puerto(p):
    """El personaje ACTIVO de la cuenta Eñeños que usa ese puerto. Si es el personaje 1 de la cuenta capturada: None."""
    u = _cuenta.usuario_por_puerto(p)
    if u is not None:
        usn = u.get("activo_usn") or (u.get("usns") or [0])[0] or u.get("pendiente_usn") or 0
        if u.get("capturada") and usn == USN_CAPTURADA:
            return None
        return por_usn(usn) if usn else None
    return _busca("puerto", p)


def usuario_por_gsn(gsn):
    return _cuenta.usuario_por_gsn(gsn)


def usuario_por_steamid(steamid):
    return _cuenta.usuario(steamid)


def personajes_de(steamid):
    """Lista ordenada de personajes creados de esa cuenta Eñeños (hasta 4).
    Para la cuenta capturada, el personaje 1 va marcado con {"capturada": True, "usn": USN_CAPTURADA}."""
    u = _cuenta.usuario(steamid)
    if not u:
        return []
    todas = _cuenta.todas()
    out = []
    for uid in u.get("usns") or []:
        if u.get("capturada") and int(uid) == USN_CAPTURADA:
            out.append({"capturada": True, "usn": USN_CAPTURADA})
        else:
            acc = todas.get(str(uid))
            if acc and acc.get("personaje") is not None:
                out.append(acc)
    return out


def _nick_capturada():
    """El apodo del personaje 1 de la captura (campo 8 del FF0B), en memoria, sin guardarlo ni imprimirlo."""
    try:
        import login
        if not os.path.exists(ajustes.RUTA_FF0B):
            return None
        cap = bytes.fromhex(open(ajustes.RUTA_FF0B, encoding="ascii").read().strip())
        l1 = struct.unpack_from("<I", cap, 3)[0]
        campos, _ = login.leer_campos(cap[7:7 + l1])
        for c, _t, v in campos[0][2]:
            if c == 8:
                return _apodo_del_cable(v)
    except Exception:
        pass
    return None


def _ocupado_en(cuentas, apodo, excepto_steamid=None, excepto_usn=None):
    """El usn (texto) del primer personaje (o cuenta local pendiente) que usa `apodo`; None si esta libre.
    Ficha 42: comparacion EXACTA. Ficha 163: dos personajes de la misma cuenta tampoco pueden compartir apodo."""
    for usn, acc in cuentas.items():
        c = acc.get("cuenta") or {}
        pj = acc.get("personaje")
        if excepto_usn is not None and str(usn) == str(excepto_usn):
            continue
        if excepto_usn is None and excepto_steamid is not None and c.get("steamid") == excepto_steamid and pj is None:
            continue
        if pj and pj.get("nick") == apodo:
            return usn
        if pj is not None and c.get("nick") == apodo:
            return usn
        if pj is None and (excepto_steamid is None or c.get("steamid") != excepto_steamid) and c.get("nick") == apodo:
            return usn
    return None


def apodo_ocupado(apodo, excepto_steamid=None, excepto_usn=None):
    """True si otro personaje ya usa ese apodo (incluye otros personajes de la misma cuenta y el de la captura)."""
    if _ocupado_en(_cuenta.todas(), apodo, excepto_steamid, excepto_usn) is not None:
        return True
    if not ajustes.pase_activo() and excepto_usn != USN_CAPTURADA and apodo == _nick_capturada():
        return True
    return False


def _nick_para(steamid, i, cuentas=None):
    """El apodo automatico de una cuenta nueva: Jugador<copia> para las copias del arnes, Jugador<i+2> para las demas. Ficha 42: si
    ese ya lo usa otra cuenta (las dos reglas pueden dar el mismo numero) se prueba el numero siguiente hasta hallar uno libre."""
    n = i + 2
    try:
        bajo = int(steamid) & 0xFFFFFFFF
        if MARCA_COPIA < bajo < MARCA_COPIA + 0x100:
            n = bajo - MARCA_COPIA
    except ValueError:
        pass
    while cuentas and _ocupado_en(cuentas, "Jugador%d" % n) is not None:
        n += 1
    return "Jugador%d" % n


def _siguiente_usn(d):
    vistos = {USN_BASE - 1}
    for k in d["cuentas"]:
        try:
            vistos.add(int(k))
        except ValueError:
            pass
    for u in (d.get("usuarios") or {}).values():
        for x in (u.get("usns") or []) + (u.get("borrados") or []) + [u.get("pendiente_usn") or 0]:
            if x:
                vistos.add(int(x))
    return max(vistos) + 1


def _siguiente_gsn(d):
    usados = {u.get("gsn") for u in (d.get("usuarios") or {}).values() if u.get("gsn")}
    for acc in d["cuentas"].values():
        g = (acc.get("cuenta") or {}).get("gsn")
        if g:
            usados.add(g)
    g = GSN_BASE
    while g in usados:
        g += 1
    return g


def _siguiente_puerto(d):
    usados = {u.get("puerto") for u in (d.get("usuarios") or {}).values() if not u.get("capturada") and u.get("puerto")}
    for p in PUERTOS[:MAX_CUENTAS]:
        if p not in usados:
            return p
    return None


def alta(steamid, gsn=None, capturada=False):
    """La cuenta Eñeños de ese SteamID; si no existe, la crea (sin personaje, o con slot 1 si es la capturada).
    None si ya hay MAX_CUENTAS cuentas locales."""
    def f(d):
        usuarios = d.setdefault("usuarios", {})
        if steamid in usuarios:
            u = usuarios[steamid]
            usn = u.get("activo_usn") or (u.get("usns") or [0])[0] or u.get("pendiente_usn") or 0
            acc = d["cuentas"].get(str(usn))
            if acc:
                return _cuenta.plana(acc)
            return {
                "steamid": steamid,
                "gsn": u["gsn"],
                "usn": usn,
                "puerto": u["puerto"],
                "nick": "",
                "alta": u.get("alta", ""),
                "personaje": {"char_id": 130900} if u.get("capturada") else None,
            }
        ahora = time.strftime("%Y-%m-%d %H:%M:%S")
        if capturada:
            g_cap = int(gsn or GSN_CAPTURADA)
            usuarios[steamid] = {
                "steamid": steamid,
                "gsn": g_cap,
                "puerto": PUERTO_CAPTURADA,
                "usns": [USN_CAPTURADA],
                "borrados": [],
                "pendiente_usn": 0,
                "activo_usn": USN_CAPTURADA,
                "alta": ahora,
                "capturada": True,
            }
            return {
                "steamid": steamid,
                "gsn": g_cap,
                "usn": USN_CAPTURADA,
                "puerto": PUERTO_CAPTURADA,
                "nick": "",
                "alta": ahora,
                "personaje": {"char_id": 130900},
            }
        locales = sum(1 for u in usuarios.values() if not u.get("capturada"))
        if identidad_ff02():
            puerto = ajustes.PUERTOS_JUEGO[0]
        else:
            puerto = _siguiente_puerto(d)
            if locales >= MAX_CUENTAS or puerto is None:
                return None
        gsn_nuevo = _siguiente_gsn(d)
        usn_nuevo = _siguiente_usn(d)
        nick = _nick_para(steamid, locales, d["cuentas"])
        c = {"steamid": steamid, "gsn": gsn_nuevo, "usn": usn_nuevo, "puerto": puerto, "nick": nick, "alta": ahora}
        d["cuentas"][str(usn_nuevo)] = {"cuenta": c, "personaje": None, "tienda": {}, "amigos": {}, "pareja": {}}
        usuarios[steamid] = {
            "steamid": steamid,
            "gsn": gsn_nuevo,
            "puerto": puerto,
            "usns": [],
            "borrados": [],
            "pendiente_usn": usn_nuevo,
            "activo_usn": usn_nuevo,
            "alta": ahora,
            "capturada": False,
        }
        return _cuenta.plana(d["cuentas"][str(usn_nuevo)])
    return _cuenta.cambiar_todas(f)


def pedir_usn(gsn):
    """Reserva un usn nuevo para crear un personaje en la cuenta Eñeños de ese gsn (FF0C GetNewUSN).
    Devuelve el usn, o None si la cuenta no existe o ya tiene MAX_PERSONAJES (4)."""
    def f(d):
        u = next((x for x in (d.get("usuarios") or {}).values() if x.get("gsn") == gsn), None)
        if u is None:
            return None
        if len(u.get("usns") or []) >= MAX_PERSONAJES:
            return None
        pend = u.get("pendiente_usn") or 0
        if pend and str(pend) in d["cuentas"] and d["cuentas"][str(pend)].get("personaje") is None:
            u["activo_usn"] = pend
            return pend
        usn_nuevo = _siguiente_usn(d)
        nick = _nick_para(u["steamid"], len(d["cuentas"]), d["cuentas"])
        ahora = time.strftime("%Y-%m-%d %H:%M:%S")
        c = {"steamid": u["steamid"], "gsn": u["gsn"], "usn": usn_nuevo, "puerto": u["puerto"], "nick": nick, "alta": ahora}
        d["cuentas"][str(usn_nuevo)] = {"cuenta": c, "personaje": None, "tienda": {}, "amigos": {}, "pareja": {}}
        u["pendiente_usn"] = usn_nuevo
        u["activo_usn"] = usn_nuevo
        return usn_nuevo
    return _cuenta.cambiar_todas(f)


def elegir_usn(steamid, usn):
    """Marca `usn` como el personaje activo de `steamid` al elegir tarjeta en FF02. True si pertenece a esa cuenta."""
    def f(d):
        u = (d.get("usuarios") or {}).get(str(steamid))
        if u is None:
            return False
        usn_i = int(usn)
        if usn_i not in (u.get("usns") or []) and usn_i != u.get("pendiente_usn"):
            return False
        u["activo_usn"] = usn_i
        return True
    return _cuenta.cambiar_todas(f)


def guardar_personaje(usn, pj):
    """Guarda el personaje recien creado en el usn dado y lo agrega a `usuarios[steamid].usns`. None si superaria 4."""
    def f(d):
        acc = d["cuentas"].get(str(usn))
        if acc is None:
            return None
        usn_i = int(usn)
        sid = acc["cuenta"]["steamid"]
        u = (d.get("usuarios") or {}).get(sid)
        if u is not None:
            if usn_i not in u["usns"]:
                if len(u["usns"]) >= MAX_PERSONAJES:
                    return None
                u["usns"].append(usn_i)
            if u.get("pendiente_usn") == usn_i:
                u["pendiente_usn"] = 0
            u["activo_usn"] = usn_i
        acc["personaje"] = pj
        acc["cuenta"]["nick"] = pj["nick"]
        acc["cuenta"]["usn"] = usn_i
        return _cuenta.plana(acc)
    return _cuenta.cambiar_todas(f)


def cambiar(steamid, **campos):
    """Cambia campos del personaje/cuenta de ese SteamID (acepta `usn=...` opcional; si no, resuelve por `personaje.nick`
    o `activo_usn`, para mantener compatibilidad con tienda.py). Devuelve la cuenta plana, o None."""
    usn_obj = campos.pop("usn", None)

    def _buscar_acc(d):
        if usn_obj is not None:
            acc = d["cuentas"].get(str(usn_obj))
            if acc and acc["cuenta"]["steamid"] == steamid:
                return acc
        pj_arg = campos.get("personaje")
        if isinstance(pj_arg, dict) and pj_arg.get("nick"):
            for acc in d["cuentas"].values():
                if acc["cuenta"]["steamid"] == steamid and (acc.get("personaje") or {}).get("nick") == pj_arg["nick"]:
                    return acc
        u = (d.get("usuarios") or {}).get(str(steamid))
        if u and u.get("activo_usn"):
            acc = d["cuentas"].get(str(u["activo_usn"]))
            if acc and acc["cuenta"]["steamid"] == steamid:
                return acc
        for acc in d["cuentas"].values():
            if acc["cuenta"]["steamid"] == steamid:
                return acc
        return None

    def f(d):
        acc = _buscar_acc(d)
        if acc is None:
            return None
        for k, v in campos.items():
            if k == "personaje":
                acc["personaje"] = v
            else:
                acc["cuenta"][k] = v
        return _cuenta.plana(acc)
    return _cuenta.cambiar_todas(f)


def usn_de(c):
    """El usn del personaje de la cuenta; lo asigna si aun vale 0 (SendGetNewUSN)."""
    if c.get("usn"):
        return c["usn"]
    return pedir_usn(c["gsn"])


def _apodo_del_cable(b):
    """Ficha 141: el UID que el cliente devuelve en el FF06 son los MISMOS bytes que le dimos en el FF00 (GB18030: `ñ` = 4 bytes). Se
    lee como texto (asi `Año` es `Año` en cuenta.json y en cada mensaje que lo lleva). ASCII: igual que antes. Si los bytes no son
    GB18030 validos (no pasa con lo que mandamos nosotros) se guardan como latin-1, que es lo que se hacia siempre."""
    try:
        return b.decode(textos.CODIFICACION)
    except UnicodeDecodeError:
        return b.decode("latin-1")


def leer_default_char(cuerpo):
    """C2S FF06 CNetwork::SendDefaultChar (0x02763ad0, lo llama la escena de crear 0x004ebd70). Medido en el exe:
        u32 char_id   0x1ff54 + (sexo != 0): 130900 hombre / 130901 mujer
        u8 largo + nick   el UID de la cuenta ([cuenta+0x82d], el que le dimos en el FF00)
        u8 n + n x u32    las partes elegidas (el bucle recorre 4 casillas de la escena)
    Igual que el FF04 CreateChar del servidor 2013 (basedatos.parse_create_char)."""
    char_id = struct.unpack_from("<I", cuerpo, 0)[0]
    n = cuerpo[4]
    nick = _apodo_del_cable(cuerpo[5:5 + n])
    k = 5 + n
    c = cuerpo[k]
    partes = list(struct.unpack_from("<%dI" % c, cuerpo, k + 1))
    if k + 1 + 4 * c != len(cuerpo):
        raise ValueError("SendDefaultChar de %d B, se leyeron %d" % (len(cuerpo), k + 1 + 4 * c))
    return {"char_id": char_id, "nick": nick, "partes": partes}
