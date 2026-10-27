// 오늘의 발굴 목록: 분류 탭(전체·스윙·단타·관찰·제외)
(function () {
  var BADGE = { '스윙': 'b-swing', '단타': 'b-day', '관찰': 'b-watch', '제외': 'b-out' };
  var all = [
    { name: 'A전자', sector: '2차전지 장비', kind: '스윙', thesis: '40일 외인·기관 매집 종목이 52주 신고가 돌파 (계기: ESS 공급계약) · 경고등 꺼짐', material: '수주·계약(설명용)', flow: '40일 상위 18% · 경고 없음', match: '3/4', chg: '+2.8%', href: 'card.html' },
    { name: 'B중공업', sector: '조선', kind: '스윙', thesis: '3분기 실적 컨센서스 상회, 발표일 +6.2% — 대형주 실적 호재는 3일 초과 +0.57% 이어진 패턴', material: '실적', flow: '40일 상위 9% · 경고 없음', match: '4/4', chg: '+1.8%' },
    { name: 'C반도체', sector: 'HBM 부품', kind: '단타', thesis: '거래대금 평소 6배, 종가 = 고가 마감 — 종베 선별 1순위 조건 충족 (다음날 시가 매도)', material: '테마', flow: '당일 급유입', match: '2/4', chg: '+12.4%' },
    { name: 'G화학', sector: '수소', kind: '관찰', thesis: '오늘 첫 급등 +7% — 첫 급등 추격은 20일 −0.41%p, 사흘 수급으로 경고등 확인 전엔 보류', material: '정책', flow: '확인 중 (D+1~3)', match: '1/4', chg: '+7.0%' },
    { name: 'D소재', sector: '원전', kind: '제외', thesis: '급등 뒤 사흘, 가격은 버티는데 외인·기관은 매도 — 개인이 받치는 경고등 (과거 20일 −0.91%p)', material: '정책', flow: '경고: 개인이 받침', match: '0/4', chg: '+0.4%' },
    { name: 'E바이오', sector: '신약', kind: '제외', thesis: '장 마감 뒤 유상증자 결정 — 유증·CB 공시 뒤엔 다음날 장중 약세가 일반적', material: '유상증자', flow: '—', match: '0/4', chg: '−2.2%' },
    { name: 'F로보틱스', sector: '로봇', kind: '제외', thesis: '실적 쇼크로 −7% — 실적 악재 낙폭 매수는 3일 초과 −0.9%, 매수 금지', material: '실적 악재', flow: '외+기 순매도', match: '0/4', chg: '−7.0%' }
  ];
  var TABS = ['전체', '스윙', '단타', '관찰', '제외'];
  var tab = '전체';
  var tabsEl = document.getElementById('tabs');
  var listEl = document.getElementById('list');

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  TABS.forEach(function (t) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'fbtn lg';
    b.setAttribute('role', 'tab');
    b.dataset.tab = t;
    var cnt = t === '전체' ? all.length : all.filter(function (r) { return r.kind === t; }).length;
    b.textContent = t + ' ' + cnt;
    b.addEventListener('click', function () { tab = t; render(); });
    tabsEl.appendChild(b);
  });

  function render() {
    Array.prototype.forEach.call(tabsEl.children, function (b) { b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false'); });
    var rows = tab === '전체' ? all : all.filter(function (r) { return r.kind === tab; });
    listEl.innerHTML = rows.map(function (r) {
      var tag = r.href ? 'a' : 'div';
      var attr = r.href ? ' href="' + r.href + '"' : ' title="상세 카드는 A전자만 예시로 있습니다"';
      return '<' + tag + ' class="item"' + attr + '>' +
        '<div class="nm"><b>' + esc(r.name) + '</b><span>' + esc(r.sector) + '</span></div>' +
        '<span class="badge ' + BADGE[r.kind] + '">' + esc(r.kind) + '</span>' +
        '<div class="mid"><span>' + esc(r.thesis) + '</span><div class="tags">' +
        '<span class="tag">재료 · ' + esc(r.material) + '</span>' +
        '<span class="tag">수급 · ' + esc(r.flow) + '</span>' +
        '<span class="tag">근거 일치 ' + esc(r.match) + '</span></div></div>' +
        '<span class="pct ' + (r.chg.charAt(0) === '+' ? 'up' : 'down') + '">' + esc(r.chg) + '</span>' +
        '</' + tag + '>';
    }).join('');
  }
  render();
})();
