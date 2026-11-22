FROM python:3.13-slim

WORKDIR /app

# salas.py (crear sala) descifra con AES: pycryptodome (21-nov: sin esto el server se caia al CREAR SALA en Miami)
COPY vps/requisitos.txt /app/vps/requisitos.txt
RUN pip install --no-cache-dir -r /app/vps/requisitos.txt
COPY servidor/ /app/servidor/
COPY vps/ /app/vps/

# Copiar solo tablas limpias del juego (sin capturas ni datos personales).
# Armar el contexto con vps/archivos_que_viajan.txt antes de docker build.
COPY datos/ /app/datos/

RUN mkdir -p /datos_cuentas /app/registros && chmod +x /app/vps/arrancar.sh

ENV PASE=si \
    HOSTS=0.0.0.0 \
    PUERTOS=28004 \
    PUERTOS_JUEGO=28008 \
    PUERTO_CUENTAS=28101 \
    CUENTA_DATOS=/datos_cuentas \
    R2_PASE_JUEGO=r2beat-moderno \
    MUSICA_2013=1 \
    SIN_CANAL_BAILE=1 \
    GESTOS_TODOS=1 \
    PYTHONUNBUFFERED=1

VOLUME ["/datos_cuentas"]

EXPOSE 28004/tcp 28008/tcp 28101-28109/tcp

CMD ["/app/vps/arrancar.sh"]
