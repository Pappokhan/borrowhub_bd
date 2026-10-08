(function () {
  'use strict';
  window.__bh = true; // tells the head fallback that scripts loaded
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function fmt(n) { return Math.round(n).toLocaleString('en-IN'); }

  /* ---------- number tween (used by counters and the price calculator) ---------- */
  function tween(el, to, prefix, ms) {
    prefix = prefix || '';
    if (reduce) { el.textContent = prefix + fmt(to); return; }
    var from = parseFloat(el.dataset.cur || '0'), start = null;
    ms = ms || 700;
    function step(t) {
      if (start === null) start = t;
      var p = Math.min((t - start) / ms, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = prefix + fmt(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step); else el.dataset.cur = to;
    }
    requestAnimationFrame(step);
  }
  window.bhTween = tween;

  /* ---------- scroll reveal ---------- */
  var REVEAL = '.listing-card,.panel,.panel-flat,.stat,.cat-tile,.section-title,.step-list li,.empty,.gallery-main,.accordion-item,.notif-item';
  var items = $$(REVEAL);
  items.forEach(function (el) {
    var sibs = el.parentElement ? Array.prototype.indexOf.call(el.parentElement.children, el) : 0;
    el.style.setProperty('--i', Math.max(0, sibs));
  });
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add('in'); });
  }

  /* ---------- count-up numbers: <b data-count="1200" data-prefix="৳">1,200</b> ---------- */
  var counters = $$('[data-count]');
  function runCounter(el) { tween(el, parseFloat(el.dataset.count) || 0, el.dataset.prefix || '', 1100); }
  if (counters.length) {
    if ('IntersectionObserver' in window && !reduce) {
      counters.forEach(function (el) { el.dataset.cur = 0; el.textContent = (el.dataset.prefix || '') + '0'; });
      var co = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { runCounter(en.target); co.unobserve(en.target); } });
      }, { threshold: 0.4 });
      counters.forEach(function (el) { co.observe(el); });
    }
  }

  /* ---------- images: fade in once loaded ---------- */
  $$('.listing-media img').forEach(function (img) {
    if (img.complete && img.naturalWidth) img.classList.add('loaded');
    else { img.addEventListener('load', function () { img.classList.add('loaded'); }); img.addEventListener('error', function () { img.classList.add('loaded'); }); }
  });

  /* ---------- nav shadow + scroll progress ---------- */
  var nav = $('.bh-nav'), bar = $('#scroll-progress'), ticking = false;
  function onScroll() {
    var y = window.scrollY || 0;
    if (nav) nav.classList.toggle('scrolled', y > 8);
    if (bar) {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.transform = 'scaleX(' + (h > 0 ? Math.min(y / h, 1) : 0) + ')';
    }
    ticking = false;
  }
  window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

  /* ---------- button ripple + loading state on submit ---------- */
  if (!reduce) {
    document.addEventListener('pointerdown', function (e) {
      var btn = e.target.closest && e.target.closest('.btn');
      if (!btn || btn.disabled) return;
      var r = btn.getBoundingClientRect(), size = Math.max(r.width, r.height) / 2, s = document.createElement('span');
      s.className = 'ripple';
      s.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:' + (e.clientX - r.left - size / 2) + 'px;top:' + (e.clientY - r.top - size / 2) + 'px';
      btn.appendChild(s);
      setTimeout(function () { s.remove(); }, 650);
    });
  }
  document.addEventListener('submit', function (e) {
    var b = e.submitter;
    if (!b || b.classList.contains('no-loading') || e.defaultPrevented) return;
    setTimeout(function () { b.classList.add('is-loading'); b.setAttribute('aria-busy', 'true'); b.disabled = true; }, 0);
  });
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) $$('.btn.is-loading').forEach(function (b) { b.classList.remove('is-loading'); b.disabled = false; b.removeAttribute('aria-busy'); });
  });

  /* ---------- flash messages: auto-dismiss ---------- */
  $$('.alert-success, .alert-info').forEach(function (a) {
    setTimeout(function () {
      if (!document.body.contains(a)) return;
      a.classList.add('closing');
      setTimeout(function () { a.remove(); }, 400);
    }, 6500);
  });

  /* ---------- gallery ---------- */
  $$('[data-gallery-thumb]').forEach(function (t) {
    t.addEventListener('click', function () {
      var main = document.getElementById('gallery-main-img');
      if (!main) return;
      main.classList.add('swap');
      setTimeout(function () { main.src = t.dataset.src; main.classList.remove('swap'); }, reduce ? 0 : 180);
      $$('[data-gallery-thumb]').forEach(function (x) { x.classList.remove('on'); });
      t.classList.add('on');
    });
  });

  /* ---------- progress bars grow in ---------- */
  $$('.progress-bar').forEach(function (p) {
    var w = p.style.width; if (reduce) return;
    p.style.width = '0'; setTimeout(function () { p.style.width = w; }, 250);
  });

  /* ---------- live price calculator on the listing page ---------- */
  var box = document.getElementById('book-box');
  if (box) {
    var price = parseFloat(box.dataset.price), deposit = parseFloat(box.dataset.deposit), fee = parseFloat(box.dataset.fee);
    var start = $('[name=start_date]', box), end = $('[name=end_date]', box);
    var addr = document.getElementById('delivery-address-wrap');
    var calc = document.getElementById('calc');
    var method = function () {
      var c = $('[name=delivery_method]:checked', box);
      if (c) return c.value;
      var h = $('input[type=hidden][name=delivery_method]', box);
      return h ? h.value : 'pickup';
    };
    var update = function () {
      if (!start || !end) return;
      var d = 0;
      if (start.value && end.value) d = Math.round((new Date(end.value) - new Date(start.value)) / 86400000) + 1;
      if (start.value) end.min = start.value;
      var delivery = method() === 'delivery';
      if (addr) addr.style.display = delivery ? '' : 'none';
      calc.style.display = d > 0 ? '' : 'none';
      if (d <= 0) return;
      var rent = price * d, f = delivery ? fee : 0;
      document.getElementById('c-days').textContent = d + (d === 1 ? ' day' : ' days');
      tween(document.getElementById('c-rent'), rent, '৳', 400);
      tween(document.getElementById('c-fee'), f, '৳', 400);
      document.getElementById('c-fee-row').style.display = delivery ? '' : 'none';
      tween(document.getElementById('c-total'), rent + f + deposit, '৳', 500);
      var tot = $('.price-line.total', box);
      tot.classList.remove('bump'); void tot.offsetWidth; tot.classList.add('bump');
    };
    [start, end].forEach(function (el) { if (el) el.addEventListener('change', update); });
    $$('[name=delivery_method]', box).forEach(function (r) { r.addEventListener('change', update); });
    update();
  }
})();
