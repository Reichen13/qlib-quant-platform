"""
LLM Provider 抽象层

支持 OpenAI-compatible API（DeepSeek/Qwen/GLM 等）。
支持服务器级环境变量配置 + 用户级 per-request API key。
无 LLM 配置时，所有 AI 端点返回 503 + 配置指引。
"""

import os
import json
import re
from dataclasses import dataclass, field
from typing import Optional, Type, TypeVar

from loguru import logger

T = TypeVar("T")


@dataclass
class LLMConfig:
    """LLM 配置。

    优先级：构造函数参数 > 环境变量 > 默认值。
    用户可以从前端传入 api_key/base_url 覆盖服务器环境变量。
    """
    base_url: str = ""
    api_key: str = ""
    quick_model: str = "deepseek-chat"
    deep_model: str = "deepseek-reasoner"
    temperature: float = 0.1
    max_retries: int = 2

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        quick_model: str = "",
        deep_model: str = "",
        temperature: float = 0.1,
        max_retries: int = 2,
    ):
        # 参数 > 环境变量 > 默认值
        env_base_url = os.getenv("LLM_BASE_URL", "")
        env_api_key = os.getenv("LLM_API_KEY", "")
        env_quick = os.getenv("LLM_QUICK_MODEL", "deepseek-chat")
        env_deep = os.getenv("LLM_DEEP_MODEL", "deepseek-reasoner")
        env_temp = float(os.getenv("LLM_TEMPERATURE", "0.1"))

        self.base_url = base_url or env_base_url
        self.api_key = api_key or env_api_key
        self.quick_model = quick_model or env_quick
        self.deep_model = deep_model or env_deep
        self.temperature = temperature if base_url or api_key else env_temp
        self.max_retries = max_retries

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls()


# 全局服务器级单例
_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    """获取服务器级 LLM 配置（从环境变量）"""
    global _config
    if _config is None:
        _config = LLMConfig.from_env()
    return _config


class LLMNotConfiguredError(Exception):
    """LLM 未配置时抛出的异常"""

    def __init__(self):
        super().__init__(
            "LLM 未配置。请在设置页面输入您的 API Key，或联系管理员配置服务器级 LLM。\n"
            "支持的提供商：OpenAI、DeepSeek、Qwen、GLM 等 OpenAI-compatible API。\n"
            "示例 Base URL:\n"
            "  DeepSeek: https://api.deepseek.com/v1\n"
            "  OpenAI:   https://api.openai.com/v1\n"
            "  Qwen:     https://dashscope.aliyuncs.com/compatible-mode/v1"
        )


class LLMClient:
    """统一的 LLM 客户端。

    每次调用 get_quick_llm() / get_deep_llm() 创建新的 ChatOpenAI 实例，
    以支持 per-request API key（不缓存）。
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_llm_config()

    def _ensure_configured(self):
        if not self.config.is_configured:
            raise LLMNotConfiguredError()

    def _build_llm(self, model: str):
        """创建 ChatOpenAI 实例（每次新建，不缓存）"""
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=model,
            temperature=self.config.temperature,
            max_retries=self.config.max_retries,
        )

    def get_quick_llm(self):
        """低延迟模型，用于数据采集、情感分析等"""
        self._ensure_configured()
        return self._build_llm(self.config.quick_model)

    def get_deep_llm(self):
        """强推理模型，用于最终决策、辩论裁判等"""
        self._ensure_configured()
        return self._build_llm(self.config.deep_model)

    def invoke_structured(
        self,
        prompt: str,
        output_schema: Type[T],
        *,
        use_deep: bool = False,
        system_prompt: str = "",
    ) -> T:
        """结构化输出：LLM → Pydantic 模型，失败时降级为自由文本解析

        Args:
            prompt: 用户提示
            output_schema: 目标 Pydantic 模型类
            use_deep: 是否使用深度推理模型
            system_prompt: 系统提示

        Returns:
            Pydantic 模型实例
        """
        self._ensure_configured()

        llm = self.get_deep_llm() if use_deep else self.get_quick_llm()

        # 尝试 structured output（需要模型支持）
        try:
            structured_llm = llm.with_structured_output(output_schema)
            messages = []
            if system_prompt:
                messages.append(("system", system_prompt))
            messages.append(("user", prompt))
            result = structured_llm.invoke(messages)
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"结构化输出失败，降级为自由文本解析: {e}")

        # 降级：自由文本 → JSON 解析
        fallback_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + (
            f"{prompt}\n\n"
            f"请以 JSON 格式返回结果，字段与以下 schema 一致：\n"
            f"{output_schema.model_json_schema()}\n"
            f"只返回 JSON，不要包含其他文字。"
        )
        response = llm.invoke(fallback_prompt)
        text = response.content if hasattr(response, "content") else str(response)

        # 提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return output_schema(**data)
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"JSON 解析失败: {e}, text={text[:200]}")

        raise RuntimeError(f"无法将 LLM 输出解析为 {output_schema.__name__}: {text[:300]}")


# ── 便捷函数 ──

_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取服务器默认 LLM 客户端（使用环境变量配置）"""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def create_llm_client(
    api_key: str,
    base_url: str = "",
    quick_model: str = "",
    deep_model: str = "",
) -> LLMClient:
    """用 per-request API key 创建 LLM 客户端。

    用户在前端 Settings 页面输入自己的 key 后，后端按请求创建独立客户端。
    用户的 key 优先于服务器环境变量。
    """
    config = LLMConfig(
        api_key=api_key,
        base_url=base_url,
        quick_model=quick_model,
        deep_model=deep_model,
    )
    return LLMClient(config=config)
