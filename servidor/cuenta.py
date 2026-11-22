# -*- coding: utf-8 -*-
r"""cuenta.py — el UNICO modulo que abre el archivo de cuentas (datos/cuenta.json). Sin estado en memoria: se puede recargar.

Forma del archivo (version 2):
  {"version": 2, "usuarios": {"<steamid>": {...}}, "cuentas": {"<usn en texto>": {...}}}
  usuarios   por cuenta Eñeños (steamid): steamid, gsn, puerto, usns (hasta 4 personajes), borrados, pendiente_usn,
             activo_usn, alta, capturada (bool).
  cuentas    por personaje (clave usn en texto):
    cuenta     steamid, gsn, usn, puerto, nick, alta
    personaje  char_id, nick, partes, licencia (opcional) — o null si aun no creo
    tienda     diamantes, items, basicas, exp, g, regalos
    amigos     {amigos: [usn], enviados: [usn], recibidos: [usn]}
    pareja     {usn, anillo} o {}
Arriba tambien hay "mudadas" ({seccion: {fecha, movidas, huerfanas}}) y "huerfanas" ({seccion: {usn: contenido}}).
Migracion desde version 1 (1 cuenta = 1 personaje): respalda con md5 y arma "usuarios" dejando cada personaje en la
casilla 1, sin perder nada de "cuentas", "huerfanas" ni "mudadas". La carpeta de datos se cambia con CUENTA_DATOS.
La clave es el usn. Una cuenta recien dada de alta aun no tiene usn (cuenta.usn = 0): su clave es el usn que
cuentas.usn_de le dara despues (USN_BASE + su posicion), asi la clave no cambia nunca.
Para volver atras: borrar datos/cuenta.json (se pierde lo cambiado despues de la mudanza). Los archivos viejos
(cuentas.json, tienda.json, ...) no se borran ni se vuelven a escribir; la copia de la primera vez esta en
datos/respaldo_<fecha>/ (y la de antes de pasar a version 2, en otro respaldo_<fecha>/).
"""
import copy
import hashlib
import json
import os
import shutil
import time

import ajustes

try:
    import msvcrt
except ImportError:          # no Windows
    msvcrt = None
    import fcntl

VERSION = 2
USN_BASE = 2000001           # el mismo que cuentas.USN_BASE
VIEJOS = ("cuentas.json", "tienda.json", "amigos.json", "parejas.json", "pruebas.json")
ESPERA_CANDADO = 30.0        # segundos que se espera el candado antes de rendirse
SECCIONES_VACIAS = ("tienda", "amigos", "pareja", "correo", "progresion", "granja", "jardin", "casa", "gemas", "boda")
# secciones que se mudan desde un archivo viejo la primera vez que se usa cuenta.json: {seccion: archivo viejo}
MUDANZAS = {"tienda": "tienda.json", "amigos": "amigos.json", "pareja": "parejas.json"}
# parejas.json que no existe: se arma con estas dos parejas de prueba (lo que hacia social.parejas() la primera vez)
SEMILLA_PAREJAS = {2000003: 2000004, 2000001: 2000006}
ANILLO_SEMILLA = 36005


class CuentaError(RuntimeError):
    """El archivo de cuentas no se puede leer o no se puede mudar: no se escribio nada."""


def datos():
    """La carpeta de datos (un solo lugar; CUENTA_DATOS la cambia)."""
    return ajustes.carpeta_cuenta()


def ruta():
    """El archivo de cuentas."""
    return os.path.join(datos(), "cuenta.json")


class _Candado:
    """Candado entre procesos sobre datos/cuenta.lock (msvcrt en Windows, fcntl en el resto). Lo suelta el sistema si el
    proceso muere."""

    def __enter__(self):
        os.makedirs(datos(), exist_ok=True)
        self.f = open(os.path.join(datos(), "cuenta.lock"), "a+b")
        limite = time.time() + ESPERA_CANDADO
        while True:
            try:
                if msvcrt:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() > limite:
                    self.f.close()
                    raise CuentaError("no se pudo tomar el candado de %s en %d s" % (ruta(), ESPERA_CANDADO))
                time.sleep(0.003)

    def __exit__(self, *a):
        try:
            if msvcrt:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        finally:
            self.f.close()


def _md5(r):
    h = hashlib.md5()
    with open(r, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _leer_json(r):
    """El JSON de un archivo. Si esta roto o no se puede abrir: CuentaError (nunca devuelve vacio)."""
    ultimo = None
    for _ in range(200):      # en Windows el archivo puede estar un instante en pleno os.replace
        try:
            with open(r, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise
        except PermissionError as e:
            ultimo = e
            time.sleep(0.005)
        except ValueError as e:
            raise CuentaError("%s esta roto (%s): no se escribio nada" % (r, e))
    raise CuentaError("no se pudo abrir %s: %s" % (r, ultimo))


def _escribir(r, d):
    """Escribe a un temporal con el pid en el nombre y lo pasa con os.replace."""
    tmp = "%s.tmp%d" % (r, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    for _ in range(400):      # un lector puede tener el destino abierto un instante
        try:
            os.replace(tmp, r)
            return
        except PermissionError:
            time.sleep(0.005)
    os.replace(tmp, r)


def _respaldar():
    """Copia los archivos viejos a datos/respaldo_<fecha>/ comprobando el md5. Devuelve la carpeta o None."""
    viejos = [n for n in VIEJOS + ("cuenta.json",) if os.path.exists(os.path.join(datos(), n))]
    if not viejos:
        return None
    base = os.path.join(datos(), "respaldo_" + time.strftime("%Y-%m-%d_%H%M%S"))
    dest, k = base, 1
    while os.path.exists(dest):          # dos respaldos en el mismo segundo: nunca se pisa uno
        k += 1
        dest = "%s_%d" % (base, k)
    os.makedirs(dest)
    for n in viejos:
        shutil.copy2(os.path.join(datos(), n), os.path.join(dest, n))
        if _md5(os.path.join(datos(), n)) != _md5(os.path.join(dest, n)):
            raise CuentaError("el respaldo de %s no coincide por md5: no se muda" % n)
    return dest


def _migrar_usuarios(d):
    """Arma o completa d['usuarios'] desde d['cuentas'] (version 1 -> 2): cada cuenta vieja queda con 1 personaje en la
    casilla 1 (o pendiente si aun no creo). No borra ni pisa nada de d['cuentas']."""
    usuarios = d.setdefault("usuarios", {})
    for clave, acc in d["cuentas"].items():
        c = acc.get("cuenta") or {}
        sid = c.get("steamid")
        if not sid:
            continue
        u = usuarios.get(sid)
        if u is None:
            u = {
                "steamid": sid,
                "gsn": c.get("gsn"),
                "puerto": c.get("puerto"),
                "usns": [],
                "borrados": [],
                "pendiente_usn": 0,
                "activo_usn": 0,
                "alta": c.get("alta", ""),
                "capturada": False,
            }
            usuarios[sid] = u
        usn_val = int(c.get("usn") or 0) or int(clave)
        if acc.get("personaje") is not None:
            if usn_val not in u["usns"]:
                u["usns"].append(usn_val)
            if not u.get("activo_usn"):
                u["activo_usn"] = usn_val
        else:
            if not u.get("pendiente_usn"):
                u["pendiente_usn"] = usn_val
            if not u.get("activo_usn"):
                u["activo_usn"] = usn_val
    d["version"] = VERSION
    return d


def _mudar(viejas):
    """De la lista de cuentas.json (formato viejo) arma el diccionario nuevo, clave usn en texto."""
    cuentas = {}
    for i, c in enumerate(viejas):
        usn = c.get("usn") or (USN_BASE + i)
        clave = str(usn)
        if clave in cuentas:
            raise CuentaError("dos cuentas con el mismo usn %s: no se muda" % clave)
        acc = {"cuenta": {k: v for k, v in c.items() if k != "personaje"}, "personaje": c.get("personaje")}
        for s in SECCIONES_VACIAS:
            acc[s] = {}
        cuentas[clave] = acc
    return _migrar_usuarios({"version": VERSION, "cuentas": cuentas})


def _forma(d):
    """Comprueba que d tenga la forma de cuenta.json; si no, CuentaError."""
    if not isinstance(d, dict) or not isinstance(d.get("cuentas"), dict):
        raise CuentaError("%s no tiene la forma esperada: no se escribio nada" % ruta())
    return d


def _viejo_de(seccion):
    """El contenido del archivo viejo de una seccion, {usn en texto: contenido}. Si el archivo no existe: {}. Roto o
    sin la forma de objeto: CuentaError (no se muda nada)."""
    r = os.path.join(datos(), MUDANZAS[seccion])
    if not os.path.exists(r):
        # Ficha 168: un paquete sin capturas nace sin parejas, tambien con PASE
        # apagado para las pruebas. Con lotes locales presentes, camino intacto.
        if seccion == "pareja" and not ajustes.pase_activo() and os.path.exists(ajustes.RUTA_LOTES):
            semilla = {str(a): {"usn": b, "anillo": ANILLO_SEMILLA} for a, b in SEMILLA_PAREJAS.items()}
            semilla.update({str(b): {"usn": a, "anillo": ANILLO_SEMILLA} for a, b in SEMILLA_PAREJAS.items()})
            return semilla
        return {}
    v = _leer_json(r)
    if not isinstance(v, dict) or not all(isinstance(x, dict) for x in v.values()):
        raise CuentaError("%s no tiene la forma esperada: no se muda" % r)
    return v


def _mudar_seccion(d, seccion, viejo):
    """Pone viejo[usn] en la seccion de la cuenta de ese usn (en memoria). Lo que no tiene cuenta NO se pierde: va a
    d["huerfanas"][seccion]. Devuelve (movidas, huerfanas)."""
    huerfanas = d.setdefault("huerfanas", {}).setdefault(seccion, {})
    movidas = 0
    for usn, contenido in viejo.items():
        acc = d["cuentas"].get(str(usn))
        if acc is None:
            huerfanas[str(usn)] = contenido
        elif acc.get(seccion):
            raise CuentaError("la cuenta %s ya tiene seccion %s: no se muda encima" % (usn, seccion))
        else:
            acc[seccion] = contenido
            movidas += 1
    if not huerfanas:
        del d["huerfanas"][seccion]
    return movidas, len(viejo) - movidas


def _pendientes(d):
    """Secciones de MUDANZAS que cuenta.json (d) aun no mudo."""
    hechas = d.get("mudadas") if isinstance(d, dict) else None
    return [s for s in MUDANZAS if s not in (hechas or {})]


def _asegurar():
    """Deja cuenta.json listo y devuelve su contenido: si no existe (primera vez) respaldo con md5 y lo arma desde
    cuentas.json; si le faltan secciones por mudar (MUDANZAS), respaldo NUEVO con md5 y las muda. Todo con el candado, lee
    antes de escribir y escribe una sola vez: si algo falla (archivo viejo roto) no se escribe nada."""
    if not os.path.exists(ruta()):
        with _Candado():
            if not os.path.exists(ruta()):
                viejo = os.path.join(datos(), "cuentas.json")
                viejas = _leer_json(viejo)["cuentas"] if os.path.exists(viejo) else []
                _respaldar()
                _escribir(ruta(), _mudar(viejas))
    d = _leer_json(ruta())
    if _pendientes(d):
        with _Candado():
            d = _forma(_leer_json(ruta()))      # con el candado otra vez: otro proceso pudo mudar mientras tanto
            pend = _pendientes(d)
            if pend:
                viejos = {s: _viejo_de(s) for s in pend}      # se lee todo antes de respaldar y de tocar nada
                _respaldar()
                for s in pend:
                    movidas, huerfanas = _mudar_seccion(d, s, viejos[s])
                    d.setdefault("mudadas", {})[s] = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                      "movidas": movidas, "huerfanas": huerfanas}
                _escribir(ruta(), d)
    if "usuarios" not in d or d.get("version", 1) < VERSION:
        with _Candado():
            d = _forma(_leer_json(ruta()))
            if "usuarios" not in d or d.get("version", 1) < VERSION:
                _respaldar()
                _migrar_usuarios(d)
                _escribir(ruta(), d)
    return d


def _cargar(asegurar=True):
    """Lee cuenta.json (lo muda si falta o si le faltan secciones). Error claro si esta roto o no tiene la forma esperada."""
    return _forma(_asegurar() if asegurar else _leer_json(ruta()))


def todas():
    """{usn en texto: cuenta} de todas las cuentas (copia)."""
    return _cargar()["cuentas"]


def leer(usn):
    """La cuenta de ese usn (copia) o None."""
    return todas().get(str(usn))


def buscar(seccion, campo, valor):
    """(usn en texto, cuenta) de la primera cuenta cuya seccion tiene campo == valor, o (None, None)."""
    for k, acc in todas().items():
        if (acc.get(seccion) or {}).get(campo) == valor:
            return k, acc
    return None, None


def cambiar_todas(funcion):
    """Con el candado: relee, llama funcion(d) sobre {"cuentas": {...}} y escribe. Devuelve lo que devuelva funcion.
    Si funcion falla no se escribe nada."""
    _asegurar()               # fuera del candado: la mudanza toma el suyo
    with _Candado():
        d = _cargar(False)
        antes = copy.deepcopy(d)
        res = funcion(d)
        if d != antes:
            _escribir(ruta(), d)
        return res


def cambiar(usn, funcion):
    """Con el candado: relee la cuenta, llama funcion(cuenta) (cambia el dict, o devuelve uno nuevo) y la escribe.
    Devuelve la cuenta ya cambiada, o None si no existe."""
    def f(d):
        acc = d["cuentas"].get(str(usn))
        if acc is None:
            return None
        nuevo = funcion(acc)
        if nuevo is not None:
            d["cuentas"][str(usn)] = acc = nuevo
        return copy.deepcopy(acc)
    return cambiar_todas(f)


def plana(acc):
    """La cuenta en el formato viejo de cuentas.json (campos de 'cuenta' + 'personaje'), para quien aun lo espera."""
    c = dict(acc["cuenta"])
    c["personaje"] = acc.get("personaje")
    return c


def todas_planas():
    """Lista de cuentas en el formato viejo, en el orden de alta."""
    return [plana(a) for a in todas().values()]


def leer_seccion(usn, seccion):
    """Copia de la seccion (tienda, amigos, pareja) de ese usn; {} si no tiene. Si el usn no es de ninguna cuenta (p. ej. 0,
    la sesion capturada) la busca en las huerfanas."""
    d = _cargar()
    acc = d["cuentas"].get(str(usn))
    if acc is not None:
        return acc.get(seccion) or {}
    return ((d.get("huerfanas") or {}).get(seccion) or {}).get(str(usn)) or {}


def cambiar_seccion(usn, seccion, funcion):
    """Con el candado: relee, llama funcion(contenido) con la seccion de ese usn (un dict que funcion cambia EN EL LUGAR) y
    escribe si cambio. Si el usn no es de ninguna cuenta usa la huerfana d["huerfanas"][seccion][usn]. Devuelve lo que
    devuelva funcion (que devuelva copias, no el dict). Una seccion que quedo vacia no deja entrada nueva."""
    def f(d):
        clave = str(usn)
        acc = d["cuentas"].get(clave)
        if acc is not None:
            lugar, k = acc, seccion
        else:
            lugar, k = d.setdefault("huerfanas", {}).setdefault(seccion, {}), clave
        existia = k in lugar
        contenido = lugar.setdefault(k, {})
        res = funcion(contenido)
        if not existia and not contenido:
            del lugar[k]
        if acc is None and not d["huerfanas"].get(seccion):
            d["huerfanas"].pop(seccion, None)
            if not d["huerfanas"]:
                del d["huerfanas"]
        return res
    return cambiar_todas(f)


def poner_secciones(seccion, contenidos):
    """Con el candado: pone contenidos[usn] como la seccion de cada usn (cuenta, o huerfana si no es de ninguna). Solo toca
    los usn que le pasan. Para quien ya tiene armado el diccionario entero."""
    def f(d):
        for usn, c in contenidos.items():
            acc = d["cuentas"].get(str(usn))
            if acc is not None:
                acc[seccion] = copy.deepcopy(c)
            else:
                d.setdefault("huerfanas", {}).setdefault(seccion, {})[str(usn)] = copy.deepcopy(c)
    return cambiar_todas(f)


def huerfanas():
    """{seccion: {usn: contenido}} de lo que vino de los archivos viejos y no tiene cuenta (copia)."""
    return _cargar().get("huerfanas") or {}


def usuarios():
    """{steamid: usuario} de todas las cuentas Eñeños (copia)."""
    return copy.deepcopy(_cargar().get("usuarios") or {})


def usuario(steamid):
    """La cuenta Eñeños de ese steamid (copia) o None."""
    return copy.deepcopy((_cargar().get("usuarios") or {}).get(str(steamid)))


def usuario_por_gsn(gsn):
    """La cuenta Eñeños cuyo gsn coincide (copia) o None."""
    for u in (_cargar().get("usuarios") or {}).values():
        if u.get("gsn") == gsn:
            return copy.deepcopy(u)
    return None


def usuario_por_puerto(puerto):
    """La cuenta Eñeños cuyo puerto coincide (copia) o None."""
    for u in (_cargar().get("usuarios") or {}).values():
        if u.get("puerto") == puerto:
            return copy.deepcopy(u)
    return None
