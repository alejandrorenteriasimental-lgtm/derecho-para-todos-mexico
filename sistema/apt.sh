#!/usr/bin/env bash
# Dependencias del sistema para CI, resistentes a espejos lentos de Ubuntu (26-10-2026: el espejo de Azure tardó >10 min
# en bajar 57 MB y la instalación de ffmpeg por apt agotó el tiempo dos veces).
#  · ffmpeg: compilación estática de BtbN/FFmpeg-Builds desde GitHub Releases (rápido; se guarda en caché).
#  · tesseract + español: apt (≈15 paquetes pequeños), con tiempos límite y cambio de espejo si el de Azure falla.
set -uo pipefail
FF="$HOME/ffmpeg-static"
if [ ! -x "$FF/bin/ffmpeg" ]; then
  echo "descargando ffmpeg estático"; date -u +%T
  mkdir -p "$FF" && curl -fL --retry 3 -sS -m 240 https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
    | tar -xJ -C "$FF" --strip-components=1 || { echo "falló la descarga de ffmpeg"; exit 1; }
fi
echo "$FF/bin" >> "${GITHUB_PATH:-/dev/null}"; export PATH="$FF/bin:$PATH"; ffmpeg -version | head -1
command -v tesseract >/dev/null && tesseract --list-langs 2>&1 | grep -q '^spa$' && { echo "tesseract spa ya instalado"; exit 0; }
OPC=(-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o DPkg::Lock::Timeout=60)
instalar() {
  timeout 150 sudo apt-get "${OPC[@]}" update -q && \
  timeout 240 sudo DEBIAN_FRONTEND=noninteractive apt-get "${OPC[@]}" install -y -q --no-install-recommends tesseract-ocr tesseract-ocr-spa
}
# 12-11-2026: el cambio de espejo borraba /etc/apt/apt-mirrors.txt, pero en ubuntu-latest (26.04) las fuentes apuntan a
# «mirror+file:/etc/apt/apt-mirrors.txt»; sin el archivo, apt quedaba sin repositorios (ciclo 43053554282 falló así).
# Ahora el archivo se reescribe con el espejo principal y las fuentes «mirror+file:» se reemplazan por él.
ESPEJO="http://archive.ubuntu.com/ubuntu/"
cambiar_espejo() {
  echo "cambiando de espejo a $ESPEJO"
  echo "$ESPEJO" | sudo tee /etc/apt/apt-mirrors.txt >/dev/null
  sudo sed -i -E "s#mirror\+file:/etc/apt/apt-mirrors\.txt/?#${ESPEJO}#g; s#https?://[a-z.]*archive\.ubuntu\.com/ubuntu/?#${ESPEJO}#g" \
    /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list 2>/dev/null || true
}
for i in 1 2 3; do
  echo "intento $i (tesseract)"; date -u +%T
  if instalar; then tesseract --list-langs 2>&1 | grep -q '^spa$' && { echo "tesseract spa OK"; exit 0; }; fi
  cambiar_espejo; sleep 5
done
echo "No se pudo instalar tesseract tras 3 intentos"; exit 1
