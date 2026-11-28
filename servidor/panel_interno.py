# -*- coding: utf-8 -*-
r"""panel_interno.py (M16, 22-nov) — puerta HTTP interna del panel del Coordinador («contrato1»).

Corre dentro del proceso de juego.py sobre el mismo bucle de asyncio (sin dependencias externas) para leer
estado.CONEXIONES / estado.SALAS y ejecutar acciones sobre conexiones vivas y cuentas (cuenta.py / tienda.py / gm.py).

Arranque:
  En juego.main(), una sola llamada `await panel_interno.iniciar(anotar)`.
  Abre SOLO si estan definidas `R2_CUENTAS_FICHA_INTERNA` y `PANEL_PUERTO`. Escucha en `PANEL_HOST` (omision `0.0.0.0`).
  Sin esas dos variables no abre ningun puerto y no cambia nada del juego.

Seguridad (contrato1):
  - `X-Ficha-Interna` igual a `R2_CUENTAS_FICHA_INTERNA` (hmac.compare_digest); si falta o no coincide -> 404.
  - Todo POST exige `X-R2: 1`; si falta -> 403.
  - Cuerpo JSON con tope de 64 KB.
  - Errores siempre `{"error": "..."}` en espanol neutro, de usted.
  - `X-Coordinador-Quien` se anota en el registro en cada accion que cambia algo.
"""
import asyncio
import hmac
import json
import os
import re
import time
import urllib.parse

import ajustes
import cuenta
import cuentas
import estado
import fichas
import gm
import salas
import tienda

PREFIJO = "/interno/panel"
TOPE_CUERPO = 64 * 1024
TOPE_LINEA = 8 * 1024
TOPE_CABECERAS = 64
TOPE_CABECERAS_BYTES = 16 * 1024
TOPE_BUSCAR = 50
MAX_SALDO_U32 = 0xFFFFFFFF
TIMEOUT_LECTURA = 10.0

ACCIONES = ["ver", "aviso", "echar", "moneda"]
MONEDAS = [
    {"id": "g", "nombre": "G"},
    {"id": "diamantes", "nombre": "Diamantes"},
    {"id": "exp", "nombre": "EXP"},
]
MONEDAS_IDS = frozenset(m["id"] for m in MONEDAS)

_RE_ENENOS = re.compile(r"^e(\d+)$")
_RAZON_HTTP = {
    200: "OK",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    413: "Payload Too Large",
    500: "Internal Server Error",
}

_ANOTAR = None
_T0 = time.time()


def _anotar(txt):
    f = _ANOTAR if callable(_ANOTAR) else estado.anotar
    f(txt)


def _limpiar_texto_log(valor, maximo=120):
    s = str(valor or "").replace("\r", " ").replace("\n", " ").strip()
    return s[:maximo]


def _enenos_id_de(steamid):
    """El numero entero de `e<sub>`, o None si la cuenta no es de Cuenta Eñeños."""
    if not isinstance(steamid, str):
        return None
    m = _RE_ENENOS.match(steamid.strip())
    return int(m.group(1)) if m else None


def _parsear_usn(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str):
        s = valor.strip()
        if s.isdigit():
            n = int(s)
            return n if n > 0 else None
    return None


def _parsear_entero(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str):
        s = valor.strip()
        if s and (s.isdigit() or (s[0] in ("+", "-") and s[1:].isdigit())):
            return int(s)
    return None


def _nick_de_plano(cta):
    cta = cta or {}
    pj = cta.get("personaje") or {}
    return str(pj.get("nick") or cta.get("nick") or "")


def _nick_de_acc(acc):
    acc = acc or {}
    pj = acc.get("personaje") or {}
    cta = acc.get("cuenta") or {}
    return str(pj.get("nick") or cta.get("nick") or "")


def _conexiones_vivas():
    """Lista de (id_con, con) abiertas y con cuenta asociada."""
    out = []
    for k, con in list(estado.CONEXIONES.items()):
        if getattr(con, "cerrada", False):
            continue
        cta = getattr(con, "cuenta", None)
        if not cta:
            continue
        out.append((k, con))
    return out


def _mapa_conectados():
    """{usn: con} de las conexiones vivas con cuenta."""
    out = {}
    for _k, con in _conexiones_vivas():
        usn = _parsear_usn((con.cuenta or {}).get("usn"))
        if usn is not None:
            out[usn] = con
    return out


def _donde_de(con):
    sala = getattr(con, "sala", None)
    return ("sala %d" % sala) if sala is not None else "lobby"


def _ip_de(con):
    tr = getattr(con, "tr", None)
    if tr is None:
        return None
    get_extra = getattr(tr, "get_extra_info", None)
    if not callable(get_extra):
        return None
    try:
        peer = get_extra("peername")
    except Exception:                                                    # noqa: BLE001
        return None
    if isinstance(peer, (tuple, list)) and peer:
        return str(peer[0])
    return None


def _formato_uptime(segundos):
    s = max(0, int(segundos))
    dias, rem = divmod(s, 86400)
    horas, rem = divmod(rem, 3600)
    minutos, segs = divmod(rem, 60)
    if dias:
        return "%dd %dh %dm %ds" % (dias, horas, minutos, segs)
    return "%dh %dm %ds" % (horas, minutos, segs)


def _descripcion_personaje(pj):
    if not isinstance(pj, dict):
        return "Sin crear"
    cid = pj.get("char_id")
    if isinstance(cid, int) and 0x1FF54 <= cid <= 0x1FF5F:
        sexo = "Mujer" if (cid - 0x1FF54) & 1 else "Varón"
        return "%s (%d)" % (sexo, cid)
    return "Creado"


def _monedas_de_acc(acc):
    sec = (acc or {}).get("tienda") or {}
    g = max(0, int(sec.get("g", 0) or 0))
    exp = tienda.con_piso(sec.get("exp", 0)) if (acc or {}).get("personaje") else max(0, int(sec.get("exp", 0) or 0))
    diamantes = max(0, int(sec.get("diamantes", tienda.SALDO_INICIAL) if "diamantes" in sec else tienda.SALDO_INICIAL))
    return {"g": g, "diamantes": diamantes, "exp": exp}


def _personajes_de_usuario(steamid, todas):
    if not steamid:
        return []
    u = cuenta.usuario(steamid)
    borrados = set((u or {}).get("borrados") or [])
    vistos = set()
    out = []

    def agregar(usn_val):
        uid = _parsear_usn(usn_val)
        if uid is None or uid in vistos or uid in borrados:
            return
        acc = todas.get(str(uid))
        if acc is None:
            return
        vistos.add(uid)
        out.append({"id": uid, "nick": _nick_de_acc(acc)})

    if u:
        for uid in u.get("usns") or []:
            agregar(uid)
        if u.get("pendiente_usn"):
            agregar(u.get("pendiente_usn"))
    for k, acc in todas.items():
        if (acc.get("cuenta") or {}).get("steamid") == steamid:
            agregar((acc.get("cuenta") or {}).get("usn") or k)
    return out


def _sexo_de(pj):
    """"m"/"f" desde char_id (0x1FF54.. como _descripcion_personaje: impar desde la base = mujer); None si no esta creado."""
    cid = pj.get("char_id") if isinstance(pj, dict) else None
    if isinstance(cid, int) and 0x1FF54 <= cid <= 0x1FF5F:
        return "f" if (cid - 0x1FF54) & 1 else "m"
    return None


def _apariencia_de(pj):
    """23-nov (maduracion, para el muneco del launcher): lo que lleva puesto el personaje, tal cual lo usa el cliente.
    - cuerpo: char_id (0x1FF54.. = cuerpo base; par varon, impar mujer). None si no esta creado.
    - partes: los ids de `personaje.partes` (la misma lista que va en el S2C FF7F, con la que el cliente viste al muneco).
      Cada id es el `Index` de rnr_script/shop.txt (= `code` de config/items_tbitems.json) dentro de rnr_script.pak.
      `pestana` = ShopIndex de shop.txt (catalogo.json: 301 pelo, 302 arriba, 303 abajo, 304 zapatos... MEDIDO solo el
      numero, el nombre de cada pestana sale de la tienda del cliente).
    - mascota / alas: None (el servidor no las guarda en el personaje).
    El paso id -> archivo de modelo/textura y su .pak NO esta medido aca (ver la sesion Biblioteca de ropa)."""
    if not isinstance(pj, dict):
        return None
    try:
        import catalogo
        pest = catalogo.pestana
    except Exception:                                            # noqa: BLE001
        pest = lambda _i: None                                   # noqa: E731
    ids = []
    for x in pj.get("partes") or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    try:
        ids = tienda.ordenar_partes(ids)       # M23: una prenda por casilla (como la vera el juego al entrar)
    except Exception:                                            # noqa: BLE001
        pass
    partes = [{"id": i, "pestana": pest(i)} for i in ids]
    cid = pj.get("char_id")
    return {"cuerpo": cid if isinstance(cid, int) else None, "sexo": _sexo_de(pj), "partes": partes,
            "mascota": None, "alas": None}


def _get_personajes(query):
    """23-nov (maduracion, para el launcher: los minichars de la cuenta). GET personajes?enenos_id=<n> -> los personajes de
    `e<n>` sin los borrados, con sexo y conectado. `nivel` va en null: el servidor no tiene la tabla de niveles del jugador
    (la calcula el cliente con la del exe) y no se inventa. Cuenta inexistente -> lista vacia (200)."""
    crudo = (query.get("enenos_id") or [""])[0].strip()
    if not crudo.isdigit() or int(crudo) <= 0 or len(crudo) > 12:
        return 400, {"error": "El parámetro enenos_id debe ser un número entero positivo."}
    steamid = "e%d" % int(crudo)
    maximo = cuentas.MAX_PERSONAJES
    if cuenta.usuario(steamid) is None:
        return 200, {"personajes": [], "maximo": maximo}
    todas = cuenta.todas()
    vivos = _mapa_conectados()
    out = []
    for p in _personajes_de_usuario(steamid, todas):
        acc = todas.get(str(p["id"])) or {}
        out.append({"id": p["id"], "nick": p["nick"], "sexo": _sexo_de(acc.get("personaje")), "nivel": None,
                    "conectado": p["id"] in vivos, "apariencia": _apariencia_de(acc.get("personaje"))})
    return 200, {"personajes": out, "maximo": maximo}


class _ConCuenta:
    """Envoltorio minimo para operar con tienda.py cuando el jugador no esta conectado."""

    def __init__(self, cta_plana):
        self.cuenta = cta_plana


# ---------- rutas del contrato ----------
def _get_capacidades():
    entorno = (os.environ.get("PANEL_ENTORNO") or "").strip() or "test"
    return 200, {
        "juego": "r2beat-moderno",
        "version": 1,
        "acciones": list(ACCIONES),
        "monedas": [dict(m) for m in MONEDAS],
        "entorno": entorno,
    }


def _get_salud():
    vivas = _conexiones_vivas()
    total_con = sum(1 for c in list(estado.CONEXIONES.values()) if not getattr(c, "cerrada", False))
    uptime = max(0.0, time.time() - _T0)
    return 200, {
        "en_linea": True,
        "jugando": len(vivas),
        "detalle": [
            {"nombre": "Salas abiertas", "valor": len(estado.SALAS)},
            {"nombre": "Tiempo activo", "valor": _formato_uptime(uptime)},
            {"nombre": "Conexiones activas", "valor": total_con},
            {"nombre": "Modo pase", "valor": "activo" if ajustes.pase_activo() else "local"},
        ],
    }


def _get_conectados():
    filas = []
    for _k, con in _conexiones_vivas():
        cta = con.cuenta or {}
        usn = _parsear_usn(cta.get("usn"))
        if usn is None:
            continue
        fila = {
            "id": usn,
            "nick": _nick_de_plano(cta),
            "enenos_id": _enenos_id_de(cta.get("steamid")),
            "donde": _donde_de(con),
            "desde": int(getattr(con, "t_conexion", 0) or 0),
        }
        ip = _ip_de(con)
        if ip:
            fila["ip"] = ip
        filas.append(fila)
    filas.sort(key=lambda f: (f["desde"], f["id"]))
    return 200, {"filas": filas}


def _get_buscar(query):
    q = str((query.get("q") or [""])[0] or "").strip()
    q_low = q.lower()
    q_sin_hash = q_low.lstrip("#")
    q_eid = q_sin_hash[1:] if q_sin_hash.startswith("e") and q_sin_hash[1:].isdigit() else q_sin_hash
    conectados = _mapa_conectados()
    try:
        todas = cuenta.todas()
    except cuenta.CuentaError:
        return 500, {"error": "No se pudieron leer las cuentas del servidor."}
    filas = []
    for k, acc in todas.items():
        cta = acc.get("cuenta") or {}
        usn = _parsear_usn(cta.get("usn") or k)
        if usn is None:
            continue
        nick = _nick_de_acc(acc)
        cta_nick = str(cta.get("nick") or "")
        steamid = str(cta.get("steamid") or "")
        eid = _enenos_id_de(steamid)
        if q_low:
            coincide = (
                q_low in nick.lower()
                or q_low in cta_nick.lower()
                or q_sin_hash == str(usn)
                or (eid is not None and (q_sin_hash == str(eid) or q_eid == str(eid) or q_low == steamid.lower()))
            )
            if not coincide:
                continue
        mon = _monedas_de_acc(acc)
        resumen = "EXP %d · G %d" % (mon["exp"], mon["g"])
        if acc.get("personaje") is None:
            resumen = "Sin personaje · " + resumen
        filas.append({
            "id": usn,
            "nick": nick,
            "enenos_id": eid,
            "conectado": usn in conectados,
            "resumen": resumen,
        })
        if len(filas) >= TOPE_BUSCAR:
            break
    return 200, {"filas": filas}


def _get_ficha(usn_txt):
    usn = _parsear_usn(usn_txt)
    if usn is None:
        return 404, {"error": "No se encontró el personaje indicado."}
    try:
        todas = cuenta.todas()
    except cuenta.CuentaError:
        return 500, {"error": "No se pudieron leer las cuentas del servidor."}
    acc = todas.get(str(usn))
    if acc is None:
        return 404, {"error": "No se encontró el personaje indicado."}
    cta = acc.get("cuenta") or {}
    pj = acc.get("personaje")
    steamid = str(cta.get("steamid") or "")
    mon = _monedas_de_acc(acc)
    con_viva = _mapa_conectados().get(usn)
    campos = [
        {"nombre": "EXP", "valor": mon["exp"]},
        {"nombre": "Alta", "valor": str(cta.get("alta") or "-")},
        {"nombre": "Personaje", "valor": _descripcion_personaje(pj)},
    ]
    if con_viva is not None:
        campos.append({"nombre": "Ubicación", "valor": _donde_de(con_viva)})
    return 200, {
        "id": usn,
        "nick": _nick_de_acc(acc),
        "enenos_id": _enenos_id_de(steamid),
        "conectado": con_viva is not None,
        "campos": campos,
        "monedas": mon,
        "personajes": _personajes_de_usuario(steamid, todas),
    }


def _post_aviso(datos, quien):
    texto = str(datos.get("texto") or "").strip()
    if not texto:
        return 400, {"error": "Indique el texto del aviso."}
    destino = str(datos.get("a") or "").strip().lower()
    if destino not in ("todos", "uno"):
        return 400, {"error": "Indique un destino válido («todos» o «uno»)."}
    paquete = gm.cuerpo_anuncio(texto)
    llego_a = 0
    if destino == "todos":
        for con in list(estado.CONEXIONES.values()):
            if getattr(con, "cerrada", False):
                continue
            try:
                con.mandar_interno(0x1F4, 0, paquete)
                llego_a += 1
            except Exception as e:                                       # noqa: BLE001
                _anotar("   ⛔ PANEL [%s] aviso a todos: fallo en una conexion: %r" % (quien, e))
        _anotar("   PANEL [%s] aviso a todos (llego_a=%d): %r" % (quien, llego_a, _limpiar_texto_log(texto, 160)))
        return 200, {"ok": True, "llego_a": llego_a}
    usn = _parsear_usn(datos.get("id"))
    if usn is None:
        return 400, {"error": "Indique el identificador del personaje destinatario."}
    for _k, con in _conexiones_vivas():
        if _parsear_usn((con.cuenta or {}).get("usn")) == usn:
            try:
                con.mandar_interno(0x1F4, 0, paquete)
                llego_a += 1
            except Exception as e:                                       # noqa: BLE001
                _anotar("   ⛔ PANEL [%s] aviso a usn %d: %r" % (quien, usn, e))
    _anotar("   PANEL [%s] aviso a usn %d (llego_a=%d): %r" % (quien, usn, llego_a, _limpiar_texto_log(texto, 160)))
    return 200, {"ok": True, "llego_a": llego_a}


def _post_echar(datos, quien):
    usn = _parsear_usn(datos.get("id"))
    if usn is None:
        return 400, {"error": "Indique el identificador del personaje."}
    motivo = _limpiar_texto_log(datos.get("motivo"), 200)
    encontrados = [
        (k, con) for k, con in list(estado.CONEXIONES.items())
        if not getattr(con, "cerrada", False) and _parsear_usn((getattr(con, "cuenta", None) or {}).get("usn")) == usn
    ]
    if not encontrados:
        return 404, {"error": "Ese personaje no está conectado."}
    for k_con, con in encontrados:
        estado.CONEXIONES.pop(k_con, None)
        if getattr(con, "sala", None) is not None and con.sala in estado.SALAS:
            try:
                salas.sacar_de_su_sala(con)
            except Exception as e:                                       # noqa: BLE001
                _anotar("   ⛔ PANEL [%s] echar sacar_de_su_sala usn %d: %r" % (quien, usn, e))
        con.cerrada = True
        tr = getattr(con, "tr", None)
        if tr is not None:
            try:
                tr.close()
            except Exception as e:                                       # noqa: BLE001
                _anotar("   ⛔ PANEL [%s] echar tr.close usn %d: %r" % (quien, usn, e))
    _anotar("   PANEL [%s] echar usn %d (%d conexion/es)%s"
            % (quien, usn, len(encontrados), (" motivo=%r" % motivo) if motivo else ""))
    return 200, {"ok": True}


def _refrescar_conexion_moneda(con, moneda):
    if con is None or getattr(con, "cerrada", False):
        return
    if moneda == "g":
        tienda.refrescar_saldos(con, g=True)
    elif moneda == "diamantes":
        tienda.refrescar_saldos(con, diamantes=True)
    elif moneda == "exp":
        mandar_claro = getattr(con, "mandar_claro", None)
        if callable(mandar_claro):
            try:
                lote = fichas.ficha_nueva(con.cuenta)
                if lote:
                    mandar_claro(lote)
            except Exception as e:                                       # noqa: BLE001
                _anotar("   ⛔ PANEL refrescar FF00 exp: %r" % e)


def _post_moneda(datos, quien):
    usn = _parsear_usn(datos.get("id"))
    if usn is None:
        return 400, {"error": "Indique el identificador del personaje."}
    moneda = str(datos.get("moneda") or "").strip().lower()
    if moneda not in MONEDAS_IDS:
        return 400, {"error": "Moneda no válida. Use g, diamantes o exp."}
    cantidad = _parsear_entero(datos.get("cantidad"))
    if cantidad is None or cantidad == 0:
        return 400, {"error": "La cantidad debe ser un número entero distinto de cero."}
    try:
        acc = cuenta.leer(usn)
    except cuenta.CuentaError:
        return 500, {"error": "No se pudo leer la cuenta del servidor."}
    if acc is None:
        return 404, {"error": "No se encontró el personaje indicado."}
    cta_plana = cuentas.por_usn(usn) or cuenta.plana(acc)
    con_viva = _mapa_conectados().get(usn)
    con_obj = con_viva if con_viva is not None else _ConCuenta(cta_plana)

    if moneda in ("g", "exp"):
        exp_act, g_act = tienda.exp_g_de_cuenta(cta_plana)
        antes = g_act if moneda == "g" else exp_act
        objetivo = antes + cantidad
        if objetivo < 0:
            return 400, {"error": "Saldo insuficiente: la operación dejaría el saldo en negativo."}
        if objetivo > MAX_SALDO_U32:
            return 400, {"error": "La cantidad supera el límite permitido."}
        try:
            tienda.acreditar(con_obj, exp=cantidad if moneda == "exp" else 0, g=cantidad if moneda == "g" else 0)
            exp_desp, g_desp = tienda.exp_g_de_cuenta(cta_plana)
        except cuenta.CuentaError:
            return 500, {"error": "No se pudo guardar el cambio de saldo."}
        despues = g_desp if moneda == "g" else exp_desp
    else:
        antes = tienda.diamantes_de_cuenta(cta_plana)
        if antes + cantidad < 0:
            return 400, {"error": "Saldo insuficiente: la operación dejaría el saldo en negativo."}
        if antes + cantidad > MAX_SALDO_U32:
            return 400, {"error": "La cantidad supera el límite permitido."}

        def _mover_diamantes(b):
            a = int(b.get("diamantes", tienda.SALDO_INICIAL))
            d = a + cantidad
            if d < 0:
                return "negativo", a, a
            if d > MAX_SALDO_U32:
                return "tope", a, a
            b["diamantes"] = d
            return "ok", a, d

        try:
            est, antes, despues = tienda._con_bolsa(con_obj, _mover_diamantes)
        except cuenta.CuentaError:
            return 500, {"error": "No se pudo guardar el cambio de saldo."}
        if est == "negativo":
            return 400, {"error": "Saldo insuficiente: la operación dejaría el saldo en negativo."}
        if est == "tope":
            return 400, {"error": "La cantidad supera el límite permitido."}

    if con_viva is not None:
        _refrescar_conexion_moneda(con_viva, moneda)
    _anotar("   PANEL [%s] moneda usn %d %s %+d (%d -> %d)" % (quien, usn, moneda, cantidad, antes, despues))
    return 200, {"ok": True, "antes": antes, "despues": despues}


# ---------- despachador de rutas (usable tambien directo en memoria) ----------
def despachar(metodo, objetivo, cabeceras, cuerpo=b""):
    """Despacha un pedido HTTP del contrato1. Devuelve (codigo_http, dict_json)."""
    cab = {str(k).strip().lower(): str(v).strip() for k, v in (cabeceras or {}).items()}
    esperada = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
    recibida = cab.get("x-ficha-interna", "")
    if not esperada or not recibida or not hmac.compare_digest(recibida, esperada):
        return 404, {"error": "No encontrado."}

    metodo_u = str(metodo or "").strip().upper()
    partes = urllib.parse.urlsplit(str(objetivo or ""))
    ruta = partes.path or ""
    if not ruta.startswith(PREFIJO + "/"):
        return 404, {"error": "No encontrado."}
    subruta = ruta[len(PREFIJO) + 1:].rstrip("/")
    query = urllib.parse.parse_qs(partes.query, keep_blank_values=True)

    if metodo_u == "GET":
        if subruta == "capacidades":
            return _get_capacidades()
        if subruta == "salud":
            return _get_salud()
        if subruta == "conectados":
            return _get_conectados()
        if subruta == "buscar":
            return _get_buscar(query)
        if subruta == "personajes":
            return _get_personajes(query)
        if subruta.startswith("ficha/"):
            resto = subruta[len("ficha/"):]
            if resto and "/" not in resto:
                return _get_ficha(resto)
        return 404, {"error": "No encontrado."}

    if metodo_u == "POST":
        if cab.get("x-r2") != "1":
            return 403, {"error": "Falta la cabecera de confirmación."}
        if len(cuerpo) > TOPE_CUERPO:
            return 413, {"error": "El cuerpo excede el límite de 64 KB."}
        if cuerpo:
            try:
                datos = json.loads(cuerpo.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return 400, {"error": "El cuerpo debe ser un objeto JSON válido."}
            if not isinstance(datos, dict):
                return 400, {"error": "El cuerpo debe ser un objeto JSON válido."}
        else:
            datos = {}
        quien = _limpiar_texto_log(cab.get("x-coordinador-quien") or "desconocido", 120) or "desconocido"
        if subruta == "aviso":
            return _post_aviso(datos, quien)
        if subruta == "echar":
            return _post_echar(datos, quien)
        if subruta == "moneda":
            return _post_moneda(datos, quien)
        return 404, {"error": "No encontrado."}

    return 404, {"error": "No encontrado."}


# ---------- servidor HTTP minimo sobre asyncio ----------
async def _escribir_respuesta(writer, codigo, datos):
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    razon = _RAZON_HTTP.get(codigo, "OK")
    cabeza = (
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n\r\n"
    ) % (codigo, razon, len(cuerpo))
    writer.write(cabeza.encode("ascii") + cuerpo)
    await writer.drain()


async def _leer_linea_acotada(reader, tope):
    linea = await asyncio.wait_for(reader.readline(), timeout=TIMEOUT_LECTURA)
    if len(linea) > tope:
        raise ValueError("linea demasiado larga")
    return linea


async def _atender_cliente(reader, writer):
    try:
        primera = await _leer_linea_acotada(reader, TOPE_LINEA)
        if not primera:
            return
        try:
            partes = primera.decode("iso-8859-1").strip().split()
        except UnicodeDecodeError:
            await _escribir_respuesta(writer, 400, {"error": "Solicitud HTTP inválida."})
            return
        if len(partes) != 3:
            await _escribir_respuesta(writer, 400, {"error": "Solicitud HTTP inválida."})
            return
        metodo, objetivo, _version = partes

        cabeceras = {}
        total_cab = 0
        for _ in range(TOPE_CABECERAS):
            linea = await _leer_linea_acotada(reader, TOPE_LINEA)
            if not linea or linea in (b"\r\n", b"\n"):
                break
            total_cab += len(linea)
            if total_cab > TOPE_CABECERAS_BYTES:
                await _escribir_respuesta(writer, 400, {"error": "Las cabeceras exceden el límite permitido."})
                return
            if b":" not in linea:
                await _escribir_respuesta(writer, 400, {"error": "Cabecera HTTP inválida."})
                return
            k, v = linea.decode("iso-8859-1").split(":", 1)
            cabeceras[k.strip().lower()] = v.strip()
        else:
            await _escribir_respuesta(writer, 400, {"error": "Demasiadas cabeceras HTTP."})
            return

        # Control de ficha antes de leer el cuerpo: sin ficha valida responde 404 como si no existiera
        esperada = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
        recibida = cabeceras.get("x-ficha-interna", "")
        if not esperada or not recibida or not hmac.compare_digest(recibida, esperada):
            await _escribir_respuesta(writer, 404, {"error": "No encontrado."})
            return

        cuerpo = b""
        if "content-length" in cabeceras:
            try:
                largo = int(cabeceras["content-length"])
            except ValueError:
                await _escribir_respuesta(writer, 400, {"error": "Encabezado Content-Length inválido."})
                return
            if largo < 0:
                await _escribir_respuesta(writer, 400, {"error": "Encabezado Content-Length inválido."})
                return
            if largo > TOPE_CUERPO:
                await _escribir_respuesta(writer, 413, {"error": "El cuerpo excede el límite de 64 KB."})
                return
            if largo:
                cuerpo = await asyncio.wait_for(reader.readexactly(largo), timeout=TIMEOUT_LECTURA)

        codigo, datos = despachar(metodo, objetivo, cabeceras, cuerpo)
        await _escribir_respuesta(writer, codigo, datos)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
        pass
    except ValueError:
        try:
            await _escribir_respuesta(writer, 400, {"error": "Solicitud HTTP inválida."})
        except Exception:                                                # noqa: BLE001
            pass
    except Exception as e:                                               # noqa: BLE001
        _anotar("   ⛔ PANEL error atendiendo pedido: %r" % e)
        try:
            await _escribir_respuesta(writer, 500, {"error": "Error interno del servidor."})
        except Exception:                                                # noqa: BLE001
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:                                                # noqa: BLE001
            pass


async def iniciar(anotar=None):
    """Abre el servidor HTTP interno SOLO si existen R2_CUENTAS_FICHA_INTERNA y PANEL_PUERTO.
    Sin ellas devuelve None sin abrir nada ni cambiar el juego."""
    global _ANOTAR, _T0
    if anotar is not None:
        _ANOTAR = anotar
    ficha = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
    puerto_txt = (os.environ.get("PANEL_PUERTO") or "").strip()
    if not ficha or not puerto_txt:
        return None
    try:
        puerto = int(puerto_txt)
        if not 1 <= puerto <= 65535:
            raise ValueError("fuera de rango")
    except ValueError:
        _anotar("   ⚠ PANEL_PUERTO invalido (%r): el panel interno no se abre" % puerto_txt)
        return None
    host = (os.environ.get("PANEL_HOST") or "").strip() or "0.0.0.0"
    _T0 = time.time()
    srv = await asyncio.start_server(_atender_cliente, host, puerto)
    _anotar("panel interno escuchando en %s:%d" % (host, puerto))
    return srv
