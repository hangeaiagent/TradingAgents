# One-API + GeminiProxy 简化使用文档

## 目录

1. [环境变量配置](#1-环境变量配置)
2. [Key 格式说明](#2-key-格式说明)
3. [最小可用实现代码](#3-最小可用实现代码)
4. [调用示例](#4-调用示例)

---

## 1. 环境变量配置

```env
ONE_API_BASE_URL=http://104.197.139.51:3000/v1
ONE_API_KEY=sk-Nz1xxxxxxxxxxxxxxxxxx
ONE_API_GEMINI_MODEL=gemini-3-flash-preview
ONE_API_GEMINI_VISION_MODEL=gemini-3-flash-preview
```

| 变量 | 说明 |
|------|------|
| `ONE_API_BASE_URL` | One-API 服务地址，**必须包含 `/v1` 后缀**，不要加尾部斜杠 |
| `ONE_API_KEY` | One-API 后台生成的令牌，格式为 `sk-...` |
| `ONE_API_GEMINI_MODEL` | 文本任务模型名，必须与 One-API 后台渠道中配置的**别名完全一致** |
| `ONE_API_GEMINI_VISION_MODEL` | 图片分析模型名，同上 |

---

## 2. Key 格式说明

| Key 类型 | 前缀示例 | 用途 |
|---------|---------|------|
| One-API 令牌 | `sk-Nz1...` | 调用 One-API 网关，**本文使用** |
| Google 原生 Key | `AIzaSy...` | 直连 Google API，本文**不使用** |

> One-API 令牌在 One-API 后台「令牌」页面创建，格式固定为 `sk-` 开头。

---

## 3. 最小可用实现代码

依赖：`pip install openai`

```python
"""
one_api_gemini_proxy.py
最小化 One-API + Gemini 调用封装，无降级、有异常直接抛出。
"""

import base64
import json
import os
from typing import Dict, Any

import openai


class OneApiGeminiProxy:
    """
    通过 One-API 网关调用 Gemini 模型。
    使用 OpenAI 兼容接口，异常直接抛出，不做降级处理。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        text_model: str | None = None,
        vision_model: str | None = None,
    ):
        self.base_url = (base_url or os.environ["ONE_API_BASE_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["ONE_API_KEY"]
        self.text_model = text_model or os.environ.get(
            "ONE_API_GEMINI_MODEL", "gemini-3-flash-preview"
        )
        self.vision_model = vision_model or os.environ.get(
            "ONE_API_GEMINI_VISION_MODEL", "gemini-3-flash-preview"
        )

        if not self.api_key.startswith("sk-"):
            raise ValueError(
                f"ONE_API_KEY 格式错误：应以 'sk-' 开头，当前值前缀为 '{self.api_key[:8]}'"
            )

        self._client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    # ------------------------------------------------------------------
    # 文本生成
    # ------------------------------------------------------------------

    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> str:
        """
        单轮文本生成。

        Args:
            prompt: 用户输入文本
            temperature: 生成温度，越低越确定性
            max_tokens: 最大输出 token 数

        Returns:
            模型生成的文本内容

        Raises:
            openai.OpenAIError: One-API / 上游模型返回错误时抛出
        """
        response = self._client.chat.completions.create(
            model=self.text_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # 多轮对话
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """
        多轮对话（非流式）。

        Args:
            messages: 消息列表，格式 [{"role": "user/assistant", "content": "..."}]
            system_prompt: 系统提示词，可为空
            temperature: 生成温度
            max_tokens: 最大输出 token 数

        Returns:
            模型回复的文本内容

        Raises:
            openai.OpenAIError: One-API / 上游模型返回错误时抛出
        """
        api_messages: list[dict] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        response = self._client.chat.completions.create(
            model=self.text_model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """
        多轮对话（流式）。

        Yields:
            str: 每个流式文本块

        Raises:
            openai.OpenAIError: One-API / 上游模型返回错误时抛出
        """
        api_messages: list[dict] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        stream = self._client.chat.completions.create(
            model=self.text_model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ------------------------------------------------------------------
    # 图片分析（Vision）
    # ------------------------------------------------------------------

    def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> str:
        """
        图片分析（Vision）。

        Args:
            image_bytes: 图片二进制数据
            mime_type: 图片 MIME 类型，如 "image/jpeg"
            prompt: 分析提示词
            temperature: 生成温度
            max_tokens: 最大输出 token 数

        Returns:
            模型返回的分析文本

        Raises:
            openai.OpenAIError: One-API / 上游模型返回错误时抛出
        """
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{b64}"

        response = self._client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def analyze_image_as_json(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        图片分析，返回解析后的 JSON 对象。

        Raises:
            openai.OpenAIError: API 调用失败
            json.JSONDecodeError: 模型返回内容无法解析为 JSON
        """
        text = self.analyze_image(image_bytes, mime_type, prompt)
        # 去除可能的 markdown 代码块包裹
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(lines[1:-1])
        return json.loads(stripped)
```

---

## 4. 调用示例

### 文本生成

```python
proxy = OneApiGeminiProxy()

result = proxy.generate_text("用三句话解释量子纠缠")
print(result)
```

### 多轮对话（非流式）

```python
proxy = OneApiGeminiProxy()

history = [
    {"role": "user", "content": "你好，我想了解 Python 异步编程"},
    {"role": "assistant", "content": "Python 异步编程基于 asyncio，核心是 async/await..."},
    {"role": "user", "content": "能给一个具体例子吗？"},
]
reply = proxy.chat(history, system_prompt="你是一位 Python 专家，回答简洁清晰")
print(reply)
```

### 多轮对话（流式）

```python
proxy = OneApiGeminiProxy()

for chunk in proxy.chat_stream(
    messages=[{"role": "user", "content": "逐字讲解快速排序算法"}],
    system_prompt="你是算法教师",
):
    print(chunk, end="", flush=True)
```

### 图片分析

```python
proxy = OneApiGeminiProxy()

with open("screenshot.jpg", "rb") as f:
    image_bytes = f.read()

# 返回原始文本
text = proxy.analyze_image(
    image_bytes,
    mime_type="image/jpeg",
    prompt="描述这张图片中人物的面部表情",
)
print(text)

# 返回 JSON（要求 prompt 明确要求输出 JSON）
json_prompt = """分析面部表情，以 JSON 返回：
{"emotion": "平静/紧张/自信", "stress_level": 0-10, "notes": "简短说明"}
只返回 JSON，不要其他文字。"""

data = proxy.analyze_image_as_json(image_bytes, "image/jpeg", json_prompt)
print(data["emotion"], data["stress_level"])
```

### 异常处理示例

```python
import openai

proxy = OneApiGeminiProxy()

try:
    result = proxy.generate_text("你好")
except openai.AuthenticationError as e:
    print(f"Key 无效或已过期: {e}")
except openai.RateLimitError as e:
    print(f"触发限流: {e}")
except openai.APIConnectionError as e:
    print(f"无法连接 One-API 网关: {e}")
except openai.OpenAIError as e:
    print(f"其他 API 错误: {e}")
```
