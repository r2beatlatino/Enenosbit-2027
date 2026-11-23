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
import re
import shutil
import sqlite3
import sys
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
ESPERA_SQLITE_MS = 5000      # busy_timeout de SQLite en milisegundos
SECCIONES_VACIAS = ("tienda", "amigos", "pareja", "correo", "progresion", "granja", "jardin", "casa", "gemas", "boda")
# secciones que se mudan desde un archivo viejo la primera vez que se usa cuenta.json: {seccion: archivo viejo}
MUDANZAS = {"tienda": "tienda.json", "amigos": "amigos.json", "pareja": "parejas.json"}
# parejas.json que no existe: se arma con estas dos parejas de prueba (lo que hacia social.parejas() la primera vez)
SEMILLA_PAREJAS = {2000003: 2000004, 2000001: 2000006}
ANILLO_SEMILLA = 36005
_IDENT_SQL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CLAVES_TABLA = ("cuentas", "usuarios", "sesiones")


def _leer_bandera_sqlite():
    return (os.environ.get("CUENTA_SQLITE") or "0").strip().lower() in ("1", "si")


# Llave CUENTA_SQLITE: leida al importar y tambien en el momento (por omision "0" = cuenta.json).
CUENTA_SQLITE = _leer_bandera_sqlite()


def _usar_sqlite():
    return _leer_bandera_sqlite()


class CuentaError(RuntimeError):
    """El archivo de cuentas no se puede leer o no se puede mudar: no se escribio nada."""


def datos():
    """La carpeta de datos (un solo lugar; CUENTA_DATOS la cambia)."""
    return ajustes.carpeta_cuenta()


def _ruta_json():
    return os.path.join(datos(), "cuenta.json")


def _ruta_db():
    return os.path.join(datos(), "cuentas.db")


def ruta():
    """El archivo de cuentas (cuentas.db con CUENTA_SQLITE=1; cuenta.json por omision)."""
    return _ruta_db() if _usar_sqlite() else _ruta_json()


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
    r = _ruta_json()
    if not os.path.exists(r):
        with _Candado():
            if not os.path.exists(r):
                viejo = os.path.join(datos(), "cuentas.json")
                viejas = _leer_json(viejo)["cuentas"] if os.path.exists(viejo) else []
                _respaldar()
                _escribir(r, _mudar(viejas))
    d = _leer_json(r)
    if _pendientes(d):
        with _Candado():
            d = _forma(_leer_json(r))      # con el candado otra vez: otro proceso pudo mudar mientras tanto
            pend = _pendientes(d)
            if pend:
                viejos = {s: _viejo_de(s) for s in pend}      # se lee todo antes de respaldar y de tocar nada
                _respaldar()
                for s in pend:
                    movidas, huerfanas = _mudar_seccion(d, s, viejos[s])
                    d.setdefault("mudadas", {})[s] = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                      "movidas": movidas, "huerfanas": huerfanas}
                _escribir(r, d)
    if "usuarios" not in d or d.get("version", 1) < VERSION:
        with _Candado():
            d = _forma(_leer_json(r))
            if "usuarios" not in d or d.get("version", 1) < VERSION:
                _respaldar()
                _migrar_usuarios(d)
                _escribir(r, d)
    return d


def _cargar(asegurar=True):
    """Lee cuenta.json (lo muda si falta o si le faltan secciones). Error claro si esta roto o no tiene la forma esperada."""
    return _forma(_asegurar() if asegurar else _leer_json(_ruta_json()))


# ---------- Almacenamiento SQLite (CUENTA_SQLITE=1) ----------

def _anotar(txt):
    mod = sys.modules.get("estado")
    if mod is not None and hasattr(mod, "anotar"):
        try:
            mod.anotar(txt)
            return
        except Exception:
            pass
    print(txt, flush=True)


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _loads(texto, origen="cuentas.db"):
    try:
        return json.loads(texto)
    except ValueError as e:
        raise CuentaError("%s tiene JSON roto (%s)" % (origen, e))


def _borrar_archivos_db(base):
    for suf in ("", "-wal", "-shm"):
        p = base + suf
        try:
            if os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


def _abrir_db(r=None, init_wal=False):
    db_path = r or _ruta_db()
    try:
        con = sqlite3.connect(db_path, timeout=ESPERA_SQLITE_MS / 1000.0, isolation_level=None)
        con.execute("PRAGMA busy_timeout=%d" % ESPERA_SQLITE_MS)
        if init_wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        return con
    except sqlite3.Error as e:
        raise CuentaError("no se pudo abrir %s: %s" % (db_path, e))


def _crear_esquema(con):
    con.execute("CREATE TABLE IF NOT EXISTS cuentas (usn TEXT PRIMARY KEY, datos TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS usuarios (steamid TEXT PRIMARY KEY, datos TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS sesiones (gsn TEXT PRIMARY KEY, datos TEXT NOT NULL, expira REAL NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS arriba (clave TEXT PRIMARY KEY, datos TEXT NOT NULL)")


def _poblar_db(con, d):
    n_cta = n_usr = n_ses = n_arr = 0
    for k, acc in (d.get("cuentas") or {}).items():
        con.execute("INSERT INTO cuentas(usn, datos) VALUES (?, ?)", (str(k), _dumps(acc)))
        n_cta += 1
    for k, u in (d.get("usuarios") or {}).items():
        con.execute("INSERT INTO usuarios(steamid, datos) VALUES (?, ?)", (str(k), _dumps(u)))
        n_usr += 1
    sesiones = d.get("sesiones")
    if isinstance(sesiones, dict):
        for k, s in sesiones.items():
            if isinstance(s, dict):
                exp = float(s.get("expira", 0) or 0)
                con.execute("INSERT INTO sesiones(gsn, datos, expira) VALUES (?, ?, ?)", (str(k), _dumps(s), exp))
                n_ses += 1
    for k, v in d.items():
        if k in _CLAVES_TABLA:
            continue
        con.execute("INSERT INTO arriba(clave, datos) VALUES (?, ?)", (str(k), _dumps(v)))
        n_arr += 1
    return n_cta, n_usr, n_ses, n_arr


def _preparar_dict_inicial_sqlite():
    """Prepara en memoria el dict inicial para crear cuentas.db (sin tocar ni borrar cuenta.json).
    Devuelve (d, desde_json)."""
    rj = _ruta_json()
    if os.path.exists(rj):
        d = _forma(_leer_json(rj))
        pend = _pendientes(d)
        if pend:
            viejos = {s: _viejo_de(s) for s in pend}
            for s in pend:
                movidas, huerf = _mudar_seccion(d, s, viejos[s])
                d.setdefault("mudadas", {})[s] = {
                    "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "movidas": movidas,
                    "huerfanas": huerf,
                }
        if "usuarios" not in d or d.get("version", 1) < VERSION:
            _migrar_usuarios(d)
        return d, True

    viejo = os.path.join(datos(), "cuentas.json")
    viejas = _leer_json(viejo)["cuentas"] if os.path.exists(viejo) else []
    d = _mudar(viejas)
    pend = _pendientes(d)
    if pend:
        viejos = {s: _viejo_de(s) for s in pend}
        for s in pend:
            movidas, huerf = _mudar_seccion(d, s, viejos[s])
            d.setdefault("mudadas", {})[s] = {
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                "movidas": movidas,
                "huerfanas": huerf,
            }
    return d, False


def _asegurar_db():
    """Deja cuentas.db listo. Si no existe y existe cuenta.json, lo migra UNA vez en una transaccion sin tocar el json."""
    db_path = _ruta_db()
    if os.path.exists(db_path):
        return db_path
    with _Candado():
        if os.path.exists(db_path):
            return db_path
        d, desde_json = _preparar_dict_inicial_sqlite()
        tmp_db = "%s.tmp%d" % (db_path, os.getpid())
        _borrar_archivos_db(tmp_db)
        con = None
        try:
            con = _abrir_db(tmp_db, init_wal=True)
            _crear_esquema(con)
            con.execute("BEGIN IMMEDIATE")
            n_cta, n_usr, n_ses, n_arr = _poblar_db(con, d)
            con.execute("COMMIT")
            con.close()
            con = None
            for _ in range(400):
                try:
                    os.replace(tmp_db, db_path)
                    break
                except PermissionError:
                    time.sleep(0.005)
            else:
                os.replace(tmp_db, db_path)
            if desde_json:
                _anotar(
                    "cuenta.py: migrado cuenta.json -> cuentas.db "
                    "(%d cuentas, %d usuarios, %d sesiones, %d arriba)"
                    % (n_cta, n_usr, n_ses, n_arr)
                )
        except Exception as e:
            if con is not None:
                try:
                    con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                try:
                    con.close()
                except sqlite3.Error:
                    pass
            _borrar_archivos_db(tmp_db)
            if isinstance(e, sqlite3.Error):
                raise CuentaError("no se pudo crear %s: %s" % (db_path, e))
            raise
    return db_path


def _ejecutar_escritura_db(fn):
    """Abre cuentas.db, inicia BEGIN IMMEDIATE, llama fn(con) -> (escribio, res), hace COMMIT o ROLLBACK y cierra."""
    db_path = _asegurar_db()
    con = _abrir_db(db_path)
    en_tx = False
    try:
        try:
            con.execute("BEGIN IMMEDIATE")
            en_tx = True
        except sqlite3.Error as e:
            raise CuentaError("no se pudo iniciar transaccion en %s: %s" % (db_path, e))
        escribio, res = fn(con)
        try:
            con.execute("COMMIT" if escribio else "ROLLBACK")
            en_tx = False
        except sqlite3.Error as e:
            raise CuentaError("no se pudo confirmar transaccion en %s: %s" % (db_path, e))
        return res
    except BaseException as e:
        if en_tx:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        if isinstance(e, sqlite3.Error):
            raise CuentaError("error SQLite en %s: %s" % (db_path, e))
        raise
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _ejecutar_lectura_db(fn):
    """Abre cuentas.db, llama fn(con) y cierra."""
    db_path = _asegurar_db()
    con = _abrir_db(db_path)
    try:
        return fn(con)
    except sqlite3.Error as e:
        raise CuentaError("error SQLite al leer %s: %s" % (db_path, e))
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass


def _sql_todas():
    def q(con):
        rows = con.execute("SELECT usn, datos FROM cuentas ORDER BY rowid").fetchall()
        return {k: _loads(v) for k, v in rows}
    return _ejecutar_lectura_db(q)


def _sql_leer(usn):
    clave = str(usn)
    def q(con):
        row = con.execute("SELECT datos FROM cuentas WHERE usn = ?", (clave,)).fetchone()
        return _loads(row[0]) if row is not None else None
    return _ejecutar_lectura_db(q)


def _sql_buscar(seccion, campo, valor):
    usa_extract = (
        isinstance(seccion, str)
        and isinstance(campo, str)
        and _IDENT_SQL.match(seccion)
        and _IDENT_SQL.match(campo)
        and isinstance(valor, (int, float, str))
        and not isinstance(valor, bool)
    )
    def q(con):
        if usa_extract:
            ruta_j = "$.%s.%s" % (seccion, campo)
            try:
                rows = con.execute(
                    "SELECT usn, datos FROM cuentas WHERE json_extract(datos, ?) = ? ORDER BY rowid",
                    (ruta_j, valor),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = con.execute("SELECT usn, datos FROM cuentas ORDER BY rowid").fetchall()
        else:
            rows = con.execute("SELECT usn, datos FROM cuentas ORDER BY rowid").fetchall()
        for k, raw in rows:
            acc = _loads(raw)
            if (acc.get(seccion) or {}).get(campo) == valor:
                return k, acc
        return None, None
    return _ejecutar_lectura_db(q)


def _sql_cambiar_todas(funcion):
    def tx(con):
        d = {}
        arriba_antes = {}
        for k, raw in con.execute("SELECT clave, datos FROM arriba ORDER BY rowid").fetchall():
            arriba_antes[k] = raw
            d[k] = _loads(raw)
        if "version" not in d:
            d["version"] = VERSION

        usuarios_antes = {}
        usuarios_d = {}
        for k, raw in con.execute("SELECT steamid, datos FROM usuarios ORDER BY rowid").fetchall():
            usuarios_antes[k] = raw
            usuarios_d[k] = _loads(raw)
        d["usuarios"] = usuarios_d

        cuentas_antes = {}
        cuentas_d = {}
        for k, raw in con.execute("SELECT usn, datos FROM cuentas ORDER BY rowid").fetchall():
            cuentas_antes[k] = raw
            cuentas_d[k] = _loads(raw)
        d["cuentas"] = cuentas_d

        sesiones_antes = {}
        ses_rows = con.execute("SELECT gsn, datos FROM sesiones ORDER BY rowid").fetchall()
        if ses_rows:
            ses_d = {}
            for k, raw in ses_rows:
                sesiones_antes[k] = raw
                ses_d[k] = _loads(raw)
            d["sesiones"] = ses_d

        res = funcion(d)
        _forma(d)

        escribio = False

        # Cuentas: solo filas agregadas, cambiadas o borradas
        ctas_despues = {str(k): v for k, v in d["cuentas"].items()}
        for k, v in ctas_despues.items():
            s = _dumps(v)
            if cuentas_antes.get(k) != s:
                con.execute(
                    "INSERT INTO cuentas(usn, datos) VALUES (?, ?) "
                    "ON CONFLICT(usn) DO UPDATE SET datos = excluded.datos",
                    (k, s),
                )
                escribio = True
        for k in cuentas_antes:
            if k not in ctas_despues:
                con.execute("DELETE FROM cuentas WHERE usn = ?", (k,))
                escribio = True

        # Usuarios: solo filas agregadas, cambiadas o borradas
        usrs_obj = d.get("usuarios")
        usrs_despues = {str(k): v for k, v in usrs_obj.items()} if isinstance(usrs_obj, dict) else {}
        for k, v in usrs_despues.items():
            s = _dumps(v)
            if usuarios_antes.get(k) != s:
                con.execute(
                    "INSERT INTO usuarios(steamid, datos) VALUES (?, ?) "
                    "ON CONFLICT(steamid) DO UPDATE SET datos = excluded.datos",
                    (k, s),
                )
                escribio = True
        for k in usuarios_antes:
            if k not in usrs_despues:
                con.execute("DELETE FROM usuarios WHERE steamid = ?", (k,))
                escribio = True

        # Sesiones: solo filas agregadas, cambiadas o borradas
        ses_obj = d.get("sesiones")
        ses_despues = {str(k): v for k, v in ses_obj.items()} if isinstance(ses_obj, dict) else {}
        for k, v in ses_despues.items():
            s = _dumps(v)
            if sesiones_antes.get(k) != s:
                exp = float(v.get("expira", 0) or 0) if isinstance(v, dict) else 0.0
                con.execute(
                    "INSERT INTO sesiones(gsn, datos, expira) VALUES (?, ?, ?) "
                    "ON CONFLICT(gsn) DO UPDATE SET datos = excluded.datos, expira = excluded.expira",
                    (k, s, exp),
                )
                escribio = True
        for k in sesiones_antes:
            if k not in ses_despues:
                con.execute("DELETE FROM sesiones WHERE gsn = ?", (k,))
                escribio = True

        # Claves de arriba (version, mudadas, huerfanas y cualquier otra)
        arriba_despues = {str(k): v for k, v in d.items() if k not in _CLAVES_TABLA}
        for k, v in arriba_despues.items():
            s = _dumps(v)
            if arriba_antes.get(k) != s:
                con.execute(
                    "INSERT INTO arriba(clave, datos) VALUES (?, ?) "
                    "ON CONFLICT(clave) DO UPDATE SET datos = excluded.datos",
                    (k, s),
                )
                escribio = True
        for k in arriba_antes:
            if k not in arriba_despues:
                con.execute("DELETE FROM arriba WHERE clave = ?", (k,))
                escribio = True

        return escribio, res
    return _ejecutar_escritura_db(tx)


def _sql_cambiar(usn, funcion):
    clave = str(usn)
    def tx(con):
        row = con.execute("SELECT datos FROM cuentas WHERE usn = ?", (clave,)).fetchone()
        if row is None:
            return False, None
        antes_raw = row[0]
        acc = _loads(antes_raw)
        nuevo = funcion(acc)
        if nuevo is not None:
            acc = nuevo
        despues_raw = _dumps(acc)
        if despues_raw != antes_raw:
            con.execute("UPDATE cuentas SET datos = ? WHERE usn = ?", (despues_raw, clave))
            return True, copy.deepcopy(acc)
        return False, copy.deepcopy(acc)
    return _ejecutar_escritura_db(tx)


def _sql_leer_seccion(usn, seccion):
    clave = str(usn)
    def q(con):
        row = con.execute("SELECT datos FROM cuentas WHERE usn = ?", (clave,)).fetchone()
        if row is not None:
            return _loads(row[0]).get(seccion) or {}
        hr = con.execute("SELECT datos FROM arriba WHERE clave = 'huerfanas'").fetchone()
        if hr is None:
            return {}
        return ((_loads(hr[0]) or {}).get(seccion) or {}).get(clave) or {}
    return _ejecutar_lectura_db(q)


def _sql_cambiar_seccion(usn, seccion, funcion):
    clave = str(usn)
    def tx(con):
        row = con.execute("SELECT datos FROM cuentas WHERE usn = ?", (clave,)).fetchone()
        if row is not None:
            antes_raw = row[0]
            acc = _loads(antes_raw)
            existia = seccion in acc
            contenido = acc.setdefault(seccion, {})
            res = funcion(contenido)
            if not existia and not contenido:
                del acc[seccion]
            despues_raw = _dumps(acc)
            if despues_raw != antes_raw:
                con.execute("UPDATE cuentas SET datos = ? WHERE usn = ?", (despues_raw, clave))
                return True, res
            return False, res

        hr = con.execute("SELECT datos FROM arriba WHERE clave = 'huerfanas'").fetchone()
        antes_raw = hr[0] if hr is not None else None
        huerf = _loads(antes_raw) if antes_raw is not None else {}
        lugar = huerf.setdefault(seccion, {})
        existia = clave in lugar
        contenido = lugar.setdefault(clave, {})
        res = funcion(contenido)
        if not existia and not contenido:
            del lugar[clave]
        if not huerf.get(seccion):
            huerf.pop(seccion, None)
        if huerf:
            despues_raw = _dumps(huerf)
            if despues_raw != antes_raw:
                con.execute(
                    "INSERT INTO arriba(clave, datos) VALUES ('huerfanas', ?) "
                    "ON CONFLICT(clave) DO UPDATE SET datos = excluded.datos",
                    (despues_raw,),
                )
                return True, res
            return False, res
        if antes_raw is not None:
            con.execute("DELETE FROM arriba WHERE clave = 'huerfanas'")
            return True, res
        return False, res
    return _ejecutar_escritura_db(tx)


def _sql_poner_secciones(seccion, contenidos):
    if not contenidos:
        _asegurar_db()
        return None
    def tx(con):
        escribio = False
        huerf_cargadas = False
        huerf_antes = None
        huerf = None
        for usn, c in contenidos.items():
            clave = str(usn)
            row = con.execute("SELECT datos FROM cuentas WHERE usn = ?", (clave,)).fetchone()
            if row is not None:
                acc = _loads(row[0])
                acc[seccion] = copy.deepcopy(c)
                despues_raw = _dumps(acc)
                if despues_raw != row[0]:
                    con.execute("UPDATE cuentas SET datos = ? WHERE usn = ?", (despues_raw, clave))
                    escribio = True
            else:
                if not huerf_cargadas:
                    hr = con.execute("SELECT datos FROM arriba WHERE clave = 'huerfanas'").fetchone()
                    huerf_antes = hr[0] if hr is not None else None
                    huerf = _loads(huerf_antes) if huerf_antes is not None else {}
                    huerf_cargadas = True
                huerf.setdefault(seccion, {})[clave] = copy.deepcopy(c)
        if huerf_cargadas:
            despues_h = _dumps(huerf)
            if despues_h != huerf_antes:
                con.execute(
                    "INSERT INTO arriba(clave, datos) VALUES ('huerfanas', ?) "
                    "ON CONFLICT(clave) DO UPDATE SET datos = excluded.datos",
                    (despues_h,),
                )
                escribio = True
        return escribio, None
    return _ejecutar_escritura_db(tx)


def _sql_huerfanas():
    def q(con):
        hr = con.execute("SELECT datos FROM arriba WHERE clave = 'huerfanas'").fetchone()
        return (_loads(hr[0]) or {}) if hr is not None else {}
    return _ejecutar_lectura_db(q)


def _sql_usuarios():
    def q(con):
        rows = con.execute("SELECT steamid, datos FROM usuarios ORDER BY rowid").fetchall()
        return {k: _loads(v) for k, v in rows}
    return _ejecutar_lectura_db(q)


def _sql_usuario(steamid):
    clave = str(steamid)
    def q(con):
        row = con.execute("SELECT datos FROM usuarios WHERE steamid = ?", (clave,)).fetchone()
        return _loads(row[0]) if row is not None else None
    return _ejecutar_lectura_db(q)


def _sql_usuario_por(campo, valor):
    usa_extract = isinstance(valor, (int, float, str)) and not isinstance(valor, bool)
    ruta_j = "$.%s" % campo
    def q(con):
        if usa_extract:
            try:
                rows = con.execute(
                    "SELECT datos FROM usuarios WHERE json_extract(datos, ?) = ? ORDER BY rowid",
                    (ruta_j, valor),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = con.execute("SELECT datos FROM usuarios ORDER BY rowid").fetchall()
        else:
            rows = con.execute("SELECT datos FROM usuarios ORDER BY rowid").fetchall()
        for (raw,) in rows:
            u = _loads(raw)
            if u.get(campo) == valor:
                return u
        return None
    return _ejecutar_lectura_db(q)


def _sql_guardar_sesion(gsn, datos_sesion):
    ahora = time.time()
    clave_g = str(gsn)
    registro = {
        "clave": str(datos_sesion["clave"]),
        "sesion_id": int(datos_sesion["sesion_id"]),
        "usuario": str(datos_sesion["usuario"]),
        "expira": float(datos_sesion["expira"]),
    }
    raw = _dumps(registro)
    def tx(con):
        con.execute("DELETE FROM sesiones WHERE expira < ?", (ahora,))
        con.execute(
            "INSERT INTO sesiones(gsn, datos, expira) VALUES (?, ?, ?) "
            "ON CONFLICT(gsn) DO UPDATE SET datos = excluded.datos, expira = excluded.expira",
            (clave_g, raw, registro["expira"]),
        )
        return True, copy.deepcopy(registro)
    return _ejecutar_escritura_db(tx)


def _sql_sesion(gsn):
    clave_g = str(gsn)
    def q(con):
        row = con.execute("SELECT datos FROM sesiones WHERE gsn = ?", (clave_g,)).fetchone()
        if row is None:
            return None
        s = _loads(row[0])
        return s if isinstance(s, dict) else None
    return _ejecutar_lectura_db(q)


# ---------- API publica ----------

def todas():
    """{usn en texto: cuenta} de todas las cuentas (copia)."""
    if _usar_sqlite():
        return _sql_todas()
    return _cargar()["cuentas"]


def leer(usn):
    """La cuenta de ese usn (copia) o None."""
    if _usar_sqlite():
        return _sql_leer(usn)
    return todas().get(str(usn))


def buscar(seccion, campo, valor):
    """(usn en texto, cuenta) de la primera cuenta cuya seccion tiene campo == valor, o (None, None)."""
    if _usar_sqlite():
        return _sql_buscar(seccion, campo, valor)
    for k, acc in todas().items():
        if (acc.get(seccion) or {}).get(campo) == valor:
            return k, acc
    return None, None


def cambiar_todas(funcion):
    """Con el candado: relee, llama funcion(d) sobre {"cuentas": {...}} y escribe. Devuelve lo que devuelva funcion.
    Si funcion falla no se escribe nada."""
    if _usar_sqlite():
        return _sql_cambiar_todas(funcion)
    _asegurar()               # fuera del candado: la mudanza toma el suyo
    with _Candado():
        d = _cargar(False)
        antes = copy.deepcopy(d)
        res = funcion(d)
        if d != antes:
            _escribir(_ruta_json(), d)
        return res


def cambiar(usn, funcion):
    """Con el candado: relee la cuenta, llama funcion(cuenta) (cambia el dict, o devuelve uno nuevo) y la escribe.
    Devuelve la cuenta ya cambiada, o None si no existe."""
    if _usar_sqlite():
        return _sql_cambiar(usn, funcion)
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
    if _usar_sqlite():
        return _sql_leer_seccion(usn, seccion)
    d = _cargar()
    acc = d["cuentas"].get(str(usn))
    if acc is not None:
        return acc.get(seccion) or {}
    return ((d.get("huerfanas") or {}).get(seccion) or {}).get(str(usn)) or {}


def cambiar_seccion(usn, seccion, funcion):
    """Con el candado: relee, llama funcion(contenido) con la seccion de ese usn (un dict que funcion cambia EN EL LUGAR) y
    escribe si cambio. Si el usn no es de ninguna cuenta usa la huerfana d["huerfanas"][seccion][usn]. Devuelve lo que
    devuelva funcion (que devuelva copias, no el dict). Una seccion que quedo vacia no deja entrada nueva."""
    if _usar_sqlite():
        return _sql_cambiar_seccion(usn, seccion, funcion)
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
    if _usar_sqlite():
        return _sql_poner_secciones(seccion, contenidos)
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
    if _usar_sqlite():
        return _sql_huerfanas()
    return _cargar().get("huerfanas") or {}


def usuarios():
    """{steamid: usuario} de todas las cuentas Eñeños (copia)."""
    if _usar_sqlite():
        return _sql_usuarios()
    return copy.deepcopy(_cargar().get("usuarios") or {})


def usuario(steamid):
    """La cuenta Eñeños de ese steamid (copia) o None."""
    if _usar_sqlite():
        return _sql_usuario(steamid)
    return copy.deepcopy((_cargar().get("usuarios") or {}).get(str(steamid)))


def usuario_por_gsn(gsn):
    """La cuenta Eñeños cuyo gsn coincide (copia) o None."""
    if _usar_sqlite():
        return _sql_usuario_por("gsn", gsn)
    for u in (_cargar().get("usuarios") or {}).values():
        if u.get("gsn") == gsn:
            return copy.deepcopy(u)
    return None


def usuario_por_puerto(puerto):
    """La cuenta Eñeños cuyo puerto coincide (copia) o None."""
    if _usar_sqlite():
        return _sql_usuario_por("puerto", puerto)
    for u in (_cargar().get("usuarios") or {}).values():
        if u.get("puerto") == puerto:
            return copy.deepcopy(u)
    return None


def guardar_sesion(gsn, datos_sesion):
    """Con el candado: guarda datos_sesion en d['sesiones'][str(gsn)] y poda las sesiones vencidas."""
    if _usar_sqlite():
        return _sql_guardar_sesion(gsn, datos_sesion)
    ahora = time.time()

    def f(d):
        sesiones = d.setdefault("sesiones", {})
        for k in [k for k, v in list(sesiones.items()) if not isinstance(v, dict) or v.get("expira", 0) < ahora]:
            del sesiones[k]
        clave_g = str(gsn)
        sesiones[clave_g] = {
            "clave": str(datos_sesion["clave"]),
            "sesion_id": int(datos_sesion["sesion_id"]),
            "usuario": str(datos_sesion["usuario"]),
            "expira": float(datos_sesion["expira"]),
        }
        return copy.deepcopy(sesiones[clave_g])
    return cambiar_todas(f)


def sesion(gsn):
    """La sesion guardada de ese gsn (copia) o None."""
    if _usar_sqlite():
        return _sql_sesion(gsn)
    s = (_cargar().get("sesiones") or {}).get(str(gsn))
    return copy.deepcopy(s) if isinstance(s, dict) else None
