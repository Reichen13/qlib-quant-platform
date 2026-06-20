import json

import baostock as bs


CODES = [
    "sz300124", "sz300433",
    "sh600068", "sh600074", "sh600190", "sh600220", "sh600270", "sh600277",
    "sh600297", "sh600317", "sh600432", "sh600485", "sh600705", "sh600804",
    "sh600811", "sh600823", "sh600837", "sh600978", "sh601258", "sh601558",
    "sh601989", "sz000046", "sz000413", "sz000540", "sz000627", "sz000667",
    "sz000671", "sz000780", "sz000961", "sz002411", "sz002450", "sz300104",
    "sh600005", "sh600087", "sh600102", "sh600591", "sh600747", "sh600849",
    "sh601268",
]


def bs_code(code: str) -> str:
    return f"{code[:2]}.{code[2:]}"


def query_recent_rows(code: str) -> tuple[int, str, str, str]:
    result = bs.query_history_k_data_plus(
        bs_code(code),
        "date,code,open,high,low,close,volume,amount",
        start_date="2026-05-01",
        end_date="2026-06-19",
        frequency="d",
        adjustflag="2",
    )
    if result.error_code != "0":
        return 0, "", "", f"{result.error_code}:{result.error_msg}"

    dates = []
    while result.next():
        row = result.get_row_data()
        if row and row[0]:
            dates.append(row[0])
    return len(dates), dates[0] if dates else "", dates[-1] if dates else "", ""


def query_stock_basic(code: str) -> dict:
    result = bs.query_stock_basic(code=bs_code(code))
    if result.error_code != "0":
        return {"error": f"{result.error_code}:{result.error_msg}"}
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    if not rows:
        return {"error": "no_basic_row"}

    row = rows[0]
    return {
        "code": row[0] if len(row) > 0 else "",
        "name": row[1] if len(row) > 1 else "",
        "ipo_date": row[2] if len(row) > 2 else "",
        "out_date": row[3] if len(row) > 3 else "",
        "type": row[4] if len(row) > 4 else "",
        "status": row[5] if len(row) > 5 else "",
    }


def main():
    login = bs.login()
    rows = []
    try:
        for code in CODES:
            count, first, last, error = query_recent_rows(code)
            basic = query_stock_basic(code)
            if count > 0:
                category = "recent_data_available"
            elif basic.get("out_date"):
                category = "delisted_or_outdated_pool"
            elif basic.get("error"):
                category = "unknown_no_basic"
            else:
                category = "no_recent_data"
            rows.append({
                "code": code,
                "bs_code": bs_code(code),
                "recent_count": count,
                "recent_first": first,
                "recent_last": last,
                "recent_error": error,
                "basic": basic,
                "category": category,
            })
    finally:
        bs.logout()

    print(json.dumps({
        "login_error_code": login.error_code,
        "login_error_msg": login.error_msg,
        "rows": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
