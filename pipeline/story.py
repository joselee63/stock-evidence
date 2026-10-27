"""종목 소개의 앞단: ① 왜 올랐나(재료) ② 시황 속 위치(업종·테마·지수) ③ 남은 기대감(앞으로의 이벤트·목표가·반영 정도).

모두 규칙 기반. '남은 기대감' 판정은 아직 검증 전인 경험칙이라 화면에 그렇게 표시하고,
history.json 에 판정을 함께 남겨 나중에 성과로 검증한다.
"""
import re

import numpy as np
import pandas as pd

from . import ai

ROUTINE = re.compile(r"가격제한폭|발행결과|증권신고서|투자설명서|기재정정|주주명부|기준일|대량보유|임원ㆍ주요주주|특정증권등|"
                     r"자기주식처분결과|주식등의대량|정정|조회공시|풍문|증권발행실적|공매도|과열|추가상장|"
                     r"반기보고서|분기보고서|사업보고서|일괄신고|상황보고서|예고|안내공시|투자주의|투자경고|"
                     r"단기과열|매매거래정지|변경상장|주주총회소집|감사보고서|기업설명회")
EARN = re.compile(r"영업\(잠정\)실적|매출액또는손익구조")


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("배", "").replace("원", ""))
    except (TypeError, ValueError):
        return None


def _pct(x):
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:+.1f}%".replace("-", "−")


def group_stats(P, t, groups, min_n=3, days=10):
    """업종·테마별 최근 days 거래일의 하루 등락(동일가중), 5일 등락, 거래대금 배수"""
    cols = set(P.c.columns)
    rows, daily = {}, {}
    lo = max(0, t - days + 1)
    for nm, codes in groups.items():
        cs = [c for c in codes if c in cols and bool(P.liq[c].iloc[t])]
        if len(cs) < min_n:
            continue
        d = P.day[cs].iloc[lo:t + 1].mean(axis=1)
        r5 = (P.c[cs].iloc[t] / P.c[cs].iloc[t - 5] - 1).mean()
        ratio = P.val[cs].iloc[t].sum() / P.tv20[cs].iloc[t - 1].sum()
        rows[nm] = dict(n=len(cs), ret1=float(d.iloc[-1]), ret5=float(r5), ratio=float(ratio))
        daily[nm] = d
    st = pd.DataFrame(rows).T
    if len(st):
        st["rank1"] = st.ret1.rank(ascending=False).astype(int)
        st["rank_ratio"] = st.ratio.rank(ascending=False).astype(int)
    return st, pd.DataFrame(daily)


def build(code, name, d, P, t, timeline, disc, integ, sector, sect_st, sect_daily, theme_of, theme_st, theme_daily,
          theme_members, names):
    c = P.c[code]
    dates = P.dates
    asof = dates[t]
    close = float(c.iloc[t])

    # ---------------------------------------------------------- ① 왜 올랐나
    lo = max(1, t - 9)
    dr = P.day[code].iloc[lo:t + 1]
    mi = None
    if d.get("pop"):
        mi = dates.get_loc(d["pop"]["day"])
    elif dr.max() >= 0.03:
        mi = dates.get_loc(dr.idxmax())
    elif d.get("signal_day") is not None:
        mi = dates.get_loc(d["signal_day"])
    move_day = dates[mi] if mi is not None else None
    move_ret = float(P.day[code].iloc[mi]) if mi is not None else None
    since = float(close / c.iloc[mi - 1] - 1) if mi is not None and mi > 0 else None

    cand = [x for x in timeline if x["kind"] in ("공시", "기사", "리포트")]
    if move_day is not None:
        a, b = move_day - pd.Timedelta(days=6), move_day + pd.Timedelta(days=1)
        win = [x for x in cand if a <= pd.Timestamp(x["date"]) <= b]
        if not win:
            win = [x for x in cand if move_day - pd.Timedelta(days=25) <= pd.Timestamp(x["date"]) <= b]
    else:
        win = [x for x in cand if pd.Timestamp(x["date"]) >= asof - pd.Timedelta(days=14)]

    def score(x):
        m = ai.material_of(x["title"])
        s = {"공시": 3, "리포트": 2, "기사": 1}[x["kind"]] + (2 if m else 0)
        if x["kind"] == "공시" and ROUTINE.search(x["title"]):
            return 0                                     # 정기·절차 공시는 상승 이유가 아님
        return s
    win = [x for x in win if score(x) > 0]
    win.sort(key=lambda x: (score(x), x["date"], x["time"]), reverse=True)
    top = win[:3]
    mtype = next((ai.material_of(x["title"]) for x in top if ai.material_of(x["title"])), None)
    first = None
    if mtype:
        same = [x for x in cand if ai.material_of(x["title"]) == mtype]
        first = same[-1] if same else None
    fresh = None
    if first:
        fd = pd.Timestamp(first["date"])
        fresh = int((dates[: t + 1] > fd).sum())

    # ---------------------------------------------------------- ② 시황 속 위치
    ctx = dict(sector=None, theme=None, themes=[], mode=None)
    if sector and sector in sect_st.index:
        s = sect_st.loc[sector]
        ctx["sector"] = dict(name=sector, ret1=float(s.ret1), ret5=float(s.ret5), ratio=round(float(s.ratio), 1),
                             rank=int(s.rank_ratio), total=len(sect_st))
    th = [x for x in theme_of.get(code, []) if x in theme_st.index]
    if th:
        # 상승일에 가장 많이 함께 오른 테마를 대표로 (상승일이 없으면 5일 등락 기준)
        if move_day is not None:
            th.sort(key=lambda x: -(theme_daily[x].get(move_day, -9) if x in theme_daily else -9))
        else:
            th.sort(key=lambda x: -theme_st.loc[x, "ret5"])
        lead = th[0]
        s = theme_st.loc[lead]
        peers = []
        for p in theme_members.get(lead, []):
            if p != code and p in P.c.columns and p in names.index:
                r5 = P.c[p].iloc[t] / P.c[p].iloc[t - 5] - 1
                if np.isfinite(r5):
                    peers.append((float(r5), p))
        peers.sort(reverse=True)
        ctx["theme"] = dict(name=lead, ret1=float(s.ret1), ret5=float(s.ret5), rank=int(s.rank1), total=len(theme_st),
                            peers=[dict(name=names.loc[p, "name"], ret5=round(r, 4)) for r, p in peers[:3]])
        ctx["themes"] = th[:4]
    if move_day is not None and move_ret is not None and move_ret > 0:
        def peer_ret(codes):                              # 이 종목을 뺀 동료 종목들의 그날 평균
            cs = [x for x in codes if x != code and x in P.c.columns]
            if len(cs) < 2:
                return None
            v = P.day[cs].loc[move_day].mean()
            return float(v) if np.isfinite(v) else None
        need = max(0.02, move_ret * 0.35)
        tr = peer_ret(theme_members.get(th[0], [])) if th else None
        sr = sect_daily[sector].get(move_day) if sector in sect_daily else None
        if tr is not None and tr >= need:
            ctx["mode"] = f"테마 동반 — {ddisp(move_day)} {th[0]} 다른 종목 평균 {_pct(tr)}"
        elif sr is not None and np.isfinite(sr) and sr >= need:
            ctx["mode"] = f"업종 동반 — {ddisp(move_day)} {sector} 평균 {_pct(sr)}"
        else:
            ctx["mode"] = f"개별 재료 — {ddisp(move_day)} 같은 테마·업종은 함께 오르지 않음" + (f" (테마 {_pct(tr)})" if tr is not None else "")

    # ---------------------------------------------------------- ③ 남은 기대감
    ev, plus, minus = [], [], []

    def dd(x):
        return pd.Timestamp(x["time"][:10])
    recent = lambda days: [x for x in disc if dd(x) >= asof - pd.Timedelta(days=days)]

    earns = [x for x in disc if EARN.search(x["title"])]
    if earns:
        last_e = dd(earns[0])
        gap = (asof - last_e).days
        if gap <= 10:
            li = int((dates[: t + 1] < last_e).sum())
            after = close / c.iloc[li - 1] - 1 if li > 0 else None
            ev.append(dict(when=ddisp(last_e), text=f"실적 발표 직후 — 발표 뒤 주가 {_pct(after)}", tone="neutral"))
            if after is not None and after <= -0.05:
                minus.append("실적 발표 뒤 하락 — 실적 재료는 소멸 쪽")
        else:
            nxt = last_e + pd.Timedelta(days=91)
            if -5 <= (nxt - asof).days <= 45:
                ev.append(dict(when=f"{ddisp(nxt)}경", text=f"다음 분기 실적 발표 예상 (직전 {ddisp(last_e)})", tone="plus"))
                plus.append("실적 발표가 가까움 — 확인할 이벤트가 남음")
    elif asof.month in (1, 2, 4, 5, 7, 8, 10, 11):
        ev.append(dict(when="이번 시즌", text="최근 1년 잠정실적 공시 없음 — 정기보고서로 실적 확인", tone="neutral"))

    for x in recent(30):
        tt = x["title"]
        if re.search(r"자기주식취득신탁계약체결|자기주식취득결정", tt):
            ev.append(dict(when=ddisp(dd(x)), text="자사주 매입 진행 중 — 과거 신탁 공시 뒤 10일 중앙 +1.5%", tone="plus"))
            plus.append("자사주 매입 수요가 남음")
            break
    for x in recent(25):
        if re.search(r"기업설명회|\bIR\b", x["title"]):
            soon = (asof - dd(x)).days <= 7                # 안내 공시는 보통 행사 1~2주 전 → 7일 안이면 아직 남았을 가능성
            ev.append(dict(when=ddisp(dd(x)), text="IR 개최 안내 공시" + (" — 행사가 아직 남았을 수 있음 (일정은 원문 확인)" if soon else " — 이미 지났을 가능성"),
                           tone="plus" if soon else "neutral"))
            if soon:
                plus.append("IR 일정이 남았을 가능성")
            break
    for x in recent(40):
        if "무상증자결정" in x["title"]:
            ev.append(dict(when=ddisp(dd(x)), text="무상증자 — 권리락·신주 상장 일정 (과거 권리락 뒤 반납이 일반적)", tone="minus"))
            minus.append("무상증자 뒤 반납 패턴")
            break
    dil = [x for x in recent(365) if re.search(r"유상증자결정|전환사채권발행결정|신주인수권부사채권발행결정", x["title"])]
    conv = [x for x in recent(30) if re.search(r"전환청구권행사|신주인수권행사|추가상장", x["title"])]
    if conv:
        ev.append(dict(when=ddisp(dd(conv[0])), text=f"전환·추가상장 물량 출회 — 최근 30일 {len(conv)}건", tone="minus"))
        minus.append("전환 물량(오버행)이 나오는 중")
    elif dil:
        ev.append(dict(when=ddisp(dd(dil[0])), text=f"1년 안 희석 공시 {len(dil)}건 — 전환 가능 물량 확인 필요", tone="minus"))
    for x in recent(30):
        if re.search(r"합병|분할|공개매수|최대주주변경", x["title"]) and not ROUTINE.search(x["title"]):
            ev.append(dict(when=ddisp(dd(x)), text=f"지배구조 이벤트 — {x['title'][:30]}", tone="neutral"))
            break
    for x in recent(30):
        if re.search(r"임상|품목허가|FDA|기술이전", x["title"]):
            ev.append(dict(when=ddisp(dd(x)), text=f"임상·허가 관련 — {x['title'][:30]} (결과 이벤트 대기 가능)", tone="neutral"))
            break

    cons = integ.get("consensusInfo") or {}
    tgt = _num(cons.get("priceTargetMean"))
    upside = (tgt / close - 1) if tgt else None
    rec = _num(cons.get("recommMean"))
    target = dict(mean=int(tgt) if tgt else None, upside=round(upside, 4) if upside is not None else None, recomm=rec)
    if upside is not None:
        if upside >= 0.2:
            plus.append(f"목표가 평균까지 {_pct(upside)} 여력")
        elif upside < 0:
            minus.append(f"현재가가 목표가 평균({int(tgt):,}원)보다 높음")
    infos = {x["code"]: x["value"] for x in integ.get("totalInfos", [])}
    per, cper = _num(infos.get("per")), _num(infos.get("cnsPer"))
    res = integ.get("researches") or []
    rec14 = [r for r in res if r.get("wdt") and pd.Timestamp(r["wdt"]) >= asof - pd.Timedelta(days=14)]
    if len(rec14) >= 2:
        plus.append(f"최근 2주 증권사 리포트 {len(rec14)}건 — 관심이 붙는 중")

    if fresh is not None:
        if fresh <= 10:
            plus.append(f"재료 발생 {fresh}거래일 — 아직 초기")
        elif fresh > 20:
            minus.append(f"재료가 나온 지 {fresh}거래일 — 새 재료 없으면 힘이 빠지는 구간")
    elif move_day is not None and not top:
        minus.append("상승을 설명할 공시·뉴스를 못 찾음 — 수급·테마성 움직임일 수 있음")
    if since is not None:
        if since >= 0.5:
            minus.append(f"재료 뒤 이미 {_pct(since)} — 상당 부분 반영")
        elif since <= -0.05 and move_ret and move_ret > 0.05:
            minus.append(f"급등분을 반납 중 ({_pct(since)})")
    if ctx["theme"] and ctx["theme"]["ret5"] >= 0.05 and ctx["theme"]["rank"] <= 10:
        plus.append(f"{ctx['theme']['name']} 테마가 5일 {_pct(ctx['theme']['ret5'])}로 강세 (상위 {ctx['theme']['rank']}위)")
    elif ctx["theme"] and ctx["theme"]["ret5"] <= -0.05:
        minus.append(f"{ctx['theme']['name']} 테마가 5일 {_pct(ctx['theme']['ret5'])}로 약세")

    if len(minus) >= 2 or (minus and not plus):
        verdict = "소진 우려"
    elif len(plus) >= 2 and not minus:
        verdict = "기대 남음"
    elif len(plus) > len(minus):
        verdict = "기대 일부"
    else:
        verdict = "판단 보류"

    # ---------------------------------------------------------- 한 줄 요약
    if top:
        head = top[0]["title"]
        lead = f"{mtype}: " if mtype else ""
        why_line = f"{lead}{head[:70]}"
    elif ctx["mode"] and ctx["mode"].startswith("테마"):
        why_line = f"뚜렷한 공시·뉴스 없이 {ctx['theme']['name']} 테마와 함께 상승"
    else:
        why_line = "상승을 설명할 공시·뉴스를 찾지 못함"
    mv = f"{ddisp(move_day)} {_pct(move_ret)}" if move_day is not None else ""
    nxt = next((e for e in ev if e["tone"] == "plus"), None) or next((e for e in ev if e["tone"] == "minus"), None)
    summary = dict(why=why_line, move=mv,
                   ctx=(f"{ctx['theme']['name']} 테마 5일 {_pct(ctx['theme']['ret5'])}" if ctx["theme"] else
                        (f"{sector} 업종 {_pct(ctx['sector']['ret1'])}" if ctx["sector"] else "")),
                   next=(f"{nxt['when']} {nxt['text'].split(' — ')[0]}" if nxt else "예정 이벤트 없음"),
                   verdict=verdict)
    return dict(
        why=dict(line=why_line, material_type=mtype or "재료 불명", move_day=ddisp(move_day) if move_day is not None else None,
                 move_ret=move_ret, since=since, fresh=fresh, first=first["date"] if first else None,
                 items=[dict(date=x["date"], time=x["time"], kind=x["kind"], title=x["title"], url=x["url"], tags=x["tags"][:3]) for x in top]),
        context=ctx, outlook=dict(verdict=verdict, plus=plus, minus=minus, events=ev, target=target,
                                  per=dict(now=per, fwd=cper), reports14=len(rec14)),
        summary=summary)


def ddisp(d):
    return f"{d.month}/{d.day}"
