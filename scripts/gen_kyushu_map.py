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
lat0, lat1 = 31.9, max(lats)   # 視窗下緣裁在 31.9°N（含震央），南部漸隱
lon0, lon1 = min(lons), max(lons)
cosf = math.cos(math.radians((lat0 + lat1) / 2))
W = 740
PADL, PADR, PADT, PADB = 30, 150, 56, 34   # 右側留標籤空間
S = (W - PADL - PADR) / ((lon1 - lon0) * cosf)
H = int((lat1 - lat0) * S + PADT + PADB + 26)

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

def q(a, b, bend=0.18, side=1):
    """兩點間 quadratic 曲線，bend 為垂直偏移比例。回傳 path d 與中點。"""
    (x1, y1), (x2, y2) = a, b
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1
    ox, oy = -dy / L * L * bend * side, dx / L * L * bend * side
    cx, cy = mx + ox, my + oy
    return f"M{x1},{y1} Q{round(cx,1)},{round(cy,1)} {x2},{y2}", (round((mx+cx)/2,1), round((my+cy)/2,1))

def shift(pt, dx, dy):
    return (round(pt[0] + dx, 1), round(pt[1] + dy, 1))

# 路徑（起訖略縮避免壓節點圓）
def lerp(a, b, t):
    return (round(a[0]+(b[0]-a[0])*t,1), round(a[1]+(b[1]-a[1])*t,1))

segs = []
d1, m1 = q(lerp(C["airport"], C["htb"], .04), lerp(C["airport"], C["htb"], .97), .10, -1)
d2a, m2 = q(lerp(C["htb"], C["uminaka"], .03), lerp(C["htb"], C["uminaka"], .97), .13, -1)
d2b, _ = q(lerp(C["uminaka"], C["hakata"], .15), lerp(C["uminaka"], C["hakata"], .85), .3, 1)
d3, m3 = q(lerp(C["hakata"], C["kokura"], .05), lerp(C["kokura"], C["hakata"], .04)[::-1] if False else lerp(C["hakata"], C["kokura"], .96), .10, -1)
d4a, m4 = q(lerp(C["kokura"], C["harmony"], .04), lerp(C["kokura"], C["harmony"], .96), .13, -1)
d4b, _ = q(lerp(C["harmony"], C["beppu"], .1), lerp(C["harmony"], C["beppu"], .85), .2, -1)
d5, m5 = q(lerp(C["beppu"], C["safari"], .2), lerp(C["beppu"], C["safari"], .8), .25, 1)
d6, m6 = q(lerp(C["beppu"], C["uminaka"], .03), lerp(C["beppu"], C["uminaka"], .965), .12, -1)
d8, m8 = q(lerp(C["hakata"], C["airport"], .2), lerp(C["hakata"], C["airport"], .8), .4, -1)

gx1, _ = q(C["hakata"], C["kumamoto"], .12, 1)
gx2, _ = q(C["kumamoto"], C["aso"], .15, -1)
gx3, _ = q(C["aso"], C["takachiho"], .15, 1)
gx4, _ = q(C["takachiho"], C["beppu"], .12, 1)

# 徽章位置：以路徑中點為錨，自動避讓（節點淨空>=6、徽章互距>=26、留邊）
_anchor = {
    "D1": shift(m1, -2, -14), "D2": shift(m2, 6, 16), "D3": shift(m3, -6, -14),
    "D4": shift(m4, 16, -4), "D5": m5, "D6": shift(m6, -16, -8),
    "D7": shift(C["hakata"], -34, -26), "D8": shift(C["airport"], 26, -10),
}
_nodesR = {"airport":0,"hakata":9,"uminaka":7,"kokura":9,"htb":9,"harmony":7,
           "beppu":9,"safari":6,"kanryu":4,"kiyama":4,"imagawa":4}
# 文字標籤 bbox 近似（與下方渲染公式同步；(x0,x1,y0,y1)）
def _bb(cx, cy, anchor, w, size):
    if anchor == "start":  x0, x1 = cx, cx + w
    elif anchor == "end":  x0, x1 = cx - w, cx
    else:                  x0, x1 = cx - w / 2, cx + w / 2
    return (x0, x1, cy - size, cy + 3)
_texts = [
    _bb(C["airport"][0]+13, C["airport"][1]+16, "start", 74, 12),
    _bb(C["htb"][0], C["htb"][1]+27, "middle", 52, 13),
    _bb(C["htb"][0], C["htb"][1]+41, "middle", 96, 10.5),
    _bb(C["uminaka"][0]-12, C["uminaka"][1]-16, "end", 50, 12.5),
    _bb(C["uminaka"][0]-12, C["uminaka"][1]-3, "end", 112, 10.5),
    _bb(C["hakata"][0]-15, C["hakata"][1]+8, "end", 65, 13),
    _bb(C["hakata"][0]-15, C["hakata"][1]+22, "end", 150, 10.5),
    _bb(C["hakata"][0]-15, C["hakata"][1]+36, "end", 122, 10.5),
    _bb(C["kokura"][0]+16, C["kokura"][1]-2, "start", 26, 13),
    _bb(C["kokura"][0]+16, C["kokura"][1]+12, "start", 118, 10.5),
    _bb(C["harmony"][0]+14, C["harmony"][1]+2, "start", 88, 12.5),
    _bb(C["harmony"][0]+14, C["harmony"][1]+16, "start", 96, 10.5),
    _bb(C["safari"][0]-12, C["safari"][1]-8, "end", 40, 11.5),
    _bb(C["safari"][0]-12, C["safari"][1]+5, "end", 72, 10.5),
    _bb(C["beppu"][0]+16, C["beppu"][1]+8, "start", 52, 13),
    _bb(C["beppu"][0]+16, C["beppu"][1]+22, "start", 124, 10.5),
    _bb(C["kanryu"][0], C["kanryu"][1]+18, "middle", 52, 10.5),
    _bb(C["kiyama"][0]+8, C["kiyama"][1]+14, "start", 52, 10.5),
    _bb(C["imagawa"][0]+9, C["imagawa"][1]+4, "start", 52, 10.5),
]
def _hits_text(x, y, pad=4):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 11 - pad < x < x1 + 11 + pad and y0 - 11 - pad < y < y1 + 11 + pad:
            return True
    return False
def _ok(pt, placed):
    x, y = pt
    if not (20 <= x <= 720 and 20 <= y <= 620):
        return False
    for nn, rr in _nodesR.items():
        if math.hypot(x - C[nn][0], y - C[nn][1]) - 11 - rr < 6:
            return False
    for q2 in placed.values():
        if math.hypot(x - q2[0], y - q2[1]) < 26:
            return False
    if _hits_text(x, y):
        return False
    return True
B = {}
for name, anc in _anchor.items():
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

svg = f'''    <svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="九州真實比例行程地圖：八天路徑與日次標注、7/28 震央位置、取消的熊本阿蘇高千穗原路線">
      <style>
        .geo-lbl text{{paint-order:stroke; stroke:var(--bg); stroke-width:3.5px; stroke-linejoin:round}}
      </style>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--sea)"/>
        </marker>
      </defs>

      <!-- 九州真實輪廓（dataofjapan/land GeoJSON，等距投影） -->
      <g fill="var(--leaf-wash)" opacity=".5" stroke="var(--line)" stroke-width="1">
{land_paths}
      </g>

      <!-- 震央（7/28 M7.1） -->
      <g>
        <circle cx="{C['epicenter'][0]}" cy="{C['epicenter'][1]}" r="30" fill="var(--alert)" opacity=".10"/>
        <circle cx="{C['epicenter'][0]}" cy="{C['epicenter'][1]}" r="16" fill="var(--alert)" opacity=".16"/>
        <text x="{C['epicenter'][0]}" y="{C['epicenter'][1]+5}" font-size="15" font-weight="800" fill="var(--alert)" text-anchor="middle">✕</text>
        <text x="{C['epicenter'][0]}" y="{C['epicenter'][1]+26}" font-size="11" font-weight="750" fill="var(--alert)" text-anchor="middle" style="paint-order:stroke; stroke:var(--bg); stroke-width:3.5px; stroke-linejoin:round">7/28 震央 M7.1</text>
      </g>

      <!-- 取消原線（灰虛線） -->
      <g stroke="var(--ink-faint)" stroke-width="2.5" fill="none" stroke-dasharray="7 6" opacity=".45">
        <path d="{gx1}"/><path d="{gx2}"/><path d="{gx3}"/><path d="{gx4}"/>
      </g>
      <g opacity=".55" font-family="inherit" font-size="12" fill="var(--ink-faint)" text-anchor="middle" class="geo-lbl">
        <circle cx="{C['kumamoto'][0]}" cy="{C['kumamoto'][1]}" r="5" fill="var(--ink-faint)"/>
        <text x="{C['kumamoto'][0]-22}" y="{C['kumamoto'][1]+4}" text-decoration="line-through">熊本</text>
        <circle cx="{C['aso'][0]}" cy="{C['aso'][1]}" r="5" fill="var(--ink-faint)"/>
        <text x="{C['aso'][0]+2}" y="{C['aso'][1]-10}" text-decoration="line-through">阿蘇</text>
        <circle cx="{C['takachiho'][0]}" cy="{C['takachiho'][1]}" r="5" fill="var(--ink-faint)"/>
        <text x="{C['takachiho'][0]+8}" y="{C['takachiho'][1]+18}" text-decoration="line-through">高千穗</text>
      </g>

      <!-- 行程路徑 -->
      <g stroke="var(--sea)" stroke-width="3.5" fill="none" stroke-linecap="round">
        <path d="{d1}" marker-end="url(#arr)"/>
        <path d="{d2a}" marker-end="url(#arr)"/>
        <path d="{d2b}" marker-end="url(#arr)"/>
        <path d="{d3}" marker-end="url(#arr)"/>
        <path d="{d4a}" marker-end="url(#arr)"/>
        <path d="{d4b}" marker-end="url(#arr)"/>
        <path d="{d5}" stroke-width="2.5" stroke-dasharray="2 5" marker-end="url(#arr)"/>
        <path d="{d6}" marker-end="url(#arr)"/>
        <path d="{d8}" marker-end="url(#arr)"/>
      </g>

      <!-- 休息站 -->
      <g font-family="inherit" font-size="10.5" fill="var(--ink-faint)" class="geo-lbl">
        <circle cx="{C['kanryu'][0]}" cy="{C['kanryu'][1]}" r="4" fill="var(--card)" stroke="var(--sea)" stroke-width="2"/>
        <text x="{C['kanryu'][0]}" y="{C['kanryu'][1]+18}" text-anchor="middle">金立SA</text>
        <circle cx="{C['kiyama'][0]}" cy="{C['kiyama'][1]}" r="4" fill="var(--card)" stroke="var(--sea)" stroke-width="2"/>
        <text x="{C['kiyama'][0]+8}" y="{C['kiyama'][1]+14}">基山PA</text>
        <circle cx="{C['imagawa'][0]}" cy="{C['imagawa'][1]}" r="4" fill="var(--card)" stroke="var(--sea)" stroke-width="2"/>
        <text x="{C['imagawa'][0]+9}" y="{C['imagawa'][1]+4}">今川PA</text>
      </g>

      <!-- 主要節點 -->
      <g font-family="inherit" class="geo-lbl">
        <text x="{C['airport'][0]+13}" y="{C['airport'][1]+16}" font-size="12" font-weight="700" fill="var(--ink)">福岡機場 ✈</text>

        <circle cx="{C['htb'][0]}" cy="{C['htb'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['htb'][0]}" y="{C['htb'][1]+27}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="middle">豪斯登堡</text>
        <text x="{C['htb'][0]}" y="{C['htb'][1]+41}" font-size="10.5" fill="var(--ink-faint)" text-anchor="middle">D1 泊・Amsterdam</text>

        <circle cx="{C['uminaka'][0]}" cy="{C['uminaka'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['uminaka'][0]-12}" y="{C['uminaka'][1]-16}" font-size="12.5" font-weight="700" fill="var(--ink)" text-anchor="end">海之中道</text>
        <text x="{C['uminaka'][0]-12}" y="{C['uminaka'][1]-3}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D2 海洋世界・D6 泳池</text>

        <circle cx="{C['hakata'][0]}" cy="{C['hakata'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['hakata'][0]-15}" y="{C['hakata'][1]+8}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="end">博多・福岡</text>
        <text x="{C['hakata'][0]-15}" y="{C['hakata'][1]+22}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D2 泊都酒店・D3 KidZania</text>
        <text x="{C['hakata'][0]-15}" y="{C['hakata'][1]+36}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D6–D7 泊 GATE ×2</text>

        <circle cx="{C['kokura'][0]}" cy="{C['kokura'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['kokura'][0]+16}" y="{C['kokura'][1]-2}" font-size="13" font-weight="800" fill="var(--ink)">小倉</text>
        <text x="{C['kokura'][0]+16}" y="{C['kokura'][1]+12}" font-size="10.5" fill="var(--ink-faint)">D3 泊 Daiwa Roynet</text>

        <circle cx="{C['harmony'][0]}" cy="{C['harmony'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['harmony'][0]+14}" y="{C['harmony'][1]+2}" font-size="12.5" font-weight="700" fill="var(--ink)">Harmonyland</text>
        <text x="{C['harmony'][0]+14}" y="{C['harmony'][1]+16}" font-size="10.5" fill="var(--ink-faint)">D4 三麗鷗樂園</text>

        <circle cx="{C['safari'][0]}" cy="{C['safari'][1]}" r="6" fill="var(--card)" stroke="var(--sea)" stroke-width="3"/>
        <text x="{C['safari'][0]-12}" y="{C['safari'][1]-8}" font-size="11.5" font-weight="700" fill="var(--ink)" text-anchor="end">Safari</text>
        <text x="{C['safari'][0]-12}" y="{C['safari'][1]+5}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D5 動物園</text>

        <circle cx="{C['beppu'][0]}" cy="{C['beppu'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['beppu'][0]+16}" y="{C['beppu'][1]+8}" font-size="13" font-weight="800" fill="var(--ink)">別府溫泉</text>
        <text x="{C['beppu'][0]+16}" y="{C['beppu'][1]+22}" font-size="10.5" fill="var(--ink-faint)">D4–D5 泊 杉乃井 ×2</text>
      </g>

      <!-- 日次徽章（擁擠處帶引線） -->
      <g font-family="inherit" font-size="11" font-weight="800" text-anchor="middle">
'''
def _seg_enter_t(p, q, bb, pad=2.5):
    """線段 p→q 進入 bbox（外擴 pad）的最小 t；不相交回 None（Liang-Barsky）。"""
    x0, x1, y0, y1 = bb[0]-pad, bb[1]+pad, bb[2]-pad, bb[3]+pad
    dx, dy = q[0]-p[0], q[1]-p[1]
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
    # 起點＝徽章圓邊；終點預設錨點，撞文字框則截短
    ux, uy = (ax - bx) / dist, (ay - by) / dist
    sx, sy = bx + ux * 12, by + uy * 12
    t_end = 1.0
    for bb in _texts:
        t = _seg_enter_t((sx, sy), (ax, ay), bb)
        if t is not None and t < t_end:
            t_end = t
    ex, ey = sx + (ax - sx) * max(t_end - 0.03, 0), sy + (ay - sy) * max(t_end - 0.03, 0)
    if math.hypot(ex - sx, ey - sy) < 8:
        continue  # 線太短乾脆不畫
    svg += f'        <line x1="{round(sx,1)}" y1="{round(sy,1)}" x2="{round(ex,1)}" y2="{round(ey,1)}" stroke="var(--ink-faint)" stroke-width="1" opacity=".55"/>\n'
for name, (bx, by) in B.items():
    svg += f'        <circle cx="{bx}" cy="{by}" r="11" fill="var(--sea)"/><text x="{bx}" y="{by+4}" fill="#fff">{name}</text>\n'
svg += '''      </g>
    </svg>'''

(SC / "kyushu_map.svg.html").write_text(svg)
print(f"viewBox 0 0 {W} {H}; rings={len(rings)}; pts={sum(len(r) for _,r in rings)}")

# ---- 自檢：徽章 vs 節點/文字粗查 ----
nodes = {k: C[k] for k in ["airport","hakata","uminaka","kokura","htb","harmony","beppu","safari","kanryu","kiyama","imagawa"]}
R = {"airport":6,"hakata":9,"uminaka":7,"kokura":9,"htb":9,"harmony":7,"beppu":9,"safari":6,"kanryu":4,"kiyama":4,"imagawa":4}
for bn,(bx,by) in B.items():
    for nn,(nx,ny) in nodes.items():
        gap = math.hypot(bx-nx, by-ny) - 11 - R[nn]
        if gap < 6:
            print(f"  ! 徽章 {bn} 距節點 {nn} 淨空 {gap:.1f}px")
