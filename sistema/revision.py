"""Revisión humana desde el teléfono, por Telegram (gratuito; sin editar archivos ni entrar al repositorio).

Flujo:
  1. Cuando una pieza llega a REVISION_HUMANA, el bot del proyecto envía al chat VINCULADO la imagen o el video final
     (el mismo archivo respaldado), con el título, la respuesta corta, las fuentes y dos botones: Aprobar / Rechazar.
  2. Cada botón lleva la VERSIÓN de la pieza: huella del guion + huella del archivo final. Al recibir la decisión se
     recalculan ambas huellas; si la pieza cambió desde que se envió, la decisión NO se aplica.
  3. La decisión se registra en estado/aprobaciones.jsonl (solo se agrega, nunca se reescribe): pieza, decisión,
     versión, huellas, quién (id y usuario de Telegram), cuándo y canal. El ciclo la aplica: APROBADO o RETENIDO.
Seguridad: el token del bot es un secreto del repositorio (TELEGRAM_TOKEN); solo se aceptan botones pulsados por la
persona vinculada; el vínculo se hace una sola vez con un código de un solo uso cuya huella (no el código) está en
estado/telegram.json. Telegram conserva los mensajes pendientes 24 h: el flujo «revision» los recoge cada 4 h.
"""
import hashlib, json, os, sys, time, uuid, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cola, respaldo

RAIZ = Path(__file__).resolve().parent.parent
ESTADO_TG = RAIZ / "estado" / "telegram.json"
REGISTRO = RAIZ / "estado" / "aprobaciones.jsonl"
API = "https://api.telegram.org/bot{tok}/{metodo}"


def _ahora(): return datetime.now(timezone.utc).isoformat(timespec="seconds")


def estado_tg():
    return json.loads(ESTADO_TG.read_text()) if ESTADO_TG.exists() else {}


def _guardar_tg(e):
    ESTADO_TG.parent.mkdir(parents=True, exist_ok=True); ESTADO_TG.write_text(json.dumps(e, ensure_ascii=False, indent=2, sort_keys=True))


# ---------------- versión exacta de una pieza ----------------
def principal(pid, formato):
    return f"{pid}_final.mp4" if formato == "reel" else f"{pid}.png"


def version(pid, formato):
    """(versión, huella_guion, huella_archivo). La huella del archivo sale del respaldo persistente, no del runner."""
    g = RAIZ / "piezas" / pid / "guion.json"
    hg = hashlib.sha256(g.read_bytes()).hexdigest() if g.exists() else ""
    ha = (respaldo.cargar().get(pid, {}).get(principal(pid, formato)) or {}).get("sha256", "")
    if not (hg and ha): return None, hg, ha
    return hashlib.sha256(f"{hg}:{ha}".encode()).hexdigest()[:16], hg, ha


# ---------------- HTTP de Telegram ----------------
def http_real(metodo, tok, campos=None, archivo=None):
    url = API.format(tok=tok, metodo=metodo)
    if archivo:
        campo, ruta = archivo; limite = uuid.uuid4().hex; partes = []
        for k, v in (campos or {}).items():
            partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"; filename="{Path(ruta).name}"\r\n'
                      f'Content-Type: application/octet-stream\r\n\r\n'.encode() + Path(ruta).read_bytes() + b"\r\n")
        datos = b"".join(partes) + f"--{limite}--\r\n".encode(); tipo = f"multipart/form-data; boundary={limite}"
    else:
        datos = json.dumps(campos or {}).encode(); tipo = "application/json"
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"ok": False, "description": f"HTTP {e.code}"}


# ---------------- vínculo con el responsable ----------------
def nuevo_codigo(vigencia_h=72):
    """Genera un código de un solo uso; guarda solo su huella. Devuelve el código (se comunica al responsable)."""
    cod = "ADL-" + uuid.uuid4().hex[:8].upper()
    e = estado_tg(); e.update(vinculo_sha256=hashlib.sha256(cod.encode()).hexdigest(), vinculo_vence=int(time.time()) + vigencia_h * 3600)
    _guardar_tg(e); return cod


def _texto_pieza(pid, t, g, ver):
    rz = g.get("razonamiento") or {}
    fuentes = sorted({f'{f.get("documento", "").split(",")[0]}, art. {f.get("articulo")}' for f in (g.get("fuentes") or {}).values()})
    fmt = "Reel" if t.get("formato", "reel") == "reel" else "Imagen"
    return (f"🧾 {fmt} para revisión · {pid}\n\n{g.get('titulo', '')}\n\nRespuesta: {rz.get('respuesta_corta', '—')}\n\n"
            f"Fuentes: {'; '.join(fuentes)[:300]}\nVersión: {ver}\n\nRevisa el contenido y la exactitud jurídica antes de decidir.")[:1000]


def enviar(c, pid, env=os.environ, http=None):
    http = http or http_real
    """Envía la pieza a revisión. Devuelve True si se envió; False si falta el bot, el vínculo o el respaldo."""
    tok, e = env.get("TELEGRAM_TOKEN"), estado_tg()
    t = c["trabajos"][pid]; fmt = t.get("formato", "reel")
    ver, hg, ha = version(pid, fmt)
    if ver and not (t.get("revision") or {}).get("version") == ver:
        # canal por defecto (decisión del usuario, 26-10-2026): revisión en el chat con Claude. Se fija aquí la versión
        # exacta que se le mostrará; una decisión solo se aplica a esta versión (sistema/decidir.py).
        t["revision"] = {"version": ver, "huella_guion": hg, "huella_archivo": ha, "preparada": _ahora(), "canal": "chat"}
        cola.log({"evento": "revision_preparada", "pieza": pid, "version": ver, "canal": "chat"})
    if not (tok and e.get("chat_id") and ver):
        if not ver: cola.log({"evento": "revision_sin_enviar", "pieza": pid, "motivo": "sin respaldo"})
        return False
    g = json.loads((RAIZ / "piezas" / pid / "guion.json").read_text())
    arch = RAIZ / "piezas" / pid / "salida" / principal(pid, fmt)
    if not arch.exists() or respaldo.sha256(arch) != ha:
        arch = respaldo.descargar(pid, principal(pid, fmt), Path("/tmp") / principal(pid, fmt), env)
    teclado = {"inline_keyboard": [[{"text": "✅ Aprobar", "callback_data": f"A|{pid}|{ver}"}, {"text": "❌ Rechazar", "callback_data": f"R|{pid}|{ver}"}]]}
    r = http("sendVideo" if fmt == "reel" else "sendPhoto", tok, {"chat_id": e["chat_id"], "caption": _texto_pieza(pid, t, g, ver),
             "reply_markup": json.dumps(teclado)}, ("video" if fmt == "reel" else "photo", arch))
    if not r.get("ok"):
        cola.log({"evento": "revision_sin_enviar", "pieza": pid, "motivo": str(r.get("description"))[:200]}); return False
    texto = (g.get("copy") or " ".join(x.get("texto", "") for x in g.get("escenas", [])))[:3500]
    http("sendMessage", tok, {"chat_id": e["chat_id"], "text": f"Texto que acompaña a {pid}:\n\n{texto}"})
    t["revision"] = {"version": ver, "huella_guion": hg, "huella_archivo": ha, "enviada": _ahora(), "mensaje_id": r["result"]["message_id"], "canal": "telegram"}
    cola.log({"evento": "revision_enviada", "pieza": pid, "version": ver}); return True


def registrar(pid, decision, ver, hg, ha, por, canal, nota=""):
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    fila = {"pieza": pid, "decision": decision, "version": ver, "huella_guion": hg, "huella_archivo": ha, "por": por, "fecha": _ahora(), "canal": canal, "nota": nota}
    with REGISTRO.open("a") as f: f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def recoger(c, env=os.environ, http=None):
    http = http or http_real
    """Lee los mensajes y botones pendientes del bot. Devuelve las decisiones registradas en esta llamada."""
    tok = env.get("TELEGRAM_TOKEN")
    if not tok: return []
    e = estado_tg(); hechas = []
    r = http("getUpdates", tok, {"offset": e.get("offset", 0), "timeout": 0, "allowed_updates": ["message", "callback_query"]})
    for u in r.get("result", []) if r.get("ok") else []:
        e["offset"] = u["update_id"] + 1
        m = u.get("message")
        if m and (m.get("text") or "").startswith("/vincular"):
            cod = (m["text"].split(maxsplit=1) + [""])[1].strip()
            valido = (not e.get("chat_id") and e.get("vinculo_sha256") == hashlib.sha256(cod.encode()).hexdigest()
                      and time.time() < e.get("vinculo_vence", 0) and m["chat"].get("type") == "private")
            if valido:
                e.update(chat_id=m["chat"]["id"], usuario_id=m["from"]["id"], usuario=m["from"].get("username"), vinculado=_ahora())
                e.pop("vinculo_sha256", None)
                http("sendMessage", tok, {"chat_id": m["chat"]["id"], "text": "Listo: este chat queda vinculado a la revisión de Aquí Dice la Ley."})
                cola.log({"evento": "telegram_vinculado", "usuario": m["from"].get("username")})
            else:
                cola.log({"evento": "telegram_vinculo_rechazado", "de": m["from"].get("id")})
            continue
        q = u.get("callback_query")
        if not q: continue
        responder = lambda txt: http("answerCallbackQuery", tok, {"callback_query_id": q["id"], "text": txt})
        if q["from"]["id"] != e.get("usuario_id"):
            responder("No autorizado."); cola.log({"evento": "revision_no_autorizada", "de": q["from"]["id"]}); continue
        try:
            accion, pid, ver = q["data"].split("|")
        except ValueError:
            responder("Botón inválido."); continue
        t = c["trabajos"].get(pid)
        actual, hg, ha = version(pid, (t or {}).get("formato", "reel")) if t else (None, "", "")
        if not t or t["estado"] != "REVISION_HUMANA":
            responder("Esta pieza ya no está en revisión."); continue
        if ver != (t.get("revision") or {}).get("version") or ver != actual:
            responder("Esta versión ya no es la vigente; no se aplicó."); cola.log({"evento": "revision_version_distinta", "pieza": pid, "boton": ver, "vigente": actual}); continue
        dec = "APROBADA" if accion == "A" else "RECHAZADA"
        por = {"telegram_id": q["from"]["id"], "usuario": q["from"].get("username"), "nombre": " ".join(x for x in (q["from"].get("first_name"), q["from"].get("last_name")) if x)}
        hechas.append(registrar(pid, dec, ver, hg, ha, por, "telegram"))
        responder("Aprobada ✅" if dec == "APROBADA" else "Rechazada ❌")
        http("editMessageReplyMarkup", tok, {"chat_id": e["chat_id"], "message_id": q["message"]["message_id"], "reply_markup": {"inline_keyboard": []}})
        http("sendMessage", tok, {"chat_id": e["chat_id"], "text": f"{pid}: {dec.lower()} (versión {ver}). Queda registrado."})
    _guardar_tg(e)
    return hechas


def _cerrar_solicitud(pid, motivo):
    """La solicitud de una pieza rechazada deja de ocupar su fecha: si no, el planificador descartaría la versión corregida."""
    carpeta = RAIZ / "estado" / "solicitudes"
    for f in carpeta.glob("*.json") if carpeta.exists() else []:
        try: d = json.loads(f.read_text())
        except ValueError: continue
        if d.get("pieza") == pid and d.get("estado") not in ("DESCARTADA", "SUPERSEDIDA"):
            d["historial"] = d.get("historial", []) + [{"estado": d["estado"], "a": "DESCARTADA", "fecha_cambio": _ahora()[:10]}]
            d.update(estado="DESCARTADA", motivo_cierre=motivo); f.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def aplicar(c):
    """Aplica la última decisión registrada de cada pieza en REVISION_HUMANA, solo si es para la versión vigente."""
    if not REGISTRO.exists(): return []
    ultimas = {}
    for l in REGISTRO.read_text().splitlines():
        try: d = json.loads(l)
        except ValueError: continue
        ultimas[d["pieza"]] = d
    aplicadas = []
    for pid, d in ultimas.items():
        t = c["trabajos"].get(pid)
        if not t or t["estado"] != "REVISION_HUMANA": continue
        actual = version(pid, t.get("formato", "reel"))[0]
        if not actual or d["version"] != actual or d["version"] != (t.get("revision") or {}).get("version"):
            cola.log({"evento": "decision_no_aplicada", "pieza": pid, "motivo": "versión distinta de la revisada"}); continue
        quien = d["por"].get("usuario") or d["por"].get("nombre") or d["por"]
        if d["decision"] == "APROBADA":
            cola.mover(c, pid, "APROBADO", f'aprobación humana: {quien} {d["fecha"]} versión {d["version"]} ({d["canal"]})')
        else:
            cola.mover(c, pid, "RETENIDO", f'rechazo humano: {quien} {d["fecha"]} versión {d["version"]} {d.get("nota", "")}'.strip())
            t["retencion"] = {"tipo": "editorial", "desde": cola.ahora()}
            _cerrar_solicitud(pid, f'Rechazo humano de {pid} (versión {d["version"]}): {d.get("nota", "")}'[:500])
        t["decision_humana"] = d; aplicadas.append(pid)
    return aplicadas


def enviar_pendientes(c, env=os.environ, http=None):
    http = http or http_real
    for t in [x for x in c["trabajos"].values() if x["estado"] == "REVISION_HUMANA" and not (x.get("revision") or {}).get("mensaje_id")
              and (env.get("TELEGRAM_TOKEN") or not (x.get("revision") or {}).get("version"))]:
        try: enviar(c, t["id"], env, http)
        except Exception as ex: cola.log({"evento": "revision_sin_enviar", "pieza": t["id"], "motivo": str(ex)[:200]})


if __name__ == "__main__":       # flujo «revision»: recoger decisiones, aplicarlas y enviar lo pendiente
    if not cola.adquirir_lock("revision"):
        print("El ciclo está en curso; se intentará en la siguiente ejecución."); sys.exit(0)
    c = cola.cargar()
    try:
        d = recoger(c); a = aplicar(c); enviar_pendientes(c)
        print(json.dumps({"decisiones": d, "aplicadas": a}, ensure_ascii=False, indent=2))
    finally:
        cola.guardar(c); cola.liberar_lock("revision")
