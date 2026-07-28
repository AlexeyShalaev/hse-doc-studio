/* HSE Doc Studio · поведение фирменных компонентов.
   Вход обязательно через document$: включены navigation.instant +
   prefetch, обычный DOMContentLoaded сработал бы только один раз. */

(function () {
  "use strict";

  /* Копирование команды установки (.hds-cmd) */
  function initCopy(root) {
    root.querySelectorAll("[data-hds-copy]").forEach(function (btn) {
      if (btn.dataset.hdsBound) return;
      btn.dataset.hdsBound = "1";
      btn.addEventListener("click", function () {
        var code = btn.closest(".hds-cmd").querySelector("code");
        if (!code || !navigator.clipboard) return;
        var original = btn.textContent;
        navigator.clipboard.writeText(code.textContent.trim()).then(function () {
          btn.textContent = document.documentElement.lang === "ru" ? "Скопировано ✓" : "Copied ✓";
          btn.classList.add("hds-done");
          setTimeout(function () {
            btn.textContent = original;
            btn.classList.remove("hds-done");
          }, 1200);
        });
      });
    });
  }

  /* Переключатель треков над рельсом маршрута (.hds-tracks + [data-hds-rail]) */
  function initTracks(root) {
    root.querySelectorAll(".hds-tracks").forEach(function (group) {
      if (group.dataset.hdsBound) return;
      group.dataset.hdsBound = "1";
      var buttons = group.querySelectorAll("button[data-track]");
      var scope = group.parentElement;

      function select(track, push) {
        buttons.forEach(function (b) {
          b.setAttribute("aria-pressed", String(b.dataset.track === track));
        });
        scope.querySelectorAll("[data-hds-rail]").forEach(function (rail) {
          rail.hidden = rail.dataset.hdsRail !== track;
        });
        if (push && window.history.replaceState) {
          var url = new URL(window.location.href);
          url.searchParams.set("track", track);
          window.history.replaceState(null, "", url);
        }
      }

      buttons.forEach(function (btn) {
        btn.addEventListener("click", function () {
          select(btn.dataset.track, true);
        });
      });

      /* состояние переживает перезагрузку и «назад» */
      var initial = new URL(window.location.href).searchParams.get("track");
      if (initial && group.querySelector('button[data-track="' + initial + '"]')) {
        select(initial, false);
      }
    });
  }

  /* Подсветка пары «выноска ↔ пункт легенды» по hover и focus */
  function initPins(root) {
    function mark(scope, n, on) {
      scope.querySelectorAll('[data-n="' + n + '"]').forEach(function (el) {
        el.classList.toggle("hds-hot", on);
      });
    }
    root.querySelectorAll(".hds-shot__pin, .hds-legend li").forEach(function (el) {
      if (el.dataset.hdsBound || !el.dataset.n) return;
      el.dataset.hdsBound = "1";
      var scope = el.closest(".hds-fig") || root;
      ["mouseenter", "focus"].forEach(function (ev) {
        el.addEventListener(ev, function () {
          mark(scope, el.dataset.n, true);
        });
      });
      ["mouseleave", "blur"].forEach(function (ev) {
        el.addEventListener(ev, function () {
          mark(scope, el.dataset.n, false);
        });
      });
    });
  }

  /* Вкладки установки: сразу открыть вариант под ОС посетителя.
     Действует только на группы, где метка упоминает ОС, и не спорит
     с явным выбором пользователя — content.tabs.link хранит его
     в localStorage-ключе `…__tabs`. Ставим input.checked напрямую,
     не click(): авто-выбор не должен записываться как предпочтение. */
  function initOsTabs(root) {
    try {
      for (var i = 0; i < localStorage.length; i++) {
        if (/__tabs$/.test(localStorage.key(i))) return;
      }
    } catch (e) {
      /* приватный режим — просто не проверяем сохранённый выбор */
    }
    var ua = navigator.userAgent || "";
    var os = /Windows/i.test(ua)
      ? "windows"
      : /Mac|iPhone|iPad/i.test(ua)
        ? "mac"
        : /Linux|X11|CrOS/i.test(ua)
          ? "linux"
          : "";
    if (!os) return;
    var needles = {
      windows: ["windows", "powershell"],
      mac: ["macos", "mac os"],
      linux: ["linux"],
    }[os];
    root.querySelectorAll(".tabbed-set").forEach(function (set) {
      if (set.dataset.hdsOsBound) return;
      set.dataset.hdsOsBound = "1";
      var labels = set.querySelectorAll(":scope > .tabbed-labels > label");
      for (var j = 0; j < labels.length; j++) {
        var text = labels[j].textContent.toLowerCase();
        var hit = needles.some(function (n) {
          return text.indexOf(n) !== -1;
        });
        if (hit) {
          var input = document.getElementById(labels[j].htmlFor);
          if (input) input.checked = true;
          break;
        }
      }
    });
  }

  /* Mod → ⌘ на Apple, Ctrl на остальных, в [data-hds-key] */
  function initKbd(root) {
    var isApple = /Mac|iPhone|iPad/.test(navigator.platform || "");
    root.querySelectorAll("[data-hds-key]").forEach(function (el) {
      if (el.dataset.hdsBound) return;
      el.dataset.hdsBound = "1";
      el.textContent = el.textContent.replace(/\bMod\b/g, isApple ? "⌘" : "Ctrl");
    });
  }

  function boot() {
    initCopy(document);
    initTracks(document);
    initPins(document);
    initOsTabs(document);
    initKbd(document);
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(boot);
  } else {
    document.addEventListener("DOMContentLoaded", boot);
  }
})();
