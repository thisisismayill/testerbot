"""A single JS probe that harvests everything the DOM-level checks need."""

DOM_PROBE = r"""
() => {
  const MAX = 300;
  const txt = (el) => ((el && (el.innerText || el.textContent)) || '').trim().replace(/\s+/g, ' ');
  const cut = (s, n) => (s && s.length > n ? s.slice(0, n) + '…' : (s || ''));

  function selectorFor(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id && /^[A-Za-z][\w:.-]*$/.test(el.id)) return '#' + el.id;
    const parts = [];
    let node = el, guard = 0;
    while (node && node.nodeType === 1 && guard++ < 5) {
      let part = node.tagName.toLowerCase();
      if (node.id && /^[A-Za-z][\w:.-]*$/.test(node.id)) { parts.unshift('#' + node.id); break; }
      const cls = (node.getAttribute('class') || '').trim().split(/\s+/)
        .filter(c => c && !/^(ng|is|has)-/.test(c) && c.length < 30).slice(0, 2);
      if (cls.length) part += '.' + cls.join('.');
      const parent = node.parentElement;
      if (parent) {
        const sibs = Array.from(parent.children).filter(c => c.tagName === node.tagName);
        if (sibs.length > 1) part += ':nth-of-type(' + (sibs.indexOf(node) + 1) + ')';
      }
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  }

  function accName(el) {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\s+/).map(id => {
        const n = document.getElementById(id); return n ? txt(n) : '';
      }).join(' ').trim();
      if (t) return t;
    }
    const t = txt(el);
    if (t) return t;
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim();
    const img = el.querySelector('img[alt]');
    if (img && img.getAttribute('alt').trim()) return img.getAttribute('alt').trim();
    if (el.tagName === 'INPUT' && el.value) return el.value;
    return '';
  }

  function visible(el) {
    if (!el || !el.getClientRects) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity) < 0.05) return false;
    return true;
  }

  const isHttps = location.protocol === 'https:';
  const out = {};

  out.url = location.href;
  out.title = (document.title || '').trim();
  out.lang = document.documentElement.getAttribute('lang') || '';
  out.charset = document.characterSet || '';
  const md = document.querySelector('meta[name="description" i]');
  out.metaDescription = md ? (md.getAttribute('content') || '').trim() : null;
  const vp = document.querySelector('meta[name="viewport" i]');
  out.viewportMeta = vp ? (vp.getAttribute('content') || '').trim() : null;
  const can = document.querySelector('link[rel="canonical" i]');
  out.canonical = can ? can.getAttribute('href') : null;
  out.ogTitle = !!document.querySelector('meta[property="og:title" i]');
  out.ogImage = !!document.querySelector('meta[property="og:image" i]');
  out.favicon = !!document.querySelector('link[rel~="icon" i]');
  out.noindex = !!document.querySelector('meta[name="robots" i][content*="noindex" i]');

  const bodyText = txt(document.body);
  out.bodyTextLength = bodyText.length;
  out.bodyExcerpt = cut(bodyText, 300);

  // headings
  const heads = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(visible);
  out.h1Count = heads.filter(h => h.tagName === 'H1').length;
  out.headings = heads.slice(0, MAX).map(h => ({ level: +h.tagName[1], text: cut(txt(h), 90) }));
  const skips = [];
  let prev = 0;
  for (const h of heads) {
    const lvl = +h.tagName[1];
    if (prev && lvl > prev + 1) skips.push({ from: prev, to: lvl, text: cut(txt(h), 80) });
    prev = lvl;
  }
  out.headingSkips = skips.slice(0, 20);

  // images
  const imgs = Array.from(document.querySelectorAll('img'));
  out.imageCount = imgs.length;
  out.imagesNoAlt = imgs.filter(i => !i.hasAttribute('alt') && visible(i)).slice(0, MAX)
    .map(i => ({ src: cut(i.currentSrc || i.src, 160), selector: selectorFor(i) }));
  out.imagesBroken = imgs.filter(i => i.complete && i.naturalWidth === 0 && (i.src || '').length)
    .slice(0, MAX).map(i => ({ src: cut(i.src, 200), selector: selectorFor(i) }));
  out.imagesNoDimensions = imgs.filter(i => visible(i) && (!i.getAttribute('width') || !i.getAttribute('height')))
    .length;

  // links
  const anchors = Array.from(document.querySelectorAll('a'));
  out.links = [];
  out.emptyLinks = [];
  out.blankNoRel = [];
  out.hrefLessAnchors = 0;
  for (const a of anchors) {
    const href = a.getAttribute('href');
    if (href === null) { if (visible(a)) out.hrefLessAnchors++; continue; }
    const abs = a.href;
    if (out.links.length < 800) {
      out.links.push({ href: abs, raw: href, text: cut(accName(a), 90),
                       target: a.getAttribute('target') || '',
                       rel: (a.getAttribute('rel') || '').toLowerCase(),
                       selector: selectorFor(a) });
    }
    if (!accName(a) && !a.closest('[aria-hidden="true"]') && out.emptyLinks.length < 40) {
      out.emptyLinks.push({ href: cut(abs, 160), selector: selectorFor(a) });
    }
    const rel = (a.getAttribute('rel') || '').toLowerCase();
    if ((a.getAttribute('target') || '') === '_blank' && !rel.includes('noopener')
        && !rel.includes('noreferrer') && out.blankNoRel.length < 40) {
      out.blankNoRel.push({ href: cut(abs, 160), selector: selectorFor(a) });
    }
  }

  // form controls / labels
  const controls = Array.from(document.querySelectorAll('input,select,textarea'))
    .filter(el => !['hidden', 'submit', 'button', 'reset', 'image'].includes((el.type || '').toLowerCase()));
  out.unlabelled = [];
  for (const el of controls) {
    if (!visible(el)) continue;
    let has = !!(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'));
    if (!has && el.id) has = !!document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    if (!has) has = !!el.closest('label');
    if (!has && el.getAttribute('placeholder')) has = 'placeholder-only';
    if (has === true) continue;
    if (out.unlabelled.length < 60) {
      out.unlabelled.push({
        selector: selectorFor(el), type: (el.type || el.tagName).toLowerCase(),
        name: el.getAttribute('name') || '', placeholderOnly: has === 'placeholder-only',
      });
    }
  }

  // buttons without an accessible name
  const btns = Array.from(document.querySelectorAll(
    "button,[role='button'],input[type='submit'],input[type='button']"));
  out.namelessButtons = btns.filter(b => visible(b) && !accName(b)).slice(0, 40)
    .map(b => ({ selector: selectorFor(b), html: cut(b.outerHTML, 150) }));

  // duplicate ids
  const seen = {}, dups = [];
  for (const el of document.querySelectorAll('[id]')) {
    const id = el.id; if (!id) continue;
    if (seen[id]) { if (dups.indexOf(id) === -1 && dups.length < 30) dups.push(id); }
    else seen[id] = 1;
  }
  out.duplicateIds = dups;

  // mixed content
  out.mixedContent = [];
  if (isHttps) {
    for (const el of document.querySelectorAll('[src],[href]')) {
      const v = el.getAttribute('src') || el.getAttribute('href') || '';
      if (v.toLowerCase().startsWith('http://') && out.mixedContent.length < 30) {
        out.mixedContent.push({ tag: el.tagName.toLowerCase(), url: cut(v, 180),
                                selector: selectorFor(el) });
      }
    }
  }

  // forms
  out.forms = Array.from(document.querySelectorAll('form')).slice(0, 30).map((f, idx) => {
    const fields = Array.from(f.querySelectorAll('input,select,textarea')).map(el => ({
      name: el.getAttribute('name') || '', id: el.id || '',
      type: (el.getAttribute('type') || el.tagName).toLowerCase(),
      required: el.hasAttribute('required'), selector: selectorFor(el),
      visible: visible(el), placeholder: el.getAttribute('placeholder') || '',
      maxlength: el.getAttribute('maxlength') || '',
      pattern: el.getAttribute('pattern') || '',
    }));
    const submit = f.querySelector("button[type='submit'],input[type='submit'],button:not([type])");
    return {
      index: idx, selector: selectorFor(f), action: f.getAttribute('action'),
      method: (f.getAttribute('method') || 'get').toLowerCase(),
      id: f.id || '', name: f.getAttribute('name') || '',
      novalidate: f.hasAttribute('novalidate'),
      fields: fields, hasSubmit: !!submit,
      submitText: submit ? cut(accName(submit), 60) : '',
      visible: visible(f),
      signature: (f.getAttribute('action') || location.pathname) + '::' +
                 fields.map(x => x.type + ':' + x.name).join(','),
      hasPassword: fields.some(x => x.type === 'password'),
      hasFile: fields.some(x => x.type === 'file'),
    };
  });

  // clickable candidates (non-link interactive things)
  const cand = new Set();
  const sels = ["button", "[role='button']", "[role='tab']", "[role='menuitem']", "summary",
                "[onclick]", "[data-toggle]", "[data-bs-toggle]", "[data-testid*='button' i]",
                ".btn", ".button", "[class*='dropdown-toggle' i]", "[class*='accordion' i]",
                "[class*='tab-' i][role]", "input[type='button']"];
  for (const s of sels) {
    let nodes = [];
    try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { continue; }
    for (const n of nodes) cand.add(n);
  }
  out.clickables = Array.from(cand).filter(visible).slice(0, 120).map(el => {
    const r = el.getBoundingClientRect();
    return {
      selector: selectorFor(el), tag: el.tagName.toLowerCase(),
      text: cut(accName(el), 70), type: (el.getAttribute('type') || '').toLowerCase(),
      inForm: !!el.closest('form'), disabled: !!el.disabled,
      w: Math.round(r.width), h: Math.round(r.height),
      html: cut(el.outerHTML, 180),
    };
  });

  // tiny tap targets among interactive elements
  out.tinyTargets = Array.from(document.querySelectorAll("a,button,[role='button'],input"))
    .filter(visible).filter(el => {
      const r = el.getBoundingClientRect();
      return (r.width < 24 || r.height < 24);
    }).slice(0, 30).map(el => ({ selector: selectorFor(el), text: cut(accName(el), 50) }));

  // placeholder / debug junk left in the page
  const junkPatterns = [
    ['lorem ipsum', /lorem ipsum/i],
    ['undefined', /(^|[\s>|:,])undefined([\s<|.,!]|$)/],
    ['NaN', /(^|[\s>|:,])NaN([\s<|.,!]|$)/],
    ['[object Object]', /\[object Object\]/],
    ['TODO/FIXME', /\b(TODO|FIXME|XXX):/],
    ['null value shown', /(^|[\s>|:,])null([\s<|.,!]|$)/],
    ['template placeholder', /\{\{\s*[\w.$]+\s*\}\}|%[A-Z_]{3,}%/],
    ['Error text', /\b(Exception|Stack trace|Fatal error|Warning: |Notice: |Traceback \(most recent)/],
    ['test placeholder', /\b(test test|asdf|qwerty|placeholder text|coming soon)\b/i],
  ];
  out.junk = [];
  for (const [label, re] of junkPatterns) {
    const m = bodyText.match(re);
    if (m) {
      const i = Math.max(0, bodyText.indexOf(m[0]) - 60);
      out.junk.push({ label: label, excerpt: cut(bodyText.slice(i, i + 180), 180) });
    }
  }

  // layout
  out.scrollWidth = document.documentElement.scrollWidth;
  out.clientWidth = document.documentElement.clientWidth;
  out.innerWidth = window.innerWidth;

  // iframes & media
  out.iframes = Array.from(document.querySelectorAll('iframe')).slice(0, 20).map(f => ({
    src: cut(f.getAttribute('src') || '', 160), title: f.getAttribute('title') || '',
  }));
  out.videosNoCaptions = Array.from(document.querySelectorAll('video'))
    .filter(v => !v.querySelector('track[kind="captions"],track[kind="subtitles"]')).length;
  out.autoplayMedia = document.querySelectorAll('video[autoplay]:not([muted]),audio[autoplay]').length;

  // http form action on https page
  out.insecureForms = Array.from(document.querySelectorAll('form')).filter(f => {
    const a = f.getAttribute('action') || '';
    return a.toLowerCase().startsWith('http://');
  }).length;

  // element counts for a rough complexity signal
  out.domNodes = document.getElementsByTagName('*').length;
  out.inlineStyles = document.querySelectorAll('[style]').length;

  return out;
}
"""
