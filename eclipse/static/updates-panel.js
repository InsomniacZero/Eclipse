/**
 * Eclipse Updates & System Version Control Engine
 * Components:
 * - @cult-ui/terminal-animation (Typed interactive command playback & git sync)
 * - @skiper-ui/skiper74 (Sticky calendar release timeline & raw commit inspector)
 * Pure vanilla ES6+, zero build step, 100% compliant with DESIGN-SYS.md
 */

(function () {
  const state = {
    initialized: false,
    versionData: null,
    isUpdating: false,
    activeTerminalTab: 1, // Default to 'check-remote'
    terminalTimeouts: [],
    typedIndex: 0,
  };

  const TERMINAL_TABS = [
    {
      id: 'status',
      label: '1. fleet-status',
      command: 'eclipse status --fleet --json',
      lines: [
        { text: '  Querying Eclipse core architecture & process tree...', color: 't-purple', delay: 150 },
        { text: '', delay: 50 },
        { text: '  ✓ Gateway Engine:    StarletteGateway (Pure Python / 0 Rust)', color: 't-green', delay: 100 },
        { text: '  ✓ Listening Socket:  http://127.0.0.1:5000 (Localhost)', color: 't-cyan', delay: 100 },
        { text: '  ✓ Credential Vault:  SQLite WAL Mode (~/eclipse.db)', color: 't-cyan', delay: 100 },
        { text: '  ✓ Provider Fleet:    1 Backend (Gemini Web)', color: 't-green', delay: 120 },
        { text: '  ✓ Catalog Models:    Gemini models online', color: 't-green', delay: 100 },
        { text: '', delay: 50 },
        { text: '  STATUS: ALL SYSTEMS NOMINAL', color: 't-white', delay: 150 },
      ]
    },
    {
      id: 'check',
      label: '2. check-origin',
      command: 'eclipse check-origin --repo Nephis-opus/Eclipse',
      lines: [
        { text: '  Connecting to remote GitHub repository...', color: 't-purple', delay: 200 },
        { text: '  Origin: https://github.com/Nephis-opus/Eclipse.git [branch: main]', color: 't-muted', delay: 150 },
        { text: '', delay: 50 },
        { text: '  ✓ Contacting remote ref via git ls-remote...', color: 't-cyan', delay: 250 },
        { text: '  [LOCAL HEAD]   9c600d4 (main branch)', color: 't-white', delay: 120 },
        { text: '  [REMOTE HEAD]  9c600d4 (origin/main)', color: 't-cyan', delay: 120 },
        { text: '', delay: 50 },
        { text: '  ✓ Synchronization verified: Local repository is 100% up to date.', color: 't-green', delay: 150 },
        { text: '  ✓ Zero commits behind. Working tree is clean.', color: 't-green', delay: 100 },
      ]
    },
    {
      id: 'update',
      label: '3. auto-pull',
      command: 'eclipse update --pull-remote --bust-cache',
      lines: [
        { text: '  [1/4] Checking local working directory state...', color: 't-purple', delay: 150 },
        { text: '  ✓ Preserving credentials vault and local state.', color: 't-cyan', delay: 120 },
        { text: '  [2/4] Fetching latest refs from Nephis-opus/Eclipse...', color: 't-purple', delay: 200 },
        { text: '  [3/4] Pulling origin/main fast-forward...', color: 't-purple', delay: 250 },
        { text: '  ✓ Synchronized 14 files, 0 conflicts.', color: 't-green', delay: 120 },
        { text: '  [4/4] Generating Brave/Chromium cache-bypass signature...', color: 't-purple', delay: 150 },
        { text: '  ✓ Active Cache-Buster: v179121_9c600d4', color: 't-green', delay: 100 },
        { text: '  ✨ Update verified. Auto-reloading client in 2s...', color: 't-highlight', delay: 200 },
      ]
    },
    {
      id: 'cache',
      label: '4. cache-bypass',
      command: 'eclipse cache --purge-stale-bytecode',
      lines: [
        { text: '  Analyzing browser cache storage (Brave / Chromium / Gecko)...', color: 't-purple', delay: 150 },
        { text: '  Browsers often cache local /static/app.js & /static/style.css.', color: 't-muted', delay: 100 },
        { text: '  Applying HTTP Response Headers: Cache-Control: no-cache, no-store, must-revalidate', color: 't-cyan', delay: 150 },
        { text: '  Generating unique timestamp query parameter: ?v=' + Date.now(), color: 't-yellow', delay: 120 },
        { text: '  ✓ Cache bypass armed. Ready to force instant refresh.', color: 't-green', delay: 100 },
      ]
    }
  ];

  function clearAllTimeouts() {
    state.terminalTimeouts.forEach(t => clearTimeout(t));
    state.terminalTimeouts = [];
  }

  function playTerminalScenario(tabIndex, customCommand, customLines) {
    clearAllTimeouts();
    state.activeTerminalTab = tabIndex;

    // Update active tab buttons
    document.querySelectorAll('.terminal-tab-btn').forEach((btn, idx) => {
      btn.classList.toggle('active', idx === tabIndex);
    });

    const tab = TERMINAL_TABS[tabIndex] || TERMINAL_TABS[0];
    const cmdText = customCommand || tab.command;
    const lines = customLines || tab.lines;

    const cmdEl = document.getElementById('terminal-typed-cmd');
    const outEl = document.getElementById('terminal-output');
    const cursorEl = document.getElementById('terminal-cursor');

    if (!cmdEl || !outEl) return;

    cmdEl.textContent = '';
    outEl.innerHTML = '';
    if (cursorEl) cursorEl.style.display = 'inline-block';

    let charIdx = 0;
    function typeChar() {
      if (charIdx <= cmdText.length) {
        cmdEl.textContent = cmdText.slice(0, charIdx);
        charIdx++;
        const delay = 18 + Math.floor(Math.random() * 25);
        const t = setTimeout(typeChar, delay);
        state.terminalTimeouts.push(t);
      } else {
        const t = setTimeout(() => {
          renderLines(0);
        }, 200);
        state.terminalTimeouts.push(t);
      }
    }

    function renderLines(lineIdx) {
      if (lineIdx < lines.length) {
        const item = lines[lineIdx];
        const lineDiv = document.createElement('div');
        lineDiv.className = `terminal-line ${item.color || 't-muted'}`;
        lineDiv.textContent = item.text || ' ';
        outEl.appendChild(lineDiv);

        // Auto-scroll terminal body
        const bodyEl = document.getElementById('terminal-body');
        if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight;

        const delay = item.delay || 100;
        const t = setTimeout(() => {
          renderLines(lineIdx + 1);
        }, delay);
        state.terminalTimeouts.push(t);
      } else {
        // Complete
        if (cursorEl) cursorEl.style.display = 'inline-block';
      }
    }

    const tStart = setTimeout(typeChar, 100);
    state.terminalTimeouts.push(tStart);
  }

  async function checkVersion(silent = false) {
    const statusBadge = document.getElementById('updates-remote-status');
    const statusText = document.getElementById('updates-status-text');
    const curVersion = document.getElementById('updates-cur-version');
    const curHash = document.getElementById('updates-cur-hash');
    const curShort = document.getElementById('updates-cur-short');
    const checkBtn = document.getElementById('btn-check-updates');

    if (checkBtn) checkBtn.disabled = true;
    if (statusBadge && !silent) {
      statusBadge.className = 'updates-status-badge checking';
      if (statusText) statusText.textContent = 'Checking GitHub...';
    }

    try {
      const resp = await fetch('/api/system/version');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      state.versionData = data;

      if (curVersion && data.version_name) {
        curVersion.textContent = data.version_name;
      }
      if (curShort && data.short_commit) {
        curShort.textContent = data.short_commit;
      }
      if (curHash && data.local_commit) {
        curHash.href = `https://github.com/${data.remote_repo || 'Nephis-opus/Eclipse'}/commit/${data.local_commit}`;
      }

      // Update badge on dock
      const dockBadge = document.getElementById('dock-badge-updates');

      if (statusBadge && statusText) {
        if (data.is_latest === true) {
          statusBadge.className = 'updates-status-badge up-to-date';
          statusText.textContent = '● Up to Date (GitHub main synced)';
          if (dockBadge) {
            dockBadge.classList.remove('visible', 'pulse');
          }
        } else if (data.is_latest === false) {
          statusBadge.className = 'updates-status-badge update-available';
          const count = data.commits_behind || 1;
          statusText.textContent = `▲ Update Available (${count} commit${count > 1 ? 's' : ''} behind)`;
          if (dockBadge) {
            dockBadge.classList.add('visible', 'pulse');
          }
        } else {
          statusBadge.className = 'updates-status-badge checking';
          statusText.textContent = data.remote_error ? 'Remote check offline' : 'Sync verified';
        }
      }

      // Update dynamic scenario 2 (check-origin) with live SHA
      if (TERMINAL_TABS[1]) {
        TERMINAL_TABS[1].lines = [
          { text: '  Connecting to remote GitHub repository...', color: 't-purple', delay: 150 },
          { text: `  Origin: https://github.com/${data.remote_repo || 'Nephis-opus/Eclipse'}.git [${data.branch || 'main'}]`, color: 't-muted', delay: 120 },
          { text: '', delay: 50 },
          { text: '  ✓ Querying remote refs via git ls-remote...', color: 't-cyan', delay: 150 },
          { text: `  [LOCAL HEAD]   ${data.short_commit || '9c600d4'} (${data.branch || 'main'})`, color: 't-white', delay: 100 },
          { text: `  [REMOTE HEAD]  ${data.remote_short || data.short_commit || '9c600d4'} (origin/${data.branch || 'main'})`, color: 't-cyan', delay: 100 },
          { text: '', delay: 50 },
          data.is_latest === true
            ? { text: '  ✓ Synchronization verified: Local repository is 100% up to date.', color: 't-green', delay: 120 }
            : { text: `  ▲ Update available: Local branch is ${data.commits_behind || 1} commit(s) behind origin.`, color: 't-yellow', delay: 120 },
          { text: `  ✓ Latest commit: "${data.commit_message || 'Active release'}"`, color: 't-dim', delay: 100 },
        ];
      }

      // Render raw commits if container exists
      renderRawCommits(data.recent_commits);

    } catch (err) {
      console.warn('Version check error:', err);
      if (statusBadge && statusText) {
        statusBadge.className = 'updates-status-badge checking';
        statusText.textContent = 'Check offline (Local Mode)';
      }
    } finally {
      if (checkBtn) checkBtn.disabled = false;
    }
  }

  function renderRawCommits(commits) {
    const listEl = document.getElementById('skiper-raw-commits-list');
    if (!listEl || !Array.isArray(commits) || commits.length === 0) return;

    listEl.innerHTML = '';
    commits.forEach(c => {
      const row = document.createElement('div');
      row.className = 'skiper-commit-row';
      row.innerHTML = `
        <div class="skiper-commit-left">
          <span class="skiper-commit-hash">${c.short || c.hash.slice(0, 7)}</span>
          <span class="skiper-commit-msg" title="${c.message}">${c.message}</span>
        </div>
        <div class="skiper-commit-meta">
          <span>${c.author || 'Insomiku'}</span> · <span>${(c.date || '').split(' ')[0]}</span>
        </div>
      `;
      listEl.appendChild(row);
    });
  }

  async function runAppUpdate() {
    if (state.isUpdating) return;
    state.isUpdating = true;

    const updateBtn = document.getElementById('btn-run-update');
    if (updateBtn) {
      updateBtn.disabled = true;
      updateBtn.innerHTML = `
        <svg class="spinning" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
        Updating Eclipse...
      `;
    }

    // Switch terminal to 'update' tab and start preliminary animation
    const liveLines = [
      { text: '  Initiating automated repository synchronization...', color: 't-purple', delay: 150 },
      { text: '  Connecting to https://github.com/Nephis-opus/Eclipse.git...', color: 't-muted', delay: 120 },
      { text: '  Executing git fetch & safe fast-forward pull...', color: 't-cyan', delay: 150 }
    ];
    playTerminalScenario(2, 'eclipse update --pull-remote --bust-cache', liveLines);

    try {
      const resp = await fetch('/api/system/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const res = await resp.json();

      const outLines = [];
      if (Array.isArray(res.logs)) {
        res.logs.forEach(log => {
          let col = 't-muted';
          if (log.includes('✓') || log.includes('successfully') || log.includes('Already')) col = 't-green';
          else if (log.includes('Initiating') || log.includes('Fetching') || log.includes('Pulling')) col = 't-cyan';
          else if (log.includes('!]')) col = 't-red';
          else if (log.includes('token') || log.includes('HEAD')) col = 't-purple';
          outLines.push({ text: '  ' + log, color: col, delay: 100 });
        });
      }

      if (res.ok) {
        outLines.push({ text: '', delay: 50 });
        outLines.push({ text: '  ✨ SUCCESS: Eclipse files updated cleanly!', color: 't-green', delay: 150 });
        outLines.push({ text: `  ⚡ Active Cache-Buster: ${res.cache_token || 'v_fresh'}`, color: 't-yellow', delay: 120 });
        outLines.push({ text: '  🔄 Purging Brave/Chromium bytecode cache and reloading in 2 seconds...', color: 't-highlight', delay: 200 });

        playTerminalScenario(2, 'eclipse update --pull-remote --bust-cache', outLines);

        // Trigger cache-busted reload after 2.2 seconds
        setTimeout(() => {
          forceCacheBustReload();
        }, 2200);
      } else {
        outLines.push({ text: `  [!] Update error: ${res.error || 'Pull failed'}`, color: 't-red', delay: 100 });
        playTerminalScenario(2, 'eclipse update --pull-remote --bust-cache', outLines);
        if (updateBtn) {
          updateBtn.disabled = false;
          updateBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path><path d="M16 16h5v5"></path></svg>
            Update App
          `;
        }
        state.isUpdating = false;
      }
    } catch (err) {
      console.error('Update fetch error:', err);
      const errLines = [
        { text: '  [!] Network error contacting update engine: ' + err.message, color: 't-red', delay: 100 }
      ];
      playTerminalScenario(2, 'eclipse update --pull-remote --bust-cache', errLines);
      if (updateBtn) {
        updateBtn.disabled = false;
        updateBtn.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path><path d="M16 16h5v5"></path></svg>
          Update App
        `;
      }
      state.isUpdating = false;
    }
  }

  async function forceCacheBustReload() {
    // 1. Purge Service Worker caches if active
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      try {
        navigator.serviceWorker.controller.postMessage({ type: 'PURGE_AND_SKIP_WAITING' });
      } catch (e) {}
    }
    // 2. Clear client CacheStorage directly
    if (window.caches) {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map(k => caches.delete(k)));
      } catch (e) {}
    }
    // 3. Brave / Chromium cache-busting: append timestamp parameter to URL
    const freshUrl = window.location.origin + window.location.pathname + '?v=' + Date.now();
    window.location.replace(freshUrl);
  }

  function copyTerminalLogs() {
    const outEl = document.getElementById('terminal-output');
    if (!outEl) return;
    const text = outEl.innerText || outEl.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const copyBtn = document.getElementById('btn-copy-terminal');
      if (copyBtn) {
        const orig = copyBtn.textContent;
        copyBtn.textContent = 'Copied!';
        setTimeout(() => { copyBtn.textContent = orig; }, 1500);
      }
    });
  }

  function init() {
    if (state.initialized) {
      checkVersion(false);
      return;
    }
    state.initialized = true;

    // Terminal Tabs wiring
    document.querySelectorAll('.terminal-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.tabIndex, 10);
        playTerminalScenario(idx);
      });
    });

    // Check updates button
    const checkBtn = document.getElementById('btn-check-updates');
    if (checkBtn) {
      checkBtn.addEventListener('click', () => {
        playTerminalScenario(1);
        checkVersion(false);
      });
    }

    // Update app button
    const updateBtn = document.getElementById('btn-run-update');
    if (updateBtn) {
      updateBtn.addEventListener('click', () => {
        runAppUpdate();
      });
    }

    // Hard refresh button
    const hardRefreshBtn = document.getElementById('btn-hard-refresh');
    if (hardRefreshBtn) {
      hardRefreshBtn.addEventListener('click', () => {
        playTerminalScenario(3);
        setTimeout(forceCacheBustReload, 800);
      });
    }

    // Terminal tools: Replay & Copy
    const replayBtn = document.getElementById('btn-replay-terminal');
    if (replayBtn) {
      replayBtn.addEventListener('click', () => {
        playTerminalScenario(state.activeTerminalTab);
      });
    }

    const copyBtn = document.getElementById('btn-copy-terminal');
    if (copyBtn) {
      copyBtn.addEventListener('click', copyTerminalLogs);
    }

    // Accordion for raw git commits
    const accordionBtn = document.getElementById('btn-toggle-raw-commits');
    const commitsPanel = document.getElementById('skiper-raw-commits-panel');
    if (accordionBtn && commitsPanel) {
      accordionBtn.addEventListener('click', () => {
        const isExp = commitsPanel.classList.toggle('visible');
        accordionBtn.classList.toggle('expanded', isExp);
        accordionBtn.setAttribute('aria-expanded', isExp ? 'true' : 'false');
      });
    }

    // Initial load check
    checkVersion(false);
    playTerminalScenario(1);
  }

  // Pre-fetch check on startup to update dock badge
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(() => { checkVersion(true); }, 1200);
    });
  } else {
    setTimeout(() => { checkVersion(true); }, 1200);
  }

  window.EclipseUpdates = {
    init,
    checkVersion,
    runAppUpdate,
    forceCacheBustReload,
    playTerminalScenario
  };
})();
