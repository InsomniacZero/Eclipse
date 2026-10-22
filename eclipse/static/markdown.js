// ===================================================================
// Chat markdown + LaTeX renderer
// ===================================================================
// EclipseMarkdown.render(src, { highlightCode, sources }) -> HTML string for innerHTML.
//
// Pipeline: marked parses the text (raw HTML in the reply is shown as text, never
// executed), a small extension turns math into KaTeX, and DOMPurify checks the result.
// Code cards, KaTeX output and citation pills are generated here from escaped input, so they are
// swapped in by placeholder AFTER sanitizing; that keeps the sanitizer allowlist small.
// `sources` ([{n, title, url, snippet}], from the chat tools) turns [1] or [1, 2] in the text
// into citation pills, but only for numbers that have a source.
// Vendored libraries (no outside hosts): vendor/marked.umd.js, vendor/purify.min.js,
// vendor/katex/katex.min.js.
(function (global) {
  'use strict';

  function escapeText(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  const LINK_ICON =
    '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="link-ext-icon">' +
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>' +
    '<polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>';

  const WRAP_ICON =
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<line x1="3" y1="6" x2="21" y2="6"></line><path d="M3 12h15a3 3 0 0 1 0 6h-4"></path><polyline points="16 16 14 18 16 20"></polyline>' +
    '<line x1="3" y1="18" x2="10" y2="18"></line></svg>';
  const COPY_ICON =
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>' +
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';

  const SAFE_HREF = /^(?:https?:\/\/|mailto:)/i;
  const SAFE_IMG_SRC = /^(?:\/static\/|data:image\/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$)/i;

  // Only one render runs at a time (everything is synchronous), so the renderer callbacks
  // read the current call's state from here.
  let ctx = null;

  function placeholder(kind, index) {
    return '@@' + ctx.nonce + kind + index + '@@';
  }

  // ---------------------------------------------------------------
  // Math
  // ---------------------------------------------------------------

  // While a reply streams the whole message is rendered again on every frame, so a
  // formula that has not changed is served from here instead of going through KaTeX again.
  const MATH_CACHE_MAX = 500;
  const mathCache = new Map();

  function katexHtml(tex, display) {
    const src = String(tex).trim();
    const key = (display ? 'D' : 'I') + src;
    const hit = mathCache.get(key);
    if (hit !== undefined) return hit;
    const out = renderKatex(src, display);
    if (mathCache.size >= MATH_CACHE_MAX) mathCache.delete(mathCache.keys().next().value);
    mathCache.set(key, out);
    return out;
  }

  function renderKatex(src, display) {
    try {
      return global.katex.renderToString(src, {
        displayMode: display,
        throwOnError: false,
        strict: 'ignore',
        trust: false,
        maxExpand: 1000,
        maxSize: 100,
        errorColor: '#cc4b37',
      });
    } catch (e) {
      return '<span class="chat-math-error">' + escapeText(src) + '</span>';
    }
  }

  function mathPlaceholder(tex, display) {
    const index = ctx.maths.push(katexHtml(tex, display)) - 1;
    return placeholder('M', index);
  }

  // Index of the closing delimiter, or -1. Backslash pairs are skipped, and a blank line
  // ends the search (math never spans paragraphs).
  function findClose(src, from, delim, allowNewline) {
    for (let i = from; i < src.length; i++) {
      const ch = src[i];
      if (src.startsWith(delim, i)) return i;
      if (ch === '\\') { i++; continue; }
      if (ch === '\n' && (!allowNewline || src[i + 1] === '\n')) return -1;
    }
    return -1;
  }

  const MATH_ENV = 'align\\*?|aligned|equation\\*?|gather\\*?|gathered|multline\\*?|split|cases|[pbBvV]?matrix|array';
  const MATH_ENV_RE = new RegExp('^ {0,3}\\\\begin\\{(' + MATH_ENV + ')\\}[\\s\\S]*?\\\\end\\{\\1\\}[ \\t]*(?:\\n|$)');

  const mathBlockExtension = {
    name: 'mathBlock',
    level: 'block',
    start(src) {
      const m = /(?:^|\n) {0,3}(?:\$\$|\\\[|\\begin\{)/.exec(src);
      if (!m) return undefined;
      return m.index + (m[0][0] === '\n' ? 1 : 0);
    },
    tokenizer(src) {
      let m = /^ {0,3}\$\$([\s\S]+?)\$\$[ \t]*(?:\n|$)/.exec(src);
      if (m) return { type: 'mathBlock', raw: m[0], text: m[1], pending: false };
      m = /^ {0,3}\\\[([\s\S]+?)\\\][ \t]*(?:\n|$)/.exec(src);
      if (m) return { type: 'mathBlock', raw: m[0], text: m[1], pending: false };
      m = MATH_ENV_RE.exec(src);
      if (m) return { type: 'mathBlock', raw: m[0], text: m[0], pending: false };
      // A $$ that has not been closed yet: the reply is still streaming.
      m = /^ {0,3}\$\$(?![\s\S]*\$\$)([\s\S]*)$/.exec(src);
      if (m) return { type: 'mathBlock', raw: m[0], text: m[1], pending: true };
      return undefined;
    },
    renderer(token) {
      if (token.pending) return '<div class="chat-math-pending">' + escapeText(token.text.trim()) + '</div>\n';
      return '<div class="chat-math-block">' + mathPlaceholder(token.text, true) + '</div>\n';
    },
  };

  const mathInlineExtension = {
    name: 'mathInline',
    level: 'inline',
    start(src) {
      const i = src.search(/\$|\\[(\[]/);
      return i < 0 ? undefined : i;
    },
    tokenizer(src) {
      let end;
      if (src.startsWith('$$')) {
        end = findClose(src, 2, '$$', true);
        if (end > 2) return { type: 'mathInline', raw: src.slice(0, end + 2), text: src.slice(2, end), display: true };
        return undefined;
      }
      if (src.startsWith('\\(')) {
        end = findClose(src, 2, '\\)', true);
        if (end > 2) return { type: 'mathInline', raw: src.slice(0, end + 2), text: src.slice(2, end), display: false };
        return undefined;
      }
      if (src.startsWith('\\[')) {
        end = findClose(src, 2, '\\]', true);
        if (end > 2) return { type: 'mathInline', raw: src.slice(0, end + 2), text: src.slice(2, end), display: true };
        return undefined;
      }
      if (src[0] === '$' && src.length > 2 && !/[\s$]/.test(src[1])) {
        end = findClose(src, 1, '$', false);
        if (end > 1) {
          const body = src.slice(1, end);
          // "$5 and $10": a closing $ after a space or before a digit is a price.
          if (!/\s$/.test(body) && !/\d/.test(src[end + 1] || '')) {
            return { type: 'mathInline', raw: src.slice(0, end + 1), text: body, display: false };
          }
        }
      }
      return undefined;
    },
    renderer(token) {
      return mathPlaceholder(token.text, token.display);
    },
  };

  // ---------------------------------------------------------------
  // Citations: [1] or [1, 2] -> pills, only for numbers that have a source
  // ---------------------------------------------------------------

  function hostOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch (e) {
      return '';
    }
  }

  function citePillHtml(source) {
    return (
      '<a class="cite-pill" href="' + escapeText(source.url) + '" target="_blank" rel="noopener noreferrer"' +
      ' data-cite="' + source.n + '" data-title="' + escapeText(source.title) + '"' +
      ' data-domain="' + escapeText(hostOf(source.url)) + '" data-snippet="' + escapeText(source.snippet) + '">' +
      source.n + '</a>'
    );
  }

  const citationExtension = {
    name: 'citation',
    level: 'inline',
    start(src) {
      const i = src.indexOf('[');
      return i < 0 ? undefined : i;
    },
    tokenizer(src) {
      if (!ctx || !ctx.sources.size) return undefined;
      const m = /^\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?![(:])/.exec(src);
      if (!m) return undefined;
      const numbers = m[1].split(',').map((x) => parseInt(x, 10));
      if (!numbers.every((n) => ctx.sources.has(n))) return undefined;
      return { type: 'citation', raw: m[0], numbers };
    },
    renderer(token) {
      return token.numbers
        .map((n) => placeholder('Q', ctx.cites.push(citePillHtml(ctx.sources.get(n))) - 1))
        .join('<span class="cite-gap"></span>');
    },
  };

  // ---------------------------------------------------------------
  // marked setup
  // ---------------------------------------------------------------

  function codeCardHtml(text, lang) {
    const code = String(text).replace(/^\n+|\s+$/g, '');
    const label = (String(lang || '').split(/\s+/)[0] || 'code').toLowerCase();
    const highlighted = ctx.highlightCode(code, label);
    let b64 = '';
    try {
      b64 = global.btoa(unescape(encodeURIComponent(code)));
    } catch (e) {
      b64 = global.btoa(code.substring(0, 500));
    }
    return (
      '<div class="chat-code-card"><div class="chat-code-header">' +
      '<span class="chat-code-lang">' + escapeText(label) + '</span>' +
      '<span class="chat-code-actions">' +
      '<button class="chat-code-wrap-btn" type="button" aria-pressed="false" title="Wrap long lines">' +
      WRAP_ICON + '<span>Wrap</span></button>' +
      '<button class="chat-code-copy-btn" data-code-b64="' + b64 + '" title="Copy code">' +
      COPY_ICON + '<span>Copy</span></button></span></div>' +
      '<pre class="chat-code-pre"><code>' + highlighted + '</code></pre></div>'
    );
  }

  function buildMarked() {
    const marked = new global.marked.Marked({ gfm: true, breaks: true });
    marked.use({
      extensions: [mathBlockExtension, mathInlineExtension, citationExtension],
      renderer: {
        code({ text, lang }) {
          const index = ctx.codes.push(codeCardHtml(text, lang)) - 1;
          return placeholder('C', index) + '\n';
        },
        codespan({ text }) {
          return '<code class="chat-md-inline-code">' + text + '</code>';
        },
        heading({ tokens, depth }) {
          return '<h' + depth + ' class="chat-md-h' + depth + '">' + this.parser.parseInline(tokens) + '</h' + depth + '>\n';
        },
        html({ text, block }) {
          if (/^<br\s*\/?>$/i.test(text.trim())) return '<br>';
          const shown = escapeText(text);
          return block ? '<p>' + shown.trim().replace(/\n/g, '<br>') + '</p>\n' : shown;
        },
        link({ href, title, tokens }) {
          const inner = this.parser.parseInline(tokens);
          const url = String(href || '').trim();
          if (!SAFE_HREF.test(url)) return inner;
          return (
            '<a href="' + escapeText(url) + '" target="_blank" rel="noopener noreferrer" class="chat-md-link"' +
            (title ? ' title="' + escapeText(title) + '"' : '') + '>' + inner + ' ' + LINK_ICON + '</a>'
          );
        },
        image({ href, title, text }) {
          const url = String(href || '').trim();
          if (SAFE_IMG_SRC.test(url)) {
            return '<img class="chat-md-img" loading="lazy" src="' + escapeText(url) + '" alt="' + escapeText(text) + '"' +
              (title ? ' title="' + escapeText(title) + '"' : '') + '>';
          }
          // A remote image would send a request (with whatever the model put in the URL)
          // the moment the message renders, so it is offered as a link instead.
          if (/^https?:\/\//i.test(url)) {
            return '<a href="' + escapeText(url) + '" target="_blank" rel="noopener noreferrer" class="chat-md-link">' +
              escapeText(text || url) + ' ' + LINK_ICON + '</a>';
          }
          return escapeText(text);
        },
        checkbox({ checked }) {
          return '<span class="chat-md-checkbox' + (checked ? ' checked' : '') + '" aria-hidden="true"></span> ';
        },
      },
    });
    return marked;
  }

  // ---------------------------------------------------------------
  // Sanitizer
  // ---------------------------------------------------------------

  const ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'a', 'ul', 'ol', 'li', 'blockquote', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span', 'img', 'svg', 'path', 'polyline', 'line',
  ];
  const ALLOWED_ATTR = [
    'href', 'target', 'rel', 'class', 'title', 'src', 'alt', 'loading', 'align', 'start',
    'width', 'height', 'viewBox', 'fill', 'stroke', 'stroke-width', 'd', 'points', 'x1', 'y1', 'x2', 'y2',
    'aria-hidden',
  ];

  let purifier = null;
  function getPurifier() {
    if (purifier) return purifier;
    purifier = global.DOMPurify(global);
    purifier.addHook('afterSanitizeAttributes', (node) => {
      if (node.tagName === 'A') {
        if (!SAFE_HREF.test(node.getAttribute('href') || '')) node.removeAttribute('href');
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer');
      } else if (node.tagName === 'IMG' && !SAFE_IMG_SRC.test(node.getAttribute('src') || '')) {
        node.remove();
      }
    });
    return purifier;
  }

  function sanitize(html) {
    return getPurifier().sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
    });
  }

  // ---------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------

  let markedInstance = null;

  function decorate(html) {
    return html
      .replace(/<(ul|ol)(?=[\s>])/g, '<$1 class="chat-md-list"')
      .replace(/<blockquote>/g, '<blockquote class="chat-md-blockquote">')
      .replace(/<hr\s*\/?>/g, '<hr class="chat-md-hr">')
      .replace(/<table>/g, '<div class="chat-table-wrapper"><table class="chat-md-table">')
      .replace(/<\/table>/g, '</table></div>');
  }

  function render(src, options) {
    const text = String(src == null ? '' : src);
    if (!text.trim()) return '';
    const highlight = options && options.highlightCode;
    if (!global.marked || !global.DOMPurify) {
      return '<p>' + escapeText(text).replace(/\n/g, '<br>') + '</p>';
    }
    if (!markedInstance) markedInstance = buildMarked();

    const outer = ctx;
    const sources = new Map();
    for (const src of (options && options.sources) || []) {
      if (src && Number.isInteger(src.n) && typeof src.url === 'string' && /^https?:\/\//i.test(src.url)) {
        sources.set(src.n, {
          n: src.n,
          url: src.url,
          title: String(src.title || src.url).slice(0, 200),
          snippet: String(src.snippet || '').slice(0, 300),
        });
      }
    }
    ctx = {
      nonce: Math.random().toString(36).slice(2, 8),
      codes: [],
      maths: [],
      cites: [],
      sources,
      highlightCode: highlight || escapeText,
    };
    try {
      let html = markedInstance.parse(text, { async: false });
      html = sanitize(decorate(html));
      const restore = new RegExp('@@' + ctx.nonce + '([CMQ])(\\d+)@@', 'g');
      const { codes, maths, cites } = ctx;
      const pools = { C: codes, M: maths, Q: cites };
      return html.replace(restore, (m, kind, i) => pools[kind][Number(i)] || '');
    } finally {
      ctx = outer;
    }
  }

  global.EclipseMarkdown = { render, escapeText };
})(window);
