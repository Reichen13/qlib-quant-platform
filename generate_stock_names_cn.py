"""
使用 akshare 获取 A 股中文名称映射表
使用更快的接口
"""

import akshare as ak
from pathlib import Path
from datetime import datetime
import pandas as pd


def get_csi300_codes():
    """从 Qlib 文件读取 CSI300 股票代码"""
    csi300_file = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "instruments" / "csi300.txt"
    codes = []
    if csi300_file.exists():
        with open(csi300_file) as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 1:
                    codes.append(parts[0])
    return codes


def fetch_stock_names_fast():
    """使用 akshare 快速获取股票中文名称"""
    stock_names = {}

    # 获取深圳A股列表
    try:
        print("正在获取深圳A股列表...")
        df_sz = ak.stock_info_sz_name_code(symbol="A股列表")
        for idx, row in df_sz.iterrows():
            code = row['A股代码']
            name = row['A股简称']
            # 深圳股票
            stock_names[f"SZ{code}"] = name
        print(f"获取到深圳股票: {len(df_sz)} 只")
    except Exception as e:
        print(f"获取深圳股票失败: {e}")

    # 获取上海A股列表
    try:
        print("正在获取上海A股列表...")
        df_sh = ak.stock_info_sh_name_code(indicator="主板A股")
        for idx, row in df_sh.iterrows():
            code = row['SECURITY_CODE_A']
            name = row['SECURITY_ABBR_A']
            # 上海股票
            stock_names[f"SH{code}"] = name
        print(f"获取到上海股票: {len(df_sh)} 只")
    except Exception as e:
        print(f"获取上海股票失败: {e}")

    return stock_names


def get_all_stocks_akshare():
    """使用东方财富一键获取所有股票"""
    try:
        print("正在从东方财富获取所有A股...")
        # 使用新版接口
        df = ak.stock_zh_a_spot_em()
        print(f"获取到 {len(df)} 只股票")

        stock_names = {}
        for idx, row in df.iterrows():
            code = str(row['代码'])
            name = row['名称']

            # 根据代码判断市场
            if code.startswith('6') or code.startswith('5'):
                stock_names[f"SH{code}"] = name
            else:
                stock_names[f"SZ{code}"] = name

        return stock_names
    except Exception as e:
        print(f"获取失败: {e}")
        return {}


def save_to_file(stock_names: dict, output_file: str):
    """保存到 Python 文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f'# 自动生成的股票名称映射表 (中文)\n')
        f.write(f'# 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'# 股票数量: {len(stock_names)}\n')
        f.write(f'# 数据源: akshare\n\n')
        f.write('STOCK_NAMES_AUTO = {\n')
        for code, name in sorted(stock_names.items()):
            # 转义引号
            name = str(name).replace('"', '\\"')
            f.write(f'    "{code}": "{name}",\n')
        f.write('}\n')

    print(f"已保存到: {output_file}")


if __name__ == "__main__":
    print("开始获取 A 股中文名称...")

    # 方法1: 使用东方财富接口（一次性获取所有）
    names = get_all_stocks_akshare()

    if names:
        save_to_file(names, "stock_names_auto.py")
        print(f"\n完成! 成功: {len(names)}")

        # 统计 CSI300 覆盖率
        csi300_codes = get_csi300_codes()
        covered = [c for c in csi300_codes if c in names]
        print(f"CSI300 覆盖: {len(covered)}/{len(csi300_codes)}")
    else:
        print("获取失败，请重试")
