"""Publicación en Instagram (@aquidicelaley) con la API Graph de Instagram (Content Publishing), con libro de operaciones.

Diferencias con Facebook que condicionan el diseño:
  · Instagram NO permite programar por API: la publicación se hace a la hora del calendario (un trabajo de publicación
    corre a esa hora). Crear el «contenedor» NO publica nada; solo `media_publish` lo hace visible.
  · Imagen: la API exige una URL pública. Se sube la imagen a la Página de Facebook como foto NO publicada
    (published=false, sin fecha: no la ve el público) y se usa la URL que Meta le asigna.
  · Reel: carga reanudable directa (upload_type=resumable), sin URL pública.

Idempotencia: cada fase se registra en estado/operaciones.jsonl ANTES y DESPUÉS (marca interna de publicar.marca).
Si `media_publish` responde de forma ambigua, el siguiente intento busca el texto exacto en las publicaciones recientes
de la cuenta antes de volver a publicar; nunca publica dos veces el mismo contenedor.
"""
import json, os, time
from pathlib import Path

import publicar
from publicar import Graph, ErrorGraph, SinRed, PublicacionAmbigua, registrar, operacion, marca, coincide, _json, GRAPH, http_real


def _ig_id(g, page):
    d = g.get(page, fields="instagram_business_account")
    ig = (d.get("instagram_business_account") or {}).get("id")
    if not ig: raise ErrorGraph(200, None, "la Página no tiene una cuenta de Instagram profesional vinculada", transitorio=False)
    return ig


def detalle_contenedor(g, cid):
    """Texto de estado de Meta para un contenedor fallido (p. ej. «Error: … 2207026»)."""
    try: return g.get(cid, fields="status").get("status") or ""
    except (ErrorGraph, SinRed) as e: return f"(sin detalle: {e})"


def esperar_contenedor(g, cid, intentos=30, pausa=10, dormir=time.sleep):
    """FINISHED | ERROR | EXPIRED | IN_PROGRESS (tras agotar los intentos)."""
    for _ in range(intentos):
        s = g.get(cid, fields="status_code,status").get("status_code")
        if s in ("FINISHED", "ERROR", "EXPIRED", "PUBLISHED"): return s
        dormir(pausa)
    return "IN_PROGRESS"


def url_publica_imagen(g, page, png, libro=None, base=None):
    """Foto NO publicada en la Página (invisible para el público) → URL de la imagen en los servidores de Meta."""
    cuerpo, ctype = publicar._multipart({"published": "false", "temporary": "true"}, Path(png).name, Path(png).read_bytes())
    r = _json(*g.http("POST", f"{GRAPH}/{page}/photos", g._cab({"Content-Type": ctype}), cuerpo, 180))
    fid = r.get("id")
    imgs = g.get(fid, fields="images").get("images") or []
    if not imgs: raise ErrorGraph(200, None, f"la foto no publicada {fid} no devolvió URL", transitorio=True)
    url = max(imgs, key=lambda i: i.get("width", 0))["source"]
    if base is not None: registrar({**base, "fase": "IMAGEN_ALOJADA", "foto_no_publicada": fid}, libro)
    return url


def url_publica_video(g, page, mp4, libro=None, base=None, intentos=18, pausa=10, dormir=time.sleep):
    """Video NO publicado en la Página (published=false, sin historia: no lo ve el público) → URL del archivo en los
    servidores de Meta. Respaldo cuando la carga reanudable de Instagram falla (prueba no pública del 28-10:
    «Request processing failed» en rupload ig-api-upload)."""
    cuerpo, ctype = publicar._multipart({"published": "false", "no_story": "true"}, Path(mp4).name, Path(mp4).read_bytes(), "video/mp4")
    vid = _json(*g.http("POST", f"{GRAPH}/{page}/videos", g._cab({"Content-Type": ctype}), cuerpo, 900)).get("id")
    if base is not None: registrar({**base, "fase": "VIDEO_ALOJADO", "video_no_publicado": vid}, libro)
    for _ in range(intentos):
        src = g.get(vid, fields="source").get("source")
        if src: return src
        dormir(pausa)
    raise ErrorGraph(200, None, f"el video no publicado {vid} no devolvió URL", transitorio=True)


def crear_contenedor(g, ig, formato, archivo, texto, page=None, libro=None, base=None, dormir=time.sleep):
    """Crea el contenedor (NO publica). Devuelve su id."""
    if formato == "imagen":
        url = url_publica_imagen(g, page, archivo, libro, base)
        return g.post(f"{ig}/media", image_url=url, caption=texto).get("id")
    try:
        r = g.post(f"{ig}/media", media_type="REELS", upload_type="resumable", caption=texto, share_to_feed="true")
    except ErrorGraph as e:
        raise ErrorGraph(e.estado, e.codigo, f"creación del contenedor de Reel: {e}", transitorio=e.transitorio)
    cid, uri = r.get("id"), r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{publicar.GRAPH_VERSION}/{r.get('id')}"
    if base is not None: registrar({**base, "fase": "CONTENEDOR_CREADO", "contenedor": cid}, libro)
    datos = Path(archivo).read_bytes()
    try:
        up = g.subir(uri, datos)
        if not up.get("success", True): raise ErrorGraph(200, None, f"carga no confirmada: {up}", transitorio=True)
    except ErrorGraph as e:
        if e.transitorio or not page: raise ErrorGraph(e.estado, e.codigo, f"carga del video a Instagram: {e}", transitorio=e.transitorio)
        # respaldo: el video se aloja como NO publicado en la Página y se crea otro contenedor con su URL
        if base is not None: registrar({**base, "fase": "CARGA_REANUDABLE_FALLIDA", "contenedor": cid, "error": str(e)[:200]}, libro)
        url = url_publica_video(g, page, archivo, libro, base, dormir=dormir)
        cid = g.post(f"{ig}/media", media_type="REELS", video_url=url, caption=texto, share_to_feed="true").get("id")
        if base is not None: registrar({**base, "fase": "CONTENEDOR_CREADO", "contenedor": cid, "via": "video_url"}, libro)
    return cid


def buscar_publicado(g, ig, texto):
    d = g.get(f"{ig}/media", fields="id,caption,timestamp", limit=25)
    for m in d.get("data", []):
        if coincide(m.get("caption"), texto): return m["id"]
    return None


def publicar_ig(pieza_id, formato, archivo, texto, huella, modo=None, env=os.environ, http=http_real, libro=None, dormir=time.sleep):
    etiqueta = marca(pieza_id, huella) + "-ig"
    if modo is None: modo, motivo = publicar.modo_operacion(env)
    else: motivo = "modo indicado por quien llama"
    base = {"pieza": pieza_id, "marca": etiqueta, "modo": modo, "formato": formato, "red": "instagram"}
    if modo == "simulacion":
        registrar({**base, "fase": "SIMULADA", "motivo": motivo}, libro)
        return {"estado": "SIMULADO", "marca": etiqueta, "motivo": motivo}
    page = env["META_PAGE_ID"]; g = Graph(env["META_PAGE_TOKEN"], http)
    ig = env.get("META_IG_ID") or _ig_id(g, page)
    op = operacion(etiqueta, "real", libro) or {}
    if op.get("fase") == "CONFIRMADA":
        return {"estado": "PUBLICADO", "media_id": op["media_id"], "marca": etiqueta, "origen": "libro"}
    previo = buscar_publicado(g, ig, texto)
    if previo:
        registrar({**base, "fase": "CONFIRMADA", "media_id": previo, "origen": "recuperada_por_texto"}, libro)
        return {"estado": "PUBLICADO", "media_id": previo, "marca": etiqueta, "origen": "recuperada_por_texto"}
    if op.get("fase") == "AMBIGUA":
        raise ErrorGraph(0, None, "publicación ambigua previa sin confirmación; revisar la cuenta antes de reintentar", transitorio=False)
    cid = op.get("contenedor")
    if cid and esperar_contenedor(g, cid, intentos=1, dormir=dormir) in ("ERROR", "EXPIRED"):
        cid = None
    if not cid:
        registrar({**base, "fase": "CREANDO_CONTENEDOR"}, libro)
        cid = crear_contenedor(g, ig, formato, archivo, texto, page, libro, base, dormir)
        registrar({**base, "fase": "CONTENEDOR_CREADO", "contenedor": cid}, libro)
    est = esperar_contenedor(g, cid, dormir=dormir)
    if est != "FINISHED":
        registrar({**base, "fase": "FALLIDA" if est in ("ERROR", "EXPIRED") else "PROCESANDO", "contenedor": cid, "estado_contenedor": est}, libro)
        raise ErrorGraph(200, None, f"contenedor {cid} en estado {est}: {detalle_contenedor(g, cid)}", transitorio=(est == "IN_PROGRESS"))
    registrar({**base, "fase": "PUBLICANDO", "contenedor": cid}, libro)
    try:
        r = g.post(f"{ig}/media_publish", timeout=120, creation_id=cid)
    except (SinRed, ErrorGraph) as e:
        if isinstance(e, ErrorGraph) and not e.transitorio:
            registrar({**base, "fase": "FALLIDA", "contenedor": cid, "error": str(e)}, libro); raise
        registrar({**base, "fase": "AMBIGUA", "contenedor": cid, "error": str(e)}, libro)
        raise PublicacionAmbigua(f"media_publish sin respuesta confirmada: {e}")
    registrar({**base, "fase": "CONFIRMADA", "contenedor": cid, "media_id": r.get("id"), "origen": "media_publish"}, libro)
    return {"estado": "PUBLICADO", "media_id": r.get("id"), "marca": etiqueta, "origen": "media_publish"}
