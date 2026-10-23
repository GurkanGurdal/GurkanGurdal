"""Profil istatistik kartını üretir: dist/stats.svg

GitHub GraphQL'den herkese açık verileri çeker (katkı takvimi, repolar, diller) ve
README'nin geri kalanıyla aynı görsel dilde bir SVG çizer. GitHub, SVG içindeki yazı
tiplerini engellediği için tüm yazılar vektöre (path) çevrilir.

Kullanım:
  GITHUB_TOKEN=... python profile_stats.py <kullanıcı> <çıktı.svg>
  python profile_stats.py --mock <çıktı.svg>      # örnek veriyle dene
"""
import json, os, random, sys, urllib.request
from datetime import date, timedelta
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

# ------------------------------------------------------------------ text → path
class Font:
    def __init__(self, pkg, weight):
        self.subs = [TTFont(os.path.join(FONTS, f"{pkg}-{s}-{weight}-normal.woff2")) for s in ("latin", "latin-ext")]
        self.upm = self.subs[0]["head"].unitsPerEm
        self.cache = {}
    def _g(self, ch):
        if ch not in self.cache:
            for f in self.subs:
                g = f.getBestCmap().get(ord(ch))
                if g:
                    self.cache[ch] = (f.getGlyphSet(), g); break
            else:
                self.cache[ch] = self._g("?")
        return self.cache[ch]
    def width(self, s, size, tr=0.0):
        sc = size / self.upm
        return sum(self._g(c)[0][self._g(c)[1]].width * sc + tr * size for c in s) - (tr * size if s else 0)
    def path(self, s, size, x, y, tr=0.0):
        sc = size / self.upm; out = []; cx = 0.0
        for ch in s:
            gs, gn = self._g(ch)
            pen = SVGPathPen(gs, ntos=lambda n: ("%.1f" % n).rstrip("0").rstrip("."))
            gs[gn].draw(TransformPen(pen, (sc, 0, 0, -sc, x + cx, y)))
            c = pen.getCommands()
            if c: out.append(c)
            cx += gs[gn].width * sc + tr * size
        return " ".join(out)

SG, I5, MONO = Font("space-grotesk", 700), Font("inter", 500), Font("jetbrains-mono", 400)

def T(font, s, size, x, y, fill, anchor="start", tr=0.0):
    w = font.width(s, size, tr)
    if anchor == "middle": x -= w / 2
    elif anchor == "end": x -= w
    return f'<path d="{font.path(s, size, x, y, tr)}" fill="{fill}"/>'

# ------------------------------------------------------------------ data
QUERY = """query($login:String!){ user(login:$login){
  repositories(ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC, first:100){ totalCount
    nodes{ stargazerCount languages(first:10, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{ name color } } } } }
  contributionsCollection{ contributionCalendar{ totalContributions weeks{ contributionDays{ contributionCount date weekday } } } } } }"""

def fetch(login, token):
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req))
    if "errors" in d: raise SystemExit(d["errors"])
    return d["data"]["user"]

def mock():
    random.seed(4)
    start = date.today() - timedelta(days=370)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    weeks, d = [], start
    while d <= date.today():
        wk = []
        for _ in range(7):
            if d <= date.today():
                c = random.choice([0, 0, 0, 1, 2, 3, 5, 8]) if random.random() < .55 else 0
                wk.append({"contributionCount": c, "date": d.isoformat(), "weekday": (d.weekday() + 1) % 7})
            d += timedelta(days=1)
        weeks.append({"contributionDays": wk})
    langs = [("JavaScript", "#f1e05a", 29), ("TypeScript", "#3178c6", 18), ("Dart", "#00B4AB", 16), ("Jupyter Notebook", "#DA5B0B", 14), ("HTML", "#e34c26", 13), ("CSS", "#663399", 10)]
    return {"repositories": {"totalCount": 11, "nodes": [{"stargazerCount": 1, "languages": {"edges": [{"size": s * 1000, "node": {"name": n, "color": c}} for n, c, s in langs]}}]},
            "contributionsCollection": {"contributionCalendar": {"totalContributions": sum(x["contributionCount"] for w in weeks for x in w["contributionDays"]), "weeks": weeks}}}

def summarize(u):
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    longest = cur = 0
    for d in days:
        cur = cur + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, cur)
    by_wd = [0] * 7
    for d in days: by_wd[d["weekday"]] += d["contributionCount"]
    names = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]
    best = names[by_wd.index(max(by_wd))] if max(by_wd) else "—"
    langs = {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or "#8b8b99"])[0] += e["size"]
    tot = sum(v[0] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    return {"total": cal["totalContributions"], "longest": longest, "best": best,
            "repos": u["repositories"]["totalCount"], "weeks": cal["weeks"],
            "langs": [(n, c, v / tot * 100) for n, (v, c) in top]}

# ------------------------------------------------------------------ render
V, C, P = "#7c5cff", "#22d3ee", "#f472b6"
BG, TILE, LINE = "#0a0a12", "#13131f", "#262636"
LEVELS = [("#1d1d2c", "#16161f", "#121219"), ("#35286e", "#291f57", "#211948"), ("#5136b8", "#3f2a90", "#332276"),
          ("#7c5cff", "#6046d1", "#4f39ad"), ("#c084fc", "#9d5ee0", "#8448c4")]

def tile(x, y, w, h):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="16" fill="{TILE}" stroke="{LINE}"/>'

def label(x, y, s, col="#a78bfa"):
    return T(MONO, s, 13, x, y, col, tr=0.06)

def iso_calendar(weeks, ox, oy, cw=8.4, ch=3.5, hmax=70, n_weeks=53):
    weeks = weeks[-n_weeks:]
    cnts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    mx = max(cnts) if cnts and max(cnts) > 0 else 1
    items = []
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            items.append((wi, d["weekday"], d["contributionCount"]))
    items.sort(key=lambda t: (t[0] + t[1], t[0]))
    out = []
    for wi, di, c in items:
        x = ox + (wi - di) * cw; y = oy + (wi + di) * ch
        lvl = 0 if c == 0 else min(4, 1 + int(3.999 * c / mx))
        h = 2.5 if c == 0 else 6 + (hmax - 6) * (c / mx) ** 0.8
        top, left, right = LEVELS[lvl]
        k = 0.88
        N = (x, y + ch * (1 - k)); E = (x + cw * k, y + ch); S = (x, y + ch * (1 + k)); W_ = (x - cw * k, y + ch)
        up = lambda p: (p[0], p[1] - h)
        pts = lambda *ps: " ".join(f"{a:.1f},{b:.1f}" for a, b in ps)
        g = (f'<g class="b" style="animation-delay:{wi*0.015:.2f}s">'
             f'<polygon points="{pts(up(W_), up(S), S, W_)}" fill="{left}"/>'
             f'<polygon points="{pts(up(S), up(E), E, S)}" fill="{right}"/>'
             f'<polygon points="{pts(up(N), up(E), up(S), up(W_))}" fill="{top}"/></g>')
        out.append(g)
    return "".join(out)

def render(s):
    W, H, pad, g = 900, 600, 14, 12
    lw = 548; rh = 330
    body = [f'<clipPath id="cl"><rect width="{W}" height="{H}" rx="20"/></clipPath><g clip-path="url(#cl)"><rect width="{W}" height="{H}" fill="{BG}"/>',
            f'<circle cx="140" cy="0" r="320" fill="url(#gv)"/><circle cx="{W}" cy="{H}" r="300" fill="url(#gc)"/><rect width="{W}" height="{H}" fill="url(#dots)"/>']
    # calendar tile
    body.append(tile(pad, pad, lw, rh) + label(pad + 24, pad + 36, "KATKI TAKVİMİ · SON 1 YIL"))
    body.append(iso_calendar(s["weeks"], ox=pad + 24 + 7 * 8.4 + 12, oy=pad + 112))
    # legend
    lx = pad + lw - 24 - 5 * 18 - 30
    body.append(T(MONO, "az", 11, lx - 6, pad + 36, "#71717a", anchor="end"))
    for i, (top, _, _) in enumerate(LEVELS):
        body.append(f'<rect x="{lx + i*18}" y="{pad + 25}" width="13" height="13" rx="3" fill="{top}"/>')
    body.append(T(MONO, "çok", 11, lx + 5 * 18 + 2, pad + 36, "#71717a"))
    # counters
    rx = pad + lw + g; rw = W - pad - rx; cw_ = (rw - g) / 2; chh = (rh - g) / 2
    cards = [(f'{s["total"]}', "katkı · son 1 yıl", "#a78bfa"), (f'{s["longest"]} gün', "en uzun seri", "#67e8f9"),
             (s["best"], "en üretken gün", "#f9a8d4"), (f'{s["repos"]}', "public repo", "#fde68a")]
    for i, (val, lbl, col) in enumerate(cards):
        x = rx + (i % 2) * (cw_ + g); y = pad + (i // 2) * (chh + g)
        size = 36
        while SG.width(val, size, -0.02) > cw_ - 40: size -= 2
        body.append(f'<g class="c" style="animation-delay:{0.3 + i*0.12:.2f}s">' + tile(x, y, cw_, chh)
                    + f'<rect x="{x+20:.1f}" y="{y+22:.1f}" width="22" height="4" rx="2" fill="{col}"/>'
                    + T(SG, val, size, x + 20, y + chh - 50, "#fafafa", tr=-0.02)
                    + T(I5, lbl, 14, x + 20, y + chh - 24, "#b4b4bf") + "</g>")
    # languages
    ly = pad + rh + g; lh = H - ly - pad
    body.append(tile(pad, ly, W - 2 * pad, lh) + label(pad + 24, ly + 36, "DİLLER · PUBLIC REPOLAR"))
    bx, by, bw = pad + 24, ly + 60, W - 2 * pad - 48
    body.append(f'<clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="22" rx="11"/></clipPath><rect x="{bx}" y="{by}" width="{bw}" height="22" rx="11" fill="#0d0d17"/>')
    tot = sum(p for _, _, p in s["langs"]) or 1
    cx = bx; segs = []
    for i, (n, col, p) in enumerate(s["langs"]):
        sw = bw * p / tot
        segs.append(f'<rect class="seg" style="animation-delay:{0.2 + i*0.12:.2f}s" x="{cx:.1f}" y="{by}" width="{max(sw-2,1):.1f}" height="22" fill="{col}"/>')
        cx += sw
    body.append(f'<g clip-path="url(#bar)">{"".join(segs)}</g>')
    colw = bw / 3
    for i, (n, col, p) in enumerate(s["langs"]):
        x = bx + (i % 3) * colw; y = by + 62 + (i // 3) * 44
        body.append(f'<circle cx="{x+7}" cy="{y-6}" r="6" fill="{col}"/>' + T(I5, n, 16, x + 22, y, "#e4e4e7")
                    + T(MONO, f"{p:.1f}%", 14, x + colw - 28, y, "#8b8b99", anchor="end"))
    body.append(T(MONO, "her gün otomatik güncellenir", 11, W - pad - 24, H - pad - 16, "#52525b", anchor="end"))
    body.append(f'</g><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="19.5" fill="none" stroke="#fff" stroke-opacity=".08"/>')
    css = (".b{transform-box:fill-box;transform-origin:center bottom;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}"
           "@keyframes grow{from{transform:scaleY(0);opacity:0}}"
           ".c{animation:fade .8s ease both}@keyframes fade{from{opacity:0;transform:translateY(8px)}}"
           ".seg{transform-box:fill-box;transform-origin:left;animation:seg 1s cubic-bezier(.2,.8,.2,1) both}@keyframes seg{from{transform:scaleX(0)}}"
           "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    defs = ('<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="#fff" fill-opacity=".07"/></pattern>'
            f'<radialGradient id="gv"><stop offset="0" stop-color="{V}" stop-opacity=".35"/><stop offset="1" stop-color="{V}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="gc"><stop offset="0" stop-color="{C}" stop-opacity=".2"/><stop offset="1" stop-color="{C}" stop-opacity="0"/></radialGradient></defs>')
    alt = (f'GitHub istatistikleri: son bir yılda {s["total"]} katkı, en uzun seri {s["longest"]} gün, en üretken gün {s["best"]}, '
           f'{s["repos"]} public repo. Diller: ' + ", ".join(f"{n} %{p:.0f}" for n, _, p in s["langs"]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{alt}">'
            f'<title>{alt}</title><style>{css}</style>{defs}{"".join(body)}</svg>')

if __name__ == "__main__":
    if sys.argv[1] == "--mock":
        data, out = mock(), sys.argv[2]
    else:
        data, out = fetch(sys.argv[1], os.environ["GITHUB_TOKEN"]), sys.argv[2]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    s = summarize(data)
    open(out, "w").write(render(s))
    print("yazıldı:", out, {k: v for k, v in s.items() if k != "weeks"})
