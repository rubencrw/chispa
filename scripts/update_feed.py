#!/usr/bin/env python3
"""
Chispa: actualización diaria del feed de noticias.

1. Descarga los RSS de las fuentes de referencia (ES + EN).
2. Descarta lo ya publicado en los últimos días.
3. Pide a Claude (API de Anthropic) que elija ~50 historias y las resuma en español,
   teniendo en cuenta tus gustos (data/prefs.json, que rellena la propia web).
4. Escribe feeds/AAAA-MM-DD.json y actualiza feeds/index.json.

Requisitos:  pip install feedparser requests
Uso:         ANTHROPIC_API_KEY=sk-... SITE_DIR=/ruta/a/la/web python3 update_feed.py
"""
import os, sys, json, re, html, time, calendar, datetime, random
import feedparser, requests

SITE_DIR   = os.environ.get("SITE_DIR", os.path.join(os.path.dirname(__file__), ".."))
API_KEY    = os.environ.get("ANTHROPIC_API_KEY")
MODEL      = os.environ.get("CHISPA_MODEL", "claude-sonnet-5")
TARGET     = int(os.environ.get("CHISPA_TARGET", "50"))
KEEP_DAYS  = int(os.environ.get("CHISPA_KEEP_DAYS", "14"))
MAX_AGE_H  = 72          # antigüedad máxima de una noticia candidata
PER_FEED   = 12          # candidatas máximas por fuente

FEEDS = {
    # nombre visible, url, idioma, tema por defecto (orientativo)
    "ScienceDaily":      ("https://www.sciencedaily.com/rss/top/science.xml", "en"),
    "ScienceDaily Salud":("https://www.sciencedaily.com/rss/top/health.xml", "en"),
    "ScienceDaily Tecnología": ("https://www.sciencedaily.com/rss/top/technology.xml", "en"),
    "ScienceDaily Nutrición":  ("https://www.sciencedaily.com/rss/health_medicine/nutrition.xml", "en"),
    "ScienceDaily Arqueología":("https://www.sciencedaily.com/rss/fossils_ruins/archaeology.xml", "en"),
    "Nature":            ("https://www.nature.com/nature.rss", "en"),
    "Quanta Magazine":   ("https://www.quantamagazine.org/feed/", "en"),
    "Live Science":      ("https://www.livescience.com/feeds/all", "en"),
    "Phys.org":          ("https://phys.org/rss-feed/science-news/archaeology-fossils/", "en"),
    "Medical Xpress":    ("https://medicalxpress.com/rss-feed/", "en"),
    "STAT News":         ("https://www.statnews.com/feed/", "en"),
    "MIT Technology Review": ("https://www.technologyreview.com/feed/", "en"),
    "TechCrunch":        ("https://techcrunch.com/category/artificial-intelligence/feed/", "en"),
    "BBC Ciencia":       ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "en"),
    "BBC Economía":      ("https://feeds.bbci.co.uk/news/business/rss.xml", "en"),
    "BBC Tecnología":    ("https://feeds.bbci.co.uk/news/technology/rss.xml", "en"),
    "Smithsonian":       ("https://www.smithsonianmag.com/rss/history/", "en"),
    "Xataka":            ("https://www.xataka.com/feedburner.xml", "es"),
    "Expansión":         ("https://e00-expansion.uecdn.es/rss/economia.xml", "es"),
    "Muy Interesante":   ("https://www.muyinteresante.com/rss", "es"),
    "The Conversation":  ("https://theconversation.com/es/articles.atom", "es"),
}
CATS = ["ciencia", "ia", "tecnologia", "medicina", "nutricion", "historia", "economia"]
MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
DIAS  = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

def clean(t, n=320):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def recent_urls(feeds_dir, days=7):
    seen = set()
    idx = load_json(os.path.join(feeds_dir, "index.json"), {"days": []})
    for d in idx.get("days", [])[:days]:
        doc = load_json(os.path.join(feeds_dir, f"{d['date']}.json"), {"items": []})
        for it in doc.get("items", []): seen.add(it.get("url"))
    return seen

def collect(seen):
    now, out = time.time(), []
    for name, (url, lang) in FEEDS.items():
        try:
            d = feedparser.parse(url, agent="Mozilla/5.0 (Chispa news digest)")
        except Exception as e:
            log("fallo", name, e); continue
        n = 0
        for e in d.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            ts = calendar.timegm(t) if t else None
            if ts and now - ts > MAX_AGE_H * 3600: continue
            link = (e.get("link") or "").split("?at_medium")[0]
            title = clean(e.get("title"), 200)
            if not link or not title or link in seen: continue
            if re.search(r"oferta|rebaja|descuento|precio al mínimo|STAT\+|The Download|tickets?", title, re.I): continue
            out.append({"src": name.split(" ")[0] if name.startswith(("ScienceDaily","BBC")) else name,
                        "lang": lang, "title": title, "summary": clean(e.get("summary")),
                        "url": link, "date": time.strftime("%m-%d", time.gmtime(ts)) if ts else ""})
            seen.add(link); n += 1
            if n >= PER_FEED: break
        log(f"{name}: {n}")
    return out

def prefs_block(site_dir):
    p = load_json(os.path.join(site_dir, "data", "prefs.json"), None)
    if not p: return "Aún no hay datos de gustos: mantén un reparto equilibrado entre temas."
    w = p.get("weights", {})
    liked = [r["title"] for r in p.get("recent", []) if (r.get("l") or r.get("s")) and r.get("title")][:30]
    skipped = [r["title"] for r in p.get("recent", []) if r.get("x") and r.get("title")][:20]
    return ("Puntuación de interés por tema (más alto = más interés; negativo = menos): "
            + json.dumps(w, ensure_ascii=False)
            + "\nHistorias que le gustaron o guardó:\n- " + "\n- ".join(liked or ["(ninguna todavía)"])
            + "\nHistorias que descartó:\n- " + "\n- ".join(skipped or ["(ninguna todavía)"])
            + "\nDa más peso a temas y ángulos parecidos a los que le gustan, menos a los descartados, "
              "pero reserva siempre al menos 3 historias por tema para que pueda descubrir cosas nuevas.")

SYSTEM = """Eres el editor de «Chispa», un feed vertical de noticias interesantes para un lector adulto curioso en España.
Temas: ciencia, ia, tecnologia, medicina, nutricion, historia, economia.
Tu trabajo: elegir las mejores historias de la lista de candidatas y escribir cada tarjeta EN ESPAÑOL.

Criterios de selección: sorprendentes, útiles o con impacto; evita ofertas, notas de empresa sin interés, política de partido,
sucesos, contenido de pago (STAT+) y duplicados (si dos candidatas cuentan lo mismo, elige una y pon la otra en "extra").

Reglas de redacción (muy importantes):
- Usa SOLO la información de la candidata (título y resumen). No inventes cifras, nombres, fechas ni resultados.
- title: titular en español, claro y con gancho, máx. 90 caracteres.
- idea: 1-2 frases con la idea principal.
- conclusion: 1 frase de «por qué importa» o qué nos deja; puede ser interpretativa pero prudente.
- hook: una cifra o palabra corta sacada del texto (máx. 10 caracteres, p. ej. "222 m", "+30%", "5.500"), o "" si no hay una clara.
- hookLabel: 3-7 palabras que expliquen el hook ("" si no hay hook).
- Si es un estudio en animales o preliminar, dilo.

Responde SOLO con JSON válido, sin texto adicional ni ```:
{"items":[{"i":<número de candidata>,"cat":"<tema>","hook":"","hookLabel":"","title":"","idea":"","conclusion":"","extra":[<números de candidatas duplicadas>]}]}"""

def ask_claude(cands, prefs):
    listing = "\n".join(
        f"[{i}] ({c['src']}, {c['lang']}, {c['date']}) {c['title']} || {c['summary']}" for i, c in enumerate(cands))
    user = (f"Elige unas {TARGET} historias (mínimo {TARGET-5}) y ordénalas de más a menos interesante.\n\n"
            f"GUSTOS DEL LECTOR:\n{prefs}\n\nCANDIDATAS:\n{listing}")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=600, headers={
        "x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 20000, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]})
    if not r.ok:
        log("Respuesta de la API:", r.status_code, r.text[:2000])
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    text = re.sub(r"^```(json)?|```$", "", text.strip()).strip()
    return json.loads(text[text.find("{"): text.rfind("}") + 1])

def build_items(sel, cands):
    items, used = [], set()
    for s in sel.get("items", []):
        i = s.get("i")
        if not isinstance(i, int) or not (0 <= i < len(cands)) or i in used: continue
        c = cands[i]; used.add(i)
        cat = s.get("cat") if s.get("cat") in CATS else "ciencia"
        extra = [{"label": cands[j]["src"], "url": cands[j]["url"]}
                 for j in (s.get("extra") or []) if isinstance(j, int) and 0 <= j < len(cands) and j != i][:2]
        slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower())[:40].strip("-")
        items.append({"id": f"{cat[:2]}-{slug}-{i}", "cat": cat,
                      "hook": (s.get("hook") or "")[:12], "hookLabel": (s.get("hookLabel") or "")[:60],
                      "title": s.get("title") or c["title"], "idea": s.get("idea", ""),
                      "conclusion": s.get("conclusion", ""),
                      "source": c["src"], "url": c["url"], "date": c["date"], "lang": c["lang"], "extra": extra})
    return items   # las URLs salen siempre de los RSS, nunca del modelo

def main():
    if not API_KEY: sys.exit("Falta ANTHROPIC_API_KEY")
    feeds_dir = os.path.join(SITE_DIR, "feeds"); os.makedirs(feeds_dir, exist_ok=True)
    today = datetime.date.today()
    date = today.isoformat()
    cands = collect(recent_urls(feeds_dir))
    random.shuffle(cands)
    log(f"candidatas: {len(cands)}")
    if len(cands) < 20: sys.exit("Muy pocas candidatas; revisa la conexión o las fuentes.")
    items = build_items(ask_claude(cands, prefs_block(SITE_DIR)), cands)
    log(f"seleccionadas: {len(items)}")
    if len(items) < 15: sys.exit("La respuesta del modelo no es válida; no se toca el feed.")
    label = f"{DIAS[today.weekday()]} {today.day} de {MESES[today.month-1]}"
    doc = {"date": date, "label": label, "generatedAt": datetime.datetime.utcnow().isoformat() + "Z", "items": items}
    tmp = os.path.join(feeds_dir, f".{date}.tmp")
    with open(tmp, "w", encoding="utf-8") as f: json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(feeds_dir, f"{date}.json"))

    idx = load_json(os.path.join(feeds_dir, "index.json"), {"days": []})
    days = [d for d in idx.get("days", []) if d["date"] != date]
    days.insert(0, {"date": date, "label": label, "count": len(items)})
    days.sort(key=lambda d: d["date"], reverse=True)
    for old in days[KEEP_DAYS:]:
        try: os.remove(os.path.join(feeds_dir, f"{old['date']}.json"))
        except FileNotFoundError: pass
    idx = {"updatedAt": doc["generatedAt"], "days": days[:KEEP_DAYS]}
    tmp = os.path.join(feeds_dir, ".index.tmp")
    with open(tmp, "w", encoding="utf-8") as f: json.dump(idx, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(feeds_dir, "index.json"))
    log("hecho:", date)

if __name__ == "__main__":
    main()
