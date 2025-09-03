// static/app.js
document.addEventListener('DOMContentLoaded', () => {
  // Theme toggle (optional; it just toggles a class you can style)
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', (e) => {
      e.preventDefault();
      document.body.classList.toggle('theme-dark');
    });
  }

  // Keep Kanban scroll position across navigations
  (function setupKanbanScroll() {
    const viewport = document.getElementById('kanbanViewport');
    if (!viewport) return; // only on Kanban page

    const KEY = `kanban-scroll:${location.pathname}`;
    const cols = Array.from(document.querySelectorAll('.kanban-col-body[data-col]'));

    function restore() {
      try {
        const state = JSON.parse(sessionStorage.getItem(KEY) || '{}');
        if (typeof state.vp === 'number') viewport.scrollTop = state.vp;
        if (state.cols) {
          cols.forEach(c => {
            const k = c.dataset.col;
            const val = state.cols[k];
            if (typeof val === 'number') c.scrollTop = val;
          });
        }
      } catch (_) {}
    }

    function save() {
      const out = { vp: viewport.scrollTop, cols: {} };
      cols.forEach(c => { out.cols[c.dataset.col] = c.scrollTop; });
      sessionStorage.setItem(KEY, JSON.stringify(out));
    }

    restore();

    window.addEventListener('beforeunload', save);
    document.addEventListener('submit', save, true);
    document.addEventListener('click', (e) => {
      const el = e.target.closest('a, button');
      if (!el) return;
      if (el.matches('a[href], button[type="submit"], .btn')) save();
    });
  })();

  // Show “Other Rep” field when selecting Other…
  (function setupRepOther() {
    const sel = document.getElementById('rep_select');
    const wrap = document.getElementById('rep_other_wrap');
    if (!sel || !wrap) return;
    const toggle = () => { wrap.style.display = sel.value === '__other__' ? '' : 'none'; };
    sel.addEventListener('change', toggle);
    toggle();
  })();
});
