#!/usr/bin/env python3
"""Archive licensed TWSE and TPEx OpenAPI responses without rewriting JSON."""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Source:
    url: str
    dataset_id: int
    dataset_title: str
    date_kind: str
    date_fields: tuple[str, ...]
    required_fields: tuple[str, ...]


SOURCES = {
    "TWSE-STOCK_DAY_ALL": Source(
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        11549, "盤後資訊 > 個股日成交資訊", "trade_date", ("Date",),
        ("Code", "OpeningPrice", "HighestPrice", "LowestPrice", "ClosingPrice", "TradeVolume", "TradeValue"),
    ),
    "TPEx-mainboard_quotes": Source(
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
        11371, "上櫃股票收盤行情", "trade_date", ("Date",),
        ("SecuritiesCompanyCode", "Open", "High", "Low", "Close", "TradingShares", "TransactionAmount"),
    ),
    "TWSE-TWT48U_ALL": Source(
        "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL",
        89748, "上市股票除權除息預告表", "ex_date", ("Date",),
        ("Code", "Exdividend", "CashDividend", "StockDividendRatio"),
    ),
    "TWSE-TWT88U": Source(
        "https://openapi.twse.com.tw/v1/exchangeReport/TWT88U",
        11659, "升降幅度/首五日無漲跌幅 > 首五日無漲跌幅", "first_five_trading_days",
        ("1stTradingDate", "5thTradingDate"), ("SecurCode", "OverAllotmentShares"),
    ),
    "TWSE-TWTAWU": Source(
        "https://openapi.twse.com.tw/v1/exchangeReport/TWTAWU",
        11677, "盤後資訊 > 暫停交易證券", "halt_and_resumption",
        ("TradingHaltDate", "TradingResumptionDate"), ("Code", "TradingHaltTime", "TradingResumptionTime"),
    ),
    "TWSE-holidaySchedule": Source(
        "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
        11761, "有價證券集中交易市場開（休）市日期", "calendar_date", ("Date",),
        ("Name", "Weekday", "Description"),
    ),
    "TPEx-exright_prepost": Source(
        "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost",
        11634, "上櫃股票除權除息預告表", "ex_date", ("ExRrightsExDividendDate",),
        ("SecuritiesCompanyCode", "ExRrightsExDividend", "CashDividend"),
    ),
    "TPEx-exright_daily": Source(
        "https://www.tpex.org.tw/openapi/v1/tpex_exright_daily",
        11633, "上櫃股票除權除息計算結果表", "ex_date", ("Date",),
        ("SecuritiesCompanyCode", "ExRightsDiviendQuote", "LimitUp", "LimitDown", "OpeningReferencePrice"),
    ),
    "TPEx-3insti_daily_trading": Source(
        "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading",
        11856, "上櫃股票三大法人買賣明細資訊", "trade_date", ("Date",),
        ("SecuritiesCompanyCode", "TotalDifference"),
    ),
}
MAX_BYTES = 4 * 1024 * 1024
TAIPEI = ZoneInfo("Asia/Taipei")
LICENSE = "https://data.gov.tw/license"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def roc_date(stamp):
    if not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{7}", stamp):
        raise ValueError("expected a seven-digit ROC date")
    return date(int(stamp[:3]) + 1911, int(stamp[3:5]), int(stamp[5:])).isoformat()


def summarize(source, body, retrieved_at):
    spec = SOURCES[source]
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("expected a JSON array")
    required = set(spec.date_fields + spec.required_fields)
    if not all(isinstance(row, dict) and required.issubset(row) for row in rows):
        raise ValueError("required OpenAPI fields missing")
    observed_date = retrieved_at.astimezone(TAIPEI).date().isoformat()
    payload_dates = {}
    for field in spec.date_fields:
        dates = set()
        for row in rows:
            value = row[field]
            if field == "TradingResumptionDate" and value in ("", "-", "--", "---"):
                continue
            dates.add(roc_date(value))
        payload_dates[field] = sorted(dates)

    if not rows and spec.date_kind in ("trade_date", "calendar_date"):
        raise ValueError("expected a nonempty report")
    meta = {
        "source": source,
        "url": spec.url,
        "dataset": f"https://data.gov.tw/dataset/{spec.dataset_id}",
        "license": LICENSE,
        "attribution": {
            "provider": "金融監督管理委員會證券期貨局",
            "publisher": "臺灣證券交易所" if source.startswith("TWSE-") else "證券櫃檯買賣中心",
            "year": observed_date[:4],
            "dataset_title": spec.dataset_title,
            "release": "OpenAPI 快照，未標示資料集版號",
            "notice": "此開放資料依政府資料開放授權條款第 1 版釋出，遵守條款即可利用。",
        },
        "date_kind": spec.date_kind,
        "payload_dates": payload_dates,
        "observed_date_taipei": observed_date,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "rows": len(rows),
        "fields": list(rows[0]) if rows else [],
    }
    if spec.date_kind == "trade_date":
        codes = [row[spec.required_fields[0]] for row in rows]
        if not all(isinstance(code, str) and code for code in codes) or len(set(codes)) != len(rows):
            raise ValueError("missing or duplicate security codes")
        dates = payload_dates["Date"]
        if len(dates) != 1 or dates[0] > observed_date:
            raise ValueError("expected exactly one nonfuture trading date")
        meta["trade_date"] = dates[0]
        directory = Path("snapshots") / dates[0]
    else:
        directory = Path("observations") / observed_date
    meta["raw_path"] = (directory / source / f'{meta["sha256"]}.json').as_posix()
    return meta


def capture(source, out):
    url = SOURCES[source].url
    req = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "TradeAuditStation-OpenData/1.0"})
    with build_opener(NoRedirect).open(req, timeout=30) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("unexpected status or response URL")
        if response.headers.get_content_type() != "application/json":
            raise ValueError("expected application/json")
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        if encoding != "identity":
            raise ValueError("unexpected content encoding")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("response exceeds maximum size")
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) != len(body):
            raise ValueError("response body length mismatch")
        headers = {key.lower(): response.headers.get(key) for key in ("Date", "Last-Modified", "ETag", "Content-Type", "Content-Length")}
    retrieved_at = datetime.now(timezone.utc)
    meta = summarize(source, body, retrieved_at)
    meta.update({"http_status": 200, "retrieved_at_utc": retrieved_at.isoformat(), "headers": headers})
    raw_path = out / meta["raw_path"]
    raw_path.parent.mkdir(exist_ok=True, parents=True)
    raw_path.write_bytes(body)
    raw_path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: meta[key] for key in ("source", "raw_path", "rows", "bytes", "sha256", "date_kind")}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    failed = False
    for source in SOURCES:
        try:
            capture(source, args.out)
        except (OSError, HTTPException, ValueError, TypeError) as exc:
            failed = True
            print(f"{source}: {exc}", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
