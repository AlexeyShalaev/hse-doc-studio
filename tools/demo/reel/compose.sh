#!/bin/bash
# Вкомпоновывает записи тура (4 варианта: ru/en × light/dark) в «плавающее окно»
# на фирменном градиенте с тенью → MP4 + постер первого кадра.
# Вход:  .build/out/<lang>-<theme>/*.webm (record.mjs) + .build/assets/* (gen-assets.mjs)
# Выход: docs/ru/assets/reel/reel.<lang>.<theme>.mp4 + reel-poster.<lang>.<theme>.png
#        (ассеты сайта общие: docs/ru — единственный источник, sync копирует в docs/en)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
BUILD="${BUILD_DIR:-$HERE/.build}"
A="${ASSETS_DIR:-$BUILD/assets}"
DIST="${DIST_DIR:-$ROOT/docs/ru/assets/reel}"
mkdir -p "$DIST"

VARIANTS="${VARIANTS:-ru-light ru-dark en-light en-dark}"
# Глобальное ускорение: паузы загрузок сжимаются, курсор и фейды бодрее —
# рекламный темп без пересъёмки. 1.0 = как записано.
SPEED="${SPEED:-1.35}"

for v in $VARIANTS; do
  lang="${v%-*}"; theme="${v#*-}"
  dir="$BUILD/out/$v"
  rec="$dir/capture.mp4"
  [ -f "$rec" ] || { echo "SKIP $v: нет записи в $dir"; continue; }
  out="$DIST/reel.$lang.$theme.mp4"
  echo "→ $v: $rec"

  # Супсемплинг: запись 2× (3200×2000) → окно на 4K-холсте → даунскейл lanczos
  # в 1920×1080. Так скринкаст Playwright перестаёт «мылить».
  ffmpeg -y -i "$rec" -i "$A/bg.$theme.png" -i "$A/mask.png" -i "$A/shadow.$theme.png" -filter_complex "
  [0:v]setpts=PTS/${SPEED},scale=3200:2000:flags=lanczos,setsar=1,fps=30[rec];
  [rec][2:v]alphamerge[win];
  [1:v][3:v]overlay=0:0[bgsh];
  [bgsh][win]overlay=(W-w)/2:(H-h)/2[comp];
  [comp]scale=1920:1080:flags=lanczos[v]
  " -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 18 -preset slow -movflags +faststart "$out" -loglevel error
  echo "  MP4: $(du -h "$out" | cut -f1) · $(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$out" | cut -d. -f1)s"

  # Постер: титр полностью проявлен (~2.2 с записи; с учётом SPEED — раньше)
  ffmpeg -y -ss "$(awk "BEGIN{printf \"%.2f\", 2.2/${SPEED}}")" -i "$out" -frames:v 1 "$DIST/reel-poster.$lang.$theme.png" -loglevel error
done

echo "COMPOSE_DONE → $DIST"
