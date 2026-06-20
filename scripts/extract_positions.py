import json
import re
from pathlib import Path

import fitz  # PyMuPDF

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
OUT = REPORTS_DIR / "positions.json"

MARKETS = [
    {"key": "USA100",       "file": "Report_USA100.pdf",       "code": "US"},
    {"key": "Canada50",     "file": "Report_Canada50.pdf",     "code": "CA"},
    {"key": "Mexico30",     "file": "Report_Mexico30.pdf",     "code": "MX"},
    {"key": "Europe50",     "file": "Report_Europe50.pdf",     "code": "EU"},
    {"key": "UK30",         "file": "Report_UK30.pdf",         "code": "GB"},
    {"key": "France40",     "file": "Report_France40.pdf",     "code": "FR"},
    {"key": "Germany30",    "file": "Report_Germany30.pdf",    "code": "DE"},
    {"key": "Italy30",      "file": "Report_Italy30.pdf",      "code": "IT"},
    {"key": "Japan50",      "file": "Report_Japan50.pdf",      "code": "JP"},
    {"key": "SouthKorea30", "file": "Report_South_Korea30.pdf","code": "KR"},
    {"key": "Australia50",  "file": "Report_Australia50.pdf",  "code": "AU"},
    {"key": "SouthAfrica30","file": "Report_South_Africa30.pdf","code": "ZA"},
]


def extract_positions(text):
    """Positions appear before 'XX.00% Capital Invested'. Collect all ticker lines."""
    m_pct = re.search(r"\d{2,3}\.\d{2}% Capital Invested", text)
    if not m_pct:
        return []
    block = text[:m_pct.start()]
    entries = []
    for line in block.splitlines():
        line = line.strip()
        # ticker: starts with letter OR digit, may contain dots/dashes/digits/uppercase
        m = re.match(r"^([A-Z0-9][A-Z0-9\.\-]{0,15})\s*[-–]\s*(.+)", line)
        if m:
            ticker = m.group(1).strip()
            name = m.group(2).strip()
            if 1 <= len(ticker) <= 16 and not name.startswith("TradingAlgo"):
                entries.append({"ticker": ticker, "name": name})
    return entries[-5:]


def extract_changes(text):
    """Changes appear after 100.00% block: IN/OUT markers then tickers."""
    changes_in = []
    changes_out = []
    m = re.search(r"\d{2,3}\.\d{2}% Capital Invested\s*(.*?)\s*Processing Objective", text, re.DOTALL)
    if not m:
        return {"in": [], "out": []}
    block = m.group(1)
    current_direction = None
    for line in block.splitlines():
        line = line.strip()
        if line == "IN":
            current_direction = "in"
            continue
        if line == "OUT":
            current_direction = "out"
            continue
        tick_match = re.match(r"^([A-Z0-9\.\-]{1,12})\s*[-–]\s*(.+)", line)
        if tick_match and current_direction:
            entry = {"ticker": tick_match.group(1), "name": tick_match.group(2).strip()}
            if current_direction == "in":
                changes_in.append(entry)
            else:
                changes_out.append(entry)
    return {"in": changes_in, "out": changes_out}


def extract_week(text):
    m = re.search(r"Week ending:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def main():
    result = {}
    for market in MARKETS:
        pdf_path = REPORTS_DIR / market["file"]
        if not pdf_path.exists():
            print(f"Missing: {pdf_path.name}")
            result[market["key"]] = {"week": "", "positions": [], "changes": {"in": [], "out": []}}
            continue
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text()
        doc.close()
        result[market["key"]] = {
            "week": extract_week(text),
            "positions": extract_positions(text),
            "changes": extract_changes(text),
        }
        print(f"{market['key']}: {len(result[market['key']]['positions'])} positions, "
              f"in={len(result[market['key']]['changes']['in'])} out={len(result[market['key']]['changes']['out'])}")

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
