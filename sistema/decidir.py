"""Revisión humana por el chat con Claude (canal elegido por el usuario el 26-10-2026; Telegram descartado).

Flujo: Claude entrega al usuario en el chat el archivo exacto respaldado de cada pieza en REVISION_HUMANA junto con su
número de versión. El usuario responde «apruebo» o «rechazo». Claude registra la decisión con este script:

    python sistema/decidir.py listar
    python sistema/decidir.py aprobar  <pieza> <versión> --por "Nombre (chat)" [--nota "..."]
    python sistema/decidir.py rechazar <pieza> <versión> --por "Nombre (chat)" --nota "motivo"

El script solo AÑADE una fila a estado/aprobaciones.jsonl (quién, cuándo, versión, huellas) después de comprobar que la
versión indicada es la que se preparó para revisión y la que resulta hoy del guion y del archivo respaldado. El ciclo
aplica la decisión al iniciar (revision.aplicar), con la misma doble comprobación; publicar usa ese archivo exacto.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola, revision


class VersionDistinta(Exception):
    pass


def pendientes(c):
    return [t for t in c["trabajos"].values() if t["estado"] == "REVISION_HUMANA"]


def decidir(c, pid, decision, ver, por, nota="", canal="chat"):
    t = c["trabajos"].get(pid)
    if not t or t["estado"] != "REVISION_HUMANA":
        raise VersionDistinta(f"{pid} no está en revisión humana")
    actual, hg, ha = revision.version(pid, t.get("formato", "reel"))
    preparada = (t.get("revision") or {}).get("version")
    if not actual or ver != actual or ver != preparada:
        raise VersionDistinta(f"{pid}: la versión {ver} no es la vigente (preparada {preparada}, actual {actual}); no se registró")
    if decision == "RECHAZADA" and not nota.strip():
        raise ValueError("un rechazo necesita el motivo (--nota)")
    return revision.registrar(pid, decision, ver, hg, ha, {"nombre": por}, canal, nota)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["listar", "aprobar", "rechazar"])
    ap.add_argument("pieza", nargs="?"); ap.add_argument("version", nargs="?")
    ap.add_argument("--por"); ap.add_argument("--nota", default="")
    ap.add_argument("--delegada", action="store_true",
                    help="aprobación editorial delegada en Claude (decisión del responsable, 29-10-2026): la pieza solo se publica "
                         "después de 72 h de aviso al responsable, que puede vetarla con «rechazar» en ese plazo")
    a = ap.parse_args(); c = cola.cargar()
    if a.accion == "listar":
        for t in pendientes(c):
            r = t.get("revision") or {}
            print(json.dumps({"pieza": t["id"], "formato": t.get("formato"), "version": r.get("version"), "preparada": r.get("preparada"),
                              "archivo": revision.principal(t["id"], t.get("formato", "reel"))}, ensure_ascii=False))
        sys.exit(0)
    if not (a.pieza and a.version and a.por): ap.error("faltan pieza, versión o --por")
    try:
        print(json.dumps(decidir(c, a.pieza, "APROBADA" if a.accion == "aprobar" else "RECHAZADA", a.version, a.por, a.nota,
                                 canal="delegada" if a.delegada else "chat"), ensure_ascii=False, indent=2))
    except (VersionDistinta, ValueError) as e:
        print(f"NO REGISTRADO: {e}"); sys.exit(2)
