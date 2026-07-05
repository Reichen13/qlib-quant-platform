"""把备份目录的指数 bin 重映射到新日历后写入当前数据目录。

背景:全量重建的 --all 清单过滤了指数代码(sh000*),导致新数据缺少
sh000300/sh000903/sh000905,回测 benchmark 与首页指数展示失效。
指数无复权因子问题(价格指数,qfq=raw),旧数据的多源缝合对指数无害,
因此从备份恢复是可接受的过渡方案;长期由 baostock 指数通道接管。

安全性:只写当前目录下 features/<index>/ 新目录,不碰任何股票 bin。
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

HOME = pathlib.Path.home()
BACKUP = HOME / ".qlib/qlib_data/cn_data_backup_20260705"
CURRENT = HOME / ".qlib/qlib_data/cn_data"
INDICES = ["sh000300", "sh000903", "sh000905"]
FIELDS = ["open", "high", "low", "close", "volume", "amount", "factor"]


def read_calendar(base: pathlib.Path) -> list[str]:
    return [l.strip() for l in (base / "calendars/day.txt").read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    old_cal = read_calendar(BACKUP)
    new_cal = read_calendar(CURRENT)
    new_idx = {d: i for i, d in enumerate(new_cal)}

    for code in INDICES:
        src_dir = BACKUP / "features" / code
        dst_dir = CURRENT / "features" / code
        if not src_dir.exists():
            print(f"{code}: 备份缺失,跳过")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)

        for field in FIELDS:
            src = src_dir / f"{field}.day.bin"
            if not src.exists():
                continue
            raw = np.fromfile(src, dtype="<f")
            if len(raw) < 2:
                continue
            start_idx_old = int(raw[0])
            vals = raw[1:]
            # 旧 bin 索引 -> 日期 -> 值(仅有限值)
            date_vals: dict[str, float] = {}
            for off, v in enumerate(vals):
                ci = start_idx_old + off
                if 0 <= ci < len(old_cal) and np.isfinite(v):
                    date_vals[old_cal[ci]] = float(v)
            if not date_vals:
                continue
            dates = sorted(d for d in date_vals if d in new_idx)
            if not dates:
                continue
            s, e = new_idx[dates[0]], new_idx[dates[-1]]
            out = [float("nan")] * (e - s + 1)
            for d in dates:
                out[new_idx[d] - s] = date_vals[d]
            payload = np.array([float(s), *out], dtype="<f")
            payload.tofile(dst_dir / f"{field}.day.bin")

        # 校验
        raw = np.fromfile(dst_dir / "close.day.bin", dtype="<f")
        s = int(raw[0]); v = raw[1:]
        finite = np.where(np.isfinite(v))[0]
        first, last = new_cal[s + finite[0]], new_cal[s + finite[-1]]
        density = len(finite) / len(v)
        print(f"{code}: {first} -> {last}, 有效 {len(finite)}/{len(v)} (密度 {density:.1%}), 末值 {v[finite[-1]]:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
