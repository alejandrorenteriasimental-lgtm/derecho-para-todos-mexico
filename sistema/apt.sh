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
for i in 1 2 3; do
  echo "intento $i (tesseract)"; date -u +%T
  if instalar; then tesseract --list-langs 2>&1 | grep -q '^spa$' && { echo "tesseract spa OK"; exit 0; }; fi
  echo "cambiando de espejo"; sudo sed -i -E 's#https?://[a-z.]*archive\.ubuntu\.com#http://archive.ubuntu.com#g; s#http://azure\.archive\.ubuntu\.com#http://archive.ubuntu.com#g' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null
  sudo rm -f /etc/apt/apt-mirrors.txt 2>/dev/null; sleep 5
done
echo "No se pudo instalar tesseract tras 3 intentos"; exit 1
