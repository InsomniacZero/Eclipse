/**
 * Eclipse Glass Dock Navigation Module
 * Inspired by VengeanceUI @vengeanceui/glass-dock
 * Strictly adheres to DESIGN-SYS.md & MISTAKES.md (Pure vanilla ES6+, zero build step)
 */

(function () {
  let hoveredIndex = null;
  let prevIndex = null;
  let dockTooltip = null;
  let tooltipTextEl = null;

  const NAV_ITEMS = [
    {
      id: 'playground',
      type: 'tab',
      title: 'Playground',
      icon: `<svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`,
    },
    {
      id: 'control',
      type: 'tab',
      title: 'Control Center',
      icon: `<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>`,
    },
    {
      id: 'models',
      type: 'tab',
      title: 'Available Models',
      icon: `<svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
    },
    {
      id: 'cookies',
      type: 'tab',
      title: 'Cookie Stacker',
      icon: `<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`,
    },
    {
      id: 'tunnel',
      type: 'tab',
      title: 'Eclipse-Access',
      icon: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
    },
    {
      id: 'updates',
      type: 'tab',
      title: 'S-Update Logs',
      icon: `<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path><path d="M16 16h5v5"></path></svg>`,
    }
  ];

  function createGlassDock() {
    if (document.getElementById('eclipse-glass-dock')) return;

    const container = document.createElement('div');
    container.className = 'glass-dock-container';
    container.id = 'eclipse-glass-dock';

    const dock = document.createElement('div');
    dock.className = 'glass-dock';

    // Tooltip Element
    dockTooltip = document.createElement('div');
    dockTooltip.className = 'glass-dock-tooltip';
    dockTooltip.innerHTML = `
      <div class="glass-dock-tooltip-inner">
        <span class="glass-dock-tooltip-text slide-in" id="glass-dock-tooltip-label"></span>
      </div>
    `;
    dock.appendChild(dockTooltip);
    tooltipTextEl = dockTooltip.querySelector('#glass-dock-tooltip-label');

    let itemIndex = 0;
    NAV_ITEMS.forEach((item) => {
      const el = document.createElement('button');
      el.className = 'glass-dock-item';
      el.type = 'button';
      el.dataset.dockId = item.id;
      el.dataset.index = itemIndex++;
      el.dataset.title = item.title;
      if (item.type === 'tab') {
        el.dataset.tab = item.id;
      }
      el.innerHTML = item.icon + `<span class="glass-dock-badge" id="dock-badge-${item.id}"></span>`;

      // Mouseenter for sliding tooltip
      el.addEventListener('mouseenter', () => {
        handleMouseEnter(el, dock);
      });

      // Click handling
      el.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        handleItemClick(item, el);
      });

      dock.appendChild(el);
    });

    dock.addEventListener('mouseleave', () => {
      hoveredIndex = null;
      prevIndex = null;
      if (dockTooltip) {
        dockTooltip.classList.remove('visible');
      }
    });

    container.appendChild(dock);
    document.body.appendChild(container);

    updateActiveDockTab();
  }

  // ===================================================================
  // Phone-only Sidebar (replaces the dock at <=768px; dock hidden via CSS)
  // ===================================================================
  const MOBILE_MQ = window.matchMedia('(max-width: 768px)');
  let sbEl = null;
  let sbScrim = null;
  let sbToggle = null;
  let sbOpen = false;
  let sbWidth = 300;

  function triggerHaptic(ms = 8) {
    try {
      if (navigator.vibrate) navigator.vibrate(ms);
    } catch (e) {}
  }
  window.triggerHaptic = triggerHaptic;

  // Real-time Visual Viewport & Soft Keyboard tracking (iOS Safari & Chrome Mobile)
  function initVisualViewportSync() {
    if (!window.visualViewport) return;
    let rAF = null;
    function updateViewport() {
      if (rAF) cancelAnimationFrame(rAF);
      rAF = requestAnimationFrame(() => {
        const vv = window.visualViewport;
        const winH = window.innerHeight;
        // Difference between layout viewport and visual viewport = soft keyboard height
        const keyboardInset = Math.max(0, winH - vv.height - (vv.offsetTop || 0));
        document.documentElement.style.setProperty('--keyboard-inset', `${Math.round(keyboardInset)}px`);
        document.documentElement.style.setProperty('--vv-height', `${Math.round(vv.height)}px`);
        const isKb = keyboardInset > 60;
        document.body.classList.toggle('keyboard-visible', isKb);
        if (isKb) {
          const chatHist = document.getElementById('chat-history');
          if (chatHist) {
            chatHist.scrollTop = chatHist.scrollHeight;
          }
        }
      });
    }
    window.visualViewport.addEventListener('resize', updateViewport, { passive: true });
    window.visualViewport.addEventListener('scroll', updateViewport, { passive: true });
    updateViewport();
  }

  function sbSetProgress(p) {
    p = Math.max(0, Math.min(1, p));
    if (sbEl) sbEl.style.setProperty('--p', p);
    if (sbScrim) {
      sbScrim.style.setProperty('--p', p);
      sbScrim.classList.toggle('visible', p > 0.001);
    }
  }

  function sbSetOpen(open, skipHistory = false) {
    sbOpen = !!open;
    triggerHaptic(8);
    if (sbEl) {
      sbEl.classList.remove('dragging');
      sbEl.classList.toggle('open', sbOpen);
      sbEl.setAttribute('aria-hidden', String(!sbOpen));
    }
    if (sbScrim) {
      sbScrim.classList.remove('dragging');
    }
    sbSetProgress(sbOpen ? 1 : 0);
    if (sbToggle) {
      sbToggle.classList.toggle('open', sbOpen);
      sbToggle.setAttribute('aria-expanded', String(sbOpen));
      sbToggle.setAttribute('aria-label', sbOpen ? 'Close navigation' : 'Open navigation');
    }
    document.body.classList.toggle('m-sidebar-open', sbOpen);
    
    // Native back button integration
    if (sbOpen && !skipHistory) {
      try {
        history.pushState({ eclipse_drawer_open: true }, '');
      } catch (e) {}
    } else if (!sbOpen && !skipHistory && history.state?.eclipse_drawer_open) {
      try {
        history.back();
      } catch (e) {}
    }

    if (sbOpen && sbEl) {
      updateSidebarProfile();
      const active = sbEl.querySelector('.m-sidebar-item.active');
      if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
    }
  }

  function resolveUserProfile() {
    let name = (localStorage.getItem('eclipse_user_name') || '').trim();
    let avatar = (localStorage.getItem('eclipse_user_avatar') || '').trim();

    if (!name || name.toLowerCase() === 'operator') {
      const alt = (localStorage.getItem('eclipse_user_profile_name') || '').trim();
      if (alt) name = alt;
    }
    if (!avatar) {
      avatar = (localStorage.getItem('eclipse_user_avatar_url') || '').trim();
    }

    if (!name) name = 'Operator';
    return { name, avatar };
  }

  function updateSidebarProfile() {
    if (!sbEl) return;
    const profile = resolveUserProfile();
    const nameEl = sbEl.querySelector('.m-sidebar-user-name');
    if (nameEl) nameEl.textContent = profile.name;

    const badgeEl = sbEl.querySelector('.m-sidebar-user-badge');
    if (badgeEl) {
      badgeEl.className = 'm-sidebar-user-badge local';
      badgeEl.textContent = 'Local Vault';
    }

    const avatarBox = sbEl.querySelector('#m-sidebar-avatar-box');
    if (avatarBox) {
      if (profile.avatar) {
        avatarBox.innerHTML = `<img src="${profile.avatar}" alt="${profile.name}" />`;
      } else {
        avatarBox.innerHTML = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
      }
    }
  }

  function createMobileSidebar() {
    if (document.getElementById('eclipse-mobile-sidebar')) return;

    initVisualViewportSync();

    // Toggle button with morphing three-bar -> X icon
    sbToggle = document.createElement('button');
    sbToggle.type = 'button';
    sbToggle.id = 'eclipse-sidebar-toggle';
    sbToggle.className = 'm-sidebar-toggle';
    sbToggle.setAttribute('aria-label', 'Open navigation');
    sbToggle.setAttribute('aria-controls', 'eclipse-mobile-sidebar');
    sbToggle.setAttribute('aria-expanded', 'false');
    sbToggle.innerHTML = `
      <span class="m-burger" aria-hidden="true">
        <span class="m-burger-bar b1"></span>
        <span class="m-burger-bar b2"></span>
        <span class="m-burger-bar b3"></span>
      </span>`;
    sbToggle.addEventListener('click', () => sbSetOpen(!sbOpen));

    sbScrim = document.createElement('div');
    sbScrim.className = 'm-sidebar-scrim';
    sbScrim.addEventListener('click', () => sbSetOpen(false));

    sbEl = document.createElement('aside');
    sbEl.id = 'eclipse-mobile-sidebar';
    sbEl.className = 'm-sidebar';
    sbEl.setAttribute('aria-label', 'Main navigation');
    sbEl.setAttribute('aria-hidden', 'true');

    // Sidebar Header: Logo & Branding (Subtitle removed per user request)
    const head = document.createElement('div');
    head.className = 'm-sidebar-head';
    head.innerHTML = `
      <img class="m-sidebar-logo" src="/logo.svg" alt="Eclipse" />
      <div class="m-sidebar-brand">
        <span class="m-sidebar-title">Eclipse</span>
      </div>`;
    sbEl.appendChild(head);

    // Navigation Items List
    const list = document.createElement('nav');
    list.className = 'm-sidebar-list';
    NAV_ITEMS.forEach((item) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'm-sidebar-item';
      b.dataset.dockId = item.id;
      if (item.type === 'tab') b.dataset.tab = item.id;
      b.innerHTML = `<span class="m-sidebar-icon">${item.icon}</span><span class="m-sidebar-label">${item.title}</span>`;
      b.addEventListener('click', () => {
        triggerHaptic(8);
        handleItemClick(item, b);
        sbSetOpen(false);
      });
      list.appendChild(b);
    });
    sbEl.appendChild(list);

    // Sidebar Footer: User Account Capsule & Settings Gear
    const foot = document.createElement('div');
    foot.className = 'm-sidebar-foot';

    const userProfile = resolveUserProfile();
    foot.innerHTML = `
      <div class="m-sidebar-profile-card">
        <div class="m-sidebar-avatar-circle" id="m-sidebar-avatar-box">
          ${userProfile.avatar ? `<img src="${userProfile.avatar}" alt="${userProfile.name}" />` : `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`}
        </div>
        <div class="m-sidebar-user-details" id="m-sidebar-user-details">
          <span class="m-sidebar-user-name">${userProfile.name}</span>
          <span class="m-sidebar-user-badge local">Local Vault</span>
        </div>
        <button type="button" class="m-sidebar-gear-btn" id="m-sidebar-gear-btn" aria-label="Settings" title="Open Settings">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
          </svg>
        </button>
      </div>
    `;

    const profileTrigger = foot.querySelector('.m-sidebar-profile-card');
    profileTrigger.addEventListener('click', (e) => {
      triggerHaptic(10);
      sbSetOpen(false);
      const gear = document.getElementById('btn-open-settings');
      if (gear) setTimeout(() => gear.click(), 220);
    });

    sbEl.appendChild(foot);

    document.body.appendChild(sbScrim);
    document.body.appendChild(sbEl);
    document.body.appendChild(sbToggle);
    sbSetProgress(0);

    // Sync profile on events
    window.addEventListener('eclipse-settings-updated', updateSidebarProfile);
    window.addEventListener('storage', updateSidebarProfile);

    // Esc closes
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && sbOpen) sbSetOpen(false);
    });

    // Hardware back button / swipe-back closes drawer
    window.addEventListener('popstate', (e) => {
      if (sbOpen) {
        sbSetOpen(false, true);
      }
    });

    // Close if viewport grows past phone breakpoint
    const onMq = () => { if (!MOBILE_MQ.matches && sbOpen) sbSetOpen(false); };
    if (MOBILE_MQ.addEventListener) MOBILE_MQ.addEventListener('change', onMq);
    else if (MOBILE_MQ.addListener) MOBILE_MQ.addListener(onMq);

    bindSidebarGestures();
    updateActiveDockTab();

    // Mobile Top Bar Model Chip click handler
    const topModelChip = document.getElementById('claude-top-model-chip');
    if (topModelChip) {
      topModelChip.addEventListener('click', (e) => {
        e.stopPropagation();
        triggerHaptic(8);
        const popover = document.getElementById('model-select-popover');
        if (popover) {
          const isOpen = popover.classList.toggle('open');
          topModelChip.classList.toggle('active', isOpen);
          if (isOpen) {
            document.getElementById('model-filter-input')?.focus();
          }
        }
      });
    }

    initBottomSheets();
  }

  // Mobile Bottom Sheet Scrim & Swipe-Down-To-Dismiss Engine
  function initBottomSheets() {
    let bsScrim = document.getElementById('bottom-sheet-scrim');
    if (!bsScrim) {
      bsScrim = document.createElement('div');
      bsScrim.id = 'bottom-sheet-scrim';
      bsScrim.className = 'bottom-sheet-scrim';
      document.body.appendChild(bsScrim);
    }

    const popover = document.getElementById('model-select-popover');
    const settings = document.getElementById('playground-settings-dropdown');
    const topChip = document.getElementById('claude-top-model-chip');
    const modelTrigger = document.getElementById('model-select-trigger');

    const popoverOrigParent = popover ? popover.parentNode : null;
    const popoverOrigNext = popover ? popover.nextSibling : null;
    const settingsOrigParent = settings ? settings.parentNode : null;
    const settingsOrigNext = settings ? settings.nextSibling : null;

    function ensureMobileSheetPlacement() {
      const isMobile = window.matchMedia('(max-width: 768px)').matches;
      if (isMobile) {
        if (popover && popover.parentNode !== document.body) {
          document.body.appendChild(popover);
        }
        if (settings && settings.parentNode !== document.body) {
          document.body.appendChild(settings);
        }
      } else {
        if (popover && popover.parentNode === document.body && popoverOrigParent) {
          popoverOrigParent.insertBefore(popover, popoverOrigNext);
        }
        if (settings && settings.parentNode === document.body && settingsOrigParent) {
          settingsOrigParent.insertBefore(settings, settingsOrigNext);
        }
      }
    }

    ensureMobileSheetPlacement();
    window.addEventListener('resize', ensureMobileSheetPlacement);

    function closeBottomSheets() {
      triggerHaptic(6);
      if (popover) popover.classList.remove('open');
      if (settings) settings.classList.remove('open');
      if (topChip) topChip.classList.remove('active');
      if (modelTrigger) modelTrigger.classList.remove('active');
      if (bsScrim) bsScrim.classList.remove('visible');
      document.body.classList.remove('bottom-sheet-open');
    }

    bsScrim.addEventListener('click', closeBottomSheets);

    function syncScrim() {
      ensureMobileSheetPlacement();
      const isMobile = window.matchMedia('(max-width: 768px)').matches;
      const isOpen = isMobile && ((popover && popover.classList.contains('open')) || (settings && settings.classList.contains('open')));
      if (bsScrim) bsScrim.classList.toggle('visible', !!isOpen);
      document.body.classList.toggle('bottom-sheet-open', !!isOpen);
    }

    if (window.MutationObserver) {
      const mo = new MutationObserver(syncScrim);
      if (popover) mo.observe(popover, { attributes: true, attributeFilter: ['class'] });
      if (settings) mo.observe(settings, { attributes: true, attributeFilter: ['class'] });
    }
    window.addEventListener('eclipse-bottomsheet-change', syncScrim);

    // Swipe-down-to-dismiss for bottom sheets on mobile
    function bindDismiss(sheet) {
      if (!sheet) return;
      let startY = 0;
      let currentY = 0;
      let dragging = false;

      sheet.addEventListener('touchstart', (e) => {
        if (!window.matchMedia('(max-width: 768px)').matches) return;
        if (sheet.scrollTop > 6) return;
        startY = e.touches[0].clientY;
        dragging = true;
      }, { passive: true });

      sheet.addEventListener('touchmove', (e) => {
        if (!dragging) return;
        currentY = e.touches[0].clientY;
        const dy = currentY - startY;
        if (dy > 0) {
          sheet.style.transform = `translate3d(0, ${dy}px, 0)`;
          sheet.style.transition = 'none';
        }
      }, { passive: true });

      const onEnd = () => {
        if (!dragging) return;
        dragging = false;
        sheet.style.transition = '';
        const dy = currentY - startY;
        if (dy > 70) {
          closeBottomSheets();
          sheet.style.transform = '';
        } else {
          sheet.style.transform = '';
        }
        startY = 0;
        currentY = 0;
      };

      sheet.addEventListener('touchend', onEnd, { passive: true });
      sheet.addEventListener('touchcancel', onEnd, { passive: true });
    }

    bindDismiss(popover);
    bindDismiss(settings);
  }

  // Edge-swipe to open, drag-to-close, finger-following drawer
  function bindSidebarGestures() {
    let tracking = null; // { mode:'open'|'close', startX, startY, lastX, lastT, vx, locked }
    const EDGE = 22;

    function width() { return sbEl.offsetWidth || sbWidth; }

    document.addEventListener('touchstart', (e) => {
      if (!MOBILE_MQ.matches || e.touches.length !== 1) return;
      const t = e.touches[0];
      if (!sbOpen && t.clientX <= EDGE) {
        tracking = { mode: 'open', startX: t.clientX, startY: t.clientY, lastX: t.clientX, lastT: Date.now(), vx: 0, locked: false };
      } else if (sbOpen) {
        tracking = { mode: 'close', startX: t.clientX, startY: t.clientY, lastX: t.clientX, lastT: Date.now(), vx: 0, locked: false };
      }
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
      if (!tracking) return;
      const t = e.touches[0];
      const dx = t.clientX - tracking.startX;
      const dy = t.clientY - tracking.startY;
      if (!tracking.locked) {
        if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 8) { tracking = null; return; }
        if (Math.abs(dx) > 8) {
          tracking.locked = true;
          sbEl.classList.add('dragging');
          sbScrim.classList.add('dragging');
        } else return;
      }
      const now = Date.now();
      const dt = Math.max(1, now - tracking.lastT);
      tracking.vx = (t.clientX - tracking.lastX) / dt;
      tracking.lastX = t.clientX;
      tracking.lastT = now;
      const w = width();
      const p = tracking.mode === 'open' ? dx / w : 1 + dx / w;
      sbSetProgress(p);
    }, { passive: true });

    function end() {
      if (!tracking) return;
      const wasLocked = tracking.locked;
      const vx = tracking.vx;
      const mode = tracking.mode;
      tracking = null;
      if (!wasLocked) return;
      const cur = parseFloat(sbEl.style.getPropertyValue('--p')) || 0;
      let open;
      if (Math.abs(vx) > 0.4) open = vx > 0;
      else open = cur > 0.5;
      sbSetOpen(open);
    }
    document.addEventListener('touchend', end, { passive: true });
    document.addEventListener('touchcancel', end, { passive: true });
  }

  function handleMouseEnter(itemEl, dockEl) {
    try {
      const idx = parseInt(itemEl.dataset.index, 10);
      const title = itemEl.dataset.title;

      if (!dockTooltip || !tooltipTextEl) return;

      tooltipTextEl.textContent = title;

      const itemRect = itemEl.getBoundingClientRect();
      const dockRect = dockEl.getBoundingClientRect();
      const isVertical = document.body.classList.contains('dock-vertical');

      const direction = (hoveredIndex !== null && idx !== hoveredIndex)
        ? (idx > hoveredIndex ? 1 : -1)
        : 0;

      prevIndex = hoveredIndex;
      hoveredIndex = idx;

      if (isVertical) {
        // In vertical format: tooltip is on the right of the dock, positioned at item's Y
        const tooltipHeight = dockTooltip.offsetHeight || 28;
        const centerOffsetY = (itemRect.top - dockRect.top) + (itemRect.height / 2) - (tooltipHeight / 2);
        dockTooltip.style.transform = `translate3d(0, ${Math.round(centerOffsetY)}px, 0) scale(1)`;
      } else {
        // In horizontal format: tooltip is on top of the dock, positioned at item's X
        const tooltipWidth = dockTooltip.offsetWidth || 100;
        const centerOffsetX = (itemRect.left - dockRect.left) + (itemRect.width / 2) - (tooltipWidth / 2);
        dockTooltip.style.transform = `translate3d(${Math.round(centerOffsetX)}px, 0, 0) scale(1)`;
      }

      dockTooltip.classList.add('visible');

      // Direction-aware blur slide
      if (direction !== 0) {
        if (isVertical) {
          tooltipTextEl.className = 'glass-dock-tooltip-text ' + (direction > 0 ? 'slide-from-bottom' : 'slide-from-top');
        } else {
          tooltipTextEl.className = 'glass-dock-tooltip-text ' + (direction > 0 ? 'slide-from-right' : 'slide-from-left');
        }
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (tooltipTextEl) {
              tooltipTextEl.className = 'glass-dock-tooltip-text slide-in';
            }
          });
        });
      } else {
        tooltipTextEl.className = 'glass-dock-tooltip-text slide-in';
      }
    } catch (err) {
      console.warn('Dock tooltip calculation:', err);
    }
  }

  function handleItemClick(item, el) {
    if (dockTooltip) {
      dockTooltip.classList.remove('visible');
    }
    hoveredIndex = null;
    prevIndex = null;

    if (item.type === 'tab') {
      try {
        if (typeof window.switchTab === 'function') {
          window.switchTab(item.id);
        }
      } catch (err) {
        console.error('switchTab error:', err);
      }
      updateActiveDockTab();
      updateDockMode();
    }
  }

  function updateActiveDockTab() {
    const activeTab = document.body.dataset.activeTab || 'playground';
    document.querySelectorAll('.glass-dock-item[data-tab], .m-sidebar-item[data-tab]').forEach((el) => {
      el.classList.toggle('active', el.dataset.tab === activeTab);
    });
  }

  // Updates dock between horizontal bottom and vertical left format
  function updateDockMode(forceVertical) {
    const activeTab = document.body.dataset.activeTab || 'playground';
    const isPlayground = activeTab === 'playground';
    const workspace = document.getElementById('playground-workspace');
    const hasMessages = workspace ? workspace.classList.contains('has-messages') : false;

    const shouldBeVertical = (typeof forceVertical === 'boolean')
      ? forceVertical
      : (!isPlayground || hasMessages);

    if (shouldBeVertical) {
      if (!document.body.classList.contains('dock-vertical')) {
        document.body.classList.add('dock-vertical');
      }
    } else {
      if (document.body.classList.contains('dock-vertical')) {
        document.body.classList.remove('dock-vertical');
      }
    }
  }

  // Observe active tab or has-messages changes without feedback loops
  const observer = new MutationObserver(() => {
    updateActiveDockTab();
    updateDockMode();
  });

  function init() {
    createGlassDock();
    createMobileSidebar();
    updateDockMode();

    // Observe data-active-tab only (NOT class on body to avoid feedback loops)
    observer.observe(document.body, { attributes: true, attributeFilter: ['data-active-tab'] });

    const workspace = document.getElementById('playground-workspace');
    if (workspace) {
      observer.observe(workspace, { attributes: true, attributeFilter: ['class'] });
    }

    window.EclipseGlassDock = {
      updateDockMode,
      updateActiveDockTab,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
