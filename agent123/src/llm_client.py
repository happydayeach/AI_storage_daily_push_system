# src/llm_client.py
import os
from openai import OpenAI

class DeepSeekClient:
    def __init__(self, api_key: str = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = model

    def chat(self, prompt: str, system_prompt: str = "", enable_search: bool = False, max_tokens: int = 2000) -> str:
        """通用对话接口，支持联网搜索"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,  # 低温度保证结构化输出稳定
            enable_search=enable_search,  # 关键：开启联网
            stream=False
        )
        return response.choices[0].message.content
