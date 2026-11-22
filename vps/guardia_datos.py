"""Ficha 168: inspeccion local, solo lectura; nunca muestra contenidos sensibles.

Uso: python -B servidor_local/vps/guardia_datos.py
Opcional --raiz PAQUETE --capturas DATOS_ORIGINALES.
Revisa bytes, literales Python y cadenas hexadecimales decodificadas.
Sin excepciones para ceros, tablas publicas o comentarios: cualquier tramo
comun de 16 bytes cuenta. Por eso una coincidencia NO prueba una filtracion,
pero SI bloquea la subida hasta revision. Salida 0 solo sin coincidencias.
No importa modulos del servidor ni abre bases de cuentas ni registros.
"""
import argparse
import ast
import ctypes
from pathlib import Path
import re
import struct

CAPTURAS = ('login_S2C.bin', 'juego_S2C.bin', 'lotes_S2C.bin',
            'respuestas_S2C.bin', 'crear_sala_S2C.bin', 'unirse_S2C.bin',
            'cartel_S2C.bin', 'examinar_S2C.bin', 'ff0b.hex', 'medallas_oninit.hex')


def cuerpo(raw, cmd):
    off = 0
    for _ in range(len(raw)//8+1):
        if off+8 > len(raw) or raw[off] != 255:
            break
        n = struct.unpack_from('<I', raw, off+4)[0]
        if off+8+n > len(raw):
            break
        if raw[off+1] == cmd:
            return raw[off+8:off+8+n]
        off += 8+n
    raise ValueError('captura sin comando requerido')


def objetivos(dat, codigo):
    # Se ejecutan solo los dos lectores puros de campos ya documentados.
    tree = ast.parse((codigo/'servidor/login.py').read_text(encoding='utf8'))
    fs = [x for x in tree.body if isinstance(x, ast.FunctionDef)
          and x.name in ('_varint', 'leer_campos')]
    assert len(fs) == 2
    scope = {}
    exec(compile(ast.Module(body=fs, type_ignores=[]), '<lectores de campos>', 'exec'), scope)
    c = cuerpo((dat/'login_S2C.bin').read_bytes(), 1)
    gsn = struct.unpack_from('<I', c, 4)[0]
    n = struct.unpack_from('<I', c, 8)[0]
    sid = c[12:12+n]
    assert sid and sid.isdigit()
    ff = bytes.fromhex((dat/'ff0b.hex').read_text(encoding='ascii').strip())
    n = struct.unpack_from('<I', ff, 3)[0]
    fields, _ = scope['leer_campos'](ff[7:7+n])
    vals = {i:v for i,t,v in fields[0][2]}
    usn, nick = vals[0], vals[8]
    assert isinstance(nick, bytes) and nick
    pats = [('gsn', str(gsn).encode()), ('gsn_bin', struct.pack('<I', gsn)),
            ('usn', str(usn).encode()), ('usn_bin', struct.pack('<I', usn)),
            ('identidad', sid), ('apodo', nick),
            ('apodo_utf8', nick.decode('gb18030').encode('utf8'))]
    for nombre, numero in (('gsn',gsn),('usn',usn)):
        for width in (0,6,8):
            for upper in (False,True):
                text = format(numero, ('0'+str(width) if width else '')+('X' if upper else 'x'))
                pats.append((nombre+'_hex_'+str(width)+str(upper),text.encode()))
    # Solo la llave calculada; no se guarda ni imprime el adaptador o su MAC.
    buf = ctypes.create_string_buffer(0x8000)
    size = ctypes.c_ulong(len(buf))
    assert ctypes.windll.iphlpapi.GetAdaptersInfo(buf, ctypes.byref(size)) == 0
    off = struct.calcsize('P')+4+260+132
    off += (-off) % 4
    assert struct.unpack_from('<I', buf.raw, off)[0] >= 6
    a = buf.raw[off+4:off+12]
    key = (a[1]<<24) | (a[3]<<16) | (a[5]<<8) | a[2]
    pats += [('llave_bin', struct.pack('<I', key)), ('llave', str(key).encode()),
             ('llave_hex', format(key, '08x').encode()), ('llave_HEX', format(key, '08X').encode())]
    return pats


def archivos(root):
    found = set()
    for line in (root/'vps/archivos_que_viajan.txt').read_text(encoding='utf8').splitlines():
        rel = line.strip()
        if not rel or rel.startswith('#'):
            continue
        p = (root/rel).resolve()
        assert p.is_relative_to(root.resolve()), 'ruta fuera de paquete'
        assert p.exists(), 'entrada faltante'
        if p.is_dir():
            found.update(x for x in p.rglob('*') if x.is_file())
        else:
            found.add(p)
    found.add(root/'vps/guardia_datos.py')
    return sorted(found)


def vistas(p):
    raw = p.read_bytes()
    yield raw
    try:
        txt = raw.decode('utf8')
    except UnicodeError:
        return
    if p.suffix == '.py':
        for node in ast.walk(ast.parse(txt)):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, bytes):
                    yield node.value
                elif isinstance(node.value, str):
                    yield node.value.encode('utf8')
                elif isinstance(node.value, int):
                    yield str(node.value).encode('ascii')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'bytes'
                    and node.func.attr == 'fromhex' and len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                try:
                    yield bytes.fromhex(node.args[0].value)
                except ValueError:
                    pass
    for match in re.finditer(r'(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])', txt):
        s = match.group()
        if len(s) % 2 == 0:
            yield bytes.fromhex(s)


# Textos de PROTOCOLO del propio juego (nombres de metodos que el cliente pide y una respuesta JSON vacia).
# Aparecen igual en las capturas porque son del juego, no de la cuenta. Revisados uno por uno por el cerebro el
# 18-nov (ficha 168): una ventana de 16 B se permite solo si, quitando a lo sumo 1 byte de cada punta, cae dentro
# de uno de estos textos. Cualquier otra coincidencia sigue contando.
PERMITIDOS = (b'modAct.getActList', b'modAct.getActInfoByKey', b'musicMedalNet.onInit', b'getdiamondInfoCS',
              b'{"l":{},"max":0}')


def permitido(w):
    for a in range(2):
        for z in range(2):
            t = w[a:len(w)-z]
            if any(t in x for x in PERMITIDOS):
                return True
    return False


def revisar(root, dat):
    pats = objetivos(dat, root)
    tramos = set()
    for name in CAPTURAS:
        p = dat/name
        raw = bytes.fromhex(p.read_text(encoding='ascii').strip()) if p.suffix == '.hex' else p.read_bytes()
        tramos.update(raw[i:i+16] for i in range(max(0, len(raw)-15)))
    files = archivos(root)
    total = 0
    for p in files:
        tipos, comunes = set(), set()
        for raw in vistas(p):
            tipos.update(k for k, pat in pats if pat and pat in raw)
            comunes.update(raw[i:i+16] for i in range(max(0, len(raw)-15))
                           if raw[i:i+16] in tramos and not permitido(raw[i:i+16]))
        n = len(tipos)+len(comunes)
        if n:
            # Nunca contenido, representacion hex, apodos, identidades o llaves.
            print(p.relative_to(root).as_posix(), 'identificadores=', len(tipos), 'tramos16=', len(comunes))
        total += n
    print(('OK' if total == 0 else 'FALLA:') + f' guardia: {total} coincidencias; {len(files)} archivos')
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--capturas', type=Path)
    args = parser.parse_args()
    try:
        return int(revisar(args.raiz.resolve(), args.capturas or args.raiz/'datos') != 0)
    except Exception:
        print('FALLA: guardia incompleto; faltan fuentes o no se pudieron interpretar (sin exponer contenido)')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
