"""Versión larga SOLO para TikTok (65 a 75 s) de cada Reel aprobado — decisión del responsable, 16-11-2026
(data/lanzamiento.json → monetizacion_decisiones.tiktok_version_larga): el programa de Recompensas de TikTok exige videos de
más de 1 minuto. Facebook, Instagram y YouTube siguen con el Reel de 30 a 45 s, que NO se modifica.

Cómo opera (sin intervención, desde TIKTOK_LARGO_DESDE de data/lanzamiento.json; antes no hace nada):
  1. En cada ciclo (ciclo.yml, paso «Versión larga para TikTok») toma los Reels del calendario más próximos a publicarse
     (al menos ANTICIPACION_DIAS por delante, para que quepan las 72 h de veto) cuya aprobación vigente coincide con el
     calendario y que todavía no tienen versión larga. Los Reels que ya duran más de 60 s no la necesitan.
  2. redactor.ampliar_tiktok redacta la ampliación (misma pregunta, misma cita literal, mismos artículos + un ejemplo o una
     condición/excepción del texto oficial) con todos los controles; luego verificador, producción (producir.py, con el rango
     de 60 a 75 s de auditoria.DURACION_TIKTOK), respaldo en el release y huella SHA-256 propia.
  3. La pieza derivada es piezas/<ID>-TT y queda en REVISION_HUMANA en estado/tiktok_largo.json (fuera de la cola del ciclo).
     Se aprueba igual que un Reel: python sistema/decidir.py aprobar <ID>-TT <versión> --por "…" --delegada (72 h de veto).
     Su aprobación es propia: nunca toca la del Reel ni sus archivos.
  4. Al aprobarse entra al calendario como dia["reel"]["tiktok"] (con la versión del Reel de la que deriva: «de_version»).
     tiktok.py la envía a la bandeja en lugar del Reel solo si está aprobada, fuera del plazo de veto y con la huella exacta.
Costo: 0 MXN (Gemini nivel gratuito; minutos de Actions dentro de la guardia del ciclo).

Uso:  python sistema/tiktok_largo.py producir      (lo llama ciclo.yml)
      python sistema/tiktok_largo.py calendario    (sincroniza dia["reel"]["tiktok"] con las variantes aprobadas)
      python sistema/tiktok_largo.py listar
"""
import hashlib, json, os, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redactor

RAIZ = Path(__file__).resolve().parent.parent
REG = RAIZ / "estado" / "tiktok_largo.json"
CAL = RAIZ / "data" / "calendario_lanzamiento.json"
AUT = RAIZ / "data" / "lanzamiento.json"
PIEZAS = RAIZ / "registro" / "piezas.jsonl"
ANTICIPACION_DIAS = 4        # producida y aprobada hoy → fin del veto en 72 h → envío a la bandeja la noche anterior a su fecha
MAX_DESCARTES = 2            # después de 2 descartes del tema, ese día TikTok recibe el Reel normal
DURACION_SUFICIENTE = 60.0   # un Reel que ya dura más de 60 s cumple el requisito de TikTok sin versión larga
SUFIJO = redactor.SUFIJO_TIKTOK


class NoDecidible(ValueError):
    pass


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hoy_mx():
    return (datetime.now(timezone.utc) - timedelta(hours=6)).date()


def id_variante(base):
    return f"{base}{SUFIJO}"


def es_variante(pid):
    return redactor.es_variante_tiktok(pid)


def desde(archivo=None):
    try: return json.loads(Path(archivo or AUT).read_text()).get("TIKTOK_LARGO_DESDE")
    except (OSError, ValueError): return None


def activo(hoy, archivo=None):
    d = desde(archivo)
    return bool(d) and hoy.isoformat() >= d


def cargar():
    try: return json.loads(REG.read_text())
    except (OSError, ValueError): return {}


def guardar(reg):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n")


def duracion_registrada(pid):
    """Duración del último MP4 producido de la pieza (registro/piezas.jsonl), o None."""
    d = None
    try:
        for l in PIEZAS.read_text().splitlines():
            if l.strip():
                x = json.loads(l)
                if x.get("id") == pid: d = x.get("duracion_s")
    except (OSError, ValueError):
        return None
    return d


def _aprobacion_vigente(e):
    """La última decisión del Reel es APROBADA y corresponde a la versión y huella del calendario."""
    import publicador
    try: d = publicador.ultima_decision(e["pieza"])
    except OSError: return False
    return bool(d and d.get("decision") == "APROBADA" and d.get("version") == e.get("version") and d.get("huella_archivo") == e.get("sha256"))


def candidatos(cal, reg, hoy, env=None):
    """[(fecha, entrada del Reel)] por producir, del más próximo a publicarse al más lejano."""
    env = env or {}
    limite = (hoy + timedelta(days=ANTICIPACION_DIAS)).isoformat()
    out = []
    for dia in cal.get("dias", []):
        e = dia.get("reel")
        if not e or dia["fecha"] < limite: continue
        if env.get("PUBLICAR_HASTA") and dia["fecha"] > env["PUBLICAR_HASTA"]: continue
        if (e.get("tiktok") or {}).get("de_version") == e.get("version"): continue      # ya tiene su versión larga aprobada
        if not _aprobacion_vigente(e): continue
        dur = duracion_registrada(e["pieza"])
        if dur and dur > DURACION_SUFICIENTE: continue
        v = reg.get(id_variante(e["pieza"])) or {}
        if v.get("version_base") == e.get("version"):
            if v.get("estado") in ("REVISION_HUMANA", "APROBADA", "RECHAZADA", "DESCARTADA"): continue
            if v.get("intentos", 0) >= MAX_DESCARTES: continue
        out.append((dia["fecha"], e))
    return sorted(out, key=lambda x: x[0])


def _log(ev):
    try:
        import cola; cola.log({"evento": "tiktok_largo", **ev})
    except Exception:
        pass


def producir_una(fecha, e, reg, env, transporte, simulador=None):
    """Redacta, verifica, produce y respalda la versión larga de un Reel. Actualiza y devuelve su registro."""
    import producir, respaldo, revision, verificador
    base_id = e["pieza"]; pid = id_variante(base_id); carpeta = RAIZ / "piezas" / pid
    gbase = RAIZ / "piezas" / base_id / "guion.json"
    base = json.loads(gbase.read_text())
    previo = reg.get(pid) or {}
    r = previo if previo.get("version_base") == e["version"] else {}
    r.update(de=base_id, version_base=e["version"], fecha_calendario=fecha, huella_guion_base=hashlib.sha256(gbase.read_bytes()).hexdigest(),
             fecha=ahora(), intentos=r.get("intentos", 0))
    for k in ("motivo", "revision", "sha256", "asset_id", "release", "duracion_s", "dictamen", "fallas_tecnicas"): r.pop(k, None)
    reg[pid] = r
    try:
        g = redactor.ampliar_tiktok(base, transporte, simulador, env)
    except redactor.Descartada as x:
        if x.categoria != "cuota": r["intentos"] += 1
        r.update(estado="PENDIENTE" if (x.transitoria or r["intentos"] < MAX_DESCARTES) else "DESCARTADA", motivo=str(x)[:600], categoria=x.categoria)
        if getattr(x, "historial", None):
            d = RAIZ / "estado" / "descartes"; d.mkdir(parents=True, exist_ok=True)
            (d / f"{pid}.json").write_text(json.dumps({"pieza": pid, "fecha": ahora(), "motivo": str(x), "historial": x.historial}, ensure_ascii=False, indent=1)[:200000])
        _log({"pieza": pid, "resultado": "descartada", "motivo": str(x)[:300]}); return r
    g["id"] = pid
    g["version_tiktok"].update(version_base=e["version"], huella_guion_base=r["huella_guion_base"], fecha_calendario=fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "guion.json").write_text(json.dumps(g, ensure_ascii=False, indent=2))
    ver = verificador.verificar_guion(g, transporte)
    (carpeta / "salida").mkdir(exist_ok=True)
    (carpeta / "salida" / "verificacion.json").write_text(json.dumps(ver, ensure_ascii=False, indent=2))
    if ver["decision"] in ("RETENER", "RECHAZADA"):
        transitoria = verificador.es_transitoria(ver)
        if not transitoria: r["intentos"] += 1
        r.update(estado="PENDIENTE" if (transitoria or r["intentos"] < MAX_DESCARTES) else "RETENIDA", motivo=f'verificación jurídica: {ver["decision"]}')
        _log({"pieza": pid, "resultado": "retenida", "motivo": r["motivo"]}); return r
    info, tec, jur = producir.producir(carpeta, ver)
    falla = [c["control"] + f' ({c["detalle"]})' for c in tec if c["resultado"] == "FALLA"]
    resp = respaldo.respaldar(pid, carpeta / "salida", env)
    mp4 = f"{pid}_final.mp4"
    r.update(duracion_s=info.get("duracion_s"), sha256=info.get("sha256"), asset_id=(resp.get(mp4) or {}).get("asset_id"),
             release=(resp.get(mp4) or {}).get("release"), dictamen=jur["decision"], fallas_tecnicas=falla, archivo=mp4)
    if falla or jur["decision"] not in ("APTO", "APTO_CON_CRITERIO"):
        r["intentos"] += 1
        r.update(estado="PENDIENTE" if r["intentos"] < MAX_DESCARTES else "RETENIDA",
                 motivo="; ".join(falla[:3] + jur.get("motivos", [])[:3])[:600] or jur["decision"])
        _log({"pieza": pid, "resultado": "retenida", "motivo": r["motivo"][:300]}); return r
    version, hg, ha = revision.version(pid, "reel")
    if not version:
        r.update(estado="PENDIENTE", motivo="sin respaldo del archivo: no hay versión que revisar"); return r
    r.update(estado="REVISION_HUMANA", revision={"version": version, "huella_guion": hg, "huella_archivo": ha, "preparada": ahora()})
    _log({"pieza": pid, "resultado": "revision_humana", "version": version, "duracion_s": r["duracion_s"]})
    return r


def ejecutar(hoy=None, env=None, transporte=None, simulador=None, maximo=1, presupuesto_s=900):
    import verificador
    env = env if env is not None else os.environ
    hoy = hoy or hoy_mx()
    if not activo(hoy):
        return {"estado": "INACTIVO", "desde": desde(), "hoy": hoy.isoformat()}
    transporte = transporte or verificador.transporte_resiliente
    cal = json.loads(CAL.read_text()); reg = cargar()
    res = {"estado": "ACTIVO", "hoy": hoy.isoformat(), "producidas": [], "otras": []}
    t0 = time.time()
    for fecha, e in candidatos(cal, reg, hoy, env)[:maximo]:
        if time.time() - t0 > presupuesto_s:
            res["pospuesto"] = f"presupuesto de {presupuesto_s} s agotado"; break
        try:
            r = producir_una(fecha, e, reg, env, transporte, simulador)
        except Exception as x:                      # una falla de una variante no detiene el ciclo ni las demás redes
            r = reg.setdefault(id_variante(e["pieza"]), {"de": e["pieza"], "version_base": e["version"]})
            r.update(estado="PENDIENTE", motivo=f"{type(x).__name__}: {x}"[:600], intentos=r.get("intentos", 0) + 1)
        guardar(reg)
        (res["producidas"] if r.get("estado") == "REVISION_HUMANA" else res["otras"]).append({"pieza": id_variante(e["pieza"]), "fecha": fecha,
                                                                                               "estado": r.get("estado"), "motivo": r.get("motivo")})
        if (r.get("categoria") == "cuota"): break
    res["calendario"] = al_calendario()
    return res


# ── aprobación (la llama decidir.py) ─────────────────────────────────────────────────────────────────────────────
def pendientes():
    return [{"pieza": k, "formato": "reel (versión larga solo TikTok)", "de": v.get("de"), "fecha": v.get("fecha_calendario"),
             "version": (v.get("revision") or {}).get("version"), "duracion_s": v.get("duracion_s"), "archivo": v.get("archivo")}
            for k, v in sorted(cargar().items()) if v.get("estado") == "REVISION_HUMANA"]


def decidir(pid, decision, ver, por, nota="", canal="chat"):
    """Registra la aprobación (o el rechazo/veto) de la versión EXACTA de la variante; nunca la del Reel del que deriva."""
    import revision
    reg = cargar(); v = reg.get(pid)
    permitido = {"REVISION_HUMANA": ("APROBADA", "RECHAZADA"), "APROBADA": ("RECHAZADA",)}   # el veto puede llegar ya aprobada
    if not v or decision not in permitido.get(v.get("estado"), ()):
        raise NoDecidible(f"{pid}: estado {v.get('estado') if v else 'desconocido'}; no admite «{decision}»")
    actual, hg, ha = revision.version(pid, "reel")
    preparada = (v.get("revision") or {}).get("version")
    if not actual or ver != actual or ver != preparada:
        raise NoDecidible(f"{pid}: la versión {ver} no es la vigente (preparada {preparada}, actual {actual}); no se registró")
    if decision == "RECHAZADA" and not nota.strip():
        raise NoDecidible("un rechazo necesita el motivo (--nota)")
    fila = revision.registrar(pid, decision, ver, hg, ha, {"nombre": por}, canal, nota or f"versión larga solo para TikTok de {v.get('de')}")
    v.update(estado=decision, decision={"fecha": fila["fecha"], "canal": canal, "por": por, "nota": nota})
    guardar(reg)
    al_calendario()
    return fila


def al_calendario(archivo=None):
    """dia["reel"]["tiktok"] = variante APROBADA de ese mismo Reel (misma versión). Quita la que ya no corresponde
    (Reel con otra versión, variante vetada). No toca ningún otro campo del calendario."""
    archivo = Path(archivo or CAL)
    cal = json.loads(archivo.read_text()); reg = cargar(); cambios = []
    for dia in cal.get("dias", []):
        e = dia.get("reel")
        if not e: continue
        pid = id_variante(e["pieza"]); v = reg.get(pid) or {}
        if v.get("estado") == "APROBADA" and v.get("version_base") == e.get("version") and v.get("asset_id") and v.get("sha256"):
            d = v.get("decision") or {}
            nuevo = {"pieza": pid, "version": (v.get("revision") or {}).get("version"), "archivo": f"{pid}_final.mp4", "sha256": v["sha256"],
                     "asset_id": v["asset_id"], "release": v.get("release"), "aprobada": d.get("fecha"),
                     "aprobacion": "delegada (72 h de veto)" if d.get("canal") == "delegada" else "directa", "de_version": e["version"],
                     "duracion_s": v.get("duracion_s")}
            if e.get("tiktok") != nuevo:
                e["tiktok"] = nuevo; cambios.append(f'{dia["fecha"]} +{pid}')
        elif e.get("tiktok") and (e["tiktok"].get("de_version") != e.get("version") or v.get("estado") != "APROBADA"):
            del e["tiktok"]; cambios.append(f'{dia["fecha"]} -{pid}')
    if cambios:
        archivo.write_text(json.dumps(cal, ensure_ascii=False, indent=1) + "\n")
    return cambios


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "producir"
    if accion == "listar":
        print(json.dumps(pendientes(), ensure_ascii=False, indent=1)); sys.exit(0)
    if accion == "calendario":
        print(json.dumps(al_calendario(), ensure_ascii=False)); sys.exit(0)
    import publicador
    env = publicador.con_autorizacion(os.environ)
    r = ejecutar(env=env, maximo=int(os.environ.get("TIKTOK_LARGO_POR_CICLO") or 1),
                 presupuesto_s=int(os.environ.get("TIKTOK_LARGO_PRESUPUESTO_S") or 900))
    print(json.dumps(r, ensure_ascii=False, indent=1))
