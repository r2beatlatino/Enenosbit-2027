# -*- coding: utf-8 -*-
r"""juego.py (22-oct) — el servidor de JUEGO local (puerto 28008) para el cliente de Steam.

Ver docs/SERVIDOR_LOCAL_STEAM.md. Despues del login, el cliente conecta al canal que le dimos en la
lista (FF03) y empieza el saludo. Todo esto sale de la CAPTURA del oficial del 22-oct
(tools/net/volcado_28008_{C2S,S2C}.bin, con permiso del usuario):

    C2S FF04  20 B  en claro   hola
    S2C FF04  25 B  en claro   [00][u32 4][u32 ...][16 B][u32 marca de tiempo]
    C2S FF02 168 B             login (blob del token)
    S2C FF02 269 B             [resultado:1][8 B][CLAVE:256][relleno:4]
    -- de aca en mas todo va en FF55, cifrado con esa clave --

EL CIFRADO (medido el 18-ago, `NOTAS_SERVER_OFICIAL.md`): XOR de keystream fijo, la clave la MANDA el
servidor en claro y vale para los dos sentidos. `K = cifra[0] ^ clave[0] ^ 0xFF` y
`claro[i] = cifra[i] ^ clave[i % 256] ^ K`. Comprobado sobre la captura: el primer FF55 del oficial
se abre y adentro aparece un marco FF56.

⚠ Lo que este servidor manda hoy es el SALUDO y nada mas: alcanza para que el cliente no se quede
con punteros en cero (se caia leyendo `[edi+0x18]` con edi=0, codigo del programa, NO una pieza que
falte). Lo que siga —el perfil, los personajes— sale de reproducir la sesion capturada.

Uso:  python juego.py          (o se arranca junto con login.py)
"""
import asyncio
import hmac
import os
import struct
import time

import ajustes
import captura
import cuenta
import cuentas
import estado
import fichas
import manejadores
import neutro
import panel_interno
import recarga

SESION_TTL = 86_400

# Lo que es regla o armado de mensajes (manejadores.py y los modulos que carga, fichas.py, practica.py, cuenta_local.py) se
# recarga solo cuando cambia su archivo, sin reiniciar el servidor: lo hace recarga.py (archivo quieto, compila antes de
# tocar, de a un modulo, si falla sigue el anterior). Este archivo es el PROCESO: puertos, encuadre, cifrado y la sesion
# capturada; para cambiarlo hay que reiniciar. estado.py (las salas) tampoco se recarga.
manejadores_al_dia = recarga.revisar


PUERTOS = list(ajustes.PUERTOS_JUEGO)          # ajustes.py: variable PUERTOS_JUEGO
# 29-oct: y el puerto de cada cuenta LOCAL (cuentas.py): la lista de canales que les da login.py apunta ahi, y por el
# puerto se sabe QUE cuenta se conecta (su FF02 de 168 B viene cifrado). CUENTAS_LOCALES=0 los apaga.
# M01b (22-nov): con IDENTIDAD_FF02 (modo pase) todos entran por el puerto compartido y la cuenta sale del FF02: los puertos
# por cuenta ya no se abren (el login no los anuncia mas).
if ajustes.CUENTAS_LOCALES and not cuentas.identidad_ff02():
    PUERTOS += [p for p in cuentas.PUERTOS if p not in PUERTOS]
HOSTS = ajustes.HOSTS
AQUI = ajustes.AQUI
# 22-oct: servidor_local/ (ver LEEME.md): los datos salen de datos/ (herramientas/preparar_datos.py) y
# lo que se anota va a registros/.
DATOS = ajustes.DATOS
DIR = ajustes.REGISTROS
os.makedirs(DIR, exist_ok=True)
SALIDA = open(os.path.join(DIR, time.strftime("juego_%Y%m%d_%H%M%S.txt")), "w", encoding="utf-8")
T0 = time.time()
# el saludo del oficial, tal cual si esta juego_S2C.bin (los 4 ultimos bytes son una marca de tiempo: se pone la de ahora)
_FF04_CAP = captura.cuerpo_del_oficial(0x04)
FF04 = _FF04_CAP[:21] if _FF04_CAP is not None and len(_FF04_CAP) >= 21 else neutro.ff04_cabeza()
RUTA_CAP_JUEGO = ajustes.RUTA_CAP_JUEGO


# ⭐ 22-oct: el FF02 (y con el la CLAVE) salen de la CAPTURA, no de nuestra invencion. Con la clave
# inventada el cliente recibia los 60 lotes y su propio log decia
#     [CNetwork]ParsePacket :: byIdentifier = 0, byType = 0, wSize = 0
# o sea que descifraba PUROS CEROS. Los lotes de `batches_S2C.bin` son los del oficial, asi que hay
# que cifrarlos con SU clave para que el cliente los vea como los vio aquella vez.
# CLAVE_PROPIA=1 vuelve a la inventada.
# 10-nov (ficha 37): lo lee captura.py; el FF02 que sale ya trae la llave de ESTA maquina (ver mas abajo).
FF02_CUERPO = captura.ff02_cuerpo()
CLAVE = captura.clave()

# ---------- LA LLAVE DE HARDWARE (01-nov) ----------
# ⭐ El "closeMe:30020" que corto a TODAS las cuentas el 01-nov (tambien a la de la captura) era esto. MEDIDO en el exe:
#   - CNetwork::CmdLogin (FF02, 0x0277b850) lee [u8 resultado][u32 X]... y en 0x0277bd22 compara X ^ 0xcacb1112 con
#     0x004740f0: la LLAVE DE HARDWARE de la maquina = los bytes 1, 3, 5 y 2 de la MAC del PRIMER adaptador de
#     GetAdaptersInfo (0x0047415f). Si no coincide, el resultado pasa a 1 y sale el cartel 30020 (0x0277c0cf).
#   - CNetwork::CmdAck (FF05, 0x0277b240) hace la misma cuenta con su primer u32; si no coincide solo anota
#     "[CNetwork]CmdAck :: dwHardwareKey = ..." (0x0277b2c9).
# La captura trae la llave de la maquina del 22-oct (0xdato local de captura, la misma en el FF02 y en todos sus FF05). El 01-nov
# el primer adaptador de esta maquina ya da otra (los adaptadores cambiaron), y desde entonces nada entraba. Testigos:
# el log del cliente (closeMe:30020 en CmdLogin linea 393) y la linea de CmdAck, que aparece SOLO en las corridas del
# 01-nov y en ninguna anterior. Como el servidor corre en la MISMA maquina que el juego, la calcula igual que el
# cliente y la pone en esos dos lugares. LLAVE=<hex> la fija a mano; LLAVE_CAPTURADA=1 manda la de la captura.
LLAVE_SAL = captura.LLAVE_SAL
LLAVE_CAP = captura.llave_de_la_captura()


LLAVE = captura.llave_de_esta_maquina()      # captura.py: LLAVE / LLAVE_CAPTURADA / la de hardware; con_llave() tambien esta ahi


# ---------- REPRODUCCION de la sesion capturada (22-oct) ----------
# Despues del saludo el oficial manda 60 lotes cifrados (14.621 bytes de contenido) con el perfil,
# los personajes y los catalogos. NO hace falta entender cada campo para que el cliente avance: se
# mandan los MISMOS bytes, cifrados con NUESTRA clave. Es el metodo que ya funciono en el login
# (ver docs/SERVIDOR_LOCAL_STEAM.md), donde se copio una cola de 68 bytes tal cual de la captura.
#
# De donde salen los lotes: `datos/lotes_S2C.bin`, los 60 de la sesion del 22-oct que el proxy guardo YA
# DESCIFRADOS en `tools/net/batches_S2C.bin` (los copia herramientas/preparar_datos.py).
RUTA_LOTES = ajustes.RUTA_LOTES
# y TODOS los FF55 del volcado del juego, descifrados con su clave (de ahi salen las respuestas por metodo)
RUTA_RESPUESTAS = ajustes.RUTA_RESPUESTAS
REPRODUCIR = ajustes.REPRODUCIR
CUANTOS_LOTES = ajustes.CUANTOS_LOTES
# El intercalado sale del log del proxy del 22-oct: S = un lote del servidor, C = uno del cliente.
# ⚠ ES APROXIMADO, y conviene saber por que: el log tiene 46 lineas S2C y 31 C2S, pero los lotes
# guardados son 60 y 58, porque un lote donde el escaneo no encuentra ningun 0xFF no deja linea. O
# sea que esto da la FORMA del dialogo (el oficial arranca con una rafaga, despues alterna), no una
# correspondencia uno a uno. Cuando el patron se agota se manda un lote por mensaje del cliente.
PATRON = ajustes.PATRON


# ⭐ 22-oct: PASAR DE REPRODUCIR A RESPONDER. Al elegir el personaje el cliente manda 233 mensajes
# cifrados pidiendo metodos por nombre (`modAct.getActList`, `vip.info`, `getdiamondInfoCS`...) y
# nuestro servidor no contestaba ninguno: hacia la secuencia de carga y volvia a la bienvenida.
# Varias respuestas del oficial traen el nombre del metodo adentro, asi que el mapa se arma SOLO
# leyendo los lotes. Los que son respuesta NO se mandan en la rafaga inicial: se guardan para cuando
# el cliente los pida. (Eso ademas quita el cartel: el JSON de la tienda es el lote de
# `getdiamondInfoCS`, y salia porque se lo mandabamos sin que lo pidiera.)
NOMBRES = ("getdiamondInfoCS", "modAct.getActInfoByKey7", "modAct.getActInfoByKey", "vip.info")


def _mapa_respuestas(lotes):
    """{nombre de metodo: indice del lote}. El nombre mas largo gana, para que `...ByKey7` no se lo
    lleve `...ByKey`."""
    out = {}
    for nom in sorted(NOMBRES, key=len, reverse=True):
        for i, d in enumerate(lotes):
            if nom.encode() in d and i not in out.values():
                out[nom] = i
                break
    return out


RESPUESTAS = _mapa_respuestas(captura.lotes_capturados()) if REPRODUCIR else {}


# ⭐⭐ 22-oct (noche): LA FORMA REAL DE UN PEDIDO Y SU RESPUESTA, leida emparejando la captura (ver
# docs/SERVIDOR_LOCAL_STEAM.md). Adentro de cada FF55 descifrado:
#
#     ff 56 [n:u16] [n bytes de relleno al azar] | [fd][cmd][seq:u16][largo:u32] | cuerpo
#     pedido:     [id:u32][u32] [u32+nombre] [u32+JSON con los ARGUMENTOS]
#     respuesta:  [8 bytes del servidor] [id:u32][u32] [u32+nombre] [u32+JSON con el RESULTADO] ...
#
# El `id` lo inventa el cliente en cada pedido y el servidor lo devuelve: es lo que empareja. Y el
# `cmd` (0x46, 0x55, 0x6f...) es el canal: los tres `getActList` van por tres canales y cada uno
# tiene su respuesta. La de arriba (`ff 56 [contador]` + 25 bytes) era una lectura equivocada: el
# "contador" es el largo del relleno, y los "25 bytes" incluian ese relleno al azar.
# ⚠ Lo que fallaba al fabricar: la respuesta lleva 8 bytes MAS que el pedido, y copiando el pedido
# el cliente leia nombre, largo y JSON corridos 8 posiciones.
def metodo_de(claro, respuesta):
    """(cmd, desplazamiento del id, nombre, JSON) de un mensaje con metodo, o None."""
    if len(claro) < 4 or claro[:2] != b"\xff\x56":
        return None
    o = 4 + struct.unpack_from("<H", claro, 2)[0]
    b = o + 8 + (8 if respuesta else 0)
    if b + 12 > len(claro):
        return None
    nl = struct.unpack_from("<I", claro, b + 8)[0]
    p = b + 12 + nl
    if not 3 <= nl <= 64 or p + 4 > len(claro):
        return None
    nombre = claro[b + 12:p]
    if not all(32 < c < 127 for c in nombre):
        return None
    jl = struct.unpack_from("<I", claro, p)[0]
    return claro[o + 1], b, nombre.decode(), claro[p + 4:p + 4 + jl]


def _respuestas_del_volcado():
    """Todas las respuestas con metodo que mando el oficial: [(nombre, cmd, claro, off_id, json)].

    ⭐ Salen del VOLCADO, no solo de los 60 lotes: las respuestas a `getActList` (y una de
    `vip.info` y las dos de `gift.info`) NO estan en `batches_S2C.bin`; por eso el 22-oct parecia
    que el oficial nunca lo habia contestado. herramientas/preparar_datos.py relee el volcado con el
    resincronizador de `tools/net/leer_captura_juego.py` y los deja descifrados en datos/.
    """
    claros = captura.claros_del_volcado()
    out, vistos = [], set()
    for d in claros:
        m = metodo_de(d, True)
        if m and d not in vistos:
            vistos.add(d)
            out.append((m[2], m[0], d, m[1], m[3]))
    return out


POR_METODO = _respuestas_del_volcado() if REPRODUCIR else []
POR_ID = ajustes.POR_ID      # POR_ID=0 vuelve a `responder` por lote
# 22-oct: NO_RESPONDER=getdiamondInfoCS,... deja SIN contestar esos metodos (para probar si una respuesta
# capturada provoca algo: el cartel con el JSON de la tienda, los gestos solos de la partida).
NO_RESPONDER = ajustes.NO_RESPONDER

def comandos_de(claro):
    """[(cmd con el byte alto, largo)] de los marcos de adentro de un FF56: 0xFF -> FF0xx, 0xFE -> FF1xx, 0xFD -> FF2xx
    (docs/FF_HANDLERS_CHINO.md §1). Solo para anotar."""
    if len(claro) < 4 or claro[:2] != b"\xff\x56":
        return []
    k, out = 4 + struct.unpack_from("<H", claro, 2)[0], []
    while k + 8 <= len(claro):
        fl, cmd = claro[k], claro[k + 1]
        ln = struct.unpack_from("<I", claro, k + 4)[0]
        if k + 8 + ln > len(claro) or fl not in (0xFF, 0xFE, 0xFD):
            break
        out.append(({0xFF: 0, 0xFE: 0x100, 0xFD: 0x200}[fl] + cmd, ln))
        k += 8 + ln
    return out


# los lotes que son respuesta no van en la rafaga inicial: se guardan para cuando los pidan
LOTES_RESPUESTA = {d for _n, _c, d, _o, _j in POR_METODO}
# ⛔ 22-oct, MEDIDO Y APAGADO: fabricar respuestas vacias para los metodos que no tenemos
# (`modAct.getActList` -> `[]`, etc.) es PEOR que no contestar. Las respuestas salen —se ven en el
# log— pero el cliente aborta con un `Runtime Error` de Visual C++ ("requested the Runtime to
# terminate it in an unusual way") ANTES de la bienvenida, y es REPRODUCIBLE (2 de 2). Eso no es una
# violacion de acceso: es el programa rindiendose a proposito (excepcion de C++ sin atrapar o un
# assert), o sea que el contenido no le sirve. Sin fabricar, el cliente al menos llega a la
# seleccion de personaje. FABRICAR=1 lo vuelve a encender para experimentar.
FABRICAR = ajustes.FABRICAR
VACIO_DE = {"modAct.getActList": b"[]", "musicMedalNet.onInit": b"{}", "gift.info": b"{}"}


def anotar(txt):
    ln = "[%7.2f s] %s" % (time.time() - T0, txt)
    print(ln, flush=True)
    SALIDA.write(ln + "\n")
    SALIDA.flush()


def marco(cmd, seq, cuerpo):
    return struct.pack("<BBHI", 0xFF, cmd, seq, len(cuerpo)) + cuerpo


def marcos(buf):
    out = []
    while len(buf) >= 8 and buf[0] == 0xFF:
        cmd, seq, largo = buf[1], struct.unpack_from("<H", buf, 2)[0], struct.unpack_from("<I", buf, 4)[0]
        if len(buf) < 8 + largo:
            break
        out.append((cmd, seq, buf[8:8 + largo]))
        buf = buf[8 + largo:]
    return out, buf


def descifrar(c, clave):
    """XOR de keystream fijo (18-ago). K sale del primer byte."""
    if not c:
        return c
    k = c[0] ^ clave[0] ^ 0xFF
    return bytes(c[i] ^ clave[i % 256] ^ k for i in range(len(c)))


def k_para(usn):
    """La constante del XOR que el CLIENTE usa para descifrar, segun el usn del personaje. MEDIDO en
    CNetwork::CmdEncryptRandomXOR (0x027ad9a0, 01-nov):
        bl = (usn + [red+0x143878]) ^ [red+0x143880]     el usn sale de la cuenta (guardado ^0xd350, 0x027ada3b); la
                                                        semilla es el u32 de +5 del FF02 (CmdLogin, 0x0277bbb2) y
                                                        el contador arranca en 0 (0x0277bc3f)
        claro[i] = cifra[i] ^ clave[i % 256] ^ clave[bl] ^ bl
    Control: con el usn de la captura da 0x0D, la constante con la que este servidor cifro siempre y con la
    que el cliente lee. Con otro usn (una cuenta LOCAL) da otra: con 0x0D el cliente descifraba basura y anotaba
    "ParsePacket :: byIdentifier = 0 ..." (01-nov): nunca veia la ficha y no abria la pantalla de crear."""
    semilla = struct.unpack_from("<I", FF02_CUERPO, 5)[0] if FF02_CUERPO is not None else neutro.FF02_SEMILLA
    bl = (usn + semilla) & 0xFF
    return CLAVE[bl] ^ bl


def cifrar(claro, clave, k=0x0D):
    return bytes(claro[i] ^ clave[i % 256] ^ k for i in range(len(claro)))


# ---------- LOS CAMPOS DE LA CONEXION ----------
# Lo que los modulos recargables le leen y le escriben a la conexion (`con`) vive aca, declarado en __init__ con su valor
# inicial: asi `con.sala` existe siempre y nadie usa getattr(con, ...). estado.py no la tiene (esta clase es la red).


class Juego(asyncio.Protocol):
    """Una conexion de un cliente (un puerto): lee marcos, descifra, despacha y escribe. La CONEXION es esto."""

    def __init__(self, puerto):
        self.puerto, self.buf = puerto, b""
        self.id_con = next(estado.NUMEROS_DE_CONEXION)
        self.cerrada = False
        self.llave = LLAVE
        por_ff02 = cuentas.identidad_ff02()
        if REPRODUCIR and not por_ff02:
            lotes = captura.lotes_capturados()
            self.lotes = lotes if ajustes.pase_activo() else [captura.con_llave(x) for x in lotes]
        else:
            self.lotes = []
        # 29-oct: una cuenta LOCAL (por el puerto, ver cuentas.py) recibe SU ficha en el FF00.
        # M01: con IDENTIDAD_FF02 activa en modo pase, self.cuenta = None en TODOS los puertos y se arma en el FF02.
        self.cuenta = None if por_ff02 else (cuentas.por_puerto(puerto) if puerto in cuentas.PUERTOS else None)
        # 01-nov: la constante del XOR depende del usn del personaje (k_para); la de la captura da 0x0D
        self.k = k_para(self.cuenta["usn"]) if self.cuenta is not None and self.cuenta.get("usn") else 0x0D
        # la rafaga de entrada: lista de canciones recortada y, en una cuenta local, SU ficha y SU ropa (fichas.py)
        if not por_ff02:
            self.lotes = fichas.lotes_de_entrada(self.lotes, self.cuenta)
        self.partida = 0x0f3d    # el numero de partida del FF3A (el oficial mando 0x0f3d); practica.py la sube de a una
        self.i_lote = 0          # cual es el proximo lote capturado por mandar
        self.i_patron = 0        # donde estamos en PATRON
        self.seq = 1
        self.sala = None         # numero de la sala donde esta (salas.crear / sentar_y_avisar / sacar_de_su_sala); None = en el lobby
        self.listo = 0           # 1 si apreto READY (salas.listo); salas.sacar_de_su_sala, cambiar_modo y carrera.mandar_cartel lo bajan a 0
        self.pidio_sala = 0      # hora (time.time) del ultimo FF15 que pidio (salas.info); carrera.revisar la compara con la vuelta del coop
        self.turno = {}          # responder_por_id: cuantas veces se uso cada respuesta capturada, {(metodo, canal): n}
        self.intento_mision = None   # misiones.py: el intento de mision en curso (dict: usn, familia, codigo, t0, ...)
        self.t_conexion = time.time()

    def connection_made(self, tr):
        self.tr = tr
        estado.CONEXIONES[self.id_con] = self
        anotar(":%d CONEXION desde %s" % (self.puerto, tr.get_extra_info("peername")))
        if self.cuenta is not None:
            anotar("   es la cuenta LOCAL %s (usn %d, XOR 0x%02x, %s)" % (self.cuenta["nick"], self.cuenta["usn"], self.k,
                   "personaje %d" % self.cuenta["personaje"]["char_id"] if self.cuenta["personaje"] else "sin personaje"))
        elif self.puerto in cuentas.PUERTOS and not cuentas.identidad_ff02():
            anotar("   ⚠ el puerto %d no es de ninguna cuenta local: va la sesion capturada" % self.puerto)
        if REPRODUCIR and not cuentas.identidad_ff02():
            anotar("   reproduccion: %d lotes capturados listos (%d bytes)"
                   % (len(self.lotes), sum(len(x) for x in self.lotes)))
            if not self.lotes:
                anotar("   ⚠ no hay lotes: falta %s" % RUTA_LOTES)

    def _rechazar_ff02(self, motivo):
        anotar("   ⛔ FF02 rechazado (%s); cierro conexion" % motivo)
        self.cerrada = True
        self.tr.close()

    def mandar_claro(self, claro):
        """Un mensaje en claro (un FF56) al cliente: sube el seq y lo manda cifrado en un FF55 con NUESTRA clave."""
        self.seq = (self.seq + 1) & 0xFFFF
        self.tr.write(marco(0x55, self.seq, cifrar(claro, CLAVE, self.k)))

    def mandar_lote(self):
        """Manda el proximo lote capturado, cifrado con NUESTRA clave. False si no quedan."""
        if self.i_lote >= len(self.lotes):
            return False
        claro = self.lotes[self.i_lote]
        self.i_lote += 1
        self.mandar_claro(claro)
        dentro = "FF%02X" % claro[1] if len(claro) > 1 and claro[0] == 0xFF else "?"
        anotar("   S2C lote %d/%d (%d B, sobre %s)"
               % (self.i_lote, len(self.lotes), len(claro), dentro))
        try:                                  # ficha 91: el FF133 vacio va justo despues del FF16D de la rafaga
            manejadores.cuenta_local.tras_lote(self, claro)
        except Exception as e:                # noqa: BLE001
            anotar("   ⛔ tras_lote: %r" % e)
        return True

    def nombre_pedido(self, claro):
        """El nombre del metodo que pide el cliente, o None.

        Los pedidos lo llevan como cadena ASCII con su largo (u32) adelante: `modAct.getActList`,
        `vip.info`, `gift.info`, `getdiamondInfoCS`, `musicMedalNet.onInit`...
        """
        for i in range(4, min(len(claro) - 4, 80)):
            n = struct.unpack_from("<I", claro, i)[0]
            if 3 <= n <= 60 and i + 4 + n <= len(claro):
                s = claro[i + 4:i + 4 + n]
                if all(32 <= c < 127 for c in s):
                    return s.decode()
        return None

    def responder_vacio(self, claro, nombre):
        """Fabrica una respuesta para un metodo del que NO tenemos la del oficial.

        ⭐ 22-oct: el cliente pide `modAct.getActList` 27 veces y se queda esperando; sin respuesta
        hace la secuencia de carga y vuelve a la bienvenida. Pedido y respuesta tienen la MISMA
        forma (medido sobre el par `vip.info`):
            ff 56 [contador:u16] | 25 bytes de campos | u32+nombre | u32+JSON
        asi que se devuelve el pedido tal cual hasta el nombre —con eso viajan los campos que sirven
        para emparejar— y se le pega un resultado vacio.
        ⚠ ES UNA SUPOSICION: los 25 bytes de campos difieren entre el pedido y la respuesta del
        oficial en 2 de ellos, asi que puede no alcanzar. Se prueba y se mide.
        """
        i = claro.find(nombre.encode())
        if i < 8:
            return False
        cab = claro[:i + len(nombre)]
        cuerpo = VACIO_DE.get(nombre, b"[]")
        r = cab + struct.pack("<I", len(cuerpo)) + cuerpo
        self.mandar_claro(r)
        anotar("   S2C respuesta FABRICADA a %s: %s (%d B)" % (nombre, cuerpo.decode(), len(r)))
        return True

    def responder_por_id(self, claro):
        """Contesta con la respuesta CAPTURADA del mismo metodo y canal, cambiandole solo el `id`
        por el del pedido. True si contesto.

        Si hay varias (los dos `getActInfoByKey` piden claves distintas), gana la que contiene una
        cadena de los argumentos del pedido —el hash de la clave aparece en el resultado—; si
        ninguna, se van turnando.
        """
        m = metodo_de(claro, False)
        if not m:
            return False
        cmd, off_id, nombre, args = m
        cands = [r for r in POR_METODO if r[0] == nombre and r[1] == cmd]
        if not cands:
            return False
        cadenas = [s for s in args.split(b'"')[1::2] if len(s) >= 8]
        elegida = next((r for r in cands if any(s in r[4] for s in cadenas)), None)
        if elegida is None:
            k = self.turno.get((nombre, cmd), 0)
            self.turno[(nombre, cmd)] = k + 1
            elegida = cands[k % len(cands)]
        _n, _c, d, o, _j = elegida
        # 08-nov: la respuesta del oficial repite los 8 BYTES del pedido ([id:u32][u32]), no solo el id: 43 de 43 pares
        # en la grabacion 20261108_130830. getdiamondInfoCS pide con 1 y la captura del 22-oct traia 2: el cliente no la
        # emparejaba y mostraba el JSON de la tienda de diamantes en un cartel al llegar a la casa.
        rid = claro[off_id:off_id + 8]
        r = d[:o] + rid + d[o + 8:]
        self.mandar_claro(r)
        anotar("   S2C RESPUESTA CAPTURADA a %s (canal %02x, id %s): %d B, resultado %s"
               % (nombre, cmd, rid.hex(), len(r),
                  "".join(chr(c) if 32 <= c < 127 else "." for c in _j[:60])))
        return True

    def mandar_interno(self, cmd, seq, cuerpo):
        """Un marco de comando adentro de un FF56 (sin relleno), cifrado en un FF55. cmd >= 0x100 va con el byte alto
        0xFE / 0xFD (docs/FF_HANDLERS_CHINO.md §1)."""
        alto = {0: 0xFF, 1: 0xFE, 2: 0xFD}[cmd >> 8]
        self.mandar_claro(b"\xff\x56\x00\x00" + struct.pack("<BBHI", alto, cmd & 0xFF, seq, len(cuerpo)) + cuerpo)

    def responder(self, nombre):
        """Contesta con el lote de la captura que corresponde a ese metodo. True si contesto."""
        i = RESPUESTAS.get(nombre)
        if i is None:
            return False
        claro = self.lotes[i]
        self.mandar_claro(claro)
        anotar("   S2C RESPUESTA a %s: lote %d (%d B)" % (nombre, i, len(claro)))
        return True

    def mandar_todo(self):
        """Manda TODOS los lotes que queden, de una.

        ⭐ 22-oct: con el patron del log el cliente recibia 2 de 60 y se quedaba esperando el resto
        (el patron pide 3 mensajes suyos antes de seguir, y no los manda). Se cae despues leyendo
        `[ecx+0x18]` con ecx=0: un objeto que nunca se creo por falta de datos. El patron solo da la
        FORMA del dialogo y encima es aproximado (ver PATRON), asi que por omision se manda todo y
        que el cliente lo consuma a su ritmo: es un flujo TCP, los marcos llegan igual.
        PATRON_FIEL=1 vuelve al guion.
        """
        n = 0
        reservados = set(RESPUESTAS.values())
        while self.i_lote < len(self.lotes):
            if self.i_lote in reservados or self.lotes[self.i_lote] in LOTES_RESPUESTA:
                # es una respuesta: se guarda para cuando la pida
                self.i_lote += 1
                continue
            if not self.mandar_lote():
                break
            n += 1
        anotar("   S2C: mandados %d lotes de una (%d bytes de contenido)"
               % (n, sum(len(x) for x in self.lotes)))

    def seguir_patron(self):
        """Manda la rafaga de lotes que toca segun PATRON, y se detiene en el proximo turno del
        cliente. Agotado el patron, manda UN lote (asi el dialogo no se corta por falta de guion)."""
        if not self.lotes:
            return
        if self.i_patron >= len(PATRON):
            self.mandar_lote()
            return
        while self.i_patron < len(PATRON) and PATRON[self.i_patron] == "S":
            self.i_patron += 1
            if not self.mandar_lote():
                return
        if self.i_patron < len(PATRON):      # toca el cliente: se consume su turno y se espera
            self.i_patron += 1

    def data_received(self, d):
        if self.cerrada:
            return
        # ⭐ 22-oct: el registro CRUDO. El cliente manda `SendCheckVer` y `SendLogin` con 35 ms de
        # diferencia (su log: Network.cpp) y despues aborta la conexion; con el cierre abortivo los
        # bytes que no alcanzamos a leer se DESCARTAN, asi que sin esto no se sabe si el FF02 llego
        # y no lo supimos encuadrar, o si nunca llego.
        anotar(":%d <- %d bytes crudos: %s%s"
               % (self.puerto, len(d), d[:48].hex(" "), " ..." if len(d) > 48 else ""))
        self.buf += d
        ms, self.buf = marcos(self.buf)
        if self.buf:
            anotar("   ⚠ quedan %d bytes SIN ENCUADRAR: %s" % (len(self.buf), self.buf[:32].hex(" ")))
        for cmd, seq, cuerpo in ms:
            if self.cerrada:
                break
            if cmd == 0x04:
                anotar(":%d C2S FF04 hola (%d B): %s" % (self.puerto, len(cuerpo), cuerpo.hex()))
                r = FF04 + struct.pack("<I", int(time.time()))
                self.tr.write(marco(0x04, seq, r))
                anotar("   S2C FF04: %d bytes" % len(r))
            elif cmd == 0x02:
                anotar(":%d C2S FF02 login del juego (%d B)" % (self.puerto, len(cuerpo)))
                llave_con = self.llave
                if cuentas.identidad_ff02():
                    info = captura.leer_c2s_ff02_juego(cuerpo)
                    if info is None:
                        self._rechazar_ff02("cuerpo FF02 malformado o cifrado invalido")
                        return
                    gsn, usn, clave_c2s, ses_id_c2s = info["gsn"], info["usn"], info["s2"], info["sesion_id"]
                    ses = cuenta.sesion(gsn)
                    ahora = time.time()
                    if ses is None or ses.get("expira", 0) < ahora:
                        self._rechazar_ff02("sin sesion activa para gsn %d" % gsn)
                        return
                    clave_ses = ses.get("clave")
                    if not isinstance(clave_ses, str) or not isinstance(clave_c2s, str) or not hmac.compare_digest(clave_c2s, clave_ses):
                        # 23-nov (maduracion, cerebro), MEDIDO con el juego: al volver a entrar desde el selector (tras 角色选择)
                        # el FF02 de juego es mas corto (136 B, no 168) y no trae la clave en s2. Como en login.py: se acepta
                        # con gsn + sesion_id de la sesion VIVA, solo si el FF02 tiene esa forma corta. RECONEXION_SESION=0 lo apaga.
                        reconexion = ((os.environ.get("RECONEXION_SESION") or "1").strip().lower() in ("1", "si")
                                      and len(cuerpo) < 168 and ses_id_c2s and int(ses.get("sesion_id", 0)) == int(ses_id_c2s))
                        anotar("   FF02 de juego %d B: s1 %d B, s2 %d B, s3 %d B, s4 %d B; reconexion: %s" % (
                            len(cuerpo), len(info["s1"]), len(info["s2"]), len(info["s3"]), len(info["s4"]), "si" if reconexion else "no"))
                        if not reconexion:
                            self._rechazar_ff02("clave de sesion invalida para gsn %d" % gsn)
                            return
                    if not ses_id_c2s or int(ses.get("sesion_id", 0)) != int(ses_id_c2s):
                        self._rechazar_ff02("sesion_id invalido para gsn %d" % gsn)
                        return
                    u = cuentas.usuario_por_steamid(ses.get("usuario", ""))
                    if u is None or u.get("gsn") != gsn:
                        self._rechazar_ff02("usuario inexistente para gsn %d" % gsn)
                        return
                    if not usn or (usn not in (u.get("usns") or []) and usn != u.get("pendiente_usn")):
                        self._rechazar_ff02("usn %d no pertenece a gsn %d" % (usn, gsn))
                        return
                    cta = cuentas.por_usn(usn)
                    if cta is None:
                        self._rechazar_ff02("cuenta no encontrada para usn %d" % usn)
                        return
                    ses["expira"] = ahora + SESION_TTL
                    cuenta.guardar_sesion(gsn, ses)
                    for k_con, otra in list(estado.CONEXIONES.items()):
                        if otra is not self and (otra.cuenta or {}).get("usn") == usn:
                            anotar("   sesion duplicada: cierro la anterior")
                            estado.CONEXIONES.pop(k_con, None)
                            otra.cerrada = True
                            otra.tr.close()
                    self.cuenta = cta
                    self.k = k_para(usn)
                    self.llave = info["llave"]
                    llave_con = info["llave"]
                    # como el __init__ de siempre: sin REPRODUCIR los lotes van vacios, pero lotes_de_entrada arma igual la
                    # rafaga neutra (FF00) si falta lotes_S2C.bin (modo VPS)
                    lotes_base = fichas.lotes_de_entrada(captura.lotes_capturados() if REPRODUCIR else [], self.cuenta)
                    self.lotes = [captura.con_llave(x, llave_con) for x in lotes_base] if lotes_base else []
                    anotar("   cuenta por FF02: %s usn %d (sesion valida)" % (self.cuenta["nick"], usn))
                    anotar("   llave de hardware del cliente (PASE=si): %d B -> usada en S2C FF02" % len(cuerpo))
                elif ajustes.pase_activo():
                    llave_cli = captura.llave_de_c2s_ff02(cuerpo)
                    if llave_cli is not None:
                        self.llave = llave_cli
                        llave_con = llave_cli
                        if REPRODUCIR and self.lotes:
                            self.lotes = [captura.con_llave(x, llave_con) for x in self.lotes]
                        anotar("   llave de hardware del cliente (PASE=si): %d B -> usada en S2C FF02" % len(cuerpo))
                    else:
                        anotar("   ⚠ PASE=si: C2S FF02 (%d B) sin llave valida; uso llave del servidor" % len(cuerpo))
                if FF02_CUERPO is not None:
                    r = (FF02_CUERPO[:1] + struct.pack("<I", (llave_con ^ LLAVE_SAL) & 0xFFFFFFFF) + FF02_CUERPO[5:]
                         if ajustes.pase_activo() and llave_con is not None else FF02_CUERPO)
                else:
                    r = neutro.ff02_cuerpo(CLAVE, llave_con)
                self.tr.write(marco(0x02, seq, r))
                anotar("   S2C FF02: %s, clave de 256 bytes (%d B)"
                       % ("DE LA CAPTURA" if FF02_CUERPO is not None else "armado a mano", len(r)))
                # el oficial arranca solo despues del login
                if ajustes.PATRON_FIEL:
                    self.seguir_patron()
                else:
                    self.mandar_todo()
            elif cmd == 0x55:
                if cuentas.identidad_ff02() and self.cuenta is None:
                    self._rechazar_ff02("FF55 sin FF02 autenticado")
                    return
                claro = descifrar(cuerpo, CLAVE)
                dentro = "FF%02X" % claro[1] if len(claro) > 1 and claro[0] == 0xFF else "?"
                nom = self.nombre_pedido(claro)
                anotar(":%d C2S FF55 (%d B) -> adentro %s%s%s"
                       % (self.puerto, len(cuerpo), dentro, ("  pide: " + nom) if nom else "",
                          "  [%s]" % " ".join("FF%X(%d)" % (c, n) for c, n in comandos_de(claro))))
                # 01-nov: primero los manejadores (manejadores.py, docs/PLAN_STEAM_COMPLETO.md): los de logica propia y, al final de
                # la lista, los que contestan de la captura (practica.py: FF3A / FF57; cuenta_local.py: crear personaje, sala grabada)
                manejadores_al_dia()
                todos_ = captura.internos_todos(claro)
                propios = [c_ for c_, s_, cu_ in todos_ if manejadores.despachar(self, c_, s_, cu_)]
                if propios and len(propios) == len(todos_):
                    pass      # todo lo que vino ya tiene respuesta propia
                elif nom in NO_RESPONDER:
                    anotar("   (NO_RESPONDER: %s queda sin contestar)" % nom)
                elif nom and POR_ID and self.responder_por_id(claro):
                    pass
                elif nom and self.responder(nom):
                    pass
                elif nom and FABRICAR and self.responder_vacio(claro, nom):
                    pass
                else:
                    self.seguir_patron()
            else:
                anotar(":%d C2S FF%02X (%d B) (sin respuesta todavia)" % (self.puerto, cmd, len(cuerpo)))

    def connection_lost(self, exc):
        if estado.CONEXIONES.get(self.id_con) is self:
            del estado.CONEXIONES[self.id_con]
        manejadores.desconectado(self)     # 01-nov: la conexion caida saca al jugador de su sala (como salir)
        anotar(":%d se cerro la conexion (%s)  lotes entregados: %d/%d%s"
               % (self.puerto, exc or "normal", self.i_lote, len(self.lotes),
                  ("   ⚠ %d bytes sin encuadrar: %s" % (len(self.buf), self.buf[:32].hex(" ")))
                  if self.buf else ""))


async def main():
    estado.anotar = anotar
    recarga.iniciar(anotar)
    cuenta.preparar(anotar)          # M09: con CUENTA_SQLITE=1, cuentas.db listo (y migrado) al arrancar
    anotar("llave de hardware: %s (la de la captura: %s)%s" % (
        "0x%08x" % LLAVE if LLAVE is not None else "NO SE PUDO LEER", "0x%08x" % LLAVE_CAP if LLAVE_CAP else "-",
        "" if LLAVE is None or LLAVE == LLAVE_CAP else " -> va la de ESTA maquina en el FF02 y en los FF05"))
    for h in HOSTS:
        for p in PUERTOS:
            await asyncio.get_running_loop().create_server(lambda p=p: Juego(p), h, p)
            anotar("escuchando en %s:%d" % (h, p))
    await panel_interno.iniciar(anotar)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
