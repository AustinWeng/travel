#!/usr/bin/env python3
"""Regression checks for the three atlas-style travel maps (browser checks separate)."""
import argparse
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TRIPS = {
    "2026-kyushu": ("gen_kyushu_map.py", 8),
    "2026-tokyo-ski": ("gen_ski_map.py", 5),
    "2025-tokyo-disney": ("gen_disney_map.py", 7),
}
CSS = re.compile(r"/\* trip-map:styles:start \*/.*?/\* trip-map:styles:end \*/", re.S)
MAP = re.compile(r'<section\b[^>]*\bid="geomap"[^>]*>.*?</section>', re.S)
GENERATED = re.compile(r"<!-- trip-map:generated:start -->(.*?)<!-- trip-map:generated:end -->", re.S)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.days = []
        self.external = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "a":
            self.links.append(a.get("href", ""))
            if "geo-day-card" in a.get("class", "").split():
                self.days.append(a.get("href", ""))
        if tag in ("script", "iframe", "img"):
            self.external.append((tag, a.get("src")))


def normalize_blank_lines(text):
    # Only blank insertion lines around the new CSS block may differ.
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)


def checked(cmd):
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{cmd}:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def file_state(path):
    stat = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_ino,
            stat.st_mtime_ns, stat.st_ctime_ns)


def map_css_only(block):
    clean = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    for prelude in re.findall(r"([^{}]+)\{", clean):
        prelude = prelude.strip()
        if prelude.startswith(("@media", "@supports")):
            continue
        for selector in prelude.split(","):
            anchor = re.search(r"(?:^|\s)#geomap(?![\w-])", selector)
            assert anchor, f"unscoped map CSS: {selector}"
            assert not re.search(r"[+~]", selector[anchor.end():]), f"sibling scope may escape map: {selector}"
            assert ":has(" not in selector, f"CSS must target the map, not a containing element: {selector}"


def verify(trip, baseline):
    script, days = TRIPS[trip]
    page = ROOT / trip / "index.html"
    current = page.read_text()
    old = checked(["git", "show", f"{baseline}:{trip}/index.html"])
    oldmap, newmap = MAP.search(old), MAP.search(current)
    assert oldmap and newmap, "geomap section missing"
    assert len(CSS.findall(current)) == 1, "one bounded scoped CSS block required"
    map_css_only(CSS.search(current)[0])
    assert current[newmap.end():] == old[oldmap.end():], "content after map changed"
    before = CSS.sub("", current[:newmap.start()])
    assert normalize_blank_lines(before) == normalize_blank_lines(old[:oldmap.start()]), "non-map prefix changed"
    generated = GENERATED.search(newmap[0])
    assert generated, "generated markers missing"
    assert len(GENERATED.findall(current)) == 1, "duplicate generated blocks"
    tags, oldtags, maptags = Tags(), Tags(), Tags()
    tags.feed(current)
    oldtags.feed(old)
    maptags.feed(newmap[0])
    assert len(tags.ids) == len(set(tags.ids)), "duplicate document ids"
    assert tags.external == oldtags.external, "external dependencies changed"
    assert set(maptags.days) == {f"#day{d}" for d in range(1, days + 1)}, "day cards missing"
    assert len(maptags.days) == days, "duplicate day cards"
    for link in maptags.links:
        if link.startswith("#"):
            assert link[1:] in tags.ids, f"broken anchor {link}"
    assert len(re.findall(r"<svg\b", newmap[0])) >= 2, "locator + detail required"
    with tempfile.TemporaryDirectory(prefix=f"check-{trip}-") as tmp:
        output = Path(tmp) / "map.html"
        protected = {p: file_state(p) for p in (ROOT / "scripts").glob("*_map.svg.html")}
        snippets = set(protected)
        protected[page] = file_state(page)
        checked([sys.executable, str(ROOT / "scripts" / script)])
        assert not output.exists()
        assert set((ROOT / "scripts").glob("*_map.svg.html")) == snippets, "default execution created an artifact"
        assert all(file_state(p) == state for p, state in protected.items()), "default execution wrote a protected artifact"
        checked([sys.executable, str(ROOT / "scripts" / script), "--output", str(output)])
        rendered = output.read_text()
        marked = GENERATED.search(rendered)
        if marked:
            assert rendered[:marked.start()].strip() == rendered[marked.end():].strip() == "", "unverified output outside generated block"
        rendered_body = marked[1] if marked else rendered
        assert generated[1].strip() == rendered_body.strip(), "generator and embedded map differ"
        state = file_state(output)
        rerun = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--output", str(output)], cwd=ROOT, capture_output=True)
        assert rerun.returncode != 0, "generator must refuse overwrite"
        message = (rerun.stdout + rerun.stderr).decode(errors="replace")
        assert re.search(r"FileExistsError|exist|已存在|拒絕覆", message, re.I), "missing explicit overwrite-refusal diagnostic"
        assert file_state(output) == state, "existing output touched or modified"
        assert set((ROOT / "scripts").glob("*_map.svg.html")) == snippets, "generator created an unexpected artifact"
        assert all(file_state(p) == state for p, state in protected.items()), "generator wrote a protected artifact"
    print(f"PASS {trip}: generated parity, safe output, {days} day cards, anchors, external dependencies, map-exterior protection")
    print(f"  SHA256 {hashlib.sha256(page.read_bytes()).hexdigest()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="b405eeeead1ba9caa55ea831db18ae1f4703155e")
    parser.add_argument("--trip", choices=TRIPS)
    args = parser.parse_args()
    for trip in ([args.trip] if args.trip else TRIPS):
        verify(trip, args.baseline)


if __name__ == "__main__":
    main()
