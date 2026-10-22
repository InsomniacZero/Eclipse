// ==UserScript==
// @name         Eclipse: JanitorAI DOM probe (throwaway)
// @namespace    eclipse
// @version      0.3
// @description  Reads the structure of a JanitorAI chat page and reports it. Never reads or sends message text.
// @match        *://janitorai.com/*
// @match        *://*.janitorai.com/*
// @match        *://janitor.ai/*
// @match        *://*.janitor.ai/*
// @run-at       document-idle
// @noframes
// @grant        GM_xmlhttpRequest
// @grant        GM.xmlHttpRequest
// @grant        GM_registerMenuCommand
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

// A probe, not a feature. It answers the questions the regex renderer depends on:
//   1. Which element holds the messages, and what do they look like inside?
//   2. Do the model's raw tags (<tucao>, <options>...) survive in the page, or does the renderer remove them?
//   3. Does the page keep the raw message text somewhere we can read (React props)?
//   4. When a reply streams in, does the page keep our changes to a message, or rebuild it?
//   5. Does the page accept injected <style> and inline styles (a content security policy might not)?
//   6. Can a userscript reach the local Eclipse gateway, and which origin does it present?
//
// Privacy: message text is never copied. Text nodes are reported as lengths, and only the NAMES of
// tags found in the text are listed. Class names, tag names and attribute NAMES are reported.
// Nothing leaves the page except the two requests in "Test gateway", which go to 127.0.0.1 only.
(function () {
  'use strict';

  const MAX_DEPTH = 7;
  const MAX_NODES = 140;

  // ---------------------------------------------------------------- structure helpers

  function sig(el) {
    return `${el.tagName}.${(el.getAttribute('class') || '').trim().split(/\s+/).sort().join('.')}`;
  }

  function textLen(el) {
    return (el.textContent || '').trim().length;
  }

  // The element whose children look most like a list of messages: many children with similar
  // markup, each holding real text. Deeper elements win ties.
  function findMessageList(root) {
    let best = null;
    let bestScore = 0;
    const all = root.querySelectorAll('*');
    for (const el of all) {
      const kids = Array.from(el.children);
      if (kids.length < 2) continue;
      const withText = kids.filter((k) => textLen(k) >= 15);
      if (withText.length < 2) continue;
      const counts = new Map();
      withText.forEach((k) => counts.set(sig(k), (counts.get(sig(k)) || 0) + 1));
      const top = Math.max(...counts.values());
      const score = top * 10 + withText.length;
      if (score >= bestScore) {
        best = el;
        bestScore = score;
      }
    }
    return best;
  }

  // JanitorAI's message wrappers: <li class="_messageDisplayWrapper_xxxx_n"> (the hash suffix changes, the prefix does not).
  function messageItems() {
    return Array.from(document.querySelectorAll('[class*="_messageDisplayWrapper_"]')).filter((el) => textLen(el) >= 5);
  }

  function commonAncestor(els) {
    if (!els.length) return document.body;
    let cur = els[0].parentElement;
    while (cur && !els.every((e) => cur.contains(e))) cur = cur.parentElement;
    return cur || document.body;
  }

  // A message container: the child of the message list that holds `el`; failing that, the nearest
  // ancestor that has 2+ siblings with the same signature.
  function messageOf(el) {
    const list = findMessageList(document.body);
    if (list && list.contains(el)) {
      let cur = el;
      while (cur && cur.parentElement !== list) cur = cur.parentElement;
      if (cur) return cur;
    }
    for (let cur = el; cur && cur.parentElement && cur !== document.body; cur = cur.parentElement) {
      const same = Array.from(cur.parentElement.children).filter((s) => sig(s) === sig(cur));
      if (same.length >= 2 && textLen(cur) >= 5) return cur;
    }
    return null;
  }

  function attrSummary(el) {
    const names = el.getAttributeNames().filter((n) => n !== 'class');
    return names.length ? ` [${names.map((n) => (n === 'role' || n === 'contenteditable' ? `${n}=${el.getAttribute(n)}` : n)).join(' ')}]` : '';
  }

  // Tree outline with text reduced to lengths. `<` characters inside text nodes are counted, because
  // an escaped tag in the text would show up there.
  function outline(el, depth, budget, lines) {
    if (depth > MAX_DEPTH || budget.n <= 0) return;
    const pad = '  '.repeat(depth);
    const cls = (el.getAttribute('class') || '').trim();
    lines.push(`${pad}<${el.tagName.toLowerCase()}${cls ? ` class="${cls}"` : ''}>${attrSummary(el)}`);
    budget.n -= 1;
    for (const node of el.childNodes) {
      if (budget.n <= 0) {
        lines.push(`${pad}  ... (cut)`);
        return;
      }
      if (node.nodeType === 3) {
        const t = node.nodeValue || '';
        if (t.trim()) {
          const lt = (t.match(/</g) || []).length;
          lines.push(`${pad}  #text(len=${t.length}${lt ? `, '<' x${lt}` : ''})`);
          budget.n -= 1;
        }
      } else if (node.nodeType === 1) {
        outline(node, depth + 1, budget, lines);
      }
    }
  }

  const KNOWN_TAG = (name) => !(document.createElement(name) instanceof HTMLUnknownElement);

  // Which tag NAMES appear: as real elements (survived into the DOM) and as text (<name> shown literally).
  function tagCensus(root) {
    const elements = new Map();
    root.querySelectorAll('*').forEach((el) => {
      const n = el.tagName.toLowerCase();
      elements.set(n, (elements.get(n) || 0) + 1);
    });
    const unknown = [...elements.keys()].filter((n) => !KNOWN_TAG(n)).sort();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const inText = new Map();
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      for (const m of (n.nodeValue || '').matchAll(/<\/?([a-zA-Z][\w-]{0,30})\b[^>]{0,40}>/g)) {
        const k = m[1].toLowerCase();
        inText.set(k, (inText.get(k) || 0) + 1);
      }
    }
    return {
      elements: [...elements.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}x${v}`).join(' '),
      unknownElements: unknown,
      tagsShownAsText: [...inText.entries()].map(([k, v]) => `${k}x${v}`),
    };
  }

  // ---------------------------------------------------------------- React: where is the raw text?

  function fiberOf(el) {
    const key = Object.keys(el).find((k) => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    return key ? el[key] : null;
  }

  function stringProps(value, path, out, depth) {
    if (out.length >= 25 || depth > 3 || value == null) return;
    if (typeof value === 'string') {
      if (value.length >= 40) out.push(`${path} (string, len=${value.length}${value.includes('<') ? ", has '<'" : ''}${/[*_`#]/.test(value) ? ', has markdown marks' : ''})`);
      return;
    }
    if (typeof value !== 'object' || value.$$typeof) return;
    for (const k of Object.keys(value).slice(0, 25)) {
      try {
        stringProps(value[k], `${path}.${k}`, out, depth + 1);
      } catch (_) { /* getter that throws */ }
    }
  }

  function reactReport(el) {
    const lines = [];
    let fiber = fiberOf(el);
    if (!fiber) return ['(no React fiber on this element: not React, or an old build)'];
    for (let hops = 0; fiber && hops < 30; hops += 1, fiber = fiber.return) {
      const type = fiber.type;
      const name = typeof type === 'string' ? type : (type && (type.displayName || type.name)) || (type && type.render && type.render.name) || '(anonymous)';
      const props = fiber.memoizedProps;
      if (!props || typeof props !== 'object') continue;
      const hits = [];
      stringProps(props, 'props', hits, 0);
      if (hits.length || typeof type !== 'string') {
        lines.push(`${hops}: ${name}  propKeys=[${Object.keys(props).slice(0, 14).join(',')}]`);
        hits.forEach((h) => lines.push(`     ${h}`));
      }
      if (lines.length > 70) break;
    }
    return lines;
  }

  // The raw reply string the page keeps in React props above a message: the longest string found at a
  // `children` prop (the markdown component) or at `message.message` / `items[n].message` (the chat store).
  function rawTextOf(el) {
    const start = el.querySelector('p') || el;
    let fiber = fiberOf(start);
    const found = [];
    for (let hops = 0; fiber && hops < 40; hops += 1, fiber = fiber.return) {
      const props = fiber.memoizedProps;
      if (!props || typeof props !== 'object') continue;
      try {
        if (typeof props.children === 'string' && props.children.length > 20) found.push({ path: `hop ${hops} props.children`, text: props.children });
        const m = props.message;
        if (m && typeof m === 'object' && typeof m.message === 'string') found.push({ path: `hop ${hops} props.message.message`, text: m.message });
        if (m && typeof m === 'object' && m[0] && typeof m[0].message === 'string') found.push({ path: `hop ${hops} props.message[0].message`, text: m[0].message });
        if (typeof m === 'string' && m.length > 20) found.push({ path: `hop ${hops} props.message`, text: m });
      } catch (_) { /* getter */ }
    }
    found.sort((a, b) => b.text.length - a.text.length);
    return found[0] || null;
  }

  function tagsInRaw(text) {
    const counts = new Map();
    for (const m of text.matchAll(/<\/?([a-zA-Z][\w-]{0,30})\b[^>]{0,60}>/g)) {
      const k = m[1].toLowerCase();
      counts.set(k, (counts.get(k) || 0) + 1);
    }
    return [...counts.entries()].map(([k, v]) => `${k}x${v}`).join(' ') || 'none';
  }

  // Key NAMES of the settings stores near a message. Values are shown only for the model name and the
  // proxy kind (never the key, token or full address).
  function settingsReport(el) {
    const lines = [];
    let fiber = fiberOf(el.querySelector('p') || el);
    const seen = new Set();
    for (let hops = 0; fiber && hops < 40; hops += 1, fiber = fiber.return) {
      const props = fiber.memoizedProps;
      if (!props || typeof props !== 'object') continue;
      for (const storeName of ['userStore', 'chatStore']) {
        const store = props[storeName];
        if (!store || typeof store !== 'object' || seen.has(storeName)) continue;
        seen.add(storeName);
        try {
          lines.push(`${storeName} keys: ${Object.keys(store).slice(0, 40).join(', ')}`);
          const cfg = store.config;
          if (cfg && typeof cfg === 'object') {
            lines.push(`${storeName}.config keys: ${Object.keys(cfg).join(', ')}`);
            for (const k of Object.keys(cfg)) {
              const v = cfg[k];
              if (/key|token|secret|auth|password/i.test(k)) continue;
              if (/proxy|url|host/i.test(k) && typeof v === 'string') {
                let kind = 'other host';
                try {
                  const u = new URL(v);
                  kind = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(u.hostname) ? `local (${u.protocol}//${u.hostname}:${u.port || 'default'})`
                    : /ngrok/.test(u.hostname) ? `ngrok (${u.protocol})` : `${u.protocol}//(other host)`;
                  kind += `, path ${u.pathname}`;
                } catch (_) { kind = `not a URL (len ${v.length})`; }
                lines.push(`  ${k}: ${kind}`);
              } else if (/model/i.test(k) && typeof v === 'string' && v.length <= 80) {
                lines.push(`  ${k}: ${v}`);
              }
            }
          }
        } catch (_) { /* getter */ }
      }
    }
    return lines.length ? lines : ['(no userStore/chatStore found in the props above this message)'];
  }

  // ---------------------------------------------------------------- environment checks

  function renderingCheck() {
    const violations = [];
    const onViolation = (e) => violations.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'}`);
    document.addEventListener('securitypolicyviolation', onViolation);
    const host = document.createElement('div');
    host.setAttribute('data-probe-scratch', '1');
    host.style.cssText = 'position:fixed;left:-9999px;top:0;';
    host.innerHTML = '<style>#pr-s2{color:rgb(4,5,6)}</style><span id="pr-s1" style="color:rgb(1,2,3)">a</span><span id="pr-s2">b</span><img id="pr-s3" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">';
    document.body.appendChild(host);
    const c1 = getComputedStyle(host.querySelector('#pr-s1')).color;
    const c2 = getComputedStyle(host.querySelector('#pr-s2')).color;
    return new Promise((resolve) => {
      setTimeout(() => {
        document.removeEventListener('securitypolicyviolation', onViolation);
        host.remove();
        const meta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
        resolve([
          `inline style attribute applied: ${c1 === 'rgb(1, 2, 3)'} (${c1})`,
          `injected <style> block applied: ${c2 === 'rgb(4, 5, 6)'} (${c2})`,
          `CSP violations while injecting: ${violations.length ? violations.join('; ') : 'none'}`,
          `CSP <meta>: ${meta ? meta.content.slice(0, 200) : 'none (a header CSP cannot be read from here)'}`,
        ]);
      }, 350);
    });
  }

  function gmRequest(url) {
    const fn = typeof GM_xmlhttpRequest === 'function' ? GM_xmlhttpRequest : (typeof GM !== 'undefined' && GM.xmlHttpRequest) || null;
    return new Promise((resolve) => {
      if (!fn) return resolve('no GM_xmlhttpRequest in this userscript manager');
      try {
        fn({
          method: 'GET', url, timeout: 5000,
          onload: (r) => resolve(`HTTP ${r.status} ${String(r.responseText || '').slice(0, 60).replace(/\s+/g, ' ')}`),
          onerror: () => resolve('network error (gateway not running, or blocked)'),
          ontimeout: () => resolve('timeout'),
        });
      } catch (e) {
        resolve(`threw: ${e && e.message}`);
      }
    });
  }

  async function gatewayCheck() {
    const base = 'http://127.0.0.1:5000';
    return [
      `GM request API: ${typeof GM_xmlhttpRequest === 'function' ? 'GM_xmlhttpRequest' : typeof GM !== 'undefined' && GM.xmlHttpRequest ? 'GM.xmlHttpRequest' : 'none'}`,
      `GET ${base}/healthz (public): ${await gmRequest(`${base}/healthz`)}`,
      `GET ${base}/api/presets (protected, needs no Origin or an allowed one): ${await gmRequest(`${base}/api/presets`)}`,
      `GET ${base}/v1/models: ${await gmRequest(`${base}/v1/models`)}`,
    ];
  }

  // ---------------------------------------------------------------- reports

  let picked = null;

  function messageReport() {
    const lines = [];
    let items = picked ? [picked] : messageItems();
    let source = picked ? 'picked' : 'class _messageDisplayWrapper_';
    if (!items.length) {
      const list = findMessageList(document.body);
      items = list ? Array.from(list.children).filter((k) => textLen(k) >= 5) : [];
      source = 'heuristic list';
    }
    if (!items.length) return ['No messages found. Click "Pick message", then click on a bot reply.'];
    lines.push(`messages found: ${items.length} (via ${source}); first one's parent chain: ${ancestorChain(items[0].parentElement || items[0], 5)}`);
    const sample = items.slice(-3);
    sample.forEach((msg, i) => {
      lines.push('', `--- message ${items.length - sample.length + i + 1} of ${items.length} (text length ${textLen(msg)}) ---`);
      lines.push(`wrapper: <${msg.tagName.toLowerCase()} class="${msg.getAttribute('class') || ''}">`);
      const out = [];
      outline(msg, 0, { n: 70 }, out);
      lines.push(...out);
      const census = tagCensus(msg);
      lines.push(`DOM elements: ${census.elements}`);
      lines.push(`non-standard elements kept in the DOM: ${census.unknownElements.join(', ') || 'none'}`);
      lines.push(`tag names shown as literal text: ${census.tagsShownAsText.join(', ') || 'none'}`);
      const raw = rawTextOf(msg);
      if (raw) {
        lines.push(`raw text (${raw.path}): ${raw.text.length} chars, ${raw.text.split('\n').length} lines`);
        lines.push(`tags in the raw text: ${tagsInRaw(raw.text)}`);
        lines.push(`raw text has a <log>: ${/<log[\s>]/i.test(raw.text)}`);
      } else {
        lines.push('raw text: not found in React props');
      }
    });
    const last = sample[sample.length - 1];
    lines.push('', '--- where <log> appears on the page right now ---');
    const logEls = document.querySelectorAll('log');
    lines.push(`<log> elements in the DOM: ${logEls.length}`);
    logEls.forEach((el, i) => { if (i < 3) lines.push(`  #${i + 1}: ${ancestorChain(el, 6)} display=${getComputedStyle(el).display} visibility=${getComputedStyle(el).visibility} textLen=${textLen(el)}`); });
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let literal = 0;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) if (/<\/?log[\s>]/i.test(n.nodeValue || '')) literal += 1;
    lines.push(`text nodes that contain a literal "<log>" or "</log>": ${literal}`);
    lines.push('', '--- settings the page keeps (key names; values only for model and proxy kind) ---', ...settingsReport(last));
    lines.push('', '--- React props above the last message ---', ...reactReport(last.querySelector('p') || last));
    return lines;
  }

  function ancestorChain(el, n) {
    const parts = [];
    for (let cur = el; cur && n > 0; cur = cur.parentElement, n -= 1) {
      parts.push(`<${cur.tagName.toLowerCase()}${cur.id ? `#${cur.id}` : ''}${cur.className && typeof cur.className === 'string' ? `.${cur.className.trim().split(/\s+/).slice(0, 3).join('.')}` : ''}>`);
    }
    return parts.join(' < ');
  }

  async function fullReport() {
    const lines = [`# Eclipse JanitorAI probe v0.3`, `page: ${location.origin}${location.pathname.replace(/[0-9a-f-]{8,}/gi, ':id')}`,
      `agent: ${navigator.userAgent}`, `viewport: ${innerWidth}x${innerHeight}`, ''];
    lines.push('## messages', ...messageReport(), '');
    lines.push('## injection', ...(await renderingCheck()), '');
    return lines.join('\n');
  }

  // ---------------------------------------------------------------- watching a reply stream in

  function watch(setOutput) {
    const items0 = picked ? [picked] : messageItems();
    const list = items0.length ? commonAncestor(items0) : (findMessageList(document.body) || null);
    if (!list) return setOutput('Nothing to watch: no message list found. Use "Pick message" first.');
    const last = () => {
      const items = messageItems();
      return (items.length ? items : Array.from(list.children).filter((k) => textLen(k) >= 5)).pop();
    };
    // Mark the newest message with an attribute and a hidden child. If the page keeps both while the
    // reply streams, we can edit a message in place; if not, it rebuilds messages and we need an overlay.
    let marked = null;
    let marker = null;
    const mark = (el) => {
      marked = el;
      marker = document.createElement('span');
      marker.setAttribute('data-probe-injected', '1');
      marker.style.display = 'none';
      el.setAttribute('data-probe-mark', '1');
      (el.querySelector('p, div, span') || el).appendChild(marker);
    };
    const initial = last();
    const stats = { childList: 0, characterData: 0, attributes: 0, added: new Map(), removed: new Map() };
    const bump = (map, node) => {
      const k = node.nodeType === 1 ? node.tagName.toLowerCase() : '#text';
      map.set(k, (map.get(k) || 0) + 1);
    };
    const begun = Date.now();
    let lastChange = Date.now();
    let total = 0;
    let swaps = 0;
    const observer = new MutationObserver((records) => {
      lastChange = Date.now();
      records.forEach((r) => {
        total += 1;
        stats[r.type] += 1;
        r.addedNodes.forEach((n) => bump(stats.added, n));
        r.removedNodes.forEach((n) => bump(stats.removed, n));
      });
      const cur = last();
      if (cur && cur !== initial && cur !== marked) {
        if (marked) swaps += 1; // the newest message became a different element while streaming
        mark(cur);
        observer.takeRecords(); // our own marking is not a page mutation
      }
    });
    observer.observe(list, { subtree: true, childList: true, characterData: true, attributes: true });
    setOutput('Watching... send a message now and let the reply finish. The report appears a few seconds after the page goes quiet (or after 2 minutes).');
    const timer = setInterval(() => {
      const quiet = Date.now() - lastChange > 6000 && total > 5;
      if (!quiet && Date.now() - begun < 120000) return;
      clearInterval(timer);
      observer.disconnect();
      const now = last();
      const fmt = (m) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([k, v]) => `${k}x${v}`).join(' ') || 'none';
      setOutput([
        '# watch report',
        `mutations: ${total} (childList ${stats.childList}, characterData ${stats.characterData}, attributes ${stats.attributes}) over ${((lastChange - begun) / 1000).toFixed(1)} s`,
        `nodes added: ${fmt(stats.added)}`,
        `nodes removed: ${fmt(stats.removed)}`,
        marked
          ? [
            `the reply element (first seen as the newest message): still in the page: ${marked.isConnected}`,
            `...kept our attribute data-probe-mark: ${marked.getAttribute('data-probe-mark') === '1'}`,
            `...kept our injected child element: ${marked.contains(marker)}`,
            `...is still the newest message at the end: ${now === marked}`,
            `times the newest message was swapped for another element while streaming: ${swaps}`,
          ].join('\n')
          : 'no new message appeared while watching (did the reply start before you pressed Watch?)',
        `text grew by editing text nodes in place (characterData > 0): ${stats.characterData > 0}`,
        'If the "kept" lines say false, the page rebuilds a message while it streams: our output would need an overlay next to it.',
      ].join('\n'));
    }, 1000);
  }

  // ---------------------------------------------------------------- panel

  function buildPanel() {
    const box = document.createElement('div');
    box.id = 'eclipse-probe';
    box.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:340px;font:12px/1.4 system-ui,sans-serif;background:#1c1c1c;color:#eee;border:1px solid #555;border-radius:8px;padding:8px;box-shadow:0 4px 18px rgba(0,0,0,.5)';
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px';
    const out = document.createElement('textarea');
    out.readOnly = true;
    out.rows = 9;
    out.style.cssText = 'width:100%;box-sizing:border-box;background:#111;color:#cfc;border:1px solid #444;font:11px/1.3 monospace;resize:vertical';
    out.value = 'Probe ready. "Report" reads the page structure (no message text).';
    const setOutput = (text) => { out.value = text; };
    const button = (label, fn) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.type = 'button';
      b.style.cssText = 'padding:3px 8px;border-radius:5px;border:1px solid #666;background:#2c2c2c;color:#eee;cursor:pointer';
      b.addEventListener('click', fn);
      row.appendChild(b);
      return b;
    };
    button('Report', async () => { setOutput('Reading...'); setOutput(await fullReport()); });
    button('Pick message', () => {
      setOutput('Click on the text of a bot reply...');
      const once = (e) => {
        e.preventDefault();
        e.stopPropagation();
        document.removeEventListener('click', once, true);
        picked = messageOf(e.target);
        setOutput(picked ? `Picked: ${ancestorChain(picked, 5)}\nNow press "Report".` : 'Could not find a message there. Try clicking directly on the reply text.');
      };
      document.addEventListener('click', once, true);
    });
    button('Watch reply', () => watch(setOutput));
    button('Test gateway', async () => { setOutput('Testing 127.0.0.1:5000...'); setOutput((await gatewayCheck()).join('\n')); });
    button('Copy', () => {
      out.select();
      try { document.execCommand('copy'); } catch (_) { /* the text is selected; copy by hand */ }
    });
    button('x', () => { dismissed = true; box.remove(); });
    box.append(row, out);
    (document.body && document.body.isConnected ? document.body : document.documentElement).appendChild(box);
  }

  // The page is a React app that can replace the whole <body> after we load, which would remove the
  // panel. So the panel lives on <html>, and a timer puts it back if it ever disappears.
  let dismissed = false;
  const ensurePanel = () => {
    if (dismissed || document.getElementById('eclipse-probe') || !document.documentElement) return;
    buildPanel();
  };
  window.addEventListener('keydown', (e) => {
    if (e.altKey && e.shiftKey && e.code === 'KeyP') {
      const existing = document.getElementById('eclipse-probe');
      if (existing) { dismissed = true; existing.remove(); } else { dismissed = false; ensurePanel(); }
    }
  });
  try {
    if (typeof GM_registerMenuCommand === 'function') GM_registerMenuCommand('Show the probe panel', () => { dismissed = false; ensurePanel(); });
  } catch (_) { /* the manager has no menu */ }
  console.log('[eclipse-probe] loaded on', location.href, '(Alt+Shift+P toggles the panel)');
  ensurePanel();
  setInterval(ensurePanel, 2000);
  window.__eclipseProbe = { messageItems, rawTextOf, settingsReport, tagsInRaw, findMessageList, messageOf, outline, tagCensus, reactReport, messageReport, fullReport };
})();
