"""東京迪士尼：首都圈定位、上野周邊與東京灣放大圖。

預設只自檢（不寫檔、不連網）；--output 新路徑以 x 模式拒絕覆寫。
海岸、原五點、原行程景點、路線一律用 XY，再作等比例仿射。
地形取自现有 japan.geojson；虛線為行程連線，並非實際鐵路線形。
"""
import argparse
import hashlib
import json
import math
import re
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

SC = Path(__file__).resolve().parent
COS = math.cos(math.radians(35.7))
PREF_IDS = {8, 11, 12, 13, 14}
# 保留 b405eee 的五個原始點位；odaiba 原本即台場／豐洲區域代表點。
P = {
    'narita': (140.386, 35.772),
    'maihama': (139.879, 35.632),
    'odaiba': (139.782, 35.638),
    'ueno': (139.777, 35.712),
    'shinagawa': (139.736, 35.628),
}
# 只展開既有行程景點。官網交通頁地圖座標，2026-09-28 核對：
# https://www.senso-ji.jp/access/ （淺草寺）
# https://www.tokyo-skytree.jp/access/ （英文地圖中心）
# https://teamlabplanets.dmm.com/en/guide （Google Maps 景點座標）
DETAIL_P = {
    'asakusa': (139.796730, 35.714634),
    'skytree': (139.8107, 35.710063),
    'toyosu': (139.7898285, 35.6491075),
}
POINTS = {**P, **DETAIL_P}


def XY(lon, lat):
    """固定標準緯線；所有圖只變更等比例 scale / translate。"""
    return ((lon - 139.6) * COS * 1000, (35.98 - lat) * 1000)


C = {k: XY(*v) for k, v in POINTS.items()}
# day, start, end, bend；日次及順序取自原頁每日行程。
ROUTES = [
    (1, 'narita', 'maihama', -.15),
    (4, 'maihama', 'toyosu', -.15),
    (4, 'toyosu', 'odaiba', -.12),
    (4, 'odaiba', 'ueno', -.15),
    (5, 'ueno', 'shinagawa', .22),
    (5, 'shinagawa', 'skytree', .26),
    (6, 'ueno', 'asakusa', -.18),
    (6, 'asakusa', 'ueno', -.18),
    (7, 'ueno', 'narita', -.16),
]
# west, east, south, north；首都圈含完整東京灣，細圖按旅程適切放大。
WINDOWS = {
    'locator': (139.40, 140.62, 35.13, 36.02),
    'city': (139.763, 139.822, 35.694, 35.730),
    'bay': (139.702, 139.910, 35.593, 35.690),
}
STATIONS = {
    'locator': ('narita', 'ueno', 'maihama'),
    'city': ('ueno', 'asakusa', 'skytree'),
    'bay': ('maihama', 'toyosu', 'odaiba', 'shinagawa'),
}
# x, y, width, 中文主標, 副標；引線連接地理點，不為排版搬動節點。
LABELS = {
    'locator': {
        'narita': (186, 10, 144, '成田機場', 'D1 抵達・D7 返台'),
        'ueno': (10, 87, 115, '上野', 'D4–D6 住宿'),
        'maihama': (186, 293, 144, '舞濱・迪士尼', 'D1–D3 住宿'),
    },
    'city': {
        'ueno': (10, 14, 144, '上野', 'D4–D6・&Here'),
        'asakusa': (178, 14, 152, '淺草', 'D6 和服・淺草寺'),
        'skytree': (178, 310, 152, '晴空塔', 'D5 寶可夢中心'),
    },
    'bay': {
        'toyosu': (10, 12, 157, '豐洲', 'D4 teamLab Planets'),
        'maihama': (182, 12, 148, '舞濱・迪士尼', 'D2 陸地・D3 海洋'),
        'shinagawa': (10, 310, 151, '品川水族館', 'D5 Maxell Aqua Park'),
        'odaiba': (178, 310, 152, '台場', 'D4 午餐'),
    },
}
DAYS = [
    ('8/3（日）', '成田・舞濱', '抵達・入住夢幻泉鄉', '電車約 60–75 分'),
    ('8/4（一）', '迪士尼樂園', '陸地園區・夢幻泉鄉第 2 晚', '雙園行程第 1 日'),
    ('8/5（二）', '迪士尼海洋', 'Fantasy Springs・換宿玩具總動員', '雙園行程第 2 日'),
    ('8/6（三）', '豐洲・台場・上野', 'teamLab・入住 &Here', '舞濱 → 豐洲 → 台場 → 上野（電車）'),
    ('8/7（四）', '品川・晴空塔', '水族館・寶可夢中心', '上野 → 品川 → 晴空塔（電車）'),
    ('8/8（五）', '淺草和服日', '淺草寺・雷門・仲見世', '上野 ⇄ 淺草（電車 12–15 分）'),
    ('8/9（六）', '上野・成田返台', '成田 T2・JX803', 'Skyliner 最快約 45 分'),
]


def rdp(points, eps):
    if len(points) < 3:
        return points
    (ax, ay), (bx, by) = points[0], points[-1]
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy) or 1e-12
    distances = [abs(dy*x - dx*y + bx*ay - by*ax)/length for x, y in points[1:-1]]
    idx = distances.index(max(distances)) + 1
    if distances[idx-1] <= eps:
        return [points[0], points[-1]]
    return rdp(points[:idx+1], eps)[:-1] + rdp(points[idx:], eps)


def coast():
    """保留東京灣小島／填海地；不使用舊版會刪小島的面積門檻。"""
    features = json.loads((SC / 'japan.geojson').read_text())['features']
    rings = []
    for feature in features:
        if feature['properties']['id'] not in PREF_IDS:
            continue
        geom = feature['geometry']
        polygons = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        for poly in polygons:
            paths = []
            for ring in poly:
                xs, ys = zip(*ring)
                if max(xs) < 139.3 or min(xs) > 140.7 or max(ys) < 35.1 or min(ys) > 36.1:
                    continue
                # 地形一次簡化、三圖共用；0.00012 度約十公尺級。
                mid = len(ring)//2
                simple = rdp(ring[:mid+1], .00012)[:-1] + rdp(ring[mid:], .00012)
                paths.append('M' + ' L'.join(f'{x:.3f},{y:.3f}' for x,y in (XY(*p) for p in simple)) + ' Z')
            if paths:
                rings.append(' '.join(paths))
    return rings


def affine(name):
    west, east, south, north = WINDOWS[name]
    x0, y0 = XY(west, north)
    x1, y1 = XY(east, south)
    s = min(292/(x1-x0), 278/(y1-y0))
    return s, 170-(x0+x1)*s/2, 195-(y0+y1)*s/2


def screen(name, point):
    s, tx, ty = affine(name)
    x, y = C[point]
    return s*x+tx, s*y+ty


def route_path(a, b, bend):
    x1, y1 = C[a]
    x2, y2 = C[b]
    cx, cy = (x1+x2)/2-(y2-y1)*bend, (y1+y2)/2+(x2-x1)*bend
    return f'M{x1:.3f},{y1:.3f} Q{cx:.3f},{cy:.3f} {x2:.3f},{y2:.3f}'


def svg(name, land):
    s, tx, ty = affine(name)
    titles = {'locator': '東京灣與首都圈定位', 'city': '上野・淺草・晴空塔放大圖', 'bay': '舞濱・豐洲・台場・品川放大圖'}
    out = [f'<svg class="geo-map geo-{name}" viewBox="0 0 340 400" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="disney-{name}-title disney-{name}-desc">',
           f'<title id="disney-{name}-title">{titles[name]}</title>',
           f'<desc id="disney-{name}-desc">北方朝上。地形與站點共用等距投影，虛線為電車行程示意；細灰引線連接標籤與地理點位。</desc>',
           f'<defs><clipPath id="disney-{name}-clip"><rect width="340" height="400" rx="12"/></clipPath></defs>',
           f'<g clip-path="url(#disney-{name}-clip)"><rect width="340" height="400" fill="var(--gm-ocean)"/>',
           f'<g class="geo-geography" transform="translate({tx:.6f} {ty:.6f}) scale({s:.9f})">',
           '<g class="geo-land" fill="var(--gm-land)" stroke="var(--gm-coast)" fill-rule="evenodd">']
    out += [f'<path d="{p}" stroke-width="{.65/s:.6f}"/>' for p in land]
    out.append('</g>')
    if name == 'locator':
        for window in ('city', 'bay'):
            w,e,so,n = WINDOWS[window]
            x,y = XY(w,n)
            xx,yy = XY(e,so)
            out.append(f'<rect data-travel-window="{window}" x="{x:.3f}" y="{y:.3f}" width="{xx-x:.3f}" height="{yy-y:.3f}" fill="none" stroke="var(--gm-ink)" stroke-width="{1/s:.6f}" stroke-dasharray="{3/s:.6f} {3/s:.6f}"/>')
    shown_days = {'locator': {1,7}, 'city': {5,6}, 'bay': {4,5}}[name]
    for day,a,b,bend in ROUTES:
        if day in shown_days:
            out.append(f'<path class="geo-route geo-d{day}" data-route-segment="d{day}-{a}-{b}" d="{route_path(a,b,bend)}" fill="none" stroke="var(--gm-d{day})" stroke-width="{2.6/s:.6f}" stroke-dasharray="{6/s:.6f} {4/s:.6f}" stroke-linecap="round"><title>D{day} 電車行程示意</title></path>')
    for key in STATIONS[name]:
        x,y = C[key]
        lon,lat = POINTS[key]
        out.append(f'<circle data-station="{key}" data-lon="{lon}" data-lat="{lat}" cx="{x:.3f}" cy="{y:.3f}" r="{4/s:.6f}" fill="var(--gm-paper)" stroke="var(--gm-ink)" stroke-width="{2/s:.6f}"/>')
    out += ['</g>', '</g>']
    for key,(x,y,width,title,subtitle) in LABELS[name].items():
        px,py = screen(name,key)
        qx,qy = max(x+8,min(x+width-8,px)), max(y+8,min(y+52,py))
        out += [f'<g class="geo-station-label" data-label="{key}">',
                f'<path class="geo-leader" d="M{px:.3f},{py:.3f} L{qx:.3f},{qy:.3f}"/>',
                f'<rect x="{x}" y="{y}" width="{width}" height="60" rx="9"/>',
                f'<text x="{x+10}" y="{y+25}" font-size="18" font-weight="800">{escape(title)}</text>',
                f'<text class="geo-subtitle" x="{x+10}" y="{y+46}" font-size="12">{escape(subtitle)}</text>', '</g>']
    notes = {'locator': [(58,259,'東京灣'),(233,237,'千葉縣'),(30,310,'神奈川縣'),(190,98,'D7'),(253,159,'D1')],
             'city': [(20,277,'D6 上野 ⇄ 淺草'),(190,287,'D5 品川 → 晴空塔')],
             'bay': [(23,98,'D4 舞濱 → 豐洲 → 台場 → 上野'),(124,273,'東京灣'),(18,287,'D5 上野 → 品川 → 晴空塔')]}
    for x,y,text in notes[name]:
        out.append(f'<text class="geo-note" x="{x}" y="{y}" font-size="12">{escape(text)}</text>')
    out += ['<text class="geo-note" x="14" y="389" font-size="12">↑ 北</text>', '</svg>']
    return '\n'.join(out)


def render():
    land = coast()
    panels = [
        ('locator','01 / 首都圈定位','東京灣・成田','抵達與返程，連接兩個住宿區'),
        ('city','02 / 市區放大','上野・淺草・晴空塔','D4–D6 以上野為住宿基地'),
        ('bay','03 / 灣岸放大','舞濱・東京灣岸','D1–D3 迪士尼，D4 起探索東京'),
    ]
    out = ['  <!-- trip-map:generated:start -->','<div class="geo-panel">',
           '<div class="geo-intro"><strong>七天，從夢幻園區到東京街角</strong><span>2025/8/3–8/9 · 北方朝上</span></div>',
           '<div class="geo-atlas">']
    for name,kicker,title,subtitle in panels:
        out += [f'<figure class="geo-{name}-panel"><figcaption><span>{kicker}</span><b>{title}</b><span>{subtitle}</span></figcaption>',svg(name,land),'</figure>']
    out += ['</div>','<div class="geo-legend" aria-label="交通與日次圖例">']
    for day,text in [(1,'D1 電車'),(4,'D4 電車'),(5,'D5 電車'),(6,'D6 電車'),(7,'D7 Skyliner')]:
        out.append(f'<span><i style="--route:var(--gm-d{day})"></i>{text}</span>')
    out += ['<span>○ 景點／住宿區</span></div>',
            '<p class="geo-map-note">虛線表示每日移動順序，並非實際鐵路線形；定位圖框線對應兩張放大圖。舞濱以度假區代表點標示雙園與飯店，台場沿用原圖區域代表點。點選下方日次卡查看完整行程。</p>','</div>',
            '<div class="geo-days" aria-label="七日日次卡">']
    for day,(date,title,subtitle,transit) in enumerate(DAYS,1):
        out.append(f'<a class="geo-day-card" href="#day{day}"><span class="geo-day-num">D{day}</span><span class="geo-day-copy"><small>{date}</small><strong>{escape(title)}</strong><span>{escape(subtitle)}</span><small>{escape(transit)}</small></span></a>')
    out += ['</div>','  <!-- trip-map:generated:end -->']
    return '\n'.join(out)+'\n'


def check(output):
    ns = {'s':'http://www.w3.org/2000/svg'}
    assert P == {'narita':(140.386,35.772),'maihama':(139.879,35.632),'odaiba':(139.782,35.638),'ueno':(139.777,35.712),'shinagawa':(139.736,35.628)}
    geometries = []
    for name,source in zip(WINDOWS,re.findall(r'<svg\b.*?</svg>',output,re.S)):
        tree = ET.fromstring(source)
        geometries.append([p.attrib['d'] for p in tree.find(".//s:g[@class='geo-land']",ns)])
        for c in tree.findall('.//s:circle[@data-station]',ns):
            key = c.attrib['data-station']
            expected = XY(float(c.attrib['data-lon']),float(c.attrib['data-lat']))
            assert all(abs(float(c.attrib[axis])-v)<.001 for axis,v in zip(('cx','cy'),expected))
            x,y = screen(name,key)
            assert 5<x<335 and 5<y<395, (name,key,x,y)
            for lx,ly,w,_,_ in LABELS[name].values():
                assert not lx-5<x<lx+w+5 or not ly-5<y<ly+65, (name,key,'node hidden by label')
        boxes = list(LABELS[name].values())
        for i,(x,y,w,title,subtitle) in enumerate(boxes):
            assert 0<=x and x+w<=340 and 0<=y and y+60<=400
            assert sum(18 if ord(c)>0x2e80 else 10 for c in title)<=w-20
            for xx,yy,ww,_,_ in boxes[i+1:]:
                assert x+w<=xx or xx+ww<=x or y+60<=yy or yy+60<=y
        for p in tree.findall('.//s:path[@data-route-segment]',ns):
            day,a,b=p.attrib['data-route-segment'].split('-')
            route=next(r for r in ROUTES if r[:3]==(int(day[1:]),a,b))
            assert p.attrib['d']==route_path(a,b,route[3])
    assert len(geometries)==3 and geometries[0]==geometries[1]==geometries[2]
    assert all(f'class="geo-day-card" href="#day{day}"' in output for day in range(1,8))
    print('PASS 原五座標保留；三圖共用地形／投影／路線；標籤互不重疊且不遮站點；七日日次卡')
    print('generated SHA256:',hashlib.sha256(output.encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='只接受尚不存在的新檔案路徑')
    args = parser.parse_args()
    output = render()
    check(output)
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as file:
            file.write(output)
        print('新檔案:',args.output)


if __name__ == '__main__':
    main()
