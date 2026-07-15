"""因子分析速度测试 - 独立运行，量化每个因子的计算时间"""
import sys, os, time
sys.path.insert(0, r'D:\qlib')
sys.path.insert(0, r'D:\qlib\backend')
os.environ['NUMBA_NUM_THREADS'] = '1'
os.chdir(r'D:\qlib')

import qlib
from qlib.config import C
from qlib.data import D

C.set_qlib_config_path(r'config/qlib_client_config.yaml')
qlib.init(provider_uri=r'C:\Users\Jason\.qlib\qlib_data\cn_data', kernels=1)

from core.alpha158_cache import load_cached_features
from core.compat import fix_parallel_ext
from scipy.stats import spearmanr
import pandas as pd
import numpy as np

fix_parallel_ext()

start_str, end_str, pred_period = '2026-01-01', '2026-06-30', 5

print("=== Loading cache ===")
t0 = time.time()
df_features = load_cached_features(start_str, end_str, 'csi300')
dt = time.time() - t0
print(f"Cache load: {dt:.1f}s, shape={df_features.shape}")

if df_features is None or df_features.empty:
    print("ERROR: Cache returned None/empty!")
    sys.exit(1)

print("=== Speed test: 10 factors ===")
stock_codes = list(df_features.index.get_level_values('instrument').unique())[:50]
feature_names = list(df_features.columns)[:10]
test_dates = sorted(df_features.index.get_level_values('datetime').unique())

times = []
for i, feat_name in enumerate(feature_names):
    t_start = time.time()
    feat_col = df_features[feat_name]
    daily_ics = []

    for dt in test_dates:
        try:
            fv = feat_col.xs(dt, level='datetime').dropna()
            if len(fv) < 20:
                continue

            fv_vals = fv.values
            # Use simple random returns as proxy for IC speed test
            np.random.seed(hash(str(dt)) % 2**31)
            fr_vals = np.random.randn(len(fv_vals))

            ic, _ = spearmanr(fv_vals, fr_vals)
            if not np.isnan(ic):
                daily_ics.append(ic)
        except:
            continue

    dt = time.time() - t_start
    times.append(dt)
    mean_ic = np.mean(daily_ics) if daily_ics else 0
    print(f"  Factor {i+1}/10 {feat_name}: IC={mean_ic:.4f} ({len(daily_ics)} days) | {dt:.1f}s")

total = sum(times)
avg = total / len(times)
est_158 = avg * 158
print(f"\nTotal 10: {total:.1f}s | Avg: {avg:.1f}s/factor | Est 158: {est_158:.1f}s = {est_158/60:.1f}min")
print("Done")
