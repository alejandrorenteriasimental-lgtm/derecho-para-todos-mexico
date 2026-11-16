"""TikTok: envío del Reel aprobado del día siguiente a la BANDEJA de @aquidicelaley como borrador (Content Posting API,
permiso video.upload). El responsable lo publica desde la app (abre el borrador, pega el texto y toca «Publicar»).

Decisión del responsable (2-11-2026): publicar en todas las redes; en TikTok, mientras la app no pase la auditoría de
TikTok (sin ella, la publicación directa por API queda privada), el sistema deja el borrador y le recuerda publicarlo.
Mismo método que usa Cronista Imposible, pero con app, credenciales y archivos propios de Aquí Dice la Ley.

Reglas:
  · Solo versiones aprobadas exactas y fuera del plazo de veto (publicador.comprobar), igual que Facebook.
  · Modo real solo con PUBLICAR=1, LANZAMIENTO_AUTORIZADO=SI, TIKTOK=1, los secretos TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET, TIKTOK_CLAVE y el archivo cifrado de tokens (estado/tiktok_token.enc). Sin eso, simula.
  · Tokens: TikTok puede entregar una clave de renovación nueva en cada renovación. Se guarda CIFRADA (Fernet con una
    llave derivada de TIKTOK_CLAVE, que solo vive en los secretos) en estado/tiktok_token.enc y se confirma en git en
    cada ejecución, para no perderla. Nunca se imprime ni se registra en claro.
  · Idempotencia: marca «…-tt» en estado/operaciones.jsonl. Un envío sin confirmación no se repite solo (AMBIGUA).
  · Un error de TikTok no detiene Facebook, Instagram ni YouTube (corre en su propio flujo, tiktok.yml).
Costo: 0 MXN.

Uso: python sistema/tiktok.py [AAAA-MM-DD]     (fecha del calendario a enviar; por omisión, mañana en CDMX)
"""
import base64, hashlib, json, os, sys, time, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicar, publicador
from publicar import SinRed, marca, operacion, registrar

RAIZ = Path(__file__).resolve().parent.parent
TOKENS = RAIZ / "estado" / "tiktok_token.enc"
API = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{API}/oauth/token/"
SECRETOS = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_CLAVE")


class ErrorTikTok(Exception):
    def __init__(self, estado, mensaje, transitorio=False):
        super().__init__(f"HTTP {estado}: {mensaje}"); self.estado = estado; self.transitorio = transitorio


class TikTokAmbigua(Exception): pass


# ── tokens cifrados ──────────────────────────────────────────────────────────────────────────────────────────────
def _fernet(clave):
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("aquidicelaley-tiktok:" + clave).encode()).digest()))


def leer_tokens(clave, archivo=None):
    archivo = Path(archivo or TOKENS)
    if not archivo.exists(): return None
    return json.loads(_fernet(clave).decrypt(archivo.read_bytes()))


def guardar_tokens(clave, datos, archivo=None):
    archivo = Path(archivo or TOKENS); archivo.parent.mkdir(parents=True, exist_ok=True)
    guardar = {k: datos[k] for k in ("access_token", "refresh_token", "open_id", "expira", "renovacion_expira") if k in datos}
    archivo.write_bytes(_fernet(clave).encrypt(json.dumps(guardar).encode()))


def _json(estado, cuerpo):
    try: d = json.loads(cuerpo or b"{}")
    except ValueError: raise ErrorTikTok(estado, f"respuesta no JSON: {cuerpo[:120]!r}", transitorio=estado >= 500)
    err = d.get("error")
    codigo = err.get("code") if isinstance(err, dict) else err
    if estado >= 400 or (codigo and codigo != "ok"):
        msg = (err.get("message") if isinstance(err, dict) else None) or d.get("error_description") or str(codigo)
        raise ErrorTikTok(estado, f"{codigo}: {msg}", transitorio=estado >= 500 or estado == 429 or codigo == "rate_limit_exceeded")
    return d


def _con_vencimientos(d, ahora):
    return {**d, "expira": (ahora + timedelta(seconds=int(d.get("expires_in", 0)))).isoformat(),
            "renovacion_expira": (ahora + timedelta(seconds=int(d.get("refresh_expires_in", 0)))).isoformat()}


def canjear_codigo(env, codigo, redirect_uri, http=publicar.http_real, archivo=None, ahora=None):
    """Conexión inicial (una vez): canjea el código de autorización de OAuth por tokens y los guarda cifrados."""
    datos = urllib.parse.urlencode({"client_key": env["TIKTOK_CLIENT_KEY"], "client_secret": env["TIKTOK_CLIENT_SECRET"],
                                    "code": codigo, "grant_type": "authorization_code", "redirect_uri": redirect_uri}).encode()
    d = _json(*http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, datos))
    guardar_tokens(env["TIKTOK_CLAVE"], _con_vencimientos(d, ahora or datetime.now(timezone.utc)), archivo)
    return {"open_id": d.get("open_id"), "alcances": d.get("scope")}


def token_vigente(env, http=publicar.http_real, archivo=None, ahora=None):
    """Devuelve un token de acceso válido; si vence en menos de 1 h, lo renueva y guarda la clave de renovación nueva."""
    ahora = ahora or datetime.now(timezone.utc)
    t = leer_tokens(env["TIKTOK_CLAVE"], archivo)
    if not t: raise ErrorTikTok(0, "sin tokens: falta la conexión inicial (tiktok-conectar.yml)")
    if datetime.fromisoformat(t["expira"]) - ahora > timedelta(hours=1): return t["access_token"]
    if datetime.fromisoformat(t["renovacion_expira"]) <= ahora:
        raise ErrorTikTok(0, "la clave de renovación venció: repetir la conexión inicial (tiktok-conectar.yml)")
    datos = urllib.parse.urlencode({"client_key": env["TIKTOK_CLIENT_KEY"], "client_secret": env["TIKTOK_CLIENT_SECRET"],
                                    "grant_type": "refresh_token", "refresh_token": t["refresh_token"]}).encode()
    d = _json(*http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, datos))
    guardar_tokens(env["TIKTOK_CLAVE"], _con_vencimientos({**t, **d}, ahora), archivo)
    return d["access_token"]


# ── envío a la bandeja ───────────────────────────────────────────────────────────────────────────────────────────
def modo_tiktok(env=os.environ, archivo=None):
    modo, motivo = publicar.modo_operacion(env)
    if modo != "real": return "simulacion", motivo
    if env.get("TIKTOK") != "1": return "simulacion", "TIKTOK distinto de 1"
    faltan = [k for k in SECRETOS if not env.get(k)]
    if faltan: return "simulacion", f"faltan secretos de TikTok: {', '.join(faltan)}"
    if not Path(archivo or TOKENS).exists(): return "simulacion", "falta la conexión inicial de TikTok (tiktok-conectar.yml)"
    return "real", "condiciones de lanzamiento y de TikTok cumplidas"


def enviar_a_bandeja(pieza_id, mp4, huella, modo=None, env=os.environ, http=publicar.http_real, libro=None, archivo=None,
                     dormir=time.sleep, ahora=None):
    etiqueta = marca(pieza_id, huella) + "-tt"
    if modo is None: modo, motivo = modo_tiktok(env, archivo)
    else: motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo, "formato": "reel", "red": "tiktok"}
    if modo == "simulacion":
        if (operacion(etiqueta, "simulacion", libro) or {}).get("fase") != "SIMULADA":
            registrar({**base, "fase": "SIMULADA", "motivo": motivo}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "motivo": motivo}
    op = operacion(etiqueta, "real", libro) or {}
    if op.get("fase") == "CONFIRMADA": return {"estado": "EN_BANDEJA", "publish_id": op["publish_id"], "marca": etiqueta, "origen": "libro"}
    if op.get("fase") in ("SUBIENDO", "AMBIGUA"):
        if op.get("fase") == "SUBIENDO": registrar({**base, "fase": "AMBIGUA", "motivo": "envío previo sin confirmación"}, libro)
        raise TikTokAmbigua(f"{pieza_id}: envío previo a TikTok sin confirmación; revisar la bandeja antes de reintentar")
    tok = token_vigente(env, http, archivo, ahora)
    datos = Path(mp4).read_bytes(); n = len(datos)
    cab = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    ini = _json(*http("POST", f"{API}/post/publish/inbox/video/init/", cab,
                      json.dumps({"source_info": {"source": "FILE_UPLOAD", "video_size": n, "chunk_size": n, "total_chunk_count": 1}}).encode()))
    pid, url = ini["data"]["publish_id"], ini["data"]["upload_url"]
    registrar({**base, "fase": "SUBIENDO", "publish_id": pid}, libro)
    try:
        est, cuerpo = http("PUT", url, {"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{n - 1}/{n}", "Content-Length": str(n)}, datos, timeout=600)
        if est >= 400: _json(est, cuerpo)
        estado = "PROCESSING_UPLOAD"
        for _ in range(18):
            s = _json(*http("POST", f"{API}/post/publish/status/fetch/", cab, json.dumps({"publish_id": pid}).encode()))
            estado = (s.get("data") or {}).get("status", estado)
            if estado in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"): break
            dormir(10)
    except SinRed as e:
        registrar({**base, "fase": "AMBIGUA", "publish_id": pid, "error": str(e)}, libro)
        raise TikTokAmbigua(f"{pieza_id}: envío sin respuesta: {e}")
    except ErrorTikTok as e:
        registrar({**base, "fase": "AMBIGUA" if e.transitorio else "FALLIDA", "publish_id": pid, "error": str(e)}, libro); raise
    if estado == "FAILED":
        registrar({**base, "fase": "FALLIDA", "publish_id": pid, "estado_remoto": estado}, libro)
        raise ErrorTikTok(200, f"TikTok rechazó el video ({pid})")
    if estado not in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
        registrar({**base, "fase": "AMBIGUA", "publish_id": pid, "estado_remoto": estado}, libro)
        raise TikTokAmbigua(f"{pieza_id}: TikTok sigue procesando ({estado}); revisar la bandeja")
    registrar({**base, "fase": "CONFIRMADA", "publish_id": pid, "estado_remoto": estado}, libro)
    return {"estado": "EN_BANDEJA", "publish_id": pid, "marca": etiqueta, "origen": "inbox"}


def ejecutar(fecha=None, env=os.environ, http=publicar.http_real, bajar=publicador.descargar, carpeta="/tmp/tiktok", ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    fecha = fecha or (ahora.astimezone(publicador.MX) + timedelta(days=1)).date().isoformat()
    res = {"ahora": ahora.isoformat(timespec="minutes"), "fecha": fecha, "red": "tiktok"}
    p = publicador.pausado(env)
    if p: return {**res, "pausa": p}
    dia = next((d for d in json.loads(publicador.CAL.read_text())["dias"] if d["fecha"] == fecha), None)
    if not dia: return {**res, "estado": "SIN_REEL_EN_CALENDARIO"}
    desde = publicador.desde_efectivo(env, json.loads(publicador.CAL.read_text()))   # 16-11: el responsable incluyó TikTok en el adelanto
    if desde and fecha < desde: return {**res, "estado": "SIN_AUTORIZACION_DE_PUBLICACION"}
    if env.get("PUBLICAR_HASTA") and fecha > env["PUBLICAR_HASTA"]: return {**res, "estado": "SIN_AUTORIZACION_DE_PUBLICACION"}
    if "reel" not in dia: return {**res, "estado": "SIN_REEL_EN_CALENDARIO"}
    e = dia["reel"]; res.update(pieza=e["pieza"], version=e["version"])
    try:
        f = bajar(e, carpeta, env); publicador.comprobar(e, f, ahora)
        r = enviar_a_bandeja(e["pieza"], f, e["version"], env=env, http=http, ahora=ahora)
        res["estado"] = r["estado"]
        res["copy"] = publicador.texto(e["pieza"])        # el recordatorio lo entrega al responsable para pegarlo
    except publicador.EnPlazoDeVeto as x: res["estado"] = "EN_PLAZO_DE_VETO"; res["detalle"] = str(x)
    except publicador.NoAprobada as x: res["estado"] = "NO_APROBADA"; res["error"] = str(x)
    except (ErrorTikTok, TikTokAmbigua, SinRed) as x: res["estado"] = "ERROR"; res["error"] = str(x)
    return res


if __name__ == "__main__":
    r = ejecutar(sys.argv[1] if len(sys.argv) > 1 else None, env=publicador.con_autorizacion(os.environ))
    out = RAIZ / "registro" / "tiktok.jsonl"; out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as h: h.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in r.items() if k != "copy"}, ensure_ascii=False, indent=1))
