"""從 japan.geojson 生成 2027-01 北海道道央行程 SVG（2027-hokkaido #geomap 內容）。
工具函數與 gen_ski_map.py / gen_kyushu_map.py 同源：等距投影、quadratic 路線、
沿曲線絕對截斷、徽章自動避讓、箭頭自檢（淨空 >=1px 且不落文字框，未過拒絕生成）。
手機／桌機共用地理投影、獨立排標；里程與日次跳轉放在 HTML 卡片。
預設只自檢；--output 指定新檔，拒絕覆蓋任何既有檔案。"""

import json, math
from pathlib import Path

SC = Path(__file__).parent
d = json.load(open(SC / "japan.geojson"))

PREF_IDS = {1}  # 北海道（投影窗只聚焦道央，viewBox 裁掉其餘）
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


# ---- 投影（手動窗：聚焦新千歳—洞爺湖—ルスツ—札幌道央走廊） ----
lat0, lat1 = 42.30, 43.35
lon0, lon1 = 140.30, 142.15
cosf = math.cos(math.radians((lat0 + lat1) / 2))
W = 740
PADL, PADR, PADT, PADB = 26, 120, 36, 26
S = (W - PADL - PADR) / ((lon1 - lon0) * cosf)
H = int((lat1 - lat0) * S + PADT + PADB)

# ---- 蒐集 ring ----
# 北海道是單一都道府縣、本島輪廓極長；九州／本州那組腳本可以整縣 eps=0.004，
# 這裡整島這樣做會吐出上萬點。改成逐點分流：投影窗內細簡化、窗外粗簡化。
WIN = (lon0 - 0.55, lon1 + 0.55, lat0 - 0.45, lat1 + 0.45)
AREA_MIN = 0.008  # 度²，濾掉利尻／礼文／奥尻等離島
rings = []
for f in prefs:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poly in polys:
        outer = poly[0]
        if ring_area(outer) < AREA_MIN:
            continue
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        if max(xs) < WIN[0] or min(xs) > WIN[1] or max(ys) < WIN[2] or min(ys) > WIN[3]:
            continue  # 整圈在窗外

        def _in(p):
            return WIN[0] <= p[0] <= WIN[1] and WIN[2] <= p[1] <= WIN[3]

        out, run, inside_prev = [], [], None
        for p in outer:
            ins = _in(p)
            if inside_prev is None:
                inside_prev = ins
            if ins != inside_prev:
                out += rdp(run, 0.004 if inside_prev else 0.09)[:-1]
                run = [run[-1]]
                inside_prev = ins
            run.append(p)
        out += rdp(run, 0.004 if inside_prev else 0.09)
        rings.append((f["properties"]["id"], out))


def XY(lon, lat):
    return (round(PADL + (lon - lon0) * cosf * S, 1), round(PADT + (lat1 - lat) * S, 1))


def path_of(r):
    pts = [XY(*p) for p in r]
    return "M" + " L".join(f"{x},{y}" for x, y in pts) + " Z"


land_paths = "\n".join(f'      <path d="{path_of(r)}"/>' for _, r in rings)

# ---- 地點（真實經緯度，來源見腳本末） ----
P = {
    "chitose": (141.692, 42.775),  # 新千歳空港
    "toya": (140.822, 42.566),  # 洞爺湖温泉（乃の風）
    "rusutsu": (140.892, 42.744),  # ルスツリゾート
    "sapporo": (141.354, 43.062),  # 札幌市中心（大通—札幌站之間）
    "nakayama": (141.033, 42.863),  # 中山峠（国道230 最高點）
    "maruyama": (141.312, 43.055),  # 円山動物園（距札幌僅十餘 px，併入札幌副標）
}
C = {k: XY(*v) for k, v in P.items()}


def q(a, b, bend=0.18, side=1, r_start=0.0, r_end=0.0):
    """兩點間 quadratic 曲線；r_start/r_end 為沿曲線的絕對截斷半徑。
    回傳 (path d, 原曲線中點, 截斷後終點)。"""
    (x1, y1), (x2, y2) = a, b
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * bend * side, my + dx * bend * side

    def B(t):
        w = 1 - t
        return (
            w * w * x1 + 2 * w * t * cx + t * t * x2,
            w * w * y1 + 2 * w * t * cy + t * t * y2,
        )

    u, v = 0.0, 1.0
    if r_start > 0:
        for i in range(1, 401):
            t = i / 400
            if math.hypot(B(t)[0] - x1, B(t)[1] - y1) >= r_start:
                u = t
                break
    if r_end > 0:
        for i in range(1, 401):
            t = 1 - i / 400
            if math.hypot(B(t)[0] - x2, B(t)[1] - y2) >= r_end:
                v = t
                break
    if v - u < 0.05:
        u, v = min(u, 0.40), max(v, 0.60)
    q0, q2 = B(u), B(v)
    dbu = (
        2 * (1 - u) * (cx - x1) + 2 * u * (x2 - cx),
        2 * (1 - u) * (cy - y1) + 2 * u * (y2 - cy),
    )
    q1 = (q0[0] + (v - u) * dbu[0] / 2, q0[1] + (v - u) * dbu[1] / 2)
    dd = f"M{round(q0[0], 1)},{round(q0[1], 1)} Q{round(q1[0], 1)},{round(q1[1], 1)} {round(q2[0], 1)},{round(q2[1], 1)}"
    mid = B(0.5)
    return dd, (round(mid[0], 1), round(mid[1], 1)), (round(q2[0], 1), round(q2[1], 1))


def shift(pt, dx, dy):
    return (round(pt[0] + dx, 1), round(pt[1] + dy, 1))


# ---- 路線 ----
# D1 新千歳 → 洞爺湖（道央道，沿太平洋岸往南彎）
d1, m1, e1 = q(C["chitose"], C["toya"], 0.10, -1, r_start=9, r_end=14)
# D2 洞爺湖 → ルスツ（短段，東彎讓開洞爺湖標籤）
d2, m2, e2 = q(C["toya"], C["rusutsu"], 0.14, 1, r_start=13, r_end=14)
# D4 ルスツ → 中山峠 → 札幌（国道230）；箭頭掛在後半段
d4a, m4a, e4a = q(C["rusutsu"], C["nakayama"], 0.10, -1, r_start=13, r_end=8)
d4b, m4b, e4b = q(C["nakayama"], C["sapporo"], 0.10, -1, r_start=8, r_end=14)
# D5 札幌 → 新千歳（JR 快速エアポート，虛線）
d5, m5, e5 = q(C["sapporo"], C["chitose"], 0.08, -1, r_start=13, r_end=14)

# ---- 文字寬度估算（全形 1em、半形 0.56em） ----
_FULL_EXTRA = {0x2708, 0x25CF, 0x2192}


def tw(s, size):
    w = 0.0
    for ch in s:
        o = ord(ch)
        w += size if (o >= 0x2E80 or o in _FULL_EXTRA) else size * 0.56
    return round(w, 1)


def _bb(cx, cy, anchor, w, size):
    if anchor == "start":
        x0, x1 = cx, cx + w
    elif anchor == "end":
        x0, x1 = cx - w, cx
    else:
        x0, x1 = cx - w / 2, cx + w / 2
    return (x0, x1, cy - size, cy + 3)


# ---- 響應式排標：地形、節點、路線共用 XY，僅整體等比例仿射 ----
# 每組為 width, height, scale, tx, ty；不單獨壓縮海岸或搬移站點。
LAYOUTS = {
    "mobile": (340, 340, .75, -81, -32),
    "desktop": (680, 440, 1, 20, -30),
}
# 標籤卡的位置在各 viewBox 內，字級不跟著地形縮小。
LABELS = {
    "mobile": {
        "sapporo": (165, 26, 165, "札幌", "D4 泊 1 晚"),
        "rusutsu": (10, 60, 145, "ルスツリゾート", "D2–D3 泊 2 晚・滑雪"),
        "toya": (10, 280, 150, "洞爺湖温泉", "D1 泊 乃の風・1 晚"),
        "chitose": (180, 280, 150, "新千歳空港", "D1 抵達・D5 返程"),
    },
    "desktop": {
        "sapporo": (416, 59, 235, "札幌", "D4 泊 1 晚・円山動物園"),
        "rusutsu": (24, 183, 190, "ルスツリゾート", "D2–D3 泊 2 晚・滑雪"),
        "toya": (72, 374, 195, "洞爺湖温泉", "D1 泊 乃の風・1 晚"),
        "chitose": (474, 302, 190, "新千歳空港", "D1 抵達・D5 返程"),
    },
}
BADGES = {
    "mobile": {"D1": (184, 250), "D2": (35, 223), "D3": (126, 201),
               "D4": (166, 140), "D5": (269, 125)},
    "desktop": {"D1": (367, 330), "D2": (183, 310), "D3": (275, 280),
                "D4": (342, 185), "D5": (461, 188)},
}
ROUTES = [("d1", d1), ("d2", d2), ("d4a", d4a), ("d4b", d4b), ("d5", d5)]
NODES_R = {"chitose": 9, "toya": 9, "rusutsu": 9, "sapporo": 9, "nakayama": 4}
TITLES = {
    "D1": "1/20 桃園 → 新千歳 → 洞爺湖",
    "D2": "1/21 洞爺湖 → ルスツ",
    "D3": "1/22 ルスツ滑雪",
    "D4": "1/23 ルスツ → 中山峠 → 札幌",
    "D5": "1/24 札幌 → JR → 新千歳 → 桃園",
}
SEG = ["道央道 110 km／1.5 h", "30 km／40 分", "ルスツ滑雪",
       "国道230 80 km／1.5 h", "JR 快速 37 分"]


def _bpts(dd, n=60):
    ps = dd.replace("M", "").replace(" Q", " ").split()
    p0 = tuple(map(float, ps[0].split(",")))
    c_ = tuple(map(float, ps[1].split(",")))
    p2 = tuple(map(float, ps[2].split(",")))
    return [
        (
            (1 - t / n) ** 2 * p0[0]
            + 2 * (1 - t / n) * (t / n) * c_[0]
            + (t / n) ** 2 * p2[0],
            (1 - t / n) ** 2 * p0[1]
            + 2 * (1 - t / n) * (t / n) * c_[1]
            + (t / n) ** 2 * p2[1],
        )
        for t in range(n + 1)
    ]


def screen(pt, layout):
    _, _, scale, tx, ty = LAYOUTS[layout]
    return (round(pt[0] * scale + tx, 2), round(pt[1] * scale + ty, 2))


def inside(pt, box, pad=0):
    x, y = pt
    x0, x1, y0, y1 = box
    return x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad


def check_geometry(layout):
    """保留原自檢：箭頭淨空、線身/字框、徽章/節點/他日路線、兩兩避讓。
    卡片取整個實心背景 bbox，比原文字估算更保守；在實際 viewBox 座標檢查。
    圖例已移至 SVG 外，天然不會與線身重疊。
    """
    width, height, scale, _, _ = LAYOUTS[layout]
    boxes = [(x, x+w, y, y+48) for x, y, w, _, _ in LABELS[layout].values()]
    curves = {nm: [screen(p, layout) for p in _bpts(dd, 160)] for nm, dd in ROUTES}
    points = {k: screen(C[k], layout) for k in NODES_R}
    for nm, target, tip in zip(
        ["d1", "d2", "d4b", "d5"], ["toya", "rusutsu", "sapporo", "chitose"],
        [e1, e2, e4b, e5],
    ):
        gap = math.dist(tip, C[target]) - 11
        assert gap >= 1, f"{layout}: {nm} 箭頭被節點蓋住"
        assert all(not inside(screen(tip, layout), box, 3) for box in boxes), f"{layout}: 箭頭壓字"
        print(f"  {layout} {nm} 箭頭淨空 {gap:.1f} 投影單位")
    for nm, pts in curves.items():
        assert all(not inside(p, box) for p in pts for box in boxes), f"{layout}: {nm} 穿過標籤卡"
    for i, a in enumerate(boxes):
        assert 0 <= a[0] < a[1] <= width and 0 <= a[2] < a[3] <= height
        for b in boxes[i+1:]:
            assert not (a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]), f"{layout}: 標籤重疊"
    own = {"D1": {"d1"}, "D2": {"d2"}, "D3": set(), "D4": {"d4a", "d4b"}, "D5": {"d5"}}
    badges = list(BADGES[layout].items())
    for i, (name, pos) in enumerate(badges):
        assert 12 <= pos[0] <= width-12 and 12 <= pos[1] <= height-12
        assert all(not inside(pos, box, 14) for box in boxes), f"{layout}: {name} 壓標籤"
        for key, pt in points.items():
            assert math.dist(pos, pt) - 12 - NODES_R[key]*scale >= 4, f"{layout}: {name} 壓節點 {key}"
        for nm, pts in curves.items():
            if nm not in own[name]:
                assert min(math.dist(pos, p) for p in pts) >= 14, f"{layout}: {name} 貼他日線 {nm}"
        for _, other in badges[i+1:]:
            assert math.dist(pos, other) >= 28, f"{layout}: 徽章重疊"
    # 原投影上的最小間距門檻維持 5；手機輸出再確保可辨識淨空。
    separation = min(math.dist(a, b) for a in _bpts(d1) for b in _bpts(d5))
    assert separation >= 5 and separation*scale >= 4, "機場進出線太近"
    print(f"  {layout} 機場進出線間距 {separation*scale:.1f}px；標籤／徽章／線身自檢通過")


def render_map(layout):
    w, h, scale, tx, ty = LAYOUTS[layout]
    prefix = f"hokkaido-{layout}"
    out = [f'''    <svg class="geo-map geo-{layout}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{prefix}-title {prefix}-desc">
      <title id="{prefix}-title">道央五日行程：新千歳空港、洞爺湖温泉、ルスツリゾート、札幌</title>
      <desc id="{prefix}-desc">D1 新千歳至洞爺湖，D2 至ルスツ，D3 留在ルスツ滑雪，D4 經中山峠至札幌與円山動物園，D5 搭 JR 返回新千歳。實線自駕、虛線 JR。真實點位與海岸線，路線為示意；下方五日日次卡可跳至行程。</desc>
      <defs>
        <marker id="{prefix}-drive" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--gm-drive)"/></marker>
        <marker id="{prefix}-rail" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--gm-rail)"/></marker>
      </defs>
      <g class="geo-geography" transform="translate({tx} {ty}) scale({scale})">
        <g class="geo-land" fill="var(--gm-land)" stroke="var(--gm-coast)" stroke-width="1.2">
{land_paths}
        </g>
        <g fill="none" stroke-width="3" stroke-linecap="round">''']
    for name, dd in ROUTES:
        mode = "rail" if name == "d5" else "drive"
        dash = ' stroke-dasharray="7 6"' if mode == "rail" else ""
        marker = "" if name == "d4a" else f' marker-end="url(#{prefix}-{mode})"'
        out.append(f'          <path data-route-segment="{name}" d="{dd}" stroke="var(--gm-{mode})"{dash}{marker}/>')
    out.append("        </g>")
    for key, r in NODES_R.items():
        x, y = C[key]
        out.append(f'        <circle data-station="{key}" cx="{x}" cy="{y}" r="{r}" fill="var(--gm-paper)" stroke="var(--gm-drive)" stroke-width="{4 if r == 9 else 2}"/>')
    out.append("      </g>")
    # 標籤連接線只表達點位對應；細灰線，與交通實線/虛線明確分層。
    for key, (x, y, width, title, sub) in LABELS[layout].items():
        px, py = screen(C[key], layout)
        ex = min(max(px, x+8), x+width-8)
        ey = y+48 if py > y+48 else y if py < y else py
        dist = math.hypot(ex-px, ey-py)
        radius = 12*scale
        sx, sy = px+(ex-px)*radius/dist, py+(ey-py)*radius/dist
        out.append(f'      <path class="geo-leader" d="M{sx:.2f},{sy:.2f} L{ex},{ey}" fill="none" stroke="var(--gm-coast)" stroke-width="1"/>')
        out.append(f'''      <g class="geo-station-label" data-label="{key}">
        <rect x="{x}" y="{y}" width="{width}" height="48" rx="9" fill="var(--gm-paper)" stroke="var(--gm-border)"/>
        <text x="{x+10}" y="{y+20}" font-size="15" font-weight="750" fill="var(--gm-ink)">{title}</text>
        <text x="{x+10}" y="{y+38}" font-size="12" fill="var(--gm-muted)">{sub}</text>
      </g>''')
    for name, (x, y) in BADGES[layout].items():
        out.append(f'''      <g class="geo-badge"><circle cx="{x}" cy="{y}" r="12" fill="var(--gm-badge)"/><text x="{x}" y="{y+4}" text-anchor="middle" font-size="12" font-weight="750" fill="var(--gm-badge-ink)">{name}</text></g>''')
    out.append("    </svg>")
    return "\n".join(out)


def render():
    maps = "\n".join(render_map(layout) for layout in LAYOUTS)
    cards = []
    destinations = ["新千歳 → 洞爺湖", "洞爺湖 → ルスツ", "ルスツ滞在",
                    "ルスツ → 札幌", "札幌 → 新千歳"]
    notes = ["自駕", "自駕", "D3 當日不移動", "自駕・中山峠・円山動物園", "JR 快速エアポート"]
    for i, (destination, segment, note) in enumerate(zip(destinations, SEG, notes), 1):
        cards.append(f'''    <a class="geo-day-card" href="#day{i}" aria-label="D{i} {TITLES[f'D{i}']}，查看當日行程">
      <span class="geo-day-num">D{i}</span><span class="geo-day-copy"><strong>{destination}</strong><span>{segment}</span><small>{note}</small></span><span class="geo-day-arrow" aria-hidden="true">↗</span>
    </a>''')
    return '''  <!-- hokkaido-map:generated:start -->
  <div class="geo-panel">
    <div class="geo-intro"><span>四站・五天冬旅</span><span>道央路線示意 · 非精確導航</span></div>
    <div class="geo-legend" aria-label="交通圖例">
      <span><i class="geo-swatch" aria-hidden="true"></i>自駕（租車）</span>
      <span><i class="geo-swatch geo-rail" aria-hidden="true"></i>JR 快速エアポート</span>
    </div>
    <div class="mapbox">
''' + maps + '''
    </div>
    <p class="geo-map-note">D3 留在ルスツ滑雪；地圖下方可依日次查看完整行程。</p>
  </div>
  <nav class="geo-days" aria-label="地圖五日行程跳轉">
''' + "\n".join(cards) + '''
  </nav>
  <!-- hokkaido-map:generated:end -->'''


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="寫入新的 HTML snippet；省略則只自檢，不寫檔")
    args = parser.parse_args()
    for layout in LAYOUTS:
        check_geometry(layout)
    print(f"rings={len(rings)}; pts={sum(len(r) for _, r in rings)}; geometry 自檢通過")
    if args.output:
        # x 模式拒絕覆蓋：尤其不可覆蓋 repo 內既有的 untracked snippet。
        with args.output.open("x", encoding="utf-8") as out:
            out.write(render() + "\n")
        print(f"generated: {args.output}")


if __name__ == "__main__":
    main()

# ---- 經緯度來源 ----
# 新千歳空港 42.7752N 141.6923E（GSI／AIS Japan RJCC 機場基準點）
# 洞爺湖温泉   42.566N 140.822E（洞爺湖町洞爺湖温泉，乃の風リゾート 一帶湖南岸）
# ルスツリゾート 42.744N 140.892E（虻田郡留寿都村泉川13）
# 札幌市中心   43.062N 141.354E（大通—札幌站之間，中央区北1条一帶）
# 中山峠       42.863N 141.033E（国道230 札幌市南区定山渓〜喜茂別町境，海拔 835m）
# 円山動物園   43.0543N 141.3117E（札幌市中央区宮ケ丘3-1）
