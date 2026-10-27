// 오늘의 발굴 목록 — data/latest.json (또는 ?date= 의 archive) 를 읽어 그림
(function () {
  var E = SE.esc;
  var BADGE = { '스윙': 'b-swing', '관찰': 'b-watch', '제외': 'b-out' };
  var TABS = ['전체', '스윙', '관찰', '제외'];
  var tab = SE.params.get('tab') || '전체';
  var D;

  function funnelHTML(f, n) {
    var steps = [
      [f.liquid, '유동 종목 (거래대금 10억↑)'],
      [f.newhigh, '52주 신고가'],
      [f.trend_flow + f.angle, '스윙 규칙 신호 (오늘)'],
      [n['스윙'] + n['관찰'] + n['제외'], '근거 카드']
    ];
    var arrow = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A90A0" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
    return steps.map(function (s, i) {
      return '<div class="step' + (i === steps.length - 1 ? ' last' : '') + '"><b>' + Number(s[0]).toLocaleString('ko-KR') + '</b><span>' + E(s[1]) + '</span></div>';
    }).join(arrow) + '<span class="why">오늘 첫 급등 ' + f.pops + '종목 · 스윙 ' + n['스윙'] + ' · 관찰 ' + n['관찰'] + ' · 제외 ' + n['제외'] + '</span>';
  }

  function renderTabs() {
    var el = document.getElementById('tabs');
    el.innerHTML = '';
    TABS.forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'fbtn lg';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', t === tab ? 'true' : 'false');
      var cnt = t === '전체' ? D.items.length : D.counts[t] || 0;
      b.textContent = t + ' ' + cnt;
      b.addEventListener('click', function () { tab = t; renderTabs(); renderList(); });
      el.appendChild(b);
    });
  }

  function renderList() {
    var rows = tab === '전체' ? D.items : D.items.filter(function (r) { return r.cat === tab; });
    var el = document.getElementById('list');
    if (!rows.length) {
      var msg = tab === '스윙'
        ? '오늘은 검증된 스윙 조건을 모두 만족한 종목이 없습니다. 지수가 60일선 아래인 약세장에선 신호가 거의 나오지 않는 것이 정상입니다.'
        : '해당 종목이 없습니다.';
      el.innerHTML = '<div class="empty">' + E(msg) + '</div>';
      return;
    }
    el.innerHTML = rows.map(function (r) {
      return '<a class="item" href="card.html' + SE.q({ code: r.code }) + '">' +
        '<div class="nm"><b>' + E(r.name) + '</b><span>' + E(r.sector || r.market) + '</span></div>' +
        '<span class="badge ' + BADGE[r.cat] + '">' + E(r.cat) + '</span>' +
        '<div class="mid"><span>' + E(r.thesis) + '</span><div class="tags">' +
        '<span class="tag">재료 · ' + E(r.material) + '</span>' +
        '<span class="tag">수급 · ' + E(r.flow) + '</span>' +
        '<span class="tag">근거 일치 ' + r.match + '/4</span></div></div>' +
        '<span class="pct ' + SE.cls(r.chg) + '">' + SE.pct(r.chg) + '<small>' + SE.won(r.close) + '</small></span>' +
        '</a>';
    }).join('');
  }

  function renderTrack() {
    var s = D.track.summary, el = document.getElementById('trackSum');
    el.innerHTML = ['스윙', '관찰', '제외'].map(function (c) {
      var x = s[c] || { n: 0 };
      var v = x.n5 ? 'D+5 ' + SE.pp(x.x5) + ' (' + x.n5 + '건)' + (x.n20 ? ' · D+20 ' + SE.pp(x.x20) + ' (' + x.n20 + '건)' : '') : '아직 결과 없음';
      return '<div class="stat"><span>' + c + ' 누적 ' + x.n + '건</span><span>' + v + '</span></div>';
    }).join('');
    var rows = (D.track.recent || []).slice().reverse().slice(0, 15);
    var t = document.getElementById('trackTable');
    if (!rows.length) {
      t.innerHTML = '<caption class="sub">기록이 쌓이는 중입니다. 다음 거래일부터 D+1 결과가 채워집니다.</caption>';
      return;
    }
    t.innerHTML = '<thead><tr><th>발굴일</th><th>종목</th><th>분류</th><th>D+1</th><th>D+5</th><th>D+20</th></tr></thead><tbody>' +
      rows.map(function (r) {
        function c(k) { var v = r['x' + k]; return '<td class="mono ' + SE.cls(v) + '">' + (v == null ? '대기' : SE.pp(v)) + '</td>'; }
        return '<tr><td class="mono">' + E(r.date.slice(5)) + '</td><td>' + E(r.name) + '</td><td>' + E(r.cat) + '</td>' + c(1) + c(5) + c(20) + '</tr>';
      }).join('') + '</tbody>';
  }

  function renderDates(list) {
    var sel = document.getElementById('dateSel');
    var cur = SE.date || D.asof;
    var opts = list.slice().reverse();
    if (opts.indexOf(cur) < 0) opts.unshift(cur);
    sel.innerHTML = opts.map(function (d) { return '<option value="' + E(d) + '"' + (d === cur ? ' selected' : '') + '>' + E(d) + '</option>'; }).join('');
    sel.addEventListener('change', function () {
      location.href = sel.value === opts[0] ? './' : './?date=' + encodeURIComponent(sel.value);
    });
  }

  SE.load().then(function (d) {
    D = d;
    document.getElementById('stamp').textContent = d.asof_label + ' · ' + d.updated + ' 갱신';
    document.getElementById('market').innerHTML = SE.marketHTML(d.market);
    document.getElementById('funnel').innerHTML = funnelHTML(d.funnel, d.counts);
    if (TABS.indexOf(tab) < 0) tab = '전체';
    renderTabs(); renderList(); renderTrack();
    return SE.archive().then(renderDates);
  }).catch(function (e) {
    document.getElementById('list').innerHTML = '<div class="empty">데이터를 불러오지 못했습니다 (' + E(e.message) + '). 잠시 뒤 다시 열어 주세요.</div>';
  });
})();
