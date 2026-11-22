# -*- coding: utf-8 -*-
r"""ajustes.py (ficha 37) — el UNICO lugar donde el servidor local mira variables de entorno y calcula rutas.

Sin estado y sin logica: solo valores. NO se recarga en vivo (cambiar algo aca = reiniciar el servidor, como los puertos).
Cada variable de entorno que lee el servidor esta aca, una vez, con una linea de comentario. Se leen al importar este
archivo (el servidor y el login son procesos aparte: cada uno la suya), salvo las dos funciones del final, que se leen
en el momento porque cambian en medio de una corrida (CUENTA_DATOS la cambian las pruebas; PUERTO_JUEGO la fija login.py).
"""
import os
import struct


def numero_capturado(ruta, cmd, desplazamiento, omision=0):
    """Identificador local: se lee solo si existe captura, nunca viaja como literal.

    FF01 login: gsn u32 en +4; FF02 login: usn/sesion u32 en +1.
    Sin captura se usa el valor neutro indicado por quien llama.
    """
    try:
        with open(ruta, 'rb') as f:
            raw = f.read()
        off = 0
        for _ in range(len(raw)//8+1):
            if off+8 > len(raw) or raw[off] != 255:
                break
            n = struct.unpack_from('<I',raw,off+4)[0]
            if off+8+n > len(raw):
                break
            if raw[off+1] == cmd and n >= desplazamiento+4:
                return struct.unpack_from('<I',raw,off+8+desplazamiento)[0]
            off += 8+n
    except OSError:
        pass
    return omision

# ---------- rutas (todas salen de donde esta este archivo, asi una copia temporal usa SU datos/) ----------
AQUI = os.path.dirname(os.path.abspath(__file__))            # servidor_local/servidor/
BASE = os.path.dirname(AQUI)                                  # servidor_local/
DATOS = os.path.join(BASE, "datos")                           # lo preparado por herramientas/preparar_*.py (y cuenta.json)
REGISTROS = os.environ.get("RECARGA_REGISTROS") or os.path.join(BASE, "registros")   # lo que se anota (juego_*.txt, login_*.txt, recarga.json)

RUTA_CAP_JUEGO = os.path.join(DATOS, "juego_S2C.bin")         # copia de tools/net/volcado_28008_S2C.bin (FF04/FF02 del oficial)
RUTA_LOTES = os.path.join(DATOS, "lotes_S2C.bin")             # los 60 lotes de la sesion del 22-oct, ya descifrados
RUTA_RESPUESTAS = os.path.join(DATOS, "respuestas_S2C.bin")   # todos los FF55 del volcado, descifrados (respuestas por metodo)
RUTA_CREAR_SALA = os.path.join(DATOS, "crear_sala_S2C.bin")   # la respuesta del oficial a crear sala (preparar_crear_sala.py)
RUTA_UNIRSE = os.path.join(DATOS, "unirse_S2C.bin")           # la respuesta del oficial a entrar a una sala (preparar_unirse.py)
RUTA_CARTEL = os.path.join(DATOS, "cartel_S2C.bin")           # el cartel de resultados del oficial (preparar_cartel.py)
RUTA_EXAMINAR = os.path.join(DATOS, "examinar_S2C.bin")       # la ficha FF77 del oficial (preparar_examinar.py)
RUTA_CHARTS = os.path.join(DATOS, "charts_1a1.json")          # canciones con chart 1 a 1 ("jugables")
DIR_CHARTS = os.path.join(DATOS, "charts")                    # <songid>.bin: el chart de cada cancion
RUTA_PRUEBAS = os.path.join(DATOS, "pruebas.json")            # ajustes de PRUEBA que carrera.py lee en cada START
RUTA_LOGIN_CAP = os.path.join(DATOS, "login_S2C.bin")         # copia de tools/net/volcado_28004_S2C.bin (lo que mando el login oficial)
RUTA_FF0B = os.path.join(DATOS, "ff0b.hex")                   # el FF0B (lista de personajes) capturado, en hexadecimal

# ---------- variables de entorno de juego.py ----------
PUERTOS_JUEGO = [int(p) for p in os.environ.get("PUERTOS_JUEGO", "28008").split(",")]   # PUERTOS_JUEGO: puertos del juego (coma)
CUENTAS_LOCALES = os.environ.get("CUENTAS_LOCALES", "1") == "1"   # CUENTAS_LOCALES=0 apaga las cuentas locales (juego y login)
HOSTS = [h.strip() for h in os.environ.get("HOSTS", "127.0.0.1,192.168.31.100").split(",") if h.strip()]   # HOSTS: direcciones donde escuchan juego y login
CLAVE_PROPIA = os.environ.get("CLAVE_PROPIA") == "1"          # CLAVE_PROPIA=1: clave de cifrado inventada en vez de la capturada
LLAVE = os.environ.get("LLAVE")                               # LLAVE=<hex>: fija a mano la llave de hardware (None = no fijada)
LLAVE_CAPTURADA = os.environ.get("LLAVE_CAPTURADA") == "1"    # LLAVE_CAPTURADA=1: manda la llave de hardware de la captura
REPRODUCIR = os.environ.get("REPRODUCIR", "1") == "1"         # REPRODUCIR=0: no manda los lotes capturados
CUANTOS_LOTES = int(os.environ.get("LOTES", "60"))            # LOTES: cuantos lotes capturados (los ultimos N) se usan
PATRON = os.environ.get(                                      # PATRON: guion S/C del intercalado (solo con PATRON_FIEL=1)
    "PATRON", "SSCCCSSSSSSSCCCCCSSCCCCCCSSSSSSSSSCSSSSSSCSCSSCSCSCSSSCSCSCSCSCSCSSSCSCSCSCSC")
PATRON_FIEL = os.environ.get("PATRON_FIEL") == "1"            # PATRON_FIEL=1: sigue el guion PATRON en vez de mandar todo de una
POR_ID = os.environ.get("POR_ID", "1") == "1"                 # POR_ID=0: vuelve a responder por lote en vez de por pedido
NO_RESPONDER = {x for x in os.environ.get("NO_RESPONDER", "").split(",") if x}   # NO_RESPONDER=a,b: metodos que quedan sin contestar
LISTA_CANCIONES = os.environ.get("LISTA_CANCIONES", "1") == "1"   # LISTA_CANCIONES=0: manda la lista de canciones capturada tal cual
LICENCIA = int(os.environ.get("LICENCIA", "65535"))           # LICENCIA: m_wLicense del FF00 (0 = la de la captura)
FABRICAR = os.environ.get("FABRICAR", "0") == "1"             # FABRICAR=1: fabrica respuestas vacias (apagado: mata al cliente)

# ---------- variable de cuentas.py ----------
PUERTO_CUENTAS = int(os.environ.get("PUERTO_CUENTAS", "28101"))   # PUERTO_CUENTAS: primer puerto de juego de las cuentas locales

# ---------- variables de otros modulos ----------
SALDO_INICIAL = int(os.environ.get("SALDO_INICIAL", "10000"))     # SALDO_INICIAL: diamantes de una cuenta nueva (tienda.py)
MAPA_COOP = os.environ.get("MAPA_COOP")                           # MAPA_COOP: escenario del cooperativo (None = 9 o 10 segun el grupo)
MANEJADORES_STEAM = os.environ.get("MANEJADORES_STEAM", "1") == "1"   # MANEJADORES_STEAM=0 apaga los manejadores propios (manejadores.py)

# ---------- variables de login.py ----------
PUERTOS_LOGIN = [int(p) for p in os.environ.get("PUERTOS", "28004").split(",")]   # PUERTOS: puertos del login (el 28008 es de juego.py)
FF01_FIEL = os.environ.get("FF01_FIEL", "0") == "1"           # FF01_FIEL=1: respuesta FF01 fiel de 139 B (la simple de 58 B es la de produccion)
FF01_ARMADO = os.environ.get("FF01_ARMADO") == "1"            # FF01_ARMADO=1: FF01 armado a mano en vez de los bytes de la captura
FF02_ARMADO = os.environ.get("FF02_ARMADO") == "1"            # FF02_ARMADO=1: CmdLogin armado a mano en vez del de la captura
USN = os.environ.get("USN")                                   # Sin variable: identificador de captura o neutro.
CLAVE_LOGIN = os.environ.get("CLAVE", "local")                # CLAVE: la clave que va en la respuesta FF01 simple
SESION = int(os.environ.get("SESION") or numero_capturado(RUTA_LOGIN_CAP, 2, 1, 1))  # INVENTADO sin captura: sesion 1.
IP_JUEGO = os.environ.get("IP_JUEGO", "192.168.31.100")       # IP_JUEGO: la IP del servidor de juego que el login anuncia
FF03_CUERPO = os.environ.get("FF03_CUERPO")                   # FF03_CUERPO=<hex>: pisa el cuerpo de la lista de canales (None = no)
CANAL = os.environ.get("CANAL", "Local")                      # CANAL: nombre del canal en la lista armada a mano
URL_TORNEO = os.environ.get("URL_TORNEO", "")                 # URL_TORNEO: url de torneo en la lista armada a mano
SIEMPRE_FF0B = os.environ.get("SIEMPRE_FF0B") == "1"          # SIEMPRE_FF0B=1: manda el FF0B tambien a quien ya trae personaje
CMDLOGIN_SIEMPRE = os.environ.get("CMDLOGIN_SIEMPRE") == "1"  # CMDLOGIN_SIEMPRE=1: manda el CmdLogin tambien al FF02 sin personaje
LISTA_A_MANO = os.environ.get("LISTA_A_MANO") == "1"          # LISTA_A_MANO=1: lista de canales armada a mano en vez de la capturada
SIN_CANAL_BAILE = os.environ.get("SIN_CANAL_BAILE") == "1"    # SIN_CANAL_BAILE=1: saca el canal 0x28 (tipo 0x0d, 竞舞) del FF03 para abrir Modo Baile en el principal (apagada por omision: cambia bytes de la captura)
PASE = (os.environ.get("PASE") or "").strip().lower() in ("si", "1")   # PASE=si: exige pase Ed25519 de Cuenta Eñeños en el FF01 (apagada por omision)
IDENTIDAD_FF02 = (os.environ.get("IDENTIDAD_FF02") or "si").strip().lower() in ("si", "1")   # IDENTIDAD_FF02=si: en modo PASE identifica por C2S FF02 de juego y sin tope de 8 cuentas (0 vuelve a puerto por cuenta)
R2_PASE_JUEGO = (os.environ.get("R2_PASE_JUEGO") or "").strip() or "r2beat-moderno"   # R2_PASE_JUEGO: `aud` esperado en el pase
R2_CUENTAS_CLAVE_PUBLICA = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()   # R2_CUENTAS_CLAVE_PUBLICA: JWK/JWKS/hex/b64u Ed25519
R2_CUENTAS_URL = (os.environ.get("R2_CUENTAS_URL") or "").strip()   # R2_CUENTAS_URL: URL base de Cuenta Eñeños (solo al arrancar si falta la clave)


# ---------- las que se leen EN EL MOMENTO ----------
def pase_activo():
    """PASE=si (o 1): True si el modo pase esta encendido en este momento."""
    return (os.environ.get("PASE") or "").strip().lower() in ("si", "1")


def identidad_ff02():
    """IDENTIDAD_FF02=si (omision si): True si pase_activo() y la llave esta prendida en este momento."""
    if not pase_activo():
        return False
    if "IDENTIDAD_FF02" in os.environ:
        return (os.environ.get("IDENTIDAD_FF02") or "si").strip().lower() in ("si", "1")
    return bool(IDENTIDAD_FF02)


def puerto_juego():
    """PUERTO_JUEGO: el puerto de juego que el login pone en la lista armada a mano (28008 si no se fijo)."""
    return int(os.environ.get("PUERTO_JUEGO", "28008"))


def fijar_puerto_juego(puerto):
    """login.py lo cambia en medio de una corrida (cuando no puede poner el puerto de la cuenta en la lista capturada)."""
    os.environ["PUERTO_JUEGO"] = str(puerto)


def carpeta_cuenta():
    """CUENTA_DATOS: la carpeta donde cuenta.py guarda cuenta.json (las pruebas la cambian); si no, datos/."""
    return os.environ.get("CUENTA_DATOS") or DATOS


def carpeta_registros_recarga():
    """RECARGA_REGISTROS: donde recarga.py escribe recarga.json (las pruebas la cambian); si no, registros/."""
    return os.environ.get("RECARGA_REGISTROS") or REGISTROS
