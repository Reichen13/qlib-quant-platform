import json

import baostock as bs


CODES = [
    "sz300024", "sz300033", "sz300058", "sz300059", "sz300070", "sz300072",
    "sz300085", "sz300122", "sz300133", "sz300136", "sz300142", "sz300144",
    "sz300146", "sz300168", "sz300182", "sz300251", "sz300296", "sz300315",
    "sz300347", "sz300408", "sz300413", "sz300498", "sz300601", "sz300628",
]


def main():
    login = bs.login()
    rows = []
    try:
        for code in CODES:
            bs_code = f"{code[:2]}.{code[2:]}"
            result = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount",
                start_date="2026-05-01",
                end_date="2026-06-19",
                frequency="d",
                adjustflag="2",
            )
            dates = []
            error = ""
            if result.error_code != "0":
                error = f"{result.error_code}:{result.error_msg}"
            else:
                while result.next():
                    row = result.get_row_data()
                    if row and row[0]:
                        dates.append(row[0])

            rows.append({
                "code": code,
                "bs_code": bs_code,
                "count": len(dates),
                "first": dates[0] if dates else "",
                "last": dates[-1] if dates else "",
                "error": error,
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
