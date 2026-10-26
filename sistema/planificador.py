"""Planificador editorial: convierte el catálogo (data/catalogo.csv) en solicitudes de guion para los próximos días.

Cada día: 1 Reel + 1 imagen fija. Reglas:
  · Antes del lanzamiento validado solo se planifican temas de carril A (riesgo bajo); el carril B entra cuando
    LANZAMIENTO_AUTORIZADO=SI y la tasa de retención jurídica de las últimas 20 piezas sea < 20 %; el C nunca se
    automatiza (requiere revisión humana).
  · El Reel atrae (historia, gancho); la imagen refuerza (concepto guardable). Tres días por semana la imagen
    COMPLEMENTA el Reel del día anterior reutilizando su investigación, pero con otro ángulo y otra plantilla;
    nunca repite el guion. Los otros cuatro días es un tema independiente (conceptos y mitos).
  · No repite tema en 60 días ni la misma categoría dos días seguidos en el mismo formato.
Las solicitudes se escriben en estado/solicitudes/. Las convierte en guiones la tarea «guionista»
(ver docs/tarea_guionista.md); el ciclo nunca produce un guion que no pase esquema.py y verificador.py."""
import csv, json, os
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / "data" / "catalogo.csv"
SOLICITUDES = RAIZ / "estado" / "solicitudes"
PLANTILLA_DIA = ["concepto", "tres_claves", "mito_realidad", "diferencia", "dato", "concepto", "tres_claves"]   # lunes…domingo
COMPLEMENTA = {1, 3, 5}          # martes, jueves y sábado: la imagen complementa el Reel del día anterior
CATS_IMAGEN = ("C.", "H.", "B.", "F.")


def cargar_catalogo():
    with open(CATALOGO, newline="") as f:
        return list(csv.DictReader(f))


def usados():
    u = {p.name for p in (RAIZ / "piezas").glob("*") if p.is_dir()}
    if SOLICITUDES.exists():
        for s in SOLICITUDES.glob("*.json"):
            d = json.loads(s.read_text()); u.add(d["tema_id"] if d["formato"] == "reel" else d["tema_id"] + ":img")
    return u


def carriles_permitidos(env=os.environ):
    return {"A", "B"} if env.get("LANZAMIENTO_AUTORIZADO") == "SI" else {"A"}


def planificar(dias=7, desde=None, env=os.environ, escribir=True):
    cat = sorted(cargar_catalogo(), key=lambda r: -float(r["puntaje"]))
    ok = carriles_permitidos(env); ya = usados(); desde = desde or date.today() + timedelta(days=1)
    plan, ult_cat = [], {"reel": None, "imagen": None}; reel_prev = None
    for i in range(dias):
        dia = desde + timedelta(days=i); dsem = dia.weekday()
        reel = next((r for r in cat if r["carril"] in ok and r["id"] not in ya and r["categoria"] != ult_cat["reel"]), None)
        if reel:
            ya.add(reel["id"]); ult_cat["reel"] = reel["categoria"]
            plan.append({"fecha": dia.isoformat(), "formato": "reel", "tema_id": reel["id"], "titulo": reel["titulo"],
                         "gancho": reel["gancho"], "carril": reel["carril"], "fuentes_sugeridas": reel["fuentes_sugeridas"],
                         "riesgo_exactitud": reel["riesgo_exactitud"], "hora_publicacion_mx": "19:00"})
        plantilla = PLANTILLA_DIA[dsem]
        if dsem in COMPLEMENTA and reel_prev:
            img = {"fecha": dia.isoformat(), "formato": "imagen", "tema_id": reel_prev["tema_id"], "titulo": reel_prev["titulo"],
                   "relacion": "complemento", "plantilla": plantilla, "carril": reel_prev["carril"],
                   "angulo": f"Concepto clave detrás de «{reel_prev['titulo']}», en formato {plantilla}; reutiliza las fuentes ya verificadas del Reel; prohibido repetir su guion.",
                   "fuentes_sugeridas": reel_prev["fuentes_sugeridas"]}
            if img["tema_id"] + ":img" in ya: img = None
        else:
            img = None
        if img is None:
            r = next((r for r in cat if r["carril"] in ok and r["id"] + ":img" not in ya and r["id"] not in ya
                      and r["categoria"].startswith(CATS_IMAGEN) and r["categoria"] != ult_cat["imagen"]), None)
            if r:
                img = {"fecha": dia.isoformat(), "formato": "imagen", "tema_id": r["id"], "titulo": r["titulo"], "relacion": "independiente",
                       "plantilla": "mito_realidad" if r["categoria"].startswith("H.") or r["titulo"].lower().startswith("mito") else plantilla, "carril": r["carril"], "angulo": r["gancho"], "fuentes_sugeridas": r["fuentes_sugeridas"]}
                ya.add(r["id"])
        if img:
            img["hora_publicacion_mx"] = "09:00"; ya.add(img["tema_id"] + ":img")
            ult_cat["imagen"] = next((r["categoria"] for r in cat if r["id"] == img["tema_id"]), None); plan.append(img)
        reel_prev = plan[-2] if reel and img else (plan[-1] if reel else None)
    if escribir:
        SOLICITUDES.mkdir(parents=True, exist_ok=True)
        for s in plan:
            f = SOLICITUDES / f'{s["fecha"]}_{s["formato"]}_{s["tema_id"]}.json'
            if not f.exists():
                f.write_text(json.dumps({**s, "estado": "PENDIENTE_GUION", "instrucciones": "docs/tarea_guionista.md"}, ensure_ascii=False, indent=2))
    return plan


if __name__ == "__main__":
    for s in planificar(escribir="--escribir" in os.sys.argv):
        print(s["fecha"], s["formato"].ljust(6), s["tema_id"], s.get("plantilla", "").ljust(13), s.get("relacion", "").ljust(13), s["titulo"][:70])
