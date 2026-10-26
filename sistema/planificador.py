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
from datetime import date, datetime, timedelta, timezone
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


ACTIVAS = {"PENDIENTE_GUION", "REDACTANDO", "GUION_LISTO"}     # una sola por fecha y formato
CERRADAS = {"DESCARTADA", "SUPERSEDIDA"}                         # se conservan como historial; nunca se borran


def _escribir(f, d):
    """Escritura atómica: si el proceso muere a la mitad, el archivo queda completo o no existe (nunca truncado)."""
    tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2)); os.replace(tmp, f)


def solicitudes():
    if not SOLICITUDES.exists(): return []
    for t in SOLICITUDES.glob("*.tmp"): t.unlink()              # restos de una escritura interrumpida
    out = []
    for f in sorted(SOLICITUDES.glob("*.json")):
        try: out.append((f, json.loads(f.read_text())))
        except Exception: continue                               # un archivo ilegible no detiene la planeación
    return out


def consolidar(hoy=None):
    """Deja UNA solicitud activa por (fecha, formato). Las sobrantes pasan a SUPERSEDIDA con su motivo (historial y
    trazabilidad intactos). Prioridad para conservar: GUION_LISTO > REDACTANDO > mayor puntaje del catálogo."""
    punt = {r["id"]: float(r["puntaje"]) for r in cargar_catalogo()}
    grupos = {}
    for f, d in solicitudes():
        if d.get("estado") in ACTIVAS: grupos.setdefault((d["fecha"], d["formato"]), []).append((f, d))
    orden = {"GUION_LISTO": 0, "REDACTANDO": 1, "PENDIENTE_GUION": 2}
    cambios = []
    for (fecha, formato), lst in grupos.items():
        if len(lst) < 2: continue
        lst.sort(key=lambda x: (orden[x[1]["estado"]], -punt.get(x[1]["tema_id"], 0), x[0].name))
        queda = lst[0][0].name
        for f, d in lst[1:]:
            d["historial"] = d.get("historial", []) + [{"estado": d["estado"], "a": "SUPERSEDIDA", "fecha_cambio": (hoy or date.today()).isoformat()}]
            d.update(estado="SUPERSEDIDA", supersedida_por=queda,
                     motivo_cierre="Duplicado por fecha y formato (defecto del planificador hasta v0.3); se conserva como historial.")
            _escribir(f, d); cambios.append(f.name)
    return cambios


def usados():
    """Temas ocupados: piezas existentes y solicitudes activas o descartadas (no se reintenta un tema descartado).
    Las SUPERSEDIDAS liberan su tema."""
    u = {p.name for p in (RAIZ / "piezas").glob("*") if p.is_dir()}
    for _, d in solicitudes():
        if d.get("estado") == "SUPERSEDIDA": continue
        u.add(d["tema_id"] if d["formato"] == "reel" else d["tema_id"] + ":img")
        if d["formato"] == "reel": u.add(d["tema_id"])
    return u


def ocupadas():
    """{(fecha, formato): solicitud activa}"""
    return {(d["fecha"], d["formato"]): d for _, d in solicitudes() if d.get("estado") in ACTIVAS}


def carriles_permitidos(env=os.environ):
    return {"A", "B"} if env.get("LANZAMIENTO_AUTORIZADO") == "SI" else {"A"}


def planificar(dias=7, desde=None, env=os.environ, escribir=True):
    cat = sorted(cargar_catalogo(), key=lambda r: -float(r["puntaje"]))
    if escribir: consolidar()
    ok = carriles_permitidos(env); ya = usados(); occ = ocupadas(); desde = desde or date.today() + timedelta(days=1)
    plan, ult_cat = [], {"reel": None, "imagen": None}; reel_prev = None
    for i in range(dias):
        dia = desde + timedelta(days=i); dsem = dia.weekday(); clave = dia.isoformat()
        cat_de = lambda tid: next((r["categoria"] for r in cat if r["id"] == tid), None)
        # --- Reel del día: si ya hay una solicitud activa para esa fecha, se respeta (idempotencia)
        reel_hoy = occ.get((clave, "reel"))
        if reel_hoy is None:
            r = next((r for r in cat if r["carril"] in ok and r["id"] not in ya and r["categoria"] != ult_cat["reel"]), None)
            if r:
                reel_hoy = {"fecha": clave, "formato": "reel", "tema_id": r["id"], "titulo": r["titulo"],
                            "gancho": r["gancho"], "carril": r["carril"], "fuentes_sugeridas": r["fuentes_sugeridas"],
                            "riesgo_exactitud": r["riesgo_exactitud"], "hora_publicacion_mx": "19:00"}
                ya.add(r["id"])
        if reel_hoy:
            plan.append(reel_hoy); ult_cat["reel"] = cat_de(reel_hoy["tema_id"])
        # --- Imagen del día
        plantilla = PLANTILLA_DIA[dsem]
        img = occ.get((clave, "imagen"))
        if img is None and dsem in COMPLEMENTA and reel_prev and reel_prev["tema_id"] + ":img" not in ya:
            img = {"fecha": clave, "formato": "imagen", "tema_id": reel_prev["tema_id"], "titulo": reel_prev["titulo"],
                   "relacion": "complemento", "plantilla": plantilla, "carril": reel_prev["carril"],
                   "angulo": f"Concepto clave detrás de «{reel_prev['titulo']}», en formato {plantilla}; reutiliza las fuentes ya verificadas del Reel; prohibido repetir su guion.",
                   "fuentes_sugeridas": reel_prev["fuentes_sugeridas"]}
        if img is None:
            r = next((r for r in cat if r["carril"] in ok and r["id"] + ":img" not in ya and r["id"] not in ya
                      and r["categoria"].startswith(CATS_IMAGEN) and r["categoria"] != ult_cat["imagen"]), None)
            if r:
                img = {"fecha": clave, "formato": "imagen", "tema_id": r["id"], "titulo": r["titulo"], "relacion": "independiente",
                       "plantilla": "mito_realidad" if r["categoria"].startswith("H.") or r["titulo"].lower().startswith("mito") else plantilla,
                       "carril": r["carril"], "angulo": r["gancho"], "fuentes_sugeridas": r["fuentes_sugeridas"]}
                ya.add(r["id"])
        if img:
            img.setdefault("hora_publicacion_mx", "09:00"); ya.add(img["tema_id"] + ":img")
            ult_cat["imagen"] = cat_de(img["tema_id"]); plan.append(img)
        reel_prev = reel_hoy
    if escribir:
        SOLICITUDES.mkdir(parents=True, exist_ok=True)
        for s in plan:
            if "estado" in s: continue                            # ya existía (activa): no se toca
            if (s["fecha"], s["formato"]) in ocupadas(): continue  # otra ejecución la creó mientras tanto
            f = SOLICITUDES / f'{s["fecha"]}_{s["formato"]}_{s["tema_id"]}.json'
            if not f.exists():
                _escribir(f, {**s, "estado": "PENDIENTE_GUION", "instrucciones": "docs/tarea_guionista.md",
                              "creada": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return plan


if __name__ == "__main__":
    for s in planificar(escribir="--escribir" in os.sys.argv):
        print(s["fecha"], s["formato"].ljust(6), s["tema_id"], s.get("plantilla", "").ljust(13), s.get("relacion", "").ljust(13), s["titulo"][:70])
