"""從 japan.geojson 生成東京—越後湯澤滑雪行程 SVG（2026-tokyo-ski #geomap 內容）。
工具函數與 gen_kyushu_map.py 同源：等距投影、quadratic 路線、沿曲線絕對截斷、
徽章自動避讓、箭頭自檢（淨空 >=1px 且不落文字框，未過拒絕生成）。"""
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
d5,  m5,  e5  = q(C["ueno"], C["narita"],   .14,  1, r_start=13, r_end=11)   # Skyliner 回程

_anchor = {
    "D1": m1b, "D2": shift(C["yuzawa"], -34, -22), "D3": m3,
    "D4": shift(C["odaiba"], -26, 16), "D5": m5,
}
_pinned_pos = {"D2": shift(C["yuzawa"], -34, -22), "D4": shift(C["odaiba"], -26, 16)}
_nodesR = {"narita": 7, "ueno": 9, "yuzawa": 9, "odaiba": 6}

def _bb(cx, cy, anchor, w, size):
    if anchor == "start":  x0, x1 = cx, cx + w
    elif anchor == "end":  x0, x1 = cx - w, cx
    else:                  x0, x1 = cx - w / 2, cx + w / 2
    return (x0, x1, cy - size, cy + 3)

_texts = [
    _bb(C["narita"][0]+13, C["narita"][1]+5,  "start", 86, 12),
    _bb(C["ueno"][0]+17,   C["ueno"][1]-6,    "start", 26, 13),
    _bb(C["ueno"][0]+17,   C["ueno"][1]+8,    "start", 150, 10.5),
    _bb(C["yuzawa"][0]+16, C["yuzawa"][1]+2,  "start", 52, 13),
    _bb(C["yuzawa"][0]+16, C["yuzawa"][1]+16, "start", 140, 10.5),
    _bb(C["odaiba"][0]-11, C["odaiba"][1]+14, "end",   26, 13),
    _bb(C["odaiba"][0]-11, C["odaiba"][1]+27, "end",   80, 10.5),
]
def _hits_text(x, y, pad=4):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 11 - pad < x < x1 + 11 + pad and y0 - 11 - pad < y < y1 + 11 + pad:
            return True
    return False

_arrow_tips = [e1a, e1b, e3, e5]

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
for (px, py) in (m1a, m1b, m3, m5):
    _xs += [px - 8, px + 8]; _ys += [py - 8, py + 8]
_PAD = 12
VX0, VY0 = round(min(_xs) - _PAD, 1), round(min(_ys) - _PAD, 1)
VW, VH = round(max(_xs) + _PAD - VX0, 1), round(max(_ys) + _PAD - VY0, 1)
print(f"content viewBox: {VX0} {VY0} {VW} {VH}")

svg = f'''    <svg viewBox="{VX0} {VY0} {VW} {VH}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="真實比例行程地圖：成田機場、上野、越後湯澤、台場，五天雙向路線與日次標注">
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

      <!-- 本州中部真實輪廓（dataofjapan/land GeoJSON，等距投影） -->
      <g fill="var(--leaf-wash)" opacity=".5" stroke="var(--line)" stroke-width="1">
{land_paths}
      </g>

      <!-- 行程路徑（點擊跳至該日行程卡） -->
      <g stroke="var(--sea)" stroke-width="3" fill="none" stroke-linecap="round">
        <a href="#day1" class="geo-day"><title>D1 1/24 成田 → 上野 → 上越新幹線 → 越後湯澤（點擊看當日行程）</title><path d="{d1a}"/><path d="{d1b}" marker-end="url(#arr)"/></a>
        <a href="#day3" class="geo-day"><title>D3 1/26 湯澤高原 → 新幹線回上野（點擊看當日行程）</title><path d="{d3}" marker-end="url(#arr)"/></a>
        <a href="#day5" class="geo-day"><title>D5 1/28 淺草寫真 → Skyliner → 成田（點擊看當日行程）</title><path d="{d5}" marker-end="url(#arr)"/></a>
      </g>

      <!-- 主要節點 -->
      <g font-family="inherit" class="geo-lbl">
        <circle cx="{C['narita'][0]}" cy="{C['narita'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['narita'][0]+13}" y="{C['narita'][1]+5}" font-size="12" font-weight="700" fill="var(--ink)">成田機場 ✈</text>

        <circle cx="{C['ueno'][0]}" cy="{C['ueno'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['ueno'][0]+17}" y="{C['ueno'][1]-6}" font-size="13" font-weight="800" fill="var(--ink)">上野</text>
        <text x="{C['ueno'][0]+17}" y="{C['ueno'][1]+8}" font-size="10.5" fill="var(--ink-faint)">D3–D4 泊 Section L・D5 淺草寫真</text>

        <circle cx="{C['yuzawa'][0]}" cy="{C['yuzawa'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['yuzawa'][0]+16}" y="{C['yuzawa'][1]+2}" font-size="13" font-weight="800" fill="var(--ink)">越後湯澤</text>
        <text x="{C['yuzawa'][0]+16}" y="{C['yuzawa'][1]+16}" font-size="10.5" fill="var(--ink-faint)">D1–D2 泊雪の花・GALA・湯澤高原</text>

        <circle cx="{C['odaiba'][0]}" cy="{C['odaiba'][1]}" r="6" fill="var(--card)" stroke="var(--sea)" stroke-width="3"/>
        <text x="{C['odaiba'][0]-11}" y="{C['odaiba'][1]+14}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="end">台場</text>
        <text x="{C['odaiba'][0]-11}" y="{C['odaiba'][1]+27}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D4 AquaCity</text>
      </g>

      <!-- 日次徽章 -->
      <g font-family="inherit" font-size="11" font-weight="800" text-anchor="middle">
'''
_day_title = {"D1": "1/24 台北 → 成田 → 越後湯澤", "D2": "1/25 GALA 湯澤滑雪",
              "D3": "1/26 湯澤高原 → 回東京", "D4": "1/27 台場一日", "D5": "1/28 寫真 → 回程"}

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

(SC / "ski_map.svg.html").write_text(svg)
print(f"rings={len(rings)}; pts={sum(len(r) for _, r in rings)}")

# ---- 自檢：箭頭尖 vs 節點外緣＋文字框；徽章 vs 節點 ----
_r_outer = {"narita": 8.75, "ueno": 11, "yuzawa": 11, "odaiba": 7.5}
_fail = False
for nm, tgt, (tx, ty) in zip(
        ["d1a→ueno", "d1b→yuzawa", "d3→ueno", "d5→narita"],
        ["ueno", "yuzawa", "ueno", "narita"], _arrow_tips):
    gap = math.hypot(tx - C[tgt][0], ty - C[tgt][1]) - _r_outer[tgt]
    flag = "" if gap >= 1 else "  !! 被節點蓋住"
    if gap < 1: _fail = True
    print(f"  tip {nm}: 距圓外緣 {gap:.1f}px{flag}")
for nm, (tx, ty) in zip(["d1a", "d1b", "d3", "d5"], _arrow_tips):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 3 < tx < x1 + 3 and y0 - 3 < ty < y1 + 3:
            print(f"  !! tip {nm} 落在文字框內 ({tx},{ty})")
            _fail = True
for bn, (bx, by) in B.items():
    for nn, (nx, ny) in C.items():
        gap = math.hypot(bx - nx, by - ny) - 11 - _nodesR[nn]
        if gap < 4:
            print(f"  ! 徽章 {bn} 距節點 {nn} 淨空 {gap:.1f}px")
# 同走廊反向段（d1b vs d3）分離檢查：取樣最小距離
def _bpts(dd):
    ps = dd.replace("M", "").replace(" Q", " ").split()
    p0 = tuple(map(float, ps[0].split(",")))
    c_ = tuple(map(float, ps[1].split(",")))
    p2 = tuple(map(float, ps[2].split(",")))
    return [( (1-t/60)**2*p0[0] + 2*(1-t/60)*(t/60)*c_[0] + (t/60)**2*p2[0],
              (1-t/60)**2*p0[1] + 2*(1-t/60)*(t/60)*c_[1] + (t/60)**2*p2[1]) for t in range(61)]
_min = min(math.hypot(a[0]-b2[0], a[1]-b2[1]) for a in _bpts(d1b) for b2 in _bpts(d3))
print(f"  d1b/d3 雙向線最小間距 {_min:.1f}px" + ("  !! 太近" if _min < 5 else ""))
if _min < 5: _fail = True
_min2 = min(math.hypot(a[0]-b2[0], a[1]-b2[1]) for a in _bpts(d1a) for b2 in _bpts(d5))
print(f"  d1a/d5 雙向線最小間距 {_min2:.1f}px" + ("  !! 太近" if _min2 < 5 else ""))
if _min2 < 5: _fail = True
if _fail:
    raise SystemExit("自檢未過")
