// ===================================================================
// Chat tools UI: the "work group" above a reply, the Sources row, and citation hover cards
// ===================================================================
// While a reply streams, EclipseToolSteps.createGroup() receives the events the gateway sends
// (step_start, tool_start, tool_result, step_limit) plus the model's reasoning, and draws a live
// status line and a timeline. When the answer starts the group folds to a one-line summary.
// The same DOM is rebuilt from saved steps by renderSaved().
//
// Everything that comes from the model or from the web (queries, titles, URLs, snippets) is put in
// with textContent, and links are only made for http(s) URLs. Nothing is loaded from an outside host.
(function (global) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const ICONS = {
    search: '<circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>',
    globe: '<circle cx="12" cy="12" r="9"></circle><line x1="3" y1="12" x2="21" y2="12"></line><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z"></path>',
    tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"></path>',
    check: '<polyline points="20 6 9 17 4 12"></polyline>',
    x: '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>',
    chevron: '<polyline points="9 6 15 12 9 18"></polyline>',
    brain: '<circle cx="12" cy="12" r="9"></circle><polyline points="12 7 12 12 15 14"></polyline>',
    stop: '<circle cx="12" cy="12" r="9"></circle><line x1="12" y1="8" x2="12" y2="13"></line><line x1="12" y1="16.5" x2="12" y2="16.6"></line>',
  };

  function icon(name, size = 14) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', String(size));
    svg.setAttribute('height', String(size));
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = ICONS[name] || ICONS.tool;   // static markup from ICONS above, never from data
    return svg;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Whether a search key is saved. app.js sets it from /api/tools; it only picks the wording of the
  // button under a failed search.
  let searchKeySaved = false;
  function setSearchKeySaved(saved) {
    searchKeySaved = !!saved;
  }

  const STOPPED_MESSAGE = 'Stopped before it finished.';

  function safeUrl(url) {
    return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '';
  }

  function hostOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch (_) {
      return '';
    }
  }

  function formatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) return '';
    if (ms < 10000) return `${(Math.round(ms / 100) / 10).toString()}s`;
    const secs = Math.round(ms / 1000);
    return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
  }

  function clip(text, max) {
    const t = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
    return t.length > max ? `${t.slice(0, max - 1)}…` : t;
  }

  // -----------------------------------------------------------------
  // How each tool is described. Unknown tools fall back to "name(argument)".
  // -----------------------------------------------------------------
  const TOOL_UI = {
    web_search: {
      icon: 'search',
      running: (a) => `Searching the web for “${clip(a.query, 80)}”`,
      done: (a) => `Searched “${clip(a.query, 80)}”`,
      kind: 'search',
    },
    fetch_url: {
      icon: 'globe',
      running: (a) => `Reading ${hostOf(a.url) || clip(a.url, 50)}`,
      done: (a) => `Read ${hostOf(a.url) || clip(a.url, 50)}`,
      kind: 'read',
    },
  };

  function describeCall(call, running) {
    const args = call && call.arguments && typeof call.arguments === 'object' ? call.arguments : {};
    const ui = TOOL_UI[call.name];
    if (ui) return { icon: ui.icon, text: running ? ui.running(args) : ui.done(args) };
    const first = Object.values(args).find((v) => typeof v === 'string');
    const name = clip(call.name || 'tool', 40);
    return { icon: 'tool', text: `${running ? 'Running' : 'Ran'} ${name}${first ? ` “${clip(first, 60)}”` : ''}` };
  }

  // -----------------------------------------------------------------
  // Sources
  // -----------------------------------------------------------------
  function sourceRow(src) {
    const url = safeUrl(src.url);
    const row = el(url ? 'a' : 'div', 'work-source');
    if (url) {
      row.href = url;
      row.target = '_blank';
      row.rel = 'noopener noreferrer';
    }
    row.appendChild(el('span', 'work-source-badge', String(src.n)));
    const text = el('span', 'work-source-text');
    text.appendChild(el('span', 'work-source-title', clip(src.title || src.url, 120)));
    text.appendChild(el('span', 'work-source-domain', hostOf(src.url)));
    row.appendChild(text);
    return row;
  }

  function sourceList(sources, className) {
    const list = el('div', className || 'work-sources');
    sources.forEach((s) => list.appendChild(sourceRow(s)));
    return list;
  }

  // Under a search: the first few results, and a toggle for the rest.
  const SOURCES_SHOWN = 5;
  function foldedSourceList(sources) {
    const list = sourceList(sources);
    const rows = [...list.children];
    const extra = rows.slice(SOURCES_SHOWN);
    if (!extra.length) return list;
    extra.forEach((r) => { r.hidden = true; });
    const toggle = el('button', 'work-sources-more', `Show ${extra.length} more`);
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      extra.forEach((r) => { r.hidden = !open; });
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.textContent = open ? 'Show fewer' : `Show ${extra.length} more`;
    });
    list.appendChild(toggle);
    return list;
  }

  function sourcesOf(steps) {
    const byNumber = new Map();
    (steps || []).forEach((step) => (step.calls || []).forEach((call) => (call.sources || []).forEach((s) => {
      if (s && Number.isInteger(s.n) && safeUrl(s.url) && !byNumber.has(s.n)) byNumber.set(s.n, s);
    })));
    return [...byNumber.values()].sort((a, b) => a.n - b.n);
  }

  // The "Sources" chip under an answer; opens to the full list.
  function renderSourcesRow(sources) {
    const list = (sources || []).filter((s) => safeUrl(s.url));
    if (!list.length) return null;
    const box = el('div', 'sources-row');
    const toggle = el('button', 'sources-toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    const badges = el('span', 'sources-badges');
    list.slice(0, 3).forEach((s) => badges.appendChild(el('span', 'sources-badge', String(s.n))));
    toggle.appendChild(badges);
    toggle.appendChild(el('span', 'sources-label', `${list.length} ${list.length === 1 ? 'source' : 'sources'}`));
    toggle.appendChild(icon('chevron', 12));
    const panel = sourceList(list, 'sources-panel');
    panel.hidden = true;
    toggle.addEventListener('click', () => {
      const open = panel.hidden;
      panel.hidden = !open;
      box.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    box.appendChild(toggle);
    box.appendChild(panel);
    return box;
  }

  // -----------------------------------------------------------------
  // The work group
  // -----------------------------------------------------------------
  function summaryLabel(steps, totalMs) {
    const calls = steps.flatMap((s) => s.calls || []);
    const kinds = new Set(calls.map((c) => (TOOL_UI[c.name] || {}).kind || 'other'));
    let label;
    if (!calls.length) {
      const secs = Number.isFinite(totalMs) ? Math.max(1, Math.round(totalMs / 1000)) : null;
      return secs === null ? 'Thought' : `Thought for ${formatDuration(secs * 1000)}`;
    }
    if (kinds.has('search') && kinds.has('read')) label = 'Searched and read pages';
    else if (kinds.has('search')) label = 'Searched the web';
    else if (kinds.has('read')) label = calls.length === 1 ? 'Read a page' : 'Read pages';
    else label = 'Used tools';
    const parts = [label, `${calls.length} ${calls.length === 1 ? 'step' : 'steps'}`];
    const time = formatDuration(totalMs);
    if (time) parts.push(time);
    return parts.join(' · ');
  }

  function createGroup() {
    const steps = [];                 // serializable, same shape the gateway stores
    const stepEls = [];               // {li, thought, thoughtText, calls}
    const sources = new Map();        // n -> source
    const rows = new Map();           // call id -> row element
    let current = null;
    let lastStep = null;              // the newest step, whose duration is fixed when the next begins
    let finished = false;
    let userToggled = false;
    let totalMs = null;

    const root = el('div', 'work-group is-streaming');
    root.setAttribute('role', 'group');
    root.setAttribute('aria-label', 'How the answer was worked out');

    const toggle = el('button', 'work-toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    const label = el('span', 'work-label', 'Thinking');
    label.setAttribute('aria-live', 'polite');
    toggle.appendChild(label);
    const chevron = icon('chevron', 14);
    chevron.classList.add('work-chevron');
    toggle.appendChild(chevron);

    const body = el('div', 'work-body');
    const inner = el('div', 'work-body-inner');
    const timeline = el('ol', 'work-timeline');
    inner.appendChild(timeline);
    body.appendChild(inner);
    root.appendChild(toggle);
    root.appendChild(body);

    function setOpen(open) {
      root.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    setOpen(true);
    toggle.addEventListener('click', () => {
      userToggled = true;
      setOpen(!root.classList.contains('is-open'));
    });

    const startedAt = performance.now();

    // The live line in the header; only while the group is still working.
    function setStatus(text) {
      if (!finished && root.classList.contains('is-streaming')) label.textContent = text;
    }

    // Work resumes after an answer had already started (the model wrote a sentence, then called a tool).
    function resumeWork() {
      if (finished) return;
      root.classList.add('is-streaming');
      if (!userToggled) setOpen(true);
    }

    function ensureStep(n) {
      if (current && (n === undefined || current.record.step === n)) return current;
      const record = { step: n === undefined ? steps.length + 1 : n, reasoning: '', calls: [] };
      const li = el('li', 'work-step');
      li.hidden = true;
      const now = performance.now();
      if (lastStep && lastStep.record.ms === undefined) lastStep.record.ms = Math.round(now - lastStep.startedAt);
      const parts = { record, li, startedAt: now, thought: null, thoughtText: null, callsBox: el('div', 'work-calls') };
      lastStep = parts;
      li.appendChild(parts.callsBox);
      timeline.appendChild(li);
      steps.push(record);
      stepEls.push(parts);
      current = parts;
      return parts;
    }

    function showThought(parts) {
      if (!parts.thought) {
        const box = el('div', 'work-thought');
        const button = el('button', 'work-thought-toggle');
        button.type = 'button';
        button.setAttribute('aria-expanded', 'false');
        button.appendChild(icon('brain', 14));
        button.appendChild(el('span', 'work-thought-label', 'Thinking'));
        button.appendChild(icon('chevron', 12));
        const text = el('div', 'work-thought-text');
        text.hidden = true;
        button.addEventListener('click', () => {
          const open = text.hidden;
          text.hidden = !open;
          box.classList.toggle('is-open', open);
          button.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
        box.appendChild(button);
        box.appendChild(text);
        parts.li.insertBefore(box, parts.callsBox);
        parts.thought = box;
        parts.thoughtText = text;
      }
      parts.li.hidden = false;
      parts.thoughtText.textContent = parts.record.reasoning;
    }

    function callRow(call, running) {
      const row = el('li', 'work-call');
      row.classList.toggle('is-running', running);
      const head = el('div', 'work-call-head');
      const status = el('span', 'work-call-status');
      const text = el('span', 'work-call-text');
      const meta = el('span', 'work-call-meta');
      head.appendChild(status);
      head.appendChild(text);
      head.appendChild(meta);
      row.appendChild(head);
      fillRow(row, call, running);
      return row;
    }

    function fillRow(row, call, running) {
      const d = describeCall(call, running);
      const head = row.firstChild;
      const [status, text, meta] = head.children;
      row.classList.toggle('is-running', running);
      row.classList.toggle('is-failed', call.ok === false);
      status.replaceChildren(running ? el('span', 'work-spinner') : icon(call.ok === false ? 'x' : d.icon, 14));
      status.dataset.state = running ? 'running' : call.ok === false ? 'failed' : 'done';
      text.textContent = d.text;
      const chips = [];
      if (!running && call.ok !== false) {
        if (call.summary) chips.push(call.summary);
        if (call.backend) chips.push(call.backend);
        const time = formatDuration(call.ms);
        if (time) chips.push(time);
      }
      meta.textContent = chips.join(' · ');
      row.querySelectorAll(':scope > .work-error, :scope > .work-fix, :scope > .work-sources').forEach((n) => n.remove());
      if (call.ok === false && call.error) row.appendChild(el('div', 'work-error', clip(call.error, 300)));
      if (call.ok === false && call.name === 'web_search' && call.error && call.error !== STOPPED_MESSAGE) {
        const fix = el('button', 'work-fix', searchKeySaved ? 'Check search settings' : 'Add a search key');
        fix.type = 'button';
        // app.js opens the Parameters panel; this file only draws.
        fix.addEventListener('click', (e) => {
          e.stopPropagation(); // the dashboard closes the panel on any outside click
          document.dispatchEvent(new global.CustomEvent('eclipse:open-search-settings'));
        });
        row.appendChild(fix);
      }
      const listed = (call.sources || []).filter((s) => safeUrl(s.url));
      if (!running && call.ok !== false && call.name === 'web_search' && listed.length) {
        row.appendChild(foldedSourceList(listed.slice(0, 8)));
      }
    }

    function remember(list) {
      (list || []).forEach((s) => {
        if (s && Number.isInteger(s.n) && safeUrl(s.url) && !sources.has(s.n)) sources.set(s.n, s);
      });
    }

    function handleEvent(ev) {
      if (!ev || finished) return;
      switch (ev.type) {
        case 'step_start':
          current = null;
          ensureStep(Number.isInteger(ev.step) ? ev.step : undefined);
          setStatus('Thinking');
          break;
        case 'tool_start': {
          resumeWork();
          const parts = ensureStep();
          const call = {
            id: String(ev.id), name: String(ev.name || 'tool'), arguments: ev.arguments && typeof ev.arguments === 'object' ? ev.arguments : {},
            ok: null, summary: '', sources: [], backend: '', ms: 0, error: '',
          };
          parts.record.calls.push(call);
          const row = callRow(call, true);
          rows.set(call.id, row);
          parts.callsBox.appendChild(row);
          parts.li.hidden = false;
          setStatus(describeCall(call, true).text);
          break;
        }
        case 'tool_result': {
          const parts = ensureStep();
          const call = parts.record.calls.find((c) => c.id === String(ev.id));
          if (!call) break;
          Object.assign(call, {
            ok: !!ev.ok,
            summary: typeof ev.summary === 'string' ? ev.summary : '',
            backend: typeof ev.backend === 'string' ? ev.backend : '',
            ms: Number.isFinite(ev.ms) ? ev.ms : 0,
            error: typeof ev.error === 'string' ? ev.error : '',
            sources: Array.isArray(ev.sources) ? ev.sources.filter((s) => s && Number.isInteger(s.n)) : [],
          });
          remember(call.sources);
          const row = rows.get(call.id);
          if (row) fillRow(row, call, false);
          setStatus('Thinking');
          break;
        }
        case 'step_limit':
          handleLimit(ensureStep());
          break;
        default:
      }
    }

    function addReasoning(text) {
      if (!text || finished) return;
      const parts = ensureStep();
      parts.record.reasoning += text;
      showThought(parts);
      if (!(parts.record.calls.some((c) => c.ok === null))) setStatus('Thinking');
    }

    function completedCalls() {
      return steps.reduce((n, s) => n + s.calls.filter((c) => c.ok !== null).length, 0);
    }

    function hasCalls() {
      return steps.some((s) => s.calls.length > 0);
    }

    function hasContent() {
      return hasCalls() || steps.some((s) => s.reasoning.trim());
    }

    function fold() {
      if (!userToggled) setOpen(false);
    }

    // The answer is being written after at least one tool ran: the work is done, fold it.
    function noteAnswerStarted() {
      if (completedCalls() > 0) {
        root.classList.remove('is-streaming');
        if (!finished) label.textContent = summaryLabel(steps, performance.now() - startedAt);
        fold();
      }
    }

    function markError(message) {
      const parts = ensureStep();
      parts.record.error = clip(message, 500);
      const note = el('li', 'work-note is-error');
      note.appendChild(icon('x', 14));
      note.appendChild(el('span', '', `Stopped: ${clip(message, 300)}`));
      parts.callsBox.appendChild(note);
      parts.li.hidden = false;
    }

    // The reply is over. Returns false when there is nothing worth showing (no tool ran and the
    // model did not think), in which case the group removes itself.
    function finish(elapsedMs) {
      finished = true;
      totalMs = elapsedMs;
      if (lastStep && lastStep.record.ms === undefined) lastStep.record.ms = Math.round(performance.now() - lastStep.startedAt);
      // A call that never got its result (stopped, or the connection dropped) is shown as stopped.
      steps.forEach((s) => s.calls.forEach((c) => {
        if (c.ok === null) {
          c.ok = false;
          c.error = c.error || STOPPED_MESSAGE;
          const row = rows.get(c.id);
          if (row) fillRow(row, c, false);
        }
      }));
      if (!hasContent()) {
        root.remove();
        return false;
      }
      root.classList.remove('is-streaming');
      label.textContent = summaryLabel(steps, totalMs);
      fold();
      return true;
    }

    // Rebuild from saved steps (no streaming).
    function load(saved) {
      (saved || []).forEach((s) => {
        current = null;
        const parts = ensureStep(Number.isInteger(s.step) ? s.step : undefined);
        if (s.reasoning) {
          parts.record.reasoning = String(s.reasoning);
          showThought(parts);
        }
        (s.calls || []).forEach((c) => {
          const call = {
            id: String(c.id || ''), name: String(c.name || 'tool'), arguments: c.arguments && typeof c.arguments === 'object' ? c.arguments : {},
            ok: c.ok === null || c.ok === undefined ? true : !!c.ok, summary: String(c.summary || ''), backend: String(c.backend || ''),
            ms: Number.isFinite(c.ms) ? c.ms : 0, error: String(c.error || ''),
            sources: Array.isArray(c.sources) ? c.sources.filter((x) => x && Number.isInteger(x.n)) : [],
          };
          parts.record.calls.push(call);
          const row = callRow(call, false);
          rows.set(call.id + ':' + parts.record.step, row);
          parts.callsBox.appendChild(row);
          parts.li.hidden = false;
          remember(call.sources);
        });
        if (s.limit) handleLimit(parts);
        if (s.error) {
          parts.record.error = String(s.error);
          const note = el('li', 'work-note is-error');
          note.appendChild(icon('x', 14));
          note.appendChild(el('span', '', `Stopped: ${clip(s.error, 300)}`));
          parts.callsBox.appendChild(note);
          parts.li.hidden = false;
        }
        if (Number.isFinite(s.ms)) parts.record.ms = s.ms;
      });
      finished = true;
      root.classList.remove('is-streaming');
      const total = steps.reduce((t, s) => t + (Number.isFinite(s.ms) ? s.ms : 0), 0);
      label.textContent = summaryLabel(steps, total || null);
      setOpen(false);
    }

    function handleLimit(parts) {
      parts.record.limit = true;
      const note = el('li', 'work-note');
      note.appendChild(icon('stop', 14));
      note.appendChild(el('span', '', 'Step limit reached. Answering with what was found.'));
      parts.callsBox.appendChild(note);
      parts.li.hidden = false;
    }

    return {
      root,
      handleEvent,
      addReasoning,
      noteAnswerStarted,
      markError,
      finish,
      load,
      hasCalls,
      hasContent,
      completedCalls,
      sources: () => [...sources.values()].sort((a, b) => a.n - b.n),
      toSteps: () => steps.map((s) => {
        const out = { step: s.step, reasoning: s.reasoning, calls: s.calls.map((c) => ({ ...c })) };
        if (Number.isFinite(s.ms)) out.ms = s.ms;
        if (s.limit) out.limit = true;
        if (s.error) out.error = s.error;
        return out;
      }),
    };
  }

  // A finished group for a saved chat, folded.
  function renderSaved(steps) {
    const group = createGroup();
    group.load(steps);
    return group;
  }

  // -----------------------------------------------------------------
  // Citation hover card
  // -----------------------------------------------------------------
  let card = null;
  let cardFor = null;

  function hideCard() {
    if (card) card.classList.remove('is-visible');
    cardFor = null;
  }

  function showCard(pill) {
    if (cardFor === pill) return;
    if (!card) {
      card = el('div', 'cite-card');
      card.setAttribute('role', 'tooltip');
      document.body.appendChild(card);
    }
    card.replaceChildren(
      el('div', 'cite-card-title', clip(pill.dataset.title || pill.href, 140)),
      el('div', 'cite-card-domain', pill.dataset.domain || ''),
      ...(pill.dataset.snippet ? [el('div', 'cite-card-snippet', clip(pill.dataset.snippet, 220))] : []),
    );
    card.classList.add('is-visible');
    const rect = pill.getBoundingClientRect();
    const width = card.offsetWidth;
    const left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.left + rect.width / 2 - width / 2));
    const above = rect.top - card.offsetHeight - 8 >= 8;
    card.style.left = `${left}px`;
    card.style.top = `${above ? rect.top - card.offsetHeight - 8 : rect.bottom + 8}px`;
    cardFor = pill;
  }

  function initCitationCards() {
    const pillOf = (e) => (e.target instanceof Element ? e.target.closest('a.cite-pill') : null);
    document.addEventListener('mouseover', (e) => {
      const pill = pillOf(e);
      if (pill) showCard(pill);
    });
    document.addEventListener('mouseout', (e) => {
      if (pillOf(e)) hideCard();
    });
    document.addEventListener('focusin', (e) => {
      const pill = pillOf(e);
      if (pill) showCard(pill);
    });
    document.addEventListener('focusout', (e) => {
      if (pillOf(e)) hideCard();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hideCard();
    });
    window.addEventListener('scroll', hideCard, true);
  }

  global.EclipseToolSteps = {
    createGroup,
    renderSaved,
    setSearchKeySaved,
    renderSourcesRow,
    sourcesOf,
    summaryLabel,
    describeCall,
    formatDuration,
    initCitationCards,
    TOOL_NAMES: ['web_search', 'fetch_url'],
  };
})(window);
