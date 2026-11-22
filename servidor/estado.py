# -*- coding: utf-8 -*-
r"""estado.py (01-nov) — lo VIVO del servidor de juego (un solo proceso para 28008 y los puertos de las cuentas locales):
quien esta conectado, las salas abiertas, lo que hay que recordar entre una recarga y otra, y los temporizadores.

Este modulo NO se recarga en caliente (recarga.py mira los demas .py): asi las salas, CERRADAS y PROPUESTAS sobreviven a
cada cambio del codigo. Aca NO hay logica: `Sala` es SOLO DE DATOS, y las reglas (sentar, levantar, jugadores, el byte de
estado...) son funciones de salas.py que reciben la sala; una sala creada antes de recargar salas.py usa siempre el
codigo de ahora. Cambiar la FORMA de algo de este archivo (campos nuevos, clases) pide reiniciar el servidor.
La conexion es juego.Juego (la red): sus campos estan declarados en su __init__ (juego.py), no aca.
"""
import asyncio
import itertools
import sys

CONEXIONES = {}            # puerto -> la conexion (juego.Juego) viva de ese puerto
SALAS = {}                 # numero de sala -> Sala (abajo)
NUMEROS_DE_SALA = itertools.count(1)
CERRADAS = {}              # numero de sala -> hora en que se cerro (salas.numero_libre no lo reusa enseguida)
PROPUESTAS = {}            # usn del que propone -> (usn del propuesto, Index del anillo, hora): pedidos de pareja pendientes (ficha 74)


def anotar(txt):
    """El registro del servidor (juego.py pone aca su `anotar` al arrancar)."""
    print(txt, flush=True)


class Sala:
    """Una sala abierta. SOLO DATOS: los valores iniciales y quien escribe/lee cada campo, una linea por campo."""

    def __init__(self, numero, pedido, anfitrion, canal=0):
        self.numero = numero              # el numero visible de la sala (clave de SALAS); lo da salas.numero_libre
        self.pedido = pedido              # el dict del FF1F5 tal cual se leyo (salas.leer_crear_sala)
        self.canal = canal                # 0..3: el canal de la lista con el que se creo (u8 del FF1F5); lo lee la lista FF1F6
        self.modo = pedido["modo"]        # el modo (u32 sin el 0x40000); lo cambia salas.cambiar_modo
        self.titulo = pedido["titulo"]    # bytes GBK; lo cambia salas.cambiar_modo
        self.clave = pedido["clave"]      # bytes; lo cambia salas.cambiar_modo
        self.anfitrion = anfitrion        # la conexion del anfitrion (None si la sala quedo sin nadie); salas.levantar la hereda
        self.orden = ()                   # asientos en orden de entrada (salas.orden_asientos); lo pone salas.nueva_sala
        self.asientos = {}                # asiento -> conexion; salas.sentar/levantar (salas.nueva_sala sienta al anfitrion)
        self.max = 6                      # lugares de la sala (la lista FF6E)
        self.cancion = None               # u16 de la ultima cancion elegida con FF1C sub 0 (None = al azar); la lee carrera.py
        self.grupo = None                 # 1 o 2, el del FF132 del cooperativo (None = no se eligio); la lee carrera.py
        self.pista = None                 # u16 de la pista elegida con FF1B (None = no se eligio; 0 tras un cambio de modo)
        self.cambio_sin_jugar = False     # FF1F8: el oficial deja UN cambio de modo entre partida y partida
        self.estado = 0                   # byte de estado de la lista: bit 0x02 = en carrera; se cambia con salas.poner_estado
        self.equipos = None               # {id(conexion): equipo} (None = sin calcular todavia); lo arma salas.equipo_de
        self.carrera = None               # la carrera en curso (dict: magic, cancion, cargados, go, ff28, ...) o None; carrera.py
        self.premio = None                # el tablero de cajas del cooperativo tras atrapar al gorila, o None; carrera.py
        self.vuelta_pendiente = None      # set de id(conexion) que faltan volver a la sala tras el cartel del coop, o None
        self.vuelta_desde = 0.0           # hora del cartel del coop (time.time) desde la que cuenta la vuelta; carrera.py
        self.cerradas = None              # {id(conexion): hora} de las cajas ya cerradas (None = no hay); carrera.py


def _disparar(destino, args):
    """Busca `modulo.funcion` AHORA (en el modulo ya recargado) y la llama; si ya no existe o falla, una linea y nada mas."""
    modulo, _, nombre = destino.partition(".")
    f = getattr(sys.modules.get(modulo), nombre, None)
    if not callable(f):
        anotar("   ⚠ temporizador a %s: esa funcion ya no existe, no se hace nada" % destino)
        return
    try:
        f(*args)
    except Exception as e:                                               # noqa: BLE001
        anotar("   ⛔ temporizador %s: %r" % (destino, e))


def mas_tarde(segundos, destino, *args):
    """Arma un temporizador a `destino` = "modulo.funcion" (texto, no la funcion): al disparar se busca por nombre en el
    modulo de turno, asi una recarga entre el armado y el disparo llama a la funcion NUEVA. Los argumentos van ya
    calculados (numeros, textos, objetos), no se vuelven a calcular al disparar."""
    try:
        bucle = asyncio.get_running_loop()
    except RuntimeError:
        bucle = asyncio.get_event_loop()
    return bucle.call_later(segundos, _disparar, destino, args)
