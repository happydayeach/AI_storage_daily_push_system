# src/llm_client.py
import os
from openai import OpenAI

class DeepSeekClient:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        # DeepSeek's standard chat model remains the default, but deployments may override it.
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def chat(self, prompt: str, system_prompt: str = "", max_tokens: int = 2000) -> str:
        """General DeepSeek chat interface without provider-specific search options."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,  # 低温度保证结构化输出稳定
            stream=False
        )
        return response.choices[0].message.content
