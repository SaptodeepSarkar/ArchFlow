#!/usr/bin/env bash
# Build a system-wide Arch package from this checkout, including current edits.
# Run as a regular user. Does not install packages or change system files.
set -euo pipefail
cd "$(dirname "$0")/.."
package_dir="$(mktemp -d "${TMPDIR:-/tmp}/vaani-package.XXXXXXXX")"
version="$(sed -n 's/^pkgver=//p' packaging/PKGBUILD)"
cp packaging/PKGBUILD packaging/vaani.install "$package_dir/"
git ls-files -co --exclude-standard -z | tar --null --verbatim-files-from -T - --transform="s,^,ArchFlow-$version/," -czf "$package_dir/vaani-$version.tar.gz"
python3 - "$package_dir/PKGBUILD" "$version" <<'PY'
from pathlib import Path
import hashlib, sys
p = Path(sys.argv[1])
archive = p.parent / ('vaani-' + sys.argv[2] + '.tar.gz')
s = p.read_text().replace('source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")', 'source=("$pkgname-$pkgver.tar.gz")')
s = s.replace("sha256sums=('SKIP')", "sha256sums=('" + hashlib.sha256(archive.read_bytes()).hexdigest() + "')")
p.write_text(s)
PY
printf 'Package sources: %s\n' "$package_dir"
cd "$package_dir"
makepkg --cleanbuild
