# -*- coding: utf-8 -*-
r"""manejadores.py (01-nov) — los comandos que el servidor CONTESTA CON LOGICA PROPIA (no copiando la captura), uno por
funcion del juego (docs/PLAN_STEAM_COMPLETO.md). juego.py llama a `despachar` con cada comando interno que llega
adentro de un FF55, ANTES de los caminos de la captura por metodo: si devuelve True, el comando ya se contesto. Los que
contestan copiando o reconstruyendo de la captura (practica.py, cuenta_local.py) van al FINAL de la lista.

Se recarga en caliente (recarga.py mira los archivos, de a un modulo, y rechaza los rotos dejando el anterior):
se puede cambiar un manejador con el servidor andando, sin cortar a nadie. Los modulos se recargan EN EL MISMO objeto,
asi que `MODULOS` y `despachar` siempre ven lo nuevo sin reapuntar nada. El estado compartido (salas, conexiones) vive en estado.py, que no se recarga.

MANEJADORES_STEAM=0 apaga los de logica propia: el servidor vuelve a ser el de la captura (el control), que sigue
contestando por practica.py y cuenta_local.py (BASE).
"""
import os

import ajustes
import boda
import carrera
import casa
import charla
import correo
import cuenta_local
import fichas
import gemas
import granja
import jardin
import liga
import lobby_metodos
import misiones
import practica
import progresion
import ranking
import sala_magica
import salas
import social
import baile
import tienda

# misiones va PRIMERO: su 0x3A de 5 B (historia) tiene que verse antes que el "empezar cancion" (practica.py); y su 0x7F/0x57
# solo observan y devuelven False. practica y cuenta_local van al final: contestan lo que los demas dejaron pasar.
MODULOS = [misiones, casa, sala_magica, baile, liga, lobby_metodos, salas, charla, tienda, carrera, social, boda, correo, gemas, granja, jardin, progresion, ranking, practica, cuenta_local]
BASE = [practica, cuenta_local]       # los que contestan tambien con MANEJADORES_STEAM=0


def recargar(nombres=None):
    """A pedido: recarga de a un modulo (recarga.py), uno que falla no frena a los demas. Devuelve {nombre: ok}."""
    import recarga
    return {mod.__name__: recarga.recargar_modulo(mod.__name__)
            for mod in MODULOS if nombres is None or mod.__name__ in nombres}


def ficha_ff00(cuerpo, cuenta):
    """La ficha FF00 de una cuenta local, con su inventario (fichas.py)."""
    return fichas.ficha_ff00(cuerpo, cuenta)


def lote_para(lote, cuenta):
    """El lote capturado con la ropa PUESTA de la cuenta local (fichas.py)."""
    return fichas.lote_para(lote, cuenta)


def desconectado(con):
    """La conexion se cayo: lo mismo que salir (la sala, el anfitrion)."""
    try:
        salas.sacar_de_su_sala(con)
    except Exception as e:                                               # noqa: BLE001
        salas.anotar("   ⛔ al desconectar: %r" % e)
    try:
        sala_magica.desconectado(con)    # ficha 96: sale de la cola de la sala magica (llave SALA_MAGICA)
    except Exception as e:                                               # noqa: BLE001
        salas.anotar("   ⛔ al sacar de la cola magica: %r" % e)
    try:
        boda.desconectado(con)       # ficha 76: un pedido de matrimonio pendiente se cancela (llave BODA)
    except Exception as e:                                               # noqa: BLE001
        salas.anotar("   ⛔ al cancelar el pedido de boda: %r" % e)
    try:
        social.desconectado(con)     # ficha 71: "fuera de linea" a los amigos conectados (llave FUERA_DE_LINEA)
    except Exception as e:                                               # noqa: BLE001
        salas.anotar("   ⛔ al avisar fuera de linea: %r" % e)


def despachar(con, cmd, seq, cuerpo):
    """Prueba el comando en cada modulo, en orden; el primero que lo contesta (True) gana. False si nadie."""
    modulos = BASE
    if ajustes.MANEJADORES_STEAM:
        modulos = MODULOS
        try:
            carrera.revisar()
        except Exception as e:                                           # noqa: BLE001
            carrera.anotar("   ⛔ carrera.revisar: %r" % e)
    if ajustes.MANEJADORES_STEAM:
        progresion.tick(con)         # ficha 83: cada ~60 s de conexion, Stay y los FF1F9/FF1FE propios (solo cuentas locales)
    for mod in modulos:
        f = mod.MANEJADORES.get(cmd)
        if f is not None and f(con, seq, cuerpo):
            return True
    return False
