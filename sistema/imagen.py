"""Segunda línea de producción: publicación diaria de imagen fija (1080×1350, 4:5 para el feed de Facebook e Instagram).

Ficha (piezas/<id>/guion.json, formato «imagen») → verificación jurídica → render con plantilla programática →
auditoría (técnica, legibilidad, OCR y jurídica) → PNG + copy + metadatos. Costo variable: 0 (Pillow + tesseract).

PLANTILLA PROVISIONAL v0: deriva del estilo visual del Reel aprobado (paleta, Inter Display + Lora, firma).
El sistema de diseño definitivo para ambos formatos se desarrolla en la Fase 4 (identidad visual)."""
import hashlib, json, re, subprocess, sys
from datetime import datetime, timezone, date
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render, auditoria, verificador

W, H = 1080, 1350
M = 72                      # margen seguro
C = {**render.C, "papel": (246, 241, 230), "tinta": (14, 26, 44), "gris": (82, 94, 110), "linea": (214, 206, 190),
     "rojo_texto": (170, 44, 36), "verde_texto": (30, 110, 70)}
TAM_MIN = 32                # px: tamaño mínimo de texto a 1080 px de ancho (≈ 11 pt en un teléfono)
RAIZ = Path(__file__).resolve().parent.parent
OCR_DIR = RAIZ / "models" / "ocr"          # modelos: fijos al código, aunque RAIZ (datos) cambie
KICKER = {"concepto": "CONCEPTO JURÍDICO", "tres_claves": "TRES CLAVES", "mito_realidad": "MITO O REALIDAD",
          "diferencia": "¿CUÁL ES LA DIFERENCIA?", "dato": "DATO JURÍDICO"}


class Lienzo:
    def __init__(self):
        self.img = Image.new("RGBA", (W, H), C["papel"] + (255,)); self.d = ImageDraw.Draw(self.img)
        self.zona = "marco"
        self.textos = []    # registro de cada texto: contenido, tamaño, color de texto y de fondo, caja

    def texto(self, xy, t, f, color, fondo):
        self.d.text(xy, t, font=f, fill=color)
        bb = self.d.textbbox(xy, t, font=f)
        self.textos.append({"texto": t, "px": f.size, "color": color[:3], "fondo": fondo[:3], "caja": bb, "zona": self.zona})
        return bb

    def parrafo(self, x, y, t, k, tam, color, fondo, ancho, interl=1.22, max_lineas=None, tam_min=TAM_MIN):
        """Ajusta el tamaño hasta que el texto quepa en `max_lineas`; nunca baja de `tam_min`."""
        while True:
            f = render.font(k, tam); lineas = render.wrap(t, f, ancho - 8)  # holgura por sobresalientes de glifos
            if not max_lineas or len(lineas) <= max_lineas or tam <= tam_min: break
            tam -= 2
        for ln in lineas:
            self.texto((x, y), ln, f, color, fondo); y += int(tam * interl)
        return y, len(lineas), tam


def _sin_acentos(x):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", x.upper()) if unicodedata.category(c) != "Mn")


def _textura(img):
    """Grano de papel muy tenue para evitar el aspecto de plantilla plana."""
    rng = np.random.default_rng(7); r = rng.normal(0, 3.2, (H, W, 1)).astype(np.float32)
    a = np.asarray(img.convert("RGB")).astype(np.float32) + r
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def _cabecera(L, g):
    d = L.d
    d.rectangle([0, 0, W, 14], fill=C["tinta"])
    L.texto((M, 50), render.FIRMA, render.font("xbold", 32), C["tinta"], C["papel"])
    serie = f'N.º {g["numero"]}' if g.get("numero") else ""   # el identificador interno no se muestra al público
    f = render.font("semi", 26)
    if serie: L.texto((W - M - f.getlength(serie), 56), serie, f, C["gris"], C["papel"])
    d.line([(M, 108), (W - M, 108)], fill=C["linea"], width=2)
    k = KICKER.get(g["plantilla"], "DERECHO COTIDIANO"); fk = render.font("bold", 28)
    w = fk.getlength(k)
    d.rounded_rectangle([M, 140, M + w + 40, 140 + 52], 26, fill=C["acc"])
    L.texto((M + 20, 150), k, fk, C["tinta"], C["acc"])
    return 222


def _pie(L, g):
    d = L.d; y = H - 150
    d.line([(M, y), (W - M, y)], fill=C["linea"], width=2)
    fuente = g["pieza"].get("fuente_visible", "")
    t = "Fuente: " + fuente                         # una línea si cabe a ≥ 24 px (I20270115-T140: «art. 77» se partía junto al aviso)
    una = len(render.wrap(t, render.font("med", 24), W - 2 * M - 8)) == 1
    L.parrafo(M, y + 22, t, "med", 26, C["gris"], C["papel"], W - 2 * M, max_lineas=1 if una else 2, tam_min=24)
    L.texto((M, H - 62), "Información general, no asesoría legal.", render.font("semi", 26), C["tinta"], C["papel"])
    import marca                                   # símbolo oficial de la marca (marca/tokens.json)
    sim = marca.simbolo(72, "noche", "cempasuchil", cola=True)
    L.img.alpha_composite(sim, (W - M - 72, H - 96)); L.d = ImageDraw.Draw(L.img)


def _titular(L, y, t, max_lineas=3):
    y, n, tam = L.parrafo(M, y, t, "black", 88, C["tinta"], C["papel"], W - 2 * M, interl=1.06, max_lineas=max_lineas, tam_min=60)
    L.d.rectangle([M, y + 18, M + 120, y + 28], fill=C["acc"])
    return y + 60


def plantilla_concepto(L, g, y):
    p = g["pieza"]
    y = _titular(L, y, p["titular"])
    if p.get("bajada"):
        y, _, _ = L.parrafo(M, y, p["bajada"], "serif", 42, C["tinta"], C["papel"], W - 2 * M, interl=1.3, max_lineas=4, tam_min=34)
        y += 30
    if p.get("cita"):
        x0, x1 = M, W - M; alto_max = H - 190 - y
        caja = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(caja)
        f = render.font("serif_it", 36); lineas = render.wrap("«" + p["cita"] + "»", f, x1 - x0 - 100)
        # 12-11-2026 (I20270121-T146): una etiqueta larga («Ley General de Acceso de las Mujeres a una Vida Libre de
        # Violencia, artículo 6») salía del margen derecho. Si no cabe en una línea se parte; si cabe, nada cambia.
        fe = render.font("semi", 26); et = render.wrap(p.get("etiqueta_cita", ""), fe, x1 - x0 - 100) or [""]
        alto = 70 + len(lineas) * 50 + 60 + (len(et) - 1) * 34
        dc.rounded_rectangle([x0, y, x1, y + alto], 28, fill=C["tinta"] + (255,))
        L.img.alpha_composite(caja); L.d = ImageDraw.Draw(L.img)
        L.d.rectangle([x0 + 40, y + 40, x0 + 48, y + alto - 40], fill=C["acc"])
        yy = y + 40
        for ln in lineas:
            L.texto((x0 + 76, yy), ln, f, C["txt"], C["tinta"]); yy += 50
        for i, ln in enumerate(et):
            L.texto((x0 + 76, yy + 6 + i * 34), ln, fe, C["acc"], C["tinta"])
        y += alto + 34
    if p.get("ojo"):
        fo = render.font("black", 34); L.texto((M, y), "OJO:", fo, C["rojo_texto"], C["papel"])
        x_ojo = M + fo.getlength("OJO: ") + 6
        y, _, _ = L.parrafo(x_ojo, y, p["ojo"], "bold", 34, C["tinta"], C["papel"], W - M - x_ojo, max_lineas=3)
    return y


def plantilla_tres_claves(L, g, y):
    p = g["pieza"]; y = _titular(L, y, p["titular"], 2)
    if p.get("bajada"):
        y, _, _ = L.parrafo(M, y, p["bajada"], "serif", 38, C["tinta"], C["papel"], W - 2 * M, max_lineas=3); y += 30
    for i, pt in enumerate(p.get("puntos", [])[:3], 1):
        L.d.ellipse([M, y, M + 76, y + 76], fill=C["tinta"])
        fn = render.font("black", 44); L.texto((M + 38 - fn.getlength(str(i)) / 2, y + 10), str(i), fn, C["acc"], C["tinta"])
        y2, _, _ = L.parrafo(M + 106, y + 6, pt, "bold", 40, C["tinta"], C["papel"], W - 2 * M - 110, max_lineas=2)
        y = max(y + 96, y2 + 26)
    return y


def plantilla_mito_realidad(L, g, y):
    p = g["pieza"]; y = _titular(L, y, p["titular"], 2)
    for etiqueta, txt, col in (("MITO", p["mito"], C["red"]), ("REALIDAD", p["realidad"], C["green"])):
        fe = render.font("black", 32); L.d.rounded_rectangle([M, y, M + fe.getlength(etiqueta) + 36, y + 50], 12, fill=col)
        L.texto((M + 18, y + 8), etiqueta, fe, C["tinta"], col)
        y, _, _ = L.parrafo(M, y + 70, txt, "serif", 40, C["tinta"], C["papel"], W - 2 * M, max_lineas=3); y += 34
    return y


def plantilla_diferencia(L, g, y):
    p = g["pieza"]; y = _titular(L, y, p["titular"], 2)
    if p.get("bajada"):                                   # la respuesta corta debe verse, no solo estar en el guion
        y, _, _ = L.parrafo(M, y + 4, p["bajada"], "serif", 38, C["tinta"], C["papel"], W - 2 * M, max_lineas=3); y += 26
    col_w = (W - 2 * M - 30) // 2; y0 = y
    for j, (nombre, desc) in enumerate(p["columnas"][:2]):
        x = M + j * (col_w + 30)
        L.d.rounded_rectangle([x, y0, x + col_w, y0 + 470], 24, fill=(C["tinta"] if j == 0 else (232, 224, 208)))
        fg = C["txt"] if j == 0 else C["tinta"]; bg = C["tinta"] if j == 0 else (232, 224, 208)
        L.texto((x + 30, y0 + 30), nombre.upper(), render.font("black", 40), C["acc"] if j == 0 else C["tinta"], bg)
        L.parrafo(x + 30, y0 + 100, desc, "med", 34, fg, bg, col_w - 60, max_lineas=8)
    return y0 + 500


PLANTILLAS = {"concepto": plantilla_concepto, "dato": plantilla_concepto, "tres_claves": plantilla_tres_claves,
              "mito_realidad": plantilla_mito_realidad, "diferencia": plantilla_diferencia}


def _componer(g, desplazamiento=0):
    L = Lienzo(); y = _cabecera(L, g)
    L.zona = "contenido"; y_fin = PLANTILLAS[g["plantilla"]](L, g, y + 10 + desplazamiento)
    L.zona = "marco"; _pie(L, g)
    return L, y_fin


def dibujar(g, salida_png):
    L, y_fin = _componer(g)
    hueco = (H - 190) - y_fin                    # espacio libre sobre el pie
    if hueco > 60:                               # segunda pasada: reparte el aire (composición equilibrada)
        L, y_fin = _componer(g, min(int(hueco * 0.45), 90))
    img = _textura(L.img).convert("RGB")
    img.save(salida_png, "PNG", optimize=True)
    return L.textos, y_fin


# ---------------- auditoría ----------------
def _lum(c):
    def ch(v):
        v = v / 255; return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c); return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)


def ocr_disponible():
    if (OCR_DIR / "spa.traineddata").exists(): return True
    r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return "spa" in r.stdout.split()


def ocr(png):
    """OCR en tres vistas (original, binarizada por luminancia local e invertida) para leer también etiquetas sobre color
    y texto claro sobre fondo oscuro. La vista invertida se agregó el 14-11-2026: la etiqueta amarilla de la cita sobre
    el recuadro azul marino no la leía ninguna de las otras dos (I20270128-T153 retenida con 86 % aunque la imagen es
    legible). El umbral del 90 % no cambia: cada palabra esperada tiene que leerse en alguna vista."""
    import tempfile
    from PIL import ImageOps
    td = OCR_DIR; textos = []
    g = Image.open(png).convert("L"); a = np.asarray(g).astype(np.float32)
    from PIL import ImageFilter as IF
    loc = np.asarray(g.filter(IF.BoxBlur(25))).astype(np.float32)
    bin_ = Image.fromarray(np.where(np.abs(a - loc) > 18, 0, 255).astype(np.uint8))
    with tempfile.TemporaryDirectory() as d:
        bp = Path(d) / "b.png"; bin_.save(bp)
        ip = Path(d) / "i.png"; ImageOps.invert(g).save(ip)
        for src in (png, bp, ip):
            cmd = ["tesseract", str(src), "-", "-l", "spa", "--psm", "3"]
            if (td / "spa.traineddata").exists(): cmd[1:1] = ["--tessdata-dir", str(td)]
            textos.append(subprocess.run(cmd, capture_output=True, text=True).stdout)
    return "\n".join(textos)


def _palabras(t):
    import unicodedata
    t = unicodedata.normalize("NFD", t.lower()); t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ]{3,}", t)


def ahash(png):
    a = np.asarray(Image.open(png).convert("L").resize((16, 16))); return "".join("1" if v else "0" for v in (a > a.mean()).flatten())


def _mismo_tema(g, otro_id):
    """La comparación de «casi idéntica» solo tiene sentido entre piezas del mismo tema o con titulares parecidos: con la
    misma plantilla, dos piezas distintas dan huellas visuales cercanas (I20261204-T031 vs. I20261126-T025, 29-10:
    distancia 11/256 con contenido totalmente distinto)."""
    if g.get("tema_id") and otro_id.endswith("-" + g["tema_id"]): return True
    try: g2 = json.loads((RAIZ / "piezas" / otro_id / "guion.json").read_text())
    except (OSError, ValueError): return True          # sin datos: se compara (criterio conservador)
    t2 = g2.get("titulo", "")
    a = {w for w in _palabras(g.get("titulo", "")) if len(w) > 3}; b = {w for w in _palabras(t2) if len(w) > 3}
    if not (bool(a and b) and len(a & b) / len(a | b) >= 0.5): return False
    # Titulares parecidos con fundamentos distintos no son el mismo tema: «¿Le pueden pagar tu sueldo a otra persona?»
    # (LFT 100) y «¿Te pueden pagar el sueldo con vales?» (LFT 101) comparten «pueden pagar sueldo» (I20270119-T144,
    # 10-11: retenida a distancia 12/256 de I20261214-T108). Si ambos guiones citan artículos y no comparten ninguno,
    # no se comparan; sin fuentes en alguno de los dos, se compara (criterio conservador).
    def arts(x): return {(f.get("documento"), str(f.get("articulo"))) for f in (x.get("fuentes") or {}).values() if f.get("articulo")}
    fa, fb = arts(g), arts(g2)
    return not (fa and fb) or bool(fa & fb)


def auditar(png, textos, y_fin, previos_hash=()):
    R = []
    def ok(n, c, det=""): R.append({"control": n, "resultado": "APROBADO" if c else "FALLA", "detalle": det})
    im = Image.open(png)
    ok("Formato 1080×1350 PNG (4:5)", im.size == (W, H) and im.format == "PNG", f"{im.size} {im.format}")
    peso = Path(png).stat().st_size; ok("Peso menor a 8 MB", peso < 8 * 1024 * 1024, f"{peso/1024:.0f} KB")
    tmin = min(t["px"] for t in textos); ok(f"Tamaño mínimo de texto ≥ 24 px (cuerpo ≥ {TAM_MIN})", tmin >= 24, f"mínimo {tmin} px")
    crs = [(round(contraste(t["color"], t["fondo"]), 2), t["texto"][:24]) for t in textos]
    peor = min(crs); ok("Contraste WCAG AA ≥ 4.5:1 en todos los textos", peor[0] >= 4.5, f"peor {peor[0]}:1 («{peor[1]}»)")
    fuera = [t["texto"][:20] for t in textos if t["caja"][0] < M - 8 or t["caja"][2] > W - M + 8 or t["caja"][3] > H - 10]
    ok("Todo el texto dentro de márgenes seguros", not fuera, ", ".join(fuera) or f"margen {M} px")
    ok("Contenido sin invadir el pie", y_fin <= H - 160, f"fin del contenido en y={y_fin}")
    n_pal = sum(len(t["texto"].split()) for t in textos if t.get("zona") == "contenido")
    ok("Contenido ≤ 60 palabras (una idea central; el resto va en el copy)", n_pal <= 60, f"{n_pal} palabras sin cabecera ni pie")
    esperado = set(_palabras(" ".join(t["texto"] for t in textos if t["texto"] != "dpt"))); leido = set(_palabras(ocr(png)))
    cobertura = len(esperado & leido) / max(1, len(esperado))
    if not ocr_disponible():
        raise RuntimeError("OCR no disponible (falta tesseract con idioma «spa»): la auditoría de imagen no puede aprobar sin él")
    ok("OCR: el texto renderizado es legible y completo (≥ 90 %)", cobertura >= 0.9, f"{cobertura:.0%} de {len(esperado)} palabras reconocidas")
    ok("Firma de marca y aviso presentes", any(_sin_acentos(render.FIRMA) in _sin_acentos(t["texto"]) for t in textos) and any("no asesoría legal" in t["texto"] for t in textos))
    ok("Fuente visible en la pieza", any(t["texto"].startswith("Fuente:") for t in textos))
    h = ahash(png); dist = min((sum(a != b for a, b in zip(h, p)) for p in previos_hash), default=256)
    ok("No es casi idéntica a una imagen anterior", dist > 12, f"distancia mínima {dist}/256")
    return R, h, cobertura


def revision_previa(g):
    """Dibuja la ficha en un archivo temporal ANTES de aceptar el guion y aplica los mismos límites de la auditoría técnica
    que dependen del texto (≤ 60 palabras de contenido; sin invadir el pie). Así el redactor corrige la longitud en la
    redacción y no se pierde el ciclo produciendo una imagen que la auditoría retendrá (I20261125-T028, 28-10: 64 palabras)."""
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as d:
            textos, y_fin = dibujar(g, Path(d) / "previa.png")
    except Exception as e:
        return [f"imagen: no se pudo dibujar la ficha ({type(e).__name__})"]
    err = []
    import razonamiento as _rz
    pz = g.get("pieza") or {}
    ojo = [w[:6] for w in _rz.plano(pz.get("ojo", "")).split() if len(w) > 4]
    base = {w[:6] for w in _rz.plano(" ".join([pz.get("titular", ""), pz.get("bajada", ""), g.get("titulo", "")])).split() if len(w) > 4}
    if ojo and sum(1 for w in ojo if w in base) >= max(1, round(len(ojo) * 0.7)):
        err.append("[ojo] El «OJO» repite la respuesta: debe agregar una precisión distinta tomada del análisis (condición, excepción u otro dato de la cita), o quitarse")
    ojo_txt = (pz.get("ojo") or "").strip()
    if ojo_txt and len(ojo_txt) > 110:
        err.append(f"[ojo] El «OJO» es demasiado largo ({len(ojo_txt)} caracteres; máximo 110): redáctalo completo y más corto, o quítalo")
    elif ojo_txt and not ojo_txt.endswith((".", ")", "»", "!", "?")):
        err.append("[ojo] El «OJO» parece cortado (no termina en punto): redáctalo como frase completa y breve, o quítalo")
    n = sum(len(t["texto"].split()) for t in textos if t.get("zona") == "contenido")
    if n > 60: err.append(f"imagen: contenido demasiado largo ({n} palabras visibles; máximo 60; sobran {n - 60}, quita al menos {n - 55}): acorta la bajada, la cita destacada o el «ojo» sin quitar la respuesta")
    if y_fin > H - 160: err.append("imagen: contenido demasiado largo: invade el pie de la ficha")
    return err


def producir(carpeta: Path, verificacion=None):
    g = json.loads((carpeta / "guion.json").read_text())
    out = carpeta / "salida"; out.mkdir(exist_ok=True)
    if verificacion is None:
        verificacion = verificador.verificar_guion(g)
    (out / "verificacion.json").write_text(json.dumps(verificacion, ensure_ascii=False, indent=2))
    jur = auditoria.dictamen(g, verificacion, date.today())
    png = out / f'{g["id"]}.png'
    textos, y_fin = dibujar(g, png)
    reg_f = RAIZ / "registro" / "imagenes.jsonl"
    previos = [x["ahash"] for x in (json.loads(l) for l in reg_f.read_text().splitlines() if l.strip()) if x["id"] != g["id"] and _mismo_tema(g, x["id"])] if reg_f.exists() else []
    tec, h, cob = auditar(png, textos, y_fin, previos)
    tec_ok = all(r["resultado"] == "APROBADO" for r in tec)
    if not tec_ok:
        jur = {**jur, "decision": "RETENIDO", "tipo_retencion": "sustantivo", "motivos": jur["motivos"] + ["falla técnica de la imagen"]}
    from producir import huella_guion
    meta = {"id": g["id"], "formato": "imagen", "titulo": g["titulo"], "plantilla": g["plantilla"], "archivo": png.name,
            "sha256": hashlib.sha256(png.read_bytes()).hexdigest(), "ahash": h, "huella_guion": huella_guion(g),
            "texto_alternativo": g.get("alt") or g["pieza"]["titular"], "copy": g["copy"],
            "fuentes": [{"id": f.get("id", k), "documento": f.get("documento"), "articulo": f.get("articulo"), "url": f.get("url")}
                        for k, f in (g["fuentes"].items() if isinstance(g["fuentes"], dict) else enumerate(g["fuentes"]))],
            "relacion_reel": g.get("relacion_reel"), "estado": jur["decision"], "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "costo": {"apis_de_pago_usd": 0.0, "nota": "Pillow + tesseract, locales y gratuitos"}}
    (out / f'{g["id"]}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    (out / f'{g["id"]}_copy.txt').write_text(g["copy"])
    (out / "auditoria.json").write_text(json.dumps({"tecnica": tec, "juridica": jur, "metadatos": meta}, ensure_ascii=False, indent=2))
    reg_f.parent.mkdir(exist_ok=True)
    lineas = [l for l in (reg_f.read_text().splitlines() if reg_f.exists() else []) if l.strip() and json.loads(l)["id"] != g["id"]]
    reg_f.write_text("\n".join(lineas + [json.dumps({k: meta[k] for k in ("id", "fecha", "sha256", "ahash", "estado", "plantilla")}, ensure_ascii=False)]) + "\n")
    return {"id": g["id"], "estado": jur["decision"], "sha256": meta["sha256"]}, tec, jur


if __name__ == "__main__":
    reg, tec, jur = producir(Path(sys.argv[1]))
    for r in tec: print(r["resultado"], "|", r["control"], "|", r["detalle"])
    print("JURÍDICA:", jur["decision"], jur.get("tipo_retencion") or "")
    for m in jur["motivos"]: print("  ·", m)
