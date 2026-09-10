#!/bin/bash
# 分块下载 big-lama.pt（TorchScript），自动检测本地代理并续传
# 用法: bash download_model.sh
set -e
cd "$(dirname "$0")"
mkdir -p models
URL="https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
OUT="models/big-lama.pt"
TOTAL=205803670
CHUNK=$((15 * 1024 * 1024))   # 15MB/块

# 自动检测本地代理（Clash 7897 / V2Ray 1087 / SS 1080）
PROXY_ARG=()
for p in 7897 7890 1087 1080; do
  if nc -z -w1 127.0.0.1 "$p" 2>/dev/null; then
    PROXY_ARG=(-x "http://127.0.0.1:$p")
    echo "检测到本地代理: 127.0.0.1:$p"
    break
  fi
done
[ ${#PROXY_ARG[@]} -eq 0 ] && echo "未检测到代理，直连下载"

start_part=0
for f in models/big-lama.pt.part.*; do
  [ -e "$f" ] || continue
  idx=${f##*.part.}
  [ "$idx" -gt "$start_part" ] && start_part=$idx
done
[ "$start_part" -gt 0 ] && echo "续传: 从第 $((start_part + 1)) 块开始"

while :; do
  offset=$((start_part * CHUNK))
  [ "$offset" -ge "$TOTAL" ] && break
  end=$((offset + CHUNK - 1))
  [ "$end" -ge "$TOTAL" ] && end=$((TOTAL - 1))
  part=$(printf "%03d" "$((start_part + 1))")
  curl -sL "${PROXY_ARG[@]}" --retry 3 -o "models/big-lama.pt.part.$part" \
    -r "$offset-$end" "$URL"
  echo "块 $part 完成 ($(( (end + 1) * 100 / TOTAL ))%)"
  start_part=$((start_part + 1))
done

cat models/big-lama.pt.part.* > "$OUT"
rm -f models/big-lama.pt.part.*
echo "MODEL_READY: $(cd models && pwd)/big-lama.pt ($(stat -f%z "$OUT") 字节)"
