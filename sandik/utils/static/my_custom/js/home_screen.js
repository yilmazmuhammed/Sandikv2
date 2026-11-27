/*
 * Ana ekrana eklenmiş uygulama (standalone) için: sayfa değişirken üstte ilerleme çubuğu ve aşağı çekince yenileme.
 *
 * Tarayıcıda (Safari, Chrome) bunların ikisi de tarayıcının kendisindedir; ana ekrandan açılan uygulamada ikisi de
 * yoktur. Bu yüzden betik yalnızca ana ekran kipinde çalışır, tarayıcıda hiçbir şey yapmaz.
 *
 * Bu dosya bütün uygulamalarda BİREBİR AYNIDIR (myilmaz_tr, Sandikv2, family_tree, davetiye, apartman, anahtarlik,
 * cuzdan, kuran_takip). Uygulamalar birbirinden import etmediği için kopyalanır; birinde yapılan değişiklik
 * diğerlerine de taşınmalıdır. Çubuk Safari'deki gibi mavidir (uygulamaların üst çubukları kendi renklerinde olduğu
 * için o renkte görünmüyordu); aşağı çekme göstergesinin rengi <script data-color="#..."> ile verilir.
 *
 * Kullanım: <head> içinde, defer olmadan: <script src=".../home_screen.js" data-color="#0f766e"></script>
 * Tek sayfalık uygulamalar ekran değişimini kendileri bildirir: window.PageProgress.start() / .done().
 * Bir bağlantıda ya da alanda kapatmak için: data-no-progress (çubuk), data-no-pull-refresh (aşağı çekme).
 */
(function () {
  "use strict";
  var standalone = window.navigator.standalone === true ||
    (window.matchMedia && (matchMedia("(display-mode: standalone)").matches ||
      matchMedia("(display-mode: fullscreen)").matches));
  var noop = function () {};
  if (!standalone) {
    window.PageProgress = { start: noop, done: noop, enabled: false };
    return;
  }

  var script = document.currentScript;
  var color = (script && script.getAttribute("data-color")) || "#007aff";
  var BAR_COLOR = "#0a84ff";
  var NAV_KEY = "home-screen-nav";      // sayfa değişimi başladı (sessionStorage, yeni sayfada çubuk sürer)
  var NAV_MAX_AGE = 15000;
  var NAV_TIMEOUT = 12000;              // sayfa bu sürede değişmediyse (dosya indirme, iptal) çubuk biter

  // Stiller öğelerin kendisine yazılır, <style> eklenmez: Anahtarlık'ın güvenlik politikası (CSP: style-src 'self')
  // betikle eklenen <style>'ı engeller, öğenin style özelliğine yazmayı engellemez.
  var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  function css(el, props) {
    for (var k in props) el.style.setProperty(k, props[k]);
    return el;
  }
  var BAR_SHOW = "width .25s ease-out", BAR_HIDE = "width .25s ease-out, opacity .3s ease .15s";

  function whenBody(fn) {
    if (document.body) fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // ------------------------------------------------------------------ ilerleme çubuğu
  var bar = null, width = 0, timer = null, finishTimer = null, navTimer = null, running = false;

  function setWidth(w) {
    width = w;
    if (bar) bar.style.width = w + "%";
  }

  function trickle() {
    // Safari gibi: hızlı başlar, %90'a yaklaştıkça yavaşlar, sayfa gelmeden bitmez.
    var step = width < 30 ? 6 : width < 60 ? 3 : width < 80 ? 1.2 : 0.4;
    setWidth(Math.min(width + step, 92));
  }

  function start(from) {
    clearTimeout(finishTimer);
    if (running) return;
    running = true;
    whenBody(function () {
      if (!running) return;
      if (!bar) {
        bar = css(document.createElement("div"), {
          position: "fixed", top: "0", left: "0", height: "3px", width: "0", "z-index": "2147483647",
          "pointer-events": "none", background: BAR_COLOR, "box-shadow": "0 0 6px rgba(10,132,255,.6)", opacity: "0"
        });
        bar.id = "hs-progress";
        bar.setAttribute("aria-hidden", "true");
        document.body.appendChild(bar);
      }
      bar.style.transition = "none";
      setWidth(0);
      void bar.offsetWidth;
      css(bar, { transition: BAR_SHOW, opacity: "1" });
      setWidth(from || 15);
      clearInterval(timer);
      timer = setInterval(trickle, 200);
    });
  }

  function done() {
    clearTimeout(navTimer);
    if (!running) return;
    running = false;
    clearInterval(timer);
    if (!bar) return;
    setWidth(100);
    css(bar, { transition: BAR_HIDE, opacity: "0" });
    finishTimer = setTimeout(function () { if (!running) setWidth(0); }, 500);
  }

  function reset() {
    running = false;
    clearInterval(timer);
    clearTimeout(navTimer);
    if (bar) { css(bar, { transition: "none", opacity: "0" }); setWidth(0); }
  }

  var skipUnloadUntil = 0;

  function navigationStarted() {
    if (Date.now() < skipUnloadUntil) return;
    try { sessionStorage.setItem(NAV_KEY, String(Date.now())); } catch (e) { /* özel kip */ }
    start();
    clearTimeout(navTimer);
    navTimer = setTimeout(function () {
      try { sessionStorage.removeItem(NAV_KEY); } catch (e) { /* yok */ }
      done();
    }, NAV_TIMEOUT);
  }

  function isPlainNavigation(a, e) {
    if (e.defaultPrevented || e.button > 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
    if (a.hasAttribute("download") || a.hasAttribute("data-no-progress")) return false;
    var target = (a.getAttribute("target") || "").toLowerCase();
    if (target && target !== "_self" && target !== "_top" && target !== "_parent") return false;
    var href = a.getAttribute("href");
    if (!href || href.charAt(0) === "#") return false;
    if (a.protocol !== "http:" && a.protocol !== "https:") return false;     // tel:, mailto:, javascript:
    if (a.origin !== location.origin) return false;                           // dışarıyı iPhone ayrı açar
    // Yalnızca #... değişiyorsa sayfa değişmez.
    if (a.pathname === location.pathname && a.search === location.search && a.hash) return false;
    return true;
  }

  // window'a dinleyici: sayfanın kendi (document üzerindeki) dinleyicileri önce çalışır, engellediyse sayılmaz.
  window.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    if (a.hasAttribute("download") || a.hasAttribute("data-no-progress")) {
      skipUnloadUntil = Date.now() + 1500;
      return;
    }
    if (isPlainNavigation(a, e)) navigationStarted();
  });

  window.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form || form.hasAttribute("data-no-progress")) return;
    var target = (form.getAttribute("target") || "").toLowerCase();
    if (target && target !== "_self" && target !== "_top") return;
    navigationStarted();
  });

  // Betikle yapılan geçişler (location.href = ..., form.submit(), yenileme) için.
  window.addEventListener("beforeunload", function () { if (!running) navigationStarted(); });

  window.addEventListener("pageshow", function (e) {
    // Geri tuşuyla önbellekten dönülen sayfada eski çubuk kalmasın.
    if (e.persisted) { reset(); resetPull(); }
  });

  // Yeni sayfada: geçiş az önce başladıysa çubuk sayfa tamamen yüklenene kadar sürer (Safari gibi).
  (function continueNavigation() {
    var started = 0;
    try {
      started = Number(sessionStorage.getItem(NAV_KEY)) || 0;
      sessionStorage.removeItem(NAV_KEY);
    } catch (e) { return; }
    if (!started || Date.now() - started > NAV_MAX_AGE || document.readyState === "complete") return;
    start(70);
    window.addEventListener("load", function () { setTimeout(done, 50); });
    navTimer = setTimeout(done, NAV_TIMEOUT);
  })();

  // ------------------------------------------------------------------ aşağı çekince yenileme
  var PULL_MAX = 110, PULL_READY = 70, RESIST = 0.5;
  var pull = null, pullEl = null, startX = 0, startY = 0, distance = 0, decided = false, active = false;
  var reloading = false;

  var spin = null;
  var SVG_NS = "http://www.w3.org/2000/svg";

  function pullIndicator() {
    if (!pullEl) {
      pullEl = css(document.createElement("div"), {
        position: "fixed", top: "0", left: "50%", width: "40px", height: "40px", "margin-left": "-20px",
        "z-index": "2147483646", "border-radius": "50%", background: dark ? "#2c2c2e" : "#fff",
        "box-shadow": dark ? "0 2px 10px rgba(0,0,0,.6)" : "0 2px 10px rgba(0,0,0,.22)", display: "flex",
        "align-items": "center", "justify-content": "center", "pointer-events": "none",
        transform: "translateY(-60px)", opacity: "0"
      });
      pullEl.id = "hs-pull";
      pullEl.setAttribute("aria-hidden", "true");
      // Yenileme oku; renkler öznitelik olarak (CSP'de style="" engellenir).
      var svg = document.createElementNS(SVG_NS, "svg");
      var attrs = { viewBox: "0 0 24 24", width: "22", height: "22", fill: "none", stroke: color,
        "stroke-width": "2.4", "stroke-linecap": "round", "stroke-linejoin": "round" };
      for (var k in attrs) svg.setAttribute(k, attrs[k]);
      ["M20 12a8 8 0 1 1-2.34-5.66", "M20 4v5h-5"].forEach(function (d) {
        var p = document.createElementNS(SVG_NS, "path");
        p.setAttribute("d", d);
        svg.appendChild(p);
      });
      pullEl.appendChild(svg);
      document.body.appendChild(pullEl);
    }
    return pullEl;
  }

  function showPull(d) {
    var el = pullIndicator();
    el.firstChild.setAttribute("stroke-width", d >= PULL_READY ? "2.9" : "2.4");
    css(el, {
      transition: "none", opacity: String(Math.min(1, d / PULL_READY)),
      transform: "translateY(" + (d - 50) + "px) rotate(" + (d / PULL_READY * 270) + "deg)"
    });
  }

  function resetPull() {
    active = false; decided = false; distance = 0; pull = null;
    if (!pullEl || reloading) return;
    if (spin) { spin.cancel(); spin = null; }
    css(pullEl, { transition: "transform .25s ease, opacity .25s ease", opacity: "0", transform: "translateY(-60px)" });
  }

  function scrollTop() {
    return (document.scrollingElement || document.documentElement).scrollTop || window.pageYOffset || 0;
  }

  function blocksPull(node) {
    for (var el = node; el && el !== document.body && el.nodeType === 1; el = el.parentElement) {
      // Açık pencerelerde (modal, alt sayfa) çekmek pencereyi kaydırmak içindir, sayfayı yenilemez.
      if (el.matches("[data-no-pull-refresh], [aria-modal='true'], dialog[open], .modal, .offcanvas.show")) return true;
      if (el.scrollTop > 0) {
        var oy = getComputedStyle(el).overflowY;
        if (oy === "auto" || oy === "scroll") return true;   // içteki kaydırılan alan yukarıda değil
      }
    }
    var body = document.body;
    return body.classList.contains("modal-open") || getComputedStyle(body).overflow === "hidden";
  }

  document.addEventListener("touchstart", function (e) {
    if (reloading || e.touches.length !== 1 || scrollTop() > 0 || blocksPull(e.target)) { pull = null; return; }
    pull = true; decided = false; active = false; distance = 0;
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });

  document.addEventListener("touchmove", function (e) {
    if (!pull) return;
    if (e.touches.length !== 1) { resetPull(); return; }
    var dx = e.touches[0].clientX - startX, dy = e.touches[0].clientY - startY;
    if (!decided) {
      if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      decided = true;
      // Yalnızca sayfanın en üstündeyken aşağı doğru çekiş; yana kaydırma ve yukarı kaydırma olduğu gibi kalır.
      if (dy <= 0 || Math.abs(dx) > Math.abs(dy) || scrollTop() > 0) { pull = null; return; }
      active = true;
    }
    if (!active) return;
    if (dy <= 0) { distance = 0; showPull(0); return; }
    if (e.cancelable) e.preventDefault();      // sayfanın kendi esnemesi yerine göstergemiz iner
    distance = Math.min(PULL_MAX, dy * RESIST);
    showPull(distance);
  }, { passive: false });

  function release() {
    if (!active) { pull = null; return; }
    if (distance >= PULL_READY) {
      reloading = true;
      var el = pullIndicator();
      css(el, { transition: "transform .25s ease", opacity: "1", transform: "translateY(" + (PULL_READY - 50) + "px)" });
      if (el.firstChild.animate) {
        spin = el.firstChild.animate([{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }],
          { duration: 800, iterations: Infinity });
      }
      navigationStarted();
      setTimeout(function () { location.reload(); }, 150);
      // Yenileme bir sebeple olmazsa (çevrimdışı) gösterge takılı kalmasın.
      setTimeout(function () { reloading = false; resetPull(); }, NAV_TIMEOUT);
      active = false; pull = null;
      return;
    }
    resetPull();
  }

  document.addEventListener("touchend", release, { passive: true });
  document.addEventListener("touchcancel", resetPull, { passive: true });

  window.PageProgress = { start: start, done: done, enabled: true };
})();
