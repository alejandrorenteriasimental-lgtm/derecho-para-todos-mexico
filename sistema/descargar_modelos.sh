#!/usr/bin/env bash
# Descarga los modelos de voz si faltan. Fuentes: GitHub Releases (accesibles desde Actions y desde el entorno de trabajo).
# Verifica tamaño mínimo para no aceptar páginas de error como si fueran modelos.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models/piper models/ocr
bajar() {  # url destino tamaño_minimo_bytes
  if [ ! -s "$2" ] || [ "$(stat -c %s "$2")" -lt "$3" ]; then
    curl -fsSL --retry 3 -o "$2.tmp" "$1"
    [ "$(stat -c %s "$2.tmp")" -ge "$3" ] || { echo "Descarga incompleta: $1"; rm -f "$2.tmp"; exit 1; }
    mv "$2.tmp" "$2"
  fi
}
bajar https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx models/kokoro-v1.0.int8.onnx 80000000
bajar https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin models/voices-v1.0.bin 20000000
if [ ! -d models/piper/vits-piper-es_MX-claude-high ]; then   # voz alterna (respaldo rápido)
  curl -fsSL --retry 3 https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_MX-claude-high.tar.bz2 | tar -xj -C models/piper
fi
# OCR en español para la auditoría de imágenes: se usa el del sistema (apt tesseract-ocr-spa) o se descarga
if ! tesseract --list-langs 2>/dev/null | grep -qx spa; then
  bajar https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/spa.traineddata models/ocr/spa.traineddata 1000000
  for f in /usr/share/tesseract-ocr/*/tessdata/osd.traineddata; do [ -f "$f" ] && cp "$f" models/ocr/ || true; done
fi
echo "Modelos listos:"; du -sh models/* | sort -h
