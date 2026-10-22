/**
 * Eclipse Janitor Bio Canvas Shim
 * The Bio Canvas engine is self-contained in /static/bio-studio/
 */
(function() {
  if (typeof window.JanitorBioCanvas === 'undefined') {
    const s = document.createElement('script');
    s.src = '/static/bio-studio/janitor-canvas.js';
    document.head.appendChild(s);
  }
})();
