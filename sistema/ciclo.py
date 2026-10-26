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
import cola, producir, publicar, verificador, esquema, presupuesto, planificador, redactor

RAIZ = Path(__file__).resolve().parent.parent
REVERIFICAR_H = 6


def alerta(msg):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT")
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
APROBACIONES = RAIZ / "estado" / "aprobaciones.json"


def _requiere_revision(pid, env):
    """Toda pieza redactada por IA pasa por aprobación humana (REVISION_HUMANA_OBLIGATORIA=0 la desactiva, solo por
    decisión del responsable tras validar la calidad). Las aprobaciones se registran en estado/aprobaciones.json."""
    g = _guion(pid)
    return bool((g.get("generacion") or {}).get("modelos")) and env.get("REVISION_HUMANA_OBLIGATORIA", "1") != "0"


def aplicar_aprobaciones(c, resumen):
    """{"I20261026-T020": {"decision": "APROBADA"|"RECHAZADA", "por": "...", "fecha": "...", "nota": "..."}}"""
    if not APROBACIONES.exists(): return
    for pid, a in json.loads(APROBACIONES.read_text()).items():
        t = c["trabajos"].get(pid)
        if not t or t["estado"] != "REVISION_HUMANA": continue
        if a.get("decision") == "APROBADA":
            cola.mover(c, pid, "APROBADO", f'aprobación humana: {a.get("por", "?")} {a.get("fecha", "")} {a.get("nota", "")}'.strip())
        elif a.get("decision") == "RECHAZADA":
            cola.mover(c, pid, "RETENIDO", f'rechazo humano: {a.get("nota", "")}'); t["retencion"] = {"tipo": "editorial", "desde": cola.ahora()}
INTENTOS_REDACCION = 3


def _hoy_mx():
    return (datetime.now(timezone.utc) - timedelta(hours=6)).date()


def redactar_pendientes(c, resumen, transporte, env, simulador=None):
    planificador.RAIZ = RAIZ; planificador.SOLICITUDES = RAIZ / "estado" / "solicitudes"
    import modelos; modelos.USO = RAIZ / "estado" / "uso_ia.jsonl"
    planificador.planificar(dias=7, desde=_hoy_mx(), env=env, escribir=True)
    import time as _t; t0 = _t.time(); limite = modelos.config().get("presupuesto_redaccion_s", 1500)
    for formato in ("reel", "imagen"):
        if any(t.get("formato", "reel") == formato and t["estado"] in ACTIVOS for t in c["trabajos"].values()):
            continue
        intentos = 0
        for f in sorted(planificador.SOLICITUDES.glob(f"*_{formato}_*.json")):
            if intentos >= INTENTOS_REDACCION: break
            if _t.time() - t0 > limite:                      # tope de minutos de Actions por ciclo
                cola.log({"evento": "redaccion_pospuesta", "motivo": f"presupuesto de redacción agotado ({limite} s)"}); break
            sol = json.loads(f.read_text())
            if sol["estado"] != "PENDIENTE_GUION": continue   # en orden de fecha; si un tema falla se adelanta el siguiente
            sol["pieza_id"] = f'{"R" if formato == "reel" else "I"}{sol["fecha"].replace("-", "")}-{sol["tema_id"]}'
            sol["archivo"] = f.name; intentos += 1
            try:
                g = redactor.generar(sol, transporte, simulador, env=env)
            except redactor.Descartada as e:
                sol["intentos"] = sol.get("intentos", 0) + 1; sol["ultimo_motivo"] = str(e)[:500]
                if not e.transitoria or sol["intentos"] >= 3:
                    sol["estado"] = "DESCARTADA"; resumen["descartadas"].append(f'{sol["tema_id"]}: {str(e)[:120]}')
                f.write_text(json.dumps(sol, ensure_ascii=False, indent=2))
                cola.log({"evento": "redaccion_descartada", "solicitud": f.name, "transitoria": e.transitoria, "motivo": str(e)[:300]})
                if e.transitoria: break                # falla de red o de cuota: no tiene caso probar otro tema ahora
                continue
            carpeta = RAIZ / "piezas" / sol["pieza_id"]; carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "guion.json").write_text(json.dumps(g, ensure_ascii=False, indent=2))
            sol["estado"] = "GUION_LISTO"; sol["pieza"] = sol["pieza_id"]; f.write_text(json.dumps(sol, ensure_ascii=False, indent=2))
            resumen["redactadas"].append(sol["pieza_id"]); cola.log({"evento": "redactada", "pieza": sol["pieza_id"], "solicitud": f.name})
            break


def ciclo(dueño, transporte_fuentes=verificador.transporte_http, http_meta=publicar.http_real, env=os.environ, por_formato=1, simulador=None):
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
        aplicar_aprobaciones(c, resumen)
        # 2) encolar y detectar guiones modificados
        for g_path in sorted((RAIZ / "piezas").glob("*/guion.json")):
            pid = g_path.parent.name
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
        for t in [x for x in c["trabajos"].values() if x["estado"] == "RETENIDO" and (x.get("retencion") or {}).get("verificador") not in (None, verificador.VERSION)
                  or (x["estado"] == "RETENIDO" and (x.get("retencion") or {}).get("verificador") is None and "verificación jurídica" in (x["historial"][-1]["motivo"] if x["historial"] else ""))]:
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
            for t in cola.siguientes(c, "PENDIENTE", n=por_formato, formato=formato):
                pid = t["id"]
                try:
                    g = _guion(pid)
                    ver = verificador.verificar_guion(g, transporte_fuentes)
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
                    resumen["producidas"].append(pid)
                    if jur["decision"] in ("APTO", "APTO_CON_CRITERIO") and _requiere_revision(pid, env):
                        cola.mover(c, pid, "REVISION_HUMANA", f'{jur["decision"]}; pieza redactada por IA: espera la aprobación editorial humana')
                        resumen.setdefault("en_revision", []).append(pid)
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
    finally:
        cola.log({"evento": "fin_ciclo", **{k: len(v) for k, v in resumen.items()}})
        cola.guardar(c); cola.liberar_lock(dueño)
    return resumen


def _publicar(c, t, modo, env, http_meta, resumen, retomar=False):
    pid = t["id"]; g = _guion(pid); fmt = t.get("formato", "reel")
    salida = RAIZ / "piezas" / pid / "salida"
    archivo = salida / (f"{pid}_final.mp4" if fmt == "reel" else f"{pid}.png")
    texto = g.get("copy") or g["titulo"]
    try:
        if fmt == "imagen":
            r = publicar.publicar_imagen(pid, archivo, texto, t["huella"], programar_para("imagen"), modo=modo, env=env, http=http_meta)
        else:
            if modo == "real" and not archivo.exists():
                producir.producir(RAIZ / "piezas" / pid)   # runner nuevo: se regenera antes de retomar la subida
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
    print(json.dumps(ciclo(os.environ.get("GITHUB_RUN_ID", "local")), ensure_ascii=False, indent=2))
