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

  // ---- the words a visitor reads next to a field
  function labelText(el) {
    let t = '';
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) t = txt(l);
    }
    if (!t) { const l = el.closest('label'); if (l) t = txt(l); }
    if (!t) t = (el.getAttribute('aria-label') || '').trim();
    if (!t && el.getAttribute('aria-labelledby')) {
      t = el.getAttribute('aria-labelledby').split(/\s+/).map(id => {
        const n = document.getElementById(id); return n ? txt(n) : '';
      }).join(' ').trim();
    }
    return t;
  }
  // a <label> sitting next to the field without being connected to it
  function nearLabel(el) {
    let box = el.parentElement;
    for (let i = 0; i < 3 && box; i++, box = box.parentElement) {
      const fields = Array.from(box.querySelectorAll('input,select,textarea')).filter(c =>
        !['hidden', 'submit', 'button', 'reset', 'image'].includes((c.type || '').toLowerCase()));
      if (fields.length > 1) return '';
      const l = box.querySelector('label');
      if (l) return txt(l);
    }
    return '';
  }

  // ---- contact links that show one address but open another
  const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;
  const digits = s => (s || '').replace(/[^0-9]/g, '');
  out.contactMismatch = [];
  for (const a of document.querySelectorAll('a[href^="mailto:" i], a[href^="tel:" i]')) {
    if (out.contactMismatch.length >= 20) break;
    const href = a.getAttribute('href') || '';
    const shown = txt(a);
    if (/^mailto:/i.test(href)) {
      let target = href.slice(7).split('?')[0];
      try { target = decodeURIComponent(target); } catch (e) {}
      const targets = target.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
      let seen = (shown.match(EMAIL_RE) || []).map(e => e.toLowerCase());
      if (!seen.length && a.parentElement) {
        const around = (txt(a.parentElement).match(EMAIL_RE) || []).map(e => e.toLowerCase());
        if (around.length === 1) seen = around;
      }
      const wrong = seen.filter(e => !targets.includes(e));
      if (targets.length && wrong.length) {
        out.contactMismatch.push({ kind: 'email', shown: wrong[0], opens: targets.join(', '),
                                   text: cut(shown, 80), selector: selectorFor(a) });
      }
    } else {
      const linked = digits(href.slice(4)), seen = digits(shown);
      if (seen.length >= 7 && linked.length >= 7 && linked.slice(-7) !== seen.slice(-7)) {
        out.contactMismatch.push({ kind: 'phone', shown: cut(shown, 40), opens: href.slice(4),
                                   text: cut(shown, 80), selector: selectorFor(a) });
      }
    }
  }

  // ---- things that react to a click but are neither links nor buttons:
  // a mouse can use them, a keyboard cannot reach them at all
  const NATIVE = 'a[href],button,input,select,textarea,summary,label,details,option,iframe,video,audio';
  const ROLE_OK = /^(button|link|tab|menuitem|menuitemcheckbox|menuitemradio|option|checkbox|radio|switch|treeitem|gridcell|row)$/;
  out.clickTraps = [];
  const trapEls = [];
  for (const el of document.querySelectorAll('body *')) {
    if (out.clickTraps.length >= 40) break;
    if (!(typeof el.onclick === 'function' || el.hasAttribute('onclick'))) continue;
    if (el.matches(NATIVE) || el.closest('a[href],button')) continue;
    const ti = el.getAttribute('tabindex');
    if (ti !== null && parseInt(ti, 10) >= 0) continue;
    const role = (el.getAttribute('role') || '').toLowerCase();
    if (ROLE_OK.test(role) && ti === '-1') continue;          // focus managed by its widget
    if (el.querySelector('a[href],button,input,select,textarea')) continue;  // just a wrapper
    if (trapEls.some(p => p.contains(el))) continue;
    if (!visible(el) || getComputedStyle(el).cursor !== 'pointer') continue;
    const t = cut(txt(el), 60);
    if (!t && !el.querySelector('img,svg')) continue;
    trapEls.push(el);
    out.clickTraps.push({ text: t, tag: el.tagName.toLowerCase(), selector: selectorFor(el) });
  }

  // ---- a field labelled "optional" that the form nevertheless requires
  out.optionalRequired = [];
  for (const el of controls) {
    if (!visible(el)) continue;
    if (!(el.required || el.getAttribute('aria-required') === 'true')) continue;
    const t = labelText(el) || nearLabel(el) || (el.getAttribute('placeholder') || '');
    if (/\boptional\b|\(opt\.?\)|isteğe bağlı|ixtiyari|məcburi deyil|необязательн/i.test(t)) {
      out.optionalRequired.push({ label: cut(t, 80), name: el.getAttribute('name') || el.id || '',
                                  selector: selectorFor(el) });
    }
  }

  // ---- labels pointing at a field id that does not exist
  out.labelsOrphaned = [];
  for (const l of document.querySelectorAll('label[for]')) {
    if (out.labelsOrphaned.length >= 20) break;
    const f = l.getAttribute('for');
    if (!f || document.getElementById(f) || !visible(l)) continue;
    let field = null, box = l.parentElement;
    for (let i = 0; i < 3 && box && !field; i++, box = box.parentElement) {
      const cs = Array.from(box.querySelectorAll('input,select,textarea')).filter(c =>
        !['hidden', 'submit', 'button', 'reset', 'image'].includes((c.type || '').toLowerCase()) && visible(c));
      if (cs.length === 1) field = cs[0];
      else if (cs.length > 1) break;
    }
    out.labelsOrphaned.push({ label: cut(txt(l), 60), points_to: f,
                              field_id: field ? (field.id || '') : '',
                              field: field ? selectorFor(field) : '' });
  }

  // ---- personal-data fields that give the browser no autocomplete hint
  const PERSONAL = /(e-?mail|user ?name|login|phone|mobile|first.?name|last.?name|full.?name|surname|given.?name|family.?name|address|post.?code|zip|city|country)/i;
  out.noAutocomplete = [];
  for (const el of controls) {
    if (out.noAutocomplete.length >= 20) break;
    if (!visible(el) || el.hasAttribute('autocomplete')) continue;
    const t = (el.type || '').toLowerCase();
    const blob = [el.getAttribute('name'), el.id, el.getAttribute('placeholder'), labelText(el)].join(' ');
    if (t === 'email' || t === 'password' || t === 'tel' || (t === 'text' && PERSONAL.test(blob))) {
      out.noAutocomplete.push({ type: t, name: el.getAttribute('name') || el.id || cut(labelText(el), 40),
                                selector: selectorFor(el) });
    }
  }

  // ---- text for the spelling check: everything visible, plus the short
  // strings visitors read first (menus, buttons, links, headings, labels)
  out.text = bodyText.slice(0, 60000);
  const ui = new Set();
  const uiSel = "a,button,[role='button'],[role='menuitem'],[role='tab'],[role='link'],label,summary," +
                "legend,h1,h2,h3,h4,h5,h6,nav li,th";
  for (const el of document.querySelectorAll(uiSel)) {
    if (ui.size >= 600) break;
    if (!visible(el)) continue;
    const t = txt(el);
    if (t && t.length <= 80) ui.add(t);
  }
  for (const c of out.clickTraps) if (c.text) ui.add(c.text);
  for (const el of document.querySelectorAll('[placeholder]')) {
    if (ui.size >= 700) break;
    if (visible(el)) ui.add((el.getAttribute('placeholder') || '').trim().slice(0, 80));
  }
  out.uiText = Array.from(ui).filter(Boolean);

  // clickable candidates (non-link interactive things)
  const cand = new Set();
  for (const el of trapEls) cand.add(el);          // menus built from divs get clicked too
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
