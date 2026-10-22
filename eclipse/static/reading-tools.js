// ===================================================================
// Reading tools: copy a table as Markdown or CSV, read the TeX of a rendered formula
// ===================================================================
// Pure DOM readers. app.js wires the clicks. Everything here only reads text out of elements
// the dashboard has already sanitized.
(function (global) {
  'use strict';

  function cellText(cell) {
    const copy = cell.cloneNode(true);
    // Only a <br> is a line break; whitespace in the source markup is not.
    copy.querySelectorAll('br').forEach((br) => br.replaceWith('\u0000'));
    return copy.textContent.replace(/\s+/g, ' ').replace(/ ?\u0000 ?/g, '\n').trim();
  }

  function rowsOf(table) {
    if (!table || !table.querySelectorAll) return [];
    return Array.from(table.querySelectorAll('tr')).map((tr) => Array.from(tr.children).filter((c) => /^(TD|TH)$/.test(c.tagName)));
  }

  function tableToMarkdown(table) {
    const rows = rowsOf(table).filter((r) => r.length);
    if (!rows.length) return '';
    const width = Math.max(...rows.map((r) => r.length));
    const text = (cell) => (cell ? cellText(cell).replace(/\|/g, '\\|').replace(/\n/g, '<br>') : '');
    const line = (r) => `| ${Array.from({ length: width }, (_, i) => text(r[i])).join(' | ')} |`;
    const align = Array.from({ length: width }, (_, i) => {
      const a = (rows[0][i] && rows[0][i].getAttribute('align')) || '';
      return a === 'left' ? ':---' : a === 'center' ? ':---:' : a === 'right' ? '---:' : '---';
    });
    return [line(rows[0]), `| ${align.join(' | ')} |`, ...rows.slice(1).map(line)].join('\n');
  }

  // A cell that starts like a spreadsheet formula would run when the CSV is opened. "-5" is a number, "-SUM(" is not.
  function csvCell(value) {
    let v = value;
    if (/^[=+@]/.test(v) || /^-[^0-9.\s]/.test(v)) v = `'${v}`;
    return /[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
  }

  function tableToCsv(table) {
    const rows = rowsOf(table).filter((r) => r.length);
    return rows.map((r) => r.map((c) => csvCell(cellText(c))).join(',')).join('\n');
  }

  // KaTeX keeps the source TeX in a MathML annotation next to the rendered glyphs.
  function texOf(node) {
    const root = node && node.closest ? (node.closest('.katex') || node.querySelector('.katex')) : null;
    const annotation = root && root.querySelector('annotation[encoding="application/x-tex"]');
    return annotation ? annotation.textContent : '';
  }

  global.EclipseReading = { tableToMarkdown, tableToCsv, texOf, cellText };
})(window);
