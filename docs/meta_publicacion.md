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

## Reels en Instagram: en espera (IG_REELS=0) — 29-10-2026

**Estado.** Las imágenes se publican en Instagram a su hora. Los Reels se publican **solo en Facebook**. En Instagram quedan como `REEL_IG_EN_ESPERA`, sin intentarse, y eso no detiene nada más. La autorización registrada en `data/lanzamiento.json` deja `IG_REELS` en `"0"`.

**Falla, reproducida el 28-10 y el 29-10.** Al cargar el Reel completo por la API de Instagram con carga reanudable, la última parte se rechaza con `400 Request processing failed`. El respaldo con `video_url`, que usa el video alojado como no publicado en la página, termina con el error de Meta **2207076**. Meta no documenta ese código.

**Lo que se descartó en las pruebas no públicas:**

| Hipótesis | Prueba | Resultado |
|---|---|---|
| Especificación del archivo | Audio AAC a 128 kbps, sin listas de edición, proporción de píxel 1:1, *faststart*, H.264 High, 30 fps, 1080×1920 | Falla igual |
| Codificación | Reel completo recodificado | Falla |
| Tamaño | Clip sintético de 10 s y 3,8 MB | Pasa |
| Duración | Clip sintético de 30 s | Pasa |
| Recorte del Reel aprobado | Primeros 5 y 15 s | Pasan |
| Recorte del Reel aprobado | Primeros 30 s | Falla |
| Forma de enviar la carga | Un solo envío y partes de 1 MB | Fallan ambas |

**Hipótesis abierta.** Algo del contenido completo, o una restricción no documentada de la cuenta o de la app, que aún no se ha revisado. Hay reportes recientes de otros desarrolladores con el mismo 2207076 atribuidos a fallas de Meta (Make Community).

**Límite anti-spam.** Por las pruebas del 28-10, Meta aplicó un límite temporal (código 368, subcódigo 1390008). **No repetir pruebas de carga en serie.**

**Siguiente paso posible.** Requiere decisión del responsable; no se hace por cuenta propia.

1. Subir **un** Reel a mano desde la app de Instagram, para comprobar si la cuenta acepta ese archivo. Si la app lo acepta, la falla es de la API.
2. Revisar el estado de la app en Meta for Developers (modo de desarrollo o publicada) y las alertas del portafolio.
3. Mientras tanto, publicar los Reels en Instagram a mano con el archivo aprobado. Están en el respaldo `piezas-2026-10`, con su SHA-256.

### Diagnóstico por variantes (no público)

Las cargas se registran en `registro/diagnostico_ig.jsonl`.

| Fecha | Variante | Resultado | Qué indica |
|---|---|---|---|
| 30-10 | `recorte:22`: primeros 22 s del Reel R20261123-T031, sin recodificar | Pasa | El límite está entre 22 y 30 s |
| 31-10 | `silencio`: video completo con audio silencioso | Falla, en la última parte de la carga | La causa está en la pista de video, no en el audio |
| 31-10 | `recorte:26` | Pasa | El límite está entre 26 y 30 s |

Siguiente paso (máximo 2 cargas no públicas al día; 31-10 ya tiene 2): bisecar con `recorte:28`.
