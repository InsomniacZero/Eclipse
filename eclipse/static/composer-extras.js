// ===================================================================
// Composer extras: slash commands and per-chat drafts
// ===================================================================
// Pure logic. app.js draws the menu, runs the commands and decides when to save or restore a draft.
(function (global) {
  'use strict';

  // The order here is the order of the menu.
  const SLASH_COMMANDS = [
    { name: 'new', description: 'Start a new chat' },
    { name: 'temp', description: 'Temporary chat: not saved (only before the first message)' },
    { name: 'search', description: 'Turn web search on or off' },
    { name: 'model', description: 'Choose the model' },
    { name: 'retry', description: 'Retry the last reply' },
    { name: 'pin', description: 'Pin or unpin this chat' },
    { name: 'archive', description: 'Archive this chat' },
    { name: 'export', description: 'Download this chat as Markdown' },
  ];

  // null: the text is not a command being typed. [] : it is, but nothing matches (Enter then sends it).
  function matchCommands(text) {
    const m = /^\/([a-z]*)$/i.exec(typeof text === 'string' ? text : '');
    if (!m) return null;
    const word = m[1].toLowerCase();
    const starts = SLASH_COMMANDS.filter((c) => c.name.startsWith(word));
    const exact = starts.filter((c) => c.name === word);
    return exact.length ? exact.concat(starts.filter((c) => c.name !== word)) : starts;
  }

  // Drafts live in one storage entry: { chatId: { text, time } }. The newest `max` are kept.
  function createDraftStore(storage, { key = 'eclipse_drafts', max = 50, maxChars = 20000, now = Date.now } = {}) {
    function load() {
      try {
        const raw = storage.getItem(key);
        const parsed = JSON.parse(raw || '{}');
        const clean = {};
        if (parsed && typeof parsed === 'object') {
          Object.keys(parsed).forEach((id) => {
            const d = parsed[id];
            if (d && typeof d.text === 'string' && d.text) clean[id] = { text: d.text, time: Number.isFinite(d.time) ? d.time : 0 };
          });
        }
        return clean;
      } catch (_) {
        return {};
      }
    }

    function save(drafts) {
      try {
        const ids = Object.keys(drafts);
        if (ids.length > max) {
          ids.sort((a, b) => drafts[b].time - drafts[a].time).slice(max).forEach((id) => { delete drafts[id]; });
        }
        if (Object.keys(drafts).length) storage.setItem(key, JSON.stringify(drafts));
        else storage.removeItem(key);
      } catch (_) { /* storage blocked or full: the draft is simply not kept */ }
    }

    return {
      get(id) {
        const d = load()[id];
        return d ? d.text : '';
      },
      set(id, text) {
        const drafts = load();
        if (typeof text !== 'string' || !text.trim()) delete drafts[id];
        else drafts[id] = { text: text.slice(0, maxChars), time: now() };
        save(drafts);
      },
      remove(id) {
        const drafts = load();
        if (id in drafts) {
          delete drafts[id];
          save(drafts);
        }
      },
      count() {
        return Object.keys(load()).length;
      },
    };
  }

  global.EclipseComposer = { SLASH_COMMANDS, matchCommands, createDraftStore };
})(window);
