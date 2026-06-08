// Google-Docs-style margin comments: align each card to its highlight,
// stack on collision, draw a connector on focus, and sync hover/click.
(function () {
  var SVGNS = "http://www.w3.org/2000/svg";

  function setActive(idx, on) {
    document.querySelectorAll('[data-idx="' + idx + '"]').forEach(function (el) {
      el.classList.toggle('active', on);
    });
    if (on) drawConnector(idx); else clearConnector();
  }

  function isStacked() {
    return window.matchMedia('(max-width: 900px)').matches;
  }

  // Lay out margin cards: align top of each card to its highlight, push down on overlap.
  function layout() {
    var area = document.getElementById('docArea');
    var margin = document.getElementById('marginCol');
    if (!area || !margin) return;
    var cards = Array.prototype.slice.call(margin.querySelectorAll('.ann-side'));
    if (isStacked()) {
      cards.forEach(function (c) { c.style.top = ''; });
      margin.style.height = '';
      clearConnector();
      return;
    }
    var areaTop = area.getBoundingClientRect().top;
    // sort by the vertical position of each card's target highlight
    cards.forEach(function (c) { c.dataset._t = targetTop(c, areaTop); });
    cards.sort(function (a, b) { return (+a.dataset._t) - (+b.dataset._t); });

    var prevBottom = 0;
    var gap = 8;
    cards.forEach(function (card) {
      var t = Math.max(+card.dataset._t, prevBottom);
      card.style.top = t + 'px';
      prevBottom = t + card.offsetHeight + gap;
    });
    margin.style.height = prevBottom + 'px';
  }

  function targetTop(card, areaTop) {
    var mark = document.getElementById('mark-' + card.dataset.idx);
    if (!mark) return parseFloat(card.style.top) || 0; // unlocated: keep flow order
    return mark.getBoundingClientRect().top - areaTop;
  }

  function drawConnector(idx) {
    var svg = document.getElementById('docConnector');
    var mark = document.getElementById('mark-' + idx);
    var card = document.getElementById('card-' + idx);
    if (!svg || !mark || !card || isStacked()) return;
    var area = document.getElementById('docArea').getBoundingClientRect();
    var m = mark.getBoundingClientRect();
    var c = card.getBoundingClientRect();
    var x1 = m.right - area.left, y1 = m.top - area.top + m.height / 2;
    var x2 = c.left - area.left, y2 = c.top - area.top + 16;
    var mid = (x1 + x2) / 2;
    svg.innerHTML =
      '<path d="M' + x1 + ',' + y1 + ' C' + mid + ',' + y1 + ' ' + mid + ',' + y2 + ' ' + x2 + ',' + y2 +
      '" fill="none" stroke="#a5b4fc" stroke-width="1.5" stroke-dasharray="3 3"/>' +
      '<circle cx="' + x1 + '" cy="' + y1 + '" r="3" fill="#6366f1"/>';
  }
  function clearConnector() {
    var svg = document.getElementById('docConnector');
    if (svg) svg.innerHTML = '';
  }

  // hover / click sync
  document.addEventListener('mouseover', function (e) {
    var t = e.target.closest('[data-idx]');
    if (t) setActive(t.getAttribute('data-idx'), true);
  });
  document.addEventListener('mouseout', function (e) {
    var t = e.target.closest('[data-idx]');
    if (t) setActive(t.getAttribute('data-idx'), false);
  });
  document.addEventListener('click', function (e) {
    var mark = e.target.closest('mark.ann');
    if (mark) {
      var card = document.getElementById('card-' + mark.getAttribute('data-idx'));
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    var c = e.target.closest('.ann-card');
    if (c) {
      var mk = document.getElementById('mark-' + c.getAttribute('data-idx'));
      if (mk) mk.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });

  var raf;
  function relayout() { cancelAnimationFrame(raf); raf = requestAnimationFrame(layout); }
  window.addEventListener('load', layout);
  window.addEventListener('resize', relayout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);
  // run once now in case load already fired
  if (document.readyState === 'complete') layout();
})();
