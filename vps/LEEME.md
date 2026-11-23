# Servidor de R2Beat moderno en VPS (Linux, solo cuentas nuevas con pase)

Este paquete prepara `servidor_local/servidor/` para `python3` en Linux, sin `.bat`.
**Dependencia: `pycryptodome`** (`pip install -r vps/requisitos.txt`; el `Dockerfile` ya la instala y `arrancar.sh`
no arranca sin ella). La usa `salas.py` al crear sala; sin ella el servidor se caia en ese momento (Miami, 21-nov).
**Estado (21-nov, ficha 181): listo para entregar.** El guardia da 0 coincidencias en los 3.933 archivos de la lista
(fichas 171 y 179); entrada con pase, practica, salas de 2, carrera, examinar, jardin y el catalogo 2013 medidos con
este paquete limpio. Ver `docs/ENTREGA_MODERNO_AL_COORDINADOR.md`. La lista por si sola no garantiza ausencia de
datos: correr el guardia antes de cada subida.

Antes de cada subida, ejecutar EN ESTA PC, con las capturas originales disponibles:
```powershell
python -B servidor_local/vps/guardia_datos.py
```
Tambien acepta `--raiz <paquete>` y `--capturas <datos originales>`. No imprime contenidos,
solo archivos y conteos. Salida 0 significa cero coincidencias; 1 bloquea por coincidencias;
2 bloquea porque la revision quedo incompleta. No exceptua tramos comunes de 16 bytes.
No enviar las fuentes de comparacion al VPS. Ver mediciones y limites en la ficha 168.

## 1. Que archivos viajan (y cuales NO)

La lista exacta para copiar esta en [`archivos_que_viajan.txt`](archivos_que_viajan.txt):

- **Viajan**: todos los `.py` de `servidor/` (incluido `pase.py`), `vps/`, y solo las tablas limpias del juego en `datos/` (`catalogo.json`, `casa_tablas.json`, `charts_1a1.json`, `charts/`, `farmpet.xml`, `farmquest.txt`, `farmshop.txt`, `farmtraining.xml`, `gemas_tablas.json`, `granja_tablas.json`, `palabras_gestos.json`, `progresion_tablas.json`).
- **NO viajan** (datos de Eñeños, apodos ajenos o cuentas locales):
  - `datos/login_S2C.bin`, `datos/ff0b.hex`, `datos/juego_S2C.bin`, `datos/lotes_S2C.bin`, `datos/respuestas_S2C.bin`
  - `datos/crear_sala_S2C.bin`, `datos/unirse_S2C.bin`, `datos/cartel_S2C.bin`, `datos/examinar_S2C.bin`, `datos/medallas_oninit.hex`
  - `datos/cuenta.json`, `datos/cuentas.json`, `datos/amigos.json`, `datos/parejas.json`, `datos/tienda.json`, `datos/cuenta.lock`, `datos/respaldo_*`
  - `datos/idioma_*`, `datos/isla/` (son del cliente/lanzador), `registros/`, `_fuera_git/`, `tools/`
- **Estado de dependencias sin capturas** (ver ficha `166`):
  - Login (`28004`) funciona sin `login_S2C.bin` ni `ff0b.hex` (`FF01`, `FF0B`, `FF02`, `FF0C`, `FF03` armados en memoria).
  - Juego (`28008`, `28101..28109`): `neutro.py` arma FF04, FF02 y FF00/rafaga si faltan las capturas. La ficha 168 midio alta, lobby y JBL en practica hasta resultados y vuelta. La lista de escenarios del FF00 habilita solo escenario 1 (eleccion INVENTADA, tabla del cliente); el inventario se arma desde el personaje nuevo y sus prendas, sin sociales heredados.
  - Aun no se declara completo el resto: metodos JSON, salas multijugador, cartel multijugador, examinar y tablas de jardin requieren sus propias mediciones sin capturas. El guardia mantiene bloqueada la subida por tramos de protocolo compartidos, pendientes de decision del cerebro.

## 2. Variables de entorno

| Variable | Valor en VPS | Nota |
|---|---|---|
| `PASE` | `si` | Exige pase Ed25519 valido en `FF01`; ignora SteamID y usa `e<sub>` |
| `R2_CUENTAS_CLAVE_PUBLICA` | JWK / JWKS / hex / base64url | Clave publica Ed25519 de Cuenta Eñeños (sin llamadas de red por login) |
| `R2_PASE_JUEGO` | `r2beat-moderno` | `aud` esperado en el pase (omision: `r2beat-moderno`) |
| `HOSTS` | `0.0.0.0` | Escucha en todas las interfaces |
| `IP_JUEGO` | `<IP publica del VPS>` | IP que `FF03` anuncia al cliente |
| `PUERTOS` | `28004` | Puerto del servidor de login |
| `PUERTOS_JUEGO` | `28008` | Puerto base del servidor de juego (compartido por todas las cuentas con `IDENTIDAD_FF02=si`) |
| `IDENTIDAD_FF02` | `si` (omision) | Con `PASE=si`, identifica la cuenta por el `C2S FF02` del puerto de juego `28008` y quita el tope de 8 cuentas (`0` vuelve a puerto por cuenta y tope 8) |
| `PUERTO_CUENTAS` | `28101` | Primer puerto de cuentas nuevas (`28101..28108` + `28109`; solo se usa si `IDENTIDAD_FF02=0`) |
| `CUENTA_DATOS` | `/ruta/datos_cuentas` | Carpeta vacia/persistente donde se crea `cuenta.json` |
| `MUSICA_2013` | `1` (omision en `arrancar.sh` y `Dockerfile`) | Catalogo 2013 de `datos/musica_2013` (ficha 179). SOLO con el cliente que trae `rnr_musica2013.pak` y `rnr_music2013_*.pak`: con uno viejo, 9 canciones lo cierran |
| `SIN_CANAL_BAILE` | `1` (omision) | Modo Baile abre en el servidor de siempre (ficha 175) |
| `CANAL` | `N2server` (omision en `arrancar.sh`) | Nombre del servidor en la lista de canales (FF03). Una ñ se ve como `?0?9` en esa parte del cliente (medido, M19) |
| `CANAL_MAXIMO` | `1800` | Maximo de la barra "usuarios/maximo" de la lista (u16). Los usuarios son los conectados de verdad (`en_linea.json`) |
| `CUENTA_SQLITE` | `1` (omision en `arrancar.sh`) | Cuentas en `cuentas.db` (SQLite WAL) en `CUENTA_DATOS`; la 1.a vez migra `cuenta.json` y lo deja intacto (maduracion M09). `0` = `cuenta.json` como antes |
| `GESTOS_TODOS` | `1` (omision) | Palabras de gesto de todos los idiomas (ficha 133) |
| `R2_CUENTAS_FICHA_INTERNA` | `<secreto compartido>` | Ficha interna del Coordinador para `/interno/panel/*` (sin esta variable y `PANEL_PUERTO`, el panel interno no se abre) |
| `PANEL_PUERTO` | `28191` (ejemplo) | Puerto HTTP del panel interno («contrato1») dentro de `juego.py`. **Solo red interna: NO poner en `ports:` del compose** |
| `PANEL_HOST` | `0.0.0.0` (omision) | Interfaz donde escucha el panel interno (`127.0.0.1` o red privada del contenedor) |
| `PANEL_ENTORNO` | `test` (omision) | Nombre del entorno que informa `GET /interno/panel/capacidades` (`test` o `live`) |

Opcional: `R2_CUENTAS_URL` si no se pasa `R2_CUENTAS_CLAVE_PUBLICA` (consulta `/clave-publica` una sola vez al arrancar).

## 3. Puertos TCP a abrir

Con `IDENTIDAD_FF02=si` (por omision en modo `PASE=si`) solo hacen falta `28004` y `28008`. Los `28101..28109` pueden quedar abiertos sin dano (solo se usan si se apaga la llave con `IDENTIDAD_FF02=0`).

- `28004/tcp` (login)
- `28008/tcp` (juego)
- `28101-28109/tcp` (opcionales con la llave prendida; pueden quedar abiertos sin dano)
- `PANEL_PUERTO` **NO** se abre al exterior ni va en `ports:` del compose: es solo para la red interna con el Coordinador.

## 4. Como armar y arrancar en Linux

1. Empaquetar solo lo limpio desde `servidor_local/`:
   ```sh
   tar -czf r2beat-vps.tgz -C servidor_local -T servidor_local/vps/archivos_que_viajan.txt
   ```
2. En el VPS, descomprimir en `/opt/r2beat` y arrancar directo con `python3`:
   ```sh
   export PASE=si
   export HOSTS=0.0.0.0
   export IP_JUEGO="<IP_PUBLICA>"
   export CUENTA_DATOS="/var/lib/r2beat/datos"
   export R2_CUENTAS_CLAVE_PUBLICA='{"kty":"OKP","crv":"Ed25519","kid":"4e1fe705c450c45c","x":"<CLAVE_B64U>"}'
   /opt/r2beat/vps/arrancar.sh
   ```
   O por separado:
   ```sh
   cd /opt/r2beat/servidor
   python3 -u login.py &
   python3 -u juego.py &
   ```
3. Con Docker (construyendo sobre el directorio descomprimido que contiene solo `archivos_que_viajan.txt`):
   ```sh
   docker build -f vps/Dockerfile -t r2beat-vps .
   docker run -d --name r2beat-vps --restart unless-stopped \
     -p 28004:28004 -p 28008:28008 -p 28101-28109:28101-28109 \
     -e IP_JUEGO="<IP_PUBLICA>" \
     -e R2_CUENTAS_CLAVE_PUBLICA='...' \
     -v r2beat_datos:/datos_cuentas \
     r2beat-vps
   ```
