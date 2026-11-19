"""YouTube (Shorts): carga programada de los Reels aprobados del calendario, con la API de datos de YouTube v3.

Decisión del responsable (2-11-2026): «quiero que se publique en todos lados, facebook, instagram, youtube, tiktok».
  · Solo se suben Reels (videos verticales). YouTube los clasifica como Shorts por su formato; no hay que marcarlos.
  · Se PROGRAMAN como Facebook: el video se sube privado con status.publishAt = hora del calendario y YouTube lo hace
    público a esa hora. El publicador lo llama con la misma ventana que Facebook (más de 20 min y menos de 28 días).
  · Modo real solo si: modo real de Meta (PUBLICAR=1, LANZAMIENTO_AUTORIZADO=SI) + YOUTUBE=1 + los secretos
    YT_CLIENT_ID, YT_CLIENT_SECRET y YT_REFRESH_TOKEN (proyecto de Google Cloud sin facturación; OAuth del responsable
    una sola vez). Sin eso solo se simula y se registra.
  · Idempotencia: libro estado/operaciones.jsonl con la marca «…-yt». Si una carga quedó sin confirmación (AMBIGUA),
    NO se reintenta sola: podría duplicar el video. Se revisa el canal y se resuelve a mano.
  · Un error de YouTube nunca detiene Facebook ni Instagram (lo maneja el publicador).
  · Miniatura personalizada (19-11-2026, solo el video largo semanal; el canal se verificó por teléfono el 16-11):
    poner_miniatura() llama thumbnails.set DESPUÉS de videos.insert, con su propia marca «…-yt-min» en el libro. Poner
    la misma miniatura dos veces no duplica nada, así que un fallo se reintenta (solo la miniatura, nunca el video).
Costo: 0 MXN (cuota gratuita de la API: 100 cargas al día).
"""
import json, os, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import publicar
from publicar import SinRed, http_real, marca, operacion, registrar

TOKEN_URL = "https://oauth2.googleapis.com/token"
CARGA_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
MINIATURA_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
MINIATURA_MAX_BYTES = 2 * 1024 * 1024
SECRETOS = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
CATEGORIA_EDUCACION = "27"


class ErrorYouTube(Exception):
    def __init__(self, estado, mensaje, transitorio=False):
        super().__init__(f"HTTP {estado}: {mensaje}"); self.estado = estado; self.transitorio = transitorio


class YouTubeAmbigua(Exception): pass


def modo_youtube(env=os.environ):
    modo, motivo = publicar.modo_operacion(env)
    if modo != "real": return "simulacion", motivo
    if env.get("YOUTUBE") != "1": return "simulacion", "YOUTUBE distinto de 1"
    faltan = [k for k in SECRETOS if not env.get(k)]
    if faltan: return "simulacion", f"faltan secretos de YouTube: {', '.join(faltan)}"
    return "real", "condiciones de lanzamiento y de YouTube cumplidas"


def _json(estado, cuerpo):
    try: d = json.loads(cuerpo or b"{}")
    except ValueError: raise ErrorYouTube(estado, f"respuesta no JSON: {cuerpo[:120]!r}", transitorio=estado >= 500)
    if estado >= 400:
        e = d.get("error")
        msg = (e.get("message") if isinstance(e, dict) else None) or d.get("error_description") or str(e or d)[:300]
        raise ErrorYouTube(estado, msg, transitorio=estado >= 500 or estado == 429)
    return d


def token_acceso(env, http=http_real):
    datos = urllib.parse.urlencode({"client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
                                    "refresh_token": env["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    est, cuerpo = http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, datos)
    return _json(est, cuerpo)["access_token"]


def titulo_yt(titulo):
    """YouTube admite hasta 100 caracteres y no acepta «<» ni «>»."""
    t = " ".join(titulo.replace("<", "").replace(">", "").split())
    return t if len(t) <= 100 else t[:99].rstrip() + "…"


def metadatos(titulo, descripcion, publicar_en):
    return {"snippet": {"title": titulo_yt(titulo), "description": descripcion[:4900], "categoryId": CATEGORIA_EDUCACION,
                        "defaultLanguage": "es", "defaultAudioLanguage": "es-419",
                        "tags": ["derecho", "leyes de México", "Aquí Dice la Ley"]},
            "status": {"privacyStatus": "private", "publishAt": publicar_en.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "selfDeclaredMadeForKids": False, "embeddable": True}}


def publicar_yt(pieza_id, mp4, titulo, descripcion, huella, publicar_en, modo=None, env=os.environ, http=http_real, libro=None, formato="reel"):
    """formato: «reel» (Short vertical del calendario) o «video_largo» (video semanal horizontal, youtube_semanal.py, 16-11-2026);
    YouTube decide si es Short por el formato del archivo, no por un campo de la API."""
    etiqueta = marca(pieza_id, huella) + "-yt"
    if modo is None: modo, motivo = modo_youtube(env)
    else: motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo, "formato": formato, "red": "youtube"}
    if modo == "simulacion":
        if (operacion(etiqueta, "simulacion", libro) or {}).get("fase") != "SIMULADA":
            registrar({**base, "fase": "SIMULADA", "motivo": motivo, "publicar_en": publicar_en.isoformat(timespec="minutes")}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "motivo": motivo}
    op = operacion(etiqueta, "real", libro) or {}
    if op.get("fase") == "CONFIRMADA":
        return {"estado": "PROGRAMADO", "video_id": op["video_id"], "marca": etiqueta, "origen": "libro"}
    if op.get("fase") in ("SUBIENDO", "AMBIGUA"):
        if op.get("fase") == "SUBIENDO": registrar({**base, "fase": "AMBIGUA", "motivo": "carga previa sin confirmación"}, libro)
        raise YouTubeAmbigua(f"{pieza_id}: carga previa a YouTube sin confirmación; revisar el canal antes de reintentar")
    tok = token_acceso(env, http)
    meta = json.dumps(metadatos(titulo, descripcion, publicar_en), ensure_ascii=False).encode()
    datos = Path(mp4).read_bytes()
    est, cuerpo = http("POST", CARGA_URL, {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                                           "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(datos))}, meta)
    if est >= 400: _json(est, cuerpo)
    ubicacion = _ubicacion(cuerpo)
    if not ubicacion: raise ErrorYouTube(est, "la carga reanudable no devolvió la URL de carga", transitorio=True)
    registrar({**base, "fase": "SUBIENDO", "publicar_en": publicar_en.isoformat(timespec="minutes")}, libro)
    try:
        est, cuerpo = http("PUT", ubicacion, {"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"}, datos, timeout=600)
        d = _json(est, cuerpo)
    except SinRed as e:
        registrar({**base, "fase": "AMBIGUA", "error": str(e)}, libro)
        raise YouTubeAmbigua(f"{pieza_id}: carga sin respuesta: {e}")
    except ErrorYouTube as e:
        registrar({**base, "fase": "AMBIGUA" if e.transitorio else "FALLIDA", "error": str(e)}, libro); raise
    registrar({**base, "fase": "CONFIRMADA", "video_id": d.get("id"), "estado_remoto": (d.get("status") or {}).get("privacyStatus"),
               "publish_at": (d.get("status") or {}).get("publishAt")}, libro)
    return {"estado": "PROGRAMADO", "video_id": d.get("id"), "marca": etiqueta, "origen": "videos.insert"}


def poner_miniatura(pieza_id, video_id, imagen, huella, modo=None, env=os.environ, http=http_real, libro=None):
    """thumbnails.set (subida simple, Content-Type image/png o image/jpeg) para un video ya subido. Idempotente con el libro:
    marca «…-yt-min»; si ya quedó CONFIRMADA para ese video no se repite. Un error queda como FALLIDA y se lanza."""
    etiqueta = marca(pieza_id, huella) + "-yt-min"
    if modo is None: modo, motivo = modo_youtube(env)
    else: motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo, "formato": "miniatura", "red": "youtube", "video_id": video_id}
    if modo == "simulacion":
        if (operacion(etiqueta, "simulacion", libro) or {}).get("fase") != "SIMULADA":
            registrar({**base, "fase": "SIMULADA", "motivo": motivo}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "motivo": motivo}
    op = operacion(etiqueta, "real", libro) or {}
    if op.get("fase") == "CONFIRMADA" and op.get("video_id") == video_id:
        return {"estado": "PUESTA", "video_id": video_id, "marca": etiqueta, "origen": "libro"}
    if not video_id: raise ErrorYouTube(0, "sin video_id para la miniatura")
    tipo = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(Path(imagen).suffix.lower())
    datos = Path(imagen).read_bytes()
    if not tipo or len(datos) >= MINIATURA_MAX_BYTES:
        registrar({**base, "fase": "FALLIDA", "error": "la miniatura debe ser PNG o JPEG de menos de 2 MB"}, libro)
        raise ErrorYouTube(0, "la miniatura debe ser PNG o JPEG de menos de 2 MB")
    try:
        tok = token_acceso(env, http)
        url = MINIATURA_URL + "?" + urllib.parse.urlencode({"videoId": video_id, "uploadType": "media"})
        est, cuerpo = http("POST", url, {"Authorization": f"Bearer {tok}", "Content-Type": tipo, "Content-Length": str(len(datos))}, datos, timeout=120)
        d = _json(est, cuerpo)
    except (SinRed, ErrorYouTube) as e:
        registrar({**base, "fase": "FALLIDA", "error": str(e)[:300]}, libro); raise
    registrar({**base, "fase": "CONFIRMADA", "bytes": len(datos), "items": len(d.get("items") or [])}, libro)
    return {"estado": "PUESTA", "video_id": video_id, "marca": etiqueta, "origen": "thumbnails.set"}


def _ubicacion(cuerpo):
    """http_real devuelve solo (estado, cuerpo); la URL de carga viaja en la cabecera Location. Para no cambiar la firma
    común, http_yt (abajo) la entrega como JSON {"location": …} en el cuerpo."""
    try: return json.loads(cuerpo or b"{}").get("location")
    except ValueError: return None


def http_yt(metodo, url, cabeceras=None, datos=None, timeout=60):
    """Como publicar.http_real, pero al iniciar la carga reanudable devuelve la cabecera Location en el cuerpo."""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if url.startswith(CARGA_URL.split("?")[0]) and metodo == "POST" and r.headers.get("Location"):
                return r.status, json.dumps({"location": r.headers["Location"]}).encode()
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise SinRed(str(e))
