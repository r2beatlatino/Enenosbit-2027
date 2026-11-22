# -*- coding: utf-8 -*-
r"""gemas.py (12-nov, ficha 95) — las Piedras Sonicas (gemas) de una cuenta LOCAL: engarzar una en un objeto y que siga ahi.
Layouts leidos del exe: docs/tablero/layouts/FF272.md, FF273.md (seccion "Lectura de la ficha 95").

  S2C FF272 (en la rafaga de entrada)  [u32 n] n x {[u32 objeto][u32 m][m x u32 gema]}   (reemplaza todo lo que tenia el cliente)
  C2S FF273 [u32 1][u32 objeto][u32 gema]  -> S2C FF273 [s "ok"][u32 objeto][u32 gema][u32 flag 1]   (s = [u32 largo][bytes])
                                           o S2C FF273 [s texto]   (cualquier texto distinto de "ok" = cartel con ESE texto)

ESTADO (seccion `gemas` de la cuenta, solo via cuenta.py): {"objetos": {"<objeto>": [gema, ...]}, "inventado": true}.
TABLA: datos/gemas_tablas.json (herramientas/preparar_gemas.py; copia de las filas itemType 26 de config/items_tbitemfuncmap.json:
  11000961..64 con su shopIndexList: [8] las tres primeras, [25] la de volar).
COMPATIBILIDAD (LEIDO en el exe, 0x00d15080 / 0x00d15db0): el cliente calcula una "clase" del objeto y la busca en el shopIndexList de
  la gema. Clase 8 = ShopIndex 505 (mascotas 6xxxxx) salvo codigo de 7 cifras que empieza con 40 (clase 27). La clase 25 depende de
  una lista que NO se identifico: la gema de volar (11000964) se RECHAZA siempre (INVENTADO, mejor que falte a que mienta).
LO INVENTADO (marcado): los textos de rechazo (en castellano, ASCII); el tope: 1 gema de cada tipo por objeto; que la piedra NO se
  descuenta del inventario (no se leyo que mensaje lo haria en el cliente: la lista izquierda la sigue mostrando).
  El efecto en la carrera (monedas x5, exp x5) NO esta hecho.
Solo cuentas LOCALES; la sesion capturada queda como siempre. Llave por entorno GEMAS (omision 1: se vio andar con el juego el 12-nov; =0 apaga todo).
"""
import json
import os
import struct

import ajustes
import catalogo
import cuenta as _cta
import estado

LLAVES_OMISION = {"GEMAS": "1"}
SECCION = "gemas"
CMD_DATOS, CMD_EDITAR = 0x272, 0x273
OK = b"ok"
_RUTAS = (
    os.path.join(ajustes.DATOS, "gemas_tablas.json"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "import_input", "steam_10379", "_extract", "rnr_script", "config", "items_tbitemfuncmap.json"),
)
_TABLA = {}

TEXTOS = {   # INVENTADO
    "sin_piedra": "No tenes esa piedra",
    "sin_objeto": "No tenes ese objeto",
    "no_va": "Esa piedra no va en ese objeto",
    "repetida": "Esa piedra ya esta puesta en ese objeto",
    "no_gema": "Eso no es una piedra",
    "error": "No se pudo engarzar la piedra",
}


def anotar(txt):
    estado.anotar(txt)


def llave(nombre="GEMAS"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def tabla():
    """{codigo(int): shopIndexList} de las gemas. {} si no hay tabla (entonces no se atiende nada)."""
    if _TABLA:
        return _TABLA
    rutas = list(_RUTAS) + [os.path.join(ajustes.carpeta_cuenta(), "gemas_tablas.json")]
    for ruta in rutas:
        try:
            with open(ruta, encoding="utf-8") as f:
                j = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(j, dict) and "gemas" in j:
            for k, v in j["gemas"].items():
                _TABLA[int(k)] = list(v.get("shopIndexList") or [])
        else:
            for f in j:
                if f.get("itemType") == 26:
                    _TABLA[int(f["code"])] = list(f.get("shopIndexList") or [])
        break
    return _TABLA


def clase_de(objeto):
    """La clase de un objeto para las gemas (LEIDO, 0x00d15080). Solo las que se pudieron leer: 8 (mascota) y 27; el resto 0."""
    if catalogo.pestana(objeto) == 505:
        return 27 if int(("%08d" % (objeto % 10_000_000))[:3]) == 40 else 8
    return 0


def compatible(gema, objeto):
    """True si el shopIndexList de la gema trae la clase del objeto. La gema de volar (clase 25) no se acepta nunca."""
    lista = tabla().get(gema)
    return bool(lista) and clase_de(objeto) in lista


def _usn(con):
    return (con.cuenta or {}).get("usn")


def _cantidad(usn, item):
    """Cuantas tiene la cuenta de `item` (inventario de la seccion tienda; 0 si no lo tiene; permanente sin cantidad = 1)."""
    n = 0
    for reg in (_cta.leer_seccion(usn, "tienda").get("items") or []):
        if reg[0] == item:
            n += max(1, int(reg[2])) if len(reg) > 2 else 1
    return n


def objetos_de(usn):
    """{objeto(int): [gemas]} guardado en la cuenta (copia)."""
    s = _cta.leer_seccion(usn, SECCION)
    return {int(k): list(v) for k, v in (s.get("objetos") or {}).items() if v}


def _s(texto):
    b = texto if isinstance(texto, bytes) else texto.encode("ascii")
    return struct.pack("<I", len(b)) + b


def cuerpo_272(objetos):
    """FF272: [u32 n] n x {[u32 objeto][u32 m][m x u32 gema]}, objetos en orden numerico."""
    out = struct.pack("<I", len(objetos))
    for ob in sorted(objetos):
        g = objetos[ob]
        out += struct.pack("<II", ob, len(g)) + b"".join(struct.pack("<I", x) for x in g)
    return out


def cuerpo(cuenta):
    """Cuerpo S2C FF272 para esta cuenta local, o None si el modulo esta apagado o no hay cuenta."""
    if not llave() or not cuenta or not cuenta.get("usn"):
        return None
    return cuerpo_272(objetos_de(cuenta["usn"]))


def cuerpo_273_ok(objeto, gema):
    return _s(OK) + struct.pack("<III", objeto, gema, 1)


def engarzar(usn, objeto, gema):
    """-> motivo (clave de TEXTOS) o None. Si None, quedo guardado. Valida todo antes de escribir."""
    if gema not in tabla():
        return "no_gema"
    if _cantidad(usn, objeto) < 1:
        return "sin_objeto"
    if _cantidad(usn, gema) < 1:
        return "sin_piedra"
    if not compatible(gema, objeto):
        return "no_va"
    res = []

    def f(c):
        obs = c.setdefault("objetos", {})
        lista = obs.setdefault(str(objeto), [])
        if gema in lista:
            res.append("repetida")
            return
        lista.append(gema)
        c["inventado"] = True
    _cta.cambiar_seccion(usn, SECCION, f)
    return res[0] if res else None


def editar(con, seq, cuerpo):
    """C2S FF273 [u32 1][u32 objeto][u32 gema] (12 B)."""
    usn = _usn(con)
    if not llave() or usn is None or len(cuerpo) != 12 or not tabla():
        return False
    op, objeto, gema = struct.unpack("<III", cuerpo)
    if op != 1:
        return False
    try:
        motivo = engarzar(usn, objeto, gema)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ gemas.engarzar: %r" % e)
        motivo = "error"
    if motivo is None:
        con.mandar_interno(CMD_EDITAR, seq, cuerpo_273_ok(objeto, gema))
        anotar("   S2C FF273 ok: gema %d en el objeto %d de %s" % (gema, objeto, (con.cuenta or {}).get("nick")))
    else:
        con.mandar_interno(CMD_EDITAR, seq, _s(TEXTOS[motivo]))
        anotar("   S2C FF273 rechazo '%s' (gema %d, objeto %d) de %s" % (motivo, gema, objeto, (con.cuenta or {}).get("nick")))
    return True


def lote_para(lote, cuenta):
    """El lote de entrada con SU FF272 (los internos se rearman). Sin llave, sin cuenta o sin gemas guardadas: el mismo lote."""
    try:
        if not llave() or not cuenta or b"\xfd\x72" not in lote or lote[:2] != b"\xff\x56":
            return lote
        objetos = objetos_de(cuenta["usn"])
        if not objetos:
            return lote
        nuevo = cuerpo_272(objetos)
        k = 4 + struct.unpack_from("<H", lote, 2)[0]
        out, cambios = lote[:k], 0
        while k + 8 <= len(lote):
            fl, cmd = lote[k], lote[k + 1]
            seq, ln = struct.unpack_from("<HI", lote, k + 2)
            if k + 8 + ln > len(lote):
                break
            cu = lote[k + 8:k + 8 + ln]
            if fl == 0xFD and cmd == 0x72:
                cu = nuevo
                cambios += 1
            out += bytes([fl, cmd]) + struct.pack("<HI", seq, len(cu)) + cu
            k += 8 + ln
        out += lote[k:]
        if cambios:
            anotar("   gemas: FF272 propio en la rafaga de entrada de %s (%d objeto(s))" % (cuenta.get("nick"), len(objetos)))
        return out
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ gemas.lote_para: %r" % e)
        return lote


MANEJADORES = {CMD_EDITAR: editar}
