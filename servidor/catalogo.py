# -*- coding: utf-8 -*-
r"""catalogo.py (ficha 62) — el catalogo de la tienda (`shop.txt` del juego chino) como funciones puras.

Lee `datos/catalogo.json` (lo arma `herramientas/preparar_catalogo.py`; formato en su docstring). Sin estado que no se
pueda rehacer: se puede recargar con `cargar()`. Si el archivo falta o esta roto, avisa UNA vez y todas las funciones
dan None / False. Lo usa tienda.py (dar_objeto). Se recarga en vivo (recarga.py): el catalogo se vuelve a leer.
"""
import json
import os

import ajustes

RUTA = os.path.join(ajustes.DATOS, "catalogo.json")
PLAZOS = {1: "1", 3: "3", 7: "7", 30: "30", 100: "100", 365: "365", 0: "I"}   # dias -> clave de `p`; 0 = permanente
PI_NO_SE_VENDE = 99999999          # HIPOTESIS: un permanente de 99999999 es "no se vende" (208 filas; nadie lo probo)

_objetos = None                    # {Index(str): ficha}; None = todavia no se cargo
_avisado = False


def cargar(ruta=None):
    """(Re)lee el catalogo de `ruta` (por omision RUTA). Si falla, deja la tabla vacia y avisa una sola vez."""
    global _objetos, _avisado, RUTA
    if ruta:
        RUTA = ruta
    try:
        with open(RUTA, "r", encoding="utf-8") as f:
            _objetos = json.load(f)["objetos"]
        _avisado = False
    except (OSError, ValueError, KeyError, TypeError):
        _objetos = {}
        if not _avisado:
            print("catalogo: no puedo leer %s (correr herramientas/preparar_catalogo.py)" % RUTA)
            _avisado = True
    return len(_objetos)


def cargado():
    """True si el catalogo se pudo leer y trae objetos (lo lee la primera vez que se pregunta). Si el archivo falta o esta
    roto da False, y entonces `ficha` da None para todo: eso no prueba que un objeto falte."""
    if _objetos is None:
        cargar()
    return bool(_objetos)


def ficha(item):
    """El registro del objeto (dict) o None si no esta en el catalogo."""
    if _objetos is None:
        cargar()
    return _objetos.get(str(item))


def existe(item):
    """True si el Index esta en shop.txt."""
    return ficha(item) is not None


def precio(item, plazo):
    """Precio del objeto para `plazo` (1, 3, 7, 30, 100, 365 dias; 0 = permanente), o None si ese plazo no se vende.
    Sale de P1..P365 y PI de shop.txt. HIPOTESIS: es el precio en la moneda de `moneda()`; no esta medido contra el oficial."""
    f = ficha(item)
    if f is None or plazo not in PLAZOS:
        return None
    return f.get("p", {}).get(PLAZOS[plazo])


def moneda(item):
    """"cash" (diamantes) si shop.txt trae Cash="1"; "g" si no lo trae (HIPOTESIS: los 1.043 sin Cash se pagan con G;
    sin medir); None si el objeto no existe."""
    f = ficha(item)
    if f is None:
        return None
    return "cash" if f.get("c") else "g"


def sexo(item):
    """"varon" / "mujer" (por la pestana 3xx / 4xx, medido sin excepciones) o None (unisex, sin dato o no existe)."""
    f = ficha(item)
    return {1: "varon", 2: "mujer"}.get(f.get("x")) if f else None


def oculto(item):
    """True si trae Show="0" (no se muestra en la tienda). False si se muestra o no existe."""
    f = ficha(item)
    return bool(f and f.get("o"))


def pestana(item):
    """La pestana (ShopIndex) del objeto, o None."""
    f = ficha(item)
    return f.get("s") if f else None


def se_vende(item):
    """True si tiene algun precio real: un plazo (menos el PI 99999999), un pack o un PN menor que ese tope.
    HIPOTESIS: que PN y pack cuenten como "se vende" y que 99999999 sea "no se vende" (nadie lo probo). No mira `oculto`."""
    f = ficha(item)
    if f is None:
        return False
    plazos = {k: v for k, v in f.get("p", {}).items() if v != PI_NO_SE_VENDE}
    return bool(plazos) or f.get("q") is not None or 0 < f.get("n", PI_NO_SE_VENDE) < PI_NO_SE_VENDE
