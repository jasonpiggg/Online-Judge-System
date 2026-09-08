"""Pack reproducible local component assets after the Vite library build."""

import base64
import gzip
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / "frontend/assets"
target.mkdir(exist_ok=True)
for extension in ("js", "css"):
    name = f"oj-components.{extension}"
    source = root / "tmp/streamlit-build" / name
    content = source.read_bytes()
    if extension == "css":
        font = base64.b64encode(
            (root / "web/public/fonts/JetBrainsMono-Regular.woff2").read_bytes()
        ).decode()
        css = content.decode().replace(
            "/fonts/JetBrainsMono-Regular.woff2", "data:font/woff2;base64," + font
        )
        # Streamlit-supported browsers support WOFF2; remove duplicate legacy formats.
        css = re.sub(r",url\(data:font/(?:woff|ttf);[^)]*\)format\([^)]*\)", "", css)
        content = css.encode()
    (target / f"{name}.gz").write_bytes(gzip.compress(content, mtime=0))
    print(f"Packed {name}: {(target / f'{name}.gz').stat().st_size} bytes")
