"""Registro de avance de la primera etapa (orden del responsable, 3-11-2026): 90 imágenes + 90 Reels, del 23-11-2026 al 20-02-2027.

Solo lee el calendario, la cola y la autorización; escribe registro/avance.json y registro/avance.md.
Una pieza cuenta como «terminada» solo si está en el calendario con versión, huella SHA-256 y respaldo (asset_id).
"""
import json, sys
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INICIO, FIN, META = date(2026, 11, 23), date(2027, 2, 20), 90


def terminada(e):
    return bool(e and e.get("version") and e.get("sha256") and e.get("asset_id"))


def calcular(calendario, cola, hoy=None):
    hoy = hoy or datetime.now(timezone.utc).date()
    dias = {d["fecha"]: d for d in calendario.get("dias", [])}
    fechas = [INICIO + timedelta(n) for n in range((FIN - INICIO).days + 1)]
    r = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "periodo": f"{INICIO} al {FIN}", "meta_por_formato": META,
         "terminadas": {}, "faltan": {}, "huecos_proximos": [], "quincenas": [], "cola": {}}
    for fmt in ("imagen", "reel"):
        n = sum(terminada(dias.get(f.isoformat(), {}).get(fmt)) for f in fechas)
        r["terminadas"][fmt] = n; r["faltan"][fmt] = META - n
        r["huecos_proximos"] += [f"{f} {fmt}" for f in fechas if not terminada(dias.get(f.isoformat(), {}).get(fmt))][:5]
    r["total"] = f'{sum(r["terminadas"].values())}/{2 * META}'
    for i in range(0, len(fechas), 15):
        q = fechas[i:i + 15]
        r["quincenas"].append({"del": str(q[0]), "al": str(q[-1]),
                               **{fmt: sum(terminada(dias.get(f.isoformat(), {}).get(fmt)) for f in q) for fmt in ("imagen", "reel")}, "dias": len(q)})
    trab = (cola or {}).get("trabajos", {})
    r["cola"] = dict(Counter(t.get("estado") for t in trab.values()))
    # día en que se acabaría el inventario si no se produjera nada más
    cubiertos = [f for f in fechas if all(terminada(dias.get(f.isoformat(), {}).get(x)) for x in ("imagen", "reel"))]
    seguidos = INICIO - timedelta(1)
    for f in fechas:
        if f in cubiertos: seguidos = f
        else: break
    r["cubierto_sin_huecos_hasta"] = str(seguidos) if seguidos >= INICIO else None
    return r


def markdown(r):
    l = [f"# Avance de la primera etapa ({r['periodo']})", "",
         f"**Terminadas: {r['total']}** · imágenes {r['terminadas']['imagen']}/90 · Reels {r['terminadas']['reel']}/90",
         f"Calendario completo y sin huecos hasta: {r['cubierto_sin_huecos_hasta'] or '—'}", "",
         "| Quincena | Imágenes | Reels |", "|---|---|---|"]
    l += [f"| {q['del']} al {q['al']} | {q['imagen']}/{q['dias']} | {q['reel']}/{q['dias']} |" for q in r["quincenas"]]
    l += ["", "Próximos huecos: " + (", ".join(r["huecos_proximos"]) or "ninguno"), "",
          "Cola: " + ", ".join(f"{k} {v}" for k, v in sorted(r["cola"].items(), key=lambda x: str(x[0]))), "",
          f"_Generado {r['generado']} por sistema/avance.py. Terminada = en calendario con versión aprobada, SHA-256 y respaldo._"]
    return "\n".join(l) + "\n"


if __name__ == "__main__":
    cal = json.loads((RAIZ / "data" / "calendario_lanzamiento.json").read_text())
    cola_f = RAIZ / "estado" / "cola.json"
    r = calcular(cal, json.loads(cola_f.read_text()) if cola_f.exists() else {})
    (RAIZ / "registro" / "avance.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    (RAIZ / "registro" / "avance.md").write_text(markdown(r))
    print(markdown(r)); sys.exit(0)
