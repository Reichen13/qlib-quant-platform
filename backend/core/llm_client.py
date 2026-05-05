"""
LLM Provider 抽象层

支持 OpenAI-compatible API（DeepSeek/Qwen/GLM 等）。
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
    """LLM 配置，从环境变量加载"""
    base_url: str = ""
    api_key: str = ""
    quick_model: str = "deepseek-chat"
    deep_model: str = "deepseek-reasoner"
    temperature: float = 0.1
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.getenv("LLM_BASE_URL", ""),
            api_key=os.getenv("LLM_API_KEY", ""),
            quick_model=os.getenv("LLM_QUICK_MODEL", "deepseek-chat"),
            deep_model=os.getenv("LLM_DEEP_MODEL", "deepseek-reasoner"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        )


# 全局单例
_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    global _config
    if _config is None:
        _config = LLMConfig.from_env()
    return _config


class LLMNotConfiguredError(Exception):
    """LLM 未配置时抛出的异常"""

    def __init__(self):
        super().__init__(
            "LLM 未配置。请设置环境变量 LLM_BASE_URL 和 LLM_API_KEY。\n"
            "示例:\n"
            "  export LLM_BASE_URL=https://api.deepseek.com/v1\n"
            "  export LLM_API_KEY=sk-your-key\n"
            "  export LLM_QUICK_MODEL=deepseek-chat      # 可选\n"
            "  export LLM_DEEP_MODEL=deepseek-reasoner   # 可选"
        )


class LLMClient:
    """统一的 LLM 客户端"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_llm_config()
        self._quick_llm = None
        self._deep_llm = None

    def _ensure_configured(self):
        if not self.config.is_configured:
            raise LLMNotConfiguredError()

    def get_quick_llm(self):
        """低延迟模型，用于数据采集、情感分析等"""
        self._ensure_configured()
        if self._quick_llm is None:
            from langchain_openai import ChatOpenAI
            self._quick_llm = ChatOpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                model=self.config.quick_model,
                temperature=self.config.temperature,
                max_retries=self.config.max_retries,
            )
        return self._quick_llm

    def get_deep_llm(self):
        """强推理模型，用于最终决策、辩论裁判等"""
        self._ensure_configured()
        if self._deep_llm is None:
            from langchain_openai import ChatOpenAI
            self._deep_llm = ChatOpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                model=self.config.deep_model,
                temperature=self.config.temperature,
                max_retries=self.config.max_retries,
            )
        return self._deep_llm

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


# 模块级便捷函数
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
