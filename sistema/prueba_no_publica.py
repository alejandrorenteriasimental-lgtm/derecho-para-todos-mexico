"""Prueba REAL de las integraciones de Meta SIN publicar nada visible para el público (manual, meta-prueba.yml).

Usa piezas ya aprobadas, descargadas del respaldo (GitHub Release), y verifica:
  1. Autenticación y permisos (incluye los de publicación).
  2. Facebook · imagen: foto NO publicada (published=false, sin fecha) → se comprueba que existe y que no es visible.
  3. Facebook · Reel: sesión start → carga completa de bytes → estado de carga en Meta; NO se ejecuta «finish»
     (es la fase que crea la publicación), así que nada se publica ni se programa.
  4. Instagram · imagen y Reel: contenedores creados y procesados hasta FINISHED (compatibilidad de formato);
     NO se llama a media_publish.
  5. Prevención de duplicados: búsqueda por texto en las publicaciones de la página y de la cuenta.
Cada paso queda en registro/meta_prueba_no_publica.json con su resultado. Nunca imprime el token.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicar, instagram
from publicar import Graph, ErrorGraph, SinRed

RAIZ = Path(__file__).resolve().parent.parent
PERMISOS = {"pages_manage_posts", "pages_read_engagement", "pages_show_list", "instagram_basic", "instagram_content_publish"}


def variante_ig(reel, variante):
    """Derivado del Reel aprobado, SOLO para diagnóstico no público (nunca se publica):
    «recorte:N» = primeros N s sin recodificar el video; «desde:N» = del segundo N al final; «silencio» = video completo con audio silencioso; «recodificar» = completo recodificado; «unaparte» = completo en un solo POST."""
    import subprocess
    if not variante: return reel, ""
    out = Path("/tmp") / f"variante_{variante.replace(':', '_')}.mp4"
    if variante.startswith("recorte:"):
        n = variante.split(":")[1]
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(reel), "-t", n, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-use_editlist", "0", str(out)]
    elif variante.startswith("desde:"):        # del segundo N al final (recodifica para empezar en fotograma clave)
        n = variante.split(":")[1]
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", n, "-i", str(reel), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-use_editlist", "0", str(out)]
    elif variante == "silencio":
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(reel), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v:0", "-map", "1:a:0", "-shortest",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-use_editlist", "0", str(out)]
    elif variante == "recodificar":      # 3-11: video completo recodificado (GOP cerrado de 2 s, sin B-frames): ¿límite de duración o de codificación?
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(reel), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-profile:v", "high", "-level", "4.0", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-bf", "0",
               "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", "-use_editlist", "0", str(out)]
    elif variante == "unaparte":         # 3-11: mismo archivo, carga reanudable en UN solo POST (¿falla la carga por partes?)
        import instagram
        instagram.PARTE = 1 << 30
        return reel, variante
    else:
        raise ValueError(f"variante desconocida: {variante}")
    subprocess.run(cmd, check=True, timeout=300)
    return out, variante


def probar(env, imagen, reel, texto_img, texto_reel, http=publicar.http_real, dormir=time.sleep, solo_reel_ig=False):
    """solo_reel_ig: carga únicamente el Reel aprobado a Instagram (sin publicar). Facebook e imagen de IG ya se
    comprobaron (28-10); tras el límite anti-spam de Meta (código 368) se minimizan las cargas de prueba."""
    R = {"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pasos": [], "publicado_algo": False}
    reel, R["variante"] = variante_ig(reel, env.get("VARIANTE_IG", ""))
    def paso(nombre, ok, detalle=""):
        R["pasos"].append({"paso": nombre, "resultado": "OK" if ok else "FALLA", "detalle": str(detalle)[:400]}); return ok
    page = env["META_PAGE_ID"]; g = Graph(publicar.token_pagina(env, http), http)
    try:
        yo = g.get("me", fields="id,name")
        paso("autenticación", str(yo.get("id")) == str(page), f'{yo.get("name")} ({yo.get("id")})')
    except (ErrorGraph, SinRed) as e:
        paso("autenticación", False, e); return R
    try:   # con un token de página, /me/permissions no aplica: se validan los permisos usándolos
        ig = instagram._ig_id(g, page); paso("Instagram vinculado", True, ig)
    except (ErrorGraph, SinRed) as e:
        ig = None; paso("Instagram vinculado", False, e)
    if not solo_reel_ig:
        # 2. Facebook · foto no publicada
        try:
            url = instagram.url_publica_imagen(g, page, imagen)
            paso("Facebook: imagen cargada como NO publicada", bool(url), "URL alojada por Meta (no visible en la página)")
        except (ErrorGraph, SinRed) as e:
            url = None; paso("Facebook: imagen cargada como NO publicada", False, e)
        # 3. Facebook · Reel: start + carga, sin finish
        try:
            r = g.post(f"{page}/video_reels", upload_phase="start")
            vid = r.get("video_id"); up = r.get("upload_url") or f"https://rupload.facebook.com/video-upload/{publicar.GRAPH_VERSION}/{vid}"
            s = g.subir(up, Path(reel).read_bytes())
            est, _ = publicar.estado_video(g, vid)
            paso("Facebook: Reel cargado completo SIN finalizar (no publicado)", s.get("success") and est in ("SUBIDO", "SUBIENDO"), f"video {vid}: {est}")
        except (ErrorGraph, SinRed) as e:
            paso("Facebook: Reel cargado completo SIN finalizar (no publicado)", False, e)
    # 4. Instagram · contenedores sin publicar
    if ig:
        for fmt, archivo, texto in ((("reel", reel, texto_reel),) if solo_reel_ig else (("imagen", imagen, texto_img), ("reel", reel, texto_reel))):
            libro = Path("/tmp") / f"ops_prueba_{fmt}.jsonl"; libro.unlink(missing_ok=True)
            try:
                cid = instagram.crear_contenedor(g, ig, fmt, archivo, texto, page, libro=libro, base={"pieza": "prueba", "red": "instagram"}, dormir=dormir)
                est = instagram.esperar_contenedor(g, cid, dormir=dormir)
                ruta = [json.loads(l).get("fase") + (f"({json.loads(l).get('error', '')[:120]})" if json.loads(l).get("error") else "") for l in libro.read_text().splitlines()] if libro.exists() else []
                paso(f"Instagram: contenedor de {fmt} procesado SIN publicar", est == "FINISHED", f"contenedor {cid}: {est}" + ("" if est == "FINISHED" else f" · {instagram.detalle_contenedor(g, cid)}") + f" · ruta: {' → '.join(ruta)}")
            except (ErrorGraph, SinRed) as e:
                paso(f"Instagram: contenedor de {fmt} procesado SIN publicar", False, e)
        try:
            paso("Instagram: búsqueda anti-duplicados", instagram.buscar_publicado(g, ig, texto_img) is None, "el texto aprobado no aparece publicado")
        except (ErrorGraph, SinRed) as e:
            paso("Instagram: búsqueda anti-duplicados", False, e)
    try:
        pid, est = publicar.buscar_publicacion(g, page, texto_img)
        paso("Facebook: búsqueda anti-duplicados", pid is None, "el texto aprobado no aparece publicado ni programado")
    except (ErrorGraph, SinRed) as e:
        paso("Facebook: búsqueda anti-duplicados", False, e)
    R["ok"] = all(p["resultado"] == "OK" for p in R["pasos"])
    return R


if __name__ == "__main__":
    env = os.environ
    if not (env.get("META_PAGE_TOKEN") or env.get("META_SYSTEM_TOKEN")) or not env.get("META_PAGE_ID"):
        print("Faltan META_PAGE_TOKEN o META_PAGE_ID; no se hizo ninguna llamada."); sys.exit(0)
    img, reel = sys.argv[1], sys.argv[2]
    g_img = json.loads((RAIZ / "piezas" / Path(img).stem / "guion.json").read_text())
    g_reel = json.loads((RAIZ / "piezas" / Path(reel).stem.replace("_final", "") / "guion.json").read_text())
    r = probar(env, img, reel, g_img.get("copy") or g_img["titulo"], g_reel.get("copy") or g_reel["titulo"], solo_reel_ig=env.get("SOLO_REEL_IG") == "1")
    out = RAIZ / "registro" / "meta_prueba_no_publica.json"; out.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    if r.get("variante") or env.get("SOLO_REEL_IG") == "1":
        with (RAIZ / "registro" / "diagnostico_ig.jsonl").open("a") as h:
            reel_paso = [p for p in r["pasos"] if "reel" in p["paso"]]
            h.write(json.dumps({"fecha": r["fecha"], "variante": r.get("variante") or "completo", "resultado": reel_paso[-1]["resultado"] if reel_paso else "SIN_PASO",
                                "detalle": reel_paso[-1]["detalle"] if reel_paso else ""}, ensure_ascii=False) + "\n")
    print(json.dumps(r, ensure_ascii=False, indent=1)); sys.exit(0)
