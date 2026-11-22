# -*- coding: utf-8 -*-
r"""textos.py (13-nov, ficha 137) — el texto que viaja por el cable del juego, en GB18030.

El cliente chino habla GBK. GB18030 es un SUPERCONJUNTO: todo lo que GBK codifica o decodifica da LOS MISMOS bytes y las mismas letras
(MEDIDO con los codecs de Python: 21.919 letras que 'gbk' codifica dan los mismos bytes con 'gb18030', 0 diferencias; 38.303
secuencias de 1 y 2 bytes que 'gbk' decodifica dan la misma letra, 0 diferencias; prueba en test_textos.py). Lo que cambia es solo
lo que GBK NO puede: una letra como `ñ` o el hangul sale como 4 bytes (81 30 8a 39) en vez de `?`, y esos 4 bytes decodifican a la
letra en vez de a dos `?`.

Los topes de largo del cable son en BYTES (apodo 12 o 13, titulo 32...). `cortar` corta a n bytes igual que `b[:n]` salvo en un caso: si el
corte caeria en el MEDIO de una secuencia de 4 bytes, corta antes de ella (una letra de 4 bytes entra entera o no entra). Para texto
GBK (sin secuencias de 4 bytes) devuelve exactamente `b[:n]`, como antes.
"""

CODIFICACION = "gb18030"


def _es_de_cuatro(b, i):
    """True si en b[i:i+4] hay una secuencia GB18030 de 4 bytes: 81..fe 30..39 81..fe 30..39."""
    return (i + 3 < len(b) and 0x81 <= b[i] <= 0xFE and 0x30 <= b[i + 1] <= 0x39
            and 0x81 <= b[i + 2] <= 0xFE and 0x30 <= b[i + 3] <= 0x39)


def cortar(b, n):
    """Los primeros n bytes de b sin partir una secuencia de 4 bytes (si no hay ninguna que se parta: b[:n] tal cual)."""
    if n is None or len(b) <= n:
        return b
    i = 0
    while i < n:
        if b[i] < 0x80:
            i += 1
        elif _es_de_cuatro(b, i):
            if i + 4 > n:
                return b[:i]
            i += 4
        else:
            i += 2
    return b[:n]


def codificar(t, n=None):
    """str -> bytes GB18030 (lo que GBK no tiene sale en 4 bytes, no en '?'), cortado a n bytes en frontera de letra."""
    return cortar(t.encode(CODIFICACION, "replace"), n)


def decodificar(b):
    """bytes del cable -> str (GB18030)."""
    return b.decode(CODIFICACION, "replace")


def decodificar_estricto_gbk(b):
    """bytes -> str como `b.decode("gbk")` (estricto: UnicodeDecodeError si no es GBK), MAS las letras de 4 bytes (`ñ`, hangul...) que GBK no
    tiene. Ficha 141 (nombre de mascota de granja.py): GB18030 acepta ademas ~2150 codigos de 2 bytes que GBK rechaza (area de usuario,
    extensiones: 53 son letras), asi que `b.decode("gb18030")` ensancharia la validacion; esta funcion no: para todo texto sin una
    letra de 4 bytes es EXACTAMENTE `b.decode("gbk")` (mismo resultado o mismo error)."""
    salida, trozo, i = [], 0, 0
    while i < len(b):
        if b[i] < 0x80:
            i += 1
        elif _es_de_cuatro(b, i):
            salida.append(b[trozo:i].decode("gbk"))
            salida.append(b[i:i + 4].decode(CODIFICACION))
            i += 4
            trozo = i
        else:
            i += 2
    salida.append(b[trozo:].decode("gbk"))
    return "".join(salida)
