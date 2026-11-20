#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: sh backend/deploy/fc-preview/build.sh /absolute/output.zip" >&2
    exit 2
fi

output=$1
case "$output" in
    /*.zip) ;;
    *) echo "Use an absolute .zip output path." >&2; exit 2 ;;
esac
root=$(git rev-parse --show-toplevel)
package=$(mktemp -d)
trap 'rm -rf "$package"' EXIT
mkdir -p "$package/backend/health_ai" "$package/demos/xunji"
cp "$root"/backend/health_ai/*.py "$package/backend/health_ai/"
cp "$root"/backend/deploy/fc-preview/bootstrap.sh "$package/"
cp "$root"/backend/deploy/fc-preview/preview.py "$package/backend/"
for asset in index.html app.js config.js style.css signals.js clinical-desk.svg knowledge.json evidence.json; do
    cp "$root/demos/xunji/$asset" "$package/demos/xunji/"
done
uv pip install --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
    --only-binary ':all:' --target "$package/backend/vendor" -r "$root/backend/requirements.txt"
python3 - "$package" "$output" <<'PY'
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

root, output = map(Path, sys.argv[1:])
with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(root))
PY
