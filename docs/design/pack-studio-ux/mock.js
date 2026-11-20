// Панель макета: тема, ширина, состояние. К дизайну приложения не относится.
(function () {
  var q = new URLSearchParams(location.search);
  var root = document.documentElement;
  var body = document.body;

  function setTheme(v) {
    if (v === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", v);
    try { localStorage.setItem("mock-theme", v); } catch (e) { /* без хранилища тоже работает */ }
    mark("[data-theme-set]", "themeSet", v);
  }
  function setWidth(v) {
    body.setAttribute("data-w", v);
    mark("[data-width-set]", "widthSet", v);
  }
  function setState(v) {
    body.setAttribute("data-state", v);
    mark("[data-state-set]", "stateSet", v);
    document.querySelectorAll("[data-show]").forEach(function (el) {
      var list = el.getAttribute("data-show").split(" ");
      el.hidden = list.indexOf(v) === -1;
    });
  }
  function mark(sel, key, value) {
    document.querySelectorAll(sel).forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset[key] === value ? "true" : "false");
    });
  }

  var saved = null;
  try { saved = localStorage.getItem("mock-theme"); } catch (e) { saved = null; }
  setTheme(q.get("theme") || saved || "auto");
  setWidth(q.get("w") || "desktop");
  var first = document.querySelector("[data-state-set]");
  if (first) setState(q.get("state") || first.dataset.stateSet);

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-theme-set],[data-width-set],[data-state-set]");
    if (!t) return;
    if (t.dataset.themeSet) setTheme(t.dataset.themeSet);
    if (t.dataset.widthSet) setWidth(t.dataset.widthSet);
    if (t.dataset.stateSet) setState(t.dataset.stateSet);
  });
})();
