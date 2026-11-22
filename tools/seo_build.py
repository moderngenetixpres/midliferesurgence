#!/usr/bin/env python3
"""Midlife Resurgence SEO build. Run from repo root before every commit:
    python3 tools/seo_build.py
- Sets <title> and meta description from tools/seo-pages.json (page values win; else keeps the page's own).
- Writes one managed block between <!-- SEO:BEGIN --> and <!-- SEO:END --> in each page head:
  canonical, Open Graph, Twitter card, JSON-LD (WebSite/Organization/Person, Article, ProfilePage,
  PodcastSeries + VideoObject ItemList on videos.html, CollectionPage on read/index.html).
- Regenerates read/index.html (article hub), sitemap.xml and robots.txt.
- New YouTube embeds on videos.html get their uploadDate from YouTube once and are cached in tools/video-dates.json.
Idempotent: running twice changes nothing. To revert a page, delete its SEO block.
"""
import json, re, os, subprocess, html, datetime, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CFG = json.load(open('tools/seo-pages.json'))
SITE = CFG['site']
DEF_IMG = SITE + CFG['default_image']
BEGIN, END = '<!-- SEO:BEGIN (managed by tools/seo_build.py) -->', '<!-- SEO:END -->'

def url_for(path):
    if path == 'index.html': return SITE + '/'
    if path == 'read/index.html': return SITE + '/read/'
    return SITE + '/' + path

def git_dates(path):
    out = subprocess.run(['git', 'log', '--format=%aI', '--', path], capture_output=True, text=True).stdout.split()
    return (out[-1] if out else None, out[0] if out else None)

def text(s): return html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).replace('\u00a0', ' ').strip()
def squash(s): return re.sub(r'\s+', ' ', s).strip()
def esc(s): return html.escape(s, quote=True)

def page_info(path, h):
    g = lambda p: (re.search(p, h, re.S | re.I) or [None, None])[1]
    cfg = CFG['pages'].get(path, {})
    title = cfg.get('title') or squash(text(g(r'<title>(.*?)</title>')))
    desc = cfg.get('description') or html.unescape(g(r'<meta name="description" content="(.*?)"') or '')
    h1 = squash(text((g(r'<h1[^>]*>(.*?)</h1>') or '').replace('<br>', ' ')))
    img = g(r'<img class="hero" src="([^"]+)"')
    img = (SITE + img if img and img.startswith('/') else img) or DEF_IMG
    created, modified = git_dates(path)
    date = cfg.get('date') or (created or datetime.date.today().isoformat())[:10]
    mod = (modified or date)[:10]
    return dict(cfg=cfg, title=title, desc=desc, h1=h1, img=img, date=date, mod=mod, url=url_for(path))

def person():
    p = dict(CFG['person']); p['@type'] = 'Person'; p['@id'] = SITE + '/#mike-gill'
    p['worksFor'] = {'@id': SITE + '/#org'}
    return p
def org():
    o = dict(CFG['org']); o['@type'] = 'Organization'; o['@id'] = SITE + '/#org'
    return o

def video_dates():
    f = 'tools/video-dates.json'
    return json.load(open(f)) if os.path.exists(f) else {}

def fetch_upload(vid):
    try:
        req = urllib.request.Request('https://www.youtube.com/watch?v=' + vid, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US', 'Cookie': 'CONSENT=YES+1'})
        h = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'ignore')
        up = re.search(r'"uploadDate":"([^"]+)"', h); ln = re.search(r'"lengthSeconds":"(\d+)"', h)
        return {'uploadDate': up and up.group(1), 'lengthSeconds': ln and int(ln.group(1))}
    except Exception as e:
        print('  warn: could not fetch', vid, e); return None

def iso_dur(sec):
    if not sec: return None
    m, s = divmod(int(sec), 60); h, m = divmod(m, 60)
    return 'PT' + (f'{h}H' if h else '') + (f'{m}M' if m else '') + f'{s}S'

def videos_ld(h):
    cache = video_dates(); changed = False; items = []
    eps = re.findall(r'<article class="ep">\s*<div class="kicker">(.*?)</div>\s*<h3>(.*?)</h3>.*?embed/([A-Za-z0-9_-]{11})', h, re.S)
    shorts = re.findall(r'embed/([A-Za-z0-9_-]{11})" title="([^"]*)"[^>]*></iframe></div><figcaption>', h)
    allv = [(k, t, v) for k, t, v in eps] + [('Short', t, v) for v, t in shorts]
    for kicker, t, vid in allv:
        if vid not in cache or not (cache[vid] or {}).get('uploadDate'):
            r = fetch_upload(vid)
            if r and r.get('uploadDate'): cache[vid] = r; changed = True
        meta = cache.get(vid) or {}
        if not meta.get('uploadDate'): continue  # never invent a date
        name = squash(text(t)); k = squash(text(kicker))
        v = {'@type': 'VideoObject', 'name': name,
             'description': (f'{k}: {name}. With Coach Mike Gill.' if k != 'Short' else f'Short: {name}. Coach Mike Gill, Midlife Resurgence.'),
             'thumbnailUrl': [f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'], 'uploadDate': meta['uploadDate'],
             'embedUrl': f'https://www.youtube-nocookie.com/embed/{vid}', 'contentUrl': f'https://www.youtube.com/watch?v={vid}'}
        d = iso_dur(meta.get('lengthSeconds'))
        if d: v['duration'] = d
        items.append(v)
    if changed: json.dump(cache, open('tools/video-dates.json', 'w'), indent=1, sort_keys=True)
    return items

def faq_ld(h):
    """FAQPage from any <h2>FAQ...</h2> section: each <h3> question + following <p> answers until the next <h2>."""
    m = re.search(r'<h2>\s*FAQ[^<]*</h2>(.*?)(?=<h2|</div>\s*</body>|$)', h, flags=re.S | re.I)
    if not m: return None
    qs = []
    for q, a in re.findall(r'<h3[^>]*>(.*?)</h3>(.*?)(?=<h3|$)', m.group(1), flags=re.S):
        ans = squash(text(' '.join(re.findall(r'<p[^>]*>(.*?)</p>', a, flags=re.S))))
        if squash(text(q)) and ans:
            qs.append({'@type': 'Question', 'name': squash(text(q)), 'acceptedAnswer': {'@type': 'Answer', 'text': ans}})
    return {'@type': 'FAQPage', 'mainEntity': qs} if qs else None

def build_ld(path, info, h):
    t = info['cfg'].get('type', 'page')
    graph = []
    if t == 'home':
        graph += [{'@type': 'WebSite', '@id': SITE + '/#website', 'url': SITE + '/', 'name': 'Midlife Resurgence', 'description': info['desc'], 'publisher': {'@id': SITE + '/#org'}, 'author': {'@id': SITE + '/#mike-gill'}}, org(), person()]
    elif t == 'profile':
        graph += [{'@type': 'ProfilePage', 'url': info['url'], 'name': info['title'], 'mainEntity': {'@id': SITE + '/#mike-gill'}}, person(), org()]
    elif t == 'article':
        graph += [{'@type': 'Article', 'headline': info['h1'][:110], 'description': info['desc'], 'image': [info['img']],
                   'datePublished': info['date'], 'dateModified': max(info['mod'], info['date']), 'articleSection': info['cfg'].get('section'),
                   'author': {'@type': 'Person', 'name': 'Mike Gill', 'url': SITE + '/bio.html'},
                   'publisher': {'@type': 'Organization', 'name': 'Modern Genetix', 'url': 'https://moderngenetix.com'},
                   'mainEntityOfPage': info['url'], 'isPartOf': {'@type': 'WebSite', 'name': 'Midlife Resurgence', 'url': SITE + '/'}}]
    elif t == 'videos':
        for p in CFG['podcasts']:
            graph.append({'@type': 'PodcastSeries', 'name': p['name'], 'url': info['url'], 'webFeed': p['feed'], 'author': {'@type': 'Person', 'name': 'Mike Gill'}, 'publisher': {'@type': 'Organization', 'name': 'Modern Genetix'}})
        vids = videos_ld(h)
        graph.append({'@type': 'ItemList', 'name': 'Midlife Resurgence and Doc & Coach videos', 'itemListElement': [dict(position=i + 1, **{'@type': 'ListItem', 'item': v}) for i, v in enumerate(vids)]})
    elif t == 'readhub':
        graph.append({'@type': 'CollectionPage', 'name': info['title'], 'url': info['url'], 'description': info['desc']})
    else:
        graph.append({'@type': 'WebPage', 'name': info['title'], 'url': info['url'], 'description': info['desc'], 'isPartOf': {'@type': 'WebSite', 'name': 'Midlife Resurgence', 'url': SITE + '/'}})
    faq = faq_ld(h)
    if faq: graph.append(faq)
    if t not in ('home',):
        crumbs = [{'@type': 'ListItem', 'position': 1, 'name': 'Midlife Resurgence', 'item': SITE + '/'}]
        if path.startswith('read/') and path != 'read/index.html':
            crumbs.append({'@type': 'ListItem', 'position': 2, 'name': 'Read', 'item': SITE + '/read/'})
        crumbs.append({'@type': 'ListItem', 'position': len(crumbs) + 1, 'name': info['h1'] or info['title'], 'item': info['url']})
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': crumbs})
    def clean(o):
        if isinstance(o, dict): return {k: clean(v) for k, v in o.items() if v not in (None, '', [])}
        if isinstance(o, list): return [clean(x) for x in o]
        return o
    return json.dumps({'@context': 'https://schema.org', '@graph': clean(graph)}, ensure_ascii=False, indent=1).replace('</', '<\\/')

def seo_block(path, info, h):
    t = info['cfg'].get('type', 'page')
    og = 'article' if t == 'article' else ('profile' if t == 'profile' else 'website')
    lines = [BEGIN,
        f'<link rel="canonical" href="{info["url"]}" />',
        '<meta name="robots" content="index, follow, max-image-preview:large" />',
        f'<meta property="og:site_name" content="Midlife Resurgence" />',
        f'<meta property="og:type" content="{og}" />',
        f'<meta property="og:title" content="{esc(info["title"])}" />',
        f'<meta property="og:description" content="{esc(info["desc"])}" />',
        f'<meta property="og:url" content="{info["url"]}" />',
        f'<meta property="og:image" content="{info["img"]}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        '<meta name="twitter:site" content="@prostrongman" />',
        f'<meta name="twitter:title" content="{esc(info["title"])}" />',
        f'<meta name="twitter:description" content="{esc(info["desc"])}" />',
        f'<meta name="twitter:image" content="{info["img"]}" />']
    if t == 'article':
        lines.append(f'<meta property="article:published_time" content="{info["date"]}" />')
    lines += ['<script type="application/ld+json">', build_ld(path, info, h), '</script>', END]
    return '\n'.join(lines)

def apply(path):
    h = open(path, encoding='utf-8').read()
    info = page_info(path, h)
    new = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', h, flags=re.S)
    new = re.sub(r'<title>.*?</title>', f'<title>{esc(info["title"])}</title>', new, count=1, flags=re.S)
    if info['desc']:
        md = f'<meta name="description" content="{esc(info["desc"])}" />'
        if re.search(r'<meta name="description"[^>]*>', new):
            new = re.sub(r'<meta name="description"[^>]*>', md, new, count=1)
        else:
            new = new.replace(f'<title>{esc(info["title"])}</title>', f'<title>{esc(info["title"])}</title>\n  {md}', 1)
    new = new.replace('</head>', seo_block(path, info, new) + '\n</head>', 1)
    if new != h:
        open(path, 'w', encoding='utf-8').write(new); print('updated', path)
    return info

READ_HUB = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Read</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Oswald:wght@500;600&display=swap" rel="stylesheet" />
  <style>
    :root { --bg:#050608; --ink:#f4f6f8; --silver:#c5cdd4; --mute:#8b939c; --cyan:#19c6e6; --line:rgba(25,198,230,.35); }
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--ink);font-family:Inter,system-ui,sans-serif;min-height:100vh;padding:28px 48px 64px}
    a{color:var(--cyan);text-decoration:none}
    .brand{letter-spacing:.34em;font-size:11px;font-weight:600;color:var(--silver);margin-bottom:48px}
    .brand span{color:var(--cyan)}
    h1{font-family:Oswald,sans-serif;font-size:clamp(40px,7vw,72px);letter-spacing:.04em;text-transform:uppercase;margin-bottom:18px}
    .rule{width:72px;height:2px;background:var(--cyan);margin-bottom:18px}
    p{color:var(--silver);max-width:40em;line-height:1.55;margin-bottom:14px}
    .list{margin:24px 0 0;max-width:44em}
    .list a{display:block;padding:16px 0;border-top:1px solid var(--line);color:var(--ink)}
    .list a span{display:block;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan);margin-bottom:4px}
    .list a strong{display:block;font-size:17px;font-weight:600;margin-bottom:4px}
    .list a em{display:block;font-style:normal;color:var(--mute);font-size:14px;line-height:1.45}
    .back{display:inline-block;margin-top:28px;font-size:12px;letter-spacing:.12em;text-transform:uppercase}
    .disclaimer{margin-top:36px;color:var(--mute);font-size:12px;max-width:40em;line-height:1.5}
  </style>
</head>
<body>
  <div class="brand"><a href="/" style="color:inherit">MODERN <span>GENETIX</span></a></div>
  <h1>Read</h1>
  <div class="rule"></div>
  <p>Training, nutrition and mindset for men over 40 who are still building. From Coach Mike Gill.</p>
  <div class="list">
{items}
  </div>
  <p style="margin-top:28px"><a href="/training.html">Training programs</a> · <a href="/nutrition.html">Nutrition</a> · <a href="/videos.html">Videos</a> · <a href="/bio.html">About Coach Mike</a></p>
  <a class="back" href="/">← Midlife Resurgence</a>
  <p class="disclaimer">I am not a doctor. This is not medical advice. Talk to your physician before you start a fitness or nutrition program.</p>
</body>
</html>
'''

def build_read_hub(infos):
    arts = [(p, i) for p, i in infos.items() if i['cfg'].get('type') == 'article' and not i['cfg'].get('noindex')]
    arts.sort(key=lambda x: (x[1]['date'], x[0]), reverse=True)
    rows = []
    for p, i in arts:
        d = datetime.date.fromisoformat(i['date']).strftime('%b %-d, %Y')
        rows.append(f'    <a href="/{p}"><span>{esc(i["cfg"].get("section", "Read"))} · {d}</span><strong>{esc(i["h1"])}</strong><em>{esc(i["desc"])}</em></a>')
    page = READ_HUB.replace('{items}', '\n'.join(rows))
    old = open('read/index.html', encoding='utf-8').read() if os.path.exists('read/index.html') else ''
    old_core = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', old, flags=re.S)
    old_core = re.sub(r'<title>.*?</title>(\n  <meta name="description"[^>]*>)?', '<title>Read</title>', old_core, count=1, flags=re.S)
    if old_core != page:
        open('read/index.html', 'w', encoding='utf-8').write(page)

def build_sitemap(infos):
    rows = []
    for p in sorted(infos, key=lambda x: (x != 'index.html', x)):
        if p in CFG.get('exclude_from_sitemap', []) or infos[p]['cfg'].get('noindex'): continue
        rows.append(f'  <url><loc>{infos[p]["url"]}</loc><lastmod>{max(infos[p]["mod"], infos[p]["date"])}</lastmod></url>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(rows) + '\n</urlset>\n'
    open('sitemap.xml', 'w').write(xml)
    open('robots.txt', 'w').write('User-agent: *\nAllow: /\nDisallow: /tools/\n\nSitemap: ' + SITE + '/sitemap.xml\n')

if __name__ == '__main__':
    pages = sorted(set(list(CFG['pages']) + [f for f in os.listdir('.') if f.endswith('.html')] + ['read/' + f for f in os.listdir('read') if f.endswith('.html')]))
    for p in pages:
        if p not in CFG['pages'] and p not in CFG.get('exclude_from_sitemap', []):
            print('  note: page not in tools/seo-pages.json, using its own title/description:', p)
    # first pass for article info (hub needs it), then hub, then apply all
    infos = {}
    for p in pages:
        if p in CFG.get('exclude_from_sitemap', []) or not os.path.exists(p) and p != 'read/index.html': continue
        if p == 'read/index.html': continue
        infos[p] = page_info(p, open(p, encoding='utf-8').read())
    build_read_hub(infos)
    infos = {}
    for p in pages:
        if p in CFG.get('exclude_from_sitemap', []) or not os.path.exists(p): continue
        infos[p] = apply(p)
    build_sitemap(infos)
    print('ok:', len(infos), 'pages; sitemap.xml + robots.txt written')
