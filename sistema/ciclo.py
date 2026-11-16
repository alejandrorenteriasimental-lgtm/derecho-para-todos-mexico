"""Un ciclo de operación autónoma (lo ejecuta GitHub Actions en horario fijo; no depende de una conversación abierta).

 1. Toma el bloqueo. Planifica 7 días y, si no hay una pieza activa de cada formato, REDACTA la siguiente solicitud
    (redactor.py: fuentes oficiales → borrador anclado → auditoría de otro modelo). Si un tema no supera los
    controles se descarta y se intenta el siguiente, hasta 3 por formato y ciclo.
 2. Encola cada piezas/<id>/guion.json válido; si el guion de una pieza RETENIDA cambió, la devuelve a PENDIENTE.
 3. Verificación jurídica ANTES de producir (descarga y coteja la fuente oficial). Sin conexión → RETENIDO transitorio.
 4. Produce y audita (técnica + dictamen jurídico). Solo APTO / APTO_CON_CRITERIO pasa a APROBADO.
 5. Publica en la MISMA ejecución (el MP4 existe en este runner): en simulación → SIMULADO; en modo real →
    PUBLICANDO y, tras confirmar el estado remoto, PROGRAMADO o PUBLICADO.
 6. Retoma operaciones PUBLICANDO de ciclos anteriores consultando su estado en Meta (nunca re-sube a ciegas).
 7. Re-verifica las retenciones transitorias después de 6 horas.
 8. Registra todo y alerta. Libera el bloqueo.
"""
import json, os, sys, traceback, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola, producir, publicar, verificador, esquema, presupuesto, planificador, redactor, respaldo, revision

RAIZ = Path(__file__).resolve().parent.parent
REVERIFICAR_H = 6


def alerta(msg):
    tok = os.environ.get("TELEGRAM_TOKEN")
    try: chat = revision.estado_tg().get("chat_id")       # chat vinculado con código (sistema/revision.py)
    except Exception: chat = None
    cola.log({"evento": "alerta", "mensaje": msg})
    if tok and chat:
        data = urllib.parse.urlencode({"chat_id": chat, "text": f"[DPT] {msg}"}).encode()
        try: urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
        except Exception as e: cola.log({"evento": "alerta_no_enviada", "error": str(e)})


def _guion(pid):
    return json.loads((RAIZ / "piezas" / pid / "guion.json").read_text())


def programar_para(formato, ahora=None):
    """Horario experimental (se ajusta con datos propios; ver docs/estrategia_dos_formatos.md)."""
    ahora = ahora or datetime.now(timezone.utc)
    hora_mx = {"reel": 19, "imagen": 9}[formato]          # 19:00 y 09:00 hora de Ciudad de México
    obj = ahora.replace(hour=(hora_mx + 6) % 24, minute=0, second=0, microsecond=0)
    if obj < ahora + timedelta(minutes=20): obj += timedelta(days=1)   # Meta exige ≥10 min a futuro
    return int(obj.timestamp())


ACTIVOS = {"PENDIENTE", "PRODUCIDO", "APROBADO", "PUBLICANDO"}


def es_version_ig(pid): return str(pid).endswith("-IG")


def es_derivada(pid):
    """Piezas derivadas de un Reel aprobado que el ciclo no encola ni publica: versión corta de Instagram (-IG, version_ig.py)
    y versión larga solo para TikTok (-TT, tiktok_largo.py). Cada una tiene su propio registro y su propia aprobación."""
    return es_version_ig(pid) or redactor.es_variante_tiktok(pid)


def _requiere_revision(pid, env):
    """Toda pieza redactada por IA pasa por aprobación humana (REVISION_HUMANA_OBLIGATORIA=0 la desactiva, solo por
    decisión del responsable tras validar la calidad). Las decisiones llegan por revision.py (Telegram) y quedan en
    estado/aprobaciones.jsonl con la versión exacta revisada."""
    g = _guion(pid)
    return bool((g.get("generacion") or {}).get("modelos")) and env.get("REVISION_HUMANA_OBLIGATORIA", "1") != "0"


def _rutas():
    """Las rutas de estado de los módulos auxiliares siguen a RAIZ (las pruebas la sustituyen por una carpeta temporal)."""
    respaldo.MANIFIESTO = RAIZ / "estado" / "respaldo.json"
    revision.RAIZ = RAIZ; revision.ESTADO_TG = RAIZ / "estado" / "telegram.json"; revision.REGISTRO = RAIZ / "estado" / "aprobaciones.jsonl"


def _respaldar(pid, resumen, env):
    try:
        respaldo.respaldar(pid, RAIZ / "piezas" / pid / "salida", env)
    except Exception as e:
        resumen["errores"].append(f"{pid}: respaldo: {e}"); alerta(f"No se pudo respaldar {pid}: {e}")
INTENTOS_REDACCION = 3


def _hoy_mx():
    return (datetime.now(timezone.utc) - timedelta(hours=6)).date()


def metrica(ev):
    """registro/metricas_generacion.jsonl: llamadas de IA e intentos por solicitud, con su resultado y categoría."""
    f = RAIZ / "registro" / "metricas_generacion.jsonl"; f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as h: h.write(json.dumps({"ts": cola.ahora(), **ev}, ensure_ascii=False) + "\n")


def huella_entrada(sol):
    """Lo que define a una solicitud: si no cambia, repetirla daría el mismo resultado (y gastaría cuota)."""
    import hashlib
    clave = {k: sol.get(k) for k in ("titulo", "gancho", "angulo", "plantilla", "fuentes_sugeridas", "investigacion")}
    return hashlib.sha256(json.dumps(clave, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def reabrir_por_cambio():
    """Una solicitud descartada por motivo jurídico o de redacción solo vuelve a intentarse si su tema cambió en el
    catálogo (pregunta, fuentes sugeridas o investigación). Los rechazos humanos y las supersedidas no se reabren."""
    planificador.SOLICITUDES = RAIZ / "estado" / "solicitudes"
    try: cat = {r["id"]: r for r in planificador.cargar_catalogo()}
    except Exception: return
    for f in sorted(planificador.SOLICITUDES.glob("*.json")):
        try: sol = json.loads(f.read_text())
        except ValueError: continue
        if sol.get("estado") != "DESCARTADA" or "Rechazo humano" in str(sol.get("motivo_cierre", "")) or not sol.get("huella_entrada"): continue
        if sol.get("lote"): continue        # la pregunta del lote la fija data/lote_piloto.json, no el catálogo (28-10: T015 se reabría en cada ciclo)
        r = cat.get(sol.get("tema_id"))
        if not r: continue
        nueva = {**sol, "titulo": r.get("titulo", sol.get("titulo")), "gancho": r.get("gancho", sol.get("gancho")), "fuentes_sugeridas": r.get("fuentes_sugeridas", sol.get("fuentes_sugeridas"))}
        if huella_entrada(nueva) != sol["huella_entrada"]:
            nueva["historial"] = sol.get("historial", []) + [{"estado": "DESCARTADA", "a": "PENDIENTE_GUION", "fecha_cambio": cola.ahora()[:10], "motivo": "el tema cambió en el catálogo"}]
            nueva.update(estado="PENDIENTE_GUION", intentos=0); f.write_text(json.dumps(nueva, ensure_ascii=False, indent=2))
            cola.log({"evento": "solicitud_reabierta", "solicitud": f.name, "motivo": "el tema cambió en el catálogo"})


def _reproduccion(t):
    """Una pieza que ya se produjo antes y vuelve a verificarse (edición, verificador nuevo, retención vencida) no ocupa el
    espacio de redacción de su formato. Antes la bloqueaba: el 27-10 la re-producción de I20261124-T073 impidió redactar
    las imágenes T016 y T028 del piloto."""
    return any(h.get("a") == "PRODUCIDO" for h in t.get("historial", []))


def redactar_pendientes(c, resumen, transporte, env, simulador=None):
    planificador.RAIZ = RAIZ; planificador.SOLICITUDES = RAIZ / "estado" / "solicitudes"; planificador.LOTE = RAIZ / "data" / "lote_piloto.json"
    redactor.ANALISIS = RAIZ / "estado" / "analisis"
    import modelos; modelos.USO = RAIZ / "estado" / "uso_ia.jsonl"; modelos.Modelo.llamadas_ciclo = 0; modelos.Modelo.caidos_ciclo = set()
    planificador.planificar(dias=7, desde=_hoy_mx(), env=env, escribir=True)
    import time as _t; t0 = _t.time(); limite = modelos.config().get("presupuesto_redaccion_s", 1500)
    reabrir_por_cambio()
    sin_cuota = False
    lote = planificador.lote_activo()
    for formato in ("reel", "imagen"):
        if sin_cuota: break                                   # cuota agotada: no se intenta ningún otro formato en este ciclo
        cupo = int((env or {}).get("REDACCIONES_POR_FORMATO") or 1)    # 3-11: inventario de 90 días; ciclo.yml fija 2
        cupo -= sum(1 for t in c["trabajos"].values() if t.get("formato", "reel") == formato and t["estado"] in ACTIVOS and not _reproduccion(t))
        if cupo <= 0:
            continue                                          # ya hay guiones nuevos de este formato esperando producción
        intentos = 0; hechas = 0
        for f in sorted(planificador.SOLICITUDES.glob(f"*_{formato}_*.json")):
            if intentos >= INTENTOS_REDACCION: break
            if _t.time() - t0 > limite:                      # tope de minutos de Actions por ciclo
                cola.log({"evento": "redaccion_pospuesta", "motivo": f"presupuesto de redacción agotado ({limite} s)"}); break
            sol = json.loads(f.read_text())
            if sol["estado"] != "PENDIENTE_GUION": continue   # en orden de fecha; si un tema falla se adelanta el siguiente
            if lote and sol.get("lote") not in {lote["id"], *lote.get("arrastre", [])}: continue  # lote activo (+ pendientes arrastrados): las demás esperan
            sol["pieza_id"] = f'{"R" if formato == "reel" else "I"}{sol["fecha"].replace("-", "")}-{sol["tema_id"]}'
            sol["archivo"] = f.name; intentos += 1
            try:
                g = redactor.generar(sol, transporte, simulador, env=env)
            except redactor.Descartada as e:
                sol["intentos"] = sol.get("intentos", 0) + (0 if e.categoria == "cuota" else 1); sol["ultimo_motivo"] = str(e)[:500]   # la cuota no es culpa del tema
                sol["ultima_categoria"] = e.categoria; sol["huella_entrada"] = huella_entrada(sol)
                metrica({"solicitud": f.name, "tema_id": sol.get("tema_id"), "lote": sol.get("lote"), "resultado": "descartada", "categoria": e.categoria,
                         "transitoria": e.transitoria, "motivo": str(e)[:600], **(e.metricas or {})})
                if e.categoria == "cuota": sin_cuota = True
                if not e.transitoria or sol["intentos"] >= (6 if e.transitoria else 3):   # fallas de red: más margen antes de descartar
                    sol["estado"] = "DESCARTADA"; resumen["descartadas"].append(f'{sol["tema_id"]}: {str(e)[:120]}')
                f.write_text(json.dumps(sol, ensure_ascii=False, indent=2))
                cola.log({"evento": "redaccion_descartada", "solicitud": f.name, "categoria": e.categoria, "transitoria": e.transitoria, "motivo": str(e)[:300]})
                if getattr(e, "historial", None):           # diagnóstico completo de cada descarte (para mejorar el sistema)
                    d = RAIZ / "estado" / "descartes"; d.mkdir(parents=True, exist_ok=True)
                    (d / f.name).write_text(json.dumps({"solicitud": f.name, "fecha": cola.ahora(), "motivo": str(e), "historial": e.historial}, ensure_ascii=False, indent=1)[:200000])
                if e.transitoria: break                # falla de red o de cuota: no tiene caso probar otro tema ahora
                continue
            carpeta = RAIZ / "piezas" / sol["pieza_id"]; carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "guion.json").write_text(json.dumps(g, ensure_ascii=False, indent=2))
            sol["estado"] = "GUION_LISTO"; sol["pieza"] = sol["pieza_id"]; f.write_text(json.dumps(sol, ensure_ascii=False, indent=2))
            metrica({"solicitud": f.name, "tema_id": sol.get("tema_id"), "lote": sol.get("lote"), "pieza": sol["pieza_id"], "resultado": "redactada", **((g.get("generacion") or {}).get("metricas") or {})})
            resumen["redactadas"].append(sol["pieza_id"]); cola.log({"evento": "redactada", "pieza": sol["pieza_id"], "solicitud": f.name})
            hechas += 1
            if hechas >= cupo: break
            intentos = 0


def ciclo(dueño, transporte_fuentes=verificador.transporte_resiliente, http_meta=publicar.http_real, env=os.environ, por_formato=1, simulador=None):
    if not cola.adquirir_lock(dueño):
        print("Otra ejecución tiene el bloqueo; salgo sin hacer nada."); return {"resultado": "bloqueado"}
    c = cola.cargar(); resumen = {"redactadas": [], "descartadas": [], "producidas": [], "retenidas": [], "simuladas": [], "publicando": [], "confirmadas": [], "errores": []}
    modo, motivo_modo = publicar.modo_operacion(env)
    cola.log({"evento": "inicio_ciclo", "modo": modo, "motivo": motivo_modo, "tope_mxn": presupuesto.tope(env)})
    try:
        # 1) redacción autónoma
        try:
            redactar_pendientes(c, resumen, transporte_fuentes, env, simulador)
        except Exception as e:
            resumen["errores"].append(f"redacción: {e}"); alerta(f"Falla en la redacción automática: {type(e).__name__}: {e}")
            cola.log({"evento": "error_redaccion", "detalle": traceback.format_exc(limit=6)[-1500:]})
        _rutas()
        try:
            revision.recoger(c, env); resumen["decisiones"] = revision.aplicar(c)
        except Exception as e:
            resumen["errores"].append(f"revisión: {e}"); cola.log({"evento": "error_revision", "detalle": str(e)[:300]})
        # 2) encolar y detectar guiones modificados
        # Las versiones cortas para Instagram (piezas/<ID>-IG) las produce y aprueba solo version_ig.py; el ciclo no las toca
        # (3-11-2026: el ciclo las re-producía y sobrescribía su salida y su respaldo).
        # 16-11: lo mismo con la versión larga de TikTok (piezas/<ID>-TT): la produce y registra tiktok_largo.py; si el ciclo la
        # encolara, al aprobarse la publicaría como pieza suelta en Facebook.
        for pid in [k for k, x in c["trabajos"].items() if es_derivada(k) and x["estado"] not in cola.ESTADOS_REALES]:
            del c["trabajos"][pid]; cola.log({"pieza": pid, "evento": "fuera_de_cola",
                                              "motivo": "versión corta de Instagram: la gestiona version_ig.py" if es_version_ig(pid) else "versión larga de TikTok: la gestiona tiktok_largo.py"})
        for g_path in sorted((RAIZ / "piezas").glob("*/guion.json")):
            pid = g_path.parent.name
            if es_derivada(pid): continue
            try:
                g = json.loads(g_path.read_text()); errores = esquema.validar(g)
            except ValueError as e:
                g, errores = None, [f"JSON inválido: {e}"]
            huella = producir.huella_guion(g) if g else None
            if cola.encolar(c, pid, formato=(g or {}).get("formato", "reel"), huella=huella) and errores:
                cola.mover(c, pid, "RETENIDO", "guion incompleto: " + "; ".join(errores[:5]))
                c["trabajos"][pid]["retencion"] = {"tipo": "sustantivo", "desde": cola.ahora()}
                resumen["retenidas"].append(pid); continue
            t = c["trabajos"][pid]
            if t["estado"] == "RETENIDO" and huella and t.get("huella") != huella and not errores:
                t["huella"] = huella; cola.mover(c, pid, "PENDIENTE", "el guion cambió; se vuelve a verificar")
        # 6b) si cambió la lógica del verificador, las retenciones por verificación se revisan de nuevo
        for t in [x for x in c["trabajos"].values() if x["estado"] == "RETENIDO" and not (x.get("retencion") or {}).get("archivada")
                  and (x.get("retencion") or {}).get("verificador") not in (None, verificador.VERSION)
                  or (x["estado"] == "RETENIDO" and not (x.get("retencion") or {}).get("archivada") and (x.get("retencion") or {}).get("verificador") is None and "verificación jurídica" in (x["historial"][-1]["motivo"] if x["historial"] else ""))]:
            cola.mover(c, t["id"], "PENDIENTE", f"verificador actualizado a {verificador.VERSION}; se vuelve a verificar")
        # 7) retenciones transitorias vencidas
        for t in [x for x in c["trabajos"].values() if x["estado"] == "RETENIDO" and (x.get("retencion") or {}).get("tipo") == "transitorio"]:
            if datetime.fromisoformat(t["retencion"]["desde"]) + timedelta(hours=REVERIFICAR_H) <= datetime.now(timezone.utc):
                cola.mover(c, t["id"], "PENDIENTE", "re-verificación de retención transitoria")
        # 6) retomar publicaciones en curso
        for t in cola.siguientes(c, "PUBLICANDO", n=5):
            _publicar(c, t, modo, env, http_meta, resumen, retomar=True)
        # 3–5) una pieza por formato
        for formato in ("reel", "imagen"):
            extra = min(2, sum(1 for x in c["trabajos"].values() if x["estado"] == "PENDIENTE" and x.get("formato", "reel") == formato and _reproduccion(x)))
            for t in cola.siguientes(c, "PENDIENTE", n=por_formato + extra, formato=formato):   # las re-producciones (edición, verificador nuevo) no quitan el lugar a una pieza nueva
                pid = t["id"]
                try:
                    g = _guion(pid)
                    n0 = len(verificador.RESPALDOS_USADOS)
                    ver = verificador.verificar_guion(g, transporte_fuentes)
                    if verificador.RESPALDOS_USADOS[n0:]:       # el texto oficial se cotejó contra una copia reciente, no en vivo
                        ver["copias_respaldo"] = verificador.RESPALDOS_USADOS[n0:]
                        cola.log({"evento": "fuente_desde_respaldo", "pieza": pid, "copias": ver["copias_respaldo"]})
                    (RAIZ / "piezas" / pid / "salida").mkdir(exist_ok=True)
                    (RAIZ / "piezas" / pid / "salida" / "verificacion.json").write_text(json.dumps(ver, ensure_ascii=False, indent=2))
                    if ver["decision"] in ("RETENER", "RECHAZADA"):
                        tipo = "transitorio" if verificador.es_transitoria(ver) else "sustantivo"
                        cola.mover(c, pid, "RETENIDO", f'verificación jurídica: {ver["decision"]}' + "".join(f' · [{x["regla"]}] {x["detalle"]}' for x in ver.get("razonamiento", []) if x["severidad"] == "bloqueante")[:900])
                        t["retencion"] = {"tipo": tipo, "desde": cola.ahora(), "verificador": verificador.VERSION}; resumen["retenidas"].append(pid)
                        if tipo == "sustantivo": alerta(f"{pid} retenido por verificación jurídica ({ver['decision']}).")
                        continue
                    if formato == "imagen":
                        import imagen
                        reg, tec, jur = imagen.producir(RAIZ / "piezas" / pid, ver)
                    else:
                        reg, tec, jur = producir.producir(RAIZ / "piezas" / pid, ver)
                    cola.mover(c, pid, "PRODUCIDO", f'{reg.get("duracion_s", "imagen")}')
                    resumen["producidas"].append(pid); _respaldar(pid, resumen, env)
                    if jur["decision"] in ("APTO", "APTO_CON_CRITERIO") and _requiere_revision(pid, env):
                        cola.mover(c, pid, "REVISION_HUMANA", f'{jur["decision"]}; pieza redactada por IA: espera la aprobación editorial humana')
                        resumen.setdefault("en_revision", []).append(pid)
                        try: revision.enviar(c, pid, env)
                        except Exception as e: cola.log({"evento": "revision_sin_enviar", "pieza": pid, "motivo": str(e)[:200]})
                    elif jur["decision"] in ("APTO", "APTO_CON_CRITERIO"):
                        cola.mover(c, pid, "APROBADO", jur["decision"])
                        _publicar(c, t, modo, env, http_meta, resumen)
                    else:
                        cola.mover(c, pid, "RETENIDO", jur["decision"] + ": " + "; ".join(jur["motivos"][:3]))
                        t["retencion"] = {"tipo": jur.get("tipo_retencion") or "sustantivo", "desde": cola.ahora()}
                        resumen["retenidas"].append(pid); alerta(f"{pid} retenido: {jur['decision']}")
                except Exception as e:
                    resumen["errores"].append(f"{pid}: {e}")
                    if cola.fallo(c, pid, traceback.format_exc(limit=3)) == "alerta": alerta(f"{pid} falló 3 veces: {e}")
        # piezas aprobadas que quedaron sin publicar en un ciclo anterior
        for t in cola.siguientes(c, "APROBADO", n=2):
            _publicar(c, t, modo, env, http_meta, resumen)
        revision.enviar_pendientes(c, env)
    finally:
        if verificador.RESPALDOS_USADOS: cola.log({"evento": "respaldos_fuentes", "usados": verificador.RESPALDOS_USADOS})
        cola.log({"evento": "fin_ciclo", **{k: len(v) for k, v in resumen.items()}})
        cola.guardar(c); cola.liberar_lock(dueño)
    return resumen


def _en_calendario(pid):
    try: cal = json.loads((RAIZ / "data" / "calendario_lanzamiento.json").read_text())
    except (OSError, ValueError): return False
    return any(d[f]["pieza"] == pid for d in cal.get("dias", []) for f in ("imagen", "reel"))


def _publicar(c, t, modo, env, http_meta, resumen, retomar=False):
    pid = t["id"]
    if modo == "real" and _en_calendario(pid):     # las piezas del calendario las publica publicador.py a su hora
        resumen.setdefault("en_calendario", []).append(pid); return
    g = _guion(pid); fmt = t.get("formato", "reel")
    d = t.get("decision_humana")
    if d and not retomar and revision.version(pid, fmt)[0] != d.get("version"):    # cambió después de aprobarse
        cola.mover(c, pid, "RETENIDO", "la pieza cambió después de la aprobación humana; se requiere una nueva revisión")
        t["retencion"] = {"tipo": "editorial", "desde": cola.ahora()}; resumen["retenidas"].append(pid); return
    salida = RAIZ / "piezas" / pid / "salida"
    archivo = salida / (f"{pid}_final.mp4" if fmt == "reel" else f"{pid}.png")
    texto = g.get("copy") or g["titulo"]
    try:
        if fmt == "imagen":
            if modo == "real" and not archivo.exists():
                salida.mkdir(parents=True, exist_ok=True); respaldo.descargar(pid, archivo.name, archivo, env)
            r = publicar.publicar_imagen(pid, archivo, texto, t["huella"], programar_para("imagen"), modo=modo, env=env, http=http_meta)
        else:
            if modo == "real" and not archivo.exists():   # runner nuevo: se recupera el archivo EXACTO aprobado (no se regenera)
                salida.mkdir(parents=True, exist_ok=True); respaldo.descargar(pid, archivo.name, archivo, env)
            r = publicar.publicar_reel(pid, archivo, texto, t["huella"], programar_para("reel"), modo=modo, env=env, http=http_meta)
    except publicar.PublicacionAmbigua as e:
        if t["estado"] == "APROBADO": cola.mover(c, pid, "PUBLICANDO", "respuesta ambigua de Meta", modo="real")
        resumen["publicando"].append(pid); alerta(f"{pid}: respuesta ambigua de Meta; se verificará su estado en el siguiente ciclo."); return
    except Exception as e:
        resumen["errores"].append(f"{pid}: {e}")
        if cola.fallo(c, pid, str(e)) == "alerta": alerta(f"Publicación de {pid} falló: {e}")
        return
    if r["estado"] == "SIMULADO":
        cola.mover(c, pid, "SIMULADO", publicar.modo_operacion(env)[1]); resumen["simuladas"].append(pid)
    elif r["estado"] == "PUBLICANDO":
        if t["estado"] == "APROBADO": cola.mover(c, pid, "PUBLICANDO", r["origen"], modo="real")
        resumen["publicando"].append(pid)
    else:
        if t["estado"] == "APROBADO": cola.mover(c, pid, "PUBLICANDO", "subida confirmada", modo="real")
        t["publicaciones"]["facebook"] = {"video_id": r.get("video_id") or r.get("post_id"), "estado": r["estado"], "marca": r["marca"]}
        cola.mover(c, pid, r["estado"], r.get("origen", ""), modo="real"); resumen["confirmadas"].append(pid)


if __name__ == "__main__":
    print(json.dumps(ciclo(os.environ.get("GITHUB_RUN_ID", "local"), por_formato=int(os.environ.get("PRODUCCIONES_POR_FORMATO") or 1)), ensure_ascii=False, indent=2))
