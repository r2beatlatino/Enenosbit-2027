# -*- coding: utf-8 -*-
r"""cupon.py (M14, 22-nov) — canje de cupones por chat (`.cupon <codigo>`) con persistencia en cuenta.json.

Medicion (docs/tablero_maduracion/M14_cupones_y_regalo_diario.md):
  - En el cliente moderno NO existe FF158 ni ventana medida para ingresar codigos de cupon (tabla_ff_cruce.json, MAPA.md).
  - Por eso el canje entra por el camino del chat (FF1F4 y FF08, enganche en charla.py) y contesta SOLO al que lo pidio
    con la forma medida de S2C FF1F4 tipo 1 de 161 B (`gm.cuerpo_anuncio`, layouts/FF1F4.md).
  - Regalo diario: `sello.py` es sello XXTEA (no sello diario) y el 2013 no tiene regalo diario automatico por entrar
    (solo `mision_hoy.py`, cuyo equivalente moderno ya esta en `progresion.py`): no se agrega regalo diario.

Archivo de codigos: `cupones.json` en `ajustes.carpeta_cuenta()` (junto a `cuenta.json`, fuera de git):
  {codigo: {"items": [[item, cantidad, vence]], "g": n, "diamantes": n, "usos_max": n, "vence": fecha}}
  - `usos_max`: tope global entre todas las cuentas (0 o None = sin tope global; siempre maximo 1 vez por cuenta).
  - `vence`: None / "" / 0 (no vence), epoch unix (int/float), o fecha texto ("AAAA-MM-DD", "AAAA-MM-DD HH:MM", ISO).
  - `items`: lista de `[item, cantidad, vence]` (cantidad por omision 1; vence 0/None = permanente, 1..36500 = dias, o epoch).

Guardado del canje: seccion `"cupones"` en `cuenta.json` (via cuenta.py): `{"canjeados": {"CODIGO": epoch}}`.
Llave `CUPONES` (entorno, leida en el momento, por omision `"1"`): con `"0"` todo se comporta igual que antes.
"""
from datetime import datetime
import json
import os
import threading
import time

import ajustes
import cuenta
import estado
import gm
import textos
import tienda

REMITENTE = "Cupon"
OK, INVALIDO, DOBLE, AGOTADO, VENCIDO, ERROR = "ok", "invalido", "doble", "agotado", "vencido", "error"
LARGO_MAX_CODIGO = 32
DIAS_MAX_PLAZO = 36500

# Reloj del modulo (las pruebas pueden reemplazarlo para probar vencimientos sin esperar).
reloj = time.time

_archivo_lock = threading.Lock()


def anotar(txt):
    estado.anotar(txt)


def activo():
    """Llave CUPONES (entorno, leida en el momento, por omision '1')."""
    return os.environ.get("CUPONES", "1").strip().lower() not in ("0", "no", "false", "")


def ruta():
    """Ubicacion de cupones.json: junto a cuenta.json en ajustes.carpeta_cuenta()."""
    return os.path.join(ajustes.carpeta_cuenta(), "cupones.json")


def normalizar(codigo):
    """Limpia espacios y pasa a mayusculas para comparar codigos sin sensibilidad a caja."""
    return str(codigo or "").strip().upper()


def _quien_de(con):
    cta = getattr(con, "cuenta", None) or {}
    pj = cta.get("personaje") or {}
    nick = str(pj.get("nick") or cta.get("nick") or "?").strip()
    usn = cta.get("usn")
    return "%s (usn %s)" % (nick, usn) if usn else nick


def _parsear_vence(valor):
    """Convierte `vence` de un cupon a epoch float, o None si no vence. ValueError si no se entiende."""
    if valor in (None, "", 0):
        return None
    if isinstance(valor, bool):
        raise ValueError("vence booleano invalido")
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    t = str(valor).strip()
    if not t:
        return None
    t_esp = t.replace("T", " ")
    for fmt, fin_dia in (
        ("%Y-%m-%d %H:%M:%S", 0),
        ("%Y-%m-%d %H:%M", 0),
        ("%Y-%m-%d", 86399),
        ("%Y%m%d", 86399),
    ):
        try:
            return datetime.strptime(t_esp, fmt).timestamp() + fin_dia
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise ValueError("fecha vence invalida: %r" % valor)


def _vence_item(valor, ahora):
    """Vence para tienda.dar_objeto: 0/None -> PERMANENTE, 1..36500 -> dias desde ahora, otro int -> epoch/PERMANENTE."""
    if valor in (None, "", 0):
        return tienda.PERMANENTE
    if isinstance(valor, bool) or not isinstance(valor, int):
        return valor
    if valor == tienda.PERMANENTE:
        return tienda.PERMANENTE
    if 1 <= valor <= DIAS_MAX_PLAZO:
        return int(ahora) + valor * 86400
    return valor


def cargar_cupones():
    """Lee cupones.json -> {CODIGO_NORMALIZADO: regla}. Si falta devuelve {}; si esta roto anota y devuelve {}."""
    r = ruta()
    try:
        with open(r, "r", encoding="utf-8") as f:
            crudo = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        anotar("   ⛔ cupon: no se pudo leer %s (%s)" % (r, e))
        return {}
    if not isinstance(crudo, dict):
        anotar("   ⛔ cupon: %s no es un objeto JSON" % r)
        return {}
    out = {}
    for k, v in crudo.items():
        nk = normalizar(k)
        if nk and isinstance(v, dict):
            out[nk] = v
    return out


def _escribir_cupones(mapa):
    r = ruta()
    os.makedirs(os.path.dirname(r), exist_ok=True)
    tmp = "%s.tmp%d" % (r, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    for _ in range(200):
        try:
            os.replace(tmp, r)
            return
        except PermissionError:
            time.sleep(0.005)
    os.replace(tmp, r)


def crear(codigo, g=0, diamantes=0, items=None, usos_max=0, vence=None):
    """Agrega un cupon nuevo a cupones.json. ValueError si el codigo ya existe o los datos son invalidos."""
    k = normalizar(codigo)
    if not k or any(c.isspace() for c in k) or len(k) > LARGO_MAX_CODIGO:
        raise ValueError("codigo invalido")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (g, diamantes, usos_max)):
        raise ValueError("g, diamantes y usos_max deben ser enteros >= 0")
    lista_items = list(items or [])
    if g == 0 and diamantes == 0 and not lista_items:
        raise ValueError("el cupon debe otorgar al menos G, diamantes o un item")
    if vence not in (None, "", 0):
        _parsear_vence(vence)
    regla = {
        "items": lista_items,
        "g": int(g),
        "diamantes": int(diamantes),
        "usos_max": int(usos_max),
        "vence": vence,
    }
    with _archivo_lock:
        actuales = cargar_cupones()
        if k in actuales:
            raise ValueError("ya existe el cupon %s" % k)
        actuales[k] = regla
        _escribir_cupones(actuales)
    return k, regla


def _acreditar_diamantes(con, cantidad):
    """Suma diamantes a la seccion `tienda` de la cuenta de `con`, preparando la bolsa si falta."""
    def sumar(b):
        b["diamantes"] = int(b.get("diamantes", tienda.SALDO_INICIAL)) + int(cantidad)
        return b["diamantes"]
    total = tienda._con_bolsa(con, sumar)
    anotar("   +%d diamantes a %s (ahora %d)" % (cantidad, (con.cuenta or {}).get("nick"), total))
    return total


def _deshacer_canje(usn, k):
    try:
        def quitar(sec):
            canj = sec.get("canjeados")
            if isinstance(canj, dict):
                canj.pop(k, None)
        cuenta.cambiar_seccion(usn, "cupones", quitar)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ cupon: no se pudo revertir %s en usn %s: %r" % (k, usn, e))


def canjear(con, codigo_texto):
    """Valida, registra en la cuenta (via cuenta.py) y acredita el premio del cupon.
    Devuelve dict {ok, estado, motivo, codigo, g, diamantes, items}."""
    def fallo(est, motivo, cod=""):
        return {"ok": False, "estado": est, "motivo": motivo, "codigo": cod, "g": 0, "diamantes": 0, "items": []}

    if not activo():
        return fallo(INVALIDO, "cupones desactivados")
    cta = getattr(con, "cuenta", None) or {}
    usn = cta.get("usn")
    if not usn:
        return fallo(ERROR, "cupon: requiere cuenta local")
    k = normalizar(codigo_texto)
    if not k:
        return fallo(INVALIDO, "cupon invalido")
    regla = cargar_cupones().get(k)
    if not isinstance(regla, dict):
        return fallo(INVALIDO, "el cupon %s no existe" % k, k)

    ahora = float(reloj())
    try:
        ts_vence = _parsear_vence(regla.get("vence"))
    except ValueError:
        return fallo(VENCIDO, "el cupon %s tiene fecha invalida" % k, k)
    if ts_vence is not None and ahora > ts_vence:
        return fallo(VENCIDO, "el cupon %s esta vencido" % k, k)

    raw_max = regla.get("usos_max", 0)
    try:
        usos_max = 0 if raw_max is None else int(raw_max)
        g = int(regla.get("g") or 0)
        diamantes = int(regla.get("diamantes") or 0)
    except (ValueError, TypeError):
        return fallo(INVALIDO, "el cupon %s esta mal configurado" % k, k)
    if usos_max < 0:
        return fallo(AGOTADO, "el cupon %s esta agotado" % k, k)
    if g < 0 or diamantes < 0:
        return fallo(INVALIDO, "el cupon %s esta mal configurado" % k, k)

    raw_items = regla.get("items") or []
    if not isinstance(raw_items, list):
        return fallo(INVALIDO, "el cupon %s esta mal configurado" % k, k)
    items_norm = []
    for entrada in raw_items:
        if not isinstance(entrada, (list, tuple)) or not 1 <= len(entrada) <= 3:
            return fallo(INVALIDO, "el cupon %s tiene un item mal formado" % k, k)
        item_id = entrada[0]
        cant = entrada[1] if len(entrada) >= 2 else 1
        vence_raw = entrada[2] if len(entrada) >= 3 else tienda.PERMANENTE
        items_norm.append((item_id, cant, _vence_item(vence_raw, ahora)))
    if g == 0 and diamantes == 0 and not items_norm:
        return fallo(INVALIDO, "el cupon %s no tiene premio" % k, k)

    def reservar(d):
        cuentas_map = d.get("cuentas") or {}
        acc = cuentas_map.get(str(usn))
        if acc is None:
            return ERROR, "cupon: cuenta local no encontrada"
        canjeados = (acc.get("cupones") or {}).get("canjeados") or {}
        if k in canjeados:
            return DOBLE, "ya canjeaste el cupon %s" % k
        if usos_max > 0:
            usados = sum(
                1 for a in cuentas_map.values()
                if k in ((a.get("cupones") or {}).get("canjeados") or {})
            )
            if usados >= usos_max:
                return AGOTADO, "el cupon %s esta agotado" % k
        acc.setdefault("cupones", {}).setdefault("canjeados", {})[k] = int(ahora)
        return OK, "canjeado"

    try:
        est, mot = cuenta.cambiar_todas(reservar)
    except cuenta.CuentaError as e:
        anotar("   ⛔ cupon %s usn %s: %s" % (k, usn, e))
        return fallo(ERROR, "cupon: error al guardar en la cuenta", k)
    if est != OK:
        return fallo(est, mot, k)

    entregados = []
    algo_dado = False
    try:
        if g > 0:
            tienda.acreditar(con, exp=0, g=g)
            algo_dado = True
        if diamantes > 0:
            _acreditar_diamantes(con, diamantes)
            algo_dado = True
        for item_id, cant, vence_it in items_norm:
            res_it = tienda.dar_objeto(usn, item_id, cant, vence_it, con=con)
            entregados.append({"item": item_id, "cantidad": cant, "resultado": res_it})
            if res_it.get("estado") == tienda.DADO:
                algo_dado = True
        if g > 0 or diamantes > 0:
            tienda.refrescar_saldos(con, g=g > 0, diamantes=diamantes > 0)
    except Exception as e:                                               # noqa: BLE001
        if not algo_dado:
            _deshacer_canje(usn, k)
        anotar("   ⛔ cupon %s entrega usn %s: %r" % (k, usn, e))
        return fallo(ERROR, "cupon: error al acreditar el premio", k)

    partes = []
    if g > 0:
        partes.append("+%d G" % g)
    if diamantes > 0:
        partes.append("+%d diamantes" % diamantes)
    dados_n = sum(1 for x in entregados if x["resultado"].get("estado") == tienda.DADO)
    if dados_n:
        partes.append("%d item(s)" % dados_n)
    elif entregados:
        partes.append("items sin cambios")
    resumen = "cupon %s canjeado: %s" % (k, ", ".join(partes) if partes else "ok")
    return {"ok": True, "estado": OK, "motivo": resumen, "codigo": k, "g": g, "diamantes": diamantes, "items": entregados}


def _avisar_uno(con, texto):
    """Manda S2C FF1F4 tipo 1 (161 B, forma medida) SOLO al jugador que pidio el cupon."""
    if con is None or getattr(con, "cerrada", False):
        return False
    try:
        con.mandar_interno(0x1F4, 0, gm.cuerpo_anuncio(texto, remitente=REMITENTE))
        return True
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ cupon aviso a uno: %r" % e)
        return False


def atender(con, texto):
    """Enganche para el camino del chat (FF1F4 y FF08). Devuelve True si se atendio `.cupon` (no se difunde como chat);
    False si la llave CUPONES esta en 0 o el texto no es `.cupon`."""
    if not activo():
        return False
    if isinstance(texto, (bytes, bytearray)):
        txt = textos.decodificar(bytes(texto)).strip()
    else:
        txt = str(texto or "").strip()
    if not txt.startswith("."):
        return False
    partes = txt[1:].split()
    if not partes or partes[0].lower() != "cupon":
        return False
    quien = _quien_de(con)
    if len(partes) < 2:
        anotar("   CUPON %s | .cupon | sin codigo" % quien)
        _avisar_uno(con, "uso: .cupon <codigo>")
        return True
    res = canjear(con, partes[1])
    _avisar_uno(con, res["motivo"])
    anotar("   CUPON %s | .cupon %s -> %s (%s)" % (quien, normalizar(partes[1]), res["estado"].upper(), res["motivo"]))
    return True
