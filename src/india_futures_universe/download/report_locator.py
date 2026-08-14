from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportCandidate:
    report_type: str
    source_format: str
    url: str
    filename: str
    source_page: str


NSE_REPORTS_PAGE = "https://www.nseindia.com/all-reports-derivatives"
ARCHIVE = "https://archives.nseindia.com"
NSEARCHIVES = "https://nsearchives.nseindia.com"


def candidates_for_date(session: date) -> list[ReportCandidate]:
    dd = session.strftime("%d")
    mon = session.strftime("%b").upper()
    yyyy = session.strftime("%Y")
    yyyymmdd = session.strftime("%Y%m%d")
    ddmmyyyy = session.strftime("%d%m%Y")
    legacy = f"fo{dd}{mon}{yyyy}bhav.csv.zip"
    udiff = f"BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
    contract = f"NSE_FO_contract_{ddmmyyyy}.csv.gz"
    settlement = f"fo_settlement_{ddmmyyyy}.csv"
    span_eod = f"nsccl.{session.strftime('%Y%m%d')}.s.zip"
    span_bod = f"nsccl.{session.strftime('%Y%m%d')}.i01.zip"
    return [
        ReportCandidate("bhavcopy", "LEGACY_FO_BHAVCOPY", f"{ARCHIVE}/content/historical/DERIVATIVES/{yyyy}/{mon}/{legacy}", legacy, NSE_REPORTS_PAGE),
        ReportCandidate("bhavcopy", "UDIFF_FO_BHAVCOPY", f"{NSEARCHIVES}/content/fo/{udiff}", udiff, NSE_REPORTS_PAGE),
        ReportCandidate("contract", "MII_FO_CONTRACT_FILE", f"{NSEARCHIVES}/content/fo/{contract}", contract, NSE_REPORTS_PAGE),
        ReportCandidate("settlement", "FO_DAILY_SETTLEMENT", f"{NSEARCHIVES}/content/fo/{settlement}", settlement, NSE_REPORTS_PAGE),
        ReportCandidate("span_eod", "FO_SPAN_EOD", f"{NSEARCHIVES}/content/fo/{span_eod}", span_eod, NSE_REPORTS_PAGE),
        ReportCandidate("span_bod", "FO_SPAN_BOD", f"{NSEARCHIVES}/content/fo/{span_bod}", span_bod, NSE_REPORTS_PAGE),
    ]
