"""패널 구성(분할 보정)과 검증된 규칙으로 스윙·관찰·제외 분류."""
import numpy as np
import pandas as pd

from . import config as C


class Panel:
    """dates × tickers 넓은 표 (종가·거래량은 액면분할 보정)"""

    def __init__(self, cap, flows, names):
        keep = set(names.index)
        cap = cap[cap.ticker.isin(keep)]
        flows = flows[flows.ticker.isin(keep)]
        pv = lambda df, col: df.pivot_table(index="date", columns="ticker", values=col, aggfunc="last").sort_index()
        close, vol = pv(cap, "close"), pv(cap, "volume")
        self.val, self.mc, sh = pv(cap, "value"), pv(cap, "mcap"), pv(cap, "shares")
        close = close.where(close > 0)
        # 액면분할·병합: 주식수가 크게 바뀌고 가격이 그 반대로 움직인 날 → 이전 가격을 나눠 이어 붙임
        ratio = sh / sh.shift(1)
        pr = close / close.shift(1)
        pr_r = pr * ratio
        split = ((ratio > 1.4) | (ratio < 0.7)) & (pr_r >= 0.7) & (pr_r <= 1.4)
        fac = ratio.where(split, 1.0).fillna(1.0)
        after = fac.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1.0)   # 그날 이후 분할 누적
        self.c = close / after
        self.v = vol * after
        self.dates = self.c.index
        fd = sorted(set(flows.date))
        fx = flows.assign(fpi=flows[["frg_nv", "inst_nv"]].sum(axis=1) + flows.get("frg2_nv", 0).fillna(0))
        self.fpi = pv(fx, "fpi").reindex(index=self.dates, columns=self.c.columns)
        self.ind = pv(flows, "indiv_nv").reindex(index=self.dates, columns=self.c.columns)
        have = self.dates.isin(fd)
        self.fpi.loc[have] = self.fpi.loc[have].fillna(0.0)
        self.ind.loc[have] = self.ind.loc[have].fillna(0.0)
        self.flow_last = max(fd) if fd else None
        self.names = names

    def derive(self):
        c, v = self.c, self.v
        self.day = c / c.shift(1) - 1
        self.m60 = c.rolling(60, min_periods=60).mean()
        self.m20 = c.rolling(20, min_periods=20).mean()
        self.hi252 = c.rolling(252, min_periods=252).max()
        self.v20 = v.rolling(20, min_periods=15).mean()
        self.tv20 = self.val.rolling(20, min_periods=15).mean()
        self.run_ok = c.rolling(C.RUN_MIN, min_periods=C.RUN_MIN).count() >= C.RUN_MIN
        self.run60 = c.rolling(60, min_periods=60).count() >= 60
        lr = np.log(c / c.shift(1))
        self.sd60 = lr.rolling(60, min_periods=55).std(ddof=0)
        self.liq = (self.tv20 >= C.LIQ_MIN) & self.run_ok
        # 외+기 40일 순매수 ÷ 시총 (t−1 기준) 순위
        f40 = self.fpi.rolling(C.FLOW_DAYS, min_periods=C.FLOW_DAYS).sum().shift(1) / self.mc.shift(1)
        self.f40 = f40
        self.f40rk = f40.where(self.liq).rank(axis=1, pct=True)
        # 이평각도 점수 (단기 가중, 0~1)
        s = pd.DataFrame(0.0, index=c.index, columns=c.columns)
        for p, w in zip(C.ANGLE_P, C.ANGLE_W):
            m = c.rolling(p, min_periods=p).mean()
            s += w * (m > m.shift(1)).astype(float)
        self.angle = (s / sum(C.ANGLE_W)).round(2)
        return self


def regime(idx_kospi, idx_kosdaq, dates):
    """지수 60일선·계단식 비중 (52주 신고가 전략용: 두 지수 중 낮은 쪽, 60·90·120·180·250일선 하나 깰 때마다 −20%)"""
    out = {}
    broken_max = 0
    for nm, s in (("코스피", idx_kospi), ("코스닥", idx_kosdaq)):
        s = s.reindex(s.index.union(dates)).ffill().reindex(dates)
        last = s.iloc[-1]
        mas = {n: s.rolling(n, min_periods=n).mean().iloc[-1] for n in (20, 60, 90, 120, 180, 250)}
        broken = sum(1 for n in (60, 90, 120, 180, 250) if np.isfinite(mas[n]) and last < mas[n])
        broken_max = max(broken_max, broken)
        out[nm] = dict(close=round(float(last), 2), chg=float(s.iloc[-1] / s.iloc[-2] - 1),
                       above60=bool(last > mas[60]), above20=bool(last > mas[20]), broken=broken)
    out["weight"] = 100 - 20 * broken_max
    out["both60"] = out["코스피"]["above60"] and out["코스닥"]["above60"]
    return out


def classify(P, reg, dil, earn):
    """오늘(마지막 날) 기준 후보. dil: {code: 공시}, earn: {code: 공시} — 최근 공시 스캔 결과."""
    c, T = P.c, len(P.dates)
    t = T - 1
    cols = c.columns
    res = {}

    PRI = {"관찰": 1, "스윙": 2, "제외": 3}

    def add(code, cat, routes=(), warns=(), notes=(), **extra):
        d = res.setdefault(code, dict(cat=cat, routes=[], warns=[], notes=[], signal_day=None))
        if PRI[cat] > PRI[d["cat"]]:
            d["cat"] = cat
        for key, vals in (("routes", routes), ("warns", warns), ("notes", notes)):
            d[key] += [x for x in vals if x not in d[key]]
        for k, v in extra.items():
            if v is not None and d.get(k) is None:
                d[k] = v

    with np.errstate(invalid="ignore"):
        m60up10 = P.m60 > P.m60.shift(10)
        m60up20 = P.m60 > P.m60.shift(20)
        newhigh = c >= P.hi252
        A = (c > P.m60) & m60up10 & newhigh & (P.v > 2 * P.v20) & P.liq & P.sd60.notna()
        A_flow = A & (P.f40rk >= C.FLOW_TOP)
        nh40 = newhigh.astype(float).rolling(40, min_periods=1).max() > 0
        lead = (c > P.m60) & m60up20 & nh40 & (P.tv20 >= C.LEAD_LIQ_MIN) & P.run_ok
        sc = P.angle
        cross = (sc >= C.ANGLE_THR) & (sc.shift(1) < C.ANGLE_THR)
        floor = sc.shift(1).rolling(15, min_periods=5).min() <= C.ANGLE_FLOOR
        B = lead & cross & floor

    funnel = dict(liquid=int(P.liq.iloc[t].sum()), newhigh=int((newhigh & P.liq).iloc[t].sum()),
                  trend=int(A.iloc[t].sum()), trend_flow=int(A_flow.iloc[t].sum()), angle=int(B.iloc[t].sum()))

    # ---- 스윙: 최근 3거래일 안의 신호 (신호일 종가 진입 기준)
    for k in range(3):
        i = t - k
        day = P.dates[i]
        for code in cols[A_flow.iloc[i].fillna(False).to_numpy()]:
            ok = reg["코스피"]["above60"]
            add(code, "스윙" if ok else "관찰", routes=["trend_flow"], signal_day=day,
                notes=[] if ok else ["코스피가 60일선 아래 — 추세추종 시장 필터 미충족"])
        for code in cols[(A.iloc[i] & ~A_flow.iloc[i]).fillna(False).to_numpy()]:
            if k == 0:
                add(code, "관찰", routes=["trend_noflow"], signal_day=day,
                    notes=["추세 조건은 맞지만 40일 외+기 수급이 상위 30% 밖"])
        for code in cols[B.iloc[i].fillna(False).to_numpy()]:
            if reg["both60"]:
                add(code, "스윙", routes=["angle"], signal_day=day)
            else:
                add(code, "관찰", routes=["angle_weak"], signal_day=day, notes=["두 지수 중 하나가 60일선 아래"])

    # ---- 첫 급등 이벤트 (최근 4거래일)
    with np.errstate(invalid="ignore"):
        pop = (P.day >= C.POP_MIN) & (P.day < C.POP_MAX) & (P.v >= C.POP_VOL * P.v20.shift(1)) & \
              (P.tv20 >= C.LIQ_MIN) & P.run60
        first = pop & ~(pop.astype(float).shift(1).rolling(20, min_periods=1).max() > 0)
    pops = []
    for k in range(4):
        i = t - k
        for code in cols[first.iloc[i].fillna(False).to_numpy()]:
            fD, iD = P.fpi[code].iloc[i], P.ind[code].iloc[i]
            ev = dict(code=code, k=k, day=P.dates[i], ret=float(P.day[code].iloc[i]), fD=fD, iD=iD)
            indiv_only = (fD <= 0) and (iD > 0)
            if k == 3:
                s3f = float(P.fpi[code].iloc[i + 1:t + 1].sum())
                hold = bool(c[code].iloc[t] >= c[code].iloc[i])
                ev.update(s3f=s3f, hold=hold)
                if hold and s3f <= 0:
                    add(code, "제외", warns=["w_hold_sell"], pop=ev)
                elif indiv_only:
                    add(code, "제외", warns=["w_indiv"], pop=ev)
                else:
                    if code in res:
                        res[code]["pop"] = ev
                    continue
            elif indiv_only:
                add(code, "제외", warns=["w_indiv"], pop=ev)
            else:
                add(code, "관찰", routes=["first_pop"], pop=ev,
                    notes=[f"첫 급등 D+{k} — D+3 수급 확인 전 (경고등 확인 대기)"])
            pops.append(ev)
    funnel["pops"] = int(first.iloc[t].sum())

    # ---- 공시 기반 제외
    for code, d in dil.items():
        if code in cols and bool(P.liq[code].iloc[t]):
            add(code, "제외", warns=["dilution"], disc=d)
    for code, d in earn.items():
        if code in cols and P.mc[code].iloc[t] >= 1e12 and P.day[code].iloc[t] <= -0.05:
            add(code, "제외", warns=["earn_bad"], disc=d)

    # 같은 종목에 경고가 있으면 스윙에서 내림
    for code, d in res.items():
        if d["warns"]:
            d["cat"] = "제외"
    return res, funnel


def stop_plan(sd):
    """변동성 손절(9%×√(σ60/REF), 5~18%), 2%룰 비중, 3R 1차 익절, 따라가기 폭"""
    if not np.isfinite(sd) or sd <= 0:
        return None
    sp = min(0.18, max(0.05, 0.09 * np.sqrt(sd / C.REF_SD)))
    return dict(stop=sp, weight=min(1.0, 0.02 / sp), take=3 * sp, trail=min(0.30, max(0.12, 3 * sp)))
