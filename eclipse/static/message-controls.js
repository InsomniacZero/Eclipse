// ===================================================================
// Message controls: the version switcher and the "Retry with..." model menu
// ===================================================================
// Pure DOM helpers; app.js decides what a click does. Model names and other text go in with
// textContent only.
(function (global) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function icon(points, size = 14) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', String(size));
    svg.setAttribute('height', String(size));
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2.2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    const line = document.createElementNS(SVG_NS, 'polyline');
    line.setAttribute('points', points);
    svg.appendChild(line);
    return svg;
  }

  // ---------------------------------------------------------------
  // Version switcher: < 2 / 3 >
  // ---------------------------------------------------------------
  function buildSwitcher({ index, total, label, onPrev, onNext }) {
    const box = document.createElement('div');
    box.className = 'version-switcher';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Versions of this message');

    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'version-btn version-prev';
    prev.setAttribute('aria-label', 'Previous version');
    prev.disabled = index <= 0;
    prev.appendChild(icon('15 6 9 12 15 18'));
    prev.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!prev.disabled) onPrev();
    });

    const count = document.createElement('span');
    count.className = 'version-count';
    count.setAttribute('aria-live', 'polite');
    count.textContent = `${index + 1} / ${total}`;
    count.title = label || `Version ${index + 1} of ${total}`;

    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'version-btn version-next';
    next.setAttribute('aria-label', 'Next version');
    next.disabled = index >= total - 1;
    next.appendChild(icon('9 6 15 12 9 18'));
    next.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!next.disabled) onNext();
    });

    box.append(prev, count, next);
    return box;
  }

  // ---------------------------------------------------------------
  // "Retry with..." model menu
  // ---------------------------------------------------------------
  let openMenu = null;

  function closeModelMenu() {
    if (!openMenu) return;
    const { root, cleanup, anchor } = openMenu;
    openMenu = null;
    cleanup();
    root.remove();
    anchor.setAttribute('aria-expanded', 'false');
  }

  // models: [{id, name, provider, locked}]. onPick(modelId) runs after the menu closes.
  function openModelMenu({ anchor, models, selectedId, onPick }) {
    closeModelMenu();

    const root = document.createElement('div');
    root.className = 'retry-model-menu';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-label', 'Retry with another model');

    const search = document.createElement('input');
    search.type = 'text';
    search.className = 'retry-model-search';
    search.placeholder = 'Retry with...';
    search.setAttribute('aria-label', 'Search models');
    search.autocomplete = 'off';
    search.spellcheck = false;

    const list = document.createElement('div');
    list.className = 'retry-model-list';
    list.setAttribute('role', 'listbox');

    root.append(search, list);
    document.body.appendChild(root);

    let shown = [];
    let active = 0;

    const setActive = (i) => {
      if (!shown.length) return;
      active = (i + shown.length) % shown.length;
      shown.forEach((row, n) => row.classList.toggle('is-active', n === active));
      shown[active].scrollIntoView?.({ block: 'nearest' });
    };

    const pick = (id) => {
      closeModelMenu();
      onPick(id);
    };

    const render = () => {
      const q = search.value.toLowerCase().trim();
      list.replaceChildren();
      shown = [];
      (models || [])
        .filter((m) => !q || `${m.name} ${m.id} ${m.provider}`.toLowerCase().includes(q))
        .forEach((m) => {
          const row = document.createElement('div');
          row.className = 'retry-model-option';
          row.setAttribute('role', 'option');
          row.dataset.id = m.id;
          if (m.id === selectedId) {
            row.classList.add('is-current');
            row.setAttribute('aria-selected', 'true');
          }
          const name = document.createElement('span');
          name.className = 'retry-model-name';
          name.textContent = m.name || m.id;
          const provider = document.createElement('span');
          provider.className = 'retry-model-provider';
          provider.textContent = m.provider || '';
          row.append(name, provider);
          if (m.locked) {
            const lock = document.createElement('span');
            lock.className = 'retry-model-lock';
            lock.textContent = 'No account';
            row.appendChild(lock);
          }
          row.addEventListener('click', (e) => {
            e.stopPropagation();
            pick(m.id);
          });
          list.appendChild(row);
          shown.push(row);
        });
      if (!shown.length) {
        const empty = document.createElement('div');
        empty.className = 'retry-model-empty';
        empty.textContent = 'No models match.';
        list.appendChild(empty);
      }
      setActive(0);
    };

    search.addEventListener('input', render);
    search.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive(active + 1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive(active - 1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (shown[active]) pick(shown[active].dataset.id);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeModelMenu();
        anchor.focus();
      }
    });

    const onOutside = (e) => {
      if (!root.contains(e.target) && !anchor.contains(e.target)) closeModelMenu();
    };
    const onKey = (e) => {
      if (e.key === 'Escape') {
        closeModelMenu();
        anchor.focus();
      }
    };
    document.addEventListener('mousedown', onOutside, true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', closeModelMenu);

    render();

    // Below the button if it fits, otherwise above; kept inside the window.
    const rect = anchor.getBoundingClientRect();
    const width = root.offsetWidth || 300;
    const height = root.offsetHeight || 320;
    const below = rect.bottom + 6 + height <= window.innerHeight - 8;
    root.style.left = `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.left))}px`;
    root.style.top = `${below ? rect.bottom + 6 : Math.max(8, rect.top - height - 6)}px`;

    anchor.setAttribute('aria-expanded', 'true');
    openMenu = {
      root,
      anchor,
      cleanup: () => {
        document.removeEventListener('mousedown', onOutside, true);
        document.removeEventListener('keydown', onKey);
        window.removeEventListener('resize', closeModelMenu);
      },
    };
    search.focus();
    return closeModelMenu;
  }

  global.EclipseMessageControls = { buildSwitcher, openModelMenu, closeModelMenu };
})(window);
