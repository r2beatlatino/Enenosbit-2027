# -*- coding: utf-8 -*-
r"""jardin.py (11-nov, ficha 93) — el jardin (開心農場) de una cuenta LOCAL: abrirlo, verlo y salir. Layouts leidos del exe:
docs/tablero/layouts/gardenSys.md (sobre, secuencia de entrada, formas de las respuestas, tablas garden_tb*).

Metodos por nombre sobre FF26F (`CmdGardenForward`) y FF246 (`guide.*`):
  C2S [u64 id][u32 nl][nombre][u32 jl][JSON]        S2C [u64 A][u64 id][u32 nl][nombre][u32 jl][JSON][u32 0]
  gardenSys.openGarden [0]       -> {"fs":{"dyId","dbId","usn","es":[5 entidades],"frame"}}  (§3.1 de gardenSys.md)
  gardenSys.getGardenLog [1,-1]  -> {"d":[],"id":1}                                            (registro vacio)
  guide.getStep [1]              -> {"t":1,"ok":true,"s":28}  (28 = ultimo paso de garden_tbgardenguide: tutorial hecho)
Todo en JSON PLANO (el oficial lo manda plano en obsync / getMyInfo / guide.*; las respuestas grandes las manda envueltas con
msgpack+zlib: si el cliente no acepta el plano, ver ENVUELTO). El resto de los `gardenSys.*` NO se contestan (se anotan).

ESTADO (seccion `jardin` de la cuenta, solo via cuenta.py): se crea la primera vez que la cuenta abre el jardin.
  SALE DE TABLAS (garden_tb*): 4 parcelas (commconfig.initLand), tipo de tierra 1 (landconfig ids 1..4 con nivel 1 y costo 0),
    monedas = beginitem[99000002].num (100), mochila = el resto de beginitem (92000003 x1), nivel 1 (level), ultimo paso del
    tutorial (guide).
  INVENTADO (marcado `inventado: true`): el id del jardin u (= usn de la cuenta) y los ids de entidad (B = u*100000; eid/cid
    B+1025+k, dbId B+1043, dyId B+65536: relaciones MEDIDAS en 2 grabaciones), frame (~30 por segundo: 2 puntos), las semillas
    de azar por parcela, thiefs="9999999", landPoint 200 (= 4 x grade 50 de landtype 1: aritmetica), la estructura de
    entidades (tags 3002/3003, componentes 1002/1005/1006/1007/1008: de la FORMA de 2 grabaciones, sin valores de cuenta).

FICHA 100 (11-nov): el CICLO. Pedidos por FF26F `gardenSys.*` (el cliente los manda y espera la respuesta en la forma grabada
{"c":D,"p":D}; layouts/gardenSys.md "Lectura de la ficha 100"):
  buyItem [id iteminfo, tipo de pago, cantidad]  sol (buyType 3: del `coin` del jardin) o moneda premium (buyType 1: por catalogo, tienda.py)
  plant [cid del componente 1002, codigo de semilla]     useItem [codigo, cantidad, eid de la parcela]  (abono itemfunc [2,10,6])
  getFruit [cid 1002]     sellItem [[{id: codigo, num}...]]     batchLock [tipo, valor] (sin objetos bloqueados: marco vacio)
Todo en la seccion `jardin` con el candado de cuenta.py. Reglas de las TABLAS garden_tb*: precio (buyPrice), nivel (buyLevel contra
`level`), cosecha (getCount, getExp, getPoint, matureFruit), venta (sellPrice), tiempo (matureTime [s1,s2,s3] x 30 cuadros), abono
(itemfunc.value s). El tiempo lo pone el SERVIDOR (cuadro = _frame(reloj del servidor)). Un pedido que no se acepta recibe (FICHA 111) un `{c,p}` vacio con el codigo de error en `c.dc` (LEIDO: gardenMgr.netSync -> _printErrors llama
onErr una vez por cada `dc` fuera de {0,1,1000001,1000002}; `p.dc` queda en 0). MEDIDO con el juego: un solo cartel con el texto del motivo
(sin sol -> 25024 "Saldo insuficiente.", cosecha antes de tiempo -> 25008 "Todavia no maduro.", nivel de compra -> 25057 "No alcanzaste el nivel de
compra."), sin el segundo cartel "Se ha producido un error en la base de datos.:<codigo>" que salia con el texto numerico suelto de antes (los
LEIDO: el validador del jardin 0x00c8ff10 y otro generico 0x004ae4d0 -que arma "<texto 3089>:<codigo>"- muestran un cartel con todo lo que no
empiece con { o [; HIPOTESIS: el segundo cartel viene de este ultimo, no se lo vio en ejecucion). Los codigos son los de
`garden/world/gerror` (25000..25063; el mapa del exe 0x00c862b0 solo llega a 25057); la tabla motivo -> codigo esta en las constantes ERR_*
y en docs/tablero/layouts/gardenSys.md ("Lectura de la ficha 111"). FORMA_ERROR = "texto" vuelve a la forma vieja.
batchLock [21, 0|1] bloquea/desbloquea los frutos (tlock, INVENTADO; visto con el juego: candado, texto del boton y total de la venta).
INVENTADO: ver `actuar` y las constantes ETAPA_*, INDICE_EXTRA; los frutos de semillas de varias cosechas (se tratan de una
sola), que nada se marchita, `index` = len(operaciones) + extra por accion. NO esta: ladrones, desastres, regar (el cliente no manda nada
sin sequia; ficha 116: ya esta), premios de primera cosecha (semillas con seedrewards). Ficha 120: mejorar la tierra, abrir una parcela y visitar a otro (ver mas abajo).

JARDIN (llave de entorno, omision 1 desde que con el juego abrio, se vio y se salio 4 de 4) = 1 abre el jardin. 0 = como antes (sin atender).
JARDIN_JUGAR (omision 1) = 0 deja el ciclo sin atender (buyItem, plant, useItem, getFruit, sellItem, batchLock).
JARDIN_SEQUIA (ficha 116, omision 1 desde que con el juego se vio la sequia, regar, la cosecha con capas y la pala) = 1 lleva la sequia PROPIA (la misma cuenta que el Lua del cliente: weaSys + ecsRand), atiende doWater, pullout,
  doDeGrass y doDebug, y aplica las capas de sequia a la cosecha. 0 = como antes. Ver gardenSys.md §11.
JARDIN_TIERRA (ficha 120, omision 1 desde que con el juego se vio 2 veces: mejorar la tierra, abrir una parcela, plantar en ella y la cosecha con el bono) = 1 atiende `upLand` (mejorar la tierra con sol: comun -> roja), `unlockLand` (abrir
  la parcela siguiente), exige que la tierra este lista para plantar y suma a la cosecha el bono de la tierra (`yieldUp`). 0 = como antes (sin atender).
JARDIN_VISITAR (ficha 120, omision 1 desde que con el juego se vio 3 veces, entrando desde DENTRO del jardin) = 1 atiende `gardenSys.visit [apodo]` (el jardin de otra cuenta local, solo mirar) y
  contesta con un rechazo real `doSteal` / `helpDoWater`. 0 = como antes (sin atender). Ver gardenSys.md §12.
JARDIN_VECINOS (ficha 125, omision 1 desde que con el juego se vio ayudar 3 veces, robar 6, la lista de amigos y el registro, con el jardin del dueno coherente al reabrirlo y tras reiniciar el servidor) = 1 (solo con JARDIN y JARDIN_VISITAR = 1)
  atiende `helpDoWater` y `doSteal` dentro del jardin de otro (la respuesta es {"m": {"<usn dueno>": {c,p}, "<usn visitante>": {c,p}}}: un diff por mundo), la cosecha del dueno que descuenta lo robado, `getAllFriends` / `getFriends`
  (la lista de amigos del jardin) y el registro (`getGardenLog`: avisos bs, bt, hp). 0 = como la ficha 120 (rechazo 25013, sin lista, registro vacio). Ver gardenSys.md §13.
"""
import datetime
import json
import os
import random
import struct
import time

import cuenta as _cta
import estado

LLAVES_OMISION = {"JARDIN": "1", "JARDIN_JUGAR": "1", "JARDIN_SEQUIA": "1", "JARDIN_TIERRA": "1", "JARDIN_VISITAR": "1", "JARDIN_VECINOS": "1"}
RELOJ = time.time               # las pruebas lo cambian por un reloj falso
VERSION_ESTADO = 1
FRAME_POR_S = 30                # ~30 cuadros por segundo (HIPOTESIS por 2 puntos de las grabaciones)
FRAME_REF = 2284638239          # un frame visto en una grabacion, usado solo como orden de magnitud (el cliente lo ve en u32)
T_REF = datetime.datetime(2026, 10, 29, 22, 4).timestamp()   # el instante de ese frame, a minutos (inventado)
THIEFS_VACIO = "9999999"        # 8 de 8 en las grabaciones
LANDPOINT_TIPO1 = 50            # landtype 1 grade
NOMBRE_OPEN, NOMBRE_LOG, NOMBRE_GETSTEP, NOMBRE_SETSTEP = (
    "gardenSys.openGarden", "gardenSys.getGardenLog", "guide.getStep", "guide.setStep")
CODIGO_SOL = 99000002           # 阳光: viaja en `coin`, no en la mochila (2 de 2 grabaciones)
GUIA_JARDIN = 1                 # el `t` de guide.getStep que manda el jardin (MEDIDO: [1] en 3 de 3)

_RUTA_TABLAS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "import_input", "steam_10379", "_extract", "rnr_script", "config")
# Ficha 171: tablas del pak, sin cuentas, incluidas en el paquete limpio.
# Si no esta la carpeta local se conserva la ruta anterior de esta PC.
_TABLAS_PAQUETE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "jardin")
if os.path.isdir(_TABLAS_PAQUETE):
    _RUTA_TABLAS = _TABLAS_PAQUETE
_TABLAS = {}


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="JARDIN"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


# ---------------------------------------------------------------- tablas
def tabla(nombre):
    """garden_tb<nombre>.json del pak (GBK o UTF-8). None si no esta."""
    if nombre in _TABLAS:
        return _TABLAS[nombre]
    t = None
    try:
        b = open(os.path.join(_RUTA_TABLAS, "garden_tbgarden%s.json" % nombre), "rb").read()
        try:
            t = json.loads(b.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            t = json.loads(b.decode("gbk", errors="replace"))
    except (OSError, ValueError):
        t = None
    _TABLAS[nombre] = t
    return t


def tablas_ok():
    return all(tabla(n) is not None for n in ("beginitem", "commconfig", "landconfig", "level", "guide"))


def ultimo_paso_guia():
    g = tabla("guide") or []
    g = list(g.values()) if isinstance(g, dict) else g
    return max([f["step"] for f in g] or [0])


# ---------------------------------------------------------------- estado
def _inicial(usn, ahora):
    """Jardin nuevo: de TABLAS lo que hay, INVENTADO lo demas (ver el encabezado)."""
    begin = tabla("beginitem") or []
    n_parcelas = int((tabla("commconfig") or {}).get("initLand", 4))
    tierras = sorted((tabla("landconfig") or {}).values(), key=lambda r: r["id"])
    abiertas = [r for r in tierras if r["useLevel"] <= 1 and r["nUseSumCoin"] == 0][:n_parcelas]
    n_parcelas = len(abiertas) or n_parcelas
    coin = sum(b["num"] for b in begin if b["code"] == CODIGO_SOL)
    bolsa = {}
    for b in begin:
        bolsa[str(b["code"])] = 0 if b["code"] == CODIGO_SOL else b["num"]
    rnd = random.Random(usn * 7919 + ahora)
    frame0 = _frame(ahora)
    return {"version": VERSION_ESTADO, "inventado": True, "creada": ahora, "u": int(usn), "nivel": 1, "gexp": 0, "gpoint": 0,
            "coin": coin, "cocnt": 0, "cof": 0, "landpoint": n_parcelas * LANDPOINT_TIPO1, "bolsa": bolsa,
            "parcelas": [{"id_tierra": a["id"], "tipo": 1, "seed": rnd.randrange(1 << 20, 1 << 32), "lsf": frame0 - 1, "planta": None}
                         for a in abiertas] or [{"id_tierra": k + 1, "tipo": 1, "seed": rnd.randrange(1 << 20, 1 << 32),
                                                 "lsf": frame0 - 1, "planta": None} for k in range(n_parcelas)]}


def _frame(ahora):
    return FRAME_REF + int((ahora - T_REF) * FRAME_POR_S)


def _marcar_apertura(usn, frame):
    """`lcf`: el cuadro del ultimo mensaje del jardin (lo usa `p.pf` de las respuestas). INVENTADO."""
    def f(c):
        c["lcf"] = frame
    _cta.cambiar_seccion(usn, "jardin", f)


def estado_de(usn, ahora=None):
    """El estado del jardin de ese usn; si no tiene (o es de otra version), lo crea INVENTADO y lo guarda. Devuelve copia."""
    ahora = int(RELOJ()) if ahora is None else ahora

    def f(c):
        _preparar(c, usn, ahora)
        return json.loads(json.dumps(c))
    return _cta.cambiar_seccion(usn, "jardin", f)


def _preparar(c, usn, ahora):
    """Dentro del candado: deja c en la version actual (lo creado en la ficha 93 se conserva: solo se agrega `planta` a cada parcela)."""
    if c.get("version") != VERSION_ESTADO:
        c.clear()
        c.update(_inicial(usn, ahora))
    for p in c.get("parcelas", []):
        p.setdefault("planta", None)
        p.setdefault("clima", {"drought": 0, "dstart": 0, "roll": 0})
    if llave("JARDIN_SEQUIA"):
        avanzar_sequia(c, ahora)


# ---------------------------------------------------------------- el fs de openGarden
def _ids(g):
    """Los ids INVENTADOS (relaciones MEDIDAS en 2 grabaciones): B = u*100000; raiz B+1025, estado B+1026, mochila B+1027,
    parcela k: eid B+1028+4k y sus 3 componentes (planta, robos, clima) eid+1..+3; dbId = el ultimo reservado."""
    B = g["u"] * 100000
    eid_t = [B + 1028 + 4 * k for k in range(len(g["parcelas"]))]
    return {"B": B, "raiz": B + 1025, "c_estado": B + 1026, "c_bolsa": B + 1027, "eid_t": eid_t,
            "dy": B + 65536, "db": (eid_t[-1] + 3) if eid_t else B + 1027}


def armar_fs(g, ahora=None):
    """El `fs` de openGarden: {"dyId","dbId","usn","es":[raiz tag 3003, parcelas tag 3002 ...],"frame"} (forma de gardenSys.md §3.1)."""
    ahora = int(RELOJ()) if ahora is None else ahora
    frame = _frame(ahora)
    ids = _ids(g)
    eid_raiz, eid_t = ids["raiz"], ids["eid_t"]
    c_estado, c_bolsa = ids["c_estado"], ids["c_bolsa"]
    raiz = {"eid": eid_raiz, "tag": 3003, "rel": {"tiles": eid_t},
            "coms": [{"cid": c_estado, "tag": 1007, "landPoint": g["landpoint"], "gpoint": g["gpoint"], "coin": g["coin"],
                      "cocnt": g["cocnt"], "gexp": g["gexp"], "cof": g["cof"]},
                     {"cid": c_bolsa, "tag": 1005,
                      "map": {code: {"itemcode": int(code), "num": num, "tlock": g.get("bloqueo", {}).get(code, 0), "twea": _twea(code)} for code, num in g["bolsa"].items()}}]}
    es = [raiz]
    for k, p in enumerate(g["parcelas"]):
        e0 = eid_t[k]
        es.append({"eid": e0, "tag": 3002, "owner": eid_raiz, "coms": [
            _comp_planta(e0 + 1, p, frame), _comp_robos(e0 + 2, p.get("robos") if llave("JARDIN_VECINOS") else None),
            _comp_clima(e0 + 3, p.get("clima"))]})
    return {"fs": {"dyId": ids["dy"], "dbId": ids["db"], "usn": g["u"], "es": es, "frame": frame}}


def _twea(code):
    """`twea` de un objeto de la mochila: 1 en los FRUTOS (itemType 21: van al almacen), 0 en el resto. MEDIDO: la grabacion 006 trae el fruto con twea 1 y
    la semilla, el abono y el sol con 0, y las operaciones `f` de la cosecha ponen [-5,"twea",1] (ver a_cosechar). Con 0 el fruto no sale en el almacen."""
    fila = items()[1].get(int(code))
    return 1 if fila is not None and fila["itemType"] == 21 else 0


def _comp_planta(cid, p, frame):
    """Componente 1002 de una parcela en el cuadro `frame` (la etapa se calcula con el reloj del SERVIDOR)."""
    pl = p.get("planta")
    c = {"cid": cid, "tag": 1002, "plantType": 0, "seed": p["seed"], "stage": 0, "plantTime": 0, "landLv": p["tipo"],
         "plantlandLv": 0, "harvestCount": 0, "sf": 0, "lsf": p["lsf"]}
    if pl:
        etapa, sf, _ok = etapa_de(pl, frame)
        c.update({"plantType": pl["code"], "stage": etapa, "plantTime": pl["t"], "plantlandLv": p["tipo"], "sf": sf})
    return c


def _comp_robos(cid, r=None):
    """Componente 1006 (robos). `r` = {times, stolen, thiefs} de la parcela (ficha 125, llave JARDIN_VECINOS); sin `r` = ceros como siempre."""
    r = r or {}
    return {"cid": cid, "tag": 1006, "stolen": r.get("stolen", 0), "times": r.get("times", 0), "thiefs": r.get("thiefs", THIEFS_VACIO)}


def _comp_clima(cid, cl=None):
    cl = cl or {}
    return {"cid": cid, "tag": 1008, "gstart": 0, "drought": cl.get("drought", 0), "dstart": cl.get("dstart", 0), "bugstat": 0,
            "roll": cl.get("roll", 0), "bstart": 0, "grasstat": 0}


# ---------------------------------------------------------------- la sequia propia (ficha 116)
# LEIDO (Lua, _fuera_git/lua/dis): ecsRand 2f53d93c f0 (generador 1664525 / 1013904223 mod 2^32), f2 (metodo de alias), f3 (pickInPool: las DOS
# tiradas usan la MISMA semilla y devuelve la semilla despues de UN paso); weaSys 4ad8136e f3 (periodo = secToFrame(disasterHappenTime 3600)),
# f4-f5 (piscina por `weight` en el orden de pairs sobre las claves 1,2,4,6), f6 rollDisaser, f9 rollDisaserEx, f11 updateImpl, f12 resetDisaster.
PERIODO = 3600 * FRAME_POR_S         # HIPOTESIS: secToFrame(s) = s * 30 (igual que matureTime x 30, MEDIDO)
MAX_CAPAS = 3                        # commconfig.maxDisLayer
MAX_TIRADAS = 48                     # weaSys.maxRollCount
TIPO_SEQUIA = 2
YIELD_DOWN = 20                      # disastertype[2].yieldDwon
EXP_REGAR = 20                       # disastertype[2].addExp
RETAIN = 5                           # commconfig.retain
ERR_NO_ENTIDAD = 25020               # NO_SUCH_ENTITY (gerror 0dc789e2, LEIDO)
ERR_NO_DESASTRE = 25026              # NO_DISASTER
ERR_TIERRA_NO_LISTA = 25032          # LAND_NOT_READY
# ficha 120 (nombres LEIDOS en `garden/world/gerror` 0dc789e2; el orden de las comprobaciones, de `tileSys` b012fa2a f9, f10, f13, f16)
ERR_NIVEL_TIERRA = 25011             # NOT_UP_LEVEL
ERR_NO_TIERRA = 25014                # NO_SUCN_LAND
ERR_SALTO_NIVEL = 25017              # UPLV_CANT_JUMP (no se puede dar: dest = nivel + 1 siempre)
ERR_NIVEL_NO_EXISTE = 25018          # LANDLV_NOT_EXISTS
ERR_TIERRA_MALA = 25019              # BAD_LAND_LV
ERR_ECID = 25021                     # MISMATCH_ECID (entidad o componente que no es el de una parcela)
ERR_SIN_RELACION = 25028             # NO_RELATION (visitar a quien no existe: HIPOTESIS que el oficial lo use asi)
ERR_NO_MAS_PARCELAS = 25058          # NOMORE_TILE
ERR_TIERRA_EN_OBRA = 25061           # UPLV_CANT_UEXPASION


def _lcg(seed):
    return (1664525.0 * seed + 1013904223.0) % 4294967296.0


def _alias_pool():
    """Pesos 8000/2000/0/0 (garden_tbgardendisastertype, orden de pairs = claves 1,2,4,6): metodo de alias de ecsRand f2 (colas FIFO)."""
    import collections
    filas = tabla("disastertype") or []
    filas = list(filas.values()) if isinstance(filas, dict) else filas
    filas = sorted(filas, key=lambda r: r["disasterType"])
    ws = [r["weight"] for r in filas]
    N, total = len(ws), sum(ws)
    prob, alias = {}, {}
    chicas, grandes = collections.deque(), collections.deque()
    for i, w in enumerate(ws, 1):
        v = w * N
        if v == total:
            prob[i] = v
        else:
            (chicas if total >= v else grandes).append({"index": i, "value": v})
    while chicas:
        c = chicas.popleft()
        g_ = grandes[0]
        prob[c["index"]], alias[c["index"]] = c["value"], g_["index"]
        g_["value"] = g_["value"] + c["value"] - total
        if g_["value"] >= total:
            if g_["value"] != total:
                continue
            grandes.popleft()
            prob[g_["index"]] = total
        else:
            grandes.popleft()
            chicas.append(g_)
    return total, prob, N, alias, [r["disasterType"] for r in filas]


def tirada(semilla):
    """pickDisaster: (tipo de desastre, semilla nueva). 1 = nada, 2 = sequia."""
    pool = _TABLAS.get("_pool_desastre")
    if pool is None:
        pool = _TABLAS["_pool_desastre"] = _alias_pool()
    total, prob, N, alias, tipos = pool
    s1 = _lcg(semilla)
    i = int(1 + (s1 % N))
    r = 1 + (s1 % total)
    k = i if prob[i] >= r else alias.get(i, i)
    return tipos[int(k) - 1], int(s1)


def frame_cliente(ahora):
    """El reloj del CLIENTE (LEIDO en el exe: ms desde 2024-06-01 00:00 UTC+8 / 33.33333); el cuadro del servidor va ~40 s detras (MEDIDO 12-nov)."""
    return int((ahora * 1000 - 1717171200000) / 33.33333)


def _cli_de_cf(cf):
    return frame_cliente(T_REF + (cf - FRAME_REF) / float(FRAME_POR_S))


def _aplicar_sequia(p, cl, last, j, semilla):
    cl["drought"] += 1
    cl["dstart"] = cl["roll"] = last + j * PERIODO
    p["seed"] = semilla


def avanzar_sequia_parcela(p, cur, lote=False):
    """Lo que hace el weaSys del Lua con la planta de la parcela `p` en el cuadro `cur` (reloj del cliente). lote=False: el cliente avanza cuadro a cuadro,
    asi que cada tirada se resuelve en su frontera (updateImpl con n = k tiradas); lote=True: UNA llamada (lote="siempre": todas las vueltas en lote, lo que hace un cliente que abre una planta vieja con el 1008 en cero) con n = min(48, (cur-last)//P) tiradas.
    Devuelve la cantidad de capas nuevas."""
    pl = p.get("planta")
    cl = p.setdefault("clima", {"drought": 0, "dstart": 0, "roll": 0})
    nuevas = 0
    while cl["drought"] < MAX_CAPAS:            # con todas las capas rollDisaserEx devuelve nil: no se toca nada
        if not pl:
            break
        last = cl["roll"] or pl["t"]
        n = min(MAX_TIRADAS, (cur - last) // PERIODO)
        if n < 1:
            break
        s, hit, s_hit = p["seed"], None, None
        for k in range(1, n + 1):
            t, s = tirada(s)
            if t == TIPO_SEQUIA:
                hit, s_hit = k, s
                break
        if hit is None:
            break
        if lote:                                 # la tabla guarda la 1.a sequia, pero la semilla queda despues de TODAS las tiradas del lote
            for k in range(hit + 1, n + 1):
                _t, s = tirada(s)
            s_hit = s
        _aplicar_sequia(p, cl, last, hit, s_hit)
        nuevas += 1
        lote = (lote == "siempre")
    return nuevas


def avanzar_sequia(c, ahora):
    cur = frame_cliente(ahora)
    for p in c.get("parcelas", []):
        if p.get("planta"):
            avanzar_sequia_parcela(p, cur)


def capas_de(p):
    return p.get("clima", {}).get("drought", 0)


def cosecha_con_capas(n, capas):
    """harvestSys f4/f6: cada capa multiplica por (100 - yieldDwon)/100 (en coma flotante), se hace floor al final y nunca menos de `retain`."""
    if capas <= 0:
        return n
    import math
    x = float(n)
    for _ in range(capas):
        x = x * ((100 - YIELD_DOWN) / 100.0)
    return max(RETAIN, int(math.floor(x)))


def cosecha_con_tierra(n, tipo):
    """harvestSys f7 + f14 (getAllFruitBonus): el bono de la tierra es calcBonusPercentageCeil(num, yieldUp) = 0 si yieldUp es 0, si no ceil(num * yieldUp / 100)
    (ecsUtility f17); se SUMA a `num` (que ya trae las capas de sequia y el minimo `retain`). Otras fuentes de bono (objetos de la mochila, borde) = 0: HIPOTESIS."""
    import math
    fila = _landtype(tipo) or {}
    pct = fila.get("yieldUp", 0)
    return n if not pct else n + int(math.ceil(n * (pct / 100.0)))


# ---------------------------------------------------------------- el sobre
def _contador(con):
    """A: contador por canal que solo crece (de proceso: vive en estado.py, que no se recarga)."""
    a = getattr(estado, "_jardin_A", None)
    if a is None:
        a = {"26F": 0x30000, "246": 0x30000}
        estado._jardin_A = a
    return a


def sobre(con, canal, cuerpo_pedido, nombre, js):
    """El cuerpo S2C [u64 A][u64 id][s nombre][s JSON][u32 0] (id = el del pedido)."""
    a = _contador(con)
    a[canal] += 1
    nb = nombre.encode("ascii")
    jb = js.encode("utf-8") if isinstance(js, str) else js
    return (struct.pack("<Q", a[canal]) + cuerpo_pedido[:8] + struct.pack("<I", len(nb)) + nb + struct.pack("<I", len(jb)) + jb
            + struct.pack("<I", 0))


def leer_pedido(cuerpo):
    """(nombre, args) de un C2S [u64 id][s nombre][s JSON]; None si no encaja."""
    if len(cuerpo) < 16:
        return None
    nl = struct.unpack_from("<I", cuerpo, 8)[0]
    if not 3 <= nl <= 64 or 12 + nl + 4 > len(cuerpo):
        return None
    nombre = cuerpo[12:12 + nl]
    jl = struct.unpack_from("<I", cuerpo, 12 + nl)[0]
    if 16 + nl + jl != len(cuerpo) or not all(32 < c < 127 for c in nombre):
        return None
    try:
        return nombre.decode(), json.loads(cuerpo[16 + nl:].decode("utf-8") or "null")
    except ValueError:
        return nombre.decode(), None


def _json(x):
    return json.dumps(x, separators=(",", ":"), ensure_ascii=False)


def _usn(con):
    c = con.cuenta or {}
    return c.get("usn"), c.get("nick") or ""


def _contestar(con, seq, cmd, canal, cuerpo, nombre, obj):
    js = _json(obj)
    con.mandar_interno(cmd, seq, sobre(con, canal, cuerpo, nombre, js))
    return len(js)


def jardin_forward(con, seq, cuerpo):
    """C2S FF26F: openGarden y getGardenLog; el resto de gardenSys.* se anota y NO se contesta."""
    if not llave() or not tablas_ok():
        return False
    usn, nick = _usn(con)
    if usn is None:
        return False
    p = leer_pedido(cuerpo)
    if p is None:
        return False
    nombre, args = p
    if nombre == NOMBRE_OPEN:
        if args not in ([0], [usn]):
            anotar("   FF26F gardenSys.openGarden con argumento %r: SIN ATENDER (solo el jardin propio)" % (args,))
            return False
        g = estado_de(usn)
        fs = armar_fs(g)
        _marcar_apertura(usn, fs["fs"]["frame"])
        n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, fs)
        anotar("   S2C FF26F openGarden de %s: JSON plano %d B, %d entidades, frame %d (INVENTADO el estado inicial)"
               % (nick, n, len(fs["fs"]["es"]), fs["fs"]["frame"]))
        return True
    if nombre == NOMBRE_LOG:
        pag = args[0] if isinstance(args, list) and args and isinstance(args[0], int) else 1
        filas = filas_registro(estado_de(usn)) if llave("JARDIN_VECINOS") else []
        n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, {"d": filas, "id": pag})
        anotar("   S2C FF26F getGardenLog: %s (%d B)" % ("%d filas" % len(filas) if filas else "vacio", n))
        return True
    if nombre == NOMBRE_VISIT and llave("JARDIN_VISITAR"):
        return _visitar(con, seq, cuerpo, usn, nick, nombre, args)
    if nombre in (NOMBRE_ROBAR, NOMBRE_AYUDAR) and llave("JARDIN_VISITAR") and llave("JARDIN_VECINOS"):
        return _vecino(con, seq, cuerpo, usn, nick, nombre, args)
    if nombre == NOMBRE_AMIGOS and llave("JARDIN_VECINOS"):
        return _amigos(con, seq, cuerpo, usn, nick, nombre, args)
    if nombre == "gardenSys.getFriends" and llave("JARDIN_VECINOS"):
        return _amigos_fila(con, seq, cuerpo, usn, nick, nombre, args)
    if nombre in NO_SOPORTADOS_VISITANDO and llave("JARDIN_VISITAR"):
        return _rechazo_visitante(con, seq, cuerpo, usn, nick, nombre, args)
    if (nombre in ACCIONES and llave("JARDIN_JUGAR") and (nombre not in METODOS_SEQUIA or llave("JARDIN_SEQUIA"))
            and (nombre not in METODOS_TIERRA or llave("JARDIN_TIERRA"))):
        return _accion(con, seq, cuerpo, usn, nick, nombre, args)
    if nombre.startswith("gardenSys.") or nombre.startswith("gardenRankAct."):
        anotar("   FF26F %s %s SIN ATENDER (jardin: openGarden, getGardenLog y el ciclo comprar/plantar/usar/cosechar/vender)"
               % (nombre, _json(args)[:80]))
    return False


def guia_forward(con, seq, cuerpo):
    """C2S FF246 guide.getStep/setStep con t = 1 (el del jardin): tutorial hecho. Otros t: se anotan y pasan."""
    if not llave() or not tablas_ok() or len(cuerpo) < 16:
        return False
    usn, _nick = _usn(con)
    if usn is None:
        return False
    p = leer_pedido(cuerpo)
    if p is None or p[0] not in (NOMBRE_GETSTEP, NOMBRE_SETSTEP):
        return False
    nombre, args = p
    if not (isinstance(args, list) and args and args[0] == GUIA_JARDIN):
        anotar("   FF246 %s %s: t distinto del jardin, SIN ATENDER" % (nombre, _json(args)[:60]))
        return False
    s = ultimo_paso_guia() if nombre == NOMBRE_GETSTEP else (args[1] if len(args) > 1 else 0)
    n = _contestar(con, seq, 0x246, "246", cuerpo, nombre, {"t": GUIA_JARDIN, "ok": True, "s": s})
    anotar("   S2C FF246 %s t=1: s=%d (%d B, tutorial del jardin hecho)" % (nombre, s, n))
    return True


# ---------------------------------------------------------------- reglas del ciclo (ficha 100): de las TABLAS garden_tb*
FPS = FRAME_POR_S
# Codigos de etapa (componente 1002, `stage`). 0 = vacia, 101 = semilla y 301 = madura: MEDIDOS en 2 grabaciones. 102 (brote) = LEIDO en el exe:
# la funcion que arma el texto de la parcela (0x00ce3a00) carga a mano el mapa codigo -> indice {0:0, 101:1, 102:2, 301:3} (datos en 0x037469f0 y
# 0x03746a40) y los nombres 4332..4335 (空 Vacio, 种子期 Semilla, 发芽期 Brotar, 成熟期 Maduro); un codigo que no esta en el mapa cae en el indice 0
# ("Vacio"). Por eso el 201 que mandaba la ficha 100 mostraba "Vacio(47minutoSemilla)". MEDIDO con el juego (ficha 101, reabriendo con la planta
# de 700 s y de 2000 s): 102 con sf = madurez -> "Brotar(48minutoMaduro)" y "Brotar(26minutoMaduro)", los textos correctos.
ETAPA_1, ETAPA_2, ETAPA_3 = 101, 102, 301
# ERRORES (ficha 111): los codigos son los de `garden/world/gerror` del Lua (id 0dc789e2, funcion 1: 25000..25063); el texto de cada uno sale del mapa
# 0x00c862b0 del exe (25000..25057 -> id de texto 4361..4420) y de la tabla de idiomas. Que codigo va con cada motivo: LEIDO por el NOMBRE del codigo
# en el Lua (los que dicen "por el nombre"), HIPOTESIS donde se marca; MEDIDO con el juego: 25024, 25005, 25008 (ficha 101) y 25057 (ficha 111).
ERR_ITEM_FALTA = 25001         # NOT_ENOUGHT  "No tienes suficientes objetos" (LEIDO por el nombre: hay objeto pero menos de la cantidad)
ERR_OCUPADA = 25005            # HAS_PLANT    "La parcela ya tiene una planta" (MEDIDO con el juego, ficha 101)
ERR_NO_SEMILLA = 25006         # NOT_A_SEED   "El objeto seleccionado no es una semilla"
ERR_SIN_COMPONENTE = 25007     # NO_SUCH_COM  "El componente solicitado no existe" (un cid de parcela que no existe; HIPOTESIS)
ERR_NO_MADURO = 25008          # NOT_MATU     "Todavia no maduro" (MEDIDO con el juego, ficha 101)
ERR_SIN_ENTIDAD = 25012        # NO_ENTITY    "La entidad no existe" (un eid de parcela que no existe; HIPOTESIS)
ERR_OPERACION = 25013          # OP_NOT_SUPPORT "Operacion no admitida"
ERR_PAGO = 25022               # NOT_SUCH_WAY "Forma de pago no admitida" (LEIDO por el nombre)
ERR_SALDO = 25024              # NO_GMONEY    "Saldo insuficiente" (MEDIDO con el juego, ficha 101)
ERR_OPERACION_MALA = 25035     # NO_SHCN_OP   "La operacion no existe" (pedido mal formado: HIPOTESIS)
ERR_SIN_OBJETO = 25036         # NOT_ITEM     "No tienes ese objeto"
ERR_COMPRA = 25037             # BUY_FIAL     "La compra fallo" (algo que el jardin no vende asi / cantidad fuera de rango; HIPOTESIS)
ERR_VENTA_PARAM = 25042        # SELL_PARM_ERR "Parametros de venta invalidos"
ERR_NO_VENDIBLE = 25043        # SELL_CANT_SELL "Este objeto no se puede vender"
ERR_PRECIO = 25044             # BAD_ITEM_PRICE "Precio del objeto incorrecto" (objeto sin precio en el catalogo; HIPOTESIS)
ERR_VENTA_BLOQUEADO = 25046    # SELL_LOCK    "No puedes vender un objeto bloqueado" (LEIDO por el nombre)
ERR_NO_USABLE = 25049          # NOT_USE_ITEM "Este objeto no se puede usar"
ERR_ETAPA_USO = 25051          # CUR_STAGE_CANT_USE "No se puede usar en esta etapa" (el abono en una planta ya madura)
ERR_EXCEPCION = 25052          # GARDEN_FALUT "La granja tuvo una anomalia" (una excepcion NUESTRA)
ERR_NO_ES_DEL_JARDIN = 25053   # NO_SUCH_ITEM "No es un objeto de granja"
ERR_GENERICO = 25054           # GFAIL        "La operacion fallo": el mas generico que hay (lo que el servidor local no soporta; HIPOTESIS)
ERR_SIN_PLANTA = 25055         # NO_PLANT     "No hay plantas en la parcela"
ERR_NIVEL_COMPRA = 25057       # BUY_NOLV     "No alcanzaste el nivel de compra"
ERROR_GENERICO = str(ERR_GENERICO)
# FORMA del rechazo (ficha 111). "json" = un `{c,p}` con el codigo en `c.dc` (LEIDO: gardenMgr.netSync -> _printErrors llama onErr si `dc` no esta en
# {0,1,1000001,1000002}); "texto" = el texto numerico de antes (sale el cartel del jardin Y despues el de "error en la base de datos").
FORMA_ERROR = "json_dc"
INDICE_EXTRA = {"buy": 0, "plant": 0, "use": 1, "fruit": 4, "sell": 1, "water": 0, "pull": 0, "land": 0, "unlock": 0}   # `index` = len(ops) + esto (MEDIDO en 7 muestras; HIPOTESIS)
FLAGS_N = {"updateBag": 1, "buyI": 21, "pl": 21, "us": 5, "hf": 23, "sl": 7}   # ultimo entero del aviso "n" (MEDIDO, 1 por nombre)
MAX_CANTIDAD = 999
BUY_SOL, BUY_CASH = 3, 1       # iteminfo.buyType: 3 = sol (coin, MEDIDO: 12 de coin al comprar el rabano); 1 = moneda premium (MEDIDO: el saldo FF51 baja)


class Rechazo(Exception):
    """Un pedido que el servidor no acepta (el estado NO se toca). `codigo` = el codigo de error del cliente (ERR_*)."""

    def __init__(self, motivo, codigo=ERR_GENERICO):
        Exception.__init__(self, motivo)
        self.codigo = codigo


def items():
    """(por_id, por_code) de iteminfo; code repetido (92000020): gana la primera fila."""
    r = _TABLAS.get("_items")
    if r is None:
        t = tabla("iteminfo") or []
        rows = list(t.values()) if isinstance(t, dict) else t
        por_code = {}
        for x in rows:
            por_code.setdefault(x["code"], x)
        r = _TABLAS["_items"] = ({x["id"]: x for x in rows}, por_code)
    return r


def semillas_con_premio():
    """Codigos de semilla cuya primera cosecha da premio (seedrewards.rewards no vacio): NO soportado en esta ficha."""
    t = tabla("seedrewards") or {}
    rows = list(t.values()) if isinstance(t, dict) else t
    return {x["code"] for x in rows if x.get("rewards")}


def abono(code):
    """Segundos que quita de crecimiento el objeto `code` (itemfunc [2,10,6] sobre una parcela 3002), o None si no es de esos."""
    t = tabla("itemfunc") or {}
    rows = list(t.values()) if isinstance(t, dict) else t
    for x in rows:
        if x["code"] == code:
            if x["function"][:3] == [2, 10, 6] and x["useObject"] == [3002] and x["value"]:
                return int(x["value"][0])
            return None
    return None


def nivel_de(gexp):
    """Nivel de jardin que dan `gexp` puntos de experiencia (tabla level: exp = umbral acumulado)."""
    filas = _TABLAS.get("_niveles")
    if filas is None:
        t = tabla("level") or []
        rows = list(t.values()) if isinstance(t, dict) else t
        filas = _TABLAS["_niveles"] = sorted((r["level"], r["exp"]) for r in rows)
    n = 1
    for lv, ex in filas:
        if ex <= gexp:
            n = lv
        else:
            break
    return n


def _tiempos(code):
    """(fin de la etapa 1, madurez, resguardo) en cuadros desde plantTime: matureTime = [s1, s2, s3] segundos (HIPOTESIS: s1 etapa
    brote, s2 etapa crecimiento, la planta madura a s1+s2; s3 = lo que dura la etapa 3 antes del `sf`)."""
    m = items()[1][code]["matureTime"]
    return m[0] * FPS, (m[0] + m[1]) * FPS, m[2] * FPS


def etapa_de(pl, frame):
    """(stage, sf, maduro) de una planta {code, t, adel} en el cuadro `frame`. 101 y sf = plantTime + s1*30 MEDIDOS; maduro por
    abono: stage 301 y sf = ahora + s3*30 MEDIDO; la etapa 102 (brote) es LEIDA (ver ETAPA_*) y MEDIDA con el juego; el paso natural a 301 a la hora de madurez lo cuenta el servidor."""
    t1, t2, t3 = _tiempos(pl["code"])
    fin1 = pl["t"] + t1 - pl.get("adel", 0)
    maduro_en = pl["t"] + t2 - pl.get("adel", 0)
    if frame >= maduro_en:
        return ETAPA_3, maduro_en + t3, True
    if frame >= fin1:
        return ETAPA_2, maduro_en, False
    return ETAPA_1, fin1, False


def _entero(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _err_falta(g, code):
    """Falta un objeto: 25036 (no tiene ninguno) o 25001 (tiene, pero menos de la cantidad pedida). La eleccion es HIPOTESIS (por los nombres NOT_ITEM / NOT_ENOUGHT)."""
    return ERR_ITEM_FALTA if g["bolsa"].get(str(code), 0) > 0 else ERR_SIN_OBJETO


def _parcela_por(g, ids, valor, que):
    """(indice, parcela) cuya `que` ('eid' o 'cid') es `valor`; Rechazo si no existe."""
    for k, e0 in enumerate(ids["eid_t"]):
        if (e0 if que == "eid" else e0 + 1) == valor:
            return k, g["parcelas"][k]
    raise Rechazo("parcela %s %r inexistente" % (que, valor), ERR_SIN_ENTIDAD if que == "eid" else ERR_SIN_COMPONENTE)


def _comp_estado(g, ids):
    return {"cid": ids["c_estado"], "landPoint": g["landpoint"], "gexp": g["gexp"], "tag": 1007, "coin": g["coin"],
            "cocnt": g["cocnt"], "gpoint": g["gpoint"], "cof": g["cof"]}


def _bolsa_suma(g, ids, u, ops, code, n, twea):
    """Agrega n de `code` a la mochila con las operaciones de la grabacion (i [g i] f)."""
    cb = ids["c_bolsa"]
    ops.append(["i", u, cb, code, 1])
    if str(code) not in g["bolsa"]:
        g["bolsa"][str(code)] = 0
        ops.append(["g", u, cb, "itemcode", {"cid": cb, "num": 0, "tlock": 0, "twea": 0, "itemcode": code}])
        ops.append(["i", u, cb, code, 1])
    g["bolsa"][str(code)] += n
    ops.append(["f", u, cb, "itemcode", code, [-9, "num", n, -5, "twea", twea]])


def _bolsa_resta(g, ids, u, ops, code, n):
    cb = ids["c_bolsa"]
    ops.append(["i", u, cb, code, 1])
    g["bolsa"][str(code)] -= n
    ops.append(["f", u, cb, "itemcode", code, [-1, "num", n]])


def _aviso(u, eid, nombre, cf, datos):
    return ["n", u, eid, 0, nombre, cf, datos, FLAGS_N[nombre]]


def _D(ids, tu, cf_, pf_, o, idx, dc=0, suc=True, err=0):
    return {"tu": tu, "ls": True, "cf": cf_, "pf": pf_, "dc": dc, "dy": ids["dy"], "db": ids["db"],
            "o": {"l": {"suc": suc, "err": err, "index": idx}, "o": o}, "ds": True}


def _marco(g, ids, cf, ops, clave):
    """{"c","p"} de la grabacion: c = el cuadro con las operaciones, p = el anterior (sin operaciones); `p.pf` = el `cf` del mensaje anterior."""
    ant = g.get("lcf") or cf
    g["lcf"] = cf
    return {"c": _D(ids, 1, cf, cf, ops, (len(ops) + INDICE_EXTRA[clave]) if ops else 0), "p": _D(ids, 0, cf, ant, [], 0)}


def marco_error(g, ids, cf, codigo):
    """El `{c,p}` de un rechazo (ficha 111), SIN tocar el estado: el mismo marco vacio, con el codigo de error en `c.dc` (LEIDO: netSync llama
    _printErrors(c) y esta llama onErr una vez porque `dc` no esta en {0,1,1000001,1000002}); `p` queda con dc 0, asi sale UN solo aviso.
    `FORMA_ERROR` = "json_dc" (solo dc), "json_dc_err" (dc y l.suc false / l.err = codigo)."""
    ant = g.get("lcf") or cf
    suc, err = (False, codigo) if FORMA_ERROR == "json_dc_err" else (True, 0)
    return {"c": _D(ids, 1, cf, cf, [], 0, dc=codigo, suc=suc, err=err), "p": _D(ids, 0, cf, ant, [], 0)}


def a_batchlock(g, args, cf):
    """batchLock [tipo, valor] = el boton del almacen 一键锁定 / 一键解锁. MEDIDO con el juego (ficha 101): con frutos en el almacen manda [21, 1] (21 =
    itemType de los frutos; 1 = bloquear) y la ventana de vender dice "total de los frutos (sin incluir los bloqueados)". Respuesta sin objetos (la
    forma grabada, o.o vacio) = no cambia nada. INVENTADO: bloquear = poner `tlock` 1 en cada fruto de la mochila con una operacion `f`
    [-5,"tlock",valor] (la misma gramatica que la de `twea`); el estado va en `bloqueo` de la seccion jardin y sale en `tlock` del openGarden."""
    if not (isinstance(args, list) and len(args) == 2 and all(_entero(a) for a in args)):
        raise Rechazo("argumentos de batchLock %r" % (args,), ERR_OPERACION_MALA)
    ids = _ids(g)
    u, cb = g["u"], ids["c_bolsa"]
    tipo, valor = args
    ops = []
    if tipo == 21 and valor in (0, 1):
        bloq = g.setdefault("bloqueo", {})
        for code in sorted(g["bolsa"]):
            if _twea(code) == 1 and bloq.get(code, 0) != valor:
                bloq[code] = valor
                ops.append(["i", u, cb, int(code), 1])
                ops.append(["f", u, cb, "itemcode", int(code), [-5, "tlock", valor]])
    return _marco(g, ids, cf, ops, "buy"), "batchLock %r: %d operaciones" % (args, len(ops))


def a_comprar_jardin(g, args, cf, fila):
    """buyItem pagado con sol: valida TODO y despues cobra (nivel, saldo)."""
    ids = _ids(g)
    u = g["u"]
    cant = args[2]
    precio = fila["buyPrice"] * cant
    if nivel_de(g["gexp"]) < fila["buyLevel"]:
        raise Rechazo("nivel %d < buyLevel %d" % (nivel_de(g["gexp"]), fila["buyLevel"]), ERR_NIVEL_COMPRA)
    if g["coin"] < precio:
        raise Rechazo("sol %d < precio %d" % (g["coin"], precio), ERR_SALDO)
    ops = []
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])
    g["coin"] -= precio
    ops.append(["e", u, ids["c_estado"], [-1, "coin", precio]])
    return _comprado(g, ids, u, cf, fila, cant, ops, precio, g["coin"], BUY_SOL)


def a_comprar_cash(g, args, cf, fila, saldo_cash, precio):
    """buyItem pagado con la moneda premium: el cobro YA se hizo en tienda (el que llama lo devuelve si esto falla). Sin h/e de coin."""
    ids = _ids(g)
    cant = args[2]
    if nivel_de(g["gexp"]) < fila["buyLevel"]:
        raise Rechazo("nivel %d < buyLevel %d" % (nivel_de(g["gexp"]), fila["buyLevel"]), ERR_NIVEL_COMPRA)
    return _comprado(g, ids, g["u"], cf, fila, cant, [], precio, saldo_cash, BUY_CASH)


def _comprado(g, ids, u, cf, fila, cant, ops, precio, restante, tipo):
    code = fila["code"]
    _bolsa_suma(g, ids, u, ops, code, cant, 0)
    ops.append(_aviso(u, 0, "updateBag", cf, {"i": fila["id"], "n": cant}))
    ops.append(_aviso(u, 0, "buyI", cf, {"i": fila["id"], "n": cant, "l": restante, "c": precio,
                                         "mp": {"pr": cant, "set": 0, "p": fila["id"]}, "t": tipo}))
    return _marco(g, ids, cf, ops, "buy"), "compra %d de %d (codigo %d): %d, queda %d" % (cant, fila["id"], code, precio, restante)


def a_plantar(g, args, cf):
    if not (isinstance(args, list) and len(args) == 2 and all(_entero(a) for a in args)):
        raise Rechazo("argumentos de plant %r" % (args,), ERR_OPERACION_MALA)
    ids = _ids(g)
    u = g["u"]
    k, p = _parcela_por(g, ids, args[0], "cid")
    code = args[1]
    fila = items()[1].get(code)
    if fila is None or fila["itemType"] != 20 or code in semillas_con_premio():
        raise Rechazo("codigo %r no es una semilla soportada" % code, ERR_NO_SEMILLA if fila is None or fila["itemType"] != 20 else ERR_GENERICO)
    if llave("JARDIN_TIERRA") and p["lsf"] > cf:         # ficha 120: plantSys f3, la parcela recien abierta / mejorada todavia no esta lista
        raise Rechazo("la tierra no esta lista", ERR_TIERRA_NO_LISTA)
    if p.get("planta"):
        raise Rechazo("parcela ocupada", ERR_OCUPADA)
    if g["bolsa"].get(str(code), 0) < 1:
        raise Rechazo("no tiene la semilla %d" % code, ERR_SIN_OBJETO)
    if p["tipo"] < fila["landGrade"]:
        raise Rechazo("tierra de tipo %d < landGrade %d" % (p["tipo"], fila["landGrade"]))
    ops = []
    _bolsa_resta(g, ids, u, ops, code, 1)
    cid = ids["eid_t"][k] + 1
    ops.append(["h", u, cid, _comp_planta(cid, p, cf)])
    p["planta"] = {"code": code, "t": cf, "adel": 0}
    p["clima"] = {"drought": 0, "dstart": 0, "roll": 0}
    p.pop("robos", None)
    est, sf, _m = etapa_de(p["planta"], cf)
    ops.append(["e", u, cid, [-5, "plantType", code, -5, "stage", est, -5, "sf", sf, -5, "plantTime", cf, -5, "plantlandLv", p["tipo"]]])
    ops.append(_aviso(u, 0, "pl", cf, {"mp": {"pr": 1, "set": 0, "p": fila["id"]}}))
    return _marco(g, ids, cf, ops, "plant"), "planta %d en la parcela %d, madura en %d cuadros" % (code, k, _tiempos(code)[1])


def a_usar(g, args, cf):
    if not (isinstance(args, list) and len(args) == 3 and all(_entero(a) for a in args)):
        raise Rechazo("argumentos de useItem %r" % (args,), ERR_OPERACION_MALA)
    ids = _ids(g)
    u = g["u"]
    code, cant, eid = args
    seg = abono(code)
    if seg is None:
        raise Rechazo("el objeto %d no es un abono soportado" % code, ERR_NO_USABLE)
    if not 1 <= cant <= MAX_CANTIDAD:
        raise Rechazo("cantidad %d" % cant, ERR_OPERACION_MALA)
    k, p = _parcela_por(g, ids, eid, "eid")
    pl = p.get("planta")
    if not pl:
        raise Rechazo("la parcela esta vacia", ERR_SIN_PLANTA)
    if etapa_de(pl, cf)[2]:
        raise Rechazo("la planta ya esta madura", ERR_ETAPA_USO)
    if g["bolsa"].get(str(code), 0) < cant:
        raise Rechazo("no tiene %d x %d" % (cant, code), _err_falta(g, code))
    ops = [_aviso(u, 0, "us", cf, {"mp": {"pr": cant, "set": 0, "p": code}})]
    _t1, t2, _t3 = _tiempos(pl["code"])
    nuevo = pl.get("adel", 0) + seg * FPS * cant
    if pl["t"] + t2 - nuevo <= cf:                       # el abono alcanza: madura AHORA (MEDIDO: sf = ahora + s3*30)
        nuevo = pl["t"] + t2 - cf
    pl["adel"] = nuevo
    est, sf, _m = etapa_de(pl, cf)
    cid = ids["eid_t"][k] + 1
    ops.append(["h", u, cid, _comp_planta(cid, p, cf)])   # MEDIDO: en useItem el `h` ya trae la planta con el efecto (stage 301)
    ops.append(["e", u, cid, [-5, "stage", est, -5, "sf", sf]])
    _bolsa_resta(g, ids, u, ops, code, cant)
    return _marco(g, ids, cf, ops, "use"), "abono %d x%d en la parcela %d: stage %d" % (code, cant, k, est)


def a_cosechar(g, args, cf):
    if not (isinstance(args, list) and len(args) == 1 and _entero(args[0])):
        raise Rechazo("argumentos de getFruit %r" % (args,), ERR_OPERACION_MALA)
    ids = _ids(g)
    u = g["u"]
    k, p = _parcela_por(g, ids, args[0], "cid")
    pl = p.get("planta")
    if not pl:
        raise Rechazo("la parcela esta vacia", ERR_SIN_PLANTA)
    est, _sf, maduro = etapa_de(pl, cf)
    if not maduro:
        raise Rechazo("todavia no crecio (stage %d)" % est, ERR_NO_MADURO)
    fila = items()[1][pl["code"]]
    n = fila["getCount"]
    capas = capas_de(p) if llave("JARDIN_SEQUIA") else 0
    robado = int((p.get("robos") or {}).get("stolen", 0)) if llave("JARDIN_VECINOS") else 0
    if robado:                                   # ficha 125: harvestSys f6 pc 9-18: primero se resta lo robado, despues las capas, y nunca menos de `retain`
        n = max(0, n - robado)
        n = cosecha_con_capas(n, capas) if capas else max(RETAIN, n)
    elif capas:
        n = cosecha_con_capas(n, capas)          # ficha 116: x0.8 por capa de sequia (harvestSys f6), floor y minimo `retain`
    if llave("JARDIN_TIERRA"):
        n = cosecha_con_tierra(n, p["tipo"])     # ficha 120: bono de la tierra (roja +10 %)
    fruto = fila["matureFruit"]
    e0 = ids["eid_t"][k]
    ops = []
    ops.append(["h", u, e0 + 1, _comp_planta(e0 + 1, p, cf)])
    ops.append(["e", u, e0 + 1, [-5, "stage", 0, -5, "sf", 0, -5, "plantType", 0, -5, "harvestCount", 0, -5, "plantTime", 0, -5, "plantlandLv", 0]])
    ops.append(["h", u, e0 + 2, _comp_robos(e0 + 2, p.get("robos") if llave("JARDIN_VECINOS") else None)])
    ops.append(["e", u, e0 + 2, [-5, "times", 0, -5, "thiefs", THIEFS_VACIO, -5, "stolen", 0]])
    ops.append(["h", u, e0 + 3, _comp_clima(e0 + 3, p.get("clima"))])
    ops.append(["e", u, e0 + 3, [-5, "roll", 0, -5, "drought", 0, -5, "dstart", 0, -5, "bugstat", 0, -5, "bstart", 0, -5, "grasstat", 0, -5, "gstart", 0]])
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])
    ops.append(["e", u, ids["c_estado"], [-9, "gexp", fila["getExp"], -9, "gpoint", fila["getPoint"]]])
    p["planta"] = None
    p.pop("robos", None)
    p["clima"] = {"drought": 0, "dstart": 0, "roll": 0}
    g["gexp"] += fila["getExp"]
    g["gpoint"] += fila["getPoint"]
    g["nivel"] = nivel_de(g["gexp"])
    _bolsa_suma(g, ids, u, ops, fruto, n, 1)
    ops.append(_aviso(u, e0, "hf", cf, {"i": fruto, "n": n, "p": fila["getPoint"], "param": fruto,
                                        "mp": {"pr": n, "set": 0, "p": fruto}, "e": fila["getExp"]}))
    return _marco(g, ids, cf, ops, "fruit"), "cosecha parcela %d: %d x %d (%d capas de sequia%s), +%d exp, +%d punto" % (
        k, n, fruto, capas, (", %d robados" % robado) if robado else "", fila["getExp"], fila["getPoint"])


def a_vender(g, args, cf):
    if not (isinstance(args, list) and len(args) == 1 and isinstance(args[0], list) and 1 <= len(args[0]) <= 50):
        raise Rechazo("argumentos de sellItem %r" % (args,), ERR_VENTA_PARAM)
    ids = _ids(g)
    u = g["u"]
    lote, total, vistos = [], 0, set()
    for it in args[0]:
        if not (isinstance(it, dict) and _entero(it.get("id")) and _entero(it.get("num")) and 1 <= it["num"] <= 100000):
            raise Rechazo("elemento %r" % (it,), ERR_VENTA_PARAM)
        fila = items()[1].get(it["id"])
        if fila is None or fila["itemType"] != 21 or fila["sellPrice"] <= 0 or fila["sellType"] != BUY_SOL:
            raise Rechazo("el objeto %r no se vende" % (it["id"],), ERR_NO_VENDIBLE)
        if it["id"] in vistos:
            raise Rechazo("objeto repetido %d" % it["id"], ERR_VENTA_PARAM)
        vistos.add(it["id"])
        if g["bolsa"].get(str(it["id"]), 0) < it["num"]:
            raise Rechazo("no tiene %d x %d" % (it["num"], it["id"]), _err_falta(g, it["id"]))
        if g.get("bloqueo", {}).get(str(it["id"]), 0):
            raise Rechazo("el objeto %d esta bloqueado" % it["id"], ERR_VENTA_BLOQUEADO)
        lote.append((it["id"], it["num"]))
        total += fila["sellPrice"] * it["num"]
    ops = []
    for code, n in lote:
        _bolsa_resta(g, ids, u, ops, code, n)
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])
    g["coin"] += total
    ops.append(["e", u, ids["c_estado"], [-9, "coin", total]])
    ops.append(_aviso(u, 0, "sl", cf, {"mp": {"pr": total, "set": 0, "p": 0}, "w": u}))
    return _marco(g, ids, cf, ops, "sell"), "venta de %d objeto(s): +%d de sol" % (len(lote), total)


# ---------------------------------------------------------------- regar, pala, maleza y bichos (ficha 116; gardenWorkSys e90bfb12 f3, f4, f6, f8, f9)
def _parcela_de_trabajo(g, args, cf, nombre):
    """Lo comun de doWater / doDeGrass / doDebug / pullout (gardenWorkSys f6): [eid], la entidad existe (25020) y la tierra esta lista (lsf <= cuadro, 25032)."""
    if not (isinstance(args, list) and len(args) == 1 and _entero(args[0])):
        raise Rechazo("argumentos de %s %r" % (nombre, args), ERR_OPERACION_MALA)
    ids = _ids(g)
    for k, e0 in enumerate(ids["eid_t"]):
        if e0 == args[0]:
            p = g["parcelas"][k]
            if p["lsf"] > cf:
                raise Rechazo("la tierra no esta lista", ERR_TIERRA_NO_LISTA)
            return ids, k, p
    raise Rechazo("parcela eid %r inexistente" % (args[0],), ERR_NO_ENTIDAD)


def a_regar(g, args, cf):
    """doWater [eid]. Lua: _doRemoveDisaster con 'drought'/'dstart': sin sequia (drought <= 0 o dstart <= 0) -> NO_DISASTER 25026; si el cuadro >= dstart + 3600 s
    (isToolateForFix) SOLO dstart = 0 y la capa se queda; si no, drought -1 y dstart 0. En los dos casos exito y +20 de exp (addExp de la sequia), 0 puntos."""
    ids, k, p = _parcela_de_trabajo(g, args, cf, "doWater")
    u = g["u"]
    cl = p.setdefault("clima", {"drought": 0, "dstart": 0, "roll": 0})
    cid = ids["eid_t"][k] + 3
    cur = _cli_de_cf(cf)
    if not (cl["drought"] > 0 and cl["dstart"] > 0):
        raise Rechazo("la parcela no tiene sequia", ERR_NO_DESASTRE)
    ops = [["h", u, cid, _comp_clima(cid, cl)]]
    if cur >= cl["dstart"] + PERIODO:             # demasiado tarde: la capa queda
        ops.append(["e", u, cid, [-5, "dstart", 0]])
        cl["dstart"] = 0
        tarde = True
    else:
        ops.append(["e", u, cid, [-1, "drought", 1, -5, "dstart", 0]])
        cl["drought"] -= 1
        cl["dstart"] = 0
        tarde = False
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])
    ops.append(["e", u, ids["c_estado"], [-9, "gexp", EXP_REGAR, -9, "gpoint", 0]])
    g["gexp"] += EXP_REGAR
    g["nivel"] = nivel_de(g["gexp"])
    # el cliente sigue su weaSys: si habia tiradas atrasadas (estaba con todas las capas) caen ahora en UN lote
    avanzar_sequia_parcela(p, cur, lote=True)
    return _marco(g, ids, cf, ops, "water"), "riego parcela %d (%s): capas %d, +%d exp" % (k, "tarde" if tarde else "a tiempo", cl["drought"], EXP_REGAR)


def a_sin_desastre(g, args, cf):
    """doDeGrass / doDebug: la maleza y los bichos tienen peso 0 en la tabla: nunca aparecen, asi que el Lua contesta NO_DISASTER (25026) si la parcela existe."""
    _parcela_de_trabajo(g, args, cf, "doDeGrass/doDebug")
    raise Rechazo("la parcela no tiene ese desastre", ERR_NO_DESASTRE)


def a_pala(g, args, cf):
    """pullout [eid] = _doPullout: con planta, tileSys.resetTile (planta, robos y clima a cero, las mismas operaciones que la cosecha); sin planta, exito sin hacer nada."""
    ids, k, p = _parcela_de_trabajo(g, args, cf, "pullout")
    u = g["u"]
    pl = p.get("planta")
    ops = []
    if pl:
        e0 = ids["eid_t"][k]
        ops.append(["h", u, e0 + 1, _comp_planta(e0 + 1, p, cf)])
        ops.append(["e", u, e0 + 1, [-5, "stage", 0, -5, "sf", 0, -5, "plantType", 0, -5, "harvestCount", 0, -5, "plantTime", 0, -5, "plantlandLv", 0]])
        ops.append(["h", u, e0 + 2, _comp_robos(e0 + 2, p.get("robos") if llave("JARDIN_VECINOS") else None)])
        ops.append(["e", u, e0 + 2, [-5, "times", 0, -5, "thiefs", THIEFS_VACIO, -5, "stolen", 0]])
        ops.append(["h", u, e0 + 3, _comp_clima(e0 + 3, p.get("clima"))])
        ops.append(["e", u, e0 + 3, [-5, "roll", 0, -5, "drought", 0, -5, "dstart", 0, -5, "bugstat", 0, -5, "bstart", 0, -5, "grasstat", 0, -5, "gstart", 0]])
        p["planta"] = None
        p.pop("robos", None)
        p["clima"] = {"drought": 0, "dstart": 0, "roll": 0}
    return _marco(g, ids, cf, ops, "pull"), "pala en la parcela %d: %s" % (k, "arrancada" if pl else "estaba vacia")


# ---------------------------------------------------------------- mejorar la tierra y abrir una parcela (ficha 120)
# LEIDO (Lua, _fuera_git/lua/dis): `tileSys` b012fa2a f16 doUpLand (entrada {eid, cid, buyType}), f13 isUpLevelAble, f15 getUpgradeCost, f22 updateLandPoint;
# f10 unlockNextTile, f9 isUnlockAble, f11 doNewTile, f6 getExpandTime; `gardenComSys` 42ac6f66 f5 utAddLandPoint y f8 utCostCoin; `notifySys` af56b8ed f9 (up) y f19 (nland);
# `syncWorld` fbf1066a f1..f4, f8..f10 (letras a b c d o p q) y `syncWorldMem` b8bd9a8e f1 (como las APLICA el cliente: a [wid,tag,eid], b [wid,comp],
# c [wid,eid,tag,cid], d [wid,eid,clave,eid hijo], p [wid,n]). MEDIDO con el juego (ficha 120): `upLand [eid, cid, buyType]` y `unlockLand [""]`.
MAX_TIERRA = 8                       # lubanEnums Garden.EGardenLandType.maxLand: el destino tiene que ser MENOR
CANT_UPGRADE = 99999999              # tileSysMt.CANT_UPGRADE
TIPO_COMUN = 1                       # landLevelEnum.NORMAL_LAND
CIDS_PARCELA = 4                     # allocId(4): la entidad + sus 3 componentes (planta 1002, robos 1006, clima 1008)
FLAGS_TIERRA = {"up": 5, "nland": 21}    # LOG|CLIENT y LOG|CLIENT|GMISSION (notifySys f9 y f19, LEIDO)


def _filas(nombre):
    t = tabla(nombre) or []
    return list(t.values()) if isinstance(t, dict) else t


def _landtype(tipo):
    return next((r for r in _filas("landtype") if r["landType"] == tipo), None)


def _landcfg(id_tierra):
    return next((r for r in _filas("landconfig") if r["id"] == id_tierra), None)


def _tierra_lista_para(g, ids, args):
    """check(eid, TILE, cid, PLANTA) del Lua: el eid tiene que ser una parcela y el cid su componente 1002; si no, MISMATCH_ECID."""
    if not (isinstance(args, list) and len(args) == 3 and all(_entero(a) for a in args)):
        raise Rechazo("argumentos de upLand %r" % (args,), ERR_OPERACION_MALA)
    eid, cid, _pago = args
    for k, e0 in enumerate(ids["eid_t"]):
        if e0 == eid and cid == e0 + 1:
            return k, g["parcelas"][k]
    raise Rechazo("upLand: eid %r / cid %r no son una parcela y su planta" % (eid, cid), ERR_ECID)


def a_mejorar(g, args, cf):
    """upLand [eid, cid, buyType] (tileSys f16). Sube la tierra UN escalon (landLv + 1). Con sol (buyType 3: solo comun -> roja, `rUseSumCoin`); con
    diamantes (buyType 1) el Lua compra el objeto 11006861 por paysys: NO soportado, se rechaza con BUY_FIAL (el codigo que el Lua da cuando paysys falla)."""
    ids = _ids(g)
    k, p = _tierra_lista_para(g, ids, args)
    pago = args[2]
    u = g["u"]
    id_tierra = k + 1                                   # getIdByTile: la posicion de la parcela entre las parcelas
    origen = p["tipo"]
    destino = origen + 1                                # f13: dest - origen == 1 (siempre: no hay UPLV_CANT_JUMP)
    if p["lsf"] > cf:                                   # isUnderExpansion
        raise Rechazo("la parcela esta en obra", ERR_TIERRA_EN_OBRA)
    if MAX_TIERRA <= destino:
        raise Rechazo("no hay tierra de nivel %d" % destino, ERR_NIVEL_NO_EXISTE)
    fila_land, fila_tipo = _landcfg(id_tierra), _landtype(destino)
    if fila_land is None:
        raise Rechazo("la parcela %d no esta en landconfig" % id_tierra, ERR_NO_TIERRA)
    if fila_tipo is None or fila_land.get(fila_tipo["useLevelName"]) is None:
        raise Rechazo("tipo de tierra %d sin configuracion" % destino, ERR_TIERRA_MALA)
    if nivel_de(g["gexp"]) < fila_land[fila_tipo["useLevelName"]]:
        raise Rechazo("nivel %d < %d" % (nivel_de(g["gexp"]), fila_land[fila_tipo["useLevelName"]]), ERR_NIVEL_TIERRA)
    if pago not in fila_tipo["buyType"]:
        raise Rechazo("la tierra %d no se paga con %d" % (destino, pago), ERR_PAGO)
    ops = []
    if pago == BUY_SOL:
        nombre = fila_tipo["useSumCoinName"]
        costo = fila_land.get(nombre) if nombre else CANT_UPGRADE
        costo = CANT_UPGRADE if costo is None else costo
        if g["coin"] < costo:
            raise Rechazo("sol %d < costo %d" % (g["coin"], costo), ERR_SALDO)
        ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])          # utCostCoin: updateDirect(1007, DECZ, coin, costo)
        ops.append(["e", u, ids["c_estado"], [-1, "coin", costo]])
        g["coin"] -= costo
    else:
        raise Rechazo("pago con diamantes (objeto 11006861 por paysys): no soportado", ERR_COMPRA)
    cid = ids["eid_t"][k] + 1
    ops.append(["h", u, cid, _comp_planta(cid, p, cf)])                      # updateDirect(1002, SET landLv, SET lsf)
    ops.append(["e", u, cid, [-5, "landLv", destino, -5, "lsf", cf]])
    p["tipo"] = destino
    p["lsf"] = cf                                                            # sin espera (f16: lsf = cuadro actual)
    # si hay planta sin madurar el Lua encola UPDATE_GROW_TIME (growSys): con la tierra roja timeDown es 0, asi que `sf` no cambia (HIPOTESIS, no medido)
    ops.append(["n", u, ids["eid_t"][k], 0, "up", cf, {"w": u, "l": destino}, FLAGS_TIERRA["up"]])
    delta = fila_tipo["grade"] - (_landtype(origen) or {}).get("grade", 0)   # updateLandPoint f22: grade[destino] - grade[origen]
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])              # utAddLandPoint: updateDirect(1007, INCZ, landPoint, delta)
    ops.append(["e", u, ids["c_estado"], [-9, "landPoint", delta]])
    g["landpoint"] += delta
    return _marco(g, ids, cf, ops, "land"), "tierra de la parcela %d: %d -> %d (%d de sol, +%d de landPoint)" % (k, origen, destino, costo, delta)


def a_desbloquear(g, args, cf):
    """unlockLand [""] (tileSys f10 + f9 + f11). El pedido NO dice cual parcela: es la siguiente (id = cantidad + 1: isUnlockAble exige que la anterior exista y esta no).
    Cuesta `nUseSumCoin` de sol, pide el nivel `useLevel` de landconfig, la parcela queda en obra `addLandTime` segundos (lsf)."""
    if not (isinstance(args, list) and len(args) == 1 and isinstance(args[0], str)):
        raise Rechazo("argumentos de unlockLand %r" % (args,), ERR_OPERACION_MALA)
    ids = _ids(g)
    u = g["u"]
    k = len(g["parcelas"])
    id_tierra = k + 1
    fila = _landcfg(id_tierra)
    if fila is None:
        raise Rechazo("no hay parcela %d en landconfig" % id_tierra, ERR_NO_TIERRA)            # isUnlockAble f9 (NO_SUCN_LAND) va antes que NOMORE_TILE
    if nivel_de(g["gexp"]) < fila["useLevel"]:
        raise Rechazo("nivel %d < %d" % (nivel_de(g["gexp"]), fila["useLevel"]), ERR_NIVEL_TIERRA)
    costo = fila.get("nUseSumCoin")
    if costo is None or costo >= CANT_UPGRADE:
        raise Rechazo("la parcela %d no se puede abrir" % id_tierra, ERR_NO_MAS_PARCELAS)
    if g["coin"] < costo:
        raise Rechazo("sol %d < costo %d" % (g["coin"], costo), ERR_SALDO)
    ops = [["h", u, ids["c_estado"], _comp_estado(g, ids)], ["e", u, ids["c_estado"], [-1, "coin", costo]]]   # utCostCoin
    g["coin"] -= costo
    e0 = ids["db"] + 1                                                       # allocId(4) devuelve base + 1
    assert e0 == ids["B"] + 1028 + 4 * k
    lsf = cf + fila["addLandTime"] * FRAME_POR_S                             # getExpandTime: secToFrame(addLandTime) (x30: HIPOTESIS)
    rnd = random.Random(g["u"] * 104729 + id_tierra * 7919 + cf)
    parcela = {"id_tierra": id_tierra, "tipo": TIPO_COMUN, "seed": rnd.randrange(1, 1 << 32), "lsf": lsf, "planta": None,
               "clima": {"drought": 0, "dstart": 0, "roll": 0}}               # `seed` = math.random(1, 2^32-1) del Lua: lo pone el servidor (INVENTADO)
    planta = _comp_planta(e0 + 1, parcela, cf)
    ops += [["p", u, CIDS_PARCELA],                                          # allocId(4)
            ["a", u, 3002, e0],                                              # newEntityWithId(tileMt, e0)
            ["b", u, planta], ["c", u, e0, 1002, e0 + 1],                    # cbindWithId: componente nuevo + atarlo, en este orden (world f14)
            ["b", u, _comp_robos(e0 + 2)], ["c", u, e0, 1006, e0 + 2],
            ["b", u, _comp_clima(e0 + 3, parcela["clima"])], ["c", u, e0, 1008, e0 + 3],
            ["d", u, ids["raiz"], "tiles", e0]]                              # setHasMany(jardin, 'tiles', parcela)
    g["parcelas"].append(parcela)
    delta = (_landtype(TIPO_COMUN) or {}).get("grade", 0)                    # updateLandPoint f22 (parcela nueva: grade del tipo comun)
    ops.append(["h", u, ids["c_estado"], _comp_estado(g, ids)])
    ops.append(["e", u, ids["c_estado"], [-9, "landPoint", delta]])
    g["landpoint"] += delta
    ops.append(["h", u, e0 + 1, planta])                                     # f10: updateDirect(1002, SET, lsf, cuadro + addLandTime) otra vez
    ops.append(["e", u, e0 + 1, [-5, "lsf", lsf]])
    ops.append(["n", u, 0, 0, "nland", cf, {"mp": {"p": 0, "set": 0, "pr": 1}}, FLAGS_TIERRA["nland"]])
    marco = _marco(g, _ids(g), cf, ops, "unlock")                            # dbId nuevo (el cliente lo toma de `c.db`)
    return marco, "parcela %d abierta (%d de sol), lista en %d cuadros" % (id_tierra, costo, lsf - cf)


METODOS = {"gardenSys.plant": a_plantar, "gardenSys.useItem": a_usar, "gardenSys.getFruit": a_cosechar,
           "gardenSys.sellItem": a_vender, "gardenSys.batchLock": a_batchlock}


def actuar(con, usn, nombre, args):
    """Ejecuta un pedido del ciclo (comprar, plantar, usar, cosechar, vender, batchLock) con el candado de cuenta.py.
    Devuelve ('ok', respuesta, nota) o ('error', motivo, codigo de error del cliente)."""
    ahora = int(RELOJ())
    cf = _frame(ahora)

    def hacer(fn, *extra):
        def f(c):
            _preparar(c, usn, ahora)
            try:
                resp, nota = fn(c, args, cf, *extra)
            except Rechazo as e:
                return ("error", str(e), e.codigo)
            return ("ok", resp, nota)
        return _cta.cambiar_seccion(usn, "jardin", f)

    try:
        if nombre == "gardenSys.buyItem":
            if not (isinstance(args, list) and len(args) == 3 and all(_entero(a) for a in args)):
                return ("error", "argumentos de buyItem %r" % (args,), ERR_OPERACION_MALA)
            fila = items()[0].get(args[0])
            cant = args[2]
            if fila is not None and fila["itemType"] in (10, 20) and fila["buyPrice"] > 0 and fila["buyType"] != args[1]:
                return ("error", "buyItem %r: el objeto se paga de otra forma (%r)" % (args, fila["buyType"]), ERR_PAGO)
            if fila is None or fila["itemType"] not in (10, 20):
                return ("error", "buyItem %r: no es un objeto del jardin" % (args,), ERR_NO_ES_DEL_JARDIN)
            if fila["buyPrice"] <= 0 or fila["buyType"] not in (BUY_SOL, BUY_CASH) or not 1 <= cant <= MAX_CANTIDAD:
                return ("error", "buyItem %r no se vende asi" % (args,), ERR_COMPRA)
            if fila["itemType"] == 20 and fila["code"] in semillas_con_premio():
                return ("error", "semilla %d con premio de primera cosecha: no soportada" % fila["code"], ERR_GENERICO)
            if fila["itemType"] == 10 and abono(fila["code"]) is None:
                return ("error", "objeto %d: su efecto no esta soportado" % fila["code"], ERR_GENERICO)
            if fila["buyType"] == BUY_SOL:
                return hacer(a_comprar_jardin, fila)
            return _comprar_con_cash(con, usn, args, fila, hacer)
        fn = (METODOS.get(nombre) or (METODOS_SEQUIA.get(nombre) if llave("JARDIN_SEQUIA") else None)
              or (METODOS_TIERRA.get(nombre) if llave("JARDIN_TIERRA") else None))
        return hacer(fn) if fn else ("error", "metodo %s" % nombre, ERR_OPERACION_MALA)
    except Exception as e:                       # noqa: BLE001  (mejor un cartel que un servidor caido)
        anotar("   ⛔ jardin.actuar %s: %r" % (nombre, e))
        return ("error", "excepcion %r" % (e,), ERR_EXCEPCION)


def precio_cash(code):
    """(moneda de tienda.py, precio por unidad) de un objeto del jardin pagado con la moneda premium. MEDIDO con el juego (ficha 100):
    la tienda del jardin muestra 40 para el abono 92000003 (la tabla garden_tbgardeniteminfo dice 240: NO es el precio); 40 es el `n` de
    ese objeto en datos/catalogo.json (el catalogo de la tienda principal). Por eso se cobra por catalogo, como FF50/FF2A."""
    import catalogo
    if not catalogo.cargado():
        return None
    f = catalogo.ficha(code)
    if f is None or f.get("n") is None or not catalogo.se_vende(code):
        return None
    return catalogo.moneda(code), int(f["n"])


def _comprar_con_cash(con, usn, args, fila, hacer):
    """Moneda premium: 0) se VALIDA todo lo que se puede validar sin cobrar (precio del catalogo, nivel), 1) se cobra en tienda (candado
    propio; falla si no alcanza), 2) se aplica al jardin, 3) si 2 rechaza O revienta se devuelve lo cobrado. Nunca dos candados a la vez.
    Ventana que queda (HIPOTESIS, no medida): que el proceso muera ENTRE 1 y 2; no hay forma de cerrarla con dos archivos de estado distintos."""
    import tienda
    pc = precio_cash(fila["code"])
    if pc is None or pc[0] not in ("cash", "g"):
        return ("error", "objeto %d: sin precio en el catalogo" % fila["code"], ERR_PRECIO)
    campo = "diamantes" if pc[0] == "cash" else "g"
    precio = pc[1] * args[2]
    g = estado_de(usn)                                         # 0) validar ANTES de cobrar (lo mismo que mira a_comprar_cash)
    if nivel_de(g["gexp"]) < fila["buyLevel"]:
        return ("error", "nivel %d < buyLevel %d" % (nivel_de(g["gexp"]), fila["buyLevel"]), ERR_NIVEL_COMPRA)

    def cobrar(b):
        if b.get(campo, 0) < precio:
            return None
        b[campo] = b.get(campo, 0) - precio
        return b[campo]
    quedan = tienda._con_bolsa(con, cobrar)
    if quedan is None:
        return ("error", "%s insuficiente para %d" % (campo, precio), ERR_SALDO)

    def devolver():
        tienda._con_bolsa(con, lambda b: b.__setitem__(campo, b.get(campo, 0) + precio))
    try:
        r = hacer(a_comprar_cash, fila, quedan, precio)
    except BaseException:                                      # una excepcion tambien devuelve lo cobrado
        devolver()
        raise
    if r[0] != "ok":
        devolver()
    else:
        con.saldo_a_refrescar = campo                          # ficha 131: _accion lo manda DESPUES de contestar el FF26F (tienda.refrescar_saldos)
    return r


def _accion(con, seq, cuerpo, usn, nick, nombre, args):
    """Un pedido del ciclo: respuesta en la forma grabada, o el texto de error LEIDO (el cliente lo muestra en un cartel)."""
    r = actuar(con, usn, nombre, args)
    if r[0] == "ok":
        n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, r[1])
        anotar("   S2C FF26F %s de %s: %s (%d B de JSON, %d operaciones)" % (nombre, nick, r[2], n, len(r[1]["c"]["o"]["o"])))
        pago = getattr(con, "saldo_a_refrescar", None)         # ficha 131: pagado con la moneda premium (diamantes o G de tienda.py)
        if pago:
            con.saldo_a_refrescar = None
            import tienda
            tienda.refrescar_saldos(con, g=pago == "g", diamantes=pago == "diamantes")
        return True
    codigo = r[2] if len(r) > 2 else ERR_GENERICO
    if FORMA_ERROR == "texto":
        con.mandar_interno(0x26F, seq, sobre(con, "26F", cuerpo, nombre, str(codigo)))
        anotar("   S2C FF26F %s de %s RECHAZADO (%s): texto de error %s" % (nombre, nick, r[1], codigo))
        return True
    g = estado_de(usn)                                           # solo lectura: el rechazo no cambia nada
    obj = marco_error(g, _ids(g), _frame(int(RELOJ())), codigo)
    n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, obj)
    anotar("   S2C FF26F %s de %s RECHAZADO (%s): {c,p} con dc %s (%d B)" % (nombre, nick, r[1], codigo, n))
    return True


# ---------------------------------------------------------------- visitar el jardin de otro (ficha 120)
# MEDIDO con el juego (ficha 120, copia 2 -> copia 3, ficha del amigo -> boton "Granja"): `gardenSys.visit ["<apodo del destino>"]` (UN elemento, texto; 12 B de JSON con un
# apodo de 8 letras). LEIDO (exe): el callback `0x00caa5f0` valida con `0x00c8ff10` y pasa la respuesta a `0x00c8ab80`, que lee las claves `u` (entero), `n` (texto) y `w`
# (objeto) y llama a `0x00c89350(this, u, w)`: el MISMO manejador de openGarden, que lee `w["fs"]` (cadenas `u`, `n`, `w`, `fs` comprobadas en 0x036227ec, 0x036227e8,
# 0x036241f4, 0x036481c4). Por eso la respuesta es {"u": usn del dueno, "n": apodo, "w": {"fs": ...}} con el fs de siempre (el del dueno).
NOMBRE_VISIT = "gardenSys.visit"
NO_SOPORTADOS_VISITANDO = ("gardenSys.doSteal", "gardenSys.helpDoWater")     # robar y ayudar: ficha aparte; aca solo un rechazo


def _cuenta_por_apodo(apodo):
    """La cuenta local (seccion `cuenta`) con ese apodo, o None (como social._por_nick: la primera)."""
    return next((c for c in _cta.todas_planas() if c.get("nick") == apodo), None)


def _contestar_texto(con, seq, cuerpo, nombre, codigo):
    """El rechazo en TEXTO (`25028`): el callback de visit espera u/n/w, asi que un `{c,p}` sin esas claves lo leeria como vacio; el texto numerico lo muestra el
    validador 0x00c8ff10 (cartel) y el callback no sigue (ficha 101: asi salia el cartel, MEDIDO)."""
    con.mandar_interno(0x26F, seq, sobre(con, "26F", cuerpo, nombre, str(codigo)))


def _visitar(con, seq, cuerpo, usn, nick, nombre, args):
    """visit [apodo]: el jardin de OTRA cuenta local, solo para mirar (INVENTADO: sin exigir amistad). El visitante no cambia nada: sus pedidos dentro de ese jardin
    traen ids del otro (B = usn * 100000) y los atiende su propio jardin como "no existe" (25012 / 25020 / 25021, sin tocar nada)."""
    if not (isinstance(args, list) and len(args) == 1 and isinstance(args[0], str) and args[0]):
        _contestar_texto(con, seq, cuerpo, nombre, ERR_OPERACION_MALA)
        anotar("   S2C FF26F gardenSys.visit de %s RECHAZADO (argumentos %s): texto %d" % (nick, _json(args)[:60], ERR_OPERACION_MALA))
        return True
    destino = _cuenta_por_apodo(args[0])
    if destino is None or destino.get("usn") is None:
        _contestar_texto(con, seq, cuerpo, nombre, ERR_SIN_RELACION)
        anotar("   S2C FF26F gardenSys.visit de %s RECHAZADO (no hay una cuenta con ese apodo): texto %d" % (nick, ERR_SIN_RELACION))
        return True
    dusn = destino["usn"]
    g = estado_de(dusn)
    obj = {"u": int(dusn), "n": destino.get("nick") or "", "w": armar_fs(g)}
    n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, obj)
    anotar("   S2C FF26F gardenSys.visit de %s al jardin de %s (usn %d): {u,n,w:{fs}} %d B, %d parcelas, frame %d (INVENTADO: sin exigir amistad; solo mirar)"
           % (nick, obj["n"], dusn, n, len(g["parcelas"]), obj["w"]["fs"]["frame"]))
    return True


def _rechazo_visitante(con, seq, cuerpo, usn, nick, nombre, args):
    """doSteal / helpDoWater: no estan programados (ficha aparte). Se contestan con el `{c,p}` de siempre y OP_NOT_SUPPORT (25013, "operacion no admitida"); no se toca nada."""
    g = estado_de(usn)
    obj = marco_error(g, _ids(g), _frame(int(RELOJ())), ERR_OPERACION)
    n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, obj)
    anotar("   S2C FF26F %s %s de %s RECHAZADO (robar y ayudar no estan programados): {c,p} con dc %d (%d B)" % (nombre, _json(args)[:60], nick, ERR_OPERACION, n))
    return True


# ---------------------------------------------------------------- ayudar a regar y robar en el jardin de otro (ficha 125, llave JARDIN_VECINOS)
# MEDIDO con el juego (ficha 125, copia 2 -> jardin de la copia 3): el cliente manda `gardenSys.helpDoWater [usn DEL DUENO, eid de la parcela]` (77 B, herramienta 浇水 sobre la planta
# con la gota) y `gardenSys.doSteal [usn DEL DUENO, eid]` (81 B con el rechazo de antes; herramienta 收获 sobre una planta madura).
# LEIDO (exe): los callbacks de doSteal (vtable 0x03648c78) y helpDoWater (0x03648bd0) llaman a 0x00c8e880: valida con 0x00c8ff10 (texto que no empieza con { o [ = cartel), recorre
# las CLAVES del objeto que hay bajo la clave "m" de la respuesta (cadena 0x0361a7b0), y por cada una llama a 0x00c47f80(usn = la clave, o 1 si la clave es "yes"/"force"; JSON del
# valor) = gardenMgr.netSync(usn, {c,p}) (gimport 0598ddb8 f18: aplica el {c,p} al mundo de ESE usn). Por eso la respuesta es {"m": {"<usn del dueno>": {c,p}, "<usn del visitante>":
# {c,p}}}: el diff del mundo del dueno (parcela: robos o sequia) y el del mundo del visitante (mochila / exp). (MEDIDO: sin el "m" el cliente no aplicaba nada: la gota seguia.)
# Un {c,p} suelto (lo que contestaba la ficha 120) no tiene "m": el cliente no hace nada.
# LEIDO (Lua): stealSys 7733bd1a f3 (isStealAble: 25029, 25008, 25030, 25031, 25060), f4 (cuanto: base = max(retain, getCount - stolen); si base <= retain, 25033; pct = math.random(10, 15);
# robo = floor(base x pct / 100) dejando al menos retain), f5 (mundo del dueno: times +1, stolen +robo, thiefs ..",<usn>"; aviso bs), f6 (mundo del ladron: la fruta a la mochila; aviso bt);
# gardenWorkSys e90bfb12 f6 (ayudar = el mismo doDisasterOp con h = true: 25020, 25032, 25047, 25026), f5 (isHelpAble: cocnt del dia >= natHazHelpCount -> 25047); interactionSys 3d1f0aa6 f4
# (mundo del que ayuda: cof = cuadro, cocnt +1 si es el mismo dia o = 1, y la exp del riego); harvestSys 468d0bf9 f6 (la cosecha del dueno resta lo robado antes de las capas).
NOMBRE_ROBAR, NOMBRE_AYUDAR, NOMBRE_AMIGOS = "gardenSys.doSteal", "gardenSys.helpDoWater", "gardenSys.getAllFriends"
ERR_ROBAR_A_SI = 25029               # CANT_STEAL_SELF
ERR_ROBO_MUCHO = 25030               # STEAL_TOO_MUCH (times >= maxStealTimes)
ERR_ROBO_DUP = 25031                 # STEAL_DUP (el usn del ladron ya esta en `thiefs`)
ERR_DEJA_UN_POCO = 25033             # NOMORE_NOMORE
ERR_AYUDA_TOPE = 25047               # HELP_TOOMUCH
ERR_PROTECCION = 25060               # STEAL_PROTECT (sin texto en el mapa del cliente 0x00c862b0, que llega a 25057)
FLAGS_N.update({"bt": 23, "bs": 22, "hp": 6})     # notifySys af56b8ed f6 (bt: GARLOG|LOG|GMISSION|CLIENT), f5 (bs: sin CLIENT), f12 (hp: GARLOG|LOG)
INDICE_EXTRA.update({"steal": 0, "thief": 0, "help": 0, "helper": 0})   # INVENTADO: len(operaciones) + 0, como regar
AZAR_ROBO = random.randint           # math.random(takeFruitMin, takeFruitMax) del Lua: las pruebas lo cambian


def _cfg(clave, defecto):
    v = (tabla("commconfig") or {}).get(clave, defecto)
    return v if _entero(v) else defecto


def _dia_de(frame):
    """El dia (fecha local) de un cuadro: frameInSameDay (ecsUtility f5) compara getDayTime(frameToUnix(frame)); el cuadro del servidor sale del reloj."""
    return datetime.date.fromtimestamp(T_REF + (frame - FRAME_REF) / float(FRAME_POR_S))


def _mismo_dia(cf, otro):
    if not otro or otro <= 0:
        return False
    try:
        return _dia_de(cf) == _dia_de(otro)
    except (OverflowError, OSError, ValueError):
        return False


def _robos_de(p):
    r = p.get("robos") or {}
    return {"times": int(r.get("times", 0)), "stolen": int(r.get("stolen", 0)), "thiefs": str(r.get("thiefs", THIEFS_VACIO))}


def _parcela_ajena(go, eid, codigo):
    ids = _ids(go)
    for k, e0 in enumerate(ids["eid_t"]):
        if e0 == eid:
            return ids, k, go["parcelas"][k]
    raise Rechazo("parcela eid %r inexistente en ese jardin" % (eid,), codigo)


def _nick_cuenta(acc):
    return ((acc or {}).get("cuenta") or {}).get("nick") or ""


def _b64(txt):
    import base64
    return base64.b64encode(txt.encode("utf-8")).decode("ascii")


MAX_REGISTRO = 50


def _registrar(g, nombre, datos, eid, cf):
    """Una fila del registro del jardin (getGardenLog) del DUENO: {id, name, data, tm}. MEDIDO en la grabacion del oficial (conexion con 2 filas, solo la FORMA): `name` = el nombre del aviso
    (2 letras: hf, sl), `data` = texto JSON {"d": los datos del aviso, "c": 0, "e": el eid del aviso (la parcela; 0 si no hay)}, `id` = 1, 2, ... y `tm` = un CUADRO (el cliente lo escribe
    como fecha con 30 por segundo desde 2024-06-01: con segundos de unix salia abril de 2026). Los datos de bs / hp salen de notifySys af56b8ed f5 y f12."""
    reg = g.setdefault("registro", [])
    nuevo = (reg[-1]["id"] + 1) if reg else 1
    reg.append({"id": nuevo, "name": nombre, "data": _json({"d": datos, "c": 0, "e": eid}), "tm": int(cf)})
    del reg[:-MAX_REGISTRO]


def filas_registro(g):
    """Las filas del registro, las mas nuevas primero (HIPOTESIS el orden)."""
    return [dict(f) for f in reversed(g.get("registro") or [])]


def a_ayudar(go, gv, acc_o, acc_v, eid, cf):
    """helpDoWater: regar la sequia de OTRO. Devuelve ({usn: {c,p}}, nota). Valida TODO antes de tocar nada."""
    dusn, usn = go["u"], gv["u"]
    ids_o, k, p = _parcela_ajena(go, eid, ERR_NO_ENTIDAD)
    if p["lsf"] > cf:
        raise Rechazo("la tierra no esta lista", ERR_TIERRA_NO_LISTA)
    hoy = int(gv.get("cocnt", 0)) if _mismo_dia(cf, gv.get("cof", 0)) else 0
    if hoy >= _cfg("natHazHelpCount", 10):
        raise Rechazo("ya ayudo %d veces hoy" % hoy, ERR_AYUDA_TOPE)
    cl = p.setdefault("clima", {"drought": 0, "dstart": 0, "roll": 0})
    if not (cl["drought"] > 0 and cl["dstart"] > 0):
        raise Rechazo("la parcela no tiene sequia", ERR_NO_DESASTRE)
    cur = _cli_de_cf(cf)
    cid = ids_o["eid_t"][k] + 3
    ops_o = [["h", dusn, cid, _comp_clima(cid, cl)]]
    if cur >= cl["dstart"] + PERIODO:                 # demasiado tarde: solo la gota
        ops_o.append(["e", dusn, cid, [-5, "dstart", 0]])
        cl["dstart"] = 0
        tarde = True
    else:
        ops_o.append(["e", dusn, cid, [-1, "drought", 1, -5, "dstart", 0]])
        cl["drought"] -= 1
        cl["dstart"] = 0
        tarde = False
    avanzar_sequia_parcela(p, cur, lote=True)         # igual que regar lo propio (a_regar)
    ids_v = _ids(gv)
    ops_v = [["h", usn, ids_v["c_estado"], _comp_estado(gv, ids_v)]]
    if hoy:
        ops_v.append(["e", usn, ids_v["c_estado"], [-5, "cof", cf, -9, "cocnt", 1]])
        gv["cocnt"] = int(gv.get("cocnt", 0)) + 1
    else:
        ops_v.append(["e", usn, ids_v["c_estado"], [-5, "cof", cf, -5, "cocnt", 1]])
        gv["cocnt"] = 1
    gv["cof"] = cf
    ops_v.append(["h", usn, ids_v["c_estado"], _comp_estado(gv, ids_v)])
    ops_v.append(["e", usn, ids_v["c_estado"], [-9, "gexp", EXP_REGAR, -9, "gpoint", 0]])
    gv["gexp"] += EXP_REGAR
    gv["nivel"] = nivel_de(gv["gexp"])
    _registrar(go, "hp", {"o": 0, "w": usn, "m": _b64(_nick_cuenta(acc_v))}, eid, cf)      # notifySys af56b8ed f12: {o = la orden (WATER_OP 0), w = quien ayuda, m = su apodo en base64}
    resp = {str(dusn): _marco(go, ids_o, cf, ops_o, "help"), str(usn): _marco(gv, ids_v, cf, ops_v, "helper")}
    return resp, "ayuda en la parcela %d de %d (%s): capas %d, +%d exp para quien ayuda, %d ayudas hoy" % (
        k, dusn, "tarde" if tarde else "a tiempo", cl["drought"], EXP_REGAR, gv["cocnt"])


def a_robar(go, gv, acc_o, acc_v, eid, cf):
    """doSteal: robar frutos de una planta madura de OTRO. Los chequeos, en el orden de stealSys f3; la cantidad, f4."""
    import math
    dusn, usn = go["u"], gv["u"]
    ids_o, k, p = _parcela_ajena(go, eid, ERR_ECID)
    pl = p.get("planta")
    est, sf, maduro = etapa_de(pl, cf) if pl else (0, 0, False)
    if not maduro:
        raise Rechazo("todavia no maduro (stage %d)" % est, ERR_NO_MADURO)
    rob = _robos_de(p)
    if rob["times"] >= _cfg("maxStealTimes", 100):
        raise Rechazo("la planta ya fue robada %d veces" % rob["times"], ERR_ROBO_MUCHO)
    if str(usn) in rob["thiefs"]:                     # string.find: busqueda de TEXTO (un usn dentro de otro tambien choca: LEIDO)
        raise Rechazo("ya le robo a esta planta", ERR_ROBO_DUP)
    if cf < sf:
        raise Rechazo("planta en proteccion (faltan %d cuadros)" % (sf - cf), ERR_PROTECCION)
    fila = items()[1][pl["code"]]
    retain = _cfg("retain", RETAIN)
    base = max(retain, fila["getCount"] - rob["stolen"])          # getHarvestReward(sin sequia, con lo robado): max(0, n - stolen), floor, max(retain)
    if base <= retain:
        raise Rechazo("quedan solo %d" % base, ERR_DEJA_UN_POCO)
    pct = AZAR_ROBO(_cfg("takeFruitMin", 10), _cfg("takeFruitMax", 15))
    robo = int(math.floor(base * pct / 100.0))
    if base - robo < retain:
        robo = base - retain
    if robo <= 0:
        raise Rechazo("el %d %% de %d no da ni uno" % (pct, base), ERR_DEJA_UN_POCO)
    fruto = fila["matureFruit"]
    e0 = ids_o["eid_t"][k]
    ops_o = [["h", dusn, e0 + 2, _comp_robos(e0 + 2, rob if p.get("robos") else None)],
             ["e", dusn, e0 + 2, [-9, "times", 1, -9, "stolen", robo, -5, "thiefs", rob["thiefs"] + ",%d" % usn]]]
    p["robos"] = {"times": rob["times"] + 1, "stolen": rob["stolen"] + robo, "thiefs": rob["thiefs"] + ",%d" % usn}
    _registrar(go, "bs", {"mp": {"p": fruto, "set": 0, "pr": robo}, "n": robo, "i": fruto, "w": usn, "m": _b64(_nick_cuenta(acc_v))}, eid, cf)   # notifySys af56b8ed f5
    ids_v = _ids(gv)
    ops_v = []
    _bolsa_suma(gv, ids_v, usn, ops_v, fruto, robo, 1)
    ops_v.append(_aviso(usn, 0, "bt", cf, {"mp": {"p": fruto, "set": 0, "pr": 1}, "w": dusn, "i": fruto, "n": robo, "m": _b64(_nick_cuenta(acc_o))}))
    _registrar(gv, "bt", {"mp": {"p": fruto, "set": 0, "pr": 1}, "n": robo, "i": fruto, "w": dusn, "m": _b64(_nick_cuenta(acc_o))}, 0, cf)   # el aviso bt (banderas 23) tambien lleva GARLOG: fila en el registro del ladron
    resp = {str(dusn): _marco(go, ids_o, cf, ops_o, "steal"), str(usn): _marco(gv, ids_v, cf, ops_v, "thief")}
    return resp, "robo %d x %d (%d %%) en la parcela %d de %d: lleva %d robados, %d veces" % (
        robo, fruto, pct, k, dusn, p["robos"]["stolen"], p["robos"]["times"])


def actuar_vecino(usn, nombre, args):
    """Un pedido de ayudar o robar. ('ok', {usn: {c,p}}, nota) o ('error', motivo, codigo). Un solo candado para los DOS jardines (dueno y visitante)."""
    if not (isinstance(args, list) and len(args) == 2 and all(_entero(a) for a in args)):
        return ("error", "argumentos de %s %r" % (nombre, args), ERR_OPERACION_MALA)
    dusn, eid = args
    ahora = int(RELOJ())
    cf = _frame(ahora)
    fn = a_robar if nombre == NOMBRE_ROBAR else a_ayudar

    def f(d):
        cuentas = d["cuentas"]
        ao, av = cuentas.get(str(dusn)), cuentas.get(str(usn))
        if av is None:
            return ("error", "el visitante no tiene cuenta", ERR_SIN_RELACION)
        if dusn == usn:
            return ("error", "%s en el propio jardin" % nombre, ERR_ROBAR_A_SI if fn is a_robar else ERR_OPERACION_MALA)
        if ao is None or not ao.get("jardin"):
            return ("error", "el dueno %d no tiene jardin" % dusn, ERR_SIN_RELACION)
        go, gv = ao["jardin"], av.setdefault("jardin", {})
        _preparar(go, dusn, ahora)
        _preparar(gv, usn, ahora)
        try:
            resp, nota = fn(go, gv, ao, av, eid, cf)
        except Rechazo as e:
            return ("error", str(e), e.codigo)
        return ("ok", resp, nota)
    try:
        return _cta.cambiar_todas(f)
    except Exception as e:                           # noqa: BLE001  (mejor un cartel que un servidor caido)
        anotar("   ⛔ jardin.actuar_vecino %s: %r" % (nombre, e))
        return ("error", "excepcion %r" % (e,), ERR_EXCEPCION)


def _vecino(con, seq, cuerpo, usn, nick, nombre, args):
    r = actuar_vecino(usn, nombre, args)
    if r[0] == "ok":
        n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, {"m": r[1]})
        anotar("   S2C FF26F %s %s de %s: %s (%d B de JSON, claves %s)" % (nombre, _json(args)[:40], nick, r[2], n, ",".join(r[1])))
        return True
    _contestar_texto(con, seq, cuerpo, nombre, r[2])
    anotar("   S2C FF26F %s %s de %s RECHAZADO (%s): texto %d" % (nombre, _json(args)[:40], nick, r[1], r[2]))
    return True


def amigos_del_jardin(usn):
    """Los amigos de `usn` (social.py: seccion `amigos`, solo lectura) que tienen jardin: [(usn, cuenta)] en el orden de la lista."""
    cuentas = _cta.todas()
    mia = cuentas.get(str(usn)) or {}
    lista = (mia.get("amigos") or {}).get("amigos") or []
    return [(int(u), cuentas[str(u)]) for u in lista if str(u) in cuentas and cuentas[str(u)].get("jardin")]


def respuesta_amigos(usn):
    """getAllFriends: LEIDO (exe 0x00c8f010): un objeto cuyos valores son {usn (entero), nick (texto), regdate (texto)}; las claves no se miran. regdate = la fecha de alta (INVENTADO el formato)."""
    return {str(i): {"usn": u, "nick": _nick_cuenta(acc), "regdate": str(((acc.get("cuenta") or {}).get("alta") or ""))[:10]}
            for i, (u, acc) in enumerate(amigos_del_jardin(usn))}


def respuesta_amigos_fila(usn, ahora=None):
    """getFriends [u32, u32] (el cliente lo manda justo despues de getAllFriends, con [1, 1] y 1 amigo): LEIDO (exe 0x00c8bea0 + la lambda 0x00c8c040): `{"n": int, "l": [fila]}`; una fila es
    {point, steal, exp, frame, nick, usn} (cadenas 0x0362be40, 0x0364827c, 0x03619344, 0x03638104, 0x03648308, 0x036223f0). Que significa cada numero NO se leyo (HIPOTESIS: point = landPoint,
    exp = gexp, frame = cuadro, steal = cuantas plantas maduras le puede robar quien pregunta)."""
    ahora = int(RELOJ()) if ahora is None else ahora
    cf = _frame(ahora)
    filas = []
    for u, acc in amigos_del_jardin(usn):
        g = acc["jardin"]
        robables = 0
        for p in g.get("parcelas", []):
            pl = p.get("planta")
            if pl and etapa_de(pl, cf)[2] and str(usn) not in _robos_de(p)["thiefs"]:
                robables += 1
        filas.append({"point": int(g.get("landpoint", 0)), "steal": robables, "exp": int(g.get("gexp", 0)), "frame": cf, "nick": _nick_cuenta(acc), "usn": u})
    return {"n": len(filas), "l": filas}


def _amigos_fila(con, seq, cuerpo, usn, nick, nombre, args):
    obj = respuesta_amigos_fila(usn)
    n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, obj)
    anotar("   S2C FF26F %s %s de %s: %d filas (%d B)" % (nombre, _json(args)[:20], nick, len(obj["l"]), n))
    return True


def _amigos(con, seq, cuerpo, usn, nick, nombre, args):
    obj = respuesta_amigos(usn)
    n = _contestar(con, seq, 0x26F, "26F", cuerpo, nombre, obj)
    anotar("   S2C FF26F %s de %s: %d amigos con jardin (%d B)" % (nombre, nick, len(obj), n))
    return True


METODOS_SEQUIA = {"gardenSys.doWater": a_regar, "gardenSys.pullout": a_pala, "gardenSys.doDeGrass": a_sin_desastre,
                  "gardenSys.doDebug": a_sin_desastre}
METODOS_TIERRA = {"gardenSys.upLand": a_mejorar, "gardenSys.unlockLand": a_desbloquear}
ACCIONES = ("gardenSys.buyItem",) + tuple(METODOS) + tuple(METODOS_SEQUIA) + tuple(METODOS_TIERRA)


MANEJADORES = {
    0x26F: jardin_forward,
    0x246: guia_forward,
}
