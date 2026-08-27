#!/usr/bin/env bash
# Build all tools' data and assemble a static dist/ directory.
set -u; cd "$(dirname "$0")/.."
mkdir -p dist; cp -r site/. dist/
for t in ghost-tracker rereport heat lanes; do
  [ -d "$t/site" ] || continue
  [ -f "$t/build.py" ] && { echo "== build $t"; python3 "$t/build.py" || echo "!! $t build failed, keeping previous data"; }
  mkdir -p "dist/$t"; cp -r "$t/site/." "dist/$t/"
done
echo "== summary"; python3 deploy/summary.py dist/summary.json || echo "!! summary failed"
echo "assembled $(date -Is)"
