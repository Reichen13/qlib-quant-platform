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
import threading
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
_training_lock = threading.Lock()


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
    """启动异步训练任务

    使用 Qlib 的 GBDT 训练管道（LightGBM/XGBoost）。
    对于 DL 模型（ALSTM/HIST 等），需要 PyTorch 环境。

    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())[:8]

    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"未知模型: {model_name}")

    model_info = MODEL_REGISTRY[model_name]
    merged_config = {**model_info["default_config"], **(config or {})}
    model_dir = MODEL_BASE / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    with _training_lock:
        _training_tasks[task_id] = {
            "status": "running",
            "model": model_name,
            "config": merged_config,
            "started_at": datetime.now().isoformat(),
            "progress": 0.0,
            "message": f"启动 {model_info['full_name']} 训练...",
        }

    # 在后台线程中运行训练
    thread = threading.Thread(
        target=_run_training,
        args=(task_id, model_name, merged_config, model_dir),
        daemon=True,
    )
    thread.start()

    return task_id


def _run_training(task_id: str, model_name: str, config: dict, model_dir: Path):
    """后台训练线程"""
    try:
        import qlib
        from qlib.data import D
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.utils import init_instance_by_config
        from qlib.contrib.model.gbdt import LGBModel
        import pandas as pd
        from datetime import datetime, timedelta

        model_info = MODEL_REGISTRY[model_name]

        def _update(msg: str, progress: float):
            with _training_lock:
                _training_tasks[task_id]["message"] = msg
                _training_tasks[task_id]["progress"] = min(progress, 1.0)

        _update("正在准备数据...", 0.05)

        # 获取沪深300成分股
        instruments = D.list_instruments(D.instruments("csi300"), as_list=True)

        # 数据集配置
        today = datetime.now()
        end_time = today.strftime("%Y-%m-%d")
        train_end = (today - timedelta(days=60)).strftime("%Y-%m-%d")
        train_start = (today - timedelta(days=365 * 2)).strftime("%Y-%m-%d")

        handler_conf = {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": train_start,
                "end_time": end_time,
                "fit_start_time": train_start,
                "fit_end_time": train_end,
                "instruments": instruments,
            },
        }

        _update("正在构建 Alpha158 特征...", 0.10)

        handler = init_instance_by_config(handler_conf)
        dataset_conf = {
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": handler,
                "segments": {
                    "train": (train_start, train_end),
                    "test": (train_end, end_time),
                },
            },
        }
        dataset = init_instance_by_config(dataset_conf)

        _update(f"正在训练 {model_info['full_name']}...", 0.20)

        # 训练模型（使用 LightGBM 作为默认，DL 模型尝试对应配置）
        if model_name == "alstm":
            model_class = "ALSTM"
            model_module = "qlib.contrib.model.pytorch_alstm"
        elif model_name == "hist":
            model_class = "HIST"
            model_module = "qlib.contrib.model.pytorch_hist"
        elif model_name in ("transformer", "localformer"):
            model_class = "Transformer"
            model_module = "qlib.contrib.model.pytorch_transformer"
        elif model_name == "tra":
            model_class = "TRA"
            model_module = "qlib.contrib.model.pytorch_tra"
        elif model_name == "ddg_da":
            model_class = "DDG_DA"
            model_module = "qlib.contrib.model.pytorch_ddg_da"
        else:
            model_class = "LGBModel"
            model_module = "qlib.contrib.model.gbdt"

        model_conf = {
            "class": model_class,
            "module_path": model_module,
            "kwargs": config,
        }

        _update(f"正在训练 {model_info['full_name']} (数据准备完成)...", 0.30)

        model = init_instance_by_config(model_conf)
        model.fit(dataset)

        _update("正在保存模型...", 0.90)

        # 保存模型
        import pickle
        model_path = model_dir / "model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)

        config_path = model_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, ensure_ascii=False)

        with _training_lock:
            _training_tasks[task_id].update({
                "status": "completed",
                "progress": 1.0,
                "message": f"{model_info['full_name']} 训练完成",
                "model_path": str(model_path),
            })

        logger.info(f"DL 训练完成: {model_name} (task={task_id})")

    except ImportError as e:
        logger.warning(f"DL 训练缺少依赖: {e}")
        with _training_lock:
            _training_tasks[task_id].update({
                "status": "failed",
                "progress": 0.0,
                "message": f"缺少依赖: {e}. 请安装 PyTorch + Qlib 完整版。",
            })
    except Exception as e:
        logger.error(f"DL 训练失败 ({model_name}): {e}")
        with _training_lock:
            _training_tasks[task_id].update({
                "status": "failed",
                "progress": 0.0,
                "message": f"训练失败: {e}",
            })


def get_training_status(task_id: str) -> dict | None:
    """获取训练任务状态"""
    return _training_tasks.get(task_id)
