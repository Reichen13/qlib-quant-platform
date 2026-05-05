"""
Qlib 兼容性补丁（统一版本）

修复 Qlib 0.9.6 与 joblib 1.5+ 的兼容性问题：
joblib 1.5+ 将 _backend_args 改名为 _backend_kwargs，
导致 Qlib 的 ParallelExt 访问 _backend_args 时 AttributeError。

本模块提供幂等补丁，在 main.py / factors.py / backtest.py 中共用。
"""

from loguru import logger

_patched = False


def fix_parallel_ext():
    """修复 ParallelExt 与 joblib 1.5+ 的兼容性（幂等调用）"""
    global _patched
    if _patched:
        return

    try:
        from qlib.utils.paral import ParallelExt

        _original_init = ParallelExt.__init__

        def _new_init(self_par, *args, **kwargs):
            try:
                _original_init(self_par, *args, **kwargs)
            except AttributeError:
                import joblib
                if hasattr(joblib, "_backend_kwargs"):
                    joblib._backend_args = joblib._backend_kwargs
                _original_init(self_par, *args, **kwargs)

        ParallelExt.__init__ = _new_init
        _patched = True
        logger.info("ParallelExt 兼容性补丁已应用 (joblib 1.5+)")
    except ImportError:
        logger.debug("Qlib 不可用，跳过 ParallelExt 补丁")
    except Exception as e:
        logger.warning(f"ParallelExt 补丁应用失败: {e}")
