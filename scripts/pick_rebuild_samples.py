"""小样本重建选股辅助脚本。

按复核要求现场选两只补充样本票（不拍脑袋写死）：
  - 次新：baostock query_stock_basic 中 ipoDate > 2025-01-01 的主板股（60/00 开头）任选一只
  - 长期停牌：对候选池跑 tradestatus，找 2023 年以来连续 ≥20 个交易日停牌的票

用法：
    python scripts/pick_rebuild_samples.py

输出：两只票的代码、名称、选择依据，可直接加入 --code 列表。
"""  # noqa: E501

from __future__ import annotations

import baostock as bs


def pick_recent_ipo() -> dict | None:
    """2025 年后主板上市的次新股任选一只。"""
    rs = bs.query_stock_basic(code_name="")
    cands = []
    while rs.next():
        row = rs.get_row_data()  # code, code_name, ipoDate, outDate, type, status
        code, name, ipo, _, _, status = row[0], row[1], row[2], row[3], row[4], row[5]
        # 主板 60/00 开头，上市中，2025 年后
        if (code.startswith("sh.60") or code.startswith("sz.00")) and ipo > "2025-01-01" and status == "1":
            cands.append({"code": code, "name": name, "ipo": ipo})
    if not cands:
        return None
    # 取第一只（query 顺序稳定）
    return {**cands[0], "reason": f"次新：{cands[0]['ipo']} 上市的主板股"}


def pick_long_suspension() -> dict | None:
    """2023 年以来连续 ≥20 个交易日停牌的票。"""
    # 候选池：从全市场抽样若干只检查 tradestatus
    rs = bs.query_stock_basic(code_name="")
    all_codes = []
    while rs.next():
        row = rs.get_row_data()
        if row[5] == "1" and (row[0].startswith("sh.6") or row[0].startswith("sz.0") or row[0].startswith("sz.3")):
            all_codes.append((row[0], row[1]))

    import datetime

    check_start = "2023-01-01"
    check_end = datetime.datetime.now().strftime("%Y-%m-%d")
    for code, name in all_codes[:200]:  # 抽样前 200 只
        rs2 = bs.query_history_k_data_plus(
            code,
            "date,code,tradestatus",
            start_date=check_start,
            end_date=check_end,
            frequency="d",
            adjustflag="3",
        )
        if rs2.error_code != "0":
            continue
        max_streak = 0
        cur_streak = 0
        susp_end = ""
        while rs2.next():
            row = rs2.get_row_data()
            tradestatus = row[2]
            if tradestatus != "1":  # 非交易（停牌）
                cur_streak += 1
                if cur_streak > max_streak:
                    max_streak = cur_streak
                    susp_end = row[0]
            else:
                cur_streak = 0
        if max_streak >= 20:
            return {"code": code, "name": name, "reason": f"长期停牌：连续停牌 {max_streak} 天，截至 {susp_end}"}
    return None


def main() -> int:
    lg = bs.login()
    if lg.error_code != "0":
        print(f"baostock 登录失败: {lg.error_msg}")
        return 1

    try:
        recent = pick_recent_ipo()
        long_susp = pick_long_suspension()
    finally:
        bs.logout()

    print("\n=== 小样本重建补充票 ===")
    for tag, item in [("次新股", recent), ("长期停牌", long_susp)]:
        if item:
            print(f"[{tag}] {item['code']} {item.get('name','')} — {item['reason']}")
        else:
            print(f"[{tag}] 未找到合适样本")

    print("\n完整 10 只样本列表（含复核指定的 8 只 + 上述 2 只）：")
    fixed = ["sh600000", "sh600519", "sz000001", "sz300750", "sh688981", "sz002594", "sh601318", "sh510300"]
    extras = [item["code"].replace(".", "") for item in (recent, long_susp) if item]
    all_codes = fixed + extras
    print(" ".join(f"--code {c}" for c in all_codes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
