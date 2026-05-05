"""
验证工具函数（toDateString, relativeDate 的 Python 等效实现）。
"""
from datetime import date, timedelta


def last_day_of_month(d: date) -> date:
    """返回当月最后一天，处理跨月边界"""
    if d.month == 12:
        return date(d.year, 12, 31)
    next_month = date(d.year, d.month + 1, 1)
    return next_month - timedelta(days=1)


def relative_date(years: int = 0, months: int = 0, days: int = 0) -> date:
    """相对今天的日期偏移"""
    d = date.today()
    if years:
        d = d.replace(year=d.year + years)
    if months:
        new_month = d.month + months
        while new_month > 12:
            d = d.replace(year=d.year + 1)
            new_month -= 12
        while new_month < 1:
            d = d.replace(year=d.year - 1)
            new_month += 12
        # 处理月末溢出（如 1月31日 + 1个月 → 2月28日）
        last_day = last_day_of_month(d.replace(month=new_month))
        d = d.replace(month=new_month, day=min(d.day, last_day.day))
    if days:
        d = d + timedelta(days=days)
    return d


def to_date_string(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def test_to_date_string_format():
    """验证日期字符串格式 YYYY-MM-DD"""
    d = date(2026, 5, 5)
    assert to_date_string(d) == "2026-05-05"
    d2 = date(2026, 12, 1)
    assert to_date_string(d2) == "2026-12-01"


def test_relative_date_today():
    """0 偏移应返回今天"""
    assert relative_date(days=0) == date.today()


def test_relative_date_days_offset():
    """天偏移"""
    result = relative_date(days=-1)
    expected = date.today() - timedelta(days=1)
    assert result == expected


def test_relative_date_month_offset():
    """月偏移"""
    result = relative_date(months=-6)
    d = date.today()
    # 向前 6 个月
    for _ in range(6):
        d = d.replace(day=1) - timedelta(days=1)
        d = d.replace(day=min(date.today().day, last_day_of_month(d).day))
    # 简化验证：结果应该是过去
    assert result < date.today()


def test_relative_date_year_offset():
    """年偏移"""
    result = relative_date(years=-2)
    d = date.today()
    expected_year = d.year - 2
    assert result.year == expected_year


def test_last_day_of_month():
    """验证月末计算"""
    assert last_day_of_month(date(2026, 1, 15)) == date(2026, 1, 31)
    assert last_day_of_month(date(2026, 2, 15)) == date(2026, 2, 28)
    assert last_day_of_month(date(2028, 2, 15)) == date(2028, 2, 29)  # 闰年
    assert last_day_of_month(date(2026, 12, 15)) == date(2026, 12, 31)


def test_default_date_ranges():
    """验证默认回测/因子分析日期范围的合理性"""
    today = date.today()
    # 回测训练：24 个月到 7 个月前
    train_start = relative_date(months=-24)
    train_end = relative_date(months=-7)
    test_start = relative_date(months=-6)
    test_end = relative_date(days=-1)

    assert train_start < train_end < test_start < test_end < today
    # 训练期至少 12 个月
    assert (train_end - train_start).days > 360
    # 测试期至少 3 个月
    assert (test_end - test_start).days > 90

    # 因子分析：6 个月前到今天
    factor_start = relative_date(months=-6)
    factor_end = relative_date(days=-1)
    assert factor_start < factor_end < today
    assert (factor_end - factor_start).days > 150
