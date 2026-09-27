"""從 japan.geojson 生成真實比例的九州行程 SVG（#geomap 內容）。"""
import json, math
from pathlib import Path

SC = Path(__file__).parent
d = json.load(open(SC / "japan.geojson"))

KYUSHU_IDS = {40, 41, 42, 43, 44, 45, 46}  # 福岡佐賀長崎熊本大分宮崎鹿兒島
prefs = [f for f in d["features"] if f["properties"]["id"] in KYUSHU_IDS]

# ---- ring 工具 ----
def ring_area(r):  # 近似度數面積（絕對值）
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

# ---- 蒐集 ring（過濾小離島；保留本島與天草級） ----
AREA_MIN = 0.008  # 度²，過濾五島/壹岐/對馬/種子島等
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

# ---- 投影（等距圓柱，cos 校正） ----
lats = [p[1] for _, r in rings for p in r]
lons = [p[0] for _, r in rings for p in r]
lat0, lat1 = 32.35, max(lats)  # 視窗下緣裁在 32.35°N（震央下方留漣漪與標籤空間）
lon0, lon1 = min(lons), max(lons)
cosf = math.cos(math.radians((lat0 + lat1) / 2))
W = 740
PADL, PADR, PADT, PADB = 26, 148, 40, 28   # 右側留標籤空間
S = (W - PADL - PADR) / ((lon1 - lon0) * cosf)
H = int((lat1 - lat0) * S + PADT + PADB)

def XY(lon, lat):
    return (round(PADL + (lon - lon0) * cosf * S, 1), round(PADT + (lat1 - lat) * S, 1))

def path_of(r):
    pts = [XY(*p) for p in r]
    return "M" + " L".join(f"{x},{y}" for x, y in pts) + " Z"

land_paths = "\n".join(
    f'      <path d="{path_of(r)}"/>' for _, r in rings
)

# ---- 地點（真實經緯度） ----
P = {
    "airport":  (130.451, 33.585),
    "hakata":   (130.421, 33.590),
    "uminaka":  (130.354, 33.660),
    "kokura":   (130.883, 33.887),
    "htb":      (129.789, 33.086),
    "harmony":  (131.559, 33.398),
    "beppu":    (131.474, 33.271),
    "safari":   (131.406, 33.346),
    "kanryu":   (130.273, 33.313),
    "kiyama":   (130.529, 33.443),
    "imagawa":  (130.968, 33.685),
    "kumamoto": (130.689, 32.790),
    "aso":      (131.045, 32.884),
    "takachiho":(131.308, 32.711),
    "epicenter":(130.72, 32.55),
}
C = {k: XY(*v) for k, v in P.items()}

def q(a, b, bend=0.18, side=1, r_start=0.0, r_end=0.0):
    """兩點間 quadratic 曲線；r_start/r_end 為起訖端沿曲線的絕對截斷半徑
    （箭頭尖剛好停在節點圓外，不再用百分比 lerp——百分比對長段縮過頭、短段縮不夠）。
    回傳 (path d, 原曲線中點, 截斷後終點)。"""
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
    if v - u < 0.05:  # 段太短兩端截不下：保留中段最小可見弧
        u, v = min(u, .40), max(v, .60)
    # De Casteljau：取 [u,v] 子曲線的控制點
    q0, q2 = B(u), B(v)
    dbu = (2*(1-u)*(cx-x1) + 2*u*(x2-cx), 2*(1-u)*(cy-y1) + 2*u*(y2-cy))
    q1 = (q0[0] + (v-u)*dbu[0]/2, q0[1] + (v-u)*dbu[1]/2)
    d = f"M{round(q0[0],1)},{round(q0[1],1)} Q{round(q1[0],1)},{round(q1[1],1)} {round(q2[0],1)},{round(q2[1],1)}"
    mid = B(.5)
    return d, (round(mid[0],1), round(mid[1],1)), (round(q2[0],1), round(q2[1],1))

def q2seg(a, b, bend=0.18, side=1, r_start=0.0, r_end=0.0):
    """同 q()，但把截斷後曲線於中點一分為二——前段掛 marker-end 形成「中段箭頭」。
    用於終點區太擠放不下箭頭的段（如 D2：海之中道圓貼著博多圓與文字）。
    回傳 (前段 d, 後段 d, 原曲線中點, 分割點)。"""
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
    q0, q2 = B(u), B(v)
    dbu = (2*(1-u)*(cx-x1) + 2*u*(x2-cx), 2*(1-u)*(cy-y1) + 2*u*(y2-cy))
    q1 = (q0[0] + (v-u)*dbu[0]/2, q0[1] + (v-u)*dbu[1]/2)
    m01 = ((q0[0]+q1[0])/2, (q0[1]+q1[1])/2)
    m12 = ((q1[0]+q2[0])/2, (q1[1]+q2[1])/2)
    bm  = ((m01[0]+m12[0])/2, (m01[1]+m12[1])/2)
    r = lambda p: (round(p[0], 1), round(p[1], 1))
    q0, q1, q2, m01, m12, bm = map(r, (q0, q1, q2, m01, m12, bm))
    df = f"M{q0[0]},{q0[1]} Q{m01[0]},{m01[1]} {bm[0]},{bm[1]}"
    db = f"M{bm[0]},{bm[1]} Q{m12[0]},{m12[1]} {q2[0]},{q2[1]}"
    mid = r(B(.5))
    return df, db, mid, bm

def shift(pt, dx, dy):
    return (round(pt[0] + dx, 1), round(pt[1] + dy, 1))

def lerp(a, b, t):
    return (round(a[0]+(b[0]-a[0])*t,1), round(a[1]+(b[1]-a[1])*t,1))

# 各端截斷半徑＝節點圓外緣（r＋stroke/2）＋2~3px 箭頭餘裕
segs = []
d1, m1, e1   = q(C["airport"], C["htb"],     .10, -1, r_start=6,  r_end=14)
# D2：箭頭放中段（海面上）——海之中道圓下緣貼博多文字框（淨空 0）、與博多圓重疊
# （圓心距 17.1 < 外緣和 19.8），終點區放不下箭頭；uminaka→hakata 段同理不畫線。
d2af, d2ab, m2, e2a = q2seg(C["htb"], C["uminaka"], .13, -1, r_start=12, r_end=0)
d3, m3, e3   = q(C["hakata"], C["kokura"],   .10, -1, r_start=13, r_end=14)
# D4：小倉→別府一條線。Harmonyland（距別府 27.7px）與 Safari（17.9px）在此比例尺
# 與別府三圓相貼，獨立節點必然疊成一團——併入別府節點副標表達。
d4, m4, e4   = q(C["kokura"], C["beppu"],    .13, -1, r_start=13, r_end=14)
# d5 不畫線：beppu 圓（外緣11）與 safari 圓（外緣7.5）圓心僅距 17.9px，兩圓重疊，
# 真實比例下無可見線段可畫；D5 徽章（可點）＋Safari 旁「D5 動物園」已表達往返。
_, m5, _     = q(C["beppu"], C["safari"],    .55,  1)
d6, m6, e6   = q(C["beppu"], C["hakata"],    .22, -1, r_start=13, r_end=16)   # 終點多留：避開「福岡機場」字頭

gx1, _, _ = q(C["hakata"], C["kumamoto"], .12, 1)
gx2, _, _ = q(C["kumamoto"], C["aso"], .15, -1)
gx3, _, _ = q(C["aso"], C["takachiho"], .15, 1)
gx4, _, _ = q(C["takachiho"], C["beppu"], .12, 1)

# ---- 響應式分區；所有地形、點位、路線都使用上述 XY 投影 ----
from html import escape
import argparse
import hashlib
import re

# viewBox 統一為 320 × 340，320px 手機仍可讀主地名；不縮小字來塞景點。
PANELS = {
    "north": {
        "title": "北九州・改線後全程", "sub": "福岡、豪斯登堡、小倉與別府",
        "affine": (.85, -164, -83),
        "nodes": ["hakata", "htb", "kokura", "beppu"],
        "labels": [
            ("hakata", 8, 10, 145, "福岡・博多", "D2–D3・D6–D8"),
            ("kokura", 176, 10, 136, "小倉", "D3"),
            ("htb", 8, 260, 136, "豪斯登堡", "D1–D2"),
            ("beppu", 176, 260, 136, "別府溫泉", "D4–D6"),
        ],
        "routes": [("d1", d1), ("d2a", d2af), ("d2b", d2ab), ("d3", d3), ("d4", d4), ("d6", d6)],
    },
    "fukuoka": {
        "title": "福岡・海之中道放大", "sub": "D2・D3・D6・D7・D8",
        "affine": (7, -2130, -1580),
        "nodes": ["uminaka", "hakata", "airport"],
        "labels": [
            ("uminaka", 8, 20, 230, "海之中道", "D2 海洋世界・D7 泳池"),
            ("hakata", 8, 260, 140, "福岡・博多", "D3 KidZania"),
            ("airport", 172, 260, 140, "福岡機場", "D1 抵達・D8 返台"),
        ],
        "routes": [
            ("d2-d7", q(C["uminaka"], C["hakata"], .08, 1, r_start=1.2, r_end=1.5)[0]),
            ("d8", q(C["hakata"], C["airport"], .12, -1, r_start=1.2, r_end=1.5)[0]),
        ],
    },
    "beppu": {
        "title": "別府・樂園與動物園放大", "sub": "D4–D6・別府連住兩晚",
        "affine": (5, -2292, -1332),
        "nodes": ["harmony", "safari", "beppu"],
        "labels": [
            ("harmony", 167, 38, 145, "三麗鷗樂園", "D4 Harmonyland"),
            ("safari", 8, 85, 145, "野生動物園", "D5 African Safari"),
            ("beppu", 144, 284, 168, "別府溫泉", "杉乃井・D4–D6"),
        ],
        "routes": [
            ("d4-local", q(C["harmony"], C["beppu"], .10, -1, r_start=1.6, r_end=2)[0]),
            ("d5-return", q(C["beppu"], C["safari"], .10, 1, r_start=1.6, r_end=2)[0]),
        ],
    },
    "cancelled": {
        "title": "已取消原案・不屬於實際行程", "sub": "7/28 地震後取消，僅保留原案對照",
        "affine": (1.15, -265, -270),
        "nodes": ["kumamoto", "aso", "takachiho", "epicenter"],
        "labels": [
            ("kumamoto", 8, 154, 120, "熊本", "已取消"),
            ("aso", 176, 40, 136, "阿蘇", "已取消"),
            ("takachiho", 176, 284, 136, "高千穗", "已取消"),
            ("epicenter", 8, 284, 150, "7/28 震央", "M7.1・宇城市/氷川町"),
        ],
        "routes": [("cancelled-1", gx1), ("cancelled-2", gx2), ("cancelled-3", gx3), ("cancelled-4", gx4)],
    },
}
DAYS = [
    ("8/1", "福岡機場 → 豪斯登堡", "抵達・豪斯登堡夜景"),
    ("8/2", "豪斯登堡 → 海之中道 → 博多", "海洋世界"),
    ("8/3", "福岡 → 小倉", "KidZania 職業體驗"),
    ("8/4", "小倉 → 三麗鷗樂園 → 別府", "Harmonyland・杉乃井"),
    ("8/5", "別府 ⇄ 野生動物園", "African Safari・杉乃井"),
    ("8/6", "別府 → 福岡", "海地獄・筑紫野公園"),
    ("8/7", "福岡・海之中道", "泳池・福岡市科學館"),
    ("8/8", "福岡機場 → 返台", "還車・返台"),
]
START = "<!-- trip-map:generated:start -->"
END = "<!-- trip-map:generated:end -->"


def screen(key, panel):
    s, tx, ty = PANELS[panel]["affine"]
    x, y = C[key]
    return x*s+tx, y*s+ty


def bezier(dd):
    values = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", dd)))
    x0,y0,cx,cy,x1,y1 = values
    return [((1-t/120)**2*x0+2*(1-t/120)*(t/120)*cx+(t/120)**2*x1,
             (1-t/120)**2*y0+2*(1-t/120)*(t/120)*cy+(t/120)**2*y1) for t in range(121)]


def frame_svg(name):
    panel = PANELS[name]
    s, tx, ty = panel["affine"]
    cancelled = name == "cancelled"
    ink = "muted" if cancelled else "route"
    paths = "\n".join(f'<path d="{path_of(r)}"/>' for _,r in rings)
    out = [f'''<svg class="tm-detail" viewBox="0 0 320 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="kyushu-{name}-title">
<title id="kyushu-{name}-title">{panel["title"]}。{panel["sub"]}。同一地理投影，路線為示意。</title>
<defs><marker id="kyushu-{name}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10Z" fill="var(--tm-{ink})"/></marker></defs>
<g class="tm-geography" transform="translate({tx} {ty}) scale({s})">
<g class="tm-land" fill="var(--tm-land)" stroke="var(--tm-coast)" stroke-width="{.8/s}">{paths}</g>''']
    for route, dd in panel["routes"]:
        dash = ' stroke-dasharray="6 5"' if cancelled else ""
        marker = "" if cancelled or route == "d2b" else f' marker-end="url(#kyushu-{name}-arrow)"'
        # 短段仍以原座標連接；D5 來回不拿虛線冒充另一交通方式。
        if route == "d5-return":
            marker += f' marker-start="url(#kyushu-{name}-arrow)"'
        out.append(f'<path data-route="{route}" d="{dd}" fill="none" stroke="var(--tm-{ink})" stroke-width="{2.5/s}" vector-effect="none"{dash}{marker}/>')
    for key in panel["nodes"]:
        x,y = C[key]
        if key == "epicenter":
            out.append(f'<path data-station="{key}" d="M{x-5/s},{y-5/s} l{10/s},{10/s} m0,{-10/s} l{-10/s},{10/s}" stroke="var(--tm-muted)" stroke-width="{2/s}" fill="none"/>')
        else:
            out.append(f'<circle data-station="{key}" cx="{x}" cy="{y}" r="{5/s}" fill="var(--tm-paper)" stroke="var(--tm-{ink})" stroke-width="{2/s}"/>')
    # 建議休息站只在全程圖顯示空心小點；名稱保留在圖下說明。
    if name == "north":
        for key in ("kanryu","kiyama","imagawa"):
            x,y = C[key]
            out.append(f'<circle data-rest="{key}" cx="{x}" cy="{y}" r="{2.5/s}" fill="var(--tm-paper)" stroke="var(--tm-muted)" stroke-width="{1/s}"><title>{dict(kanryu="金立 SA",kiyama="基山 PA",imagawa="今川 PA")[key]}（建議休息站）</title></circle>')
    out.append("</g>")
    for key,x,y,w,title,sub in panel["labels"]:
        px,py = screen(key,name)
        ex = max(x+8,min(px,x+w-8))
        ey = y if py < y else y+46 if py > y+46 else py
        dist = math.hypot(ex-px,ey-py)
        assert dist > 7, f"{name}/{key} label covers node"
        sx,sy = px+(ex-px)*7/dist, py+(ey-py)*7/dist
        out.append(f'''<path class="tm-leader" d="M{sx:.2f},{sy:.2f} L{ex:.2f},{ey:.2f}" stroke="var(--tm-muted)" stroke-width="1.2" fill="none"/>
<g class="tm-label" data-label="{key}"><rect x="{x}" y="{y}" width="{w}" height="46" rx="8" fill="var(--tm-paper)" stroke="var(--tm-border)"/>
<text x="{x+9}" y="{y+21}" fill="var(--tm-ink)" font-size="18" font-weight="800">{escape(title)}</text>
<text x="{x+9}" y="{y+38}" fill="var(--tm-muted)" font-size="13">{escape(sub)}</text></g>''')
    out.append("</svg>")
    return "\n".join(out)


def locator():
    # 本島、天草及周邊近海島嶼；不把對馬或南方列島拉進空白。
    visible = [(pid,r) for pid,r in rings if
               max(p[1] for p in r) >= 30.95 and min(p[1] for p in r) <= 34.05
               and max(p[0] for p in r) >= 129.35 and min(p[0] for p in r) <= 132.15]
    pts = [XY(*p) for _,r in visible for p in r]
    minx,maxx = min(x for x,y in pts),max(x for x,y in pts)
    miny,maxy = min(y for x,y in pts),max(y for x,y in pts)
    s = min(276/(maxx-minx),286/(maxy-miny))
    tx,ty = (320-(maxx-minx)*s)/2-minx*s, 24-miny*s
    out = [f'''<svg class="tm-locator" viewBox="0 0 320 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="九州完整本島輪廓，框內為北九州旅行區">
<g class="tm-geography" transform="translate({tx} {ty}) scale({s})">
<g class="tm-land" fill="var(--tm-land)" stroke="var(--tm-coast)" stroke-width="{.9/s}">''']
    out.extend(f'<path d="{path_of(r)}"/>' for _,r in visible)
    out.append("</g>")
    # 用全程圖所用點位的包絡框顯示旅行區；不改動任何地理座標。
    keys = ["htb","hakata","airport","uminaka","kokura","harmony","beppu","safari"]
    xs,ys = [C[k][0] for k in keys],[C[k][1] for k in keys]
    x0,y0,x1,y1 = min(xs)-18,min(ys)-18,max(xs)+18,max(ys)+18
    out.append(f'<rect data-travel-window="true" x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="var(--tm-route)" fill-opacity=".12" stroke="var(--tm-route)" stroke-width="{2/s}"/>')
    for _,dd in PANELS["north"]["routes"]:
        out.append(f'<path d="{dd}" fill="none" stroke="var(--tm-route)" stroke-width="{1.4/s}"/>')
    out.append(f'''</g>
<text x="157" y="217" text-anchor="middle" fill="var(--tm-ink)" font-size="26" font-weight="800">九州</text>
<rect x="10" y="10" width="181" height="32" rx="7" fill="var(--tm-paper)"/>
<text x="20" y="32" fill="var(--tm-ink)" font-size="17" font-weight="750">框內：北九州旅行區</text>
<text x="12" y="230" fill="var(--tm-muted)" font-size="14">東海</text>
<text x="258" y="270" fill="var(--tm-muted)" font-size="14">太平洋</text>
<path d="M296,67 V32 M290,41 L296,32 L302,41" fill="none" stroke="var(--tm-muted)" stroke-width="1.5"/>
<text x="296" y="23" text-anchor="middle" fill="var(--tm-muted)" font-size="13">北 N</text>
</svg>''')
    for x,y in pts:
        assert 15 <= x*s+tx <= 305 and 20 <= y*s+ty <= 313, "九州輪廓裁切"
    return "\n".join(out)


def render():
    out = [START, '''<div class="tm-intro"><b>九州八日・北線旅行</b><span>真實點位與海岸輪廓 · 路線示意，非精確導航</span></div>
<div class="tm-legend"><span><i></i>自駕・改線後行程</span><span><i class="tm-rest"></i>建議休息站</span><span>細灰線連接地名與站點</span></div>
<div class="tm-atlas"><figure><figcaption><b>九州全島定位</b><span>從完整島形看本次旅行範圍</span></figcaption>''',
           locator(), "</figure><figure><figcaption><b>北九州全程路線</b><span>D1–D8・福岡起訖，經豪斯登堡、小倉與別府</span></figcaption>",
           frame_svg("north"), "</figure></div>",
           '<p class="tm-note">空心小點為原行程建議休息站：金立 SA、基山 PA、今川 PA；停靠以當日需求為準。福岡周邊及別府密集景點，見下方放大圖。</p>',
           '<div class="tm-local">']
    for name in ("fukuoka","beppu"):
        p=PANELS[name]
        out.extend([f'<figure><figcaption><b>{p["title"]}</b><span>{p["sub"]}</span></figcaption>',frame_svg(name),"</figure>"])
    out.append('</div><nav class="tm-days" aria-label="九州八日日次跳轉">')
    for i,(date,destination,note) in enumerate(DAYS,1):
        reduced = """if(!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&matchMedia('(prefers-reduced-motion: reduce)').matches){event.preventDefault();const t=document.querySelector(this.hash);history.pushState(null,'',this.hash);t.setAttribute('tabindex','-1');t.focus({preventScroll:true});t.scrollIntoView({behavior:'instant',block:'start'});t.addEventListener('blur',()=>t.removeAttribute('tabindex'),{once:true});}"""
        out.append(f'<a href="#day{i}" class="geo-day-card" onclick="{reduced}"><span class="tm-badge">D{i}</span><span><strong>{destination}</strong><small>{date} · {note}</small></span></a>')
    out.extend(['''</nav>
<details class="tm-cancelled"><summary>已取消原案：熊本・阿蘇・高千穗（7/28 地震後改線）</summary>
<p>以下灰虛線與取消地點僅作原案對照，不屬於實際行程。✕ 為原手帖記錄的 7/28 震央（M7.1，宇城市/氷川町）。</p>
<div class="tm-legend"><span><i class="tm-cancel-line"></i>已取消原路線</span></div>''',
                frame_svg("cancelled"), '<a class="tm-history" href="#earthquake">查看地震改線記事與取消原案</a></details>',
                '<p class="tm-note">全程圖、分區圖與定位圖共用同一地理投影；路線僅連接行程站點，實際導航請使用每日卡的「當日路線」。</p>',
                END])
    return "\n".join(out)+"\n"


def check():
    for name,panel in PANELS.items():
        s,tx,ty=panel["affine"]
        boxes=[]
        for key,x,y,w,title,sub in panel["labels"]:
            assert 0<=x<x+w<=320 and 0<=y<y+46<=340
            assert len(title)*18 <= w-18, f"主標溢出 {name}/{key}"
            px,py=screen(key,name)
            assert 6<px<314 and 6<py<334, f"節點裁切 {name}/{key}"
            boxes.append((x,x+w,y,y+46))
        for i,a in enumerate(boxes):
            for b in boxes[i+1:]:
                assert not(a[0]<b[1] and b[0]<a[1] and a[2]<b[3] and b[2]<a[3]), f"標籤重疊 {name}"
        for route,dd in panel["routes"]:
            for px,py in bezier(dd):
                x,y=px*s+tx,py*s+ty
                assert all(not(a<x<b and c<y<d) for a,b,c,d in boxes), f"路線穿過標籤 {name}/{route}"
        frame_svg(name)
        print(f"PASS {name}: 原投影點位、字框邊界/避讓、路線/標籤淨空")
    # 原箭頭端點與幾何維持檢查；新顯示節點半徑為 5px。
    for key,tip in [("htb",e1),("uminaka",e2a),("kokura",e3),("beppu",e4),("hakata",e6)]:
        assert math.dist(tip,C[key])*.85-6 >= 1, f"箭頭壓節點 {key}"
    locator()
    result=render()
    assert all(f'href="#day{i}"' in result for i in range(1,9))
    # 取消段只能存在於已取消 details 內。
    actual=result.split('<details class="tm-cancelled">')[0]
    assert all(f'data-station="{k}"' not in actual for k in ("kumamoto","aso","takachiho","epicenter"))
    print("PASS 九州全島無裁切；取消原案隔離；八日原生鍵盤錨點；零外部依賴")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,help="輸出至新檔；x 模式拒絕覆蓋，省略只自檢")
    parser.add_argument("--check-page",type=Path,help="檢查 HTML 生成區與產物逐位元一致")
    parser.add_argument("--baseline",type=Path,help="搭配 --check-page 檢查地圖/CSS 以外逐位元不變")
    args=parser.parse_args()
    check()
    generated=render()
    if args.check_page:
        page=args.check_page.read_text()
        embedded=page[page.index(START):page.index(END)+len(END)]+"\n"
        assert embedded==generated,"生成區不同步"
        if args.baseline:
            old=args.baseline.read_text()
            def outside(text):
                text=re.sub(r"/\* trip-map:styles:start \*/.*?/\* trip-map:styles:end \*/\n?","",text,flags=re.S)
                return re.sub(r'<section id="geomap".*?</section>',"",text,flags=re.S)
            assert outside(page)==outside(old),"地圖外內容有變"
            marker='<article class="day" id="day1">'
            assert page[page.index(marker):]==old[old.index(marker):],"day1 後有變"
            print("PASS 地圖外逐位元不變；day1-end SHA256",hashlib.sha256(page[page.index(marker):].encode()).hexdigest())
        print("PASS HTML 生成區逐位元同步")
    if args.output:
        with args.output.open("x",encoding="utf-8") as stream:
            stream.write(generated)
        print("generated:",args.output)


if __name__=="__main__":
    main()
