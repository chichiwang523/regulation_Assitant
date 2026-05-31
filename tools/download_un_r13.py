from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "sources"
MANIFEST = SOURCE_DIR / "un_r13_sources.json"


def main() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    sources = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for source in sources:
        target = SOURCE_DIR / source["file"]
        if target.exists() and target.stat().st_size > 0:
            print(f"skip {target.name}")
            continue
        request = Request(source["source_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
        print(f"downloaded {target.name} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
