"""Acceso a modelos de lenguaje para la redacción y la auditoría editorial.

Proveedor predeterminado: GitHub Models, gratuito para cuentas personales con límites diarios.
Según la documentación consultada el 25-10-2026, el nivel «low» permite 150 solicitudes al día y el «high» 50,
con 8,000 tokens de entrada y 4,000 de salida por solicitud. Sin método de pago, el uso se BLOQUEA al agotar la
cuota: no genera cargos. Se autentica con el GITHUB_TOKEN del propio workflow (permiso `models: read`), sin
cuentas ni llaves adicionales. Limitación declarada por GitHub: los límites gratuitos están pensados para
prototipos y experimentación y «pueden cambiar sin aviso». Por eso:
  · cada llamada se registra en estado/uso_ia.jsonl y hay un tope diario propio, muy por debajo del de GitHub;
  · si el proveedor falla o agota la cuota, la solicitud queda PENDIENTE para el siguiente ciclo (no se inventa nada);
  · el proveedor es intercambiable (config_ia.json): `github_models`, `openai_compatible` (p. ej., un servidor
    llama.cpp local) o `simulado` (pruebas deterministas, sin red).
"""
import json, os, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).resolve().parent / "config_ia.json"
USO = RAIZ / "estado" / "uso_ia.jsonl"


PROVEEDORES = {"github_models", "gemini", "simulado"}


def _limpiar_json(t):
    """Quita cercas ```json … ``` y texto alrededor del primer objeto JSON."""
    t = t.strip()
    if t.startswith("```"): t = t.split("\n", 1)[1] if "\n" in t else t[3:]
    if t.endswith("```"): t = t[:-3]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i >= 0 and j > i else t


class CuotaAgotada(Exception): pass
class Saturado(Exception):
    """HTTP 5xx del proveedor («model is currently experiencing high demand»): se reintenta tras una pausa."""
class FallaModelo(Exception): pass


def config():
    return json.loads(CONFIG.read_text())


def usos_hoy(modelo, archivo=None, proveedor=None):
    """Solicitudes de hoy (UTC, como GitHub) a ese modelo y proveedor; las simuladas no consumen la cuota real."""
    f = Path(archivo or USO); hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not f.exists(): return 0
    return sum(1 for l in f.read_text().splitlines() if l.strip() and (e := json.loads(l))["modelo"] == modelo
               and e["ts"].startswith(hoy) and e.get("proveedor", "github_models") == (proveedor or "github_models")
               and (e.get("resultado") == "ok" or "429" in e.get("error", "")))   # los 5xx y tiempos agotados no consumen cuota


def _registrar(ev, archivo=None):
    f = Path(archivo or USO); f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a") as h: h.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **ev}, ensure_ascii=False) + "\n")


_SERVIDOR = {"proc": None, "gguf": None}


def servidor_local(cfg):
    """Mantiene UN llama-server con el modelo pedido (en 7 GB de RAM no caben dos). Cambia de modelo si hace falta."""
    import subprocess, atexit
    url = f'http://127.0.0.1:{cfg["puerto"]}'
    if _SERVIDOR["gguf"] == cfg["gguf"] and _SERVIDOR["proc"] and _SERVIDOR["proc"].poll() is None:
        return url + "/v1/chat/completions"
    if _SERVIDOR["proc"] and _SERVIDOR["proc"].poll() is None:
        _SERVIDOR["proc"].terminate(); _SERVIDOR["proc"].wait(30)
    binario, gguf = RAIZ / cfg["binario"], RAIZ / cfg["gguf"]
    if not (binario.exists() and gguf.exists()):
        raise FallaModelo(f"IA local no instalada ({binario.name} / {gguf.name})")
    log = open(f"/tmp/llama-{gguf.stem}.log", "w")
    env = {**os.environ, "LD_LIBRARY_PATH": f'{binario.parent}:{os.environ.get("LD_LIBRARY_PATH", "")}'}
    _SERVIDOR["proc"] = subprocess.Popen([str(binario), "-m", str(gguf), "--port", str(cfg["puerto"]), "-c", str(cfg["contexto"]),
                                         "-t", str(os.cpu_count() or 2), "--alias", cfg["modelo"]], stdout=log, stderr=log, env=env)
    _SERVIDOR["gguf"] = cfg["gguf"]; atexit.register(lambda: _SERVIDOR["proc"] and _SERVIDOR["proc"].terminate())
    for _ in range(180):
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                if r.status == 200: return url + "/v1/chat/completions"
        except Exception:
            pass
        if _SERVIDOR["proc"].poll() is not None:
            raise FallaModelo(f"llama-server terminó al cargar {gguf.name}: ver /tmp/llama-{gguf.stem}.log")
        time.sleep(2)
    raise FallaModelo("llama-server no respondió en 6 minutos")


class Modelo:
    """Interfaz: completar(sistema, usuario) → dict (JSON)."""
    def __init__(self, rol, cfg=None, env=os.environ, archivo_uso=None):
        cfg = cfg or config(); self.rol = rol; self.env = env; self.archivo_uso = archivo_uso
        r = cfg["roles"][rol]; self.proveedor = cfg["proveedor"]; self.modelos = r["modelos"]
        self.pausa_429 = cfg.get("pausa_429_s", 35); self.topes = cfg.get("topes_por_modelo", {}); self.pausa_5xx = cfg.get("pausa_5xx_s", 20); self.timeout_gemini = r.get("timeout_s", cfg.get("timeout_gemini_s", 100)); self.razonamiento = r.get("razonamiento"); self.tope = r["tope_diario"]; self.max_tokens = r.get("max_tokens", 3000); self.temperatura = r.get("temperatura", 0.4)
        self.endpoint = cfg.get("endpoint", "https://models.github.ai/inference/chat/completions")
        self.endpoint_gemini = cfg.get("endpoint_gemini", "https://generativelanguage.googleapis.com/v1beta")
        rl = cfg.get("respaldo_local") or {}
        self.local = {**rl[rol], **{k: rl[k] for k in ("binario", "puerto", "contexto") if k in rl}} if env.get("IA_LOCAL") == "1" and rol in rl else None

    def _http(self, modelo, mensajes):
        token = self.env.get("GITHUB_TOKEN") or self.env.get("MODELOS_TOKEN")
        if not token: raise FallaModelo("sin GITHUB_TOKEN con permiso models:read")
        cuerpo = {"model": modelo, "messages": mensajes, "temperature": self.temperatura, "max_tokens": self.max_tokens,
                  "response_format": {"type": "json_object"}}
        req = urllib.request.Request(self.endpoint, data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                crudo = r.read()
            try:
                return json.loads(crudo)
            except ValueError:
                raise FallaModelo(f"{modelo}: respuesta no JSON del proveedor: {crudo[:120]!r}")
        except urllib.error.HTTPError as e:
            txt = e.read()[:300].decode("utf-8", "replace")
            if e.code == 429: raise CuotaAgotada(f"{modelo}: HTTP 429 {txt}")
            if e.code in (400, 404, 422) and "model" in txt.lower(): raise FallaModelo(f"modelo no disponible {modelo}: {txt}")
            raise FallaModelo(f"{modelo}: HTTP {e.code} {txt}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FallaModelo(f"{modelo}: sin conexión ({e})")

    def _http_gemini(self, modelo, sistema, usuario, json_mode=True):
        """API de Gemini (Google AI Studio), nivel gratuito: sin facturación, el exceso de cuota devuelve 429 (no cobra).
        La clave viaja en el encabezado x-goog-api-key, nunca en la URL ni en los registros."""
        clave = self.env.get("GEMINI_API_KEY")
        if not clave: raise FallaModelo("sin GEMINI_API_KEY (secreto del repositorio)")
        gen = {"temperature": self.temperatura, "maxOutputTokens": max(self.max_tokens, 1024) * 3}   # margen para el razonamiento interno
        if json_mode: gen["responseMimeType"] = "application/json"
        if self.razonamiento and modelo.startswith("gemini-3") and not getattr(self, "_sin_razonamiento", False):
            gen["thinkingConfig"] = {"thinkingLevel": self.razonamiento}
        cuerpo = {"systemInstruction": {"parts": [{"text": sistema}]}, "contents": [{"role": "user", "parts": [{"text": usuario}]}],
                  "generationConfig": gen}
        url = f"{self.endpoint_gemini}/models/{modelo}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_gemini) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            txt = e.read()[:400].decode("utf-8", "replace").replace(clave, "***")
            if e.code == 429: raise CuotaAgotada(f"{modelo}: HTTP 429 {txt[:200]}")
            if e.code == 400 and "thinking" in txt.lower() and not getattr(self, "_sin_razonamiento", False):
                self._sin_razonamiento = True                      # el modelo no acepta el nivel de razonamiento
                return self._http_gemini(modelo, sistema, usuario, json_mode)
            if e.code in (500, 502, 503, 504): raise Saturado(f"{modelo}: HTTP {e.code} {txt[:160]}")
            if e.code == 400 and json_mode and ("mime" in txt.lower() or "json" in txt.lower()):
                return self._http_gemini(modelo, sistema, usuario, json_mode=False)    # modelos (p. ej., Gemma) sin modo JSON
            if e.code == 400 and "system" in txt.lower() and "instruction" in txt.lower():
                return self._http_gemini_sin_sistema(modelo, sistema, usuario)
            raise FallaModelo(f"{modelo}: HTTP {e.code} {txt[:200]}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise FallaModelo(f"{modelo}: sin conexión o respuesta ilegible ({type(e).__name__})")
        cands = d.get("candidates") or []
        if not cands: raise FallaModelo(f"{modelo}: sin respuesta (bloqueo: {d.get('promptFeedback')})")
        partes = (cands[0].get("content") or {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        if not texto.strip(): raise FallaModelo(f"{modelo}: respuesta vacía (finishReason={cands[0].get('finishReason')})")
        um = d.get("usageMetadata", {})
        return {"choices": [{"message": {"content": _limpiar_json(texto)}}],
                "usage": {"prompt_tokens": um.get("promptTokenCount"), "completion_tokens": um.get("candidatesTokenCount"),
                          "thinking_tokens": um.get("thoughtsTokenCount")}}

    def _http_gemini_sin_sistema(self, modelo, sistema, usuario):
        return self._http_gemini(modelo, "Sigue las instrucciones.", f"INSTRUCCIONES DEL SISTEMA:\n{sistema}\n\n---\n\n{usuario}", json_mode=False)

    def _http_local(self, mensajes):
        url = servidor_local(self.local)
        cuerpo = {"model": self.local["modelo"], "messages": mensajes, "temperature": self.temperatura, "max_tokens": self.max_tokens,
                  "response_format": {"type": "json_object"}}
        req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=1500) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise FallaModelo(f"IA local: {e}")

    def completar(self, sistema, usuario, simulador=None):
        try:
            return self._completar_remoto(sistema, usuario, simulador)
        except (CuotaAgotada, FallaModelo) as e:
            if not self.local or self.proveedor == "simulado":
                raise
            t0 = time.time()
            r = self._http_local([{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])
            uso = r.get("usage", {})
            _registrar({"rol": self.rol, "proveedor": "local", "modelo": self.local["modelo"], "resultado": "ok", "motivo_respaldo": str(e)[:160],
                        "segundos": round(time.time() - t0, 1), "tokens_entrada": uso.get("prompt_tokens"), "tokens_salida": uso.get("completion_tokens")}, self.archivo_uso)
            self.ultimo_modelo = self.local["modelo"]
            try:
                return json.loads(r["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError):
                raise FallaModelo("IA local: la respuesta no es JSON válido")

    def _completar_remoto(self, sistema, usuario, simulador=None):
        ultimo = None
        for entrada in self.modelos:                        # cadena de respaldo, en orden; «proveedor:modelo» o solo «modelo»
            prov, modelo = (entrada.split(":", 1) if ":" in entrada and entrada.split(":", 1)[0] in PROVEEDORES else (self.proveedor, entrada))
            if self.proveedor == "simulado": prov = "simulado"
            if usos_hoy(modelo, self.archivo_uso, prov) >= min(self.tope, self.topes.get(modelo, self.tope)):
                ultimo = CuotaAgotada(f"tope propio diario alcanzado para {modelo}"); continue
            t0 = time.time()
            for intento in (1, 2):
                try:
                    if prov == "simulado":
                        contenido = simulador(self.rol, sistema, usuario); uso = {}
                    elif prov == "gemini":
                        r = self._http_gemini(modelo, sistema, usuario)
                        contenido = r["choices"][0]["message"]["content"]; uso = r.get("usage", {})
                    else:
                        r = self._http(modelo, [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])
                        contenido = r["choices"][0]["message"]["content"]; uso = r.get("usage", {})
                    break
                except CuotaAgotada as e:                   # 429: límite por minuto; un reintento tras una pausa
                    _registrar({"rol": self.rol, "proveedor": prov, "modelo": modelo, "resultado": "error", "error": str(e)[:200]}, self.archivo_uso)
                    ultimo = e
                    if intento == 1 and prov == "gemini" and "PerDay" not in str(e): time.sleep(self.pausa_429); continue
                    contenido = None; break
                except Saturado as e:                       # 5xx: saturación temporal; un reintento y luego el siguiente modelo
                    _registrar({"rol": self.rol, "proveedor": prov, "modelo": modelo, "resultado": "error", "error": str(e)[:200]}, self.archivo_uso)
                    ultimo = FallaModelo(str(e))
                    if intento == 1: time.sleep(self.pausa_5xx); continue
                    contenido = None; break
                except FallaModelo as e:
                    _registrar({"rol": self.rol, "proveedor": prov, "modelo": modelo, "resultado": "error", "error": str(e)[:200]}, self.archivo_uso)
                    ultimo = e; contenido = None; break
            if contenido is None: continue
            self.ultimo_modelo = modelo
            _registrar({"rol": self.rol, "proveedor": prov, "modelo": modelo, "resultado": "ok", "segundos": round(time.time() - t0, 1),
                        "tokens_entrada": uso.get("prompt_tokens"), "tokens_salida": uso.get("completion_tokens"),
                        "tokens_razonamiento": uso.get("thinking_tokens")}, self.archivo_uso)
            try:
                return json.loads(contenido) if isinstance(contenido, str) else contenido
            except ValueError:
                ultimo = FallaModelo(f"{modelo}: la respuesta no es JSON válido"); continue
        raise ultimo or FallaModelo("sin modelos configurados")
