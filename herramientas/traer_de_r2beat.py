#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""traer_de_r2beat — lleva el server de D:\R2Beat\servidor_local (o de un worktree) a ESTE repo, con el guardia.

    python herramientas/traer_de_r2beat.py --desde D:\R2Beat\servidor_local
        copia y corre el guardia; no toca git (para mirar el diff a mano)
    python herramientas/traer_de_r2beat.py --desde <worktree>\servidor_local --publicar --rama m01-cuentas \
        --mensaje "M01: cuentas sin tope" [--merge]
        rama nueva desde origin/develop → copia → guardia → commit → push → PR contra develop (→ merge)

QUÉ VIAJA: lo de `vps/archivos_que_viajan.txt` del ORIGEN. Las carpetas de la lista (`datos/charts/`…) se copian
ESPEJADAS: lo que ya no está en el origen, se borra acá. Un `servidor/*.py` que ya no está en el origen también se
borra. ⛔ Frena si un `servidor/*.py` del origen NO está en la lista, o si el repo tiene algún archivo fuera de ella
(salvo LEEME.md, .gitignore y herramientas/): el guardia SÓLO revisa lo de la lista, y eso no se sube sin revisar.

⛔ EL PUSH SÓLO DESPUÉS DEL GUARDIA EN 0. Las capturas para comparar están en la copia principal de D:\R2Beat (no en
   los worktrees, porque git las ignora): `--capturas` apunta ahí por omisión.
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                # noqa: BLE001
        pass

REPO = Path(__file__).resolve().parents[1]
CAPTURAS = Path(r"D:\R2Beat\servidor_local\datos")
FIRMA = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
IGNORAR = {"__pycache__"}


def git(*a, ok=True):
    r = subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if ok and r.returncode:
        sys.exit(f"⛔ git {' '.join(a)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def lista(desde):
    entradas = []
    for linea in (desde / "vps" / "archivos_que_viajan.txt").read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            entradas.append(linea.replace("\\", "/"))
    faltan = [f"servidor/{p.name}" for p in sorted((desde / "servidor").glob("*.py"))
              if f"servidor/{p.name}" not in entradas]
    if faltan:
        # el guardia SÓLO revisa lo de la lista: un .py fuera de ella se subiría sin revisar
        sys.exit(f"⛔ {', '.join(faltan)} no está(n) en vps/archivos_que_viajan.txt del origen: agregalo(s) ahí "
                 "(si no, el guardia no lo revisa y la imagen no lo lleva)")
    return entradas


PROPIOS = {"LEEME.md", ".gitignore"}            # del repo, no del server: no pasan por el guardia


def fuera_de_lista(entradas):
    """Todo archivo que git subiría y el guardia NO revisa. Tiene que dar vacío."""
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8")
    archivos = [x for x in r.stdout.splitlines() if x and (REPO / x).exists()]
    sueltos = {e for e in entradas if not e.endswith("/")} | {"vps/guardia_datos.py"}
    carpetas = tuple(e for e in entradas if e.endswith("/"))
    return [x for x in archivos if x not in sueltos and not x.startswith(carpetas)
            and x not in PROPIOS and not x.startswith("herramientas/")]


def copiar(a, b, cambios):
    if b.exists() and filecmp.cmp(a, b, shallow=False):
        return
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a, b)
    cambios.append(b.relative_to(REPO).as_posix())


def espejar(desde, entradas):
    cambios, borrados = [], []
    for e in entradas:
        a, b = desde / e.rstrip("/"), REPO / e.rstrip("/")
        if e.endswith("/"):
            if not a.is_dir():
                sys.exit(f"⛔ la lista pide la carpeta {e} y el origen no la tiene")
            vistos = set()
            for raiz, dirs, archivos in os.walk(a):
                dirs[:] = [d for d in dirs if d not in IGNORAR]
                for f in archivos:
                    rel = Path(raiz, f).relative_to(a)
                    vistos.add(rel.as_posix())
                    copiar(Path(raiz, f), b / rel, cambios)
            if b.is_dir():
                for raiz, dirs, archivos in os.walk(b):
                    for f in archivos:
                        rel = Path(raiz, f).relative_to(b).as_posix()
                        if rel not in vistos:
                            os.remove(Path(raiz, f))
                            borrados.append(f"{e}{rel}")
        else:
            if not a.is_file():
                sys.exit(f"⛔ la lista pide {e} y el origen no lo tiene")
            copiar(a, b, cambios)
    fuente = {p.name for p in (desde / "servidor").glob("*.py")}
    for p in (REPO / "servidor").glob("*.py"):
        if p.name not in fuente:
            p.unlink()
            borrados.append(f"servidor/{p.name}")
    return cambios, borrados


def guardia(desde, capturas):
    script = desde / "vps" / "guardia_datos.py"
    r = subprocess.run([sys.executable, "-B", str(script), "--raiz", str(REPO), "--capturas", str(capturas)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    salida = (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]
    print(f"   guardia: {salida}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", type=Path, default=Path(r"D:\R2Beat\servidor_local"))
    ap.add_argument("--capturas", type=Path, default=CAPTURAS)
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--rama")
    ap.add_argument("--mensaje")
    ap.add_argument("--base", default="develop")
    ap.add_argument("--merge", action="store_true", help="después del PR, merge a la base (dispara el server de prueba)")
    a = ap.parse_args()
    desde = a.desde.resolve()
    if not (desde / "servidor" / "juego.py").is_file():
        sys.exit(f"⛔ {desde} no parece un servidor_local (no hay servidor/juego.py)")
    if a.publicar:
        if not (a.rama and a.mensaje):
            sys.exit("⛔ --publicar necesita --rama y --mensaje")
        if a.base == "main":
            sys.exit("⛔ main es PROD: el PR a main lo arma y lo aprueba Benja, no esta herramienta")
        if git("status", "--porcelain"):
            sys.exit("⛔ este repo tiene cambios sin commit: limpialo antes de publicar")
        git("fetch", "-q", "origin")
        git("checkout", "-q", "-B", a.rama, f"origin/{a.base}")

    print(f"▶ {desde} → {REPO}")
    entradas = lista(desde)
    cambios, borrados = espejar(desde, entradas)
    print(f"   {len(cambios)} archivo(s) nuevos o cambiados, {len(borrados)} borrado(s)")
    for x in (cambios + [f"(borrado) {b}" for b in borrados])[:40]:
        print(f"     {x}")

    sueltos = fuera_de_lista(entradas)
    if sueltos:
        sys.exit(f"⛔ {len(sueltos)} archivo(s) del repo que el guardia NO revisa (no están en archivos_que_viajan.txt):"
                 f" {', '.join(sueltos[:10])} — sacalos o agregalos a la lista. Nada se sube.")
    if guardia(desde, a.capturas) != 0:
        sys.exit("⛔ el guardia NO dio 0: nada se sube. Revisar lo que marcó (sin imprimir contenidos).")
    if not a.publicar:
        print("✅ copiado y guardia en 0 (sin publicar: el diff se mira con git)")
        return 0
    git("add", "-A")
    if not git("status", "--porcelain"):
        print("✅ nada distinto de origin/" + a.base + ": no hay PR que abrir")
        return 0
    git("commit", "-q", "-m", f"{a.mensaje}\n\nTraído de {desde.as_posix()} con herramientas/traer_de_r2beat.py "
                              f"(guardia en 0).\n\n{FIRMA}")
    git("push", "-q", "-u", "origin", a.rama, "--force-with-lease")
    pr = subprocess.run(["gh", "pr", "create", "--base", a.base, "--head", a.rama, "--title", a.mensaje,
                         "--body", f"Traído de `{desde.as_posix()}` con `herramientas/traer_de_r2beat.py` "
                                   f"(guardia en 0).\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"],
                        cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    url = (pr.stdout or pr.stderr).strip()
    print(f"   PR: {url}")
    if a.merge:
        m = subprocess.run(["gh", "pr", "merge", a.rama, "--merge", "--delete-branch"], cwd=REPO,
                           capture_output=True, text=True, encoding="utf-8")
        if m.returncode:
            sys.exit(f"⛔ no se pudo hacer el merge: {(m.stderr or m.stdout).strip()}")
        git("checkout", "-q", a.base)
        git("pull", "-q", "--ff-only")
        print(f"✅ merge a {a.base}: el server de prueba se pone al día solo en ≤ 5 min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
