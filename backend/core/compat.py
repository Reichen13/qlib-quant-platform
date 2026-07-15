"""
Qlib 兼容性补丁（统一版本）

修复 Qlib 0.9.6 与 joblib 1.5+ 的兼容性问题：
joblib 1.5+ 将 _backend_args 改名为 _backend_kwargs，
导致 Qlib 的 ParallelExt 访问 _backend_args 时 AttributeError。

本模块提供幂等补丁，在 main.py / factors.py / backtest.py 中共用。
"""

import os

from loguru import logger

_patched = False
_serial_forced = False


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


def force_serial_joblib(n_jobs: int = 1) -> None:
    """
    强制 Qlib ParallelExt / joblib 走单线程。

    因子分析在 FastAPI daemon 线程中运行时，loky 多进程在 Windows 上
    容易卡死（进度长期停在假 ticker 的 40%~50%）。幂等调用。
    """
    global _serial_forced, _patched
    fix_parallel_ext()

    os.environ.setdefault("NUMBA_NUM_THREADS", "1")
    os.environ.setdefault("QLIB_NO_MULTI_PROCESS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    # 0 = 禁用 joblib 进程池，避免在 daemon 线程内 spawn 子进程
    os.environ["JOBLIB_MULTIPROCESSING"] = "0"

    if _serial_forced:
        return

    try:
        from qlib.utils.paral import ParallelExt

        _original_init = ParallelExt.__init__

        def _serial_init(self_par, *args, **kwargs):
            kwargs["n_jobs"] = n_jobs
            # joblib Parallel: prefer threads 避免 loky 进程
            kwargs.setdefault("prefer", "threads")
            try:
                return _original_init(self_par, *args, **kwargs)
            except TypeError:
                # 旧版本 Parallel 可能不认 prefer
                kwargs.pop("prefer", None)
                return _original_init(self_par, *args, **kwargs)
            except AttributeError:
                import joblib
                if hasattr(joblib, "_backend_kwargs"):
                    joblib._backend_args = joblib._backend_kwargs
                try:
                    return _original_init(self_par, *args, **kwargs)
                except TypeError:
                    kwargs.pop("prefer", None)
                    return _original_init(self_par, *args, **kwargs)

        ParallelExt.__init__ = _serial_init
        _serial_forced = True
        _patched = True
        logger.info(f"ParallelExt 已强制串行 n_jobs={n_jobs}, prefer=threads")
    except ImportError:
        logger.debug("Qlib 不可用，跳过串行 Parallel 补丁")
    except Exception as e:
        logger.warning(f"串行 Parallel 补丁失败: {e}")
