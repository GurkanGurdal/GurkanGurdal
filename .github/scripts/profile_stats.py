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
  allRepos: repositories(ownerAffiliations:OWNER, privacy:PUBLIC){ totalCount }
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
    return {"allRepos": {"totalCount": 11}, "repositories": {"totalCount": 10, "nodes": [{"stargazerCount": 1, "languages": {"edges": [{"size": s * 1000, "node": {"name": n, "color": c}} for n, c, s in langs]}}]},
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
            "repos": u.get("allRepos", u["repositories"])["totalCount"], "weeks": cal["weeks"],
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
        import math
        lvl = 0 if c == 0 else (2 if mx <= 1 else min(4, 1 + int(3.999 * math.log(c) / math.log(mx))))
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

# ------------------------------------------------------------------ outro: imleç katkı grafiğini boyar
I6 = Font("inter", 600)
PAINT = ["#1d1d2c", "#5b45c9", "#7c5cff", "#a78bfa", "#e9d5ff"]

def render_outro(s):
    W, H = 900, 400
    CYCLE = 12.0                     # saniye
    SWEEP = (0.06, 0.46)             # imlecin grafiği boyadığı aralık (döngünün oranı)
    HOLD_END, FADE_END = 0.86, 0.93  # boyalı grafik bu noktaya kadar durur, sonra silinir
    weeks = s["weeks"][-53:]
    n = len(weeks)
    pitch, cell = 14.6, 11.6
    gw = n * pitch - (pitch - cell)
    gx = (W - gw) / 2; gy = 152
    cnts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    mx = max(cnts) if cnts and max(cnts) > 0 else 1
    import math
    def lvl(c):
        if c == 0: return 0
        if mx <= 1: return 2
        return min(4, 1 + int(3.999 * math.log(c) / math.log(mx)))

    body = [f'<clipPath id="cl"><rect width="{W}" height="{H}" rx="20"/></clipPath><g clip-path="url(#cl)"><rect width="{W}" height="{H}" fill="{BG}"/>',
            f'<circle cx="120" cy="0" r="300" fill="url(#gv)"/><circle cx="{W}" cy="{H}" r="300" fill="url(#gc)"/><rect width="{W}" height="{H}" fill="url(#dots)"/>']
    # dalgalar
    for col, op, amp, dur, yy in [(V, .32, 14, 9, 330), (C, .2, 10, 12, 344), (P, .22, 8, 7, 358)]:
        d = f"M0 {yy}" + "".join(f" q150 {-amp if k % 2 == 0 else amp} 300 0" for k in range(8)) + f" V{H} H0 Z"
        body.append(f'<path class="wv" style="animation-duration:{dur}s" d="{d}" fill="{col}" fill-opacity="{op}"/>')
    # başlık
    body.append(T(SG, "Okuduğun için teşekkürler.", 32, W / 2, 70, "#fafafa", anchor="middle", tr=-0.02))
    body.append(T(I5, "Bir fikrin mi var? Birlikte tasarlayıp kodlayalım.", 18, W / 2, 104, "#b4b4bf", anchor="middle"))
    # zemin ızgarası
    base = []
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            base.append(f'<rect x="{gx + wi*pitch:.1f}" y="{gy + d["weekday"]*pitch:.1f}" width="{cell}" height="{cell}" rx="2.5" fill="{PAINT[0]}"/>')
    body.append("".join(base))
    # boya: her hafta kendi zamanlamasıyla
    kf, paint = [], []
    for wi, w in enumerate(weeks):
        p0 = SWEEP[0] + (SWEEP[1] - SWEEP[0]) * wi / max(n - 1, 1)
        p1 = p0 + 0.015
        kf.append(f"@keyframes k{wi}{{0%,{p0*100:.2f}%{{opacity:0;transform:scale(.2)}}{p1*100:.2f}%{{opacity:1;transform:scale(1.25)}}"
                  f"{(p1+0.01)*100:.2f}%,{HOLD_END*100:.0f}%{{opacity:1;transform:scale(1)}}{FADE_END*100:.0f}%,100%{{opacity:0;transform:scale(1)}}}}"
                  f".w{wi}{{animation:k{wi} {CYCLE}s linear infinite}}")
        for d in w["contributionDays"]:
            l = lvl(d["contributionCount"])
            if l == 0: continue
            paint.append(f'<rect class="pc w{wi}" x="{gx + wi*pitch:.1f}" y="{gy + d["weekday"]*pitch:.1f}" width="{cell}" height="{cell}" rx="2.5" fill="{PAINT[l]}"/>')
    body.append("".join(paint))
    # fırça izi: imleci takip eden ışıklı şerit
    gh_ = 6 * pitch + cell
    body.append(f'<linearGradient id="br" x1="0" x2="1"><stop offset="0" stop-color="{V}" stop-opacity="0"/><stop offset=".85" stop-color="#a78bfa" stop-opacity=".35"/><stop offset="1" stop-color="#e9d5ff" stop-opacity=".7"/></linearGradient>'
                f'<rect class="br" x="{gx - 70:.1f}" y="{gy - 4:.1f}" width="72" height="{gh_ + 8:.1f}" rx="4" fill="url(#br)"/>')
    # seçim çerçevesi + etiket
    fx0, fy0 = gx - 8, gy - 8; fx1, fy1 = gx + gw + 8, gy + 6 * pitch + cell + 8
    lab = f'son 1 yıl · {s["total"]} katkı'
    lw = MONO.width(lab, 12) + 18
    handles = "".join(f'<rect x="{x-4:.1f}" y="{y-4:.1f}" width="8" height="8" rx="1.5" fill="#fff" stroke="{V}" stroke-width="1.5"/>'
                      for x, y in [(fx0, fy0), (fx1, fy0), (fx0, fy1), (fx1, fy1)])
    body.append(f'<g class="fr"><rect x="{fx0:.1f}" y="{fy0:.1f}" width="{fx1-fx0:.1f}" height="{fy1-fy0:.1f}" fill="{V}" fill-opacity=".05" stroke="{V}" stroke-width="1.5"/>{handles}'
                f'<rect x="{(fx0+fx1)/2 - lw/2:.1f}" y="{fy1+10:.1f}" width="{lw:.1f}" height="20" rx="5" fill="{V}"/>'
                + T(MONO, lab, 12, (fx0 + fx1) / 2, fy1 + 24, "#fff", anchor="middle") + "</g>")
    # imleç
    tag_w = I6.width("Gürkan", 12) + 16
    body.append(f'<g class="cur"><path d="M0 0 L0 20 L5.5 15 L9.5 24 L13 22.5 L9 13.8 L16 13.8 Z" fill="{V}" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>'
                f'<rect x="14" y="22" width="{tag_w:.0f}" height="20" rx="6" fill="{V}"/>' + T(I6, "Gürkan", 12, 22, 36, "#fff") + "</g>")
    body.append(f'</g><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="19.5" fill="none" stroke="#fff" stroke-opacity=".08"/>')

    x0, x1 = gx + 2, gx + gw - 2
    y_mid = gy + 3 * pitch
    cur_kf = (f"@keyframes cur{{0%{{transform:translate({W+20}px,{gy-40}px)}}"
              f"{SWEEP[0]*100:.1f}%{{transform:translate({x0:.0f}px,{y_mid:.0f}px)}}"
              + "".join(f"{(SWEEP[0]+(SWEEP[1]-SWEEP[0])*k/8)*100:.1f}%{{transform:translate({x0+(x1-x0)*k/8:.0f}px,{y_mid + (22 if k % 2 else -22):.0f}px)}}" for k in range(1, 8))
              + f"{SWEEP[1]*100:.1f}%{{transform:translate({x1:.0f}px,{y_mid:.0f}px)}}"
              f"52%,60%{{transform:translate({fx0:.0f}px,{fy1:.0f}px)}}"
              f"{HOLD_END*100:.0f}%{{transform:translate({fx0+30:.0f}px,{fy1+40:.0f}px)}}"
              f"100%{{transform:translate({W+20}px,{gy-40}px)}}}}")
    css = ("".join(kf) + ".pc{transform-box:fill-box;transform-origin:center}"
           + cur_kf + f".cur{{animation:cur {CYCLE}s cubic-bezier(.45,0,.55,1) infinite}}"
           + f".br{{opacity:0;animation:br {CYCLE}s linear infinite}}@keyframes br{{0%,{SWEEP[0]*100-.5:.1f}%{{opacity:0;transform:translateX(0)}}{SWEEP[0]*100+1:.1f}%{{opacity:1;transform:translateX(0)}}"
             f"{SWEEP[1]*100:.1f}%{{opacity:1;transform:translateX({gw:.0f}px)}}{SWEEP[1]*100+3:.1f}%,100%{{opacity:0;transform:translateX({gw:.0f}px)}}}}"
           + f".fr{{opacity:0;animation:fr {CYCLE}s ease infinite}}@keyframes fr{{0%,{SWEEP[1]*100+2:.0f}%{{opacity:0}}{SWEEP[1]*100+6:.0f}%,{HOLD_END*100:.0f}%{{opacity:1}}{FADE_END*100:.0f}%,100%{{opacity:0}}}}"
           + ".wv{animation:wv linear infinite}@keyframes wv{from{transform:translateX(0)}to{transform:translateX(-600px)}}"
           + "@media (prefers-reduced-motion:reduce){*{animation:none!important}.pc,.fr{opacity:1}}")
    defs = ('<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="#fff" fill-opacity=".07"/></pattern>'
            f'<radialGradient id="gv"><stop offset="0" stop-color="{V}" stop-opacity=".35"/><stop offset="1" stop-color="{V}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="gc"><stop offset="0" stop-color="{C}" stop-opacity=".2"/><stop offset="1" stop-color="{C}" stop-opacity="0"/></radialGradient></defs>')
    alt = f'Okuduğun için teşekkürler. Gürkan imleci son bir yılın katkı grafiğini boyuyor: {s["total"]} katkı.'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{alt}">'
            f'<title>{alt}</title><style>{css}</style>{defs}{"".join(body)}</svg>')

if __name__ == "__main__":
    # profile_stats.py <kullanıcı|--mock> <çıktı klasörü>  → stats.svg ve outro.svg
    data = mock() if sys.argv[1] == "--mock" else fetch(sys.argv[1], os.environ["GITHUB_TOKEN"])
    out = sys.argv[2]
    if out.endswith(".svg"): out = os.path.dirname(out) or "."
    os.makedirs(out, exist_ok=True)
    s = summarize(data)
    open(os.path.join(out, "stats.svg"), "w").write(render(s))
    open(os.path.join(out, "outro.svg"), "w").write(render_outro(s))
    print("yazıldı:", out, {k: v for k, v in s.items() if k != "weeks"})
