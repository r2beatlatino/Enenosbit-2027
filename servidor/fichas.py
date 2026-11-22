# -*- coding: utf-8 -*-
r"""fichas.py (ficha 38) — ARMA los bytes de las fichas de una cuenta a partir de datos. No decide nada y no guarda.

Lo que arma:
  FF00  la ficha de la cuenta local (RECONSTRUIDA sobre la plantilla capturada) con la lista de canciones, la licencia y
        el inventario de la cuenta;  FF7F  la ropa puesta;  FF0C  la lista de jugadores de una sala (y la del oficial con
        el jugador de la cuenta);  y el lote de entrada completo de cada conexion (`lotes_de_entrada`).
Se recarga en vivo (recarga.py). Antes estaba repartido en juego.py (que no se recarga), manejadores.py, tienda.py y salas.py;
esos conservan una funcion delgada con la misma firma cuando alguien las llama desde afuera.

⚠⚠ RECONSTRUIDO, NO COPIADO (29-oct). El oficial ya no deja registrar cuentas (1002 DBERROR): no hay captura de un
personaje recien nacido. La ficha de una cuenta local es la CAPTURADA (dato local de captura) con tres cosas cambiadas, ancladas por
ESTRUCTURA. Lo que el cliente lee del FF00 (CmdMyRecord?, 0x0277c3d0), en orden de ejecucion:
    u8 sexo -> [cuenta+0x40] | u32 personaje puesto (si != 0, 0x00471950) | u32 EXP (@5) + u64 EXP (@9): el cliente los SUMA
    en [C+0x960] | u32 G (@17: el cliente lo guarda con xor 0x2efd en [C+0x968]; por el cable va el numero PLANO, el getter
    0x005977c0 lo vuelve a xorear) | u32 (@21 -> [C+0x974])
    | u16 licencia | u32 | u8 largo + UID (<= 12) -> [cuenta+0x82d] "[cAccount]SetUID" | u8+texto | u8+texto | ...
    | u16 cantidad de personajes + por cada uno [u32 char_id][u8 n][n x u32 partes] (0x0277c961; los id != 0 van a
      0x0046ec70) | u16 cantidad de canciones + songids (LISTA_EN) | ...
Igual que el MyRecord del 2013: una ficha SIN personajes es la que abre la pantalla de crear. Se cambian: el UID (el nick),
el personaje puesto y la lista de personajes. 11-nov (ficha 81): tambien la EXP (@5/@9) y el G (@17) de la cuenta local,
los de su seccion `tienda` (la misma fuente que el FF0C); una cuenta de la sesion capturada va con los de la captura.
"""
import os
import re
import struct
import time

import ajustes
import captura
import estado
import neutro
import textos

LISTA_EN = 90                  # desplazamiento de la cantidad de canciones, en el cuerpo del FF00 (medido)
LICENCIA = ajustes.LICENCIA    # m_wLicense del FF00: 0xFFFF abre todo el picker, Sol incluido (MEDIDO); 0 = la de la captura
JUGABLES = captura.jugables()  # los songid con chart 1 a 1, de mayor a menor
MAX_CANCIONES = 6000           # una lista mas larga no es la del registro: el FF00 va sin tocar
LARGO_FF00_GRANDE = 1190       # menos que esto es la ficha CORTA (sin personaje o recien creado): no lleva inventario
PERMANENTE = 0xEEFFCBB8        # "vence" de lo que no se acaba
LARGO_REGISTRO = 17            # un item del inventario de la ficha: <IIBHIH
FF0C_COLA = 222                # bytes fijos al final de cada ficha del FF0C


def anotar(txt):
    estado.anotar(txt)


# ---------- ficha 44: la hora de verdad (FF97) y el `vence` de los objetos en su formato real ----------
# LEIDO en Game_g21_local.exe (docs/tablero/layouts/FF97.md y VENCE_OBJETOS.md):
#  - FF97 S2C (0x027a56d0) = [u8 14]['AAAAMMDDhhmmss'][u64 unix UTC] (23 B): el texto se parsea con mktime LOCAL y es EL "ahora" del cliente
#    ([obj+0x1254], unas 45 funciones: plazos de objetos, tienda, eventos, correo). La captura trae la hora del 23-oct (China).
#  - `vence` de un objeto = u32 empaquetado en hora LOCAL (decodificador 0x02732730 -> mktime; codificador 0x027327a0 <- localtime):
#    anio bits 0-11, mes 12-15, dia 16-20, hora 21-25, minuto 26-31. PERMANENTE (anio 3000) y 0 van tal cual.
# Lo GUARDADO en cuenta.json sigue en segundos unix; solo el CABLE lleva el empaquetado (vence_al_cable, al armar cada mensaje).
# Llave HORA_REAL (entorno; cuenta_local.LLAVES_OMISION): 0 = los FF97 salen como en la captura.
FECHA_MINIMA, FECHA_MAXIMA = 1_500_000_000, 2_200_000_000    # un `vence` guardado que no es 0 ni PERMANENTE tiene que ser una fecha unix


def hora_real_activa():
    import cuenta_local
    return cuenta_local.llave("HORA_REAL")


def vence_al_cable(v):
    """El `vence` guardado (0, PERMANENTE o segundos unix) como lo lee el cliente: 0 -> 0, PERMANENTE -> PERMANENTE, unix -> u32
    empaquetado en hora local (minuto exacto, sin segundos). Un valor que no es ninguno de los tres sale igual y se anota."""
    if v in (0, PERMANENTE):
        return v
    if not FECHA_MINIMA < v < FECHA_MAXIMA:
        anotar("   ⛔ vence_al_cable: %r no es 0, PERMANENTE ni una fecha unix; va tal cual" % (v,))
        return v
    t = time.localtime(v)
    return ((t.tm_year & 0xFFF) | ((t.tm_mon << 12) & 0xF000) | (t.tm_mday << 16) | (t.tm_hour << 21) | (t.tm_min << 26)) & 0xFFFFFFFF


def vence_del_cable(u):
    """La inversa de vence_al_cable (para un `vence` que se relea del cable): 0 -> 0, PERMANENTE -> PERMANENTE, empaquetado -> segundos
    unix (hora local, segundos 0). Solo vale para un valor que SE SABE empaquetado: un unix y un empaquetado pueden coincidir en rango."""
    if u in (0, PERMANENTE):
        return u
    anio, mes, dia, hora, minu = u & 0xFFF, (u >> 12) & 0xF, (u >> 16) & 0x1F, (u >> 21) & 0x1F, u >> 26
    return int(time.mktime((anio, mes, dia, hora, minu, 0, 0, 0, -1)))


def reloj_cuerpo(ahora=None):
    """El cuerpo de un S2C FF97 con la hora de AHORA: [14]['AAAAMMDDhhmmss' local][u64 unix UTC] (23 B, el mismo largo de la captura)."""
    t = int(time.time() if ahora is None else ahora)
    return b"\x0e" + time.strftime("%Y%m%d%H%M%S", time.localtime(t)).encode("ascii") + struct.pack("<Q", t)


def con_hora_real(lote, ahora=None):
    """El lote con la hora de AHORA en cada FF97 de adentro (los FF56; el largo de cada interno va en su cabecera). Con HORA_REAL=0, o si
    no hay ningun FF97 de 23 B, el mismo lote. Vale para TODAS las conexiones, tambien la sesion capturada (es la hora, no un dato de cuenta)."""
    try:
        if lote[:2] != b"\xff\x56" or b"\xff\x97" not in lote or not hora_real_activa():
            return lote
        nuevo = reloj_cuerpo(ahora)
        k = 4 + struct.unpack_from("<H", lote, 2)[0]
        out, cambios = lote[:k], 0
        while k + 8 <= len(lote):
            fl, cmd = lote[k], lote[k + 1]
            seq, ln = struct.unpack_from("<HI", lote, k + 2)
            if k + 8 + ln > len(lote):
                break
            cu = lote[k + 8:k + 8 + ln]
            if fl == 0xFF and cmd == 0x97 and ln == len(nuevo):
                cu = nuevo
                cambios += 1
            out += bytes([fl, cmd]) + struct.pack("<HI", seq, len(cu)) + cu
            k += 8 + ln
        out += lote[k:]
        if cambios:
            anotar("   hora real: %d FF97 con la hora de ahora (%s)" % (cambios, nuevo[1:15].decode()))
        return out
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ fichas.con_hora_real: %r" % e)
        return lote


# ---------- la licencia y la lista de canciones ----------
def _sitios_nick(cuerpo):
    """[(desplazamiento del byte de largo del UID, largo)] de todo lo que parece el UID, anclado por ESTRUCTURA:
    [00 x4][licencia u16][00 x4][largo][nick]. Se ancla asi (no por desplazamiento) porque el nick reaparece en
    chat/sala/score y pisar ahi desconecta."""
    sitios = []
    for ni in range(15, min(len(cuerpo), 512)):
        largo = cuerpo[ni - 1]
        off = ni - 1 - 4 - 2
        if (2 <= largo <= 32 and ni + largo <= len(cuerpo) and cuerpo[off - 4:off] == bytes(4)
                and cuerpo[off + 2:off + 6] == bytes(4) and all(0x20 < b < 0x7f for b in cuerpo[ni:ni + largo])):
            sitios.append((ni - 1, largo))
    return sitios


def _sitio_nick(cuerpo):
    """El unico sitio del UID, o None si no hay o no es unico."""
    sitios = _sitios_nick(cuerpo)
    return sitios[0] if len(sitios) == 1 else None


def con_licencia(cuerpo, licencia=None):
    """El cuerpo del FF00 con m_wLicense = licencia (o LICENCIA si es None), solo si el sitio es unico y el valor actual
    es plausible (< 0x100). En la cuenta capturada: vale 1 (estrella). ⛔ 7 (la escala del 2013) NO es Sol. LICENCIA=0 no toca."""
    lic = LICENCIA if licencia is None else int(licencia)
    if licencia is None and not lic:
        return cuerpo
    sitios = [uid - 4 - 2 for uid, _largo in _sitios_nick(cuerpo)]
    if len(sitios) != 1:
        anotar("   ⚠ FF00: la licencia no esta donde se espera (%d sitios): va sin tocar" % len(sitios))
        return cuerpo
    off = sitios[0]
    actual = struct.unpack_from("<H", cuerpo, off)[0]
    if actual >= 0x100:
        anotar("   ⚠ FF00: la licencia vale %d, no es plausible: va sin tocar" % actual)
        return cuerpo
    anotar("   FF00: licencia %d -> %d (+%d)" % (actual, lic, off))
    return cuerpo[:off] + struct.pack("<H", lic) + cuerpo[off + 2:]


def con_lote_licencia(lote, licencia=None):
    """El lote del FF00 con la licencia aplicada sin tocar la lista de canciones."""
    if len(lote) < 4 or lote[:2] != b"\xff\x56":
        return lote
    k = 4 + struct.unpack_from("<H", lote, 2)[0]
    if k + 8 > len(lote) or lote[k] != 0xFF or lote[k + 1] != 0x00:
        return lote
    seq, ln = struct.unpack_from("<HI", lote, k + 2)
    nuevo = con_licencia(lote[k + 8:k + 8 + ln], licencia)
    return lote[:k] + struct.pack("<BBHI", 0xFF, 0x00, seq, len(nuevo)) + nuevo + lote[k + 8 + ln:]


def con_lista_recortada(lote, licencia=None):
    """El lote con el FF00 adentro, con la lista de canciones reemplazada por JUGABLES. El mismo lote si no trae FF00 o si
    la lista no esta donde se espera (no se toca a ciegas). ⛔ una cancion sin chart en el picker mata al cliente."""
    if len(lote) < 4 or lote[:2] != b"\xff\x56":
        return lote
    k = 4 + struct.unpack_from("<H", lote, 2)[0]
    if k + 8 > len(lote) or lote[k] != 0xFF or lote[k + 1] != 0x00:
        return lote
    seq, ln = struct.unpack_from("<HI", lote, k + 2)
    cuerpo = lote[k + 8:k + 8 + ln]
    n = struct.unpack_from("<H", cuerpo, LISTA_EN)[0]
    viejos = struct.unpack_from("<%dH" % n, cuerpo, LISTA_EN + 2) if LISTA_EN + 2 + 2 * n <= len(cuerpo) else ()
    # control: una cantidad razonable que entra en el registro, y los primeros de mayor a menor (como los
    # 3.454 del catalogo en la cuenta capturada; los 54 del final, que este cliente no conoce, no lo estan)
    if not viejos or n > MAX_CANCIONES or any(a <= b for a, b in zip(viejos[:50], viejos[1:50])):
        anotar("   ⚠ el FF00 no tiene la lista de canciones donde se esperaba: va sin tocar")
        return lote
    nuevo = (cuerpo[:LISTA_EN] + struct.pack("<H", len(JUGABLES)) + struct.pack("<%dH" % len(JUGABLES), *JUGABLES)
             + cuerpo[LISTA_EN + 2 + 2 * n:])
    anotar("   FF00: lista de canciones %d -> %d (las que tienen chart 1 a 1)" % (n, len(JUGABLES)))
    nuevo = con_licencia(nuevo, licencia)
    return (lote[:k] + struct.pack("<BBHI", 0xFF, 0x00, seq, len(nuevo)) + nuevo + lote[k + 8 + ln:])


# ---------- la ficha FF00 de una cuenta local ----------
def _lista_personajes(cuerpo, desde, hasta):
    """El comienzo de la lista de personajes: el unico s entre `desde` y `hasta` tal que [u16 n][n x (u32 id, u8 c,
    c x u32)] termina JUSTO en `hasta` (donde empieza la lista de canciones), con 1..8 personajes de id 13xxxx."""
    buenos = []
    for st in range(desde, hasta - 2):
        n, k, ok = struct.unpack_from("<H", cuerpo, st)[0], st + 2, True
        if not 1 <= n <= 8:
            continue
        for _ in range(n):
            if k + 5 > hasta:
                ok = False
                break
            cid, c = struct.unpack_from("<I", cuerpo, k)[0], cuerpo[k + 4]
            if not 130000 <= cid < 140000 or c > 16:
                ok = False
                break
            k += 5 + 4 * c
        if ok and k == hasta:
            buenos.append(st)
    return buenos[0] if len(buenos) == 1 else None


def ficha_para(lote, cuenta):
    """El lote del FF00 con la ficha de la cuenta local. El mismo lote si no trae FF00; None si el FF00 no tiene la forma
    esperada (no se manda una ficha de OTRA cuenta a ciegas)."""
    if len(lote) < 4 or lote[:2] != b"\xff\x56":
        return lote
    k = 4 + struct.unpack_from("<H", lote, 2)[0]
    if k + 8 > len(lote) or lote[k] != 0xFF or lote[k + 1] != 0x00:
        return lote
    seq, ln = struct.unpack_from("<HI", lote, k + 2)
    cu = lote[k + 8:k + 8 + ln]
    sn = _sitio_nick(cu)
    canciones = LISTA_EN                     # la lista de canciones empieza ahi (medido; tambien con la recortada)
    lp = _lista_personajes(cu, sn[0] + 1 + sn[1], canciones) if sn else None
    if sn is None or lp is None:
        anotar("   ⛔ FF00: no encuentro el UID o la lista de personajes (%s, %s): la ficha NO va" % (sn, lp))
        return None
    pj = cuenta.get("personaje")
    nick = textos.codificar(cuenta["nick"], 12)
    if pj:
        lista = struct.pack("<HIB", 1, pj["char_id"], len(pj["partes"])) + struct.pack("<%dI" % len(pj["partes"]), *pj["partes"])
        sexo, puesto = (pj["char_id"] - 0x1FF54) & 1, pj["char_id"]
    else:
        lista, sexo, puesto = struct.pack("<H", 0), cu[0], 0
    nuevo = (bytes([sexo]) + struct.pack("<I", puesto) + cu[5:sn[0]] + bytes([len(nick)]) + nick
             + cu[sn[0] + 1 + sn[1]:lp] + lista + cu[canciones:])
    anotar("   FF00 de la cuenta local %s: UID %r, %s (RECONSTRUIDA sobre la plantilla capturada)"
           % (cuenta["nick"], textos.decodificar(nick), "personaje %d con %d partes" % (puesto, len(pj["partes"])) if pj
              else "SIN personajes -> el cliente deberia abrir la pantalla de crear"))
    nuevo = ficha_ff00(nuevo, cuenta)     # 02-nov: el inventario de la ficha con lo de esta cuenta
    nuevo = ficha_progreso(nuevo, cuenta)  # 11-nov (ficha 81): la EXP y el G de esta cuenta
    return lote[:k] + struct.pack("<BBHI", 0xFF, 0x00, seq, len(nuevo)) + nuevo + lote[k + 8 + ln:]


EXP_EN, EXP64_EN, G_EN = 5, 9, 17    # FF00: u32 EXP, u64 EXP (se SUMAN en [C+0x960]) y u32 G (-> [C+0x968] con xor 0x2efd). MEDIDO (0x0277c4c9..0x0277c577)
U32_MAX = 0xFFFFFFFF


def con_exp_y_g(cuerpo, exp, g):
    """El cuerpo del FF00 con la EXP (u32@5 + u64@9, que el cliente suma) y el G (u32@17, plano) dados. El resto, byte a byte
    igual. exp > u32 se reparte (el u32 al tope y el resto al u64). Negativos se toman como 0."""
    if len(cuerpo) < G_EN + 4:
        return cuerpo
    exp, g = max(0, int(exp)), min(U32_MAX, max(0, int(g)))
    bajo = min(exp, U32_MAX)
    b = bytearray(cuerpo)
    struct.pack_into("<I", b, EXP_EN, bajo)
    struct.pack_into("<Q", b, EXP64_EN, min(exp - bajo, 0xFFFFFFFFFFFFFFFF))
    struct.pack_into("<I", b, G_EN, g)
    return bytes(b)


CASH_EN = 21     # FF00: u32 -> [C+0x974] (con xor 0x2efd al guardar; por el cable va plano). MEDIDO 0x0277c582..0x0277c590. La ventana de compra lo muestra
                 # como el saldo "G币" de un objeto de diamantes (0x00b40f7d); FF50 con tipo 0x12 lo deja igual (0x027a9be3)


def con_cash(cuerpo, cash):
    """El cuerpo del FF00 con el u32@21 (el 2.o saldo de la ventana de compra, [C+0x974]) puesto. El resto, byte a byte igual."""
    if len(cuerpo) < CASH_EN + 4:
        return cuerpo
    b = bytearray(cuerpo)
    struct.pack_into("<I", b, CASH_EN, min(U32_MAX, max(0, int(cash))))
    return bytes(b)


def con_tutorial_baile(cuerpo, valor):
    """El cuerpo del FF00 con el u32 [cMyInfo+0x5c] (tutorial baile; bit 0 = hecho) puesto (UID en @31)."""
    if len(cuerpo) <= 32 or not (1 <= cuerpo[31] <= 32):
        return cuerpo
    p = 32 + cuerpo[31]
    for _ in range(2):
        if p >= len(cuerpo):
            return cuerpo
        p += 1 + cuerpo[p]
    p += 9
    if p + 4 > len(cuerpo):
        return cuerpo
    b = bytearray(cuerpo)
    struct.pack_into("<I", b, p, int(valor) & U32_MAX)
    return bytes(b)


def con_saldos_en_ff51(lote, diamantes):
    """Ficha 131 (llave SALDOS_AL_DIA): el lote con el diamante real en cada S2C FF51 de 5 B `[01][u32]` de adentro (la rafaga de entrada
    trae uno, el del lote 45, con 0). Mismo largo; el mismo lote si no hay ninguno."""
    try:
        if lote[:2] != b"\xff\x56" or b"\xff\x51" not in lote:
            return lote
        k = 4 + struct.unpack_from("<H", lote, 2)[0]
        out, cambios = lote[:k], 0
        while k + 8 <= len(lote):
            fl, cmd = lote[k], lote[k + 1]
            seq, ln = struct.unpack_from("<HI", lote, k + 2)
            if k + 8 + ln > len(lote):
                break
            cu = lote[k + 8:k + 8 + ln]
            if fl == 0xFF and cmd == 0x51 and ln == 5 and cu[0] == 1:
                cu = b"\x01" + struct.pack("<I", min(U32_MAX, max(0, int(diamantes))))
                cambios += 1
            out += bytes([fl, cmd]) + struct.pack("<HI", seq, len(cu)) + cu
            k += 8 + ln
        out += lote[k:]
        if cambios:
            anotar("   saldos al dia: %d FF51 de la rafaga con %d diamantes" % (cambios, diamantes))
        return out
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ fichas.con_saldos_en_ff51: %r" % e)
        return lote


def ficha_progreso(cuerpo, cuenta):
    """La ficha FF00 de una cuenta local con SU exp y SU G (tienda.exp_g_de_cuenta). Si no se pueden leer, la ficha tal cual
    (la de la captura). Una cuenta sin nada guardado va con 0 y 0."""
    try:
        import tienda
        exp, g = tienda.exp_g_de_cuenta(cuenta)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF00 exp/g: %r (va la de la captura)" % e)
        return cuerpo
    anotar("   FF00 de %s: exp %d, G %d (de la cuenta)" % ((cuenta or {}).get("nick"), exp, g))
    cuerpo = con_exp_y_g(cuerpo, exp, g)
    try:
        if tienda.saldos_al_dia():                                       # ficha 131 (llave SALDOS_AL_DIA)
            d = tienda.diamantes_de_cuenta(cuenta)
            cuerpo = con_cash(cuerpo, d)
            anotar("   FF00 de %s: u32@21 (-> [C+0x974], el 2.o saldo de la ventana de compra) = %d diamantes" % ((cuenta or {}).get("nick"), d))
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF00 saldos al dia: %r" % e)
    try:
        import baile
        if baile.activo():
            tut = baile.tutorial_hecho(cuenta)
            if tut:
                cuerpo = con_tutorial_baile(cuerpo, tut)
                anotar("   FF00 de %s: tutorial baile [cMyInfo+0x5c] = %d" % ((cuenta or {}).get("nick"), tut))
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF00 tutorial baile: %r" % e)
    return cuerpo


def ficha_nueva(cuenta):
    """La ficha FF00 (lote completo) de una cuenta que acaba de crear su personaje, sobre la plantilla recortada (o la
    plantilla neutra si falta lotes_S2C.bin)."""
    lic = ((cuenta or {}).get("personaje") or {}).get("licencia") if cuenta is not None else None
    lote = next((x for x in [con_lista_recortada(captura.con_llave(y), lic) for y in captura.lotes_capturados()]
                 if any(cc == 0x00 for cc, _s, _c in captura.internos_todos(x))), None)
    if lote:
        return ficha_para(lote, cuenta)
    if not os.path.exists(ajustes.RUTA_LOTES):
        return neutro.ff00_lote(cuenta)
    return None  # captura presente pero sin FF00: no reemplazarla por invencion


def lotes_de_entrada(lotes, cuenta):
    """La rafaga de entrada de una conexion: los lotes capturados con la lista de canciones recortada y, en una cuenta LOCAL,
    con SU ficha FF00 (los que no se pueden armar se sacan) y SU ropa en el FF7F. Mismo orden que los capturados.
    Si falta lotes_S2C.bin, usa la rafaga neutra de neutro.py."""
    if not lotes and not os.path.exists(ajustes.RUTA_LOTES):
        return neutro.lotes_entrada(cuenta)
    lic = ((cuenta or {}).get("personaje") or {}).get("licencia") if cuenta is not None else None
    if ajustes.LISTA_CANCIONES and JUGABLES:
        lotes = [con_lista_recortada(x, lic) for x in lotes]
    elif lic is not None:
        lotes = [con_lote_licencia(x, lic) for x in lotes]
    lotes = [con_hora_real(x) for x in lotes]      # ficha 44: la hora de ahora en los FF97 (todas las conexiones)
    if cuenta is not None:
        lotes = [ficha_para(x, cuenta) for x in lotes]
        lotes = [x for x in lotes if x is not None]
        lotes = [lote_para(x, cuenta) for x in lotes]
        import tienda
        if tienda.saldos_al_dia():                                    # ficha 131: SUS diamantes en el FF51 de la rafaga
            d = tienda.diamantes_de_cuenta(cuenta)
            lotes = [con_saldos_en_ff51(x, d) for x in lotes]
        import progresion
        lotes = [progresion.lote_para(x, cuenta) for x in lotes]      # ficha 83: SUS misiones de hoy y semanales
        import gemas
        lotes = [gemas.lote_para(x, cuenta) for x in lotes]           # ficha 95: SU FF272 (gemas engarzadas)
    return lotes


# ---------- el inventario de la ficha FF00 (lo arma tienda.ficha_ff00 con los datos de la cuenta) ----------
def registro_ok(d, p):
    """True si en `d`, en `p`, hay un registro de inventario de 17 B con valores plausibles."""
    it, vence, uso, cant, fecha, cola = struct.unpack_from("<IIBHIH", d, p)
    fecha_ok = 1_500_000_000 < fecha < 2_200_000_000
    return (0 < it < 100_000_000 and (vence in (0, PERMANENTE) or 1_500_000_000 < vence < 2_200_000_000)
            and uso in (0, 1) and cant < 10_000 and fecha_ok and cola == 0)


def inventario_en(d):
    """El inventario de la ficha FF00 (nota 10 de S-2013, ff00_steam.py): el primer [n u16] seguido de n registros de
    17 B validos. Los offsets se corren (textos variables al principio): se busca, no se clava. -> (k, n) o (None, 0)"""
    for k in range(len(d) - 19):
        n = struct.unpack_from("<H", d, k)[0]
        if 1 <= n <= 2000 and k + 2 + 17 * n <= len(d) and all(registro_ok(d, k + 2 + 17 * i) for i in range(n)):
            return k, n
    return None, 0


def lleva_inventario(cu, cuenta):
    """True si la ficha FF00 es la GRANDE de una cuenta con personaje. 3-nov: la RECORTADA (canciones 3508 -> 277: 1.198 B)
    trae el MISMO inventario que la grande (medido); solo se salta la CORTA (1.177-1.198 B: sin personaje, o la que se
    reenvia justo despues de crearlo), donde el buscador encontraba un inventario FALSO."""
    return bool((cuenta or {}).get("personaje")) and len(cu) >= LARGO_FF00_GRANDE


def con_inventario(cu, cuenta, leer_bolsa, leer_hora):
    """La ficha FF00 con el inventario de ESTA cuenta (nota 10 §4: el cliente dibuja la ropa puesta solo si esta en el
    inventario de la ficha): la ropa basica + lo comprado, permanente, en_uso=1 en lo puesto. `leer_bolsa()` da la seccion
    `tienda` de la cuenta y `leer_hora()` la fecha de lo basico; se piden solo si el inventario esta. El mismo cuerpo si
    no lo encuentra."""
    k, n = inventario_en(cu)
    if k is None:
        anotar("   ⛔ FF00: no encuentro el inventario de la ficha; va el de la captura")
        return cu
    bolsa, ahora = leer_bolsa(), leer_hora()
    puestas = list(((cuenta or {}).get("personaje") or {}).get("partes", []))
    items = {}
    for it in list(bolsa.get("basicas", [])) + puestas:
        items.setdefault(it, [it, PERMANENTE, 0, ahora])
    for it, vence, cant, fecha in bolsa.get("items", []):
        items.setdefault(it, [it, vence, cant, fecha])
    regs = b"".join(struct.pack("<IIBHIH", it, vence_al_cable(vence), 1 if it in puestas else 0, cant, fecha, 0)
                    for it, vence, cant, fecha in items.values())
    anotar("   FF00 inventario de %s: %d items en @%d (en la ficha estaban %d de la captura; ficha de %d B)"
           % (cuenta.get("nick"), len(items), k, n, len(cu)))
    return cu[:k] + struct.pack("<H", len(items)) + regs + cu[k + 2 + 17 * n:]


def ficha_ff00(cuerpo, cuenta):
    """La ficha FF00 de una cuenta local, con su inventario (tienda.ficha_ff00 lo lee y llama a con_inventario). Si falla,
    la ficha tal cual."""
    try:
        import tienda
        return tienda.ficha_ff00(cuerpo, cuenta)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF00 inventario: %r" % e)
        return cuerpo


# ---------- la ropa puesta (FF7F) ----------
def lote_para(lote, cuenta):
    """3-nov: el lote capturado de la cuenta local. El oficial manda en la rafaga de entrada un S2C FF7F CmdEditAvatarMult
    [n=4][210566][310565][410491][510430] = la ropa de dato local de captura (varon): el cliente la aplica al personaje (0x027c4230 ->
    0x7b82d0) y el muneco del LOBBY sale de varon y sin lo comprado (medido en la memoria viva de la copia 7 por un
    subagente). Se reescribe con las partes PUESTAS de la cuenta (mismo largo si son 4; si no, se rearma el interno)."""
    try:
        pj = (cuenta or {}).get("personaje")
        if not pj or b"\xff\x7f" not in lote:
            return lote
        partes = list(pj.get("partes", []))
        nuevo = bytes([len(partes)]) + struct.pack("<%dI" % len(partes), *partes)
        i = 0
        while True:
            i = lote.find(b"\xff\x7f", i)
            if i < 0 or i + 8 > len(lote):
                return lote
            ln = struct.unpack_from("<I", lote, i + 4)[0]
            cu = lote[i + 8:i + 8 + ln]
            if ln == 17 and cu[0] == 4:
                if len(nuevo) == ln:
                    return lote[:i + 8] + nuevo + lote[i + 8 + ln:]
                # el largo del sobre FF56 ([ff 56][u16 largo de la cabeza]...) no cubre a los internos: se deja
                return lote[:i + 4] + struct.pack("<I", len(nuevo)) + nuevo + lote[i + 8 + ln:]
            i += 2
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ FF7F de la cuenta: %r" % e)
        return lote


# ---------- el FF0C (lista de jugadores de una sala) ----------
def sala_para(cuerpo, cuenta):
    """01-nov: el FF0C RoomUserList grabado (285 B), con el jugador de la cuenta local en vez del grabado. Medido en la
    grabacion: el jugador va como [u32 char_id 0x1ff54..][u8 n][n x u32 partes] ... [u8 largo][nick]. RECONSTRUIDO: el
    resto de los campos (nivel, equipo, lugar) quedan los grabados. El mismo cuerpo si no encuentra la forma."""
    pj = cuenta.get("personaje") if cuenta else None
    if not pj:
        return cuerpo
    for k in range(len(cuerpo) - 5):
        cid, n = struct.unpack_from("<IB", cuerpo, k)
        if 0x1FF54 <= cid <= 0x1FF5F and 1 <= n <= 8 and k + 5 + 4 * n <= len(cuerpo):
            break
    else:
        return cuerpo
    fin = k + 5 + 4 * n
    m = re.compile(rb"([\x03-\x0c])([\x20-\x7e]{3,12})").search(cuerpo, fin)
    if not m or m.group(1)[0] != len(m.group(2)) or m.start() > fin + 32:
        return cuerpo
    nick = textos.codificar(cuenta["nick"], 12)
    partes = struct.pack("<IB", pj["char_id"], len(pj["partes"])) + struct.pack("<%dI" % len(pj["partes"]), *pj["partes"])
    return cuerpo[:k] + partes + cuerpo[fin:m.start()] + bytes([len(nick)]) + nick + cuerpo[m.end():]


def cola_ff0c():
    """Los 222 B fijos de la ficha grabada del oficial (el FF0C de la plantilla de crear sala)."""
    for cmd, _s, cu in captura.plantilla_crear_sala():
        if cmd == 0x0C:
            o = 3 + 23 + 4
            o += 1 + 4 * cu[o] + 8
            return cu[o + 1 + cu[o]:]
    return bytes(FF0C_COLA)


def ficha_ff0c(cuenta, exp, listo, asiento, equipo=1):
    """Un jugador del FF0C (nota 06 de S-2013, medido sobre los 6 FF0C / 29 jugadores de la grabacion 213306; un byte de mas
    rompe la lectura). Por jugador: pre 23 B [u32 exp][12 B en 0][u16 fijo por jugador][u8 genero = char_id & 1][u8 ASIENTO]
    [u8 equipo][u8 0][u8 LISTO]; [u32 char_id][u8 n][n x u32 ropa] [f32 x = -342.5 + 177.5 x asiento][f32 z = 0]
    [u8 n][apodo GBK] y la cola FIJA de 222 B (cola[26] = 0xFF: sin pareja). 10-nov (ficha 13): el byte 22 es el LISTO (el
    cliente lo lee solo si el asiento no es el del anfitrion, igual que el FF17; MEDIDO en el exe, 0x02787e69). En el
    oficial vale 0 en las 42 fichas de no-anfitrion vistas (el FF0C sale entre partidas / al entrar / tras un reset)."""
    cuenta = cuenta or {}
    pj = cuenta.get("personaje") or {}
    char_id = pj.get("char_id", 0x1FF54)
    partes = pj.get("partes", [])
    nick = textos.codificar(cuenta.get("nick", "Jugador"), 12)
    pre = (struct.pack("<I", exp & 0xFFFFFFFF) + bytes(12) + struct.pack("<H", 0)
           + bytes([char_id & 1, asiento, equipo, 0, 1 if listo else 0]))
    return (pre + struct.pack("<IB", char_id, len(partes)) + struct.pack("<%dI" % len(partes), *partes)
            + struct.pack("<ff", -342.5 + 177.5 * asiento, 0.0) + bytes([len(nick)]) + nick + cola_ff0c())


def lista_ff0c(jugadores):
    """El FF0C entero: [0x66][u8 cantidad][0] y las fichas ya armadas (ficha_ff0c) de cada jugador, en orden de asiento."""
    return bytes([0x66, len(jugadores), 0]) + b"".join(jugadores)


# Ficha 69 (11-nov): el FF13 CmdRoomUserInfo (0x0278ebf0) = UNA ficha de jugador para repintar a uno YA sentado, sin aviso de chat.
# Layout: docs/tablero/layouts/FF13.md ("Lectura de la ficha 68"). Cuerpo S2C sin cabecera; cierra EXACTO en 25 de 25 muestras del oficial.
# Despues de la lista de prendas: lista de (ancho, valor) en orden de ejecucion; el valor 0 = "cero en las 25 muestras" (no se manda
# nada propio). Solo los de abajo llevan algo: #7 exp (MEDIDO 17/25 iguales al exp del FF0C), #17 y #57 = 255, #46 y #47 = 1 (constantes
# en las 25; HIPOTESIS que sean de juego y no de la cuenta: las 25 son de un solo char_id), k = 11 (LEIDO: tope 0xb @0x02887118).
FF13_ANCHOS_1 = (1, 4, 4, 2, 1, 1, 1, 8, 1, 1, 2, 1, 1, 1, 4, 4, 1, 4, 4, 4, 4, 4, 4, 4)   # #6..#29 (el #7 es la exp)
FF13_ANCHOS_2 = (1, 1, 4, 1, 4, 1)                  # #30 (m=0, sin lista #31), #32..#35, #36 (L=0, sin apodo #37)
FF13_ANCHOS_3 = (1, 4, 1, 2, 4, 1, 1, 4, 4, 4, 4, 4, 2, 4, 4, 4, 1, 1, 1, 4, 4, 4)         # #40..#61
FF13_CONST = {17: 255, 46: 1, 47: 1, 57: 255}      # numero de campo -> valor constante de las 25


def ff13(asiento, char_id, partes, exp, equipo=1):
    """FF13 de UN jugador. LEIDO en el exe + MEDIDO 25/25: asiento (#1, la llave de busqueda), #2 = 0, char_id (#3), n y las n prendas
    (#4/#5, n <= 11: HIPOTESIS que mas no cabe), exp (#7), m = 0 (#30), L = 0 sin apodo (#36), k = 11 casillas en cero (#62), K = 0.
    #6 = equipo del asiento (MEDIDO con juego, ficha 69: con #6 = 0 la barra del asiento paso de roja a VERDE en la sala individual;
    el FF0C trae equipo 1 ahi: HIPOTESIS que #6 sea el equipo, no el 'listo'). El resto, ceros. Largo = 200 + 4n (n=4: 216 B, n=5: 220, n=6: 224; la ficha 69 decia 196+4n)."""
    partes = list(partes)[:11]
    out = struct.pack("<BBIB", asiento & 0xFF, 0, char_id & 0xFFFFFFFF, len(partes))
    out += struct.pack("<%dI" % len(partes), *partes)
    num = 6
    for ancho in FF13_ANCHOS_1:
        v = (exp & 0xFFFFFFFF) if num == 7 else (equipo & 0xFF) if num == 6 else FF13_CONST.get(num, 0)
        out += int(v).to_bytes(ancho, "little")
        num += 1
    num = 30
    for i, ancho in enumerate(FF13_ANCHOS_2):
        out += int(FF13_CONST.get(num, 0)).to_bytes(ancho, "little")
        num += 1 if i != 0 else 2            # tras #30 vienen #32.. (el #31 es el bucle de m)
    num = 40
    for ancho in FF13_ANCHOS_3:
        out += int(FF13_CONST.get(num, 0)).to_bytes(ancho, "little")
        num += 1
    return out + struct.pack("<I", 11) + bytes(4 * 11) + struct.pack("<I", 0)
