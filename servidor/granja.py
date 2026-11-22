# -*- coding: utf-8 -*-
r"""granja.py (11-nov, fichas 92 y 99) — la granja (我的庄园) de una cuenta LOCAL: abrirla, comprar un objeto de la
tienda y colocarlo, y que SIGA ahi al reabrir. Layouts leidos del exe: docs/tablero/layouts/FF14C.md (secciones
"Lectura de la ficha 92" y "Lectura de la ficha 99"), FF150.md, FF181.md.

  C2S FF14C [04][u8 largo][apodo]  (2 B = la propia; con apodo = visitar a otro)
  S2C FF14C [04][u8 res=0]...  y despues, como el oficial (6 de 6 aperturas propias): [0f] [18] ; los [14] y [24] se
  contestan cuando el cliente los pide (C2S [14] y [24] de 1 B, 12 de 12 tras el 04).
  C2S FF14C [05][u32 Index][s8 x][s8 y][u8 giro][u8][u32] (13 B: comprar+colocar; MEDIDO con el juego y 2 de 2 en el oficial)
  C2S FF14C [09][u16 n][n x {u32 id, s8 x, s8 y, u8 giro}] (mover, 移动完毕: MEDIDO con el juego, 10 B con n = 1); S2C [09][u8 res][u16 n][n x 7 B]
        (LEIDO en 0x02738bf0; el eco es INVENTADO: no hay muestra del oficial)
  S2C FF14C [05][u32 Index][u32 0][u8 res] si falla; si sale bien: [05][u32 Index][u32 0][u8 0][fila 38 B][u32][u8]
        [u32 hora][u32 16][u32 0xffffffff] (65 B, 2 de 2 del oficial) y [0a][u8 tipo=1][dueno 37 B][u8 subio de nivel]
        [7 x s32 diferencias: energia, estrellas, madera, exp, 0, 0, 0][u32 id del objeto] (72 B, 1 de 1 del oficial).

ESTADO (seccion `granja` de la cuenta, solo via cuenta.py, version 2): exp (a), energia (b) y su hora, energia maxima (c),
estrellas (d), madera (e), dulces (f), tamano, objetos [{id, index, x, y, giro, estado, t, u17}], sig_id.
LO QUE VIENE DEL OFICIAL (grabacion 215530 = una granja recien creada, 1 sola testigo: HIPOTESIS que valga para todas):
  el 1.er 04 trae exp 0, energia 10/10, 3000 estrellas, 3000 madera, 0 dulces, tamano 28 y UNA mascota (Index 5000004, en
  la celda 14,14, estado 'X') + su registro de mascota (n12 = 1); el byte byPetMaxExtensionCnt vale 16 en 12 de 12.
LO INVENTADO (marcado `inventado: true` en la seccion): que esos valores sean los de TODA granja nueva; el nombre del objeto
  (en el oficial sale "(null)": aca va vacio); los 2 bytes de relleno de la fila (0); el aviso de subida de nivel (siempre 0,
  sin efecto de nivel); la hora de fin de produccion (ahora + Buildtime + Cooltime de farmshop.txt: 1 sola muestra: 135 s
  = 15 + 120); la regeneracion de energia (1 punto cada 150 s: LEIDO del texto de ayuda del cliente, no del codigo).
LO QUE SALE DE TABLA: costos (LI estrellas, WI madera, Energy), nivel pedido (Level), EXP que suma, tamano (Width/Depth),
  Buildtime y Cooltime, todo de farmshop.txt.

Visitar a otro (apodo): res 0x0d "esa granja no existe" (LEIDO, ver FF14C.md). Sesion capturada (sin cuenta local): sin contestar.
FICHA 102 (cosechar, vender, niveles, 1e; layouts en FF14C.md "Lectura de la ficha 102"):
  C2S FF14C [08][u32 id] (5 B) -> S2C [08][u32 id][u8 res]  y si res 0: [u32 fin del proximo ciclo][u32 ahora]  (14 B, 6 de 6 del
        oficial: fin - ahora = Cooltime de farmshop.txt en 6 de 6) y despues [0a] tipo 2 (72 B): diferencias (-IEnergy, +Output en
        estrellas si Function L o en madera si W, +EXP, 0, 0, 0) (2 de 2 del oficial con IEnergy / Output / EXP de la tabla).
  C2S FF14C [0b][u32 id] (5 B) -> S2C [0b][u32 id][u8 res=0] (LEIDO en 0x02738fa0: saca el edificio de la escena); devuelve el 10 %
        de LI y de WI (lo que dice la ventana de venta del cliente, MEDIDO en la ficha 99) con un [0a] tipo 3 ANTES (INVENTADO).
  C2S FF14C [1e] (1 B; el cliente lo manda cuando su energia es 0, 0x02992970) -> S2C [1e][u32 A][u32 B] (LEIDO en 0x0273ce60:
        A = hora de la proxima energia, B = ahora; 0x02992df0 muestra la cuenta atras A - B si A >= B).
  NIVEL: umbrales de exp horneados en el exe (0x0360d308, LEIDO en 0x02992be0; MEDIDOS exp 5 -> Lv 2, exp 7 -> barra 2/5,
        exp 10 -> Lv 3, exp 27 -> Lv 5): UMBRALES abajo. La hora la pone el SERVIDOR: cosechar antes de tiempo se rechaza.
FICHA 104 (misiones y ampliar; layouts en FF14C.md "Lectura de la ficha 104"; llave GRANJA_MISIONES, omision 0):
  S2C FF14C [0e][32 B]  mision nueva; [0f][u8 n][n x 32 B] lista de las activas al abrir; [10][32 B] la misma con estado 1 (cumplida);
        [11][u8 res=0][u32 serial] cobrada; despues [0a] tipo 5 (0, +estrellas, +madera, +exp, +dulces, 0, 0; id = serial) y las [0e]
        nuevas. Registro de 32 B: [u32 serial][u32 questID][u32 estado][u32 -1][16 B Constant de la tabla, NUL]. El cliente NO manda
        nada de misiones (las lleva el servidor). Cadena MEDIDA (1 sesion del oficial, 9 pasos): accion -> 10 -> 11 -> 0a tipo 5 -> 0e.
        Tabla farmquest.txt (datos/): las 3 iniciales = las filas sin otro requisito que firstquest / petlevel:1; luego salen las de
        tipo 1 (questID / 10^7 = 1: las regulares) cuyo Prerequisite se cumple, EN EL ORDEN DE LA TABLA (3 de 3 y 3 de 3 del oficial).
        Disparadores que el servidor YA atiende: 05 (build), 08 (collect), 0c (expand). Lo demas (train, visit, hammer...: ver EVENTOS)
        existe en el motor como evento pero NINGUN C2S lo manda hoy; las misiones con otra Goal, con Cumulate > 1, las diarias y las
        repentinas quedan activas SIN avanzar (no se inventa su progreso).
  C2S FF14C [0c][u8 tamano nuevo] (2 B) -> S2C [0a] tipo 4 (0, -LI, -WI, 0, 0, +2, 0) con el dueno ya con el tamano nuevo + [0c][u8 res][u8 tamano]
        (LEIDO en 0x02739320; MEDIDO 1 de 1 con 30). El "ticket" es el Index de la tienda (5400001..04 / 08 / 09 = 30..40 de a 2): LI, WI y Level
        de la tabla; solo la siguiente al tamano actual (res 8 = "ampliar primero las anteriores", ms 0x218 LEIDO); lo demas res 3 (INVENTADO).
  GRANJA_MISIONES (omision 1 desde la ficha 108): con la ficha 104 quedaba en 0 porque el tutorial del cliente (misiones de Category tutorial) dejaba al
  jugador ENCERRADO en el paso de entrenar (59). Con la 108 se recorre ENTERO con el juego: 10501001..06 y 08 avanzan, y la tienda y el boton de salir responden.
FICHA 108 (entrenar, visitar, ayudar; layouts en FF14C.md "Lectura de la ficha 108"):
  C2S FF14C [59][u8 modo][u32 mascota][u32 torre] (10 B): modo 0x81 = EMPEZAR -> 0a tipo 8 (-Energy, -Price de farmtraining.xml) + (la mision `train`: 10, 11,
        0a tipo 5) + S2C [59] de 59 B (res 0, hora del SERVIDOR + TrainingTime) + los 0e nuevos (orden del oficial); modo 0x85 = COBRAR (HIPOTESIS: S2C 59 con
        res 0x14 y el nivel nuevo de la mascota en la cola; MEDIDO con el juego que la torre vuelve a quedar libre): suma EXP y piezas de la tabla a la mascota.
  C2S FF14C [04][u8 largo][texto]: `%NPC%` = granja_npc (forma grabada del oficial, usn 1, apodo "NPC王"), `%RANDOM%` o un apodo = el estado GUARDADO de otra cuenta
        local (solo mirar), respuesta 04 (byte "ajena" = 1) + 18 (el bloque PROPIO) + la mision `visit`; res 0x16 (sin granja al azar) / 0x0d (no existe). Mientras
        se ve una granja ajena se ignoran 05 / 08 / 09 / 0b / 0c / 59.
  C2S FF14C [12][u8 modo][u32 id] (AYUDAR, en la granja ajena): modo 0 -> [12][0x2e][id]; modo 1 -> [12] res 0 (id, 1,1 x Output, apodo y usn de quien ayuda) + [17][n]
        + 0a tipo 6 (+200 estrellas edificio L / +100 madera W, +1 dulce); una vez por edificio y dia (INVENTADO: tope 5; en %NPC% sin limite). [a7] -> [a2][0x20]
        (el boton de clavar); [a8][u32 5300016][s8 x][s8 y][u8 giro][u8 largo][texto] -> a2 (44 B) + a3 (9 B) + 0a tipo 15 y la mision `hammer`; solo en %NPC%.
  ESTADO: cada mascota guarda `exp` y `piezas` [VIT, DEX, INT] y, entrenando, `torre` y `fin`; la torre queda `T` con t = fin y u17 = mascota; la seccion
  `granja` suma `trabajo` {dia, n, ya} (ayudas del dia) y `sig_clavo`. Tablas: datos/farmtraining.xml y datos/farmpet.xml (herramientas/preparar_granja.py).
FICHA 104, ENERGIA/EXP al comprar la torre 5200001: el oficial resto energia 0 y dio +1 exp (1 de 1; la tabla dice Energy 1 y sin EXP):
  MEDIDO_COMPRA lo corrige para ese Index (los demas Function T siguen con la tabla: HIPOTESIS que sean iguales).
FICHA 119 (terminar ya, decoraciones y defensas, misiones ronda 2; layouts en FF14C.md "Medido con el juego, ficha 119"; llaves GRANJA_TERMINAR_YA,
  GRANJA_DECORAR y GRANJA_MISIONES2, omision 1 las tres: lo suyo se vio con el juego; en 0 los bytes son los de la ficha 108):
  C2S FF14C [1d][u32 id] (5 B: lo manda el tutorial solo al seguir despues de comprar el queso y la ventana 生产 de un edificio de produccion, boton 立即完成) ->
        S2C [0a] tipo 9 con (-IEnergy, -ILI, -IWI) de farmshop.txt + [1d][u32 id][u8 res]: res 0 = termina YA (la hora de fin pasa a ahora: el globo de cosecha sale y
        el 08 cosecha); 0x17 = ya estaba completo; 5 / 6 / 7 = falta energia / madera / estrellas (el cliente abre el cartel de comprar: MEDIDO el 5); 3 = no existe /
        no es de produccion (el cliente no hace nada). En el TUTORIAL (mision `collect` de Category tutorial activa sobre ese Index) el cobro es 0, como la unica muestra.
  Decoraciones (Function J) y defensas (D): el 05 de siempre (colocables() las suma con la llave), objeto en reposo X sin hora; las D guardan u17 = Output (5).
  Misiones ronda 2 (_m2): Cumulate > 1 con el contador `n` en la mision activa de la cuenta; eventos arrange (09), sell (0b), star / wood (lo cosechado), arbeit (12),
        quickfinish (1d); el prerequisito `Farmlevel:` con F mayuscula.
GRANJA (llave de entorno, omision 1) = 0 apaga todo (como antes: sin atender). GRANJA_COMPRA (omision 1) = 0 apaga solo
comprar/colocar (el sub 05 queda sin atender). GRANJA_VARIANTE (omision 2): 1 = las listas en 0 (sin mascota ni objetos:
el prado vacio de la ficha 92), 2 = lo del oficial (mascota + objetos comprados), 3 = como 2 y el 24 con 1 fila de 29 B.
"""
import copy
import os
import random
import re
import struct
import time

import cuenta as _cta
import estado
import textos

LLAVES_OMISION = {"GRANJA": "1", "GRANJA_COMPRA": "1", "GRANJA_MISIONES": "1", "GRANJA_TERMINAR_YA": "1", "GRANJA_DECORAR": "1", "GRANJA_MISIONES2": "1",
                  "GRANJA_MASCOTAS": "1", "GRANJA_RANKING": "0"}
VERSION_ESTADO = 2
TAMANO_BASE = 28                # MEDIDO: el 1.er 04 del oficial trae 28; el cliente lo busca EXACTO en farmcamera.txt (28/30/32/34)
INDEX_MASCOTA = 5000004         # farmshop.txt Function P; la mascota que trae una granja nueva del oficial
RES_NO_EXISTE = 0x0D
ENERGIA_CADA = 150              # segundos por punto de energia (texto de ayuda del cliente: "cada 2 min 30 s")
LUGARES_BASE = 2                # FICHA 126: lugares de mascota de una granja nueva (MEDIDO en las grabaciones: byte +32 del bloque del dueno = 2; constructor 0x00977dfd)
MASCOTA_MAX = 16               # byPetMaxExtensionCnt: 16 en 12 de 12 respuestas grabadas
FUNCIONES_COLOCABLES = ("L", "W", "T")   # edificios: estrellas (L), madera (W), entrenamiento (T); el resto de Function: sin atender (no probado)
FUNCIONES_DECORAR = ("J", "D")           # FICHA 119 (llave GRANJA_DECORAR): decoraciones (J, 57 filas) y defensas (D, 2): el 05 de siempre, sin produccion
RES_YA_COMPLETO = 0x17          # S2C 1d res 0x17: "ya esta completo" (LEIDO en 0x0273cae0, ficha 118)
RES_FALLA = 3                   # res generico (el cliente muestra "System Error : code 3")
RES_NIVEL, RES_ENERGIA, RES_MADERA, RES_ESTRELLAS = 4, 5, 6, 7     # LEIDO en 0x02738207: tabla de saltos de res de la respuesta 05
# FICHA 108 (entrenar, visitar, ayudar). LEIDO en el exe: S2C 59 en 0x0273f150 (res 0 = empezo, 0x14 = terminado, 0x82 y el resto = cartel por la tabla
# 0x0273f884/0x0273f89c: res 3 y 15 un cartel, 7, 9 y 10 otros tres, 16 suma al contador de la mascota, los demas "System Error : code N"); S2C 12 en 0x02739690.
RES_TERMINO = 0x14              # S2C 59 con res 0x14: el entrenamiento termino (la torre pasa a estado 12, la mascota recibe su nivel nuevo)
RES_12_LISTO = 0x2E             # S2C 12 con res 0x2e: la torre... el edificio pasa a su estado 5 (LEIDO 0x02739a44); sale como respuesta a 12 [modo 0]
RES_NO_HAY_AZAR = 0x16          # S2C 04 res 0x16: "no hay granjas para visitar al azar" (LEIDO, ficha 92)
NPC_USN = 1                     # MEDIDO: el 04 de %NPC% del oficial trae usn 1
NPC_NICK = "NPC王"           # "NPC王": cadena 595 de la tabla de textos de la granja (5 B en gbk, como el apodo del 04 de %NPC% grabado)
NPC_PETS = ((9230, 2, 2, 0), (9250, 2, 0, 0))     # (id, a, e, f) de las 2 mascotas del 04 de %NPC% (forma grabada; ids de juego del NPC)
TRABAJO_ESTRELLAS, TRABAJO_MADERA, TRABAJO_DULCES = 200, 100, 1      # 0a tipo 6 del oficial: 2 de 2 con estrellas 200 (edificio L) / 1 de 1 madera 100 (W), dulces +1
TRABAJO_MAX_DIA = 5             # INVENTADO: el cliente muestra "打工(n/max)" y solo manda n; el maximo no esta leido
CLAVO_INDEX = 5300016           # MEDIDO: el 0a tipo 15 del oficial lleva el Index 5300016 (el clavo) como id

_RUTAS_SHOP = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "farmshop.txt"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "import_input", "steam_10379", "_extract", "rnr_script", "farmshop.txt"),
)
_SHOP = {}
_RUTAS_QUEST = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "farmquest.txt"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "import_input", "steam_10379", "_extract", "rnr_script", "farmquest.txt"),
)
_QUEST = {}
# MEDIDO en el oficial (grabacion 215530, 1 de 1): construir la torre 5200001 resto ENERGIA 0 y dio +1 EXP; farmshop.txt dice Energy 1 y
# no tiene EXP. Solo se corrige ese Index (los otros Function T siguen con la tabla: HIPOTESIS que sean iguales).
MEDIDO_COMPRA = {5200001: {"energia": 0, "exp": 1}}
# AMPLIAR (LEIDO en 0x02978060: Index del ticket -> tamano): 5400001..04 = 30..36, 5400008 = 38, 5400009 = 40. Cada una se compra
# con LI / WI / Level de farmshop.txt (las de 38 y 40 tienen Sell 0: tienda() no las trae y se rechazan). farmcamera.txt trae 28..40.
TICKETS = {30: 5400001, 32: 5400002, 34: 5400003, 36: 5400004, 38: 5400008, 40: 5400009}
RES_ORDEN = 8                   # 0c res 8 = ms 0x218 "ampliar primero las anteriores" (LEIDO en 0x027395a4 + 0x029cc820)


RELOJ = time.time               # las pruebas lo cambian por un reloj falso


def ahora():
    return int(RELOJ())


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="GRANJA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def colocables():
    """Las Function de la tienda que se compran / colocan / venden: edificios L, W, T y, con GRANJA_DECORAR (ficha 119), decoraciones J y defensas D."""
    return FUNCIONES_COLOCABLES + (FUNCIONES_DECORAR if llave("GRANJA_DECORAR") else ())


def variante():
    try:
        return int(os.environ.get("GRANJA_VARIANTE", "2"))
    except ValueError:
        return 2


# ---------------------------------------------------------------- tabla de la tienda (farmshop.txt)
def tienda():
    """{Index: fila} de farmshop.txt (las filas con Sell=1), con los numeros ya como int. {} si el archivo no esta."""
    if _SHOP:
        return _SHOP
    for ruta in _RUTAS_SHOP:
        try:
            txt = open(ruta, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.findall(r"<Farm [^>]*>", txt):
            r = dict(re.findall(r'(\w+)="([^"]*)"', m))
            try:
                if r.get("Sell") != "1":
                    continue
                f = {"index": int(r["Index"]), "fn": r.get("Function", "")}
                for k, dst in (("LI", "li"), ("WI", "wi"), ("Energy", "energia"), ("EXP", "exp"), ("Level", "nivel"),
                               ("Width", "ancho"), ("Depth", "fondo"), ("Buildtime", "obra"), ("Cooltime", "ciclo"),
                               ("Cash", "cash"), ("Output", "salida"), ("IEnergy", "i_energia"), ("ILI", "i_li"), ("IWI", "i_wi")):
                    f[dst] = int(r.get(k, "0") or 0)
                _SHOP[f["index"]] = f
            except (KeyError, ValueError):
                continue
        break
    return _SHOP


# Umbrales de exp de la granja, LEIDOS del exe (Game_g21_local.exe, 0x0360d308 + 4 * k, k = 0..49; 0x02992be0 busca el menor
# nivel L (1..49) con exp < UMBRALES[L] y, si ninguno, nivel 50). Barra = exp - UMBRALES[L-1] sobre UMBRALES[L] - UMBRALES[L-1].
UMBRALES = (0, 5, 10, 17, 26, 45, 66, 89, 114, 201, 294, 393, 498, 609, 867, 1149, 1455, 1785, 2139, 2659, 3211, 3795, 4411,
            5059, 5755, 6483, 7243, 8035, 8859, 10821, 13071, 15681, 18651, 21981, 25707, 30009, 34887, 40341, 46371, 53751,
            61851, 70671, 80211, 90471, 101491, 113311, 125931, 139351, 153571, 168631)
NIVEL_MAX = 50


# Energia maxima por nivel: MEDIDA en las 46 apariciones del bloque del dueno en las grabaciones del oficial (nivel 1, 2 y 3: 10;
# 5, 6 y 8: 15; 50: 33). Los niveles que no se vieron (4, 7, 9..49) INVENTADO: el ultimo valor medido hacia abajo.
EMAX_MEDIDA = {1: 10, 2: 10, 3: 10, 5: 15, 6: 15, 8: 15, 50: 33}


def emax_de(nivel):
    """Energia maxima de un nivel (MEDIDA en los niveles de EMAX_MEDIDA; en el resto, el ultimo medido hacia abajo: INVENTADO)."""
    return EMAX_MEDIDA[max(k for k in EMAX_MEDIDA if k <= max(1, nivel))]


def subir_nivel(c, nv0, hoy):
    """Si la exp de c paso a un nivel mas alto que nv0: sube la energia maxima (emax_de) y la energia vuelve a estar llena (MEDIDO:
    el 0a del oficial trae energia = maxima en las 3 subidas vistas; el cliente muestra "能量已全部恢复" en la ventana LEVEL N).
    Devuelve el nivel nuevo, o 0 si no subio."""
    nv1 = nivel_de(c["exp"])
    if nv1 <= nv0:
        return 0
    c["energia_max"] = max(c["energia_max"], emax_de(nv1))
    c["energia"] = c["energia_max"]
    c["energia_t"] = hoy
    return nv1


def nivel_de(exp):
    """Nivel de granja de una exp total: el de la tabla de umbrales del exe (50 como tope)."""
    for lv in range(1, NIVEL_MAX):
        if exp < UMBRALES[lv]:
            return lv
    return NIVEL_MAX


# ---------------------------------------------------------------- mascotas y entrenamiento (ficha 108)
_DATOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos")
_TRAIN = {}
_PETTAB = {}


def _leer_datos(nombre):
    try:
        return open(os.path.join(_DATOS, nombre), "rb").read().decode("latin-1")
    except OSError:
        return ""


def entrenamientos():
    """{Index de torre: fila} de farmtraining.xml (rnr_sng.pak; LEIDO en 0x029286e0 lo que carga el cliente; Ability y TrainingTime son del SERVIDOR):
    {hab: 0 VIT / 1 DEX / 2 INT, energia, tiempo (s), exp, pieza, tipo (L = estrellas), precio, nivel}. {} si el archivo no esta en datos/."""
    if _TRAIN:
        return _TRAIN
    for m in re.findall(r"<Building [^>]*>", _leer_datos("farmtraining.xml")):
        r = dict(re.findall(r'(\w+)="([^"]*)"', m))
        try:
            _TRAIN[int(r["Index"])] = {"hab": ("VIT", "DEX", "INT").index(r["Ability"]), "energia": int(r["Energy"]), "tiempo": int(r["TrainingTime"]),
                                       "exp": int(r["MinEXP"]), "pieza": int(r["MinPiece"]), "tipo": r["PriceType"], "precio": int(r["Price"]),
                                       "nivel": int(r["Level"])}
        except (KeyError, ValueError):
            continue
    return _TRAIN


def mascotas_tabla():
    """De farmpet.xml (rnr_script.pak; el cliente NO lo carga, es del servidor): {niveles: [(nivel, EXP acumulada)], add: [VIT, DEX, INT] de
    [(piezas, suma)], base: {Index: (VIT, DEX, INT)}}. Con el archivo ausente de datos/: nivel 1 y nada mas."""
    if _PETTAB:
        return _PETTAB
    txt = _leer_datos("farmpet.xml")
    niveles = [(int(a), int(b)) for a, b in re.findall(r'<Level Value="(\d+)"[^>]*?NeedEXP="(\d+)"', txt)]
    add = [[(int(a), int(b)) for a, b in re.findall(r'<%sLevel NeedPiece="(\d+)" Add="(\d+)"' % k, txt)] for k in ("Vit", "Dex", "Int")]
    base = {int(i): (int(v), int(d), int(n)) for i, v, d, n in re.findall(r'<FarmPet Index="(\d+)"[^>]*?BaseVIT="(\d+)" BaseDEX="(\d+)" BaseINT="(\d+)"', txt)}
    _PETTAB.update({"niveles": niveles or [(1, 0)], "add": add, "base": base})
    return _PETTAB


def nivel_mascota(exp):
    """Nivel (1..30) de una mascota con esa EXP: el mayor cuya EXP acumulada ya se alcanzo (farmpet.xml, Level / NeedEXP)."""
    nv = 1
    for v, need in mascotas_tabla()["niveles"]:
        if exp >= need:
            nv = v
    return nv


def estadisticas_mascota(o):
    """(nivel, (VIT, DEX, INT)) de una mascota: base de su fila de farmpet.xml (3/4/3 si no esta) + (nivel - 1) por nivel + la suma que dan
    sus piezas (DexLevel / VitLevel / IntLevel: la mayor 'Add' cuyo NeedPiece ya se junto). MEDIDO contra el oficial en el nivel 1 (3/4/3 =
    BaseVIT/DEX/INT) y a nivel 30 (~45); la suma exacta con piezas es HIPOTESIS."""
    t = mascotas_tabla()
    nv = nivel_mascota(o.get("exp", 0))
    base = t["base"].get(o["index"], (3, 4, 3))
    pz = (list(o.get("piezas", [])) + [0, 0, 0])[:3]
    st = []
    for k in range(3):
        suma = max([a for need, a in t["add"][k] if need <= pz[k]] or [0])
        st.append(base[k] + nv - 1 + suma)
    return nv, tuple(st)


def mensajes_entrenar(nick, g, fila, pasos, cuerpo59):
    """Orden MEDIDO del oficial al empezar a entrenar: 0a tipo 8 (-Energy, -Price), la mision `train` (10, 11, 0a tipo 5), el 59 y recien despues
    los 0e de las misiones nuevas (1 de 1). Devuelve la lista de cuerpos S2C FF14C."""
    out = [cuerpo_0a(nick, g, 8, (-fila["energia"], -fila["precio"], 0, 0, 0, 0, 0), 0)]
    msgs = mensajes_pasos(nick, pasos) if pasos else []
    k = next((i for i, m in enumerate(msgs) if m[0] == 0x0E), len(msgs))
    return out + msgs[:k] + [cuerpo59] + msgs[k:]


def cuerpo_59(res, pet_id, torre_id, hoy, torre_index, fin, fila, nivel=0, ganado=(0, 0)):
    """S2C FF14C [59] de 59 B (rx 0x0273f150; 1 muestra del oficial, res 0): [u8 res][u32 mascota][u32 torre][u32 ahora][36 B = 9 x u32: ?, torre,
    Index de la torre, fin, ?, Price, Energy, ?, ?][u32 fin][u8 ...][u32 0]. LEIDO: con res 0 la torre pasa a su estado 10 y se le pone la hora;
    con res 0x14 la mascota recibe como nivel el u8 de la cola y si el 8.o u32 de los 36 B != 0 el edificio muestra ese numero (tipo 5).
    INVENTADO: los dos u32 '?' (basura distinta en la muestra) van en 0; en 0x14 el 8.o u32 = piezas ganadas y el 9.o = EXP ganada (HIPOTESIS)."""
    rec = (0, torre_id, torre_index, fin, 0, fila["precio"], fila["energia"], ganado[0], ganado[1])
    return (bytes([0x59, res]) + struct.pack("<III", pet_id, torre_id, hoy & 0xFFFFFFFF) + struct.pack("<9I", *[x & 0xFFFFFFFF for x in rec])
            + struct.pack("<IBI", fin & 0xFFFFFFFF, nivel & 255, 0))


def entrenar(usn, pet_id, torre_id):
    """C2S 59 [0x81][mascota][torre]. Con el candado: valida (la mascota y la torre existen, la torre es de entrenamiento y esta libre, la mascota no
    esta entrenando, hay Energy y Price de la tabla), cobra, pone la hora de fin con el reloj del SERVIDOR (ahora + TrainingTime) y marca la torre
    (estado T, u17 = mascota) y la mascota. Devuelve (res, g, fila, indice de la torre, ahora, fin, pasos); res 0 = bien, si no RES_FALLA
    (INVENTADO: el res 3 del cliente muestra un cartel, el motivo exacto no esta leido)."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        pet = next((o for o in c["objetos"] if o["id"] == pet_id and _es_mascota(o)), None)
        torre = next((o for o in c["objetos"] if o["id"] == torre_id), None)
        fila = entrenamientos().get(torre["index"]) if torre else None
        if pet is None or torre is None or fila is None or torre.get("estado") != "X" or pet.get("torre") or fila["tipo"] != "L":
            return RES_FALLA
        if c["energia"] < fila["energia"] or c["estrellas"] < fila["precio"]:
            return RES_FALLA
        c["energia"] -= fila["energia"]
        c["estrellas"] -= fila["precio"]
        fin = hoy + fila["tiempo"]
        torre.update({"estado": "T", "t": fin, "u17": pet_id})
        pet.update({"torre": torre_id, "fin": fin})
        sal.update({"g": _copia(c), "fila": fila, "idx": torre["index"], "fin": fin,
                    "pasos": _evento(c, hoy, "train", torre["index"]) if llave("GRANJA_MISIONES") else []})
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("fila"), sal.get("idx"), hoy, sal.get("fin"), sal.get("pasos", [])


def cobrar_entrenamiento(usn, pet_id, torre_id):
    """C2S 59 [0x85][mascota][torre] (el cliente lo manda con la torre en su estado 9, 0x0294ece9; la RESPUESTA no esta en ninguna grabacion:
    HIPOTESIS que sea el S2C 59 con res 0x14). Con el candado: si la hora de fin (la del SERVIDOR) ya paso, la mascota suma la EXP y las piezas de
    la tabla (farmtraining.xml: MinEXP, MinPiece en la estadistica Ability), la torre queda libre. Devuelve (res, g, fila, indice, ahora, fin,
    nivel de la mascota, (piezas, exp)); res RES_FALLA si no esta entrenando, no coincide o todavia no termino."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        pet = next((o for o in c["objetos"] if o["id"] == pet_id and _es_mascota(o)), None)
        torre = next((o for o in c["objetos"] if o["id"] == torre_id), None)
        if pet is None or torre is None or torre.get("estado") != "T" or pet.get("torre") != torre_id or torre.get("u17") != pet_id:
            return RES_FALLA
        fila = entrenamientos().get(torre["index"])
        if fila is None or torre.get("t", 0) > hoy:
            return RES_FALLA
        pz = (list(pet.get("piezas", [])) + [0, 0, 0])[:3]
        pz[fila["hab"]] += fila["pieza"]
        pet["piezas"] = pz
        pet["exp"] = pet.get("exp", 0) + fila["exp"]
        fin = torre["t"]
        torre.update({"estado": "X", "t": 0, "u17": 0})
        pet.pop("torre", None)
        pet.pop("fin", None)
        nv = nivel_mascota(pet["exp"])
        pasos, nuevas = [], []
        if llave("GRANJA_MISIONES"):
            pasos = _evento(c, hoy, "petlevel", nv)
            if not pasos:
                nuevas = _entregar(c) if nv > nivel_mascota(pet["exp"] - fila["exp"]) else []     # el nivel nuevo abre misiones con `petlevel:N`
        sal.update({"g": _copia(c), "fila": fila, "idx": torre["index"], "fin": fin, "nivel": nv, "ganado": (fila["pieza"], fila["exp"]), "pasos": pasos, "nuevas": nuevas})
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("fila"), sal.get("idx"), hoy, sal.get("fin"), sal.get("nivel", 0), sal.get("ganado", (0, 0)), sal.get("pasos", []), sal.get("nuevas", [])


# ---------------------------------------------------------------- estado
def _inicial(ahora):
    """Estado de una granja nueva: lo visto en el 1.er 04 del oficial (mascota en 14,14). INVENTADO que valga para todas."""
    return {"version": VERSION_ESTADO, "inventado": True, "exp": 0, "energia": 10, "energia_t": ahora, "energia_max": 10,
            "estrellas": 3000, "madera": 3000, "dulces": 0, "tamano": TAMANO_BASE, "creada": ahora, "sig_id": 2,
            "objetos": [{"id": 1, "index": INDEX_MASCOTA, "x": 14, "y": 14, "giro": 0, "estado": "X", "t": 0, "u17": 0}]}


def _regenerar(g, ahora):
    """Suma la energia que volvio con el tiempo (1 cada ENERGIA_CADA s) hasta el maximo. Cambia g en el lugar."""
    if g["energia"] >= g["energia_max"]:
        g["energia_t"] = ahora
        return
    n = max(0, (ahora - g.get("energia_t", ahora)) // ENERGIA_CADA)
    if n:
        g["energia"] = min(g["energia_max"], g["energia"] + n)
        g["energia_t"] = ahora if g["energia"] >= g["energia_max"] else g["energia_t"] + n * ENERGIA_CADA


def _preparar(g, ahora):
    """Deja g en la version actual (una granja de la ficha 92 era INVENTADA entera: se rehace) y con la energia al dia."""
    if g.get("version") != VERSION_ESTADO:
        g.clear()
        g.update(_inicial(ahora))
    _regenerar(g, ahora)


def _copia(g):
    return {k: ([dict(o) for o in v] if isinstance(v, list) else (copy.deepcopy(v) if isinstance(v, dict) else v)) for k, v in g.items()}


def estado_de(usn):
    """El estado de la granja de ese usn; si no tiene, lo crea (INVENTADO) y lo guarda. Devuelve copia."""
    def f(c):
        _preparar(c, ahora())
        return _copia(c)
    return _cta.cambiar_seccion(usn, "granja", f)


# ---------------------------------------------------------------- piezas del mensaje
def _dueno(nick, tamano, g=None):
    """37 B del dueno (LEIDO en 0x0293c710; MEDIDO con el juego, un campo cada vez): [u32 exp total][u8 energia][u8 energia
    maxima][u32 estrellas][u32 madera][u32 dulces][u8 tamano (clave de farmcamera.txt)][apodo NUL, 18 B]."""
    g = g or {}
    if llave("GRANJA_MASCOTAS"):
        # FICHA 126: el apodo mide 13 B (+19..+31) y el byte +32 son los LUGARES DE MASCOTA (LEIDO 0x0293c7cd..0x0293c865: `[0x3a7f920]+0x18` = ese byte, y
        # 0x0297885b rechaza comprar una mascota si las que hay >= ese valor; MEDIDO en las grabaciones: 2 en una granja nueva, 10 / 15 / 16 en otras); los 4 B de
        # despues (+33) van a `[0x3a7f920]+0x24` (grab: el id de una mascota; aca 0)
        cola = textos.codificar(nick, 12).ljust(13, b"\x00") + bytes([g.get("lugares", LUGARES_BASE) & 255]) + struct.pack("<I", g.get("rep", 0) & 0xFFFFFFFF)
    else:
        cola = textos.codificar(nick, 17).ljust(18, b"\x00")
    return (struct.pack("<I", g.get("exp", 0) & 0xFFFFFFFF) + bytes([g.get("energia", 0) & 255, g.get("energia_max", 0) & 255])
            + struct.pack("<III", g.get("estrellas", 0) & 0xFFFFFFFF, g.get("madera", 0) & 0xFFFFFFFF, g.get("dulces", 0) & 0xFFFFFFFF)
            + bytes([tamano & 255]) + cola)


def _fila(o):
    """Fila de objeto de 38 B (la de n1 del 04 y la del 05; LEIDO en 0x02947f30, MEDIDO con 2 respuestas del oficial):
    [u32 Index][u32 id][s8 x][s8 y][u8 giro][2 B relleno][u32 hora][u32 u17][u8 estado][nombre 16 B]."""
    est = o.get("estado", "X")
    b = (struct.pack("<IIbbB", o["index"], o["id"], o["x"], o["y"], o.get("giro", 0)) + b"\x00\x00"
         + struct.pack("<II", o.get("t", 0) & 0xFFFFFFFF, o.get("u17", 0) & 0xFFFFFFFF) + est.encode("ascii")[:1] + bytes(16))
    assert len(b) == 38
    return b


def _mascota(o):
    """Registro de mascota (n12; 35 B sin nombre). Forma del 1.er 04 del oficial: [u32 id][u32 Index][a, b, c][u32 edificio][u32 hora de fin]
    [u8 d][u8 largo 0][e, f][u32 g][u32 h][u32 i]. FICHA 108: b = NIVEL, g,h,i = VIT, DEX, INT (MEDIDO contra la tabla, ficha 104) salen de
    estadisticas_mascota(o); c = 1 y edificio / fin puestos mientras entrena (MEDIDO en el 04 propio del oficial con la torre en uso:
    abc [1,1,1], edificio = id de la torre, fin = la hora). Sin entrenar y sin experiencia los bytes son los de siempre (nivel 1, 3/4/3)."""
    nivel, (vit, dex, inte) = estadisticas_mascota(o)
    torre = o.get("torre", 0) or 0
    fin = o.get("fin", 0) if torre else 946656000
    nom = textos.codificar(o.get("nombre", ""), 15) if llave("GRANJA_MASCOTAS") else b""     # FICHA 126: el apodo de la mascota (LEIDO 0x02736208: [u8 largo < 0x20][nombre])
    b = (struct.pack("<II", o["id"], o["index"]) + bytes([o.get("a", 1), nivel, 1 if torre else 0]) + struct.pack("<II", torre, fin & 0xFFFFFFFF)
         + bytes([0, len(nom)]) + nom + bytes([o.get("e", 1), o.get("f", 0)]) + struct.pack("<III", vit, dex, inte))
    assert len(b) == 35 + len(nom)
    return b


def _es_mascota(o):
    return 5000000 <= o["index"] < 5100000


def _look(c):
    """(char_id, [4 partes]) del personaje de la cuenta (como el FF77); lo que el 04 trae al final para dibujar el avatar."""
    pj = (c or {}).get("personaje") or {}
    partes = (list(pj.get("partes", [])) + [0] * 4)[:4]
    return pj.get("char_id", 0), [p & 0xFFFFFFFF for p in partes]


def cuerpo_04(usn, nick, g, var=None, look=None, ajeno=False, mascotas=None):
    """El cuerpo del S2C FF14C sub 04 (con el byte sub) para esta cuenta. ajeno=True (FICHA 108): es la granja de OTRO (el byte tras la hora vale 1:
    6 de 6 visitas del oficial; 0 en las propias); mascotas = lista de objetos-mascota para el n12 (si no, las del estado)."""
    var = variante() if var is None else var
    objs = g.get("objetos", []) if var >= 2 else []
    pets = mascotas if mascotas is not None else [o for o in objs if _es_mascota(o)]
    char_id, partes = look or (0, [0, 0, 0, 0])
    b = bytes([0x04, 0])                                         # sub, res 0
    b += struct.pack("<I", usn) + _dueno(nick, g.get("tamano", TAMANO_BASE), g)
    b += struct.pack("<H", len(objs)) + b"".join(_fila(o) for o in objs)      # n1: TODOS los objetos (mascota incluida)
    b += struct.pack("<H", 0)                                    # n2 (11 B)
    b += struct.pack("<H", 0)                                    # n3 (85 B)
    b += struct.pack("<I", ahora() & 0xFFFFFFFF) + bytes([1 if ajeno else 0])    # hora del servidor (1.er u32 de los 12 grabados: unix) y 0 = mia / 1 = ajena
    b += struct.pack("<H", len(pets)) + b"".join(_mascota(o) for o in pets)
    b += struct.pack("<H", 0)                                    # n28
    b += bytes([MASCOTA_MAX])                                    # byPetMaxExtensionCnt (16 en 12 de 12)
    b += struct.pack("<H", 0)                                    # n35
    b += struct.pack("<I", char_id) + struct.pack("<11I", *(partes + [0] * 7))   # personaje + ropa (como en las 12 grabadas)
    b += struct.pack("<I", 0)                                    # n39
    b += struct.pack("<I", 0)                                    # n41
    b += struct.pack("<I", 0)                                    # flag
    return b


def cuerpo_0f():
    return bytes([0x0F, 0])


def cuerpo_18(nick, g):
    return bytes([0x18]) + _dueno(nick, g.get("tamano", TAMANO_BASE), g) + bytes([0]) + struct.pack("<H", 0)


def cuerpo_14():
    return bytes([0x14]) + struct.pack("<I", ahora() & 0xFFFFFFFF)


def cuerpo_24(var=None):
    var = variante() if var is None else var
    if var >= 3:
        return bytes([0x24, 0]) + struct.pack("<H", 1) + bytes(29)
    return bytes([0x24, 0]) + struct.pack("<H", 0)


def cuerpo_05_ok(index, o, ahora):
    """65 B: [05][Index][u32 0][res 0][fila 38][u32 0][u8 0][u32 hora][u32 16][u32 -1] (LEIDO en 0x02737af0: el u32 y el u8
    tras la fila solo cuentan en la rama de error, la hora es el reloj del objeto, el 16 el tope de mascotas, -1 no toca nada)."""
    return (bytes([0x05]) + struct.pack("<IIB", index, 0, 0) + _fila(o) + struct.pack("<IBIII", 0, 0, ahora & 0xFFFFFFFF, MASCOTA_MAX, 0xFFFFFFFF))


def cuerpo_05_error(index, res):
    return bytes([0x05]) + struct.pack("<IIB", index, 0, res)


def cuerpo_0a(nick, g, tipo, dif, id_obj, nivel_nuevo=0):
    """72 B: [0a][u8 tipo][dueno 37 B ya actualizado][u8 nivel nuevo (0 = no subio)][7 x s32 diferencias][u32 id]. tipo 1 = construir
    (1 de 1 del oficial: energia -1, estrellas -200, madera -170, exp +1). nivel_nuevo = el nivel al que SUBIO (0 = no subio: el
    oficial lo manda en 2 con exp 5, 3 con exp 10 y 5 con exp 27, igual que la tabla de umbrales)."""
    return (bytes([0x0A, tipo]) + _dueno(nick, g.get("tamano", TAMANO_BASE), g) + bytes([nivel_nuevo & 255])
            + struct.pack("<7i", *(list(dif) + [0] * 7)[:7]) + struct.pack("<I", id_obj & 0xFFFFFFFF))


# ---------------------------------------------------------------- comprar y colocar (sub 05)
def comprar(usn, index, x, y, giro):
    """Con el candado: valida contra la tabla y el estado, cobra y agrega el objeto. Devuelve (res, objeto, g, dif, ahora).
    res 0 = bien; si no, el res del 05 de error (RES_*)."""
    hoy = ahora()
    fila = tienda().get(index)
    sal = {}

    def f(c):
        _preparar(c, hoy)
        px, py = x, y
        es_p = fila is not None and fila["fn"] == "P" and llave("GRANJA_MASCOTAS")       # FICHA 126: mascota de la tienda (Function P, estrellas)
        if fila is None or (fila["fn"] not in colocables() and not es_p) or fila["cash"] or fila["ancho"] < 1:
            return RES_FALLA
        if es_p and (fila["li"] <= 0 and fila["wi"] <= 0):          # las 20 de efectivo (CI, 6102) no traen LI / WI: no se pagan hoy
            return RES_FALLA
        if fila["nivel"] > nivel_de(c["exp"]):
            return RES_NIVEL
        if es_p:
            if sum(1 for o in c["objetos"] if _es_mascota(o)) >= c.get("lugares", LUGARES_BASE):
                return RES_FALLA                                    # sin lugar (el cliente ya lo avisa solo: ms 0x19d; LEIDO 0x0297885b)
            if not (0 <= x < c["tamano"] and 0 <= y < c["tamano"]):
                px, py = 14, 14                                     # INVENTADO: la celda de la primera mascota
        elif not (0 <= x < c["tamano"] and 0 <= y < c["tamano"]):
            return RES_FALLA
        medido = MEDIDO_COMPRA.get(index, {})
        energia, exp = medido.get("energia", fila["energia"]), medido.get("exp", fila["exp"])
        if c["energia"] < energia:
            return RES_ENERGIA
        if c["estrellas"] < fila["li"]:
            return RES_ESTRELLAS
        if c["madera"] < fila["wi"]:
            return RES_MADERA
        c["energia"] -= energia
        c["estrellas"] -= fila["li"]
        c["madera"] -= fila["wi"]
        nv0 = nivel_de(c["exp"])
        c["exp"] += exp
        sal["subio"] = subir_nivel(c, nv0, hoy)
        o = {"id": c["sig_id"], "index": index, "x": px, "y": py, "giro": giro & 255, "estado": "X", "t": 0, "u17": 0}
        if fila["fn"] in ("L", "W"):
            o["estado"] = "P"                                    # produciendo (el oficial: 'P' en los dos casos vistos de L)
            o["t"] = hoy + fila["obra"] + fila["ciclo"]        # 135 s = 15 + 120 en la unica muestra
        if fila["fn"] == "D":                                    # FICHA 119: defensa (nuez). MEDIDO con el juego: con u17 = 0 el cliente dibuja sobre ella un globo de
            o["u17"] = fila["salida"]                            # "escudo roto" y con u17 = Output (5) no. INVENTADO que u17 sea la durabilidad (Output = 5 en la tabla)
        c["sig_id"] += 1
        c["objetos"].append(o)
        sal["o"] = dict(o)
        sal["g"] = _copia(c)
        sal["dif"] = (-energia, -fila["li"], -fila["wi"], exp)
        if llave("GRANJA_MISIONES"):
            if es_p:                                             # FICHA 126: misiones buypet y `pet N` (tener N mascotas)
                sal["pasos"] = _evento(c, hoy, "buypet", index) + _evento(c, hoy, "pet", sum(1 for z in c["objetos"] if _es_mascota(z)))
            else:
                sal["pasos"] = _evento(c, hoy, "build", index)
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("o"), sal.get("g"), sal.get("dif"), hoy, sal.get("subio", 0), sal.get("pasos", [])


RES_NOMBRE_SIMBOLO, RES_NOMBRE_PROHIBIDO = 5, 6      # S2C 54: LEIDO 0x0273d681 (res 5 -> ms 459 "no se pueden usar simbolos fuera de [ ] - _ . *") y 0x0273d64e (res 6 -> ms 450 "lenguaje prohibido")


def cuerpo_51(pets):
    """S2C [51][u16 n][n x registro de mascota] (rx 0x0273e710; en las grabaciones 42 B = 1 + 2 + un registro de 35 B + 4 de nombre; sale con la adopcion). Cada
    registro es el del n12 del 04 (_mascota). HIPOTESIS que el oficial lo mande tras comprar en la tienda: se probo con el juego (ficha 126)."""
    return bytes([0x51]) + struct.pack("<H", len(pets)) + b"".join(_mascota(o) for o in pets)


def cuerpo_54(res, pet_id, nombre=b""):
    """S2C [54][u8 res][u32 mascota][u8 largo][nombre][u8 largo 2][texto 2] (rx 0x0273d380, LEIDO: dos cadenas de <= 16 B; con res 0 llama a 0x02969790(mascota,
    cadena 1) que pone el nombre en el registro (+0x7c); la 2.a cadena no se usa en res 0: va vacia, INVENTADO); res 5 / 6 = carteles; el resto "System Error :
    code N, petname"."""
    return bytes([0x54, res]) + struct.pack("<I", pet_id) + bytes([len(nombre)]) + nombre + bytes([0])


def nombrar(usn, pet_id, nombre):
    """C2S 54: pone el apodo a una mascota. Con el candado: la mascota existe y NO tiene apodo (el cliente lo ofrece solo la 1.a vez: "despues se puede usar la tarjeta
    de cambio de nombre", LEIDO en la ventana), 1..12 B en gbk (el cliente avisa "6 caracteres chinos, 12 ingleses"); solo letras / numeros / chinos y `[ ] - _ . *`
    (ms 459). Devuelve (res, objeto, pasos): 0 bien, RES_NOMBRE_SIMBOLO (5), RES_FALLA (3, INVENTADO: motivo no leido)."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        o = next((x for x in c["objetos"] if x["id"] == pet_id and _es_mascota(x)), None)
        if o is None or o.get("nombre") or not 1 <= len(nombre) <= 12:
            return RES_FALLA
        try:
            txt = textos.decodificar_estricto_gbk(nombre)     # ficha 141: GBK de siempre + las letras de 4 bytes
        except UnicodeDecodeError:
            return RES_NOMBRE_SIMBOLO
        if not all(ch.isalnum() or ch in "[ ]-_.*" for ch in txt):
            return RES_NOMBRE_SIMBOLO
        o["nombre"] = txt
        sal["o"] = dict(o)
        sal["pasos"] = _evento(c, hoy, "namepet", None) if llave("GRANJA_MISIONES") else []
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("o"), sal.get("pasos", [])


# ---------------------------------------------------------------- ranking (a1 / a5, ficha 126; llave GRANJA_RANKING, omision 0)
def ranking_dulces(usn):
    """Las cuentas locales con granja por dulces (mas primero; a igualdad, por usn): [(usn, nick, dulces)]."""
    filas = [(int(k), (a.get("cuenta") or {}).get("nick") or "", (a.get("granja") or {}).get("dulces", 0))
             for k, a in sorted(_cta.todas().items()) if (a.get("granja") or {}).get("version") == VERSION_ESTADO]
    filas.sort(key=lambda f: (-f[2], f[0]))
    return filas


def cuerpo_a1(usn):
    """S2C [a1][u32 n][n x 21 B] (rx 0x0273aea0, LEIDO): cada fila = [13 B apodo][u32 @13][u32 @17]; las 10 primeras van a la lista, la 11.a es la fila PROPIA (0x0273afbe: esi >= 10).
    La ventana (0x0298fe00 / 0x02990020) dibuja el apodo y itoa(u32 @13) = los dulces; el u32 @17 (= rec+0x1c) NO se vio usado: HIPOTESIS que sea el puesto. INVENTADO el orden
    por dulces y el puesto 1..n. SIN VER CON EL JUEGO: el boton Button_rank NO esta en ningun .rui de rnr_sng.pak (la ventana sng_ranking no se puede abrir)."""
    filas = ranking_dulces(usn)
    top = filas[:10]
    mia = next(((i + 1, f) for i, f in enumerate(filas) if f[0] == usn), None)

    def fila(puesto, f):
        return textos.codificar(f[1], 12).ljust(13, b"\x00") + struct.pack("<II", f[2] & 0xFFFFFFFF, puesto)
    cuerpos = [fila(i + 1, f) for i, f in enumerate(top)]
    if mia:                                                  # la fila propia es la 11.a: antes tienen que estar las 10 (INVENTADO: filas vacias de relleno)
        cuerpos += [bytes(21)] * (10 - len(cuerpos))
        cuerpos.append(fila(*mia))
    return bytes([0xA1]) + struct.pack("<I", len(cuerpos)) + b"".join(cuerpos)


def cuerpo_a5():
    """S2C [a5][u32 0]: la lista de mascotas (filas de 34 B, rx 0x0273b130) NO se descompuso: lista vacia (mejor que falte a que mienta)."""
    return bytes([0xA5]) + struct.pack("<I", 0)


def mover(usn, items):
    """Con el candado: mueve los objetos [(id, x, y, giro)] (todos o ninguno). Devuelve (res, items_validos)."""
    hoy = ahora()

    def f(c):
        _preparar(c, hoy)
        por_id = {o["id"]: o for o in c["objetos"]}
        for oid, x, y, giro in items:
            o = por_id.get(oid)
            if o is None or _es_mascota(o) or not (0 <= x < c["tamano"] and 0 <= y < c["tamano"]):
                return RES_FALLA
        for oid, x, y, giro in items:
            por_id[oid].update({"x": x, "y": y, "giro": giro & 255})
        return 0
    return _cta.cambiar_seccion(usn, "granja", f)


def cuerpo_09(items):
    """S2C [09][u8 res 0][u16 n][n x {u32 id, s8 x, s8 y, u8 giro}]: LEIDO en 0x02738bf0 (pone cada objeto donde dice);
    NO hay muestra del oficial: el eco de lo que pidio el cliente es INVENTADO."""
    return bytes([0x09, 0]) + struct.pack("<H", len(items)) + b"".join(struct.pack("<IbbB", i, x, y, g & 255) for i, x, y, g in items)


# ---------------------------------------------------------------- cosechar (sub 08) y vender (sub 0b)
def cosechar(usn, oid):
    """Con el candado y la hora del SERVIDOR: cosecha el edificio de produccion `oid` si ya termino su ciclo. Devuelve
    (res, g, dif, objeto, ahora, subio): res 0 = bien (el edificio vuelve a producir: fin = ahora + Cooltime de la tabla; da
    Output en estrellas si Function L o en madera si W, EXP, y cuesta IEnergy: 2 de 2 muestras del oficial); si no, el res:
    RES_ENERGIA (5, LEIDO: el cliente muestra el cartel de comprar energia) o RES_FALLA (3, INVENTADO: no existe, no es de
    produccion, no esta produciendo o todavia no termino)."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        o = next((x for x in c["objetos"] if x["id"] == oid), None)
        fila = tienda().get(o["index"]) if o else None
        if o is None or fila is None or fila["fn"] not in ("L", "W") or o.get("estado") != "P" or o.get("t", 0) > hoy:
            return RES_FALLA
        if c["energia"] < fila["i_energia"]:
            return RES_ENERGIA
        nv0 = nivel_de(c["exp"])
        c["energia"] -= fila["i_energia"]
        est = fila["salida"] if fila["fn"] == "L" else 0
        mad = fila["salida"] if fila["fn"] == "W" else 0
        c["estrellas"] += est
        c["madera"] += mad
        c["exp"] += fila["exp"]
        o["t"] = hoy + fila["ciclo"]
        o["u17"] = 0
        sal["subio"] = subir_nivel(c, nv0, hoy)
        sal["o"] = dict(o)
        sal["g"] = _copia(c)
        sal["dif"] = (-fila["i_energia"], est, mad, fila["exp"])
        if llave("GRANJA_MISIONES"):
            sal["pasos"] = _evento(c, hoy, "collect", o["index"])
            if _m2():                                            # FICHA 119: acumuladores star / wood (lo cosechado)
                sal["pasos"] += _evento(c, hoy, "star" if fila["fn"] == "L" else "wood", fila["salida"])
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("dif"), sal.get("o"), hoy, sal.get("subio", 0), sal.get("pasos", [])


def cuerpo_08(oid, t_fin, hoy):
    """S2C [08][u32 id][u8 res 0][u32 fin del proximo ciclo][u32 ahora] (14 B; 6 de 6 del oficial con fin - ahora = Cooltime)."""
    return bytes([0x08]) + struct.pack("<IBII", oid, 0, t_fin & 0xFFFFFFFF, hoy & 0xFFFFFFFF)


def vender(usn, oid):
    """Con el candado: vende un edificio colocado (L / W / T, no la mascota ni uno con una mascota entrenando) y devuelve el
    10 % de LI y de WI de la tabla (la ventana de venta del cliente lo dice: 20 y 17 para el 5100001, MEDIDO en la ficha 99).
    Devuelve (res, g, dif, objeto): res 0 = bien; si no RES_FALLA."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        o = next((x for x in c["objetos"] if x["id"] == oid), None)
        fila = tienda().get(o["index"]) if o else None
        if o is None or fila is None or _es_mascota(o) or fila["fn"] not in colocables() or o.get("estado") == "T":
            return RES_FALLA
        est, mad = fila["li"] // 10, fila["wi"] // 10
        c["objetos"].remove(o)
        c["estrellas"] += est
        c["madera"] += mad
        sal["o"] = dict(o)
        sal["g"] = _copia(c)
        sal["dif"] = (0, est, mad, 0)
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("dif"), sal.get("o")


# ---------------------------------------------------------------- terminar ya (sub 1d, ficha 119; llave GRANJA_TERMINAR_YA)
def terminar_ya(usn, oid):
    """C2S [1d][u32 id] (立即完成): con el candado, termina YA la produccion del edificio L / W propio `oid` (estado P con la hora de fin todavia por venir):
    cobra IEnergy / ILI / IWI de la tabla (LEIDO ficha 118: 36 de 36 edificios; en el TUTORIAL = hay una mision `collect` de Category tutorial activa
    sobre ese Index = cobro 0, como la unica muestra grabada) y deja la hora de fin en AHORA (el globo de cosecha sale y 08 cosecha). Devuelve
    (res, g, dif, objeto, ahora, pasos): res 0 = bien; RES_YA_COMPLETO (0x17, LEIDO) si ya termino; RES_ENERGIA / RES_MADERA / RES_ESTRELLAS (5 / 6 / 7,
    LEIDO: los mismos del 05) si no alcanza; RES_FALLA (3, LEIDO: el cliente no hace nada) si no existe, es ajeno o no es un edificio de produccion
    (INVENTADO que las torres T no se terminen con 1d: sin muestra)."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        o = next((x for x in c["objetos"] if x["id"] == oid), None)
        fila = tienda().get(o["index"]) if o else None
        if o is None or fila is None or fila["fn"] not in ("L", "W") or o.get("estado") != "P":
            return RES_FALLA
        if o.get("t", 0) <= hoy:
            return RES_YA_COMPLETO
        tabla = misiones_tabla()
        tut = any(tabla.get(a["q"], {}).get("cat") == "tutorial" and tabla[a["q"]]["goal"] == "collect" and tabla[a["q"]]["const"] == str(o["index"])
                  for a in _estado_misiones(c)["act"])
        ie, il, iw = (0, 0, 0) if tut else (fila["i_energia"], fila["i_li"], fila["i_wi"])
        if c["energia"] < ie:
            return RES_ENERGIA
        if c["estrellas"] < il:
            return RES_ESTRELLAS
        if c["madera"] < iw:
            return RES_MADERA
        c["energia"] -= ie
        c["estrellas"] -= il
        c["madera"] -= iw
        o["t"] = hoy
        sal["o"] = dict(o)
        sal["g"] = _copia(c)
        sal["dif"] = (-ie, -il, -iw, 0)
        sal["tut"] = tut
        if _m2():
            sal["pasos"] = _evento(c, hoy, "quickfinish", o["index"])
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("dif"), sal.get("o"), hoy, sal.get("pasos", [])


def cuerpo_1e(g, hoy):
    """S2C [1e][u32 A][u32 B] (LEIDO en 0x0273ce60): A = hora de la proxima energia, B = ahora. Con la energia llena no hay
    proxima: A = ahora - 1, y 0x02992df0 no toca el texto de la energia (A - B < 0)."""
    if g["energia"] >= g["energia_max"]:
        a = hoy - 1
    else:
        a = g.get("energia_t", hoy) + ENERGIA_CADA
    return bytes([0x1E]) + struct.pack("<II", a & 0xFFFFFFFF, hoy & 0xFFFFFFFF)


# ---------------------------------------------------------------- visitar (sub 04 con texto) y ayudar (sub 12) — ficha 108
ELEGIR = random.choice          # las pruebas lo cambian por una eleccion fija


def granja_npc(hoy):
    """La granja de %NPC% (la del tutorial). FORMA grabada del oficial (1 visita, usn 1): 4 objetos (mascota 14,14; queso 5100001 en 13,4 produciendo;
    torre 5200001 en 16,3 con una mascota entrenando y la hora de fin vieja; otra mascota 14,14), 2 mascotas, exp 0, energia 10/10, 3000 / 3000,
    tamano 28, sin personaje. Los Index salen de las tablas; los ids 1..4 y 9230/9250 y las posiciones son los grabados (ids de juego del NPC, no de
    una cuenta). INVENTADO: que la hora del queso sea ahora + 85 (en la muestra +85 s) y que la torre use una fecha vieja fija (1658470120)."""
    return {"exp": 0, "energia": 10, "energia_max": 10, "estrellas": 3000, "madera": 3000, "dulces": 0, "tamano": TAMANO_BASE,
            "objetos": [{"id": 1, "index": INDEX_MASCOTA, "x": 14, "y": 14, "giro": 0, "estado": "X", "t": 0, "u17": 0},
                        {"id": 2, "index": 5100001, "x": 13, "y": 4, "giro": 0, "estado": "P", "t": hoy + 85, "u17": 0},
                        {"id": 3, "index": 5200001, "x": 16, "y": 3, "giro": 0, "estado": "T", "t": 1658470120, "u17": NPC_PETS[0][0]},
                        {"id": 4, "index": INDEX_MASCOTA, "x": 14, "y": 14, "giro": 0, "estado": "X", "t": 0, "u17": 0}]}


def mascotas_npc():
    return [{"id": i, "index": INDEX_MASCOTA, "a": a, "e": e, "f": f} for i, a, e, f in NPC_PETS]


def buscar_visita(usn, texto):
    """Quien se visita con ese texto del C2S 04 (bytes). Devuelve (res, destino): res 0 con destino {usn, nick, g, look, npc, tipo}, o el res del 04:
    RES_NO_HAY_AZAR (0x16, %RANDOM% sin otra cuenta local con granja: LEIDO) / RES_NO_EXISTE (0x0d: el apodo no es de una cuenta local con granja, o
    es la propia). %NPC% = granja_npc; un apodo o %RANDOM% = el estado GUARDADO de otra cuenta local (solo se mira; nada se escribe)."""
    hoy = ahora()
    if texto == b"%NPC%":
        return 0, {"usn": NPC_USN, "nick": NPC_NICK, "g": granja_npc(hoy), "look": (0, [0, 0, 0, 0]), "npc": True, "tipo": "npc"}
    otras = [(int(k), a) for k, a in sorted(_cta.todas().items()) if int(k) != usn and (a.get("granja") or {}).get("version") == VERSION_ESTADO]
    if texto == b"%RANDOM%":
        if not otras:
            return RES_NO_HAY_AZAR, None
        k, a = ELEGIR(otras)
        tipo = "random"
    else:
        nick = textos.decodificar(texto)
        elegida = [(k, a) for k, a in otras if (a.get("cuenta") or {}).get("nick") == nick]
        if not elegida:
            return RES_NO_EXISTE, None
        k, a = elegida[0]
        tipo = "friend"
    g = _copia(a["granja"])
    _regenerar(g, hoy)
    return 0, {"usn": k, "nick": (a.get("cuenta") or {}).get("nick") or "", "g": g, "look": _look(a), "npc": False, "tipo": tipo}


def _dia(hoy):
    return time.strftime("%Y%m%d", time.localtime(hoy))


def trabajar(usn, dest, oid, hoy=None):
    """C2S 12 [1][id]: ayudar (打工) en un edificio de la granja visitada. Con el candado, en la granja PROPIA: paga 200 estrellas (edificio L) o 100
    madera (W) y +1 dulce (0a tipo 6: 2 de 2 muestras del oficial, valores de INVENTADO fuera de ahi) y cuenta 1 en el dia (una vez por edificio y a
    lo sumo TRABAJO_MAX_DIA por dia: INVENTADO; en %NPC% no cuenta, como el 17 con 0 de la muestra). El edificio debe existir y producir.
    Devuelve (res, cantidad X = 1,1 x Output, cuenta del dia, g, dif, ahora): res 0 = bien, si no RES_FALLA."""
    hoy = ahora() if hoy is None else hoy
    o = next((x for x in dest["g"]["objetos"] if x["id"] == oid), None)
    fila = tienda().get(o["index"]) if o else None
    if o is None or fila is None or fila["fn"] not in ("L", "W") or o.get("estado") != "P":
        return RES_FALLA, 0, 0, None, None, hoy
    est = TRABAJO_ESTRELLAS if fila["fn"] == "L" else 0
    mad = TRABAJO_MADERA if fila["fn"] == "W" else 0
    sal = {}
    clave = "%d:%d" % (dest["usn"], oid)

    def f(c):
        _preparar(c, hoy)
        ar = c.setdefault("trabajo", {"dia": "", "n": 0, "ya": []})
        if ar["dia"] != _dia(hoy):
            ar.update({"dia": _dia(hoy), "n": 0, "ya": []})
        if not dest["npc"]:
            if clave in ar["ya"] or ar["n"] >= TRABAJO_MAX_DIA:
                return RES_FALLA
            ar["ya"].append(clave)
            ar["n"] += 1
        c["estrellas"] += est
        c["madera"] += mad
        c["dulces"] += TRABAJO_DULCES
        sal["g"] = _copia(c)
        sal["n"] = 0 if dest["npc"] else ar["n"]
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    if res:
        return res, 0, 0, None, None, hoy
    return 0, fila["salida"] * 11 // 10, sal["n"], sal["g"], (0, est, mad, 0, TRABAJO_DULCES, 0, 0), hoy


def cuerpo_12_ok(oid, cantidad, nick, usn):
    """S2C 12 con res 0 (22 B en la muestra con apodo de 7): [00][u32 id][u32 cantidad = 1,1 x Output (MEDIDO 49 = 1,1 x 45, 9460 y 3080 en otra
    sesion)][u8 largo][apodo de QUIEN AYUDA][u32 usn de quien ayuda]. LEIDO en 0x02739690: el cliente compara ese ultimo u32 con SU usn y solo
    entonces pasa a modo ayudar (G+0x12bb0 = 1); MEDIDO: es el usn del que ayuda (1099194 = el usn del propio 04)."""
    n = textos.codificar(nick, 17)
    return bytes([0x12, 0]) + struct.pack("<II", oid, cantidad) + bytes([len(n)]) + n + struct.pack("<I", usn & 0xFFFFFFFF)


# ---------------------------------------------------------------- misiones (ficha 104; llave GRANJA_MISIONES)
def misiones_tabla():
    """{questID: fila} de farmquest.txt (448 filas), en el ORDEN de la tabla (la entrega usa ese orden: 3 de 3 y 3 de 3 del oficial).
    fila = {q, goal, const, cum, pre (texto), L, W, exp, dul, cat, orden}. {} si el archivo no esta."""
    if _QUEST:
        return _QUEST
    for ruta in _RUTAS_QUEST:
        try:
            txt = open(ruta, "rb").read().decode("gb18030", errors="replace")
        except OSError:
            continue
        for k, m in enumerate(re.findall(r"<quest\s([^>]*)>", txt)):
            r = dict(re.findall(r'(\w+)="([^"]*)"', m))
            try:
                q = int(r["questID"])
                _QUEST[q] = {"q": q, "goal": r.get("Goal", ""), "const": r.get("Constant", ""), "cum": int(r.get("Cumulate", "1") or 1),
                             "pre": r.get("Prerequisite", ""), "L": int(r.get("RewardLemons", "0") or 0), "W": int(r.get("RewardWoods", "0") or 0),
                             "exp": int(r.get("RewardExp", "0") or 0), "dul": int(r.get("RewardCandies", "0") or 0),
                             "cat": r.get("Category", ""), "orden": k}
            except (KeyError, ValueError):
                continue
        break
    return _QUEST


def _estado_misiones(c):
    """Las misiones de la cuenta dentro de la seccion granja: {init, sig, act: [{s, q}], hechas: [questID]}."""
    return c.setdefault("misiones", {"init": False, "sig": 1, "act": [], "hechas": []})


def _prerequisito(c, pre):
    """True si se cumplen TODOS los requisitos del texto (coma). farmlevel / quest / hasbuild / nothasbuild / haspet salen del estado;
    petlevel: las mascotas no suben de nivel todavia (entrenar no esta hecho): nivel 1 (INVENTADO); firstquest: siempre (la entrega no
    repite lo hecho o activo); adultpet y lo desconocido: False (no se entrega)."""
    for tok in [t.strip() for t in pre.split(",") if t.strip()]:
        k, _, v = tok.partition(":")
        k = k.lower() if llave("GRANJA_MISIONES2") else k          # FICHA 119: `Farmlevel:` con F mayuscula (4 filas diarias)
        try:
            n = int(v) if v else 0
        except ValueError:
            return False
        if k == "firstquest":
            continue
        if k == "quest":
            if n not in c["misiones"]["hechas"]:
                return False
        elif k == "farmlevel":
            if nivel_de(c["exp"]) < n:
                return False
        elif k == "hasbuild":
            if not any(o["index"] == n for o in c["objetos"]):
                return False
        elif k == "nothasbuild":
            if any(o["index"] == n for o in c["objetos"]):
                return False
        elif k == "haspet":
            if not any(o["index"] == n and _es_mascota(o) for o in c["objetos"]):
                return False
        elif k == "petlevel":
            if not any(_es_mascota(o) and nivel_mascota(o.get("exp", 0)) >= n for o in c["objetos"]):      # ficha 108: las mascotas suben entrenando
                return False
        else:
            return False
    return True


def _registro(serial, q, estado):
    """Registro de mision de 32 B (LEIDO en 0x0273a4d0; 45 de 45 casan con la tabla): [u32 serial][u32 questID][u32 estado][u32 -1][16 B Constant]."""
    const = misiones_tabla().get(q, {}).get("const", "")
    return struct.pack("<IIII", serial, q, estado, 0xFFFFFFFF) + const.encode("ascii", "replace")[:15].ljust(16, b"\x00")


def _entregar(c):
    """Activa las misiones REGULARES (questID / 10^7 == 1) cuyo requisito se cumple y que no estan activas ni hechas, en el orden de la
    tabla. Devuelve [(serial, questID)] nuevas. Las diarias (2...) y repentinas (3...) no se entregan: sin muestra de como se reparten."""
    m = _estado_misiones(c)
    ya = set(m["hechas"]) | {a["q"] for a in m["act"]}
    nuevas = []
    for q, fila in misiones_tabla().items():
        if q // 10000000 != 1 or q in ya or not _prerequisito(c, fila["pre"]):
            continue
        a = {"s": m["sig"], "q": q}
        m["sig"] += 1
        m["act"].append(a)
        nuevas.append((a["s"], q))
    return nuevas


def _cumple(fila, kind, dato):
    """Un evento (kind, dato) cumple la mision? SOLO Cumulate 1. build / collect: Constant = Index del edificio; expand: Constant k = tamano
    28 + 2k (MEDIDO k=1 -> 30; las otras 5 filas, HIPOTESIS). FICHA 108: train (Constant = Index de la torre, o `none` = cualquiera), visit y hammer
    (Constant `npc` / `random` / `friend` = a quien se visita o en cuya granja se clava) se cumplen con su evento; sin dato (las pruebas viejas) cuenta
    cualquiera."""
    if fila["cum"] != 1 or fila["goal"] != kind:
        return False
    if kind in ("build", "collect"):
        return fila["const"] == str(dato)
    if kind == "expand":
        return fila["const"].isdigit() and 28 + 2 * int(fila["const"]) == dato
    if kind == "train":
        return dato is None or fila["const"] in ("none", str(dato))
    if kind in ("visit", "hammer"):
        return dato is None or fila["const"] == dato
    if kind == "petlevel":                                    # Constant = nivel que tiene que alcanzar una mascota (11500159: 2)
        return dato is None or (fila["const"].isdigit() and dato >= int(fila["const"]))
    if kind in ("buypet", "namepet"):                         # FICHA 126: Constant `none`
        return True
    if kind in ("pet", "petslot"):                            # FICHA 126: `pet N` = tener N mascotas, `petslot N` = abrir el lugar N (dato = la cuenta que hay)
        return fila["const"].isdigit() and dato is not None and dato >= int(fila["const"])
    return False


def _m2():
    """La ronda 2 del motor de misiones (ficha 119): Cumulate > 1 con contador por mision y los eventos arrange / sell / star / wood / arbeit / quickfinish."""
    return llave("GRANJA_MISIONES") and llave("GRANJA_MISIONES2")


def _aporte(fila, kind, dato):
    """FICHA 119 (ronda 2): cuanto suma el evento (kind, dato) a la mision `fila` (0 = no la toca). Los viejos (build, collect, expand, train, visit,
    hammer, petlevel) suman 1 con las mismas reglas que _cumple pero ya CON Cumulate > 1 (el contador lo lleva _evento); nuevos: arrange (una orden de
    mover, 09) y sell (0b) suman 1; star / wood suman lo cosechado (`dato` = cantidad: INVENTADO que cuente solo lo cosechado); arbeit (12) y quickfinish (1d):
    Constant `random` / `friend` (en %NPC% el dato es `npc`: ninguna fila lo usa) o el Index (o `production` / `training`). El cliente no ve nada de esto (el contador es del servidor)."""
    if fila["goal"] != kind or fila["cum"] < 1:
        return 0
    if kind in ("star", "wood"):
        return int(dato) if isinstance(dato, int) and dato > 0 else 0
    if kind in ("arrange", "sell"):
        return 1
    if kind == "arbeit":
        return 1 if fila["const"] == dato else 0
    if kind == "quickfinish":
        fn = tienda().get(dato, {}).get("fn")
        return 1 if (fila["const"] == str(dato) or (fila["const"] == "production" and fn in ("L", "W")) or (fila["const"] == "training" and fn == "T")) else 0
    if kind == "petlevel":
        return 1 if (dato is None or (fila["const"].isdigit() and dato >= int(fila["const"]))) else 0
    return 1 if _cumple(dict(fila, cum=1), kind, dato) else 0


def _evento(c, hoy, kind, dato):
    """Dentro del candado: revisa las misiones activas con el evento (kind, dato). Por cada una cumplida (en el orden de la lista): la saca de
    las activas, paga el premio de la TABLA (estrellas, madera, exp, dulces; sube de nivel si toca) y entrega las nuevas. Devuelve la lista
    de pasos {serial, q, g (estado tras el premio), dif, nivel, nuevas: [(serial, q)]} que mensajes_pasos convierte en 10, 11, 0a tipo 5 y 0e.
    FICHA 119 (GRANJA_MISIONES2): una de `Cumulate` > 1 guarda su cuenta `n` en la mision activa (se guarda en la cuenta: sobrevive al reinicio) y
    se cumple al llegar a `Cumulate`."""
    if not llave("GRANJA_MISIONES"):
        return []
    m = _estado_misiones(c)
    tabla = misiones_tabla()
    pasos = []
    if _m2():
        hechas = []
        for a in list(m["act"]):
            fila = tabla.get(a["q"])
            if fila is None:
                continue
            suma = _aporte(fila, kind, dato)
            if not suma:
                continue
            a["n"] = a.get("n", 0) + suma
            if a["n"] >= fila["cum"]:
                hechas.append(a)
    else:
        hechas = [x for x in m["act"] if _cumple(tabla.get(x["q"], {"cum": 0, "goal": ""}), kind, dato)]
    for a in hechas:
        fila = tabla[a["q"]]
        m["act"].remove(a)
        m["hechas"].append(a["q"])
        nv0 = nivel_de(c["exp"])
        c["estrellas"] += fila["L"]
        c["madera"] += fila["W"]
        c["exp"] += fila["exp"]
        c["dulces"] += fila["dul"]
        subio = subir_nivel(c, nv0, hoy)
        nuevas = _entregar(c)
        pasos.append({"serial": a["s"], "q": a["q"], "g": _copia(c), "dif": (0, fila["L"], fila["W"], fila["exp"], fila["dul"], 0, 0),
                      "nivel": subio, "nuevas": nuevas})
    return pasos


def evento(usn, kind, dato=None):
    """Para quien atienda otros disparadores (entrenar, visitar, ayudar: fichas siguientes) y para las pruebas: con el candado, aplica el
    evento a las misiones de la cuenta. Devuelve los pasos (ver _evento)."""
    hoy = ahora()

    def f(c):
        _preparar(c, hoy)
        return _evento(c, hoy, kind, dato)
    return _cta.cambiar_seccion(usn, "granja", f)


def mensajes_pasos(nick, pasos):
    """Los mensajes S2C de cada paso, en el orden MEDIDO del oficial: 10 (estado 1), 11 (res 0), 0a tipo 5, y las 0e de las nuevas."""
    out = []
    for p in pasos:
        out.append(bytes([0x10]) + _registro(p["serial"], p["q"], 1))
        out.append(bytes([0x11, 0]) + struct.pack("<I", p["serial"]))
        out.append(cuerpo_0a(nick, p["g"], 5, p["dif"], p["serial"], p["nivel"]))
        out.extend(bytes([0x0E]) + _registro(s_, q, 0) for s_, q in p["nuevas"])
    return out


def abrir_misiones(usn):
    """Al abrir la granja propia: (lista de registros del 0f, nuevas por 0e). La primera vez (como el oficial: 0f vacia y despues las
    iniciales por 0e) se entregan las misiones que ya correspondan; despues el 0f trae las activas."""
    hoy = ahora()

    def f(c):
        _preparar(c, hoy)
        m = _estado_misiones(c)
        if not m["init"]:
            m["init"] = True
            return [], _entregar(c)
        return [(a["s"], a["q"]) for a in m["act"]], []
    return _cta.cambiar_seccion(usn, "granja", f)


def cuerpo_0f_lista(lista):
    """[0f][u8 n][n x 32 B] (LEIDO en 0x0273a4d0)."""
    return bytes([0x0F, len(lista) & 255]) + b"".join(_registro(s_, q, 0) for s_, q in lista)


def _mandar_pasos(con, seq, nick, pasos):
    """Las misiones cumplidas por una accion (10, 11, 0a tipo 5, 0e) van DESPUES de los mensajes de la accion, como en el oficial."""
    for cu in mensajes_pasos(nick, pasos):
        con.mandar_interno(0x14C, seq, cu)
    for p in pasos:
        anotar("   S2C FF14C mision %d cumplida (serial %d): premio %s, nuevas %s" % (p["q"], p["serial"], p["dif"][:5], [q for s_, q in p["nuevas"]]))


def clavar(usn):
    """Con el candado: +1 dulce (0a tipo 15 del oficial: dulces +1, 1 de 1) y un numero de clavo por cuenta (INVENTADO: el contador del oficial era global).
    Devuelve (numero de clavo, g)."""
    sal = {}

    def f(c):
        _preparar(c, ahora())
        c["dulces"] += 1
        c["sig_clavo"] = c.get("sig_clavo", 0) + 1
        sal["n"] = c["sig_clavo"]
        sal["g"] = _copia(c)
        return 0
    _cta.cambiar_seccion(usn, "granja", f)
    return sal["n"], sal["g"]


def mensajes_clavo(nick, g, usn, item, n_clavo, x, y, texto):
    """Respuesta a C2S a8 [u32 Index del clavo][s8 x][s8 y][u8 giro][u8 largo][texto] (11 B con "22"; el oficial: a2 de 44 B, a3 de 9 B y el 0a tipo 15 con el
    Index del clavo como id). a2 = [00][u32 usn de quien clava][u32 Index][u32 numero de clavo][s8 x][s8 y][11 B en 0][0x58][apodo 16 B] (LEIDO en
    0x0273b530: el cliente compara el usn con el suyo; el 0x58 y los ceros se copian de la muestra, HIPOTESIS); a3 = [00][u32 numero de clavo][u8 largo][texto]."""
    nk = textos.codificar(nick, 15)
    a2 = (bytes([0xA2, 0]) + struct.pack("<III", usn & 0xFFFFFFFF, item, n_clavo) + struct.pack("<bb", x, y) + bytes(11) + bytes([0x58]) + nk.ljust(16, b"\x00"))
    a3 = bytes([0xA3, 0]) + struct.pack("<I", n_clavo) + bytes([len(texto)]) + texto
    return [a2, a3, cuerpo_0a(nick, g, 15, (0, 0, 0, 0, 1, 0, 0), item)]


# ---------------------------------------------------------------- ampliar (sub 0c)
def ampliar(usn, tam):
    """Con el candado: amplia la granja al tamano `tam` (la siguiente al actual, de a 2) cobrando el LI / WI del ticket de la tabla y
    exigiendo su nivel. Devuelve (res, g, dif, ahora, pasos): res 0 = bien; RES_ORDEN (8) si no es la siguiente; RES_FALLA (3, INVENTADO) si
    no hay ticket vendible de ese tamano, no alcanza el nivel o faltan estrellas / madera."""
    hoy = ahora()
    sal = {}

    def f(c):
        _preparar(c, hoy)
        if tam not in TICKETS or tam <= c["tamano"]:
            return RES_FALLA
        if tam != c["tamano"] + 2:
            return RES_ORDEN
        fila = tienda().get(TICKETS[tam])
        if fila is None or fila["fn"] != "E" or fila["cash"] or fila["nivel"] > nivel_de(c["exp"]):
            return RES_FALLA
        if c["estrellas"] < fila["li"] or c["madera"] < fila["wi"]:
            return RES_FALLA
        c["estrellas"] -= fila["li"]
        c["madera"] -= fila["wi"]
        c["tamano"] = tam
        sal["g"] = _copia(c)
        sal["dif"] = (0, -fila["li"], -fila["wi"], 0, 0, 2, 0)
        if llave("GRANJA_MISIONES"):
            sal["pasos"] = _evento(c, hoy, "expand", tam)
        return 0
    res = _cta.cambiar_seccion(usn, "granja", f)
    return res, sal.get("g"), sal.get("dif"), hoy, sal.get("pasos", [])


def _usn_nick(con):
    c = con.cuenta or {}
    return c.get("usn"), c.get("nick") or ""


def farm_forward(con, seq, cuerpo):
    """C2S FF14C [sub][args]: 04 (abrir), 05 (comprar y colocar), 08 (cosechar), 09 (mover), 0b (vender), 0c (ampliar, GRANJA_MISIONES), 14 (hora), 1e (energia), 24 (lista); los demas sub: sin atender."""
    if not llave() or not cuerpo:
        return False
    usn, nick = _usn_nick(con)
    if usn is None:
        return False
    sub = cuerpo[0]
    ajena = getattr(con, "granja_ajena", None)          # FICHA 108: la granja AJENA que esta viendo esta conexion (None = la propia)
    if ajena is not None and sub in (0x05, 0x08, 0x09, 0x0B, 0x0C, 0x59):
        anotar("   FF14C sub 0x%02x ignorado: se esta viendo la granja de otro (%s)" % (sub, ajena["nick"]))
        return True
    if sub == 0x04:
        largo = cuerpo[1] if len(cuerpo) > 1 else 0
        if largo:
            res, dest = buscar_visita(usn, bytes(cuerpo[2:2 + largo]))
            if res:
                con.granja_ajena = None
                con.mandar_interno(0x14C, seq, bytes([0x04, res]))
                anotar("   S2C FF14C 04 visitar %r: res 0x%02x (%s)" % (bytes(cuerpo[2:2 + largo]), res, "sin granja al azar" if res == RES_NO_HAY_AZAR else "no existe"))
                return True
            con.granja_ajena = dest
            con.trabajo_listo = None
            con.clavo = False
            g_propia = estado_de(usn)
            con.mandar_interno(0x14C, seq, cuerpo_04(dest["usn"], dest["nick"], dest["g"], look=dest["look"], ajeno=True,
                                                     mascotas=mascotas_npc() if dest["npc"] else None))
            con.mandar_interno(0x14C, seq, cuerpo_18(nick, g_propia))
            pasos = evento(usn, "visit", dest["tipo"]) if llave("GRANJA_MISIONES") else []
            _mandar_pasos(con, seq, nick, pasos)
            anotar("   S2C FF14C 04 visitar (%s) a %s: %d objetos + 18 propio%s" % (dest["tipo"], dest["nick"], len(dest["g"]["objetos"]),
                                                                              ", mision %s" % [p["q"] for p in pasos] if pasos else ""))
            return True
        con.granja_ajena = None
        g = estado_de(usn)
        r = cuerpo_04(usn, nick, g, look=_look(con.cuenta))
        con.mandar_interno(0x14C, seq, r)
        if llave("GRANJA_MISIONES"):
            lista, nuevas = abrir_misiones(usn)
            con.mandar_interno(0x14C, seq, cuerpo_0f_lista(lista))
            con.mandar_interno(0x14C, seq, cuerpo_18(nick, g))
            for s_, q in nuevas:
                con.mandar_interno(0x14C, seq, bytes([0x0E]) + _registro(s_, q, 0))
            anotar("   S2C FF14C misiones: 0f con %d activas, %d nuevas por 0e %s" % (len(lista), len(nuevas), [q for s_, q in nuevas]))
        else:
            con.mandar_interno(0x14C, seq, cuerpo_0f())
            con.mandar_interno(0x14C, seq, cuerpo_18(nick, g))
        anotar("   S2C FF14C 04 abrir granja de %s: variante %d, %d B, %d objetos + 0f + 18 (INVENTADO el estado inicial)"
               % (nick, variante(), len(r), len(g.get("objetos", []))))
        return True
    if sub == 0x59 and len(cuerpo) == 10 and cuerpo[1] in (0x81, 0x85) and llave("GRANJA_COMPRA"):
        pet_id, torre_id = struct.unpack_from("<II", cuerpo, 2)
        if cuerpo[1] == 0x81:
            res, g, fila, idx, hoy, fin, pasos = entrenar(usn, pet_id, torre_id)
            if res:
                con.mandar_interno(0x14C, seq, bytes([0x59, res]) + struct.pack("<II", pet_id, torre_id) + bytes(49))
                anotar("   S2C FF14C 59 entrenar mascota %d en la torre %d: res %d (no se cobro)" % (pet_id, torre_id, res))
                return True
            for m in mensajes_entrenar(nick, g, fila, pasos, cuerpo_59(0, pet_id, torre_id, hoy, idx, fin, fila)):
                con.mandar_interno(0x14C, seq, m)
            anotar("   S2C FF14C 59 entrenar mascota %d en la torre %d (Index %d): -%d energia -%d estrellas, termina en %d s%s"
                   % (pet_id, torre_id, idx, fila["energia"], fila["precio"], fin - hoy, ", mision %s" % [p["q"] for p in pasos] if pasos else ""))
            return True
        res, g, fila, idx, hoy, fin, nivel, ganado, pasos, nuevas = cobrar_entrenamiento(usn, pet_id, torre_id)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x59, res]) + struct.pack("<II", pet_id, torre_id) + bytes(49))
            anotar("   S2C FF14C 59 cobrar mascota %d en la torre %d: res %d (todavia no / no coincide)" % (pet_id, torre_id, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_59(RES_TERMINO, pet_id, torre_id, hoy, idx, fin, fila, nivel, ganado))
        _mandar_pasos(con, seq, nick, pasos)
        for s_, q in nuevas:
            con.mandar_interno(0x14C, seq, bytes([0x0E]) + _registro(s_, q, 0))
        anotar("   S2C FF14C 59 cobrar mascota %d en la torre %d: +%d piezas +%d EXP, nivel %d (HIPOTESIS: res 0x14)%s"
               % (pet_id, torre_id, ganado[0], ganado[1], nivel, ", mision %s" % [p["q"] for p in pasos] if pasos else ""))
        return True
    if sub == 0x12 and len(cuerpo) == 6 and cuerpo[1] in (0, 1) and ajena is not None and llave("GRANJA_COMPRA"):
        oid = struct.unpack_from("<I", cuerpo, 2)[0]
        if cuerpo[1] == 0:
            o = next((x for x in ajena["g"]["objetos"] if x["id"] == oid), None)
            fila = tienda().get(o["index"]) if o else None
            if o is None or fila is None or fila["fn"] not in ("L", "W") or o.get("estado") != "P":
                con.mandar_interno(0x14C, seq, bytes([0x12, RES_FALLA]) + struct.pack("<I", oid))
                anotar("   S2C FF14C 12 ayudar (pedido) id %d: res %d (no produce)" % (oid, RES_FALLA))
            else:
                con.trabajo_listo = oid
                con.mandar_interno(0x14C, seq, bytes([0x12, RES_12_LISTO]) + struct.pack("<I", oid))
                anotar("   S2C FF14C 12 ayudar (pedido) id %d: res 0x2e" % oid)
            return True
        if getattr(con, "trabajo_listo", None) != oid:
            con.mandar_interno(0x14C, seq, bytes([0x12, RES_FALLA]) + struct.pack("<I", oid))
            anotar("   S2C FF14C 12 ayudar id %d: res %d (sin pedido previo)" % (oid, RES_FALLA))
            return True
        res, cant, n, g, dif, hoy = trabajar(usn, ajena, oid)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x12, res]) + struct.pack("<I", oid))
            anotar("   S2C FF14C 12 ayudar id %d: res %d (ya ayudaste hoy / sin cupo)" % (oid, res))
            return True
        con.clavo = ajena["npc"]                      # el clavo solo se puede usar en %NPC% (en una granja de verdad no se atiende)
        con.mandar_interno(0x14C, seq, cuerpo_12_ok(oid, cant, nick, usn))
        con.mandar_interno(0x14C, seq, bytes([0x17, n & 255]))
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 6, dif, oid))
        anotar("   S2C FF14C 12 ayudar id %d: %s (12 + 17 con %d + 0a tipo 6)" % (oid, dif, n))
        if _m2():                                                # FICHA 119: evento `arbeit` (random / friend; el NPC no cuenta)
            _mandar_pasos(con, seq, nick, evento(usn, "arbeit", ajena["tipo"]))
        return True
    if sub == 0xA7 and len(cuerpo) == 1 and ajena is not None and llave("GRANJA_COMPRA"):
        # C2S a7 (1 B, el boton 钉钉子): el oficial contesto a2 [0x20] (MEDIDO 1 de 1). LEIDO 0x0273b74a: con res 0x20 en una granja ajena el cliente no hace nada.
        con.mandar_interno(0x14C, seq, bytes([0xA2, 0x20]))
        anotar("   S2C FF14C a2 0x20 (boton de clavar)")
        return True
    if sub == 0xA8 and len(cuerpo) >= 9 and ajena is not None and ajena["npc"] and getattr(con, "clavo", False) and llave("GRANJA_COMPRA"):
        item, cx, cy, giro, largo = struct.unpack_from("<IbbBB", cuerpo, 1)
        texto = bytes(cuerpo[9:9 + largo])
        if len(cuerpo) != 9 + largo or item != CLAVO_INDEX:
            anotar("   FF14C a8 con forma rara (%d B, Index %d): SIN ATENDER" % (len(cuerpo), item))
            return False
        con.clavo = False
        n_clavo, g = clavar(usn)
        for m in mensajes_clavo(nick, g, usn, item, n_clavo, cx, cy, texto):
            con.mandar_interno(0x14C, seq, m)
        pasos = evento(usn, "hammer", "npc") if llave("GRANJA_MISIONES") else []
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C a8 clavar en %d,%d (%d B de texto): a2 + a3 + 0a tipo 15%s" % (cx, cy, len(texto), ", mision %s" % [p["q"] for p in pasos] if pasos else ""))
        return True
    if sub == 0x1D and len(cuerpo) == 5 and llave("GRANJA_COMPRA") and llave("GRANJA_TERMINAR_YA"):
        oid = struct.unpack_from("<I", cuerpo, 1)[0]
        if ajena is not None:
            anotar("   FF14C sub 0x1d ignorado: se esta viendo la granja de otro (%s)" % ajena["nick"])
            return True
        res, g, dif, o, hoy, pasos = terminar_ya(usn, oid)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x1D]) + struct.pack("<IB", oid, res))
            anotar("   S2C FF14C 1d terminar ya id %d: res %d (no se cobro)" % (oid, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 9, dif, oid))
        con.mandar_interno(0x14C, seq, bytes([0x1D]) + struct.pack("<IB", oid, 0))
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C 1d terminar ya id %d (Index %d): %s, estrellas %d madera %d energia %d (0a tipo 9 + 1d res 0)"
               % (oid, o["index"], dif, g["estrellas"], g["madera"], g["energia"]))
        return True
    if sub == 0x05 and len(cuerpo) == 13 and llave("GRANJA_COMPRA"):
        index, x, y, giro = struct.unpack_from("<Ibbb", cuerpo, 1)
        res, o, g, dif, ahora_, subio, pasos = comprar(usn, index, x, y, giro)
        if res:
            con.mandar_interno(0x14C, seq, cuerpo_05_error(index, res))
            anotar("   S2C FF14C 05 comprar Index %d en %d,%d: res %d (no se cobro)" % (index, x, y, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_05_ok(index, o, ahora_))
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 1, dif, o["id"], subio))
        if llave("GRANJA_MASCOTAS") and _es_mascota(o):          # FICHA 126: el registro de la mascota nueva (rx 0x51 = lista de registros como el n12 del 04)
            con.mandar_interno(0x14C, seq, cuerpo_51([o]))
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C 05 comprar Index %d en %d,%d: objeto %d, estrellas %d madera %d energia %d (05 65 B + 0a 72 B)"
               % (index, x, y, o["id"], g["estrellas"], g["madera"], g["energia"]))
        return True
    if sub in (0xA1, 0xA5) and len(cuerpo) == 1 and llave("GRANJA_COMPRA") and llave("GRANJA_RANKING"):
        # C2S a1 / a5 (1 B, LEIDO 0x0273ae55: solo el sub): ranking de dulces / de mascotas. SIN VER CON EL JUEGO (no hay boton que lo mande: ver cuerpo_a1)
        con.mandar_interno(0x14C, seq, cuerpo_a1(usn) if sub == 0xA1 else cuerpo_a5())
        anotar("   S2C FF14C %02x ranking (%s)" % (sub, "dulces de las cuentas locales con granja" if sub == 0xA1 else "lista vacia"))
        return True
    if sub == 0x54 and 6 <= len(cuerpo) <= 6 + 40 and llave("GRANJA_COMPRA") and llave("GRANJA_MASCOTAS"):
        # C2S 54 [u32 mascota][u8 largo][nombre] (MEDIDO con el juego: 13 B con "Naranja"; el cliente lo manda al apretar 确认 en la ventana 宠物昵称 que abre solo tras comprar una mascota)
        pet_id, largo = struct.unpack_from("<IB", cuerpo, 1)
        nombre = bytes(cuerpo[6:6 + largo])
        if len(cuerpo) != 6 + largo:
            anotar("   FF14C 54 con forma rara (%d B, largo %d): SIN ATENDER" % (len(cuerpo), largo))
            return False
        res, o, pasos = nombrar(usn, pet_id, nombre)
        con.mandar_interno(0x14C, seq, cuerpo_54(res, pet_id, nombre if not res else b""))
        if res:
            anotar("   S2C FF14C 54 nombrar mascota %d: res %d (no se guardo)" % (pet_id, res))
            return True
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C 54 nombrar mascota %d: %r%s" % (pet_id, nombre, ", mision %s" % [p["q"] for p in pasos] if pasos else ""))
        return True
    if sub == 0x09 and len(cuerpo) >= 3 and llave("GRANJA_COMPRA"):
        n = struct.unpack_from("<H", cuerpo, 1)[0]
        if n and len(cuerpo) == 3 + 7 * n:
            items = [struct.unpack_from("<IbbB", cuerpo, 3 + 7 * k) for k in range(n)]
            res = mover(usn, items)
            if res:
                con.mandar_interno(0x14C, seq, bytes([0x09, res]))
                anotar("   S2C FF14C 09 mover %d objetos: res %d (no se movio)" % (n, res))
            else:
                con.mandar_interno(0x14C, seq, cuerpo_09(items))
                anotar("   S2C FF14C 09 mover %d objeto(s): %s" % (n, [(i, x, y) for i, x, y, g in items]))
                if _m2():                                        # FICHA 119: evento `arrange` (una orden de mover = 1)
                    _mandar_pasos(con, seq, nick, evento(usn, "arrange"))
            return True
    if sub == 0x08 and len(cuerpo) == 5 and llave("GRANJA_COMPRA"):
        oid = struct.unpack_from("<I", cuerpo, 1)[0]
        res, g, dif, o, hoy, subio, pasos = cosechar(usn, oid)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x08]) + struct.pack("<IB", oid, res))
            anotar("   S2C FF14C 08 cosechar id %d: res %d (no se cobro ni se dio nada)" % (oid, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_08(oid, o["t"], hoy))
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 2, dif, oid, subio))
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C 08 cosechar id %d (Index %d): %s, estrellas %d madera %d energia %d exp %d, proxima en %d s (08 14 B + 0a 72 B)"
               % (oid, o["index"], dif, g["estrellas"], g["madera"], g["energia"], g["exp"], o["t"] - hoy))
        return True
    if sub == 0x0B and len(cuerpo) == 5 and llave("GRANJA_COMPRA"):
        oid = struct.unpack_from("<I", cuerpo, 1)[0]
        res, g, dif, o = vender(usn, oid)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x0B]) + struct.pack("<IB", oid, res))
            anotar("   S2C FF14C 0b vender id %d: res %d (no se vendio)" % (oid, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 3, dif, oid))
        con.mandar_interno(0x14C, seq, bytes([0x0B]) + struct.pack("<IB", oid, 0))
        anotar("   S2C FF14C 0b vender id %d (Index %d): +%d estrellas +%d madera (INVENTADO: 0a tipo 3 antes del 0b)" % (oid, o["index"], dif[1], dif[2]))
        if _m2():                                                # FICHA 119: evento `sell`
            _mandar_pasos(con, seq, nick, evento(usn, "sell", o["index"]))
        return True
    if sub == 0x0C and len(cuerpo) == 2 and llave("GRANJA_COMPRA"):
        tam = cuerpo[1]
        res, g, dif, hoy, pasos = ampliar(usn, tam)
        if res:
            con.mandar_interno(0x14C, seq, bytes([0x0C, res, tam]))
            anotar("   S2C FF14C 0c ampliar a %d: res %d (no se cobro)" % (tam, res))
            return True
        con.mandar_interno(0x14C, seq, cuerpo_0a(nick, g, 4, dif, 0))
        con.mandar_interno(0x14C, seq, bytes([0x0C, 0, tam]))
        _mandar_pasos(con, seq, nick, pasos)
        anotar("   S2C FF14C 0c ampliar a %d: %s, estrellas %d madera %d (0a tipo 4 + 0c 3 B)" % (tam, dif, g["estrellas"], g["madera"]))
        return True
    if sub == 0x1E and len(cuerpo) == 1 and llave("GRANJA_COMPRA"):
        g = estado_de(usn)
        con.mandar_interno(0x14C, seq, cuerpo_1e(g, ahora()))
        anotar("   S2C FF14C 1e energia %d/%d (cuenta atras a la proxima)" % (g["energia"], g["energia_max"]))
        return True
    if sub == 0x14 and len(cuerpo) == 1:
        con.mandar_interno(0x14C, seq, cuerpo_14())
        anotar("   S2C FF14C 14 hora")
        return True
    if sub == 0x24 and len(cuerpo) == 1:
        con.mandar_interno(0x14C, seq, cuerpo_24())
        anotar("   S2C FF14C 24 lista")
        return True
    anotar("   FF14C sub 0x%02x (%d B) SIN ATENDER: %s" % (sub, len(cuerpo), cuerpo[1:24].hex()))
    return False


def cerrar(con, seq, cuerpo):
    """C2S FF150 (0 B): el cliente vuelve solo al lobby; no se contesta nada. Solo se anota."""
    if not llave() or cuerpo:
        return False
    anotar("   FF150 cerrar granja (sin respuesta: el cliente vuelve solo)")
    return False


MANEJADORES = {
    0x14C: farm_forward,
    0x150: cerrar,
}
