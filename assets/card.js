// 종목 근거 카드 — ?code=XXXXXX (&date=YYYY-MM-DD)
(function () {
  var E = SE.esc;
  var code = SE.params.get('code');
  var app = document.getElementById('app');
  document.getElementById('back').href = './' + SE.q();
  var BADGE = { '스윙': 'b-swing', '관찰': 'b-watch', '제외': 'b-out' };
  var ICON = {
    ok: '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3A4BD8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    partial: '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A5A00" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3z"/><line x1="12" y1="10" x2="12" y2="14"/><line x1="12" y1="17.5" x2="12" y2="17.6"/></svg>',
    no: '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A90A0" stroke-width="2.5" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>'
  };
  var STATUS = { ok: '일치', partial: '부분 일치', no: '불일치' };
  var LIGHT = {
    on: ['pill-on', '켜짐'], off: ['pill-off', '꺼짐'], wait: ['pill-wait', 'D+3 확인 대기'],
    na: ['pill-wait', '해당 없음'], pass: ['pill-pass', '통과'], fail: ['pill-on', '미통과']
  };
  var TAGCLS = { '공시': 't-disc', '리포트': 't-rep', '시장 경고': 't-ref', '첫 급등': 't-ref', '52주 신고가': 't-first', '40일 수급': 't-first' };

  var VCLS = { '기대 남음': 'v-good', '기대 일부': 'v-some', '판단 보류': 'v-hold', '소진 우려': 'v-bad' };
  var TONE = { plus: ['t-plus', '+'], minus: ['t-minus', '−'], neutral: ['t-neu', '·'] };

  function li(label, value) { return '<li><span>' + E(label) + '</span><b>' + value + '</b></li>'; }

  // 종목 소개 앞단: 왜 올랐나 · 시황 속 위치 · 남은 기대감
  function storyHTML(c, D) {
    var s = c.story, w = s.why, x = s.context, o = s.outlook, g = D.market.regime;
    var items = w.items.length ? '<ul class="mat">' + w.items.map(function (it) {
      var t = it.url ? '<a href="' + E(it.url) + '" target="_blank" rel="noopener noreferrer">' + E(it.title) + '</a>' : E(it.title);
      return '<li><span class="when">' + E(it.time) + '</span><span class="tag ' + (it.kind === '공시' ? 't-disc' : it.kind === '리포트' ? 't-rep' : '') + '">' + E(it.kind) + '</span> ' + t + '</li>';
    }).join('') + '</ul>' : '<p class="note">상승일 앞뒤로 설명할 만한 공시·뉴스·리포트를 찾지 못했습니다.</p>';
    var facts = [];
    facts.push(li('재료 유형', E(w.material_type)));
    if (w.first) facts.push(li('처음 확인', E(w.first.slice(5).replace('-', '/')) + (w.fresh != null ? ' · ' + w.fresh + '거래일 전' : '')));
    if (w.move_day) facts.push(li('상승일 → 지금', E(w.move_day) + ' ' + SE.pct(w.move_ret) + ' → 누적 ' + SE.pct(w.since)));
    var p1 = '<div class="panel"><h3>왜 올랐나</h3>' + items + '<ul class="facts">' + facts.join('') + '</ul></div>';

    var cx = [];
    if (x.mode) cx.push('<p class="mode">' + E(x.mode) + '</p>');
    var f2 = [];
    if (x.theme) {
      f2.push(li('테마', E(x.theme.name) + ' · 5일 ' + SE.pct(x.theme.ret5) + ' (' + x.theme.rank + '/' + x.theme.total + '위)'));
      if (x.theme.peers.length) f2.push(li('같은 테마 강한 종목', x.theme.peers.map(function (p) { return E(p.name) + ' ' + SE.pct(p.ret5); }).join(', ')));
    }
    if (x.sector) f2.push(li('업종', E(x.sector.name) + ' · 기준일 ' + SE.pct(x.sector.ret1) + ' · 거래대금 ' + x.sector.ratio + '배 (' + x.sector.rank + '/' + x.sector.total + '위)'));
    f2.push(li('지수', '코스피 60일선 ' + (g['코스피'].above60 ? '위' : '아래') + ' · 코스닥 60일선 ' + (g['코스닥'].above60 ? '위' : '아래')));
    if (x.themes && x.themes.length > 1) f2.push(li('다른 소속 테마', x.themes.slice(1).map(E).join(', ')));
    var p2 = '<div class="panel"><h3>시황 속 위치</h3>' + cx.join('') + '<ul class="facts">' + f2.join('') + '</ul></div>';

    var ev = o.events.length ? '<ul class="evt">' + o.events.map(function (e) {
      var t = TONE[e.tone] || TONE.neutral;
      return '<li><span class="tone ' + t[0] + '" aria-hidden="true">' + t[1] + '</span><span class="when">' + E(e.when) + '</span><span>' + E(e.text) + '</span></li>';
    }).join('') + '</ul>' : '<p class="note">공시로 확인되는 예정 이벤트 없음</p>';
    var f3 = [];
    if (o.target.mean) f3.push(li('목표가 평균', SE.won(o.target.mean) + '원 · 여력 ' + SE.pct(o.target.upside) + (o.target.recomm ? ' · 의견 ' + o.target.recomm.toFixed(1) + '/5' : '')));
    if (o.per.now || o.per.fwd) f3.push(li('PER', (o.per.now ? o.per.now + '배' : '—') + ' → 추정 ' + (o.per.fwd ? o.per.fwd + '배' : '—')));
    if (o.reports14) f3.push(li('최근 2주 리포트', o.reports14 + '건'));
    var why = o.plus.map(function (r) { return '<li class="t-plus">+ ' + E(r) + '</li>'; }).concat(o.minus.map(function (r) { return '<li class="t-minus">− ' + E(r) + '</li>'; })).join('');
    var p3 = '<div class="panel"><h3>남은 기대감 <span class="badge ' + VCLS[o.verdict] + '">' + E(o.verdict) + '</span></h3>' +
      '<h4>앞으로의 이벤트</h4>' + ev + (f3.length ? '<ul class="facts">' + f3.join('') + '</ul>' : '') +
      (why ? '<h4>판단 이유</h4><ul class="reasons">' + why + '</ul>' : '') +
      '<p class="sub">규칙 기반 판단 · 아직 검증 전 (발굴 기록이 쌓이면 성과로 검증)</p></div>';
    return '<div class="story3">' + p1 + p2 + p3 + '</div>';
  }

  function section(title, body, sub) {
    return '<section class="card"><div class="card-head"><h2>' + E(title) + '</h2>' + (sub ? '<span class="sub">' + sub + '</span>' : '') + '</div>' + body + '</section>';
  }

  function chart(p) {
    var vals = p.close.concat(p.ma20).filter(function (v) { return v != null; });
    if (!vals.length) return '';
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.06 || 1;
    lo -= pad; hi += pad;
    var n = p.close.length;
    function X(i) { return (n > 1 ? i * 600 / (n - 1) : 300).toFixed(1); }
    function Y(v) { return (150 - (v - lo) / (hi - lo) * 142).toFixed(1); }
    function line(arr) {
      return arr.map(function (v, i) { return v == null ? null : X(i) + ',' + Y(v); }).filter(Boolean).join(' ');
    }
    var mk = p.mark != null ? '<line x1="' + X(p.mark) + '" x2="' + X(p.mark) + '" y1="4" y2="150" stroke="#3A4BD8" stroke-width="2" vector-effect="non-scaling-stroke"/>' : '';
    var last = p.close[n - 1];
    return '<svg class="chart" role="img" aria-label="최근 ' + n + '거래일 종가 차트, 마지막 ' + SE.won(last) + '원" viewBox="0 0 600 160" preserveAspectRatio="none">' +
      '<line x1="0" y1="150" x2="600" y2="150" stroke="#E3E5EA" vector-effect="non-scaling-stroke"/>' + mk +
      '<polyline points="' + line(p.ma20) + '" fill="none" stroke="#8A90A0" stroke-width="1.5" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"/>' +
      '<polyline points="' + line(p.close) + '" fill="none" stroke="#15171C" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>' +
      '<div class="axis"><span>' + E(p.dates[0]) + '</span><span>' + E(p.mark_label || '') + '</span><span>' + E(p.dates[n - 1]) + '</span></div>';
  }

  function bars(f) {
    var max = Math.max.apply(null, f.map(function (x) { return Math.abs(x.fpi || 0); })) || 1;
    return '<div class="bars">' + f.map(function (x) {
      var v = x.fpi || 0, h = Math.round(Math.abs(v) / max * 60);
      return '<div class="bar" aria-label="' + E(x.d) + ' 외인+기관 ' + SE.eok(v) + '">' +
        '<div class="pos"><small>' + (v > 0 ? '+' + v.toLocaleString('ko-KR') : '') + '</small><i style="height:' + (v > 0 ? h : 0) + 'px"></i></div>' +
        '<div class="zero"></div>' +
        '<div class="neg"><i style="height:' + (v < 0 ? h : 0) + 'px"></i><small>' + (v < 0 ? '−' + Math.abs(v).toLocaleString('ko-KR') : '') + '</small></div>' +
        '<small class="d">' + E(x.d) + '</small></div>';
    }).join('') + '</div>';
  }

  function rows(list) {
    return '<div class="rows">' + list.map(function (x) { return '<div class="row"><b>' + E(x.title) + '</b><span>' + E(x.text) + '</span></div>'; }).join('') + '</div>';
  }

  function render(D, c) {
    document.title = c.name + ' · 종목 근거 카드';
    document.getElementById('stamp').textContent = D.asof_label + ' · ' + D.updated + ' 갱신';
    var h = [];
    h.push('<section class="market" aria-label="시황">' + SE.marketHTML(D.market) + '</section>');

    // 머리
    var checks = c.checks.map(function (x) {
      return '<div class="check' + (x.status === 'partial' ? ' partial' : x.status === 'no' ? ' miss' : '') + '"><div class="t">' + ICON[x.status] +
        '<b>' + E(x.name) + '</b><em>' + STATUS[x.status] + '</em></div><span class="body-text">' + E(x.text) + '</span></div>';
    }).join('');
    var notes = (c.notes || []).map(function (n) { return '<li>' + E(n) + '</li>'; }).join('');
    var st = c.story;
    var vd = st.outlook.verdict;
    h.push('<section class="card hero"><div class="id-row"><div><h1>' + E(c.name) + '</h1><span class="note" style="font-size:14px">' +
      E([c.market, c.sector, c.code, c.mcap_eok ? '시총 ' + c.mcap_eok.toLocaleString('ko-KR') + '억' : ''].filter(Boolean).join(' · ')) + '</span></div>' +
      '<div class="price"><b>' + SE.won(c.close) + '</b><span class="chg ' + SE.cls(c.chg) + '">' + SE.pct(c.chg) + '</span></div>' +
      '<div class="verdict"><span class="badge lg ' + VCLS[vd] + '">기대감 · ' + E(vd) + '</span>' +
      '<span class="badge ' + BADGE[c.cat] + '">분류 · ' + E(c.cat === '스윙' ? '스윙 후보' : c.cat) + '</span></div></div>' +
      '<p class="thesis">' + (st.why.move_day ? '<span class="movechip ' + SE.cls(st.why.move_ret) + '">' + E(st.why.move_day) + ' ' + SE.pct(st.why.move_ret) + '</span> ' : '') +
      E(st.why.line) + '</p>' + storyHTML(c, D) + '</section>');

    h.push('<section class="card"><div class="card-head"><h2>분류 근거 — 검증된 규칙 체크</h2><span class="sub">근거 일치 ' + c.match + ' / 4' +
      (c.signal_day ? ' · 신호일 ' + E(c.signal_day.slice(5)) : '') + '</span></div>' +
      '<p class="body-text">' + E(c.thesis) + '</p><div class="checks">' + checks + '</div>' +
      (notes ? '<ul class="bul">' + notes + '</ul>' : '') +
      '<p class="note">스윙·관찰·제외 분류는 백테스트로 검증된 가격·수급 규칙으로만 정합니다. 위의 재료·시황·기대감은 판단을 돕는 정보이고, 뉴스 유무 자체로는 성적이 갈리지 않았습니다.</p></section>');

    var main = [], side = [];
    main.push(section('가격 흐름 (최근 ' + c.price.close.length + '거래일)', '<div class="legend"><span><i style="width:16px;height:2px;background:var(--ink)"></i>종가</span>' +
      '<span><i style="width:16px;height:0;border-top:2px dashed #8A90A0"></i>20일선</span>' +
      (c.price.mark != null ? '<span><i style="width:2px;height:12px;background:var(--accent)"></i>' + E(c.price.mark_label) + '</span>' : '') + '</div>' + chart(c.price)));

    var lights = c.lights.map(function (l) {
      var st = LIGHT[l.state] || ['pill-wait', l.state];
      return '<div class="light' + (l.key === 'pass' ? ' pass' : '') + '"><div><b>' + E(l.label) + '</b><span class="sub">' + E(l.sub) + '</span></div><span class="' + st[0] + '">' + st[1] + '</span></div>';
    }).join('');
    var stats = c.flow_stats.map(function (s) { return '<div class="stat"><span>' + E(s.label) + '</span><span>' + E(s.value) + '</span></div>'; }).join('');
    main.push(section('수급 경고등', '<div class="lights">' + lights + '</div><h3 class="h3">외인+기관 일별 순매수 (억원) · 위 = 매수 · 아래 = 매도</h3>' + bars(c.flows) +
      '<div class="stats">' + stats + '</div><p class="body-text">읽는 법: 외인·기관이 급등 뒤 따라 산다고 시장보다 더 오르지는 않았습니다(손바뀜 20일 −0.30%p, 42,342건). 수급은 경고등이 켜진 종목을 빼는 데만 쓰고, 매수 근거는 급등 전부터 쌓인 40일 수급과 추세로 봅니다.</p>',
      '수급은 사는 근거가 아니라 거르는 근거'));

    main.push('<section class="card"><div class="card-head"><h2>재료 타임라인</h2><span id="tlCount" class="sub"></span></div>' +
      '<div id="tlFilters" class="filters" role="group" aria-label="재료 종류" hidden></div><ol id="timeline" class="timeline"></ol>' +
      '<button id="tlMore" class="more" type="button" aria-expanded="false" aria-controls="timeline"></button></section>');

    var a = c.ai || {};
    if (a.source === 'ai') {
      main.push(section('AI 판독', '<dl class="kv">' + [['재료 유형', a.material_type], ['신규성', a.novelty], ['규모', a.scale], ['지속 근거', a.lasting],
        ['일회성 위험', a.one_off], ['산업 맥락', a.industry]].map(function (kv) {
          return '<dt>' + E(kv[0]) + '</dt><dd>' + E(kv[1] || '—') + '</dd>';
        }).join('') + '</dl>', '공시·뉴스·리포트 제목을 Claude가 읽고 정리'));
    }

    var b = c.base;
    side.push(section('과거 성적표', '<p class="note">이 종목에 해당하는 패턴이 과거에 어땠는지 (2015~2026 무편향 백테스트, 상폐 포함)</p>' +
      (b.buy.length ? '<h3 class="grp buy">매수 근거 — 해당</h3>' + rows(b.buy) : '<h3 class="grp buy">매수 근거 — 해당 없음</h3>') +
      (b.out.length ? '<h3 class="grp out">제외 신호 — 해당</h3>' + rows(b.out) : '<h3 class="grp out">제외 신호 — 해당 없음</h3>') +
      '<h3 class="grp ref">참고 — 근거로 쓰지 않는 것</h3>' + rows(b.ref) +
      '<p class="sub">2026년 하반기엔 기존 엣지들이 약해짐 — 실전 기록 20회 뒤 재판정</p>'));

    side.push(section('반대 근거', c.counter.length ? '<ul class="bul">' + c.counter.map(function (x) { return '<li>' + E(x) + '</li>'; }).join('') + '</ul>' : '<p class="note">자동으로 찾은 반대 근거 없음</p>'));

    if (c.plan && c.cat !== '제외') {
      var p = c.plan;
      side.push(section('시나리오', '<div class="scn"><b style="color:var(--up-ink)">지속</b><span class="body-text">20일선 위 유지 → 보유, 고점에서 −' + p.trail + '% 내려오면 정리(따라가기)</span></div>' +
        '<div class="scn"><b style="color:var(--down-ink)">무효화</b><span class="body-text">종가 ' + SE.won(p.stop_price) + '원(−' + p.stop + '%) 이탈, 또는 ‘가격은 버티는데 외인·기관이 파는’ 경고등이 켜지면 → 정리</span></div>' +
        '<div class="box2"><span>변동성 손절폭</span><span>−' + p.stop + '%</span><span>2%룰 최대 비중</span><span>계좌의 ' + p.weight + '%</span>' +
        '<span>1차 익절 (3R)</span><span>+' + p.take + '% (' + SE.won(p.take_price) + '원)에서 1/3</span></div>', '기준일 종가 기준'));
    }
    side.push(section('리스크 점검', '<div class="risk">' + c.risk.map(function (r) {
      return '<span>' + E(r.label) + '</span><span' + (r.warn ? ' style="color:#7A4F00"' : '') + '>' + E(r.value) + '</span>';
    }).join('') + '</div>'));
    var tr = (c.track || []).slice(-1)[0];
    function tcell(k) {
      var v = tr && tr['x' + k];
      return '<div><span>D+' + k + '</span><span class="' + SE.cls(v) + '">' + (v == null ? '대기' : SE.pp(v)) + '</span></div>';
    }
    side.push(section('발굴 후 추적', '<div class="track">' + tcell(1) + tcell(5) + tcell(20) + '</div><p class="sub">' +
      (tr ? E(tr.date) + ' 발굴 · 같은 기간 유동 종목 평균 대비 초과수익. ' : '') + '실패한 종목도 지우지 않고 그대로 기록합니다.</p>'));

    h.push('<div class="cols"><div class="col-main">' + main.join('') + '</div><div class="col-side">' + side.join('') + '</div></div>');
    app.innerHTML = h.join('');
    timeline(c.timeline);
  }

  function timeline(all) {
    var KINDS = ['전체', '공시', '기사', '리포트', '가격·수급'];
    var state = { more: false, kind: '전체' };
    var keyCount = all.filter(function (x) { return x.key; }).length;
    var tl = document.getElementById('timeline'), filters = document.getElementById('tlFilters');
    var btn = document.getElementById('tlMore'), cnt = document.getElementById('tlCount');
    KINDS.forEach(function (k) {
      var n = k === '전체' ? all.length : all.filter(function (x) { return x.kind === k; }).length;
      if (!n && k !== '전체') return;
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'fbtn'; b.dataset.kind = k; b.textContent = k + ' ' + n;
      b.addEventListener('click', function () { state.kind = k; draw(); });
      filters.appendChild(b);
    });
    btn.addEventListener('click', function () { state.more = !state.more; state.kind = '전체'; draw(); });
    function draw() {
      var shown = state.more ? all.filter(function (x) { return state.kind === '전체' || x.kind === state.kind; })
        : all.filter(function (x) { return x.key; }).slice(0, 8);
      if (!state.more && !shown.length) shown = all.slice(0, 5);
      tl.innerHTML = shown.length ? shown.map(function (x) {
        var tags = x.tags.map(function (t) { return '<span class="tag ' + (TAGCLS[t] || '') + '">' + E(t) + '</span>'; }).join('');
        var title = x.url ? '<a class="title" href="' + E(x.url) + '" target="_blank" rel="noopener noreferrer">' + E(x.title) + '</a>' : '<span class="title">' + E(x.title) + '</span>';
        return '<li><span class="when">' + E(x.time) + '</span><div class="what"><div class="tags">' + tags + '</div>' + title +
          (x.note ? '<span class="note">' + E(x.note) + '</span>' : '') + '</div></li>';
      }).join('') : '<li><span class="note">최근 45일 공시·뉴스·리포트가 없습니다.</span></li>';
      filters.hidden = !state.more;
      Array.prototype.forEach.call(filters.children, function (b) { b.setAttribute('aria-pressed', b.dataset.kind === state.kind ? 'true' : 'false'); });
      var hidden = all.length - Math.min(keyCount, 8);
      btn.hidden = all.length <= shown.length && !state.more;
      btn.setAttribute('aria-expanded', state.more ? 'true' : 'false');
      btn.textContent = state.more ? '핵심만 보기 ▴' : '재료 ' + Math.max(hidden, 0) + '건 더 보기 ▾';
      cnt.textContent = state.more ? '전체 ' + all.length + '건' : '핵심 ' + shown.length + '건 · 전체 ' + all.length + '건';
    }
    draw();
  }

  SE.load().then(function (D) {
    var c = code && D.cards[code];
    if (!c) {
      app.innerHTML = '<div class="empty">이 날짜에 해당 종목 카드가 없습니다. <a href="./' + SE.q() + '">오늘의 발굴로 돌아가기</a></div>';
      return;
    }
    render(D, c);
  }).catch(function (e) {
    app.innerHTML = '<div class="empty">데이터를 불러오지 못했습니다 (' + E(e.message) + ').</div>';
  });
})();
