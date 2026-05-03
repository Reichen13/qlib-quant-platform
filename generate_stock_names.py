"""
预生成股票名称映射表
批量获取 CSI300 股票名称并保存到本地文件
"""

import pandas as pd
import yfinance as yf
import time
from pathlib import Path
from datetime import datetime

# CSI300 主要股票代码列表（从 csi300.txt 读取）
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

def yf_code(qlib_code: str) -> str:
    """Qlib 代码转 yfinance 格式"""
    code = qlib_code.upper()
    pure = code.replace("SH", "").replace("SZ", "")
    if pure.startswith("6") or pure.startswith("5"):
        return f"{pure}.SS"
    else:
        return f"{pure}.SZ"

def fetch_stock_names():
    """批量获取股票名称"""
    codes = get_csi300_codes()
    print(f"找到 {len(codes)} 只股票")

    stock_names = {}
    failed = []

    for i, code in enumerate(codes):
        try:
            yf_c = yf_code(code)
            ticker = yf.Ticker(yf_c)
            info = ticker.info

            # 尝试获取名称
            name = None
            if info:
                name = info.get('shortName') or info.get('longName') or info.get('symbol')

            if name:
                # 清理名称（去掉多余的股票代码后缀）
                name = name.split('-')[0].strip()
                # 去掉 .SS 或 .SZ 后缀
                name = name.replace('.SS', '').replace('.SZ', '')
                stock_names[code] = name
                print(f"[{i+1}/{len(codes)}] {code} -> {name}")
            else:
                failed.append(code)
                print(f"[{i+1}/{len(codes)}] {code} -> 未找到")

            # 避免请求过快
            time.sleep(0.1)

        except Exception as e:
            failed.append(code)
            print(f"[{i+1}/{len(codes)}] {code} -> 错误: {e}")

    return stock_names, failed

def save_to_file(stock_names: dict, output_file: str):
    """保存到 Python 文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f'# 自动生成的股票名称映射表\n')
        f.write(f'# 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'# 股票数量: {len(stock_names)}\n\n')
        f.write('STOCK_NAMES_AUTO = {\n')
        for code, name in sorted(stock_names.items()):
            f.write(f'    "{code}": "{name}",\n')
        f.write('}\n')

    print(f"已保存到: {output_file}")

if __name__ == "__main__":
    print("开始获取 CSI300 股票名称...")
    names, failed = fetch_stock_names()
    save_to_file(names, "stock_names_auto.py")
    print(f"\n完成! 成功: {len(names)}, 失败: {len(failed)}")
    if failed:
        print(f"失败的股票: {failed[:10]}...")
