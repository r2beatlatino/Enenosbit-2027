# -*- coding: utf-8 -*-
r"""sello.py (12-nov, ficha 97) — el SELLO de 36 bytes que el cliente chino exige en los avisos por nombre de FF255 (`match.*`) y FF246
(`modAct.getActList`, `familySys.*`): el tercer texto del sobre `[u64 A][u64 id][s nombre][s JSON][u32 36][36 B]`.

DE DONDE SALE CADA CONSTANTE (LEIDO en `Game_g21_local.exe`, manejador de `match.signin` `0x028edc00`; MEDIDO: valida 48 de 48 mensajes
S2C grabados que traen esos 36 B — 45 `modAct.getActList`, 1 `match.signin`, 2 `familySys` —, ver docs/tablero/layouts/rankedMatch.md §1):
  - bloque de 32 B: ceros; el byte `i` del JSON se SUMA (mod 256) en la posicion `i mod 32`          (0x028edc76..0x028edc8a)
  - 8 palabras u32 little-endian del bloque = los datos que se cifran
  - llave de 4 palabras: [largo del JSON, 0x1a2e4d9c, nonce ^ 0x1a2e4d9c, 0xd13f1c9f]              (0x028edc92..0x028edca6)
  - XXTEA estandar de n = 8 palabras, 6 vueltas, delta = 0x1a2e4d9c                                  (0x028edcb4..0x028ede83)
  - el cliente compara las 8 palabras con los 32 primeros bytes del sello; el NONCE es el u32 de los 4 ultimos bytes (offset 0x20,
    `mov eax,[eax+0x20]` en 0x028edc56)                                                              (0x028ede94..0x028edeb1)
El nonce lo elige quien manda (el oficial: al azar, distinto en cada mensaje). Se recarga en caliente (recarga.RECARGABLES).
"""
import os
import struct

DELTA = 0x1A2E4D9C
K3 = 0xD13F1C9F
M = 0xFFFFFFFF
VUELTAS = 6


def _bloque(js):
    b = bytearray(32)
    for i, c in enumerate(js):
        b[i % 32] = (b[i % 32] + c) & 255
    return bytes(b)


def calcular(js, nonce):
    """Los 32 B cifrados para ese JSON (bytes) y ese nonce (u32)."""
    v = list(struct.unpack("<8I", _bloque(js)))
    k = [len(js) & M, DELTA, (nonce ^ DELTA) & M, K3]
    s = 0
    for _ in range(VUELTAS):
        s = (s + DELTA) & M
        e = (s >> 2) & 3
        for p in range(8):
            y = v[(p + 1) % 8]
            z = v[(p - 1) % 8]
            mx = ((((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((s ^ y) + (k[(p & 3) ^ e] ^ z))) & M
            v[p] = (v[p] + mx) & M
    return struct.pack("<8I", *v)


def sellar(js, nonce=None):
    """Los 36 B del sello (32 cifrados + nonce). `js` bytes o str; nonce None = al azar (como el oficial)."""
    if isinstance(js, str):
        js = js.encode("utf-8")
    if nonce is None:
        nonce = struct.unpack("<I", os.urandom(4))[0]
    return calcular(js, nonce) + struct.pack("<I", nonce)


def valido(js, sello):
    """True si `sello` (36 B) corresponde a `js`."""
    if isinstance(js, str):
        js = js.encode("utf-8")
    return len(sello) == 36 and calcular(js, struct.unpack_from("<I", sello, 32)[0]) == sello[:32]
