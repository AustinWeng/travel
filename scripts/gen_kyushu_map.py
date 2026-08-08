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
d4a, m4, _   = q(C["kokura"], C["harmony"],  .13, -1, r_start=13, r_end=12)
d4b, _, e4b  = q(C["harmony"], C["beppu"],   .20, -1, r_start=11, r_end=14)
# d5 不畫線：beppu 圓（外緣11）與 safari 圓（外緣7.5）圓心僅距 17.9px，兩圓重疊，
# 真實比例下無可見線段可畫；D5 徽章（可點）＋Safari 旁「D5 動物園」已表達往返。
_, m5, _     = q(C["beppu"], C["safari"],    .55,  1)
d6, m6, e6   = q(C["beppu"], C["hakata"],    .22, -1, r_start=13, r_end=16)   # 終點多留：避開「福岡機場」字頭

gx1, _, _ = q(C["hakata"], C["kumamoto"], .12, 1)
gx2, _, _ = q(C["kumamoto"], C["aso"], .15, -1)
gx3, _, _ = q(C["aso"], C["takachiho"], .15, 1)
gx4, _, _ = q(C["takachiho"], C["beppu"], .12, 1)

# 徽章位置：以路徑中點為錨，自動避讓（節點淨空>=6、徽章互距>=26、留邊）
_anchor = {
    "D1": m1, "D2": m2, "D3": shift(m3, -6, -14),
    "D4": shift(m4, 16, -4), "D5": m5, "D6": shift(m6, -16, -8),
    "D7": shift(C["hakata"], -34, -26), "D8": shift(C["airport"], 104, 2),
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
    _bb(C["airport"][0]+16, C["airport"][1]+5, "start", 74, 12),
    _bb(C["htb"][0], C["htb"][1]+27, "middle", 52, 13),
    _bb(C["uminaka"][0]-12, C["uminaka"][1]-16, "end", 50, 12.5),
    _bb(C["uminaka"][0]-12, C["uminaka"][1]-3, "end", 112, 10.5),
    _bb(C["hakata"][0]-15, C["hakata"][1]+8, "end", 65, 13),
    _bb(C["hakata"][0]-15, C["hakata"][1]+22, "end", 78, 10.5),
    _bb(C["kokura"][0]+16, C["kokura"][1]-2, "start", 26, 13),
    _bb(C["harmony"][0]+14, C["harmony"][1]+2, "start", 88, 12.5),
    _bb(C["harmony"][0]+14, C["harmony"][1]+16, "start", 96, 10.5),
    _bb(C["safari"][0]-16, C["safari"][1]-10, "end", 40, 11.5),
    _bb(C["safari"][0]-16, C["safari"][1]+3, "end", 72, 10.5),
    _bb(C["beppu"][0]+15, C["beppu"][1]+16, "start", 52, 13),
    _bb(C["kanryu"][0], C["kanryu"][1]+18, "middle", 52, 10.5),
    _bb(C["kiyama"][0]+8, C["kiyama"][1]+14, "start", 52, 10.5),
    _bb(C["imagawa"][0]+9, C["imagawa"][1]+4, "start", 52, 10.5),
]
def _hits_text(x, y, pad=4):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 11 - pad < x < x1 + 11 + pad and y0 - 11 - pad < y < y1 + 11 + pad:
            return True
    return False
_arrow_tips = [e1, e2a, e3, e4b, e6]  # 各段截斷後的實際箭頭尖（d5 無線）
def _ok(pt, placed):
    x, y = pt
    if not (20 <= x <= 720 and 20 <= y <= 620):
        return False
    for tp in _arrow_tips:
        if math.hypot(x - tp[0], y - tp[1]) < 24:
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
_pinned_pos = {"D1": shift(m1, -22, 15), "D2": shift(m2, -30, 0)}
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

# ---- 視窗緊貼內容 bbox（Austin 2026-07-31：周圍空白裁到只剩內容） ----
_xs, _ys = [], []
for k in ("airport","hakata","uminaka","kokura","htb","harmony","beppu","safari","kanryu","kiyama","imagawa"):
    _xs += [C[k][0] - _nodesR[k], C[k][0] + _nodesR[k]]
    _ys += [C[k][1] - _nodesR[k], C[k][1] + _nodesR[k]]
for (tx0, tx1, ty0, ty1) in _texts:
    _xs += [tx0, tx1]; _ys += [ty0, ty1]
for k in ("kumamoto","aso","takachiho"):
    _xs += [C[k][0] - 40, C[k][0] + 40]; _ys += [C[k][1] - 22, C[k][1] + 22]
_xs += [C["epicenter"][0] - 52, C["epicenter"][0] + 52]
_ys += [C["epicenter"][1] - 32, C["epicenter"][1] + 34]
for (bx, by) in B.values():
    _xs += [bx - 12, bx + 12]; _ys += [by - 12, by + 12]
_PAD = 12
VX0, VY0 = round(min(_xs) - _PAD, 1), round(min(_ys) - _PAD, 1)
VW, VH = round(max(_xs) + _PAD - VX0, 1), round(max(_ys) + _PAD - VY0, 1)
print(f"content viewBox: {VX0} {VY0} {VW} {VH}")


svg = f'''    <svg viewBox="{VX0} {VY0} {VW} {VH}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="九州真實比例行程地圖：八天路徑與日次標注、7/28 震央位置、取消的熊本阿蘇高千穗原路線">
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

      <!-- 九州真實輪廓（dataofjapan/land GeoJSON，等距投影） -->
      <g fill="var(--leaf-wash)" opacity=".5" stroke="var(--line)" stroke-width="1">
{land_paths}
      </g>

      <text x="{VX0+16}" y="{VY0+VH-10}" font-size="11" fill="var(--ink-faint)" opacity=".8">↓ 九州南部（本次不前往）</text>

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
        <text x="{C['kumamoto'][0]-22}" y="{C['kumamoto'][1]+4}">熊本</text>
        <circle cx="{C['aso'][0]}" cy="{C['aso'][1]}" r="5" fill="var(--ink-faint)"/>
        <text x="{C['aso'][0]+2}" y="{C['aso'][1]-10}">阿蘇</text>
        <circle cx="{C['takachiho'][0]}" cy="{C['takachiho'][1]}" r="5" fill="var(--ink-faint)"/>
        <text x="{C['takachiho'][0]+8}" y="{C['takachiho'][1]+18}">高千穗</text>
      </g>

      <!-- 行程路徑（點擊跳至該日行程卡） -->
      <g stroke="var(--sea)" stroke-width="3" fill="none" stroke-linecap="round">
        <a href="#day1" class="geo-day"><title>D1 8/1 機場 → 豪斯登堡（點擊看當日行程）</title><path d="{d1}" marker-end="url(#arr)"/></a>
        <a href="#day2" class="geo-day"><title>D2 8/2 豪斯登堡 → 海洋世界 → 博多（點擊看當日行程）</title><path d="{d2af}" marker-end="url(#arr)"/><path d="{d2ab}"/></a>
        <a href="#day3" class="geo-day"><title>D3 8/3 KidZania → 小倉（點擊看當日行程）</title><path d="{d3}" marker-end="url(#arr)"/></a>
        <a href="#day4" class="geo-day"><title>D4 8/4 Harmonyland → 別府（點擊看當日行程）</title><path d="{d4a}"/><path d="{d4b}" marker-end="url(#arr)"/></a>
        <a href="#day6" class="geo-day"><title>D6 8/6 海地獄 → 筑紫野公園 → 福岡（點擊看當日行程）</title><path d="{d6}" marker-end="url(#arr)"/></a>
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
        <text x="{C['airport'][0]+16}" y="{C['airport'][1]+5}" font-size="12" font-weight="700" fill="var(--ink)">福岡機場 ✈</text>

        <circle cx="{C['htb'][0]}" cy="{C['htb'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['htb'][0]}" y="{C['htb'][1]+27}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="middle">豪斯登堡</text>

        <circle cx="{C['uminaka'][0]}" cy="{C['uminaka'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['uminaka'][0]-12}" y="{C['uminaka'][1]-16}" font-size="12.5" font-weight="700" fill="var(--ink)" text-anchor="end">海之中道</text>
        <text x="{C['uminaka'][0]-12}" y="{C['uminaka'][1]-3}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D2 海洋世界・D7 泳池</text>

        <circle cx="{C['hakata'][0]}" cy="{C['hakata'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['hakata'][0]-15}" y="{C['hakata'][1]+8}" font-size="13" font-weight="800" fill="var(--ink)" text-anchor="end">博多・福岡</text>
        <text x="{C['hakata'][0]-15}" y="{C['hakata'][1]+22}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D3 KidZania</text>

        <circle cx="{C['kokura'][0]}" cy="{C['kokura'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['kokura'][0]+16}" y="{C['kokura'][1]-2}" font-size="13" font-weight="800" fill="var(--ink)">小倉</text>

        <circle cx="{C['harmony'][0]}" cy="{C['harmony'][1]}" r="7" fill="var(--card)" stroke="var(--sea)" stroke-width="3.5"/>
        <text x="{C['harmony'][0]+14}" y="{C['harmony'][1]+2}" font-size="12.5" font-weight="700" fill="var(--ink)">Harmonyland</text>
        <text x="{C['harmony'][0]+14}" y="{C['harmony'][1]+16}" font-size="10.5" fill="var(--ink-faint)">D4 三麗鷗樂園</text>

        <circle cx="{C['safari'][0]}" cy="{C['safari'][1]}" r="6" fill="var(--card)" stroke="var(--sea)" stroke-width="3"/>
        <text x="{C['safari'][0]-16}" y="{C['safari'][1]-10}" font-size="11.5" font-weight="700" fill="var(--ink)" text-anchor="end">Safari</text>
        <text x="{C['safari'][0]-16}" y="{C['safari'][1]+3}" font-size="10.5" fill="var(--ink-faint)" text-anchor="end">D5 動物園</text>

        <circle cx="{C['beppu'][0]}" cy="{C['beppu'][1]}" r="9" fill="var(--card)" stroke="var(--sea)" stroke-width="4"/>
        <text x="{C['beppu'][0]+15}" y="{C['beppu'][1]+16}" font-size="13" font-weight="800" fill="var(--ink)">別府溫泉</text>
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
print("DEBUG m1,m2,B:", m1, m2, {k: v for k, v in B.items() if k in ("D1","D2")})
_day_title = {"D1":"8/1 機場 → 豪斯登堡","D2":"8/2 豪斯登堡 → 海洋世界 → 博多","D3":"8/3 KidZania → 小倉","D4":"8/4 Harmonyland → 別府","D5":"8/5 African Safari","D6":"8/6 海地獄 → 筑紫野公園 → 福岡","D7":"8/7 海之中道泳池・科學館","D8":"8/8 還車返台"}
for name, (bx, by) in B.items():
    n = name[1]
    svg += f'        <a href="#day{n}" class="geo-day"><title>{name} {_day_title[name]}（點擊看當日行程）</title><circle cx="{bx}" cy="{by}" r="11" fill="var(--sea)"/><text x="{bx}" y="{by+4}" fill="#fff">{name}</text></a>\n'
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

# ---- 自檢：箭頭尖 vs 節點圓外緣（必須在圓外，淨空 >= 1）----
_r_outer = {"airport":4,"hakata":11,"uminaka":8.8,"kokura":11,"htb":11,"harmony":8.8,"beppu":11,"safari":7.5}
_tip_names = ["d1→htb","d2 中段箭頭","d3→kokura","d4b→beppu","d6→hakata"]
_tip_targets = ["htb","uminaka","kokura","beppu","hakata"]
_fail = False
for nm, tgt, (tx, ty) in zip(_tip_names, _tip_targets, _arrow_tips):
    gap = math.hypot(tx - C[tgt][0], ty - C[tgt][1]) - _r_outer[tgt]
    flag = "" if gap >= 1 else "  !! 被節點蓋住"
    if gap < 1: _fail = True
    print(f"  tip {nm}: 距圓外緣 {gap:.1f}px{flag}")
for nm, (tx, ty) in zip(_tip_names, _arrow_tips):
    for (x0, x1, y0, y1) in _texts:
        if x0 - 3 < tx < x1 + 3 and y0 - 3 < ty < y1 + 3:
            print(f"  !! tip {nm} 落在文字框內 ({tx},{ty})")
            _fail = True
if _fail:
    raise SystemExit("箭頭自檢未過")
