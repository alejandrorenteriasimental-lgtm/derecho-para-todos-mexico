"""Publicación de Reels en una Página de Facebook (Graph API · Reels Publishing API) con libro de operaciones.

MODOS
  · simulacion (predeterminado): no hace ninguna llamada a Meta. Registra la operación como SIMULADA y la pieza
    pasa al estado SIMULADO. Nunca se guarda un identificador remoto ni se marca nada como programado o publicado.
  · real: solo si PUBLICAR=1, LANZAMIENTO_AUTORIZADO=SI y existen META_PAGE_ID y META_PAGE_TOKEN. Cualquier
    condición faltante devuelve a simulación y queda registrada.

IDEMPOTENCIA (Meta no ofrece llave de idempotencia)
  1. Cada pieza tiene UNA operación en estado/operaciones.jsonl, identificada por su marca #dpt-<id>-<huella8>
     (huella = hash del guion aprobado, estable entre ejecuciones aunque el MP4 se vuelva a renderizar).
  2. Cada fase se registra ANTES y DESPUÉS de ejecutarse: SESION_CREADA (video_id, upload_url) → BYTES_SUBIDOS →
     FINALIZANDO → FINALIZADA → CONFIRMADA. Si una ejecución muere a la mitad, la siguiente retoma la MISMA
     sesión (mismo video_id) consultando su estado en Meta; nunca abre una segunda sesión mientras la primera
     pueda seguir viva.
  3. Solo la fase «finish» puede crear una publicación visible, y siempre se aplica al mismo video_id. Si su
     respuesta es ambigua (tiempo agotado, error 5xx, cuerpo ilegible) la operación queda AMBIGUA y el siguiente
     ciclo consulta el estado del video antes de hacer cualquier otra cosa.
  4. Si no hay operación local, se busca la marca en los Reels de la página (con paginación) antes de subir.
"""
import json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

GRAPH_VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
RAIZ = Path(__file__).resolve().parent.parent
LIBRO = RAIZ / "estado" / "operaciones.jsonl"
CODIGOS_TRANSITORIOS = {1, 2, 4, 17, 32, 341, 368, 613, 80001}   # límites de tasa y fallas temporales de Graph API
CODIGOS_TOKEN = {102, 190}


class SinRed(Exception): pass
class ErrorGraph(Exception):
    def __init__(self, estado, codigo, mensaje, transitorio):
        super().__init__(f"HTTP {estado} · código {codigo}: {mensaje}")
        self.estado, self.codigo, self.transitorio = estado, codigo, transitorio
class PublicacionAmbigua(Exception): pass


# ---------------- transporte (inyectable para pruebas) ----------------
def http_real(metodo, url, cabeceras=None, datos=None, timeout=60):
    req = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise SinRed(str(e))


def _json(estado, cuerpo):
    try:
        d = json.loads(cuerpo or b"{}")
    except ValueError:
        raise ErrorGraph(estado, None, f"respuesta no JSON: {cuerpo[:120]!r}", transitorio=estado >= 500)
    if estado >= 400 or "error" in d:
        e = d.get("error", {})
        cod = e.get("code")
        raise ErrorGraph(estado, cod, e.get("message", "sin mensaje"), transitorio=(estado >= 500 or cod in CODIGOS_TRANSITORIOS))
    return d


class Graph:
    def __init__(self, token, http=http_real):
        self.token, self.http = token, http

    def _cab(self, extra=None):
        return {"Authorization": f"OAuth {self.token}", **(extra or {})}   # el token nunca va en la URL

    def get(self, ruta_o_url, **params):
        url = ruta_o_url if ruta_o_url.startswith("https://") else f"{GRAPH}/{ruta_o_url}"
        if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        return _json(*self.http("GET", url, self._cab()))

    def post(self, ruta, timeout=60, **campos):
        return _json(*self.http("POST", f"{GRAPH}/{ruta}", self._cab({"Content-Type": "application/x-www-form-urlencoded"}),
                                urllib.parse.urlencode(campos).encode(), timeout))

    def subir(self, upload_url, datos, offset=0):
        cab = self._cab({"offset": str(offset), "file_size": str(len(datos) + offset), "Content-Type": "application/octet-stream"})
        return _json(*self.http("POST", upload_url, cab, datos, 900))


# ---------------- libro de operaciones ----------------
def marca(pieza_id, huella):
    return f"#dpt-{pieza_id.lower()}-{huella[:8]}"


def registrar(evento, libro=None):
    libro = Path(libro or LIBRO); libro.parent.mkdir(parents=True, exist_ok=True)
    ev = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evento}
    with open(libro, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n"); f.flush(); os.fsync(f.fileno())   # durable antes de seguir
    return ev


def operacion(etiqueta, modo="real", libro=None):
    """Estado acumulado de la operación (último valor de cada campo) para una marca."""
    libro = Path(libro or LIBRO); op = None
    if not libro.exists(): return None
    for l in libro.read_text().splitlines():
        if not l.strip(): continue
        e = json.loads(l)
        if e.get("marca") == etiqueta and e.get("modo") == modo:
            op = {**(op or {}), **{k: v for k, v in e.items() if v is not None}}
    return op


def modo_operacion(env=os.environ):
    faltan = [k for k in ("META_PAGE_ID", "META_PAGE_TOKEN") if not env.get(k)]
    if env.get("PUBLICAR") != "1":
        return "simulacion", "PUBLICAR distinto de 1"
    if env.get("LANZAMIENTO_AUTORIZADO") != "SI":
        return "simulacion", "falta la autorización expresa de lanzamiento (LANZAMIENTO_AUTORIZADO=SI)"
    if faltan:
        return "simulacion", f"faltan secretos: {', '.join(faltan)}"
    return "real", "condiciones de lanzamiento cumplidas"


# ---------------- consulta remota ----------------
def buscar_en_pagina(g, page, etiqueta, paginas=4):
    url = f"{page}/video_reels"; params = {"fields": "id,description,created_time", "limit": 50}
    for _ in range(paginas):
        d = g.get(url, **params)
        for v in d.get("data", []):
            if etiqueta in (v.get("description") or ""):
                return v["id"]
        url = d.get("paging", {}).get("next"); params = {}
        if not url: break
    return None


def estado_video(g, video_id):
    """Devuelve 'PUBLICADO' | 'PROGRAMADO' | 'SUBIDO' | ('SUBIENDO', bytes) | 'ERROR' | 'INEXISTENTE'."""
    try:
        s = g.get(video_id, fields="status").get("status", {})
    except ErrorGraph as e:
        if e.estado == 404 or e.codigo == 100: return "INEXISTENTE", 0
        raise
    pub = (s.get("publishing_phase") or {})
    if pub.get("publish_status") == "published" or s.get("video_status") == "published": return "PUBLICADO", 0
    if pub.get("publish_status") == "scheduled" or s.get("video_status") == "scheduled": return "PROGRAMADO", 0
    if s.get("video_status") == "error" or (s.get("processing_phase") or {}).get("status") == "error": return "ERROR", 0
    up = s.get("uploading_phase") or {}
    if up.get("status") == "complete": return "SUBIDO", 0
    return "SUBIENDO", int(up.get("bytes_transferred") or 0)


# ---------------- publicación ----------------
def publicar_reel(pieza_id, mp4, descripcion, huella, programar_unix=None, modo=None, env=os.environ, http=http_real, libro=None):
    etiqueta = marca(pieza_id, huella)
    texto = f"{descripcion}\n\n{etiqueta}"
    if modo is None:
        modo, motivo = modo_operacion(env)
    else:
        motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo}

    if modo == "simulacion":
        registrar({**base, "fase": "SIMULADA", "motivo": motivo, "programar_unix": programar_unix}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "descripcion": texto, "motivo": motivo}

    page, g = env["META_PAGE_ID"], Graph(env["META_PAGE_TOKEN"], http)
    op = operacion(etiqueta, "real", libro) or {}

    def confirmar(estado_remoto, vid, origen):
        registrar({**base, "fase": "CONFIRMADA", "video_id": vid, "estado_remoto": estado_remoto, "origen": origen}, libro)
        return {"estado": estado_remoto, "video_id": vid, "marca": etiqueta, "origen": origen}

    if op.get("fase") == "CONFIRMADA":
        return {"estado": op["estado_remoto"], "video_id": op["video_id"], "marca": etiqueta, "origen": "libro"}

    vid = op.get("video_id")
    if vid:   # hay una sesión previa: se retoma, nunca se duplica
        est, transferidos = estado_video(g, vid)
        if est in ("PUBLICADO", "PROGRAMADO"):
            return confirmar(est, vid, "recuperada_por_estado")
        if est in ("ERROR", "INEXISTENTE"):
            previo = buscar_en_pagina(g, page, etiqueta)
            if previo: return confirmar("PUBLICADO", previo, "recuperada_por_marca")
            registrar({**base, "fase": "ABANDONADA", "video_id": vid, "motivo": f"sesión previa en estado {est}"}, libro)
            vid = None
        elif est == "SUBIENDO":
            datos = Path(mp4).read_bytes()
            r = g.subir(op["upload_url"], datos[transferidos:], offset=transferidos)
            if not r.get("success"): raise ErrorGraph(200, None, f"subida no confirmada: {r}", transitorio=True)
            registrar({**base, "fase": "BYTES_SUBIDOS", "video_id": vid, "reanudada_desde": transferidos}, libro)
    else:
        previo = buscar_en_pagina(g, page, etiqueta)
        if previo:
            return confirmar("PUBLICADO", previo, "recuperada_por_marca")

    if not vid:
        registrar({**base, "fase": "INICIANDO"}, libro)
        r = g.post(f"{page}/video_reels", upload_phase="start")
        vid = r.get("video_id")
        if not vid: raise ErrorGraph(200, None, f"start sin video_id: {r}", transitorio=True)
        upload_url = r.get("upload_url") or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{vid}"
        registrar({**base, "fase": "SESION_CREADA", "video_id": vid, "upload_url": upload_url}, libro)
        datos = Path(mp4).read_bytes()
        r = g.subir(upload_url, datos)
        if not r.get("success"): raise ErrorGraph(200, None, f"subida no confirmada: {r}", transitorio=True)
        registrar({**base, "fase": "BYTES_SUBIDOS", "video_id": vid, "bytes": len(datos)}, libro)

    campos = {"upload_phase": "finish", "video_id": vid, "description": texto}
    if programar_unix:
        campos.update(video_state="SCHEDULED", scheduled_publish_time=str(int(programar_unix)))
    else:
        campos["video_state"] = "PUBLISHED"
    registrar({**base, "fase": "FINALIZANDO", "video_id": vid, "programar_unix": programar_unix}, libro)
    try:
        r = g.post(f"{page}/video_reels", timeout=120, **campos)
    except (SinRed, ErrorGraph) as e:
        if isinstance(e, ErrorGraph) and not e.transitorio:
            registrar({**base, "fase": "FALLIDA", "video_id": vid, "error": str(e)}, libro); raise
        registrar({**base, "fase": "AMBIGUA", "video_id": vid, "error": str(e)}, libro)
        raise PublicacionAmbigua(f"finish sin respuesta confirmada para {vid}: {e}")
    if not r.get("success", False):
        registrar({**base, "fase": "AMBIGUA", "video_id": vid, "error": f"respuesta sin success: {r}"}, libro)
        raise PublicacionAmbigua(f"finish respondió sin success para {vid}")
    registrar({**base, "fase": "FINALIZADA", "video_id": vid, "post_id": r.get("post_id")}, libro)
    est, _ = estado_video(g, vid)
    if est in ("PUBLICADO", "PROGRAMADO"):
        return confirmar(est, vid, "finish")
    return {"estado": "PUBLICANDO", "video_id": vid, "marca": etiqueta, "origen": "procesando en Meta; se confirmará en el siguiente ciclo"}


# ---------------- imagen fija (Página de Facebook · /photos) ----------------
def _multipart(campos, nombre_archivo, datos, tipo="image/png"):
    import uuid
    b = uuid.uuid4().hex; partes = []
    for k, v in campos.items():
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(f'--{b}\r\nContent-Disposition: form-data; name="source"; filename="{nombre_archivo}"\r\nContent-Type: {tipo}\r\n\r\n'.encode() + datos + b"\r\n")
    partes.append(f"--{b}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={b}"


def buscar_publicacion(g, page, etiqueta):
    for ruta in (f"{page}/scheduled_posts", f"{page}/posts"):
        try:
            d = g.get(ruta, fields="id,message", limit=50)
        except ErrorGraph:
            continue
        for p in d.get("data", []):
            if etiqueta in (p.get("message") or ""):
                return p["id"], ("PROGRAMADO" if "scheduled" in ruta else "PUBLICADO")
    return None, None


def publicar_imagen(pieza_id, png, texto, huella, programar_unix=None, modo=None, env=os.environ, http=http_real, libro=None):
    """Una sola llamada crea la publicación; por eso el riesgo de duplicado está en respuestas ambiguas:
    antes de cualquier intento se busca la marca en las publicaciones programadas y publicadas de la página."""
    etiqueta = marca(pieza_id, huella); mensaje = f"{texto}\n\n{etiqueta}"
    if modo is None: modo, motivo = modo_operacion(env)
    else: motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo, "formato": "imagen"}
    if modo == "simulacion":
        registrar({**base, "fase": "SIMULADA", "motivo": motivo, "programar_unix": programar_unix}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "descripcion": mensaje, "motivo": motivo}
    page, g = env["META_PAGE_ID"], Graph(env["META_PAGE_TOKEN"], http)
    op = operacion(etiqueta, "real", libro) or {}
    if op.get("fase") == "CONFIRMADA":
        return {"estado": op["estado_remoto"], "post_id": op["post_id"], "marca": etiqueta, "origen": "libro"}
    pid, est = buscar_publicacion(g, page, etiqueta)
    if pid:
        registrar({**base, "fase": "CONFIRMADA", "post_id": pid, "estado_remoto": est, "origen": "recuperada_por_marca"}, libro)
        return {"estado": est, "post_id": pid, "marca": etiqueta, "origen": "recuperada_por_marca"}
    if op.get("fase") == "AMBIGUA" and op.get("intentos_ambiguos", 0) >= 1:
        # ya hubo una respuesta ambigua y la marca no aparece: no se reintenta a ciegas, se pide revisión
        raise ErrorGraph(0, None, "respuesta ambigua previa sin confirmación; revisar la página manualmente", transitorio=False)
    campos = {"message": mensaje}
    if programar_unix:
        campos.update(published="false", scheduled_publish_time=str(int(programar_unix)), unpublished_content_type="SCHEDULED")
    cuerpo, ctype = _multipart(campos, Path(png).name, Path(png).read_bytes())
    registrar({**base, "fase": "ENVIANDO"}, libro)
    try:
        r = _json(*g.http("POST", f"{GRAPH}/{page}/photos", g._cab({"Content-Type": ctype}), cuerpo, 180))
    except (SinRed, ErrorGraph) as e:
        if isinstance(e, ErrorGraph) and not e.transitorio:
            registrar({**base, "fase": "FALLIDA", "error": str(e)}, libro); raise
        registrar({**base, "fase": "AMBIGUA", "error": str(e), "intentos_ambiguos": op.get("intentos_ambiguos", 0) + 1}, libro)
        raise PublicacionAmbigua(f"/photos sin respuesta confirmada: {e}")
    post = r.get("post_id") or r.get("id")
    est = "PROGRAMADO" if programar_unix else "PUBLICADO"
    registrar({**base, "fase": "CONFIRMADA", "post_id": post, "estado_remoto": est, "origen": "photos"}, libro)
    return {"estado": est, "post_id": post, "marca": etiqueta, "origen": "photos"}
