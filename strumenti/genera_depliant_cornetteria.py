#!/usr/bin/env python3
"""Genera il PDF della Linea Cornetteria dal file catalogo/cornetteria.js.
Uso: python3 strumenti/genera_depliant_cornetteria.py . docs/depliant/magrini-linea-cornetteria.pdf
Serve Playwright con Chromium. La foto di copertina e' img/catalogo/cornetteria/copertina-foto.jpg.
Impaginazione: copertina, pagine prodotti (3 file da 3 schede per pagina, sezioni continue), pagina prezzi e condizioni.
"""
import json, re, sys, os, html, asyncio

REPO = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])

s = open(os.path.join(REPO, 'catalogo/cornetteria.js'), encoding='utf-8').read()
m = re.search(r'window\.CATALOGO\.cornetteria\s*=\s*', s)
L = json.loads(s[m.end():s.rindex(';')])
P = L['prodotti']

SEZ = {
    'CORNETTI E GRANCORNETTI': ('Cornetti e grancornetti', 'Grancornetti, alta pasticceria Ischia e Paris, cornetti multicereali, bicolore e salati.'),
    'PLANT BASED': ('Plant based', "Cornetti senza ingredienti di origine animale, adatti a un'alimentazione vegana."),
    'FAGOTTI E SFOGLIE': ('Fagotti e sfoglie', 'Fagotti, trecce e sfoglie pronte da infornare.'),
    'CIAMBELLE E DONUT': ('Ciambelle e donut', 'Ciambelle e bomboloni già cotti.'),
    'PERLA': ('Perla', 'La sfoglia a conchiglia e altre sfoglie da forno.'),
}
PILLOLE = ['Pronto forno', 'Vegano', 'Già cotto']

def it(v):
    if isinstance(v, dict): return v.get('it', '')
    return v or ''

e = html.escape
from PIL import Image, ImageChops
TRIM = OUT + '_img'; os.makedirs(TRIM, exist_ok=True)
def ritaglia(rel):
    src = os.path.join(REPO, rel); dst = os.path.join(TRIM, os.path.basename(rel).rsplit('.',1)[0] + '.jpg')
    im = Image.open(src).convert('RGB')
    bg = Image.new('RGB', im.size, (255,255,255))
    d = ImageChops.difference(im, bg).convert('L').point(lambda v: 255 if v > 18 else 0)
    bb = d.getbbox() or (0,0)+im.size
    pad = 6
    bb = (max(0,bb[0]-pad), max(0,bb[1]-pad), min(im.width,bb[2]+pad), min(im.height,bb[3]+pad))
    angoli = [im.getpixel(xy) for xy in [(2,2),(im.width-3,2),(2,im.height-3),(im.width-3,im.height-3)]]
    pieno = sum(1 for c in angoli if min(c) < 235) >= 2
    out = im if pieno else im.crop(bb)
    if out.width > 700: out = out.resize((700, round(out.height * 700 / out.width)), Image.LANCZOS)
    out.save(dst, quality=86)
    return dst, pieno


# gruppi nell'ordine del file
gruppi = []
for p in P:
    g = p['gruppo']
    if not gruppi or gruppi[-1][0] != g: gruppi.append((g, []))
    gruppi[-1][1].append(p)

# impaginazione: massimo 3 file per pagina; una sezione nuova parte in una pagina con spazio
pagine = []   # ogni pagina: lista di blocchi (gruppo, prodotti, continua)
cur, righe = [], 0
for g, prods in gruppi:
    i = 0; prima = True
    while i < len(prods):
        if righe >= 3:
            pagine.append(cur); cur, righe = [], 0
        libere = 3 - righe
        n = min(len(prods) - i, libere * 3)
        cur.append((g, prods[i:i+n], not prima))
        righe += (n + 2) // 3
        i += n; prima = False
if cur: pagine.append(cur)

def scheda(p):
    img, pieno = ritaglia(p['img'])
    eti = it(p.get('eti'))
    pills = [it(t) for t in p.get('tags', []) if it(t) in PILLOLE]
    return f'''<div class="card">
  <div class="ph{' full' if pieno else ''}">{f'<span class="eti">{e(eti)}</span>' if eti else ''}<img src="file://{img}"></div>
  <div class="tx">
    <div class="marca">{e(p['marca'].upper())}</div>
    <div class="nome">{e(p['nome'])}</div>
    <div class="fmt">{e(it(p['fmt']))}</div>
    <div class="cod">cod. {e(p['cod'])}</div>
    {('<div class="pills">' + ''.join(f'<span>{e(x)}</span>' for x in pills) + '</div>') if pills else ''}
  </div>
</div>'''

FOOT = '<b>Prezzi e condizioni riservati.</b> Chiedi al tuo agente di zona o scrivi a info@magrinigelati.it, tel. 085 8941066'

corpo = []
n_tot = len(P)
logo = os.path.join(REPO, 'img/logo-magrini.png')
cop = os.environ.get('COPERTINA_FOTO') or os.path.join(REPO, 'img/catalogo/cornetteria/copertina-foto.jpg')
corpo.append(f'''<section class="pag cover">
  <div class="logo"><img src="file://{logo}"></div>
  <div class="kick">CATALOGO {e(L['anno'])}</div>
  <h1>{e(L['titolo'])}</h1>
  <div class="tric"><i></i><i></i><i></i></div>
  <p class="intro">Cornetti, sfoglie, ciambelle e colazioni da forno per bar, pasticcerie e hotel. {n_tot} proposte per la prima colazione.</p>
  <div class="hero"><img src="file://{cop}"></div>
  <div class="cfoot"><b>MAGRINI R. &amp; CECI G. SNC</b> · Via Norvegia 5 · 64026 Roseto degli Abruzzi (TE)<br>Tel. 085 8941066 · info@magrinigelati.it · www.magrinigelati.it</div>
</section>''')

for k, pag in enumerate(pagine):
    num = k + 2
    blocchi = []
    for g, prods, cont in pag:
        t, sub = SEZ[g]
        blocchi.append(f'''<h2 class="{'cont' if cont else ''}">{e(t)}</h2>{'' if cont else f'<p class="sub">{e(sub)}</p>'}
<div class="grid">{''.join(scheda(p) for p in prods)}</div>''')
    corpo.append(f'''<section class="pag prod">
  <div class="kick">LINEA CORNETTERIA {e(L['anno'])}</div>
  {''.join(blocchi)}
  <div class="pfoot"><span>{FOOT}</span><span>{num}</span></div>
</section>''')

corpo.append(f'''<section class="pag fine">
  <div class="logo big"><img src="file://{logo}"></div>
  <h2>Prezzi e condizioni</h2>
  <p class="ris">Sono riservati ai nostri clienti: chiedi al tuo agente di zona oppure scrivici.</p>
  <p class="ditta"><b>MAGRINI R. &amp; CECI G. SNC</b><br>Via Norvegia, 5 · 64026 Roseto degli Abruzzi (TE)<br>Tel. 085 8941066<br>info@magrinigelati.it<br>www.magrinigelati.it</p>
  <p class="sdi">Codice SdI 5RUO82D · P. IVA 00257660670</p>
  <p class="nota">Le immagini sono indicative. Disponibilità e formati possono variare.</p>
</section>''')

F = os.path.join(REPO, 'fonts')
CSS = f'''
@font-face{{font-family:Figtree;src:url(file://{F}/figtree-latin-400-normal.woff2);font-weight:400}}
@font-face{{font-family:Figtree;src:url(file://{F}/figtree-latin-500-normal.woff2);font-weight:500}}
@font-face{{font-family:Figtree;src:url(file://{F}/figtree-latin-700-normal.woff2);font-weight:700}}
@font-face{{font-family:YS;src:url(file://{F}/young-serif-latin-400-normal.woff2)}}
@font-face{{font-family:DMM;src:url(file://{F}/dm-mono-latin-500-normal.woff2)}}
@page{{size:A4;margin:0}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Figtree;color:#333344;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.pag{{width:210mm;height:297mm;position:relative;overflow:hidden;page-break-after:always;background:#F6F2E4}}
.kick{{font:500 11.6px DMM;letter-spacing:.32em;color:#2446a0}}
.prod{{padding:62px 53px 0}}
.prod h2{{font:400 27px/1.2 YS;color:#2446a0;margin-top:11px}}
.prod h2.cont{{margin-bottom:13px}}
.prod .sub{{font:500 11.6px Figtree;color:#586080;margin:4px 0 15px}}
.grid{{display:grid;grid-template-columns:repeat(3,218.7px);column-gap:15px;row-gap:17px;margin-bottom:16px}}
.card{{background:#fff;border-radius:15px;height:248.5px;box-shadow:0 2px 6px rgba(40,40,20,.08);overflow:hidden;position:relative}}
.ph{{height:105.5px;border-bottom:1px solid #E8E3D0;display:flex;align-items:center;justify-content:center;position:relative}}
.ph img{{max-width:150px;max-height:90px;object-fit:contain}}
.ph.full img{{max-width:none;max-height:none;width:100%;height:100%;object-fit:cover}}
.eti{{position:absolute;left:10px;top:10px;background:#FCC80B;color:#1a2140;font:700 8.9px Figtree;letter-spacing:.06em;padding:4px 9px;border-radius:999px}}
.tx{{padding:15px 15px 0}}
.marca{{font:500 8.9px DMM;letter-spacing:.12em;color:#8a8fa6}}
.nome{{font:400 14.2px/1.18 YS;color:#1a2140;margin-top:4px}}
.fmt{{font:500 10.7px Figtree;color:#586080;margin-top:4px}}
.cod{{font:500 8.9px DMM;color:#8a8fa6;margin-top:5px}}
.pills{{margin-top:6px;display:flex;gap:4px}}
.pills span{{font:500 8.9px Figtree;color:#2446a0;border:1px solid #c5cee3;border-radius:999px;padding:2px 8px}}
.pfoot{{position:absolute;left:53px;right:53px;bottom:33px;border-top:1px solid #D8D2BC;padding-top:8px;display:flex;justify-content:space-between;font:500 9.8px Figtree;color:#586080}}
.pfoot b{{color:#333344}}
.cover{{background:linear-gradient(#F7E6D0,#E9CDA4);padding:61px}}
.logo{{width:155px;height:119px;background:#fff;border-radius:15px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(60,40,10,.08)}}
.logo img{{width:124px}}
.cover .kick{{margin-top:52px;font-size:11.6px}}
.cover h1{{font:400 53px/1.25 YS;color:#2446a0;margin-top:2px}}
.tric{{display:flex;width:181px;height:8px;margin-top:14px}}
.tric i{{flex:1}}.tric i:nth-child(1){{background:#009246}}.tric i:nth-child(2){{background:#ddd}}.tric i:nth-child(3){{background:#CE2B37}}
.intro{{font:500 16px/1.45 Figtree;color:#333344;margin-top:18px;max-width:500px}}
.hero{{margin-top:24px;width:672px;height:559px;border-radius:10px 85px 10px 10px;overflow:hidden;box-shadow:0 4px 14px rgba(60,40,10,.15)}}
.hero img{{width:100%;height:100%;object-fit:cover}}
.cfoot{{position:absolute;left:61px;right:61px;bottom:56px;border-top:1px solid #B9C4DD;padding-top:12px;font:500 11.6px/1.6 Figtree;color:#333344}}
.fine{{text-align:center;padding-top:190px}}
.logo.big{{margin:0 auto;width:240px;height:181px}}
.logo.big img{{width:205px}}
.fine h2{{font:400 34.7px YS;color:#2446a0;margin-top:52px}}
.ris{{font:500 16px/1.4 Figtree;color:#333344;margin:16px auto 0;max-width:480px}}
.ditta{{font:500 16px/1.85 Figtree;color:#1a2140;margin-top:40px}}
.sdi{{font:500 13.3px Figtree;color:#586080;margin-top:4px}}
.nota{{position:absolute;left:0;right:0;bottom:85px;font:500 9.8px Figtree;color:#586080}}
'''

doc = f'<!doctype html><html lang="it"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(corpo)}</body></html>'
tmp = OUT + '.html'
open(tmp, 'w', encoding='utf-8').write(doc)

from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        await pg.goto('file://' + tmp)
        await pg.wait_for_load_state('networkidle')
        await pg.evaluate('document.fonts.ready')
        await pg.pdf(path=OUT, format='A4', print_background=True, prefer_css_page_size=True)
        await b.close()
asyncio.run(main())
print('pagine prodotti:', [[(g, len(p)) for g, p, c in pg] for pg in pagine])
