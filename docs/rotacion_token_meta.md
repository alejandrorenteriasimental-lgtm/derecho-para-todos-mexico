# Rotación del token de Meta (preparada el 3-11-2026)

**Por qué.** El token de página se vio en una captura del chat. Un token nuevo NO invalida el anterior: para dejar inservible el expuesto hay que revocarlo (cambio de contraseña de Facebook o retiro de permisos de la app).

**Qué no se interrumpe.** Las publicaciones ya programadas en Facebook viven en los servidores de Meta y salen aunque el token cambie. Lo único que se detendría es la programación de piezas NUEVAS si el sistema corre con un token inválido (error 190 → paro de emergencia automático). Por eso se hace todo en una sola sentada, lejos de las ejecuciones de las 09:03 y 19:03 CDMX (ventana segura: 10:00–18:30).

## Pasos (los hace el responsable; ~10 min)
1. **Revocar el token expuesto:** Facebook → Configuración y privacidad → Configuración → Centro de cuentas → Contraseña y seguridad → Cambiar contraseña (marcar «cerrar sesión en otros dispositivos»).
2. **Token nuevo de usuario:** https://developers.facebook.com/tools/explorer → App «Aquí Dice la Ley Lectura» → «Generate Access Token» con: pages_show_list, pages_read_engagement, pages_manage_posts, read_insights, instagram_basic, instagram_content_publish. Aceptar solo para la Página «Aquí Dice la Ley» y @aquidicelaley.
3. **Hacerlo de larga duración:** https://developers.facebook.com/tools/debug/accesstoken → pegar el token → «Extend Access Token» → copiar el nuevo.
4. **Token de página (no caduca):** de vuelta en el Explorer, con el token largo, consultar `me/accounts` y copiar el `access_token` de la Página 1359758353893509.
5. **Guardarlo:** GitHub → repositorio → Settings → Secrets and variables → Actions → META_PAGE_TOKEN → Update → pegar → Save. No pegarlo en el chat.
6. Avisar «listo» a Claude: corre `meta-prueba` en modo lectura (no publica nada) y confirma que lee la Página, que Instagram sigue vinculado y que las publicaciones programadas siguen ahí.
