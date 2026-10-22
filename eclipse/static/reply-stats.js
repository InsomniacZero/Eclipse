// ===================================================================
// Reply time and token info shown at the end of an assistant reply's action bar
// ===================================================================
// Pure functions. Time is what the dashboard measured (request start to the end of the reply, so it
// includes thinking and tool work). No provider reports token counts while streaming, so tokens are an
// estimate: about four characters per token, with CJK characters counted one each.
(function (global) {
  'use strict';

  // Hiragana, Katakana, CJK ideographs (and extension A), Hangul syllables, full-width forms.
  const CJK = /[぀-ヿ㐀-䶿一-鿿가-힯＀-￯]/g;

  function estimateTokens(text) {
    const s = typeof text === 'string' ? text : '';
    if (!s) return 0;
    const cjk = (s.match(CJK) || []).length;
    const other = s.length - cjk;
    return Math.max(1, cjk + Math.ceil(other / 4));
  }

  function formatElapsed(ms) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return '';
    const tenths = Math.round(ms / 100) / 10;
    if (tenths < 0.1) return '<0.1s';
    if (tenths < 10) return `${tenths.toFixed(1)}s`;
    const secs = Math.round(ms / 1000);
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  }

  function formatTokens(n) {
    if (!Number.isFinite(n) || n <= 0) return '';
    if (n < 1000) return `~${n} token${n === 1 ? '' : 's'}`;
    const k = n / 1000;
    return `~${k < 10 ? String(Math.round(k * 10) / 10) : String(Math.round(k))}k tokens`;
  }

  // The two parts of the visible line; either is '' when it is not known.
  function line({ elapsedMs, content } = {}) {
    return { time: formatElapsed(elapsedMs), tokens: formatTokens(estimateTokens(content)) };
  }

  // The tooltip on the date.
  function detail({ date, model, elapsedMs, thoughtMs, content, reasoning } = {}) {
    const head = [date, model].filter(Boolean).join(' • ');
    const parts = [];
    const total = formatElapsed(elapsedMs);
    if (total) {
      const thought = formatElapsed(thoughtMs);
      parts.push(`${total} total${thought ? `, thought ${thought}` : ''}`);
    }
    const reply = estimateTokens(content);
    if (reply) parts.push(`${formatTokens(reply)} in the reply`);
    const thinking = estimateTokens(reasoning);
    if (thinking) parts.push(`${formatTokens(thinking)} of thinking`);
    if (reply || thinking) parts.push('Tokens are estimated: about 4 characters each.');
    return parts.length ? `${head}\n${parts.join('\n')}` : head;
  }

  global.EclipseReplyStats = { estimateTokens, formatElapsed, formatTokens, line, detail };
})(window);
