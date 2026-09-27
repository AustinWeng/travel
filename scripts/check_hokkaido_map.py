"""北海道地圖限定檢查：生成同步、共用幾何、對比、可選 baseline 保護。

python3 scripts/check_hokkaido_map.py --baseline /path/to/index.baseline.html
瀏覽器的尺寸、字型、鍵盤與視覺驗收另由 fresh context 執行。
"""
import argparse
import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "2027-hokkaido/index.html"
GEN = ROOT / "scripts/gen_hokkaido_map.py"
START = "  <!-- hokkaido-map:generated:start -->"
END = "  <!-- hokkaido-map:generated:end -->"


def luminance(color):
    rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
    rgb = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v, w in zip(rgb, (.2126, .7152, .0722)))


def contrast(a, b):
    aa, bb = sorted((luminance(a), luminance(b)))
    return (bb+.05)/(aa+.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    html = PAGE.read_text()
    with tempfile.TemporaryDirectory(prefix="hokkaido-map-check-") as tmp:
        output = Path(tmp) / "map.html"
        subprocess.run([sys.executable, str(GEN), "--output", str(output)], check=True)
        embedded = html[html.index(START):html.index(END)+len(END)] + "\n"
        assert embedded == output.read_text(), "generator 與嵌入產物不同步"
        # 再次生成必須拒絕覆蓋，且既有檔內容不变。
        original = output.read_bytes()
        retry = subprocess.run([sys.executable, str(GEN), "--output", str(output)], capture_output=True)
        assert retry.returncode and b"FileExistsError" in retry.stderr
        assert output.read_bytes() == original
    print("PASS 產物逐位元同步；--output 拒絕覆蓋")
    svgs = [ET.fromstring(s) for s in re.findall(r'<svg class="geo-map .*?</svg>', embedded, re.S)]
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert len(svgs) == 2
    def geometry(svg):
        group = svg.find("s:g[@class='geo-geography']", ns)
        # transform 是唯一允許的差異；其中點位、海岸與路線相同。
        return ([p.attrib["d"] for p in group.findall(".//s:path", ns)],
                [c.attrib for c in group.findall(".//s:circle", ns)])
    assert geometry(svgs[0]) == geometry(svgs[1])
    for svg in svgs:
        assert len(svg.findall("s:g[@class='geo-station-label']", ns)) == 4
        assert len(svg.findall("s:g[@class='geo-badge']", ns)) == 5
    for day in range(1, 6):
        assert f'class="geo-day-card" href="#day{day}"' in embedded
        assert f'id="day{day}"' in html
    assert not re.search(r'<(?:script|iframe)|(?:src|href)="https?://', embedded)
    print("PASS 手機／桌機四站五日、完整共用幾何、日次錨點、零外部依賴")
    # 直接取頁面 token，不複製配色到測試中。
    palettes = re.findall(r'(?<!\w)#geomap\s*\{([^}]*--gm-ocean[^}]*)\}', html)
    assert len(palettes) == 3, "需含 light、system dark、explicit dark"
    ratios = []
    for palette in palettes:
        colors = dict(re.findall(r'--gm-([\w-]+):\s*(#[0-9A-Fa-f]{6})', palette))
        for fg, bg in [("ink", "paper"), ("muted", "paper"), ("ink", "ocean"),
                       ("muted", "ocean"), ("badge-ink", "badge"), ("drive", "paper")]:
            value = contrast(colors[fg], colors[bg])
            assert value >= 4.5, f"{fg}/{bg} 對比不足 {value:.2f}"
            ratios.append(value)
        for fg in ("drive", "rail"):
            for bg in ("land", "ocean"):
                assert contrast(colors[fg], colors[bg]) >= 3, f"{fg}/{bg} 路線對比不足"
    print(f"PASS 必要文字/徽章最低對比 {min(ratios):.2f}:1；路線對比 ≥3:1")
    assert "prefers-reduced-motion:reduce" in html and "html:has(#geomap){scroll-behavior:auto}" in html
    if args.baseline:
        baseline = args.baseline.read_text()
        marker = '<article class="day" id="day1">'
        old_tail = baseline[baseline.index(marker):]
        new_tail = html[html.index(marker):]
        assert old_tail == new_tail, "day1 之後內容有變"
        def outside_map(text):
            text = re.sub(r'/\* 北海道地圖專屬.*?(?=/\* ---------- day card)', "", text, flags=re.S)
            return re.sub(r'<section id="geomap".*?</section>', "", text, flags=re.S)
        assert outside_map(baseline) == outside_map(html), "地圖/CSS 以外有變"
        # 原地理投影核心 AST 等同性由 baseline generator 的手動 diff 確認；
        # 已有點位、路線與海岸 SVG 幾何在此直接對照頁面 baseline。
        oldsvg = ET.fromstring(re.search(r'<section id="geomap".*?(<svg.*?</svg>)', baseline, re.S)[1])
        old_paths = {p.attrib["d"] for p in oldsvg.findall(".//s:path", ns)}
        new_paths = set(geometry(svgs[0])[0])
        assert new_paths <= old_paths, "海岸或路線 d 發生變更"
        for value in ("道央道 110 km／1.5 h", "30 km／40 分", "国道230 80 km／1.5 h", "JR 快速 37 分"):
            assert value in baseline and value in embedded, f"原里程時間缺漏：{value}"
        print("PASS 地圖以外逐位元未變；原海岸與路線 d 未變；四組里程時間原樣保留")
        print("day1-end SHA256:", hashlib.sha256(new_tail.encode()).hexdigest())


if __name__ == "__main__":
    main()
