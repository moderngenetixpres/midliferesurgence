# Publishing a Midlife Resurgence post (routine-safe)

Hosting: GitHub Pages, repo moderngenetixpres/midliferesurgence, branch main, custom domain midliferesurgence.com (CNAME).
Local checkout on the box: /workspace/midlife-live. Push auth: the logged-in gh CLI at /usr/local/bin/gh. The repo's global helper points at a stale /usr/bin/gh path, so push with:
  git -c credential.https://github.com.helper= -c 'credential.https://github.com.helper=!/usr/local/bin/gh auth git-credential' push origin main
A push to main is live in about 1 to 2 minutes.

1. cd /workspace/midlife-live && git pull --ff-only
2. Copy tools/post-template.html to read/<slug>.html (slug = lowercase-hyphenated target keyword, e.g. strength-training-after-40).
   Fill every {{...}} placeholder. Delete unused optional blocks.
3. Optional hero image: read/images/<slug>.jpg, 1200x675, under 200 KB, descriptive alt text.
4. Add the page to tools/seo-pages.json "pages":
   "read/<slug>.html": {"type": "article", "date": "YYYY-MM-DD", "section": "Training|Nutrition|Mindset|Recovery", "title": "<= 60 chars + ' · Midlife Resurgence'", "description": "140-160 chars"}
5. Link the new post from at least one hub (training.html list, nutrition.html, or an older related post's Keep going list).
6. python3 tools/seo_build.py   (updates title/meta, canonical, OG, Article JSON-LD, /read/ hub, sitemap.xml, robots.txt)
7. git add read tools sitemap.xml robots.txt *.html && git commit -m "Read: <title>" && push with the command above
8. Verify: curl -s -o /dev/null -w "%{http_code}" https://midliferesurgence.com/read/<slug>.html returns 200 (retry for up to 3 minutes).

The videos sync routine must also run step 6 before its commit, so new episodes get VideoObject schema and the sitemap lastmod updates.
Rules: honest copy, no invented stats or results, Mike's voice, "Not medical advice" disclaimer, supplement mentions in FDA structure/function wording with the asterisk disclaimer.

AEO (added Nov 22, 2026): every new post should answer the buyer question it targets in the first 2-3 paragraphs, and end with an `<h2>FAQ: ...</h2>` section (each question an `<h3>`, answer in `<p>`), then a "Keep going" list with 2-3 internal links (one shop product or Journal link where it fits, FDA-compliant). seo_build.py turns the FAQ section into FAQPage JSON-LD automatically. Topic queue: /workspace/modern-genetix/aeo/gap-topics.md.
