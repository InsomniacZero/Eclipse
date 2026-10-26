// ===================================================================
// Eclipse: JanitorAI regex display
// ===================================================================
// Applies a preset's display regex scripts to JanitorAI's replies. Built into one file by
// eclipse/userscript.py, which puts `marked` and `DOMPurify` in scope above this code.
//
// How it works (see docs/superpowers/specs/2026-10-01-presets-phase1-design.md):
//   1. The page keeps the model name (kimi-k3@miyabi) and the proxy address in its settings, so the
//      preset name and the gateway are read from the page. Nothing to configure locally.
//   2. The display scripts come from GET <gateway>/v1/presets/<name>/display-scripts.
//   3. For each message the raw reply text is read from the page's React props (the page's own renderer
//      has already turned `<log>` into plain text, so the DOM no longer has the tags).
//   4. The scripts run on the raw text exactly like SillyTavern's regex engine. If nothing changed, the
//      message is left alone. If something changed, the result is rendered as markdown, sanitized, and
//      shown in a shadow-DOM box in place of the original (the original is only hidden).
//
// Safety: every replacement is untrusted HTML (a shared preset could carry anything). It is sanitized
// with DOMPurify, scripts and event handlers are removed, CSS may not load anything from the network, and
// the result lives in a shadow root so its <style> cannot restyle JanitorAI. The page's API key is never
// read: only the model name and the proxy address.
const SG_VERSION = '1.0.0';
const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,39}$/;
const CACHE_MS = 120000;
const WRAPPER = '[class*="_messageDisplayWrapper_"]';
const BODY = '[class*="_messageBody_"]';

const state = {
  enabled: true,
  preset: null,
  base: null,
  scripts: [],
  names: { char: '', user: '' },
  fetchedAt: 0,
  misses: 0,
  loading: false,
  notice: '',
  toasted: '',
};
const overlays = new WeakMap();   // wrapper -> { host, shadow, body, mdRoot, key, showOriginal, hiddenDisplay }

// ------------------------------------------------------------------ React props

function fiberOf(el) {
  if (!el) return null;
  const key = Object.keys(el).find((k) => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
  return key ? el[key] : null;
}

function walkFibers(el, visit, maxHops) {
  let fiber = fiberOf(el);
  for (let hops = 0; fiber && hops < (maxHops || 60); hops += 1, fiber = fiber.return) {
    const props = fiber.memoizedProps;
    if (props && typeof props === 'object') {
      try {
        if (visit(props, hops) === true) return;
      } catch (_) { /* a getter that throws */ }
    }
  }
}

function anchorOf(wrapper) {
  return wrapper.querySelector('p') || wrapper;
}

// The reply as the model wrote it. The longest string on the way up is the whole message (the nearer
// ones are single paragraphs).
function rawTextOf(wrapper) {
  let best = '';
  walkFibers(anchorOf(wrapper), (props) => {
    if (typeof props.children === 'string' && props.children.length > best.length) best = props.children;
    const m = props.message;
    if (m && typeof m === 'object' && typeof m.message === 'string' && m.message.length > best.length) best = m.message;
  });
  return best;
}

// 'user' or 'bot'. The page's message object is checked for the usual fields; when none is there the
// message counts as the character's.
function roleOf(wrapper) {
  let role = 'bot';
  walkFibers(anchorOf(wrapper), (props) => {
    const m = props.message;
    if (!m || typeof m !== 'object') return false;
    const first = Array.isArray(m) || typeof m.length === 'number' ? m[0] : m;
    const o = first && typeof first === 'object' ? first : m;
    if (o.is_bot === false || o.isBot === false || o.is_user === true || o.isUser === true) { role = 'user'; return true; }
    if (o.is_bot === true || o.isBot === true) { role = 'bot'; return true; }
    const r = String(o.role || o.sender || o.author || '').toLowerCase();
    if (r === 'user' || r === 'human') { role = 'user'; return true; }
    if (r === 'assistant' || r === 'bot' || r === 'character' || r === 'model') { role = 'bot'; return true; }
    return false;
  });
  return role;
}

// Dynamic detection of local ngrok tunnels (runs on ANY user or friend's machine)
function detectDynamicNgrok() {
  return new Promise((resolve) => {
    const custom = gmGet('customGateway', '');
    if (custom && typeof custom === 'string' && /^https?:\/\//i.test(custom)) {
      return resolve(gatewayOf(custom));
    }
    if (typeof GM_xmlhttpRequest === 'function') {
      try {
        GM_xmlhttpRequest({
          method: 'GET',
          url: 'http://127.0.0.1:4040/api/tunnels',
          timeout: 1800,
          onload: (r) => {
            if (r.status === 200 && r.responseText) {
              try {
                const data = JSON.parse(r.responseText);
                const tunnels = Array.isArray(data.tunnels) ? data.tunnels : [];
                const httpsTunnel = tunnels.find((t) => t && (t.proto === 'https' || String(t.public_url || '').startsWith('https')));
                const chosen = httpsTunnel || tunnels[0];
                if (chosen && chosen.public_url) {
                  return resolve(gatewayOf(chosen.public_url));
                }
              } catch (_) {}
            }
            resolve(null);
          },
          onerror: () => resolve(null),
          ontimeout: () => resolve(null),
        });
        return;
      } catch (_) {}
    }
    resolve(null);
  });
}

function readSettingsFromStorage() {
  let model = gmGet('defaultModel', '');
  let proxy = gmGet('customGateway', '');
  try {
    if (typeof localStorage !== 'undefined') {
      let p = localStorage.getItem('open_ai_reverse_proxy') || '';
      let m = localStorage.getItem('openAiModel') || localStorage.getItem('open_ai_model') || '';
      if (p) proxy = p;
      if (m) model = m;

      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k) continue;
        const lk = k.toLowerCase();
        if (lk.includes('user') || lk.includes('proxy') || lk.includes('persist') || lk.includes('config') || lk.includes('setting')) {
          try {
            const raw = localStorage.getItem(k);
            if (raw && (raw.startsWith('{') || raw.startsWith('['))) {
              const parsed = JSON.parse(raw);
              const target = parsed.state || parsed.config || parsed;
              if (target && typeof target === 'object') {
                const c = target.config || target;
                if (!proxy && typeof c.open_ai_reverse_proxy === 'string') proxy = c.open_ai_reverse_proxy;
                if (!model && typeof c.openAiModel === 'string') model = c.openAiModel;
                if (c.proxyConfigurations && c.selectedProxyConfigId) {
                  const list = c.proxyConfigurations;
                  const item = Array.isArray(list) ? list.find(x => x && x.id === c.selectedProxyConfigId) : list[c.selectedProxyConfigId];
                  if (item && typeof item === 'object') {
                    if (item.url || item.proxy) proxy = item.url || item.proxy;
                    if (item.model) model = item.model;
                  }
                }
              }
            }
          } catch (_) {}
        }
      }
    }
  } catch (_) {}
  return (model || proxy) ? { model, proxy } : null;
}

// The preset and the gateway, from the page's own settings. Only these two are read (never a key).
function readSettings(wrapper) {
  let found = null;
  walkFibers(anchorOf(wrapper), (props) => {
    const store = props.userStore;
    if (store && typeof store === 'object' && store.config && typeof store.config === 'object') {
      found = store.config;
      return true;
    }
    return false;
  }, 80);

  let model = '';
  let proxy = '';
  if (found) {
    model = typeof found.openAiModel === 'string' ? found.openAiModel : '';
    proxy = typeof found.open_ai_reverse_proxy === 'string' ? found.open_ai_reverse_proxy : '';
    try {
      const list = found.proxyConfigurations;
      const id = found.selectedProxyConfigId;
      const chosen = Array.isArray(list) ? list.find((c) => c && c.id === id) : (list && list[id]);
      if (chosen && typeof chosen === 'object') {
        const m = chosen.model || chosen.openAiModel || chosen.open_ai_model;
        const u = chosen.url || chosen.proxy || chosen.open_ai_reverse_proxy || chosen.endpoint;
        if (typeof m === 'string' && m.includes('@')) model = m;
        if (typeof u === 'string' && /^https?:/i.test(u)) proxy = u;
      }
    } catch (_) {}
  }

  if (!model || !proxy) {
    const fallback = readSettingsFromStorage();
    if (fallback) {
      if (!model && fallback.model) model = fallback.model;
      if (!proxy && fallback.proxy) proxy = fallback.proxy;
    }
  }

  if (!proxy) {
    if (typeof SG_EMBEDDED_NGROK !== 'undefined' && SG_EMBEDDED_NGROK) proxy = SG_EMBEDDED_NGROK;
    else if (typeof SG_EMBEDDED_BASE !== 'undefined' && SG_EMBEDDED_BASE) proxy = SG_EMBEDDED_BASE;
  }

  return (model || proxy) ? { model, proxy } : null;
}

function presetFromModel(model) {
  if (typeof model !== 'string' || !model.includes('@')) return null;
  const name = model.slice(model.lastIndexOf('@') + 1).trim().toLowerCase();
  return NAME_RE.test(name) ? name : null;
}

function gatewayOf(proxy) {
  if (!proxy || typeof proxy !== 'string') return null;
  let raw = proxy.trim();
  if (!/^https?:\/\//i.test(raw)) raw = 'http://' + raw;
  try {
    const u = new URL(raw);
    return /^https?:$/.test(u.protocol) ? u.origin : null;
  } catch (_) { return null; }
}

// ------------------------------------------------------------------ fetching the scripts

function gmGet(name, fallback) {
  try { return typeof GM_getValue === 'function' ? GM_getValue(name, fallback) : fallback; } catch (_) { return fallback; }
}

function httpGet(url) {
  const headers = {
    'ngrok-skip-browser-warning': 'true',
    'Accept': 'application/json, text/plain, */*'
  };
  const key = gmGet('gatewayKey', '');
  if (key) headers.Authorization = `Bearer ${key}`;
  return new Promise((resolve, reject) => {
    const doFetch = () => {
      fetch(url, { headers })
        .then((r) => r.text().then((text) => resolve({ status: r.status, text })))
        .catch((err) => reject(new Error(err && err.message ? err.message : 'could not reach the gateway')));
    };
    if (typeof GM_xmlhttpRequest === 'function') {
      try {
        GM_xmlhttpRequest({
          method: 'GET', url, headers, timeout: 8000,
          onload: (r) => {
            if (r.status === 200 || r.status === 401 || r.status === 404) {
              resolve({ status: r.status, text: r.responseText });
            } else {
              doFetch();
            }
          },
          onerror: () => doFetch(),
          ontimeout: () => doFetch(),
        });
        return;
      } catch (_) {
        doFetch();
        return;
      }
    }
    doFetch();
  });
}

async function loadScripts(force) {
  if (state.loading || !state.preset) return;
  if (!state.base) {
    const dynamicNgrok = await detectDynamicNgrok();
    if (dynamicNgrok) {
      state.base = dynamicNgrok;
      toastOnce(`Connected via active ngrok tunnel: ${state.base}`);
    } else if (typeof SG_EMBEDDED_NGROK !== 'undefined' && SG_EMBEDDED_NGROK) {
      state.base = gatewayOf(SG_EMBEDDED_NGROK);
    } else if (typeof SG_EMBEDDED_BASE !== 'undefined' && SG_EMBEDDED_BASE) {
      state.base = gatewayOf(SG_EMBEDDED_BASE);
    }
  }
  if (!state.base) return;
  if (!force && Date.now() - state.fetchedAt < CACHE_MS) return;
  state.loading = true;
  try {
    const res = await httpGet(`${state.base}/v1/presets/${encodeURIComponent(state.preset)}/display-scripts`);
    if (res.status === 404) { state.scripts = []; state.notice = `No preset called "${state.preset}" at ${state.base}`; }
    else if (res.status === 401) { state.scripts = []; state.notice = 'The gateway wants its key: use the Tampermonkey menu, "Set gateway key"'; }
    else if (res.status !== 200) { state.scripts = []; state.notice = `The gateway answered ${res.status}`; }
    else {
      const data = JSON.parse(res.text);
      state.scripts = Array.isArray(data.scripts) ? data.scripts : [];
      state.names = { char: data.char_name || '', user: data.user_name || '' };
      state.notice = state.scripts.length ? `Preset ${state.preset}: ${state.scripts.length} display script${state.scripts.length === 1 ? '' : 's'}` : `Preset ${state.preset} has no display scripts`;
    }
  } catch (e) {
    if (/localhost|127\.0\.0\.1/i.test(state.base)) {
      try {
        const dynamicNgrok = await detectDynamicNgrok();
        const altBase = dynamicNgrok || (typeof SG_EMBEDDED_NGROK !== 'undefined' && SG_EMBEDDED_NGROK ? gatewayOf(SG_EMBEDDED_NGROK) : null);
        if (altBase && altBase !== state.base) {
          state.base = altBase;
          toastOnce(`Switched to active ngrok tunnel: ${state.base}`);
          const altRes = await httpGet(`${state.base}/v1/presets/${encodeURIComponent(state.preset)}/display-scripts`);
          if (altRes.status === 200) {
            const data = JSON.parse(altRes.text);
            state.scripts = Array.isArray(data.scripts) ? data.scripts : [];
            state.names = { char: data.char_name || '', user: data.user_name || '' };
            state.notice = `Preset ${state.preset} loaded via ngrok tunnel`;
            state.fetchedAt = Date.now();
            state.loading = false;
            toastOnce(state.notice);
            return;
          }
        }
      } catch (_) {}
    }
    state.scripts = [];
    state.notice = e && e.message ? e.message : 'could not load the scripts';
  }
  state.fetchedAt = Date.now();
  state.loading = false;
  toastOnce(state.notice);
}

// ------------------------------------------------------------------ the regex engine (SillyTavern rules)

const regexCache = new Map();

// How SillyTavern reads `/pattern/flags` (or a bare pattern). Returns null when it is not a valid RegExp.
function regexFromString(input) {
  if (typeof input !== 'string' || !input) return null;
  if (regexCache.has(input)) return regexCache.get(input);
  let re = null;
  try {
    const m = input.match(/(\/?)(.+)\1([a-z]*)/i);
    if (m) {
      if (m[3] && !/^(?!.*?(.).*?\1)[gmixXsuUAJ]+$/.test(m[3])) re = new RegExp(input);
      else re = new RegExp(m[2], m[3]);
    }
  } catch (_) { re = null; }
  if (regexCache.size > 500) regexCache.clear();
  regexCache.set(input, re);
  return re;
}

// {{char}} {{user}} {{newline}} {{// comment}} {{trim}}. Anything else stays as written.
function macroLite(text, names) {
  if (!text || !text.includes('{{')) return text || '';
  const out = String(text).replace(/\{\{\s*(char|user|newline|trim|\/\/[^}]*)\s*\}\}/gi, (whole, key) => {
    const k = key.toLowerCase();
    if (k.startsWith('//')) return '';
    if (k === 'newline') return '\n';
    if (k === 'trim') return '';
    const v = k === 'char' ? names.char : names.user;
    return v || whole;
  });
  return out.replace(/\n*\n*/g, '');
}

function escapeRegexText(text) {
  return String(text).replace(/[.^$*+?{}[\]\\/|()]/g, '\\$&');
}

function applyScript(script, text, names) {
  if (!script || script.disabled || !script.find || !text) return text;
  let find = script.find;
  if (script.substitute === 1 || script.substitute === 2) {
    find = find.replace(/\{\{\s*(char|user)\s*\}\}/gi, (whole, k) => {
      const v = k.toLowerCase() === 'char' ? names.char : names.user;
      if (!v) return whole;
      return script.substitute === 2 ? escapeRegexText(v) : v;
    });
  }
  const re = regexFromString(find);
  if (!re) return text;
  if (re.global || re.sticky) re.lastIndex = 0;
  // Macros are rendered on the template first, so captured chat text can never be read as a macro.
  const template = macroLite(String(script.replace || '').replace(/\{\{match\}\}/gi, '$0'), names);
  const trims = (script.trim_strings || []).map((t) => macroLite(String(t), names)).filter(Boolean);
  try {
    return text.replace(re, (...args) => {
      const last = args[args.length - 1];
      const named = last && typeof last === 'object' ? last : null;
      const groupCount = args.length - (named ? 4 : 3);
      return template.replace(/\$(\d+)|\$<([^>]+)>/g, (_, num, name) => {
        let value;
        if (num !== undefined) {
          const n = Number(num);
          value = n === 0 ? args[0] : (n <= groupCount ? args[n] : undefined);
        } else {
          value = named ? named[name] : undefined;
        }
        if (!value || typeof value !== 'string') return '';
        trims.forEach((t) => { value = value.split(t).join(''); });
        return value;
      });
    });
  } catch (_) {
    return text;
  }
}

function runsOnDisplay(script) {
  return !!script.markdown_only || !script.prompt_only;
}

function depthAllows(script, depth) {
  if (typeof depth !== 'number') return true;
  if (script.min_depth != null && script.min_depth >= -1 && depth < script.min_depth) return false;
  if (script.max_depth != null && script.max_depth >= 0 && depth > script.max_depth) return false;
  return true;
}

function runScripts(text, scripts, placement, depth, names) {
  let out = text;
  for (const script of scripts) {
    if (script.disabled || !runsOnDisplay(script)) continue;
    if (!(script.placement || []).includes(placement)) continue;
    if (!depthAllows(script, depth)) continue;
    out = applyScript(script, out, names);
  }
  return out;
}

// ------------------------------------------------------------------ sanitizing

// CSS may style but not fetch: no @import, no url() unless it is data: or a fragment. Escapes are
// decoded first so `u\72l(` cannot hide a url().
// A script's <style> was written for the whole SillyTavern page. Inside the box, :root and html mean the box
// itself (so variables defined there reach everything) and body means the box's content.
function scopeCss(css) {
  return String(css || '')
    .replace(/:root\b/g, ':host')
    .replace(/(^|[,{}\s>+~])html(?=[\s,{.:#>+~[]|$)/gi, '$1:host')
    .replace(/(^|[,{}\s>+~])body(?=[\s,{.:#>+~[]|$)/gi, '$1.sg');
}

function cleanCss(css) {
  let text = String(css || '').replace(/\\([0-9a-fA-F]{1,6})\s?/g, (_, hex) => {
    const code = parseInt(hex, 16);
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : '';
  }).replace(/\\(.)/g, '$1');
  text = text.replace(/@import[^;{]*;?/gi, '');
  text = text.replace(/url\(\s*(['"]?)\s*(?!data:image\/|#)[^)]*\1\s*\)/gi, 'none');
  text = text.replace(/expression\s*\(|-moz-binding|behavior\s*:/gi, 'x-blocked');
  return text;
}

let purifyReady = false;
function setupPurify() {
  if (purifyReady) return;
  purifyReady = true;
  DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
    if (data.attrName === 'style') data.attrValue = cleanCss(data.attrValue);
    if ((data.attrName === 'src' || data.attrName === 'srcset' || data.attrName === 'poster') && !/^\s*(https:|data:image\/)/i.test(data.attrValue)) {
      data.keepAttr = false;
    }
  });
  DOMPurify.addHook('afterSanitizeElements', (node) => {
    if (node.nodeName === 'STYLE') node.textContent = scopeCss(cleanCss(node.textContent));
  });
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.nodeName === 'A' && node.hasAttribute('href')) {
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer nofollow');
    }
  });
}

function sanitizeHtml(html) {
  setupPurify();
  return DOMPurify.sanitize(html, {
    FORCE_BODY: true,
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['script', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'form', 'base', 'meta', 'link', 'use', 'foreignObject', 'math'],
    FORBID_ATTR: ['srcdoc', 'formaction', 'action', 'ping'],
  });
}

// <style> blocks skip the markdown pass: it would turn a URL inside the CSS into a link and break the block.
function renderMarkdown(text) {
  const styles = [];
  const guarded = String(text).replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, (block) => {
    styles.push(block);
    return `\uE000${styles.length - 1}\uE001`;
  });
  const html = marked.parse(guarded, { gfm: true, breaks: true, async: false })
    .replace(/\uE000(\d+)\uE001/g, (_, i) => styles[Number(i)] || '');
  return sanitizeHtml(html);
}

// ------------------------------------------------------------------ the message box

const BASE_CSS = `
:host { display: block; }
.sg { font: inherit; color: inherit; line-height: 1.6; overflow-wrap: anywhere; position: relative; }
.sg > :first-child { margin-top: 0; }
.sg p { margin: 0 0 0.8em; }
.sg img, .sg svg { max-width: 100%; height: auto; }
.sg pre { overflow: auto; padding: 0.6em 0.8em; border-radius: 6px; background: rgba(127,127,127,.16); }
.sg code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.92em; }
.sg a { color: inherit; text-decoration: underline; }
.sg blockquote { margin: 0.6em 0; padding-left: 0.9em; border-left: 3px solid rgba(127,127,127,.6); }
.sg table { border-collapse: collapse; }
.sg td, .sg th { border: 1px solid rgba(127,127,127,.5); padding: 0.25em 0.5em; }
.sg-toggle { position: absolute; top: -2px; right: 0; border: 0; background: transparent; color: inherit; opacity: 0; cursor: pointer; font-size: 12px; }
:host(:hover) .sg-toggle { opacity: 0.5; }
.sg-toggle:hover { opacity: 1 !important; }
`;

// SillyTavern's theme variables, which presets use for colours (var(--SmartThemeQuoteColor) and so on).
// JanitorAI has none of them, so the box defines them from the page's own colours.
function parseColor(text) {
  const m = String(text || '').match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const [r, g, b, a] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
  return { r, g, b, a: a === undefined || Number.isNaN(a) ? 1 : a };
}

function themeVariables(anchor) {
  let text = parseColor(getComputedStyle(anchor).color) || { r: 230, g: 230, b: 230, a: 1 };
  let bg = null;
  for (let el = anchor; el && !bg; el = el.parentElement) {
    const c = parseColor(getComputedStyle(el).backgroundColor);
    if (c && c.a > 0.5) bg = c;
  }
  const dark = (0.299 * text.r + 0.587 * text.g + 0.114 * text.b) > 140;
  bg = bg || (dark ? { r: 24, g: 24, b: 24, a: 1 } : { r: 250, g: 250, b: 250, a: 1 });
  const rgb = (c, a) => `rgba(${c.r}, ${c.g}, ${c.b}, ${a})`;
  return {
    '--SmartThemeBodyColor': rgb(text, 1),
    '--SmartThemeEmColor': rgb(text, 0.85),
    '--SmartThemeUnderlineColor': rgb(text, 0.9),
    '--SmartThemeQuoteColor': dark ? '#e0a84f' : '#a8641a',
    '--SmartThemeBlurTintColor': rgb(bg, 1),
    '--SmartThemeChatTintColor': rgb(bg, 1),
    '--SmartThemeBotMesBlurTintColor': rgb(bg, 1),
    '--SmartThemeUserMesBlurTintColor': rgb(bg, 1),
    '--SmartThemeShadowColor': dark ? 'rgba(0, 0, 0, 0.55)' : 'rgba(0, 0, 0, 0.18)',
    '--SmartThemeBorderColor': rgb(text, 0.3),
    '--mainFontFamily': 'inherit',
  };
}

function visibleWrappers() {
  const all = Array.from(document.querySelectorAll(WRAPPER));
  const set = new Set(all);
  return all.filter((el) => {
    for (let p = el.parentElement; p; p = p.parentElement) if (set.has(p)) return false;
    if (el.closest('[hidden]') || getComputedStyle(el).display === 'none') return false;
    return el.textContent.length > 0;
  });
}

// The element that holds the page's own rendering of the reply: the child of the message body that
// contains the first paragraph (or, failing that, the child that is not the name bar or the footer).
function markdownRootOf(wrapper) {
  const body = wrapper.querySelector(BODY);
  if (!body) return null;
  const p = wrapper.querySelector('p');
  if (p) {
    for (let cur = p; cur && cur !== body; cur = cur.parentElement) {
      if (cur.parentElement === body) return cur;
    }
  }
  return Array.from(body.children).find((c) => !/_message(Name|Footer)/.test(String(c.className))) || null;
}

function removeOverlay(wrapper) {
  const o = overlays.get(wrapper);
  if (!o) return;
  if (o.host && o.host.parentNode) o.host.parentNode.removeChild(o.host);
  if (o.mdRoot) o.mdRoot.style.display = o.hiddenDisplay || '';
  overlays.delete(wrapper);
}

function showOverlay(wrapper, mdRoot, html, key) {
  let o = overlays.get(wrapper);
  if (o && (o.mdRoot !== mdRoot || !o.host.isConnected)) { removeOverlay(wrapper); o = null; }
  if (!o) {
    const host = document.createElement('div');
    host.setAttribute('data-eclipse-regex', '1');
    const shadow = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = BASE_CSS;
    const body = document.createElement('div');
    body.className = 'sg';
    const toggle = document.createElement('button');
    toggle.className = 'sg-toggle';
    toggle.type = 'button';
    toggle.textContent = '↺';
    toggle.title = 'Show the original text';
    shadow.append(style, body);
    o = { host, shadow, body, toggle, mdRoot, key: '', showOriginal: false, hiddenDisplay: mdRoot.style.display };
    toggle.addEventListener('click', () => {
      o.showOriginal = !o.showOriginal;
      applyVisibility(o);
    });
    mdRoot.parentNode.insertBefore(host, mdRoot.nextSibling);
    overlays.set(wrapper, o);
  }
  if (o.key !== key) {
    o.key = key;
    o.body.innerHTML = html;
    o.body.prepend(o.toggle);
  }
  try {
    const vars = themeVariables(mdRoot);
    o.body.style.cssText = Object.keys(vars).map((k) => `${k}: ${vars[k]}`).join('; ');
  } catch (_) { /* no computed style: the box keeps the page's colours */ }
  applyVisibility(o);
}

function applyVisibility(o) {
  o.mdRoot.style.display = o.showOriginal ? (o.hiddenDisplay || '') : 'none';
  o.host.style.display = o.showOriginal ? 'none' : '';
  o.toggle.title = o.showOriginal ? 'Show the restyled text' : 'Show the original text';
}

function handle(wrapper, depth) {
  const raw = rawTextOf(wrapper);
  if (!raw) return;
  const placement = roleOf(wrapper) === 'user' ? 1 : 2;
  const out = runScripts(raw, state.scripts, placement, depth, state.names);
  if (out === raw) { removeOverlay(wrapper); return; }
  const mdRoot = markdownRootOf(wrapper);
  if (!mdRoot) return;
  const key = `${depth}|${out}`;
  const existing = overlays.get(wrapper);
  if (existing && existing.key === key && existing.mdRoot === mdRoot && existing.host.isConnected) { applyVisibility(existing); return; }
  let html;
  try { html = renderMarkdown(out); } catch (_) { removeOverlay(wrapper); return; }
  showOverlay(wrapper, mdRoot, html, key);
}

function process() {
  const items = visibleWrappers();
  if (!state.enabled) { items.forEach(removeOverlay); return; }
  if (!state.preset || !state.base) {
    const first = items[items.length - 1];
    const settings = first ? readSettings(first) : null;
    if (settings) {
      const preset = presetFromModel(settings.model);
      const base = gatewayOf(settings.proxy);
      if (preset && base) { state.preset = preset; state.base = base; }
      else if (!preset) { state.notice = `the model "${settings.model || '(empty)'}" has no @preset: use model@presetname`; toastOnce(state.notice); }
      else { state.notice = 'the proxy address in the settings is not a web address'; toastOnce(state.notice); }
    } else {
      // Say so, once, after a few tries: a silent script is impossible to debug.
      state.misses += 1;
      if (state.misses === 4) {
        state.notice = items.length ? 'cannot read the model name from this page (Alt+Shift+D prints details)' : 'cannot find any chat messages on this page';
        toastOnce(state.notice);
      }
    }
  }
  if (state.preset && state.base) loadScripts(false);
  if (!state.scripts.length) { items.forEach(removeOverlay); return; }
  items.forEach((wrapper, i) => {
    try { handle(wrapper, items.length - 1 - i); } catch (_) { removeOverlay(wrapper); }
  });
}

// ------------------------------------------------------------------ notices, menu, start

function toastOnce(text) {
  if (!text || state.toasted === text || typeof document === 'undefined') return;
  state.toasted = text;
  const box = document.createElement('div');
  box.textContent = `Eclipse: ${text}`;
  box.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;max-width:340px;padding:8px 12px;border-radius:8px;background:#1c1c1c;color:#eee;font:12px/1.4 system-ui,sans-serif;border:1px solid #555;box-shadow:0 4px 18px rgba(0,0,0,.5)';
  (document.body || document.documentElement).appendChild(box);
  setTimeout(() => box.remove(), 6000);
}

let timer = null;
function schedule() {
  if (timer) return;
  timer = setTimeout(() => { timer = null; process(); }, 80);
}

function debugDump() {
  const items = visibleWrappers();
  const last = items[items.length - 1];
  const info = { version: SG_VERSION, preset: state.preset, gateway: state.base, scripts: state.scripts.length, notice: state.notice, messages: items.length };
  if (last) {
    info.lastRole = roleOf(last);
    info.lastRawLength = rawTextOf(last).length;
    walkFibers(anchorOf(last), (props) => {
      const m = props.message;
      if (m && typeof m === 'object' && !info.messageKeys) info.messageKeys = Object.keys(Array.isArray(m) ? (m[0] || {}) : m).slice(0, 30);
    });
  }
  console.log('[eclipse-regex]', info);
}

function start() {
  try {
    if (typeof GM_registerMenuCommand === 'function') {
      GM_registerMenuCommand('Set or auto-detect gateway / ngrok URL', async () => {
        let detected = await detectDynamicNgrok();
        const msg = detected ? `Detected local ngrok tunnel:\n${detected}\n\nEnter gateway URL or press OK to use detected:` : 'Enter Eclipse Gateway or ngrok URL (leave empty for auto-detect):';
        const entered = window.prompt(msg, detected || state.base || '');
        if (entered !== null) {
          const clean = entered.trim() ? gatewayOf(entered.trim()) : null;
          if (typeof GM_setValue === 'function') GM_setValue('customGateway', clean || '');
          state.base = clean;
          state.fetchedAt = 0;
          state.toasted = '';
          toastOnce(clean ? `Gateway set to ${clean}` : 'Gateway reset to auto-detect');
          loadScripts(true).then(schedule);
        }
      });
      GM_registerMenuCommand('Reload the display scripts', () => { state.fetchedAt = 0; state.toasted = ''; loadScripts(true).then(schedule); });
      GM_registerMenuCommand('Turn restyling on or off', () => { state.enabled = !state.enabled; toastOnce(state.enabled ? 'restyling on' : 'restyling off'); state.toasted = ''; schedule(); });
      GM_registerMenuCommand('Set gateway key (for a tunnel or LAN)', () => {
        const key = window.prompt('Eclipse gateway key (leave empty to clear). Run ./start.sh key to see it.', '');
        if (key !== null && typeof GM_setValue === 'function') { GM_setValue('gatewayKey', key.trim()); state.fetchedAt = 0; state.toasted = ''; loadScripts(true).then(schedule); }
      });
      GM_registerMenuCommand('Print debug info to the console', debugDump);
    }
  } catch (_) { /* no menu in this manager */ }
  window.addEventListener('keydown', (e) => { if (e.altKey && e.shiftKey && e.code === 'KeyD') debugDump(); });
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  setInterval(schedule, 2000);
  schedule();
  console.log('[eclipse-regex] loaded', SG_VERSION);
}

if (typeof window !== 'undefined' && !window.__eclipseRegexLoaded) {
  window.__eclipseRegexLoaded = true;
  window.__eclipseRegex = {
    state, regexFromString, applyScript, runScripts, depthAllows, macroLite, cleanCss, scopeCss, themeVariables, sanitizeHtml, renderMarkdown,
    rawTextOf, roleOf, readSettings, presetFromModel, gatewayOf, markdownRootOf, process, loadScripts, visibleWrappers, overlays,
  };
  start();
}
