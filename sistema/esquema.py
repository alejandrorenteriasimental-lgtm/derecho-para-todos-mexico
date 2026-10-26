"""Validación estructural de guiones (Reel) y fichas (imagen fija) antes de cualquier verificación o producción.
Un guion incompleto nunca llega a producirse: queda RETENIDO con la lista exacta de lo que falta."""
TIPOS_ESCENA = {"gancho": ["titulo"], "titular": ["titulo"], "cita": ["cita", "etiqueta"], "lista": ["items"],
                "excepcion": ["numero", "encabezado", "detalle", "fuente_corta"], "cierre": ["aviso"]}
CAMPOS_FUENTE = ["url", "nivel", "documento", "articulo"]
PLANTILLAS = {"concepto", "tres_claves", "mito_realidad", "diferencia", "dato"}
LIMITES_IMAGEN = {"titular": 70, "bajada": 160, "punto": 70}


def _fuentes(g, err):
    fu = g.get("fuentes")
    if not fu:
        err.append("sin fuentes"); return {}
    if isinstance(fu, list):
        fu = {f.get("id"): f for f in fu}
    for k, f in fu.items():
        for c in CAMPOS_FUENTE:
            if not f.get(c): err.append(f"fuente {k}: falta «{c}»")
        if not (f.get("literal") or f.get("texto_literal")): err.append(f"fuente {k}: falta el texto literal a cotejar")
    return fu


def _afirmaciones(afs, fu, err, donde):
    for a in afs:
        if not a.get("id"): err.append(f"{donde}: afirmación sin id")
        refs = a.get("fuentes") or ([a["fuente"]] if a.get("fuente") else [])
        if not refs: err.append(f"{donde}: afirmación {a.get('id')} sin fuente")
        for r in refs:
            if r not in fu: err.append(f"{donde}: afirmación {a.get('id')} cita la fuente inexistente {r}")


def validar(g):
    err = []
    for c in ("id", "titulo", "riesgo"):
        if not g.get(c): err.append(f"falta «{c}»")
    if g.get("riesgo") and g["riesgo"] not in ("bajo", "medio", "alto"):
        err.append("riesgo debe ser bajo, medio o alto")
    fu = _fuentes(g, err)
    if g.get("formato", "reel") == "imagen":
        if g.get("plantilla") not in PLANTILLAS: err.append(f"plantilla desconocida: {g.get('plantilla')}")
        p = g.get("pieza") or {}
        if not p.get("titular"): err.append("imagen: falta el titular")
        if len(p.get("titular", "")) > LIMITES_IMAGEN["titular"]: err.append("imagen: titular demasiado largo para móvil")
        if len(p.get("bajada", "")) > LIMITES_IMAGEN["bajada"]: err.append("imagen: bajada demasiado larga")
        for x in p.get("puntos", []):
            if len(x) > LIMITES_IMAGEN["punto"]: err.append(f"imagen: punto demasiado largo («{x[:30]}…»)")
        if len(p.get("puntos", [])) > 3: err.append("imagen: más de tres puntos (una idea central por pieza)")
        if not g.get("copy"): err.append("imagen: falta el texto de acompañamiento")
        elif "no es asesoría legal" not in g["copy"].lower() and "no asesoría legal" not in g["copy"].lower():
            err.append("imagen: el texto de acompañamiento debe incluir el aviso de información general")
        _afirmaciones(g.get("afirmaciones", []), fu, err, "imagen")
        if not g.get("afirmaciones"): err.append("imagen: sin afirmaciones verificables")
        return err
    esc = g.get("escenas") or []
    if len(esc) < 4: err.append("menos de 4 escenas")
    if esc and esc[0].get("tipo") != "gancho": err.append("la primera escena debe ser el gancho")
    if esc and esc[-1].get("tipo") != "cierre": err.append("la última escena debe ser el cierre")
    total = 0
    for i, e in enumerate(esc):
        if e.get("tipo") not in TIPOS_ESCENA: err.append(f"escena {i}: tipo desconocido «{e.get('tipo')}»"); continue
        if not (e.get("texto") or "").strip(): err.append(f"escena {i}: sin texto de narración")
        total += len(e.get("texto", ""))
        for c in TIPOS_ESCENA[e["tipo"]]:
            if e.get(c) in (None, "", []): err.append(f"escena {i} ({e['tipo']}): falta «{c}»")
        _afirmaciones(e.get("afirmaciones", []), fu, err, f"escena {i}")
        for ln in e.get("titulo", []) if isinstance(e.get("titulo"), list) else []:
            if len(ln) > 20: err.append(f"escena {i}: línea de título demasiado larga para pantalla («{ln}»)")
        if isinstance(e.get("titulo"), list) and len(e["titulo"]) > 3: err.append(f"escena {i}: más de 3 líneas de título")
        for it in e.get("items", []) or []:
            if len(it) > 32: err.append(f"escena {i}: elemento de lista demasiado largo («{it[:30]}…»)")
        if len(e.get("items", []) or []) > 4: err.append(f"escena {i}: más de 4 elementos en la lista")
        if len(e.get("encabezado", "")) > 44: err.append(f"escena {i}: encabezado demasiado largo")
        if len(e.get("detalle", "")) > 38: err.append(f"escena {i}: detalle demasiado largo")
        if e.get("tipo") == "cita" and len(e.get("cita", "")) > 220: err.append(f"escena {i}: cita demasiado larga para pantalla")
    if esc and not (300 <= total <= 1600): err.append(f"narración de {total} caracteres (rango 300–1600, ≈20–90 s)")
    if esc and "no asesoría legal" not in esc[-1].get("texto", "").lower() and "no es asesoría legal" not in esc[-1].get("texto", "").lower():
        err.append("el cierre debe decir que es información general, no asesoría legal")
    if not any(e.get("afirmaciones") for e in esc): err.append("sin afirmaciones verificables")
    return err
