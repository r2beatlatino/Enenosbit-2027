# -*- coding: utf-8 -*-
r"""recarga.py (10-nov, ficha 33) — recarga SEGURA en caliente de los modulos del servidor local.

Antes (juego.manejadores_al_dia): si cambiaba CUALQUIER .py se recargaban los 5 temas de golpe, y un archivo roto
dejaba todo a medias. Ahora, por cada modulo recargable que cambia:
  1. se espera a que el archivo este quieto (QUIETO segundos con la misma fecha y largo);
  2. se lee y se rechaza si tiene bytes NUL, no es UTF-8 o no compila (compile() del texto, sin escribir .pyc);
  3. se recarga SOLO ese modulo: el codigo ya compilado se ejecuta en el MISMO objeto modulo (el que tienen
     manejadores.MODULOS y los `import x` de adentro de las funciones), asi nada tiene que reapuntar;
  4. si falla a mitad (por ej. un `import` que no existe) se repone el diccionario del modulo tal como estaba:
     el modulo ANTERIOR sigue funcionando; el error se anota UNA vez y no se reintenta hasta que el archivo cambie.
Una linea en el registro por cada cosa y el estado en registros/recarga.json (lo lee el panel).

NO se recargan (si cambian, una linea "hace falta reiniciar"): juego, login, cuentas, estado, ajustes y este mismo archivo.
Los archivos .py que no estan en ninguna de las dos listas (nuevos) se ignoran.

Limites conocidos: importlib/exec reusa el diccionario, asi que un nombre BORRADO del archivo sigue vivo hasta reiniciar.
Lo vivo (salas, CERRADAS, PROPUESTAS) esta en estado.py y los temporizadores se arman con estado.mas_tarde (buscan la funcion por
nombre al disparar), asi que una recarga no los pierde. Un modulo recargable que guardara estado propio en memoria lo vaciaria.

RECARGA_REGISTROS=<carpeta> cambia donde se escribe recarga.json (para pruebas).
"""
import json
import os
import sys
import time

import ajustes

AQUI = os.path.dirname(os.path.abspath(__file__))
REGISTROS = ajustes.carpeta_registros_recarga()     # RECARGA_REGISTROS (ajustes.py)
RUTA_JSON = os.path.join(REGISTROS, "recarga.json")

RECARGABLES = ["cuenta", "sello", "captura", "catalogo", "fichas", "salas", "casa", "sala_magica", "liga", "charla", "tienda", "carrera", "social", "boda", "correo", "gemas", "granja", "jardin", "progresion", "ranking", "misiones",
               "practica", "cuenta_local", "manejadores"]
FIJOS = ["juego", "login", "cuentas", "estado", "ajustes", "recarga"]
QUIETO = 1.0          # segundos sin cambiar de fecha ni de largo antes de tocar un archivo
PERIODO = 1.0         # cada cuanto mira el reloj (ademas de cuando llega un FF55)

ANOTAR = print
_PROCESADA = {}       # nombre -> firma (mtime_ns, largo) ya atendida (recargada, rechazada o avisada)
_PENDIENTE = {}       # nombre -> (firma, momento en que se vio por primera vez con esa firma)
_ESTADO = {}          # nombre -> dict que va a recarga.json
_LISTO = False


def _ruta(nombre):
    return os.path.join(AQUI, nombre + ".py")


def _firma(nombre):
    try:
        st = os.stat(_ruta(nombre))
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _guardar_json():
    try:
        os.makedirs(os.path.dirname(RUTA_JSON), exist_ok=True)
        tmp = RUTA_JSON + ".tmp%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"actualizado": time.strftime("%Y-%m-%d %H:%M:%S"), "modulos": _ESTADO}, f,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, RUTA_JSON)
    except Exception as e:                                               # noqa: BLE001
        ANOTAR("   ⛔ recarga.json no se pudo escribir: %r" % e)


def _poner(nombre, firma, estado, motivo=""):
    _ESTADO[nombre] = {
        "archivo": nombre + ".py",
        "fecha_archivo": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(firma[0] / 1e9)) if firma else "",
        "largo": firma[1] if firma else 0,
        "estado": estado,          # ok | rechazado | reiniciar
        "motivo": motivo,
        "hora": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _guardar_json()


def _revisar_texto(nombre):
    """Lee el archivo y devuelve (codigo, firma_leida) o levanta ValueError con el motivo."""
    ruta = _ruta(nombre)
    antes = _firma(nombre)
    with open(ruta, "rb") as f:
        crudo = f.read()
    if b"\x00" in crudo:
        raise ValueError("tiene bytes NUL (%d)" % crudo.count(b"\x00"))
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("no es UTF-8 (%s)" % e)
    try:
        codigo = compile(texto, ruta, "exec", dont_inherit=True)
    except SyntaxError as e:
        raise ValueError("SyntaxError l.%s: %s" % (e.lineno, e.msg))
    except Exception as e:                                               # noqa: BLE001
        raise ValueError("no compila: %r" % e)
    if _firma(nombre) != antes:
        raise _Cambio()
    return codigo, antes


class _Cambio(Exception):
    """El archivo cambio mientras se lo leia: no se hace nada, se vuelve a esperar."""


def _recargar_uno(nombre):
    mod = sys.modules.get(nombre)
    if mod is None:
        raise ValueError("el modulo no esta cargado")
    codigo, firma = _revisar_texto(nombre)
    viejo = dict(mod.__dict__)
    t0 = time.time()
    try:
        exec(codigo, mod.__dict__)
    except BaseException as e:                                           # noqa: BLE001
        mod.__dict__.clear()
        mod.__dict__.update(viejo)
        raise ValueError("error al ejecutarlo (sigue el modulo anterior): %s: %s" % (type(e).__name__, e))
    return firma, time.time() - t0


def _atender(nombre, firma):
    """El archivo `nombre` cambio y esta quieto: recargarlo, rechazarlo o avisar que hace falta reiniciar."""
    if nombre in FIJOS:
        _PROCESADA[nombre] = firma
        ANOTAR("   %s.py cambio: hace falta reiniciar" % nombre)
        _poner(nombre, firma, "reiniciar", "cambio y no se recarga en caliente: hace falta reiniciar")
        return
    try:
        firma_leida, seg = _recargar_uno(nombre)
    except _Cambio:
        return                    # cambio en el medio: no se marca como atendido, se espera de nuevo
    except ValueError as e:
        _PROCESADA[nombre] = firma
        ANOTAR("   ⛔ RECHAZADO %s.py: %s" % (nombre, e))
        _poner(nombre, firma, "rechazado", str(e))
        return
    _PROCESADA[nombre] = firma_leida
    ANOTAR("   recargado %s.py (%.2f s)" % (nombre, seg))
    _poner(nombre, firma_leida, "ok", "")


def revisar(ahora=None):
    """Mira los archivos y atiende los que cambiaron y ya estan quietos. Barata: un stat por archivo. No levanta
    excepciones (la llama el bucle de red)."""
    global _LISTO
    try:
        ahora = time.monotonic() if ahora is None else ahora
        if not _LISTO:
            _LISTO = True
            for n in RECARGABLES + FIJOS:
                f = _firma(n)
                _PROCESADA[n] = f
                if n in RECARGABLES and f is not None:
                    _poner(n, f, "ok", "cargado al arrancar")
            return
        for n in RECARGABLES + FIJOS:
            f = _firma(n)
            if f is None or f == _PROCESADA.get(n):
                _PENDIENTE.pop(n, None)
                continue
            p = _PENDIENTE.get(n)
            if p is None or p[0] != f:
                _PENDIENTE[n] = (f, ahora)
                continue
            if ahora - p[1] < QUIETO:
                continue
            _PENDIENTE.pop(n, None)
            _atender(n, f)
    except Exception as e:                                               # noqa: BLE001
        try:
            ANOTAR("   ⛔ recarga.revisar: %r" % e)
        except Exception:                                                # noqa: BLE001
            pass


def recargar_modulo(nombre):
    """A pedido (manejadores.recargar): recarga ese modulo ya, sin esperar. Devuelve True si quedo recargado."""
    try:
        firma, seg = _recargar_uno(nombre)
    except (ValueError, _Cambio) as e:
        ANOTAR("   ⛔ RECHAZADO %s.py: %s" % (nombre, e))
        return False
    _PROCESADA[nombre] = firma
    ANOTAR("   recargado %s.py (%.2f s)" % (nombre, seg))
    _poner(nombre, firma, "ok", "")
    return True


def iniciar(anotar=None):
    """Una vez, desde juego.main (con el bucle de asyncio andando): fija el registro, toma la foto de partida y deja
    un reloj que mira cada PERIODO segundos (ademas de la llamada a revisar() con cada FF55)."""
    global ANOTAR
    if anotar is not None:
        ANOTAR = anotar
    revisar()
    try:
        import asyncio
        bucle = asyncio.get_running_loop()
    except Exception:                                                    # noqa: BLE001
        return

    def _tic():
        revisar()
        bucle.call_later(PERIODO, _tic)
    bucle.call_later(PERIODO, _tic)
