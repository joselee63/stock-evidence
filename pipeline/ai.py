"""AI 판독 — 종목별 뉴스·공시·리포트 제목을 읽고 재료를 정리 (ANTHROPIC_API_KEY 가 있을 때만).

키가 없거나 호출이 실패하면 rule_based() 로 대신한다. 매수 판단은 AI 가 하지 않는다
(분류는 검증된 규칙이 정하고, AI 는 '왜 올랐나'를 설명하는 역할만).
"""
import json
import os
import re

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "material_type": {"type": "string", "description": "재료 유형 (예: 수주·공급계약, 실적, 자사주, 유상증자·CB, 임상·허가, 정책, 테마, 업황, 재료 불명)"},
        "novelty": {"type": "string", "description": "처음 나온 재료인지, 이미 알려진 재료의 재탕인지 — 날짜 근거와 함께 한 문장"},
        "scale": {"type": "string", "description": "규모 (계약금액·매출 대비 등). 제목만으로 알 수 없으면 '제목만으론 알 수 없음'"},
        "lasting": {"type": "string", "description": "재료가 이어질 수 있는 근거 한 문장"},
        "one_off": {"type": "string", "description": "일회성으로 끝날 위험 한 문장"},
        "industry": {"type": "string", "description": "산업 맥락 한 문장"},
        "counter": {"type": "array", "items": {"type": "string"}, "description": "반대 근거 1~3개 (짧게)"},
    },
    "required": ["material_type", "novelty", "scale", "lasting", "one_off", "industry", "counter"],
    "additionalProperties": False,
}

SYSTEM = (
    "너는 한국 주식 리서치 보조다. 주어진 종목의 최근 공시·뉴스·증권사 리포트 제목만 근거로 "
    "'이 종목이 왜 움직였는지'를 정리한다. 매수·매도 권유나 목표가 제시는 하지 않는다. "
    "제목에 없는 사실을 지어내지 말고, 모르면 모른다고 쓴다. 모든 값은 한국어로 짧게 쓴다."
)


def _prompt(card):
    lines = [f"종목: {card['name']} ({card['code']}) · {card.get('market', '')} · 업종 {card.get('sector') or '미상'}",
             f"기준일: {card['asof']} · 종가 {card['close']:,} ({card['chg'] * 100:+.1f}%)", "", "[타임라인 — 최신순]"]
    for it in card["timeline"][:40]:
        lines.append(f"- {it['time']} [{it['kind']}] {it['title']}")
    return "\n".join(lines)


def analyze(cards):
    """cards: build 단계의 카드 dict 목록 → {code: ai dict}"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    try:
        import anthropic
    except ImportError:
        print("   anthropic 패키지 없음 — AI 판독 건너뜀")
        return {}
    client = anthropic.Anthropic()
    out = {}
    for card in cards:
        try:
            resp = client.beta.messages.create(
                model=MODEL,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM,
                messages=[{"role": "user", "content": _prompt(card)}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
            if resp.stop_reason != "end_turn":
                print(f"   AI {card['code']}: stop_reason={resp.stop_reason}")
                continue
            text = next((b.text for b in resp.content if b.type == "text"), "")
            out[card["code"]] = dict(json.loads(text), source="ai")
        except anthropic.RateLimitError:
            print("   AI 호출 한도 — 나머지는 규칙 기반으로")
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError, json.JSONDecodeError) as e:
            print(f"   AI {card['code']} 실패: {repr(e)[:100]}")
    return out


# ---------------------------------------------------------------- 규칙 기반 대체
TYPES = [   # 순서 = 우선순위 (앞에서 먼저 걸리면 그 유형)
    ("유상증자·CB", r"유상증자|전환사채|신주인수권부사채|교환사채"),
    ("자사주", r"자기주식|자사주|주식 ?소각"),
    ("최대주주·M&A", r"최대주주|경영권|인수|합병|매각|지분 취득|공개매수|주식양수도"),
    ("무상증자", r"무상증자"),
    ("수주·공급계약", r"공급계약|수주|납품|판매ㆍ공급"),
    ("실적", r"영업\(잠정\)실적|영업실적|실적|어닝|분기 최대|흑자전환|서프라이즈"),
    ("임상·허가", r"임상|FDA|허가|품목|기술이전|기술수출|라이선스"),
    ("신제품·기술", r"신제품|출시|개발 성공|특허|양산"),
    ("정책", r"정부|정책|규제|법안|지원책|예산"),
]


def material_of(text):
    for nm, pat in TYPES:
        if re.search(pat, text):
            return nm
    return None


def rule_based(card):
    tl = card["timeline"]
    keyed = [x for x in tl if x["kind"] in ("공시", "리포트", "기사")]
    mt, first = None, None
    for x in reversed(keyed):                        # 오래된 것부터 — 처음 등장한 재료
        m = material_of(x["title"])
        if m:
            mt, first = m, x
    latest = next((x for x in keyed if material_of(x["title"]) == mt), None) if mt else None
    return dict(
        source="rule",
        material_type=mt or "재료 불명 (최근 30일 공시·뉴스 제목에서 특정 못 함)",
        novelty=(f"{first['time'][:10]} {first['kind']}에서 처음 확인" + (f", 최근 {latest['time'][:10]}" if latest is not first else ""))
        if first else "—",
        scale="자동 분류 — 규모는 원문 확인 필요",
        lasting="—", one_off="—", industry=card.get("sector") or "—", counter=[],
    )
