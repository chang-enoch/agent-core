# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""死响应（empty + zero-usage）判定与抛错路径测试。

死响应 = 网关/代理合成的空 200（content/tool_calls/reasoning 全空且
零 token 用量），修复前被 ReAct 当正常终答收下，任务永久挂起。
"""

import pytest

from openjiuwen.core.foundation.llm import AssistantMessage
from openjiuwen.core.foundation.llm.schema.message import UsageMetadata
from openjiuwen.core.single_agent.agents.react_agent import (
    _is_dead_model_response,
    _raise_dead_model_response,
)
from openjiuwen.harness.rails.llm_retry_rail import LLMRetryRail


def _usage(input_tokens: int = 0, output_tokens: int = 0) -> UsageMetadata:
    return UsageMetadata(
        model_name="m",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _msg(**kwargs) -> AssistantMessage:
    defaults = dict(content="", tool_calls=[], reasoning_content=None, usage_metadata=None)
    defaults.update(kwargs)
    return AssistantMessage(**defaults)


class TestIsDeadModelResponse:
    """判定矩阵：宁漏不误——任一说话通道非空或用量缺失即放过。"""

    def test_empty_with_zero_usage_is_dead(self):
        assert _is_dead_model_response(_msg(usage_metadata=_usage(0, 0))) is True

    def test_empty_with_usage_absent_is_not_dead(self):
        # provider 不上报用量：无法区分合法空答与故障，保守放过
        assert _is_dead_model_response(_msg()) is False

    def test_empty_with_real_input_usage_is_not_dead(self):
        # content_filter 类应答：模型真处理过（input>0）但没说话
        assert _is_dead_model_response(_msg(usage_metadata=_usage(100, 0))) is False

    def test_content_present_is_not_dead(self):
        assert _is_dead_model_response(_msg(content="你好", usage_metadata=_usage(0, 0))) is False

    def test_tool_calls_present_is_not_dead(self):
        tc = [{"id": "1", "type": "function", "name": "t", "arguments": "{}"}]
        assert _is_dead_model_response(_msg(tool_calls=tc, usage_metadata=_usage(0, 0))) is False

    def test_reasoning_present_is_not_dead(self):
        # reasoning 模型纯思考帧
        assert _is_dead_model_response(_msg(reasoning_content="thinking", usage_metadata=_usage(0, 0))) is False


class TestRaiseDeadModelResponse:
    """抛错契约：MODEL_CALL_FAILED + marker 命中 LLMRetryRail 既有分类。"""

    @pytest.mark.parametrize("path,marker", [
        ("invoke", "async invoke error"),
        ("stream", "async stream error"),
    ])
    def test_raises_with_retry_rail_marker(self, path, marker):
        with pytest.raises(Exception) as exc_info:
            _raise_dead_model_response(path, "no content/tool_calls/reasoning, zero token usage")
        assert marker in str(exc_info.value)
        # 钉死关键契约：LLMRetryRail._is_model_call_failed_exception 必须命中，
        # 否则重试链断（退化为直接穿透，仍优于静默但失自愈）
        assert LLMRetryRail._is_model_call_failed_exception(exc_info.value) is True

    def test_zero_chunks_reason(self):
        with pytest.raises(Exception) as exc_info:
            _raise_dead_model_response("stream", "connection closed with zero chunks")
        assert "async stream error" in str(exc_info.value)
        assert "zero chunks" in str(exc_info.value)
