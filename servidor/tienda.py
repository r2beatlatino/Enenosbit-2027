# -*- coding: utf-8 -*-
r"""tienda.py (02-nov) — la TIENDA del cliente de Steam (Fase 5). Contrato: notas 07 (regla) y 08 (bytes) de S-2013.

Lo medido:
  C2S FF50 CmdBuyCashItem (5 B, en vivo 02-nov): [codigo u32][tipo u8]. El codigo es el item con el PLAZO en el digito
      de los miles (regla del 2013); el tipo dice con que se paga (6, 0x0F, 0x0D segun quien llama; nota 08 §1).
  S2C FF50: Steam lee 4,4,4,4,1,1,4,4 (26 B). ⚠ HIPOTESIS de la nota 08 §2 (el 2019 manda 15 B):
      [resultado u32 0=OK][codigo u32][vence u32 0xEEFFCBB8 = permanente][saldo u32][tipo u8][u8 0][u32 0][u32 0]
      Se mide en vivo: si el dialogo cierra y el saldo baja, va.
  S2C FF51 CmdGetCashAmount (lee 1,4): el oficial manda siempre `01 00000000` (01 + saldo de diamantes).

Lo guardado (fuera de git): datos/cuenta.json, seccion `tienda` de cada cuenta -> {"diamantes": n, "items": [[item, vence,
cantidad, fecha], ...], "basicas", "exp", "g", "regalos"} (antes datos/tienda.json, que ya no se escribe). Todo va por cuenta.py.
SALDO_INICIAL (diamantes de una cuenta nueva) es una DECISION local, no del oficial: ⏳ que la confirme Benja.
"""
import copy
import json
import struct
import time

import ajustes
import captura
import catalogo
import cuenta as _cta     # el unico que abre los archivos de cuentas; aca la tienda es la seccion `tienda`
import estado
import fichas
import textos

PERMANENTE = fichas.PERMANENTE
LARGO_REGISTRO = 17           # un item del inventario en el FF49 y en la ficha FF00
COLA_FIJA = 6 * 4 + 2 + 2     # al final del FF49: 6 x u32, u16, u16
SALDO_INICIAL = ajustes.SALDO_INICIAL


def anotar(txt):
    estado.anotar(txt)


def _usn_de(con):
    return str((con.cuenta or {}).get("usn", 0))


def _preparar(b, basicas):
    """Dentro de cuenta.cambiar_seccion: crea la bolsa si falta (la ropa basica = la del personaje al abrirla) y da los
    regalos que falten. b es la seccion `tienda` de la cuenta y se cambia en el lugar."""
    if not b:
        b.update({"diamantes": SALDO_INICIAL, "items": [], "basicas": basicas})
    dados = b.setdefault("regalos", [])
    for item, cant in REGALOS.items():
        if item not in dados:
            b["items"].append([item, PERMANENTE, cant, int(time.time())])
            dados.append(item)


def _con_bolsa(con, f):
    """Con el candado de cuenta.py: prepara la bolsa de esta cuenta y llama f(bolsa) (cambia en el lugar). Devuelve lo que
    devuelva f. Solo escribe si algo cambio. Sin cuenta (sesion capturada, usn 0) usa la bolsa huerfana del usn 0."""
    basicas = list((((con.cuenta or {}).get("personaje")) or {}).get("partes", []))

    def g(b):
        _preparar(b, basicas)
        return f(b)
    return _cta.cambiar_seccion(_usn_de(con), "tienda", g)


def _cargar():
    """{usn: bolsa} de todas las bolsas (cuentas y huerfanas), solo lectura; lo que antes era tienda.json."""
    d = _cta.todas()
    r = {k: a["tienda"] for k, a in d.items() if a.get("tienda")}
    r.update({k: v for k, v in _cta.huerfanas().get("tienda", {}).items() if v})
    return r


def _guardar(d):
    """Pone cada bolsa de d (una sola vez, con el candado). Lo que d no nombra no se toca."""
    _cta.poner_secciones("tienda", d)


def bolsa(con):
    """({usn: copia de la bolsa}, usn). Crea la bolsa y da los regalos si faltan."""
    usn = _usn_de(con)
    return {usn: _con_bolsa(con, lambda b: copy.deepcopy(b))}, usn


# 3-nov: el MODO HEROE (英雄模式) pide en el START un consumible, «英雄凭证» = item 11000491 (shop.txt: Cash, PN 90, oculto
# en la tienda); el texto del juego dice que se gana jugando ese modo (el huevo y la gallina para una cuenta nueva).
# DECISION (Benja la confirma): cada cuenta recibe una vez REGALOS. ⏳ la cantidad y si se gastan al jugar.
# + 3-nov: un 金戒指 = el 玩伴信物 para proponer pareja. El inventario guarda el INDEX de ring.txt (30xxx; la ficha del
# oficial trae 30084), no el ChargeId (36xxx): con 36005 no aparecia
REGALOS = {11000491: 10, 30005: 1}


def acreditar(con, exp=0, g=0):
    """Suma exp y G (las monedas del cartel) a la cuenta, en la seccion `tienda` de cuenta.json. El nivel no se guarda: lo
    calcula el cliente con la tabla de su exe (nota 11 §4)."""
    def sumar(b):
        b["exp"] = b.get("exp", 0) + exp
        b["g"] = b.get("g", 0) + g
        return b["exp"], b["g"]
    exp_total, g_total = _con_bolsa(con, sumar)
    try:
        import progresion
        progresion.ganancia(con, exp, g)                  # ficha 83: cuenta para las misiones de monedas y EXP
    except Exception as e:                                # noqa: BLE001
        anotar("   ⛔ progresion.ganancia: %r" % e)
    anotar("   +%d exp, +%d G a %s (ahora exp %d, G %d)" % (exp, g, (con.cuenta or {}).get("nick"), exp_total, g_total))


# ---------- dar un objeto a una cuenta (ficha 61) ----------
DADO, YA_ESTABA, RECHAZADO = "dado", "ya_estaba", "rechazado"
CANTIDAD_MAXIMA = 9999           # la cantidad viaja en un u16 y la ficha FF00 (fichas.registro_ok) solo acepta menos de 10000
ITEM_MAXIMO = 100_000_000        # la misma cota que fichas.registro_ok: un item mayor haria invisible el inventario de la ficha
FECHA_MINIMA, FECHA_MAXIMA = 1_500_000_000, 2_200_000_000     # un "vence" que no es 0 ni PERMANENTE tiene que ser una fecha
OPCODE_AGREGAR_OBJETO = 0xCE     # FFCE CmdAddItem [u32][u32][u16][u8] (layouts/FFCE.md)


def _resultado(estado, motivo="", cantidad=0):
    """Lo que devuelve dar_objeto: estado (DADO / YA_ESTABA / RECHAZADO), motivo en una linea y la cantidad que queda."""
    return {"estado": estado, "motivo": motivo, "cantidad": cantidad}


def _motivo_invalido(item, cantidad, vence):
    """'' si item, cantidad y vence se pueden guardar en un registro de 17 B que la ficha FF00 acepta; si no, el motivo."""
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (item, cantidad, vence)):
        return "item, cantidad y vence tienen que ser enteros"
    if not 0 < item < ITEM_MAXIMO:
        return "item %d fuera de rango" % item
    if not 1 <= cantidad <= CANTIDAD_MAXIMA:
        return "cantidad %d fuera de 1..%d" % (cantidad, CANTIDAD_MAXIMA)
    if vence not in (0, PERMANENTE) and not FECHA_MINIMA < vence < FECHA_MAXIMA:
        return "vence %d no es 0, PERMANENTE ni una fecha" % vence
    return ""


def _catalogo_leido():
    """True si datos/catalogo.json se pudo leer (si no, catalogo.ficha da None para todo y no prueba que falte el objeto)."""
    return catalogo.cargado()


def _es_de_cantidad(ficha):
    """Los objetos que el catalogo vende por cantidad (trae PN) se suman; los demas se tienen o no se tienen."""
    return bool(ficha) and ficha.get("n") is not None


def _basicas_de(usn):
    """La ropa del personaje de esa cuenta (para crear la bolsa si falta), igual que _con_bolsa; [] si no hay personaje."""
    acc = _cta.leer(usn) if usn else None
    return list((((acc or {}).get("personaje")) or {}).get("partes", []))


def _permanente(vence):
    """True si el registro no vence nunca (0 o PERMANENTE)."""
    return vence in (0, PERMANENTE)


def _agregar(items, item, cantidad, vence, de_cantidad, dias=0):
    """En el lugar, dentro del candado: suma o agrega el registro [item, vence, cantidad, fecha] (la misma forma que deja una
    compra: cantidad 0 en lo que no es de cantidad). `dias` > 0 (ficha 63, compra con plazo): si ya lo tiene con fecha, la
    corre `dias` mas (HIPOTESIS: renovar suma) y si ya lo tiene con fecha y esto es permanente, lo pasa a permanente.
    Lo permanente no se toca. -> resultado"""
    for reg in items:
        if reg[0] != item:
            continue
        if de_cantidad:
            reg[2] = min(reg[2] + cantidad, CANTIDAD_MAXIMA)
            return _resultado(DADO, "sumado a lo que habia", reg[2])
        if _permanente(reg[1]):
            return _resultado(YA_ESTABA, "ya estaba en el inventario", reg[2])
        if vence == PERMANENTE:
            reg[1] = PERMANENTE
            return _resultado(DADO, "paso de plazo a permanente", reg[2])
        if dias > 0:
            reg[1] = max(reg[1], int(time.time())) + dias * 86400
            return _resultado(DADO, "plazo renovado %d dias" % dias, reg[2])
        return _resultado(YA_ESTABA, "ya estaba en el inventario", reg[2])
    items.append([item, vence, cantidad if de_cantidad else 0, int(time.time())])
    return _resultado(DADO, "agregado", cantidad if de_cantidad else 0)


def llave_ffce():
    """True si datos/pruebas.json trae "ffce": true (se lee en cada llamada, como carrera.pruebas). Apagada por omision."""
    try:
        with open(ajustes.RUTA_PRUEBAS, encoding="utf-8") as f:
            return json.load(f).get("ffce") is True
    except (OSError, ValueError, AttributeError):
        return False


def avisar_ffce(con, item, cantidad):
    """Si la llave "ffce" esta prendida, manda al cliente conectado el FFCE [item u32][?? u32][cantidad u16][en uso u8].
    HIPOTESIS: el 2.o campo no esta identificado (se manda 0) y el cliente puede no mostrar nada; por eso esta apagado."""
    if con is None or not llave_ffce():
        return False
    con.mandar_interno(OPCODE_AGREGAR_OBJETO, 0, struct.pack("<IIHB", item, 0, cantidad, 0))
    anotar("   S2C FFCE aviso del objeto %d x%d (llave ffce, 2.o campo sin identificar)" % (item, cantidad))
    return True


def dar_objeto(usn, item, cantidad=1, vence=PERMANENTE, con=None):
    """Guarda un objeto en la seccion `tienda` de la cuenta `usn` (0 = la bolsa huerfana de la sesion capturada), con el
    candado de cuenta.py y la forma de una compra [item, vence, cantidad, fecha]. -> {"estado", "motivo", "cantidad"}:
      DADO       agregado, o sumado si el catalogo lo vende por cantidad (trae PN);
      YA_ESTABA  lo tiene y no es de cantidad: no se duplica;
      RECHAZADO  dato invalido o no esta en el catalogo: no se escribe nada y el motivo dice por que.
    Si falta datos/catalogo.json lo guarda igual y lo avisa (no se trabo el juego por eso); sin catalogo no se sabe si es de
    cantidad, asi que no se suma. JSON de cuentas roto: CuentaError sin escribir (como acreditar). `con` (opcional) es la
    conexion a avisar por FFCE si la llave esta prendida; el inventario se ve igual al pedir de nuevo el FF49."""
    motivo = _motivo_invalido(item, cantidad, vence)
    if not motivo and _catalogo_leido() and not catalogo.existe(item):
        motivo = "el objeto %d no esta en el catalogo" % item
    if motivo:
        anotar("   dar_objeto usn %s: RECHAZADO (%s)" % (usn, motivo))
        return _resultado(RECHAZADO, motivo)
    if not _catalogo_leido():
        anotar("   dar_objeto usn %s: falta datos/catalogo.json, el objeto %d se guarda sin comprobar" % (usn, item))
    de_cantidad = _es_de_cantidad(catalogo.ficha(item))
    basicas = _basicas_de(usn)

    def poner(b):
        _preparar(b, basicas)
        return _agregar(b["items"], item, cantidad, vence, de_cantidad)
    res = _cta.cambiar_seccion(str(usn), "tienda", poner)
    anotar("   dar_objeto usn %s: %s %d (%s, cantidad %d)" % (usn, res["estado"].upper(), item, res["motivo"], res["cantidad"]))
    if res["estado"] == DADO:
        avisar_ffce(con, item, cantidad)
    return res


def exp_de(con):
    return _con_bolsa(con, lambda b: b.get("exp", 0))


def exp_g_de_cuenta(cuenta):
    """(exp, g) guardados de una cuenta LOCAL (seccion `tienda` de cuenta.json), SOLO LECTURA (no crea la bolsa ni da regalos).
    Es la MISMA fuente de `exp_de` (la que muestra el FF0C): la ficha FF00 y el FF9F usan esto para no dar un salto
    visible (ficha 81). (0, 0) si la cuenta no tiene nada guardado."""
    b = _cta.leer_seccion((cuenta or {}).get("usn", 0), "tienda") or {}
    return max(0, int(b.get("exp", 0))), max(0, int(b.get("g", 0)))


def saldo(con, seq, cuerpo):
    """C2S FF51 SendGetCashAmount (0 B) -> S2C FF51 [01][u32 diamantes]."""
    if cuerpo:
        return False
    diamantes = _con_bolsa(con, lambda b: b["diamantes"])
    con.mandar_interno(0x51, seq, b"\x01" + struct.pack("<I", diamantes))
    anotar("   S2C FF51 saldo de %s: %d diamantes" % ((con.cuenta or {}).get("nick"), diamantes))
    return True


# ---------- comprar (ficha 63) ----------
# MEDIDO en el exe (docs/tablero/layouts/FF50.md, FF2A.md, FF5B.md, seccion "Lectura de la ficha 63"):
#  - el cliente manda FF50 si el item trae Cash="1" en su tabla de tienda, y FF2A si no lo trae (o no esta): cuerpo 5 B
#    [codigo u32][tipo u8] y 6 B [0 u8][codigo u32][0 u8];
#  - el S2C FF50 trae el resultado en el campo #1 (0 = comprado; 1, 4, 21, 10002 y 10005 muestran cartel, abajo); el S2C
#    FF2A [u8 res][u8][u32 item][u32 vence][u32 G] al comprar guarda el campo #5 como el G del cliente (+0x968, el mismo
#    lugar que FF5B).
RES_OK = 0
RES_FALLA = 1                # "购买失败，网络错误" (la falla generica; es la que mandaba el codigo antes de la ficha 63)
RES_SIN_SALDO = 4            # "钻石/点券,余额不足" (diamantes/cupones, saldo insuficiente)
RES_NO_A_LA_VENTA = 21       # "道具未上架" (el objeto no esta en la tienda)
RES_NO_EXISTE = 10002        # "没有找到这个道具" (no se encontro el objeto)
RES_PRECIO = 10005           # "价格不匹配" (el precio no coincide)
PRECIO_SIN_CATALOGO = 500    # el del dialogo medido el 02-nov; solo si falta datos/catalogo.json
SEGUNDOS_DIA = 86400
# El digito de los miles del codigo: el cliente lo pone en lugar del digito de los miles del item (en el catalogo ningun
# item lo trae distinto de 0, asi que sacarlo no pierde nada). El cliente lo saca de una tabla de 10 bytes indexada por la
# posicion del precio que eligio en el dialogo (0x00b42a28: P1 P3 P7 P30 P100 P365 PI PN pack ? -> 4,7,1,2,3,8,9,6,5,0).
# MEDIDO con el juego (ficha 63): permanente (PI) = digito 9 (el dialogo mostro "500 / Permanent" y el catalogo dice PI 500).
# El resto sale de esa tabla, sin verlo uno por uno: HIPOTESIS. 5 (pack) y 0 (posicion 10, sin identificar) se rechazan.
DIGITO_PLAZO = {4: 1, 7: 3, 1: 7, 2: 30, 3: 100, 8: 365, 9: 0}      # digito -> dias (0 = permanente)
DIGITO_CANTIDAD = 6                                                   # posicion de PN


def precio_de(item, plazo=0):
    """Precio del catalogo para `plazo` (dias; 0 = permanente) o None si no se vende a ese plazo. Sin datos/catalogo.json
    (no se pudo leer): el 500 fijo del 02-nov, para no trabar el juego."""
    if not catalogo.cargado():
        return PRECIO_SIN_CATALOGO
    return catalogo.precio(item, plazo)


def _evaluar(item, digito, via):
    """Que se compra y a que precio, sin tocar la cuenta. `via` = "cash" (FF50) o "g" (FF2A). -> dict con `res` (RES_*),
    `motivo` y, si res es RES_OK, `precio`, `dias`, `cantidad` (0 si no es de cantidad)."""
    def no(res, motivo):
        return {"res": res, "motivo": motivo}
    if not catalogo.cargado():
        if via != "cash":
            return no(RES_FALLA, "falta datos/catalogo.json: sin el no se sabe el precio en G")
        return {"res": RES_OK, "motivo": "sin catalogo", "precio": PRECIO_SIN_CATALOGO, "dias": 0, "cantidad": 0}
    ficha = catalogo.ficha(item)
    if ficha is None:
        return no(RES_NO_EXISTE, "el objeto %d no esta en el catalogo" % item)
    if not catalogo.se_vende(item):
        return no(RES_NO_A_LA_VENTA, "el objeto %d no se vende (HIPOTESIS: PI 99999999)" % item)
    if catalogo.moneda(item) != via:
        return no(RES_FALLA, "el objeto %d se paga con %s y llego por la via de %s" % (item, catalogo.moneda(item), via))
    if digito == DIGITO_CANTIDAD:
        precio = ficha.get("n")
        if precio is None:
            return no(RES_PRECIO, "el objeto %d no se vende por cantidad (digito %d)" % (item, digito))
        return {"res": RES_OK, "motivo": "por cantidad", "precio": precio, "dias": 0, "cantidad": 1}
    if digito not in DIGITO_PLAZO:
        return no(RES_PRECIO, "digito de plazo %d sin significado conocido" % digito)
    dias = DIGITO_PLAZO[digito]
    plazo = "%d dias" % dias if dias else "permanente"
    precio = catalogo.precio(item, dias)
    if precio is None:
        return no(RES_PRECIO, "el objeto %d no se vende a %s (digito %d)" % (item, plazo, digito))
    return {"res": RES_OK, "motivo": plazo, "precio": precio, "dias": dias, "cantidad": 0}


def _comprar(con, codigo, via):
    """El corazon de FF50 y FF2A, con el candado de cuenta.py: mira el catalogo, controla saldo y 'ya lo tiene', cobra y guarda
    el objeto por _agregar (la misma forma que dar_objeto), todo junto. -> dict(res, motivo, item, vence, saldo (de esa
    moneda, despues), diamantes (despues), precio, dias)"""
    digito = (codigo // 1000) % 10
    item = codigo - digito * 1000
    moneda = "diamantes" if via == "cash" else "g"

    def pagar(b):
        plan = _evaluar(item, digito, via)
        r = {"res": plan["res"], "motivo": plan["motivo"], "item": item, "vence": PERMANENTE,
             "precio": plan.get("precio", 0), "dias": plan.get("dias", 0)}

        def fin(res=None, motivo=None):
            if res is not None:
                r["res"], r["motivo"] = res, motivo
            r["saldo"], r["diamantes"] = b.get(moneda, 0), b["diamantes"]
            return r
        if plan["res"] != RES_OK:
            return fin()
        de_cantidad = plan["cantidad"] > 0
        tiene = next((reg for reg in b["items"] if reg[0] == item), None)
        if tiene is not None and not de_cantidad and _permanente(tiene[1]):
            return fin(RES_FALLA, "ya lo tiene y es permanente (el exe no tiene un codigo para eso: va la falla generica)")
        if b.get(moneda, 0) < plan["precio"]:
            return fin(RES_SIN_SALDO, "saldo %d menor que el precio %d" % (b.get(moneda, 0), plan["precio"]))
        r["vence"] = PERMANENTE if plan["dias"] == 0 else int(time.time()) + plan["dias"] * SEGUNDOS_DIA
        b[moneda] = b.get(moneda, 0) - plan["precio"]
        _agregar(b["items"], item, plan["cantidad"], r["vence"], de_cantidad, plan["dias"])
        r["vence"] = next(reg for reg in b["items"] if reg[0] == item)[1]
        return fin()
    return _con_bolsa(con, pagar)


def comprar_cash(con, seq, cuerpo):
    """C2S FF50 CmdBuyCashItem (5 B) -> S2C FF50 (26 B) + FF51 con el saldo. Precio y plazo del catalogo (ficha 63)."""
    if len(cuerpo) != 5:
        anotar("   C2S FF50 CmdBuyCashItem (%d B): %s -- forma desconocida, sin respuesta" % (len(cuerpo), cuerpo.hex()))
        return False
    codigo, tipo = struct.unpack("<IB", cuerpo)
    if not catalogo.cargado():
        anotar("   ⚠ FF50: no se pudo leer datos/catalogo.json, precio fijo %d y sin plazo" % PRECIO_SIN_CATALOGO)
    r = _comprar(con, codigo, "cash")
    resp = struct.pack("<IIIIBBII", r["res"], codigo, fichas.vence_al_cable(r["vence"]), r["diamantes"], tipo, 0, 0, 0)
    con.mandar_interno(0x50, seq, resp)
    con.mandar_interno(0x51, 0, b"\x01" + struct.pack("<I", r["diamantes"]))     # el saldo nuevo, sin que lo pida
    anotar("   C2S FF50 comprar codigo %d tipo 0x%02x -> S2C FF50 resultado %d (%s), precio %d, vence %s, saldo %d"
           % (codigo, tipo, r["res"], r["motivo"], r["precio"], "permanente" if r["vence"] == PERMANENTE else "fecha",
              r["diamantes"]))
    return True


def comprar_g(con, seq, cuerpo):
    """C2S FF2A CmdBuyDress [u8 0][u32 codigo][u8 n=0] (6 B; el unico llamador del exe siempre manda 0 y 0) -> S2C FF2A
    [u8 res][u8 0][u32 item][u32 vence][u32 G]. Es la compra de lo que NO trae Cash, cobrada del G de la cuenta.
    ⚠ HIPOTESIS: que el item del S2C vaya SIN el digito del plazo y que el 4.o campo sea el vence (el cliente lo pasa como 2.o
    argumento de agregar-objeto, igual que el 3.o del FF50); los codigos de falla de FF2A (1, 2, 4, 5, 6) no se leyeron: se
    manda 1 en toda falla."""
    if len(cuerpo) != 6 or cuerpo[0] != 0 or cuerpo[5] != 0:
        anotar("   C2S FF2A CmdBuyDress (%d B): %s -- forma no medida, sin respuesta" % (len(cuerpo), cuerpo.hex()))
        return False
    codigo = struct.unpack_from("<I", cuerpo, 1)[0]
    r = _comprar(con, codigo, "g")
    res = RES_OK if r["res"] == RES_OK else 1
    con.mandar_interno(0x2A, seq, struct.pack("<BBIII", res, 0, r["item"], fichas.vence_al_cable(r["vence"]), r["saldo"]))
    anotar("   C2S FF2A comprar codigo %d -> S2C FF2A resultado %d (%s; en FF50 seria %d), precio %d G, vence %s, G %d"
           % (codigo, res, r["motivo"], r["res"], r["precio"], "permanente" if r["vence"] == PERMANENTE else "fecha",
              r["saldo"]))
    return True


def saldo_g(con, seq, cuerpo):
    """C2S FF5B SendGetCoinAmount (0 B) -> S2C FF5B [u32 G] (layout del exe; el cliente lo guarda en +0x968). El unico sitio
    del exe que lo pide, visto en .text, es el manejador de FF53 (regalar) tras un res=0."""
    if cuerpo:
        return False
    g = _con_bolsa(con, lambda b: b.get("g", 0))
    con.mandar_interno(0x5B, seq, struct.pack("<I", g))
    anotar("   S2C FF5B G de %s: %d" % ((con.cuenta or {}).get("nick"), g))
    return True


# ---------- saldos al dia (ficha 131) ----------
# LEIDO en el exe (docs/tablero/TIENDA_INVENTARIO.md, seccion "Ficha 131: saldos en pantalla"): el cliente guarda el G en [C+0x968]
# (xor 0x2efd) y lo guardan FF00, FF2A, FF53, FF5B, FFAB, FF9F y otros; FF5B (CmdGetCoinAmount 0x027ae600) SOLO guarda el u32
# y escribe una linea de log: ningun cartel, sonido, estado ni pedido de vuelta. Los diamantes van en [C+0x96c] / [C+0x970]
# (FF51, 0x027aab40) y la ventana de compra muestra tambien [C+0x974] (FF00 u32@21 y el tipo 0x12 de FF50).
# Llave SALDOS_AL_DIA (entorno; cuenta_local.LLAVES_OMISION; 0 = bytes de hoy).
def saldos_al_dia():
    import cuenta_local
    return cuenta_local.llave("SALDOS_AL_DIA")


def diamantes_de_cuenta(cuenta):
    """Los diamantes guardados de una cuenta LOCAL, SOLO LECTURA (no crea la bolsa); SALDO_INICIAL si todavia no tiene bolsa (es lo
    que `_preparar` le pondria al crearla)."""
    b = _cta.leer_seccion((cuenta or {}).get("usn", 0), "tienda") or {}
    return max(0, int(b.get("diamantes", SALDO_INICIAL)))


def refrescar_saldos(con, g=False, diamantes=False):
    """Ficha 131: manda SIN que lo pidan el saldo de G (S2C FF5B `[u32 G]`) y / o el de diamantes (S2C FF51 `[01][u32]`) de la cuenta de `con`,
    para que la barra de G y la ventana de compra no queden viejos despues de un cobro fuera de la tienda. Con SALDOS_AL_DIA=0 no manda nada.
    No lanza: si algo falla lo anota y sigue. -> True si mando algo."""
    try:
        if con is None or not (g or diamantes) or not saldos_al_dia():
            return False
        sg, sd = _con_bolsa(con, lambda b: (b.get("g", 0), b["diamantes"]))
        usos = []
        if g:
            con.mandar_interno(0x5B, 0, struct.pack("<I", max(0, int(sg)) & 0xFFFFFFFF))
            usos.append("FF5B G %d" % sg)
        if diamantes:
            con.mandar_interno(0x51, 0, b"\x01" + struct.pack("<I", max(0, int(sd)) & 0xFFFFFFFF))
            usos.append("FF51 diamantes %d" % sd)
        anotar("   saldos al dia a %s: %s" % ((con.cuenta or {}).get("nick"), ", ".join(usos)))
        return True
    except Exception as e:                                                   # noqa: BLE001
        anotar("   ⛔ tienda.refrescar_saldos: %r" % e)
        return False


def _fin_personajes(cu):
    """Donde termina la lista de personajes del FF49 (layout FF49 #1-#5): [char u32][u16 n][n x {u32, u8 m, m x u32}]."""
    o = 4
    n = struct.unpack_from("<H", cu, o)[0]
    o += 2
    for _ in range(n):
        m = cu[o + 4]
        o += 5 + 4 * m
    return o


def _fin_cola(cu, o):
    """Donde termina la cola del FF49 que empieza en o (layout FF49 #14-#31): [u32 a][u8 b][si b: a x 12 B][u16 c]
    [c x {u32, u8, u32, u8 L, L B}][6 x u32][u16][u16]. Con b=0 y c=0 son 35 B."""
    a = struct.unpack_from("<I", cu, o)[0]
    b = cu[o + 4]
    o += 5 + (12 * a if b else 0)
    c = struct.unpack_from("<H", cu, o)[0]
    o += 2
    for _ in range(c):
        o += 10 + cu[o + 9]
    return o + COLA_FIJA


def _partir_ff49(cu):
    """FF49 CmdGetDressList con el layout del exe (docs/tablero/layouts/FF49.md): [char u32][u16 n][n personajes]
    [u16 k][k x 17 B: item u32, vence u32, u8, cantidad u16, fecha u32, u8, u8][cola variable]. -> (cabeza, items, cola).
    Levanta ValueError si el cuerpo no cierra EXACTO (ni sobran ni faltan bytes)."""
    try:
        o = _fin_personajes(cu)
        k = struct.unpack_from("<H", cu, o)[0]
        fin_items = o + 2 + LARGO_REGISTRO * k
        if _fin_cola(cu, fin_items) != len(cu):
            raise ValueError("la cola no cierra con el largo del cuerpo (%d B)" % len(cu))
    except (IndexError, struct.error) as e:
        raise ValueError("cuerpo cortado: %s" % e)
    items = [cu[o + 2 + LARGO_REGISTRO * i:o + 2 + LARGO_REGISTRO * (i + 1)] for i in range(k)]
    return cu[:o], items, cu[fin_items:]


def inventario(con, seq, cuerpo):
    """C2S FF49 SendGetDressList (0 B) -> S2C FF49 con lo que COMPRO esta cuenta (cuenta.json, seccion tienda), sobre la cabeza y la
    cola de la respuesta capturada. ⏳ La ropa de la plantilla (la de la cuenta capturada) NO va: solo lo comprado."""
    if cuerpo:
        return False
    plantilla = captura.cuerpo_capturado(0x49)
    if plantilla is None:
        anotar("   ⛔ FF49: no hay plantilla capturada; sin respuesta propia")
        return False
    try:
        cabeza, _items, cola = _partir_ff49(plantilla)
    except (ValueError, IndexError, struct.error) as e:
        anotar("   ⛔ FF49: la plantilla no tiene la forma medida (%s)" % e)
        return False
    items = _con_bolsa(con, lambda b: copy.deepcopy(b["items"]))
    mios = [struct.pack("<IIBHIH", it, fichas.vence_al_cable(vence), 0, cant, fecha, 0) for it, vence, cant, fecha in items]
    con.mandar_interno(0x49, seq, cabeza + struct.pack("<H", len(mios)) + b"".join(mios) + cola)
    anotar("   S2C FF49 我的物品 de %s: %d items comprados" % ((con.cuenta or {}).get("nick"), len(mios)))
    return True


# ---------- vestir y desvestir (ficha 64) ----------
# MEDIDO en el exe (docs/tablero/layouts/FF1A.md, seccion "Lectura de la ficha 64"): el byte 25 del C2S es `byEditType`
# (1 = poner, 0 = sacar, 2 = sacar todo); el S2C es `[byResult][byEditType][iItem][byVIPGrade][byAnnualMembership]`;
# con byResult != 0 el cliente no hace nada (no hay cartel) y por eso la respuesta de error es ese solo byte.
EDITAR_SACAR, EDITAR_PONER, EDITAR_SACAR_TODO = 0, 1, 2
RES_VESTIR_FALLA = 1                  # cualquier byResult != 0 vale lo mismo para el cliente: 1 B, sin cartel
# El formato de `vence` (unix segundos, lo que guarda _comprar) NO esta confirmado contra el oficial: por ahora no se rechaza
# nada por vencido. Cambiar a True cuando se confirme (ficha 64, parte B.1).
RECHAZAR_VENCIDOS = False


def _ropa_ok(reg_vence, ahora):
    """True si un registro [item, vence, ...] sirve para vestir. Hoy siempre True (ver RECHAZAR_VENCIDOS)."""
    if not RECHAZAR_VENCIDOS or _permanente(reg_vence):
        return True
    return reg_vence > ahora


def _tiene_para_vestir(b, item, partes):
    """True si la cuenta puede ponerse `item`: esta en lo que compro/le dieron (`items`, y no vencido), es de la ropa basica
    del personaje, o ya lo lleva puesto. b = la bolsa (seccion `tienda`)."""
    ahora = int(time.time())
    if any(reg[0] == item and _ropa_ok(reg[1], ahora) for reg in b.get("items", [])):
        return True
    return item in b.get("basicas", []) or item in partes


def _respuesta_ff1a(tipo, item):
    """S2C FF1A de exito: [byResult 0][byEditType][iItem u32][byVIPGrade 0][byAnnualMembership 0] (8 B)."""
    return bytes([0, tipo]) + struct.pack("<I", item) + bytes(2)


def _guardar_partes(con, partes):
    """Guarda la ropa puesta en el personaje de la cuenta (el mismo camino de siempre: cuentas.cambiar)."""
    pj = (con.cuenta or {}).get("personaje") or {}
    try:
        import cuentas
        con.cuenta = cuentas.cambiar(con.cuenta["steamid"], personaje=dict(pj, partes=partes)) or con.cuenta
        return True
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF1A: no se pudo guardar la ropa: %r" % e)
        return False


def vestir(con, seq, cuerpo):
    """C2S FF1A SendEditAvatar (38 B; layout en layouts/FF1A.md): [id u32][item u32][u8][4 x u32][u8 byEditType @25][12 ceros].
    Regla del 2013: una prenda por familia (item // 10000), menos la familia 0509 (un cajon).
      poner (1): exige que el item este en el inventario de la cuenta (o sea basico o ya puesto) -> reemplaza la prenda de la
                 misma familia, guarda y avisa a la sala (FF0C). Si no lo tiene: S2C `[1]` y no escribe nada.
      sacar (0): si lo lleva y NO es una basica -> vuelve la basica de esa familia (si el personaje tiene una) y se la manda al
                 cliente como un `poner`. Si no lo lleva, lo deja como esta. Una prenda basica no se saca (S2C `[1]`).
      otro (2 = sacar todo, 4...): no atendido (S2C `[1]` y nada escrito); el exe lo trata del lado S2C pero no se midio en vivo.
    ⏳ vencimiento: ver RECHAZAR_VENCIDOS."""
    if len(cuerpo) != 38:
        return False
    usn, item = struct.unpack_from("<II", cuerpo, 0)
    tipo = cuerpo[25]
    pj = (con.cuenta or {}).get("personaje")
    nick = (con.cuenta or {}).get("nick")

    def error(motivo):
        con.mandar_interno(0x1A, seq, bytes([RES_VESTIR_FALLA]))
        anotar("   C2S FF1A %s %d (usn %d, byEditType %d) -> S2C FF1A error %d: %s"
               % ("vestir" if tipo == EDITAR_PONER else "desvestir", item, usn, tipo, RES_VESTIR_FALLA, motivo))
        return True
    if not pj:      # la sesion capturada (sin personaje propio): se contesta como siempre y no se guarda nada
        con.mandar_interno(0x1A, seq, _respuesta_ff1a(EDITAR_PONER, item))
        anotar("   C2S FF1A (byEditType %d) item %d sin personaje: contestado, nada guardado" % (tipo, item))
        return True
    partes = list(pj.get("partes", []))
    basicas = _con_bolsa(con, lambda b: list(b.get("basicas", [])))
    nuevas = None
    if tipo == EDITAR_PONER:
        if not _con_bolsa(con, lambda b: _tiene_para_vestir(b, item, partes)):
            return error("el item no esta en el inventario de %s" % nick)
        if item // 10000 != 509:
            nuevas = list(partes)
            familia = [i for i, p in enumerate(nuevas) if p // 10000 == item // 10000]
            if familia:
                nuevas[familia[0]] = item
            else:
                nuevas.append(item)
        con.mandar_interno(0x1A, seq, _respuesta_ff1a(EDITAR_PONER, item))
        extra = None
    elif tipo == EDITAR_SACAR:
        if item not in partes:
            con.mandar_interno(0x1A, seq, _respuesta_ff1a(EDITAR_SACAR, item))
            anotar("   C2S FF1A desvestir %d: no lo llevaba puesto, queda igual" % item)
            return True
        if item in basicas:
            return error("es una prenda basica del personaje: no se saca")
        base = next((p for p in basicas if p // 10000 == item // 10000), None)
        nuevas = [base if p == item else p for p in partes] if base is not None else [p for p in partes if p != item]
        con.mandar_interno(0x1A, seq, _respuesta_ff1a(EDITAR_SACAR, item))
        extra = base
        if base is not None:      # el cliente solo borra el item de su lista: la basica hay que ponersela
            con.mandar_interno(0x1A, 0, _respuesta_ff1a(EDITAR_PONER, base))
    else:
        return error("byEditType %d no atendido" % tipo)
    if nuevas is not None and nuevas != partes:
        _guardar_partes(con, nuevas)
    anotar("   C2S FF1A %s %d (usn %d, byEditType %d) -> S2C FF1A ok%s; partes ahora %s"
           % ("vestir" if tipo == EDITAR_PONER else "desvestir", item, usn, tipo,
              " + basica %d" % extra if tipo == EDITAR_SACAR and extra else "",
              ((con.cuenta or {}).get("personaje") or {}).get("partes")))
    sala = estado.SALAS.get(con.sala)
    if sala is not None:
        import salas
        salas.mandar_ropa_a_todos(sala, con)   # la sala ve la ropa nueva (ficha 67: el FF0C solo no repinta a los que ya estaban)
    return True


def _inventario_en(d):
    """(k, n) del inventario de una ficha FF00, o (None, 0): fichas.inventario_en."""
    return fichas.inventario_en(d)


def ficha_ff00(cu, cuenta):
    """La ficha FF00 con el inventario de ESTA cuenta (lo arma fichas.con_inventario con la seccion `tienda`). El mismo cuerpo
    si es la ficha corta o la cuenta no tiene personaje."""
    if not fichas.lleva_inventario(cu, cuenta):
        return cu
    return fichas.con_inventario(cu, cuenta, lambda: _cta.leer_seccion((cuenta or {}).get("usn", 0), "tienda"),
                                 lambda: int(time.time()))


def avatar(con, seq, cuerpo):
    """C2S FF7F SendEditAvatarMult [u8 n][n x u32] (lo manda el lobby al entrar con lo que tiene el registro del personaje).
    3-nov: el S2C FF7F lo APLICA el cliente al personaje (0x027c4230): en vez del eco, la ropa PUESTA de la cuenta
    (partes de la ficha), asi el muneco del lobby sale con su sexo y lo comprado (el registro venia con la ropa de varon
    de la captura)."""
    pj = (con.cuenta or {}).get("personaje")
    if not pj or not cuerpo:
        return False
    partes = list(pj.get("partes", []))
    con.mandar_interno(0x7F, seq, bytes([len(partes)]) + struct.pack("<%dI" % len(partes), *partes))
    pedido = list(struct.unpack_from("<%dI" % cuerpo[0], cuerpo, 1)) if len(cuerpo) >= 1 + 4 * cuerpo[0] else []
    anotar("   FF7F de %s: pidio %s -> va la ropa de la cuenta %s" % ((con.cuenta or {}).get("nick"), pedido, partes))
    return True


# ---------- regalar (ficha 65, FF53) ----------
# LEIDO del exe (docs/tablero/layouts/FF53.md, "Lectura de la ficha 65"): C2S [u8 n][n B apodo][u32 codigo con el digito del
# plazo]; S2C [u32 res][u8 n<13][apodo del que RECIBE][u32 codigo][u32 G real]. Con res 0 el cliente guarda el G y repide FF51 y
# FF5B (los dos ya se atienden). Cobra en G (el lado del FF2A) y NUNCA con diamantes (res 16). Los cartels por res estan en
# el layout. DIFERENCIAS con el oficial (decision del 11-nov): no se exige amistad de 3 dias (res 151) ni nivel (7 y 8); el
# objeto va directo a la mochila del que recibe (el oficial miraba mochila, deposito y buzon: HIPOTESIS); a B conectado NO se
# le avisa (FFCE apagado): lo ve al volver a entrar.
RG_OK, RG_NO_EXISTE_JUGADOR, RG_SIN_SALDO, RG_GENERICO = 0, 1, 2, 3
RG_GENERO, RG_A_UNO_MISMO, RG_NO_ENCONTRADO, RG_YA_TIENE, RG_SIN_DIAMANTES = 4, 6, 12, 13, 16
NO_REGALABLES = (30031, 30032)       # el cliente ni los manda (cartel propio); si llegan igual, generico
APODO_MAXIMO = 12                    # el S2C lee el apodo en un buffer de 13: n tiene que ser < 13


def _sexo_de(pj):
    """"varon" / "mujer" del personaje (char_id = 0x1FF54 + sexo) o None si no hay dato."""
    cid = (pj or {}).get("char_id")
    if not isinstance(cid, int) or not 0x1FF54 <= cid <= 0x1FF5F:
        return None
    return "mujer" if (cid - 0x1FF54) & 1 else "varon"


def _buscar_apodo(cuentas, apodo):
    """(usn, cuenta) de la PRIMERA cuenta local cuyo personaje se llama `apodo` o, si ninguna, cuyo nombre de cuenta (el UID de la
    ficha FF00, que es lo que ven los demas jugadores) se llama asi; (None, None) si no hay. Solo lectura, no crea nada."""
    for usn, acc in cuentas.items():
        pj = acc.get("personaje") or {}
        if pj.get("nick") == apodo:
            return usn, acc
    for usn, acc in cuentas.items():
        if (acc.get("cuenta") or {}).get("nick") == apodo:
            return usn, acc
    return None, None


def _regalar(usn_a, apodo, codigo):
    """Todo o nada, con UN candado de cuenta.py sobre las dos cuentas. -> dict(res, motivo, nick (del que recibe) , g (de quien regala)).
    No escribe nada si res != 0."""
    digito = (codigo // 1000) % 10
    item = codigo - digito * 1000

    def hacer(d):
        cuentas = d["cuentas"]
        a = cuentas.get(str(usn_a))
        r = {"res": RG_GENERICO, "motivo": "", "nick": apodo, "g": ((a or {}).get("tienda") or {}).get("g", 0)}

        def no(res, motivo):
            r["res"], r["motivo"] = res, motivo
            return r
        if a is None:
            return no(RG_GENERICO, "quien regala no es una cuenta local (sesion capturada): no se atiende")
        usn_b, b = _buscar_apodo(cuentas, apodo)
        if b is None:
            return no(RG_NO_EXISTE_JUGADOR, "no hay una cuenta con el apodo %r" % apodo)
        r["nick"] = (b.get("personaje") or {}).get("nick") or (b.get("cuenta") or {}).get("nick") or apodo
        if str(usn_b) == str(usn_a):
            return no(RG_A_UNO_MISMO, "regalo a uno mismo")
        if digito == DIGITO_CANTIDAD:
            return no(RG_GENERICO, "objeto de cantidad (digito 6): el regalo no los atiende")
        if item in NO_REGALABLES:
            return no(RG_GENERICO, "el objeto %d no se puede regalar (el cliente tampoco lo manda)" % item)
        if not catalogo.cargado():
            return no(RG_GENERICO, "falta datos/catalogo.json: sin el no se sabe el precio")
        if not catalogo.existe(item) or not catalogo.se_vende(item):
            return no(RG_NO_ENCONTRADO, "el objeto %d no existe o no se vende" % item)
        if catalogo.moneda(item) == "cash":
            return no(RG_SIN_DIAMANTES, "el objeto %d es solo de diamantes y no se regala con ellos" % item)
        plan = _evaluar(item, digito, "g")
        if plan["res"] != RES_OK:
            return no(RG_NO_ENCONTRADO if plan["res"] in (RES_NO_EXISTE, RES_NO_A_LA_VENTA) else RG_GENERICO, plan["motivo"])
        sx_obj, sx_dest = catalogo.sexo(item), _sexo_de(b.get("personaje"))
        if sx_obj and sx_dest and sx_obj != sx_dest:
            return no(RG_GENERO, "el objeto es de %s y el personaje que recibe es %s" % (sx_obj, sx_dest))
        ba = copy.deepcopy(a.get("tienda") or {})          # copias: si algo falla no se escribe ni la bolsa nueva
        _preparar(ba, list(((a.get("personaje") or {}).get("partes", []))))
        bb = copy.deepcopy(b.get("tienda") or {})
        _preparar(bb, list(((b.get("personaje") or {}).get("partes", []))))
        r["g"] = ba.get("g", 0)
        tiene = next((reg for reg in bb["items"] if reg[0] == item), None)
        if tiene is not None and _permanente(tiene[1]):
            return no(RG_YA_TIENE, "el que recibe ya tiene el objeto %d permanente" % item)
        if ba.get("g", 0) < plan["precio"]:
            return no(RG_SIN_SALDO, "G %d menor que el precio %d" % (ba.get("g", 0), plan["precio"]))
        vence = PERMANENTE if plan["dias"] == 0 else int(time.time()) + plan["dias"] * SEGUNDOS_DIA
        ba["g"] = ba.get("g", 0) - plan["precio"]
        _agregar(bb["items"], item, 0, vence, False, plan["dias"])
        a["tienda"], b["tienda"] = ba, bb
        r.update(res=RG_OK, motivo="%s, precio %d G" % (plan["motivo"], plan["precio"]), g=ba["g"], precio=plan["precio"])
        return r
    return _cta.cambiar_todas(hacer)


def regalar(con, seq, cuerpo):
    """C2S FF53 CmdGiftItem [u8 n][n B apodo][u32 codigo] -> S2C FF53 [u32 res][u8 n][apodo][u32 codigo][u32 G]."""
    if len(cuerpo) < 6 or not 1 <= cuerpo[0] <= 32 or len(cuerpo) != 1 + cuerpo[0] + 4:
        anotar("   C2S FF53 CmdGiftItem (%d B): %s -- forma desconocida, sin respuesta" % (len(cuerpo), cuerpo[:40].hex()))
        return False
    n = cuerpo[0]
    apodo = textos.decodificar(cuerpo[1:1 + n])      # ficha 141: GB18030 (antes latin-1: un apodo con letras no inglesas no se hallaba)
    codigo = struct.unpack_from("<I", cuerpo, 1 + n)[0]
    usn = (con.cuenta or {}).get("usn")
    try:
        r = _regalar(usn, apodo, codigo) if usn else {"res": RG_GENERICO, "nick": apodo, "g": 0,
                                                       "motivo": "sesion sin cuenta local: no se atiende"}
    except Exception as e:                                       # noqa: BLE001  (JSON roto, etc.: no se cobra nada)
        r = {"res": RG_GENERICO, "nick": apodo, "g": 0, "motivo": "error %s: no se cobro nada" % e}
    # ficha 141: el apodo que vuelve: si es el MISMO que llego (no se hallo a nadie) van los bytes tal cual llegaron; si es el de una cuenta, GB18030
    nick = textos.cortar(cuerpo[1:1 + n], APODO_MAXIMO) if r["nick"] == apodo else textos.codificar(r["nick"], APODO_MAXIMO)
    con.mandar_interno(0x53, seq, struct.pack("<IB", r["res"], len(nick)) + nick + struct.pack("<II", codigo, r["g"]))
    anotar("   C2S FF53 regalar codigo %d a %r (de %s) -> S2C FF53 res %d (%s), G de quien regala %d"
           % (codigo, apodo, (con.cuenta or {}).get("nick"), r["res"], r["motivo"], r["g"]))
    return True


MANEJADORES = {
    0x7F: avatar,
    0x50: comprar_cash,
    0x2A: comprar_g,
    0x5B: saldo_g,
    0x51: saldo,
    0x49: inventario,
    0x1A: vestir,
    0x53: regalar,
}
