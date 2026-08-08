"""從 japan.geojson 生成東京迪士尼行程 SVG（2025-tokyo-disney #geomap 內容）。
工具與 gen_kyushu_map.py / gen_ski_map.py 同源。東京灣區聚焦：
上野吸收淺草/晴空塔（11/20px 內），台場・豐洲併一節點（17.6px）。"""
import json, math
from pathlib import Path

SC = Path(__file__).parent
d = json.load(open(SC / "japan.geojson"))

PREF_IDS = {8, 11, 12, 13, 14}
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
            simp = rdp(outer[:mid + 1], 0.002)[:-1] + rdp(outer[mid:], 0.002)
            rings.append((f["properties"]["id"], simp))

# ---- 投影（手動窗：東京灣區＋成田） ----
lat0, lat1 = 35.42, 35.98
lon0, lon1 = 139.60, 140.55
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
    "narita":    (140.386, 35.772),
    "maihama":   (139.879, 35.632),   # 東京迪士尼度假區（兩飯店都在區內）
    "odaiba":    (139.782, 35.638),   # 台場・豐洲 teamLab 中點（兩地 17.6px 併）
    "ueno":      (139.777, 35.712),   # &Here 上野；淺草 11px、晴空塔 20px 在旁
    "shinagawa": (139.736, 35.628),   # Maxell Aqua Park
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

# ---- 路線 ----
d1,  m1,  e1  = q(C["narita"], C["maihama"],   .13, -1, r_start=9,  r_end=14)   # 抵達日（彎南沿灣）
d4a, m4a, e4a = q(C["maihama"], C["odaiba"],   .16,  1, r_start=13, r_end=12)   # 舞浜 → 台場豐洲
d4b, m4b, e4b = q(C["odaiba"], C["ueno"],      .14,  1, r_start=12, r_end=14)   # 台場 → 上野
d5,  m5,  e5  = q(C["ueno"], C["shinagawa"],   .25, -1, r_start=13, r_end=12)   # 上野 → 品川（彎東側進，避台場文字帶）
d7,  m7,  e7  = q(C["ueno"], C["narita"],      .13, -1, r_start=13, r_end=11)   # 回程（彎北內陸，與 d1 分流）

_anchor = {
    "D1": m1, "D2": shift(C["maihama"], -30, -20), "D3": shift(C["maihama"], 30, -20),
    "D4": m4a, "D5": m5, "D6": shift(C["ueno"], -32, 2), "D7": m7,
}
_pinned_pos = {"D2": shift(C["maihama"], -30, -20), "D3": shift(C["maihama"], 30, -20),
               "D6": shift(C["ueno"], -32, 2)}
_nodesR = {"narita": 7, "maihama": 9, "odaiba": 7, "ueno": 9, "shinagawa": 7}

def _bb(cx, cy, anchor, w, size):
    if anchor == "start":  x0, x1 = cx, cx + w
    elif anchor == "end":  x0, x1 = cx - w, cx
    else:                  x0, x1 = cx - w / 2, cx + w / 2
    return (x0, x1, cy - size, cy + 3)

_texts = [
    _bb(C["narita"][0]+13,  C["narita"][1]+5,   "start",  86, 12),
    _bb(C["maihama"][0],    C["maihama"][1]+26, "middle", 65, 13),
    _bb(C["maihama"][0],    C["maihama"][1]+40, "middle", 150, 10.5),
    _bb(C["odaiba"][0]-18,  C["odaiba"][1]-21,  "end",  78, 12.5),
    _bb(C["odaiba"][0]-18,  C["odaiba"][1]-8,   "end",  90, 10.5),
    _bb(C["ueno"][0]-13,    C["ueno"][1]-12,    "end",  26, 13),   # 主標放圓左上斜角（西北無線帶；東北是 d7 出線）
    _bb(C["ueno"][0]+15,    C["ueno"][1]+8,     "start",  150, 10.5),
    _bb(C["shinagawa"][0]-12, C["shinagawa"][1]+2,  "end", 26, 13),
    _bb(C["shinagawa"][0]-12, C["shinagawa"][1]+15, "end", 68, 10.5),
]
def _hits_text(x, y, pad=4):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 11 - pad < x < x1 + 11 + pad and y0 - 11 - pad < y < y1 + 11 + pad:
            return True
    return False

_arrow_tips = [e1, e4a, e4b, e5, e7]

def _ok(pt, placed):
    x, y = pt
    if not (20 <= x <= W - 20 and 20 <= y <= H - 10):
        return False
    for tp in _arrow_tips:
        if math.hypot(x - tp[0], y - tp[1]) < 24:
            return False
    for nn, rr in _nodesR.items():
        if math.hypot(x - C[nn][0], y - C[nn][1]) - 11 - rr < 6:
            return False
    for q2_ in placed.values():
        if math.hypot(x - q2_[0], y - q2_[1]) < 26:
            return False
    if _hits_text(x, y):
        return False
    return True

B = {}
for name, anc in _anchor.items():
    if name in _pinned_pos:
        B[name] = _pinned_pos[name]
        continue
    if _ok(anc, B):
        B[name] = anc
        continue
    best = None
    for r in (10, 16, 22, 28, 36, 44, 54, 64):
        for k in range(16):
            a = k * math.pi / 8
            cand = (round(anc[0] + r * math.cos(a), 1), round(anc[1] + r * math.sin(a), 1))
            if _ok(cand, B):
                best = cand
                break
        if best:
            break
    B[name] = best or anc
    if not best:
        print(f"  !! {name} 找不到避讓位，沿用錨點")

# ---- 視窗緊貼內容 bbox ----
_xs, _ys = [], []
for k in _nodesR:
    _xs += [C[k][0] - _nodesR[k], C[k][0] + _nodesR[k]]
    _ys += [C[k][1] - _nodesR[k], C[k][1] + _nodesR[k]]
for (tx0, tx1, ty0, ty1) in _texts:
    _xs += [tx0, tx1]; _ys += [ty0, ty1]
for (bx, by) in B.values():
    _xs += [bx - 12, bx + 12]; _ys += [by - 12, by + 12]
for (px, py) in (m1, m4a, m4b, m5, m7):
    _xs += [px - 8, px + 8]; _ys += [py - 8, py + 8]
_PAD = 12
VX0, VY0 = round(min(_xs) - _PAD, 1), round(min(_ys) - _PAD, 1)
VW, VH = round(max(_xs) + _PAD - VX0, 1), round(max(_ys) + _PAD - VY0, 1)
print(f"content viewBox: {VX0} {VY0} {VW} {VH}")

svg = f'''    <svg viewBox="{VX0} {VY0} {VW} {VH}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="真實比例行程地圖：成田機場、東京迪士尼、台場豐洲、上野、品川，七天路線與日次標注">
      <style>
        .geo-lbl text{{paint-order:stroke; stroke:var(--bg); stroke-width:3.5px; stroke-linejoin:round}}
        a.geo-day{{cursor:pointer}}
        a.geo-day:hover path{{stroke-width:4.5px}}
        a.geo-day:hover circle{{r:13px}}
      </style>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--sea)"/>
        </marker>
      </defs>

      <!-- 東京灣區真實輪廓（dataofjapan/land GeoJSON，等距投影） -->
      <g fill="var(--leaf-wash)" opacity=".5" stroke="var(--line)" stroke-width="1">
{land_paths}
      </g>

      <!-- 行程路徑（點擊跳至該日行程卡） -->
      <g stroke="var(--sea)" stroke-width="3" fill="none" stroke-linecap="round">
        <a href="#day1" class="geo-day"><title>D1 8/3 成田 → 舞濱・夢幻泉鄉（點擊看當日行程）</title><path d="{d1}" marker-end="url(#arr)"/></a>
        <a href="#day4" class="geo-day"><title>D4 8/6 teamLab 豐洲 → 台場 → 上野（點擊看當日行程）</title><path d="{d4a}" marker-end="url(#arr)"/><path d="{d4b}" marker-end="url(#arr)"/></a>
        <a href="#day5" class="geo-day"><title>D5 8/7 品川水族館・晴空塔（點擊看當日行程）</title><path d="{d5}" marker-end="url(#arr)"/></a>
        <a href="#day7" class="geo-day"><title>D7 8/9 上野 → 成田 返台（點擊看當日行程）</title><path d="{d7}" marker-end="url(#arr)"/></a>
      </g>

      <!-- 主要節點 -->
      <g font-family="inherit" class="geo-lbl">
        <circle cx="{C['narita'][0]}" cy="{C['narita'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['narita'][0]+13}" y="{C['narita'][1]+5}" font-size="12" font-weight="700" fill="var(--ink)">成田機場 ✈</text>

        <circle cx="{C['maihama'][0]}" cy="{C['maihama'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['maihama'][0]}" y="{C['maihama'][1]+26}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="middle">東京迪士尼</text>
        <text x="{C['maihama'][0]}" y="{C['maihama'][1]+40}" font-size="10.5" fill="var(--ink-faint)" text-anchor="middle">D1–D3 泊・D2 陸地・D3 海洋</text>

        <circle cx="{C['odaiba'][0]}" cy="{C['odaiba'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['odaiba'][0]-18}" y="{C['odaiba'][1]-21}" font-size="12.5" font-weight="700" fill="var(--ink)" text-anchor="end">台場・豐洲</text>
        <text x="{C['odaiba'][0]-18}" y="{C['odaiba'][1]-8}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D4 teamLab</text>

        <circle cx="{C['ueno'][0]}" cy="{C['ueno'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['ueno'][0]-13}" y="{C['ueno'][1]-12}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="end">上野</text>
        <text x="{C['ueno'][0]+15}" y="{C['ueno'][1]+8}" font-size="10.5" fill="var(--ink-faint)">D4–D6 泊・D5 晴空塔・D6 淺草</text>

        <circle cx="{C['shinagawa'][0]}" cy="{C['shinagawa'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['shinagawa'][0]-12}" y="{C['shinagawa'][1]+2}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="end">品川</text>
        <text x="{C['shinagawa'][0]-12}" y="{C['shinagawa'][1]+15}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D5 水族館</text>
      </g>

      <!-- 日次徽章 -->
      <g font-family="inherit" font-size="11" font-weight="800" text-anchor="middle">
'''
_day_title = {"D1": "8/3 抵達・夢幻泉鄉", "D2": "8/4 迪士尼樂園（陸地）", "D3": "8/5 迪士尼海洋",
              "D4": "8/6 teamLab・台場 → 上野", "D5": "8/7 品川水族館・晴空塔",
              "D6": "8/8 淺草和服日", "D7": "8/9 返台"}

def _seg_enter_t(p, q_, bb, pad=2.5):
    x0, x1, y0, y1 = bb[0]-pad, bb[1]+pad, bb[2]-pad, bb[3]+pad
    dx, dy = q_[0]-p[0], q_[1]-p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0]-x0), (dx, x1-p[0]), (-dy, p[1]-y0), (dy, y1-p[1])):
        if pp == 0:
            if qq < 0: return None
            continue
        r = qq / pp
        if pp < 0:
            if r > t1: return None
            t0 = max(t0, r)
        else:
            if r < t0: return None
            t1 = min(t1, r)
    return t0 if t0 > 0 else 0.0

for name, (bx, by) in B.items():
    ax, ay = _anchor[name]
    dist = math.hypot(bx - ax, by - ay)
    if dist <= 22:
        continue
    ux, uy = (ax - bx) / dist, (ay - by) / dist
    sx, sy = bx + ux * 12, by + uy * 12
    t_end = 1.0
    for bb in _texts:
        t = _seg_enter_t((sx, sy), (ax, ay), bb)
        if t is not None and t < t_end:
            t_end = t
    ex, ey = sx + (ax - sx) * max(t_end - 0.03, 0), sy + (ay - sy) * max(t_end - 0.03, 0)
    if math.hypot(ex - sx, ey - sy) < 8:
        continue
    svg += f'        <line x1="{round(sx,1)}" y1="{round(sy,1)}" x2="{round(ex,1)}" y2="{round(ey,1)}" stroke="var(--ink-faint)" stroke-width="1" opacity=".55"/>\n'

for name, (bx, by) in B.items():
    n = name[1]
    svg += f'        <a href="#day{n}" class="geo-day"><title>{name} {_day_title[name]}（點擊看當日行程）</title><circle cx="{bx}" cy="{by}" r="11" fill="var(--sea)"/><text x="{bx}" y="{by+4}" fill="#fff">{name}</text></a>\n'
svg += '''      </g>
    </svg>'''

(SC / "disney_map.svg.html").write_text(svg)
print(f"rings={len(rings)}; pts={sum(len(r) for _, r in rings)}")

# ---- 自檢 ----
_r_outer = {"narita": 8.75, "maihama": 11, "odaiba": 8.75, "ueno": 11, "shinagawa": 8.75}
_fail = False
for nm, tgt, (tx, ty) in zip(
        ["d1→maihama", "d4a→odaiba", "d4b→ueno", "d5→shinagawa", "d7→narita"],
        ["maihama", "odaiba", "ueno", "shinagawa", "narita"], _arrow_tips):
    gap = math.hypot(tx - C[tgt][0], ty - C[tgt][1]) - _r_outer[tgt]
    flag = "" if gap >= 1 else "  !! 被節點蓋住"
    if gap < 1: _fail = True
    print(f"  tip {nm}: 距圓外緣 {gap:.1f}px{flag}")
for nm, (tx, ty) in zip(["d1", "d4a", "d4b", "d5", "d7"], _arrow_tips):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 3 < tx < x1 + 3 and y0 - 3 < ty < y1 + 3:
            print(f"  !! tip {nm} 落在文字框內 ({tx},{ty})")
            _fail = True
for bn, (bx, by) in B.items():
    for nn, (nx, ny) in C.items():
        gap = math.hypot(bx - nx, by - ny) - 11 - _nodesR[nn]
        if gap < 4:
            print(f"  ! 徽章 {bn} 距節點 {nn} 淨空 {gap:.1f}px")
# d1（NRT→舞浜）與 d7（上野→NRT）進出線分離檢查
def _bpts(dd):
    ps = dd.replace("M", "").replace(" Q", " ").split()
    p0 = tuple(map(float, ps[0].split(",")))
    c_ = tuple(map(float, ps[1].split(",")))
    p2 = tuple(map(float, ps[2].split(",")))
    return [( (1-t/60)**2*p0[0] + 2*(1-t/60)*(t/60)*c_[0] + (t/60)**2*p2[0],
              (1-t/60)**2*p0[1] + 2*(1-t/60)*(t/60)*c_[1] + (t/60)**2*p2[1]) for t in range(61)]
_min = min(math.hypot(a[0]-b2[0], a[1]-b2[1]) for a in _bpts(d1) for b2 in _bpts(d7))
print(f"  d1/d7 進出線最小間距 {_min:.1f}px" + ("  !! 太近" if _min < 5 else ""))
if _min < 5: _fail = True
# 線身 × 文字框（取樣，框內縮 1px 嚴格內部才算穿）
for nm, dd in [("d1", d1), ("d4a", d4a), ("d4b", d4b), ("d5", d5), ("d7", d7)]:
    hit = None
    for (x, y) in _bpts(dd):
        for (x0, x1, y0, y1) in _texts:
            if x0 + 1 < x < x1 - 1 and y0 + 1 < y < y1 - 1:
                hit = (round(x, 1), round(y, 1)); break
        if hit: break
    if hit:
        print(f"  !! 線 {nm} 穿過文字框 {hit}")
        _fail = True
# 徽章 × 文字框
for bn, (bx, by) in B.items():
    for (x0, x1, y0, y1) in _texts:
        if x0 - 8 < bx < x1 + 8 and y0 - 8 < by < y1 + 8:
            print(f"  !! 徽章 {bn} 壓文字框 ({bx},{by})")
            _fail = True
if _fail:
    raise SystemExit("自檢未過")
