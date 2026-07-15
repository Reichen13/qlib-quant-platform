"""
深度学习模型注册与训练

支持的模型:
- alstm: Attention LSTM — 时序模式识别
- hist: HIST — 图神经网络，股票间关系建模
- transformer: Transformer/Localformer — 多头注意力
- tra: TRA — 市场状态自适应
- gru: GRU — 门控循环单元，简洁高效

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
from db.task_store import TaskStore

MODEL_BASE = Path.home() / ".qlib" / "dl_models"
dl_training_task_store = TaskStore(Path.home() / ".qlib" / "dl_training_tasks.db", table_name="dl_training_tasks")

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
    "gru": {
        "name": "GRU",
        "full_name": "Gated Recurrent Unit",
        "description": "门控循环单元，结构简洁计算高效，擅长捕抓短u671f依u8d56关系。对波段交易者是不错的基u7ebfu6a21u578b。",
        "category": "时序",
        "paper": "Empirical Evaluation of Gated Recurrent Neural Networks on Sequence Modeling",
        "best_for": ["短u671fu8d8bu52bf", "快u901fu8badu7ec3"],
        "default_config": {
            "d_feat": 158,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 50,
            "lr": 0.001,
            "early_stop": 10,
        },
    },
}

# 训练任务内存存储
_training_tasks: dict = {}
_training_lock = threading.Lock()


def _progress_to_percent(progress) -> int:
    try:
        value = float(progress)
    except (TypeError, ValueError):
        return 0
    if value <= 1:
        value *= 100
    return max(0, min(100, int(round(value))))


def _persist_training_task(task_id: str, task: dict) -> None:
    dl_training_task_store.init_db()
    if dl_training_task_store.get_task(task_id) is None:
        dl_training_task_store.create_task(
            task_id,
            json.dumps({
                "model": task.get("model"),
                "config": task.get("config", {}),
                "started_at": task.get("started_at"),
            }, ensure_ascii=False),
        )

    payload = json.dumps(task, ensure_ascii=False)
    status = task.get("status")
    if status == "completed":
        dl_training_task_store.set_completed(task_id, payload)
    elif status == "failed":
        dl_training_task_store.set_failed(
            task_id,
            task.get("error") or task.get("message") or "DL training failed",
            payload,
        )
    else:
        dl_training_task_store.set_running(
            task_id,
            _progress_to_percent(task.get("progress", 0)),
            payload,
        )


def _save_training_task(task_id: str, **updates) -> dict:
    with _training_lock:
        current = _training_tasks.get(task_id, {})
        current.update(updates)
        _training_tasks[task_id] = current
        task_snapshot = current.copy()
    _persist_training_task(task_id, task_snapshot)
    return task_snapshot


def _get_persisted_training_task(task_id: str) -> dict | None:
    try:
        dl_training_task_store.init_db()
        row = dl_training_task_store.get_task(task_id)
    except Exception as e:
        logger.warning(f"Failed to load persisted DL training task {task_id}: {e}")
        return None

    if row is None:
        return None

    payload = {}
    for field in ("result_json", "params_json"):
        if row.get(field):
            try:
                payload = json.loads(row[field])
                break
            except Exception:
                payload = {}

    progress = payload.get("progress")
    if progress is None:
        progress = (row.get("progress") or 0) / 100

    return {
        **payload,
        "status": payload.get("status") or row.get("status"),
        "progress": progress,
        "message": payload.get("message") or row.get("error") or "DL training task is running",
        "error": payload.get("error") or row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


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
    with _training_lock:
        task_snapshot = _training_tasks[task_id].copy()
    _persist_training_task(task_id, task_snapshot)

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
                task_snapshot = _training_tasks[task_id].copy()
            _persist_training_task(task_id, task_snapshot)

        _update("正在准备数据...", 0.05)

        # 获取核心研究池（约650只，非官方沪深300）
        from core.universe import DEFAULT_UNIVERSE, ensure_core650_instruments
        ensure_core650_instruments()
        instruments = D.list_instruments(D.instruments(DEFAULT_UNIVERSE), as_list=True)

        # 数据集配置
        today = datetime.now()
        end_time = today.strftime("%Y-%m-%d")
        train_start = (today - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
        valid_start = (today - timedelta(days=120)).strftime("%Y-%m-%d")
        valid_end = (today - timedelta(days=60)).strftime("%Y-%m-%d")

        handler_conf = {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": train_start,
                "end_time": end_time,
                "fit_start_time": train_start,
                "fit_end_time": valid_start,
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
                    "train": (train_start, valid_start),
                    "valid": (valid_start, valid_end),
                    "test": (valid_end, end_time),
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
        elif model_name == "gru":
            model_class = "GRU"
            model_module = "qlib.contrib.model.pytorch_gru"
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
            task_snapshot = _training_tasks[task_id].copy()
        _persist_training_task(task_id, task_snapshot)

        logger.info(f"DL 训练完成: {model_name} (task={task_id})")

    except ImportError as e:
        logger.warning(f"DL 训练缺少依赖: {e}")
        with _training_lock:
            _training_tasks[task_id].update({
                "status": "failed",
                "progress": 0.0,
                "message": f"缺少依赖: {e}. 请安装 PyTorch + Qlib 完整版。",
            })
            task_snapshot = _training_tasks[task_id].copy()
        _persist_training_task(task_id, task_snapshot)
    except Exception as e:
        logger.error(f"DL 训练失败 ({model_name}): {e}")
        with _training_lock:
            _training_tasks[task_id].update({
                "status": "failed",
                "progress": 0.0,
                "message": f"训练失败: {e}",
            })
            task_snapshot = _training_tasks[task_id].copy()
        _persist_training_task(task_id, task_snapshot)



_prediction_tasks: dict = {}
_prediction_lock = threading.Lock()


def start_prediction(model_name: str, top_n: int = 20) -> str:
    """启动异步预测任务，使用已训练的 DL 模型对最新数据运行推理。

    Returns:
        task_id
    """
    task_id = str(uuid.uuid4())[:8]

    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"未知模型: {model_name}")

    model_path = MODEL_BASE / model_name / "model.pkl"
    if not model_path.exists():
        raise ValueError(f"模型 {model_name} 尚未训练，请先训练再预测")

    with _prediction_lock:
        _prediction_tasks[task_id] = {
            "status": "running",
            "model": model_name,
            "top_n": top_n,
            "started_at": datetime.now().isoformat(),
            "progress": 0.0,
            "message": f"启动 {model_name} 预测...",
        }

    thread = threading.Thread(
        target=_run_prediction,
        args=(task_id, model_name, top_n),
        daemon=True,
    )
    thread.start()
    return task_id


def _run_prediction(task_id: str, model_name: str, top_n: int):
    """后台预测线程。"""
    try:
        import pickle
        import qlib
        from qlib.data import D
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.utils import init_instance_by_config
        import pandas as pd
        from datetime import datetime, timedelta

        from stock_names import get_stock_name

        def _update(msg, progress):
            with _prediction_lock:
                _prediction_tasks[task_id]["message"] = msg
                _prediction_tasks[task_id]["progress"] = min(progress, 1.0)
            _persist_prediction(task_id)

        _update("正在加载模型...", 0.05)

        model_path = MODEL_BASE / model_name / "model.pkl"
        with open(model_path, "rb") as f:
            model = pickle.load(f)

        _update("正在准备 Alpha158 特征...", 0.15)

        from core.universe import DEFAULT_UNIVERSE, ensure_core650_instruments
        ensure_core650_instruments()
        instruments = D.list_instruments(D.instruments(DEFAULT_UNIVERSE), as_list=True)

        today = datetime.now()
        end_time = today.strftime("%Y-%m-%d")
        start_time = (today - timedelta(days=365)).strftime("%Y-%m-%d")

        handler_conf = {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": start_time,
                "end_time": end_time,
                "fit_start_time": start_time,
                "fit_end_time": start_time,
                "instruments": instruments,
            },
        }
        handler = init_instance_by_config(handler_conf)

        dataset_conf = {
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": handler,
                "segments": {
                    "test": (start_time, end_time),
                },
            },
        }
        dataset = init_instance_by_config(dataset_conf)

        _update("正在运行模型预测...", 0.50)

        predictions = model.predict(dataset, segment="test")

        _update("正在整理预测结果...", 0.80)

        if not hasattr(predictions, "index"):
            predictions = pd.Series(predictions)

        pred_date = end_time
        if hasattr(predictions.index, "get_level_values"):
            datetime_level = None
            for level_name in ["datetime", "time", "date"]:
                try:
                    datetime_level = predictions.index.get_level_values(level_name)
                    break
                except (KeyError, AttributeError):
                    continue

            if datetime_level is not None and hasattr(datetime_level, "max"):
                latest_date = datetime_level.max()
                mask = datetime_level == latest_date
                predictions = predictions[mask]
                pred_date = str(latest_date)[:10]

        sorted_preds = predictions.sort_values(ascending=False)
        top = sorted_preds.head(top_n)

        results = []
        for idx, val in top.items():
            code = idx
            if isinstance(idx, tuple):
                code = idx[0]
            code_str = str(code)
            try:
                name = get_stock_name(code_str) or code_str
            except Exception:
                name = code_str
            results.append({
                "code": code_str,
                "name": name,
                "score": round(float(val), 6),
            })

        with _prediction_lock:
            _prediction_tasks[task_id].update({
                "status": "completed",
                "progress": 1.0,
                "message": f"{model_name} 预测完成，返回前 {len(results)} 只股票",
                "predictions": results,
                "pred_date": pred_date,
            })
        _persist_prediction(task_id)
        logger.info(f"DL 预测完成: {model_name} (task={task_id}), top-{len(results)}")

    except Exception as e:
        logger.error(f"DL 预测失败 ({model_name}): {e}")
        with _prediction_lock:
            _prediction_tasks[task_id].update({
                "status": "failed",
                "progress": 0.0,
                "message": f"预测失败: {e}",
            })
        _persist_prediction(task_id)


def _persist_prediction(task_id: str):
    with _prediction_lock:
        task = _prediction_tasks.get(task_id)
        if task is None:
            return
        snapshot = task.copy()
    try:
        import json
        dl_training_task_store.init_db()
        existing = dl_training_task_store.get_task(task_id)
        payload = json.dumps(snapshot, ensure_ascii=False, default=str)
        if existing is None:
            dl_training_task_store.create_task(task_id, payload)
        else:
            dl_training_task_store.set_running(task_id, int(snapshot.get("progress", 0) * 100), payload)
    except Exception:
        pass


def get_prediction_status(task_id: str) -> dict | None:
    """获取预测任务状态。"""
    with _prediction_lock:
        task = _prediction_tasks.get(task_id)
        if task is not None:
            return task.copy()

    try:
        import json
        dl_training_task_store.init_db()
        row = dl_training_task_store.get_task(task_id)
        if row is None:
            return None
        payload = {}
        if row.get("result_json"):
            try:
                payload = json.loads(row["result_json"])
            except Exception:
                payload = {}
        if not payload and row.get("params_json"):
            try:
                payload = json.loads(row["params_json"])
            except Exception:
                payload = {}
        return {
            **payload,
            "task_id": task_id,
            "status": payload.get("status") or row.get("status"),
            "progress": payload.get("progress") if payload.get("progress") is not None else row.get("progress"),
        }
    except Exception:
        return None


def get_latest_prediction(model_name: str) -> dict | None:
    """返回某个模型最近一次完成的预测结果。"""
    import json
    dl_training_task_store.init_db()
    tasks = dl_training_task_store.list_tasks(limit=50)
    for row in tasks:
        result_json = row.get("result_json") or ""
        if not result_json:
            continue
        try:
            payload = json.loads(result_json)
        except Exception:
            continue
        if (
            payload.get("model") == model_name
            and payload.get("status") == "completed"
            and "predictions" in payload
        ):
            return payload
    return None




def get_training_status(task_id: str) -> dict | None:
    """获取训练任务状态"""
    with _training_lock:
        task = _training_tasks.get(task_id)
        if task is not None:
            return task.copy()
    return _get_persisted_training_task(task_id)
