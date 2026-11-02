# Integraciones de publicación (revisado el 25-10-2026)

| Plataforma | ¿Publicación automática oficial? | Requisitos | Limitaciones clave | Estado en el sistema |
|---|---|---|---|---|
| **Facebook (Página)** | Sí: Reels Publishing API (`/video_reels`) y fotos (`/photos`) | Página de Facebook; app de Meta en modo desarrollo con el responsable como administrador; permisos `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`; token de Página guardado como secreto | 30 Reels por 24 h por Página; programación de 10 min a 29 días; las métricas *impressions* se retiraron en 2025 (usar `post_media_view`) | **Implementado y probado contra simulador** (`publicar.py`): libro de operaciones, recuperación y estados. Falta conexión real |
| **Instagram** | Sí: Content Publishing API | Cuenta profesional vinculada a la Página; `instagram_basic`, `instagram_content_publish` (+ `pages_read_engagement`) | 100 publicaciones API por 24 h (la propia documentación también menciona 50 en carruseles; se consulta `content_publishing_limit`); **imágenes solo JPEG y en URL pública**; Reels por URL pública o carga reanudable (solo con Facebook Login for Business) | Diseñado: Reel por carga reanudable con el mismo token; imagen JPEG publicada primero como foto no visible en la Página para obtener una URL pública temporal. Se valida al conectar |
| **YouTube (Shorts)** | Sí: `videos.insert` | Canal de YouTube; proyecto de Google Cloud **sin facturación**; OAuth del responsable una vez (token de actualización como secreto) | La documentación vigente dice que los videos de proyectos no verificados **ya no quedan forzados a privado**; cuota de carga: 100 llamadas al día | **Implementado el 2-11-2026** (`sistema/youtube.py`, con pruebas): programa cada Reel aprobado con `publishAt` a la hora de Facebook. Autorizado por el responsable (`data/lanzamiento.json`: `YOUTUBE=1`). En simulación hasta que existan los secretos `YT_CLIENT_ID`, `YT_CLIENT_SECRET` y `YT_REFRESH_TOKEN` |
| **TikTok** | Solo con auditoría | App en TikTok for Developers + auditoría de cumplimiento | Sin auditoría, todo lo publicado por API queda **privado**; las cuentas de organización no acceden a Creator Rewards | No automatizable de forma útil sin auditoría; alternativa: carga manual semanal desde los MP4 producidos |

## Lo que solo puede hacer el responsable (cuando se autorice el lanzamiento)
1. Crear la Página de Facebook de la marca (y la cuenta profesional de Instagram vinculada).
2. Iniciar sesión una vez para conceder los permisos a la app de Meta (y, después, a la de Google para YouTube).
Todo lo demás (crear la app en modo desarrollo, guardar los tokens como secretos cifrados del repositorio,
programar y medir) lo hace el sistema. Mientras `PUBLICAR` no sea `1` y `LANZAMIENTO_AUTORIZADO` no sea `SI`,
no se hace ninguna llamada de publicación.

Fuentes: [Instagram Content Publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing) ·
[YouTube videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert) ·
[TikTok Content Posting API](https://developers.tiktok.com/docs/en/content-posting-api-get-started) ·
[Meta: métricas retiradas](https://developers.facebook.com/documentation/pages-api/platforminsights/page/deprecated-metrics)


## YouTube: conexión (una sola vez, la hace el responsable) — 2-11-2026

Claude no ve ni escribe las credenciales; viven solo en los secretos de GitHub.

1. Google Cloud Console, proyecto existente «derecho-para-todo» (sin facturación): activar **YouTube Data API v3**.
2. Pantalla de consentimiento de OAuth: tipo Externo; publicar la app en **Producción** (en «Prueba» el token de actualización caduca a los 7 días). Google mostrará el aviso de app no verificada; es normal para uso propio.
3. Credenciales → ID de cliente de OAuth → Aplicación web; URI de redirección autorizada: `https://developers.google.com/oauthplayground`.
4. OAuth 2.0 Playground → engrane → «Use your own OAuth credentials» (ID y secreto del paso 3). Alcance: `https://www.googleapis.com/auth/youtube.upload`. Autorizar eligiendo el canal **Aquí Dice la Ley** (cuenta de marca) y canjear el código por tokens.
5. GitHub → Settings → Secrets and variables → Actions → New repository secret: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

Al día siguiente el publicador programa en YouTube los Reels aprobados que estén dentro de la ventana de 28 días; `registro/publicacion.jsonl` muestra `"youtube": "PROGRAMADO"` por pieza.
