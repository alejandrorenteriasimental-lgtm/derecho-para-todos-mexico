"""Auditorías deterministas y gratuitas: técnica (ffprobe/ffmpeg) y jurídica (reglas sobre el guion estructurado)."""
import hashlib, json, re, subprocess, unicodedata
from datetime import date
from pathlib import Path


# Primera palabra de una institución o autoridad (no de una persona): «Autoridad Conciliadora», «Tribunal Colegiado»…
# R20261130-T014, 29-10: «Autoridad Conciliadora» (LFT 48) se marcó como persona real.
INICIO_INSTITUCION = {"Autoridad", "Autoridades", "Tribunal", "Tribunales", "Centro", "Centros", "Procuraduría", "Secretaría", "Instituto",
                      "Comisión", "Junta", "Juzgado", "Fiscalía", "Congreso", "Cámara", "Poder", "Consejo", "Defensoría", "Registro"}


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


# ---------------- TÉCNICA ----------------
def tecnica(mp4: Path, srt: Path, registro_hashes: set):
    res = []
    def ok(nombre, cond, detalle=""):
        res.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    _, out, _ = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)])
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    au = [s for s in info["streams"] if s["codec_type"] == "audio"]
    dur = float(info["format"]["duration"])
    ok("Resolución 1080x1920 (9:16)", v["width"] == 1080 and v["height"] == 1920, f'{v["width"]}x{v["height"]}')
    ok("Códec H.264, yuv420p", v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f'{v["codec_name"]}, {v["pix_fmt"]}')
    fr = eval(v["r_frame_rate"])
    ok("30 cuadros por segundo", abs(fr - 30) < 0.01, f"{fr:.2f} fps")
    ok("Duración entre 30 y 90 s (límite de Reels por API)", 30 <= dur <= 90, f"{dur:.1f} s")
    ok("Duración mayor a 60 s (requisito de TikTok Recompensas)", dur > 60, f"{dur:.1f} s")
    ok("Pista de audio AAC 48 kHz estéreo", bool(au) and au[0]["codec_name"] == "aac" and au[0]["sample_rate"] == "48000" and au[0]["channels"] == 2,
       f'{au[0]["codec_name"]}, {au[0]["sample_rate"]} Hz, {au[0]["channels"]} canales' if au else "sin audio")
    # integridad: decodificar todo
    code, _, err = _run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "null", "-"])
    ok("Archivo íntegro (decodificación completa sin errores)", code == 0 and not err.strip(), err.strip()[:200])
    # sonoridad
    _, _, err = _run(["ffmpeg", "-nostats", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err); tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    lufs = float(m[-1]) if m else None; pico = float(tp[-1]) if tp else None
    ok("Sonoridad -14 LUFS ±1.5", lufs is not None and abs(lufs + 14) <= 1.5, f"{lufs} LUFS")
    ok("Pico verdadero ≤ -1 dBTP", pico is not None and pico <= -1.0, f"{pico} dBTP")
    # silencios largos y negro
    _, _, err = _run(["ffmpeg", "-nostats", "-i", str(mp4), "-af", "silencedetect=n=-45dB:d=1.5", "-f", "null", "-"])
    sil = re.findall(r"silence_duration: ([\d.]+)", err)
    ok("Sin silencios mayores a 1.5 s", not sil, f"{len(sil)} silencios")
    _, _, err = _run(["ffmpeg", "-nostats", "-i", str(mp4), "-vf", "blackdetect=d=0.5:pix_th=0.05", "-an", "-f", "null", "-"])
    neg = re.findall(r"black_duration:([\d.]+)", err)
    ok("Sin pantallas negras mayores a 0.5 s", not neg, f"{len(neg)} tramos")
    # subtítulos
    cues = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})\n(.+)", srt.read_text()) if srt.exists() else []
    def s(h, m_, s_, ms): return int(h) * 3600 + int(m_) * 60 + int(s_) + int(ms) / 1000
    dentro = all(s(*c[4:8]) <= dur + 0.2 for c in cues)
    largos = [c[8] for c in cues if len(c[8]) > 30]
    ok("Subtítulos presentes y dentro de la duración", bool(cues) and dentro, f"{len(cues)} bloques")
    ok("Bloques de subtítulo de 30 caracteres o menos", not largos, f"{len(largos)} excedidos")
    # duplicados
    h = hashlib.sha256(mp4.read_bytes()).hexdigest()
    ok("No duplica un video ya registrado (SHA-256)", h not in registro_hashes, h[:16])
    return res, h, dur


# ---------------- JURÍDICA ----------------
def _norm(t):
    t = unicodedata.normalize("NFD", t.lower()); t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", t)).strip()

PROHIBIDAS = ["en tu caso", "te garantizo", "contactanos", "somos abogados", "asesoria gratuita"]
JURIDICAS = {"Código", "Ley", "Constitución", "Corte", "Suprema", "Justicia", "Tribunal", "Federal", "Nacional", "Penal", "Penales",
             "Civil", "Procedimientos", "Trabajo", "Diario", "Oficial", "Federación", "Ciudad", "México", "Estado", "Estados",
             "Unidos", "Mexicanos", "Congreso", "Cámara", "Diputados", "Senado", "Fiscalía", "General", "República", "Información"}


def juridica(guion: dict, hoy: date):
    hallazgos, estados = [], []
    narr = " ".join(e["texto"] for e in guion["escenas"]); nn = _norm(narr)
    fuentes = guion["fuentes"]; dudas_materiales = 0; carril = guion.get("carril_inicial", "A")
    for esc in guion["escenas"]:
        for af in esc.get("afirmaciones", []):
            fu = fuentes.get(af["fuente"])
            est = {"id": af["id"], "afirmacion": af["texto"], "fuente": fu["cita"] if fu else "SIN FUENTE"}
            if not fu:
                est["estado"] = "NO VERIFICADA"; est["motivo"] = "Sin fuente"; dudas_materiales += 1
            else:
                dias = (hoy - date.fromisoformat(fu["consultado"])).days
                if fu["nivel"] != "oficial":
                    est["estado"] = "VERIFICACIÓN SECUNDARIA"; est["motivo"] = fu.get("nota_nivel", "Fuente no oficial"); dudas_materiales += 1
                elif dias > 30:
                    est["estado"] = "VIGENCIA VENCIDA"; est["motivo"] = f"Consulta de hace {dias} días"; dudas_materiales += 1
                else:
                    est["estado"] = "VERIFICADA (fuente oficial)"; est["motivo"] = f'{fu.get("ultima_reforma_articulo", fu.get("ultima_reforma_ley", ""))}; consulta {fu["consultado"]}'
                if af.get("comparar_literal") and _norm(fu["texto_literal"]) not in nn:
                    est["estado"] = "CITA NO LITERAL"; est["motivo"] = "La narración no reproduce el texto oficial"; dudas_materiales += 1
                if af["tipo"] == "interpretacion":
                    carril = max(carril, "B")
                    if af.get("nota"):
                        est["estado"] += " · INTERPRETACIÓN CON DUDA"; est["motivo"] += f' · {af["nota"]}'; dudas_materiales += 1
                    else:
                        est["estado"] += " · INTERPRETACIÓN"
            estados.append(est)
    # reglas de pieza
    def regla(nombre, cond, detalle):
        hallazgos.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    regla("Aviso de información general", "no asesoria legal" in nn, "Debe decir que no es asesoría legal")
    penal = any("penal" in _norm(f["cita"]) for f in fuentes.values())
    regla("Leyenda de jurisdicción en temas penales o locales", (not penal) or ("segun tu estado" in nn), "Requerida si se cita derecho penal")
    pro = [p for p in PROHIBIDAS if p in nn]
    regla("Sin frases de asesoría o adjetivos de culpabilidad", not pro, ", ".join(pro) or "ninguna")
    nombres = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", narr)
    INICIO = {"En", "El", "La", "Los", "Las", "Pero", "Si", "Y", "Así", "Esto", "Eso", "Esta", "Este", "Un", "Una", "Nadie", "Síguenos"}
    INSTITUCIONES = {"Código Penal", "Penal Federal", "Suprema Corte", "Corte Interamericana", "Diario Oficial", "Ciudad México", "Aquí Dice", "Dice La", "Ministerio Público", "Estados Unidos", "Unidos Mexicanos"}
    oficiales = " ".join(str(f.get(k, "")) for f in fuentes.values() for k in ("documento", "cita", "texto_literal", "literal"))
    personas = [x for x in nombres if x.split()[0] not in INICIO and x.split()[0] not in INICIO_INSTITUCION and x not in INSTITUCIONES and x not in oficiales]   # cargos e instituciones citados en la ley no son personas
    regla("Sin personas reales identificables", not personas, ", ".join(personas) or "ninguna")
    if personas: carril = "C"
    regla("Toda afirmación jurídica tiene fuente", all(e["fuente"] != "SIN FUENTE" for e in estados), f"{len(estados)} afirmaciones")
    fallas = [h for h in hallazgos if h["resultado"] == "FALLA"]
    if carril == "C":
        decision = "RETENIDO: riesgo alto, requiere revisión humana especializada"
    elif fallas or dudas_materiales:
        decision = f"RETENIDO: {dudas_materiales} afirmación(es) con duda material y {len(fallas)} regla(s) fallida(s)"
    else:
        decision = "APTO PARA PUBLICACIÓN AUTOMÁTICA"
    return {"carril": carril, "decision": decision, "afirmaciones": estados, "reglas": hallazgos, "dudas_materiales": dudas_materiales}


def editorial(guion: dict):
    """Reglas editoriales deterministas, independientes de la verificación documental."""
    hallazgos = []
    if guion.get("formato") == "imagen":
        p = guion.get("pieza", {})
        narr = " ".join([p.get("titular", ""), p.get("bajada", ""), " ".join(p.get("puntos", [])), guion.get("copy", "")])
    else:
        narr = " ".join(e.get("texto", "") for e in guion.get("escenas", []))
    nn = _norm(narr); carril = guion.get("carril_inicial", "A")
    fuentes = guion.get("fuentes", {}); fuentes = fuentes.values() if isinstance(fuentes, dict) else fuentes
    def regla(nombre, cond, detalle):
        hallazgos.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    regla("Aviso de información general", "no asesoria legal" in nn or "no es asesoria legal" in nn, "Debe decir que no es asesoría legal")
    # la leyenda es obligatoria cuando la norma citada tiene equivalentes estatales distintos (códigos penales y civiles
    # sustantivos, leyes locales); no aplica a la Constitución ni a códigos nacionales de aplicación en todo el país
    penal = any(re.search(r"codigo (penal|civil)(?! nacional)", _norm(f.get("documento", "") + " " + f.get("cita", "")))
                and "nacional" not in _norm(f.get("documento", "")) or "local" in _norm(f.get("jurisdiccion", "")) for f in fuentes)
    regla("Leyenda de jurisdicción en temas penales o locales", (not penal) or ("segun tu estado" in nn) or ("varian por estado" in nn) or ("pueden variar" in nn),
          "Requerida si se cita derecho penal")
    pro = [x for x in PROHIBIDAS if x in nn]
    pro += re.findall(r"\b(?:es|era|fue|son|eran|fueron) (?:un |una |el |la )?(?:culpable|asesin[oa]|criminal|delincuente)s?\b", nn)
    regla("Sin frases de asesoría o adjetivos de culpabilidad", not pro, ", ".join(pro) or "ninguna")
    nombres = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", narr)
    INICIO = {"En", "El", "La", "Los", "Las", "Pero", "Si", "Y", "Así", "Esto", "Eso", "Esta", "Este", "Un", "Una", "Nadie", "Síguenos", "Guárdalo", "Comparte", "Qué", "Cuál"}
    INSTITUCIONES = {"Código Penal", "Penal Federal", "Suprema Corte", "Corte Interamericana", "Diario Oficial", "Ciudad México", "Ley Federal", "Federal Trabajo", "Código Civil", "Código Nacional", "Aquí Dice", "Dice La", "Ministerio Público", "Estados Unidos", "Unidos Mexicanos"}
    oficiales = " ".join(str(f.get(k, "")) for f in fuentes for k in ("documento", "cita", "texto_literal", "literal"))
    personas = [x for x in nombres if x.split()[0] not in INICIO and x.split()[0] not in INICIO_INSTITUCION and x not in INSTITUCIONES and not (set(x.split()) & JURIDICAS)
                and x not in oficiales]   # cargos e instituciones que aparecen en el texto legal citado no son personas
    regla("Sin personas reales identificables", not personas, ", ".join(personas) or "ninguna")
    if personas: carril = "C"
    if guion.get("riesgo") == "alto": carril = "C"
    return {"reglas": hallazgos, "carril": carril}


def dictamen(guion: dict, verificacion: dict, hoy: date):
    """Dictamen jurídico v0.2 = verificación documental contra la fuente oficial (verificador.py)
    + reglas editoriales deterministas (aviso, jurisdicción, frases prohibidas, personas reales)."""
    ed = editorial(guion)
    reglas = ed["reglas"]
    fallas = [r for r in reglas if r["resultado"] == "FALLA"]
    d = verificacion["decision"]
    motivos = [f'{k}: {x["motivo"]}' for k, x in verificacion["fuentes"].items() if x["estado"] != "VERIFICADA"]
    motivos += [f'{a["id"]}: {a["dictamen"]}' + (f' ({a["duda"]})' if a.get("duda") else "") for a in verificacion["afirmaciones"] if a["dictamen"] != "VERIFICADA"]
    import verificador
    transitorio = verificador.es_transitoria(verificacion)
    if fallas:
        decision, tipo = "RETENIDO", "sustantivo"; motivos += [f'Regla: {r["control"]}' for r in fallas]
    elif ed["carril"] == "C" or d == "REVISION_HUMANA":
        decision, tipo = "REVISION_HUMANA", "sustantivo"
    elif d in ("APTA", "APTA_CON_CRITERIO"):
        decision, tipo = ("APTO" if d == "APTA" else "APTO_CON_CRITERIO"), None
    else:
        decision, tipo = "RETENIDO", ("transitorio" if transitorio else "sustantivo")
    return {"decision": decision, "tipo_retencion": tipo, "motivos": motivos, "verificacion": verificacion["decision"],
            "carril": ed["carril"], "reglas": reglas}


def sincronia(salida: Path, tolerancia=0.15):
    """Compara el inicio de cada oración del subtítulo con el fin del silencio previo detectado en la voz."""
    lt = json.loads((salida / "linea_tiempo.json").read_text())
    ors = [o for sg in lt["segmentos"] for o in sg.get("oraciones", [])]
    if not ors:
        return {"control": "Sincronía voz-subtítulos por oración", "resultado": "FALLA", "detalle": "sin tiempos por oración"}
    err = subprocess.run(["ffmpeg", "-i", str(salida / "voz.wav"), "-af", "silencedetect=n=-40dB:d=0.25", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    fines = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    desf = [min((abs(f - o["inicio"]) for f in fines), default=9) for o in ors[1:]]   # la primera inicia tras el silencio inicial
    peor = max(desf, default=0)
    return {"control": f"Sincronía voz-subtítulos ≤ {int(tolerancia*1000)} ms por oración", "resultado": "APROBADO" if peor <= tolerancia else "FALLA",
            "detalle": f"desfase máximo {peor*1000:.0f} ms en {len(ors)} oraciones"}


def subtitulos_sin_solape(solapes):
    """Los subtítulos no deben tapar citas, fuentes ni información esencial (rechazo humano de R20261028-T068, 26-10-2026).
    El render mide el borde inferior del contenido de cada cuadro y coloca el subtítulo debajo; si no cabe, lo reporta."""
    if solapes is None:
        return {"control": "Subtítulos sin tapar citas ni contenido", "resultado": "FALLA", "detalle": "el render no midió el contenido"}
    escenas = sorted({(s["escena"], s["tipo"]) for s in solapes})
    return {"control": "Subtítulos sin tapar citas ni contenido", "resultado": "APROBADO" if not solapes else "FALLA",
            "detalle": "0 cuadros con solape" if not solapes else f"{len(solapes)} cuadros; escenas {escenas[:5]}"}
