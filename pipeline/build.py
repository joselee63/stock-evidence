"""발굴 노트 하루치 생성.  python -m pipeline.build   (FORCE=1 이면 같은 날짜도 다시 만듦)

1) 수집: data 브랜치(종가·시총·거래대금·외인/기관/개인 순매수·리포트) + 네이버(종목명·업종·지수·뉴스) + KIND(공시)
2) 분류: 검증된 규칙만 — 스윙(추세추종+40일 수급, 이평각도 돌파) · 관찰(첫 급등 확인 대기 등) · 제외(경고등·희석 공시·실적 악재)
3) 카드: 종목별 근거(체크·경고등·타임라인·과거 성적표·반대 근거·손절 계획·추적) → data/latest.json
"""
import datetime as dt
import json
import math
import os
import re
import sys
import time

import numpy as np
import pandas as pd

from . import ai, sources as SRC
from . import config as C
from .signals import Panel, classify, regime, stop_plan

KST = dt.timezone(dt.timedelta(hours=9))
WD = "월화수목금토일"


def log(*a):
    print(*a, flush=True)


def num(x, nd=None):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return round(x, nd) if nd is not None else x


def eok(x):
    """원 → 억원 (정수)"""
    x = num(x)
    return None if x is None else int(round(x / 1e8))


def fmt_eok(x):
    v = eok(x)
    return "—" if v is None else f"{v:+,}억".replace("-", "−")


def ddisp(d):
    return f"{d.month}/{d.day}"


# ---------------------------------------------------------------- 공시 시간창
def recent_window(rows, t_day, prev_day):
    """기준일 공시 + 전 거래일 장 마감(15:30) 뒤 공시"""
    out = {}
    for r in rows:
        if r.get("corr"):
            continue
        ts = pd.Timestamp(r["time"])
        ok = ts.normalize() == t_day or (ts.normalize() == prev_day and ts.hour * 60 + ts.minute >= 930) \
            or (prev_day < ts.normalize() < t_day)
        if ok:
            code = r["kind_code"] + "0"
            out.setdefault(code, r)
    return out


# ---------------------------------------------------------------- 타임라인
ROUTINE = re.compile(r"가격제한폭|발행결과|증권신고서|투자설명서|기재정정|주주명부|기준일|대량보유|임원ㆍ주요주주|"
                     r"특정증권등|자기주식처분결과|주식등의대량|정정")
WARN_DISC = re.compile(r"투자주의|투자경고|투자위험|단기과열|매매거래정지|불성실공시")
DIL = re.compile(r"유상증자결정|전환사채권발행결정|신주인수권부사채권발행결정|교환사채권발행결정")


def build_timeline(code, P, disc, news, reps, ev_rows, t_day, name=""):
    t_day = pd.Timestamp(t_day)
    items = []
    key_name = name.replace(" ", "")
    # 종목 뉴스 목록엔 시황 기사도 섞여 있음 → 제목·요약에 종목명이 있는 기사만
    news = [n for n in news if not key_name or key_name in (n["title"] + n["body"]).replace(" ", "")]
    for r in disc:
        ts = pd.Timestamp(r["time"])
        if ts < t_day - pd.Timedelta(days=45):
            continue
        tags = ["공시"]
        m = ai.material_of(r["title"])
        if m:
            tags.append(m)
        if WARN_DISC.search(r["title"]):
            tags.append("시장 경고")
        if ts.hour * 60 + ts.minute >= 930 or ts.hour < 9:
            tags.append("장 마감 뒤" if ts.hour >= 15 else "장 시작 전")
        items.append(dict(ts=ts, kind="공시", tags=tags, title=r["title"], url=SRC.kind_url(r["rcp"]),
                          key=not ROUTINE.search(r["title"])))
    for n in news:
        ts = pd.Timestamp(dt.datetime.strptime(n["time"], "%Y%m%d%H%M"))
        if ts < t_day - pd.Timedelta(days=45):
            continue
        tags = ["기사"] + ([f"{n['count']}건 묶음"] if n["count"] > 1 else []) + ([n["office"]] if n["office"] else [])
        m = ai.material_of(n["title"])
        if m:
            tags.insert(1, m)
        items.append(dict(ts=ts, kind="기사", tags=tags, title=n["title"], url=n["url"], key=bool(m)))
    for _, r in reps.iterrows():
        tp = r.get("tp")
        tail = f" — 목표가 {int(float(tp)):,}원" if isinstance(tp, str) and tp.replace(".", "").isdigit() and float(tp) > 0 else ""
        op = f" · {r['op']}" if isinstance(r.get("op"), str) and r["op"] else ""
        items.append(dict(ts=r["date"] + pd.Timedelta(hours=8), kind="리포트", tags=["리포트", str(r.get("firm") or "")],
                          title=f"{r['summary'] if isinstance(r.get('summary'), str) else r['title']}{tail}{op}", url="", key=True))
    for e in ev_rows:
        items.append(dict(ts=e["ts"], kind="가격·수급", tags=["가격·수급"] + e.get("tags", []), title=e["title"],
                          url="", key=True, note=e.get("note", "")))
    items.sort(key=lambda x: x["ts"], reverse=True)
    out = []
    for x in items:
        ts = x["ts"]
        tdisp = f"{ts.month}/{ts.day}" + ("" if (ts.hour == 0 and ts.minute == 0) or x["kind"] in ("가격·수급", "리포트")
                                         else f" {ts.hour:02d}:{ts.minute:02d}")
        out.append(dict(time=tdisp, date=ts.strftime("%Y-%m-%d"), kind=x["kind"], tags=[t for t in x["tags"] if t],
                        title=x["title"], url=x["url"], key=bool(x["key"]), note=x.get("note", "")))
    return out


def price_events(code, P, t, d):
    """최근 30거래일 가격·수급 사건 (52주 신고가, 첫 급등, 신호일)"""
    c = P.c[code]
    ev = []
    lo = max(0, t - 30)
    nh = (c >= P.hi252[code]).iloc[lo:t + 1]
    days = list(nh[nh].index)
    if days:
        first, last = days[0], days[-1]
        ev.append(dict(ts=last, tags=["52주 신고가"], title=f"52주 신고가 {int(c[last]):,}원 (최근 30일 중 {len(days)}일)"))
        if first != last:
            ev.append(dict(ts=first, tags=["52주 신고가"], title=f"52주 신고가 첫 돌파 {int(c[first]):,}원"))
    pop = d.get("pop")
    if pop:
        tags = ["첫 급등"]
        note = ""
        if pop["k"] == 3:
            tags.append("D+3 확인")
            note = (f"급등 뒤 3일 외+기 {fmt_eok(pop.get('s3f'))} · 가격 {'버팀' if pop.get('hold') else '밀림'}")
        ev.append(dict(ts=pop["day"], tags=tags,
                       title=f"{pop['ret'] * 100:+.1f}% 첫 급등 · 그날 외+기 {fmt_eok(pop['fD'])} / 개인 {fmt_eok(pop['iD'])}", note=note))
    i40 = t - C.FLOW_DAYS
    if i40 > 0:
        s = P.fpi[code].iloc[i40:t].sum()
        ev.append(dict(ts=P.dates[i40], tags=["40일 수급"],
                       title=f"외+기 40일 누적 순매수 {fmt_eok(s)} — 시총 대비 상위 {pct_top(P.f40rk[code].iloc[t])}",
                       note="매수 근거는 급등 뒤가 아니라 급등 전부터 쌓인 수급"))
    return ev


def pct_top(rk):
    rk = num(rk)
    return "—" if rk is None else f"{max(1, round((1 - rk) * 100))}%"


# ---------------------------------------------------------------- 카드
CAT_ORDER = {"스윙": 0, "관찰": 1, "제외": 2}


def make_card(code, d, P, t, names, sect, reg, nq, research, history_track):
    c = P.c[code]
    close, chg = float(c.iloc[t]), float(P.day[code].iloc[t])
    sday = d.get("signal_day")
    si = P.dates.get_loc(sday) if sday is not None else t           # 거래량 배수는 신호일 기준
    vr = num(P.v[code].iloc[si] / P.v20[code].iloc[si - 1], 1) if si > 0 else None
    rk = num(P.f40rk[code].iloc[t])
    score = num(P.angle[code].iloc[t])
    m60, hi = num(P.m60[code].iloc[t]), num(P.hi252[code].iloc[t])
    pop = d.get("pop")
    asof = pd.Timestamp(P.dates[t])

    # 경고등
    def light(key, label, sub, state):
        return dict(key=key, label=label, sub=sub, state=state)
    lights = []
    if pop:
        indiv_only = pop["fD"] <= 0 and pop["iD"] > 0
        if pop["k"] == 3:
            hs = "on" if (pop.get("hold") and pop.get("s3f", 1) <= 0) else "off"
            s3 = "on" if pop.get("s3f", 1) <= 0 else "off"
        else:
            hs = s3 = "wait"
        lights += [
            light("w_hold_sell", "가격은 버티는데 외인·기관은 매도 (개인이 받침)", C.BASE["w_hold_sell"][1], hs),
            light("w_indiv", "급등 당일 개인만 순매수", C.BASE["w_indiv"][1] + f" · 그날 외+기 {fmt_eok(pop['fD'])}",
                  "on" if indiv_only else "off"),
            light("w_after", "급등 뒤 3일 외+기 순매도", "과거 20일 −0.79%p (하위 1/3 기준)", s3),
        ]
    else:
        lights.append(light("none", "최근 4거래일 안에 첫 급등 없음", "급등 뒤 경고등은 해당 사항 없음", "na"))
    flow_pass = rk is not None and rk >= C.FLOW_TOP
    lights.append(light("pass", "추세추종 필터: 40일 외+기 순매수 ÷ 시총 상위 30%",
                        "급등 전부터 쌓인 수급 · 매매당 +0.42% → +0.71%", "pass" if flow_pass else "fail"))
    any_on = any(x["state"] == "on" for x in lights)

    # 4가지 체크
    above = m60 is not None and close > m60
    m60up = bool(P.m60[code].iloc[t] > P.m60[code].iloc[t - 10]) if t >= 10 else False
    newhigh = hi is not None and close >= hi
    gap_hi = None if hi is None else close / hi - 1
    trend_ok = above and m60up and (newhigh or (gap_hi is not None and gap_hi > -0.05))
    checks = [
        dict(name="추세", status="ok" if trend_ok else ("partial" if above else "no"),
             text=" · ".join([("60일선 위" if above else "60일선 아래") + ("·상승" if m60up else ""),
                              "52주 신고가" if newhigh else (f"52주 신고가까지 {gap_hi * 100:.0f}%" if gap_hi is not None else "52주 고가 없음"),
                              f"거래량 평소 {vr}배" if vr else "거래량 —"])),
        dict(name="수급", status="no" if any_on else ("ok" if flow_pass else "partial"),
             text=("경고등 켜짐" if any_on else "경고등 꺼짐") + f" · 40일 외+기 순매수/시총 상위 {pct_top(rk)}"),
        dict(name="차트", status="ok" if (score or 0) >= C.ANGLE_THR else ("partial" if (score or 0) >= 0.5 else "no"),
             text=f"이평각도 {round((score or 0) * 100)}점" + (" 돌파" if "angle" in d["routes"] or "angle_weak" in d["routes"] else "")
             + f" · 20일선 {'위' if close > (num(P.m20[code].iloc[t]) or 9e18) else '아래'}"),
        dict(name="시황", status="ok" if reg["both60"] else ("partial" if (reg["코스피"]["above60"] or reg["코스닥"]["above60"]) else "no"),
             text=f"코스피 60일선 {'위' if reg['코스피']['above60'] else '아래'} · 코스닥 60일선 {'위' if reg['코스닥']['above60'] else '아래'}"
             + (f" / 나스닥 선물 {nq['chg'] * 100:+.1f}%" if nq else "")),
    ]
    match = sum(1 for x in checks if x["status"] == "ok")

    # 가격·수급 차트 데이터
    lo = max(0, t - 59)
    seg = c.iloc[lo:t + 1]
    m20 = P.m20[code].iloc[lo:t + 1]
    mark = None
    md = d.get("signal_day") or (pop["day"] if pop else None)
    if md is not None and md in seg.index:
        mark = int(list(seg.index).index(md))
    price = dict(dates=[x.strftime("%m/%d") for x in seg.index], close=[num(x, 2) for x in seg],
                 ma20=[num(x, 2) for x in m20], mark=mark,
                 mark_label=(f"{ddisp(md)} " + ("신호일" if d.get("signal_day") is not None else "첫 급등")) if md is not None else "")
    f10 = []
    for i in range(max(0, t - 9), t + 1):
        f10.append(dict(d=ddisp(P.dates[i]), fpi=eok(P.fpi[code].iloc[i]), ind=eok(P.ind[code].iloc[i])))
    stats = [
        dict(label=f"기준일 ({ddisp(asof)})", value=f"외+기 {fmt_eok(P.fpi[code].iloc[t])} / 개인 {fmt_eok(P.ind[code].iloc[t])}"),
        dict(label="최근 5일 합", value=f"외+기 {fmt_eok(P.fpi[code].iloc[t - 4:t + 1].sum())} / 개인 {fmt_eok(P.ind[code].iloc[t - 4:t + 1].sum())}"),
        dict(label="40일 외+기 순매수 ÷ 시총", value=f"상위 {pct_top(rk)} (기준 30%)"),
    ]

    # 타임라인
    r = research.get(code, {})
    reps = r.get("reports", pd.DataFrame())
    timeline = build_timeline(code, P, r.get("disc", []), r.get("news", []), reps, price_events(code, P, t, d), asof,
                              name=names.loc[code, "name"])

    # 과거 성적표
    base_buy = [dict(title=C.BASE[k][0], text=C.BASE[k][1]) for k in d["routes"] if k in ("trend_flow", "angle", "angle_weak")]
    base_out = [dict(title=C.BASE[k][0], text=C.BASE[k][1]) for k in d["warns"]]
    ref_keys = ["first_pop", "handoff", "news"]
    if any(ai.material_of(x["title"]) == "수주·공급계약" for x in timeline if x["kind"] == "공시"):
        ref_keys.insert(2, "supply")
    base_ref = [dict(title=C.BASE[k][0], text=C.BASE[k][1]) for k in ref_keys if k not in d["warns"]]

    # 반대 근거 (규칙)
    counter = []
    if pop and pop["k"] <= 3 and d["cat"] != "제외":
        counter.append("최근 첫 급등이 있어 ‘첫 급등 따라 사기’ 평균(20일 −0.41%p)을 안고 시작함")
    if "angle" in d["routes"] or "angle_weak" in d["routes"]:
        counter.append("이평각도 패턴 승률은 36% — 대부분은 손절, 소수의 큰 수익이 평균을 만듦")
    if not reg["both60"]:
        counter.append("두 지수 중 하나 이상이 60일선 아래 — 신고가 매수 성과가 약해지는 장")
    if nq and abs(nq["chg"]) >= 0.005:
        counter.append(f"나스닥 선물 {nq['chg'] * 100:+.1f}% (±0.5% 경고선 넘음, {nq['at']} 기준)")
    if chg >= 0.15:
        counter.append(f"기준일 {chg * 100:+.1f}% 급등 — 다음날 시가 변동이 큼")
    if not flow_pass and d["cat"] != "제외":
        counter.append("40일 외+기 수급이 상위 30% 밖")

    # 리스크
    disc = r.get("disc", [])
    dil1y = [x for x in disc if DIL.search(x["title"])]
    warn30 = [x for x in disc if WARN_DISC.search(x["title"]) and pd.Timestamp(x["time"]) >= asof - pd.Timedelta(days=30)]
    risk = [
        dict(label="최근 1년 유증·CB·BW", value=f"{len(dil1y)}건" + (f" (최근 {dil1y[0]['time'][:10]})" if dil1y else ""), warn=bool(dil1y)),
        dict(label="최근 30일 시장 경고 공시", value=f"{len(warn30)}건" + (f" ({warn30[0]['title'][:18]})" if warn30 else ""), warn=bool(warn30)),
        dict(label="시가총액", value=f"{eok(P.mc[code].iloc[t]):,}억" if eok(P.mc[code].iloc[t]) else "—", warn=False),
        dict(label="20일 평균 거래대금", value=f"{eok(P.tv20[code].iloc[t]):,}억" if eok(P.tv20[code].iloc[t]) is not None else "—", warn=False),
    ]
    sp = stop_plan(num(P.sd60[code].iloc[t]))
    plan = None
    if sp:
        plan = dict(stop=round(sp["stop"] * 100, 1), stop_price=int(close * (1 - sp["stop"])), weight=round(sp["weight"] * 100, 1),
                    take=round(sp["take"] * 100, 1), take_price=int(close * (1 + sp["take"])), trail=round(sp["trail"] * 100, 1))

    nm = names.loc[code]
    card = dict(code=code, name=nm["name"], market=nm["market"], sector=sect.get(code, ""), cat=d["cat"], routes=d["routes"],
                warns=d["warns"], notes=d["notes"], asof=asof.strftime("%Y-%m-%d"),
                signal_day=d["signal_day"].strftime("%Y-%m-%d") if d.get("signal_day") is not None else None,
                close=int(round(close)), chg=round(chg, 4), mcap_eok=eok(P.mc[code].iloc[t]),
                value_eok=eok(P.val[code].iloc[t]), checks=checks, match=match, lights=lights, price=price,
                flows=f10, flow_stats=stats, timeline=timeline,
                base=dict(buy=base_buy, out=base_out, ref=base_ref), counter=counter, risk=risk, plan=plan,
                track=history_track.get(code, []))
    card["thesis"] = thesis(card, d, P, t, vr, rk, score)
    return card


def thesis(card, d, P, t, vr, rk, score):
    mt = next((ai.material_of(x["title"]) for x in card["timeline"] if x["kind"] in ("공시", "기사", "리포트")
               and ai.material_of(x["title"])), None)
    mat = f" 최근 재료는 ‘{mt}’ — 오른 이유일 뿐 매수 근거로 세지 않습니다." if mt else ""
    pop = d.get("pop")
    sd = d.get("signal_day")
    if d["cat"] == "제외":
        w = d["warns"][0] if d["warns"] else ""
        if w == "w_hold_sell":
            return (f"{ddisp(pop['day'])} 첫 급등 뒤 사흘 동안 가격은 버텼지만 외인·기관은 {fmt_eok(pop.get('s3f'))} 팔았습니다. "
                    "개인이 받치는 패턴으로, 과거 20일 성과가 시장보다 −0.91%p였습니다.")
        if w == "w_indiv":
            return (f"{ddisp(pop['day'])} {pop['ret'] * 100:+.1f}% 급등한 날 개인만 순매수했습니다(외+기 {fmt_eok(pop['fD'])}). "
                    "과거 20일 성과가 시장보다 −0.64%p였고, 이후 외인·기관이 받아가도 회복되지 않았습니다.")
        if w == "dilution":
            return f"유상증자·사채 발행 결정 공시({d['disc']['title'][:30]}) — 공시 다음날 장중 약세가 일반적이라 제외합니다."
        if w == "earn_bad":
            return (f"실적 공시 뒤 {card['chg'] * 100:+.1f}% 하락한 대형주 — 실적 악재 낙폭은 3일간 시장보다 −0.9% 더 빠졌습니다. "
                    "매수 금지 구간입니다.")
        return "경고 신호가 있어 제외합니다."
    if "trend_flow" in d["routes"]:
        s = (f"40일 동안 외인·기관이 시총 대비 상위 {pct_top(rk)} 수준으로 모아 온 종목이 "
             f"{ddisp(sd)} 52주 신고가를 거래량 평소 {vr or '2+'}배로 돌파했습니다.")
        if d["cat"] == "관찰":
            s += " 다만 코스피가 60일선 아래라 시장 필터는 미충족입니다."
        return s + mat
    if "angle" in d["routes"] or "angle_weak" in d["routes"]:
        s = (f"60일선 위에서 오르던 주도 종목이 눌림 뒤 {ddisp(sd)} 이평각도 {round((score or 0) * 100)}점으로 다시 올라섰습니다.")
        if "angle_weak" in d["routes"]:
            s += " 두 지수 중 하나가 60일선 아래라 검증 조건은 일부만 충족합니다."
        return s + mat
    if "trend_noflow" in d["routes"]:
        return f"52주 신고가 돌파는 맞지만 40일 외+기 순매수가 시총 대비 상위 {pct_top(rk)}로 수급 필터(상위 30%) 밖입니다." + mat
    if pop:
        return (f"{ddisp(pop['day'])} 첫 급등 {pop['ret'] * 100:+.1f}%. 첫 급등을 바로 따라 사면 20일간 시장보다 −0.41%p였고, "
                f"급등 뒤 사흘(D+3) 수급으로 경고등을 확인하기 전까지는 근거가 없습니다." + mat)
    return mat.strip() or "—"


# ---------------------------------------------------------------- 추적
def track_history(hist, P, t):
    """지난 후보의 기준일 종가 대비 D+1·D+5·D+20 수익과 같은 기간 유동 종목 평균 대비 초과"""
    di = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(P.dates)}
    liq = P.liq
    per_code, rows = {}, []
    for h in hist:
        i = di.get(h["date"])
        code = h["code"]
        if i is None or code not in P.c.columns:
            continue
        p0 = P.c[code].iloc[i]
        rec = dict(date=h["date"], cat=h["cat"])
        for k in (1, 5, 20):
            j = i + k
            if j > t:
                rec[f"d{k}"] = None
                continue
            r = P.c[code].iloc[j] / p0 - 1
            u = (P.c.iloc[j] / P.c.iloc[i] - 1)[liq.iloc[i]].mean()
            rec[f"d{k}"] = num(r, 4)
            rec[f"x{k}"] = num(r - u, 4)
        per_code.setdefault(code, []).append(rec)
        rows.append(dict(rec, code=code, name=h["name"]))
    summ = {}
    for cat in ("스윙", "관찰", "제외"):
        sub = [x for x in rows if x["cat"] == cat]
        s = dict(n=len(sub))
        for k in (1, 5, 20):
            xs = [x[f"x{k}"] for x in sub if x.get(f"x{k}") is not None]
            s[f"x{k}"] = num(np.mean(xs), 4) if xs else None
            s[f"n{k}"] = len(xs)
        summ[cat] = s
    return per_code, summ, rows


# ---------------------------------------------------------------- 메인
def main():
    t0 = time.time()
    C.DATA_OUT.mkdir(parents=True, exist_ok=True)
    log("1) 종목 목록·업종")
    names = SRC.listing()
    log(f"   보통주 {len(names):,}")
    log("2) data 브랜치 종가·시총·수급")
    cap = SRC.load_alpha("cap", C.MONTHS_BACK)
    flows = SRC.load_alpha("flows", C.MONTHS_BACK)
    last = min(cap.date.max(), flows.date.max())
    cap, flows = cap[cap.date <= last], flows[flows.date <= last]
    asof = last.strftime("%Y-%m-%d")
    log(f"   기준일 {asof} (종가 {cap.date.max():%m/%d} · 수급 {flows.date.max():%m/%d})")
    latest_f = C.DATA_OUT / "latest.json"
    if latest_f.exists() and not os.environ.get("FORCE"):
        old = json.loads(latest_f.read_text(encoding="utf-8"))
        if old.get("asof") == asof:
            log("   이미 만든 날짜 — 건너뜀 (FORCE=1 로 다시 만들기)")
            return 0
    sect = SRC.sectors()
    log(f"   업종 매핑 {len(sect):,}")
    P = Panel(cap, flows, names).derive()
    t = len(P.dates) - 1
    t_day, prev_day = P.dates[t], P.dates[t - 1]

    log("3) 지수·해외")
    start = (t_day - pd.Timedelta(days=420)).date()
    kospi, kosdaq = SRC.index_closes("KOSPI", start), SRC.index_closes("KOSDAQ", start)
    reg = regime(kospi.loc[:t_day], kosdaq.loc[:t_day], P.dates)
    nq = SRC.nasdaq_futures()
    log(f"   코스피 60일선 {'위' if reg['코스피']['above60'] else '아래'} · 코스닥 {'위' if reg['코스닥']['above60'] else '아래'} · 비중 {reg['weight']}%")

    log("4) 시장 공시 스캔 (희석·실적)")
    w0, w1 = prev_day.date(), (t_day + pd.Timedelta(days=1)).date()
    dil_rows = []
    for kw in ("유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정"):
        dil_rows += SRC.kind_report(kw, w0, w1, pages=2)
    dil = recent_window([r for r in dil_rows if "자회사" not in r["title"]], t_day, prev_day)
    earn = recent_window(SRC.kind_report("영업(잠정)실적", w0, w1, pages=3), t_day, prev_day)
    log(f"   희석 공시 {len(dil)} · 실적 공시 {len(earn)}")

    log("5) 분류")
    res, funnel = classify(P, reg, dil, earn)
    tv = P.tv20.iloc[t]
    pick = {"스윙": [], "관찰": [], "제외": []}
    for code, d in res.items():
        pick[d["cat"]].append(code)
    for k in pick:
        pick[k].sort(key=lambda x: -(num(tv.get(x)) or 0))
    pick["관찰"] = pick["관찰"][:C.MAX_WATCH]
    pick["제외"] = pick["제외"][:C.MAX_OUT]
    chosen = pick["스윙"] + pick["관찰"] + pick["제외"]
    log(f"   스윙 {len(pick['스윙'])} · 관찰 {len(pick['관찰'])} · 제외 {len(pick['제외'])}  (전체 후보 {len(res)})")

    log("6) 종목별 리서치 (공시·뉴스·리포트)")
    reports = SRC.load_reports(sorted({t_day.year - 1, t_day.year}))
    research = {}
    for i, code in enumerate(chosen):
        disc = SRC.kind_company(code, (t_day - pd.Timedelta(days=365)).date(), (t_day + pd.Timedelta(days=1)).date())
        nw = SRC.news(code)
        rp = reports[(reports.ticker == code) & (reports.date >= t_day - pd.Timedelta(days=90))].sort_values("date", ascending=False).head(8)
        research[code] = dict(disc=disc, news=nw, reports=rp)
        log(f"   [{i + 1}/{len(chosen)}] {names.loc[code, 'name']} 공시 {len(disc)} · 뉴스 {len(nw)} · 리포트 {len(rp)}")
        time.sleep(0.2)

    log("7) 추적 기록")
    hist_f = C.DATA_OUT / "history.json"
    hist = json.loads(hist_f.read_text(encoding="utf-8")) if hist_f.exists() else []
    hist = [h for h in hist if h["date"] != asof]
    for cat in ("스윙", "관찰", "제외"):
        for code in pick[cat]:
            hist.append(dict(date=asof, code=code, name=names.loc[code, "name"], cat=cat))
    per_code, summ, rows = track_history(hist, P, t)

    log("8) 카드")
    cards = {}
    for code in chosen:
        cards[code] = make_card(code, res[code], P, t, names, sect, reg, nq, research, per_code)
    targets = [cards[c] for c in pick["스윙"] + pick["관찰"]][:20]
    ai_out = ai.analyze(targets)
    for code, card in cards.items():
        card["ai"] = ai_out.get(code) or ai.rule_based(card)
        card["counter"] += [x for x in card["ai"].get("counter", []) if x not in card["counter"]]
    log(f"   AI 판독 {len(ai_out)}건 (나머지는 규칙 기반)")

    # 돈 몰린 업종: 기준일 거래대금이 20일 평균 대비 가장 많이 늘고 오른 업종
    sec = pd.Series(sect).reindex(P.c.columns)
    df = pd.DataFrame(dict(sec=sec, val=P.val.iloc[t], tv=P.tv20.iloc[t - 1], ret=P.day.iloc[t])).dropna()
    g = df.groupby("sec").agg(val=("val", "sum"), tv=("tv", "sum"), n=("val", "size"))
    g["ret"] = df.assign(w=df.val * df.ret).groupby("sec").w.sum() / g.val
    g["ratio"] = g.val / g.tv
    hot = g[(g.n >= 5) & (g.ret > 0)].sort_values("ratio", ascending=False).head(3)
    hot_list = [dict(name=k, ratio=round(float(v.ratio), 1), ret=round(float(v.ret), 4)) for k, v in hot.iterrows()]

    items = []
    for cat in ("스윙", "관찰", "제외"):
        for code in pick[cat]:
            cd = cards[code]
            items.append(dict(code=code, name=cd["name"], sector=cd["sector"], market=cd["market"], cat=cat,
                              thesis=cd["thesis"], material=cd["ai"]["material_type"].split(" (")[0],
                              flow=next(x["text"] for x in cd["checks"] if x["name"] == "수급"),
                              match=cd["match"], chg=cd["chg"], close=cd["close"]))
    now = dt.datetime.now(KST)
    out = dict(asof=asof, asof_label=f"{t_day:%Y-%m-%d} ({WD[t_day.weekday()]}) 장 마감 기준",
               updated=now.strftime("%Y-%m-%d %H:%M"), market=dict(regime=reg, nasdaq=nq, hot=hot_list),
               funnel=funnel, counts={k: len(v) for k, v in pick.items()}, items=items, cards=cards,
               track=dict(summary=summ, recent=[r for r in rows if r["date"] != asof][-40:]),
               ai_enabled=bool(ai_out))
    js = json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=lambda o: None)
    latest_f.write_text(js, encoding="utf-8")
    (C.DATA_OUT / "archive").mkdir(exist_ok=True)
    (C.DATA_OUT / "archive" / f"{asof}.json").write_text(js, encoding="utf-8")
    hist_f.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    arch = sorted(p.stem for p in (C.DATA_OUT / "archive").glob("*.json"))
    (C.DATA_OUT / "archive" / "index.json").write_text(json.dumps(arch), encoding="utf-8")
    log(f"완료 {asof} · {len(js) / 1024:.0f}KB · {time.time() - t0:.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
