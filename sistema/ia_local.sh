#!/usr/bin/env bash
# IA local y gratuita para la redacción y la auditoría (respaldo cuando GitHub Models no responde).
# llama.cpp (MIT) desde sus GitHub Releases + modelos GGUF de código abierto desde Hugging Face:
#   redactor/investigador: Qwen2.5-7B-Instruct Q4_K_M (Apache-2.0) → puerto 8080
#   auditor (otra familia): Phi-3.5-mini-instruct Q4_K_M (MIT)      → puerto 8081
# Corre en la CPU del runner; no hay cuentas, llaves ni cargos. Uso: bash sistema/ia_local.sh [iniciar|descargar]
set -euo pipefail
cd "$(dirname "$0")/.."
D=models/ia; mkdir -p "$D"
bajar() { [ -s "$2" ] && [ "$(stat -c %s "$2")" -ge "$3" ] && return 0
  curl -fL --retry 3 -sS -o "$2.tmp" "$1"; [ "$(stat -c %s "$2.tmp")" -ge "$3" ] || { echo "descarga incompleta: $1"; exit 1; }; mv "$2.tmp" "$2"; }
if [ ! -x "$D/bin/llama-server" ]; then
  URL=$(curl -fsSL ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15" | python3 -c "
import json,sys
a=[x['browser_download_url'] for r in json.load(sys.stdin) for x in r['assets']]   # la «latest» a veces solo trae una etiqueta
malos=('vulkan','cuda','sycl','rocm','hip','opencl','arm64','aarch64','s390x','musa','kompute')
c=[u for u in a if 'ubuntu' in u.lower() and 'x64' in u.lower() and not any(m in u.lower() for m in malos) and (u.endswith('.zip') or u.endswith('.tar.gz'))]
if not c:
    sys.stderr.write('Activos disponibles:\n' + '\n'.join(a) + '\n'); sys.exit(1)
print(c[0])")
  rm -rf /tmp/llama && mkdir -p /tmp/llama
  case "$URL" in
    *.zip) curl -fsSL -o /tmp/llama.zip "$URL" && unzip -q /tmp/llama.zip -d /tmp/llama ;;
    *.tar.gz) curl -fsSL "$URL" | tar -xz -C /tmp/llama ;;
  esac
  mkdir -p "$D/bin"; cp -r "$(dirname "$(find /tmp/llama -name llama-server -type f | head -1)")"/* "$D/bin/"; chmod +x "$D/bin/"* || true
  echo "$URL" > "$D/bin/ORIGEN"
fi
bajar https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf "$D/qwen2.5-7b-instruct-q4_k_m.gguf" 4000000000
bajar https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf "$D/phi-3.5-mini-instruct-q4_k_m.gguf" 2000000000
[ "${1:-iniciar}" = "descargar" ] && exit 0
export LD_LIBRARY_PATH="$PWD/$D/bin:${LD_LIBRARY_PATH:-}"
HILOS=$(nproc)
nohup "$D/bin/llama-server" -m "$D/qwen2.5-7b-instruct-q4_k_m.gguf" --port 8080 -c 8192 -t "$HILOS" --alias local-redactor > /tmp/llama-8080.log 2>&1 &
nohup "$D/bin/llama-server" -m "$D/phi-3.5-mini-instruct-q4_k_m.gguf" --port 8081 -c 8192 -t "$HILOS" --alias local-auditor > /tmp/llama-8081.log 2>&1 &
for p in 8080 8081; do
  for i in $(seq 1 120); do curl -fs "http://127.0.0.1:$p/health" >/dev/null 2>&1 && break; sleep 2; done
  curl -fs "http://127.0.0.1:$p/health" >/dev/null || { echo "el servidor $p no arrancó"; tail -20 /tmp/llama-$p.log; exit 1; }
done
echo "IA local lista (8080 redactor, 8081 auditor)"
