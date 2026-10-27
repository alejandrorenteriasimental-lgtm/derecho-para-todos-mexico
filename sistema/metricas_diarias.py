"""Métricas diarias y guardia de minutos de GitHub Actions (instrucción del responsable, 27-10-2026).

Solo lee los registros que ya existen (no genera tareas ni llama a modelos):
  estado/solicitudes/, estado/cola.json, estado/aprobaciones.jsonl, estado/uso_ia.jsonl,
  registro/consumo.jsonl, registro/metricas_generacion.jsonl y, si hay token, la API de GitHub Actions.

Escribe registro/metricas_diarias.jsonl (una línea por día de Ciudad de México; si se vuelve a calcular el mismo día, la
línea se reemplaza) y registro/actions_mes.json.

Distingue: solicitudes (planes), borradores (guion listo), piezas producidas (renderizadas), piezas que superaron la
auditoría automática (llegaron a revisión humana) y piezas APROBADAS por el responsable. Solo las últimas cuentan como
contenido disponible.

Uso:
  python sistema/metricas_diarias.py            → calcula y guarda
  python sistema/metricas_diarias.py --guardia  → además escribe «continuar=true|false» en $GITHUB_OUTPUT: false si los
                                                   minutos del mes alcanzan el tope propio (por debajo del gratuito)
"""
import json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GRATIS_MES = 2000            # minutos incluidos al mes en repositorios privados (plan gratuito de GitHub)
TOPE_PROPIO = 1700           # el ciclo se detiene antes de llegar al límite gratuito (margen para correcciones)
META = {"reel": 7, "imagen": 7}
LANZAMIENTO_OBJETIVO = date(2026, 11, 23)
MX = timedelta(hours=-6)


def _jsonl(p):
    out = []
    try:
        for l in Path(p).read_text().splitlines():
            try: out.append(json.loads(l))
            except ValueError: pass
    except OSError:
        pass
    return out


def dia_mx(ts):
    try: return (datetime.fromisoformat(str(ts).replace("Z", "+00:00")) + MX).date()
    except ValueError: return None


def minutos_actions(repo, token, ahora=None, abrir=urllib.request.urlopen):
    """Minutos de Actions del mes en curso: suma, por trabajo, de su duración redondeada hacia arriba al minuto (así
    factura GitHub). Es un cálculo propio con los datos de la API, no la cifra oficial de facturación."""
    ahora = ahora or datetime.now(timezone.utc)
    inicio = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    def get(url):
        with abrir(urllib.request.Request(url, headers=h), timeout=30) as r: return json.loads(r.read())
    total, runs, pagina = 0, 0, 1
    while True:
        d = get(f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&page={pagina}&created=%3E%3D{inicio:%Y-%m-%d}")
        for run in d.get("workflow_runs", []):
            runs += 1
            for j in get(f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", []):
                if j.get("started_at") and j.get("completed_at"):
                    s = (datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00")) - datetime.fromisoformat(j["started_at"].replace("Z", "+00:00"))).total_seconds()
                    total += max(1, math.ceil(s / 60)) if s > 0 else 0
        if len(d.get("workflow_runs", [])) < 100: break
        pagina += 1
    dias_mes = ((inicio + timedelta(days=32)).replace(day=1) - inicio).days
    return {"mes": f"{inicio:%Y-%m}", "minutos": total, "ejecuciones": runs, "gratis": GRATIS_MES, "tope_propio": TOPE_PROPIO,
            "disponibles_hasta_tope": max(0, TOPE_PROPIO - total), "dias_restantes": dias_mes - ahora.day + 1,
            "calculado": ahora.isoformat(timespec="seconds"), "nota": "cálculo propio por trabajo (redondeo al minuto); no es la factura oficial"}


def calcular(hoy=None, actions=None, raiz=RAIZ):
    hoy = hoy or (datetime.now(timezone.utc) + MX).date()
    sols = []
    for f in sorted((raiz / "estado" / "solicitudes").glob("*.json")):
        try: sols.append(json.loads(f.read_text()))
        except ValueError: pass
    try: cola = json.loads((raiz / "estado" / "cola.json").read_text())["trabajos"]
    except (OSError, ValueError, KeyError): cola = {}
    aprob = _jsonl(raiz / "estado" / "aprobaciones.jsonl")
    uso = _jsonl(raiz / "estado" / "uso_ia.jsonl")
    consumo = _jsonl(raiz / "registro" / "consumo.jsonl")

    def eventos(a):    # (pieza, formato, día) de cada paso de la cola al estado «a»
        return [(pid, t.get("formato", "reel"), dia_mx(h.get("ts"))) for pid, t in cola.items() for h in t.get("historial", []) if h.get("a") == a]

    producidas = eventos("PRODUCIDO"); auditadas = eventos("REVISION_HUMANA")
    ultima = {}
    for d in aprob: ultima[d["pieza"]] = d                            # la última decisión por pieza
    aprobadas_vigentes = {p: d for p, d in ultima.items() if d.get("decision") == "APROBADA"}
    hoy_ia = [e for e in uso if dia_mx(e.get("ts")) == hoy and e.get("proveedor") != "simulado"]
    util = sum(1 for e in hoy_ia if e.get("resultado") == "ok")
    tiempos = [e.get("segundos_ciclo", 0) / 60 for e in consumo if dia_mx(e.get("ts")) == hoy]
    prod_hoy = [p for p, _, d in producidas if d == hoy]
    decid = [d for d in aprob if dia_mx(d.get("fecha")) and dia_mx(d.get("fecha")) <= hoy]
    tasa = (sum(1 for d in decid if d["decision"] == "APROBADA") / len(decid)) if decid else None

    disp = {f: sum(1 for p in aprobadas_vigentes if cola.get(p, {}).get("formato", "reel") == f) for f in ("reel", "imagen")}
    # estimación de lanzamiento con el rendimiento observado (piezas aprobadas por día desde la primera decisión)
    inicio = min((dia_mx(d["fecha"]) for d in aprob), default=None)
    ritmo = {}
    for f in ("reel", "imagen"):
        n = disp[f]; dias = max(1, (hoy - inicio).days + 1) if inicio else None
        ritmo[f] = (n / dias) if dias else 0
    if all(disp[f] >= META[f] for f in META):
        estimada = hoy.isoformat(); base = "colchón completo"
    elif all(ritmo[f] > 0 for f in META):
        dias_falta = max(math.ceil((META[f] - disp[f]) / ritmo[f]) for f in META)
        estimada = (hoy + timedelta(days=dias_falta)).isoformat(); base = "ritmo observado de aprobaciones"
    else:
        estimada = None; base = "sin aprobaciones todavía: no se puede estimar con datos reales"
    return {
        "fecha": hoy.isoformat(),
        "1_producidas_nuevas": len(prod_hoy), "producidas_ids": prod_hoy,
        "2_superaron_auditoria": sum(1 for _, _, d in auditadas if d == hoy),
        "3_aprobadas_por_responsable": sum(1 for d in aprob if dia_mx(d.get("fecha")) == hoy and d["decision"] == "APROBADA"),
        "4_tasa_aprobacion_acumulada": None if tasa is None else round(tasa, 3), "decisiones_acumuladas": len(decid),
        "5_minutos_actions": {"hoy_ciclos_estimado": round(sum(tiempos), 1), "mes": actions},
        "6_gemini": {"utiles": util, "rechazadas": len(hoy_ia) - util,
                     "cuota": sum(1 for e in hoy_ia if e.get("resultado") != "ok" and "429" in str(e.get("error", ""))),
                     "errores_proveedor": sum(1 for e in hoy_ia if e.get("resultado") != "ok" and "429" not in str(e.get("error", "")))},
        "7_minutos_por_pieza_producida": round(sum(tiempos) / len(prod_hoy), 1) if prod_hoy else None,
        "8_costo_externo_mxn": sum(float(e.get("costo_mxn", 0) or 0) for e in consumo),
        "9_aprobadas_disponibles": disp, "dias_de_contenido": min(disp.values()),
        "10_lanzamiento_estimado": estimada, "base_estimacion": base, "lanzamiento_objetivo": LANZAMIENTO_OBJETIVO.isoformat(),
        "embudo_acumulado": {
            "solicitudes_efectivas": sum(1 for s in sols if s.get("estado") != "SUPERSEDIDA"),
            "descartadas": sum(1 for s in sols if s.get("estado") == "DESCARTADA"),
            "borradores_guion_listo": sum(1 for s in sols if s.get("estado") == "GUION_LISTO"),
            "pendientes": sum(1 for s in sols if s.get("estado") == "PENDIENTE_GUION"),
            "producidas": len({p for p, _, _ in producidas}), "en_revision": sum(1 for t in cola.values() if t["estado"] == "REVISION_HUMANA"),
            "aprobadas": len(aprobadas_vigentes), "rechazadas": sum(1 for d in ultima.values() if d.get("decision") == "RECHAZADA")},
    }


def guardar(m, raiz=RAIZ):
    f = raiz / "registro" / "metricas_diarias.jsonl"; f.parent.mkdir(parents=True, exist_ok=True)
    lineas = [l for l in _jsonl(f) if l.get("fecha") != m["fecha"]] + [m]
    f.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in sorted(lineas, key=lambda x: x["fecha"])))
    if m["5_minutos_actions"]["mes"]:
        (raiz / "registro" / "actions_mes.json").write_text(json.dumps(m["5_minutos_actions"]["mes"], ensure_ascii=False, indent=1))


def main(argv):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    act = None
    if token and repo:
        try: act = minutos_actions(repo, token)
        except Exception as e: act = {"error": f"{type(e).__name__}: {e}"[:200]}
    m = calcular(actions=act); guardar(m)
    print(json.dumps({k: m[k] for k in ("fecha", "1_producidas_nuevas", "2_superaron_auditoria", "9_aprobadas_disponibles", "10_lanzamiento_estimado")}, ensure_ascii=False))
    if "--guardia" in argv:
        seguir = not (act and "minutos" in act and act["minutos"] >= TOPE_PROPIO)
        if not seguir: print(f"::warning::Minutos de Actions del mes ({act['minutos']}) en el tope propio ({TOPE_PROPIO}); el ciclo no se ejecuta.")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as h: h.write(f"continuar={'true' if seguir else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
