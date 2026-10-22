// ===================================================================
// Chat titles: the quick local title and cleaning of a model-written one
// ===================================================================
// Pure functions. app.js gives a new chat localTitle() at once and, after the first reply, asks the
// model for a better one; cleanGenerated() decides whether the model's answer is usable.
(function (global) {
  'use strict';

  const MAX_TITLE = 60;
  const MAX_WORDS = 12;

  // Words that open a request but say nothing about its topic.
  const OPENERS = [
    /^(?:hey|hi|hello|yo|hiya|good (?:morning|afternoon|evening))\b[\s,!.:;-]*/i,
    /^(?:can|could|would|will) you(?: please)?\b[\s,:;-]*/i,
    /^(?:please|pls)\b[\s,:;-]*/i,
    /^(?:i(?:'d| would)? (?:need|want|like) you to)\b[\s,:;-]*/i,
    /^help me to\b[\s,:;-]*/i,
  ];

  function plain(text) {
    return String(text == null ? '' : text)
      .replace(/<attachment[\s\S]*?<\/attachment>/gi, ' ')
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/[*_`#>~]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function cutAtWord(text, max) {
    if (text.length <= max) return text;
    const head = text.slice(0, max);
    const space = head.lastIndexOf(' ');
    return `${(space > max / 2 ? head.slice(0, space) : head).replace(/[\s,;:-]+$/, '')}…`;
  }

  // The first sentence of the first message, without greetings or "can you please".
  function localTitle(text) {
    let t = plain(text);
    for (let i = 0; i < 3; i++) {
      let changed = false;
      for (const opener of OPENERS) {
        const next = t.replace(opener, '');
        if (next !== t) {
          t = next;
          changed = true;
        }
      }
      if (!changed) break;
    }
    const sentence = t.split(/(?<=[.!?])\s+/)[0] || '';
    t = sentence.replace(/[.!?:;,\s]+$/, '').trim();
    if (!t) return 'New chat';
    t = t.charAt(0).toUpperCase() + t.slice(1);
    return cutAtWord(t, MAX_TITLE);
  }

  const REFUSAL = /^(?:i['’]?m\b|i am\b|i can(?:['’]?t|not)\b|i['’]ll\b|i will\b|sorry\b|apolog|as an ai\b|unable\b|here(?:['’]s| is)\b|sure\b|certainly\b|of course\b)/i;

  // A model's answer to "write a title": usable text, or '' when it should be ignored.
  function cleanGenerated(raw) {
    let t = String(raw == null ? '' : raw)
      .replace(/<(antThinking|think|thinking)>[\s\S]*?<\/\1>/gi, '')
      .replace(/<[^>]+>/g, '');
    const line = t.split(/\r?\n/).map((l) => l.trim()).find(Boolean) || '';
    t = line
      .replace(/^(?:chat title|conversation title|title)\s*[:–-]\s*/i, '')
      .replace(/^[#>*\-\s"'“”‘’`]+/, '')
      .replace(/["“”`*_]+$/, '')
      .replace(/[*_`]/g, '')
      .replace(/[.!?:;,\s]+$/, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t) return '';
    if (t.split(' ').length > MAX_WORDS) return '';
    if (REFUSAL.test(t)) return '';
    return cutAtWord(t, MAX_TITLE);
  }

  // What is sent to the model. The texts are cut so a long chat costs no more than a short one.
  function request(userText, assistantText) {
    const clip = (text) => plain(text).slice(0, 500);
    return (
      'Write a title of at most six words for this conversation. ' +
      'Reply with the title only: no quotes, no markdown, no final period.\n\n' +
      `User: ${clip(userText)}\n\nAssistant: ${clip(assistantText)}`
    );
  }

  global.EclipseTitles = { localTitle, cleanGenerated, request, plain };
})(window);
