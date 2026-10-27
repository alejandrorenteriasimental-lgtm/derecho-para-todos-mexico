# Preparación de la publicación en Meta (sin activar)

Estado al 27-10-2026: **preparado, no activado.** La publicación sigue apagada: `PUBLICAR=0` y `LANZAMIENTO_AUTORIZADO` vacío. No se ha solicitado ningún permiso de publicación.

## Lo que ya existe
- App «Aquí Dice la Ley Lectura» (ID 1813774219932627), en modo desarrollo. Tiene solo permisos de lectura: `pages_show_list`, `pages_read_engagement`, `read_insights` e `instagram_basic`.
- Página de Facebook: Graph ID 1359758353893509. Instagram profesional @aquidicelaley: ID 17841456017575703.
- `sistema/publicar.py`:
  - Reel: carga en tres fases con `video_state=SCHEDULED`.
  - Imagen: `published=false` con `scheduled_publish_time`.
  - Usa una marca idempotente, un libro de operaciones y una verificación posterior.
  - Solo se ha probado en simulación (`pruebas/test_publicacion.py`, con una Meta falsa).
- Seguro de doble llave: no se publica nada si falta `PUBLICAR=1` o `LANZAMIENTO_AUTORIZADO=SI`. Además, la pieza necesita aprobación humana de la versión exacta.

## Lo que falta. Requiere autorización expresa del responsable
1. **Permisos para el modo desarrollo.** Agregar `pages_manage_posts` y, si se publicará en Instagram, `instagram_content_publish`. Como la app está en modo desarrollo y el responsable es su administrador, Meta no exige revisión de la app para usarlos con su propia página.
2. **Token de página de larga duración:**
   - Se genera desde el explorador de Graph API o desde el flujo OAuth de la app.
   - Se guarda únicamente como secreto del repositorio: `META_PAGE_TOKEN` y `META_PAGE_ID`.
   - Nunca se escribe en el chat ni en archivos.
3. **Prueba segura** (`meta-prueba.yml`, manual, una sola vez):
   - Lectura de la página.
   - Una publicación de imagen **no publicada** (`published=false`, sin fecha). Este tipo de publicación no la ve el público.
   - Comprobación de que existe y borrado inmediato.
   - Si la prueba falla, se registra el error exacto y no se repite.
4. Activación. Solo la decide el responsable: `PUBLICAR=1` y `LANZAMIENTO_AUTORIZADO=SI`.

## Momento recomendado
Cuando haya al menos 4 Reels y 4 imágenes aprobados, y a más tardar el 13-11-2026, para llegar al 23-11 con la ruta probada.
