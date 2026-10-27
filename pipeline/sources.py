"""데이터 수집: kr-sector-charts data 브랜치(수급·시총·리포트), 네이버(종목명·업종·지수·뉴스), KIND(공시), 야후(나스닥 선물)."""
import datetime as dt
import gzip
import html
import io
import re
import time

import pandas as pd
import requests

from .config import CACHE, DATA_RAW, UA

S = requests.Session()
S.headers.update(UA)


def _get(url, tries=4, timeout=30, **kw):
    for i in range(tries):
        try:
            r = S.get(url, timeout=timeout, **kw)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                print(f"   ! {url[:90]} {repr(e)[:80]}")
                return None
            time.sleep(2 * (i + 1))


# ---------------------------------------------------------------- data 브랜치
def load_alpha(kind, months):
    """alpha/<kind>/<YYYY>/<YYYY-MM>.csv.gz 를 months 개월치 이어 붙임. 지난달 이전 파일은 로컬 캐시 재사용."""
    CACHE.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    frames = []
    for k in range(months, -1, -1):
        y, m = today.year, today.month - k
        while m <= 0:
            y, m = y - 1, m + 12
        name = f"{y}-{m:02d}.csv.gz"
        f = CACHE / f"{kind}_{name}"
        fresh = k <= 1                       # 이번 달·지난달은 매번 새로 받음
        if fresh or not f.exists():
            r = _get(f"{DATA_RAW}/alpha/{kind}/{y}/{name}")
            if r is None:
                continue
            f.write_bytes(r.content)
        frames.append(pd.read_csv(io.BytesIO(gzip.decompress(f.read_bytes())), dtype={"ticker": str, "date": str}))
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = df["ticker"].str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_reports(years):
    """한경 컨센서스 리포트 (data 브랜치 alpha/reports/hk_<연도>.csv)"""
    out = []
    for y in years:
        r = _get(f"{DATA_RAW}/alpha/reports/hk_{y}.csv")
        if r is None:
            continue
        d = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig")), dtype=str)
        out.append(d)
    if not out:
        return pd.DataFrame(columns=["date", "name", "ticker", "tp", "op", "firm", "summary"])
    d = pd.concat(out, ignore_index=True)
    code = d["name"].str.extract(r"\((\d{6})\)")[0]
    d["ticker"] = d["ticker"].fillna(code).fillna("").str.zfill(6)
    d["title"] = d["name"].str.replace(r"\(\d{6}\)", "", regex=True).str.strip()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    return d


# ---------------------------------------------------------------- 네이버
def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return float("nan")


def listing():
    """코스피·코스닥 보통주 목록 (종목명·시장). ETF·스팩·우선주 제외."""
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        page = 1
        while page < 60:
            r = _get(f"https://m.stock.naver.com/api/stocks/marketValue/{mk}?page={page}&pageSize=100")
            st = (r.json().get("stocks") if r else None) or []
            if not st:
                break
            for s in st:
                if s.get("stockEndType") != "stock":
                    continue
                nm = s["stockName"]
                if "스팩" in nm or re.search(r"\d+호$", nm) or not s["itemCode"].endswith("0"):
                    continue
                rows.append(dict(ticker=s["itemCode"], name=nm, market=mk))
            page += 1
            time.sleep(0.1)
    return pd.DataFrame(rows).drop_duplicates("ticker").set_index("ticker")


def sectors():
    """네이버 업종(약 80개) → 종목코드별 업종명"""
    r = _get("https://m.stock.naver.com/api/stocks/industry?page=1&pageSize=100")
    groups = (r.json().get("groups") if r else None) or []
    out = {}
    for g in groups:
        page = 1
        while page < 20:
            r = _get(f"https://m.stock.naver.com/api/stocks/industry/{g['no']}?page={page}&pageSize=100")
            st = (r.json().get("stocks") if r else None) or []
            for s in st:
                out[s["itemCode"]] = g["name"]
            if len(st) < 100:
                break
            page += 1
            time.sleep(0.1)
        time.sleep(0.1)
    return out


def index_closes(code, start):
    """KOSPI / KOSDAQ 일봉 종가"""
    r = _get(f"https://api.stock.naver.com/chart/domestic/index/{code}/day"
             f"?startDateTime={start:%Y%m%d}0000&endDateTime={dt.date.today():%Y%m%d}2359")
    rows = r.json() if r else []
    s = pd.Series({pd.Timestamp(x["localDate"]): float(x["closePrice"]) for x in rows})
    return s.sort_index()


def nasdaq_futures():
    """나스닥100 선물 최근 등락 (전일 정산가 대비)"""
    r = _get("https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?range=5d&interval=1d")
    try:
        m = r.json()["chart"]["result"][0]["meta"]
        return dict(price=m["regularMarketPrice"], chg=m["regularMarketPrice"] / m["chartPreviousClose"] - 1,
                    at=dt.datetime.fromtimestamp(m["regularMarketTime"], dt.timezone(dt.timedelta(hours=9))).strftime("%m/%d %H:%M"))
    except Exception:  # noqa: BLE001
        return None


def news(code, n=20):
    """종목 뉴스 (네이버 증권). 같은 묶음의 기사는 대표 1건 + 묶음 수."""
    r = _get(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize={n}&page=1")
    out = []
    for grp in (r.json() if r else []) or []:
        items = grp.get("items") or []
        if not items:
            continue
        it = items[0]
        out.append(dict(time=it["datetime"], office=it.get("officeName", ""), title=html.unescape(it.get("titleFull") or it["title"]),
                        url=it.get("mobileNewsUrl") or "", body=html.unescape(it.get("body", ""))[:200], count=int(grp.get("total") or 1)))
    return out


def integration(code):
    r = _get(f"https://m.stock.naver.com/api/stock/{code}/integration")
    return r.json() if r else {}


# ---------------------------------------------------------------- KIND 공시
KIND_URL = "https://kind.krx.co.kr/disclosure/details.do"
KIND_H = dict(UA, Referer=KIND_URL + "?method=searchDetailsMain", **{"X-Requested-With": "XMLHttpRequest"})
KIND_BASE = {f"disclosureType{k:02d}": "" for k in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 20)}
KIND_BASE.update(method="searchDetailsSub", currentPageSize="100", orderMode="1", orderStat="D", forward="details_sub",
                 pDisclosureType01="", marketType="", repIsuSrtCd="", kosdaqSegment="", searchCodeType="",
                 searchCorpName="", copyright="", bfrDsclsType="on", reportNm="")
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_kind_ready = False


def _kind_post(**params):
    global _kind_ready
    for i in range(5):
        try:
            if not _kind_ready:
                S.get(KIND_URL + "?method=searchDetailsMain", headers=KIND_H, timeout=30)
                _kind_ready = True
            t = S.post(KIND_URL, data=dict(KIND_BASE, **params), headers=KIND_H, timeout=30).text
            time.sleep(2.5)                              # 서버가 빠른 연속 요청에 '잠시 후 다시' 응답
            if "잠시 후 다시" in t:
                time.sleep(20 * (i + 1)); continue
            return t
        except Exception as e:  # noqa: BLE001
            print("   KIND retry", repr(e)[:80]); time.sleep(8 * (i + 1))
    return ""


def _kind_parse(t):
    body = t[t.find("<tbody"):t.find("</tbody>")]
    out = []
    for r in ROW.findall(body):
        tm = re.search(r'<td class="txc">(\d{4}-\d{2}-\d{2} \d{2}:\d{2})</td>', r)
        cd = re.search(r"companysummary_open\('(\w+)'\)", r)
        ti = re.search(r"openDisclsViewer\('(\d+)'[^>]*title='([^']*)'", r)
        if not (tm and cd and ti):
            continue
        nm = re.search(r"title='([^']*)'>\s*[^<]*</a>", r)
        out.append(dict(time=tm.group(1), kind_code=cd.group(1), name=html.unescape(nm.group(1)) if nm else "",
                        title=html.unescape(ti.group(2)), rcp=ti.group(1), corr="[정정]" in r))
    return out


def kind_company(code, start, end):
    """한 종목의 기간 내 공시 (최신순 최대 100건)"""
    return _kind_parse(_kind_post(repIsuSrtCd="A" + code, fromDate=f"{start:%Y-%m-%d}", toDate=f"{end:%Y-%m-%d}", pageIndex="1"))


def kind_report(keyword, start, end, pages=3):
    """보고서명 키워드로 전체 시장 공시 검색"""
    out = []
    for p in range(1, pages + 1):
        rows = _kind_parse(_kind_post(reportNm=keyword, fromDate=f"{start:%Y-%m-%d}", toDate=f"{end:%Y-%m-%d}", pageIndex=str(p)))
        out += rows
        if len(rows) < 100:
            break
    return out


def kind_url(rcp):
    return f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={rcp}"
