# -*- coding: utf-8 -*-
r"""login.py (21-oct) — paso 2 del servidor LOCAL: contestar el login del cliente de Steam en el 28004.

Ver docs/SERVIDOR_LOCAL_STEAM.md. Lo que el cliente espera sale de LEER el exe, no de inventarlo:

  despachador del 28004: 0x02755284 — cabecera de 8 bytes `[0xFF][cmd:u8][seq:u16][largo:u32]`,
      cmd <= 0x19, manejador = [obj + cmd*8 + 0x14248c] (registro en 0x0274d51e)
  cmd 0x01 = CLoginServerClient::CmdAccountLogin (0x027502c0), que lee con 0x02c153b0 (copia N bytes):
      u32 resultado      1000 = OK; 1001 BUSY, 1002 DBERROR, 1003 FAIL, 1004 FAIL_IDNOTMATCH,
                         1005 (lee un u32 y muestra el texto 0xb7c), 1006 ERROR, 1007 NEED_OTP, ...
      -- si es 1000 (0x02750844) --
      u32 ?              a [ebp-0x704]
      u32 largo + bytes  la CUENTA (hasta 100): se compara, sin distinguir mayusculas, con
                         [config+0x28c] = el SteamID que mando el cliente; si no coincide, texto 0xb75
      u32 largo + bytes  a [ebp-0x57c] (hasta 0x400)
      u32 ?              a [ebp-0x700]
      -- y en 0x0275097a salta a 0x0f2b7efd, la pieza repatriada (22-oct). Sus tramos 1, 2 y 3 siguen
         leyendo del MISMO paquete (`prog:0x028153b0`): 4, 8 y 4 bytes mas. Sin ellos el juego anota
         "[ERROR] ParsePacket() ReadGuard Error Type 1 Read 4640, Body 42".

  cmd 0x02 = CLoginServerClient::CmdLogin (0x02753a60), legible. Lee, en orden:
      u8  estado         -> [ebp-0x231], con el lector EN LINEA (0x02753c46, no una llamada: por eso
                            no aparece en el barrido de `call 0x2c153b0`). Se compara con 3,1,2,5,6,7,
                            8,0xa,0xb y cada uno levanta su cartel; en 0x02754128 `test al,al / je
                            0x27541b4`: SOLO con 0 sigue leyendo el resto.
      -- si estado == 0 (0x027541b4) --
      u32 resultado      -> [ebp-0x23c]
      u8                 -> [ebp-0x231]
      u16                -> [ebp-0x234]
      u8  codigo/largo   -> [ebp-0x231]; si != 0, lee esos bytes de texto (< 13) -> [ebp-0x1d0]
      u8  largo          -> [ebp-0x230]; lee esos bytes (< 33) -> [ebp-0xbc]
      u32                -> [ebp-0x234]
      u16                -> [ebp-0x234]
    Si todo sale bien el cliente llama a `CLoginServerClient::SendServerList` (0x0274fc50) en
    0x02754400, que manda el FF03 (sin cuerpo) pidiendo la lista de canales.

El FF01 que manda el cliente: `[02][largo:u8][SteamID ascii][largo:u32][ticket de Steam en hex]`. El
ticket es una credencial: NO se guarda ni se imprime; del cuerpo solo se anota el largo.

Uso:  python login.py            (escucha en 127.0.0.1 y 192.168.31.100, puerto 28004)
"""
import asyncio
import hmac
import os
import re
import secrets
import struct
import time

import ajustes
import cuentas
import pase
import textos

# 22-oct: solo 28004 por omision. El 28008 es de juego.py; con los dos aca, el login agarraba el 28008
# y juego.py no podia arrancar ("solo se permite un uso de cada direccion de socket").
PUERTOS = list(ajustes.PUERTOS_LOGIN)
HOSTS = ajustes.HOSTS
# 22-oct: servidor_local/ (ver LEEME.md): los datos salen de datos/ (herramientas/preparar_datos.py) y
# lo que se anota va a registros/.
BASE = ajustes.BASE
DATOS = ajustes.DATOS
DIR = ajustes.REGISTROS
os.makedirs(DIR, exist_ok=True)
SALIDA = open(os.path.join(DIR, time.strftime("login_%Y%m%d_%H%M%S.txt")), "w", encoding="utf-8")
T0 = time.time()


def anotar(txt):
    ln = "[%7.2f s] %s" % (time.time() - T0, txt)
    print(ln, flush=True)
    SALIDA.write(ln + "\n")
    SALIDA.flush()


def marco(cmd, seq, cuerpo):
    return struct.pack("<BBHI", 0xFF, cmd, seq, len(cuerpo)) + cuerpo


def lstr(b):
    return struct.pack("<I", len(b)) + b


def marcos(buf):
    out = []
    while len(buf) >= 8 and buf[0] == 0xFF:
        cmd, seq, largo = buf[1], struct.unpack_from("<H", buf, 2)[0], struct.unpack_from("<I", buf, 4)[0]
        if len(buf) < 8 + largo:
            break
        out.append((cmd, seq, buf[8:8 + largo]))
        buf = buf[8 + largo:]
    return out, buf


RUTA_CAPTURA = ajustes.RUTA_LOGIN_CAP      # copia de tools/net/volcado_28004_S2C.bin
_CAP = {}


def cuerpo_capturado(cmd):
    r"""El cuerpo CRUDO que el servidor oficial mando para ese comando, de la captura del 22-oct.

    ⭐ 22-oct: las versiones "fieles" que teniamos de FF01 y FF02 estaban RECONSTRUIDAS campo por
    campo (con una cola de 68 bytes copiada a mano), no eran los bytes de la captura. Donde
    reconstruimos, rompimos; donde copiamos tal cual, el cliente avanzo. Asi que ahora se mandan los
    bytes como vinieron. La captura tiene los cuatro: FF01 139 B, FF0B 168 B, FF02 48 B, FF03 166 B.

    ⚠ El FF01 trae la cuenta y una ficha de sesion del usuario: la captura queda FUERA de git y esto
    solo se usa localmente, con su propia cuenta.
    """
    if not _CAP:
        if not os.path.exists(RUTA_CAPTURA):
            return None
        b = open(RUTA_CAPTURA, "rb").read()
        off = 0
        while off + 8 <= len(b) and b[off] == 0xFF:
            largo = struct.unpack_from("<I", b, off + 4)[0]
            if off + 8 + largo > len(b):
                break
            _CAP[b[off + 1]] = b[off + 8:off + 8 + largo]
            off += 8 + largo
    return _CAP.get(cmd)


def respuesta_login(cuerpo, gsn=None):
    """CmdAccountLogin (cmd 0x01). ⭐⭐ 22-oct: el formato y los valores salen de una CAPTURA del
    servidor oficial chino con NUESTRO cliente de Steam (proxy_mitm.py VOLCAR=1, con permiso del
    usuario). Su FF01 son 139 bytes:
        u32 1000 (resultado) | u32 usn | u32+cuenta | u32+"VALOFE|R2BEAT|<cuenta>|<usn>" | 68 bytes
    Los 68 del final son 17 numeros (el primero, una marca de tiempo). Se copian de la captura: son
    los que la pieza 0x0f2b7efd sigue leyendo despues de la clave.
    """
    # ⚠ 22-oct: la version FIEL (139 B, la de la captura) hace que el cliente mande su FF02 completo
    # de 108 B —correcto— pero despues CORTA la conexion sin pedir la lista de canales (su CmdLogin
    # ni llega a la cola). Con la version simple (58 B, clave "local") el cliente SI pide la lista y
    # llega a conectarse al 28008. Hasta entender por que, la simple es la de produccion.
    simple = not ajustes.FF01_FIEL
    if len(cuerpo) < 2 or cuerpo[0] != 0x02:
        raise ValueError("FF01 con otra forma (primer byte 0x%02x)" % (cuerpo[0] if cuerpo else -1))
    steamid = cuerpo[2:2 + cuerpo[1]]
    # ⭐ por omision, los BYTES DE LA CAPTURA tal cual (ver `cuerpo_capturado`). FF01_ARMADO=1 vuelve
    # a las versiones que armabamos a mano. Si la cuenta de la captura no es la que pide el cliente,
    # se avisa y se usa la armada: los bytes de otra cuenta no servirian.
    if not ajustes.FF01_ARMADO:
        cap = cuerpo_capturado(0x01)
        if cap is not None:
            if steamid in cap:
                return cap, steamid
            anotar("   ⚠ el FF01 de la captura es de OTRA cuenta: uso el armado a mano")
    usn = int(ajustes.USN if ajustes.USN is not None else (cuentas.GSN_CAPTURADA or 1))
    clave = b"VALOFE|R2BEAT|" + steamid + b"|" + str(usn).encode()
    cap_local = cuerpo_capturado(0x01)
    # Con captura: mismos bytes locales. Sin captura: INVENTADO 68 ceros;
    # el login normal sin captura usa la rama simple de abajo, no esta cola.
    cola = cap_local[-68:] if cap_local is not None and len(cap_local) >= 68 else bytes(68)
    if simple:
        # 29-oct: para una cuenta LOCAL (cuentas.py) este u32 es su gsn: el cliente lo devuelve en cada FF02 / FF0C
        usn = gsn if gsn is not None else int(ajustes.USN if ajustes.USN is not None else "1")
        clave = ajustes.CLAVE_LOGIN.encode()
        return (struct.pack("<I", 1000) + struct.pack("<I", usn)
                + struct.pack("<I", len(steamid)) + steamid
                + struct.pack("<I", len(clave)) + clave
                + struct.pack("<I", 0)
                + struct.pack("<I", 0) + struct.pack("<Q", 0) + struct.pack("<I", 0)), steamid
    return (struct.pack("<I", 1000) + struct.pack("<I", usn)
            + struct.pack("<I", len(steamid)) + steamid
            + struct.pack("<I", len(clave)) + clave
            + cola), steamid

def respuesta_cmdlogin():
    """CmdLogin (cmd 0x02): los bytes de la CAPTURA; FF02_ARMADO=1 usa el que armabamos a mano.

    El armado a mano mide lo mismo (48 B) pero lleva una ficha de 32 caracteres inventada por
    nosotros y la sesion por variable de entorno; el de la captura trae los valores reales.
    """
    if not ajustes.FF02_ARMADO:
        cap = cuerpo_capturado(0x02)
        if cap is not None:
            return cap
    return _cmdlogin_armado()


def _cmdlogin_armado():
    """CmdLogin (cmd 0x02): todo en cero = sin cartel de error y sin textos. 16 bytes."""
    # ⭐ 22-oct: en la captura del oficial este u32 es 0x0dato local de captura y el cliente lo DEVUELVE en su
    # siguiente FF02. Con 0 el juego se desconecta solo: "与服务器断开 (30001)".
    return (struct.pack("<B", 0)        # estado: 0 = OK (va PRIMERO, lector en linea)
            + struct.pack("<I", ajustes.SESION)
            + struct.pack("<B", 0)      # [ebp-0x231]
            + struct.pack("<H", 0)      # [ebp-0x234]
            + struct.pack("<B", 0)      # codigo/largo: 0 = sin texto y sin cartel
            # el FF02 del oficial trae aca un testigo de 32 caracteres (hex): se imita
            + struct.pack("<B", 32) + b"a0cf6d4e399f033a21dd27cc2bf7678b"
            + struct.pack("<I", 0)      # [ebp-0x234]
            + struct.pack("<H", 0))     # [ebp-0x234]


def lista_capturada():
    r"""⭐ 22-oct: la lista de canales REAL, de la captura, con la IP cambiada por la nuestra.

    POR QUE. La lista que armabamos a mano medía 36 bytes y la del oficial 166, con TRES canales y
    los campos en otro orden y otros tamanios. Medido sobre `tools/net/volcado_28004_S2C.bin`:

        u8  cantidad (3)
        por canal:  u32 ?  |  u16 puerto (0x6d68=28008, 0x6d69=28009, 0x6d6a=28010)
                    u8 largo + IP  |  u16 ?  |  u8 8  |  u8 7  |  u8 ?  |  u8 largo + nombre
        al final:   u8 largo + URL del torneo  |  u16 0

    Los nombres son UTF-8 ("linea 1", "sala de chat 1", "competencia"). Solo se reemplazan las tres
    apariciones de la IP; los puertos, los nombres y todo lo demas quedan tal cual, porque de esos
    campos no sabemos el significado y una suposicion nuestra es justamente lo que rompia.
    ⚠ La IP nuestra puede medir distinto que la del oficial (14 vs 13), asi que se reescribe tambien
    el byte de largo de cada una. Devuelve None si no esta la captura.
    """
    ruta = RUTA_CAPTURA
    if not os.path.exists(ruta):
        return None
    b = open(ruta, "rb").read()
    cuerpo, off = None, 0
    while off + 8 <= len(b) and b[off] == 0xFF:
        largo = struct.unpack_from("<I", b, off + 4)[0]
        if off + 8 + largo > len(b):
            break
        if b[off + 1] == 0x03:
            cuerpo = b[off + 8:off + 8 + largo]
        off += 8 + largo
    if cuerpo is None:
        return None
    nueva = ajustes.IP_JUEGO.encode()
    out, i = bytearray(), 0
    while i < len(cuerpo):
        m = re.compile(rb"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}").search(cuerpo, i)
        if not m or i > m.start():
            out += cuerpo[i:]
            break
        out += cuerpo[i:m.start() - 1]        # todo hasta el byte de largo de la IP
        out += bytes([len(nueva)]) + nueva    # el largo nuevo y la IP nueva
        i = m.end()
    res = bytes(out)
    return sin_canal_baile(res) if ajustes.SIN_CANAL_BAILE else res


def sin_canal_baile(cuerpo):
    """Saca del FF03 el canal con bandera 0x28 (tipo 0x0d = Modo Baile, ficha 175).

    Con ese canal anunciado, cMultiplay::CmdClub (0x008c2891) intenta cambiar de servidor por
    sub_8bf390 y el cliente nunca manda nada (el socket de login sigue abierto). Sin el canal
    0x28, abre la ventana de Modo Baile directo en el canal principal.
    """
    if not cuerpo:
        return cuerpo
    n = cuerpo[0]
    pos = 1
    quedan = []
    for _ in range(n):
        inicio = pos
        if pos + 7 > len(cuerpo):
            return cuerpo
        pos += 6  # id (u32) + puerto (u16)
        iplen = cuerpo[pos]
        pos += 1 + iplen
        if pos + 6 > len(cuerpo):
            return cuerpo
        bandera = cuerpo[pos + 4]
        nlen = cuerpo[pos + 5]
        pos += 6 + nlen
        if pos > len(cuerpo):
            return cuerpo
        if bandera != 0x28:
            quedan.append(cuerpo[inicio:pos])
    if not quedan or len(quedan) == n:
        return cuerpo
    return bytes([len(quedan)]) + b"".join(quedan) + cuerpo[pos:]


def respuesta_lista():
    """CmdLobbyServerList (cmd 0x03, 0x02754510).

    ⭐⭐ 22-oct: el formato salio de una CAPTURA del servidor oficial
    (tools/net/_volcados_viejos_17sep/volcado_28004_S2C.bin, 17-sep), que trae su FF03 entero (35 B):
        01 | 00000000 | 6b6d | 0e "43.248.185.207" | 64 | 00 | e803 | 1e | 04 "Muse" | 00 00 00
    o sea, por canal: u32, u16 PUERTO, u8+IP, u8 (usuarios), u8, u16 (maximo), u8, u8+nombre, y tres
    textos vacios al final. La IP va ANTES de los numeros y el nombre AL FINAL: por eso ninguna de mis
    versiones deducidas del codigo la tomaba y el juego anotaba `--IP()wServerPort_1(0)`.

    El guardia del despachador (0x0275531f) compara los bytes que consume el manejador con el largo
    declarado y anota "ReadGuard Error ... Read %d, Body %d": es el oraculo para ajustar los largos.
    FF03_CUERPO (hex) pisa el cuerpo para iterar sin tocar el codigo.
    """
    h = ajustes.FF03_CUERPO
    if h:
        return bytes.fromhex(h)
    ip = ajustes.IP_JUEGO.encode()
    puerto = ajustes.puerto_juego()
    nombre = ajustes.CANAL.encode()
    url = ajustes.URL_TORNEO.encode()
    return (struct.pack("<B", 1)                        # 1 canal
            + struct.pack("<I", 0)
            + struct.pack("<H", puerto)                 # PUERTO del servidor de juego
            + struct.pack("<B", len(ip)) + ip           # IP del servidor de juego
            + struct.pack("<B", 32)                     # usuarios (0x20 en el oficial)
            + struct.pack("<B", 0)
            + struct.pack("<H", 1800)                   # maximo (0x0708 en el oficial)
            + struct.pack("<B", 30)
            + struct.pack("<B", len(nombre)) + nombre   # nombre del canal
            # los tres textos del final: en el oficial el primero es una URL y los otros dos vacios
            + struct.pack("<B", len(url)) + url + bytes(2))


# ---------- CUENTAS LOCALES (29-oct): crear cuenta y personaje ----------
# ⚠⚠ RECONSTRUIDO, NO COPIADO: el oficial ya no deja registrar cuentas (1002 DBERROR, medido el 29-oct con una cuenta
# nueva, con y sin el grabador), asi que no hay captura de un alta. Todo esto sale de LEER el exe (tabla del login en
# docs/FF_HANDLERS_CHINO.md §5). La cuenta de la captura (su SteamID esta en el FF01 capturado) sigue igual que antes.
#
# El camino de una cuenta SIN personaje, medido en CmdCharacterSelect (0x02755ef0):
#     FF0B  [u8 casillas][u8 ?][u8 cantidad] + cantidad x ([u32 L1][L1 B][u32 L2][L2 B]) + [u32][u32] + [u8]
#           con cantidad 0 el cliente anota "-No Character => <SendGetNewUSN>" (0x027573cc) y manda
#     C2S FF0C  [u32 gsn]                       CLoginServerClient::SendGetNewUSN (0x027576e0)
#     S2C FF0C  [u8 resultado][u32 gsn][u32 usn] CmdGetNewUSN (0x02757990): con 0 guarda el usn y "-Result 0 =>
#           <SendLogin>, proc(Login)": el cliente manda su FF02 con ese usn, como al elegir un personaje.
def ff0b_sin_personajes():
    """La lista de personajes VACIA (12 B). Los dos primeros bytes y el ultimo, como los de la captura (02 02 ... 01):
    02 = casillas (0x027562d9 acepta 2, 4 u 8) y el ultimo va a [cuenta+0xcd8]; los dos u32 en 0 no encienden el
    aviso de [cuenta+0x134c] (0x02757247: solo con 1 y 0)."""
    ruta = ajustes.RUTA_FF0B
    cap = bytes.fromhex(open(ruta).read().strip()) if os.path.exists(ruta) else b"\x02\x02\x00" + bytes(8) + b"\x01"
    return cap[:2] + b"\x00" + struct.pack("<II", 0, 0) + cap[-1:]


# ---------- LA FICHA DE UN PERSONAJE EN EL FF0B (01-nov) ----------
# MEDIDO en el exe: cada personaje del FF0B son dos bloques con largo; el primero lo lee 0x0275c620 -> 0x0275c890 en un
# formato de CAMPOS CON ETIQUETA: un byte de cabecera = (tipo << 4) | campo (0x0274cbd0; si el campo es 0xF, el numero
# sigue en un varint, 0x0274cc40), los numeros en varint de 7 bits. Tipos vistos: 0 numero, 4 texto (varint largo +
# bytes), 5 lista (varint n + n x [00 + varint]), 7 estructura ... 8 fin. Campos de 0x0275c890 (con su nombre en el
# exe): 0 usn, 1 character, 2 arrslot, 3 face, 4 gender, 5 ?, 6 clubexp, 7 lcmissionid, 8 nick, 9 onDressList,
# 10 regdate, 11 isSameCouple, 12 sameCoupleGender, 13 personalItem, 14 ?, 15 exexp, 16 money, 17 removeMark. Los dos
# personajes capturados se leen enteros (77 de 77 y 59 de 59 bytes); el segundo bloque de los dos es `70 80` (una
# estructura vacia, la de 0x0275c6d0: curLevel, bodyType, friendly...).
def _varint(d, i):
    v = c = 0
    while True:
        b = d[i]
        i += 1
        v |= (b & 0x7F) << c
        c += 7
        if not b & 0x80:
            return v, i


def leer_campos(d, i=0):
    """[(campo, tipo, valor)] hasta el fin de estructura. ValueError si aparece un tipo que no se midio."""
    out = []
    while i < len(d):
        h = d[i]
        i += 1
        t, campo = h >> 4, h & 0xF
        if campo == 0xF:
            campo, i = _varint(d, i)
        if t == 8:
            return out, i
        if t == 0:
            v, i = _varint(d, i)
        elif t == 4:
            n, i = _varint(d, i)
            v, i = d[i:i + n], i + n
        elif t == 5:
            n, i = _varint(d, i)
            v = []
            for _ in range(n):
                if d[i] != 0:
                    raise ValueError("lista con elementos de tipo %d" % (d[i] >> 4))
                x, i = _varint(d, i + 1)
                v.append(x)
        elif t == 7:
            v, i = leer_campos(d, i)
        else:
            raise ValueError("tipo %d sin medir" % t)
        out.append((campo, t, v))
    return out, i


def _vi(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def escribir_campos(campos):
    out = bytearray()
    for campo, t, v in campos:
        out += bytes([(t << 4) | campo]) if campo < 0xF else bytes([(t << 4) | 0xF]) + _vi(campo)
        if t == 0:
            out += _vi(v)
        elif t == 4:
            out += _vi(len(v)) + v
        elif t == 5:
            out += _vi(len(v)) + b"".join(b"\x00" + _vi(x) for x in v)
        elif t == 7:
            out += escribir_campos(v) + b"\x80"
    return bytes(out)


def ff0b_con_personaje(cuenta):
    """⚠ RECONSTRUIDO. El FF0B capturado con UN personaje: el de la cuenta local. La ficha es la del primer personaje
    capturado (dato local de captura) con usn, character, arrslot (las partes que eligio al crear, y el resto de las 11 casillas en
    0), nick y regdate (la fecha del alta local) cambiados; el resto (campo 5, lcmissionid, money) queda el de la
    plantilla. Sin `gender`, como en la de dato local de captura (130900): ⚠ para un personaje de mujer (130901) ese campo no se
    midio. None si la captura no se deja leer o no vuelve igual al reescribirla (control de ida y vuelta)."""
    ruta = ajustes.RUTA_FF0B
    if not os.path.exists(ruta):
        return None
    cap = bytes.fromhex(open(ruta).read().strip())
    try:
        l1 = struct.unpack_from("<I", cap, 3)[0]
        b1 = cap[7:7 + l1]
        l2 = struct.unpack_from("<I", cap, 7 + l1)[0]
        b2 = cap[11 + l1:11 + l1 + l2]
        campos, k = leer_campos(b1)
        if k != l1 or escribir_campos(campos) != b1 or len(campos) != 1 or campos[0][1] != 7:
            raise ValueError("la ficha capturada no vuelve igual")
    except (ValueError, IndexError, struct.error) as e:
        anotar("   ⚠ FF0B: %s" % e)
        return None
    pj = cuenta["personaje"]
    fecha = time.strftime("%Y%m%d%H%M%S", time.strptime(cuenta.get("alta", "2026-11-01 00:00:00"), "%Y-%m-%d %H:%M:%S"))
    nuevo = {0: cuentas.usn_de(cuenta), 1: pj["char_id"], 2: (list(pj["partes"]) + [0] * 11)[:11],
             8: textos.codificar(pj["nick"]), 10: fecha.encode()}
    ficha = [(c, t, nuevo.get(c, v)) for c, t, v in campos[0][2]]
    blob = escribir_campos([(0, 7, ficha)])
    # la cola ([u32][u32][u8]): despues de TODOS los personajes capturados
    off = 3
    for _ in range(cap[2]):
        off += 4 + struct.unpack_from("<I", cap, off)[0]
        off += 4 + struct.unpack_from("<I", cap, off)[0]
    cola = cap[off:]
    return cap[:2] + b"\x01" + struct.pack("<I", len(blob)) + blob + struct.pack("<I", len(b2)) + b2 + cola


_PLANTILLA_FF0B_NEUTRA = [
    (0, 0, 0),
    (1, 0, 0x1FF54),
    (2, 5, [0] * 11),
    (5, 0, 0),
    (7, 0, 1),
    (8, 4, b""),
    (10, 4, b"20261101000000"),
    (16, 0, 0),
]


def ff0b_multi(personajes, casillas=cuentas.MAX_PERSONAJES):
    """Ficha 163/164: FF0B con 1..4 personajes. Con `casillas>=4`, el exe carga `slot_character.md9` ('?') en los
    huecos vacios (`0x02722b58`, sin rama por FF0B); con 1 personaje y `casillas` por omision (`MAX_PERSONAJES`),
    usa `casillas=2` para mostrar el boton verde redondo de crear de siempre (`0x027245f0`), y desde 2 personajes usa
    `casillas=4`. Cada personaje local sale sobre la plantilla de ff0b.hex (o la estructura neutra si no hay ff0b.hex);
    el 1.o de la capturada usa sus bytes crudos."""
    if len(personajes) == 1 and int(casillas) == cuentas.MAX_PERSONAJES:
        casillas = 2
    ruta = ajustes.RUTA_FF0B
    if os.path.exists(ruta):
        cap = bytes.fromhex(open(ruta, encoding="ascii").read().strip())
        try:
            l1 = struct.unpack_from("<I", cap, 3)[0]
            b1 = cap[7:7 + l1]
            l2 = struct.unpack_from("<I", cap, 7 + l1)[0]
            b2 = cap[11 + l1:11 + l1 + l2]
            campos, k = leer_campos(b1)
            if k != l1 or escribir_campos(campos) != b1 or len(campos) != 1 or campos[0][1] != 7:
                raise ValueError("la ficha capturada no vuelve igual")
        except (ValueError, IndexError, struct.error) as e:
            anotar("   ⚠ FF0B: %s" % e)
            return None
        off = 3
        for _ in range(cap[2]):
            off += 4 + struct.unpack_from("<I", cap, off)[0]
            off += 4 + struct.unpack_from("<I", cap, off)[0]
        cola = cap[off:]
        crudo_0 = cap[3:11 + l1 + l2]
        plantilla_campos = campos[0][2]
    else:
        b2 = b"\x70\x80"
        cola = bytes(8) + b"\x01"
        crudo_0 = None
        plantilla_campos = _PLANTILLA_FF0B_NEUTRA

    bloques = bytearray()
    for item in personajes[:casillas]:
        if item.get("capturada") and crudo_0 is not None:
            bloques += crudo_0
            continue
        cta = item.get("cuenta") or {}
        pj = item.get("personaje") or {}
        tienda = item.get("tienda") or {}
        alta_s = cta.get("alta") or "2026-11-01 00:00:00"
        try:
            fecha = time.strftime("%Y%m%d%H%M%S", time.strptime(alta_s, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            fecha = "20261101000000"
        char_id = int(pj.get("char_id", 0x1FF54))
        reemplazos = {
            0: int(cta["usn"]),
            1: char_id,
            2: (list(pj.get("partes") or []) + [0] * 11)[:11],
            5: int(tienda.get("exp", 0)),
            8: textos.codificar(pj.get("nick") or cta.get("nick") or "Jugador"),
            10: fecha.encode("ascii"),
            16: int(tienda.get("g", 0)),
        }
        ficha = []
        vistos = set()
        for c, t, v in plantilla_campos:
            vistos.add(c)
            ficha.append((c, t, reemplazos.get(c, v)))
        if 4 not in vistos:
            ficha.append((4, 0, (char_id - 0x1FF54) & 1))
            ficha.sort(key=lambda x: x[0])
        blob = escribir_campos([(0, 7, ficha)])
        bloques += struct.pack("<I", len(blob)) + blob + struct.pack("<I", len(b2)) + b2
    return bytes([int(casillas) & 0xFF, int(casillas) & 0xFF, len(personajes[:casillas]) & 0xFF]) + bytes(bloques) + cola


def cmdlogin_para(usn):
    """El CmdLogin capturado (48 B) con el usn de OTRO personaje. En la captura el u32 de +1 es el usn que el cliente
    eligio (dato local de captura, el mismo de su FF02) y el cliente lo DEVUELVE despues (ver _cmdlogin_armado). Se cambia solo ese
    campo y solo si el cuerpo tiene la forma de siempre: estado 0 y 48 B."""
    cap = respuesta_cmdlogin()
    if len(cap) != 48 or cap[0] != 0:
        anotar("   ⚠ el CmdLogin capturado no tiene la forma esperada: va el armado a mano")
        cap = _cmdlogin_armado()
    return cap[:1] + struct.pack("<I", usn) + cap[5:]


def lista_para(puerto):
    """La lista de canales capturada con TODOS los puertos cambiados por el de la cuenta (cuentas.py): asi juego.py
    sabe que cuenta se le conecta. Se anclan por estructura: el u16 que va justo antes del largo de cada IP (ver
    lista_capturada), y solo si vale como un puerto del oficial (28000..28999)."""
    cuerpo = lista_capturada()
    if cuerpo is None:
        return None
    out = bytearray(cuerpo)
    ip = ajustes.IP_JUEGO.encode()
    n, i = 0, 0
    while True:
        i = cuerpo.find(bytes([len(ip)]) + ip, i)
        if i < 2:
            break
        if 28000 <= struct.unpack_from("<H", cuerpo, i - 2)[0] < 29000:
            struct.pack_into("<H", out, i - 2, puerto)
            n += 1
        i += 1 + len(ip)
    return bytes(out) if n else None


MAX_SESIONES = 10_000
SESION_TTL = 86_400
RECHAZO_LOGIN_FAIL = 1003       # VALOFE_LOGIN_FAIL (CmdAccountLogin 0x027504c7)
RECHAZO_LOGIN_BUSY = 1001       # VALOFE_LOGIN_BUSY (0x02750473)
_SESIONES = {}                  # gsn -> {"clave": str, "sesion_id": int, "usuario": str, "expira": float}


def limpiar_sesiones():
    """Vacia las sesiones abiertas en memoria (para pruebas)."""
    _SESIONES.clear()


def _registrar_sesion(gsn, usuario, clave, sesion_id):
    ahora = time.time()
    for k in [k for k, v in _SESIONES.items() if v["expira"] < ahora]:
        del _SESIONES[k]
    if len(_SESIONES) >= MAX_SESIONES:
        del _SESIONES[min(_SESIONES, key=lambda k: _SESIONES[k]["expira"])]
    _SESIONES[int(gsn)] = {"clave": clave, "sesion_id": int(sesion_id), "usuario": usuario, "expira": ahora + SESION_TTL}


def _validar_sesion(gsn, clave, sesion_id):
    ses = _SESIONES.get(int(gsn))
    if ses is None or ses["expira"] < time.time():
        _SESIONES.pop(int(gsn), None)
        return None
    if ses["sesion_id"] != int(sesion_id) or not ses["sesion_id"]:
        return None
    if not isinstance(clave, str) or not hmac.compare_digest(ses["clave"], clave):
        return None
    return ses


def extraer_ticket_ff01(cuerpo):
    """Extrae `(steamid_bytes, pase_txt)` de un C2S FF01 (`[02][u8 l_sid][sid][u32 l_ticket][ticket_hex]...`).
    ValueError si el marco no tiene esa forma o el ticket no decodifica de hex/ASCII."""
    if len(cuerpo) < 7 or cuerpo[0] != 0x02:
        raise ValueError("FF01 con cabecera invalida")
    l_sid = cuerpo[1]
    off = 2 + l_sid
    if off + 4 > len(cuerpo):
        raise ValueError("FF01 truncado en largo de ticket")
    l_ticket = struct.unpack_from("<I", cuerpo, off)[0]
    if l_ticket <= 0 or l_ticket > 4096 or off + 4 + l_ticket > len(cuerpo):
        raise ValueError("FF01 con largo de ticket invalido (%d)" % l_ticket)
    sid = cuerpo[2:off]
    ticket_hex = cuerpo[off + 4:off + 4 + l_ticket]
    try:
        pase_txt = bytes.fromhex(ticket_hex.decode("ascii")).decode("ascii")
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError("ticket hex invalido") from e
    return sid, pase_txt


def respuesta_login_pase(steamid_bytes, gsn, clave_sesion, sesion_id):
    """S2C FF01 CmdAccountLogin (1000 OK) entregando `(clave_sesion, sesion_id != 0)` para reconexiones."""
    clave_b = clave_sesion.encode("ascii")
    return (struct.pack("<II", 1000, int(gsn))
            + struct.pack("<I", len(steamid_bytes)) + steamid_bytes
            + struct.pack("<I", len(clave_b)) + clave_b
            + struct.pack("<I", int(sesion_id))
            + struct.pack("<IQI", 0, 0, 0))


def leer_ff02_sesion(cuerpo):
    """Lee `(gsn, usn, clave, sesion_id)` del C2S FF02 (`0x0274f530`), o None si esta malformado."""
    if len(cuerpo) < 20:
        return None
    gsn, usn = struct.unpack_from("<II", cuerpo, 0)
    pos = 13
    l_clave = cuerpo[pos]
    pos += 1
    if pos + l_clave + 1 > len(cuerpo):
        return None
    clave = cuerpo[pos:pos + l_clave].decode("ascii", errors="replace")
    pos += l_clave
    l_hash = cuerpo[pos]
    pos += 1 + l_hash + 1
    if pos >= len(cuerpo):
        return None
    l_sid = cuerpo[pos]
    pos += 1 + l_sid
    if pos + 4 != len(cuerpo):
        return None
    sesion_id = struct.unpack_from("<I", cuerpo, pos)[0]
    return gsn, usn, clave, sesion_id


class Login(asyncio.Protocol):
    def __init__(self, puerto):
        self.puerto, self.buf = puerto, b""
        self.cuenta = None        # 29-oct: la cuenta LOCAL de esta conexion (cuentas.py); None = la de la captura
        self.usuario = None       # ficha 163: la cuenta Eñeños (usuarios[steamid]) para locales y capturada
        self.puerto_destino = None
        self.cerrada = False

    def connection_made(self, tr):
        self.tr = tr
        anotar(":%d CONEXION desde %s" % (self.puerto, tr.get_extra_info("peername")))

    def _rechazar_ff01(self, seq, codigo, motivo):
        anotar("   ⛔ S2C FF01 rechazo %d (%s); cierro conexion" % (codigo, motivo))
        self.tr.write(marco(0x01, seq, struct.pack("<IIII", codigo, 0, 0, 0)))
        self.cerrada = True
        self.tr.close()

    def _cerrar(self, motivo):
        anotar("   ⛔ %s; cierro conexion" % motivo)
        self.cerrada = True
        self.tr.close()

    def _enviar_ff0b_o_cmdlogin(self, seq, u, usn):
        if not usn:
            pjs = cuentas.personajes_de(u["steamid"])
            r = ff0b_multi(pjs, casillas=cuentas.MAX_PERSONAJES) if pjs else None
            if r is not None:
                self.tr.write(marco(0x0B, seq, r))
                anotar("   S2C FF0B CmdCharacterSelect (%d casillas, %d personaje(s)): %d bytes"
                       % (cuentas.MAX_PERSONAJES, len(pjs), len(r)))
            else:
                r = ff0b_sin_personajes()
                self.tr.write(marco(0x0B, seq, r))
                anotar("   S2C FF0B CmdCharacterSelect VACIO (cuenta local): %d bytes" % len(r))
            return True
        if not cuentas.elegir_usn(u["steamid"], usn):
            return False
        if u.get("capturada") and usn == cuentas.USN_CAPTURADA:
            self.puerto_destino = None
            r = respuesta_cmdlogin()
            self.tr.write(marco(0x02, seq, r))
            anotar("   S2C FF02 CmdLogin (capturada, usn %d): %d bytes" % (usn, len(r)))
        else:
            self.puerto_destino = u["puerto"]
            r = cmdlogin_para(usn)
            self.tr.write(marco(0x02, seq, r))
            anotar("   S2C FF02 CmdLogin (usn %d -> puerto %d): %d bytes" % (usn, u["puerto"], len(r)))
        return True

    def _enviar_lista_puerto(self, seq, puerto_dest):
        r = lista_para(puerto_dest)
        if r is None:
            anotar("   ⚠ no pude poner el puerto %d en la lista capturada: va la armada a mano" % puerto_dest)
            ajustes.fijar_puerto_juego(puerto_dest)
            r = respuesta_lista()
        self.tr.write(marco(0x03, seq, r))
        anotar("   S2C FF03 CmdLobbyServerList -> puerto %d: %d bytes" % (puerto_dest, len(r)))

    def _manejar_pase(self, cmd, seq, cuerpo):
        if cmd == 0x01:
            try:
                sid, pase_txt = extraer_ticket_ff01(cuerpo)
            except ValueError as e:
                self._rechazar_ff01(seq, RECHAZO_LOGIN_FAIL, str(e))
                return
            carga = pase.verificar_pase(pase_txt, pase.juego())
            if carga is None:
                self._rechazar_ff01(seq, RECHAZO_LOGIN_FAIL, "pase invalido, vencido, repetido o sin clave")
                return
            uid = int(carga["sub"])
            clave_usuario = "e%d" % uid
            cta = cuentas.alta(clave_usuario)
            if cta is None:
                self._rechazar_ff01(seq, RECHAZO_LOGIN_BUSY, "sin cupo de cuentas (%d)" % cuentas.MAX_CUENTAS)
                return
            u = cuentas.usuario_por_steamid(clave_usuario)
            ses_id = secrets.randbelow(0xFFFFFFFE) + 1
            ses_clave = secrets.token_hex(16)
            _registrar_sesion(u["gsn"], clave_usuario, ses_clave, ses_id)
            self.cuenta = cta
            self.usuario = u
            r = respuesta_login_pase(sid, u["gsn"], ses_clave, ses_id)
            self.tr.write(marco(0x01, seq, r))
            anotar("   S2C FF01 CmdAccountLogin PASE OK: usuario %s (gsn %d, puerto %d, %d personaje(s))"
                   % (clave_usuario, u["gsn"], u["puerto"], len(cuentas.personajes_de(clave_usuario))))
            return
        if cmd == 0x02:
            leido = leer_ff02_sesion(cuerpo)
            if leido is None:
                self._cerrar("FF02 malformado en modo pase")
                return
            gsn, usn, clave_c2s, ses_id_c2s = leido
            ses = _validar_sesion(gsn, clave_c2s, ses_id_c2s)
            if ses is None or (self.usuario is not None and self.usuario["gsn"] != gsn):
                self._cerrar("FF02 sin sesion valida (gsn %d)" % gsn)
                return
            u = cuentas.usuario_por_steamid(ses["usuario"])
            if u is None or u.get("capturada"):
                self._cerrar("usuario de sesion invalido (%s)" % ses["usuario"])
                return
            self.usuario = u
            anotar("   el FF02 trae GSN %d, personaje (usn) %d (sesion valida)" % (gsn, usn))
            if not self._enviar_ff0b_o_cmdlogin(seq, u, usn):
                self._cerrar("usn %d no pertenece a %s" % (usn, u["steamid"]))
            return
        if cmd == 0x0C:
            gsn = struct.unpack_from("<I", cuerpo, 0)[0] if len(cuerpo) >= 4 else 0
            if self.usuario is None or self.usuario["gsn"] != gsn:
                self._cerrar("FF0C sin sesion autenticada (gsn %d)" % gsn)
                return
            usn = cuentas.pedir_usn(self.usuario["gsn"])
            if usn is None:
                self.tr.write(marco(0x0C, seq, struct.pack("<BII", 1, gsn, 0)))
                anotar("   ⛔ S2C FF0C GetNewUSN rechazado: gsn %d ya tiene %d personajes" % (gsn, cuentas.MAX_PERSONAJES))
                return
            self.usuario = cuentas.usuario_por_gsn(self.usuario["gsn"]) or self.usuario
            self.puerto_destino = self.usuario["puerto"]
            self.tr.write(marco(0x0C, seq, struct.pack("<BII", 0, gsn, usn)))
            anotar("   S2C FF0C CmdGetNewUSN: gsn %d -> usn %d (puerto %d)" % (gsn, usn, self.usuario["puerto"]))
            return
        if cmd == 0x03:
            if self.usuario is None or self.puerto_destino is None:
                self._cerrar("FF03 sin personaje elegido ni sesion")
                return
            self._enviar_lista_puerto(seq, self.puerto_destino)
            return
        anotar("   (sin respuesta todavia) %s" % cuerpo[:48].hex())

    def data_received(self, d):
        if self.cerrada:
            return
        self.buf += d
        ms, self.buf = marcos(self.buf)
        for cmd, seq, cuerpo in ms:
            if self.cerrada:
                break
            anotar(":%d C2S FF%02X seq=%d largo=%d" % (self.puerto, cmd, seq, len(cuerpo)))
            if self.puerto in PUERTOS and pase.modo_pase():
                self._manejar_pase(cmd, seq, cuerpo)
                continue
            if self.puerto in PUERTOS and cmd == 0x01:
                sid = cuerpo[2:2 + cuerpo[1]] if len(cuerpo) > 2 and cuerpo[0] == 0x02 else b""
                cap = cuerpo_capturado(0x01)
                if sid and (cap is None or sid not in cap) and ajustes.CUENTAS_LOCALES:
                    # 29-oct: un SteamID que NO es el de la captura = una cuenta LOCAL (RECONSTRUIDO, ver arriba)
                    sid_s = sid.decode("latin-1")
                    self.cuenta = cuentas.alta(sid_s)
                    if self.cuenta is None:
                        anotar("   ⛔ ya hay %d cuentas locales: no contesto" % cuentas.MAX_CUENTAS)
                        continue
                    self.usuario = cuentas.usuario_por_steamid(sid_s)
                    pjs = cuentas.personajes_de(sid_s)
                    anotar("   CUENTA LOCAL %s (gsn %d, puerto %d, %d personaje(s))" % (
                        self.cuenta["nick"] or sid_s, self.cuenta["gsn"], self.cuenta["puerto"], len(pjs)))
                    r, _sid = respuesta_login(cuerpo, self.cuenta["gsn"])
                    self.tr.write(marco(0x01, seq, r))
                    anotar("   S2C FF01 CmdAccountLogin ARMADO (cuenta local): resultado 1000, %d bytes" % len(r))
                    continue
                if sid and cap is not None and sid in cap and ajustes.CUENTAS_LOCALES:
                    sid_s = sid.decode("latin-1")
                    gsn_cap = struct.unpack_from("<I", cap, 4)[0]
                    cuentas.alta(sid_s, gsn=gsn_cap, capturada=True)
                    self.usuario = cuentas.usuario_por_steamid(sid_s)
                try:
                    r, steamid = respuesta_login(cuerpo)
                except ValueError as e:
                    anotar("   no contesto: %s" % e)
                    continue
                self.tr.write(marco(0x01, seq, r))
                anotar("   S2C FF01 CmdAccountLogin: resultado 1000, cuenta de %d caracteres, %d bytes"
                       % (len(steamid), len(r)))
            elif self.puerto in PUERTOS and cmd == 0x02:
                # ⭐ 22-oct: en el volcado del oficial el orden es FF01, FF0B, FF02: el FF0B
                # (CmdCharacterSelect, cmd 11 de la tabla del login) va JUNTO AL FF02, no al FF01.
                # Mandandolo con el FF01 el cliente corta antes de mandar su segundo mensaje.
                #
                # ⭐⭐ 22-oct (noche): pero el oficial NO contesta igual a todos los FF02. El cliente
                # mando dos, y los 4 bytes despues del GSN son el PERSONAJE elegido:
                #     1er FF02  usn 0         -> FF0B (la lista de personajes)
                #     2do FF02  usn dato local de captura   -> FF02 CmdLogin solo (que trae ese mismo usn)
                # Al hacer clic en el personaje ("<Game Start> slot 0" en el log del juego) el
                # cliente manda un FF02 de 72 B con el usn; contestandole tambien el FF0B, su log
                # dice `CMDCharacterSelect` -> `Character Exist => proc(MultiCharacter)` y vuelve a
                # la bienvenida. SIEMPRE_FF0B=1 vuelve a mandarlo siempre.
                gsn, usn = struct.unpack_from("<II", cuerpo, 0) if len(cuerpo) >= 8 else (0, 0)
                anotar("   el FF02 trae GSN %d, personaje (usn) %d" % (gsn, usn))
                if ajustes.CUENTAS_LOCALES:
                    u = cuentas.usuario_por_gsn(gsn) or self.usuario
                    if u is not None:
                        self.usuario = u
                        self._enviar_ff0b_o_cmdlogin(seq, u, usn)
                        continue
                ff0b = ajustes.RUTA_FF0B
                if usn and not ajustes.SIEMPRE_FF0B:
                    anotar("   trae personaje: va SOLO el CmdLogin, como el oficial")
                elif os.path.exists(ff0b):
                    cuerpo0b = bytes.fromhex(open(ff0b).read().strip())
                    self.tr.write(marco(0x0B, seq, cuerpo0b))
                    anotar("   S2C FF0B CmdCharacterSelect: %d bytes (de la captura)" % len(cuerpo0b))
                # ⭐⭐ y al FF02 SIN personaje el oficial NO manda el CmdLogin. Medido en el log del
                # juego ORIGINAL contra el oficial (22-oct 13:58): `SendLogin USN:0` -> solo
                # `CMDCharacterSelect` -> pantalla de personajes; `<Game Start>` USN:dato local de captura ->
                # CmdLogin -> RECIEN AHI `wServerPort_1(28008)` y el lobby. Mandandolo al primero,
                # el cliente se conectaba al 28008 ANTES de elegir, y al hacer clic el CmdLogin
                # tomaba la rama de "ya conectado" (0x023543ef) y se quedaba en la carga.
                # CMDLOGIN_SIEMPRE=1 vuelve a mandarlo tambien al primero.
                if not usn and not ajustes.CMDLOGIN_SIEMPRE and os.path.exists(ff0b):
                    continue
                r = respuesta_cmdlogin()
                self.tr.write(marco(0x02, seq, r))
                anotar("   S2C FF02 CmdLogin: %d bytes" % len(r))
            elif self.puerto in PUERTOS and cmd == 0x0C:
                # 29-oct / ficha 163: C2S SendGetNewUSN [u32 gsn] -> S2C CmdGetNewUSN [u8 res][u32 gsn][u32 usn]
                gsn = struct.unpack_from("<I", cuerpo, 0)[0] if len(cuerpo) >= 4 else 0
                u = (cuentas.usuario_por_gsn(gsn) or self.usuario) if ajustes.CUENTAS_LOCALES else None
                if u is None:
                    anotar("   ⚠ FF0C GetNewUSN de un gsn %d desconocido: no contesto" % gsn)
                    continue
                usn = cuentas.pedir_usn(u["gsn"])
                if usn is None:
                    self.tr.write(marco(0x0C, seq, struct.pack("<BII", 1, gsn, 0)))
                    anotar("   ⛔ S2C FF0C GetNewUSN rechazado: gsn %d ya tiene %d personajes" % (gsn, cuentas.MAX_PERSONAJES))
                    continue
                self.usuario = cuentas.usuario_por_gsn(u["gsn"]) or u
                self.puerto_destino = u["puerto"]
                self.tr.write(marco(0x0C, seq, struct.pack("<BII", 0, gsn, usn)))
                anotar("   S2C FF0C CmdGetNewUSN: gsn %d -> usn %d (puerto %d)" % (gsn, usn, u["puerto"]))
            elif self.puerto in PUERTOS and cmd == 0x03 and self.puerto_destino is not None:
                self._enviar_lista_puerto(seq, self.puerto_destino)
            elif self.puerto in PUERTOS and cmd == 0x03:
                r = None if ajustes.LISTA_A_MANO else lista_capturada()
                de = "de la CAPTURA (%d canales)" % r[0] if r else "de la CAPTURA"
                if r is None:
                    r, de = respuesta_lista(), "armada a mano (1 canal)"
                self.tr.write(marco(0x03, seq, r))
                anotar("   S2C FF03 CmdLobbyServerList %s: %d bytes" % (de, len(r)))
            else:
                anotar("   (sin respuesta todavia) %s" % cuerpo[:48].hex())

    def connection_lost(self, exc):
        anotar(":%d se cerro la conexion (%s)" % (self.puerto, exc or "normal"))


async def main():
    if pase.modo_pase():
        pase.inicializar(log=anotar)
    for h in HOSTS:
        for p in PUERTOS:
            await asyncio.get_running_loop().create_server(lambda p=p: Login(p), h, p)
            anotar("escuchando en %s:%d" % (h, p))
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
