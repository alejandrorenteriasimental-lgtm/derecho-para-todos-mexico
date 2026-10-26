#!/usr/bin/env bash
# Instala ffmpeg y tesseract (español) con tiempos límite y reintentos: el 26-10-2026 un «apt-get update» se quedó
# colgado 15 min sin salida en el runner. Muestra el progreso para que un bloqueo sea visible en el registro.
set -uo pipefail
OPC=(-o Acquire::Retries=3 -o Acquire::http::Timeout=25 -o Acquire::https::Timeout=25 -o DPkg::Lock::Timeout=60)
for i in 1 2 3; do
  echo "intento $i: apt-get update"; date -u +%T
  if timeout 180 sudo apt-get "${OPC[@]}" update -q; then
    echo "apt-get install"; date -u +%T
    if timeout 300 sudo DEBIAN_FRONTEND=noninteractive apt-get "${OPC[@]}" install -y -q --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-spa; then
      ffmpeg -version | head -1; tesseract --list-langs 2>&1 | grep -q spa && echo "tesseract spa OK"; exit 0
    fi
  fi
  echo "falló el intento $i; reintento en 15 s"; sleep 15
done
echo "No se pudieron instalar ffmpeg/tesseract tras 3 intentos"; exit 1
