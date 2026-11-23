# -*- coding: utf-8 -*-
r"""gm.py (M15, 22-nov) — comandos minimos de GM por chat para moderar el alpha.

Quien es GM: variable de entorno `GM_USUARIOS` (lista separada por comas de claves `e<sub>` de la Cuenta Eñeños o
apodos). Sin la variable (o vacia), nadie es GM. Llave `GM_COMANDOS` (entorno, leida en el momento, por omision "1"):
con "0" todo queda exactamente como antes (ni comandos ni silencios).

Comandos (solo si el que escribe es GM; el texto del comando nunca se difunde como chat):
  .anuncio <texto>               linea de chat S2C FF1F4 tipo 1 (161 B, forma medida en FF1F4.md y charla.registro161)
                                 con remitente "GM" a todos los conectados (estado.CONEXIONES).
  .expulsar <apodo>              cierra la conexion de ese jugador (tr.close(), como juego.py con sesion duplicada).
  .silenciar <apodo> <minutos>   bloquea el chat de ese jugador (sala y charla) hasta `reloj() + minutos * 60`;
                                 se guarda en cuenta.json (seccion "gm", via cuenta.py) para que siga tras reconectar.
  .desilenciar <apodo>           levanta el silencio guardado en cuenta.json.

Cada accion de GM se anota en el registro (estado.anotar): quien, que y a quien.
"""
import math
import os
import time

import cuenta
import estado
import salas
import textos

REMITENTE_GM = "GM"
COMANDOS = ("anuncio", "expulsar", "silenciar", "desilenciar", "cupon_nuevo")
MINUTOS_MAX = 525600.0            # 1 anio: cota razonable contra numeros absurdos

# Reloj del modulo (las pruebas lo reemplazan para vencer silencios sin esperar).
reloj = time.time


def anotar(txt):
    estado.anotar(txt)


def activo():
    """Llave GM_COMANDOS (entorno, leida en el momento, por omision '1')."""
    return os.environ.get("GM_COMANDOS", "1").strip().lower() not in ("0", "no", "false", "")


def usuarios():
    """Conjunto de claves (`e<sub>`) o apodos autorizados por GM_USUARIOS. Vacio si falta la variable."""
    crudo = os.environ.get("GM_USUARIOS", "")
    return {x.strip() for x in crudo.split(",") if x.strip()}


def _nick_de(con):
    cta = getattr(con, "cuenta", None) or {}
    pj = cta.get("personaje") or {}
    return str(pj.get("nick") or cta.get("nick") or "").strip()


def _quien_de(con):
    cta = getattr(con, "cuenta", None) or {}
    nick = _nick_de(con) or "?"
    sid = str(cta.get("steamid") or "").strip()
    usn = cta.get("usn")
    partes = [p for p in (sid, ("usn %s" % usn) if usn else "") if p]
    return "%s (%s)" % (nick, ", ".join(partes)) if partes else nick


def es_gm(con):
    """True si GM_COMANDOS esta activa y la cuenta Eñeños de la conexion (`e<sub>`) figura en GM_USUARIOS."""
    if not activo():
        return False
    lista = usuarios()
    if not lista:
        return False
    cta = getattr(con, "cuenta", None) or {}
    if not cta:
        return False
    # SOLO por la cuenta Eñeños (`e<sub>` del pase firmado): un apodo cambia y se puede reusar, no sirve para dar permisos
    sid = str(cta.get("steamid") or "").strip()
    return bool(sid) and sid in lista


def cuerpo_anuncio(texto, remitente=REMITENTE_GM):
    """S2C FF1F4 tipo 1 de 161 B (forma medida en docs/tablero/layouts/FF1F4.md y charla.registro161; 127/127 en el oficial)."""
    txt_b = textos.codificar(str(texto or ""), 128)
    nick_b = textos.codificar(str(remitente or REMITENTE_GM), 12)
    return (bytes(8) + bytes([1, 0]) + txt_b.ljust(129, b"\0") + bytes(4)
            + nick_b.ljust(13, b"\0") + b"\0" + bytes(4))


def _avisar_uno(con, texto):
    if con is None or getattr(con, "cerrada", False):
        return False
    try:
        con.mandar_interno(0x1F4, 0, cuerpo_anuncio(texto))
        return True
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ GM aviso a uno: %r" % e)
        return False


def _silencio_hasta(usn):
    if not usn or not os.path.exists(cuenta.ruta()):
        return 0.0
    try:
        sec = cuenta.leer_seccion(usn, "gm") or {}
        return float(sec.get("silencio_hasta") or 0.0)
    except (cuenta.CuentaError, ValueError, TypeError) as e:
        anotar("   ⛔ GM silencio usn %s: %s" % (usn, e))
        return 0.0


def esta_silenciado(con):
    """True si GM_COMANDOS esta activa y la cuenta de `con` tiene un silencio vigente en cuenta.json."""
    if not activo():
        return False
    usn = (getattr(con, "cuenta", None) or {}).get("usn")
    if not usn:
        return False
    return _silencio_hasta(usn) > float(reloj())


def _conexiones_por_apodo(apodo):
    objetivo = str(apodo or "").strip()
    if not objetivo:
        return []
    return [(k, c) for k, c in list(estado.CONEXIONES.items()) if _nick_de(c) == objetivo]


def _usn_por_apodo(apodo):
    objetivo = str(apodo or "").strip()
    if not objetivo:
        return None
    for _k, c in _conexiones_por_apodo(objetivo):
        u = (getattr(c, "cuenta", None) or {}).get("usn")
        if u:
            return int(u)
    if os.path.exists(cuenta.ruta()):
        try:
            for k, acc in cuenta.todas().items():
                pj = acc.get("personaje") or {}
                cta = acc.get("cuenta") or {}
                if pj.get("nick") == objetivo or cta.get("nick") == objetivo:
                    return int(cta.get("usn") or k)
        except (cuenta.CuentaError, ValueError, TypeError) as e:
            anotar("   ⛔ GM buscar apodo %r: %s" % (objetivo, e))
    return None


def _cmd_anuncio(con, quien, resto):
    if not resto:
        anotar("   GM %s | .anuncio | sin texto" % quien)
        _avisar_uno(con, "uso: .anuncio <texto>")
        return True
    paquete = cuerpo_anuncio(resto)
    enviados = 0
    for c in list(estado.CONEXIONES.values()):
        if getattr(c, "cerrada", False):
            continue
        try:
            c.mandar_interno(0x1F4, 0, paquete)
            enviados += 1
        except Exception as e:                                           # noqa: BLE001
            anotar("   ⛔ GM anuncio: no se pudo enviar a una conexion: %r" % e)
    anotar("   GM %s | .anuncio | a todos (%d conexion/es): %r" % (quien, enviados, resto))
    return True


def _cmd_expulsar(con, quien, args):
    if not args:
        anotar("   GM %s | .expulsar | sin apodo" % quien)
        _avisar_uno(con, "uso: .expulsar <apodo>")
        return True
    apodo = args[0]
    encontrados = _conexiones_por_apodo(apodo)
    if not encontrados:
        anotar("   GM %s | .expulsar | a %s -> no conectado" % (quien, apodo))
        _avisar_uno(con, "expulsar: %s no esta conectado" % apodo)
        return True
    for k_con, obj in encontrados:
        estado.CONEXIONES.pop(k_con, None)
        if getattr(obj, "sala", None) is not None:
            try:
                salas.sacar_de_su_sala(obj)
            except Exception as e:                                       # noqa: BLE001
                anotar("   ⛔ GM expulsar sacar_de_su_sala %s: %r" % (apodo, e))
        obj.cerrada = True
        tr = getattr(obj, "tr", None)
        if tr is not None:
            try:
                tr.close()
            except Exception as e:                                       # noqa: BLE001
                anotar("   ⛔ GM expulsar tr.close %s: %r" % (apodo, e))
    anotar("   GM %s | .expulsar | a %s -> %d conexion(es) cerrada(s)" % (quien, apodo, len(encontrados)))
    if not getattr(con, "cerrada", False):
        _avisar_uno(con, "expulsado: %s" % apodo)
    return True


def _cmd_silenciar(con, quien, args):
    if len(args) < 2:
        anotar("   GM %s | .silenciar | argumentos incompletos" % quien)
        _avisar_uno(con, "uso: .silenciar <apodo> <minutos>")
        return True
    apodo = args[0]
    try:
        minutos = float(args[1].replace(",", "."))
    except ValueError:
        minutos = -1.0
    if not math.isfinite(minutos) or not (0.0 < minutos <= MINUTOS_MAX):
        anotar("   GM %s | .silenciar | a %s: minutos invalidos (%r)" % (quien, apodo, args[1]))
        _avisar_uno(con, "uso: .silenciar <apodo> <minutos> (minutos > 0)")
        return True
    usn = _usn_por_apodo(apodo)
    if usn is None:
        anotar("   GM %s | .silenciar | a %s -> no encontrado" % (quien, apodo))
        _avisar_uno(con, "silenciar: %s no existe" % apodo)
        return True
    hasta = float(reloj()) + minutos * 60.0

    def guardar(sec):
        sec["silencio_hasta"] = hasta
        sec["silencio_por"] = quien
        return hasta

    try:
        cuenta.cambiar_seccion(usn, "gm", guardar)
    except cuenta.CuentaError as e:
        anotar("   ⛔ GM %s | .silenciar | a %s (usn %d): %s" % (quien, apodo, usn, e))
        _avisar_uno(con, "silenciar: error al guardar en la cuenta")
        return True
    anotar("   GM %s | .silenciar | a %s (usn %d) por %g min (hasta %.0f)" % (quien, apodo, usn, minutos, hasta))
    _avisar_uno(con, "silenciado: %s (%g min)" % (apodo, minutos))
    return True


def _cmd_desilenciar(con, quien, args):
    if not args:
        anotar("   GM %s | .desilenciar | sin apodo" % quien)
        _avisar_uno(con, "uso: .desilenciar <apodo>")
        return True
    apodo = args[0]
    usn = _usn_por_apodo(apodo)
    if usn is None:
        anotar("   GM %s | .desilenciar | a %s -> no encontrado" % (quien, apodo))
        _avisar_uno(con, "desilenciar: %s no existe" % apodo)
        return True

    def quitar(sec):
        tenia = "silencio_hasta" in sec
        sec.pop("silencio_hasta", None)
        sec.pop("silencio_por", None)
        return tenia

    try:
        tenia = cuenta.cambiar_seccion(usn, "gm", quitar)
    except cuenta.CuentaError as e:
        anotar("   ⛔ GM %s | .desilenciar | a %s (usn %d): %s" % (quien, apodo, usn, e))
        _avisar_uno(con, "desilenciar: error al guardar en la cuenta")
        return True
    anotar("   GM %s | .desilenciar | a %s (usn %d)%s" % (quien, apodo, usn, "" if tenia else " (no estaba silenciado)"))
    _avisar_uno(con, "desilenciado: %s" % apodo)
    return True


def _cmd_cupon_nuevo(con, quien, args):
    import cupon
    if len(args) < 2:
        anotar("   GM %s | .cupon_nuevo | argumentos incompletos" % quien)
        _avisar_uno(con, "uso: .cupon_nuevo <codigo> <g> [usos]")
        return True
    codigo = args[0]
    try:
        g = int(args[1])
        usos = int(args[2]) if len(args) >= 3 else 0
    except ValueError:
        anotar("   GM %s | .cupon_nuevo | numeros invalidos (%r)" % (quien, args[1:]))
        _avisar_uno(con, "uso: .cupon_nuevo <codigo> <g> [usos]")
        return True
    if g <= 0 or usos < 0:
        anotar("   GM %s | .cupon_nuevo | fuera de rango g=%d usos=%d" % (quien, g, usos))
        _avisar_uno(con, "uso: .cupon_nuevo <codigo> <g> [usos] (g > 0, usos >= 0)")
        return True
    try:
        k, _regla = cupon.crear(codigo, g=g, usos_max=usos)
    except ValueError as e:
        anotar("   GM %s | .cupon_nuevo | %r -> %s" % (quien, codigo, e))
        _avisar_uno(con, "cupon_nuevo: %s" % e)
        return True
    anotar("   GM %s | .cupon_nuevo | %s (+%d G, usos_max=%d)" % (quien, k, g, usos))
    _avisar_uno(con, "cupon creado: %s (+%d G, usos %s)" % (k, g, usos if usos else "sin tope"))
    return True


def atender(con, texto):
    """Enganche unico para el camino del chat (FF1F4 y FF08). Devuelve True si se atendio como comando de GM o se
    bloqueo por silencio (el llamador no sigue ni difunde); False si sigue como chat normal."""
    if not activo():
        return False
    if isinstance(texto, (bytes, bytearray)):
        txt = textos.decodificar(bytes(texto)).strip()
    else:
        txt = str(texto or "").strip()
    if txt.startswith(".") and es_gm(con):
        partes = txt[1:].split()
        cmd = partes[0].lower() if partes else ""
        if cmd in COMANDOS:
            quien = _quien_de(con)
            if cmd == "anuncio":
                trozos = txt.split(None, 1)
                return _cmd_anuncio(con, quien, trozos[1].strip() if len(trozos) > 1 else "")
            if cmd == "expulsar":
                return _cmd_expulsar(con, quien, partes[1:])
            if cmd == "silenciar":
                return _cmd_silenciar(con, quien, partes[1:])
            if cmd == "desilenciar":
                return _cmd_desilenciar(con, quien, partes[1:])
            if cmd == "cupon_nuevo":
                import cupon
                if not cupon.activo():
                    return False
                return _cmd_cupon_nuevo(con, quien, partes[1:])
    if esta_silenciado(con):
        anotar("   GM silencio: chat bloqueado de %s" % _quien_de(con))
        return True
    return False
