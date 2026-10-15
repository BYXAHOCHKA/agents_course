import os

import httpx


class Model:
    def __init__(self):
        self.name = os.environ.get("MODEL_NAME", "tmp/models/qwen3-0.6b")
        self.url = os.environ.get("MODEL_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        self.client = httpx.Client(timeout=90)

    def call(self, messages, seed):
        response = self.client.post(
            self.url + "/chat/completions",
            json={
                "model": self.name,
                "messages": messages,
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 20,
                "max_tokens": 160,
                "seed": seed,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        if "prompt_tokens" not in usage or "completion_tokens" not in usage:
            raise ValueError("Сервер модели не вернул usage с числом токенов.")
        return {
            "text": data["choices"][0]["message"].get("content") or "",
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "finish_reason": data["choices"][0].get("finish_reason"),
            "model": data.get("model", self.name),
        }
