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


class CuotaAgotada(Exception): pass
class FallaModelo(Exception): pass


def config():
    return json.loads(CONFIG.read_text())


def usos_hoy(modelo, archivo=None, proveedor=None):
    """Solicitudes de hoy (UTC, como GitHub) a ese modelo y proveedor; las simuladas no consumen la cuota real."""
    f = Path(archivo or USO); hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not f.exists(): return 0
    return sum(1 for l in f.read_text().splitlines() if l.strip() and (e := json.loads(l))["modelo"] == modelo
               and e["ts"].startswith(hoy) and e.get("proveedor", "github_models") == (proveedor or "github_models"))


def _registrar(ev, archivo=None):
    f = Path(archivo or USO); f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a") as h: h.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **ev}, ensure_ascii=False) + "\n")


class Modelo:
    """Interfaz: completar(sistema, usuario) → dict (JSON)."""
    def __init__(self, rol, cfg=None, env=os.environ, archivo_uso=None):
        cfg = cfg or config(); self.rol = rol; self.env = env; self.archivo_uso = archivo_uso
        r = cfg["roles"][rol]; self.proveedor = cfg["proveedor"]; self.modelos = r["modelos"]
        self.tope = r["tope_diario"]; self.max_tokens = r.get("max_tokens", 3000); self.temperatura = r.get("temperatura", 0.4)
        self.endpoint = cfg.get("endpoint", "https://models.github.ai/inference/chat/completions")

    def _http(self, modelo, mensajes):
        token = self.env.get("GITHUB_TOKEN") or self.env.get("MODELOS_TOKEN")
        if not token: raise FallaModelo("sin GITHUB_TOKEN con permiso models:read")
        cuerpo = {"model": modelo, "messages": mensajes, "temperature": self.temperatura, "max_tokens": self.max_tokens,
                  "response_format": {"type": "json_object"}}
        req = urllib.request.Request(self.endpoint, data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            txt = e.read()[:300].decode("utf-8", "replace")
            if e.code == 429: raise CuotaAgotada(f"{modelo}: HTTP 429 {txt}")
            if e.code in (400, 404, 422) and "model" in txt.lower(): raise FallaModelo(f"modelo no disponible {modelo}: {txt}")
            raise FallaModelo(f"{modelo}: HTTP {e.code} {txt}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FallaModelo(f"{modelo}: sin conexión ({e})")

    def completar(self, sistema, usuario, simulador=None):
        ultimo = None
        for modelo in self.modelos:                         # cadena de respaldo, en orden
            if usos_hoy(modelo, self.archivo_uso, self.proveedor) >= self.tope:
                ultimo = CuotaAgotada(f"tope propio diario alcanzado para {modelo}"); continue
            t0 = time.time()
            try:
                if self.proveedor == "simulado":
                    contenido = simulador(self.rol, sistema, usuario); uso = {}
                else:
                    r = self._http(modelo, [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])
                    contenido = r["choices"][0]["message"]["content"]; uso = r.get("usage", {})
            except (CuotaAgotada, FallaModelo) as e:
                _registrar({"rol": self.rol, "proveedor": self.proveedor, "modelo": modelo, "resultado": "error", "error": str(e)[:200]}, self.archivo_uso)
                ultimo = e; continue
            _registrar({"rol": self.rol, "proveedor": self.proveedor, "modelo": modelo, "resultado": "ok", "segundos": round(time.time() - t0, 1),
                        "tokens_entrada": uso.get("prompt_tokens"), "tokens_salida": uso.get("completion_tokens")}, self.archivo_uso)
            try:
                return json.loads(contenido) if isinstance(contenido, str) else contenido
            except ValueError:
                ultimo = FallaModelo(f"{modelo}: la respuesta no es JSON válido"); continue
        raise ultimo or FallaModelo("sin modelos configurados")
