#!/usr/bin/env python3
"""Controllo settimanale del sito magrinigelati.it.

Verifica:
  1. collegamenti interni (pagine, immagini, PDF, video, script) che puntano a file mancanti;
  2. collegamenti esterni rotti (404, 410, errori del server);
  3. sito online e velocita' delle pagine principali, peso delle pagine.

Se trova un errore esce con codice 1: GitHub segna il controllo come fallito
e manda la mail di avviso. Gli avvisi minori finiscono solo nel resoconto.
Solo libreria standard di Python, nessuna installazione.
"""
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
SITO = "https://www.magrinigelati.it"
PAGINE_LIVE = ["/", "/catalogo.html", "/privacy.html", "/novita/", "/commerciale/", "/portale/"]
# percorsi serviti da altri repository (portale agenti e buste paga): si verificano online, non come file
ALTRI_REPO = ("/commerciale", "/portale")

# soglie
SECONDI_MAX = 5.0          # oltre: errore (sito troppo lento o bloccato)
SECONDI_AVVISO = 2.5       # oltre: avviso
PESO_PAGINA_AVVISO = 8e6   # byte di pagina + risorse locali
PESO_FILE_AVVISO = 1.5e6   # singola immagine o PDF pesante

# siti che bloccano i controlli automatici: un rifiuto non e' un link rotto
BLOCCANO_ROBOT = ("instagram.com", "facebook.com", "linkedin.com", "api.whatsapp.com", "wa.me")
UA = "Mozilla/5.0 (controllo-sito magrinigelati.it)"

errori: list[str] = []
avvisi: list[str] = []

RIF = re.compile(r'''(?:href|src|poster|data-src)\s*=\s*["']([^"']+)["']''', re.I)
CARICATI = re.compile(r'''(?:src|poster|data-src)\s*=\s*["']([^"']+)["']''', re.I)  # cio' che il browser scarica
RIF_CSS = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''', re.I)
RIF_JS = re.compile(r'''["']((?:\.?/)?(?:img|docs|video|fonts|catalogo)/[^"']+)["']''')


def locale(rif: str, base: Path) -> Path | None:
    """Percorso del file locale a cui punta un riferimento, o None se esterno/speciale."""
    rif = rif.strip()
    if not rif or rif.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:")):
        return None
    p = urllib.parse.urlsplit(rif)
    if p.scheme in ("http", "https"):
        if p.netloc.lower() in ("www.magrinigelati.it", "magrinigelati.it"):
            percorso = p.path
        else:
            return None
    elif p.scheme or p.netloc:
        return None
    else:
        percorso = p.path
    if not percorso or "${" in percorso or "{{" in percorso:
        return None
    if percorso.startswith(ALTRI_REPO):
        return None
    percorso = urllib.parse.unquote(percorso)
    f = (RADICE / percorso.lstrip("/")) if percorso.startswith("/") else (base / percorso)
    f = Path(os.path.normpath(f))
    if f.is_dir() or percorso.endswith("/"):
        f = f / "index.html"
    return f


def esterni_di(testo: str) -> set[str]:
    out = set()
    for r in RIF.findall(testo):
        p = urllib.parse.urlsplit(r.strip())
        if p.scheme in ("http", "https") and p.netloc.lower() not in ("www.magrinigelati.it", "magrinigelati.it"):
            out.add(r.strip())
    return out


def richiesta(url: str, metodo: str = "GET", timeout: float = 20):
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def controlla_esterno(url: str) -> None:
    host = urllib.parse.urlsplit(url).netloc.lower()
    ultimo = ""
    for tentativo in range(2):
        try:
            with richiesta(url, "GET") as r:
                r.read(1024)
            return
        except urllib.error.HTTPError as e:
            if host.endswith(BLOCCANO_ROBOT) or e.code in (401, 403, 405, 429, 999):
                return  # risposta di protezione, la pagina esiste
            ultimo = f"HTTP {e.code}"
            if e.code in (404, 410):
                break
        except Exception as e:  # rete, timeout, certificato
            ultimo = type(e).__name__ + ": " + str(e)[:120]
        time.sleep(3)
    errori.append(f"Link esterno non raggiungibile ({ultimo}): {url}")


def main() -> int:
    file_html = sorted(p for p in RADICE.rglob("*.html") if ".git" not in p.parts and "email" not in p.parts)
    file_js = sorted((RADICE / "catalogo").glob("*.js"))
    esterni: dict[str, set[str]] = {}
    peso_pagina: dict[str, int] = {}

    # 1. riferimenti interni
    for f in file_html + file_js:
        testo = f.read_text(encoding="utf-8", errors="replace")
        nome = str(f.relative_to(RADICE))
        refs = set(RIF_JS.findall(testo)) if f.suffix == ".js" else set(RIF.findall(testo)) | set(RIF_CSS.findall(testo))
        base = RADICE if f.suffix == ".js" else f.parent  # i .js del catalogo lavorano dalla radice
        totale = f.stat().st_size
        caricati = set(CARICATI.findall(testo)) | set(RIF_CSS.findall(testo)) if f.suffix == ".html" else set()
        for r in sorted(refs):
            dest = locale(r, base)
            if dest is None:
                continue
            if not dest.exists():
                tipo = "PDF mancante" if dest.suffix.lower() == ".pdf" else "File mancante"
                errori.append(f"{tipo}: {r}  (in {nome})")
                continue
            dim = dest.stat().st_size
            if r in caricati:
                totale += dim
            if dim > PESO_FILE_AVVISO and dest.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"):
                avvisi.append(f"File pesante ({dim/1e6:.1f} MB): {dest.relative_to(RADICE)}")
        if f.suffix == ".html":
            peso_pagina[nome] = totale
            for u in esterni_di(testo):
                esterni.setdefault(u, set()).add(nome)

    if os.environ.get("SOLO_LOCALE"):  # prova senza internet
        esterni.clear()
        PAGINE_LIVE.clear()
    # 2. collegamenti esterni
    for u in sorted(esterni):
        controlla_esterno(u)

    # 3. sito online e velocita'
    tempi = []
    for p in PAGINE_LIVE:
        url = SITO + p
        try:
            t0 = time.monotonic()
            with richiesta(url, timeout=30) as r:
                corpo = r.read()
            s = time.monotonic() - t0
            tempi.append((p, s, len(corpo)))
            if s > SECONDI_MAX:
                errori.append(f"Pagina troppo lenta ({s:.1f} s): {url}")
            elif s > SECONDI_AVVISO:
                avvisi.append(f"Pagina lenta ({s:.1f} s): {url}")
        except Exception as e:
            errori.append(f"Pagina non raggiungibile ({type(e).__name__}: {str(e)[:120]}): {url}")

    # PDF online: un campione dei documenti, per verificare che il sito li serva davvero
    for pdf in ([] if os.environ.get("SOLO_LOCALE") else sorted((RADICE / "docs").rglob("*.pdf"))):
        url = SITO + "/" + urllib.parse.quote(str(pdf.relative_to(RADICE)))
        try:
            with richiesta(url, "HEAD") as r:
                pass
        except urllib.error.HTTPError as e:
            errori.append(f"PDF non scaricabile dal sito (HTTP {e.code}): {url}")
        except Exception:
            pass  # rete: gia' segnalato sopra se il sito e' giu'

    for nome, peso in peso_pagina.items():
        if peso > PESO_PAGINA_AVVISO:
            avvisi.append(f"Pagina pesante ({peso/1e6:.1f} MB con immagini e file): {nome}")

    # resoconto
    righe = ["# Controllo sito magrinigelati.it", ""]
    righe.append(f"Esito: **{'PROBLEMI DA SISTEMARE' if errori else 'tutto in ordine'}**")
    righe += ["", f"Pagine controllate: {len(file_html)}, collegamenti esterni: {len(esterni)}", ""]
    if tempi:
        righe.append("| Pagina | Tempo | Peso HTML |")
        righe.append("| --- | --- | --- |")
        righe += [f"| {p} | {s:.2f} s | {b/1e3:.0f} KB |" for p, s, b in tempi]
        righe.append("")
    if errori:
        righe += ["## Errori", ""] + [f"- {e}" for e in errori] + [""]
    if avvisi:
        righe += ["## Avvisi (nessuna mail per questi)", ""] + [f"- {a}" for a in sorted(set(avvisi))] + [""]
    testo = "\n".join(righe)
    print(testo)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(testo + "\n")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
