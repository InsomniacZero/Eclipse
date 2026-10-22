// ===================================================================
// Suggested follow-up questions: the request and cleaning the answer
// ===================================================================
// Pure functions. app.js sends the silent request after a finished reply and shows what clean() keeps.
// The questions are model text: they are only ever put on the page with textContent.
(function (global) {
  'use strict';

  const MAX_QUESTIONS = 3;
  const MIN_CHARS = 8;
  const MAX_CHARS = 80;
  const CLIP = 700;

  function plain(text) {
    return String(text == null ? '' : text)
      .replace(/<antArtifact[\s\S]*?<\/antArtifact>/gi, ' ')
      .replace(/<antThinking>[\s\S]*?<\/antThinking>/gi, ' ')
      .replace(/<attachment[\s\S]*?<\/attachment>/gi, ' ')
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // What is sent to the model. The texts are cut so a long chat costs no more than a short one.
  function request(userText, assistantText) {
    const clip = (t) => plain(t).slice(0, CLIP);
    return (
      'Suggest three short follow-up questions the user might ask next, each under 12 words. ' +
      'Reply with the questions only, one per line, no numbering, no quotes and no introduction.\n\n' +
      `User: ${clip(userText)}\n\nAssistant: ${clip(assistantText)}`
    );
  }

  function clean(raw) {
    if (typeof raw !== 'string') return [];
    const seen = new Set();
    const out = [];
    for (const line of raw.split(/\r?\n/)) {
      const q = line
        .replace(/^\s*(?:[-*•]|\d+[.)])\s+/, '')
        .replace(/[*_`]+/g, '')
        .replace(/^["'“‘]+|["'”’]+$/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      if (!/[?？]$/.test(q) || q.length < MIN_CHARS || q.length > MAX_CHARS) continue;
      const key = q.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(q);
      if (out.length === MAX_QUESTIONS) break;
    }
    return out;
  }

  global.EclipseFollowUps = { request, clean, MAX_QUESTIONS };
})(window);
