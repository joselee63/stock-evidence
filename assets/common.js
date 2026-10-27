// 공통: 데이터 불러오기, 이스케이프, 숫자 표시, 시황 띠
var SE = (function () {
  var params = new URLSearchParams(location.search);
  var date = params.get('date');
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) date = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pct(x, d) {
    if (x == null || isNaN(x)) return '—';
    return (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x * 100).toFixed(d == null ? 1 : d) + '%';
  }
  function pp(x) {
    if (x == null || isNaN(x)) return '—';
    return (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x * 100).toFixed(2) + '%p';
  }
  function cls(x) { return x > 0 ? 'up' : x < 0 ? 'down' : ''; }
  function won(x) { return x == null ? '—' : Math.round(x).toLocaleString('ko-KR'); }
  function eok(x) { return x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toLocaleString('ko-KR') + '억'; }
  function q(extra) {
    var p = new URLSearchParams(extra || {});
    if (date) p.set('date', date);
    var s = p.toString();
    return s ? '?' + s : '';
  }
  function load() {
    var url = date ? 'data/archive/' + date + '.json' : 'data/latest.json';
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }
  function archive() {
    return fetch('data/archive/index.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; });
  }
  function marketHTML(m, compact) {
    var g = m.regime, nq = m.nasdaq, out = [];
    function chip(label, value, warn, wide) {
      return '<div class="chip' + (wide ? ' wide' : '') + (warn ? ' warn' : '') + '"><span>' + esc(label) + '</span><span>' + value + '</span></div>';
    }
    ['코스피', '코스닥'].forEach(function (k) {
      var x = g[k];
      out.push(chip(k + ' ' + won(x.close) + ' ' + pct(x.chg),
        '60일선 ' + (x.above60 ? '위 ✓' : '아래'), !x.above60));
    });
    if (m.hot && m.hot.length) {
      out.push(chip('돈 몰린 업종 (거래대금 증가)', m.hot.map(function (h) { return esc(h.name); }).join(' · '), false, true));
    }
    if (nq) {
      var big = Math.abs(nq.chg) >= 0.005;
      out.push(chip('나스닥 선물 (' + esc(nq.at) + ')', pct(nq.chg) + (big ? ' · 경고선(±0.5%) 넘음' : ''), big, true));
    }
    out.push(chip('신고가 전략 비중 (계단식)', '평소의 ' + g.weight + '%', g.weight < 60, true));
    return out.join('');
  }
  return { esc: esc, pct: pct, pp: pp, cls: cls, won: won, eok: eok, q: q, load: load, archive: archive,
           marketHTML: marketHTML, date: date, params: params };
})();
