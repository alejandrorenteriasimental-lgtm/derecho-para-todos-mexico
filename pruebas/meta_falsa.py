"""Simulador en memoria de la Graph API de Meta (Reels y fotos de Página) con inyección de fallas.
Reproduce el comportamiento documentado: start → upload (rupload) → finish → status. Permite provocar
caídas de red antes o DESPUÉS de que Meta aplique la operación (el caso que genera duplicados)."""
import json, re
from urllib.parse import urlparse, parse_qs
import publicar


class MetaFalsa:
    def __init__(self, page="PAGE1", token="TOKEN-SECRETO", upload_host="https://rupload.facebook.com"):
        self.page, self.token, self.upload_host = page, token, upload_host
        self.videos, self.fotos, self.llamadas, self.fallas = {}, [], [], {}
        self.n = 0; self.paginar_cada = 50

    # fallas: clave → lista de efectos que se consumen en orden: "red_antes", "red_despues", "500", "html", "vacio",
    #         "token", "limite", "sin_exito", "expirada"
    def fallar(self, clave, *efectos): self.fallas.setdefault(clave, []).extend(efectos)

    def _efecto(self, clave):
        lst = self.fallas.get(clave) or []
        return lst.pop(0) if lst else None

    def _resp(self, d, estado=200): return estado, json.dumps(d).encode()
    def _err(self, estado, codigo, msg): return estado, json.dumps({"error": {"code": codigo, "message": msg}}).encode()

    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        cab = cab or {}; self.llamadas.append((metodo, url))
        if cab.get("Authorization") != f"OAuth {self.token}":
            return self._err(401, 190, "Invalid OAuth access token")
        u = urlparse(url); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        campos = {}
        if datos and cab.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            campos = {k: v[0] for k, v in parse_qs(datos.decode()).items()}
        fase = campos.get("upload_phase")
        clave = fase or ("upload" if "rupload" in url else ("photos" if url.endswith("/photos") else "get"))
        ef = self._efecto(clave)
        if ef == "red_antes": raise publicar.SinRed("conexión reiniciada (simulada)")
        if ef == "token": return self._err(400, 190, "Error validating access token")
        if ef == "limite": return self._err(400, 4, "Application request limit reached")
        if ef == "500": return 500, b'{"error":{"code":2,"message":"Service temporarily unavailable"}}'
        if ef == "html": return 502, b"<html>Bad Gateway</html>"
        res = self._aplicar(metodo, u, q, campos, cab, datos, clave)
        if ef == "red_despues": raise publicar.SinRed("tiempo de espera agotado tras enviar (simulado)")
        if ef == "vacio": return 200, b"{}"
        if ef == "sin_exito": return self._resp({"success": False})
        return res

    def _aplicar(self, metodo, u, q, campos, cab, datos, clave):
        ruta = u.path.split("/", 2)[-1] if u.netloc == "graph.facebook.com" else u.path
        if clave == "start":
            self.n += 1; vid = f"V{self.n}"
            self.videos[vid] = {"bytes": 0, "total": None, "estado": "nuevo", "descripcion": None, "expirada": False}
            return self._resp({"video_id": vid, "upload_url": f"{self.upload_host}/video-upload/v26.0/{vid}?sesion=x"})
        if clave == "upload":
            vid = re.search(r"/(V\d+)", u.path).group(1); v = self.videos[vid]
            off = int(cab.get("offset", 0)); total = int(cab["file_size"])
            if off != v["bytes"]: return self._err(400, 100, "offset incorrecto")
            v["bytes"] = off + len(datos); v["total"] = total
            return self._resp({"success": True})
        if clave == "finish":
            v = self.videos.get(campos["video_id"])
            if not v or v["bytes"] != v["total"]: return self._err(400, 100, "upload incompleto")
            v["descripcion"] = campos.get("description")
            v["estado"] = "scheduled" if campos.get("video_state") == "SCHEDULED" else "published"
            return self._resp({"success": True})
        if clave == "photos":
            msg = re.search(rb'name="message"\r\n\r\n(.*?)\r\n--', datos, re.S).group(1).decode()
            prog = b'name="scheduled_publish_time"' in datos
            self.n += 1; pid = f"P{self.n}"
            self.fotos.append({"id": pid, "message": msg, "programada": prog})
            return self._resp({"id": f"F{self.n}", "post_id": pid})
        # GET
        if ruta.endswith("/video_reels"):
            pub = [{"id": k, "description": v["descripcion"]} for k, v in self.videos.items() if v["estado"] == "published"]
            ini = int(q.get("after", 0)); pag = pub[ini: ini + self.paginar_cada]
            d = {"data": pag}
            if ini + self.paginar_cada < len(pub):
                d["paging"] = {"next": f"https://graph.facebook.com/v26.0/{self.page}/video_reels?fields=id,description&after={ini + self.paginar_cada}"}
            return self._resp(d)
        if ruta.endswith("/scheduled_posts"):
            return self._resp({"data": [{"id": f["id"], "message": f["message"]} for f in self.fotos if f["programada"]]})
        if ruta.endswith("/posts"):
            return self._resp({"data": [{"id": f["id"], "message": f["message"]} for f in self.fotos if not f["programada"]]})
        m = re.search(r"(V\d+)$", ruta)
        if m:
            v = self.videos.get(m.group(1))
            if not v or v["expirada"]: return self._err(404, 100, "Unsupported get request")
            fase_sub = "complete" if v["total"] and v["bytes"] == v["total"] else ("in_progress" if v["bytes"] else "not_started")
            pubst = {"published": "published", "scheduled": "scheduled"}.get(v["estado"], "not_published")
            return self._resp({"status": {"video_status": "ready" if fase_sub == "complete" else "upload_in_progress",
                                          "uploading_phase": {"status": fase_sub, "bytes_transferred": v["bytes"]},
                                          "publishing_phase": {"status": "complete" if pubst != "not_published" else "not_started", "publish_status": pubst}}})
        return self._err(400, 100, f"ruta no simulada: {ruta}")

    # utilidades de aserción
    def publicaciones_visibles(self):
        return [k for k, v in self.videos.items() if v["estado"] in ("published", "scheduled")] + [f["id"] for f in self.fotos]

    def llamadas_a(self, fase):
        return sum(1 for m, u in self.llamadas if fase in u)
