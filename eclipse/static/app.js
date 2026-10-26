/**
 * Eclipse App Frontend Logic
 * Universal AI Gateway & Hub Client
 */

// Global State
const state = {
  currentTab: 'playground',
  services: [],
  limits: {},
  models: [],
  activeCookieProvider: 'antigravity',
  cookiesData: {},
  selectedModel: localStorage.getItem('eclipse_selected_model') || 'gemini-3.8-flash',
  chatMessages: [],
  isStreaming: false,
  playgroundModality: 'all',
  selectedAspectRatio: '1:1',
  tunnel: { status: 'offline', public_url: null, has_authtoken: false },
  enableArtifacts: true,
  artifacts: {},
  activeArtifactId: null,
  activeArtifactView: 'preview',
  artifactWorkbenchOpen: false,
  toolsEnabled: false,
  toolsInfo: null,
  voiceModeEnabled: localStorage.getItem('eclipse_voice_mode') === 'true',
  voiceModel: localStorage.getItem('eclipse_voice_model') || 'ais-gemini-3.8-flash-tts',
  voiceTimbre: localStorage.getItem('eclipse_voice_timbre') || 'Puck',
  voiceAutoSpeak: localStorage.getItem('eclipse_voice_autospeak') !== 'false',
  currentAudio: null,
};

// ===================================================================
// Custom Toast Notification System (NO DEFAULT GOOGLE POPUPS)
// ===================================================================
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconSvg = {
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97757" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
  }[type] || '';

  toast.innerHTML = `
    ${iconSvg}
    <div class="toast-message">${escapeHtml(message)}</div>
    <button class="toast-close" title="Close">&times;</button>
  `;

  toast.querySelector('.toast-close').addEventListener('click', () => {
    toast.remove();
  });

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Media URLs pulled out of model output: allow only web, generated-file and inline media sources.
// Callers still escapeHtml() the result before putting it in an attribute.
function safeMediaUrl(url) {
  const u = String(url || '').trim();
  if (/^https?:\/\//i.test(u) || /^\/static\//.test(u) || /^blob:/i.test(u)) return u;
  if (/^data:(?:image\/(?:png|jpe?g|gif|webp|svg\+xml)|video\/(?:mp4|webm));base64,[A-Za-z0-9+/=]+$/i.test(u)) return u;
  return '';
}

// ===================================================================
// Gateway Login (off-machine browsers only: phone, LAN, ngrok tunnel)
// ===================================================================
// On the machine running Eclipse the gateway trusts loopback requests, so this never shows.
// Anywhere else, the gateway answers 401 until the browser logs in with the gateway key and
// receives an HttpOnly session cookie.

const nativeFetch = window.fetch.bind(window);

// Default gateway authentication key (auto-unlocks local and mobile clients without manual prompts)
const DEFAULT_GATEWAY_KEY = 'Insom-Eclipse';
const activeGatewayKey = localStorage.getItem('eclipse_gateway_key') || DEFAULT_GATEWAY_KEY;
localStorage.setItem('eclipse_gateway_key', activeGatewayKey);

// Silent auto-login so browser session cookie is established seamlessly
nativeFetch('/api/auth/status')
  .then((r) => r.json())
  .then((s) => {
    if (s && s.authenticated === false) {
      nativeFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: activeGatewayKey }),
      }).catch(() => {});
    }
  })
  .catch(() => {});

window.fetch = async (input, init = {}) => {
  const savedKey = localStorage.getItem('eclipse_gateway_key') || DEFAULT_GATEWAY_KEY;
  if (savedKey) {
    init = init || {};
    init.headers = init.headers || {};
    if (init.headers instanceof Headers) {
      if (!init.headers.has('X-Gateway-Key')) init.headers.set('X-Gateway-Key', savedKey);
    } else if (Array.isArray(init.headers)) {
      init.headers.push(['X-Gateway-Key', savedKey]);
    } else {
      if (!init.headers['X-Gateway-Key']) init.headers['X-Gateway-Key'] = savedKey;
    }
  }
  return await nativeFetch(input, init);
};

// ===================================================================
// Theme Controller (3-Option Segmented Control + OS Dynamic Scheme)
// ===================================================================
let systemThemeMediaQuery = null;

function applyThemePref(pref, animate = true) {
  const validPref = ['system', 'light', 'dark'].includes(pref) ? pref : 'system';
  localStorage.setItem('eclipse_theme_pref', validPref);

  let effectiveTheme = validPref;
  if (validPref === 'system') {
    const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    effectiveTheme = isDark ? 'dark' : 'light';
  }

  if (animate) {
    document.documentElement.classList.add('theme-transitioning');
    clearTimeout(window.__themeTransitionTimeout);
    window.__themeTransitionTimeout = setTimeout(() => {
      document.documentElement.classList.remove('theme-transitioning');
    }, 280);
  }

  document.documentElement.setAttribute('data-theme', effectiveTheme);
  localStorage.setItem('eclipse_theme', effectiveTheme);
  const themeMeta = document.getElementById('theme-color-meta');
  if (themeMeta) {
    themeMeta.setAttribute('content', effectiveTheme === 'light' ? '#fcfbfa' : '#141414');
  }

  // Update 3-icon segmented control UI
  const btnSystem = document.getElementById('btn-theme-system');
  const btnLight = document.getElementById('btn-theme-light');
  const btnDark = document.getElementById('btn-theme-dark');
  const indicator = document.getElementById('theme-seg-indicator');

  if (btnSystem) {
    btnSystem.classList.toggle('active', validPref === 'system');
    btnSystem.setAttribute('aria-checked', validPref === 'system' ? 'true' : 'false');
  }
  if (btnLight) {
    btnLight.classList.toggle('active', validPref === 'light');
    btnLight.setAttribute('aria-checked', validPref === 'light' ? 'true' : 'false');
  }
  if (btnDark) {
    btnDark.classList.toggle('active', validPref === 'dark');
    btnDark.setAttribute('aria-checked', validPref === 'dark' ? 'true' : 'false');
  }

  if (indicator) {
    if (validPref === 'system') indicator.style.transform = 'translateX(0%)';
    else if (validPref === 'light') indicator.style.transform = 'translateX(100%)';
    else if (validPref === 'dark') indicator.style.transform = 'translateX(200%)';
  }

  if (typeof syncGlobeTheme === 'function' && typeof globeRunning !== 'undefined' && globeRunning) {
    var isOnline = state.tunnel && state.tunnel.status === 'online';
    syncGlobeTheme(isOnline);
  }

  if (animate) {
    window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
  }
}
window.applyThemePref = applyThemePref;

function setAppTheme(theme) {
  applyThemePref(theme, true);
}

function initTheme() {
  const savedPref = localStorage.getItem('eclipse_theme_pref') || localStorage.getItem('eclipse_theme') || 'system';
  applyThemePref(savedPref, false);

  // Dynamic OS preference listener
  if (window.matchMedia && !systemThemeMediaQuery) {
    systemThemeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    systemThemeMediaQuery.addEventListener('change', (e) => {
      const currentPref = localStorage.getItem('eclipse_theme_pref') || 'system';
      if (currentPref === 'system') {
        applyThemePref('system', true);
      }
    });
  }

  // 3-Icon Segmented Buttons Event Listeners
  const btnSystem = document.getElementById('btn-theme-system');
  const btnLight = document.getElementById('btn-theme-light');
  const btnDark = document.getElementById('btn-theme-dark');

  if (btnSystem) {
    btnSystem.addEventListener('click', (e) => {
      e.stopPropagation();
      applyThemePref('system', true);
      showToast('Theme set to Match System', 'info', 1800);
    });
  }
  if (btnLight) {
    btnLight.addEventListener('click', (e) => {
      e.stopPropagation();
      applyThemePref('light', true);
      showToast('Theme set to Light Mode', 'info', 1800);
    });
  }
  if (btnDark) {
    btnDark.addEventListener('click', (e) => {
      e.stopPropagation();
      applyThemePref('dark', true);
      showToast('Theme set to Dark Mode', 'info', 1800);
    });
  }

  // Initialize Profile Settings
  initClaudeSettings();
}

function initUserProfile() {
  return initClaudeSettings();
}

async function copyTextToClipboard(text) {
  if (!text) return false;
  // 1. Try native Async Clipboard API if available in secure context
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      console.warn('navigator.clipboard write failed, using fallback:', err);
    }
  }

  // 2. Cross-platform fallback for mobile (iOS Safari & Android Chrome over insecure LAN)
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.width = '2em';
    textArea.style.height = '2em';
    textArea.style.padding = '0';
    textArea.style.border = 'none';
    textArea.style.outline = 'none';
    textArea.style.boxShadow = 'none';
    textArea.style.background = 'transparent';
    textArea.style.opacity = '0.01';
    textArea.style.zIndex = '-9999';
    textArea.style.fontSize = '16px'; // Prevents auto-zoom on iOS Safari
    textArea.setAttribute('readonly', '');
    document.body.appendChild(textArea);

    if (navigator.userAgent.match(/ipad|ipod|iphone/i)) {
      textArea.contentEditable = 'true';
      textArea.readOnly = false;
      const range = document.createRange();
      range.selectNodeContents(textArea);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      textArea.setSelectionRange(0, 999999);
    } else {
      textArea.focus();
      textArea.select();
    }
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    if (successful) return true;
  } catch (err) {
    console.warn('execCommand clipboard copy failed:', err);
  }

  // 3. Prompt fallback if programmatic clipboard write is blocked by phone OS
  try {
    window.prompt('Copy endpoint URL to clipboard: Ctrl+C / tap copy', text);
    return true;
  } catch (_) {
    return false;
  }
}

function processAvatarFile(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith('image/')) {
      return reject(new Error('Please select an image file (PNG, JPG, WebP).'));
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const size = Math.min(img.width, img.height);
        const sx = (img.width - size) / 2;
        const sy = (img.height - size) / 2;
        const targetDim = Math.min(size, 256);
        const canvas = document.createElement('canvas');
        canvas.width = targetDim;
        canvas.height = targetDim;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, sx, sy, size, size, 0, 0, targetDim, targetDim);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.88);
        resolve(dataUrl);
      };
      img.onerror = () => reject(new Error('Failed to load image.'));
      img.src = e.target.result;
    };
    reader.onerror = () => reject(new Error('Failed to read file.'));
    reader.readAsDataURL(file);
  });
}

function playCompletionChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;
    
    // Smooth chime: C5 (523.25Hz) followed by E5 (659.25Hz)
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gainNode = ctx.createGain();

    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(523.25, now);
    osc1.frequency.exponentialRampToValueAtTime(659.25, now + 0.12);

    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(659.25, now + 0.08);

    gainNode.gain.setValueAtTime(0.001, now);
    gainNode.gain.linearRampToValueAtTime(0.06, now + 0.04);
    gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.45);

    osc1.connect(gainNode);
    osc2.connect(gainNode);
    gainNode.connect(ctx.destination);

    osc1.start(now);
    osc2.start(now + 0.08);
    osc1.stop(now + 0.45);
    osc2.stop(now + 0.45);
    setTimeout(() => ctx.close(), 600);
  } catch (err) {
    // AudioContext autoplay might be constrained; ignore silently
  }
}

function initClaudeSettings() {
  if (window._claudeSettingsInitialized) return;
  window._claudeSettingsInitialized = true;

  const settingsBtn = document.getElementById('btn-open-settings') || document.getElementById('btn-user-avatar');
  const settingsModal = document.getElementById('claude-settings-modal');
  const settingsDialog = document.getElementById('claude-settings-dialog');
  const closeBtn = document.getElementById('btn-close-settings-modal');
  const searchInput = document.getElementById('claude-settings-search');
  const navItems = document.querySelectorAll('.claude-settings-nav-item');
  const panels = document.querySelectorAll('.claude-settings-panel');
  const avatarUploadTrigger = document.getElementById('user-avatar-upload-trigger');
  const avatarCircle = document.getElementById('user-profile-avatar-circle');
  const avatarFileInput = document.getElementById('user-avatar-file-input');
  const removeAvatarBtn = document.getElementById('btn-remove-avatar');
  const nameInput = document.getElementById('user-profile-name-input');
  const saveNameBtn = document.getElementById('btn-save-user-name');
  const copyEndpointRow = document.getElementById('profile-copy-endpoint');
  const endpointTextEl = document.getElementById('profile-endpoint-text');
  const endpointCopyBtn = document.getElementById('btn-copy-gateway-endpoint');
  const copyHintEl = document.getElementById('profile-copy-hint');
  const apikeyCopyRow = document.getElementById('apikey-copy-row');
  const apikeyCopyBtn = document.getElementById('btn-copy-apikey');
  const apikeyCopyHint = document.getElementById('apikey-copy-hint');
  const profileApikeyText = document.getElementById('profile-apikey-text');
  const inputGatewayKey = document.getElementById('input-gateway-key');
  const btnSaveGatewayKey = document.getElementById('btn-save-gateway-key');
  const btnCopyCustomGatewayKey = document.getElementById('btn-copy-custom-gateway-key');
  const btnRotateGatewayKey = document.getElementById('btn-rotate-gateway-key');

  // Modal open / close logic
  let isModalOpen = false;
  let closeTimer = null;

  const openModal = (defaultTab = null) => {
    const modal = settingsModal || document.getElementById('claude-settings-modal');
    if (!modal) return;
    clearTimeout(closeTimer);
    modal.style.display = 'flex';
    modal.style.pointerEvents = 'auto';
    void modal.offsetWidth; // Force reflow for CSS spring transition
    modal.classList.add('open');
    isModalOpen = true;

    if (defaultTab) {
      switchTab(defaultTab);
    }
    if (typeof initSmoothInputs === 'function') {
      setTimeout(() => initSmoothInputs(), 50);
    }
  };

  const closeModal = () => {
    const modal = settingsModal || document.getElementById('claude-settings-modal');
    if (!modal || !isModalOpen) return;
    modal.classList.remove('open');
    modal.style.pointerEvents = 'none';
    isModalOpen = false;
    closeTimer = setTimeout(() => {
      if (!isModalOpen) {
        modal.style.display = 'none';
      }
    }, 220);
  };

  window.openClaudeSettings = openModal;
  window.closeClaudeSettings = closeModal;

  // Global event delegation for opening settings modal
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('#btn-open-settings, #profile-open-settings, .claude-settings-gear-btn, [data-action="open-settings"]');
    if (trigger) {
      e.preventDefault();
      e.stopPropagation();
      openModal();
    }
  });

  if (settingsBtn) {
    settingsBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      openModal();
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      closeModal();
    });
  }

  if (settingsModal) {
    settingsModal.addEventListener('click', (e) => {
      if (e.target === settingsModal) {
        closeModal();
      }
    });
  }

  if (settingsDialog) {
    settingsDialog.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isModalOpen) {
      closeModal();
    }
  });

  // Tab switching logic
  const switchTab = (tabId) => {
    navItems.forEach(btn => {
      const isMatch = btn.getAttribute('data-tab') === tabId;
      btn.classList.toggle('active', isMatch);
      btn.setAttribute('aria-selected', isMatch ? 'true' : 'false');
    });

    panels.forEach(p => {
      const isMatch = p.id === `settings-panel-${tabId}`;
      p.classList.toggle('active', isMatch);
    });

    if (searchInput && searchInput.value.trim()) {
      filterSettings(searchInput.value.trim());
    }
  };

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = item.getAttribute('data-tab');
      if (tabId) switchTab(tabId);
    });
  });

  // Search filter across active panel & rows
  const filterSettings = (query) => {
    const q = query.toLowerCase();
    const activePanel = document.querySelector('.claude-settings-panel.active');
    if (!activePanel) return;

    const rows = activePanel.querySelectorAll('.claude-settings-row');
    rows.forEach(row => {
      const searchAttr = row.getAttribute('data-search-text') || '';
      const text = (row.textContent + ' ' + searchAttr).toLowerCase();
      if (!q || text.includes(q)) {
        row.style.display = 'flex';
      } else {
        row.style.display = 'none';
      }
    });
  };

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      filterSettings(e.target.value.trim());
    });
  }

  // Chat Font Selector Logic
  const fontSelectWrap = document.getElementById('chat-font-select-wrap');
  const fontSelectBtn = document.getElementById('btn-chat-font-select');
  const fontSelectMenu = document.getElementById('chat-font-select-menu');
  const fontSelectedLabel = document.getElementById('chat-font-selected-label');
  const fontOptions = fontSelectMenu ? fontSelectMenu.querySelectorAll('.claude-select-option') : [];

  const fontMap = {
    'serif': { label: 'Anthropic Serif', value: 'var(--font-serif)' },
    'sans': { label: 'Anthropic Sans', value: 'var(--font-sans)' },
    'system': { label: 'System', value: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
    'mono': { label: 'OpenDyslexic', value: 'var(--font-mono)' }
  };

  const applyChatFont = (fontKey, save = true) => {
    const config = fontMap[fontKey] || fontMap['sans'];
    document.documentElement.style.setProperty('--chat-font', config.value);
    if (fontSelectedLabel) fontSelectedLabel.textContent = config.label;

    fontOptions.forEach(opt => {
      opt.classList.toggle('active', opt.getAttribute('data-font') === fontKey);
    });

    if (save) {
      localStorage.setItem('eclipse_chat_font', fontKey);
      showToast(`Chat font set to ${config.label}`, 'info', 1600);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    }
  };
  window.applyChatFont = applyChatFont;

  const savedFont = localStorage.getItem('eclipse_chat_font') || 'sans';
  applyChatFont(savedFont, false);

  if (fontSelectBtn && fontSelectMenu) {
    fontSelectBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fontSelectMenu.classList.toggle('open');
    });

    fontOptions.forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const fontKey = opt.getAttribute('data-font');
        if (fontKey) {
          applyChatFont(fontKey, true);
        }
        fontSelectMenu.classList.remove('open');
      });
    });

    document.addEventListener('click', (e) => {
      if (!fontSelectBtn.contains(e.target) && !fontSelectMenu.contains(e.target)) {
        fontSelectMenu.classList.remove('open');
      }
    });
  }

  // Generic Custom Dropdown Helper for Claude Settings
  const setupCustomDropdown = (wrapId, btnId, menuId, labelId, storageKey, defaultValue, onChange) => {
    const wrap = document.getElementById(wrapId);
    const btn = document.getElementById(btnId);
    const menu = document.getElementById(menuId);
    const label = document.getElementById(labelId);
    if (!wrap || !btn || !menu) return null;

    const options = menu.querySelectorAll('.claude-select-option');

    const setValue = (val, save = true) => {
      let activeText = '';
      options.forEach(opt => {
        const isMatch = opt.getAttribute('data-value') === val || opt.getAttribute('data-font') === val;
        opt.classList.toggle('active', isMatch);
        if (isMatch) {
          const spanEl = opt.querySelector('span');
          activeText = spanEl ? spanEl.textContent : opt.textContent.trim();
        }
      });

      if (label && activeText) {
        label.textContent = activeText;
      }

      if (save && storageKey) {
        localStorage.setItem(storageKey, val);
      }

      if (typeof onChange === 'function') {
        onChange(val, save);
      }
    };

    const initial = storageKey ? (localStorage.getItem(storageKey) || defaultValue) : defaultValue;
    if (initial) {
      setValue(initial, false);
    }

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      document.querySelectorAll('.claude-custom-select-menu.open').forEach(m => {
        if (m !== menu) m.classList.remove('open');
      });
      menu.classList.toggle('open');
    });

    options.forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const val = opt.getAttribute('data-value') || opt.getAttribute('data-font');
        if (val) {
          setValue(val, true);
        }
        menu.classList.remove('open');
      });
    });

    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) {
        menu.classList.remove('open');
      }
    });

    return { setValue };
  };

  // Voice Custom Select Dropdowns
  setupCustomDropdown(
    'voice-language-select-wrap',
    'btn-voice-language-select',
    'voice-language-select-menu',
    'voice-language-selected-label',
    'eclipse_voice_language',
    'en-US',
    (val, save) => {
      if (save) showToast(`Voice language set to ${val}`, 'info', 1600);
    }
  );

  setupCustomDropdown(
    'voice-style-select-wrap',
    'btn-voice-style-select',
    'voice-style-select-menu',
    'voice-style-selected-label',
    'eclipse_voice_style',
    'buttery',
    (val, save) => {
      if (save) showToast(`Voice style set to ${val}`, 'info', 1600);
    }
  );

  setupCustomDropdown(
    'voice-speed-select-wrap',
    'btn-voice-speed-select',
    'voice-speed-select-menu',
    'voice-speed-selected-label',
    'eclipse_voice_speed',
    'normal',
    (val, save) => {
      if (save) showToast(`Voice speed set to ${val}`, 'info', 1600);
    }
  );

  // Motion Toggle Switch
  const motionToggle = document.getElementById('toggle-reduce-motion');
  if (motionToggle) {
    const isReduced = localStorage.getItem('eclipse_reduce_motion') === 'true';
    motionToggle.checked = isReduced;
    document.documentElement.classList.toggle('reduce-motion', isReduced);

    motionToggle.addEventListener('change', (e) => {
      const reduced = e.target.checked;
      document.documentElement.classList.toggle('reduce-motion', reduced);
      localStorage.setItem('eclipse_reduce_motion', reduced ? 'true' : 'false');
      showToast(reduced ? 'Reduced motion enabled' : 'Smooth animations restored', 'info', 1800);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  // Audio Chime Toggle
  const chimeToggle = document.getElementById('toggle-response-chime');
  if (chimeToggle) {
    chimeToggle.checked = localStorage.getItem('eclipse_response_chime') === 'true';
    chimeToggle.addEventListener('change', (e) => {
      localStorage.setItem('eclipse_response_chime', e.target.checked ? 'true' : 'false');
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
      if (e.target.checked) {
        playCompletionChime();
        showToast('Completion chime enabled', 'info', 1800);
      }
    });
  }

  // Profile Avatar & Name in Account Panel
  const renderUserAvatar = (dataUrl) => {
    if (dataUrl) {
      if (avatarCircle) {
        avatarCircle.innerHTML = `<img src="${dataUrl}" class="user-avatar-img" alt="Profile Picture" />`;
      }
      if (removeAvatarBtn) removeAvatarBtn.style.display = 'inline-block';
    } else {
      if (avatarCircle) {
        avatarCircle.innerHTML = `
          <svg class="default-avatar-svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        `;
      }
      if (removeAvatarBtn) removeAvatarBtn.style.display = 'none';
    }
  };
  window.renderUserAvatar = renderUserAvatar;

  const storedAvatar = localStorage.getItem('eclipse_user_avatar');
  renderUserAvatar(storedAvatar);

  const savedName = (localStorage.getItem('eclipse_user_name') || 'Operator').trim();
  if (nameInput) {
    nameInput.value = savedName;
  }

  const saveProfileName = (showNotification = true) => {
    const raw = nameInput ? nameInput.value.trim() : '';
    const name = raw || 'Operator';
    if (nameInput) nameInput.value = name;
    localStorage.setItem('eclipse_user_name', name);
    window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));

    if (saveNameBtn) {
      saveNameBtn.classList.remove('visible');
      saveNameBtn.classList.add('saved');
      setTimeout(() => saveNameBtn.classList.remove('saved'), 1500);
    }
    if (showNotification) {
      showToast(`Profile name saved as "${name}"`, 'success', 2000);
    }
  };

  if (nameInput) {
    nameInput.addEventListener('input', () => {
      const currentStored = localStorage.getItem('eclipse_user_name') || 'Operator';
      if (nameInput.value.trim() !== currentStored) {
        if (saveNameBtn) saveNameBtn.classList.add('visible');
      } else {
        if (saveNameBtn) saveNameBtn.classList.remove('visible');
      }
    });

    nameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        nameInput.blur();
        saveProfileName(true);
      }
    });

    nameInput.addEventListener('blur', () => {
      const currentStored = localStorage.getItem('eclipse_user_name') || 'Operator';
      if (nameInput.value.trim() && nameInput.value.trim() !== currentStored) {
        saveProfileName(true);
      }
    });
  }

  if (saveNameBtn) {
    saveNameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      saveProfileName(true);
    });
  }

  if (avatarUploadTrigger && avatarFileInput) {
    avatarUploadTrigger.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        avatarFileInput.click();
      }
    });

    avatarFileInput.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    avatarFileInput.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const dataUrl = await processAvatarFile(file);
        localStorage.setItem('eclipse_user_avatar', dataUrl);
        renderUserAvatar(dataUrl);
        showToast('Profile picture updated', 'success', 2200);
        window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
      } catch (err) {
        showToast(err.message || 'Failed to process picture', 'error', 3000);
      } finally {
        avatarFileInput.value = '';
      }
    });
  }

  if (removeAvatarBtn) {
    removeAvatarBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      localStorage.removeItem('eclipse_user_avatar');
      renderUserAvatar(null);
      showToast('Profile picture removed', 'info', 2000);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  // Allowed Web Origins / CORS Client Management
  const originsContainer = document.getElementById('allowed-origins-container');
  const newOriginInput = document.getElementById('input-new-allowed-origin');
  const addOriginBtn = document.getElementById('btn-add-allowed-origin');
  const presetOriginBtns = document.querySelectorAll('.preset-origin-btn');

  const renderAllowedOrigins = (origins) => {
    if (!originsContainer) return;
    if (!origins || origins.length === 0) {
      originsContainer.innerHTML = '<span style="font-size: 12px; color: var(--text-muted); font-style: italic;">No external web origins added. Gateway allows localhost and local network by default.</span>';
      return;
    }
    originsContainer.innerHTML = origins.map(orig => `
      <div class="origin-tag" style="display: inline-flex; align-items: center; gap: 6px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; padding: 4px 8px; font-size: 12px; font-family: var(--font-mono);">
        <span style="color: var(--text-primary);">${orig}</span>
        <button type="button" class="btn-delete-origin" data-origin="${orig}" title="Revoke origin" style="background: none; border: none; color: var(--color-error); cursor: pointer; padding: 0 2px; font-weight: bold; font-size: 14px; line-height: 1;">&times;</button>
      </div>
    `).join('');

    originsContainer.querySelectorAll('.btn-delete-origin').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const orig = btn.getAttribute('data-origin');
        if (!orig) return;
        try {
          const res = await fetch(`/api/security/allowed-origins?origin=${encodeURIComponent(orig)}`, { method: 'DELETE' });
          if (res.ok) {
            const data = await res.json();
            renderAllowedOrigins(data.allowed_origins);
            showToast(`Revoked access for ${orig}`, 'info', 2000);
          } else {
            showToast(`Failed to remove origin`, 'error', 2000);
          }
        } catch (err) {
          showToast(`Error removing origin: ${err.message}`, 'error', 2000);
        }
      });
    });
  };

  const loadAllowedOrigins = async () => {
    if (!originsContainer) return;
    try {
      const res = await fetch('/api/security/allowed-origins');
      if (res.ok) {
        const data = await res.json();
        renderAllowedOrigins(data.allowed_origins);
      }
    } catch (e) {
      console.warn('Failed to fetch allowed origins:', e);
    }
  };

  const handleAddOrigin = async (originUrl) => {
    let clean = (originUrl || '').trim();
    if (!clean) return;
    if (clean !== '*' && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      clean = 'https://' + clean;
    }
    if (clean !== '*') {
      try {
        const parsed = new URL(clean);
        clean = `${parsed.protocol}//${parsed.host}`;
      } catch (e) {
        clean = clean.replace(/\/+$/, '');
      }
    }
    try {
      const res = await fetch('/api/security/allowed-origins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin: clean })
      });
      if (res.ok) {
        const data = await res.json();
        renderAllowedOrigins(data.allowed_origins);
        if (newOriginInput) newOriginInput.value = '';
        showToast(`Authorized ${clean} to access Eclipse`, 'success', 2500);
      } else {
        const errData = await res.json().catch(() => ({}));
        showToast(errData.detail || 'Failed to add origin', 'error', 2500);
      }
    } catch (err) {
      showToast(`Error adding origin: ${err.message}`, 'error', 2500);
    }
  };

  if (addOriginBtn && newOriginInput) {
    addOriginBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleAddOrigin(newOriginInput.value);
    });
    newOriginInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddOrigin(newOriginInput.value);
      }
    });
  }

  if (presetOriginBtns) {
    presetOriginBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const orig = btn.getAttribute('data-origin');
        if (orig) handleAddOrigin(orig);
      });
    });
  }

  loadAllowedOrigins();

  // Gateway Custom API Key Management
  let currentGatewayKey = localStorage.getItem('eclipse_gateway_key') || 'Insom-Eclipse';

  const updateGatewayKeyDisplays = (key) => {
    currentGatewayKey = key;
    try {
      localStorage.setItem('eclipse_gateway_key', key);
    } catch (e) {}
    if (inputGatewayKey) inputGatewayKey.value = key;
    if (profileApikeyText) profileApikeyText.textContent = key;
    if (typeof updateClaudeCodeKeySnippet === 'function') {
      updateClaudeCodeKeySnippet(key);
    }
  };

  const loadGatewayKey = async () => {
    try {
      const res = await fetch('/api/security/gateway-key');
      if (res.ok) {
        const data = await res.json();
        if (data && data.gateway_key) {
          updateGatewayKeyDisplays(data.gateway_key);
        }
      }
    } catch (err) {
      console.warn('Failed to load gateway key:', err);
    }
  };

  const handleSaveGatewayKey = async (newKey) => {
    const key = (newKey || '').trim();
    if (!key) {
      showToast('API Key cannot be empty', 'error', 2000);
      return;
    }
    try {
      const res = await fetch('/api/security/gateway-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gateway_key: key })
      });
      if (res.ok) {
        const data = await res.json();
        updateGatewayKeyDisplays(data.gateway_key || key);
        showToast(`Gateway API Key saved: ${data.gateway_key || key}`, 'success', 2500);
      } else {
        showToast('Failed to save API key', 'error', 2500);
      }
    } catch (err) {
      showToast(`Error saving API key: ${err.message}`, 'error', 2500);
    }
  };

  const handleRotateGatewayKey = async () => {
    try {
      const res = await fetch('/api/security/gateway-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rotate' })
      });
      if (res.ok) {
        const data = await res.json();
        updateGatewayKeyDisplays(data.gateway_key);
        showToast(`Generated new Gateway API Key`, 'success', 2500);
      } else {
        showToast('Failed to generate key', 'error', 2500);
      }
    } catch (err) {
      showToast(`Error generating key: ${err.message}`, 'error', 2500);
    }
  };

  if (btnSaveGatewayKey && inputGatewayKey) {
    btnSaveGatewayKey.addEventListener('click', (e) => {
      e.stopPropagation();
      handleSaveGatewayKey(inputGatewayKey.value);
    });
    inputGatewayKey.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSaveGatewayKey(inputGatewayKey.value);
      }
    });
  }

  if (btnRotateGatewayKey) {
    btnRotateGatewayKey.addEventListener('click', (e) => {
      e.stopPropagation();
      handleRotateGatewayKey();
    });
  }

  if (btnCopyCustomGatewayKey) {
    btnCopyCustomGatewayKey.addEventListener('click', async (e) => {
      e.stopPropagation();
      const val = inputGatewayKey ? inputGatewayKey.value : currentGatewayKey;
      if (val) {
        const ok = await copyTextToClipboard(val);
        if (ok) showToast('Copied Gateway API Key to clipboard', 'success', 2000);
      }
    });
  }

  loadGatewayKey();

  // Clear Local Cache
  const clearCacheBtn = document.getElementById('btn-clear-local-cache');
  if (clearCacheBtn) {
    clearCacheBtn.addEventListener('click', () => {
      try {
        const keysToKeep = ['eclipse_user_avatar', 'eclipse_user_name', 'eclipse_theme', 'eclipse_theme_pref', 'eclipse_chat_font', 'eclipse_custom_instructions'];
        const saved = {};
        keysToKeep.forEach(k => {
          const val = localStorage.getItem(k);
          if (val) saved[k] = val;
        });
        localStorage.clear();
        Object.entries(saved).forEach(([k, v]) => localStorage.setItem(k, v));
        showToast('Local cache reset successfully', 'success', 2200);
      } catch (err) {
        showToast('Failed to reset cache', 'error', 2000);
      }
    });
  }

  // Gateway Endpoint Quick-Copy with animated feedback
  const dynamicOrigin = (window.location && window.location.origin && window.location.origin.startsWith('http'))
    ? window.location.origin
    : 'http://localhost:5000';
  const gatewayEndpointUrl = `${dynamicOrigin}/v1`;

  if (endpointTextEl) {
    endpointTextEl.textContent = gatewayEndpointUrl;
  }

  let copyResetTimer = null;
  const executeEndpointCopy = async (e) => {
    if (e) e.stopPropagation();
    const success = await copyTextToClipboard(gatewayEndpointUrl);
    if (success) {
      if (copyEndpointRow) copyEndpointRow.classList.add('copied');
      if (copyHintEl) copyHintEl.textContent = 'Copied!';
      const defaultIcon = copyEndpointRow ? copyEndpointRow.querySelector('.copy-default-icon') : null;
      const successIcon = copyEndpointRow ? copyEndpointRow.querySelector('.copy-success-icon') : null;
      if (defaultIcon) defaultIcon.style.display = 'none';
      if (successIcon) successIcon.style.display = 'inline-block';

      showToast(`Copied API endpoint: ${gatewayEndpointUrl}`, 'success', 2500);

      clearTimeout(copyResetTimer);
      copyResetTimer = setTimeout(() => {
        if (copyEndpointRow) copyEndpointRow.classList.remove('copied');
        if (copyHintEl) copyHintEl.textContent = 'Copy';
        if (defaultIcon) defaultIcon.style.display = 'inline-block';
        if (successIcon) successIcon.style.display = 'none';
      }, 2000);
    } else {
      showToast('Failed to copy endpoint to clipboard', 'error', 2500);
    }
  };

  if (copyEndpointRow) {
    copyEndpointRow.addEventListener('click', executeEndpointCopy);
    copyEndpointRow.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        executeEndpointCopy(e);
      }
    });
  }

  if (endpointCopyBtn) {
    endpointCopyBtn.addEventListener('click', executeEndpointCopy);
  }

  // API Key Quick-Copy
  let apiKeyResetTimer = null;
  const executeApiKeyCopy = async (e) => {
    if (e) e.stopPropagation();
    const apiKey = currentGatewayKey || 'sk-eclipse-local';
    const success = await copyTextToClipboard(apiKey);
    if (success) {
      if (apikeyCopyRow) apikeyCopyRow.classList.add('copied');
      if (apikeyCopyHint) apikeyCopyHint.textContent = 'Copied!';
      const defaultIcon = apikeyCopyRow ? apikeyCopyRow.querySelector('.copy-default-icon') : null;
      const successIcon = apikeyCopyRow ? apikeyCopyRow.querySelector('.copy-success-icon') : null;
      if (defaultIcon) defaultIcon.style.display = 'none';
      if (successIcon) successIcon.style.display = 'inline-block';

      showToast(`Copied Gateway API Key: ${apiKey}`, 'success', 2200);

      clearTimeout(apiKeyResetTimer);
      apiKeyResetTimer = setTimeout(() => {
        if (apikeyCopyRow) apikeyCopyRow.classList.remove('copied');
        if (apikeyCopyHint) apikeyCopyHint.textContent = 'Copy';
        if (defaultIcon) defaultIcon.style.display = 'inline-block';
        if (successIcon) successIcon.style.display = 'none';
      }, 2000);
    } else {
      showToast('Failed to copy API key to clipboard', 'error', 2500);
    }
  };

  if (apikeyCopyRow) {
    apikeyCopyRow.addEventListener('click', executeApiKeyCopy);
  }
  if (apikeyCopyBtn) {
    apikeyCopyBtn.addEventListener('click', executeApiKeyCopy);
  }

  // Capabilities & Inference Defaults - Reasoning Effort Custom Dropdown
  setupCustomDropdown(
    'reasoning-effort-select-wrap',
    'btn-reasoning-effort-select',
    'reasoning-effort-select-menu',
    'reasoning-effort-selected-label',
    'eclipse_reasoning_effort',
    'medium',
    (val, save) => {
      if (save) {
        showToast(`Reasoning effort set to ${val}`, 'info', 1600);
        window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
      }
    }
  );

  const tempSlider = document.getElementById('settings-temperature-slider');
  const tempVal = document.getElementById('settings-temperature-val');
  if (tempSlider && tempVal) {
    const savedTemp = localStorage.getItem('eclipse_default_temp') || '0.7';
    tempSlider.value = savedTemp;
    tempVal.textContent = parseFloat(savedTemp).toFixed(2);

    tempSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value).toFixed(2);
      tempVal.textContent = val;
      localStorage.setItem('eclipse_default_temp', val);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  const genuiToggle = document.getElementById('toggle-genui-artifacts');
  if (genuiToggle) {
    genuiToggle.checked = localStorage.getItem('eclipse_genui_enabled') !== 'false';
    genuiToggle.addEventListener('change', (e) => {
      localStorage.setItem('eclipse_genui_enabled', e.target.checked ? 'true' : 'false');
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  // Memory & Custom Instructions
  const customInstructionsArea = document.getElementById('settings-custom-instructions');
  const saveInstructionsBtn = document.getElementById('btn-save-custom-instructions');
  const identityToggle = document.getElementById('toggle-identity-awareness');

  if (customInstructionsArea) {
    customInstructionsArea.value = localStorage.getItem('eclipse_custom_instructions') || '';
  }

  if (saveInstructionsBtn && customInstructionsArea) {
    saveInstructionsBtn.addEventListener('click', () => {
      const instructions = customInstructionsArea.value.trim();
      localStorage.setItem('eclipse_custom_instructions', instructions);
      showToast('Custom instructions saved for AI models', 'success', 2200);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  if (identityToggle) {
    identityToggle.checked = localStorage.getItem('eclipse_identity_awareness') !== 'false';
    identityToggle.addEventListener('change', (e) => {
      localStorage.setItem('eclipse_identity_awareness', e.target.checked ? 'true' : 'false');
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
    });
  }

  // Dynamic Connectors Grid (Gemini)
  const connectorsGrid = document.getElementById('settings-connectors-grid');
  if (connectorsGrid && connectorsGrid.children.length === 0) {
    const providers = [
      { id: 'gemini', name: 'Google Gemini', meta: 'Gemini 4 Argon, 3.1 Pro, 3.8 Flash, Imagen & Veo', icon: '/static/icons/gemini.svg' },
      { id: 'glm', name: 'Zhipu AI (GLM)', meta: 'GLM 5.3, Thinking, Web Search, Flash, CogView 4', icon: '/static/icons/glm.svg' },
    ];

    connectorsGrid.innerHTML = providers.map(p => `
      <div class="claude-connector-card">
        <div class="claude-connector-icon">
          <img src="${p.icon}" width="24" height="24" alt="${p.name}" />
        </div>
        <div class="claude-connector-info">
          <div class="claude-connector-name">${p.name}</div>
          <div class="claude-connector-meta">${p.meta}</div>
        </div>
      </div>
    `).join('');
  }
}
window.initUserProfile = initClaudeSettings;
window.initClaudeSettings = initClaudeSettings;

// ===================================================================
// Navigation Tabs
// ===================================================================
function initNavigation() {
  const tabs = document.querySelectorAll('.nav-item');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const mobileToggle = document.getElementById('mobile-nav-toggle');

  const closeSidebar = () => {
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
  };

  const toggleSidebar = () => {
    if (sidebar) {
      const isOpen = sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('active', isOpen);
    }
  };

  if (mobileToggle) {
    mobileToggle.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleSidebar();
    });
  }

  if (overlay) {
    ['click', 'touchstart', 'pointerdown'].forEach(evt => {
      overlay.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeSidebar();
      }, { passive: false });
    });
  }

  // Also catch any click outside the sidebar when open on mobile
  document.addEventListener('click', (e) => {
    if (sidebar && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && !mobileToggle?.contains(e.target)) {
        closeSidebar();
      }
    }
  });

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      if (target) switchTab(target);
      if (window.innerWidth <= 1024) {
        closeSidebar();
      }
    });
  });

  document.body.dataset.activeTab = state.currentTab || 'playground';
  document.documentElement.dataset.activeTab = state.currentTab || 'playground';
}

function switchTab(tabId, updateHash = true) {
  state.currentTab = tabId;
  document.body.dataset.activeTab = tabId;
  document.documentElement.dataset.activeTab = tabId;

  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.tab === tabId);
  });

  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `pane-${tabId}`);
  });

  window.EclipseGlassDock?.updateActiveDockTab?.();
  window.EclipseGlassDock?.updateDockMode?.();

  // Push state to browser history so Back/Forward buttons work cleanly
  if (updateHash) {
    if (window.location.hash !== `#${tabId}`) {
      history.pushState({ tab: tabId }, '', `#${tabId}`);
    }
  }

  const heading = document.getElementById('page-heading');
  const subheading = document.getElementById('page-subheading');

  const titles = {
    control: {
      h: 'Control Center',
      sub: '',
    },
    limits: {
      h: 'Limits & Quotas',
      sub: '',
    },
    models: {
      h: 'Available Models',
      sub: '',
    },
    cookies: {
      h: 'Cookie Stacker & Accounts',
      sub: '',
    },
    playground: {
      h: 'Playground',
      sub: '',
    },
    tunnel: {
      h: 'Eclipse-Access',
      sub: '',
    },
    updates: {
      h: 'S-Update Logs',
      sub: '',
    },
  }[tabId] || { h: 'Eclipse', sub: '' };

  if (heading) heading.textContent = titles.h;
  if (subheading) {
    subheading.textContent = titles.sub;
    subheading.style.display = titles.sub ? 'block' : 'none';
  }

  try {
    if (tabId === 'control') {
      renderServices();
      fetchServices();
    }
    if (tabId === 'models') {
      if (!state.models || state.models.length === 0) {
        fetchModels();
      } else {
        renderModels();
      }
    }
    if (tabId === 'cookies') {
      loadCookiesTab();
      if (window.EclipseConnections?.show) window.EclipseConnections.show();
    }
    if (tabId === 'updates') {
      if (window.EclipseUpdates?.init) window.EclipseUpdates.init();
    }
    if (tabId === 'tunnel') {
      loadTunnelTab();
    } else {
      stopGlobeAnimation();
      stopUptimeTracker();
    }
  } catch (err) {
    console.error('Error rendering tab content:', err);
  }
}

// ===================================================================
// Control Center & Telemetry
// ===================================================================
async function fetchServices() {
  if (document.hidden && state.services && state.services.length > 0) return;
  try {
    const res = await fetch('/api/services');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.services = data.services || [];
    renderServices();
    updateSidebarStatus(data.hub);
  } catch (err) {
    console.error('Error fetching services:', err);
    const dot = document.getElementById('hub-dot');
    const text = document.getElementById('hub-status-text');
    if (dot) dot.className = 'status-dot offline';
    if (text) text.textContent = 'Gateway Offline';
  }
}

function renderServices() {
  const container = document.getElementById('providers-container');
  if (!container) return;

  const onlineCount = state.services.filter(s => s.running).length;
  const totalCount = state.services.length || 8;
  const activeBadge = document.getElementById('nav-active-count');
  if (activeBadge) activeBadge.textContent = `${onlineCount}/${totalCount} Active`;

  const providerIcons = {
    gemini: '/static/icons/gemini.svg',
    claude: '/static/icons/claude.svg',
    kimi: '/static/icons/kimi.svg',
    glm: '/static/icons/glm.svg',
    deepseek: '/static/icons/deepseek.svg',
    qwen: '/static/icons/qwen.svg',
    antigravity: '/static/icons/antigravity.svg',
    aistudio: '/static/icons/aistudio.svg',
    mimo: '/static/icons/mimo.svg',
  };

  const existingCards = container.querySelectorAll('.provider-card');
  const serviceIds = state.services.map(s => s.id).join(',');

  // Fast-path: in-place mutations if DOM cards match existing fleet (0 allocations, 0 reflow thrashing)
  if (existingCards.length === state.services.length && container._renderedIds === serviceIds) {
    state.services.forEach(srv => {
      const card = container.querySelector(`.provider-card[data-provider="${srv.id}"]`);
      if (!card) return;
      const isOnline = srv.running;
      const badge = card.querySelector('.provider-status-badge');
      if (badge) {
        const badgeClass = isOnline ? 'online' : 'offline';
        const badgeText = isOnline ? 'RUNNING' : 'STOPPED';
        if (badge.textContent !== badgeText) {
          badge.className = `provider-status-badge ${badgeClass}`;
          badge.textContent = badgeText;
        }
      }
      const statBoxes = card.querySelectorAll('.stat-box .stat-value');
      if (statBoxes[0]) statBoxes[0].textContent = `:${srv.port}`;
      if (statBoxes[1]) statBoxes[1].textContent = srv.pid || '—';
      if (statBoxes[2]) statBoxes[2].textContent = srv.latency_ms !== null ? srv.latency_ms + 'ms' : 'Offline';

      const actions = card.querySelector('.provider-card-actions');
      if (actions && card._lastRunning !== isOnline) {
        card._lastRunning = isOnline;
        actions.innerHTML = isOnline
          ? `<button class="btn btn-secondary btn-sm" onclick="restartService('${srv.id}')">Restart</button>
             <button class="btn btn-danger btn-sm" onclick="stopService('${srv.id}')">Stop</button>`
          : `<button class="btn btn-primary btn-sm" onclick="startService('${srv.id}')">Start</button>`;
      }
    });
    return;
  }

  container._renderedIds = serviceIds;
  container.innerHTML = state.services.map(srv => {
    const isOnline = srv.running;
    const badgeClass = isOnline ? 'online' : 'offline';
    const badgeText = isOnline ? 'RUNNING' : 'STOPPED';
    const iconUrl = providerIcons[srv.id] || '/logo.svg';

    return `
      <div class="provider-card" data-provider="${srv.id}">
        <div class="provider-card-top">
          <div class="provider-identity">
            <div class="provider-badge-icon">
              <img src="${iconUrl}" alt="${escapeHtml(srv.name)}" />
            </div>
            <div>
              <div class="provider-name">${escapeHtml(srv.name)}</div>
              <div class="provider-company">${escapeHtml(srv.badge)}</div>
            </div>
          </div>
          <span class="provider-status-badge ${badgeClass}">${badgeText}</span>
        </div>

        <div class="provider-stats-row">
          <div class="stat-box">
            <span class="stat-label">Port</span>
            <span class="stat-value">:${srv.port}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">PID</span>
            <span class="stat-value">${srv.pid || '—'}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Latency</span>
            <span class="stat-value">${srv.latency_ms !== null ? srv.latency_ms + 'ms' : 'Offline'}</span>
          </div>
        </div>

        <div class="provider-card-actions">
          ${isOnline
        ? `
                <button class="btn btn-secondary btn-sm" onclick="restartService('${srv.id}')">Restart</button>
                <button class="btn btn-danger btn-sm" onclick="stopService('${srv.id}')">Stop</button>
              `
        : `
                <button class="btn btn-primary btn-sm" onclick="startService('${srv.id}')">Start</button>
              `
      }
        </div>
      </div>
    `;
  }).join('');
}

function updateSidebarStatus(hub) {
  const dot = document.getElementById('hub-dot');
  const text = document.getElementById('hub-status-text');
  if (dot) {
    dot.className = hub && hub.running ? 'status-dot' : 'status-dot offline';
  }
  if (text) {
    text.textContent = hub && hub.running ? 'Gateway Online' : 'Gateway Offline';
  }
}

async function startService(id) {
  try {
    showToast(`Starting ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/start`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
    } else {
      showToast(data.message || 'Failed to start', 'error');
    }
    await fetchServices();
    setTimeout(fetchServices, 1000);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function stopService(id) {
  try {
    showToast(`Stopping ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/stop`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
    } else {
      showToast(data.message || 'Failed to stop', 'error');
    }
    await fetchServices();
    setTimeout(fetchServices, 800);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function restartService(id) {
  try {
    showToast(`Restarting ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/restart`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message || `Restarted ${id}`, 'success');
    } else {
      showToast(data.message || `Could not restart ${id}`, 'warning');
    }
    await fetchServices();
    setTimeout(fetchServices, 1000);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function startAllServices() {
  try {
    showToast('Starting all 7 providers...', 'info');
    const res = await fetch('/api/services/start_all', { method: 'POST' });
    const data = await res.json();
    showToast('All 7 providers started successfully.', 'success');
    await fetchServices();
    setTimeout(fetchServices, 1000);
    setTimeout(fetchServices, 2500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function stopAllServices() {
  try {
    showToast('Stopping all 7 providers...', 'info');
    const res = await fetch('/api/services/stop_all', { method: 'POST' });
    const data = await res.json();
    showToast('All providers stopped.', 'success');
    await fetchServices();
    setTimeout(fetchServices, 1000);
  } catch (err) {
    showToast(err.message, 'error');
  }
}



function renderLimits() {}

// ===================================================================
// Available Models Catalog
// ===================================================================
async function fetchModels() {
  try {
    const res = await fetch('/api/models');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.models = data.models || [];
    const modelBadge = document.getElementById('nav-model-count');
    if (modelBadge) modelBadge.textContent = `${state.models.length} Models`;

    // Ensure selectedModel is valid among available models
    const hasSelected = state.models.some(m => m.id.toLowerCase() === (state.selectedModel || '').toLowerCase());
    if (!hasSelected && state.models.length > 0) {
      const defaultChoice = state.models.find(m => m.id === 'gemini-3.8-flash') || state.models[0];
      state.selectedModel = defaultChoice.id;
      localStorage.setItem('eclipse_selected_model', state.selectedModel);
    }

    renderModels();
    renderCustomSelectOptions();
    renderParamModelSelectOptions();
    const label = document.getElementById('model-select-label');
    if (label) label.textContent = formatModelDisplayName(state.selectedModel);
    const topLabel = document.getElementById('claude-top-model-name');
    if (topLabel) topLabel.textContent = formatModelDisplayName(state.selectedModel);
    const inputModel = document.getElementById('input-model-name');
    if (inputModel) inputModel.textContent = formatModelDisplayName(state.selectedModel);
    const paramLabel = document.getElementById('param-model-selected-label');
    if (paramLabel) paramLabel.textContent = formatModelDisplayName(state.selectedModel);
  } catch (err) {
    console.error('Error fetching models:', err);
  }
}

const PROVIDER_METAS = {
  gemini: { name: 'Gemini', icon: '/static/icons/gemini.svg' },
};

let isScrollSpyLocked = false;
let scrollSpyUnlockTimer = null;

const PROVIDER_DISPLAY_NAMES = {
  all: 'All Models',
  gemini: 'Gemini',
};

function updateModelFilterUI(filter) {
  // Desktop pills
  const pills = document.querySelectorAll('#model-filter-pills .filter-btn');
  pills.forEach(b => {
    b.classList.toggle('active', b.dataset.filter === filter);
  });

  // Mobile dropdown label & option
  const dropdownLabel = document.getElementById('models-provider-dropdown-label');
  if (dropdownLabel) {
    dropdownLabel.textContent = PROVIDER_DISPLAY_NAMES[filter] || 'All Models';
  }
  const dropdownOptions = document.querySelectorAll('#models-provider-dropdown-menu .claude-select-option');
  dropdownOptions.forEach(opt => {
    opt.classList.toggle('selected', opt.dataset.filter === filter);
  });
}

function applyModelFilter(filter) {
  updateModelFilterUI(filter);

  if (filter === 'gemini') {
    const sec = document.getElementById('models-section-gemini');
    const viewport = document.querySelector('.panel-viewport');
    if (sec && viewport) {
      isScrollSpyLocked = true;
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      clearTimeout(scrollSpyUnlockTimer);
      scrollSpyUnlockTimer = setTimeout(() => {
        isScrollSpyLocked = false;
      }, 700);
      return;
    }
  }

  if (filter === 'all') {
    const viewport = document.querySelector('.panel-viewport');
    if (viewport) {
      isScrollSpyLocked = true;
      viewport.scrollTo({ top: 0, behavior: 'smooth' });
      clearTimeout(scrollSpyUnlockTimer);
      scrollSpyUnlockTimer = setTimeout(() => {
        isScrollSpyLocked = false;
      }, 700);
    }
  }

  renderModels();
}

function initModelFilters() {
  const pills = document.querySelectorAll('#model-filter-pills .filter-btn');
  pills.forEach(btn => {
    btn.addEventListener('click', () => {
      applyModelFilter(btn.dataset.filter);
    });
  });

  // Mobile custom provider dropdown options
  const dropdownOptions = document.querySelectorAll('#models-provider-dropdown-menu .claude-select-option');
  dropdownOptions.forEach(opt => {
    opt.addEventListener('click', (e) => {
      e.stopPropagation();
      const filter = opt.dataset.filter;
      applyModelFilter(filter);
      const wrap = document.getElementById('models-provider-dropdown-wrap');
      if (wrap) wrap.classList.remove('open');
      const menu = document.getElementById('models-provider-dropdown-menu');
      if (menu) menu.classList.remove('open');
    });
  });

  // Mobile sidebar drawer trigger
  const mobileSidebarBtn = document.getElementById('btn-models-mobile-sidebar');
  if (mobileSidebarBtn) {
    mobileSidebarBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.triggerHaptic?.(8);
      const dockToggle = document.getElementById('eclipse-sidebar-toggle');
      if (dockToggle) {
        dockToggle.click();
      } else {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar) sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
      }
    });
  }

  const searchInput = document.getElementById('model-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderModels();
    });
  }

  initModelsScrollSpy();
}

window.toggleModelsProviderDropdown = function(event) {
  if (event) event.stopPropagation();
  window.triggerHaptic?.(8);
  const wrap = document.getElementById('models-provider-dropdown-wrap');
  if (!wrap) return;
  const menu = document.getElementById('models-provider-dropdown-menu');
  const isOpen = wrap.classList.contains('open');
  document.querySelectorAll('.claude-custom-select-wrap.open').forEach(w => {
    if (w !== wrap) w.classList.remove('open');
  });
  wrap.classList.toggle('open', !isOpen);
  if (menu) menu.classList.toggle('open', !isOpen);
};

document.addEventListener('click', (e) => {
  const wrap = document.getElementById('models-provider-dropdown-wrap');
  if (wrap && wrap.classList.contains('open') && !wrap.contains(e.target)) {
    wrap.classList.remove('open');
    const menu = document.getElementById('models-provider-dropdown-menu');
    if (menu) menu.classList.remove('open');
  }
});

function initModelsScrollSpy() {
  const viewport = document.querySelector('.panel-viewport');
  if (!viewport || viewport._hasScrollSpyAttached) return;
  viewport._hasScrollSpyAttached = true;

  viewport.addEventListener('scroll', () => {
    if (isScrollSpyLocked) return;

    const activePane = document.querySelector('.tab-pane.active');
    if (!activePane || activePane.id !== 'pane-models') return;

    // Near top -> highlight 'all'
    if (viewport.scrollTop < 60) {
      const allBtn = document.querySelector('#model-filter-pills .filter-btn[data-filter="all"]');
      if (allBtn && !allBtn.classList.contains('active')) {
        updateModelFilterUI('all');
      }
      return;
    }

    const sections = document.querySelectorAll('.provider-models-section');
    if (!sections.length) return;

    const viewportRect = viewport.getBoundingClientRect();
    const probeY = viewportRect.top + 90;

    let currentSectionProvider = null;
    sections.forEach(sec => {
      const rect = sec.getBoundingClientRect();
      if (rect.top <= probeY && rect.bottom > probeY) {
        currentSectionProvider = sec.dataset.provider;
      }
    });

    if (!currentSectionProvider && sections.length > 0) {
      if (viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 30) {
        currentSectionProvider = sections[sections.length - 1].dataset.provider;
      }
    }

    if (currentSectionProvider) {
      const targetBtn = document.querySelector(`#model-filter-pills .filter-btn[data-filter="${currentSectionProvider}"]`);
      if (targetBtn && !targetBtn.classList.contains('active')) {
        updateModelFilterUI(currentSectionProvider);
      }
    }
  }, { passive: true });
}

function getModelVariantInfo(model) {
  const id = (model.id || '').toLowerCase();

  const patterns = [
    { regex: /-(?:thinking-search|think-search)$/i, label: 'Thinking + Search', order: 4 },
    { regex: /-(?:thinking|think)$/i, label: 'Thinking', order: 2 },
    { regex: /-search$/i, label: 'Search', order: 3 },
    { regex: /-extra-low$/i, label: 'Extra-Low', order: 4 },
    { regex: /-high$/i, label: 'High', order: 1 },
    { regex: /-medium$/i, label: 'Medium', order: 2 },
    { regex: /-low$/i, label: 'Low', order: 3 },
  ];

  for (const p of patterns) {
    const match = p.regex.exec(id);
    if (match) {
      const baseId = id.slice(0, match.index);
      return { baseId, label: p.label, order: p.order, isVariant: true };
    }
  }

  if (id === 'kimi-2.6-fast') {
    return { baseId: 'kimi-2.6', label: 'Fast', order: 1, isVariant: true };
  }

  return { baseId: id, label: 'Base', order: 1, isVariant: false };
}

function getCleanModelTitle(model, baseId) {
  let name = model.name || baseId;
  name = name.replace(/\s*\((?:High|Medium|Low|Extra-Low|Thinking|Search|Default)\)/ig, '');
  name = name.replace(/\b(?:High|Medium|Low|Extra-Low)\b/g, '');
  name = name.replace(/\s+(?:Thinking|Search|Thinking Search)$/ig, '');
  name = name.replace(/\s{2,}/g, ' ');
  return name.trim();
}

function groupModelsList(modelsList) {
  const groupsMap = new Map();

  modelsList.forEach(m => {
    const p = (m.provider || '').toLowerCase();
    const { baseId, label, order } = getModelVariantInfo(m);
    const key = `${p}::${baseId}`;

    if (!groupsMap.has(key)) {
      groupsMap.set(key, {
        provider: p,
        baseId: baseId,
        title: getCleanModelTitle(m, baseId),
        variants: []
      });
    }

    groupsMap.get(key).variants.push({
      label,
      order,
      model: m
    });
  });

  groupsMap.forEach(group => {
    group.variants.sort((a, b) => a.order - b.order);
  });

  return Array.from(groupsMap.values());
}

function renderGroupedModelCard(group, query = '') {
  const variants = group.variants;
  let activeVariant = variants[0];

  const matchSelected = variants.find(v => v.model.id.toLowerCase() === (state.selectedModel || '').toLowerCase());
  if (matchSelected) {
    activeVariant = matchSelected;
  } else if (query) {
    const qLower = query.toLowerCase();
    const matchQuery = variants.find(v =>
      v.label.toLowerCase().includes(qLower) ||
      v.model.id.toLowerCase().includes(qLower)
    );
    if (matchQuery) activeVariant = matchQuery;
  }

  const activeModel = activeVariant.model;
  const cardId = `mc-${group.provider}-${group.baseId.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
  const hasVariants = variants.length > 1;

  let variantSelectorHtml = '';
  if (hasVariants) {
    variantSelectorHtml = `
      <div class="claude-custom-select-wrap model-variant-select-wrap" id="variant-wrap-${cardId}">
        <button type="button" class="claude-custom-select-btn model-variant-select-btn" onclick="toggleModelVariantSelect('${cardId}', event)">
          <span class="claude-custom-select-text" id="variant-label-${cardId}">${escapeHtml(activeVariant.label)}</span>
          <svg class="claude-select-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
        <div class="claude-custom-select-menu model-variant-select-menu" role="listbox">
          ${variants.map(v => `
            <button type="button" class="claude-select-option ${v.model.id === activeModel.id ? 'selected' : ''}" onclick="selectModelCardVariant('${cardId}', '${escapeHtml(v.model.id)}', '${escapeHtml(v.label)}', event)">
              <span>${escapeHtml(v.label)}</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  return `
    <div class="model-card" id="${cardId}" data-active-id="${escapeHtml(activeModel.id)}">
      <div class="model-header">
        <div class="model-header-main">
          <div class="model-title"><span>${escapeHtml(group.title)}</span></div>
          <div class="model-id-badge" id="model-id-disp-${cardId}">${escapeHtml(activeModel.id)}</div>
        </div>
        ${variantSelectorHtml}
      </div>

      <p class="model-desc" id="model-desc-${cardId}">${escapeHtml(activeModel.description || '')}</p>

      <div class="model-card-footer">
        <button class="btn btn-secondary btn-sm btn-test-model" id="btn-test-${cardId}" onclick="selectAndTestModel('${escapeHtml(activeModel.id)}')">
          <span>Test in Playground</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
    </div>
  `;
}

window.toggleModelVariantSelect = function(cardId, event) {
  if (event) event.stopPropagation();
  window.triggerHaptic?.(8);
  const wrap = document.getElementById(`variant-wrap-${cardId}`);
  if (!wrap) return;

  const menu = wrap.querySelector('.claude-custom-select-menu');
  const isOpen = wrap.classList.contains('open');

  document.querySelectorAll('.model-variant-select-wrap.open').forEach(w => {
    if (w !== wrap) {
      w.classList.remove('open');
      w.querySelector('.claude-custom-select-menu')?.classList.remove('open');
    }
  });

  if (isOpen) {
    wrap.classList.remove('open');
    if (menu) menu.classList.remove('open');
  } else {
    wrap.classList.add('open');
    if (menu) menu.classList.add('open');
  }
};

window.selectModelCardVariant = function(cardId, modelId, variantLabel, event) {
  if (event) event.stopPropagation();
  window.triggerHaptic?.(8);

  const wrap = document.getElementById(`variant-wrap-${cardId}`);
  if (wrap) {
    wrap.classList.remove('open');
    const menu = wrap.querySelector('.claude-custom-select-menu');
    if (menu) menu.classList.remove('open');
    wrap.querySelectorAll('.claude-select-option').forEach(opt => {
      opt.classList.toggle('selected', opt.textContent.trim() === variantLabel);
    });
  }

  const labelEl = document.getElementById(`variant-label-${cardId}`);
  if (labelEl) labelEl.textContent = variantLabel;

  const idEl = document.getElementById(`model-id-disp-${cardId}`);
  if (idEl) idEl.textContent = modelId;

  const card = document.getElementById(cardId);
  if (card) card.dataset.activeId = modelId;

  const mData = state.models?.find(m => m.id === modelId);
  if (mData && mData.description) {
    const descEl = document.getElementById(`model-desc-${cardId}`);
    if (descEl) descEl.textContent = mData.description;
  }

  const btnTest = document.getElementById(`btn-test-${cardId}`);
  if (btnTest) {
    btnTest.setAttribute('onclick', `selectAndTestModel('${escapeHtml(modelId)}')`);
  }
};

if (!window._modelVariantSelectCloseAttached) {
  window._modelVariantSelectCloseAttached = true;
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.model-variant-select-wrap')) {
      document.querySelectorAll('.model-variant-select-wrap.open').forEach(w => {
        w.classList.remove('open');
        w.querySelector('.claude-custom-select-menu')?.classList.remove('open');
      });
    }
  });
}

function renderModels() {
  const container = document.getElementById('models-container');
  if (!container) return;

  const query = (document.getElementById('model-search')?.value || '').toLowerCase().trim();

  const filtered = state.models.filter(m => {
    if (query) {
      const matchName = (m.name || '').toLowerCase().includes(query);
      const matchId = (m.id || '').toLowerCase().includes(query);
      const matchDesc = (m.description || '').toLowerCase().includes(query);
      const matchCaps = (m.capabilities || []).some(c => c.toLowerCase().includes(query));
      if (!matchName && !matchId && !matchDesc && !matchCaps) return false;
    }
    return true;
  });

  const providerOrder = ['gemini'];
  const groupedByProvider = { gemini: [] };

  filtered.forEach(m => {
    const p = (m.provider || 'gemini').toLowerCase();
    if (!groupedByProvider[p]) groupedByProvider[p] = [];
    groupedByProvider[p].push(m);
  });

  let html = '';
  providerOrder.forEach(provider => {
    const list = groupedByProvider[provider] || [];
    if (list.length === 0) return;

    const cards = groupModelsList(list);
    if (cards.length === 0) return;

    const meta = PROVIDER_METAS[provider] || { name: 'Gemini', icon: '/static/icons/gemini.svg' };

    html += `
      <section class="provider-models-section" id="models-section-${provider}" data-provider="${provider}">
        <div class="provider-section-header">
          <div class="provider-section-title">
            <img src="${meta.icon}" class="provider-section-icon" alt="${meta.name}" onerror="this.style.display='none'" />
            <h3 class="provider-section-name">${escapeHtml(meta.name)}</h3>
          </div>
          <span class="provider-section-count">${cards.length} ${cards.length === 1 ? 'Model' : 'Models'}</span>
        </div>
        <div class="models-grid">
          ${cards.map(g => renderGroupedModelCard(g, query)).join('')}
        </div>
      </section>
    `;
  });

  if (!html) {
    if (!state.models || state.models.length === 0) {
      fetchModels();
    }
    html = `
      <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
        <p style="font-size: 16px; margin-bottom: 8px;">No models found matching your criteria</p>
        <span style="font-size: 13px;">Try changing the filter or clearing the search box.</span>
      </div>
    `;
  }

  container.innerHTML = html;
}

function selectAndTestModel(modelId) {
  if (!modelId) return;
  state.selectedModel = modelId;
  localStorage.setItem('eclipse_selected_model', modelId);
  window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
  if (typeof window.pushSettings === 'function') {
    window.pushSettings();
  }
  const label = document.getElementById('model-select-label');
  if (label) label.textContent = formatModelDisplayName(modelId);
  const topLabel = document.getElementById('claude-top-model-name');
  if (topLabel) topLabel.textContent = formatModelDisplayName(modelId);
  const topChip = document.getElementById('claude-top-model-chip');
  if (topChip) topChip.classList.remove('active');
  const inputModel = document.getElementById('input-model-name');
  if (inputModel) inputModel.textContent = formatModelDisplayName(modelId);
  const paramLabel = document.getElementById('param-model-selected-label');
  if (paramLabel) paramLabel.textContent = formatModelDisplayName(modelId);
  renderCustomSelectOptions();
  if (typeof loadModelSettings === 'function') {
    loadModelSettings(modelId);
  }
  switchTab('playground');
  showToast(`Selected model: ${formatModelDisplayName(modelId)}`, 'info');
  document.getElementById('chat-input')?.focus();
}

// ===================================================================
// Cookie Changer & Stacker Section
// ===================================================================
function initCookieTabs() {
  const tabs = document.querySelectorAll('#cookie-provider-tabs .provider-tab-btn');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeCookieProvider = btn.dataset.p;
      loadCookiesTab();
    });
  });

  const saveBtn = document.getElementById('btn-save-cookie');
  if (saveBtn) saveBtn.addEventListener('click', saveCookies);

  const exportBtn = document.getElementById('btn-export-cookies');
  if (exportBtn) exportBtn.addEventListener('click', exportAllCookies);

  const importBtn = document.getElementById('btn-import-cookies');
  const importInput = document.getElementById('import-file-input');
  if (importBtn && importInput) {
    importBtn.addEventListener('click', () => importInput.click());
    importInput.addEventListener('change', handleImportCookiesFile);
  }
}

const TOKEN_GUIDES = {
  gemini: {
    title: 'How to Connect Gemini Google Cookies',
    script: "(() => { const c = document.cookie; const p1 = (c.match(/(?:^|;\\s*)__Secure-1PSID=([^;]+)/) || [])[1]; const pt = (c.match(/(?:^|;\\s*)__Secure-1PSIDTS=([^;]+)/) || [])[1]; const sa = (c.match(/(?:^|;\\s*)(?:SAPISID|__Secure-1PAPISID)=([^;]+)/) || [])[1]; if (p1 && pt) { const r = '__Secure-1PSID=' + p1 + '; __Secure-1PSIDTS=' + pt + (sa ? '; SAPISID=' + sa : ''); if (typeof copy === 'function') copy(r); else if (navigator.clipboard) navigator.clipboard.writeText(r); console.log('%c[Eclipse] Gemini cookies copied!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ Gemini cookies copied! Paste into Eclipse.'); } else { console.clear(); console.log('%c[Eclipse] ⚡ EASIEST WAY:', 'color:#10b981;font-weight:bold;font-size:14px;', 'Use \"Auto-Fetch Local Session\" button in Eclipse Control Center — 0 manual steps!'); console.log('%c[Eclipse] 📋 FAST MANUAL WAY:', 'color:#f59e0b;font-weight:bold;font-size:13px;', 'Go to Network tab -> Right-click any \"StreamGenerate\" or \"batchexecute\" request -> Copy -> Copy as cURL (or Copy request headers) -> Paste into Eclipse.'); alert('⚡ Pro-Tip: Use the \"Auto-Fetch Live Gemini Session\" button in Eclipse Control Center to import your cookies with 1 click without manual copying!\\n\\nOr in DevTools: Switch to Network tab -> right click any request -> Copy as cURL -> paste into Eclipse.'); } })()",
    steps: [
      {
        num: '⚡',
        text: '<strong>One-Click Auto-Discovery (Zero Manual Copying):</strong><br>' +
              '<button type="button" class="btn btn-secondary btn-sm" id="btn-autofetch-gemini" style="margin-top: 8px; border: none; background: rgba(66,133,244,0.15); color: #4285F4; border-radius: 8px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;">' +
              '  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>' +
              '  <span>⚡ Auto-Fetch Live Gemini Session from Browser</span>' +
              '</button>' +
              '<div style="font-size: 11.5px; color: var(--text-muted); margin-top: 6px;">Automatically scans Chrome, Brave, Edge, & Firefox, extracts your live encrypted session cookies (__Secure-1PSID & __Secure-1PSIDTS), and stacks directly into the vault!</div>'
      },
      {
        num: '1',
        text: '<strong>Manual DevTools (Alternative):</strong><br>' +
              '1. On <a href="https://gemini.google.com" target="_blank" rel="noopener" class="token-guide-link">gemini.google.com</a>, press <kbd>F12</kbd> &rarr; switch to the <strong>Network</strong> tab.<br>' +
              '2. Send a message or refresh &rarr; right click any <code>StreamGenerate</code> or <code>batchexecute</code> request &rarr; <strong>Copy</strong> &rarr; <strong>Copy as cURL</strong>.<br>' +
              '3. Paste the entire cURL command into the box below (Eclipse automatically isolates and decrypts your Cookie header!).'
      },
      {
        num: '2',
        text: '<strong>Console Script (Alternative):</strong><br>' +
              'Click <strong>Copy Extraction Script</strong>, paste into DevTools Console, and press <kbd>Enter</kbd>.'
      }
    ]
  },
  claude: {
    title: 'How to Extract Claude SessionKey',
    script: "(() => { let k = ''; const m = document.cookie.match(/(?:^|;\\s*)sessionKey=([^;]+)/); if (m) k = m[1]; if (!k) { for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && v.includes('sk-ant-sid02')) { const sm = v.match(/sk-ant-sid02-[a-zA-Z0-9_-]+/); if (sm) { k = sm[0]; break; } } } } const r = k || document.cookie; if (r) { if (typeof copy === 'function') copy(r); else if (navigator.clipboard) navigator.clipboard.writeText(r); console.log('%c[Eclipse] Claude credential copied!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert(k ? '✓ Claude sessionKey copied to clipboard! Paste into Eclipse.' : '✓ Available cookies copied to clipboard! (If sessionKey is HttpOnly, copy sessionKey from Application > Cookies)'); } else { alert('No credentials found. Ensure you are logged into claude.ai'); } })()",
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://claude.ai" target="_blank" rel="noopener" class="token-guide-link">claude.ai</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> (or right-click &rarr; Inspect) and switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied <code>sessionKey</code> below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  kimi: {
    title: 'How to Extract Kimi JWT Refresh Tokens',
    script: "(() => { let t = localStorage.getItem('refresh_token') || localStorage.getItem('access_token'); if (!t) { for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && v.includes('ey') && v.length > 50) { try { const j = JSON.parse(v); t = j.refresh_token || j.access_token || j.token || v; } catch(_) { t = v; } break; } } } const tok = (t || '').replace(/^[\"']|[\"']$/g, '').trim(); if (tok) { if (typeof copy === 'function') copy(tok); else if (navigator.clipboard) navigator.clipboard.writeText(tok); console.log('%c[Eclipse] Kimi refresh_token copied to clipboard!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ Kimi token copied to clipboard! Paste it into Eclipse.'); } else { alert('Kimi token not found. Please log in on kimi.ai first.'); } })()",
    steps: [
      {
        num: '1',
        text: 'Log into <a href="https://kimi.ai" target="_blank" rel="noopener" class="token-guide-link">kimi.ai</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> &rarr; switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied token below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  glm: {
    title: 'How to Extract GLM (ChatGLM) Token',
    script: "(() => { let t = localStorage.getItem('chatglm_token') || localStorage.getItem('token'); if (!t) { for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && (v.includes('eyJ') || v.includes('Bearer'))) { try { const j = JSON.parse(v); t = j.token || j.access_token || v; } catch(_) { t = v; } break; } } } const tok = (t || '').replace(/^[\"']|[\"']$/g, '').replace(/^Bearer\\s+/i, '').trim(); if (tok) { if (typeof copy === 'function') copy(tok); else if (navigator.clipboard) navigator.clipboard.writeText(tok); console.log('%c[Eclipse] GLM token copied to clipboard!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ GLM token copied to clipboard! Paste it into Eclipse.'); } else { alert('GLM token not found. Please log in on chatglm.cn first.'); } })()",
    steps: [
      {
        num: '1',
        text: 'Log into <a href="https://chatglm.cn" target="_blank" rel="noopener" class="token-guide-link">chatglm.cn</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> &rarr; switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied token below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  deepseek: {
    title: 'How to Extract DeepSeek userToken',
    script: "(() => { let t = localStorage.getItem('userToken') || localStorage.getItem('token'); if (!t) { for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && v.includes('ey') && v.length > 50) { try { const j = JSON.parse(v); t = j.userToken || j.token || j.value || v; } catch(_) { t = v; } break; } } } const tok = (t || '').replace(/^[\"']|[\"']$/g, '').trim(); if (tok) { if (typeof copy === 'function') copy(tok); else if (navigator.clipboard) navigator.clipboard.writeText(tok); console.log('%c[Eclipse] DeepSeek userToken copied to clipboard!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ DeepSeek userToken copied to clipboard! Paste into Eclipse.'); } else { alert('DeepSeek token not found. Please log in on chat.deepseek.com first.'); } })()",
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://chat.deepseek.com" target="_blank" rel="noopener" class="token-guide-link">chat.deepseek.com</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> &rarr; switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied <code>userToken</code> below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  qwen: {
    title: 'How to Extract Qwen Bearer Token',
    script: "(() => { let t = localStorage.getItem('token') || localStorage.getItem('access_token'); if (!t) { for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && v.includes('eyJ')) { try { const j = JSON.parse(v); t = j.token || j.access_token || j.value || v; } catch(_) { t = v; } break; } } } const tok = (t || '').replace(/^[\"']|[\"']$/g, '').trim(); if (tok) { if (typeof copy === 'function') copy(tok); else if (navigator.clipboard) navigator.clipboard.writeText(tok); console.log('%c[Eclipse] Qwen token copied to clipboard!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ Qwen token copied to clipboard! Paste into Eclipse.'); } else { alert('Qwen token not found. Please log in on chat.qwen.ai first.'); } })()",
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://chat.qwen.ai" target="_blank" rel="noopener" class="token-guide-link">chat.qwen.ai</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> &rarr; switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied token below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  antigravity: {
    title: 'How to Connect Google Antigravity (AGY)',
    steps: [
      {
        num: '1',
        text: '<strong>1-Click Google OAuth Sign-In (Recommended for 1 or Multiple Accounts):</strong><br>' +
              '<div style="margin-top:9px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">' +
              '  <button type="button" class="btn btn-primary btn-sm" id="btn-oauth-login-antigravity" style="padding: 7px 15px; font-size: 12.5px; font-weight: 600; display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg, #ea4335 0%, #d97757 100%); border: none; border-radius: 8px; box-shadow: 0 2px 8px rgba(234,67,53,0.25); cursor: pointer; color: #fff;">' +
              '    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>' +
              '    <span>Connect Google Account</span>' +
              '  </button>' +
              '  <button type="button" class="btn btn-secondary btn-sm" id="btn-autofetch-antigravity" style="padding: 6px 12px; font-size: 11.5px; display: inline-flex; align-items: center; gap: 5px; cursor: pointer; background: rgba(255,255,255,0.08); border: none; color: var(--text-secondary); border-radius: 8px;">' +
              '    ⚡ Auto-Detect Local IDE' +
              '  </button>' +
              '</div>' +
              '<div style="font-size: 11.5px; color: var(--text-muted); margin-top: 7px; line-height: 1.45;">Click <strong>Connect Google Account</strong> to sign in. Repeat for each of your accounts (Account #1, #2, #3, #4) &mdash; each is automatically saved to your vault with quota failover!</div>'
      },
      {
        num: '2',
        text: '<strong>Zero Manual Token Expiration:</strong> When you authorize in the Google window, Eclipse automatically captures the OAuth session on port 51121, stores the refresh token into SQLite, and auto-refreshes access tokens every hour.'
      },
      {
        num: '3',
        text: '<strong>Manual Entry (Optional):</strong> If you already have a <code>refresh_token</code> (starts with <code>1//</code>) or full JSON credentials dump, you can still paste it into the box below and click <strong>Save & Stack</strong>.'
      }
    ]
  },
  aistudio: {
    title: 'How to Connect Google AI Studio (API Key)',
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener" class="token-guide-link">aistudio.google.com/app/apikey</a> with your Google Account.<br>' +
              '<a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener" class="btn btn-secondary btn-sm" style="display:inline-flex; align-items:center; gap:6px; margin-top:8px; text-decoration:none; border:none; background:rgba(255,255,255,0.08); border-radius:8px;">' +
              '  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>' +
              '  <span>Open AI Studio API Key Page</span>' +
              '</a>'
      },
      {
        num: '2',
        text: 'Click <strong>Create API key</strong> (or copy your existing key). AI Studio API keys start with <code>AIzaSy...</code>.'
      },
      {
        num: '3',
        text: 'Paste your API key into the box below and click <strong>Save & Stack</strong> &mdash; zero cookies or session tokens required!'
      }
    ]
  },
  mimo: {
    title: 'How to Connect Xiaomi MiMo AI Studio',
    script: "(() => { const c = document.cookie; if (c) { if (typeof copy === 'function') copy(c); else if (navigator.clipboard) navigator.clipboard.writeText(c); console.log('%c[Eclipse] Xiaomi cookies copied!', 'color:#10b981;font-weight:bold;font-size:13px;'); alert('✓ Xiaomi cookies copied to clipboard! Paste into Eclipse.'); } else { alert('No cookies found. Please log in on aistudio.xiaomimimo.com first.'); } })()",
    steps: [
      {
        num: '⚡',
        text: '<strong>One-Click Auto-Discovery:</strong> Click the button below to auto-fetch your live Xiaomi MiMo session directly from local browser cookies:<br><button class="btn btn-secondary btn-sm" id="btn-autofetch-mimo" style="margin-top: 8px; border: none; background: rgba(255,105,0,0.15); color: #FF6900; border-radius: 8px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> <span>Auto-Fetch Local Browser Token</span></button>'
      },
      {
        num: '1',
        text: 'Alternatively, sign in to <a href="https://aistudio.xiaomimimo.com" target="_blank" rel="noopener" class="token-guide-link">aistudio.xiaomimimo.com</a> with your Xiaomi Account.'
      },
      {
        num: '2',
        text: 'Press <kbd>F12</kbd> &rarr; switch to the <strong>Console</strong> tab.'
      },
      {
        num: '3',
        text: 'Click <strong>Copy Extraction Script</strong>, paste into Console, and hit <kbd>Enter</kbd>.'
      },
      {
        num: '4',
        text: 'Paste the copied cookies into the box below and click <strong>Save & Stack</strong>.'
      }
    ]
  }
};

async function loadCookiesTab() {
  try {
    const res = await fetch('/api/cookies');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.cookiesData = await res.json();
  } catch (err) {
    console.error('Error fetching cookies:', err);
  }

  // Update cross-device SQLite status badge
  let totalAccounts = 0;
  if (state.cookiesData) {
    Object.values(state.cookiesData).forEach(entry => {
      if (entry && Array.isArray(entry.accounts)) {
        totalAccounts += entry.accounts.length;
      }
    });
  }
  const syncBadge = document.getElementById('sync-db-status');
  if (syncBadge) {
    syncBadge.textContent = `${totalAccounts} Stacked`;
  }
  if (window.EclipseConnections?.show) window.EclipseConnections.show();

  const p = state.activeCookieProvider;
  const pData = state.cookiesData[p] || { accounts: [] };

  const title = document.getElementById('cookie-input-title');
  const desc = document.getElementById('cookie-input-desc');
  const textarea = document.getElementById('cookie-textarea');

  const meta = {
    claude: {
      title: 'Claude SessionKey Stacker',
      desc: 'Paste sessionKey strings (sk-ant-sid02-...). Stacks multiple sessions into the Eclipse Unified Vault (SQLite).',
      placeholder: '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',
    },
    kimi: {
      title: 'Kimi JWT Stacker',
      desc: 'Paste Kimi refresh token JWT (one per line). Stored securely in Eclipse Unified Vault (SQLite).',
      placeholder: 'eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...',
    },
    gemini: {
      title: 'Gemini Cookie Stacker',
      desc: 'Paste raw Google cookies containing __Secure-1PSID and __Secure-1PSIDTS (one per line).',
      placeholder: '__Secure-1PSID=...; __Secure-1PSIDTS=...',
    },
    glm: {
      title: 'GLM Token Stacker',
      desc: 'Paste Zhipu AI refresh tokens or localStorage dump (one per line). Stored securely in Eclipse Unified Vault (SQLite).',
      placeholder: 'Paste GLM token or localStorage dump...',
    },
    deepseek: {
      title: 'DeepSeek Token Stacker',
      desc: 'Paste DeepSeek userToken (JWT from chat.deepseek.com) or {"email": "...", "password": "..."}.',
      placeholder: 'userToken (Bearer ey...) or login credentials dump...',
    },
    qwen: {
      title: 'Qwen Token Stacker',
      desc: 'Paste Qwen Bearer token, session cookie string, or localStorage JSON (one per line).',
      placeholder: 'Bearer token or {"token": "..."} dump...',
    },
    antigravity: {
      title: 'Antigravity Account Stacker',
      desc: 'Paste Google OAuth credentials JSON (from oauth_creds.json), refresh_token, or Bearer access token.',
      placeholder: 'Paste Google OAuth JSON dump or refresh token...',
    },
    aistudio: {
      title: 'Google AI Studio API Key Stacker',
      desc: 'Paste your Google AI Studio API key (starts with AIzaSy...). No cookies or session tokens required.',
      placeholder: 'AIzaSy...',
    },
    mimo: {
      title: 'Xiaomi MiMo Account Stacker',
      desc: 'Paste Xiaomi MiMo cookies (serviceToken=...; xiaomichatbot_ph=...; passToken=...) or click Auto-Fetch.',
      placeholder: 'serviceToken=...; userId=...; xiaomichatbot_ph=...; passToken=...',
    },
  }[p] || { title: 'Account Stacker', desc: '', placeholder: '' };

  title.textContent = meta.title;
  desc.textContent = meta.desc;
  textarea.placeholder = meta.placeholder;
  textarea.value = '';

  // Render dynamic Token Extraction & Safety Guide
  const guideCard = document.getElementById('token-guide-card');
  const guide = TOKEN_GUIDES[p];

  if (!guide) {
    if (guideCard) guideCard.style.display = 'none';
  } else {
    if (guideCard) {
      guideCard.style.display = 'flex';
      const scriptBtnHtml = guide.script ? `
        <button type="button" class="btn-copy-script" id="btn-copy-console-script" title="Copy automatic extraction script for browser Console">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span>Copy Extraction Script</span>
        </button>
      ` : '';

      guideCard.innerHTML = `
        <div class="token-guide-header">
          <div class="token-guide-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--brand-primary)" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>${escapeHtml(guide.title)}</span>
          </div>
          ${scriptBtnHtml}
        </div>

        <div class="token-guide-steps">
          ${guide.steps.map(s => `
            <div class="token-step-item">
              <span class="token-step-num">${s.num}</span>
              <div>${s.text}</div>
            </div>
          `).join('')}
        </div>

      `;

      // Copy script button handler
      const btnCopyScript = document.getElementById('btn-copy-console-script');
      if (btnCopyScript && guide.script) {
        btnCopyScript.addEventListener('click', async (e) => {
          e.preventDefault();
          try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(guide.script);
            } else {
              const ta = document.createElement('textarea');
              ta.value = guide.script;
              ta.style.position = 'fixed';
              ta.style.opacity = '0';
              document.body.appendChild(ta);
              ta.focus();
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
            }
            btnCopyScript.classList.add('copied');
            const span = btnCopyScript.querySelector('span');
            const prevText = span ? span.textContent : 'Copy Extraction Script';
            if (span) span.textContent = '✓ Script Copied!';
            showToast('Extraction script copied! Paste it into browser Console (F12) and hit Enter.', 'success');
            setTimeout(() => {
              btnCopyScript.classList.remove('copied');
              if (span) span.textContent = prevText;
            }, 2500);
          } catch (err) {
            showToast('Failed to copy script: ' + err.message, 'error');
          }
        });
      }

      const btnOAuthAgy = document.getElementById('btn-oauth-login-antigravity');
      if (btnOAuthAgy) {
        btnOAuthAgy.addEventListener('click', async (e) => {
          e.preventDefault();
          const origHtml = btnOAuthAgy.innerHTML;
          btnOAuthAgy.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <span>Opening Google Sign-In...</span>
          `;
          btnOAuthAgy.disabled = true;
          try {
            const resp = await fetch('/api/antigravity/oauth/start', { method: 'POST' });
            const data = await resp.json();
            if (data.ok && data.url) {
              showToast('Google Sign-In opened. Select your account to link.', 'info');
              const authWin = window.open(data.url, 'GoogleOAuth', 'width=620,height=750,status=no,resizable=yes');
              
              const startTime = Date.now();
              let pollTimer = null;

              const cleanup = () => {
                if (pollTimer) clearInterval(pollTimer);
                window.removeEventListener('message', onMsg);
                btnOAuthAgy.innerHTML = origHtml;
                btnOAuthAgy.disabled = false;
              };

              const onMsg = async (ev) => {
                if (ev.data && ev.data.type === 'antigravity_oauth_success') {
                  cleanup();
                  showToast(`Google account (${ev.data.email || 'connected'}) stacked into vault!`, 'success');
                  await loadCookiesTab();
                }
              };
              window.addEventListener('message', onMsg);

              pollTimer = setInterval(async () => {
                if (Date.now() - startTime > 180000) {
                  cleanup();
                  return;
                }
                try {
                  const stResp = await fetch('/api/antigravity/oauth/status');
                  const stData = await stResp.json();
                  if (stData.latest && stData.latest.timestamp && (stData.latest.timestamp * 1000) >= (startTime - 2000)) {
                    cleanup();
                    showToast(`Google account (${stData.latest.email}) stacked into vault!`, 'success');
                    if (authWin && !authWin.closed) {
                      try { authWin.close(); } catch(_) {}
                    }
                    await loadCookiesTab();
                  }
                } catch (_) {}
              }, 1500);

            } else {
              showToast('Could not start OAuth: ' + (data.message || 'Unknown error'), 'error');
              btnOAuthAgy.innerHTML = origHtml;
              btnOAuthAgy.disabled = false;
            }
          } catch (err) {
            showToast('OAuth Error: ' + err.message, 'error');
            btnOAuthAgy.innerHTML = origHtml;
            btnOAuthAgy.disabled = false;
          }
        });
      }

      const btnAutoGemini = document.getElementById('btn-autofetch-gemini');
      if (btnAutoGemini) {
        btnAutoGemini.addEventListener('click', async (e) => {
          e.preventDefault();
          const origText = btnAutoGemini.innerHTML;
          btnAutoGemini.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Scanning Browsers...
          `;
          btnAutoGemini.disabled = true;
          try {
            const resp = await fetch('/api/gemini/autofetch', { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
              showToast(data.message || 'Gemini session auto-fetched & stacked!', 'success');
              if (data.cookie_string || data.token) {
                textarea.value = data.cookie_string || data.token;
              }
              await loadCookiesTab();
            } else {
              showToast(data.detail || data.message || 'No Gemini session found in local browser cookies.', 'warning');
            }
          } catch (err) {
            showToast('Auto-fetch error: ' + err.message, 'error');
          } finally {
            btnAutoGemini.innerHTML = origText;
            btnAutoGemini.disabled = false;
          }
        });
      }

      const btnAutoFetchAgy = document.getElementById('btn-autofetch-antigravity');
      if (btnAutoFetchAgy) {
        btnAutoFetchAgy.addEventListener('click', async (e) => {
          e.preventDefault();
          const origText = btnAutoFetchAgy.innerHTML;
          btnAutoFetchAgy.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Detecting...
          `;
          btnAutoFetchAgy.disabled = true;
          try {
            const resp = await fetch('/api/antigravity/autofetch', { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
              showToast(data.message || 'Antigravity account auto-detected!', 'success');
              if (data.token) {
                textarea.value = data.token;
              }
              await loadCookiesTab();
            } else {
              showToast(data.message || 'Could not auto-detect Antigravity credentials.', 'error');
            }
          } catch (err) {
            showToast('Auto-detect error: ' + err.message, 'error');
          } finally {
            btnAutoFetchAgy.innerHTML = origText;
            btnAutoFetchAgy.disabled = false;
          }
        });
      }

      const btnAutoMimo = document.getElementById('btn-autofetch-mimo');
      if (btnAutoMimo) {
        btnAutoMimo.addEventListener('click', async (e) => {
          e.preventDefault();
          const origText = btnAutoMimo.innerHTML;
          btnAutoMimo.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Scanning Browsers...
          `;
          btnAutoMimo.disabled = true;
          try {
            const resp = await fetch('/api/mimo/autofetch', { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
              showToast(data.message || 'Xiaomi MiMo session auto-fetched & stacked!', 'success');
              if (data.token) {
                textarea.value = data.token;
              }
              await loadCookiesTab();
            } else {
              showToast(data.detail || data.message || 'No Xiaomi MiMo session found in local browser cookies.', 'warning');
            }
          } catch (err) {
            showToast('Auto-fetch error: ' + err.message, 'error');
          } finally {
            btnAutoMimo.innerHTML = origText;
            btnAutoMimo.disabled = false;
          }
        });
      }
    }
  }

  // Render active stacked accounts
  const listContainer = document.getElementById('stacked-accounts-list');
  const accounts = pData.accounts || [];

  if (accounts.length === 0) {
    listContainer.innerHTML = `
      <div class="card" style="padding: 16px; color: var(--text-muted); text-align: center; font-size: 13px;">
        No active stacked accounts found for ${p.toUpperCase()}. Paste new credentials above to stack.
      </div>
    `;
    return;
  }

  listContainer.innerHTML = accounts.map((acc, idx) => {
    const label = acc.email || acc.name || acc.masked || `Account #${idx + 1}`;
    const sub = acc.plan ? `Plan: ${acc.plan.toUpperCase()}` : (acc.masked || 'Active Session');
    const ident = acc.identifier || acc.email || acc.sessionKey || acc.token || acc.raw || '';
    const cardId = `acc-card-${p}-${acc.id != null ? acc.id : idx}`;
    const badgeId = `acc-badge-${p}-${acc.id != null ? acc.id : idx}`;
    const descId = `acc-desc-${p}-${acc.id != null ? acc.id : idx}`;

    return `
      <div class="account-card" id="${cardId}">
        <div class="account-card-info">
          <div class="account-card-title">${escapeHtml(label)}</div>
          <div class="account-card-desc" id="${descId}" style="display:flex;align-items:center;gap:6px;">
            <span>${escapeHtml(sub)}</span>
            <span id="${badgeId}" style="display:inline-flex;align-items:center;gap:3px;font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px;background:rgba(255,255,255,0.07);color:var(--text-muted);">
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              Checking…
            </span>
          </div>
        </div>
        <div class="account-card-actions">
          <button class="btn-remove-acc" onclick="removeStackedAccount('${escapeHtml(p)}', ${Number(acc.id != null ? acc.id : idx)}, '${escapeHtml(ident)}')" title="Remove this account">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
            <span>Remove</span>
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Fire real-time token validation for providers that support it
  if (p === 'gemini') {
    _validateAccountsLive(p, accounts);
  } else {
    // For other providers just show DB status
    accounts.forEach((acc, idx) => {
      const badgeId = `acc-badge-${p}-${acc.id != null ? acc.id : idx}`;
      const badge = document.getElementById(badgeId);
      if (badge) {
        badge.innerHTML = '● STACKED';
        badge.style.background = 'rgba(34,197,94,0.12)';
        badge.style.color = '#4ade80';
        badge.style.animation = 'none';
      }
    });
  }
}

async function _validateAccountsLive(provider, accounts) {
  // Show spinner CSS if not already added
  if (!document.getElementById('spin-keyframes')) {
    const style = document.createElement('style');
    style.id = 'spin-keyframes';
    style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
    document.head.appendChild(style);
  }

  try {
    const res = await fetch(`/api/accounts/validate?provider=${encodeURIComponent(provider)}`);
    if (!res.ok) return;
    const data = await res.json();
    const validated = data.accounts || [];

    validated.forEach(vAcc => {
      const cardIndex = accounts.findIndex(a => (a.id != null ? a.id : -1) === (vAcc.id != null ? vAcc.id : -2));
      const idx = cardIndex >= 0 ? cardIndex : validated.indexOf(vAcc);
      const badgeId = `acc-badge-${provider}-${vAcc.id != null ? vAcc.id : idx}`;
      const badge = document.getElementById(badgeId);
      if (!badge) return;

      if (vAcc.valid) {
        let expLabel = '';
        if (vAcc.expires_at) {
          const d = new Date(vAcc.expires_at * 1000);
          expLabel = ` · exp ${d.toLocaleDateString()}`;
        }
        badge.innerHTML = `✓ Valid${expLabel}`;
        badge.style.background = 'rgba(34,197,94,0.12)';
        badge.style.color = '#4ade80';
      } else {
        badge.innerHTML = `✗ Expired`;
        badge.style.background = 'rgba(239,68,68,0.12)';
        badge.style.color = '#f87171';
        badge.title = vAcc.reason || 'Token expired or invalid';
        // Also dim the whole card
        const cardId = `acc-card-${provider}-${vAcc.id != null ? vAcc.id : idx}`;
        const card = document.getElementById(cardId);
        if (card) card.style.opacity = '0.55';
      }
    });
  } catch (e) {
    // Validation probe failed silently — leave badges as-is
  }
}

async function removeStackedAccount(provider, index, identifier) {
  if (!confirm(`Are you sure you want to remove this account from ${provider.toUpperCase()}?`)) {
    return;
  }

  try {
    showToast(`Removing account from ${provider.toUpperCase()}...`, 'info');
    const res = await fetch(`/api/cookies/${provider}/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: index, identifier: identifier, id: index }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
      await loadCookiesTab();

      // Restart daemon to apply removal if currently running
      const srv = state.services?.find(s => s.id === provider);
      if (srv && srv.running) {
        setTimeout(() => {
          showToast(`Restarting ${provider} daemon to apply changes...`, 'info');
          restartService(provider);
        }, 800);
      }
    } else {
      showToast(data.message || 'Failed to remove account', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function saveCookies() {
  const p = state.activeCookieProvider;
  const textarea = document.getElementById('cookie-textarea');
  const content = textarea.value.trim();

  if (!content) {
    showToast('Please enter credential content to save.', 'error');
    return;
  }

  try {
    showToast(`Saving credentials for ${p.toUpperCase()}...`, 'info');
    const res = await fetch(`/api/cookies/${p}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accounts: content }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
      if (data.warning) {
        setTimeout(() => showToast(data.warning, 'warning', 10000), 600);
      } else if (p === 'gemini' && content.includes('__Secure-1PSID') && !content.includes('__Secure-1PSIDTS')) {
        setTimeout(() => showToast('⚠️ Warning: __Secure-1PSIDTS was not found in your pasted cookie! Image generation strictly requires both __Secure-1PSID and __Secure-1PSIDTS.', 'warning', 10000), 600);
      }
      textarea.value = '';
      await loadCookiesTab();


      // Restart daemon to apply new credentials only if it is already running
      const srv = state.services?.find(s => s.id === p);
      if (srv && srv.running) {
        setTimeout(() => {
          showToast(`Restarting ${p} daemon to apply new credentials...`, 'info');
          restartService(p);
        }, 800);
      }
    } else {
      showToast(data.message || 'Failed to save', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function exportAllCookies() {
  try {
    showToast('Exporting credentials backup...', 'info');
    const res = await fetch('/api/cookies/export');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `eclipse_credentials_${dateStr}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Exported ${data.total_accounts || 0} accounts successfully!`, 'success');
  } catch (err) {
    showToast(`Export failed: ${err.message}`, 'error');
  }
}

async function handleImportCookiesFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    showToast('Reading credentials file...', 'info');
    const text = await file.text();
    const parsed = JSON.parse(text);

    showToast('Importing credentials to SQLite...', 'info');
    const res = await fetch('/api/cookies/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(parsed),
    });

    const data = await res.json();
    if (!res.ok || data.status !== 'ok') {
      throw new Error(data.message || data.detail || 'Import failed');
    }

    showToast(data.message || 'Imported accounts successfully!', 'success');
    await loadCookiesTab();
    fetchServices();
  } catch (err) {
    showToast(`Import error: ${err.message}`, 'error');
  } finally {
    event.target.value = '';
  }
}


// ===================================================================
// Model Display Formatter & Custom Select Component
// ===================================================================
function formatModelDisplayName(modelId) {
  if (!modelId) return 'Gemini 3.8 Flash';
  const found = state.models?.find(m => m.id.toLowerCase() === modelId.toLowerCase());
  if (found && found.name) {
    return found.name.replace(/^GPT[- ]/i, 'Gpt ').replace(/-/g, ' ');
  }
  return modelId
    .split(/[-_]/)
    .filter(Boolean)
    .map(token => {
      if (/^\d+(\.\d+)*$/.test(token)) return token;
      return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
    })
    .join(' ');
}

function initCustomSelect() {
  const trigger = document.getElementById('model-select-trigger');
  const popover = document.getElementById('model-select-popover');
  const searchInput = document.getElementById('model-filter-input');
  const topChip = document.getElementById('claude-top-model-chip');

  const label = document.getElementById('model-select-label');
  if (label) {
    label.textContent = formatModelDisplayName(state.selectedModel);
  }
  const topLabel = document.getElementById('claude-top-model-name');
  if (topLabel) {
    topLabel.textContent = formatModelDisplayName(state.selectedModel);
  }
  const inputModel = document.getElementById('input-model-name');
  if (inputModel) {
    inputModel.textContent = formatModelDisplayName(state.selectedModel);
  }

  function toggleModelPopover(e) {
    if (e) e.stopPropagation();
    window.triggerHaptic?.(8);
    const isOpen = popover.classList.toggle('open');
    if (trigger) trigger.classList.toggle('active', isOpen);
    if (topChip) topChip.classList.toggle('active', isOpen);
    if (isOpen) {
      renderCustomSelectOptions(searchInput ? searchInput.value.toLowerCase().trim() : '');
      if (searchInput) searchInput.focus();
    }
  }

  if (trigger) trigger.addEventListener('click', toggleModelPopover);
  if (topChip) topChip.addEventListener('click', toggleModelPopover);

  document.addEventListener('click', (e) => {
    if (!popover.contains(e.target) && (!trigger || !trigger.contains(e.target)) && (!topChip || !topChip.contains(e.target))) {
      popover.classList.remove('open');
      if (trigger) trigger.classList.remove('active');
      if (topChip) topChip.classList.remove('active');
    }
  });

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderCustomSelectOptions(searchInput.value.toLowerCase().trim());
    });
  }
}

function renderCustomSelectOptions(query = '') {
  const list = document.getElementById('select-options-list');
  if (!list) return;

  const modality = state.playgroundModality || 'all';

  const filtered = state.models.filter(m => {
    // Exclude voice, TTS, speech, and transcribe models from the normal model dropdown
    const isVoiceOrAudio = (m.capabilities && (m.capabilities.includes('tts') || m.capabilities.includes('speech') || m.capabilities.includes('audio') || m.capabilities.includes('transcribe') || m.capabilities.includes('voice'))) ||
      /(?:-tts\b|-live\b|-transcribe\b)/i.test(m.id) ||
      /(tts|speech|transcribe|real-time voice)/i.test(m.name || '');
    if (isVoiceOrAudio) return false;

    // Modality filter
    if (modality === 'image') {
      const isImg = (m.capabilities && (m.capabilities.includes('image') || m.capabilities.includes('image_generation'))) ||
        /(image|imagine|cogview|dall-e|flux|imagen|sdxl|wanx)/i.test(m.id) ||
        /(image|imagine|cogview|dall-e)/i.test(m.name);
      if (!isImg) return false;
    } else if (modality === 'video') {
      const isVid = (m.capabilities && m.capabilities.includes('video')) ||
        /(video|cogvideox|kling|sora|runway)/i.test(m.id) ||
        /(video|animation)/i.test(m.name);
      if (!isVid) return false;
    }

    if (!query) return true;
    return m.name.toLowerCase().includes(query) || m.id.toLowerCase().includes(query) || m.provider.toLowerCase().includes(query);
  });

  list.innerHTML = filtered.map(m => {
    const isSelected = m.id === state.selectedModel;
    return `
      <div class="select-option ${isSelected ? 'selected' : ''}" data-id="${escapeHtml(m.id)}">
        <div>
          <span style="font-weight: 600;">${escapeHtml(m.name)}</span>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">(${escapeHtml(m.provider)})</span>
        </div>
        ${m.locked ? '<span class="lock-badge locked" style="font-size: 9px;">LOCKED</span>' : ''}
      </div>
    `;
  }).join('');

  list.querySelectorAll('.select-option').forEach(opt => {
    opt.addEventListener('click', () => {
      window.triggerHaptic?.(8);
      const modelId = opt.dataset.id;
      state.selectedModel = modelId;
      localStorage.setItem('eclipse_selected_model', modelId);
      window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
      if (typeof window.pushSettings === 'function') {
        window.pushSettings();
      }
      const label = document.getElementById('model-select-label');
      if (label) label.textContent = formatModelDisplayName(modelId);
      const topLabel = document.getElementById('claude-top-model-name');
      if (topLabel) topLabel.textContent = formatModelDisplayName(modelId);
      const topChip = document.getElementById('claude-top-model-chip');
      if (topChip) topChip.classList.remove('active');
      const inputModel = document.getElementById('input-model-name');
      if (inputModel) inputModel.textContent = formatModelDisplayName(modelId);
      const paramLabel = document.getElementById('param-model-selected-label');
      if (paramLabel) paramLabel.textContent = formatModelDisplayName(modelId);
      document.getElementById('model-select-popover').classList.remove('open');
      const trigger = document.getElementById('model-select-trigger');
      if (trigger) trigger.classList.remove('active');
      window.dispatchEvent(new CustomEvent('eclipse-bottomsheet-change'));
      renderCustomSelectOptions();
      if (typeof loadModelSettings === 'function') {
        loadModelSettings(modelId);
      }
    });
  });
}

function selectModelFromParamsModal(modelId) {
  if (!modelId) return;
  state.selectedModel = modelId;
  localStorage.setItem('eclipse_selected_model', modelId);
  window.dispatchEvent(new CustomEvent('eclipse-settings-updated'));
  if (typeof window.pushSettings === 'function') {
    window.pushSettings();
  }

  // 1. Update Parameters Modal display
  const paramLabel = document.getElementById('param-model-selected-label');
  if (paramLabel) paramLabel.textContent = formatModelDisplayName(modelId);
  const paramInput = document.getElementById('param-model-select');
  if (paramInput) paramInput.value = modelId;
  const activeModelLabel = document.getElementById('param-active-model-name');
  if (activeModelLabel) activeModelLabel.textContent = modelId;

  // 2. Update Main Playground model selector & input model
  const mainLabel = document.getElementById('model-select-label');
  if (mainLabel) mainLabel.textContent = formatModelDisplayName(modelId);
  const topLabel = document.getElementById('claude-top-model-name');
  if (topLabel) topLabel.textContent = formatModelDisplayName(modelId);
  const topChip = document.getElementById('claude-top-model-chip');
  if (topChip) topChip.classList.remove('active');
  const inputModel = document.getElementById('input-model-name');
  if (inputModel) inputModel.textContent = formatModelDisplayName(modelId);

  // 3. Close the custom select menu
  const menu = document.getElementById('param-model-select-menu');
  if (menu) menu.classList.remove('open');
  const wrap = document.getElementById('param-model-select-wrap');
  if (wrap) wrap.classList.remove('open');
  const btn = document.getElementById('btn-param-model-select');
  if (btn) btn.setAttribute('aria-expanded', 'false');

  // 4. Re-render options in both selectors
  renderCustomSelectOptions();
  renderParamModelSelectOptions();

  // 5. Load model-specific parameters
  if (typeof loadModelSettings === 'function') {
    loadModelSettings(modelId);
  }
}

function renderParamModelSelectOptions(query = '') {
  const list = document.getElementById('param-model-options-list');
  if (!list) return;

  const currentModel = state.selectedModel || 'gemini-3.8-flash';
  const models = (state.models && state.models.length > 0) ? state.models : [
    { id: currentModel, name: formatModelDisplayName(currentModel), provider: 'gemini' }
  ];

  const q = (query || '').toLowerCase().trim();
  const filtered = models.filter(m => {
    // Exclude voice, TTS, speech, and transcribe models from parameters dropdown
    const isVoiceOrAudio = (m.capabilities && (m.capabilities.includes('tts') || m.capabilities.includes('speech') || m.capabilities.includes('audio') || m.capabilities.includes('transcribe') || m.capabilities.includes('voice'))) ||
      /(?:-tts\b|-live\b|-transcribe\b)/i.test(m.id) ||
      /(tts|speech|transcribe|real-time voice)/i.test(m.name || '');
    if (isVoiceOrAudio) return false;

    if (!q) return true;
    const nameMatch = m.name && m.name.toLowerCase().includes(q);
    const idMatch = m.id && m.id.toLowerCase().includes(q);
    const provMatch = m.provider && m.provider.toLowerCase().includes(q);
    return nameMatch || idMatch || provMatch;
  });

  if (filtered.length === 0) {
    list.innerHTML = `<div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 12px;">No models found</div>`;
    return;
  }

  list.innerHTML = filtered.map(m => {
    const isSelected = m.id === currentModel;
    return `
      <button type="button" class="claude-select-option ${isSelected ? 'active' : ''}" data-value="${escapeHtml(m.id)}" title="${escapeHtml(m.name || m.id)}">
        <div style="display: flex; flex-direction: column; align-items: flex-start; text-align: left; min-width: 0; flex: 1; padding-right: 6px;">
          <span style="font-weight: 550; font-size: 12.5px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 230px;">${escapeHtml(m.name || m.id)}</span>
          <span style="font-size: 10px; color: var(--text-muted); opacity: 0.85; font-family: var(--font-mono);">${escapeHtml(m.provider || 'ai')} &bull; ${escapeHtml(m.id)}</span>
        </div>
        <svg class="option-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
      </button>
    `;
  }).join('');

  list.querySelectorAll('.claude-select-option').forEach(opt => {
    opt.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const val = opt.getAttribute('data-value');
      selectModelFromParamsModal(val);
    });
  });
}

function initParamModelSelect() {
  const btn = document.getElementById('btn-param-model-select');
  const wrap = document.getElementById('param-model-select-wrap');
  const menu = document.getElementById('param-model-select-menu');
  const filterInput = document.getElementById('param-model-filter-input');

  const paramLabel = document.getElementById('param-model-selected-label');
  if (paramLabel) {
    paramLabel.textContent = formatModelDisplayName(state.selectedModel || 'gemini-3.8-flash');
  }

  if (!btn || !wrap || !menu) return;

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();

    // Close any other open claude-custom-select-menu
    document.querySelectorAll('.claude-custom-select-menu.open').forEach(m => {
      if (m !== menu) {
        m.classList.remove('open');
        m.closest('.claude-custom-select-wrap')?.classList.remove('open');
      }
    });

    const isOpen = menu.classList.toggle('open');
    wrap.classList.toggle('open', isOpen);
    btn.setAttribute('aria-expanded', String(isOpen));

    if (isOpen) {
      renderParamModelSelectOptions(filterInput ? filterInput.value : '');
      if (filterInput) {
        filterInput.focus();
      }
    }
  });

  if (filterInput) {
    filterInput.addEventListener('input', () => {
      renderParamModelSelectOptions(filterInput.value);
    });
    filterInput.addEventListener('click', (e) => e.stopPropagation());
    filterInput.addEventListener('keydown', (e) => e.stopPropagation());
  }

  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) {
      menu.classList.remove('open');
      wrap.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    }
  });
}

// ===================================================================
// Interactive Playground with Rich Media & Motion Graphics
// ===================================================================

let currentLightboxSrc = null;

function openMediaLightbox(src, type = 'image', caption = '') {
  const modal = document.getElementById('playground-lightbox');
  const box = document.getElementById('lightbox-content-box');
  if (!modal || !box) return;

  currentLightboxSrc = src;
  box.innerHTML = `<img src="${escapeHtml(safeMediaUrl(src))}" alt="${escapeHtml(caption || 'Generated Media')}" />`;
  modal.classList.add('open');
}

function closeMediaLightbox() {
  const modal = document.getElementById('playground-lightbox');
  if (modal) modal.classList.remove('open');
  currentLightboxSrc = null;
}

function downloadMediaFile(src, filename) {
  const safeSrc = safeMediaUrl(src);
  if (!safeSrc) return;
  const link = document.createElement('a');
  link.href = safeSrc;
  link.download = filename || 'download';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast('Downloading media file...', 'info');
}

async function copyMediaToClipboard(src) {
  try {
    if (src.startsWith('data:image/')) {
      const resp = await fetch(src);
      const blob = await resp.blob();
      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob })
      ]);
      showToast('Image copied to clipboard!', 'success');
      return;
    }
    await navigator.clipboard.writeText(src);
    showToast('Image link copied to clipboard!', 'success');
  } catch (err) {
    await navigator.clipboard.writeText(src);
    showToast('Copied media URL to clipboard!', 'success');
  }
}

function detectQueryModality(modelId, promptText) {
  if (state.playgroundModality === 'image') return 'image';
  if (state.playgroundModality === 'video') return 'video';

  const m = (modelId || '').toLowerCase();
  const text = (promptText || '').toLowerCase();
  const modelInfo = (state.models || []).find(x => x.id === modelId);
  const caps = modelInfo?.capabilities || [];

  if (
    caps.includes('video') ||
    /(video|veo|cogvideox|kling|sora|runway)/i.test(m) ||
    /(\bgenerate\b|\bmake\b|\bcreate\b|\brender\b).*(\bvideo\b|\banimation\b|\bclip\b|\bmp4\b|\bmovie\b)/i.test(text)
  ) {
    return 'video';
  }

  if (
    caps.includes('image') ||
    caps.includes('image_generation') ||
    /(image|imagine|dall-e|cogview|flux|imagen|sdxl|wanx|banana)/i.test(m) ||
    /(\bgenerate\b|\bmake\b|\bcreate\b|\bdraw\b|\bpaint\b|\brender\b).*(\bimage\b|\bimg\b|\bpicture\b|\bphoto\b|\billustration\b|\bart\b|\bwallpaper\b|\bposter\b|\bapple\b)/i.test(text)
  ) {
    return 'image';
  }

  return 'text';
}

function detectImageAspectRatio(promptText) {
  const p = (promptText || '').toLowerCase();

  // 1. Explicit numeric aspect ratios take highest precedence
  if (/(?:^|\D)16\s*[:/x]\s*9(?:\D|$)/i.test(p)) {
    return { ratio: '16 / 9', maxWidth: '512px', isDefault: false };
  }
  if (/(?:^|\D)9\s*[:/x]\s*16(?:\D|$)/i.test(p)) {
    return { ratio: '9 / 16', maxWidth: '300px', isDefault: false };
  }
  if (/(?:^|\D)4\s*[:/x]\s*3(?:\D|$)/i.test(p)) {
    return { ratio: '4 / 3', maxWidth: '480px', isDefault: false };
  }
  if (/(?:^|\D)3\s*[:/x]\s*4(?:\D|$)/i.test(p)) {
    return { ratio: '3 / 4', maxWidth: '360px', isDefault: false };
  }
  if (/(?:^|\D)2\s*[:/x]\s*1(?:\D|$)/i.test(p)) {
    return { ratio: '2 / 1', maxWidth: '520px', isDefault: false };
  }
  if (/(?:^|\D)1\s*[:/x]\s*2(?:\D|$)/i.test(p)) {
    return { ratio: '1 / 2', maxWidth: '260px', isDefault: false };
  }
  if (/(?:^|\D)1\s*[:/x]\s*1(?:\D|$)/i.test(p)) {
    return { ratio: '1 / 1', maxWidth: '440px', isDefault: false };
  }

  // 2. Generic semantic format descriptors
  if (/\b(?:widescreen|landscape|wide|horizontal)\b/i.test(p)) {
    return { ratio: '16 / 9', maxWidth: '512px', isDefault: false };
  }
  if (/\b(?:portrait|vertical|story|reel|tiktok)\b/i.test(p)) {
    return { ratio: '9 / 16', maxWidth: '300px', isDefault: false };
  }
  if (/\b(?:panoramic|banner|header|ultrawide)\b/i.test(p)) {
    return { ratio: '2 / 1', maxWidth: '520px', isDefault: false };
  }
  if (/\b(?:square)\b/i.test(p)) {
    return { ratio: '1 / 1', maxWidth: '440px', isDefault: false };
  }

  // 3. Default is strictly 1:1 square
  return { ratio: '1 / 1', maxWidth: '440px', isDefault: true };
}

/**
 * High-Definition Real-Time Fluid Simulation (WebGL GPU Navier-Stokes & Curl Advection)
 * Renders at full Retina/display native resolution (zero pixelation/blockiness).
 * Autonomously billows and swirls without user controls.
 * - Light theme: Pure white #ffffff background with #d97757 terracotta and white fluid flowing and merging.
 * - Dark theme: Dark obsidian #0d0c0b background with glowing terracotta streams.
 */
function startCanvasFluidSimulation(canvas, progressPill) {
  let isRunning = true;
  let animId = null;

  // Progress counter simulation (as shown in Image 1: "19%", etc.)
  let progressPct = 12;
  const progressTimer = setInterval(() => {
    if (!isRunning) return;
    if (progressPct < 92) {
      progressPct += Math.floor(Math.random() * 6) + 3;
      if (progressPct > 92) progressPct = 92;
      if (progressPill) progressPill.textContent = `${progressPct}%`;
    }
  }, 450);

  const vsSource = `
    attribute vec2 a_position;
    void main() {
      gl_Position = vec4(a_position, 0.0, 1.0);
    }
  `;

  const fsSource = `
    precision highp float;
    uniform vec2 u_resolution;
    uniform float u_time;
    uniform float u_is_dark;

    void main() {
      vec2 res = max(u_resolution, vec2(1.0, 1.0));
      vec2 p = (gl_FragCoord.xy * 2.0 - res) / min(res.x, res.y);
      float t = u_time * 0.55;

      // Harmonic rotating vortex currents: advect, stretch, and fold the fluid coordinates
      for (int i = 1; i <= 4; i++) {
        float fi = float(i);
        vec2 center = vec2(
          sin(t * 0.35 * fi + fi * 1.5) * 0.45,
          cos(t * 0.30 * fi + fi * 0.8) * 0.45
        );
        vec2 delta = p - center;
        float dist = length(delta);
        float angle = atan(delta.y, delta.x);

        // Smooth tangential vortex flow + gentle radial current (100% continuous, zero noise hash)
        float strength = 0.28 / (1.0 + dist * 2.2);
        p.x += sin(angle * 2.0 + dist * 3.2 - t * 0.7 * fi) * strength;
        p.y += cos(angle * 2.0 - dist * 3.2 + t * 0.6 * fi) * strength;
      }

      // Smooth liquid interference currents (creamy continuous waves, zero TV grain)
      float w1 = sin(p.x * 2.6 + sin(p.y * 2.0 + t * 0.5)) * cos(p.y * 2.4 - sin(p.x * 1.6 - t * 0.4));
      float w2 = sin(length(p) * 3.8 - t * 0.9) * 0.5;
      float density = clamp((w1 + w2) * 0.55 + 0.5, 0.0, 1.0);

      // Buttery-smooth fluid boundaries
      float fluid = smoothstep(0.22, 0.78, density);
      float detail = smoothstep(0.32, 0.68, sin(p.x * 4.2 - p.y * 3.5 + t * 0.8) * 0.5 + 0.5);

      vec3 color;
      if (u_is_dark > 0.5) {
        // DARK THEME: UI background color #000000 with glowing #d97757 terracotta streams
        vec3 bgDark = vec3(0.0, 0.0, 0.0);
        vec3 terra = vec3(0.851, 0.467, 0.341); // #d97757
        vec3 peach = vec3(0.988, 0.68, 0.56);
        vec3 stream = mix(terra, peach, detail * 0.5);
        color = mix(bgDark, stream, fluid);
      } else {
        // LIGHT THEME: Pure white #ffffff and whitish fluid (zero dark/black!)
        vec3 pureWhite = vec3(1.0, 1.0, 1.0);
        vec3 softWhite = vec3(0.985, 0.980, 0.975);
        vec3 terracotta = vec3(0.851, 0.467, 0.341); // #d97757
        vec3 deepTerra = vec3(0.78, 0.38, 0.26);

        vec3 terraStream = mix(terracotta, deepTerra, detail * 0.38);

        // Terracotta and white fluids folding, swirling, and merging together
        float whiteMerge = smoothstep(0.35, 0.74, cos(p.y * 3.2 + p.x * 2.4 - t * 0.75) * 0.5 + 0.5);
        vec3 mergedFluid = mix(terraStream, softWhite, whiteMerge * 0.85);

        // Fluid stream over pure white background
        color = mix(pureWhite, mergedFluid, fluid);
      }

      gl_FragColor = vec4(color, 1.0);
    }
  `;

  // Helper to reliably check theme from documentElement
  function isThemeDark() {
    const theme = document.documentElement.getAttribute('data-theme') ||
                  document.body.getAttribute('data-theme');
    return theme !== 'light';
  }

  // Try WebGL first for full native hardware resolution (zero pixelation!)
  let gl = null;
  try {
    gl = canvas.getContext('webgl', { antialias: true, alpha: false, depth: false }) ||
         canvas.getContext('experimental-webgl', { antialias: true, alpha: false, depth: false });
  } catch (e) {
    gl = null;
  }

  if (gl) {
    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, vsSource);
    gl.compileShader(vs);

    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, fsSource);
    gl.compileShader(fs);

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.useProgram(program);

      const posBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([
          -1, -1,
           1, -1,
          -1,  1,
          -1,  1,
           1, -1,
           1,  1
        ]),
        gl.STATIC_DRAW
      );

      const aPos = gl.getAttribLocation(program, 'a_position');
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

      const uRes = gl.getUniformLocation(program, 'u_resolution');
      const uTime = gl.getUniformLocation(program, 'u_time');
      const uDark = gl.getUniformLocation(program, 'u_is_dark');

      const startTime = performance.now();

      function renderGL() {
        if (!isRunning) return;

        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.floor((canvas.clientWidth || 440) * dpr);
        const h = Math.floor((canvas.clientHeight || 440) * dpr);

        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
          gl.viewport(0, 0, w, h);
        }

        const elapsed = (performance.now() - startTime) * 0.001;
        const isDark = isThemeDark() ? 1.0 : 0.0;

        gl.uniform2f(uRes, canvas.width, canvas.height);
        gl.uniform1f(uTime, elapsed);
        gl.uniform1f(uDark, isDark);

        gl.drawArrays(gl.TRIANGLES, 0, 6);

        animId = requestAnimationFrame(renderGL);
      }

      animId = requestAnimationFrame(renderGL);

      return {
        finish() {
          isRunning = false;
          clearInterval(progressTimer);
          if (animId) cancelAnimationFrame(animId);
          if (progressPill) progressPill.textContent = '100%';
          try {
            gl.deleteProgram(program);
            gl.deleteShader(vs);
            gl.deleteShader(fs);
            gl.deleteBuffer(posBuffer);
          } catch (_) {}
        },
        updateProgress(pct) {
          progressPct = pct;
          if (progressPill) progressPill.textContent = `${pct}%`;
        }
      };
    }
  }

  // Smooth Canvas 2D Fallback if WebGL is unavailable
  const ctx = canvas.getContext('2d');
  const startTime2D = performance.now();

  function render2D() {
    if (!isRunning) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = (canvas.clientWidth || 440) * dpr;
    const h = (canvas.clientHeight || 440) * dpr;

    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    const t = (performance.now() - startTime2D) * 0.001;
    const isDark = isThemeDark();

    // Pure white in light mode, pitch black #000000 in dark mode
    ctx.fillStyle = isDark ? '#000000' : '#ffffff';
    ctx.fillRect(0, 0, w, h);

    // Render smooth layered fluid plumes in #d97757
    const cx = w * 0.5 + Math.sin(t * 0.6) * (w * 0.15);
    const cy = h * 0.5 + Math.cos(t * 0.5) * (h * 0.15);
    const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, w * 0.45);
    grad.addColorStop(0, '#d97757');
    grad.addColorStop(0.6, isDark ? 'rgba(217, 119, 87, 0.65)' : 'rgba(217, 119, 87, 0.45)');
    grad.addColorStop(1, isDark ? 'rgba(13, 12, 11, 0)' : 'rgba(255, 255, 255, 0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, w * 0.45, 0, Math.PI * 2);
    ctx.fill();

    animId = requestAnimationFrame(render2D);
  }

  animId = requestAnimationFrame(render2D);

  return {
    finish() {
      isRunning = false;
      clearInterval(progressTimer);
      if (animId) cancelAnimationFrame(animId);
      if (progressPill) progressPill.textContent = '100%';
    },
    updateProgress(pct) {
      progressPct = pct;
      if (progressPill) progressPill.textContent = `${pct}%`;
    }
  };
}

function createThinkingLoader(modality, promptText) {
  const container = document.createElement('div');
  let updateProgress = () => {};
  let finish = () => {};

  if (modality === 'image') {
    // 1. IMAGE LOADER: Authentic HTML5 Canvas Fluid Simulation (Navier-Stokes) with aspect ratio & progress pill
    const aspect = detectImageAspectRatio(promptText);
    container.className = 'image-gen-loader';
    container.style.width = aspect.maxWidth;

    container.innerHTML = `
      <div class="image-gen-header">
        <span class="image-gen-title">Creating image</span>
      </div>
      <div class="image-gen-viewport" style="aspect-ratio: ${aspect.ratio};">
        <canvas class="image-gen-canvas"></canvas>
        <div class="image-gen-progress-pill">12%</div>
      </div>
    `;

    const canvas = container.querySelector('.image-gen-canvas');
    const pill = container.querySelector('.image-gen-progress-pill');
    const sim = startCanvasFluidSimulation(canvas, pill);

    return {
      el: container,
      updateProgress(pct) {
        sim.updateProgress(pct);
      },
      finish() {
        sim.finish();
      },
    };

  } else if (modality === 'video') {
    // 2. VIDEO LOADER: Cinematic 16:9 Frame Scanline with Sprockets & HUD
    container.className = 'video-gen-loader';
    container.innerHTML = `
      <div class="media-gen-header">
        <div class="media-gen-title-wrap">
          <span style="color: #c084fc; display: flex;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="23 7 16 12 23 17 23 7"></polygon>
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
            </svg>
          </span>
          <span class="media-gen-title">Generating video</span>
        </div>
        <span class="media-gen-subtitle" style="color: #c084fc;">Interpolating keyframes...</span>
      </div>
      <div class="cinematic-frame">
        <div class="film-perforations"></div>
        <div class="cinematic-canvas">
          <div class="video-scanline"></div>
          <span class="video-hud-res">720P • 24FPS</span>
          <div class="video-hud-rec">
            <span class="rec-dot"></span> REC
          </div>
          <svg class="video-vectors-svg" viewBox="0 0 320 120" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="vidWaveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#a855f7" stop-opacity="0.3"/>
                <stop offset="50%" stop-color="#38bdf8" stop-opacity="0.9"/>
                <stop offset="100%" stop-color="#a855f7" stop-opacity="0.3"/>
              </linearGradient>
            </defs>
            <line x1="0" y1="60" x2="320" y2="60" stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4 4" />
            <path d="M 20 60 Q 60 20, 100 60 T 180 60 T 260 60 T 300 60" fill="none" stroke="url(#vidWaveGrad)" stroke-width="2">
              <animate attributeName="d" dur="2.5s" repeatCount="indefinite"
                values="M 20 60 Q 60 20, 100 60 T 180 60 T 260 60 T 300 60;
                        M 20 60 Q 60 90, 100 60 T 180 60 T 260 60 T 300 60;
                        M 20 60 Q 60 20, 100 60 T 180 60 T 260 60 T 300 60" />
            </path>
            <polygon points="100,55 105,60 100,65 95,60" fill="#38bdf8" />
            <polygon points="180,53 187,60 180,67 173,60" fill="#c084fc" />
            <polygon points="260,55 265,60 260,65 255,60" fill="#38bdf8" />
          </svg>
        </div>
        <div class="film-perforations"></div>
      </div>
      <div class="gen-progress-pill video-pill">
        <span class="gen-progress-num">0%</span>
      </div>
    `;

    const pillNum = container.querySelector('.gen-progress-num');
    let progress = 0;
    const startTime = Date.now();

    timerId = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      if (elapsed < 3) {
        progress = Math.min(35, Math.round((elapsed / 3) * 35));
      } else if (elapsed < 8) {
        progress = Math.min(78, 35 + Math.round(((elapsed - 3) / 5) * 43));
      } else {
        progress = Math.min(97, 78 + Math.round(((elapsed - 8) / 8) * 19));
      }
      pillNum.textContent = `${progress}%`;
    }, 140);

    updateProgress = (p) => {
      progress = Math.max(progress, p);
      pillNum.textContent = `${progress}%`;
    };

    finish = () => {
      clearInterval(timerId);
      pillNum.textContent = '100%';
    };

  } else {
    // 3. TEXT / REASONING LOADER: Neural Orbital Spinner & Live Timer
    container.className = 'text-thinking-loader';
    const isDeepReasoning = /(deepseek-r1|reasoner|o1|o3|think)/i.test(state.selectedModel);

    container.innerHTML = `
      <div class="neural-orbital-spinner">
        <div class="orbital-ring orbital-ring-outer"></div>
        <div class="orbital-ring orbital-ring-inner"></div>
      </div>
      <div class="thinking-text-container">
        <span class="thinking-main-label">${isDeepReasoning ? 'Reasoning deeply' : 'Thinking'}</span>
        <span class="thinking-timer-pill">(0.0s)</span>
        <span class="thinking-wave-bars">
          <span class="thinking-wave-bar"></span>
          <span class="thinking-wave-bar"></span>
          <span class="thinking-wave-bar"></span>
          <span class="thinking-wave-bar"></span>
        </span>
      </div>
    `;

    const timerPill = container.querySelector('.thinking-timer-pill');
    const startTime = Date.now();

    timerId = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      timerPill.textContent = `(${elapsed}s)`;
    }, 100);

    finish = () => {
      clearInterval(timerId);
    };
  }

  return { el: container, updateProgress, finish, timerId };
}

function convertGenUiToArtifact(text) {
  if (!text || typeof text !== 'string' || !text.includes('※genui※')) {
    return text;
  }
  return text.replace(/※genui※(\{[\s\S]*?)(?:※|$)/g, (match, rawJson) => {
    let data = null;
    for (const suffix of ['', '}}', '"}}', '"]}}']) {
      try {
        data = JSON.parse(rawJson.trim() + suffix);
        break;
      } catch (e) { }
    }

    let title = 'Interactive Application';
    let content = '';

    if (data) {
      const block = data.app_block || data;
      title = block.title || title;
      content = block.content || '';
    } else {
      const titleMatch = rawJson.match(/"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/);
      if (titleMatch) title = titleMatch[1].replace(/\\"/g, '"');
      const contentMatch = rawJson.match(/"content"\s*:\s*"((?:[^"\\]|\\.)*)/);
      if (contentMatch) {
        let rawC = contentMatch[1];
        try {
          content = JSON.parse('"' + rawC + (rawC.endsWith('"') ? '' : '"'));
        } catch (_) {
          content = rawC.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"').replace(/\\\\/g, '\\');
        }
      } else {
        return match;
      }
    }

    const id = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'genui-app';
    let type = 'text/html';
    if (/export\s+default|import\s+React|from\s+["']react["']/.test(content)) {
      type = 'application/vnd.ant.react';
    }

    return `\n\n<antArtifact identifier="${id}" type="${type}" title="${title}">\n${content}\n</antArtifact>\n`;
  });
}

function renderMarkdown(text) {
  if (!text) return '';
  text = convertGenUiToArtifact(text);

  // 0. Remove thinking trace tags from the visible chat bubble
  let processed = text.replace(/<antThinking>[\s\S]*?<\/antThinking>/gi, '');
  processed = processed.replace(/<antThinking>[\s\S]*$/gi, '');

  // 0.05 Strip internal search citations and OpenAI private PUA markers
  processed = processed.replace(/[※\u203B][^\s]*/g, '');
  processed = processed.replace(/\bcite[a-zA-Z0-9_]*turn[a-zA-Z0-9_]*\b/gi, '');
  processed = processed.replace(/\bturn\d+[a-zA-Z0-9_]*\b/gi, '');
  processed = processed.replace(/[\uE200-\uE20F]message_reaction[\uE200-\uE20F][^\uE200-\uE20F]*[\uE200-\uE20F]/g, '');
  processed = processed.replace(/[\uE200-\uE20F]/g, '');

  // 0.1 Extract Artifacts and replace with clean interactive pill placeholders
  const artifactPills = [];
  // Match closed artifacts
  processed = processed.replace(/<antArtifact\s+([^>]+)>([\s\S]*?)<\/antArtifact>/gi, (match, rawAttrs, code) => {
    const attrs = parseXmlAttributes(rawAttrs);
    const id = attrs.identifier || 'artifact';
    const type = attrs.type || 'application/vnd.ant.code';
    const title = attrs.title || id;
    const cleanContent = stripArtifactCodeFences(code);

    if (!state.artifacts[id]) {
      state.artifacts[id] = {
        identifier: id,
        type: type,
        title: title,
        language: attrs.language || '',
        currentVersion: 1,
        versions: [{ version: 1, content: cleanContent, timestamp: Date.now() }],
        isStreaming: false,
      };
    } else {
      const art = state.artifacts[id];
      art.type = type;
      art.title = title;
      art.language = attrs.language || art.language || '';
      art.isStreaming = false;
      const curVer = art.currentVersion || 1;
      if (art.versions && art.versions[curVer - 1]) {
        art.versions[curVer - 1].content = cleanContent;
      }
    }

    const placeholder = `@@ARTIFACT_PILL_${artifactPills.length}@@`;
    artifactPills.push({ id, title, type, isStreaming: false });
    return placeholder;
  });

  // Match in-flight (unclosed) streaming artifact
  processed = processed.replace(/<antArtifact\s+([^>]+)>([\s\S]*)$/gi, (match, rawAttrs, partialCode) => {
    const attrs = parseXmlAttributes(rawAttrs);
    const id = attrs.identifier || 'artifact';
    const type = attrs.type || 'application/vnd.ant.code';
    const title = attrs.title || id;
    const cleanPartial = stripArtifactCodeFences(partialCode);

    if (!state.artifacts[id]) {
      state.artifacts[id] = {
        identifier: id,
        type: type,
        title: title,
        language: attrs.language || '',
        currentVersion: 1,
        versions: [{ version: 1, content: cleanPartial, timestamp: Date.now() }],
        isStreaming: true,
      };
    } else {
      const art = state.artifacts[id];
      const curVer = art.currentVersion || 1;
      if (art.versions && art.versions[curVer - 1]) {
        art.versions[curVer - 1].content = cleanPartial;
      }
      art.isStreaming = true;
    }

    const placeholder = `@@ARTIFACT_PILL_${artifactPills.length}@@`;
    artifactPills.push({ id, title, type, isStreaming: true });
    return placeholder;
  });

  // 1. Extract and safeguard code blocks
  const codeBlocks = [];
  processed = processed.replace(/```([a-zA-Z0-9_\-\+]*)\n?([\s\S]*?)```/g, (match, lang, code) => {
    const placeholder = `@@CODE_BLOCK_${codeBlocks.length}@@`;
    codeBlocks.push({ lang: (lang || 'code').toLowerCase(), code });
    return placeholder;
  });

  // 2. Extract and safeguard inline code
  const inlineCodes = [];
  processed = processed.replace(/`([^`\n]+)`/g, (match, code) => {
    const placeholder = `@@INLINE_CODE_${inlineCodes.length}@@`;
    inlineCodes.push(code);
    return placeholder;
  });

  // 3. Escape HTML entities
  processed = escapeHtml(processed);

  // 4. Markdown Tables
  processed = processed.replace(/((?:\|[^\n]+\|\r?\n)+)/g, (match) => {
    const lines = match.trim().split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (lines.length >= 2 && lines[1].includes('---')) {
      const parseRow = (rowStr, tag = 'td') => {
        const cells = rowStr.split('|').slice(1, -1);
        return '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
      };
      const headerHtml = '<thead>' + parseRow(lines[0], 'th') + '</thead>';
      const bodyLines = lines.slice(2);
      const bodyHtml = '<tbody>' + bodyLines.map(r => parseRow(r, 'td')).join('') + '</tbody>';
      return `<div class="chat-table-wrapper"><table class="chat-md-table">${headerHtml}${bodyHtml}</table></div>`;
    }
    return match;
  });

  // 5. Horizontal rules
  processed = processed.replace(/^(?:---|\*\*\*|___)\s*$/gm, '<hr class="chat-md-hr"/>');

  // 6. Headings
  processed = processed.replace(/^######\s+(.+)$/gm, '<h6 class="chat-md-h6">$1</h6>');
  processed = processed.replace(/^#####\s+(.+)$/gm, '<h5 class="chat-md-h5">$1</h5>');
  processed = processed.replace(/^####\s+(.+)$/gm, '<h4 class="chat-md-h4">$1</h4>');
  processed = processed.replace(/^###\s+(.+)$/gm, '<h3 class="chat-md-h3">$1</h3>');
  processed = processed.replace(/^##\s+(.+)$/gm, '<h2 class="chat-md-h2">$1</h2>');
  processed = processed.replace(/^#\s+(.+)$/gm, '<h1 class="chat-md-h1">$1</h1>');

  // 7. Blockquotes
  processed = processed.replace(/^>\s*(.+)$/gm, '<blockquote class="chat-md-blockquote">$1</blockquote>');

  // 8. Markdown Links [label](url)
  processed = processed.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)\"\'<>]+)\)/g, (match, title, url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-md-link">${title} <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="link-ext-icon"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>`;
  });

  // 9. Autolink standalone raw URLs
  processed = processed.replace(/(^|[\s(])(https?:\/\/[^\s\)\"\'<>]+)(?=$|[\s)])/g, (match, prefix, url) => {
    return `${prefix}<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-md-link">${url} <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="link-ext-icon"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>`;
  });

  // 10. Bold & Italic
  processed = processed.replace(/\*\*\*([^\*\n]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  processed = processed.replace(/___([^_\n]+)___/g, '<strong><em>$1</em></strong>');
  processed = processed.replace(/\*\*([^\*\n]+)\*\*/g, '<strong>$1</strong>');
  processed = processed.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
  processed = processed.replace(/(^|[^\w])\*([^\*\n]+)\*([^\w]|$)/g, '$1<em>$2</em>$3');
  processed = processed.replace(/(^|[^\w])_([^_\n]+)_([^\w]|$)/g, '$1<em>$2</em>$3');

  // 11. Strikethrough
  processed = processed.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');

  // 12. Lists
  processed = processed.replace(/((?:^(?:[\*\-•]|\d+\.)\s+[^\n]+(?:\n|$))+)/gm, (match) => {
    const isOrdered = /^\d+\./.test(match.trim());
    const items = match.trim().split('\n').map(l => {
      const clean = l.replace(/^(?:[\*\-•]|\d+\.)\s+/, '');
      return `<li>${clean}</li>`;
    }).join('');
    const tag = isOrdered ? 'ol' : 'ul';
    return `<${tag} class="chat-md-list">${items}</${tag}>`;
  });

  // 13. Paragraph breaks & Linebreaks
  processed = processed.replace(/\n\n+/g, '<div class="chat-md-spacer"></div>');
  processed = processed.replace(/\n/g, '<br/>');

  // 14. Restore Inline Codes
  processed = processed.replace(/@@INLINE_CODE_(\d+)@@/g, (match, idx) => {
    const code = inlineCodes[Number(idx)] || '';
    return `<code class="chat-md-inline-code">${escapeHtml(code)}</code>`;
  });

  // 15. Restore Code Blocks
  processed = processed.replace(/@@CODE_BLOCK_(\d+)@@/g, (match, idx) => {
    const item = codeBlocks[Number(idx)];
    if (!item) return '';
    const cleanLang = escapeHtml(item.lang || 'text');
    const cleanCode = escapeHtml(item.code.trim());
    let rawB64 = '';
    try {
      rawB64 = btoa(unescape(encodeURIComponent(item.code.trim())));
    } catch (e) {
      rawB64 = btoa(item.code.trim().substring(0, 500));
    }
    return `
      <div class="chat-code-card">
        <div class="chat-code-header">
          <span class="chat-code-lang">${cleanLang}</span>
          <button class="chat-code-copy-btn" data-code-b64="${rawB64}" title="Copy code">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy</span>
          </button>
        </div>
        <pre class="chat-code-pre"><code>${cleanCode}</code></pre>
      </div>
    `;
  });

  // 16. Restore Artifact Pills
  processed = processed.replace(/@@ARTIFACT_PILL_(\d+)@@/g, (match, idx) => {
    const item = artifactPills[Number(idx)];
    if (!item) return '';
    return renderArtifactChatPillHtml(item.id, item.title, item.type, item.isStreaming);
  });

  return processed;
}

function formatMarkdownSimple(text) {
  return renderMarkdown(text);
}

function parseAndRenderMediaContent(assistantMsgEl, bubbleEl, rawContent, reasoningText, promptText, modality) {
  bubbleEl.classList.remove('playground-loader-bubble');
  bubbleEl.innerHTML = '';

  let content = rawContent || '';

  // Preserve artifacts before any raw base64 or media cleaning
  const preservedArtifacts = [];
  content = content.replace(/<antArtifact\s+[^>]+>[\s\S]*?<\/antArtifact>/gi, (match) => {
    const ph = `@@ARTIFACT_RAW_PRESERVE_${preservedArtifacts.length}@@`;
    preservedArtifacts.push(match);
    return ph;
  });

  const extractedImages = [];
  const extractedVideos = [];

  // 0. Extract markdown videos !?[alt](url.mp4) or data:video/
  content = content.replace(/!?\[(.*?)\]\(((?:https?:\/\/|\/|data:video\/)[^\)]+\.(?:mp4|webm|mov|m3u8)[^\)]*|data:video\/[^\)]+)\)/gi, (match, title, url) => {
    extractedVideos.push({ src: url.trim(), title: title || 'Generated Video' });
    return '';
  });

  // 1. Extract markdown images ![alt](url)
  content = content.replace(/!\[(.*?)\]\((data:image\/[^\)]+|https?:\/\/[^\)]+|\/[^\)]+)\)/gi, (match, alt, url) => {
    extractedImages.push({ src: url.trim(), alt: alt || 'Generated Image' });
    return '';
  });

  // 2. Extract HTML images <img src="...">
  content = content.replace(/<img[^>]+src=["'](data:image\/[^"']+|https?:\/\/[^"']+|\/[^"']+)["'][^>]*>/gi, (match, url) => {
    extractedImages.push({ src: url.trim(), alt: 'Generated Image' });
    return '';
  });

  // 3. Extract standalone base64 data URLs: data:image/...;base64,...
  content = content.replace(/data:image\/(?:png|jpeg|jpg|webp|gif|svg\+xml);base64,[A-Za-z0-9+/=]+/gi, (match) => {
    extractedImages.push({ src: match.trim(), alt: 'Generated Image' });
    return '';
  });

  // 4. Extract raw base64 image chunks (> 160 base64 chars without spaces)
  content = content.replace(/```(?:base64|img|image)?\s*([A-Za-z0-9+/=\s]{160,})\s*```/gi, (match, b64) => {
    const cleanB64 = b64.replace(/\s+/g, '');
    const prefix = cleanB64.startsWith('/9j/') ? 'data:image/jpeg;base64,' :
      cleanB64.startsWith('UklGR') ? 'data:image/webp;base64,' :
        cleanB64.startsWith('PHN2Zy') ? 'data:image/svg+xml;base64,' :
          'data:image/png;base64,';
    extractedImages.push({ src: prefix + cleanB64, alt: 'Generated Image' });
    return '';
  });

  // 4b. Extract unadorned bare base64 chunks (120+ chars) if not yet caught
  content = content.replace(/(?:^|\s)([A-Za-z0-9+/=]{120,})(?:\s|$)/g, (match, b64) => {
    const cleanB64 = b64.trim();
    const prefix = cleanB64.startsWith('/9j/') ? 'data:image/jpeg;base64,' :
      cleanB64.startsWith('UklGR') ? 'data:image/webp;base64,' :
        cleanB64.startsWith('PHN2Zy') ? 'data:image/svg+xml;base64,' :
          cleanB64.startsWith('iVBORw0KGgo') ? 'data:image/png;base64,' : '';
    if (prefix) {
      extractedImages.push({ src: prefix + cleanB64, alt: 'Generated Image' });
    }
    return '';
  });

  // 5. Extract markdown videos [video](url) or video URLs (.mp4, .webm, .mov)
  content = content.replace(/\[(.*?)\]\(((?:https?:\/\/|\/)[^\)]+\.(?:mp4|webm|mov|m3u8)[^\)]*)\)/gi, (match, title, url) => {
    extractedVideos.push({ src: url.trim(), title: title || 'Generated Video' });
    return '';
  });

  content = content.replace(/(?:https?:\/\/[^\s"'<>]|\/static\/[^\s"'<>])+\.(?:mp4|webm|mov|m3u8)(?:\?[^\s"'<>]*)?/gi, (match) => {
    extractedVideos.push({ src: match.trim(), title: 'Generated Video' });
    return '';
  });

  content = content.replace(/data:video\/(?:mp4|webm);base64,[A-Za-z0-9+/=]+/gi, (match) => {
    extractedVideos.push({ src: match.trim(), title: 'Generated Video' });
    return '';
  });

  // 6. Absolute safety cleanup: strip any orphaned markdown brackets and leftover long base64 blocks
  content = content.replace(/!\[.*?\]\(\s*\)/g, '');
  content = content.replace(/[A-Za-z0-9+/=]{90,}/g, '');

  // Restore preserved raw artifacts
  content = content.replace(/@@ARTIFACT_RAW_PRESERVE_(\d+)@@/g, (m, idx) => {
    return preservedArtifacts[Number(idx)] || '';
  });

  const cleanText = content.trim();

  // If there is accompanying commentary text, render it cleanly
  if (cleanText) {
    const textNode = document.createElement('div');
    textNode.className = 'chat-md-content';
    textNode.innerHTML = renderMarkdown(cleanText);
    bubbleEl.appendChild(textNode);
  } else if (!extractedImages.length && !extractedVideos.length) {
    if (reasoningText && reasoningText.trim()) {
      const textNode = document.createElement('div');
      textNode.className = 'chat-md-content';
      textNode.style.color = 'var(--text-secondary)';
      textNode.style.fontStyle = 'italic';
      textNode.textContent = 'Thinking process complete.';
      bubbleEl.appendChild(textNode);
    } else {
      const textNode = document.createElement('div');
      textNode.className = 'chat-md-content';
      textNode.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">No text response generated.</span>';
      bubbleEl.appendChild(textNode);
    }
  }

  // Render Interactive Image Cards
  extractedImages.forEach((img, idx) => {
    const aspect = detectImageAspectRatio(promptText);
    const card = document.createElement('div');
    card.className = 'gpt-rendered-image-card';
    card.style.aspectRatio = aspect.ratio;
    card.style.width = aspect.maxWidth;
    const filename = `eclipse-${state.selectedModel || 'image'}-${Date.now()}-${idx + 1}.png`;

    card.innerHTML = `
      <div class="gpt-image-viewport" style="aspect-ratio: ${aspect.ratio}; width: 100%; height: 100%;">
        <img src="${escapeHtml(safeMediaUrl(img.src))}" alt="${escapeHtml(img.alt || promptText || 'Generated Image')}" class="gpt-image-element gpt-image-fadein" loading="eager" />
        <div class="gpt-image-glass-toolbar">
          <button class="gpt-glass-action-btn btn-copy" data-tooltip="Copy" aria-label="Copy image">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
          <button class="gpt-glass-action-btn btn-download" data-tooltip="Download" aria-label="Download image">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
          </button>
        </div>
      </div>
    `;

    const imgEl = card.querySelector('.gpt-image-element');
    const viewportEl = card.querySelector('.gpt-image-viewport');

    imgEl.addEventListener('load', () => {
      imgEl.classList.add('gpt-image-loaded');
      if (aspect.isDefault && imgEl.naturalWidth && imgEl.naturalHeight) {
        const natRatio = `${imgEl.naturalWidth} / ${imgEl.naturalHeight}`;
        viewportEl.style.aspectRatio = natRatio;
        card.style.aspectRatio = natRatio;
      }
    });

    viewportEl.addEventListener('click', (e) => {
      if (e.target.closest('.gpt-glass-action-btn')) return;
      openMediaLightbox(img.src, 'image', promptText || img.alt);
    });

    const copyBtn = card.querySelector('.btn-copy');
    copyBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await copyMediaToClipboard(img.src);
      copyBtn.setAttribute('data-tooltip', 'Copied!');
      copyBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #10b981;">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      const tip = document.getElementById('eclipse-tooltip');
      if (tip && tip.classList.contains('visible')) {
        tip.textContent = 'Copied!';
      }
      setTimeout(() => {
        copyBtn.setAttribute('data-tooltip', 'Copy');
        copyBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        `;
      }, 2000);
    });

    const downloadBtn = card.querySelector('.btn-download');
    downloadBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      downloadMediaFile(img.src, filename);
    });

    bubbleEl.appendChild(card);
  });

  // Render Interactive Video Cards
  extractedVideos.forEach((vid, idx) => {
    const card = document.createElement('div');
    card.className = 'gpt-rendered-video-card';
    const filename = `eclipse-${state.selectedModel || 'video'}-${Date.now()}-${idx + 1}.mp4`;

    card.innerHTML = `
      <div class="gpt-video-viewport" style="aspect-ratio: 16/9; width: 100%; max-width: 680px;">
        <video controls autoplay muted loop playsinline preload="auto" class="gpt-video-element" src="${escapeHtml(safeMediaUrl(vid.src))}"></video>
        <div class="gpt-image-glass-toolbar">
          <button class="gpt-glass-action-btn btn-copy" data-tooltip="Copy Link" aria-label="Copy video link">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
          <button class="gpt-glass-action-btn btn-download" data-tooltip="Download" aria-label="Download video">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
          </button>
        </div>
      </div>
    `;

    const videoEl = card.querySelector('video');
    const viewportEl = card.querySelector('.gpt-video-viewport');

    videoEl.addEventListener('loadedmetadata', () => {
      if (videoEl.videoWidth && videoEl.videoHeight) {
        const natRatio = `${videoEl.videoWidth} / ${videoEl.videoHeight}`;
        viewportEl.style.aspectRatio = natRatio;
        card.style.aspectRatio = natRatio;
      }
    });

    const copyBtn = card.querySelector('.btn-copy');
    copyBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(vid.src);
        copyBtn.setAttribute('data-tooltip', 'Copied!');
        copyBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #10b981;">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        `;
        const tip = document.getElementById('eclipse-tooltip');
        if (tip && tip.classList.contains('visible')) {
          tip.textContent = 'Copied!';
        }
        setTimeout(() => {
          copyBtn.setAttribute('data-tooltip', 'Copy Link');
          copyBtn.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          `;
        }, 2000);
      } catch (err) { }
    });

    const downloadBtn = card.querySelector('.btn-download');
    downloadBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      downloadMediaFile(vid.src, filename);
    });

    bubbleEl.appendChild(card);
  });

  if (!extractedImages.length && !extractedVideos.length && !cleanText) {
    bubbleEl.textContent = '(Model completed response without text output)';
  }
}

// ===================================================================
// Model Parameter Overrides & Global Thinking Budget Enforcement
// ===================================================================

function updateThinkingBudgetDisplay(tokens) {
  const valEl = document.getElementById('thinking-budget-val');
  const t = parseInt(tokens, 10) || 0;
  if (valEl) {
    valEl.textContent = t > 0 ? `${t.toLocaleString()} tokens` : 'Off (0)';
  }
  const btns = document.querySelectorAll('#thinking-preset-btns .preset-btn');
  btns.forEach(b => {
    const btnTok = parseInt(b.dataset.tokens, 10);
    b.classList.toggle('active', btnTok === t);
  });
}

function applyModelSettingsToUI(cfg, model) {
  const targetModel = model || state.selectedModel || 'gemini-3.8-flash';
  const activeModelLabel = document.getElementById('param-active-model-name');
  if (activeModelLabel) activeModelLabel.textContent = targetModel;
  const paramLabel = document.getElementById('param-model-selected-label');
  if (paramLabel) paramLabel.textContent = formatModelDisplayName(targetModel);
  const paramInput = document.getElementById('param-model-select');
  if (paramInput) paramInput.value = targetModel;

  const thinkingRange = document.getElementById('thinking-budget-range');
  const maxTokensRange = document.getElementById('max-tokens-range');
  const maxTokensVal = document.getElementById('max-tokens-val');
  const tempRange = document.getElementById('temp-range');
  const tempVal = document.getElementById('temp-val');
  const promptInput = document.getElementById('system-prompt-input');

  const budget = (cfg && cfg.thinking_budget !== undefined) ? cfg.thinking_budget : 0;
  if (thinkingRange) thinkingRange.value = budget;
  updateThinkingBudgetDisplay(budget);

  const maxTokens = (cfg && cfg.max_tokens !== undefined) ? cfg.max_tokens : 4096;
  if (maxTokensRange) maxTokensRange.value = maxTokens;
  if (maxTokensVal) maxTokensVal.textContent = `${Number(maxTokens).toLocaleString()} tokens`;

  const maxBtns = document.querySelectorAll('#max-tokens-preset-btns .preset-btn');
  maxBtns.forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.tokens, 10) === maxTokens);
  });

  if (cfg && cfg.temperature !== undefined && tempRange) {
    tempRange.value = cfg.temperature;
    if (tempVal) tempVal.textContent = Number(cfg.temperature).toFixed(2);
  }
  if (cfg && cfg.system_prompt !== undefined && promptInput) {
    promptInput.value = cfg.system_prompt;
  }
}

async function loadModelSettings(model) {
  const targetModel = model || state.selectedModel || 'gemini-3.8-flash';
  const activeModelLabel = document.getElementById('param-active-model-name');
  if (activeModelLabel) activeModelLabel.textContent = targetModel;
  const paramLabel = document.getElementById('param-model-selected-label');
  if (paramLabel) paramLabel.textContent = formatModelDisplayName(targetModel);
  const paramInput = document.getElementById('param-model-select');
  if (paramInput) paramInput.value = targetModel;
  renderParamModelSelectOptions();

  try {
    const res = await fetch(`/api/model-settings?model=${encodeURIComponent(targetModel)}`);
    if (res.ok) {
      const data = await res.json();
      applyModelSettingsToUI(data.settings || {}, targetModel);
    }
  } catch (e) {
    console.warn('Failed to load model settings:', e);
  }
}

let _saveSettingsDebounceTimer = null;
async function saveCurrentModelSettings(showNotice = true, applyGlobally = false) {
  const model = state.selectedModel || 'gemini-3.8-flash';
  const thinkingRange = document.getElementById('thinking-budget-range');
  const maxTokensRange = document.getElementById('max-tokens-range');
  const tempRange = document.getElementById('temp-range');
  const promptInput = document.getElementById('system-prompt-input');
  const statusEl = document.getElementById('model-settings-status');

  const payload = {
    model: model,
    apply_globally: applyGlobally,
    thinking_budget: parseInt(thinkingRange?.value || 0, 10),
    max_tokens: parseInt(maxTokensRange?.value || 4096, 10),
    temperature: parseFloat(tempRange?.value || 0.7),
    system_prompt: promptInput?.value.trim() || '',
  };

  try {
    const res = await fetch('/api/model-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const data = await res.json();
      const msg = data.message || 'Settings saved successfully';
      if (statusEl) {
        statusEl.textContent = msg;
        clearTimeout(_saveSettingsDebounceTimer);
        _saveSettingsDebounceTimer = setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 4000);
      }
      if (showNotice) {
        showToast(msg, 'success');
      }
    }
  } catch (e) {
    if (showNotice) showToast(`Failed to save settings: ${e.message}`, 'error');
  }
}

async function resetCurrentModelSettings() {
  const model = state.selectedModel || 'gemini-3.8-flash';
  try {
    await fetch(`/api/model-settings?model=${encodeURIComponent(model)}`, { method: 'DELETE' });
    applyModelSettingsToUI({ thinking_budget: 0, max_tokens: 4096, temperature: 0.7, system_prompt: '' }, model);
    showToast(`Reset settings for '${model}' to factory defaults.`, 'info');
  } catch (e) {
    showToast(`Failed to reset: ${e.message}`, 'error');
  }
}

function getHeroGreetingText() {
  const hour = new Date().getHours();
  const rawName = (localStorage.getItem('eclipse_user_name') || 'Operator').trim();
  const name = rawName || 'Operator';
  if (hour >= 5 && hour < 12) return `Good morning, ${name}`;
  if (hour >= 12 && hour < 17) return `Good afternoon, ${name}`;
  if (hour >= 17 && hour < 22) return `Good evening, ${name}`;
  return `Good night, ${name}`;
}

const HERO_DIALOGUES = [
  // --- JJK & Shonen Anime ---
  "Nah, I'd win",
  "Stand proud, you're strong",
  "Throughout Heaven and Earth, I alone am the honored one",
  "With this treasure I summon...",
  "Domain Expansion: Infinite Yap",
  "Domain Expansion: Malevolent Kitchen",
  "You are my specialz",

  // --- Anime Classics & Romcoms ---
  "Aura, kill yourself",
  "Himmel the Hero would've fixed this bug",
  "Frieren sleeping through 80 years of updates",
  "Get in the fucking robot, Shinji",
  "Shinji, crank that Soulja Boy",
  "I will take a potato chip... AND EAT IT!",
  "All according to keikaku (keikaku means plan)",
  "El Psy Kongroo",
  "Steins;Gate was a documentary",
  "I reject my humanity, JoJo!",
  "KONO DIO DA!",
  "Is that a motherfucking JoJo reference?!",
  "Zasshu (Mongrel)",
  "Yorokobe Shounen",
  "I yearn for true gender equality",
  "EXPLOSION! 💥",
  "Watch Konosuba, Trust.",
  "Giga Drill Break!",
  "Row row fight the power!",
  "Bocchi just like me fr fr",
  "Griffith did nothing wrong (cap, fuck that guy)",
  "Omae wa mou shindeiru",
  "Ara ara, what do we have here?",
  "Tomboys for the win!",
  "Ore wa Ochinchin ga Daisuki Nandayo",

  // --- Gaming & Soulsborne ---
  "Hey you, you're finally awake",
  "I used to be an adventurer like you...",
  "Praise the Sun! \\[T]/",
  "Git gud, scrub",
  "You died. Again.",
  "Put these foolish ambitions to rest",
  "I am Malenia, Blade of Miquella",
  "Maidenless behavior detected",
  "Touch grace immediately",
  "Kept you waiting, huh?",
  "Nanomachines, son!",
  "Making the mother of all omelettes here, Jack",
  "Memes, the DNA of the soul",
  "The cake is a lie",
  "Protocol 3: Protect the Pilot",
  "Ah shit, here we go again",
  "All you had to do was follow the damn train, CJ!",
  "Would you kindly?",
  "War. War never changes.",
  "Snake? Snake?! SNAAAAKE!",
  "Rush B, don't stop cyka",
  "Report jg diff, ff at 15",
  "Mid or feed, uninstall trash",
  "Wake the fuck up Samurai, we have a city to burn",
  "A corpse should be left well alone",
  "Cheeki Breeki I v Damke",
  "Clutch or kick",

  // --- TV Shows & Pop Culture ---
  "Say my name. (Heisenberg)",
  "Waltuh, put your dick away Waltuh",
  "Jesse, we need to cook",
  "Better Call Saul!",
  "I am the one who knocks!",
  "Lisan al-Gaib! As written!",
  "May thy knife chip and shatter",
  "Winter is coming",
  "Shut up and take my money!",
  "Good news, everyone!",

  // --- Internet & Dev Brainrot ---
  "Am I cooking, Chat?",
  "Let him cook, I said LET HIM COOK",
  "Who let bro cook in production?",
  "Bro think he the main character",
  "Bro is definitely not him",
  "L + Ratio + Maidenless + Skill Issue",
  "Touch grass? In this economy?",
  "Certified yapper in the building",
  "Works on my machine, ship it",
  "Submitting PR and fleeing the country",
  "Sir, a second PR has hit production",
  "Zero bitches? Fascinating.",
  "Bait used to be believable",
  "Absolute cinema ✋😔🤚",
  "We ball regardless",
  "Trust the process (I have no plan)",
  "The voices told me to refactor",
  "Terminal open, brain disconnected"
];

let lastGreetingIndex = -1;
function updateHeroGreeting(forceNew = true) {
  const greetingEl = document.getElementById('claude-hero-greeting');
  if (!greetingEl) return;
  const list = HERO_DIALOGUES;
  let idx = Math.floor(Math.random() * list.length);
  if (forceNew && list.length > 1 && idx === lastGreetingIndex) {
    idx = (idx + 1) % list.length;
  }
  lastGreetingIndex = idx;
  const text = list[idx];

  greetingEl.className = 'claude-hero-greeting';
  greetingEl.style.opacity = '0';
  greetingEl.style.transform = 'translateY(4px)';
  setTimeout(() => {
    greetingEl.textContent = text;
    greetingEl.style.opacity = '1';
    greetingEl.style.transform = 'translateY(0)';
  }, 160);
}

// ===================================================================
// Universal Artifacts Workbench Engine (Claude-Style Multi-Model System)
// ===================================================================

function parseXmlAttributes(rawAttrs) {
  const attrs = {};
  if (!rawAttrs) return attrs;
  const attrRegex = /([a-zA-Z0-9_\-]+)=["']([^"']*)["']/g;
  let m;
  while ((m = attrRegex.exec(rawAttrs)) !== null) {
    attrs[m[1]] = m[2];
  }
  return attrs;
}

function stripArtifactCodeFences(code) {
  if (!code) return '';
  let str = String(code).trim();
  // Strip leading code fence e.g. ```jsx, ```html, ```css, etc.
  str = str.replace(/^\s*```[a-zA-Z0-9_\-\+]*\s*(\r?\n)?/i, '');
  // Strip trailing code fence e.g. ```
  str = str.replace(/(\r?\n)?```\s*$/i, '');
  return str.replace(/^\r?\n+/, '').replace(/\r?\n+$/, '');
}

function getArtifactIconSvg(type) {
  if (type === 'application/vnd.ant.react') {
    return `<img src="/static/icons/react-js-icon.svg" class="artifact-icon-img artifact-icon-react" alt="React" width="22" height="22" />`;
  } else if (type === 'text/html') {
    return `<img src="/static/icons/html-icon.svg" class="artifact-icon-img artifact-icon-html" alt="HTML" width="20" height="20" />`;
  } else if (type === 'image/svg+xml') {
    return `<img src="/static/icons/svg-icon.svg" class="artifact-icon-img artifact-icon-svg" alt="SVG" width="20" height="20" />`;
  } else if (type === 'text/markdown') {
    return `<img src="/static/icons/markdown-icon.svg" class="artifact-icon-img artifact-icon-md" alt="Markdown" width="20" height="20" />`;
  } else if (type === 'application/vnd.ant.mermaid') {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="artifact-icon-img artifact-icon-diagram"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="8.5" y="14" width="7" height="7" rx="1"></rect><path d="M6.5 10v2a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2v-2"></path><path d="M12 14v-2"></path></svg>`;
  }
  return `<img src="/static/icons/code-icon.svg" class="artifact-icon-img artifact-icon-code" alt="Code" width="20" height="20" />`;
}

function getArtifactShortTypeLabel(type, language) {
  if (type === 'application/vnd.ant.react') return 'React';
  if (type === 'text/html') return 'HTML';
  if (type === 'image/svg+xml') return 'SVG';
  if (type === 'application/vnd.ant.mermaid') return 'Mermaid';
  if (type === 'text/markdown') return 'Markdown';
  return (language || 'Code').toUpperCase();
}

function updateArtifactDownloadLabel(type, language) {
  const labelEl = document.getElementById('artifact-download-label');
  if (!labelEl) return;
  if (type === 'text/html') labelEl.textContent = 'Download as HTML';
  else if (type === 'application/vnd.ant.react') labelEl.textContent = 'Download as TSX';
  else if (type === 'image/svg+xml') labelEl.textContent = 'Download as SVG';
  else if (type === 'text/markdown') labelEl.textContent = 'Download as Markdown';
  else if (type === 'application/vnd.ant.mermaid') labelEl.textContent = 'Download as Mermaid';
  else {
    const ext = (language || 'txt').toUpperCase();
    labelEl.textContent = `Download as ${ext}`;
  }
}

function getArtifactTypeLabel(type) {
  if (type === 'application/vnd.ant.react') return 'React Component';
  if (type === 'text/html') return 'HTML Web App';
  if (type === 'image/svg+xml') return 'Vector Art (SVG)';
  if (type === 'application/vnd.ant.mermaid') return 'Mermaid Diagram';
  if (type === 'text/markdown') return 'Markdown Document';
  return 'Source Code';
}

function getArtifactFileExtension(type, language) {
  if (type === 'application/vnd.ant.react') return '.tsx';
  if (type === 'text/html') return '.html';
  if (type === 'image/svg+xml') return '.svg';
  if (type === 'application/vnd.ant.mermaid') return '.mmd';
  if (type === 'text/markdown') return '.md';
  const langMap = { python: '.py', javascript: '.js', typescript: '.ts', html: '.html', css: '.css', json: '.json', rust: '.rs', go: '.go', c: '.c', cpp: '.cpp', bash: '.sh', sql: '.sql' };
  return langMap[(language || '').toLowerCase()] || '.txt';
}

function renderArtifactChatPillHtml(id, title, type, isStreaming) {
  const icon = getArtifactIconSvg(type);
  const label = getArtifactTypeLabel(type);
  const activeClass = (state.activeArtifactId === id && state.artifactWorkbenchOpen) ? 'active' : '';
  const streamingDot = isStreaming ? '<span class="artifact-pill-streaming-dot"></span> Generating ' : '';
  return `
    <div class="artifact-chat-pill ${activeClass}" data-artifact-id="${escapeHtml(id)}" onclick="openArtifact('${escapeHtml(id)}')">
      <div class="artifact-pill-icon">${icon}</div>
      <div class="artifact-pill-info">
        <div class="artifact-pill-title">${escapeHtml(title || id)}</div>
        <div class="artifact-pill-subtitle">${streamingDot}${label}</div>
      </div>
      <div class="artifact-pill-action">
        <span>${isStreaming ? 'View' : 'Open'}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
      </div>
    </div>
  `;
}

function openArtifact(identifier, versionNum = null) {
  const art = state.artifacts[identifier];
  if (!art) return;

  state.activeArtifactId = identifier;
  state.artifactWorkbenchOpen = true;

  const workspace = document.getElementById('playground-workspace');
  if (workspace) {
    workspace.classList.add('artifact-open');
  }
  const resizer = document.getElementById('artifact-resizer');
  const wb = document.getElementById('artifact-workbench');
  if (resizer) resizer.style.display = 'flex';
  if (wb) wb.style.display = 'flex';

  const ver = versionNum || art.currentVersion || 1;
  art.currentVersion = ver;

  // Update Header UI
  const titleEl = document.getElementById('artifact-title');
  if (titleEl) {
    titleEl.textContent = art.title || art.identifier;
    titleEl.title = art.title || art.identifier;
  }

  const badgeEl = document.getElementById('artifact-type-badge');
  if (badgeEl) badgeEl.textContent = getArtifactShortTypeLabel(art.type, art.language);

  updateArtifactDownloadLabel(art.type, art.language);
  updateVersionStepper(art);

  // Set default view: React/HTML/CSS/SVG/Mermaid default to 'preview', Code defaults to 'code'
  const isVisualType = art.type === 'application/vnd.ant.react' ||
    art.type === 'text/html' ||
    art.type === 'text/css' ||
    (art.type === 'application/vnd.ant.code' && art.language === 'css') ||
    art.type === 'image/svg+xml' ||
    art.type === 'application/vnd.ant.mermaid';
  if (!isVisualType && art.type === 'application/vnd.ant.code') {
    switchArtifactView('code');
  } else {
    switchArtifactView(state.activeArtifactView || 'preview');
  }

  renderArtifactContent(art, ver);

  // Highlight pill in chat
  document.querySelectorAll('.artifact-chat-pill').forEach(pill => {
    if (pill.dataset.artifactId === identifier) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });
}

function closeArtifactWorkbench() {
  state.artifactWorkbenchOpen = false;
  const workspace = document.getElementById('playground-workspace');
  if (workspace) {
    workspace.classList.remove('artifact-open');
  }
  const resizer = document.getElementById('artifact-resizer');
  const wb = document.getElementById('artifact-workbench');
  if (resizer) resizer.style.display = 'none';
  if (wb) {
    wb.style.display = 'none';
    wb.classList.remove('is-fullscreen');
  }
  document.querySelectorAll('.artifact-chat-pill').forEach(pill => {
    pill.classList.remove('active');
  });
}

function switchArtifactVersion(delta) {
  const art = state.artifacts[state.activeArtifactId];
  if (!art || !art.versions) return;

  const newVer = (art.currentVersion || 1) + delta;
  if (newVer >= 1 && newVer <= art.versions.length) {
    art.currentVersion = newVer;
    updateVersionStepper(art);
    renderArtifactContent(art, newVer);
  }
}

function updateVersionStepper(art) {
  const label = document.getElementById('artifact-version-label');
  const prevBtn = document.getElementById('btn-artifact-prev-ver');
  const nextBtn = document.getElementById('btn-artifact-next-ver');

  const total = art.versions ? art.versions.length : 1;
  const current = art.currentVersion || 1;

  if (label) label.textContent = total > 1 ? `v${current} of ${total}` : `v${current}`;
  if (prevBtn) prevBtn.disabled = current <= 1;
  if (nextBtn) nextBtn.disabled = current >= total;
}

function switchArtifactView(view) {
  state.activeArtifactView = view;
  const btnPrev = document.getElementById('btn-artifact-preview');
  const btnCode = document.getElementById('btn-artifact-code');
  const panePrev = document.getElementById('artifact-preview-pane');
  const paneCode = document.getElementById('artifact-code-pane');

  if (view === 'preview') {
    if (btnPrev) btnPrev.classList.add('active');
    if (btnCode) btnCode.classList.remove('active');
    if (panePrev) panePrev.classList.add('active');
    if (paneCode) paneCode.classList.remove('active');
  } else {
    if (btnPrev) btnPrev.classList.remove('active');
    if (btnCode) btnCode.classList.add('active');
    if (panePrev) panePrev.classList.remove('active');
    if (paneCode) paneCode.classList.add('active');
  }
}

function copyActiveArtifactCode() {
  const art = state.artifacts[state.activeArtifactId];
  if (!art || !art.versions) return;
  const ver = art.versions[art.currentVersion - 1];
  const code = ver ? stripArtifactCodeFences(ver.content) : '';
  if (!code) return;

  navigator.clipboard.writeText(code).then(() => {
    const copyBtn = document.getElementById('btn-artifact-copy');
    if (copyBtn) {
      const span = copyBtn.querySelector('span');
      if (span) span.textContent = 'Copied!';
      copyBtn.classList.add('copied');
      setTimeout(() => {
        if (span) span.textContent = 'Copy';
        copyBtn.classList.remove('copied');
      }, 2000);
    }
    showToast('Copied artifact code to clipboard', 'success');
  }).catch(() => {
    showToast('Failed to copy to clipboard', 'error');
  });
}

function toggleArtifactMenu(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('artifact-dropdown-menu');
  if (menu) {
    const isShown = menu.style.display !== 'none';
    menu.style.display = isShown ? 'none' : 'block';
  }
}

function downloadActiveArtifact() {
  const menu = document.getElementById('artifact-dropdown-menu');
  if (menu) menu.style.display = 'none';

  const art = state.artifacts[state.activeArtifactId];
  if (!art || !art.versions) return;
  const ver = art.versions[art.currentVersion - 1];
  const code = ver ? stripArtifactCodeFences(ver.content) : '';
  if (!code) return;

  const ext = getArtifactFileExtension(art.type, art.language);
  const filename = `${art.identifier || 'artifact'}${ext}`;
  const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Downloaded ${filename}`, 'success');
}

function toggleArtifactFullscreen() {
  const wb = document.getElementById('artifact-workbench');
  if (wb) {
    wb.classList.toggle('is-fullscreen');
  }
}

function renderArtifactContent(art, versionNum) {
  if (!art || !art.versions) return;
  const verObj = art.versions[versionNum - 1] || art.versions[art.versions.length - 1];
  if (!verObj) return;

  const content = stripArtifactCodeFences(verObj.content || '');

  // 1. Update Code Pane & Line Numbers
  const codeEl = document.getElementById('artifact-code-content');
  const gutterEl = document.getElementById('artifact-code-gutter');
  if (codeEl) codeEl.textContent = content;

  if (gutterEl) {
    const lines = content.length > 0 ? content.split('\n') : [''];
    let gutterHtml = '';
    for (let i = 1; i <= lines.length; i++) {
      gutterHtml += `<div class="line-number">${i}</div>`;
    }
    gutterEl.innerHTML = gutterHtml;
  }

  const langLabel = document.getElementById('artifact-code-lang');
  if (langLabel) {
    if (art.type === 'application/vnd.ant.react') langLabel.textContent = 'REACT / JSX';
    else if (art.type === 'text/html') langLabel.textContent = 'HTML5 / WEB';
    else if (art.type === 'image/svg+xml') langLabel.textContent = 'SVG / VECTOR';
    else if (art.type === 'application/vnd.ant.mermaid') langLabel.textContent = 'MERMAID DIAGRAM';
    else if (art.type === 'text/markdown') langLabel.textContent = 'MARKDOWN';
    else langLabel.textContent = (art.language || 'CODE').toUpperCase();
  }

  // 2. Update Preview Pane
  const iframe = document.getElementById('artifact-sandbox-frame');
  const svgBox = document.getElementById('artifact-svg-container');
  const mmdBox = document.getElementById('artifact-mermaid-container');
  const mdBox = document.getElementById('artifact-md-container');

  if (iframe) { iframe.style.display = 'none'; iframe.classList.add('hidden'); }
  if (svgBox) { svgBox.style.display = 'none'; svgBox.classList.add('hidden'); }
  if (mmdBox) { mmdBox.style.display = 'none'; mmdBox.classList.add('hidden'); }
  if (mdBox) { mdBox.style.display = 'none'; mdBox.classList.add('hidden'); }

  const isCss = art.type === 'text/css' ||
    (art.type === 'application/vnd.ant.code' && (art.language === 'css' || (content && (content.includes('@keyframes') || content.includes('backdrop-filter') || content.includes('.glass') || content.includes('background:')) && !content.includes('import ') && !content.includes('function ') && !content.includes('<html'))));

  // Every executable or markup artifact renders inside the sandboxed iframe, never in this page's DOM.
  const sandboxDoc =
    art.type === 'application/vnd.ant.react' ? buildReactSandboxHtml(content) :
    art.type === 'text/html' ? buildHtmlSandboxDoc(content) :
    isCss ? buildCssSandboxDoc(content) :
    art.type === 'image/svg+xml' ? buildSvgSandboxDoc(content) :
    art.type === 'application/vnd.ant.mermaid' ? buildMermaidSandboxDoc(content) :
    null;

  if (sandboxDoc !== null) {
    if (iframe) {
      iframe.style.display = 'block';
      iframe.classList.remove('hidden');
      iframe.srcdoc = withSandboxShims(sandboxDoc);
    }
  } else if (art.type === 'text/markdown') {
    if (mdBox) {
      mdBox.style.display = 'block';
      mdBox.classList.remove('hidden');
      mdBox.innerHTML = renderMarkdown(content);
    }
  } else {
    // Plain code -> show formatted guidance in preview pane instead of black screen
    if (mdBox) {
      mdBox.style.display = 'block';
      mdBox.classList.remove('hidden');
      mdBox.innerHTML = `
        <div style="padding: 48px 24px; text-align: center; color: var(--text-muted); max-width: 480px; margin: 0 auto;">
          <div style="font-size: 36px; margin-bottom: 16px;">📄</div>
          <h3 style="font-size: 16px; font-weight: 600; color: var(--text-primary); margin: 0 0 8px 0;">Source Code Artifact (${escapeHtml(art.language || 'code')})</h3>
          <p style="font-size: 13px; line-height: 1.6; color: var(--text-secondary); margin: 0 0 20px 0;">This artifact contains raw source code without an interactive DOM runtime. Click below to inspect, edit, or copy the source code.</p>
          <button class="btn btn-secondary btn-sm" onclick="switchArtifactView('code')">Open Code Tab</button>
        </div>
      `;
    }
    switchArtifactView('code');
  }
}

function buildCssSandboxDoc(cssCode) {
  let cleanCss = (cssCode || '')
    .replace(/^\s*```[a-zA-Z0-9_\-\+]*\s*\n?/gi, '')
    .replace(/\n?```\s*$/gi, '')
    .trim();

  const styleTag = cleanCss.includes('<style') ? cleanCss : `<style>${cleanCss}</style>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <base href="${window.location.origin}/"/>
  <style>
    :root {
      --viz-bg: #0b0f19;
      --viz-card: rgba(255, 255, 255, 0.05);
      --viz-border: rgba(255, 255, 255, 0.12);
      --viz-text: #f1f5f9;
      --viz-muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 32px 20px;
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0b0f19 80%);
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
      gap: 24px;
    }
    .sandbox-preview-container {
      width: 100%;
      max-width: 680px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 24px;
    }
    .sandbox-stage {
      width: 100%;
      padding: 40px 24px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 20px;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 16px;
    }
    .sandbox-header {
      text-align: center;
    }
    .sandbox-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0 0 6px 0;
      color: #fff;
    }
    .sandbox-subtitle {
      font-size: 13px;
      color: var(--viz-muted);
      margin: 0;
    }
    .sandbox-hint {
      font-size: 12px;
      color: #64748b;
      margin-top: 8px;
    }
  </style>
  ${styleTag}
</head>
<body>
  <div class="sandbox-preview-container">
    <div class="sandbox-header">
      <h2 class="sandbox-title">Interactive CSS Preview</h2>
      <p class="sandbox-subtitle">Styles applied live to the interactive test elements below</p>
    </div>

    <div class="sandbox-stage" id="css-dynamic-stage">
      <button class="btn btn-primary glass-btn glass-button glassmorphism">Primary Action</button>
      <button class="btn btn-secondary glass-btn glass-button glassmorphism-secondary">Secondary</button>
      <button class="btn btn-glow glass-btn-glow glass-button-glow">Glow Effect</button>
      <button class="btn btn-accent glass-accent" disabled>Disabled</button>
    </div>

    <div class="sandbox-stage" style="flex-direction: column; align-items: stretch; gap: 16px;">
      <div class="glass-card card glassmorphism-card" style="padding: 20px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.05); backdrop-filter: blur(12px);">
        <h4 style="margin: 0 0 8px 0; font-size: 15px; color: #fff;">Glassmorphism Surface</h4>
        <p style="margin: 0 0 16px 0; font-size: 13px; color: #94a3b8;">Interactive test container with glass backdrop and button actions.</p>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
          <button class="glass-btn glass-button btn">Click State</button>
          <button class="glass-btn glass-button btn" style="opacity: 0.85;">Hover State</button>
        </div>
      </div>
    </div>

    <div class="sandbox-hint">Switch to the "Code" tab at top right to copy the full stylesheet.</div>
  </div>

  <script>
    try {
      const stage = document.getElementById('css-dynamic-stage');
      const cssRules = [];
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules || []) {
            if (rule.selectorText) {
              const selectors = rule.selectorText.split(',');
              selectors.forEach(sel => {
                const match = sel.trim().match(/^\\.([a-zA-Z0-9_\\-]+)(?::[a-zA-Z0-9_\\-]+)?$/);
                if (match && match[1] && !match[1].startsWith('sandbox') && !match[1].startsWith('btn')) {
                  cssRules.push(match[1]);
                }
              });
            }
          }
        } catch(e) {}
      }
      const uniqueClasses = [...new Set(cssRules)];
      if (uniqueClasses.length > 0) {
        uniqueClasses.slice(0, 6).forEach(cls => {
          const btn = document.createElement('button');
          btn.className = cls;
          btn.textContent = '.' + cls;
          btn.style.cursor = 'pointer';
          stage.appendChild(btn);
        });
      }
    } catch(e) {}
  </script>
</body>
</html>`;
}

function buildReactSandboxHtml(jsxCode) {
  let cleanCode = jsxCode || '';

  // 0. Universal Markdown Code-Fence Stripper
  cleanCode = cleanCode.replace(/^\s*```[a-zA-Z0-9_\-\+]*\s*\n?/gi, '');
  cleanCode = cleanCode.replace(/\n?```\s*$/gi, '').trim();

  // 1. Universal Import Stripper & Identifier Collector
  const importedIcons = new Set();
  cleanCode = cleanCode.replace(/import\s+(?:(?:\*\s+as\s+([a-zA-Z0-9_$]+))|(?:([a-zA-Z0-9_$]+)\s*,?\s*)?(?:\{([^}]+)\})?)\s+from\s*['"][^'"]+['"]\s*;?/g, (m, star, def, named) => {
    if (star) importedIcons.add(star.trim());
    if (named) {
      named.split(',').forEach(n => {
        const cleanName = n.trim().split(/\s+as\s+/)[0].trim();
        if (cleanName) importedIcons.add(cleanName);
      });
    }
    return '';
  });
  // Strip any remaining imports safely (both single-line and multiline without eating code)
  cleanCode = cleanCode.replace(/import\s+(?:[\s\S]*?)\s+from\s+['"][^'"]+['"]\s*;?/g, '');
  cleanCode = cleanCode.replace(/import\s+['"][^'"]+['"]\s*;?/g, '');

  // 2. Export default handler
  let detectedName = null;
  const funcMatch = cleanCode.match(/export\s+default\s+function\s+([a-zA-Z0-9_$]+)/);
  if (funcMatch) {
    detectedName = funcMatch[1];
    cleanCode = cleanCode.replace(/export\s+default\s+function\s+([a-zA-Z0-9_$]+)/, 'function $1');
  } else {
    const identMatch = cleanCode.match(/export\s+default\s+([a-zA-Z0-9_$]+);?/);
    if (identMatch) {
      detectedName = identMatch[1];
      cleanCode = cleanCode.replace(/export\s+default\s+([a-zA-Z0-9_$]+);?/, '');
    } else {
      cleanCode = cleanCode.replace(/export\s+default\s+/, 'const __AppExport = ');
      detectedName = '__AppExport';
    }
  }
  cleanCode = cleanCode.replace(/export\s*\{[^}]*\};?/g, '');
  cleanCode = cleanCode.replace(/export\s+(const|let|var|function|class)\s+/g, '$1 ');

  // Candidate component names
  const candidateNames = [...new Set([...cleanCode.matchAll(/(?:function|const|let|var|class)\s+([A-Z][a-zA-Z0-9_$]*)/g)].map(m => m[1]))];

  const safeCodeJson = JSON.stringify(cleanCode).replace(/<\/script/gi, '<\\/script');
  const safeNameJson = JSON.stringify(detectedName || '');
  const safeIconsJson = JSON.stringify([...importedIcons]);
  const safeCandidatesJson = JSON.stringify(candidateNames);

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <base href="${window.location.origin}/"/>
  <script src="/static/vendor/react.min.js" onerror="this.onerror=null;this.src='https://unpkg.com/react@18/umd/react.production.min.js'"></script>
  <script src="/static/vendor/react-dom.min.js" onerror="this.onerror=null;this.src='https://unpkg.com/react-dom@18/umd/react-dom.production.min.js'"></script>
  <script src="/static/vendor/babel.min.js" onerror="this.onerror=null;this.src='https://unpkg.com/@babel/standalone/babel.min.js'"></script>
  <script src="https://cdn.tailwindcss.com" async></script>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      background-color: #0b0f19;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
    }
    #root { min-height: 100vh; }
    #error-boundary {
      display: none;
      position: fixed;
      top: 16px;
      left: 16px;
      right: 16px;
      z-index: 999999;
      padding: 16px;
      background: rgba(220, 38, 38, 0.95);
      border: 1px solid #ef4444;
      border-radius: 8px;
      color: #fff;
      font-family: monospace;
      font-size: 13px;
      line-height: 1.5;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      max-height: 80vh;
      overflow: auto;
    }
    /* Fallback styles for immediate rendering */
    .bg-white\\/5 { background-color: rgba(255, 255, 255, 0.05); }
    .bg-white\\/10 { background-color: rgba(255, 255, 255, 0.10); }
    .bg-white\\/15 { background-color: rgba(255, 255, 255, 0.15); }
    .bg-white\\/20 { background-color: rgba(255, 255, 255, 0.20); }
    .border-white\\/10 { border-color: rgba(255, 255, 255, 0.10); }
    .border-white\\/20 { border-color: rgba(255, 255, 255, 0.20); }
    .backdrop-blur-xl { backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); }
    .rounded-2xl { border-radius: 1rem; }
    .rounded-3xl { border-radius: 1.5rem; }
    .min-h-screen { min-height: 100vh; }
    .flex { display: flex; }
    .flex-1 { flex: 1 1 0%; }
    .items-center { align-items: center; }
    .justify-center { justify-content: center; }
    .justify-between { justify-content: space-between; }
    .text-center { text-align: center; }
    .text-white { color: #ffffff; }
    button { cursor: pointer; border-style: solid; }
  </style>
</head>
<body>
  <div id="error-boundary"></div>
  <div id="root"></div>

  <script>
    function showError(title, msg) {
      var box = document.getElementById('error-boundary');
      if (box) {
        box.style.display = 'block';
        box.innerHTML = '<strong style="color:#ffffff">' + title + '</strong><br>' +
          '<pre style="white-space:pre-wrap;font-size:12px;margin-top:6px;color:#fee2e2;max-height:300px;overflow:auto;">' +
          String(msg || '').replace(/</g, '&lt;') +
          '</pre>';
      }
    }

    window.onerror = function(msg, src, line, col, err) {
      showError('Uncaught Runtime Error:', (err && err.stack) ? err.stack : (msg + ' (line ' + line + ')'));
    };

    function waitForDependencies(callback, maxAttempts = 300) {
      let attempts = 0;
      function check() {
        try {
          if (!window.React && window.parent && window.parent.React) window.React = window.parent.React;
          if (!window.ReactDOM && window.parent && window.parent.ReactDOM) window.ReactDOM = window.parent.ReactDOM;
          if (!window.Babel && window.parent && window.parent.Babel) window.Babel = window.parent.Babel;
        } catch (_) { /* sandboxed: parent is cross-origin, load our own copies */ }

        if (window.React && window.ReactDOM && window.Babel && window.ReactDOM.createRoot) {
          callback();
        } else if (++attempts < maxAttempts) {
          setTimeout(check, 30);
        } else {
          showError('Engine Initialization Error', 'Timeout loading React, ReactDOM, or Babel engine.');
        }
      }
      check();
    }

    waitForDependencies(function() {
      // 1. Universal ClassName helpers (cn, clsx, twMerge)
      const cn = (...args) => args.flat(Infinity).filter(Boolean).map(x => {
        if (typeof x === 'object' && x !== null) {
          return Object.keys(x).filter(k => x[k]).join(' ');
        }
        return String(x);
      }).join(' ');
      const clsx = cn;
      const twMerge = cn;

      // 2. Universal Icon Proxy: returns crisp SVGs for requested icons
      const ICON_PATHS = {
        Minus: [React.createElement('line', { key: '1', x1: 5, y1: 12, x2: 19, y2: 12 })],
        Plus: [
          React.createElement('line', { key: '1', x1: 12, y1: 5, x2: 12, y2: 19 }),
          React.createElement('line', { key: '2', x1: 5, y1: 12, x2: 19, y2: 12 })
        ],
        RotateCcw: [
          React.createElement('path', { key: '1', d: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8' }),
          React.createElement('path', { key: '2', d: 'M3 3v5h5' })
        ],
        RotateCw: [
          React.createElement('path', { key: '1', d: 'M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8' }),
          React.createElement('path', { key: '2', d: 'M21 3v5h-5' })
        ],
        RefreshCw: [
          React.createElement('path', { key: '1', d: 'M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8' }),
          React.createElement('path', { key: '2', d: 'M21 3v5h-5' }),
          React.createElement('path', { key: '3', d: 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16' }),
          React.createElement('path', { key: '4', d: 'M8 16H3v5' })
        ],
        Check: [React.createElement('polyline', { key: '1', points: '20 6 9 17 4 12' })],
        X: [
          React.createElement('line', { key: '1', x1: 18, y1: 6, x2: 6, y2: 18 }),
          React.createElement('line', { key: '2', x1: 6, y1: 6, x2: 18, y2: 18 })
        ],
        Search: [
          React.createElement('circle', { key: '1', cx: 11, cy: 11, r: 8 }),
          React.createElement('line', { key: '2', x1: 21, y1: 21, x2: 16.65, y2: 16.65 })
        ],
        ArrowLeft: [
          React.createElement('line', { key: '1', x1: 19, y1: 12, x2: 5, y2: 12 }),
          React.createElement('polyline', { key: '2', points: '12 19 5 12 12 5' })
        ],
        ArrowRight: [
          React.createElement('line', { key: '1', x1: 5, y1: 12, x2: 19, y2: 12 }),
          React.createElement('polyline', { key: '2', points: '12 5 19 12 12 19' })
        ],
        ChevronLeft: [React.createElement('polyline', { key: '1', points: '15 18 9 12 15 6' })],
        ChevronRight: [React.createElement('polyline', { key: '1', points: '9 18 15 12 9 6' })],
        ChevronDown: [React.createElement('polyline', { key: '1', points: '6 9 12 15 18 9' })],
        ChevronUp: [React.createElement('polyline', { key: '1', points: '18 15 12 9 6 15' })],
        Heart: [React.createElement('path', { key: '1', d: 'M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z' })],
        Star: [React.createElement('polygon', { key: '1', points: '12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2' })]
      };

      const LucideIcons = new Proxy({}, {
        get: (target, prop) => {
          if (prop === '__esModule') return true;
          if (prop === 'default') return target;
          const IconComp = (props = {}) => {
            const s = props.size || props.width || 20;
            const stroke = props.color || 'currentColor';
            const sw = props.strokeWidth || 2;
            const knownChildren = ICON_PATHS[prop];
            return React.createElement('svg', {
              width: s,
              height: s,
              viewBox: '0 0 24 24',
              fill: 'none',
              stroke: stroke,
              strokeWidth: sw,
              strokeLinecap: 'round',
              strokeLinejoin: 'round',
              className: props.className || '',
              style: props.style
            },
              knownChildren || [
                React.createElement('circle', { key: 'c', cx: 12, cy: 12, r: 9, opacity: 0.25 }),
                React.createElement('text', {
                  key: 't',
                  x: 12, y: 15,
                  fontSize: 8,
                  textAnchor: 'middle',
                  fill: stroke,
                  stroke: 'none',
                  fontWeight: 'bold',
                  fontFamily: 'sans-serif'
                }, String(prop || '').substring(0, 3).toUpperCase())
              ]
            );
          };
          IconComp.displayName = String(prop || 'Icon');
          return IconComp;
        }
      });

      // 3. Mock animation library proxies (framer-motion)
      const motion = new Proxy({}, {
        get: (target, tag) => {
          const MotionComp = ({ children, whileHover, whileTap, animate, initial, transition, ...rest } = {}) => {
            return React.createElement(tag || 'div', rest, children);
          };
          MotionComp.displayName = 'motion.' + String(tag || 'div');
          return MotionComp;
        }
      });
      const AnimatePresence = ({ children }) => children;

      // 4. React Error Boundary
      class SandboxErrorBoundary extends React.Component {
        constructor(props) {
          super(props);
          this.state = { hasError: false, error: null };
        }
        static getDerivedStateFromError(error) {
          return { hasError: true, error };
        }
        componentDidCatch(error, info) {
          console.error("Component Caught Error:", error, info);
        }
        render() {
          if (this.state.hasError) {
            const err = this.state.error;
            const msg = (err && (err.stack || err.message)) ? String(err.stack || err.message) : 'Unknown render error';
            return React.createElement('div', {
              style: {
                margin: '16px',
                padding: '16px',
                background: 'rgba(239, 68, 68, 0.9)',
                border: '1px solid #ef4444',
                borderRadius: '8px',
                color: '#fff',
                fontFamily: 'monospace',
                fontSize: '13px',
                lineHeight: '1.5',
                whiteSpace: 'pre-wrap'
              }
            },
              React.createElement('strong', { style: { color: '#ffffff' } }, 'React Component Render Error: '),
              msg
            );
          }
          return this.props.children;
        }
      }

      // 5. Transform and execute
      try {
        const rawCode = ${safeCodeJson};
        const detectedName = ${safeNameJson};
        const importedIcons = ${safeIconsJson};
        const candidateNames = ${safeCandidatesJson};

        // Compile JSX / TSX via Babel directly
        let compiled = '';
        try {
          compiled = Babel.transform(rawCode, { filename: 'app.tsx', presets: ['react', 'typescript'] }).code;
        } catch (compileErr) {
          showError('Component Compilation Error:', (compileErr.stack || compileErr.message));
          return;
        }

        // Clean any residual export statements in compiled code so new Function never throws SyntaxError
        compiled = compiled.replace(/export\\s+default\\s+(function\\s+[a-zA-Z0-9_$]+)/g, '$1');
        compiled = compiled.replace(/export\\s+default\\s+/g, 'const __AppExport = ');
        compiled = compiled.replace(/export\\s+(const|let|var|function|class)\\s+/g, '$1 ');
        compiled = compiled.replace(/export\\s*\\{[^}]*\\};?/g, '');

        const excluded = new Set([
          'React', 'ReactDOM', 'useState', 'useEffect', 'useRef', 'useMemo', 'useCallback',
          'createContext', 'useContext', 'useReducer', 'cn', 'clsx', 'twMerge', 'motion', 'AnimatePresence'
        ]);
        const iconDecls = importedIcons
          .filter(id => id && !excluded.has(id) && /^[A-Z][a-zA-Z0-9_$]*$/.test(id))
          .map(id => 'const ' + id + ' = LucideIcons.' + id + ';')
          .join('\\n');

        const probeCandidates = candidateNames
          .filter(n => n && !excluded.has(n))
          .map(n => 'if (!__Target && typeof ' + n + ' !== "undefined" && typeof ' + n + ' === "function") __Target = ' + n + ';')
          .join('\\n');

        const runnerCode = [
          iconDecls,
          compiled,
          'let __Target = null;',
          detectedName ? ('if (typeof ' + detectedName + ' !== "undefined" && typeof ' + detectedName + ' === "function") __Target = ' + detectedName + ';') : '',
          probeCandidates,
          'if (!__Target && typeof GlassCounter !== "undefined") __Target = GlassCounter;',
          'if (!__Target && typeof App !== "undefined") __Target = App;',
          'if (!__Target && typeof CounterApp !== "undefined") __Target = CounterApp;',
          'if (!__Target && typeof Counter !== "undefined") __Target = Counter;',
          'if (!__Target && typeof DarkGlassCounter !== "undefined") __Target = DarkGlassCounter;',
          'if (!__Target && typeof DarkGlassmorphismCounter !== "undefined") __Target = DarkGlassmorphismCounter;',
          'if (!__Target && typeof GlassButtonSystem !== "undefined") __Target = GlassButtonSystem;',
          'if (!__Target && typeof ButtonSystem !== "undefined") __Target = ButtonSystem;',
          'if (!__Target && typeof __AppExport !== "undefined" && typeof __AppExport === "function") __Target = __AppExport;',
          'if (!__Target) {',
          '  const globals = Object.keys(window).filter(k => /^[A-Z][a-zA-Z0-9]+$/.test(k) && typeof window[k] === "function");',
          '  for (const k of globals) {',
          '    if (k !== "React" && k !== "ReactDOM" && k !== "Babel") { __Target = window[k]; break; }',
          '  }',
          '}',
          'return __Target;'
        ].join('\\n');

        let factory = null;
        try {
          factory = new Function(
            'React', 'ReactDOM', 'useState', 'useEffect', 'useRef', 'useMemo', 'useCallback',
            'createContext', 'useContext', 'useReducer', 'cn', 'clsx', 'twMerge', 'LucideIcons',
            'motion', 'AnimatePresence',
            runnerCode
          );
        } catch (fnErr) {
          showError('Component Factory Creation Error:', (fnErr.stack || fnErr.message));
          return;
        }

        let Component = null;
        try {
          Component = factory(
            React, ReactDOM, React.useState, React.useEffect, React.useRef, React.useMemo, React.useCallback,
            React.createContext, React.useContext, React.useReducer, cn, clsx, twMerge, LucideIcons,
            motion, AnimatePresence
          );
        } catch (factoryExecErr) {
          showError('Component Factory Call Error:', (factoryExecErr.stack || factoryExecErr.message));
          return;
        }

        if (!Component || typeof Component !== 'function') {
          showError('Component Mount Error:', 'No valid React component function was returned from the code.');
          return;
        }

        try {
          const rootEl = document.getElementById('root');
          const root = ReactDOM.createRoot(rootEl);
          root.render(React.createElement(SandboxErrorBoundary, null, React.createElement(Component)));
        } catch (renderErr) {
          showError('Component Render Error:', (renderErr.stack || renderErr.message));
          return;
        }
      } catch (err) {
        showError('Component Execution Error:', (err.stack || err.message));
      }
    });
  </script>
</body>
</html>`;
}

function buildHtmlSandboxDoc(html) {
  let cleanHtml = (html || '').replace(/^\s*```[a-zA-Z0-9_\-\+]*\s*\n?/gi, '').replace(/\n?```\s*$/gi, '').trim();

  if (cleanHtml.includes('<!DOCTYPE html>') || cleanHtml.includes('<html')) {
    return cleanHtml;
  }
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <base href="${window.location.origin}/"/>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {
      --viz-text: #f1f5f9;
      --viz-muted: #94a3b8;
      --viz-panel: rgba(255, 255, 255, 0.05);
      --viz-border: rgba(255, 255, 255, 0.15);
      --viz-accent: #6366f1;
      --viz-accent-bg: rgba(99, 102, 241, 0.2);
    }
    body {
      margin: 0;
      padding: 16px;
      background: #0b0f19;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
  </style>
</head>
<body>
  ${cleanHtml}
</body>
</html>`;
}

// Runs first inside every sandbox document. The iframe has an opaque origin, so the real
// localStorage/sessionStorage throw; artifacts get per-render in-memory stand-ins instead.
const SANDBOX_SHIM = `<script>(function(){function mk(){var d=Object.create(null);return{getItem:function(k){k=String(k);return k in d?d[k]:null},setItem:function(k,v){d[String(k)]=String(v)},removeItem:function(k){delete d[String(k)]},clear:function(){d=Object.create(null)},key:function(i){return Object.keys(d)[i]||null},get length(){return Object.keys(d).length}}}['localStorage','sessionStorage'].forEach(function(n){try{window[n].getItem('x')}catch(e){try{Object.defineProperty(window,n,{value:mk(),configurable:true})}catch(_){}}});})();</script>`;

function withSandboxShims(doc) {
  if (/<head[^>]*>/i.test(doc)) return doc.replace(/<head[^>]*>/i, (m) => m + SANDBOX_SHIM);
  return SANDBOX_SHIM + doc;
}

function buildSvgSandboxDoc(content) {
  const svg = (content || '').includes('<svg') ? content : `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">${content || ''}</svg>`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <style>
    html, body { margin: 0; height: 100%; }
    body { display: flex; align-items: center; justify-content: center; background: transparent; }
    body > svg { max-width: 100%; max-height: 100%; }
  </style>
</head>
<body>${svg}</body>
</html>`;
}

function buildMermaidSandboxDoc(code) {
  // JSON-encode and escape '<' so diagram text can't close the script tag.
  const source = JSON.stringify((code || '').trim()).replace(/</g, '\\u003c');
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <style>
    body { margin: 0; padding: 16px; background: #0b0f19; color: #f1f5f9; display: flex; justify-content: center; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    .notice { padding: 16px; background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; border-radius: 8px; color: #fca5a5; white-space: pre-wrap; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body>
  <div id="out">Rendering diagram...</div>
  <script>
    (async function () {
      const out = document.getElementById('out');
      const code = ${source};
      try {
        mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' });
        const { svg } = await mermaid.render('mermaid-svg-' + Date.now(), code);
        out.innerHTML = svg;
      } catch (err) {
        out.className = 'notice';
        out.textContent = 'Mermaid Syntax / Render Notice: ' + ((err && err.message) || 'Syntax error') + '\\n\\n' + code;
      }
    })();
  </script>
</body>
</html>`;
}

function handleStreamingArtifact(content, isFinished = false) {
  content = convertGenUiToArtifact(content);
  const artifactRegex = /<antArtifact\s+([^>]+)>([\s\S]*?)(?:<\/antArtifact>|$)/gi;
  let match;
  while ((match = artifactRegex.exec(content)) !== null) {
    const rawAttrs = match[1];
    const extractedCode = match[2];
    const isTagClosed = /<\/antArtifact\s*>/i.test(match[0]);
    const attrs = parseXmlAttributes(rawAttrs);
    const id = attrs.identifier;
    if (!id) continue;

    const type = attrs.type || 'application/vnd.ant.code';
    const title = attrs.title || id;
    const lang = attrs.language || '';
    const cleanCode = stripArtifactCodeFences(extractedCode);

    if (!state.artifacts[id]) {
      state.artifacts[id] = {
        identifier: id,
        type: type,
        title: title,
        language: lang,
        currentVersion: 1,
        versions: [{ version: 1, content: cleanCode, timestamp: Date.now() }],
        isStreaming: !isTagClosed && !isFinished,
      };
      openArtifact(id);
    } else {
      const art = state.artifacts[id];
      if (!art.isStreaming && !isTagClosed && !isFinished) {
        const newVer = art.versions.length + 1;
        art.versions.push({ version: newVer, content: cleanCode, timestamp: Date.now() });
        art.currentVersion = newVer;
        art.title = title;
        art.type = type;
        art.language = lang;
        art.isStreaming = true;
        openArtifact(id, newVer);
      } else {
        const curVerIdx = (art.currentVersion || 1) - 1;
        if (art.versions[curVerIdx]) {
          art.versions[curVerIdx].content = cleanCode;
        }
        art.isStreaming = !isTagClosed && !isFinished;
      }
    }

    if (state.activeArtifactId === id) {
      const codeEl = document.getElementById('artifact-code-content');
      const gutterEl = document.getElementById('artifact-code-gutter');
      if (codeEl) {
        codeEl.textContent = cleanCode;
      }
      if (gutterEl) {
        const lineCount = (cleanCode.match(/\n/g) || []).length + 1;
        if (gutterEl._lastLineCount !== lineCount) {
          gutterEl._lastLineCount = lineCount;
          let gutterHtml = '';
          for (let i = 1; i <= lineCount; i++) {
            gutterHtml += `<div class="line-number">${i}</div>`;
          }
          gutterEl.innerHTML = gutterHtml;
        }
      }
      if (isTagClosed || isFinished) {
        const art = state.artifacts[id];
        renderArtifactContent(art, art.currentVersion);
        updateVersionStepper(art);
      }
    }
  }
}

function initArtifactsWorkbench() {
  const resizer = document.getElementById('artifact-resizer');
  const wb = document.getElementById('artifact-workbench');
  if (resizer) resizer.style.display = 'none';
  if (wb) wb.style.display = 'none';

  const toggle = document.getElementById('toggle-artifacts-enable');
  if (toggle) {
    toggle.checked = state.enableArtifacts;
    toggle.addEventListener('change', () => {
      state.enableArtifacts = toggle.checked;
      showToast(state.enableArtifacts ? 'Eclipse Artifacts enabled' : 'Eclipse Artifacts disabled', 'info');
    });
  }

  const btnPrev = document.getElementById('btn-artifact-preview');
  const btnCode = document.getElementById('btn-artifact-code');
  if (btnPrev) btnPrev.addEventListener('click', () => switchArtifactView('preview'));
  if (btnCode) btnCode.addEventListener('click', () => switchArtifactView('code'));

  const prevVerBtn = document.getElementById('btn-artifact-prev-ver');
  const nextVerBtn = document.getElementById('btn-artifact-next-ver');
  if (prevVerBtn) prevVerBtn.addEventListener('click', () => switchArtifactVersion(-1));
  if (nextVerBtn) nextVerBtn.addEventListener('click', () => switchArtifactVersion(1));

  const copyBtn = document.getElementById('btn-artifact-copy');
  if (copyBtn) copyBtn.addEventListener('click', copyActiveArtifactCode);

  const moreBtn = document.getElementById('btn-artifact-more');
  if (moreBtn) moreBtn.addEventListener('click', toggleArtifactMenu);

  document.addEventListener('click', (e) => {
    const splitBtn = document.getElementById('artifact-split-btn');
    const menu = document.getElementById('artifact-dropdown-menu');
    if (menu && splitBtn && !splitBtn.contains(e.target)) {
      menu.style.display = 'none';
    }
  });

  const dlBtn = document.getElementById('btn-artifact-download');
  if (dlBtn) dlBtn.addEventListener('click', downloadActiveArtifact);

  const fsBtn = document.getElementById('btn-artifact-fullscreen');
  if (fsBtn) fsBtn.addEventListener('click', toggleArtifactFullscreen);

  const closeBtn = document.getElementById('btn-artifact-close');
  if (closeBtn) closeBtn.addEventListener('click', closeArtifactWorkbench);

  initArtifactResizer();
}

function initArtifactResizer() {
  const resizer = document.getElementById('artifact-resizer');
  const workspace = document.getElementById('playground-workspace');
  if (!resizer || !workspace) return;

  let isDragging = false;

  const startDrag = (e) => {
    isDragging = true;
    resizer.classList.add('is-dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const doDrag = (e) => {
    if (!isDragging) return;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    if (!clientX) return;
    const rect = workspace.getBoundingClientRect();
    const offset = clientX - rect.left;
    const pct = Math.max(25, Math.min(75, (offset / rect.width) * 100));
    workspace.style.setProperty('--chat-pane-width', `${pct}%`);
  };

  const stopDrag = () => {
    if (isDragging) {
      isDragging = false;
      resizer.classList.remove('is-dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  };

  resizer.addEventListener('mousedown', startDrag);
  window.addEventListener('mousemove', doDrag);
  window.addEventListener('mouseup', stopDrag);

  resizer.addEventListener('touchstart', startDrag, { passive: true });
  window.addEventListener('touchmove', doDrag, { passive: true });
  window.addEventListener('touchend', stopDrag, { passive: true });
}

// ===================================================================
// Playground Background (clean minimal backdrop, no animation overhead)
// ===================================================================
function initPlaygroundLightLines() {
  // Background effect removed per design preference & performance
}

function initPlayground() {
  const sendBtn = document.getElementById('btn-send-chat');
  const input = document.getElementById('chat-input');
  const tempRange = document.getElementById('temp-range');
  const tempVal = document.getElementById('temp-val');
  const clearBtn = document.getElementById('btn-clear-chat');
  const inputModelName = document.getElementById('input-model-name');
  if (inputModelName) inputModelName.textContent = formatModelDisplayName(state.selectedModel || 'gemini-3.8-flash');

  // Initialize dynamic time-aware greeting
  updateHeroGreeting(false);
  const heroTrigger = document.getElementById('claude-hero-trigger');
  if (heroTrigger) {
    heroTrigger.addEventListener('click', () => updateHeroGreeting(true));
  }

  // Parameters Popover Toggle (Settings)
  const btnToggleSettings = document.getElementById('btn-toggle-playground-settings');
  const settingsDropdown = document.getElementById('playground-settings-dropdown');
  const btnCloseSettings = document.getElementById('btn-close-pg-settings');

  if (btnToggleSettings && settingsDropdown) {
    btnToggleSettings.addEventListener('click', (e) => {
      e.stopPropagation();
      settingsDropdown.classList.toggle('open');
      if (settingsDropdown.classList.contains('open')) {
        loadModelSettings(state.selectedModel || 'gemini-3.8-flash');
        renderParamModelSelectOptions();
      }
    });
    if (btnCloseSettings) {
      btnCloseSettings.addEventListener('click', () => {
        settingsDropdown.classList.remove('open');
      });
    }
    document.addEventListener('click', (e) => {
      if (!settingsDropdown.contains(e.target) && !btnToggleSettings.contains(e.target)) {
        settingsDropdown.classList.remove('open');
      }
    });
  }

  // Model Parameter Overrides (Thinking Budget, Max Tokens, Temperature)
  const thinkingRange = document.getElementById('thinking-budget-range');
  const maxTokensRange = document.getElementById('max-tokens-range');
  const maxTokensVal = document.getElementById('max-tokens-val');
  const btnSaveSettings = document.getElementById('btn-save-model-settings');
  const btnResetSettings = document.getElementById('btn-reset-model-settings');

  if (thinkingRange) {
    thinkingRange.addEventListener('input', () => {
      updateThinkingBudgetDisplay(thinkingRange.value);
    });
    thinkingRange.addEventListener('change', () => {
      saveCurrentModelSettings(false);
    });
  }

  const thinkingBtns = document.querySelectorAll('#thinking-preset-btns .preset-btn');
  thinkingBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tokens = parseInt(btn.dataset.tokens, 10);
      if (thinkingRange) thinkingRange.value = tokens;
      updateThinkingBudgetDisplay(tokens);
      saveCurrentModelSettings(true);
    });
  });

  if (maxTokensRange && maxTokensVal) {
    maxTokensRange.addEventListener('input', () => {
      const val = parseInt(maxTokensRange.value, 10);
      maxTokensVal.textContent = `${val.toLocaleString()} tokens`;
    });
    maxTokensRange.addEventListener('change', () => {
      saveCurrentModelSettings(false);
    });
  }

  const maxTokensBtns = document.querySelectorAll('#max-tokens-preset-btns .preset-btn');
  maxTokensBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tokens = parseInt(btn.dataset.tokens, 10);
      if (maxTokensRange) maxTokensRange.value = tokens;
      if (maxTokensVal) maxTokensVal.textContent = `${tokens.toLocaleString()} tokens`;
      maxTokensBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      saveCurrentModelSettings(true);
    });
  });

  if (tempRange && tempVal) {
    tempRange.addEventListener('input', () => {
      tempVal.textContent = parseFloat(tempRange.value).toFixed(2);
    });
    tempRange.addEventListener('change', () => {
      saveCurrentModelSettings(false);
    });
  }

  const sysPromptInput = document.getElementById('system-prompt-input');
  if (sysPromptInput) {
    sysPromptInput.addEventListener('change', () => {
      saveCurrentModelSettings(false);
    });
  }

  const btnSaveGlobal = document.getElementById('btn-save-global-settings');
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', () => {
      saveCurrentModelSettings(true, false);
    });
  }

  if (btnSaveGlobal) {
    btnSaveGlobal.addEventListener('click', () => {
      saveCurrentModelSettings(true, true);
    });
  }

  if (btnResetSettings) {
    btnResetSettings.addEventListener('click', resetCurrentModelSettings);
  }

  // Initial load of model settings
  loadModelSettings(state.selectedModel || 'gemini-3.8-flash');

  // Lightbox close & download
  const btnCloseLightbox = document.getElementById('btn-lightbox-close');
  const btnDownloadLightbox = document.getElementById('btn-lightbox-download');
  const lightboxModal = document.getElementById('playground-lightbox');

  if (btnCloseLightbox) {
    btnCloseLightbox.addEventListener('click', closeMediaLightbox);
  }
  if (btnDownloadLightbox) {
    btnDownloadLightbox.addEventListener('click', () => {
      if (currentLightboxSrc) {
        downloadMediaFile(currentLightboxSrc, `eclipse-export-${Date.now()}.png`);
      }
    });
  }
  if (lightboxModal) {
    lightboxModal.addEventListener('click', (e) => {
      if (e.target === lightboxModal) {
        closeMediaLightbox();
      }
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeMediaLightbox();
    }
  });

  // Delegated code copy action for code blocks rendered in chat history
  const chatHistoryEl = document.getElementById('chat-history');
  if (chatHistoryEl) {
    chatHistoryEl.addEventListener('click', (e) => {
      const btn = e.target.closest('.chat-code-copy-btn');
      if (!btn) return;
      const b64 = btn.getAttribute('data-code-b64');
      if (!b64) return;
      try {
        const code = decodeURIComponent(escape(atob(b64)));
        navigator.clipboard.writeText(code).then(() => {
          const span = btn.querySelector('span');
          if (span) span.textContent = 'Copied!';
          btn.classList.add('copied');
          setTimeout(() => {
            if (span) span.textContent = 'Copy';
            btn.classList.remove('copied');
          }, 2000);
        });
      } catch (err) {
        console.error('Code copy failed:', err);
      }
    });
  }

  // Floating Scroll-to-Bottom FAB controller
  const scrollFab = document.getElementById('btn-scroll-bottom');
  if (chatHistoryEl && scrollFab) {
    const updateScrollFab = () => {
      const scrollDist = chatHistoryEl.scrollHeight - chatHistoryEl.scrollTop - chatHistoryEl.clientHeight;
      if (scrollDist > 160) {
        scrollFab.classList.add('visible');
      } else {
        scrollFab.classList.remove('visible');
      }
    };
    chatHistoryEl.addEventListener('scroll', updateScrollFab, { passive: true });
    scrollFab.addEventListener('click', () => {
      chatHistoryEl.scrollTo({ top: chatHistoryEl.scrollHeight, behavior: 'smooth' });
      scrollFab.classList.remove('visible');
    });
  }

  // Auto-grow textarea & send button enabling
  if (input) {
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 180) + 'px';
      if (sendBtn) {
        sendBtn.disabled = !input.value.trim() || state.isStreaming;
      }
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        const isMobileTouch = window.matchMedia('(max-width: 768px)').matches && window.matchMedia('(pointer: coarse)').matches;
        if (!isMobileTouch) {
          e.preventDefault();
          sendChatMessage();
        }
      }
    });
  }

  if (sendBtn) sendBtn.addEventListener('click', sendChatMessage);

  // Mobile: swipe/scroll chat thread dismisses soft keyboard
  if (chatHistoryEl && input) {
    let touchStartY = 0;
    chatHistoryEl.addEventListener('touchstart', (e) => {
      if (e.touches && e.touches[0]) touchStartY = e.touches[0].clientY;
    }, { passive: true });
    chatHistoryEl.addEventListener('touchmove', (e) => {
      if (e.touches && e.touches[0] && Math.abs(e.touches[0].clientY - touchStartY) > 18) {
        if (document.activeElement === input) {
          input.blur();
        }
      }
    }, { passive: true });
  }

  // Claude Suggestion Pills & Legacy Chips Click
  document.addEventListener('click', (e) => {
    const pill = e.target.closest('.claude-pill-btn, .hero-chip');
    if (pill) {
      const prompt = pill.getAttribute('data-prompt');
      if (input && prompt) {
        input.value = prompt;
        input.focus();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        if (sendBtn) sendBtn.disabled = false;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 180) + 'px';
      }
    }
  });



  // Attachment button
  const attachBtn = document.getElementById('claude-attach-btn');
  const fileInput = document.getElementById('claude-file-input');
  if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        showToast(`Attached ${e.target.files.length} file(s)`, 'info');
      }
    });
  }

  // Clear Chat Button Handler
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      state.chatMessages = [];
      state.artifacts = {};
      state.activeArtifactId = null;
      closeArtifactWorkbench();
      const history = document.getElementById('chat-history');
      const thread = history?.querySelector('.chat-thread-container');
      if (thread) thread.innerHTML = '';
      const workspace = document.getElementById('playground-workspace');
      if (workspace) workspace.classList.remove('has-messages');
      document.body.classList.remove('dock-vertical');
      window.EclipseGlassDock?.updateDockMode(false);
      const heroEl = document.getElementById('playground-hero');
      if (heroEl) heroEl.classList.remove('hidden');
      updateHeroGreeting(true);
      if (input) {
        input.value = '';
        input.style.height = 'auto';
      }
      if (sendBtn) sendBtn.disabled = true;
      showToast('Chat history cleared', 'info');
    });
  }

  // Initialize Artifacts Workbench controls & resizer
  initArtifactsWorkbench();
}

function formatShortMonthDate(date = new Date()) {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[date.getMonth()]} ${date.getDate()}`;
}

function cleanTextForSpeech(raw) {
  if (!raw) return '';
  return raw
    .replace(/<antArtifact[\s\S]*?<\/antArtifact>/gi, 'Interactive artifact rendered.')
    .replace(/<[^>]+>/g, '')
    .replace(/```[\s\S]*?```/g, 'Code block omitted.')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/[*_#~>]/g, '')
    .replace(/data:image\/[a-zA-Z+]+;base64,[A-Za-z0-9+/=]+/g, '')
    .replace(/https?:\/\/[^\s]+/g, 'link')
    .replace(/\s+/g, ' ')
    .trim();
}

// Fast client-side audio cache for immediate replay
const _clientAudioBlobCache = new Map();

function splitTextIntoSpeechChunks(text) {
  if (text.length <= 180) return [text];
  // Break on sentence boundaries (. ! ? \n)
  const sentences = text.match(/[^.!?\n]+[.!?\n]*/g) || [text];
  const chunks = [];
  let currentChunk = '';
  for (const s of sentences) {
    const trimmed = s.trim();
    if (!trimmed) continue;
    if ((currentChunk + ' ' + trimmed).length > 200 && currentChunk) {
      chunks.push(currentChunk.trim());
      currentChunk = trimmed;
    } else {
      currentChunk = currentChunk ? (currentChunk + ' ' + trimmed) : trimmed;
    }
  }
  if (currentChunk.trim()) {
    chunks.push(currentChunk.trim());
  }
  return chunks.length > 0 ? chunks : [text];
}

async function playAssistantAudio(text, containerEl = null, onFinish = null) {
  const speechText = cleanTextForSpeech(text);
  if (!speechText) {
    if (onFinish) onFinish();
    return;
  }

  // Stop any active audio
  if (state.currentAudio) {
    try {
      state.currentAudio.pause();
      state.currentAudio = null;
    } catch (e) {}
  }
  if (window.speechSynthesis && window.speechSynthesis.speaking) {
    try {
      window.speechSynthesis.cancel();
    } catch (e) {}
  }

  const voiceModel = state.voiceModel || 'ais-gemini-3.8-flash-tts';
  const voiceTimbre = state.voiceTimbre || 'Puck';

  // Create UI Player Bar if container is provided
  let playerBar = null;
  let playBtn = null;
  if (containerEl && !containerEl.querySelector('.assistant-voice-bar')) {
    playerBar = document.createElement('div');
    playerBar.className = 'assistant-voice-bar';
    playerBar.innerHTML = `
      <button type="button" class="assistant-voice-play-btn" title="Pause audio">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16"></rect>
          <rect x="14" y="4" width="4" height="16"></rect>
        </svg>
      </button>
      <span style="font-weight:600;">Speaking (${escapeHtml(voiceTimbre)})</span>
      <span style="opacity:0.75; font-size:10px; margin-left:auto;">${escapeHtml(formatModelDisplayName(voiceModel))}</span>
    `;
    playBtn = playerBar.querySelector('.assistant-voice-play-btn');
    playBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!state.currentAudio) return;
      if (state.currentAudio.paused) {
        state.currentAudio.play();
        playBtn.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';
      } else {
        state.currentAudio.pause();
        playBtn.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
      }
    });
    containerEl.appendChild(playerBar);
  }

  // Progressive streaming audio chunks for fast time-to-first-sound
  const chunks = splitTextIntoSpeechChunks(speechText);
  let isCancelled = false;

  async function fetchAudioBlob(chunkText) {
    const cacheKey = `${voiceTimbre}:${chunkText}`;
    if (_clientAudioBlobCache.has(cacheKey)) {
      return _clientAudioBlobCache.get(cacheKey);
    }
    const res = await fetch('/v1/audio/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: chunkText,
        model: voiceModel,
        voice: voiceTimbre,
        response_format: 'mp3',
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error?.message || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    if (blob.size < 200) {
      throw new Error('Invalid audio data received');
    }
    _clientAudioBlobCache.set(cacheKey, blob);
    return blob;
  }

  try {
    // 1. Fetch first chunk to start speech rapidly
    const firstBlob = await fetchAudioBlob(chunks[0]);
    if (isCancelled) return;

    // Concurrently prefetch remaining chunks
    const chunkPromises = chunks.slice(1).map(chunk => fetchAudioBlob(chunk).catch(e => {
      console.warn('Subsequent chunk fetch error:', e);
      return null;
    }));

    // Sequential audio playback
    let currentIdx = 0;
    const playNextChunk = async (blob) => {
      if (!blob || isCancelled) {
        if (playerBar) playerBar.remove();
        state.currentAudio = null;
        if (onFinish) onFinish();
        return;
      }

      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      state.currentAudio = audio;

      audio.onended = async () => {
        currentIdx++;
        if (currentIdx < chunks.length) {
          const nextBlob = await chunkPromises[currentIdx - 1];
          playNextChunk(nextBlob);
        } else {
          if (playerBar) playerBar.remove();
          state.currentAudio = null;
          if (onFinish) onFinish();
        }
      };

      audio.onerror = () => {
        if (playerBar) playerBar.remove();
        state.currentAudio = null;
        if (onFinish) onFinish();
      };

      await audio.play();
    };

    await playNextChunk(firstBlob);

  } catch (err) {
    console.error('Gemini TTS playback error:', err);
    if (playerBar) playerBar.remove();
    state.currentAudio = null;
    showToast(`Gemini TTS Error: ${err.message}`, 'error');
    if (onFinish) onFinish();
  }
}

function initVoiceModeControls() {
  const btn = document.getElementById('btn-voice-chat');
  const popover = document.getElementById('voice-models-popover');
  const masterToggle = document.getElementById('voice-mode-master-toggle');
  const autoSpeakToggle = document.getElementById('voice-auto-speak-checkbox');
  const previewBtn = document.getElementById('btn-preview-voice');
  const timbreChips = document.getElementById('voice-timbre-chips');
  const timbreLabel = document.getElementById('voice-timbre-display-label');
  const statusSubtitle = document.getElementById('voice-status-subtitle');

  if (!btn || !popover) return;
  if (btn._voiceControlsInit) return;
  btn._voiceControlsInit = true;

  // Prevent internal interactions (toggles, chips, model selections) from bubbling to document dismiss handler
  popover.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // Guarantee popover starts completely hidden
  popover.style.display = 'none';
  popover.classList.remove('open');
  btn.classList.remove('open');
  btn.setAttribute('aria-expanded', 'false');

  // Restore state
  state.voiceModeEnabled = localStorage.getItem('eclipse_voice_mode') === 'true';
  state.voiceModel = localStorage.getItem('eclipse_voice_model') || 'ais-gemini-3.8-flash-tts';
  state.voiceTimbre = localStorage.getItem('eclipse_voice_timbre') || 'Puck';
  state.voiceAutoSpeak = localStorage.getItem('eclipse_voice_autospeak') !== 'false';

  if (masterToggle) masterToggle.checked = state.voiceModeEnabled;
  if (autoSpeakToggle) autoSpeakToggle.checked = state.voiceAutoSpeak;
  btn.classList.toggle('active', state.voiceModeEnabled);
  if (timbreLabel) timbreLabel.textContent = state.voiceTimbre;
  if (statusSubtitle) {
    statusSubtitle.textContent = state.voiceModeEnabled ? 'Live Voice Active • Auto-speaking' : 'Neural Speech Synthesis';
  }

  if (timbreChips) {
    timbreChips.querySelectorAll('.voice-timbre-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.voice === state.voiceTimbre);
    });
  }

  function renderVoiceModelsList() {
    const listEl = document.getElementById('voice-models-options-list');
    if (!listEl) return;

    let voiceModels = state.models.filter(m => {
      return (m.capabilities && (m.capabilities.includes('tts') || m.capabilities.includes('speech') || m.capabilities.includes('audio') || m.capabilities.includes('transcribe') || m.capabilities.includes('voice'))) ||
        /(?:-tts\b|-live\b|-transcribe\b)/i.test(m.id) ||
        /(tts|speech|transcribe|real-time voice)/i.test(m.name || '');
    });

    if (voiceModels.length === 0) {
      voiceModels = [
        { id: 'ais-gemini-3.8-flash-tts', name: 'Gemini 3.8 Flash TTS', description: 'Studio-grade expressive voice generation' },
        { id: 'ais-gemini-3.8-flash-lite-tts', name: 'Gemini 3.8 Flash-Lite TTS', description: 'Low-latency streaming speech synthesis' },
        { id: 'ais-gemini-3.8-live', name: 'Gemini 3.8 Live', description: 'Bidirectional real-time voice conversation' },
        { id: 'ais-gemini-3.8-live-thinking', name: 'Gemini 3.8 Live Thinking', description: 'Real-time voice with extended reasoning' },
        { id: 'ais-gemini-3.5-transcribe', name: 'Gemini 3.5 Transcribe', description: 'Structured audio transcription & analysis' },
      ];
    }

    listEl.innerHTML = voiceModels.map(m => {
      const isSel = m.id === state.voiceModel;
      return `
        <div class="voice-model-item ${isSel ? 'active' : ''}" data-id="${escapeHtml(m.id)}">
          <div class="voice-model-info">
            <span class="voice-model-title">${escapeHtml(m.name)}</span>
            <span class="voice-model-desc">${escapeHtml(m.description || m.id)}</span>
          </div>
          <svg class="voice-model-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
      `;
    }).join('');

    listEl.querySelectorAll('.voice-model-item').forEach(item => {
      item.addEventListener('click', () => {
        window.triggerHaptic?.(8);
        const mId = item.dataset.id;
        state.voiceModel = mId;
        localStorage.setItem('eclipse_voice_model', mId);
        renderVoiceModelsList();
        showToast(`Voice model: ${formatModelDisplayName(mId)}`, 'info');
      });
    });
  }

  renderVoiceModelsList();
  window.addEventListener('eclipse-models-loaded', renderVoiceModelsList);

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isCurrentlyOpen = popover.classList.contains('open') && popover.style.display !== 'none';
    if (!isCurrentlyOpen) {
      popover.style.display = 'flex';
      void popover.offsetWidth; // trigger layout reflow
      popover.classList.add('open');
      btn.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      renderVoiceModelsList();
    } else {
      popover.classList.remove('open');
      btn.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
      setTimeout(() => {
        if (!popover.classList.contains('open')) {
          popover.style.display = 'none';
        }
      }, 180);
    }
  });

  document.addEventListener('click', (e) => {
    if (!popover.contains(e.target) && !btn.contains(e.target)) {
      if (popover.classList.contains('open') || popover.style.display !== 'none') {
        popover.classList.remove('open');
        btn.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
        setTimeout(() => {
          if (!popover.classList.contains('open')) {
            popover.style.display = 'none';
          }
        }, 180);
      }
    }
  });

  masterToggle?.addEventListener('change', (e) => {
    state.voiceModeEnabled = e.target.checked;
    localStorage.setItem('eclipse_voice_mode', String(state.voiceModeEnabled));
    btn.classList.toggle('active', state.voiceModeEnabled);
    if (statusSubtitle) {
      statusSubtitle.textContent = state.voiceModeEnabled ? 'Live Voice Active • Auto-speaking' : 'Neural Speech Synthesis';
    }
    showToast(state.voiceModeEnabled ? 'Voice Conversation Mode enabled' : 'Voice Mode disabled', state.voiceModeEnabled ? 'success' : 'info');
  });

  autoSpeakToggle?.addEventListener('change', (e) => {
    state.voiceAutoSpeak = e.target.checked;
    localStorage.setItem('eclipse_voice_autospeak', String(state.voiceAutoSpeak));
  });

  timbreChips?.addEventListener('click', (e) => {
    const chip = e.target.closest('.voice-timbre-chip');
    if (!chip) return;
    const voiceName = chip.dataset.voice;
    state.voiceTimbre = voiceName;
    localStorage.setItem('eclipse_voice_timbre', voiceName);
    if (timbreLabel) timbreLabel.textContent = voiceName;
    timbreChips.querySelectorAll('.voice-timbre-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    showToast(`Voice timbre: ${voiceName}`, 'info');
  });

  const openStudioBtn = document.getElementById('btn-open-voice-studio');
  openStudioBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    openVoiceStudioModal();
  });

  previewBtn?.addEventListener('click', async () => {
    if (previewBtn.classList.contains('playing')) {
      if (state.currentAudio) {
        state.currentAudio.pause();
        state.currentAudio = null;
      }
      previewBtn.classList.remove('playing');
      return;
    }

    const testPhrases = {
      Puck: 'Hello! I am ready to converse with you using natural, studio-quality speech.',
      Charon: 'Greetings. The system is active, and I am prepared for your questions.',
      Aoede: 'Welcome! I look forward to assisting you in our voice conversation.',
      Fenrir: 'Eclipse audio engine initialized. Let us begin.',
      Kore: 'Voice channel online. Clarity and responsiveness optimized.',
      'The Meditation Guide': 'Take a slow, deep breath in... and let it go. You are safe here, relaxed and completely at ease.',
      'The Grizzled Detective': 'It was two in the morning when she walked into my office. Rain was hitting the blinds, and trouble was right behind her.',
      'The Hype Announcer': 'Ladies and gentlemen, welcome to the main event! Make some noise!',
      'The Regal Monarch': 'Silence. When the crown speaks, the realm listens with utmost reverence.',
      'The Everyday Assistant': 'Good morning! I have prepared your schedule and notes for today. How can I assist you?',
      'The Guarded NPC': 'Halt, traveler. What business brings you to our gates at this hour?',
      'The Energetic Co-Host': 'Welcome back to the stream, everyone! We have got an amazing topic lined up today.',
      'The Master Storyteller': 'Deep within the forgotten ruins of the ancient world, a secret was waiting to be unveiled.',
    };
    const sample = testPhrases[state.voiceTimbre] || `Hello! You are listening to the ${state.voiceTimbre} voice persona on Gemini 3.8 Flash TTS.`;

    previewBtn.classList.add('playing');
    const labelSpan = previewBtn.querySelector('span');
    if (labelSpan) labelSpan.textContent = 'Playing...';

    await playAssistantAudio(sample, null, () => {
      previewBtn.classList.remove('playing');
      if (labelSpan) labelSpan.textContent = 'Preview';
    });
  });
}

// -----------------------------------------------------------------------------
// Voice Design Studio & Extended Voice Library (Google Gemini 3.8 Flash TTS)
// -----------------------------------------------------------------------------
let _voiceStudioInitialized = false;
let _studioAuditionAudio = null;
let _allVoicesList = [];
let _lastAuditionedVoice = null;
let _activeCardAudio = null;
let _activePlayingCardBtn = null;

function openVoiceStudioModal() {
  initVoiceStudio();
  const modal = document.getElementById('voice-studio-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  void modal.offsetWidth;
  modal.classList.add('open');
  updateVoiceStudioActiveLabel();
  loadAndRenderVoiceLibrary();
}

function closeVoiceStudioModal() {
  const modal = document.getElementById('voice-studio-modal');
  if (!modal) return;
  modal.classList.remove('open');
  if (_studioAuditionAudio) {
    _studioAuditionAudio.pause();
    _studioAuditionAudio = null;
  }
  if (_activeCardAudio) {
    _activeCardAudio.pause();
    _activeCardAudio = null;
  }
  if (_activePlayingCardBtn) {
    _activePlayingCardBtn.classList.remove('playing');
    _activePlayingCardBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
    _activePlayingCardBtn = null;
  }
  setTimeout(() => {
    if (!modal.classList.contains('open')) {
      modal.style.display = 'none';
    }
  }, 220);
}

function updateVoiceStudioActiveLabel() {
  const lbl = document.getElementById('voice-studio-current-active-label');
  if (lbl) lbl.textContent = state.voiceTimbre || 'Puck';
}

function initVoiceStudio() {
  if (_voiceStudioInitialized) return;
  _voiceStudioInitialized = true;

  const modal = document.getElementById('voice-studio-modal');
  const dialog = modal?.querySelector('.voice-studio-dialog');
  const closeBtn = document.getElementById('btn-close-voice-studio');
  const tabExplore = document.getElementById('tab-btn-explore-voices');
  const tabDesign = document.getElementById('tab-btn-design-voice');
  const panelExplore = document.getElementById('panel-explore-voices');
  const panelDesign = document.getElementById('panel-design-voice');
  const searchInput = document.getElementById('voice-library-search');
  const filterChips = document.getElementById('voice-category-filters');
  const nameInput = document.getElementById('input-design-voice-name');
  const promptInput = document.getElementById('textarea-design-voice-prompt');
  const charCounter = document.getElementById('voice-prompt-counter');
  const generateBtn = document.getElementById('btn-generate-custom-voice');
  const saveBtn = document.getElementById('btn-save-use-custom-voice');
  const auditionPlayBtn = document.getElementById('btn-audition-toggle-play');

  closeBtn?.addEventListener('click', closeVoiceStudioModal);
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) closeVoiceStudioModal();
  });
  dialog?.addEventListener('click', (e) => e.stopPropagation());

  // Tab switching
  tabExplore?.addEventListener('click', () => {
    tabExplore.classList.add('active');
    tabDesign?.classList.remove('active');
    if (panelExplore) panelExplore.style.display = 'flex';
    if (panelDesign) panelDesign.style.display = 'none';
  });

  tabDesign?.addEventListener('click', () => {
    tabDesign.classList.add('active');
    tabExplore?.classList.remove('active');
    if (panelDesign) panelDesign.style.display = 'flex';
    if (panelExplore) panelExplore.style.display = 'none';
  });

  // Prompt counter
  promptInput?.addEventListener('input', () => {
    if (charCounter) charCounter.textContent = `${promptInput.value.length} chars`;
  });

  // Inspiration chips
  document.querySelectorAll('.voice-insp-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (promptInput) promptInput.value = chip.dataset.prompt || '';
      if (nameInput) nameInput.value = chip.dataset.name || '';
      if (charCounter && promptInput) charCounter.textContent = `${promptInput.value.length} chars`;
    });
  });

  // Search filtering
  searchInput?.addEventListener('input', () => {
    filterAndRenderCards();
  });

  // Category filters
  filterChips?.addEventListener('click', (e) => {
    const chip = e.target.closest('.voice-filter-chip');
    if (!chip) return;
    filterChips.querySelectorAll('.voice-filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    filterAndRenderCards();
  });

  // Generate / Synthesize custom voice
  generateBtn?.addEventListener('click', async () => {
    const prompt = (promptInput?.value || '').trim();
    const name = (nameInput?.value || '').trim() || 'Custom Persona';
    if (!prompt) {
      showToast('Please describe the vocal persona in the prompt box', 'warning');
      promptInput?.focus();
      return;
    }

    generateBtn.classList.add('loading');
    generateBtn.innerHTML = `
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
        <path d="M12 2a10 10 0 0 1 10 10" stroke-width="2.5"></path>
      </svg>
      <span>Synthesizing Voice Persona...</span>
    `;

    try {
      const res = await fetch('/v1/audio/voices/design', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, prompt }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      _lastAuditionedVoice = data;

      // Update preview card
      const nameLbl = document.getElementById('voice-preview-name-label');
      const descLbl = document.getElementById('voice-preview-desc-label');
      const playerBox = document.getElementById('voice-audition-player');
      if (nameLbl) nameLbl.textContent = data.name;
      if (descLbl) descLbl.textContent = data.description || prompt;
      if (playerBox) playerBox.style.display = 'flex';
      if (saveBtn) saveBtn.disabled = false;

      // Play audio sample
      if (data.sample_audio) {
        playAuditionSample("data:audio/wav;base64," + data.sample_audio);
      } else {
        const sampleText = `Hello! I am ${name}. ${prompt}`;
        auditionVoiceWithText(name, sampleText);
      }
      showToast(`Voice '${name}' synthesized successfully!`, 'success');
    } catch (err) {
      console.error('Voice Design error:', err);
      showToast('Failed to synthesize custom voice. Check backend log.', 'error');
    } finally {
      generateBtn.classList.remove('loading');
      generateBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Synthesize & Audition Voice</span>
      `;
    }
  });

  // Audition toggle play
  auditionPlayBtn?.addEventListener('click', () => {
    if (_studioAuditionAudio) {
      if (_studioAuditionAudio.paused) {
        _studioAuditionAudio.play();
        setAuditionPlayingState(true);
      } else {
        _studioAuditionAudio.pause();
        setAuditionPlayingState(false);
      }
    } else if (_lastAuditionedVoice) {
      const sampleText = `Hello! I am ${_lastAuditionedVoice.name}. ${_lastAuditionedVoice.prompt}`;
      auditionVoiceWithText(_lastAuditionedVoice.name, sampleText);
    }
  });

  // Save & Use Custom Voice
  saveBtn?.addEventListener('click', () => {
    if (!_lastAuditionedVoice) return;
    const voiceName = _lastAuditionedVoice.name;
    setActiveVoice(voiceName);
    showToast(`Voice '${voiceName}' set as active speech persona!`, 'success');
    if (tabExplore) tabExplore.click();
    loadAndRenderVoiceLibrary();
  });
}

function setAuditionPlayingState(isPlaying) {
  const btn = document.getElementById('btn-audition-toggle-play');
  const wave = document.querySelector('.voice-audition-wave-visualizer');
  if (wave) wave.classList.toggle('playing', isPlaying);
  if (btn) {
    btn.innerHTML = isPlaying
      ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>'
      : '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
  }
}

function playAuditionSample(audioSrc) {
  if (_studioAuditionAudio) {
    _studioAuditionAudio.pause();
    _studioAuditionAudio = null;
  }
  const audio = new Audio(audioSrc);
  _studioAuditionAudio = audio;
  audio.onplay = () => setAuditionPlayingState(true);
  audio.onended = () => setAuditionPlayingState(false);
  audio.onerror = () => setAuditionPlayingState(false);
  audio.play().catch(() => {});
}

async function auditionVoiceWithText(voiceNameOrId, text) {
  try {
    setAuditionPlayingState(true);
    const res = await fetch('/v1/audio/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: text,
        model: 'ais-gemini-3.8-flash-tts',
        voice: voiceNameOrId,
        response_format: 'mp3',
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error?.message || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    if (blob.size < 200) throw new Error('Received invalid audio data');
    playAuditionSample(URL.createObjectURL(blob));
  } catch (err) {
    console.error('Audition error:', err);
    setAuditionPlayingState(false);
    showToast(`Audition preview unavailable: ${err.message}`, 'warning');
  }
}

async function loadAndRenderVoiceLibrary() {
  try {
    const res = await fetch('/v1/audio/voices');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _allVoicesList = data.voices || [];
    filterAndRenderCards();
  } catch (err) {
    console.warn('Failed to load voices from API, using defaults:', err);
    _allVoicesList = [
      { id: 'grizzled-detective', name: 'The Grizzled Detective', description: 'Low, gravelly, world-weary noir narration.', type: 'curated', gender: 'Male / Deep' },
      { id: 'meditation-guide', name: 'The Meditation Guide', description: 'Airy, hushed, endlessly patient.', type: 'curated', gender: 'Female / Soft' },
      { id: 'hype-announcer', name: 'The Hype Announcer', description: 'Booming, rapid, arena-sized energy.', type: 'curated', gender: 'Male / Resonant' },
      { id: 'regal-monarch', name: 'The Regal Monarch', description: 'Measured, precise, quietly commanding.', type: 'curated', gender: 'Female / Noble' },
      { id: 'everyday-assistant', name: 'The Everyday Assistant', description: 'A helpful and professional personal assistant.', type: 'curated', gender: 'Neutral / Friendly' },
      { id: 'guarded-npc', name: 'The Guarded NPC', description: 'Creates multi-character dialogue in a fantasy setting.', type: 'curated', gender: 'Male / Gritty' },
      { id: 'energetic-co-host', name: 'The Energetic Co-Host', description: 'Podcast style conversational delivery.', type: 'curated', gender: 'Female / Dynamic' },
      { id: 'master-storyteller', name: 'The Master Storyteller', description: 'Crafts rich, immersive storytelling narration.', type: 'curated', gender: 'Male / Rich' },
      { id: 'Puck', name: 'Puck', description: 'Dynamic, lively, expressive storytelling & natural cadence', type: 'prebuilt', gender: 'Neutral / Expressive' },
      { id: 'Charon', name: 'Charon', description: 'Calm, authoritative, thoughtful and grounding', type: 'prebuilt', gender: 'Male / Deep' },
      { id: 'Aoede', name: 'Aoede', description: 'Warm, melodious, empathetic and clear conversational tone', type: 'prebuilt', gender: 'Female / Warm' },
      { id: 'Fenrir', name: 'Fenrir', description: 'Strong, resonant, confident and energetic pacing', type: 'prebuilt', gender: 'Male / Strong' },
      { id: 'Kore', name: 'Kore', description: 'Bright, lucid, precise and crisp articulation', type: 'prebuilt', gender: 'Female / Bright' },
    ];
    filterAndRenderCards();
  }
}

function filterAndRenderCards() {
  const grid = document.getElementById('voice-cards-grid');
  if (!grid) return;
  const search = (document.getElementById('voice-library-search')?.value || '').toLowerCase().trim();
  const activeCatChip = document.querySelector('#voice-category-filters .voice-filter-chip.active');
  const cat = activeCatChip?.dataset.cat || 'all';

  const filtered = _allVoicesList.filter(v => {
    if (cat === 'curated' && v.type !== 'curated') return false;
    if (cat === 'prebuilt' && v.type !== 'prebuilt') return false;
    if (cat === 'custom' && v.type !== 'custom') return false;
    if (search) {
      const matchName = (v.name || '').toLowerCase().includes(search);
      const matchDesc = (v.description || '').toLowerCase().includes(search);
      const matchGender = (v.gender || '').toLowerCase().includes(search);
      return matchName || matchDesc || matchGender;
    }
    return true;
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.45); font-size: 13px;">
        No voices match your search filter. Try designing a custom voice in the 'Design Custom Voice' tab!
      </div>
    `;
    return;
  }

  const currentActive = state.voiceTimbre || 'Puck';

  grid.innerHTML = filtered.map(v => {
    const isAct = v.name === currentActive || v.id === currentActive;
    const typeLabel = v.type === 'custom' ? 'Custom Designed' : (v.type === 'curated' ? 'Curated Persona' : 'Foundational');
    const badge = v.gender || (v.type === 'custom' ? 'User Vault' : 'Studio');
    return `
      <div class="voice-card ${isAct ? 'active' : ''}" data-id="${escapeHtml(v.id || v.name)}" data-name="${escapeHtml(v.name)}">
        <div class="voice-card-top">
          <div class="voice-card-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="4" y="9" width="2" height="6" rx="1"></rect>
              <rect x="8" y="5" width="2" height="14" rx="1"></rect>
              <rect x="12" y="2" width="2" height="20" rx="1"></rect>
              <rect x="16" y="6" width="2" height="12" rx="1"></rect>
              <rect x="20" y="10" width="2" height="4" rx="1"></rect>
            </svg>
          </div>
          <button type="button" class="voice-card-play-btn" title="Audition ${escapeHtml(v.name)}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
          </button>
        </div>
        <div class="voice-card-info">
          <div class="voice-card-title">
            <span>${escapeHtml(v.name)}</span>
            <span class="voice-card-badge">${escapeHtml(badge)}</span>
          </div>
          <div class="voice-card-desc">${escapeHtml(v.description || 'Natural expressive speech persona.')}</div>
        </div>
        <div class="voice-card-footer">
          <span class="voice-card-type-tag">${escapeHtml(typeLabel)}</span>
          <button type="button" class="voice-card-select-btn">${isAct ? '✓ Active' : 'Use Voice'}</button>
        </div>
      </div>
    `;
  }).join('');

  const CARD_AUDITION_SAMPLES = {
    'The Meditation Guide': "Take a slow, deep breath in... and let it go. You are safe here, relaxed and completely at ease.",
    'meditation-guide': "Take a slow, deep breath in... and let it go. You are safe here, relaxed and completely at ease.",
    'The Grizzled Detective': "It was two in the morning when she walked into my office. Rain was hitting the blinds, and trouble was right behind her.",
    'grizzled-detective': "It was two in the morning when she walked into my office. Rain was hitting the blinds, and trouble was right behind her.",
    'The Hype Announcer': "Ladies and gentlemen, welcome to the main event! Make some noise!",
    'hype-announcer': "Ladies and gentlemen, welcome to the main event! Make some noise!",
    'The Regal Monarch': "Silence. When the crown speaks, the realm listens with utmost reverence.",
    'regal-monarch': "Silence. When the crown speaks, the realm listens with utmost reverence.",
    'The Everyday Assistant': "Good morning! I have prepared your schedule and notes for today. How can I assist you?",
    'everyday-assistant': "Good morning! I have prepared your schedule and notes for today. How can I assist you?",
    'The Guarded NPC': "Halt, traveler. What business brings you to our gates at this hour?",
    'guarded-npc': "Halt, traveler. What business brings you to our gates at this hour?",
    'The Energetic Co-Host': "Welcome back to the stream, everyone! We've got an amazing topic lined up today.",
    'energetic-co-host': "Welcome back to the stream, everyone! We've got an amazing topic lined up today.",
    'The Master Storyteller': "Deep within the forgotten ruins of the ancient world, a secret was waiting to be unveiled.",
    'master-storyteller': "Deep within the forgotten ruins of the ancient world, a secret was waiting to be unveiled.",
    'Puck': "Hello! I am ready to converse with you using natural, studio-quality speech.",
    'Charon': "Greetings. The system is active, and I am prepared for your questions.",
    'Aoede': "Welcome! I look forward to assisting you in our voice conversation.",
    'Fenrir': "Eclipse audio engine initialized. Let us begin.",
    'Kore': "Voice channel online. Clarity and responsiveness optimized.",
  };

  // Attach card event listeners
  grid.querySelectorAll('.voice-card').forEach(card => {
    const vId = card.dataset.id;
    const vName = card.dataset.name;
    const playBtn = card.querySelector('.voice-card-play-btn');
    const selectBtn = card.querySelector('.voice-card-select-btn');

    playBtn?.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (_activePlayingCardBtn === playBtn && _activeCardAudio && !_activeCardAudio.paused) {
        _activeCardAudio.pause();
        playBtn.classList.remove('playing', 'loading');
        playBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
        return;
      }
      if (_activePlayingCardBtn && _activePlayingCardBtn !== playBtn) {
        _activePlayingCardBtn.classList.remove('playing', 'loading');
        _activePlayingCardBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
      }
      if (_activeCardAudio) {
        _activeCardAudio.pause();
        _activeCardAudio = null;
      }

      playBtn.classList.remove('playing');
      playBtn.classList.add('loading');
      playBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg>';
      _activePlayingCardBtn = playBtn;

      const sampleText = CARD_AUDITION_SAMPLES[vName] || CARD_AUDITION_SAMPLES[vId] || `Hello! You are listening to the ${vName} speech persona on Gemini 3.8 Flash TTS.`;
      const cacheKey = `${vName || vId}:${sampleText}`;

      try {
        let blob = _clientAudioBlobCache.get(cacheKey);
        if (!blob) {
          const res = await fetch('/v1/audio/speech', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              input: sampleText,
              model: 'ais-gemini-3.8-flash-tts',
              voice: vName || vId,
              response_format: 'mp3',
            }),
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error?.message || `HTTP ${res.status}`);
          }
          blob = await res.blob();
          if (blob.size < 200) throw new Error('Received invalid audio response');
          _clientAudioBlobCache.set(cacheKey, blob);
        }

        if (_activePlayingCardBtn !== playBtn) return;

        playBtn.classList.remove('loading');
        playBtn.classList.add('playing');
        playBtn.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';

        const audio = new Audio(URL.createObjectURL(blob));
        _activeCardAudio = audio;
        audio.onended = () => {
          playBtn.classList.remove('playing', 'loading');
          playBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
          _activeCardAudio = null;
          _activePlayingCardBtn = null;
        };
        audio.onerror = () => {
          playBtn.classList.remove('playing', 'loading');
          playBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
          _activeCardAudio = null;
          _activePlayingCardBtn = null;
        };
        await audio.play();
      } catch (err) {
        console.error('Audition error:', err);
        playBtn.classList.remove('playing', 'loading');
        playBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';
        _activePlayingCardBtn = null;
        showToast(`Audition failed: ${err.message}`, 'error');
      }
    });

    selectBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      setActiveVoice(vName || vId);
      showToast(`Active voice set to: ${vName}`, 'info');
      filterAndRenderCards();
    });
  });
}

function setActiveVoice(voiceName) {
  state.voiceTimbre = voiceName;
  localStorage.setItem('eclipse_voice_timbre', voiceName);
  updateVoiceStudioActiveLabel();
  const timbreLabel = document.getElementById('voice-timbre-display-label');
  if (timbreLabel) timbreLabel.textContent = voiceName;
  const timbreChips = document.getElementById('voice-timbre-chips');
  if (timbreChips) {
    timbreChips.querySelectorAll('.voice-timbre-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.voice === voiceName);
    });
  }
}

function createResponseActionBar(assistantMsgEl, fullContent, promptText, modelName, elapsedMs, timestamp = new Date()) {
  if (assistantMsgEl.querySelector('.response-actions')) {
    return;
  }

  const bar = document.createElement('div');
  bar.className = 'response-actions';

  const shortDate = formatShortMonthDate(timestamp);
  const fullDateTime = timestamp.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  // 1. Copy Button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'response-action-btn btn-copy-response';
  copyBtn.setAttribute('data-tooltip', 'Copy');
  copyBtn.setAttribute('aria-label', 'Copy response');
  copyBtn.innerHTML = `
    <svg class="icon-copy" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>
  `;
  copyBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    try {
      const textToCopy = (fullContent || '')
        .replace(/<antArtifact\s+[^>]+>[\s\S]*?<\/antArtifact>/gi, '')
        .replace(/data:image\/[a-zA-Z+]+;base64,[A-Za-z0-9+/=]+/g, '[Image]')
        .trim();
      await navigator.clipboard.writeText(textToCopy);
      copyBtn.innerHTML = `
        <svg class="icon-check" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      copyBtn.setAttribute('data-tooltip', 'Copied!');
      copyBtn.classList.add('active');
      showToast('Copied to clipboard', 'success');

      const tip = document.getElementById('eclipse-tooltip');
      if (tip && tip.classList.contains('visible')) {
        tip.textContent = 'Copied!';
      }

      setTimeout(() => {
        copyBtn.innerHTML = `
          <svg class="icon-copy" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        `;
        copyBtn.setAttribute('data-tooltip', 'Copy');
        copyBtn.classList.remove('active');
      }, 2000);
    } catch (err) {
      console.error('Failed to copy response:', err);
      showToast('Failed to copy to clipboard', 'error');
    }
  });
  bar.appendChild(copyBtn);

  // 2. Read Aloud / Speaker Button
  const speakBtn = document.createElement('button');
  speakBtn.className = 'response-action-btn btn-speak-response';
  speakBtn.setAttribute('data-tooltip', 'Read aloud');
  speakBtn.setAttribute('aria-label', 'Read response aloud');
  speakBtn.innerHTML = `
    <svg class="icon-speak" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
    </svg>
  `;
  speakBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (state.currentAudio && !state.currentAudio.paused) {
      state.currentAudio.pause();
      state.currentAudio = null;
      document.querySelectorAll('.btn-speak-response.active').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('data-tooltip', 'Read aloud');
      });
      return;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      document.querySelectorAll('.btn-speak-response.active').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('data-tooltip', 'Read aloud');
      });
      return;
    }

    const speakText = cleanTextForSpeech(fullContent);
    if (!speakText) return;

    speakBtn.classList.add('active');
    speakBtn.setAttribute('data-tooltip', 'Stop reading');

    const tip = document.getElementById('eclipse-tooltip');
    if (tip && tip.classList.contains('visible')) {
      tip.textContent = 'Stop reading';
    }

    playAssistantAudio(fullContent, assistantMsgEl, () => {
      speakBtn.classList.remove('active');
      speakBtn.setAttribute('data-tooltip', 'Read aloud');
      if (tip && tip.classList.contains('visible')) {
        tip.textContent = 'Read aloud';
      }
    });
  });
  bar.appendChild(speakBtn);

  // 3. Thumbs Up Button
  const thumbsUpBtn = document.createElement('button');
  thumbsUpBtn.className = 'response-action-btn btn-thumbs-up';
  thumbsUpBtn.setAttribute('data-tooltip', 'Good response');
  thumbsUpBtn.setAttribute('aria-label', 'Good response');
  thumbsUpBtn.innerHTML = `
    <svg class="icon-thumbs-up" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
    </svg>
  `;
  thumbsUpBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isCurrentlyActive = thumbsUpBtn.classList.contains('active');
    thumbsDownBtn.classList.remove('active');
    thumbsDownBtn.setAttribute('data-tooltip', 'Bad response');
    if (isCurrentlyActive) {
      thumbsUpBtn.classList.remove('active');
      thumbsUpBtn.setAttribute('data-tooltip', 'Good response');
    } else {
      thumbsUpBtn.classList.add('active');
      thumbsUpBtn.setAttribute('data-tooltip', 'Helpful');
      showToast('Thanks for your feedback!', 'info');
    }
  });
  bar.appendChild(thumbsUpBtn);

  // 4. Thumbs Down Button
  const thumbsDownBtn = document.createElement('button');
  thumbsDownBtn.className = 'response-action-btn btn-thumbs-down';
  thumbsDownBtn.setAttribute('data-tooltip', 'Bad response');
  thumbsDownBtn.setAttribute('aria-label', 'Bad response');
  thumbsDownBtn.innerHTML = `
    <svg class="icon-thumbs-down" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
    </svg>
  `;
  thumbsDownBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isCurrentlyActive = thumbsDownBtn.classList.contains('active');
    thumbsUpBtn.classList.remove('active');
    thumbsUpBtn.setAttribute('data-tooltip', 'Good response');
    if (isCurrentlyActive) {
      thumbsDownBtn.classList.remove('active');
      thumbsDownBtn.setAttribute('data-tooltip', 'Bad response');
    } else {
      thumbsDownBtn.classList.add('active');
      thumbsDownBtn.setAttribute('data-tooltip', 'Reported');
      showToast('Feedback noted', 'info');
    }
  });
  bar.appendChild(thumbsDownBtn);

  // 5. Retry Button
  const retryBtn = document.createElement('button');
  retryBtn.className = 'response-action-btn btn-retry-response';
  retryBtn.setAttribute('data-tooltip', 'Retry');
  retryBtn.setAttribute('aria-label', 'Retry response');
  retryBtn.innerHTML = `
    <svg class="icon-retry" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="23 4 23 10 17 10"></polyline>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
    </svg>
  `;
  retryBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (state.isStreaming) {
      showToast('A message is already generating', 'warning');
      return;
    }
    retryBtn.classList.add('spinning');
    retryChatMessage(promptText, assistantMsgEl);
  });
  bar.appendChild(retryBtn);

  // 6. Response Date Timestamp (short month like Aug, Sep, Oct + day)
  const dateEl = document.createElement('span');
  dateEl.className = 'response-date';
  dateEl.textContent = shortDate;
  dateEl.setAttribute('data-tooltip', `${fullDateTime} • ${modelName || state.selectedModel} (${elapsedMs}ms)`);
  bar.appendChild(dateEl);

  assistantMsgEl.appendChild(bar);
}

function createUserActionBar(userMsgEl, userText, timestamp = new Date()) {
  if (userMsgEl.querySelector('.user-msg-actions')) {
    return;
  }

  const bar = document.createElement('div');
  bar.className = 'user-msg-actions';

  const shortDate = formatShortMonthDate(timestamp);
  const fullDateTime = timestamp.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  // 1. Date Timestamp (short month like Aug, Sep, Oct)
  const dateEl = document.createElement('span');
  dateEl.className = 'user-msg-date';
  dateEl.textContent = shortDate;
  dateEl.setAttribute('data-tooltip', fullDateTime);
  bar.appendChild(dateEl);

  // 2. Retry Button
  const retryBtn = document.createElement('button');
  retryBtn.className = 'response-action-btn btn-retry-user';
  retryBtn.setAttribute('data-tooltip', 'Retry');
  retryBtn.setAttribute('aria-label', 'Retry prompt');
  retryBtn.innerHTML = `
    <svg class="icon-retry" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="23 4 23 10 17 10"></polyline>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
    </svg>
  `;
  retryBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    window.triggerHaptic?.(10);
    if (state.isStreaming) {
      showToast('A message is already generating', 'warning');
      return;
    }
    retryBtn.classList.add('spinning');
    retryUserMessage(userMsgEl, userMsgEl.dataset.promptText || userText);
  });
  bar.appendChild(retryBtn);

  // 3. Edit Button
  const editBtn = document.createElement('button');
  editBtn.className = 'response-action-btn btn-edit-user';
  editBtn.setAttribute('data-tooltip', 'Edit');
  editBtn.setAttribute('aria-label', 'Edit message');
  editBtn.innerHTML = `
    <svg class="icon-edit" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
    </svg>
  `;
  editBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    window.triggerHaptic?.(8);
    if (state.isStreaming) {
      showToast('A message is already generating', 'warning');
      return;
    }
    startInlineUserEdit(userMsgEl, userMsgEl.dataset.promptText || userText, bar);
  });
  bar.appendChild(editBtn);

  // 4. Copy Button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'response-action-btn btn-copy-user';
  copyBtn.setAttribute('data-tooltip', 'Copy');
  copyBtn.setAttribute('aria-label', 'Copy message');
  copyBtn.innerHTML = `
    <svg class="icon-copy" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>
  `;
  copyBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    window.triggerHaptic?.(8);
    try {
      const textToCopy = userMsgEl.dataset.promptText || userText;
      await navigator.clipboard.writeText(textToCopy);
      copyBtn.innerHTML = `
        <svg class="icon-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      copyBtn.setAttribute('data-tooltip', 'Copied!');
      copyBtn.classList.add('active');
      showToast('Copied to clipboard', 'success');

      const tip = document.getElementById('eclipse-tooltip');
      if (tip && tip.classList.contains('visible')) {
        tip.textContent = 'Copied!';
      }

      setTimeout(() => {
        copyBtn.innerHTML = `
          <svg class="icon-copy" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        `;
        copyBtn.setAttribute('data-tooltip', 'Copy');
        copyBtn.classList.remove('active');
      }, 2000);
    } catch (err) {
      console.error('Failed to copy user message:', err);
      showToast('Failed to copy to clipboard', 'error');
    }
  });
  bar.appendChild(copyBtn);

  userMsgEl.appendChild(bar);
}

function retryUserMessage(userMsgEl, userText) {
  if (state.isStreaming) {
    showToast('A message is already generating', 'warning');
    return;
  }

  const history = document.getElementById('chat-history');
  const thread = history?.querySelector('.chat-thread-container');
  if (!thread) return;

  // Remove all siblings following userMsgEl in thread
  let nextEl = userMsgEl.nextElementSibling;
  while (nextEl) {
    const toRemove = nextEl;
    nextEl = nextEl.nextElementSibling;
    toRemove.remove();
  }

  // Find index of this user message among all .chat-msg.user in thread
  const allUserEls = Array.from(thread.querySelectorAll('.chat-msg.user'));
  const userIdx = allUserEls.indexOf(userMsgEl);

  // Slice state.chatMessages up to this user message
  if (userIdx !== -1) {
    let countUsers = 0;
    const newChatMessages = [];
    for (const msg of state.chatMessages) {
      if (msg.role === 'user') {
        if (countUsers === userIdx) {
          newChatMessages.push({ role: 'user', content: userText });
          break;
        }
        countUsers++;
      }
      newChatMessages.push(msg);
    }
    state.chatMessages = newChatMessages;
  } else {
    state.chatMessages = [{ role: 'user', content: userText }];
  }

  const modality = detectQueryModality(state.selectedModel, userText);

  // Append assistant message container
  const assistantMsgEl = document.createElement('div');
  assistantMsgEl.className = 'chat-msg assistant';

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'msg-bubble playground-loader-bubble';

  // Mount the motion graphic thinking loader
  const loaderObj = createThinkingLoader(modality, userText);
  bubbleEl.appendChild(loaderObj.el);
  assistantMsgEl.appendChild(bubbleEl);
  thread.appendChild(assistantMsgEl);

  history.scrollTop = history.scrollHeight;

  runAssistantStream(assistantMsgEl, bubbleEl, loaderObj, userText, modality);
}

function startInlineUserEdit(userMsgEl, userText, actionBar) {
  const bubble = userMsgEl.querySelector('.msg-bubble');
  if (!bubble) return;

  if (userMsgEl.classList.contains('is-editing')) return;
  userMsgEl.classList.add('is-editing');
  if (actionBar) actionBar.style.display = 'none';

  const originalHtml = bubble.innerHTML;
  const currentText = userMsgEl.dataset.promptText || userText;

  // Replace bubble with editor
  bubble.innerHTML = `
    <div class="user-msg-edit-box">
      <textarea class="user-msg-edit-textarea" rows="1" placeholder="Edit your message..."></textarea>
      <div class="user-msg-edit-actions">
        <button type="button" class="user-msg-btn-cancel">Cancel</button>
        <button type="button" class="user-msg-btn-submit">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
          Send
        </button>
      </div>
    </div>
  `;

  const textarea = bubble.querySelector('.user-msg-edit-textarea');
  const cancelBtn = bubble.querySelector('.user-msg-btn-cancel');
  const submitBtn = bubble.querySelector('.user-msg-btn-submit');

  textarea.value = currentText;

  const cancelEdit = () => {
    userMsgEl.classList.remove('is-editing');
    bubble.innerHTML = originalHtml;
    if (actionBar) actionBar.style.display = '';
  };

  const autoResize = () => {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(Math.max(textarea.scrollHeight, 24), 260) + 'px';
    if (textarea.scrollHeight > 260) {
      textarea.style.overflowY = 'auto';
    } else {
      textarea.style.overflowY = 'hidden';
    }
  };

  textarea.addEventListener('input', autoResize);
  setTimeout(() => {
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    autoResize();
  }, 30);

  cancelBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    cancelEdit();
  });

  const submitEdit = () => {
    const newText = textarea.value.trim();
    if (!newText) {
      showToast('Message cannot be empty', 'warning');
      return;
    }

    userMsgEl.classList.remove('is-editing');
    userMsgEl.dataset.promptText = newText;
    bubble.innerHTML = escapeHtml(newText);
    if (actionBar) {
      actionBar.style.display = '';
      actionBar.remove();
      createUserActionBar(userMsgEl, newText, new Date());
    }

    retryUserMessage(userMsgEl, newText);
  };

  submitBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    submitEdit();
  });

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      cancelEdit();
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitEdit();
    }
  });
}

async function retryChatMessage(promptText, failedAssistantEl = null) {
  if (state.isStreaming) {
    showToast('A message is already generating', 'warning');
    return;
  }

  const history = document.getElementById('chat-history');
  const thread = history?.querySelector('.chat-thread-container');
  if (!thread) return;

  // Remove the previous assistant element if supplied
  if (failedAssistantEl && failedAssistantEl.parentNode) {
    failedAssistantEl.remove();
  }

  // Pop previous assistant message from state.chatMessages if present
  if (state.chatMessages.length && state.chatMessages[state.chatMessages.length - 1].role === 'assistant') {
    state.chatMessages.pop();
  }

  const modality = detectQueryModality(state.selectedModel, promptText);

  // Append fresh assistant message container
  const assistantMsgEl = document.createElement('div');
  assistantMsgEl.className = 'chat-msg assistant';

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'msg-bubble playground-loader-bubble';

  const loaderObj = createThinkingLoader(modality, promptText);
  bubbleEl.appendChild(loaderObj.el);
  assistantMsgEl.appendChild(bubbleEl);
  thread.appendChild(assistantMsgEl);

  history.scrollTop = history.scrollHeight;

  await runAssistantStream(assistantMsgEl, bubbleEl, loaderObj, promptText, modality);
}

async function runAssistantStream(assistantMsgEl, bubbleEl, loaderObj, userText, modality) {
  const history = document.getElementById('chat-history');
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('btn-send-chat');

  state.isStreaming = true;
  if (sendBtn) sendBtn.disabled = true;

  const systemPrompt = document.getElementById('system-prompt-input')?.value.trim();
  const messagesPayload = [];
  if (systemPrompt) {
    messagesPayload.push({ role: 'system', content: systemPrompt });
  }
  messagesPayload.push(...state.chatMessages);

  const temperature = parseFloat(document.getElementById('temp-range')?.value || 0.7);
  const thinkingBudget = parseInt(document.getElementById('thinking-budget-range')?.value || 0, 10);
  const maxTokens = parseInt(document.getElementById('max-tokens-range')?.value || 4096, 10);

  const requestTools = state.toolsEnabled && !!window.EclipseToolSteps;
  let toolGroup = null;
  const ensureToolGroup = () => {
    if (!toolGroup) {
      toolGroup = window.EclipseToolSteps.createGroup();
      assistantMsgEl.insertBefore(toolGroup.root, bubbleEl);
    }
    return toolGroup;
  };

  let fullContent = '';
  let fullReasoning = '';
  let reasoningBox = null;
  const startTime = performance.now();
  let hasTransformedToText = false;

  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-eclipse-artifacts': state.enableArtifacts ? 'true' : 'false',
      },
      body: JSON.stringify({
        model: state.selectedModel,
        messages: messagesPayload,
        temperature: temperature,
        max_tokens: maxTokens,
        thinking_budget: thinkingBudget,
        artifacts: state.enableArtifacts,
        stream: true,
        ...(requestTools ? { eclipse_tools: window.EclipseToolSteps.TOOL_NAMES } : {}),
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      if (loaderObj.finish) loaderObj.finish();
      bubbleEl.classList.remove('playground-loader-bubble');
      bubbleEl.innerHTML = `<span style="color: var(--color-error);">Error: ${escapeHtml(errText)}</span>`;
      const elapsed = Math.round(performance.now() - startTime);
      createResponseActionBar(assistantMsgEl, `Error: ${errText}`, userText, state.selectedModel, elapsed, new Date());
      state.isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    // RAF Batching: Throttle DOM Markdown rendering to display refresh rate (~60fps)
    // instead of running 25+ regular expressions synchronously on every single SSE chunk
    let streamRafId = null;
    let pendingStreamContent = '';
    let pendingArtifactCheck = false;

    const scheduleStreamRender = (rawText, checkArtifacts) => {
      pendingStreamContent = rawText;
      if (checkArtifacts) pendingArtifactCheck = true;
      if (streamRafId) return;
      streamRafId = requestAnimationFrame(() => {
        streamRafId = null;
        if (!pendingStreamContent) return;
        const display = convertGenUiToArtifact(pendingStreamContent);
        if (state.enableArtifacts && pendingArtifactCheck && (display.includes('<antArtifact') || pendingStreamContent.includes('※genui※'))) {
          handleStreamingArtifact(display, false);
          pendingArtifactCheck = false;
        }
        const contentBox = bubbleEl.querySelector('.chat-md-content');
        if (contentBox) {
          contentBox.innerHTML = renderMarkdown(display);
        } else {
          bubbleEl.innerHTML = `<div class="chat-md-content">${renderMarkdown(display)}</div>`;
        }
        const isNearBottom = (history.scrollHeight - history.scrollTop - history.clientHeight) < 160;
        if (isNearBottom) {
          history.scrollTop = history.scrollHeight;
        }
      });
    };

    const flushStreamRender = (rawText) => {
      if (streamRafId) {
        cancelAnimationFrame(streamRafId);
        streamRafId = null;
      }
      const display = convertGenUiToArtifact(rawText);
      const contentBox = bubbleEl.querySelector('.chat-md-content');
      if (contentBox) {
        contentBox.innerHTML = renderMarkdown(display);
      } else {
        bubbleEl.innerHTML = `<div class="chat-md-content">${renderMarkdown(display)}</div>`;
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep remainder

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;
        const rawJson = trimmed.substring(6).trim();
        if (rawJson === '[DONE]') continue;

        try {
          const parsed = JSON.parse(rawJson);
          const delta = parsed.choices?.[0]?.delta || {};

          // Tool loop progress: a step began, a tool started or finished
          if (delta.eclipse_event && requestTools) {
            ensureToolGroup().handleEvent(delta.eclipse_event);
            history.scrollTop = history.scrollHeight;
          }

          // Reasoning Content Delta
          if (delta.reasoning_content) {
            fullReasoning += delta.reasoning_content;
            if (requestTools) {
              ensureToolGroup().addReasoning(delta.reasoning_content);
            } else {
              if (!reasoningBox) {
                reasoningBox = document.createElement('div');
                reasoningBox.className = 'reasoning-box';
                reasoningBox.innerHTML = `
                  <div class="reasoning-summary">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
                    Thinking Process Trace
                  </div>
                  <div class="reasoning-content"></div>
                `;
                assistantMsgEl.insertBefore(reasoningBox, bubbleEl);
              }
              reasoningBox.querySelector('.reasoning-content').textContent = fullReasoning;
            }
          }

          // Main Content Delta
          if (delta.content) {
            const cleanDelta = delta.content
              .replace(/[※\u203B][^\s]*/g, '')
              .replace(/\bcite[a-zA-Z0-9_]*turn[a-zA-Z0-9_]*\b/gi, '')
              .replace(/\bturn\d+[a-zA-Z0-9_]*\b/gi, '')
              .replace(/[\uE200-\uE20F]message_reaction[\uE200-\uE20F][^\uE200-\uE20F]*[\uE200-\uE20F]/g, '')
              .replace(/[\uE200-\uE20F]/g, '');
            fullContent += cleanDelta;
            if (toolGroup && cleanDelta.trim()) toolGroup.noteAnswerStarted();

            // Stream thinking trace if tag is present (e.g. from models outputting <antThinking>)
            const thinkingMatch = fullContent.match(/<antThinking>([\s\S]*?)(?:<\/antThinking>|$)/i);
            if (thinkingMatch && thinkingMatch[1] && !delta.reasoning_content) {
              const streamedThinking = thinkingMatch[1].trim();
              if (streamedThinking) {
                if (!reasoningBox) {
                  reasoningBox = document.createElement('div');
                  reasoningBox.className = 'reasoning-box';
                  reasoningBox.innerHTML = `
                    <div class="reasoning-summary">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
                      Thinking Process Trace
                    </div>
                    <div class="reasoning-content"></div>
                  `;
                  assistantMsgEl.insertBefore(reasoningBox, bubbleEl);
                }
                const reasoningContentEl = reasoningBox.querySelector('.reasoning-content');
                if (reasoningContentEl) reasoningContentEl.textContent = streamedThinking;
              }
            }

            // Check if chunks contain base64 image or video data
            const isBase64Stream = fullContent.includes('data:image/') || fullContent.includes('data:video/') || /[A-Za-z0-9+/=]{180,}/.test(fullContent);

            if (isBase64Stream) {
              if (loaderObj.updateProgress) {
                loaderObj.updateProgress(92);
              }
            } else {
              if (!hasTransformedToText) {
                hasTransformedToText = true;
                if (loaderObj.finish) loaderObj.finish();
                bubbleEl.classList.remove('playground-loader-bubble');
                bubbleEl.innerHTML = '<div class="chat-md-content"></div>';
              }
              // Batch render via RAF to ensure smooth 60fps on mobile/low-end devices
              scheduleStreamRender(fullContent, true);
            }
          }
        } catch (e) {
          // ignore chunk parse errors
        }
      }
    }

    // Flush any pending stream text and finalize artifact
    flushStreamRender(fullContent);

    // Finalize streaming artifact once stream finishes
    const finalDisplayContent = convertGenUiToArtifact(fullContent);
    if (state.enableArtifacts && (finalDisplayContent.includes('<antArtifact') || fullContent.includes('※genui※'))) {
      handleStreamingArtifact(finalDisplayContent, true);
    }

    if (loaderObj.finish) loaderObj.finish();
    bubbleEl.classList.remove('playground-loader-bubble');

    // Finalize tools work group & display sources row if present
    if (toolGroup) {
      toolGroup.finish();
      const sources = toolGroup.sources ? toolGroup.sources() : [];
      if (sources && sources.length && window.EclipseToolSteps) {
        const sourcesRow = window.EclipseToolSteps.renderSourcesRow(sources);
        if (sourcesRow) assistantMsgEl.insertBefore(sourcesRow, bubbleEl.nextSibling);
      }
    }

    const elapsed = Math.round(performance.now() - startTime);
    state.chatMessages.push({ role: 'assistant', content: finalDisplayContent });

    // Parse and render rich interactive media cards (without any raw base64!)
    parseAndRenderMediaContent(assistantMsgEl, bubbleEl, fullContent, fullReasoning, userText, modality);

    // Create Claude-grade interactive response action bar
    createResponseActionBar(assistantMsgEl, fullContent, userText, state.selectedModel, elapsed, new Date());
    window.dispatchEvent(new CustomEvent('eclipse-chat-updated'));

    // Voice Conversation Mode: Automatically speak assistant response aloud when active
    if (state.voiceModeEnabled && state.voiceAutoSpeak) {
      playAssistantAudio(fullContent, assistantMsgEl);
    }

  } catch (err) {
    if (loaderObj.finish) loaderObj.finish();
    bubbleEl.classList.remove('playground-loader-bubble');
    bubbleEl.innerHTML = `<span style="color: var(--color-error);">Stream Failed: ${escapeHtml(err.message)}</span>`;
    const elapsed = Math.round(performance.now() - startTime);
    createResponseActionBar(assistantMsgEl, `Stream Failed: ${err.message}`, userText, state.selectedModel, elapsed, new Date());
  } finally {
    state.isStreaming = false;
    if (sendBtn && input) sendBtn.disabled = !input.value.trim();
    history.scrollTop = history.scrollHeight;
  }
}

async function sendChatMessage() {
  if (state.isStreaming) return;

  const input = document.getElementById('chat-input');
  const userText = input.value.trim();
  if (!userText) return;

  window.triggerHaptic?.(12);

  // Toggle active chat workspace mode & shift dock to left vertical format
  const workspace = document.getElementById('playground-workspace');
  if (workspace) {
    workspace.classList.add('has-messages');
  }
  document.body.classList.add('dock-vertical');
  window.EclipseGlassDock?.updateDockMode(true);

  // Hide the centered playground hero when sending message
  const heroEl = document.getElementById('playground-hero');
  if (heroEl) {
    heroEl.classList.add('hidden');
  }

  input.value = '';
  input.style.height = '24px';

  const history = document.getElementById('chat-history');
  let thread = history.querySelector('.chat-thread-container');
  if (!thread) {
    thread = document.createElement('div');
    thread.className = 'chat-thread-container';
    history.appendChild(thread);
  }

  // Append user message
  const userMsgEl = document.createElement('div');
  userMsgEl.className = 'chat-msg user';
  userMsgEl.dataset.promptText = userText;
  userMsgEl.innerHTML = `<div class="msg-bubble">${escapeHtml(userText)}</div>`;
  createUserActionBar(userMsgEl, userText, new Date());
  thread.appendChild(userMsgEl);

  state.chatMessages.push({ role: 'user', content: userText });

  // Detect modality: 'image', 'video', or 'text'
  const modality = detectQueryModality(state.selectedModel, userText);

  // Append assistant message container
  const assistantMsgEl = document.createElement('div');
  assistantMsgEl.className = 'chat-msg assistant';

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'msg-bubble playground-loader-bubble';

  // Mount the motion graphic thinking loader
  const loaderObj = createThinkingLoader(modality, userText);
  bubbleEl.appendChild(loaderObj.el);
  assistantMsgEl.appendChild(bubbleEl);
  thread.appendChild(assistantMsgEl);

  history.scrollTop = history.scrollHeight;

  await runAssistantStream(assistantMsgEl, bubbleEl, loaderObj, userText, modality);
}

// ===================================================================
// Copy Endpoint Action
// ===================================================================
function initCopyAction() {
  const btn = document.getElementById('btn-copy-url');
  const urlSpan = document.getElementById('gateway-url-text');
  const stChip = document.getElementById('chip-sillytavern');

  function getGatewayBaseUrl() {
    const host = window.location.host;
    const proto = window.location.protocol;
    // Auto-detect reachable host on phone / LAN / ngrok tunnel
    if (host && !host.includes('localhost') && !host.startsWith('127.0.0.1')) {
      return `${proto}//${host}/v1`;
    }
    return `${proto}//${host || 'localhost:5000'}/v1`;
  }

  // Initialize displayed URL if currently default localhost but user is on LAN/Tunnel
  if (urlSpan) {
    const base = getGatewayBaseUrl();
    if (stChip && stChip.classList.contains('active')) {
      urlSpan.textContent = base + '/chat/completions';
    } else {
      urlSpan.textContent = base;
    }
  }

  if (btn) {
    btn.addEventListener('click', async () => {
      const text = urlSpan ? urlSpan.textContent.trim() : getGatewayBaseUrl();
      const success = await copyTextToClipboard(text);
      if (success) {
        window.triggerHaptic?.(12);
        showToast('Copied endpoint to clipboard: ' + text, 'success');

        // Tactile button visual feedback
        const origContent = btn.innerHTML;
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: #4ade80;">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span style="color: #4ade80; font-weight: 600;">Copied!</span>
        `;
        btn.classList.add('btn-copied-success');
        setTimeout(() => {
          btn.innerHTML = origContent;
          btn.classList.remove('btn-copied-success');
        }, 2200);
      } else {
        showToast('Failed to copy. Please long-press the text to copy.', 'error');
      }
    });
  }

  if (stChip) {
    stChip.addEventListener('click', () => {
      if (!urlSpan) return;
      const base = getGatewayBaseUrl();
      if (urlSpan.textContent.endsWith('/chat/completions')) {
        urlSpan.textContent = base;
        stChip.classList.remove('active');
        showToast('Switched to Base URL: ' + base, 'info');
      } else {
        urlSpan.textContent = base + '/chat/completions';
        stChip.classList.add('active');
        showToast('Appended /chat/completions for SillyTavern', 'success');
      }
    });
  }
}

// ===================================================================
// Cloud Tunnel (ngrok Remote Access)
// ===================================================================
async function fetchTunnelStatus() {
  try {
    const res = await fetch('/api/tunnel/status');
    if (!res.ok) return;
    const data = await res.json();
    state.tunnel = data;
    updateTunnelUI();
  } catch (err) {
    console.error('Failed to fetch tunnel status:', err);
  }
}

function updateTunnelUI() {
  const t = state.tunnel || { status: 'offline' };
  const isOnline = t.status === 'online' && !!t.public_url;
  const isInstalled = t.installed !== false;

  // Sidebar badge
  const navBadge = document.getElementById('nav-tunnel-badge');
  if (navBadge) {
    navBadge.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
    navBadge.className = `nav-badge ${isOnline ? 'online' : 'offline'}`;
  }

  // Toggle button text & styles
  const toggleBtn = document.getElementById('btn-toggle-tunnel');
  const toggleBtnText = document.getElementById('btn-toggle-tunnel-text');
  if (toggleBtn && toggleBtnText) {
    if (isOnline) {
      toggleBtn.className = 'btn btn-secondary btn-sm';
      toggleBtnText.textContent = 'Stop Tunnel';
    } else {
      toggleBtn.className = 'btn btn-primary btn-sm';
      toggleBtnText.textContent = isInstalled ? 'Start ngrok Tunnel' : 'Install & Start Tunnel';
    }
  }

  // Install native ngrok button
  const installBtn = document.getElementById('btn-install-tunnel');
  const installBtnText = document.getElementById('btn-install-tunnel-text');
  if (installBtn) {
    if (!isInstalled) {
      installBtn.style.display = 'inline-flex';
      if (installBtnText) {
        installBtnText.textContent = t.is_termux ? 'Install ngrok (Termux Phone)' : 'Install ngrok (Native)';
      }
    } else {
      installBtn.style.display = 'none';
    }
  }

  // URL Display Box & Text
  const urlText = document.getElementById('tunnel-url-text');
  if (urlText) {
    if (isOnline) {
      urlText.textContent = `${t.public_url}/v1/chat/completions`;
    } else {
      if (!isInstalled) {
        urlText.textContent = t.is_termux
          ? '📱 Phone Mode: ngrok not yet installed in Termux — Click "Install ngrok" to install natively!'
          : 'Offline — Click "Install & Start Tunnel" to set up natively for this device';
      } else {
        urlText.textContent = 'Offline — Click "Start ngrok Tunnel" to expose';
      }
    }
  }

  // Authtoken input placeholder
  const tokenInput = document.getElementById('input-ngrok-authtoken');
  if (tokenInput && t.has_authtoken && !tokenInput.value) {
    tokenInput.placeholder = '✓ Authtoken configured (paste new token to update)';
  }

  // Sync ThreeUI rotating typographic globe sphere theme
  if (state.currentTab === 'tunnel') {
    syncGlobeTheme(isOnline);
    updateUptimeDisplay();
  }
}

// ===================================================================
// Direct Typographic World Sphere Canvas Engine (In-Site, No Iframe)
// ===================================================================
var globeAnimationId = null;
var globeRunning = false;
var globeCanvas = null;
var globeCtx = null;
var globeWidth = 0;
var globeHeight = 0;
var globeDpr = 1;
var globeInk = '226,228,233';
var globeInk64 = [];
var GLOBE_SOFT = 0.88;

function updateGlobeInk(inkRgb) {
  globeInk = inkRgb || '226,228,233';
  globeInk64 = [];
  for (var q = 0; q < 64; q++) {
    globeInk64.push('rgba(' + globeInk + ',' + ((q / 63) * GLOBE_SOFT).toFixed(4) + ')');
  }
}
updateGlobeInk('226,228,233');

function getGlobeInk(a) {
  return globeInk64[a <= 0 ? 0 : a >= 1 ? 63 : (a * 63) | 0];
}

var GLOBE_QA = (Math.PI * 2) / 64;
function globeQang(a) {
  return Math.round(a / GLOBE_QA) * GLOBE_QA;
}

var GLOBE_LAND_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPcBAOD/HwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACA//+P//f/LwgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4/v/4/////wcAAAAEAPABAAAAfAAAAAAAAAAAAAAAAAAAAADg9w/4/////wEAAP4AAAAAAAAA+AAAAAAAAAAAAAAAAAAAAIAG+Of//////wAAAHwGAAAAAAAAAAMAAAAAAAAAAAAAAACABwAc/4P//////wAAADAAAAAAQAAAAD4AAAAAAAAAAAAAAAAAfMbDcQAA/v///wAAAAAAAADABwAA//8HAMAPAAAAAAAAAABgAAAAAAAA/P///wAAAAAAAABwAADg//8AAAAAAAAAAAAAAADwG457dwcA8P//HwAAAAAAAAAYAAD///9/eAAAAAAAAAAAAAD4/g0H/w8A8P//PwAAAAAAAAAOgOv/////fwD/AAAAAAA/AAAA/B84/v8A8P//LwAAAAD4AAAA4PP//////////wAAAOD///H/+D/3cPgDoP//DwAAAID/BwAAx/v/////////P4AA/P///////////////////////w8AAOcBAAgAAAAAAAAAAAAAgP///////////////////////wcAACYAAAQAAAAAAAAAAAAAgf///////////////////////wMM8AAAAAAAAAAAAAAAAAAAIID/////////e+wPwH8AgA8AAP/5z/////////////////8/ANH///////9/AIALgD8AAAAAwH/+//////////////////9/APj///////8fADwAAD8AAAAA8D/+//////////////////sPAPC/+f////8fAPwAADgAAAAA8D/+////////////////D/wBAMCfAP////8PAPwYAAAAAAAA8H/4//////////////9/DgcAAAAcAOD///8/APw/AAAAAAAQAB7w//////////////8BgAMAAAACAMD/////Afh/AAAAAAA4gBz+/////////////38A4AMAAMAAAMD/////B/z/AAAAAABwwAb+/////////////x8A8AEAAAAAAAD/////P///AwAAAADmgOH//////////////z8A4AAAAAAAAAD+////P/7/BwAAAAD28P////////////////8D4AAAAAAAAAD8////f/7/BwAAAADz+f////////////////8HIAAAAAAAAAD6////////BAAAAABw/v////////////////8EAAAAAAAAAADo//////8jHgAAAACA//////////////////8MAAAAAAAAAADQ//////8OPgAAAADw//////////////////8AAAAAAAAAAADg//////+PIAAAAADA////v////////////38EAAAAAAAAAADg////////AAAAAACA//v/zD/8/////////z8AAAAAAAAAAADg//////8bAAAAAACA//N/gD///////////x8GAAAAAAAAAADw//////8AAAAAAAD+B8c/AD/+/////////wcPAAAAAAAAAADg//////8AAAAAAAD+gx4/DH74/////////wABAAAAAAAAAADg/////x8AAAAAAAD+gbCn///8////////fQABAAAAAAAAAADg/////w8AAAAAAAD/gCDn///4//////9/MgADAAAAAAAAAADA/////w8AAAAAAAD+AADm/3/4//////8/cIABAAAAAAAAAADA/////wcAAAAAAAA44AHC///5////////4+ABAAAAAAAAAACA/////wcAAAAAAACI/wEA4P//////////4OgAAAAAAAAAAAAA/////wMAAAAAAAD4/wAA4P//////////ADYAAAAAAAAAAAAA/P///wEAAAAAAAD+/wEA8P//////////AQcAAAAAAAAAAAAA+P//fwAAAAAAAAD//w8P8P//////////AQEAAAAAAAAAAAAAyP//fwAAAAAAAAD//3//////////////AQAAAAAAAAAAAAAA0P+PYQAAAAAAAAD//////z//////////AwAAAAAAAAAAAAAAoP8HwAAAAAAAAMD/////83/+////////AQAAAAAAAAAAAAAAIP8DwAAAAAAAAOD/////5//I////////AAAAAAAAAAAAAAAAQP4DgAAAAAAAAPD/////z/+A////////AAAAAAAAAAAAAAAAAPwDAAIAAAAAAPD/////z/8ZwP////9/AQAAAAAAAAAAAAAAAPgDQAAAAAAAAPj/////j/9/gP////8fAQAAAAAAAAAAAAAAAPADEAMAAAAAAPz/////v///AP9//P8DAAAAAAAAAAAAAAAAAPADAwwAAAAAAPj/////P/9/APw//B8AAAAAAAAAAAAIAAAAAPCHA8AAAAAAAPj/////P/4/APwP+J8BAAAAAAAAAAAAAAAAAMD/A0YEAAAAAPj/////f/4fAPwH+B8AAwAAAAAAAAAAAAAAAAD/AQAAAAAAAPj/////f/wHAPgD8D8AAwAAAAAAAAAAAAAAAADgHwAAAAAAAPj///////wDAPgAwH8AAQAAAAAAAAAAAAAAAADAHwAAAAAAAPz//////30AAPAAwH8AAAAAAAAAAAAAAAAAAAAAHAAAAAAAAPj//////wsAAPAAgH4AAQAAAAAAAAAAAAAAAAAAGEAAAAAAAPj//////wMBAPAAgHwAAAAAAAAAAAAAAAAAAAAAGPAhAAAAAPD///////cBAOAAgDiABAAAAAAAAAAAAAAAAAAAIPl/AAAAAOD///////8AAGABABBAFAAAAAAAAAAAAAAAAAAAgP7/AQAAAMD///////8AAAABgAAAHAAAAAAAAAAAAAAAAAAAAPz/AQAAAID///////8AAAABAAEgCAAAAAAAAAAAAAAAAAAAAPz/HwAAAAD/8P///38AAAAAAANgAAAAAAAAAAAAAAAAAAAAAPz/fwAAAAAAoP///z8AAAAAYAd4AAAAAAAAAAAAAAAAAAAAAPz/fwAAAAAAAP///x8AAAAAwAY8AAAAAAAAAAAAAAAAAAAAAP7//wAAAAAAAP///w8AAAAAgAc+AAAAAAAAAAAAAAAAAAAAAP///wAAAAAAAP///wcAAAAAgIM/TwAAAAAAAAAAAAAAAAAAAP///wEAAAAAgP///wMAAAAAAIc/QAQAAAAAAAAAAAAAAAAAgP///w8AAAAAgP///wEAAAAAAA6fAUQAAAAAAAAAAAAAAAAAAP////8AAAAAAP///wAAAAAAAB6ewuwDAgAAAAAAAAAAAAAAgP////8DAAAAAP7//wAAAAAAABwAAvAPAgAAAAAAAAAAAAAAgP////8PAAAAAPz/fwAAAAAAABAAAMCfAQAAAAAAAAAAAAAAAP////8PAAAAAPz//wAAAAAAAOADAIA/MAAAAAAAAAAAAAAAAP7///8PAAAAAPz/fwAAAAAAAAAPAMBngAAAAAAAAAAAAAAAAP7///8PAAAAAPz//wAAAAAAAAAACABAAAAAAAAAAAAAAAAAAPz///8HAAAAAPj//wAAAAAAAAAAAAAAAAIAAAAAAAAAAAAAAPz///8DAAAAAPj//wAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAPj///8BAAAAAPz//4AAAAAAAAAAAB8GAAAAAAAAAAAAAAAAAPj///8BAAAAAPz//8EAAAAAAAAAIB8OAAAAAAAAAAAAAAAAAPD///8BAAAAAP7//+AAAAAAAAAA+B8OACAAAAAAAAAAAAAAAMD///8BAAAAAP7/f/gAAAAAAAAA/H8eAAAAAAAAAAAAAAAAAID///8AAAAAAP7/H/gAAAAAAAAA/P8fAABAAAAAAAAAAAAAAAD///8AAAAAAPz/D3AAAAAAAAAA/v8/AAAAAAAAAAAAAAAAAAD///8AAAAAAPj/D3gAAAAAAADA//9/AAgAAAAAAAAAAAAAAAD//38AAAAAAPj/DzgAAAAAAADw////AAAAAAAAAAAAAAAAAAD//x8AAAAAAPD/DzgAAAAAAAD4////AQAAAAAAAAAAAAAAAAD//wMAAAAAAPD/DzgAAAAAAAD4////AwAAAAAAAAAAAAAAAID//wEAAAAAAPD/AwAAAAAAAAD4////AwAAAAAAAAAAAAAAAID//wEAAAAAAPD/AwAAAAAAAAD4////BwAAAAAAAAAAAAAAAID//wEAAAAAAOD/AwAAAAAAAAD4////BwAAAAAAAAAAAAAAAID//wAAAAAAAOD/AQAAAAAAAADw////BwAAAAAAAAAAAAAAAID//wAAAAAAAMD/AAAAAAAAAADw////AwAAAAAAAAAAAAAAAID/fwAAAAAAAIB/AAAAAAAAAADgf/z/AwAAAAAAAAAAAAAAAID/PwAAAAAAAIA/AAAAAAAAAADgB/D/AQAAAAAAAAAAAAAAAMD/HQAAAAAAAIABAAAAAAAAAADwAND/AQAAAAAAAAAAAAAAAMD/AwAAAAAAAAAAAAAAAAAAAAAAAID/AAAIAAAAAAAAAAAAAMD/BwAAAAAAAAAAAAAAAAAAAAAAAAD/AAAQAAAAAAAAAAAAAOD/AwAAAAAAAAAAAAAAAAAAAAAAAAA+AABwAAAAAAAAAAAAAOA/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4AAAAAAAAAAAAAOA/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAOAPAAAAAAAAAAAAAAAAAAAAAAAAAABwAAAGAAAAAAAAAAAAAMAPAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAADAAAAAAAAAAAAAPAPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMABAAAAAAAAAAAAAPADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOABAAAAAAAAAAAAAPAHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPAHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPADAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAPABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPCBAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMAHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAcAAAAAAAAAAAAAAA+AABAAJ8//j8PAAAAAAAAAAAAAAAAAAAMAAAAAAAAAAAAAPD/fwD///////8/AAAAAAAAAAAAAAAAAIA+AAAAAAAAAAAAPP///8D/////////HwAAAAAAAAAAAAAAAIA9AAAAAAAA8Pz/////P/j//////////wMAAAAAAAAAAMAAAPB9AAAAAID/////////P/7///////////8BAAAAAAAAAOABAwB/AAAAAPD///////////////////////8AAAAAAFACPoD///9/AAAAAPD//////////////////////x8AAAAA+P////////8HAAAAAP///////////////////////wcAAAAA/v///////wMAAAAA/v///////////////////////wcAAAD8/////////w8AAA7w/////////////////////////w8AAMAB/////////wMAgB84/////////////////////////wEAAAAA/P///////3/w4AcA/////////////////////////wAAAADg//////////8/gM///////////////////////////wMAAADg/////////////f///////////////////////////z8A7wMA/v////////////////////////////////////////8/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

var globeNodes = [];
(function initGlobeNodes() {
  var MW = 288, MH = 144;
  var bin = atob(GLOBE_LAND_B64);
  var land = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) land[i] = bin.charCodeAt(i);

  function isLand(lon, lat) {
    var gx = Math.floor(((lon + 180) / 360) * MW);
    var gy = Math.floor(((90 - lat) / 180) * MH);
    if (gx < 0 || gx >= MW || gy < 0 || gy >= MH) return false;
    var b = gy * MW + gx;
    return (land[b >> 3] >> (b & 7)) & 1;
  }

  var PHRASE = "everypointonthisballisapathbacktoanotherone";
  var LAT_STEP = 3.05;
  var k = 0, run = 0, sea3 = 0;
  for (var lat = -86; lat <= 86; lat += LAT_STEP) {
    var rl = Math.cos((lat * Math.PI) / 180);
    var n = Math.max(1, Math.round(98 * rl));
    for (var i = 0; i < n; i++) {
      var lon = -180 + (360 * i) / n;
      var l = isLand(lon, lat);
      if (!l && sea3++ % 2) continue;
      var letter = 0;
      if (l && run++ % 2 === 0) letter = PHRASE.charAt(k++ % PHRASE.length);
      globeNodes.push({
        lat: (lat * Math.PI) / 180,
        lon: (lon * Math.PI) / 180,
        land: l,
        c: letter,
      });
    }
  }
})();

var globeSpin = 2.1;
var globeVel = 0.20;
var globeTilt = -0.26;
var globeLand8 = [];
var globeSea = [];
var globeSoil = [];
var globePrevTime = performance.now();

function resizeGlobeCanvas() {
  if (!globeCanvas) {
    globeCanvas = document.getElementById('tunnel-globe-canvas');
    if (globeCanvas) globeCtx = globeCanvas.getContext('2d');
  }
  if (!globeCanvas) return;
  var parent = globeCanvas.parentElement;
  var rect = parent ? parent.getBoundingClientRect() : globeCanvas.getBoundingClientRect();
  globeDpr = Math.min(2, window.devicePixelRatio || 1);
  var w = Math.round(rect.width || (parent ? parent.clientWidth : 0) || window.innerWidth || 800);
  var h = Math.round(rect.height || (parent ? parent.clientHeight : 0) || 500);
  if (w > 0 && h > 0) {
    globeWidth = w;
    globeHeight = h;
    if (globeCanvas.width !== Math.round(w * globeDpr) || globeCanvas.height !== Math.round(h * globeDpr)) {
      globeCanvas.width = Math.round(w * globeDpr);
      globeCanvas.height = Math.round(h * globeDpr);
    }
  }
}

function dots(ctx, list, base, gain, grow, dmin) {
  for (var lvl = 0; lvl < 6; lvl++) {
    var z = (lvl + 0.5) / 6, dsz = dmin * grow * (0.55 + 0.75 * z);
    ctx.fillStyle = getGlobeInk(base + gain * z);
    ctx.beginPath();
    for (var q = 0; q < list.length; q += 3) {
      var lv = list[q + 2] >= 1 ? 5 : (list[q + 2] * 6) | 0;
      if (lv !== lvl) continue;
      ctx.rect(list[q] - dsz / 2, list[q + 1] - dsz / 2, dsz, dsz);
    }
    ctx.fill();
  }
}

function drawGlobeFrame(now) {
  // Strict execution guard: only animate if actively running, tab is visible, and on tunnel tab
  if (!globeRunning || state.currentTab !== 'tunnel' || document.hidden) {
    stopGlobeAnimation();
    return;
  }

  if (!globeCanvas || !globeCtx) {
    globeCanvas = document.getElementById('tunnel-globe-canvas');
    if (globeCanvas) globeCtx = globeCanvas.getContext('2d');
  }

  if (!globeCtx) {
    stopGlobeAnimation();
    return;
  }

  if (globeWidth <= 0 || globeHeight <= 0) {
    resizeGlobeCanvas();
  }
  if (globeWidth <= 0 || globeHeight <= 0) return;

  var dt = Math.min(64, now - globePrevTime);
  globePrevTime = now;

  globeCtx.setTransform(globeDpr, 0, 0, globeDpr, 0, 0);
  globeCtx.clearRect(0, 0, globeWidth, globeHeight);

  globeSpin += (globeVel * dt) / 1000;

  var availableHalfHeight = Math.max(80, (globeHeight / 2) - 4);
  var availableHalfWidth = Math.max(80, (globeWidth / 2) - 4);
  var R = Math.min(availableHalfWidth, availableHalfHeight);
  var cx = globeWidth / 2;
  var cy = globeHeight / 2;
  var fs = R * 0.076;

  var cs = Math.cos(globeSpin), sn = Math.sin(globeSpin);
  var ct = Math.cos(globeTilt), st = Math.sin(globeTilt);

  globeCtx.textAlign = 'center';
  globeCtx.textBaseline = 'middle';

  globeSea.length = 0;
  globeSoil.length = 0;

  for (var i = 0; i < globeNodes.length; i++) {
    var nd = globeNodes[i];
    var cl = Math.cos(nd.lat);
    var x0 = cl * Math.cos(nd.lon), y0 = Math.sin(nd.lat), z0 = cl * Math.sin(nd.lon);
    var x1 = x0 * cs - z0 * sn, z1 = x0 * sn + z0 * cs;
    var y2 = y0 * ct - z1 * st, z2 = y0 * st + z1 * ct;
    if (z2 <= 0.02) continue;

    var px = cx + x1 * R, py = cy - y2 * R;
    if (!nd.land) {
      globeSea.push(px, py, Math.min(0.999, z2));
      continue;
    }
    if (!nd.c) {
      globeSoil.push(px, py, Math.min(0.999, z2));
      continue;
    }

    var tx0 = -Math.sin(nd.lon), tz0 = Math.cos(nd.lon);
    var tx1 = tx0 * cs - tz0 * sn, tz1 = tx0 * sn + tz0 * cs;
    var ang = globeQang(Math.atan2(tz1 * st, tx1));
    var b = Math.min(7, Math.max(0, ((Math.min(0.999, z2) * 7.99) | 0)));
    (globeLand8[b] || (globeLand8[b] = [])).push(px, py, ang, nd.c);
  }

  var dmin = Math.max(0.7, R * 0.0065);
  dots(globeCtx, globeSea, 0.10, 0.22, 1.0, dmin);
  dots(globeCtx, globeSoil, 0.34, 0.46, 1.7, dmin);

  var FACE = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  for (var bi = 0; bi < 8; bi++) {
    var arr = globeLand8[bi];
    if (!arr || !arr.length) continue;
    var zb = (bi + 0.5) / 8;
    globeCtx.font = 'bold ' + (fs * (0.42 + 0.58 * zb)).toFixed(2) + 'px ' + FACE;
    globeCtx.fillStyle = getGlobeInk(0.28 + 0.72 * Math.pow(zb, 0.6));
    for (var t = 0; t < arr.length; t += 4) {
      globeCtx.save();
      globeCtx.translate(arr[t], arr[t + 1]);
      globeCtx.rotate(arr[t + 2]);
      globeCtx.fillText(arr[t + 3], 0, 0);
      globeCtx.restore();
    }
    arr.length = 0;
  }

  if (globeRunning && state.currentTab === 'tunnel' && !document.hidden) {
    globeAnimationId = requestAnimationFrame(drawGlobeFrame);
  } else {
    globeAnimationId = null;
  }
}

function startGlobeAnimation() {
  if (state.currentTab !== 'tunnel' || document.hidden) return;
  globeRunning = true;
  globePrevTime = performance.now();
  resizeGlobeCanvas();
  if (globeAnimationId) {
    cancelAnimationFrame(globeAnimationId);
    globeAnimationId = null;
  }
  globeAnimationId = requestAnimationFrame(drawGlobeFrame);
}

function stopGlobeAnimation() {
  globeRunning = false;
  if (globeAnimationId) {
    cancelAnimationFrame(globeAnimationId);
    globeAnimationId = null;
  }
  if (globeCtx && globeCanvas) {
    try {
      globeCtx.clearRect(0, 0, globeCanvas.width, globeCanvas.height);
    } catch (_) {}
  }
  globeSea.length = 0;
  globeSoil.length = 0;
  for (var bi = 0; bi < 8; bi++) {
    if (globeLand8[bi]) globeLand8[bi].length = 0;
  }
}

function initTunnelGlobe() {
  if (state.currentTab !== 'tunnel') return;
  globeCanvas = document.getElementById('tunnel-globe-canvas');
  if (!globeCanvas) return;
  globeCtx = globeCanvas.getContext('2d');

  var isOnline = state.tunnel && state.tunnel.status === 'online';
  syncGlobeTheme(isOnline);

  resizeGlobeCanvas();
  setTimeout(resizeGlobeCanvas, 60);

  if (window.ResizeObserver && globeCanvas.parentElement && !globeCanvas._ro) {
    var ro = new ResizeObserver(function() {
      if (globeRunning && state.currentTab === 'tunnel') {
        resizeGlobeCanvas();
      }
    });
    ro.observe(globeCanvas.parentElement);
    globeCanvas._ro = ro;
  }

  startGlobeAnimation();
}

function syncGlobeTheme(isOnline) {
  var isDark = (document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme')) !== 'light';
  var ink;
  if (isOnline) {
    ink = '219,125,37'; // #db7d25 (replacing terracotta orange)
  } else {
    ink = isDark ? '226,228,233' : '45,45,45';
  }
  updateGlobeInk(ink);
}

window.addEventListener('resize', function() {
  if (globeRunning) {
    resizeGlobeCanvas();
  }
});

async function installNativeNgrok() {
  const btn = document.getElementById('btn-install-tunnel');
  const btnText = document.getElementById('btn-install-tunnel-text');
  const origText = btnText ? btnText.textContent : 'Install ngrok';
  if (btnText) btnText.textContent = 'Installing...';
  if (btn) btn.disabled = true;

  try {
    showToast('Downloading and installing native ngrok binary for this device...', 'info');
    const res = await fetch('/api/tunnel/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: false }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message || 'ngrok installed natively!', 'success');
    } else {
      showToast(data.message || 'Installation failed', 'error');
    }
    await fetchTunnelStatus();
  } catch (err) {
    showToast(`Install error: ${err.message}`, 'error');
    await fetchTunnelStatus();
  } finally {
    if (btnText) btnText.textContent = origText;
    if (btn) btn.disabled = false;
  }
}

async function toggleTunnel() {
  const isOnline = state.tunnel && state.tunnel.status === 'online';
  const isInstalled = state.tunnel && state.tunnel.installed !== false;
  const endpoint = isOnline ? '/api/tunnel/stop' : '/api/tunnel/start';
  const toggleBtnText = document.getElementById('btn-toggle-tunnel-text');

  if (toggleBtnText) {
    toggleBtnText.textContent = isOnline ? 'Stopping...' : (!isInstalled ? 'Installing & Starting...' : 'Starting...');
  }

  try {
    if (!isOnline && !isInstalled) {
      showToast('Installing native ngrok binary for this device and starting tunnel...', 'info');
    } else {
      showToast(isOnline ? 'Stopping ngrok tunnel...' : 'Starting ngrok tunnel on port 5000...', 'info');
    }
    const res = await fetch(endpoint, { method: 'POST' });
    const data = await res.json();

    if (data.status === 'error') {
      showToast(data.message || 'Tunnel operation failed', 'error');
    } else if (data.status === 'online') {
      showToast(`Tunnel active: ${data.public_url} (log in there with the key from ./singular key)`, 'success');
    } else if (data.status === 'offline') {
      showToast('ngrok tunnel stopped successfully', 'info');
    }
    await fetchTunnelStatus();
  } catch (err) {
    showToast(`Tunnel error: ${err.message}`, 'error');
    await fetchTunnelStatus();
  }
}

async function saveNgrokAuthtoken() {
  const input = document.getElementById('input-ngrok-authtoken');
  if (!input) return;
  const token = input.value.trim();
  if (!token) {
    showToast('Please paste an ngrok authtoken first.', 'error');
    return;
  }

  try {
    showToast('Saving ngrok authtoken...', 'info');
    const res = await fetch('/api/tunnel/authtoken', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ authtoken: token })
    });
    const data = await res.json();
    if (data.status === 'error') {
      showToast(data.message || 'Failed to save authtoken', 'error');
    } else {
      showToast('ngrok authtoken configured successfully!', 'success');
      input.value = '';
      await fetchTunnelStatus();
    }
  } catch (err) {
    showToast(`Failed to configure token: ${err.message}`, 'error');
  }
}

function initTunnelControls() {
  const btnToggle = document.getElementById('btn-toggle-tunnel');
  if (btnToggle) {
    btnToggle.addEventListener('click', toggleTunnel);
  }

  const btnRefresh = document.getElementById('btn-refresh-tunnel');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      showToast('Refreshing tunnel status...', 'info');
      fetchTunnelStatus();
    });
  }

  const btnInstall = document.getElementById('btn-install-tunnel');
  if (btnInstall) {
    btnInstall.addEventListener('click', installNativeNgrok);
  }

  const btnCopy = document.getElementById('btn-copy-tunnel-url');
  if (btnCopy) {
    btnCopy.addEventListener('click', async () => {
      const urlText = document.getElementById('tunnel-url-text');
      const text = urlText ? urlText.textContent : '';
      if (!text || text.startsWith('Offline')) {
        showToast('Start ngrok tunnel first to get an endpoint', 'info');
        return;
      }
      const ok = await copyTextToClipboard(text);
      if (ok) {
        showToast('Copied endpoint to clipboard: ' + text, 'success');
      } else {
        showToast('Failed to copy endpoint to clipboard', 'error');
      }
    });
  }

  const btnSaveToken = document.getElementById('btn-save-authtoken');
  if (btnSaveToken) {
    btnSaveToken.addEventListener('click', saveNgrokAuthtoken);
  }

}

// Skiper37-Inspired Live Server Uptime Tracker
var STORAGE_TUNNEL_START_KEY = 'eclipse_tunnel_started_at';
var uptimeInterval = null;
var tunnelUptimeStart = null;

// Read cached start time immediately so timer starts without resetting on page refresh
try {
  var cachedStart = localStorage.getItem(STORAGE_TUNNEL_START_KEY);
  if (cachedStart) {
    var parsedStart = parseInt(cachedStart, 10);
    if (!isNaN(parsedStart) && parsedStart > 0 && parsedStart <= Date.now()) {
      tunnelUptimeStart = parsedStart;
    }
  }
} catch (e) {}

function setSkiper37Digit(colName, nextDigit) {
  var col = document.querySelector('.skiper37-digit-col[data-col="' + colName + '"]');
  if (!col) return;
  var track = col.querySelector('.skiper37-digit-track');
  if (!track) return;

  var currentDigitStr = col.dataset.currentDigit;
  var targetDigit = parseInt(nextDigit, 10);
  if (isNaN(targetDigit)) targetDigit = 0;

  var itemHeight = 42;
  var firstSpan = track.querySelector('span');
  if (firstSpan && firstSpan.offsetHeight > 0) {
    itemHeight = firstSpan.offsetHeight;
  }

  // Initial load without transition
  if (currentDigitStr === undefined || currentDigitStr === null || currentDigitStr === '') {
    track.style.transition = 'none';
    track.style.transform = 'translateY(' + (-targetDigit * itemHeight) + 'px)';
    col.dataset.currentDigit = String(targetDigit);
    return;
  }

  var currentDigit = parseInt(currentDigitStr, 10);
  if (currentDigit === targetDigit) return;

  // Skiper37 / NumberFlow smooth forward roll:
  // Moving 9 -> 0 rolls forward to index 10 (the bottom 0 span),
  // then after the animation completes, snaps back to 0 without transition.
  if (currentDigit === 9 && targetDigit === 0) {
    track.style.transition = 'transform 0.45s cubic-bezier(0.16, 1, 0.3, 1)';
    track.style.transform = 'translateY(' + (-10 * itemHeight) + 'px)';
    col.dataset.currentDigit = '0';
    setTimeout(function() {
      if (col.dataset.currentDigit === '0') {
        track.style.transition = 'none';
        track.style.transform = 'translateY(0px)';
        void track.offsetHeight;
      }
    }, 480);
  } else {
    track.style.transition = 'transform 0.45s cubic-bezier(0.16, 1, 0.3, 1)';
    track.style.transform = 'translateY(' + (-targetDigit * itemHeight) + 'px)';
    col.dataset.currentDigit = String(targetDigit);
  }
}

function updateUptimeDisplay() {
  var t = state.tunnel;

  if (t && t.status === 'online') {
    var accurateStart = null;
    if (t.started_at) {
      accurateStart = Math.floor(t.started_at * 1000);
    } else if (t.uptime_seconds) {
      accurateStart = Date.now() - (t.uptime_seconds * 1000);
    }

    if (accurateStart && (!tunnelUptimeStart || Math.abs(tunnelUptimeStart - accurateStart) > 2000)) {
      tunnelUptimeStart = accurateStart;
      try {
        localStorage.setItem(STORAGE_TUNNEL_START_KEY, String(accurateStart));
      } catch (e) {}
    } else if (!tunnelUptimeStart) {
      tunnelUptimeStart = accurateStart || Date.now();
      try {
        localStorage.setItem(STORAGE_TUNNEL_START_KEY, String(tunnelUptimeStart));
      } catch (e) {}
    }
  } else if (t && t.status !== 'online') {
    tunnelUptimeStart = null;
    try {
      localStorage.removeItem(STORAGE_TUNNEL_START_KEY);
    } catch (e) {}
    setSkiper37Digit('h0', 0);
    setSkiper37Digit('h1', 0);
    setSkiper37Digit('m0', 0);
    setSkiper37Digit('m1', 0);
    setSkiper37Digit('s0', 0);
    setSkiper37Digit('s1', 0);
    return;
  }

  if (!tunnelUptimeStart) {
    setSkiper37Digit('h0', 0);
    setSkiper37Digit('h1', 0);
    setSkiper37Digit('m0', 0);
    setSkiper37Digit('m1', 0);
    setSkiper37Digit('s0', 0);
    setSkiper37Digit('s1', 0);
    return;
  }

  var elapsedMs = Math.max(0, Date.now() - tunnelUptimeStart);
  var totalSec = Math.floor(elapsedMs / 1000);
  var hrs = Math.floor(totalSec / 3600);
  var mins = Math.floor((totalSec % 3600) / 60);
  var secs = totalSec % 60;

  var h0 = Math.floor(hrs / 10) % 10;
  var h1 = hrs % 10;
  var m0 = Math.floor(mins / 10);
  var m1 = mins % 10;
  var s0 = Math.floor(secs / 10);
  var s1 = secs % 10;

  setSkiper37Digit('h0', h0);
  setSkiper37Digit('h1', h1);
  setSkiper37Digit('m0', m0);
  setSkiper37Digit('m1', m1);
  setSkiper37Digit('s0', s0);
  setSkiper37Digit('s1', s1);
}

function startUptimeTracker() {
  updateUptimeDisplay();
  if (!uptimeInterval) {
    uptimeInterval = setInterval(updateUptimeDisplay, 1000);
  }
}

function stopUptimeTracker() {
  if (uptimeInterval) {
    clearInterval(uptimeInterval);
    uptimeInterval = null;
  }
}

document.addEventListener('visibilitychange', function() {
  if (document.hidden) {
    stopGlobeAnimation();
    stopUptimeTracker();
  } else if (state.currentTab === 'tunnel') {
    startGlobeAnimation();
    startUptimeTracker();
  }
});

// ===================================================================
// VengeanceUI Testimonials Card Stack Controller (Ngrok Key Guide)
// ===================================================================
var GUIDE_STEPS = [
  {
    id: 1,
    title: "1. Create Free Account",
    description: "Sign up at <a href=\"https://dashboard.ngrok.com\" target=\"_blank\" rel=\"noopener noreferrer\">dashboard.ngrok.com</a> to access your private tunnel credentials.",
    url: "https://dashboard.ngrok.com",
    svg: `<svg viewBox="0 0 160 160" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="vg1" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#1f1a14"/>
          <stop offset="100%" stop-color="#0e0e11"/>
        </linearGradient>
        <linearGradient id="vog1" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#db7d25"/>
          <stop offset="100%" stop-color="#f59e0b"/>
        </linearGradient>
      </defs>
      <rect width="160" height="160" fill="url(#vg1)"/>
      <circle cx="80" cy="65" r="44" fill="#db7d25" opacity="0.08"/>
      <circle cx="80" cy="65" r="30" fill="none" stroke="#db7d25" stroke-width="1.5" stroke-dasharray="3 3"/>
      <path d="M80 46 A11 11 0 1 0 80 68 A11 11 0 1 0 80 46 Z M65 82 C65 72 72 68 80 68 C88 68 95 72 95 82 Z" fill="url(#vog1)"/>
      <rect x="18" y="116" width="124" height="24" rx="6" fill="#18181b" stroke="#27272a" stroke-width="1"/>
      <text x="80" y="132" fill="#db7d25" font-family="monospace" font-size="8.5" font-weight="700" text-anchor="middle" letter-spacing="0.8">DASHBOARD.NGROK.COM ↗</text>
    </svg>`,
    image: null
  },
  {
    id: 2,
    title: "2. Your Authtoken",
    description: "Navigate to 'Your Authtoken' under Getting Started in the left dashboard sidebar.",
    svg: `<svg viewBox="0 0 160 160" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="vg2" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#1a1c23"/>
          <stop offset="100%" stop-color="#0d0e12"/>
        </linearGradient>
      </defs>
      <rect width="160" height="160" fill="url(#vg2)"/>
      <rect x="18" y="24" width="46" height="112" rx="6" fill="#141417" stroke="#27272a" stroke-width="1"/>
      <line x1="24" y1="36" x2="52" y2="36" stroke="#52525b" stroke-width="2" stroke-linecap="round"/>
      <line x1="24" y1="46" x2="44" y2="46" stroke="#3f3f46" stroke-width="2" stroke-linecap="round"/>
      <rect x="22" y="56" width="38" height="16" rx="4" fill="rgba(219, 125, 37, 0.2)" stroke="#db7d25" stroke-width="1"/>
      <line x1="26" y1="64" x2="52" y2="64" stroke="#db7d25" stroke-width="2" stroke-linecap="round"/>
      <line x1="24" y1="82" x2="48" y2="82" stroke="#3f3f46" stroke-width="2" stroke-linecap="round"/>
      <circle cx="110" cy="74" r="28" fill="#db7d25" opacity="0.12"/>
      <path d="M104 62 A10 10 0 1 0 114 78 L122 86 L128 86 L128 80 L124 80 L124 76 L116 68 A10 10 0 0 0 104 62 Z M102 68 A3 3 0 1 1 108 68 A3 3 0 1 1 102 68 Z" fill="#db7d25"/>
    </svg>`,
    image: null
  },
  {
    id: 3,
    title: "3. Copy Secret Token",
    description: "Click the 'Copy' button beside your authtoken string to copy it to clipboard.",
    svg: `<svg viewBox="0 0 160 160" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="vg3" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#181a17"/>
          <stop offset="100%" stop-color="#0d0f0d"/>
        </linearGradient>
      </defs>
      <rect width="160" height="160" fill="url(#vg3)"/>
      <rect x="18" y="52" width="124" height="42" rx="8" fill="#131514" stroke="#27272a" stroke-width="1.2"/>
      <text x="26" y="76" fill="#a1a1aa" font-family="monospace" font-size="11" letter-spacing="2">2tX•••••••••</text>
      <rect x="108" y="58" width="28" height="30" rx="6" fill="rgba(219, 125, 37, 0.22)" stroke="#db7d25" stroke-width="1"/>
      <path d="M117 73 L121 77 L128 68" fill="none" stroke="#db7d25" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="80" cy="122" r="12" fill="#10b981" opacity="0.15"/>
      <text x="80" y="126" fill="#10b981" font-family="monospace" font-size="9" font-weight="700" text-anchor="middle">TOKEN READY</text>
    </svg>`,
    image: null
  },
  {
    id: 4,
    title: "4. Paste & Save",
    description: "Paste it into the Authtoken field above and click 'Save Token' to activate.",
    svg: `<svg viewBox="0 0 160 160" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="vg4" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#211710"/>
          <stop offset="100%" stop-color="#0f0c0a"/>
        </linearGradient>
      </defs>
      <rect width="160" height="160" fill="url(#vg4)"/>
      <circle cx="80" cy="62" r="32" fill="#db7d25" opacity="0.12"/>
      <path d="M60 62 L74 62 M86 62 L100 62" stroke="#db7d25" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="2 3"/>
      <circle cx="56" cy="62" r="5" fill="#db7d25"/>
      <circle cx="80" cy="62" r="7" fill="#10b981"/>
      <circle cx="104" cy="62" r="5" fill="#db7d25"/>
      <rect x="36" y="112" width="88" height="26" rx="6" fill="#db7d25"/>
      <text x="80" y="128" fill="#ffffff" font-family="sans-serif" font-size="10" font-weight="700" text-anchor="middle" letter-spacing="0.5">SAVE TOKEN</text>
    </svg>`,
    image: null
  }
];

var guideActiveIndex = 0;
var guideRotations = [4, -2, -9, 7];
var guideIsAnimating = false;

function buildGuideTransform(x, y, z, rotDeg, scaleVal) {
  return 'translate3d(' + x + 'px, ' + y + 'px, ' + z + 'px) rotateZ(' + rotDeg + 'deg) scale(' + scaleVal + ')';
}

function initGuideCardsDOM() {
  var stackEl = document.getElementById('guide-card-stack');
  if (!stackEl) return;

  if (stackEl.children.length !== GUIDE_STEPS.length) {
    stackEl.innerHTML = '';
    GUIDE_STEPS.forEach(function(step, index) {
      var card = document.createElement('div');
      card.className = 'guide-card-item';
      card.dataset.index = index;
      if (step.url) {
        card.dataset.hasUrl = 'true';
        card.setAttribute('title', 'Click to open ' + step.url.replace(/^https?:\/\//, ''));
      }

      var innerHtml = '';
      if (step.image) {
        innerHtml = '<img src="' + step.image + '" alt="' + step.title + '" draggable="false">';
      } else if (step.svg) {
        innerHtml = step.svg;
      }

      if (step.url) {
        card.innerHTML = '<a href="' + step.url + '" target="_blank" rel="noopener noreferrer" class="guide-card-link" aria-label="' + step.title + '">' + innerHtml + '</a>';
      } else {
        card.innerHTML = innerHtml;
      }

      card.addEventListener('click', function(e) {
        if (guideIsAnimating) {
          e.preventDefault();
          return;
        }
        if (index === guideActiveIndex) {
          if (step.url) {
            window.open(step.url, '_blank', 'noopener,noreferrer');
            e.preventDefault();
          }
        } else {
          e.preventDefault();
          animateGuideDeck(index, index > guideActiveIndex ? 1 : -1);
        }
      });
      stackEl.appendChild(card);
    });
  }
}

function setGuideCardsStatic() {
  var stackEl = document.getElementById('guide-card-stack');
  if (!stackEl) return;
  var cards = stackEl.querySelectorAll('.guide-card-item');

  cards.forEach(function(card, index) {
    var offset = index - guideActiveIndex;
    var rot = guideRotations[index % 4];

    if (offset === 0) {
      card.style.transform = buildGuideTransform(0, 0, 0, 0, 1);
      card.style.opacity = '1';
      card.style.zIndex = '100';
      card.style.pointerEvents = 'auto';
    } else if (offset > 0) {
      var x = offset * 15;
      var y = Math.abs(offset) * 6;
      var z = -150 * Math.abs(offset);
      var scale = Math.max(0.65, 0.85 - Math.abs(offset) * 0.04);
      var opacity = offset === 1 ? 0.55 : (offset === 2 ? 0.35 : 0);
      card.style.transform = buildGuideTransform(x, y, z, rot, scale);
      card.style.opacity = String(opacity);
      card.style.zIndex = String(10 - Math.abs(offset));
      card.style.pointerEvents = 'auto';
    } else {
      card.style.transform = buildGuideTransform(-250, 0, -260, -10, 0.75);
      card.style.opacity = '0';
      card.style.zIndex = '0';
      card.style.pointerEvents = 'none';
    }
  });

  var currentStep = GUIDE_STEPS[guideActiveIndex];
  var counterEl = document.getElementById('guide-deck-counter');
  var titleEl = document.getElementById('guide-deck-title');
  var descEl = document.getElementById('guide-deck-desc');
  var btnPrev = document.getElementById('btn-guide-prev');
  var btnNext = document.getElementById('btn-guide-next');

  if (counterEl) counterEl.textContent = (guideActiveIndex + 1) + ' / ' + GUIDE_STEPS.length;
  if (titleEl) titleEl.textContent = currentStep.title;
  if (descEl) descEl.innerHTML = currentStep.description;
  if (btnPrev) btnPrev.disabled = (guideActiveIndex === 0);
  if (btnNext) btnNext.disabled = (guideActiveIndex === GUIDE_STEPS.length - 1);
}

function animateGuideDeck(targetIndex, direction) {
  if (guideIsAnimating) return;
  if (targetIndex === guideActiveIndex) return;
  if (targetIndex < 0 || targetIndex >= GUIDE_STEPS.length) return;

  var prevIndex = guideActiveIndex;
  var dir = direction !== undefined ? direction : (targetIndex > prevIndex ? 1 : -1);
  guideActiveIndex = targetIndex;
  guideIsAnimating = true;

  var currentStep = GUIDE_STEPS[guideActiveIndex];
  var counterEl = document.getElementById('guide-deck-counter');
  var titleEl = document.getElementById('guide-deck-title');
  var descEl = document.getElementById('guide-deck-desc');
  var btnPrev = document.getElementById('btn-guide-prev');
  var btnNext = document.getElementById('btn-guide-next');

  if (counterEl) counterEl.textContent = (guideActiveIndex + 1) + ' / ' + GUIDE_STEPS.length;
  if (btnPrev) btnPrev.disabled = (guideActiveIndex === 0);
  if (btnNext) btnNext.disabled = (guideActiveIndex === GUIDE_STEPS.length - 1);

  // Animate Text Area (VengeanceUI AnimatePresence mode="wait")
  var textWrapper = document.querySelector('.guide-deck-text');
  if (textWrapper && titleEl && descEl) {
    textWrapper.animate([
      { opacity: 1, transform: 'translateY(0px)' },
      { opacity: 0, transform: 'translateY(' + (dir === 1 ? -25 : 25) + 'px)' }
    ], {
      duration: 200,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      fill: 'forwards'
    }).onfinish = function() {
      titleEl.textContent = currentStep.title;
      descEl.innerHTML = currentStep.description;
      textWrapper.animate([
        { opacity: 0, transform: 'translateY(' + (dir === 1 ? 25 : -25) + 'px)' },
        { opacity: 1, transform: 'translateY(0px)' }
      ], {
        duration: 350,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        fill: 'forwards'
      });
    };
  }

  // Exact VengeanceUI 3D Animation Physics (750ms, cubic-bezier(0.22, 1, 0.36, 1))
  var stackEl = document.getElementById('guide-card-stack');
  if (!stackEl) {
    guideIsAnimating = false;
    return;
  }
  var cards = stackEl.querySelectorAll('.guide-card-item');

  cards.forEach(function(card, index) {
    var prevOffset = index - prevIndex;
    var newOffset = index - guideActiveIndex;
    var rot = guideRotations[index % 4];

    // 1. Exiting card
    if (prevOffset === 0 && newOffset !== 0) {
      card.style.zIndex = '80';
      var exitX = dir === 1 ? -250 : 250;
      var exitZ = -260;
      var exitRot = dir === 1 ? -10 : 10;
      var exitScale = 0.75;

      var exitAnim = card.animate([
        {
          transform: buildGuideTransform(0, 0, 0, 0, 1),
          opacity: 1
        },
        {
          transform: buildGuideTransform(exitX, 0, exitZ, exitRot, exitScale),
          opacity: 0
        }
      ], {
        duration: 750,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        fill: 'forwards'
      });

      exitAnim.onfinish = function() {
        var finalX = newOffset * 15;
        var finalY = Math.abs(newOffset) * 6;
        var finalZ = -150 * Math.abs(newOffset);
        var finalScale = Math.max(0.65, 0.85 - Math.abs(newOffset) * 0.04);
        var finalOpacity = newOffset > 0 ? (newOffset === 1 ? 0.55 : 0.35) : 0;
        card.style.transform = buildGuideTransform(finalX, finalY, finalZ, rot, finalScale);
        card.style.opacity = String(finalOpacity);
        card.style.zIndex = String(Math.max(1, 10 - Math.abs(newOffset)));
        card.style.pointerEvents = newOffset > 0 ? 'auto' : 'none';
      };
      return;
    }

    // 2. Incoming card (the signature 3-keyframe 3D swoop)
    if (newOffset === 0) {
      card.style.zIndex = '100';
      card.style.pointerEvents = 'auto';

      var startX = prevOffset * 15;
      var startY = Math.abs(prevOffset) * 6;
      var startZ = -150 * Math.abs(prevOffset);
      var startScale = Math.max(0.65, 0.85 - Math.abs(prevOffset) * 0.04);

      var swoopX = dir === 1 ? -200 : 200;
      var swoopZ = 150;
      var swoopRot = dir === 1 ? -5 : 5;
      var swoopScale = 1.05;

      var enterAnim = card.animate([
        {
          transform: buildGuideTransform(startX, startY, startZ, rot, startScale),
          opacity: 0.55,
          offset: 0
        },
        {
          transform: buildGuideTransform(swoopX, 0, swoopZ, swoopRot, swoopScale),
          opacity: 1,
          offset: 0.48
        },
        {
          transform: buildGuideTransform(0, 0, 0, 0, 1),
          opacity: 1,
          offset: 1
        }
      ], {
        duration: 750,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        fill: 'forwards'
      });

      enterAnim.onfinish = function() {
        card.style.transform = buildGuideTransform(0, 0, 0, 0, 1);
        card.style.opacity = '1';
        card.style.zIndex = '100';
      };
      return;
    }

    // 3. Other cards in the background stack
    var fromX = prevOffset * 15;
    var fromY = Math.abs(prevOffset) * 6;
    var fromZ = -150 * Math.abs(prevOffset);
    var fromScale = Math.max(0.65, 0.85 - Math.abs(prevOffset) * 0.04);
    var fromOpacity = prevOffset > 0 ? (prevOffset === 1 ? 0.55 : (prevOffset === 2 ? 0.35 : 0)) : 0;

    var toX = newOffset * 15;
    var toY = Math.abs(newOffset) * 6;
    var toZ = -150 * Math.abs(newOffset);
    var toScale = Math.max(0.65, 0.85 - Math.abs(newOffset) * 0.04);
    var toOpacity = newOffset > 0 ? (newOffset === 1 ? 0.55 : (newOffset === 2 ? 0.35 : 0)) : 0;

    card.style.zIndex = String(Math.max(1, 10 - Math.abs(newOffset)));
    card.style.pointerEvents = newOffset > 0 ? 'auto' : 'none';

    var bgAnim = card.animate([
      {
        transform: buildGuideTransform(fromX, fromY, fromZ, rot, fromScale),
        opacity: fromOpacity
      },
      {
        transform: buildGuideTransform(toX, toY, toZ, rot, toScale),
        opacity: toOpacity
      }
    ], {
      duration: 750,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      fill: 'forwards'
    });

    bgAnim.onfinish = function() {
      card.style.transform = buildGuideTransform(toX, toY, toZ, rot, toScale);
      card.style.opacity = String(toOpacity);
    };
  });

  setTimeout(function() {
    guideIsAnimating = false;
  }, 760);
}

function initTestimonialsGuideDeck() {
  var btnPrev = document.getElementById('btn-guide-prev');
  var btnNext = document.getElementById('btn-guide-next');

  initGuideCardsDOM();
  setGuideCardsStatic();

  if (btnPrev && !btnPrev.dataset.bound) {
    btnPrev.dataset.bound = 'true';
    btnPrev.addEventListener('click', function(e) {
      e.stopPropagation();
      if (!guideIsAnimating && guideActiveIndex > 0) {
        animateGuideDeck(guideActiveIndex - 1, -1);
      }
    });
  }

  if (btnNext && !btnNext.dataset.bound) {
    btnNext.dataset.bound = 'true';
    btnNext.addEventListener('click', function(e) {
      e.stopPropagation();
      if (!guideIsAnimating && guideActiveIndex < GUIDE_STEPS.length - 1) {
        animateGuideDeck(guideActiveIndex + 1, 1);
      }
    });
  }
}

function loadTunnelTab() {
  fetchTunnelStatus();
  initTunnelGlobe();
  startUptimeTracker();
  initTestimonialsGuideDeck();
}

// ===================================================================
// Claude-Grade Global Floating Tooltip System
// ===================================================================
function initTooltips() {
  let tooltipEl = document.getElementById('eclipse-tooltip');
  if (!tooltipEl) {
    tooltipEl = document.createElement('div');
    tooltipEl.id = 'eclipse-tooltip';
    document.body.appendChild(tooltipEl);
  }

  let hoverTimer = null;
  let isWarm = false;
  let warmResetTimer = null;
  let currentTarget = null;

  function showTooltip(target) {
    const text = target.getAttribute('data-tooltip') || target.getAttribute('data-title');
    if (!text || !text.trim()) return;

    tooltipEl.textContent = text.trim();
    tooltipEl.style.display = 'block';

    const rect = target.getBoundingClientRect();
    const tipRect = tooltipEl.getBoundingClientRect();

    let top = rect.top - tipRect.height - 8;
    let left = rect.left + (rect.width / 2) - (tipRect.width / 2);

    if (top < 8) {
      top = rect.bottom + 8;
    }

    if (left < 10) left = 10;
    if (left + tipRect.width > window.innerWidth - 10) {
      left = window.innerWidth - tipRect.width - 10;
    }

    tooltipEl.style.top = `${Math.round(top)}px`;
    tooltipEl.style.left = `${Math.round(left)}px`;
    tooltipEl.classList.add('visible');

    isWarm = true;
    clearTimeout(warmResetTimer);
  }

  function hideTooltip() {
    clearTimeout(hoverTimer);
    if (tooltipEl.classList.contains('visible')) {
      tooltipEl.classList.remove('visible');
      warmResetTimer = setTimeout(() => {
        isWarm = false;
        tooltipEl.style.display = 'none';
      }, 250);
    }
    currentTarget = null;
  }

  // Intercept titles and upgrade them to buttery data-tooltips
  function convertTitles(root = document) {
    root.querySelectorAll('[title]').forEach(el => {
      if (el.id === 'sidebar-toggle-btn' || el.hasAttribute('data-no-tooltip') || el.closest('#sidebar-toggle-btn')) {
        return;
      }
      const title = el.getAttribute('title');
      if (title && !el.hasAttribute('data-tooltip')) {
        el.setAttribute('data-tooltip', title);
        el.removeAttribute('title');
      }
    });
  }

  convertTitles();

  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'childList') {
        m.addedNodes.forEach(node => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            convertTitles(node);
          }
        });
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  document.addEventListener('mouseover', (e) => {
    const target = e.target.closest('[data-tooltip]');
    if (!target || target === currentTarget || target.id === 'sidebar-toggle-btn' || target.hasAttribute('data-no-tooltip')) return;

    clearTimeout(hoverTimer);
    currentTarget = target;

    if (isWarm) {
      showTooltip(target);
    } else {
      hoverTimer = setTimeout(() => {
        if (currentTarget === target) {
          showTooltip(target);
        }
      }, 260);
    }
  }, true);

  document.addEventListener('mouseout', (e) => {
    const target = e.target.closest('[data-tooltip]');
    if (target && target === currentTarget) {
      const related = e.relatedTarget ? e.relatedTarget.closest('[data-tooltip]') : null;
      if (!related || related !== currentTarget) {
        hideTooltip();
      }
    }
  }, true);

  document.addEventListener('click', hideTooltip, true);
  window.addEventListener('scroll', hideTooltip, true);
}

// ===================================================================
// Claude-Style Resizable & Collapsible Sidebar
// ===================================================================
function initSidebar() {
  const sidebar = document.getElementById('sidebar') || document.querySelector('.sidebar');
  const resizer = document.getElementById('sidebar-resizer');
  const toggleBtn = document.getElementById('sidebar-toggle-btn');
  const collapseBtn = document.getElementById('sidebar-collapse-btn');
  const expandBtn = document.getElementById('sidebar-expand-btn');
  if (!sidebar) return;

  const STORAGE_WIDTH_KEY = 'eclipse_sidebar_width';
  const STORAGE_COLLAPSED_KEY = 'eclipse_sidebar_collapsed';
  const DEFAULT_WIDTH = 270;
  const MIN_WIDTH = 180;
  const MAX_WIDTH = 500;
  const COLLAPSE_THRESHOLD = 150;

  // Restore saved width
  let savedWidth = parseInt(localStorage.getItem(STORAGE_WIDTH_KEY), 10);
  if (isNaN(savedWidth) || savedWidth < MIN_WIDTH || savedWidth > MAX_WIDTH) {
    savedWidth = DEFAULT_WIDTH;
  }
  document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);

  let peekTimer = null;

  function showPeek() {
    clearTimeout(peekTimer);
    if (document.body.classList.contains('has-collapsed-sidebar') || sidebar.classList.contains('collapsed')) {
      document.body.classList.add('sidebar-peeking');
    }
  }

  function scheduleHidePeek() {
    clearTimeout(peekTimer);
    peekTimer = setTimeout(() => {
      document.body.classList.remove('sidebar-peeking');
    }, 180);
  }

  function updateButtonTooltip(collapsed) {
    const tip = collapsed ? 'Expand sidebar (Ctrl+[)' : 'Collapse sidebar (Ctrl+[';
    if (toggleBtn) {
      delete toggleBtn.dataset.tooltip;
      toggleBtn.removeAttribute('data-tooltip');
      toggleBtn.setAttribute('aria-label', tip);
    }
    if (collapseBtn) {
      delete collapseBtn.dataset.tooltip;
      collapseBtn.removeAttribute('data-tooltip');
      collapseBtn.setAttribute('aria-label', 'Collapse sidebar');
    }
    if (expandBtn) {
      delete expandBtn.dataset.tooltip;
      expandBtn.removeAttribute('data-tooltip');
      expandBtn.setAttribute('aria-label', 'Expand sidebar');
    }
  }

  function setSidebarCollapsed(collapsed) {
    clearTimeout(peekTimer);
    document.body.classList.remove('sidebar-peeking');
    if (collapsed) {
      sidebar.classList.add('collapsed');
      document.body.classList.add('has-collapsed-sidebar');
      localStorage.setItem(STORAGE_COLLAPSED_KEY, 'true');
    } else {
      sidebar.classList.remove('collapsed');
      document.body.classList.remove('has-collapsed-sidebar');
      localStorage.setItem(STORAGE_COLLAPSED_KEY, 'false');
      document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
    }
    updateButtonTooltip(collapsed);
  }

  // Restore collapsed state
  const isCollapsed = localStorage.getItem(STORAGE_COLLAPSED_KEY) === 'true';
  if (isCollapsed) {
    setSidebarCollapsed(true);
  } else {
    updateButtonTooltip(false);
  }

  // Claude Hover-Peek on Toggle Button
  if (toggleBtn) {
    toggleBtn.addEventListener('mouseenter', showPeek);
    toggleBtn.addEventListener('mouseleave', scheduleHidePeek);

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      clearTimeout(peekTimer);
      document.body.classList.remove('sidebar-peeking');
      const isCurrentlyCollapsed = sidebar.classList.contains('collapsed') || document.body.classList.contains('has-collapsed-sidebar');
      setSidebarCollapsed(!isCurrentlyCollapsed);
    });
  }

  // Claude Hover-Peek on Sidebar itself (keeps it open while cursor is inside)
  if (sidebar) {
    sidebar.addEventListener('mouseenter', showPeek);
    sidebar.addEventListener('mouseleave', scheduleHidePeek);

    // If user clicks a nav item while peeking, activate tab and close peek
    sidebar.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => {
        if (document.body.classList.contains('sidebar-peeking')) {
          scheduleHidePeek();
        }
      });
    });
  }

  if (collapseBtn) {
    collapseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      setSidebarCollapsed(true);
    });
  }

  if (expandBtn) {
    expandBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      setSidebarCollapsed(false);
    });
  }

  // Keyboard shortcut: Ctrl+[ or Cmd+[
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === '[') {
      e.preventDefault();
      const current = sidebar.classList.contains('collapsed') || document.body.classList.contains('has-collapsed-sidebar');
      setSidebarCollapsed(!current);
    }
  });

  // Drag to Resize Handling
  if (resizer) {
    let startX = 0;
    let startWidth = savedWidth;
    let isDragging = false;

    resizer.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      isDragging = true;
      startX = e.clientX;
      startWidth = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width'), 10) || DEFAULT_WIDTH;

      sidebar.classList.add('resizing');
      document.body.classList.add('sidebar-resizing');

      function onMouseMove(moveEvent) {
        if (!isDragging) return;
        const currentX = moveEvent.clientX;

        // If dragged too close to the left, visually hint collapse
        if (currentX < COLLAPSE_THRESHOLD) {
          sidebar.style.opacity = '0.35';
          return;
        }

        sidebar.style.opacity = '1';
        let newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, currentX));
        document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
        savedWidth = newWidth;
      }

      function onMouseUp(upEvent) {
        if (!isDragging) return;
        isDragging = false;
        sidebar.classList.remove('resizing');
        document.body.classList.remove('sidebar-resizing');
        sidebar.style.opacity = '';

        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);

        if (upEvent.clientX < COLLAPSE_THRESHOLD) {
          setSidebarCollapsed(true);
        } else {
          setSidebarCollapsed(false);
          localStorage.setItem(STORAGE_WIDTH_KEY, String(savedWidth));
        }
      }

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    });

    // Double-click to reset width
    resizer.addEventListener('dblclick', () => {
      savedWidth = DEFAULT_WIDTH;
      document.documentElement.style.setProperty('--sidebar-width', `${DEFAULT_WIDTH}px`);
      localStorage.setItem(STORAGE_WIDTH_KEY, String(DEFAULT_WIDTH));
      setSidebarCollapsed(false);
      showToast('Sidebar reset to default width (270px)', 'info');
    });
  }
}

// ===================================================================
// Universal App Router (Enables Browser Back/Forward & Direct URL Hashing)
// ===================================================================
function initAppRouter() {
  function handleRoute() {
    const rawHash = (window.location.hash || '').replace(/^#\/?/, '');
    if (!rawHash) {
      if (state.currentTab !== 'playground') {
        switchTab('playground', false);
      }
      return;
    }

    const parts = rawHash.split('/');
    const tab = parts[0];

    const validTabs = ['playground', 'control', 'providers', 'accounts', 'models', 'cookies', 'tunnel', 'updates'];
    if (validTabs.includes(tab)) {
      const canonicalTab = tab === 'providers' ? 'control' : (tab === 'accounts' ? 'cookies' : tab);
      if (state.currentTab !== canonicalTab) {
        switchTab(canonicalTab, false);
      }
    }
  }

  window.addEventListener('hashchange', handleRoute);
  window.addEventListener('popstate', handleRoute);

  // If a hash was present on initial boot, navigate to it cleanly
  if (window.location.hash) {
    setTimeout(handleRoute, 40);
  }
}

// ===================================================================
// PWA Service Worker Registration & Install Experience
// ===================================================================
let deferredPwaPrompt = null;

function initPwa() {
  const installBtn = document.getElementById('btn-pwa-install');

  // Capture install prompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPwaPrompt = e;
    window.deferredPwaPrompt = e;
    if (installBtn) {
      installBtn.style.display = 'inline-flex';
    }
  });

  window.addEventListener('appinstalled', () => {
    deferredPwaPrompt = null;
    window.deferredPwaPrompt = null;
    showToast('Eclipse installed successfully!', 'success');
  });

  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      triggerHaptic(8);
      if (deferredPwaPrompt) {
        deferredPwaPrompt.prompt();
        const { outcome } = await deferredPwaPrompt.userChoice;
        if (outcome === 'accepted') {
          showToast('Installing Eclipse...', 'info');
        }
        deferredPwaPrompt = null;
      } else {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS) {
          showToast('Tap Safari Share button (⎋), then select "Add to Home Screen".', 'info', 6000);
        } else if (!window.isSecureContext) {
          showToast('PWA requires HTTPS or localhost. If on phone via LAN IP, use ngrok tunnel (./singular tunnel start) or chrome://flags.', 'error', 6000);
        } else {
          const isAndroid = /Android/i.test(navigator.userAgent);
          const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
          if (isAndroid && isLocal) {
            showToast('Note: Chrome on Android requires a public HTTPS URL (./singular tunnel start) for WebAPK minting, or use menu (⋮) -> Add to Home screen.', 'info', 7000);
          } else {
            showToast('Tap browser menu (⋮) -> "Add to Home Screen" or "Install App".', 'info', 5000);
          }
        }
      }
    });
  }

  // Register Service Worker
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .catch(() => {
          return navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
        })
        .then((reg) => {
          if (reg) {
            // Check for worker updates when returning to the tab
            window.addEventListener('focus', () => {
              reg.update().catch(() => {});
            });
          }
        })
        .catch((err) => {
          // Expected on plain HTTP non-localhost IP
          console.debug('[PWA] Service Worker registration:', err.message || err);
        });
    });
  }
}

// ===================================================================
// Initialization
// ===================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initClaudeSettings();
  initSidebar();
  initTooltips();
  initNavigation();
  initAppRouter();
  initModelFilters();
  initCookieTabs();
  initCustomSelect();
  initParamModelSelect();
  initPlayground();
  initVoiceModeControls();
  initVoiceStudio();
  initCopyAction();
  initTunnelControls();
  initSmoothInputs();
  initPwa();

  // Mobile sidebar drawer trigger for Control Center
  const btnControlSidebar = document.getElementById('btn-control-mobile-sidebar');
  if (btnControlSidebar) {
    btnControlSidebar.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.triggerHaptic?.(8);
      const dockToggle = document.getElementById('eclipse-sidebar-toggle');
      if (dockToggle) {
        dockToggle.click();
      } else {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar) sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
      }
    });
  }

  // Fleet controls (Desktop & Mobile)
  const handleRefresh = () => {
    showToast('Refreshing telemetry...', 'info');
    fetchServices();
  };

  const btnRefresh = document.getElementById('btn-refresh-telemetry');
  if (btnRefresh) btnRefresh.addEventListener('click', handleRefresh);

  const btnRefreshMobile = document.getElementById('btn-refresh-telemetry-mobile');
  if (btnRefreshMobile) btnRefreshMobile.addEventListener('click', handleRefresh);

  const btnStartAll = document.getElementById('btn-start-all');
  if (btnStartAll) btnStartAll.addEventListener('click', startAllServices);

  const btnStartAllMobile = document.getElementById('btn-start-all-mobile');
  if (btnStartAllMobile) btnStartAllMobile.addEventListener('click', startAllServices);

  const btnStopAll = document.getElementById('btn-stop-all');
  if (btnStopAll) btnStopAll.addEventListener('click', stopAllServices);

  const btnStopAllMobile = document.getElementById('btn-stop-all-mobile');
  if (btnStopAllMobile) btnStopAllMobile.addEventListener('click', stopAllServices);

  // Initial Data Fetches
  fetchServices();
  fetchModels();
  fetchTunnelStatus();

  // Background Telemetry Polling (every 5s, paused when tab is hidden)
  setInterval(() => {
    if (document.hidden) return;
    fetchServices();
    if (state.currentTab === 'tunnel') {
      fetchTunnelStatus();
    }
  }, 5000);

  // Periodic status refresh (every 12s, paused when tab is hidden)
  setInterval(() => {
    if (document.hidden) return;
    if (state.currentTab !== 'tunnel') {
      fetchTunnelStatus();
    }
  }, 12000);
});

// Global exports for modular UI integrations (e.g. Glass Dock, Artifacts)
window.switchTab = switchTab;
window.showToast = showToast;
window.openArtifact = openArtifact;
window.closeArtifactWorkbench = closeArtifactWorkbench;
window.switchArtifactView = switchArtifactView;
window.switchArtifactVersion = switchArtifactVersion;
window.copyActiveArtifactCode = copyActiveArtifactCode;
window.downloadActiveArtifact = downloadActiveArtifact;
window.toggleArtifactFullscreen = toggleArtifactFullscreen;
window.initTunnelGlobe = initTunnelGlobe;
window.startGlobeAnimation = startGlobeAnimation;
window.stopGlobeAnimation = stopGlobeAnimation;

// ===================================================================
// Skiper106 Smooth Caret Input Component (@skiper-ui/skiper106)
// Spring-interpolated smooth caret with Canvas & DOM mirror tracking
// ===================================================================

class SkiperSmoothCaret {
  constructor(inputEl) {
    if (!inputEl || inputEl._skiperSmoothCaret) return;
    this.el = inputEl;
    this.el._skiperSmoothCaret = this;

    this.isTextarea = this.el.tagName.toLowerCase() === 'textarea';
    this.canvas = document.createElement('canvas');
    this.ctx = this.canvas.getContext('2d');
    
    this.idleTimer = null;
    this.mirrorEl = null;

    this.setupDOM();
    this.bindEvents();
  }

  setupDOM() {
    let wrapper = this.el.parentElement;
    if (!wrapper || !wrapper.classList.contains('skiper-smooth-wrapper')) {
      wrapper = document.createElement('div');
      wrapper.className = 'skiper-smooth-wrapper';
      if (this.isTextarea) {
        wrapper.classList.add('block-wrapper');
      }
      this.el.parentNode.insertBefore(wrapper, this.el);
      wrapper.appendChild(this.el);
    }
    this.wrapper = wrapper;

    this.caret = document.createElement('div');
    this.caret.className = 'skiper-smooth-caret';
    this.wrapper.appendChild(this.caret);

    this.el.classList.add('skiper-smooth-input');

    if (this.isTextarea) {
      this.mirrorEl = document.createElement('div');
      this.mirrorEl.setAttribute('aria-hidden', 'true');
      this.mirrorEl.style.cssText = `
        position: absolute;
        top: -9999px;
        left: -9999px;
        visibility: hidden;
        pointer-events: none;
        white-space: pre-wrap;
        word-wrap: break-word;
        overflow-wrap: break-word;
      `;
      document.body.appendChild(this.mirrorEl);
    }
  }

  bindEvents() {
    const update = () => this.updateCaretPosition();
    const onActivity = () => {
      this.caret.classList.add('active-typing', 'visible');
      this.caret.classList.remove('idle-blinking');
      update();
      clearTimeout(this.idleTimer);
      this.idleTimer = setTimeout(() => {
        this.caret.classList.remove('active-typing');
        if (document.activeElement === this.el) {
          this.caret.classList.add('idle-blinking');
        }
      }, 380);
    };

    this.el.addEventListener('focus', () => {
      this.caret.classList.add('visible', 'idle-blinking');
      update();
    });

    this.el.addEventListener('blur', () => {
      this.caret.classList.remove('visible', 'active-typing', 'idle-blinking');
    });

    this.el.addEventListener('input', onActivity);
    this.el.addEventListener('keydown', onActivity);
    this.el.addEventListener('keyup', update);
    this.el.addEventListener('click', update);
    this.el.addEventListener('select', update);
    this.el.addEventListener('mouseup', update);
    this.el.addEventListener('scroll', update);

    window.addEventListener('resize', update);
  }

  updateCaretPosition() {
    if (document.activeElement !== this.el) return;

    const start = this.el.selectionStart;
    const end = this.el.selectionEnd;

    // Hide caret if there's an active text selection range
    if (start === null || start === undefined || start !== end) {
      this.caret.style.opacity = '0';
      return;
    } else {
      this.caret.style.opacity = '';
    }

    const style = window.getComputedStyle(this.el);
    const fontSize = parseFloat(style.fontSize) || 14;
    const paddingLeft = parseFloat(style.paddingLeft) || 0;
    const paddingTop = parseFloat(style.paddingTop) || 0;
    const borderLeft = parseFloat(style.borderLeftWidth) || 0;
    const borderTop = parseFloat(style.borderTopWidth) || 0;

    const val = this.el.value || '';
    const textBefore = val.substring(0, start);

    let caretX = 0;
    let caretY = 0;
    let caretHeight = fontSize * 1.18;

    if (!this.isTextarea) {
      // Single-line text/password/search input
      let measuredText = textBefore;
      if (this.el.type === 'password') {
        measuredText = '•'.repeat(textBefore.length);
      }
      this.ctx.font = `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      const textWidth = this.ctx.measureText(measuredText).width;
      
      const inputHeight = this.el.offsetHeight || parseFloat(style.height) || (fontSize + paddingTop * 2);
      caretX = paddingLeft + borderLeft + textWidth - this.el.scrollLeft;
      caretY = Math.max(0, (inputHeight - caretHeight) / 2);
    } else {
      // Multi-line textarea with pixel-perfect DOM mirror probe
      if (this.mirrorEl) {
        const mirrorStyles = [
          'boxSizing', 'width', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
          'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
          'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'lineHeight',
          'textTransform', 'wordSpacing', 'textIndent', 'whiteSpace', 'wordBreak', 'overflowWrap'
        ];
        mirrorStyles.forEach(prop => {
          this.mirrorEl.style[prop] = style[prop];
        });
        this.mirrorEl.style.width = `${this.el.clientWidth}px`;

        // Escape HTML
        const safeText = textBefore
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#039;');

        this.mirrorEl.innerHTML = `${safeText}<span id="skiper-probe" style="display:inline-block;width:0;height:${caretHeight}px;vertical-align:baseline;">&#8203;</span>`;
        const probe = this.mirrorEl.querySelector('#skiper-probe');

        if (probe) {
          caretX = paddingLeft + borderLeft + probe.offsetLeft - this.el.scrollLeft;
          caretY = paddingTop + borderTop + probe.offsetTop - this.el.scrollTop;
        } else {
          caretX = paddingLeft;
          caretY = paddingTop;
        }
      }
    }

    this.caret.style.height = `${Math.round(caretHeight)}px`;
    this.caret.style.transform = `translate3d(${Math.round(caretX)}px, ${Math.round(caretY)}px, 0)`;
  }
}

function initSmoothInputs() {
  const selectors = [
    '#chat-input',
    '#model-search',
    '#model-filter-input',
    '#claude-settings-search',
    '#input-ngrok-authtoken',
    '#user-profile-name-input',
    '#system-prompt-input',
    '.smooth-input',
    '[data-smooth-input]'
  ];
  document.querySelectorAll(selectors.join(', ')).forEach(el => {
    if (!el._skiperSmoothCaret) {
      new SkiperSmoothCaret(el);
    }
  });
}

window.initSmoothInputs = initSmoothInputs;
window.SkiperSmoothCaret = SkiperSmoothCaret;



