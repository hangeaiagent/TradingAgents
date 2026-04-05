(function() {
  var KEY = 'ta_theme';
  var saved = localStorage.getItem(KEY) || 'dark';
  document.documentElement.setAttribute('data-theme', saved);

  function update(t) {
    var btnDark = document.getElementById('btn-theme-dark');
    var btnLight = document.getElementById('btn-theme-light');
    if (btnDark) btnDark.className = t === 'dark' ? 'active' : '';
    if (btnLight) btnLight.className = t === 'light' ? 'active' : '';
  }

  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem(KEY, t);
    update(t);
  }

  // Attach after DOM is ready
  function init() {
    update(saved);
    var btnDark = document.getElementById('btn-theme-dark');
    var btnLight = document.getElementById('btn-theme-light');
    if (btnDark) btnDark.onclick = function() { setTheme('dark'); };
    if (btnLight) btnLight.onclick = function() { setTheme('light'); };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
