// 종목 근거 카드: 가격 차트, 수급 막대, 재료 타임라인(더보기·종류 필터)
(function () {
  var NS = 'http://www.w3.org/2000/svg';

  // ---- 가격 차트 (예시 데이터)
  var prices = [9100, 9140, 9080, 9160, 9220, 9190, 9260, 9310, 9280, 9350, 9400, 9370, 9440, 9500, 9470,
    9540, 9600, 9570, 9650, 9700, 9680, 9760, 9820, 9790, 9870, 10020, 11150, 11380, 11240, 11560];
  var lo = 8950, hi = 11700, n = prices.length;
  function X(i) { return (i * 600 / (n - 1)).toFixed(1); }
  function Y(p) { return (150 - (p - lo) / (hi - lo) * 142).toFixed(1); }
  document.getElementById('pxLine').setAttribute('points', prices.map(function (p, i) { return X(i) + ',' + Y(p); }).join(' '));
  var ma = [];
  for (var i = 19; i < n; i++) {
    var s = 0;
    for (var j = i - 19; j <= i; j++) s += prices[j];
    ma.push(X(i) + ',' + Y(s / 20));
  }
  document.getElementById('maLine').setAttribute('points', ma.join(' '));
  var gap = document.getElementById('gapLine');
  gap.setAttribute('x1', X(26)); gap.setAttribute('x2', X(26));

  // ---- 외인+기관 일별 순매수 막대 (예시 데이터, 억원)
  var days = ['10/14', '10/15', '10/16', '10/19', '10/20', '10/21', '10/22', '10/23', '10/26', '10/27'];
  var vals = [8, 5, -3, 7, 4, 6, 18, 12, -6, 9];
  var max = Math.max.apply(null, vals.map(Math.abs));
  var bars = document.getElementById('bars');
  days.forEach(function (d, k) {
    var v = vals[k];
    var h = Math.round(Math.abs(v) / max * 60);
    var el = document.createElement('div');
    el.className = 'bar';
    el.setAttribute('aria-label', d + ' ' + (v > 0 ? '+' : '') + v + '억');
    el.innerHTML =
      '<div class="pos"><small>' + (v > 0 ? '+' + v : '') + '</small><i style="height:' + (v > 0 ? h : 0) + 'px"></i></div>' +
      '<div class="zero"></div>' +
      '<div class="neg"><i style="height:' + (v < 0 ? h : 0) + 'px"></i><small>' + (v < 0 ? v : '') + '</small></div>' +
      '<small class="d">' + d + '</small>';
    bars.appendChild(el);
  });

  // ---- 재료 타임라인
  var TAGCLS = { '공시': 't-disc', '리포트': 't-rep', '첫 보도': 't-first', '참고 패턴': 't-ref' };
  var all = [
    { time: '9/1~10/21', kind: '가격·수급', key: true, tags: ['가격·수급', '급등 전'], title: '외+기 40일 누적 순매수 +[96]억 — 시총 대비 상위 18%, 60일선 위에서 완만한 상승', note: '매수 근거는 급등 뒤가 아니라 이 구간의 수급' },
    { time: '10/15 14:00', kind: '기사', key: false, tags: ['기사', '사전 징후'], title: '“A전자, 북미 고객사 현장 실사 진행” — [언론사]', note: '공시 1주 전 보도 — 일부 선반영 가능성' },
    { time: '10/21 18:40', kind: '공시', key: true, tags: ['공시', '첫 보도', '장 마감 뒤'], title: '단일판매·공급계약 체결 — 북미 ESS 업체, 계약금액 매출 대비 38%', link: 'https://dart.fss.or.kr' },
    { time: '10/21 19:10', kind: '텔레그램', key: false, tags: ['텔레그램 2곳', '참고 패턴'], title: '공시 직후 속보·테마 채널 언급', note: '장후 언급 종목은 다음날 갭(+1.31%p) 뒤 장중 되밀림(−0.61%p) 경향' },
    { time: '10/22 07:10', kind: '기사', key: true, tags: ['기사 14건', '재탕 (공시 기반)'], title: '“A전자, 북미 ESS 장비 수주…” 외 13건 — 새 정보 없음' },
    { time: '10/22 09:30', kind: '기사', key: false, tags: ['기사', '동종사'], title: '“B사도 북미 증설용 장비 발주 받아” — [언론사]', note: '업종 전체 수주 사이클 신호' },
    { time: '10/22 장중', kind: '가격·수급', key: true, tags: ['가격·수급'], title: '시가 갭 +11.3%로 52주 신고가 돌파, 거래량 평소 4배. 개인 +120억, 외+기 +18억 (함께 매수)' },
    { time: '10/23~27', kind: '가격·수급', key: true, tags: ['가격·수급', '경고등 꺼짐'], title: '외+기 +12·−6·+9억, 가격은 갭 위 유지 — 개인만 받치는 패턴 아님' },
    { time: '10/24 10:05', kind: '리포트', key: false, tags: ['리포트', '업종'], title: '[증권사] 2차전지 장비 업종 — 수주 사이클 재개, 비중 확대' },
    { time: '10/26 16:20', kind: '기사', key: false, tags: ['기사', '산업'], title: '“미국 ESS 설치량 3분기 사상 최대” — [언론사]' },
    { time: '10/26 18:05', kind: '공시', key: false, tags: ['공시'], title: '기업설명회(IR) 개최 예정 — [날짜]', link: 'https://dart.fss.or.kr' },
    { time: '10/27 08:00', kind: '리포트', key: true, tags: ['리포트', '첫 커버'], title: '[증권사] “수주 잔고 사상 최대, 내년 실적 반영” — 목표가 [가격]' }
  ];
  var KINDS = ['전체', '공시', '기사', '리포트', '가격·수급', '텔레그램'];
  var state = { more: false, kind: '전체' };
  var keyCount = all.filter(function (x) { return x.key; }).length;
  var tl = document.getElementById('timeline');
  var filters = document.getElementById('tlFilters');
  var moreBtn = document.getElementById('tlMore');
  var countEl = document.getElementById('tlCount');

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  KINDS.forEach(function (k) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'fbtn';
    b.dataset.kind = k;
    var cnt = k === '전체' ? all.length : all.filter(function (x) { return x.kind === k; }).length;
    b.textContent = k + ' ' + cnt;
    b.addEventListener('click', function () { state.kind = k; render(); });
    filters.appendChild(b);
  });
  moreBtn.addEventListener('click', function () { state.more = !state.more; state.kind = '전체'; render(); });

  function render() {
    var shown = state.more
      ? all.filter(function (x) { return state.kind === '전체' || x.kind === state.kind; })
      : all.filter(function (x) { return x.key; });
    tl.innerHTML = shown.map(function (x) {
      var tags = x.tags.map(function (t) { return '<span class="tag ' + (TAGCLS[t] || '') + '">' + esc(t) + '</span>'; }).join('');
      var title = x.link
        ? '<a class="title" href="' + esc(x.link) + '" target="_blank" rel="noopener">' + esc(x.title) + '</a>'
        : '<span class="title">' + esc(x.title) + '</span>';
      var note = x.note ? '<span class="note">' + esc(x.note) + '</span>' : '';
      return '<li><span class="when">' + esc(x.time) + '</span><div class="what"><div class="tags">' + tags + '</div>' + title + note + '</div></li>';
    }).join('');
    filters.hidden = !state.more;
    Array.prototype.forEach.call(filters.children, function (b) { b.setAttribute('aria-pressed', b.dataset.kind === state.kind ? 'true' : 'false'); });
    moreBtn.setAttribute('aria-expanded', state.more ? 'true' : 'false');
    moreBtn.textContent = state.more ? '핵심만 보기 ▴' : '재료 ' + (all.length - keyCount) + '건 더 보기 ▾';
    countEl.textContent = state.more ? '전체 ' + all.length + '건' : '핵심 ' + keyCount + '건 · 전체 ' + all.length + '건';
  }
  render();
})();
