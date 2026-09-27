"""東京滑雪地圖：關東至越後定位、往返路線與東京市區放大。
既有四站經緯度、投影、四段路線與海岸幾何保留；各圖僅等比縮放及平移。
預設只自檢，不寫檔；--output 以 x 模式寫新路徑，拒絕覆蓋。
"""
import json, math
from pathlib import Path

SC = Path(__file__).parent
d = json.load(open(SC / "japan.geojson"))

# 本州中部（覆蓋投影窗視野即可，多取無妨——viewBox 只顯示內容範圍）
PREF_IDS = {7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 22}
prefs = [f for f in d["features"] if f["properties"]["id"] in PREF_IDS]

def ring_area(r):
    s = 0.0
    for i in range(len(r) - 1):
        s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
    return abs(s) / 2

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1e-12
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        dist = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / L
        if dist > dmax:
            dmax, idx = dist, i
    if dmax > eps:
        a = rdp(pts[: idx + 1], eps)
        b = rdp(pts[idx:], eps)
        return a[:-1] + b
    return [pts[0], pts[-1]]

AREA_MIN = 0.008
rings = []
for f in prefs:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poly in polys:
        outer = poly[0]
        if ring_area(outer) >= AREA_MIN:
            mid = len(outer) // 2
            simp = rdp(outer[:mid + 1], 0.004)[:-1] + rdp(outer[mid:], 0.004)
            rings.append((f["properties"]["id"], simp))

# ---- 投影（手動窗：聚焦成田—上野—越後湯澤走廊） ----
lat0, lat1 = 35.40, 37.15
lon0, lon1 = 138.30, 140.95
cosf = math.cos(math.radians((lat0 + lat1) / 2))
W = 740
PADL, PADR, PADT, PADB = 26, 120, 36, 26
S = (W - PADL - PADR) / ((lon1 - lon0) * cosf)
H = int((lat1 - lat0) * S + PADT + PADB)

def XY(lon, lat):
    return (round(PADL + (lon - lon0) * cosf * S, 1), round(PADT + (lat1 - lat) * S, 1))

def path_of(r):
    pts = [XY(*p) for p in r]
    return "M" + " L".join(f"{x},{y}" for x, y in pts) + " Z"

land_paths = "\n".join(f'      <path d="{path_of(r)}"/>' for _, r in rings)

# ---- 地點（真實經緯度） ----
P = {
    "narita": (140.386, 35.772),
    "ueno":   (139.777, 35.712),   # Section L 上野・淺草寫真在旁（3.8px，圓內）
    "yuzawa": (138.808, 36.936),   # 雪の花・GALA・湯澤高原全在站旁
    "odaiba": (139.776, 35.627),   # 距上野 22.5px（外緣和 19.8）：貼近，不畫線
}
C = {k: XY(*v) for k, v in P.items()}

def q(a, b, bend=0.18, side=1, r_start=0.0, r_end=0.0):
    (x1, y1), (x2, y2) = a, b
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * bend * side, my + dx * bend * side
    def B(t):
        w = 1 - t
        return (w*w*x1 + 2*w*t*cx + t*t*x2, w*w*y1 + 2*w*t*cy + t*t*y2)
    u, v = 0.0, 1.0
    if r_start > 0:
        for i in range(1, 401):
            t = i / 400
            if math.hypot(B(t)[0]-x1, B(t)[1]-y1) >= r_start:
                u = t; break
    if r_end > 0:
        for i in range(1, 401):
            t = 1 - i / 400
            if math.hypot(B(t)[0]-x2, B(t)[1]-y2) >= r_end:
                v = t; break
    if v - u < 0.05:
        u, v = min(u, .40), max(v, .60)
    q0, q2 = B(u), B(v)
    dbu = (2*(1-u)*(cx-x1) + 2*u*(x2-cx), 2*(1-u)*(cy-y1) + 2*u*(y2-cy))
    q1 = (q0[0] + (v-u)*dbu[0]/2, q0[1] + (v-u)*dbu[1]/2)
    dd = f"M{round(q0[0],1)},{round(q0[1],1)} Q{round(q1[0],1)},{round(q1[1],1)} {round(q2[0],1)},{round(q2[1],1)}"
    mid = B(.5)
    return dd, (round(mid[0],1), round(mid[1],1)), (round(q2[0],1), round(q2[1],1))

def shift(pt, dx, dy):
    return (round(pt[0] + dx, 1), round(pt[1] + dy, 1))

# ---- 路線（同走廊雙向段用反側 bend 分開） ----
d1a, m1a, e1a = q(C["narita"], C["ueno"],   .17,  1, r_start=9,  r_end=13)   # Skyliner
d1b, m1b, e1b = q(C["ueno"], C["yuzawa"],   .10,  1, r_start=13, r_end=14)   # 上越新幹線
d3,  m3,  e3  = q(C["yuzawa"], C["ueno"],   .10,  1, r_start=13, r_end=14)   # 回程（反向同 side＝彎另一側）
d5,  m5,  e5  = q(C["ueno"], C["narita"],   .10,  1, r_start=13, r_end=11)   # Skyliner 回程（小彎陡升；上野文字在西側，東側線帶無字）


# 原投影座標是三幅地圖的共同座標系；排標座標不參與地理計算。
ROUTES = [("d1a", d1a, "drive", 1), ("d1b", d1b, "rail", 1),
          ("d3", d3, "rail", 3), ("d5", d5, "drive", 5)]
LAYOUTS = {
    "locator": (340, 350, .37, 25, 110),
    "detail": (340, 420, .70, -60, 0),
    "city": (340, 320, 5, -1615, -2078),
}
# x, y, width, height, main title, subtitle lines, leader endpoint
LABELS = {
    "locator": {
        "yuzawa": (93, 126, 176, 48, "越後湯澤", ["雪場所在・新潟縣"], (93, 150)),
        "ueno": (12, 293, 160, 48, "東京・上野", ["台場見市區放大圖"], (153, 293)),
        "narita": (211, 278, 117, 48, "成田機場", ["千葉縣"], (220, 278)),
    },
    "detail": {
        "yuzawa": (64, 24, 260, 65, "越後湯澤", ["D1–D2 雪の花・D2 GALA 湯澤", "D3 湯澤高原"], (64, 67)),
        "narita": (211, 229, 117, 48, "成田機場", ["D1 抵達・D5 回程"], (272, 277)),
        "ueno": (12, 347, 165, 61, "東京・上野", ["D3–D4 Section L 住宿", "東京市區見下方放大圖"], (167, 347)),
        "odaiba": (212, 354, 116, 48, "台場", ["D4 AquaCity"], (212, 370)),
    },
    "city": {
        "ueno": (16, 20, 308, 64, "上野", ["D3–D4 泊 Section L Ueno-Hirokoji", "D5 Skyliner 前往成田機場"], (171, 84)),
        "odaiba": (16, 246, 308, 57, "台場", ["D4 AquaCity Odaiba・玩具反斗城"], (169, 246)),
    },
}
DAYS = [
    ("1/24（六）", "成田 → 上野 → 越後湯澤", "Skyliner・上越新幹線", "Tanigawa 405，17:18–18:36"),
    ("1/25（日）", "GALA 湯澤滑雪", "接駁巴士 BLUE/ORANGE LINE", "或 JR 一站直達・巨人滑雪學校"),
    ("1/26（一）", "湯澤高原 → 上野", "上越新幹線回東京", "雪の花退房・入住 Section L"),
    ("1/27（二）", "台場一日", "AquaCity・玩具反斗城", "Section L 上野連住"),
    ("1/28（三）", "淺草寫真 → 成田", "Skyliner 回機場", "拉麵林田・花筏親子寫真"),
]


def screen(layout, point):
    _, _, scale, tx, ty = LAYOUTS[layout]
    return (point[0] * scale + tx, point[1] * scale + ty)


def city_land():
    """市區海岸沿用同一 GeoJSON，以較小容差保留東京灣填海地形。"""
    result = []
    for feature in prefs:
        if feature["properties"]["id"] not in (12, 13, 14):
            continue
        geometry = feature["geometry"]
        polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for poly in polys:
            outer = poly[0]
            xs, ys = zip(*outer)
            if max(xs) < 139.60 or min(xs) > 139.94 or max(ys) < 35.54 or min(ys) > 35.79:
                continue
            middle = len(outer)//2
            simplified = rdp(outer[:middle+1], .0002)[:-1] + rdp(outer[middle:], .0002)
            result.append(f'<path d="{path_of(simplified)}"/>')
    return "\n".join(result)


def label(layout, key, spec):
    x, y, width, height, title, subtitles, end = spec
    px, py = screen(layout, C[key])
    ex, ey = end
    subtitle = "".join(f'<text x="{x+10}" y="{y+42+i*14}" font-size="11.5" fill="var(--gm-muted)">{line}</text>'
                       for i, line in enumerate(subtitles))
    return f'''<g class="geo-station-label" data-label-for="{key}">
      <path d="M{px:.2f},{py:.2f} L{ex},{ey}" stroke="var(--gm-muted)" stroke-width="1.2" fill="none"/>
      <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="var(--gm-paper)" stroke="var(--gm-border)"/>
      <text x="{x+10}" y="{y+24}" font-size="19" font-weight="800" fill="var(--gm-ink)">{title}</text>
      {subtitle}
    </g>'''


def north():
    return '''<g fill="var(--gm-muted)" stroke="var(--gm-muted)">
      <path d="M313,51 V28 M309,35 L313,27 L317,35" fill="none" stroke-width="1.3"/>
      <text x="313" y="20" text-anchor="middle" font-size="11" stroke="none">北 N</text>
    </g>'''


def render_map(layout):
    width, height, scale, tx, ty = LAYOUTS[layout]
    names = {"locator": "關東至越後區域定位", "detail": "東京與越後湯澤往返路線",
             "city": "東京市區放大：上野與台場"}
    title = names[layout]
    keys = ("ueno", "odaiba") if layout == "city" else tuple(P)
    outlines = city_land() if layout == "city" else land_paths
    out = [f'''<svg class="geo-map geo-{layout}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="ski-{layout}-title ski-{layout}-desc">
      <title id="ski-{layout}-title">{title}</title>
      <desc id="ski-{layout}-desc">使用同一等距投影與真實經緯度，北方朝上。越後湯澤位在東京西北方，成田在上野東方，台場在上野南方。連線為行程示意，非實際軌道或導航。</desc>
      <defs><clipPath id="ski-{layout}-clip"><rect width="{width}" height="{height}"/></clipPath></defs>
      <g clip-path="url(#ski-{layout}-clip)">
      <g class="geo-geography" data-projection="ski-equirectangular" transform="translate({tx} {ty}) scale({scale})">
      <g class="geo-land" fill="var(--gm-land)" stroke="var(--gm-coast)" stroke-width="{.7/scale:.6f}" stroke-linejoin="round">
{outlines}
      </g>''']
    if layout == "locator":
        # 以詳細圖視窗的反變換取得定位框，非目測畫框。
        dw, dh, ds, dx, dy = LAYOUTS["detail"]
        out.append(f'<rect data-travel-window="detail" x="{-dx/ds}" y="{-dy/ds}" width="{dw/ds}" height="{dh/ds}" fill="var(--gm-drive)" fill-opacity=".05" stroke="var(--gm-drive)" stroke-width="{1.3/scale}"/>')
    if layout != "city":
        for name, path, mode, day in ROUTES:
            dash = f' stroke-dasharray="{6/scale} {3/scale}"' if mode == "rail" else ""
            out.append(f'<a href="#day{day}"><title>D{day} {"上越新幹線" if mode == "rail" else "Skyliner"}</title><path data-route-segment="{name}" d="{path}" fill="none" stroke="var(--gm-{mode})" stroke-width="{(2.8 if layout == "detail" else 1.6)/scale}"{dash}/></a>')
    for key in keys:
        x, y = C[key]
        # 位置資料與投影座標在不同縮放圖完全相同。
        out.append(f'<circle data-station="{key}" data-lon="{P[key][0]}" data-lat="{P[key][1]}" cx="{x}" cy="{y}" r="{(3.5 if layout == "locator" else 4.5)/scale}" fill="var(--gm-paper)" stroke="var(--gm-drive)" stroke-width="{2/scale}"/>')
    if layout == "detail":
        cw, ch, cs, cx, cy = LAYOUTS["city"]
        out.append(f'<rect data-travel-window="city" x="{-cx/cs}" y="{-cy/cs}" width="{cw/cs}" height="{ch/cs}" fill="none" stroke="var(--gm-muted)" stroke-width="{1/scale}" stroke-dasharray="{3/scale} {3/scale}"/>')
    out.append("</g></g>")
    if layout == "locator":
        out.extend([north(), '<text x="34" y="70" font-size="14" fill="var(--gm-muted)">日本海</text>',
                    '<text x="266" y="223" font-size="14" fill="var(--gm-muted)">太平洋</text>',
                    '<text x="107" y="210" font-size="17" fill="var(--gm-muted)" font-weight="750">本州</text>'])
    if layout == "city":
        out.extend(['<g transform="translate(0 92)">' + north() + '</g>', '<text x="246" y="205" font-size="14" fill="var(--gm-muted)">東京灣</text>'])
    for key, spec in LABELS[layout].items():
        out.append(label(layout, key, spec))
    if layout == "detail":
        # 日次標記與對應路線中點相連，不壓在地名或站點上。
        for day, point, bx, by in [(1, m1b, 151, 175), (3, m3, 67, 215),
                                    (5, m5, 261, 325)]:
            px, py = screen(layout, point)
            out.append(f'''<a class="geo-badge" href="#day{day}"><title>D{day} 查看當日行程</title>
              <path d="M{px:.2f},{py:.2f} L{bx},{by}" fill="none" stroke="var(--gm-muted)" stroke-width="1"/>
              <rect x="{bx-17}" y="{by-12}" width="34" height="24" rx="12" fill="var(--gm-badge)"/>
              <text x="{bx}" y="{by+4}" text-anchor="middle" font-size="12" font-weight="800" fill="var(--gm-badge-ink)">D{day}</text></a>''')
    out.append("</svg>")
    return "\n".join(out)


def render():
    cards = []
    for day, (date, title, transport, note) in enumerate(DAYS, 1):
        cards.append(f'''    <a class="geo-day-card" href="#day{day}">
      <span class="geo-day-num">D{day}</span><span class="geo-day-copy"><span>{date}</span><strong>{title}</strong><span>{transport}</span><small>{note}</small></span>
    </a>''')
    return '''  <!-- trip-map:generated:start -->
  <div class="geo-panel">
    <div class="geo-intro"><span>東京與越後湯澤・五日冬旅</span><span>2026.01.24–01.28</span></div>
    <div class="geo-atlas">
      <figure class="geo-overview">
        <figcaption><b>關東至越後・區域定位</b><span>從東京往西北，前往越後湯澤雪場</span></figcaption>
''' + render_map("locator") + '''
        <p class="geo-map-note">保留本州中部地理輪廓；實線框對應往返詳細圖範圍，聚焦本次旅行區域。</p>
      </figure>
      <figure class="geo-detail">
        <figcaption><b>滑雪往返・路線詳細圖</b><span>D1 前往湯澤，D3 回東京，D5 回成田</span></figcaption>
        <div class="geo-legend" aria-label="交通圖例"><span><i class="geo-swatch" aria-hidden="true"></i>Skyliner</span><span><i class="geo-swatch geo-rail" aria-hidden="true"></i>上越新幹線</span></div>
''' + render_map("detail") + '''
      </figure>
    </div>
    <figure class="geo-city-panel">
      <figcaption><b>東京市區・局部放大</b><span>東京住宿與台場一日行程</span></figcaption>
      <div class="geo-city-content">
''' + render_map("city") + '''
        <div class="geo-city-copy"><strong>先雪場，再回東京</strong><p>上野是本次東京住宿與轉乘的主要節點；台場在南側，D4 安排 AquaCity 與玩具反斗城。</p><p>D5 淺草拉麵林田與花筏親子寫真，詳見當日行程卡。</p><p>D2 前往 GALA 湯澤：接駁巴士 BLUE/ORANGE LINE，或 JR 一站直達。</p></div>
      </div>
    </figure>
    <p class="geo-map-note">各圖共用地理投影，僅改變縮放與視窗。細灰引線連接中文地名與原始點位；詳細圖虛線框對應東京市區。雪の花、GALA 湯澤、湯澤高原沿用越後湯澤區域標示。路線為行程示意，非精確軌道或導航。</p>
  </div>
  <nav class="geo-days" aria-label="地圖五日行程跳轉">
''' + "\n".join(cards) + '''
  </nav>
  <!-- trip-map:generated:end -->'''


def check_geometry():
    """檢查同投影點位、縮放、定位框及排標；失敗即拒絕輸出。"""
    from xml.etree import ElementTree as ET
    ns = {"s": "http://www.w3.org/2000/svg"}
    original_points = {"narita": (140.386, 35.772), "ueno": (139.777, 35.712),
                       "yuzawa": (138.808, 36.936), "odaiba": (139.776, 35.627)}
    assert P == original_points, "原始經緯度不得改動"
    assert C == {"narita": (493.6, 419.1), "ueno": (357.1, 435.8),
                 "yuzawa": (139.9, 95.5), "odaiba": (356.8, 459.5)}
    for layout in LAYOUTS:
        width, height, scale, tx, ty = LAYOUTS[layout]
        svg = ET.fromstring(render_map(layout))
        for circle in svg.findall(".//s:circle[@data-station]", ns):
            key = circle.attrib["data-station"]
            assert (float(circle.attrib["cx"]), float(circle.attrib["cy"])) == C[key]
            x, y = screen(layout, C[key])
            assert 6 <= x <= width-6 and 6 <= y <= height-6, (layout, key, "站點出框")
        boxes = []
        for key, (x, y, w, h, _, _, _) in LABELS[layout].items():
            assert 0 <= x <= x+w <= width and 0 <= y <= y+h <= height
            for a, b, c, e in boxes:
                assert x+w <= a or a+c <= x or y+h <= b or b+e <= y, "標籤重疊"
            boxes.append((x, y, w, h))
            for station in (("ueno", "odaiba") if layout == "city" else P):
                px, py = screen(layout, C[station])
                assert not (x-6 < px < x+w+6 and y-6 < py < y+h+6), (layout, key, station, "標籤壓站點")
        for frame in svg.findall(".//s:rect[@data-travel-window]", ns):
            target = frame.attrib["data-travel-window"]
            target_keys = ("ueno", "odaiba") if target == "city" else P
            x, y, w, h = [float(frame.attrib[k]) for k in ("x", "y", "width", "height")]
            for key in target_keys:
                px, py = C[key]
                assert x <= px <= x+w and y <= py <= y+h, "定位框漏站點"
        print(f"PASS {layout}: 共用點位與投影、定位框、標籤邊界及站點淨空")
    assert C["yuzawa"][0] < C["ueno"][0] and C["yuzawa"][1] < C["ueno"][1]
    print(f"PASS 原四站、四條往返路線；{len(rings)} 個原地形環；五日日期與交通卡")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="只寫新路徑；省略時只自檢，不寫任何檔案")
    args = parser.parse_args()
    check_geometry()
    if args.output:
        with args.output.open("x", encoding="utf-8") as out:
            out.write(render() + "\n")
        print(f"generated: {args.output}")


if __name__ == "__main__":
    main()
