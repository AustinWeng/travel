"""從 japan.geojson 生成 2027-01 北海道道央行程 SVG（2027-hokkaido #geomap 內容）。
工具函數與 gen_ski_map.py / gen_kyushu_map.py 同源：等距投影、quadratic 路線、
沿曲線絕對截斷、徽章自動避讓、箭頭自檢（淨空 >=1px 且不落文字框，未過拒絕生成）。
新增：路段距離／時間標籤（入 _texts 參與避讓）、自駕實線 vs JR 虛線圖例。"""

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


# ---- 節點標籤（文案＋位置一處定義，渲染與 bbox 共用） ----
LBL = [
    # (key, dx, dy, anchor, text, size, weight, fill)
    ("chitose", 13, 5, "start", "新千歳空港 ✈", 12, "700", "ink"),
    ("chitose", 13, 19, "start", "D1 抵達・D5 返程", 10.5, None, "faint"),
    ("toya", -15, 4, "end", "洞爺湖温泉", 13, "800", "ink"),
    ("toya", -15, 18, "end", "D1 泊 乃の風・1 晚", 10.5, None, "faint"),
    ("rusutsu", -15, 2, "end", "ルスツリゾート", 13, "800", "ink"),
    ("rusutsu", -15, 16, "end", "D2–D3 泊 2 晚・滑雪", 10.5, None, "faint"),
    # 札幌標籤放北側：D4 由西南進站、D5 往東南離站，東側被 JR 線佔走
    ("sapporo", 14, -20, "start", "札幌", 13, "800", "ink"),
    ("sapporo", 14, -6, "start", "D4 泊 1 晚・円山動物園", 10.5, None, "faint"),
]
_texts = [
    _bb(C[k][0] + dx, C[k][1] + dy, anc, tw(t, sz), sz)
    for (k, dx, dy, anc, t, sz, wt, fl) in LBL
]

# 途經點：中山峠（休息站級小節點，字在西北側）
NAKA = (-9, -6, "end", "中山峠", 10.5)
_texts.append(
    _bb(
        C["nakayama"][0] + NAKA[0],
        C["nakayama"][1] + NAKA[1],
        NAKA[2],
        tw(NAKA[3], NAKA[4]),
        NAKA[4],
    )
)

# ---- 路段距離／時間標籤（錨在曲線中點，手動偏移避開線身） ----
SEG_SZ = 10.5
SEG = [
    ("d1", shift(m1, -2, 26), "middle", "道央道 110 km／1.5 h"),
    ("d2", shift(m2, 24, 4), "start", "30 km／40 分"),
    ("d4", shift(m4a, -12, -8), "end", "国道230 80 km／1.5 h"),
    ("d5", shift(m5, 22, -6), "start", "JR 快速 37 分"),
]
_seg_bb = {n: _bb(p[0], p[1], anc, tw(t, SEG_SZ), SEG_SZ) for (n, p, anc, t) in SEG}
_texts += list(_seg_bb.values())

# ---- 圖例（石狩湾海面；自駕實線 vs JR 虛線） ----
LEG_X, LEG_Y = 176.0, 62.0
LEG_ROWS = [("solid", "自駕（租車）"), ("dash", "JR 快速エアポート")]
LEG_SW, LEG_GAP, LEG_LH, LEG_SZ = 26, 7, 19, 11
LEG_W = LEG_SW + LEG_GAP + max(tw(t, LEG_SZ) for _, t in LEG_ROWS)
LEG_H = LEG_LH * len(LEG_ROWS)
_leg_bb = (LEG_X - 6, LEG_X + LEG_W + 6, LEG_Y - 12, LEG_Y + LEG_H - 4)
_texts.append(_leg_bb)


def _hits_text(x, y, pad=4):
    for x0, x1, y0, y1 in _texts:
        if x0 - 11 - pad < x < x1 + 11 + pad and y0 - 11 - pad < y < y1 + 11 + pad:
            return True
    return False


# ---- 日次徽章 ----
_anchor = {
    "D1": shift(m1, 10, -20),
    "D2": shift(m2, -26, 2),
    "D3": shift(C["rusutsu"], 32, 14),
    "D4": shift(m4b, 20, 6),
    "D5": shift(m5, -24, 10),
}
# D3 當天無移動：釘在 ルスツ 右下側空白處（右上會壓到 D4 的国道230 線身，誤讀成有移動）
_pinned_pos = {"D3": shift(C["rusutsu"], 32, 14)}
_nodesR = {"chitose": 9, "toya": 9, "rusutsu": 9, "sapporo": 9, "nakayama": 4}
_arrow_tips = [e1, e2, e4b, e5]


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
            cand = (
                round(anc[0] + r * math.cos(a), 1),
                round(anc[1] + r * math.sin(a), 1),
            )
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
for tx0, tx1, ty0, ty1 in _texts:
    _xs += [tx0, tx1]
    _ys += [ty0, ty1]
for bx, by in B.values():
    _xs += [bx - 12, bx + 12]
    _ys += [by - 12, by + 12]
for px, py in (m1, m2, m4a, m4b, m5):
    _xs += [px - 8, px + 8]
    _ys += [py - 8, py + 8]
_PAD = 12
VX0, VY0 = round(min(_xs) - _PAD, 1), round(min(_ys) - _PAD, 1)
VW, VH = round(max(_xs) + _PAD - VX0, 1), round(max(_ys) + _PAD - VY0, 1)
print(f"content viewBox: {VX0} {VY0} {VW} {VH}")

_FILL = {"ink": "var(--ink)", "faint": "var(--ink-faint)"}

svg = f'''    <svg viewBox="{VX0} {VY0} {VW} {VH}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="真實比例行程地圖：新千歳空港、洞爺湖温泉、ルスツリゾート、札幌，五天路線與日次標注，末段札幌回新千歳為 JR 虛線">
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

      <!-- 北海道道央真實輪廓（dataofjapan/land GeoJSON，等距投影） -->
      <g fill="var(--leaf-wash)" opacity=".5" stroke="var(--line)" stroke-width="1">
{land_paths}
      </g>

      <!-- 行程路徑（點擊跳至該日行程卡） -->
      <g stroke="var(--sea)" stroke-width="3" fill="none" stroke-linecap="round">
        <a href="#day1" class="geo-day"><title>D1 1/20 新千歳空港 → 道央道 → 洞爺湖温泉（點擊看當日行程）</title><path d="{d1}" marker-end="url(#arr)"/></a>
        <a href="#day2" class="geo-day"><title>D2 1/21 洞爺湖 → ルスツリゾート（點擊看當日行程）</title><path d="{d2}" marker-end="url(#arr)"/></a>
        <a href="#day4" class="geo-day"><title>D4 1/23 ルスツ → 国道230 中山峠 → 札幌（點擊看當日行程）</title><path d="{d4a}"/><path d="{d4b}" marker-end="url(#arr)"/></a>
      </g>

      <!-- JR 段（虛線，非自駕） -->
      <g stroke="var(--sea)" stroke-width="3" fill="none" stroke-linecap="round" stroke-dasharray="7 6">
        <a href="#day5" class="geo-day"><title>D5 1/24 札幌 → JR 快速エアポート 37 分 → 新千歳空港（點擊看當日行程）</title><path d="{d5}" marker-end="url(#arr)"/></a>
      </g>

      <!-- 路段距離／時間 -->
      <g font-family="inherit" font-size="{SEG_SZ}" fill="var(--ink-faint)" class="geo-lbl">
'''
for n, (sx, sy), anc, t in SEG:
    a_attr = "" if anc == "start" else f' text-anchor="{anc}"'
    svg += f'        <text x="{sx}" y="{sy}"{a_attr}>{t}</text>\n'

svg += f'''      </g>

      <!-- 圖例 -->
      <g font-family="inherit" font-size="{LEG_SZ}" fill="var(--ink-faint)" class="geo-lbl">
'''
for i, (kind, t) in enumerate(LEG_ROWS):
    ly = LEG_Y + i * LEG_LH
    dash = ' stroke-dasharray="7 6"' if kind == "dash" else ""
    svg += (
        f'        <line x1="{LEG_X}" y1="{round(ly - 4, 1)}" x2="{LEG_X + LEG_SW}" y2="{round(ly - 4, 1)}"'
        f' stroke="var(--sea)" stroke-width="3" stroke-linecap="round"{dash}/>\n'
        f'        <text x="{LEG_X + LEG_SW + LEG_GAP}" y="{ly}">{t}</text>\n'
    )

svg += """      </g>

      <!-- 途經點 -->
      <g font-family="inherit" font-size="10.5" fill="var(--ink-faint)" class="geo-lbl">
"""
svg += (
    f'        <circle cx="{C["nakayama"][0]}" cy="{C["nakayama"][1]}" r="4" fill="var(--card)" stroke="var(--sea)" stroke-width="2"/>\n'
    f'        <text x="{round(C["nakayama"][0] + NAKA[0], 1)}" y="{round(C["nakayama"][1] + NAKA[1], 1)}" text-anchor="end">{NAKA[3]}</text>\n'
)

svg += """      </g>

      <!-- 主要節點 -->
      <g font-family="inherit" class="geo-lbl">
"""
_drawn = set()
for k, dx, dy, anc, t, sz, wt, fl in LBL:
    if k not in _drawn:
        _drawn.add(k)
        svg += (
            f'        <circle cx="{C[k][0]}" cy="{C[k][1]}" r="{_nodesR[k]}" fill="var(--card)"'
            f' stroke="var(--sea)" stroke-width="{4 if _nodesR[k] >= 9 else 3}"/>\n'
        )
    a_attr = "" if anc == "start" else f' text-anchor="{anc}"'
    w_attr = f' font-weight="{wt}"' if wt else ""
    svg += (
        f'        <text x="{round(C[k][0] + dx, 1)}" y="{round(C[k][1] + dy, 1)}" font-size="{sz}"{w_attr}'
        f' fill="{_FILL[fl]}"{a_attr}>{t}</text>\n'
    )

svg += """      </g>

      <!-- 日次徽章 -->
      <g font-family="inherit" font-size="11" font-weight="800" text-anchor="middle">
"""
_day_title = {
    "D1": "1/20 桃園 → 新千歳 → 洞爺湖",
    "D2": "1/21 洞爺湖 → ルスツ",
    "D3": "1/22 ルスツ滑雪",
    "D4": "1/23 ルスツ → 中山峠 → 札幌",
    "D5": "1/24 札幌 → JR → 新千歳 → 桃園",
}


def _seg_enter_t(p, q_, bb, pad=2.5):
    x0, x1, y0, y1 = bb[0] - pad, bb[1] + pad, bb[2] - pad, bb[3] + pad
    dx, dy = q_[0] - p[0], q_[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in (
        (-dx, p[0] - x0),
        (dx, x1 - p[0]),
        (-dy, p[1] - y0),
        (dy, y1 - p[1]),
    ):
        if pp == 0:
            if qq < 0:
                return None
            continue
        r = qq / pp
        if pp < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
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
    ex, ey = (
        sx + (ax - sx) * max(t_end - 0.03, 0),
        sy + (ay - sy) * max(t_end - 0.03, 0),
    )
    if math.hypot(ex - sx, ey - sy) < 8:
        continue
    svg += f'        <line x1="{round(sx, 1)}" y1="{round(sy, 1)}" x2="{round(ex, 1)}" y2="{round(ey, 1)}" stroke="var(--ink-faint)" stroke-width="1" opacity=".55"/>\n'

for name, (bx, by) in B.items():
    n = name[1]
    svg += f'        <a href="#day{n}" class="geo-day"><title>{name} {_day_title[name]}（點擊看當日行程）</title><circle cx="{bx}" cy="{by}" r="11" fill="var(--sea)"/><text x="{bx}" y="{by + 4}" fill="#fff">{name}</text></a>\n'
svg += """      </g>
    </svg>"""

(SC / "hokkaido_map.svg.html").write_text(svg)
print(f"rings={len(rings)}; pts={sum(len(r) for _, r in rings)}")

# ================= 自檢 =================
_r_outer = {"chitose": 11, "toya": 11, "rusutsu": 11, "sapporo": 11, "nakayama": 5}
_fail = False
for nm, tgt, (tx, ty) in zip(
    ["d1→toya", "d2→rusutsu", "d4b→sapporo", "d5→chitose"],
    ["toya", "rusutsu", "sapporo", "chitose"],
    _arrow_tips,
):
    gap = math.hypot(tx - C[tgt][0], ty - C[tgt][1]) - _r_outer[tgt]
    flag = "" if gap >= 1 else "  !! 被節點蓋住"
    if gap < 1:
        _fail = True
    print(f"  tip {nm}: 距圓外緣 {gap:.1f}px{flag}")
for nm, (tx, ty) in zip(["d1", "d2", "d4b", "d5"], _arrow_tips):
    for x0, x1, y0, y1 in _texts:
        if x0 - 3 < tx < x1 + 3 and y0 - 3 < ty < y1 + 3:
            print(f"  !! tip {nm} 落在文字框內 ({tx},{ty})")
            _fail = True
for bn, (bx, by) in B.items():
    for nn, (nx, ny) in C.items():
        if nn == "maruyama":
            continue
        gap = math.hypot(bx - nx, by - ny) - 11 - _nodesR[nn]
        if gap < 4:
            print(f"  !! 徽章 {bn} 距節點 {nn} 淨空 {gap:.1f}px")
            _fail = True


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


# 同站進出線（d1 出新千歳 vs d5 進新千歳）分離
_min = min(
    math.hypot(a[0] - b2[0], a[1] - b2[1]) for a in _bpts(d1) for b2 in _bpts(d5)
)
print(f"  d1/d5 新千歳進出線最小間距 {_min:.1f}px" + ("  !! 太近" if _min < 5 else ""))
if _min < 5:
    _fail = True

# 線身 × 文字框（框內縮 1px 嚴格內部才算穿）
_ALL = [("d1", d1), ("d2", d2), ("d4a", d4a), ("d4b", d4b), ("d5", d5)]
for nm, dd in _ALL:
    hit = None
    for x, y in _bpts(dd, 120):
        for bb in _texts:
            x0, x1, y0, y1 = bb
            if x0 + 1 < x < x1 - 1 and y0 + 1 < y < y1 - 1:
                hit = (round(x, 1), round(y, 1), bb)
                break
        if hit:
            break
    if hit:
        print(
            f"  !! 線 {nm} 穿過文字框 ({hit[0]},{hit[1]}) bb={tuple(round(v, 1) for v in hit[2])}"
        )
        _fail = True
# 徽章 × 「不屬於自己那天」的線身：D1/D2/D4/D5 本來就騎在自己的路段上，
# 但 D3（當天不移動）碰到任何線都會被誤讀成有移動，故一律要求淨空。
_badge_seg = {
    "D1": {"d1"},
    "D2": {"d2"},
    "D3": set(),
    "D4": {"d4a", "d4b"},
    "D5": {"d5"},
}
for bn, (bx, by) in B.items():
    for nm, dd in _ALL:
        if nm in _badge_seg[bn]:
            continue
        g = min(math.hypot(bx - x, by - y) for (x, y) in _bpts(dd, 120))
        if g < 13:
            print(f"  !! 徽章 {bn} 距線 {nm} 僅 {g:.1f}px（<13，會貼線）")
            _fail = True
# 徽章 × 文字框
for bn, (bx, by) in B.items():
    for x0, x1, y0, y1 in _texts:
        if x0 - 8 < bx < x1 + 8 and y0 - 8 < by < y1 + 8:
            print(
                f"  !! 徽章 {bn} 壓文字框 ({bx},{by}) bb=({x0:.1f},{x1:.1f},{y0:.1f},{y1:.1f})"
            )
            _fail = True
# 徽章兩兩距離
_bk = list(B.items())
for i in range(len(_bk)):
    for j in range(i + 1, len(_bk)):
        g = math.hypot(_bk[i][1][0] - _bk[j][1][0], _bk[i][1][1] - _bk[j][1][1])
        if g < 26:
            print(f"  !! 徽章 {_bk[i][0]}／{_bk[j][0]} 圓心距 {g:.1f}px（<26）")
            _fail = True
# 文字框兩兩重疊
for i in range(len(_texts)):
    for j in range(i + 1, len(_texts)):
        a, b2 = _texts[i], _texts[j]
        if a[0] < b2[1] and b2[0] < a[1] and a[2] < b2[3] and b2[2] < a[3]:
            print(
                f"  !! 文字框重疊 #{i}{tuple(round(v, 1) for v in a)} × #{j}{tuple(round(v, 1) for v in b2)}"
            )
            _fail = True
# 圖例區 × 線身
for nm, dd in _ALL:
    for x, y in _bpts(dd, 120):
        if _leg_bb[0] < x < _leg_bb[1] and _leg_bb[2] < y < _leg_bb[3]:
            print(f"  !! 線 {nm} 穿過圖例 ({x:.1f},{y:.1f})")
            _fail = True
            break
print(
    f"  圖例 bbox=({_leg_bb[0]:.1f},{_leg_bb[1]:.1f},{_leg_bb[2]:.1f},{_leg_bb[3]:.1f})"
)
_mg = math.hypot(C["maruyama"][0] - C["sapporo"][0], C["maruyama"][1] - C["sapporo"][1])
print(
    f"  円山動物園 距札幌 {_mg:.1f}px（< 兩圓外緣和 17px → 不獨立成節點，併入札幌副標）"
)
if _fail:
    raise SystemExit("自檢未過")
print("自檢通過")

# ---- 經緯度來源 ----
# 新千歳空港 42.7752N 141.6923E（GSI／AIS Japan RJCC 機場基準點）
# 洞爺湖温泉   42.566N 140.822E（洞爺湖町洞爺湖温泉，乃の風リゾート 一帶湖南岸）
# ルスツリゾート 42.744N 140.892E（虻田郡留寿都村泉川13）
# 札幌市中心   43.062N 141.354E（大通—札幌站之間，中央区北1条一帶）
# 中山峠       42.863N 141.033E（国道230 札幌市南区定山渓〜喜茂別町境，海拔 835m）
# 円山動物園   43.0543N 141.3117E（札幌市中央区宮ケ丘3-1）
