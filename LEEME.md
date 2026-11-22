# Eñeñosbit 2027 — el server

El server del **Eñeñosbit 2027** (el R2Beat moderno: el cliente chino de Steam repatriado). Corre en Miami, en la pila
`/opt/enenos`, detrás de Cuenta Eñeños: sólo entra quien trae el pase con `aud r2beat-moderno`.

| carpeta | qué es |
|---|---|
| `servidor/` | el server: `login.py` (login) y `juego.py` (juego), y sus módulos |
| `datos/` | sólo las tablas LIMPIAS del juego (catálogo, charts, granja, jardín, progresión…) |
| `vps/` | `Dockerfile`, `arrancar.sh`, `guardia_datos.py` y la lista `archivos_que_viajan.txt` |
| `herramientas/` | `traer_de_r2beat.py`: lleva lo de `D:\R2Beat\servidor_local` a este repo (con el guardia) |

## Las dos ramas — igual que R2Beat 2013 y EDA

| rama | server | cómo se actualiza |
|---|---|---|
| **`develop`** | **el de PRUEBA** (`r2beat-moderno-prueba`: 38004 / 38008) | ★ **solo**: a los ≤ 5 min de un merge. Lo hace `actualizar_moderno_prueba.sh` en el VPS (cron) |
| **`main`** | **PROD** (`r2beat-moderno`: 28004 / 28008) | ⛔ **a mano, y sólo cuando Benja lo aprueba** |

`main` nació el 22-nov-2026 como copia exacta de lo que corría en prod: la imagen `r2beat-moderno:2026-11-21b`.

### Cómo se trabaja

1. Rama propia, desde `develop`.
2. PR contra **`develop`**, y merge.
3. Al rato, el server de prueba está en ese commit. En el launcher: casilla «Servidor de prueba» del Eñeñosbit.
4. Si la imagen no se arma (le falta una librería, o un módulo no importa), o el server no queda sano, **el de
   prueba sigue en el anterior**. Ese commit queda anotado y no se reintenta hasta que llegue otro.
5. Pasar algo a prod = PR de `develop` a `main` que **aprueba Benja**.

### ⛔ Antes de cada push

Correr el guardia **en la PC de Benja** (necesita las capturas originales para comparar):

```powershell
python -B D:\R2Beat\servidor_local\vps\guardia_datos.py --raiz <este repo> --capturas D:\R2Beat\servidor_local\datos
```

Sale 0 sólo con cero coincidencias. `herramientas/traer_de_r2beat.py --publicar` lo corre solo, y **no hace el push**
si no da 0.
