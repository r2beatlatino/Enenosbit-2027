# -*- coding: utf-8 -*-
r"""social.py (03-nov) — lo SOCIAL del cliente de Steam (Fase 6 del plan; contrato: nota 07 §B de S-2013). Arranca por lo
que el cliente pide SOLO al entrar al lobby, con las respuestas MEDIDAS en las grabaciones del oficial
(herramientas/_social_grabaciones.py, las 5 del 29-oct; iguales en todas):

  C2S FF45 (0 B)        -> S2C FF45 17 B: [00 00][u8 14]['AAAAMMDDhhmmss']   (una fecha-hora de 14 cifras: la de AHORA)
  C2S FF4A (0 B)        -> S2C FF4A 11 B: 11 ceros                              (CmdGetCoupleData: sin pareja)
  C2S FF40 [21] (1 B)   -> S2C FF40 13 B: [21][00 00][ff ff ff ff][6 ceros]    (tunel FF40, sub 0x21 = GuildInfo: sin circulo)

⏳ Lo demas del tunel FF40 (amigos 0x1D, susurro 0x04/0x0D, invitar 0x07, pareja 0x0A, la ficha 0x06, buscar 0x01) va
despues: el panel 密友 de Steam muestra un cartel vacio y no manda nada (medido 03-nov); primero se prueba si con estas
respuestas del login se habilita.
"""
import copy
import os
import struct
import threading
import time

import captura
import ajustes
import cuenta as _cta     # el unico que abre los archivos de cuentas: amigos y pareja son secciones de cuenta.json
import estado
import neutro
import textos


def anotar(txt):
    estado.anotar(txt)


def fecha(con, seq, cuerpo):
    if cuerpo:
        return False
    ahora = time.strftime("%Y%m%d%H%M%S").encode()
    con.mandar_interno(0x45, seq, b"\x00\x00" + bytes([len(ahora)]) + ahora)
    return True


# PAREJAS (玩伴): {usn: {usn, anillo}}. Se GUARDAN en la seccion `pareja` de cada cuenta (cuenta.json; antes parejas.json) y se
# arman proponiendo (FF40 0x0A, abajo). Las dos parejas fijas de prueba de antes (cuenta.SEMILLA_PAREJAS) se siembran en la
# mudanza si parejas.json no existia.


def parejas():
    """{usn(int): {usn, anillo}} de todas las cuentas que tienen pareja (cada pareja figura dos veces). Solo lectura."""
    return {int(k): dict(a["pareja"]) for k, a in _cta.todas().items() if a.get("pareja")}


def _volcar(d, seccion, vacio):
    """Dentro de cuenta.cambiar_todas: lo que d dice (usn -> contenido) pasa a la seccion de cada cuenta. Lo que d ya no
    nombra queda vacio. Una entrada nueva sin nada (`vacio`) no se escribe."""
    def f(dd):
        cu = dd["cuentas"]
        for k, a in cu.items():
            nuevo = d.get(int(k))
            if nuevo is None:
                if a.get(seccion):
                    a[seccion] = {}
            elif a.get(seccion) != nuevo and (a.get(seccion) or not vacio(nuevo)):
                a[seccion] = nuevo
    return f


def _cambiar_parejas(f):
    """Con UN solo candado: f(d) con d = {usn: pareja} de todas las cuentas con pareja; lo que f deje en d se guarda (las
    cuentas que ya no figuran quedan sin pareja). Asi una pareja, que toca dos cuentas, no queda a medias. Devuelve lo de f."""
    cambios = []                                               # ficha 117: (usn, pareja que tenia) de las cuentas cuya pareja cambio

    def g(dd):
        d = {int(k): copy.deepcopy(a["pareja"]) for k, a in dd["cuentas"].items() if a.get("pareja")}
        antes = {u: x.get("usn") for u, x in d.items()}
        r = f(d)
        _volcar(d, "pareja", lambda x: not x)(dd)
        if _boda_casados():
            # FICHA 117 (llave BODA_CASADOS): el cliente borra la boda con CUALQUIER 0A 07 / 0A 0B (LEIDO 0x0279fef8 / 0x027a0079); el servidor la borra de las dos cuentas en este mismo candado
            import boda
            boda.borrar_boda_de_las_que_cambian(dd, antes)
            cambios.extend((u, v) for u, v in antes.items() if (d.get(u) or {}).get("usn") != v)
        return r
    r = _cta.cambiar_todas(g)
    if cambios:
        import boda
        for u, v in cambios:
            boda.separadas(u, v)                               # y se olvidan los pedidos en memoria (boda estado 1, divorcio mutuo)
    return r


def _boda_casados():
    """Llave BODA_CASADOS (boda.py, ficha 117), con BODA. Si boda no se puede importar: apagada."""
    try:
        import boda
        return boda.casados_activo()
    except Exception:                                          # noqa: BLE001
        return False


def _guardar_parejas(d):
    """Compat: deja las parejas exactamente como d (un solo candado)."""
    _cambiar_parejas(lambda x: (x.clear(), x.update(copy.deepcopy(d))))


class _Parejas:
    """PAREJAS.get(usn) -> usn de la pareja (lo usan ff4a y salas.equipo_de)."""
    def get(self, usn, defecto=None):
        return (parejas().get(usn) or {}).get("usn", defecto)


PAREJAS = _Parejas()
# PROPUESTAS ({usn del que propone: (usn del propuesto, Index del anillo, hora)}) vive en estado.py: sobrevive a las recargas


def _cuenta_por_usn(usn):
    """La cuenta (formato viejo) con ese usn, o None."""
    import cuenta as _cta
    return next((c for c in _cta.todas_planas() if c.get("usn") == usn), None)


def _apodo(usn):
    n = _gbk(_nick(usn), 13)
    return bytes([len(n)]) + n


def _aceptado(otro_usn, anillo, para_el_que_acepta):
    """S2C FF40 0x0A sub2 4 (al que propuso) / 8 (al que acepto): los dos llaman a 0x478f40 (pone la pareja en la
    cuenta: usn, apodo, A = anillo) y a 0x4738c0 (ficha 74: NO es "el anillo al inventario": arma un registro de 0x38 B con una fecha
    "%04u%02u..." y lo suma a una lista de la cuenta, que parece el historial de pareja; no se vio que toque el inventario).
    Layout leido por un subagente (03-nov):
    [0A][4|8][u32 usn][L][apodo][u32 A][8 B serie][u8 a][u8 L2][txt][u8 b][u32] y despues 28 B (sub2 4, con el u8 f
    final) o 51 B (sub2 8). Lo que no se sabe va en 0 [H]."""
    cab = (bytes([0x0A, 8 if para_el_que_acepta else 4]) + struct.pack("<I", otro_usn) + _apodo(otro_usn)
           + struct.pack("<I", anillo) + bytes(8) + b"\x00\x00\x00" + struct.pack("<I", 0))
    return cab + bytes(51 if para_el_que_acepta else 28)


# ====================================================================================================================
# PAREJA DE VERDAD (ficha 74, 11-nov). LEIDO en el exe (docs/tablero/BODA_LECTURA.md §3 y layouts/FF40.md "Lectura de la ficha 74"):
#  * sub2 02 `[u8 quedan][u8 cod]` (+`[L][apodo]` con cod 0 y 5), manejador 0x0279f39f: 0 solo a conectados (texto 140), 1 diez por
#    dia (141), 2 ya hay UNA propuesta propia pendiente (142: "Cancele su propuesta pendiente"), 4 ya son pareja (144), 5 el otro se
#    desconecto y la propuesta se cancela (145), 6 a uno mismo (146), 7 sin anillo valido (147). NO hay codigo para "alguno ya tiene
#    OTRA pareja": al contrario, el cliente lo permite con un aviso (texto 134 pedido en 0x009582a1, rama `0x00445380` != 0) que dice
#    "si el otro acepta, se termina la relacion actual": por eso NO se exige que ninguno tenga pareja; al aceptar, la anterior se termina
#    (el que queda solo recibe `0A 07 [u32]`, texto 155).
#  * sub2 06 (0x0279f71d) `[u32 usn][u8 L<0xe][apodo][u32 sin uso]`: suma al que propone a la lista de pedidos del cliente (0x0095eeb0);
#    03 (0x0279f8b0) `[u8 quedan][u32][L][apodo]`; 05 (0x0279f7cb) `[u32][L][apodo]`; 0C (0x0279f966) `[u8 quedan]`; 07 (0x0279fef8)
#    y 0B (0x027a0079) `[u32]`: los dos llaman a 0x012c44f0, que borra la pareja de la cuenta del cliente (apodo +0x136c, largo +0x137c,
#    usn +0x1384) y resetean el bloque de boda; 04/08 llaman a 0x00478f40, que la ESCRIBE. O sea que el cliente se actualiza solo con
#    estos S2C; el FF4A solo hace falta al entrar.
#  * C2S: `0A 00 [L][apodo][u32 ChargeId]`, `0A 03 [u32]` / `0A 04 [u32]` (el usn del que propuso), `0A 05`, `0A 07`.
# DEL 2013 (server/servidor/lobby_social.py: couple_propose / couple_accept / couple_reject / couple_cancel / couple_break): proponer pide
# anillo (sin usar), no mira el nivel; 10 propuestas por dia (cancelar no devuelve el cupo); aceptar gasta el anillo y se vuelve amigos;
# separarse ROMPE el anillo. DE ESO SE REPLICA: lo del anillo que hay que TENER y el cupo diario. NO se replica (sin lectura del Steam):
# gastar/romper el anillo (el inventario del cliente no tiene un estado "en uso" conocido: el u8 del registro del FF49 es siempre 0),
# el sexo (codigo 3: el Steam trae anillos "de amistad" para el mismo sexo, textos 1725/1735), la amistad automatica. Todo eso queda
# como esta (el anillo se queda en el inventario).
PE_SOLO_CONECTADOS, PE_DIEZ_POR_DIA, PE_YA_HAY_PROPUESTA, PE_YA_SON_PAREJA = 0, 1, 2, 4
PE_DESCONECTADO, PE_A_UNO_MISMO, PE_SIN_ANILLO = 5, 6, 7
PROPUESTAS_POR_DIA = 10      # texto 141 "Puede enviar su propuesta 10 veces al dia" (LEIDO)

# `Index:ChargeId` de las 110 filas <Couple> de rnr_script/ring.txt del juego chino (rnr_script.pak md5 beae81e06e2f5b363d9600749de01177;
# ring.txt md5 4c4b32ade5707ad800ed6b7428ebf290). El inventario guarda el Index (30xxx); el C2S de proponer trae el ChargeId (HIPOTESIS
# hasta medirlo: se acepta tambien el Index).
_ANILLOS_TXT = """
30005:36005 30006:36006 30007:36007 30009:31009 30017:36017 30027:31027 30030:36030 30078:36078 30080:36080
30090:36090 30102:36102 30120:36120 30162:36162 30182:36182 30717:36717 30638:36638 30743:36743 30815:36815
30513:36513 30539:36539 30482:36482 30561:36561 30639:36639 30562:36562 30640:36640 30797:36797 30803:36803
30805:36805 30807:36807 30029:39029 30060:36060 30205:36205 30562:36562 30639:36639 30799:36799 30809:36809
30816:36816 30829:36829 30645:36645 30475:36475 30823:36823 30834:36834 30827:36827 30478:36478 30528:36528
30487:36487 30198:36198 30760:36760 30830:36830 30800:36800 30814:36814 30814:36814 30313:36313 30466:36466
30160:36160 30810:36810 30751:36751 30633:36633 30822:36822 30828:36828 30831:36831 30832:36832 30096:36096
30216:36216 30826:36826 30818:36818 30835:36835 30837:36837 30492:36492 30495:36495 30570:36570 30836:36836
30821:36821 30508:36508 30813:36813 30798:36798 30806:36806 30820:36820 30802:36802 30819:36819 30838:36838
30472:36472 30804:36804 30571:36571 30801:36801 30839:36839 30825:36825 30315:36315 30808:36808 30811:36811
30817:36817 30842:36842 30840:36840 30845:36845 30846:36846 30824:36824 30848:36848 30841:36841 30850:36850
30851:36851 30852:36852 30849:36849 30843:36843 30853:36853 30833:36833 30854:36854 30856:36856 30855:36855
30857:36857 30858:36858
"""
ANILLOS = {}               # Index -> ChargeId
CARGO_A_ANILLO = {}        # ChargeId -> Index
for _par in _ANILLOS_TXT.split():
    _i, _c = (int(x) for x in _par.split(":"))
    ANILLOS.setdefault(_i, _c)
    CARGO_A_ANILLO.setdefault(_c, _i)

# Lo vivo vive en estado.py (sobrevive a las recargas; estado.py no se recarga). PROPUESTAS: {usn del que propone: (usn del propuesto,
# Index del anillo, hora)}: UNA propuesta por persona (texto 142); un propuesto puede tener varias (la lista del cliente las admite).
_PEND = estado.PROPUESTAS
_HOY = estado.__dict__.setdefault("PROPUESTAS_HOY", {})                  # usn -> (AAAAMMDD, cuantas mando hoy)
_CANDADO = estado.__dict__.setdefault("PROPUESTAS_CANDADO", threading.RLock())


def _quedan(usn, sumar=0):
    """Las propuestas que le quedan hoy a ese usn (suma `sumar` primero)."""
    hoy = time.strftime("%Y%m%d")
    fecha, n = _HOY.get(usn, (hoy, 0))
    if fecha != hoy:
        n = 0
    n += sumar
    _HOY[usn] = (hoy, n)
    return max(0, PROPUESTAS_POR_DIA - n)


def _anillo_que_tiene(con, pedido):
    """Index del anillo de pareja (<Couple> de ring.txt) que la cuenta de `con` tiene en su inventario y vale para `pedido` (el u32 del
    C2S: el ChargeId, o el Index, o 0 = cualquiera); None si no. Un anillo con plazo vencido no cuenta. Solo LEE el inventario."""
    import tienda
    if con is None or not (con.cuenta or {}).get("usn"):
        return None
    bolsa, usn = tienda.bolsa(con)
    ahora = time.time()
    tiene = [r[0] for r in bolsa[usn].get("items", []) if r[0] in ANILLOS and (r[1] in (0, tienda.PERMANENTE) or r[1] > ahora)]
    if pedido == 0:
        return tiene[0] if tiene else None
    idx = CARGO_A_ANILLO.get(pedido, pedido if pedido in ANILLOS else None)
    return idx if idx in tiene else None


def _error_propuesta(con, seq, quedan, cod, nick=b""):
    """S2C `0A 02 [quedan][cod]` (+ `[L][apodo]` con 0 y 5)."""
    cu = bytes([0x0A, 0x02, quedan, cod])
    if cod in (PE_SOLO_CONECTADOS, PE_DESCONECTADO):
        nick = nick[:13]
        cu += bytes([len(nick)]) + nick
    con.mandar_interno(0x40, seq, cu)


def _aviso_cancelada(destino, usn_que_cancela):
    """S2C `0A 05 [u32][L][apodo]` al propuesto: "X ha cancelado la propuesta" (texto 150)."""
    destino.mandar_interno(0x40, 0, bytes([0x0A, 0x05]) + struct.pack("<I", usn_que_cancela) + _apodo(usn_que_cancela))


def _limpiar_propuestas(con):
    """Al desconectarse `con`: se borran sus propuestas pendientes (la que hizo y las que le hicieron) y al otro lado se le avisa: al
    propuesto, con 0A 05 (cancelada); al que propuso, con 0A 02 cod 5 (texto 145: "esta desconectado, su propuesta pendiente ha sido
    cancelada")."""
    yo = (con.cuenta or {}).get("usn")
    if yo is None:
        return
    with _CANDADO:
        propia = _PEND.pop(yo, None)
        ajenas = [k for k, v in _PEND.items() if v[0] == yo]
        for k in ajenas:
            del _PEND[k]
    if propia is not None:
        destino = _conectado(propia[0])
        if destino is not None and destino is not con:
            _aviso_cancelada(destino, yo)
    nick = _gbk(_nick(yo), 13)
    for k in ajenas:
        pc = _conectado(k)
        if pc is not None and pc is not con:
            _error_propuesta(pc, 0, _quedan(k), PE_DESCONECTADO, nick)
    if propia is not None or ajenas:
        anotar("   PAREJA: %s se desconecta: propuestas pendientes borradas (hecha: %s, recibidas: %d)" % (
            (con.cuenta or {}).get("nick"), "si" if propia is not None else "no", len(ajenas)))


def proponer(con, seq, cuerpo):
    """PAREJA (玩伴) por el tunel FF40 0x0A (ver el bloque de arriba y BODA_LECTURA.md §3):
    C2S [0A][00][L][apodo][u32 ChargeId] proponer · [0A][04][u32 x] aceptar · [0A][03][u32 x] rechazar · [0A][05] cancelar la
    propia · [0A][07] separarse.
    S2C sub2 1 OK al que propone [01][quedan][u32 usn][L][apodo] · sub2 2 error [02][quedan][cod](+[L][apodo] con 0/5) ·
    sub2 6 pedido ENTRANTE [06][u32 usn][L][apodo][u32] · sub2 3 rechazado [03][quedan][u32][L][apodo] ·
    sub2 5 cancelado al otro [05][u32][L][apodo] + 0x0C al que cancela [0C][quedan] · sub2 4/8 aceptado ·
    sub2 7 al otro / 0x0B al que se separa [u32 usn]."""
    sub = cuerpo[1]
    yo = (con.cuenta or {}).get("usn")
    nick_yo = (con.cuenta or {}).get("nick")
    if yo is None:
        anotar("   PAREJA: la sesion no tiene cuenta local (sesion capturada): FF40 0A sub 0x%02x no se atiende" % sub)
        return True
    if sub == 0x00 and len(cuerpo) >= 3:
        L = cuerpo[2]
        if len(cuerpo) < 3 + L:
            anotar("   PAREJA: proponer con el apodo cortado (%d B): no se atiende" % len(cuerpo))
            return True
        nick = cuerpo[3:3 + L]
        pedido = struct.unpack_from("<I", cuerpo, 3 + L)[0] if len(cuerpo) >= 7 + L else 0
        c = _por_nick(textos.decodificar(nick))
        otro = _conectado(c["usn"]) if c else None
        quedan = _quedan(yo)
        anillo = None if (c is None or otro is None or c["usn"] == yo) else _anillo_que_tiene(con, pedido)
        d = parejas()
        real = pareja_real()
        with _CANDADO:
            if c is None or otro is None:
                cod = PE_SOLO_CONECTADOS
            elif c["usn"] == yo:
                cod = PE_A_UNO_MISMO
            elif d.get(yo, {}).get("usn") == c["usn"] or (real and (yo in d or c["usn"] in d)):
                cod = PE_YA_SON_PAREJA
            elif anillo is None:
                cod = PE_SIN_ANILLO
            elif yo in _PEND:
                cod = PE_YA_HAY_PROPUESTA
            elif quedan <= 0:
                cod = PE_DIEZ_POR_DIA
            else:
                cod = None
                _PEND[yo] = (c["usn"], anillo, time.time())
                quedan = _quedan(yo, 1)
        if cod is not None:
            _error_propuesta(con, seq, quedan, cod, nick)
            anotar("   PAREJA: %s le propone a %s: codigo de error %d (pedido %d)" % (nick_yo, textos.decodificar(nick), cod, pedido))
            return True
        con.mandar_interno(0x40, seq, bytes([0x0A, 0x01, quedan]) + struct.pack("<I", c["usn"]) + _apodo(c["usn"]))
        otro.mandar_interno(0x40, 0, bytes([0x0A, 0x06]) + struct.pack("<I", yo) + _apodo(yo) + struct.pack("<I", anillo))
        anotar("   PAREJA: %s le propone a %s (anillo %d, el cliente mando %d; le quedan %d)" % (
            nick_yo, textos.decodificar(nick), anillo, pedido, quedan))
    elif sub == 0x04:
        x = struct.unpack_from("<I", cuerpo, 2)[0] if len(cuerpo) >= 6 else None
        with _CANDADO:
            prop = _PEND.get(x)
            if prop is None or prop[0] != yo:
                prop = None
            else:
                del _PEND[x]
        if prop is None:
            anotar("   PAREJA: %s acepta a %s pero no hay propuesta de esa persona: no se hace nada" % (nick_yo, x))
            return True
        anillo = prop[1]
        proponente = _conectado(x)
        if proponente is None or _anillo_que_tiene(proponente, anillo) is None:
            # el que propuso ya no esta o ya no tiene el anillo (lo regalo, vencio): ninguna pareja, nada escrito (como el 2013, code 7)
            for q in (con, proponente):
                if q is not None:
                    _error_propuesta(q, seq if q is con else 0, _quedan(x), PE_SIN_ANILLO)
            anotar("   PAREJA: %s acepta a %s pero el anillo %d ya no esta: no son pareja" % (nick_yo, _nick(x), anillo))
            return True

        real = pareja_real()
        desde = time.strftime("%Y%m%d%H%M%S") if real else None

        def aceptar(dd):
            if dd.get(yo, {}).get("usn") == x and dd.get(x, {}).get("usn") == yo:
                return None                                   # ya eran pareja (propuestas cruzadas): nada que escribir
            if real and (yo in dd or x in dd):
                return "ya_tiene"                             # M11 (PAREJA_REAL=1): ninguno puede tener pareja previa
            dejados = []                                      # (el que quedo solo, el que se fue)
            for a, b2 in ((yo, x), (x, yo)):
                viejo = dd.pop(a, {}).get("usn")
                if viejo and viejo != b2:
                    dd.pop(viejo, None)
                    dejados.append((viejo, a))
                reg = {"usn": b2, "anillo": anillo}
                if real:
                    reg["desde"] = desde
                dd[a] = reg
            return dejados
        dejados = _cambiar_parejas(aceptar)                    # las dos cuentas (y las parejas que dejan) en UN candado
        if dejados == "ya_tiene":
            _error_propuesta(con, seq, _quedan(yo), PE_YA_SON_PAREJA)
            anotar("   PAREJA: %s acepta a %s pero alguno ya tiene pareja (PAREJA_REAL=1): nada escrito" % (nick_yo, _nick(x)))
            return True
        with _CANDADO:                                         # una propuesta cruzada entre los dos ya no tiene sentido
            if _PEND.get(yo, (None,))[0] == x:
                del _PEND[yo]
        if dejados is None:
            anotar("   PAREJA: %s acepta a %s: ya eran pareja (nada que escribir)" % (nick_yo, _nick(x)))
            return True
        con.mandar_interno(0x40, seq, _aceptado(x, anillo, True))
        proponente.mandar_interno(0x40, 0, _aceptado(yo, anillo, False))
        pareja_al_mensajero(yo, x)
        for solo, se_fue in dejados:
            if _conectado(solo) is not None:
                _conectado(solo).mandar_interno(0x40, 0, bytes([0x0A, 0x07]) + struct.pack("<I", se_fue))
        anotar("   PAREJA: %s acepta a %s: ahora son pareja (anillo %d)%s" % (
            nick_yo, _nick(x), anillo, "; terminan con otra pareja: %d" % len(dejados) if dejados else ""))
    elif sub == 0x03:
        x = struct.unpack_from("<I", cuerpo, 2)[0] if len(cuerpo) >= 6 else None
        with _CANDADO:
            prop = _PEND.get(x)
            if prop is None or prop[0] != yo:
                prop = None
            else:
                del _PEND[x]
        if prop is not None and _conectado(x) is not None:
            _conectado(x).mandar_interno(0x40, 0, bytes([0x0A, 0x03, _quedan(x)]) + struct.pack("<I", yo) + _apodo(yo))
        anotar("   PAREJA: %s rechaza a %s%s" % (nick_yo, x, "" if prop is not None else " (no habia propuesta)"))
    elif sub == 0x05:
        with _CANDADO:
            prop = _PEND.pop(yo, None)
        if prop is not None and _conectado(prop[0]) is not None:
            _aviso_cancelada(_conectado(prop[0]), yo)
        # el 0C se contesta siempre: el cliente se queda esperando y, tras un reinicio, la propuesta ya no esta en el servidor
        con.mandar_interno(0x40, seq, bytes([0x0A, 0x0C, _quedan(yo)]))
        anotar("   PAREJA: %s cancela su propuesta%s" % (nick_yo, "" if prop is not None else " (no habia ninguna en el servidor)"))
    elif sub == 0x07:
        def separar(dd):
            otro_ = dd.pop(yo, {}).get("usn")
            if otro_:
                dd.pop(otro_, None)
            return otro_
        el = _cambiar_parejas(separar)
        if el:
            if _conectado(el) is not None:
                _conectado(el).mandar_interno(0x40, 0, bytes([0x0A, 0x07]) + struct.pack("<I", yo))
            con.mandar_interno(0x40, seq, bytes([0x0A, 0x0B]) + struct.pack("<I", el))
        anotar("   PAREJA: %s se separa de %s" % (nick_yo, _nick(el) if el else "(nadie)"))
    else:
        anotar("   FF40 0x0A sub2 0x%02x sin manejar: %s" % (sub, cuerpo.hex(" ")))
        return False
    return True


# ---- la FICHA de otro jugador (cUserinfo_NewUI: ver ropa, agregar amigo, PROPONER PAREJA). Subagente, 03-nov:
#   C2S FF40 0x01 SendGetUserInfo [01][L][apodo][u32 usn][u8 bandera] -> S2C FF40 0x02 [02][ok 1][b2][L][apodo<14]
#     [u32 A][8 B][u32 C][u16 D][u16 E][u16 F][u32 G][u32 H][u8 I][u8 L2][txt][u8 J][u8 K][u8 M][u32 N][u32 usn]; el
#     cliente sigue con C2S FF77 SendExamine [u32 usn][L][apodo] y FF40 06 [u32 usn]
#   S2C FF77 CmdExamine (566 B, plantilla del oficial: datos/examinar_S2C.bin; byte 0 = 0 OK) ABRE la ficha
#   S2C FF40 0x06 [06][tipo 1][u32][L][apodo][u32][8 B][u32][u16 D][u16][u16][u32][u32][u8][u8 L2][txt][u8][u8][u8]
#     [u32][u8 L3][txt][10 x u32]
def _cuenta_de(nick=None, usn=None):
    return next((c for c in _todas() if (nick and c.get("nick") == nick) or (usn and c.get("usn") == usn)), None)


def ficha_pedir(con, seq, cuerpo):
    L = cuerpo[1]
    nick = textos.decodificar(cuerpo[2:2 + L])
    usn = struct.unpack_from("<I", cuerpo, 2 + L)[0] if len(cuerpo) >= 6 + L else 0
    c = _cuenta_de(nick or None, usn or None)
    if c is None:
        con.mandar_interno(0x40, seq, bytes([0x02, 0, 1]))
        anotar("   FF40 0x01 ficha de %r: no existe" % nick)
        return True
    n = _gbk(c["nick"], 13)
    cu = (bytes([0x02, 1, 0, len(n)]) + n + bytes(4 + 8 + 4) + struct.pack("<HHH", 1, 0, 0) + bytes(8)
          + bytes([0, 0, 0, 0, 0]) + struct.pack("<II", 0, c["usn"]))
    con.mandar_interno(0x40, seq, cu)
    anotar("   FF40 0x01 ficha de %s -> 0x02 (usn %d)" % (c["nick"], c["usn"]))
    return True


def ficha_datos(con, seq, cuerpo):
    usn = struct.unpack_from("<I", cuerpo, 1)[0]
    c = _cuenta_de(usn=usn)
    if c is None:
        return False
    n = _gbk(c["nick"], 13)
    cu = (bytes([0x06, 1]) + struct.pack("<I", usn) + bytes([len(n)]) + n + bytes(4 + 8 + 4)
          + struct.pack("<HHH", 1, 0, 0) + bytes(8) + bytes([0, 0, 0, 0, 0]) + bytes(4) + b"\x00" + bytes(40))
    con.mandar_interno(0x40, seq, cu)
    return True


# ---- La PAREJA en la ficha (individual: 个人信息, solapa 关系). Ficha 78 (11-nov). CADENA LEIDA del exe (docs/tablero/layouts/FF77.md,
# "Lectura de la ficha 78"): la solapa dibuja "SetSingle" (el cartel de "no tenes pareja") si [UI+0x1568] == 0 (0x00b8c7c0) y
# "SetCouple"/"SetModelCouple" si no; [UI+0x1568] = (struct+0x23d != 0) (0x00b89b7e/0x00b89b90) y struct+0x23d es el u8 `#62` del FF77
# (el manejador 0x027babc0 lo lee en 0x027bd318; con #62 == 0 salta todo el bloque, 0x027bd33b). El bloque #62..#85 ya no es una
# plantilla fija: se arma con la seccion `pareja` de la cuenta. Campos (LEIDO salvo lo marcado):
#   #62 u8 hay pareja | #63 u32 Index del anillo (HIPOTESIS: solo lo usa la ficha de OTRO jugador, 0x00b90f85) | #64 u8 L + #65 texto
#   (TXT_CONFESSION, 0x00b90d40: la "confesion"; se manda vacio) | #66 u8 modelo (UI+0x1569; 0 = sin modelo, SetModelCouple no lo dibuja;
#   el modelo (#71..#84) NO se manda) | #67 u8 L + #68 apodo de la pareja (TXT_NAME, 0x00b90b72, <= 13 B) | #69/#70 u8 nivel e icono de la
#   pareja (LEVEL, 0x00b90b03..0x00b90b68; NO se sabe: 0) | #85 u64 fecha de inicio {u16 anio, u8 mes, u8 dia, hora, min, seg, 0}
#   (TXT_DATE, 0x00b90be9..0x00b90ca2 lee anio, mes y dia; sin fecha guardada: ceros).
#   ⚠ APAGADA por omision (11-nov): con el juego (copias 2 y 3, con pareja y el bloque armado) la solapa 关系 SIGUE diciendo "no tenes
#   pareja" ([UI+0x1568] queda en 0, leido con ReadProcessMemory). Ver docs/tablero/layouts/FF77.md, "Lectura de la ficha 78": el FF77 NO
#   llega al campo #62 en este exe (HIPOTESIS: el tramo del manejador que vive en la cueva 0x1da649d4 lee 4 B fijos en +9 donde el
#   oficial parece traer [L][bytes], y el resto del flujo queda desalineado). Se deja armado para cuando se arregle eso.
LLAVES_OMISION = {"FICHA_PAREJA": "0", "PAREJA_EN_MENSAJERO": "1", "PAREJA_REAL": "1"}   # ficha 112: tipo 1 prende el icono 玩伴; M11: PAREJA_REAL (sin pareja los dos + fecha `desde` en cuenta y registro97 +0x2f)
FF77_LARGO = 566          # la plantilla del oficial: #62 es el u8 de +561 y #86 (u32 = 0) cierra los 4 ultimos bytes
FF77_PAREJA_OFS = 561


def llave(nombre="FICHA_PAREJA"):
    return os.environ.get(nombre, LLAVES_OMISION[nombre]) == "1"


def pareja_real():
    """Llave M11 (entorno PAREJA_REAL, leida en el momento, omision '1'): exige que ninguno tenga pareja al proponer/aceptar y guarda `desde`."""
    return llave("PAREJA_REAL")


def _fecha8(desde):
    """'AAAAMMDDhhmmss' (o vacio) -> u64 del FF77 #85 / FF45 (anio u16, mes, dia, hora, minuto, segundo, relleno). Ceros si no hay."""
    try:
        s = str(desde or "")
        if len(s) != 14 or not s.isdigit():
            return bytes(8)
        return struct.pack("<H6B", int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]), 0)
    except Exception:                                                # noqa: BLE001
        return bytes(8)


def _bloque_pareja(c):
    """Los bytes de FF77 #62..#85 de la cuenta `c` (dict con usn) si tiene pareja de verdad; None si no (entonces el FF77 sale como siempre)."""
    p = parejas().get(c.get("usn")) or {}
    otro = _cuenta_por_usn(p.get("usn")) if p.get("usn") else None
    if not otro:
        return None
    nick = _gbk(otro.get("nick", ""), 13)
    anillo = p.get("anillo", 0)
    anillo = CARGO_A_ANILLO.get(anillo, anillo)                      # el Index (si quedo guardado el ChargeId)
    return (b"\x01" + struct.pack("<I", anillo & 0xFFFFFFFF) + b"\x00"       # #62, #63, #64 (L = 0: sin #65)
            + b"\x00" + bytes([len(nick)]) + nick + b"\x00\x00"                # #66 (sin modelo), #67, #68, #69, #70
            + _fecha8(p.get("desde")))                                          # #85


def examinar(con, seq, cuerpo):
    """C2S FF77 SendExamine [u32 usn][L][apodo] -> S2C FF77 con la plantilla del oficial y el personaje y la ropa de
    esa cuenta (+29 char_id, +35 las partes). Si esa cuenta tiene pareja (llave FICHA_PAREJA), el bloque #62..#85 sale armado."""
    import os
    if len(cuerpo) < 5:
        return False
    usn = struct.unpack_from("<I", cuerpo, 0)[0]
    L = cuerpo[4]
    nick = textos.decodificar(cuerpo[5:5 + L])
    c = _cuenta_de(nick or None, usn or None)
    if c is not None and not os.path.exists(ajustes.RUTA_EXAMINAR):
        con.mandar_interno(0x77, seq, neutro.ff77_examinar(c))
        anotar("   FF77 examinar: ficha neutra de cuenta local")
        return True
    plantilla = captura.ficha_examinar() if c is not None else None
    if c is None or plantilla is None:
        anotar("   FF77 examinar %r: %s" % (nick, "no existe" if c is None else "falta datos/examinar_S2C.bin "
                                                                     "(herramientas/preparar_examinar.py)"))
        return False
    t = bytearray(plantilla)
    pj = c.get("personaje") or {}
    struct.pack_into("<I", t, 29, pj.get("char_id", 130900))
    partes = (list(pj.get("partes", [])) + [0] * 4)[:4]
    struct.pack_into("<4I", t, 35, *partes)
    con_pareja = ""
    if llave() and len(t) == FF77_LARGO and t[FF77_PAREJA_OFS] == 0 and not any(t[FF77_PAREJA_OFS + 1:]):
        blq = _bloque_pareja(c)
        if blq is not None:
            t[FF77_PAREJA_OFS:FF77_PAREJA_OFS + 1] = blq
            con_pareja = ", con pareja"
    con.mandar_interno(0x77, seq, bytes(t))
    anotar("   FF77 examinar a %s: personaje %d, ropa %s%s" % (c["nick"], pj.get("char_id", 0), partes, con_pareja))
    return True


def ff4a(con):
    """S2C FF4A CmdGetCoupleData (handler 0x027a6900, leido por un subagente el 03-nov):
    [u32 usn de la pareja][u32 B (¿anillo?)][u8 X][u8 L][nick GBK, L <= 12][u8 L2 = 0 (si no, es aviso de separacion)].
    Escribe la pareja en la cuenta propia (0x445800 +0x136c nick, +0x1384 usn); el modo 玩伴 solo mira que el nick no
    este vacio (cartel 0x703 «由于您没有玩伴»). Sin pareja: 11 ceros (lo del oficial)."""
    p = parejas().get((con.cuenta or {}).get("usn")) or {}
    otro = p.get("usn")
    c = _cuenta_por_usn(otro) if otro else None
    if not c:
        return bytes(11)
    nick = textos.codificar(c["nick"], 12)
    return struct.pack("<IIBB", otro, p.get("anillo", 0), 0, len(nick)) + nick + b"\x00"


def reenviar_ff4a(con, cu):
    """El FF4A repetido, 1.5 s despues (lo arma estado.mas_tarde, que busca esta funcion por nombre al disparar)."""
    con.mandar_interno(0x4A, 0, cu)


def pareja(con, seq, cuerpo):
    if cuerpo:
        return False
    cu = ff4a(con)
    con.mandar_interno(0x4A, seq, cu)
    if len(cu) > 11:
        # ⚠ la ficha FF00 BORRA la pareja (0x0277c899 la reescribe siempre con la que trae, vacia) y juego.py la manda
        # de nuevo ~0.4 s despues de este pedido (medido 03-nov): se repite el FF4A cuando ya llego
        estado.mas_tarde(1.5, "social.reenviar_ff4a", con, cu)
        anotar("   FF4A pareja de %s: %s" % ((con.cuenta or {}).get("nick"), textos.decodificar(cu[10:-1])))
    return True


def tunel(con, seq, cuerpo):
    """FF40 CmdSessionForward: por ahora solo el sub 0x21 (GuildInfo). El resto sigue su camino (captura)."""
    if cuerpo == b"\x21":
        con.mandar_interno(0x40, seq, b"\x21\x00\x00" + b"\xff" * 4 + bytes(6))
        return True
    if cuerpo[:1] == b"\x09" and len(cuerpo) == 5:
        return borrar_amigo(con, seq, cuerpo)
    if cuerpo[:1] in (b"\x04", b"\x0d"):
        return susurro(con, seq, cuerpo)
    if cuerpo[:1] == b"\x0b" and len(cuerpo) >= 6:
        if megafono(con, seq, cuerpo):                                 # M10: con las llaves apagadas devuelve False y sigue como siempre
            return True
    if cuerpo[:1] == b"\x0a" and len(cuerpo) >= 2:
        return proponer(con, seq, cuerpo)
    if cuerpo[:1] == b"\x01" and len(cuerpo) >= 2:
        return ficha_pedir(con, seq, cuerpo)
    if cuerpo[:1] == b"\x06" and len(cuerpo) >= 5:
        return ficha_datos(con, seq, cuerpo)
    if cuerpo[:1] == b"\x3f" and len(cuerpo) >= 3:
        # SendCheckUserLogin (0x027db980): [3F][motivo][L][apodo] = ¿existe y esta conectado? (motivo 0x17 = agregar
        # amigo). S2C [3F][motivo][estado 0][L][apodo] -> con 0x17 el cliente manda el FF23B tipo 1. «No existe»: motivo
        # distinto de 0x17/0x71/0x8e/0x38 con estado 0 -> texto 0x5d «您所查找的用户未在线或不存在» (subagente, 03-nov)
        motivo, L = cuerpo[1], cuerpo[2]
        nick = cuerpo[3:3 + L]
        c = _por_nick(textos.decodificar(nick))
        hay = bool(c and _conectado(c["usn"]))
        if hay:
            con.mandar_interno(0x40, seq, bytes([0x3F, motivo, 0, len(nick)]) + nick)
        else:
            con.mandar_interno(0x40, seq, b"\x3f\x00\x00\x00")
        anotar("   FF40 0x3F consulta %r (motivo 0x%02x): %s" % (textos.decodificar(nick), motivo,
               "conectado" if hay else "no existe / no conectado"))
        return True
    anotar("   FF40 sub 0x%02x (%d B) sin manejar: %s" % (cuerpo[0] if cuerpo else -1, len(cuerpo), cuerpo[:24].hex(" ")))
    return False


# ====================================================================================================================
# AMIGOS, SUSURRO e INVITAR (3-nov). Layouts del cliente Steam leidos del exe por un subagente (estatico): la mensajeria
# es la ventana cMessenger_NewUI (boton BTN_FRIENDLIST del lobby), NO 社交->密友 (eso es el 密友群, FF1DE..FF1EC).
#   C2S FF214 (vacio, desde CmdLogin)  -> S2C FF214 CmdMSGInit: [u32 n][n x 97 B][u32 g][g x 26 B][u32 m][m x 19 B]
#     registro de 97 B: +0 tipo (1 pareja, 2 AMIGO, 8 bloqueado, 0xb enviados, 0xc recibidos) +5 u32 usn
#     +9 u8 en linea +0xf apodo 13 B (el resto, UI: en 0)
#   C2S FF23B SendAddFriendReform 34 B: [16 B 0][u8 tipo][00][u8 L][00][apodo 14 B]; tipo 1 pedir, 2/5 aceptar,
#     3/6 rechazar, 4 cancelar [H], 7 = dame los pendientes [H]
#   S2C FF23B 34 B: +4 u32 usn del otro, +8/+0xc contadores, +0x11 CODIGO, +0x12 L, +0x14 apodo; codigo 2 = pedido hecho
#     (al que pide), 3 = pedido ENTRANTE (cartel), 6/9/0xb sacan de enviados, 7/8/0xa de recibidos, 0x10 ya amigos,
#     0x12/0x13 errores
#   S2C FF23C pendientes: [u32 0][u32 usn a sacar][u32 contador][u8 1 enviados / 2 recibidos][u32 n][n x 19 B:
#     u8 tipo 0xb/0xc, u32 usn, apodo 13 B, u8 0]
#   S2C FF216 CmdMSGUpdate [u32 n][n x 97 B]: tipo != 0 agrega/actualiza, 0 lo saca
# Lo guardado: cuenta.json, seccion `amigos` de cada cuenta {"amigos": [...], "enviados": [...], "recibidos": [...]} (fuera de git;
# antes datos/amigos.json).

def _amigos():
    """{usn(int): {amigos, enviados, recibidos}} de las cuentas que tienen algo. Solo lectura (copia)."""
    return {int(k): copy.deepcopy(a["amigos"]) for k, a in _cta.todas().items() if a.get("amigos")}


def _cambiar_amigos(f):
    """Con UN solo candado: f(d) con d = {usn: amigos} (usar _de para tomar o crear el de un usn); lo que f deje en d se
    guarda en cada cuenta. Una amistad toca DOS cuentas y no queda a medias. Devuelve (lo de f, copia de d ya cambiado)."""
    def g(dd):
        d = {int(k): a["amigos"] for k, a in dd["cuentas"].items() if a.get("amigos")}
        r = f(d)
        _volcar(d, "amigos", lambda x: not any(x.values()))(dd)
        return r, copy.deepcopy(d)
    return _cta.cambiar_todas(g)


def _guardar_amigos(d):
    """Compat: deja los amigos exactamente como d (un solo candado)."""
    _cambiar_amigos(lambda x: (x.clear(), x.update(copy.deepcopy(d))))


def _de(d, usn):
    return d.setdefault(usn, {"amigos": [], "enviados": [], "recibidos": []})


def _todas():
    """Todas las cuentas locales en el formato viejo."""
    import cuenta as _cta
    return _cta.todas_planas()


def _nick(usn):
    c = next((c for c in _todas() if c.get("usn") == usn), None)
    return (c or {}).get("nick", "")


def _por_nick(nick):
    return next((c for c in _todas() if c.get("nick") == nick), None)


def _conectado(usn):
    return next((c for c in estado.CONEXIONES.values() if (c.cuenta or {}).get("usn") == usn), None)


def _gbk(t, n):
    return textos.codificar(t, n)


def _desde_pareja(usn):
    """Texto AAAAMMDD (8 B ASCII, LEIDO 0x00871ec1 / 0x02732c60, BODA_LECTURA.md §2) de desde cuando `usn` tiene pareja (玩伴纪念日), con PAREJA_REAL=1."""
    if not pareja_real():
        return b""
    d = str((parejas().get(usn) or {}).get("desde") or "")
    return d[:8].encode("ascii") if len(d) >= 8 and d[:8].isdigit() else b""


def registro97(tipo, usn):
    r = bytearray(97)
    r[0] = tipo
    struct.pack_into("<I", r, 5, usn)
    r[9] = 1 if _conectado(usn) else 0
    nick = _gbk(_nick(usn), 12)
    r[0xf:0xf + len(nick)] = nick
    desde = _desde_pareja(usn)
    if desde:
        # M11 (LEIDO 0x00871ec1 / 0x02732c60, BODA_LECTURA.md §2): reg+0x2f = fecha AAAAMMDD -> 玩伴纪念日 (en todo registro de ese usn, como +0x3e)
        r[0x2f:0x2f + len(desde)] = desde
    aniv = _aniversario_de(usn)
    if aniv:
        # ficha 117 (MEDIDO con el juego): reg+0x3e = fecha de la boda AAAAMMDD -> 结婚纪念日. Va en TODO registro de ese usn (tipo 1, 2 y 0): si la pareja tambien es amiga, la
        # ficha de amigo (tipo 2) pisa a la de pareja al abrir la pagina y el aniversario volvia a "Ninguno" (visto: amigos = Ninguno, no amigos = 2026/11/10).
        r[0x3e:0x3e + len(aniv)] = aniv
    return bytes(r)


def registro19(tipo, usn):
    nick = _gbk(_nick(usn), 12)
    return bytes([tipo]) + struct.pack("<I", usn) + nick.ljust(13, b"\0") + b"\0"


def ff23b(usn_otro, codigo, nick=""):
    r = bytearray(34)
    struct.pack_into("<I", r, 4, usn_otro)
    r[0x11] = codigo
    n = _gbk(nick or _nick(usn_otro), 12)
    r[0x12] = len(n)
    r[0x14:0x14 + len(n)] = n
    return bytes(r)


def ff23c(yo, cual, d):
    lista = _de(d, yo)["enviados" if cual == 1 else "recibidos"]
    regs = b"".join(registro19(0xb if cual == 1 else 0xc, u) for u in lista)
    return struct.pack("<IIIBI", 0, 0, len(lista), cual, len(lista)) + regs


# Ficha 71 (11-nov). LEIDO en el exe (layouts/FF216.md, FF23B.md, FF40.md "Lectura de la ficha 71"):
#  * un registro de 97 B de FF216 con tipo != 0 es un ALTA (map::insert en el codigo; MEDIDO 11-nov: igual pasa a en linea un amigo listado fuera de linea); tipo 0 ACTUALIZA
#    en sitio por usn (0x00878ad0) y el unico estado que entiende el cliente es el byte +9 (0 fuera de linea, !=0 en linea);
#  * FF23B S2C con codigo +0x11 = 4 o 5 saca el usn de la lista de amigos (0x02866634), sin cartel; FF40 S2C 09 no hace nada.
# Llaves. FUERA_DE_LINEA=1 por omision (visto en pantalla con 2 copias: el amigo pasa a 不在线好友). EN_LINEA_TIPO0=0 por omision:
# el tipo 2 de siempre ya pasa a un amigo de fuera de linea a en linea (medido); el tipo 0 no hizo falta.
FUERA_DE_LINEA = os.environ.get("FUERA_DE_LINEA", "1") == "1"      # al desconectarse: FF216 tipo 0, +9=0 a los amigos conectados
EN_LINEA_TIPO0 = os.environ.get("EN_LINEA_TIPO0", "0") == "1"     # al entrar: ademas del tipo 2, un tipo 0 con +9=1


def registro97_estado(usn, en_linea):
    """Registro de 97 B de tipo 0 (actualiza en sitio): usn, +9 = en linea (1) o fuera (0), apodo."""
    r = bytearray(registro97(0, usn))
    r[9] = 1 if en_linea else 0
    return bytes(r)


# Ficha 112 (12-nov). LEIDO (BODA_LECTURA.md "Lectura de la ficha 110"): el icono 玩伴 del mensajero se prende con `[mensajero+0x4b0]` != 0 y eso lo
# escribe SOLO `AddUserData` (0x00878600 -> 0x008789d0) con un registro de 97 B de TIPO 1 (+0 = 1, +5 = usn de la pareja); llega por FF214 (la lista) o
# FF216 `[u32 n][n x 97 B]`. Los demas campos del tipo 1 (+9 en linea, +0xf apodo) = como los del tipo 2: HIPOTESIS. Llave PAREJA_EN_MENSAJERO.
def pareja_en_mensajero():
    return llave("PAREJA_EN_MENSAJERO")


def registro_pareja(otro, en_linea=None):
    """Registro de 97 B de tipo 1 (la pareja) de `otro`. `en_linea` None = lo que diga la conexion; True/False lo fuerza (+9)."""
    r = bytearray(registro97(1, otro))
    if en_linea is not None:
        r[9] = 1 if en_linea else 0
    return bytes(r)                       # (la fecha de la boda +0x3e la pone registro97, ficha 117)


def _aniversario_de(otro):
    """Texto AAAAMMDD de la boda de `otro` con su pareja si estan casados (boda.aniversario, llave BODA_CASADOS), si no b""."""
    if not _boda_casados():
        return b""
    try:
        import boda
        b = (parejas().get(otro) or {}).get("usn")
        return boda.aniversario(otro, b) if b else b""
    except Exception:                                          # noqa: BLE001
        return b""


def pareja_al_mensajero(a, b):
    """Al formarse la pareja (0A 04/08): FF216 `[u32 1][registro tipo 1]` a cada uno, con la pareja del OTRO."""
    if not pareja_en_mensajero():
        return
    for yo, otro in ((a, b), (b, a)):
        c = _conectado(yo)
        if c is not None:
            c.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro_pareja(otro))
    anotar("   FF216 tipo 1 (pareja) a %d y %d" % (a, b))


def avisar_pareja_estado(yo, en_linea):
    """HIPOTESIS (ficha 112): cuando yo entro o salgo, la pareja conectada recibe de nuevo su registro tipo 1 con +9 = en linea / fuera
    (tipo 1 otra vez pisa el FriendInfo de la pareja; tipo 0 NO busca en esa lista, 0x00878ad0)."""
    if not pareja_en_mensajero():
        return
    otro = (parejas().get(yo) or {}).get("usn")
    c = _conectado(otro) if otro else None
    if c is not None:
        c.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro_pareja(yo, en_linea))


def borrar_amigo(con, seq, cuerpo):
    """C2S FF40 [09][u32 usn] (SendDeleteFriend): quita la amistad de las DOS cuentas en un candado y manda FF23B codigo 4
    (el cliente lo usa para sacar al usn de la lista de amigos) a quien borra y, si esta conectado, al otro. Si no eran
    amigos no escribe nada. No contesta el S2C 09 (el cliente no hace nada con el). HIPOTESIS: el oficial usa 4 y no 5."""
    yo = (con.cuenta or {}).get("usn")
    ou = struct.unpack_from("<I", cuerpo, 1)[0]
    if yo is None or ou == yo:
        return True

    def cambio(d):
        me = _de(d, yo)
        el = _de(d, ou)
        if ou not in me["amigos"] and yo not in el["amigos"]:
            return False
        for a, u in ((me, ou), (el, yo)):
            if u in a["amigos"]:
                a["amigos"].remove(u)
        return True
    hubo, _d = _cambiar_amigos(cambio)
    if not hubo:
        anotar("   FF40 09 borrar: %s y %d no eran amigos (nada que borrar)" % ((con.cuenta or {}).get("nick"), ou))
        return True
    con.mandar_interno(0x23B, 0, ff23b(ou, 4))
    otro = _conectado(ou)
    if otro is not None and otro is not con:
        otro.mandar_interno(0x23B, 0, ff23b(yo, 4))
    anotar("   FF40 09: %s borra a %d: sin amistad en las dos cuentas, FF23B codigo 4 a %s" % (
        (con.cuenta or {}).get("nick"), ou, "los dos" if otro is not None else "quien borra (el otro no esta conectado)"))
    return True


def desconectado(con):
    """Llamado por manejadores.desconectado (la conexion ya salio de estado.CONEXIONES): FF216 tipo 0 con +9 = 0 a cada
    amigo CONECTADO. Con la llave FUERA_DE_LINEA apagada no hace nada ESO. Ficha 74: antes, siempre, se borran las propuestas de
    pareja pendientes de esta conexion y al otro lado se le avisa (_limpiar_propuestas)."""
    try:
        _limpiar_propuestas(con)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ al limpiar las propuestas de pareja: %r" % e)
    yo = (con.cuenta or {}).get("usn")
    if yo is not None:
        try:
            avisar_pareja_estado(yo, False)
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ al avisar la pareja fuera de linea: %r" % e)
    if not FUERA_DE_LINEA:
        return
    if yo is None:
        return
    n = 0
    for u in _de(_amigos(), yo)["amigos"]:
        otro = _conectado(u)
        if otro is not None and otro is not con:
            otro.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro97_estado(yo, False))
            n += 1
    if n:
        anotar("   FF216 fuera de linea de %s a %d amigo(s) conectado(s)" % ((con.cuenta or {}).get("nick"), n))


def mensajeria(con, seq, cuerpo):
    """C2S FF214 MSGInit -> la lista de amigos (y bloqueados/pendientes) de la cuenta."""
    if cuerpo:
        return False
    yo = (con.cuenta or {}).get("usn")
    d = _amigos()
    me = _de(d, yo)
    regs = [registro97(2, u) for u in me["amigos"]]
    otra = (parejas().get(yo) or {}).get("usn") if pareja_en_mensajero() else None
    if otra:
        regs.append(registro_pareja(otra))                    # ficha 112: tipo 1 = prende el icono 玩伴 del mensajero
    pend = [registro19(0xb, u) for u in me["enviados"]] + [registro19(0xc, u) for u in me["recibidos"]]
    cu = (struct.pack("<I", len(regs)) + b"".join(regs) + struct.pack("<I", 0)
          + struct.pack("<I", len(pend)) + b"".join(pend))
    con.mandar_interno(0x214, seq, cu)
    anotar("   FF214 mensajeria de %s: %d registros (%d de pareja tipo 1), %d pendientes" % ((con.cuenta or {}).get("nick"), len(regs), 1 if otra else 0, len(pend)))
    avisar_pareja_estado(yo, True)
    # avisar a los amigos conectados que este entro (en linea)
    for u in me["amigos"]:
        otro = _conectado(u)
        if otro is not None and otro is not con:
            otro.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro97(2, yo))
            if EN_LINEA_TIPO0:
                otro.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro97_estado(yo, True))
    return True


def amistad(con, seq, cuerpo):
    """C2S FF23B: pedir / aceptar / rechazar amistad (por apodo)."""
    if len(cuerpo) != 34:
        return False
    tipo, L = cuerpo[16], cuerpo[18]
    nick = textos.decodificar(cuerpo[20:20 + L])
    yo = (con.cuenta or {}).get("usn")
    d = _amigos()
    me = _de(d, yo)
    if tipo == 7:
        con.mandar_interno(0x23C, seq, ff23c(yo, 1, d))
        con.mandar_interno(0x23C, 0, ff23c(yo, 2, d))
        return True
    otra = _por_nick(nick)
    if otra is None or otra.get("usn") == yo:
        con.mandar_interno(0x23B, seq, ff23b(0, 0x13, nick))
        anotar("   FF23B amistad %d de %s a %r: no existe" % (tipo, (con.cuenta or {}).get("nick"), nick))
        return True
    ou = otra["usn"]
    otro = _conectado(ou)

    def cambio(d):
        me = _de(d, yo)
        el = _de(d, ou)
        if tipo == 1:
            if ou in me["amigos"]:
                return "ya"
            if ou not in me["enviados"]:
                me["enviados"].append(ou)
            if yo not in el["recibidos"]:
                el["recibidos"].append(yo)
            return "pidio"
        if tipo in (2, 5):
            for lista, u in ((me["recibidos"], ou), (el["enviados"], yo)):
                if u in lista:
                    lista.remove(u)
            for a, b2 in ((me, ou), (el, yo)):
                if b2 not in a["amigos"]:
                    a["amigos"].append(b2)
            return "acepto"
        if tipo in (3, 6, 4):
            for lista, u in ((me["recibidos"], ou), (el["enviados"], yo), (me["enviados"], ou), (el["recibidos"], yo)):
                if u in lista:
                    lista.remove(u)
            return "rechazo"
        return "otro"
    r, d = _cambiar_amigos(cambio)        # decidir y guardar las dos cuentas en UN candado; los mensajes salen despues
    if r == "ya":
        con.mandar_interno(0x23B, seq, ff23b(ou, 0x10))
        return True
    if r == "pidio":
        con.mandar_interno(0x23B, seq, ff23b(ou, 2))
        con.mandar_interno(0x23C, 0, ff23c(yo, 1, d))
        if otro is not None:
            otro.mandar_interno(0x23B, 0, ff23b(yo, 3))
            otro.mandar_interno(0x23C, 0, ff23c(ou, 2, d))
        anotar("   FF23B %s le pide amistad a %s" % ((con.cuenta or {}).get("nick"), nick))
    elif r == "acepto":
        con.mandar_interno(0x216, seq, struct.pack("<I", 1) + registro97(2, ou))
        con.mandar_interno(0x23B, 0, ff23b(ou, 7))
        con.mandar_interno(0x23C, 0, ff23c(yo, 2, d))
        if otro is not None:
            otro.mandar_interno(0x216, 0, struct.pack("<I", 1) + registro97(2, yo))
            otro.mandar_interno(0x23B, 0, ff23b(yo, 6))
            otro.mandar_interno(0x23C, 0, ff23c(ou, 1, d))
        anotar("   FF23B %s acepta a %s: amigos" % ((con.cuenta or {}).get("nick"), nick))
    elif r == "rechazo":
        con.mandar_interno(0x23B, seq, ff23b(ou, 0xa))
        con.mandar_interno(0x23C, 0, ff23c(yo, 2, d))
        if otro is not None:
            otro.mandar_interno(0x23B, 0, ff23b(yo, 9))
            otro.mandar_interno(0x23C, 0, ff23c(ou, 1, d))
        anotar("   FF23B %s rechaza/cancela con %s (tipo %d)" % ((con.cuenta or {}).get("nick"), nick, tipo))
    else:
        anotar("   FF23B tipo %d sin manejar: %s" % (tipo, cuerpo.hex(" ")))
    return True


def susurro(con, seq, cuerpo):
    """FF40 0x04 [u32 usn][u16 L][msg] (a un amigo) o 0x0D [L][apodo][L][msg] (por apodo). Al destino: FF09
    [L][apodo<=13][L][msg] (el susurro gris); al que lo manda: FF40 0x05 [05][1][usn][u16 L][msg][color] o 0x0f
    [0f][0][L][apodo][L][msg][color]. Sin conectar: 0x05 estado 3 / 0x0f estado 2 (不在线)."""
    yo_nick = (con.cuenta or {}).get("nick", "")
    if cuerpo[0] == 0x04 and len(cuerpo) >= 7:
        usn, L = struct.unpack_from("<IH", cuerpo, 1)
        msg = cuerpo[7:7 + L]
        otro = _conectado(usn)
        if otro is None:
            con.mandar_interno(0x40, seq, bytes([0x05, 3]) + struct.pack("<I", usn))
        else:
            n = _gbk(yo_nick, 13)
            otro.mandar_interno(0x09, 0, bytes([len(n)]) + n + bytes([len(msg)]) + msg)
            con.mandar_interno(0x40, seq, bytes([0x05, 1]) + struct.pack("<IH", usn, len(msg)) + msg + b"\0")
    elif cuerpo[0] == 0x0D and len(cuerpo) >= 3:
        L = cuerpo[1]
        nick = cuerpo[2:2 + L]
        L2 = cuerpo[2 + L]
        msg = cuerpo[3 + L:3 + L + L2]
        c = _por_nick(textos.decodificar(nick))
        otro = _conectado(c["usn"]) if c else None
        if otro is None:
            con.mandar_interno(0x40, seq, bytes([0x0f, 2, len(nick)]) + nick + bytes([len(msg)]) + msg + b"\0")
        else:
            n = _gbk(yo_nick, 13)
            otro.mandar_interno(0x09, 0, bytes([len(n)]) + n + bytes([len(msg)]) + msg)
            con.mandar_interno(0x40, seq, bytes([0x0f, 0, len(nick)]) + nick + bytes([len(msg)]) + msg + b"\0")
    else:
        return False
    anotar("   susurro de %s (FF40 0x%02x)" % (yo_nick, cuerpo[0]))
    return True


def invitar(con, seq, cuerpo):
    """C2S FF52 (vacio, boton 邀请 de la sala): al que invita [00] (texto 0xa7); a los del lobby (sin sala)
    [01][u16 A][u8 0][u8 0] (cartel 0xa6/0x267; A = numero de sala & 0x7FF | tipo << 11, como el 2013 [H]). El OK entra
    por el camino de unirse de siempre."""
    if cuerpo:
        return False
    sala = estado.SALAS.get(con.sala)
    if sala is None:
        return False
    con.mandar_interno(0x52, seq, b"\x00")
    a = sala.numero & 0x7FF
    n = 0
    for c in estado.CONEXIONES.values():
        if c is not con and c.sala is None and c.cuenta:
            c.mandar_interno(0x52, 0, b"\x01" + struct.pack("<H", a) + b"\x00\x00")
            n += 1
    anotar("   FF52 %s invita a la sala %d: a %d del lobby" % ((con.cuenta or {}).get("nick"), sala.numero, n))
    return True


def lista_amigos(con, seq, cuerpo):
    """C2S FF215 (vacio, al abrir la mensajeria: el sobre del lobby) -> S2C FF215 [u32 n][n x 97 B] (mismo layout que
    FF216, segun el subagente) con los amigos, cada uno con su en-linea al dia."""
    if cuerpo:
        return False
    me = _de(_amigos(), (con.cuenta or {}).get("usn"))
    regs = [registro97(2, u) for u in me["amigos"]]
    con.mandar_interno(0x215, seq, struct.pack("<I", len(regs)) + b"".join(regs))
    return True


# ====================================================================================================================
# MEGAFONO (M10, 22-nov). Lo MEDIDO: el C2S es FF40 sub 0x0B `SendMegaphoneMessage` [0B][u32 item][u8 L][texto] (docs/tablero/layouts/
# FF40.md, emisor 0x02775fb0: campos [u8][u32][u8][bytes]; NO es el sub 0x19, que en la tabla del emisor es el chat chico). Los
# megafonos del Steam son los `type` de notice.xml (rnr_script.pak, copia en _fuera_git/m07/steam): itemcode 1 y 2 (noticedtype S,
# chico y grande) y 200 / 11000146 (noticedtype D, "agregar amigo"; el 11000146 es el 婚礼喇叭 de wdshop). El cliente ya comprueba solo
# que tenga el objeto (string.csv: "no hay altavoz adecuado, comprelo") y el servidor cobra 1 unidad de ese item: sin item, no se manda.
# ⛔ SIN MEDIR: la forma del S2C que dibuja el cartel en el cliente moderno. Abajo va la del 2013 (S2C FF40 [12][u32 item][u8 L][quien]
# [u8 L][texto], lobby_social.py `_s2c_cartel_megafono`): en el exe moderno el lector del FF40 no se pudo atar a un sub 0x12 con
# seguridad (layouts/FF40.md no rotula los subs del S2C salvo los de pareja/amigos). Por eso hay DOS llaves:
#   MEGAFONO_TODOS  (omision "1")  prende toda la logica de abajo;
#   MEGAFONO_CARTEL (omision "0")  autoriza mandar ESE S2C 2013 (HIPOTESIS) a todos; con "0" el megafono se atiende como hoy
#                                  (nada se cobra ni se manda) hasta que se mida el cartel con dos copias del juego.
# Sin cuenta local (sesion capturada) tampoco se atiende.
LLAVES_M10 = {"MEGAFONO_TODOS": "1", "MEGAFONO_CARTEL": "0"}
MEGAFONOS = (1, 2, 200, 11000146)       # itemcode de notice.xml del Steam (S: 1, 2; D: 200, 11000146). 88/89/104/112: sin medir, no se aceptan
MEGAFONO_TEXTO_MAX = 120                # MEGAFONO_LARGO_MAX del 2013 (HIPOTESIS para el Steam: el limite del cliente no se midio)
MEGAFONO_APODO_MAX = 13                 # igual que _apodo: el buffer del cliente lee apodos de menos de 14 B


def llave_m10(nombre):
    """Llave de M10, leida en el momento (por omision LLAVES_M10)."""
    return os.environ.get(nombre, LLAVES_M10[nombre]) == "1"


def cartel_megafono(item, nick_gbk, texto):
    """S2C FF40 [0D][u32 item][u8 L1][quien (L1 <= 13)][u8 L2][texto][u8 extra=0]. LEIDO en el exe moderno (M10b, 22-nov,
    un testigo: lectura estatica): sub 0x0D @ 0x027a089f es el cartel del megafono; `extra` 0 -> arg4 0 de 0x00980e40.
    ⚠ L1 >= 14 hace __report_rangecheckfailure en el cliente (0x027a08d9): el apodo se corta a 13 B aca tambien."""
    nick_gbk = nick_gbk[:13]
    texto = texto[:255]
    return (bytes([0x0D]) + struct.pack("<I", item) + bytes([len(nick_gbk)]) + nick_gbk + bytes([len(texto)]) + texto
            + bytes([0]))


def acuse_megafono(item, ok=True):
    """S2C FF40 [0C][u8 res][u32 item] al que lo mando (M10b: res 1 = 'mensaje enviado' y el cliente descuenta 1 carga
    del item en SU mochila, 0x00473e50; res 2 = 'usa un lenguaje respetuoso')."""
    return bytes([0x0C, 1 if ok else 2]) + struct.pack("<I", item)


def megafono(con, seq, cuerpo):
    """C2S FF40 0x0B: con el item (se cobra 1) el cartel le llega a TODOS los conectados (estado.CONEXIONES, el que lo mando tambien).
    Sin item, o con un item que no es megafono, no se cobra ni se manda nada. False = no se atiende (llaves apagadas o sin cuenta)."""
    if not (llave_m10("MEGAFONO_TODOS") and llave_m10("MEGAFONO_CARTEL")):
        return False
    yo = (con.cuenta or {}).get("usn")
    if yo is None:
        return False
    nick = (con.cuenta or {}).get("nick") or _nick(yo)
    item = struct.unpack_from("<I", cuerpo, 1)[0]
    L = cuerpo[5]
    texto = cuerpo[6:6 + L]
    if len(texto) < L or not texto.strip(b"\x00 "):
        anotar("   MEGAFONO: %s mando un texto cortado o vacio (%d B): no se cobra ni se manda" % (nick, len(texto)))
        return True
    if item not in MEGAFONOS:
        anotar("   MEGAFONO: %s pidio el item %d, que no es un megafono medido: no se cobra ni se manda" % (nick, item))
        return True
    import tienda
    quedan = tienda.gastar_objeto(yo, item)                         # gastar y comprobar en UN solo candado: el resultado es el permiso
    if quedan is None:
        anotar("   MEGAFONO: %s no tiene el item %d: no se manda" % (nick, item))
        return True
    paquete = cartel_megafono(item, _gbk(nick, MEGAFONO_APODO_MAX), texto[:MEGAFONO_TEXTO_MAX])
    n = 0
    for c in list(estado.CONEXIONES.values()):
        try:
            c.mandar_interno(0x40, 0, paquete)
            n += 1
        except Exception as e:                                       # noqa: BLE001
            anotar("   ⛔ megafono: una conexion no recibio el cartel: %r" % e)
    try:
        con.mandar_interno(0x40, seq, acuse_megafono(item))
    except Exception as e:                                           # noqa: BLE001
        anotar("   ⛔ megafono: sin acuse al que lo mando: %r" % e)
    anotar("   MEGAFONO de %s (item %d, le quedan %d) -> %d conexion(es)" % (nick, item, quedan, n))
    return True


MANEJADORES = {
    0x45: fecha,
    0x4A: pareja,
    0x40: tunel,
    0x214: mensajeria,
    0x77: examinar,
    0x215: lista_amigos,
    0x23B: amistad,
    0x52: invitar,
}
