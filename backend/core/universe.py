"""研究股票池（universe）命名与展示口径。

历史遗留：Qlib instruments 文件曾命名为 csi300.txt，但实际约 650 只，
并非中证官方「沪深300」的 300 只成分。为避免与真实 CSI300 混淆：

- 研究池内部 ID：core650（instruments/core650.txt）
- 展示名：核心研究池（约650只）
- 真实沪深300指数：SH000300 / hs300，仅作基准与展示，不与研究池混名
- 兼容：旧代码/旧任务里的 "csi300" 会映射到 core650
"""

from __future__ import annotations

from pathlib import Path

# 默认研究股票池（非官方沪深300）
DEFAULT_UNIVERSE = "core650"

# 旧 ID → 新 ID
UNIVERSE_ALIASES: dict[str, str] = {
    "csi300": "core650",
    "hs300": "core650",  # 仅当被误用作 universe 时
    "沪深300": "core650",
}

# 用户可见名称（不要写「沪深300」）
UNIVERSE_LABELS: dict[str, str] = {
    "core650": "核心研究池（约650只，快）",
    "csi500": "中证500扩展池（约500+，中）",
    "all": "全市场（约4500只，慢）",
    # 兼容展示：若 UI 仍收到旧 id
    "csi300": "核心研究池（约650只，兼容旧名）",
}

# 真实指数（可称沪深300）
INDEX_LABELS: dict[str, str] = {
    "SH000300": "沪深300指数",
    "hs300": "沪深300指数",
    "000300": "沪深300指数",
}


def resolve_universe(name: str | None) -> str:
    """Normalize universe id; map legacy csi300 → core650."""
    raw = str(name or DEFAULT_UNIVERSE).strip()
    key = raw.lower() if raw.isascii() else raw
    if key in UNIVERSE_ALIASES:
        return UNIVERSE_ALIASES[key]
    # also try lower for ascii codes
    low = raw.lower()
    return UNIVERSE_ALIASES.get(low, low if raw.isascii() else raw)


def universe_label(name: str | None) -> str:
    uid = resolve_universe(name)
    return UNIVERSE_LABELS.get(uid, uid)


def instruments_path(data_dir: Path | None = None, universe: str | None = None) -> Path:
    """Path to instruments txt for a universe (prefers core650, falls back csi300)."""
    root = Path(data_dir) if data_dir else (Path.home() / ".qlib" / "qlib_data" / "cn_data")
    uid = resolve_universe(universe)
    primary = root / "instruments" / f"{uid}.txt"
    if primary.exists():
        return primary
    # legacy fallback
    legacy = root / "instruments" / "csi300.txt"
    if uid == "core650" and legacy.exists():
        return legacy
    return primary


def ensure_core650_instruments(data_dir: Path | None = None) -> Path | None:
    """Ensure core650.txt exists by copying from legacy csi300.txt if needed."""
    root = Path(data_dir) if data_dir else (Path.home() / ".qlib" / "qlib_data" / "cn_data")
    inst_dir = root / "instruments"
    core = inst_dir / "core650.txt"
    legacy = inst_dir / "csi300.txt"
    if core.exists():
        return core
    if legacy.exists():
        try:
            core.write_bytes(legacy.read_bytes())
            return core
        except Exception:
            return legacy
    return None
