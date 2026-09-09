# src/llm_client.py
import os
import json
from openai import OpenAI


class LLMClient:
    def __init__(self, api_key: str = None, model: str = None):
        self.provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
        if self.provider == "codex":
            with open(os.path.expanduser("~/.codex/auth.json"), encoding="utf-8") as auth_file:
                tokens = json.load(auth_file).get("tokens", {})
            self.api_key = api_key or tokens.get("access_token")
            if not self.api_key:
                raise ValueError("Codex OAuth access_token is required")
            account_id = tokens.get("account_id")
            client_kwargs = {
                "api_key": self.api_key,
                "base_url": "https://chatgpt.com/backend-api/codex",
            }
            if account_id:
                client_kwargs["default_headers"] = {"ChatGPT-Account-Id": account_id}
            self.client = OpenAI(**client_kwargs)
            self.model = model or os.getenv("CODEX_MODEL", "gpt-5.6-terra")
        else:
            self.provider = "deepseek"
            self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
            if not self.api_key:
                raise ValueError("DEEPSEEK_API_KEY is required")
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com/v1"
            )
            self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    def chat(self, prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
        """Return a chat completion from the configured LLM provider."""
        if self.provider == "codex":
            response = self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=[{"role": "user", "content": prompt}],
                reasoning={"effort": "low"},
                store=False,
                stream=True,
            )
            output_text = getattr(response, "output_text", None)
            if isinstance(output_text, str):
                return output_text
            return "".join(
                delta
                for event in response
                if getattr(event, "type", None) == "response.output_text.delta"
                if isinstance((delta := getattr(event, "delta", None)), str)
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,  # 低温度保证结构化输出稳定
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response.choices[0].message.content
