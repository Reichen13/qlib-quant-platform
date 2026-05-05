"""
深度学习模型注册与训练

支持的模型:
- alstm: Attention LSTM — 时序模式识别
- hist: HIST — 图神经网络，股票间关系建模
- transformer: Transformer/Localformer — 多头注意力
- tra: TRA — 市场状态自适应
- ddg_da: DDG-DA — 分布偏移适应

模型存储: ~/.qlib/dl_models/{name}/model.pkl + config.json
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

MODEL_BASE = Path.home() / ".qlib" / "dl_models"

MODEL_REGISTRY: dict = {
    "alstm": {
        "name": "ALSTM",
        "full_name": "Attention LSTM",
        "description": "基于注意力机制的双层LSTM网络，擅长捕捉时序模式中的长程依赖关系",
        "category": "时序",
        "paper": "Attention-based LSTM for Financial Time Series Prediction",
        "best_for": ["趋势预测", "波动率建模"],
        "default_config": {
            "d_feat": 158,
            "hidden_size": 128,
            "num_layers": 2,
            "dropout": 0.2,
            "n_epochs": 50,
            "lr": 0.001,
            "early_stop": 10,
        },
    },
    "hist": {
        "name": "HIST",
        "full_name": "Historical Information-based Stock Trend",
        "description": "基于图神经网络的股票关系建模，利用股票间历史和行业关联性进行预测",
        "category": "图神经网络",
        "paper": "HIST: A Graph-based Framework for Stock Trend Forecasting",
        "best_for": ["行业轮动", "关联股票预测"],
        "default_config": {
            "d_feat": 158,
            "num_layers": 2,
            "hidden_size": 64,
            "dropout": 0.1,
            "n_epochs": 60,
            "lr": 0.0005,
            "early_stop": 15,
        },
    },
    "transformer": {
        "name": "Transformer",
        "full_name": "Transformer / Localformer",
        "description": "基于多头自注意力的Transformer架构，自动发现序列中的重要时间点和特征交互",
        "category": "注意力",
        "paper": "Attention Is All You Need (Adapted for Finance)",
        "best_for": ["多因子预测", "复杂模式识别"],
        "default_config": {
            "d_feat": 158,
            "n_heads": 4,
            "head_dim": 32,
            "n_layers": 3,
            "dropout": 0.1,
            "n_epochs": 40,
            "lr": 0.0001,
            "early_stop": 10,
        },
    },
    "tra": {
        "name": "TRA",
        "full_name": "Temporal Routing Adaptor",
        "description": "市场状态自适应模型，根据市场环境动态调整预测策略，减少牛熊切换时失效",
        "category": "自适应",
        "paper": "TRA: Temporal Routing Adaptor for Market-Aware Predictions",
        "best_for": ["全市场周期", "牛熊自适应"],
        "default_config": {
            "d_feat": 158,
            "hidden_size": 96,
            "n_routes": 4,
            "dropout": 0.2,
            "n_epochs": 50,
            "lr": 0.001,
            "early_stop": 10,
        },
    },
    "ddg_da": {
        "name": "DDG-DA",
        "full_name": "Distribution Drift-Guided Domain Adaptation",
        "description": "分布偏移适应模型，通过域适应技术减少训练集和测试集之间的分布差异",
        "category": "域适应",
        "paper": "DDG-DA: Distribution Drift Adaptation for Stock Prediction",
        "best_for": ["长回测期", "市场结构变化"],
        "default_config": {
            "d_feat": 158,
            "hidden_size": 64,
            "alpha": 0.1,
            "n_epochs": 50,
            "lr": 0.0005,
            "early_stop": 10,
        },
    },
}

# 训练任务内存存储
_training_tasks: dict = {}


def get_available_models() -> list[dict]:
    """获取可用模型列表"""
    models = []
    for key, info in MODEL_REGISTRY.items():
        model_dir = MODEL_BASE / key
        is_trained = (model_dir / "model.pkl").exists()
        models.append({
            "id": key,
            **info,
            "is_trained": is_trained,
            "model_path": str(model_dir) if is_trained else None,
        })
    return models


def start_training(model_name: str, config: dict | None = None) -> str:
    """启动异步训练任务（桩实现）

    完整实现需要 Qlib 的模型训练管道。
    当前版本返回配置信息，实际训练需要安装完整 Qlib+PyTorch 环境。

    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())[:8]

    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"未知模型: {model_name}")

    model_info = MODEL_REGISTRY[model_name]
    merged_config = {**model_info["default_config"], **(config or {})}

    _training_tasks[task_id] = {
        "status": "completed",  # 桩状态
        "model": model_name,
        "config": merged_config,
        "started_at": datetime.now().isoformat(),
        "progress": 1.0,
        "message": (
            f"{model_info['full_name']} 训练准备就绪（桩模式）。"
            f"实际训练需要安装 PyTorch + Qlib 完整依赖。"
            f"配置: {json.dumps(merged_config, ensure_ascii=False)}"
        ),
    }

    return task_id


def get_training_status(task_id: str) -> dict | None:
    """获取训练任务状态"""
    return _training_tasks.get(task_id)
