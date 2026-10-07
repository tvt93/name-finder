"""Build docs/ : a standalone copy of the app for hosting outside claude.ai (Netlify, GitHub Pages, ...).

The artifact version (app/index.html) has no <html>/<head> skeleton because claude.ai adds one at publish
time. This wraps the same content in a full document and copies the data files next to it.

Run:  python make_dist.py   ->  docs/index.html, docs/data/names.js, docs/data/meanings.js, dist.zip
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
APP = ROOT / "app"
DIST = ROOT / "docs"  # GitHub Pages serves the docs/ folder of the main branch

body = (APP / "index.html").read_text(encoding="utf-8")
page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<style>
:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
body{{margin:0;font:14px system-ui,sans-serif}}
img{{max-width:100%}}
[hidden]{{display:none!important}}
</style>
</head>
<body>
{body}
</body>
</html>
"""
if DIST.exists():
    shutil.rmtree(DIST)
(DIST / "data").mkdir(parents=True)
(DIST / "index.html").write_text(page, encoding="utf-8")
for f in ("names.js", "meanings.js"):
    shutil.copy(APP / "data" / f, DIST / "data" / f)
zip_path = shutil.make_archive(str(ROOT / "dist"), "zip", DIST)
print(f"dist/ ready, {sum(p.stat().st_size for p in DIST.rglob('*') if p.is_file())/1e6:.1f} MB, zip at {zip_path}")
