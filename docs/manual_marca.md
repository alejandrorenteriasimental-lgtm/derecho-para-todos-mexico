# Manual de marca — Derecho para Todos México (v1.0, 25-10-2026)

**Idea de marca:** «El Derecho, explicado en voz clara.» Un medio editorial cercano y riguroso, no un despacho.
Fuente única de verdad para colores y tipografías: `marca/tokens.json`. Los activos se regeneran con `python sistema/marca.py`.

## Nombre
Se conserva **Derecho para Todos México**: dice lo que es y para quién, se entiende a la primera y no suena a despacho.
Riesgos: es una frase genérica (hay páginas y organizaciones con nombres parecidos) y su registro como marca ante el
IMPI no está verificado. Antes del lanzamiento se debe buscar en MARCia (IMPI) en las clases 41 (educación y
entretenimiento) y 38 (difusión), y confirmar que los nombres de usuario `@derechoparatodosmx` estén libres en
Facebook, Instagram, YouTube y TikTok. Si existe un registro previo en esas clases, la alternativa preparada es
**«En Claro: Derecho para Todos»**, que conserva el lema y el símbolo.

## Símbolo y logotipo
- **Símbolo:** una burbuja de diálogo con el signo de sección «§». Burbuja = explicación y conversación; § = norma.
  Evita a propósito balanzas, mazos, columnas y laureles, que son el lenguaje visual de los despachos.
- **Versiones:** horizontal claro y oscuro, símbolo solo, inverso (§ azul noche sobre cempasúchil), avatar de perfil.
- **Área de protección:** la altura de la cola de la burbuja alrededor del símbolo. Tamaño mínimo: 24 px de alto.
- **No:** girar, cambiar colores, poner sombras ni contornos, o usar el símbolo sobre fotos muy contrastadas sin la placa.

## Color
| Token | Hex | Uso |
|---|---|---|
| noche | #0B1626 | Fondo del Reel, texto principal sobre papel, placa del símbolo |
| noche_2 | #152942 | Degradado del fondo |
| cempasúchil | #F2B544 | Acento: palabra activa del subtítulo, barras, etiquetas. **Nunca como texto sobre papel** (contraste 1.7:1) |
| papel | #F6F1E6 | Fondo de la imagen fija y de las tarjetas de cita |
| coral / coral_texto | #E5645A / #AA2C24 | Excepciones y alertas (el tono _texto es el único válido para letras sobre papel) |
| jade / jade_texto | #5BC08A / #1E6E46 | Realidad, aciertos |
| bruma / tinta_suave | #9FB0C3 / #525E6E | Textos secundarios |
Todo texto debe cumplir contraste WCAG AA de 4.5:1 o más; la auditoría de imagen lo comprueba en cada pieza.

## Tipografía (todas con licencia SIL OFL, uso comercial libre)
- **Inter Display Black / ExtraBold:** titulares y subtítulos del Reel.
- **Inter Semibold / Medium / Regular:** etiquetas, fuentes y textos de apoyo.
- **Lora Italic:** citas textuales de la ley (siempre entre comillas angulares «»).
Mínimos en pantalla de 1080 px: cuerpo 32 px, notas legales 24 px.

## Reel (1080×1920, 30 fps) — sistema aprobado en T073
Fondo noche con degradado y líneas diagonales tenues; seis tipos de escena (gancho, titular, cita, lista,
excepción, cierre); barra de progreso cempasúchil; firma «DERECHO PARA TODOS» arriba a la izquierda y la etiqueta
«Voz generada con IA» arriba a la derecha; fuente de cada afirmación visible sobre el subtítulo.
**Subtítulos:** Inter ExtraBold 66 px, máximo 24–30 caracteres por bloque, sobre placa noche al 78 %, la palabra
que se está diciendo en cempasúchil; sincronizados por oración con la voz (desfase auditado ≤ 150 ms).

## Imagen editorial (1080×1350, 4:5)
Papel con grano sutil; cabecera con nombre y número de serie; etiqueta de sección en cempasúchil; titular Inter
Display Black; bajada en Lora; una sola idea central (≤ 60 palabras); pie con fuente, aviso legal y símbolo.
Plantillas: concepto, tres claves, mito o realidad, diferencia, dato.

## Voz e identidad sonora
- **Voz oficial:** Kokoro «em_santa» con fonética latinoamericana (es-419), velocidad 0.95, masterizada a −16 LUFS.
- **Mezcla del Reel:** −14 LUFS integrados, pico ≤ −1.5 dBTP; la música baja automáticamente cuando habla la voz.
- **Firma sonora:** 1.6 s (La → Mi y acorde abierto de Do mayor), al final de cada Reel, sobre la tarjeta de cierre.

## Tono editorial
Cercano, claro y exacto. Se tutea al público. Se explican las palabras técnicas la primera vez. Nunca se asegura
un resultado («te garantizo»), nunca se aconseja un caso concreto («en tu caso»), nunca se llama culpable a nadie.
Toda pieza termina con: «Esto es información general, no asesoría legal.»

## Activos de plataforma (en `marca/png/`)
Perfil 1080×1080 (se ve bien en círculo) · Portada de Facebook 1640×624 (contenido dentro de la franja central
segura) · Banner de YouTube 2560×1440 (zona segura 1546×423).
