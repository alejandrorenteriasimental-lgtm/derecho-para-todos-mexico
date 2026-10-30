"""Publicación del calendario de lanzamiento (data/calendario_lanzamiento.json) en Facebook e Instagram.

Reglas (instrucción del responsable, 28-10-2026):
  · Solo piezas con aprobación humana de su VERSIÓN EXACTA: antes de enviar cualquier archivo se comprueba que la
    última decisión registrada (estado/aprobaciones.jsonl) es APROBADA, que su versión y su huella de archivo coinciden
    con el calendario y que el SHA-256 del archivo descargado del respaldo es el mismo. Si algo no coincide, no se envía.
  · Facebook: se PROGRAMA con anticipación (Meta admite fechas futuras). Instagram no admite programación por API:
    se publica cuando llega la hora (este módulo corre a las 09:00 y 19:00 CDMX con publicacion.yml).
  · Modo real solo con PUBLICAR=1, LANZAMIENTO_AUTORIZADO=SI y los secretos de Meta (publicar.modo_operacion).
    Sin eso, solo se simula y se registra qué se haría.
  · PARO DE EMERGENCIA: si existe estado/pausa_publicacion.json, o la variable PAUSA_PUBLICACION=1, no se envía nada.
    Ante cualquier error no transitorio el propio módulo crea ese archivo (se detiene solo) y deja el motivo.
    Para reanudar se borra el archivo después de revisar la causa.

Uso: python sistema/publicador.py [AAAA-MM-DDTHH:MM]   (hora UTC opcional para pruebas)
"""
import hashlib, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicar, instagram

RAIZ = Path(__file__).resolve().parent.parent
CAL = RAIZ / "data" / "calendario_lanzamiento.json"
PAUSA = RAIZ / "estado" / "pausa_publicacion.json"
APROB = RAIZ / "estado" / "aprobaciones.jsonl"
MX = timezone(timedelta(hours=-6))
VENTANA_IG = timedelta(hours=3)
VETO = timedelta(hours=72)             # aprobación delegada en Claude: el responsable puede vetar durante 72 h (29-10-2026)          # si una ejecución se retrasa, se publica dentro de esta ventana; después, se avisa


class NoAprobada(Exception): pass


def pausado(env=os.environ):
    if env.get("PAUSA_PUBLICACION") == "1": return "variable PAUSA_PUBLICACION=1"
    if PAUSA.exists():
        try: return json.loads(PAUSA.read_text()).get("motivo", "pausa manual")
        except ValueError: return "pausa manual"
    return None


def pausar(motivo):
    PAUSA.parent.mkdir(parents=True, exist_ok=True)
    PAUSA.write_text(json.dumps({"desde": datetime.now(timezone.utc).isoformat(timespec="seconds"), "motivo": motivo}, ensure_ascii=False, indent=1))


def ultima_decision(pieza):
    d = None
    for l in APROB.read_text().splitlines():
        x = json.loads(l)
        if x.get("pieza") == pieza: d = x
    return d


class EnPlazoDeVeto(Exception): pass


def plazo_de_veto(d, ahora):
    """Una aprobación delegada (canal «delegada») solo habilita la publicación cuando terminan las 72 h de aviso."""
    if d and d.get("canal") == "delegada":
        fin = datetime.fromisoformat(d["fecha"]) + VETO
        if ahora < fin: return fin
    return None


def comprobar(entrada, archivo, ahora=None):
    """Aprobación de la versión exacta + archivo idéntico al aprobado (+ plazo de veto si la aprobación es delegada)."""
    d = ultima_decision(entrada["pieza"])
    if not d or d.get("decision") != "APROBADA": raise NoAprobada(f'{entrada["pieza"]}: sin aprobación vigente')
    fin = plazo_de_veto(d, ahora or datetime.now(timezone.utc))
    if fin: raise EnPlazoDeVeto(f'{entrada["pieza"]}: aprobación delegada; plazo de veto hasta {fin.isoformat(timespec="minutes")}')
    if d.get("version") != entrada["version"]: raise NoAprobada(f'{entrada["pieza"]}: versión aprobada {d.get("version")} ≠ calendario {entrada["version"]}')
    if d.get("huella_archivo") != entrada["sha256"]: raise NoAprobada(f'{entrada["pieza"]}: huella aprobada distinta del calendario')
    sha = hashlib.sha256(Path(archivo).read_bytes()).hexdigest()
    if sha != entrada["sha256"]: raise NoAprobada(f'{entrada["pieza"]}: el archivo descargado no es el aprobado ({sha[:12]})')
    return True


def descargar(entrada, destino, env=os.environ, abrir=urllib.request.urlopen):
    destino = Path(destino); destino.mkdir(parents=True, exist_ok=True); f = destino / entrada["archivo"]
    if f.exists() and hashlib.sha256(f.read_bytes()).hexdigest() == entrada["sha256"]: return f
    repo = env.get("GITHUB_REPOSITORY", "alejandrorenteriasimental-lgtm/derecho-para-todos-mexico")
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/releases/assets/{entrada["asset_id"]}',
                                 headers={"Accept": "application/octet-stream", "Authorization": f'Bearer {env.get("GITHUB_TOKEN", "")}'})
    with abrir(req, timeout=300) as r: f.write_bytes(r.read())
    return f


def texto(pieza):
    g = json.loads((RAIZ / "piezas" / pieza / "guion.json").read_text())
    return g.get("copy") or g["titulo"]


def hora_utc(fecha, hora):
    h, m = map(int, hora.split(":"))
    return datetime.fromisoformat(fecha).replace(hour=h, minute=m, tzinfo=MX).astimezone(timezone.utc)


AUT = RAIZ / "data" / "lanzamiento.json"


def con_autorizacion(env, archivo=None):
    """Variables del repositorio primero; si no están, la autorización registrada en data/lanzamiento.json."""
    archivo = archivo or AUT
    try: a = json.loads(Path(archivo).read_text())
    except (OSError, ValueError): return dict(env)
    out = dict(env)
    for k in ("PUBLICAR", "LANZAMIENTO_AUTORIZADO", "IG_REELS"):
        if not out.get(k) and a.get(k) is not None: out[k] = str(a[k])
    return out


def ejecutar(ahora=None, env=os.environ, http=publicar.http_real, bajar=descargar, carpeta="/tmp/publicacion"):
    ahora = ahora or datetime.now(timezone.utc)
    modo, motivo = publicar.modo_operacion(env)
    res = {"ahora": ahora.isoformat(timespec="minutes"), "modo": modo, "motivo": motivo, "acciones": []}
    p = pausado(env)
    if p:
        res["pausa"] = p; return res
    cal = json.loads(CAL.read_text())
    for dia in cal["dias"]:
        for fmt in ("imagen", "reel"):
            e = dia[fmt]; cuando = hora_utc(dia["fecha"], e["hora"])
            acc = {"fecha": dia["fecha"], "formato": fmt, "pieza": e["pieza"], "version": e["version"], "hora_utc": cuando.isoformat(timespec="minutes")}
            try:
                # Facebook: programar con anticipación (más de 20 min y dentro de 28 días)
                if timedelta(minutes=20) < cuando - ahora < timedelta(days=28):
                    f = bajar(e, carpeta, env); comprobar(e, f, ahora)
                    huella = e["version"]
                    if fmt == "imagen":
                        r = publicar.publicar_imagen(e["pieza"], f, texto(e["pieza"]), huella, int(cuando.timestamp()), modo=modo, env=env, http=http)
                    else:
                        r = publicar.publicar_reel(e["pieza"], f, texto(e["pieza"]), huella, int(cuando.timestamp()), modo=modo, env=env, http=http)
                    acc["facebook"] = r.get("estado")
                # Instagram: publicar al llegar la hora (sin programación por API)
                if fmt == "reel" and env.get("IG_REELS") != "1" and timedelta(0) <= ahora - cuando <= VENTANA_IG:
                    acc["instagram"] = "REEL_IG_EN_ESPERA"     # carga de Reels a IG pendiente de resolver (28-10); no detiene lo demás
                elif timedelta(0) <= ahora - cuando <= VENTANA_IG:
                    f = bajar(e, carpeta, env); comprobar(e, f, ahora)
                    r = instagram.publicar_ig(e["pieza"], fmt, f, texto(e["pieza"]), e["version"], modo=modo, env=env, http=http)
                    acc["instagram"] = r.get("estado")
                elif ahora - cuando > VENTANA_IG and modo == "real" and (fmt == "imagen" or env.get("IG_REELS") == "1"):
                    op = publicar.operacion(publicar.marca(e["pieza"], e["version"]) + "-ig", "real") or {}
                    if op.get("fase") != "CONFIRMADA": acc["instagram"] = "VENCIDA_SIN_PUBLICAR"
            except EnPlazoDeVeto as x:
                acc["espera"] = str(x)                    # no es un error: se intenta en la siguiente ejecución
            except NoAprobada as x:
                acc["error"] = str(x); pausar(f"pieza no aprobada en su versión exacta: {x}"); res["acciones"].append(acc); res["pausa"] = str(x); return res
            except publicar.PublicacionAmbigua as x:
                acc["error"] = f"ambigua: {x}"            # el siguiente ciclo la resuelve consultando el estado remoto
            except publicar.ErrorGraph as x:
                acc["error"] = str(x)
                if not x.transitorio:
                    pausar(f"error de Meta no transitorio en {e['pieza']}: {x}"); res["acciones"].append(acc); res["pausa"] = str(x); return res
            except publicar.SinRed as x:
                acc["error"] = f"sin red: {x}"
            if len(acc) > 5: res["acciones"].append(acc)
    return res


if __name__ == "__main__":
    ahora = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc) if len(sys.argv) > 1 else None
    r = ejecutar(ahora, env=con_autorizacion(os.environ))
    out = RAIZ / "registro" / "publicacion.jsonl"; out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as h: h.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if r.get("pausa") and r["modo"] == "real" else 0)
