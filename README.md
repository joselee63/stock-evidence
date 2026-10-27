# 발굴 노트 (stock-evidence)

뉴스·공시·리포트·수급을 모아 종목별 근거를 한 장에 보여주는 사이트입니다.
https://joselee63.github.io/stock-evidence/

## 구조

- `pipeline/` — 매일 데이터를 만드는 파이썬 코드
  - `sources.py` 수집: kr-sector-charts `data` 브랜치(종가·시총·거래대금·외인/기관/개인 순매수·한경 리포트), 네이버 증권(종목명·업종·지수·종목 뉴스), KIND(공시), 야후(나스닥 선물)
  - `signals.py` 분류: 검증된 규칙만 사용 (아래)
  - `ai.py` AI 판독: `ANTHROPIC_API_KEY` 가 있으면 Claude가 공시·뉴스·리포트 제목을 읽고 재료를 정리, 없으면 규칙 기반 분류
  - `build.py` 실행: `data/latest.json`, `data/archive/<날짜>.json`, `data/history.json`(추적) 생성
- `index.html` 오늘의 발굴 목록 · `card.html?code=` 종목 근거 카드 — 둘 다 `data/*.json` 을 읽어 그림
- `.github/workflows/update.yml` — 밤 10시~아침 9시 매시간 새 기준일 확인 → 생성 → 커밋 → Pages 반영

## 분류 규칙 (kr-sector-charts 무편향 백테스트 2015~2026)

- **스윙**: ① 60일선 위·상승 + 52주 신고가 + 거래량 2배 + 40일 외+기 순매수/시총 상위 30% (코스피 60일선 위) — 매매당 +0.71%,
  ② 주도 종목의 이평각도(5~60일선 10개, 단기 가중) 눌림 뒤 80점 돌파 (두 지수 60일선 위) — 매매당 +2.33%
- **관찰**: 첫 급등(+5%↑·거래량 3배) 뒤 D+3 수급 확인 전, 스윙 조건 일부 미충족
- **제외**: 급등 뒤 가격은 버티는데 외+기 매도(20일 −0.91%p), 급등 당일 개인만 순매수(−0.64%p), 유상증자·CB·BW 결정, 대형주 실적 악재 −5%↓
- 뉴스·공시는 ‘오른 이유’ 설명용 — 뉴스 유무로는 성적이 갈리지 않았음

## 로컬 실행

```bash
pip install -r requirements.txt
FORCE=1 python -m pipeline.build
python -m http.server 8791
```

## AI 판독 켜기 (선택)

저장소 Settings → Secrets and variables → Actions → `ANTHROPIC_API_KEY` 등록. 스윙·관찰 상위 20종목만 호출합니다.

투자 판단을 돕는 근거 정리이며 매수 권유가 아닙니다.
