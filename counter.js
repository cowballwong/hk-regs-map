/* Visit counter: a public count of visits, shown in the footer.
   Counts once per browser session (sessionStorage flag); a reload in the same
   tab session only reads the number. No cookies, no personal data, no
   third-party script: one Firestore REST call to a single integer.
   Security rules only allow "+1 on visits". If anything fails, the line stays
   hidden and the map is never affected. */
(function () {
  'use strict';
  var KEY = 'AIzaSyCNwMFWLo2WP6la9bx2rdwIoeEsv-6uNEM'; // public Firebase web key (not a secret)
  var BASE = 'https://firestore.googleapis.com/v1/projects/worldcup-bet-2026/databases/(default)/documents';
  var DOC = 'projects/worldcup-bet-2026/databases/(default)/documents/site_counters/hk-regs-map';
  var FLAG = 'hkmap_visit_counted';

  function show(n) {
    var el = document.getElementById('visits');
    var num = document.getElementById('visitsn');
    if (!el || !num || !isFinite(n) || n < 1) return;
    num.textContent = Number(n).toLocaleString('en-GB');
    el.hidden = false;
  }

  function call(url, opts) {
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, 8000) : 0;
    if (ctl) opts.signal = ctl.signal;
    return fetch(url, opts).then(function (r) {
      clearTimeout(t);
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    });
  }

  function read() {
    return call(BASE + '/site_counters/hk-regs-map?key=' + KEY, { method: 'GET' })
      .then(function (d) { return parseInt(d.fields.visits.integerValue, 10); });
  }

  function count() {
    var body = { writes: [{ transform: { document: DOC, fieldTransforms: [
      { fieldPath: 'visits', increment: { integerValue: '1' } }] } }] };
    return call(BASE + ':commit?key=' + KEY, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (d) {
      try { sessionStorage.setItem(FLAG, '1'); } catch (e) {}
      var v = d && d.writeResults && d.writeResults[0] && d.writeResults[0].transformResults;
      return v && v[0] && v[0].integerValue ? parseInt(v[0].integerValue, 10) : read();
    });
  }

  function run() {
    try {
      if (typeof fetch !== 'function') return;
      var counted = false;
      try { counted = sessionStorage.getItem(FLAG) === '1'; } catch (e) { counted = true; } // storage blocked: read only, never recount
      (counted ? read() : count()).then(show).catch(function () {});
    } catch (e) {}
  }

  // After the map has loaded, so the count never competes with it.
  if (document.readyState === 'complete') setTimeout(run, 400);
  else window.addEventListener('load', function () { setTimeout(run, 400); });
})();
