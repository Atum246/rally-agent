"""
🟣 Rally Agent — COMPLETE Provider Registry
Every AI model provider on the planet. ALL of them.
"""

import os
import asyncio
from typing import Optional
from abc import ABC, abstractmethod

from cli.theme import Theme


class BaseProvider(ABC):
    """Base class for all LLM providers"""
    name: str = "unknown"
    description: str = ""
    requires_key: bool = True
    default_model: str = ""
    models: list[str] = []

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key
        self.base_url = kwargs.get("base_url", "")
        self.kwargs = kwargs

    @abstractmethod
    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        pass

    def get_models(self) -> list[str]:
        return self.models

    def is_available(self) -> bool:
        if self.requires_key:
            return bool(self.api_key)
        return True


# ═══════════════════════════════════════════════════════════════
# 🟢 TIER 1 — Major Cloud Providers
# ═══════════════════════════════════════════════════════════════

class OpenAIProvider(BaseProvider):
    name = "openai"
    description = "OpenAI — GPT-4o, GPT-4, o1, o3"
    default_model = "gpt-4o"
    models = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
        "o1", "o1-mini", "o1-pro", "o3", "o3-mini", "o4-mini",
        "gpt-4o-audio-preview", "gpt-4o-realtime-preview",
        "gpt-4o-search-preview", "gpt-4o-mini-search-preview",
        "chatgpt-4o-latest",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096), "temperature": kwargs.get("temperature", 0.7)}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    description = "Anthropic — Claude 4, Claude 3.5, Claude 3"
    default_model = "claude-sonnet-4-20250514"
    models = [
        "claude-opus-4-20250514", "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        system_msg = ""
        formatted = []
        for m in messages:
            if m.get("role") == "system":
                system_msg = m.get("content", "")
            else:
                formatted.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        body = {"model": model, "max_tokens": kwargs.get("max_tokens", 4096), "messages": formatted}
        if system_msg:
            body["system"] = system_msg
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]


class GoogleProvider(BaseProvider):
    name = "google"
    description = "Google — Gemini 2.5, Gemini 2.0, Gemini 1.5"
    default_model = "gemini-2.5-flash"
    models = [
        "gemini-2.5-pro", "gemini-2.5-flash",
        "gemini-2.0-flash", "gemini-2.0-flash-lite",
        "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        formatted = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            formatted.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        body = {"contents": formatted}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


class GoogleVertexProvider(BaseProvider):
    name = "google_vertex"
    description = "Google Vertex AI — Enterprise Gemini"
    default_model = "gemini-2.5-pro"
    models = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.project_id = kwargs.get("project_id", "")
        self.location = kwargs.get("location", "us-central1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        formatted = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            formatted.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        body = {"contents": formatted}
        url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model}:generateContent"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# ═══════════════════════════════════════════════════════════════
# ⚡ TIER 2 — Fast Inference Providers
# ═══════════════════════════════════════════════════════════════

class GroqProvider(BaseProvider):
    name = "groq"
    description = "Groq — Ultra-fast LPU inference"
    default_model = "llama-3.3-70b-versatile"
    models = [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
        "llama3-groq-8b-8192-tool-use-preview", "llama3-groq-70b-8192-tool-use-preview",
        "llama-guard-3-8b", "llama3-70b-8192", "llama3-8b-8192",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096, "temperature": 0.7}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class CerebrasProvider(BaseProvider):
    name = "cerebras"
    description = "Cerebras — Fastest inference on wafer-scale hardware"
    default_model = "llama-3.3-70b"
    models = ["llama-3.3-70b", "llama-3.1-8b"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.cerebras.ai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class SambaNovaProvider(BaseProvider):
    name = "sambanova"
    description = "SambaNova — Fast inference on RDU chips"
    default_model = "Meta-Llama-3.3-70B-Instruct"
    models = ["Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-8B-Instruct", "DeepSeek-V3-0324"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.sambanova.ai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class FireworksProvider(BaseProvider):
    name = "fireworks"
    description = "Fireworks AI — Fast open model inference"
    default_model = "accounts/fireworks/models/llama-v3p3-70b-instruct"
    models = [
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "accounts/fireworks/models/deepseek-v3",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
        "accounts/fireworks/models/mixtral-8x22b-instruct",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class TogetherProvider(BaseProvider):
    name = "together"
    description = "Together AI — Open model inference platform"
    default_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    models = [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "google/gemma-2-27b-it",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.together.xyz/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🔀 TIER 3 — Aggregators & Routers
# ═══════════════════════════════════════════════════════════════

class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    description = "OpenRouter — 300+ models, one API"
    default_model = "anthropic/claude-sonnet-4"
    models = [
        "anthropic/claude-sonnet-4", "anthropic/claude-opus-4",
        "anthropic/claude-3.5-sonnet", "openai/gpt-4o", "openai/gpt-4o-mini",
        "google/gemini-2.5-pro", "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat",
        "mistralai/mistral-large", "qwen/qwen-2.5-72b-instruct",
        "cohere/command-r-plus", "perplexity/sonar-pro",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://rally-agent.dev"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class UnifyProvider(BaseProvider):
    name = "unify"
    description = "Unify AI — Optimal model routing"
    default_model = "openai/gpt-4o"
    models = ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash", "meta-llama/llama-3.3-70b-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.unify.ai/v0/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class PortkeyProvider(BaseProvider):
    name = "portkey"
    description = "Portkey AI — Gateway to 200+ LLMs"
    default_model = "gpt-4o"
    models = ["gpt-4o", "claude-3.5-sonnet", "gemini-2.0-flash", "llama-3.3-70b"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"x-portkey-api-key": self.api_key, "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.portkey.ai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🏠 TIER 4 — Local & Self-Hosted
# ═══════════════════════════════════════════════════════════════

class OllamaProvider(BaseProvider):
    name = "ollama"
    description = "Ollama — Run models locally"
    requires_key = False
    default_model = "llama3.2"
    models = ["llama3.2", "llama3.1", "mistral", "mixtral", "codellama", "phi3", "gemma2", "qwen2.5", "deepseek-v2"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.host = kwargs.get("host", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "stream": False}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.host}/api/chat", json=body)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    def get_models(self) -> list[str]:
        try:
            import httpx
            resp = httpx.get(f"{self.host}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return self.models


class LMStudioProvider(BaseProvider):
    name = "lmstudio"
    description = "LM Studio — Local model server"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:1234/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        headers = {"Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class VLLMProvider(BaseProvider):
    name = "vllm"
    description = "vLLM — High-throughput LLM serving"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:8000/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class TextGenWebUIProvider(BaseProvider):
    name = "textgen"
    description = "text-generation-webui — Oobabooga local"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:5000/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"mode": "instruct", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class JanProvider(BaseProvider):
    name = "jan"
    description = "Jan — Local AI platform"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:1337/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class GPT4AllProvider(BaseProvider):
    name = "gpt4all"
    description = "GPT4All — Local AI on any device"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:4891/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class LlamaCppProvider(BaseProvider):
    name = "llamacpp"
    description = "llama.cpp — C++ inference server"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "http://localhost:8080/v1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🌏 TIER 5 — International Providers
# ═══════════════════════════════════════════════════════════════

class MistralProvider(BaseProvider):
    name = "mistral"
    description = "Mistral AI — European AI leader"
    default_model = "mistral-large-latest"
    models = [
        "mistral-large-latest", "mistral-medium-latest", "mistral-small-latest",
        "codestral-latest", "pixtral-large-latest",
        "open-mistral-nemo", "open-codestral-mamba",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    description = "DeepSeek — Chinese AI powerhouse"
    default_model = "deepseek-chat"
    models = ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class QwenProvider(BaseProvider):
    name = "qwen"
    description = "Alibaba Qwen — Chinese language models"
    default_model = "qwen-max"
    models = ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", "qwen2.5-72b-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "input": {"messages": formatted}, "parameters": {"max_tokens": 4096}}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["output"]["choices"][0]["message"]["content"]


class BaiduProvider(BaseProvider):
    name = "baidu"
    description = "Baidu ERNIE — Chinese AI"
    default_model = "ernie-4.0-turbo"
    models = ["ernie-4.0-turbo", "ernie-4.0", "ernie-3.5", "ernie-speed"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"messages": formatted}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{model}?access_token={self.api_key}", json=body)
            resp.raise_for_status()
            return resp.json()["result"]


class ZhipuProvider(BaseProvider):
    name = "zhipu"
    description = "Zhipu AI (GLM) — Chinese language models"
    default_model = "glm-4"
    models = ["glm-4", "glm-4-flash", "glm-4v", "glm-3-turbo"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class MoonshotProvider(BaseProvider):
    name = "moonshot"
    description = "Moonshot AI (Kimi) — Long context Chinese AI"
    default_model = "moonshot-v1-128k"
    models = ["moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.moonshot.cn/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class YiProvider(BaseProvider):
    name = "yi"
    description = "01.AI Yi — Chinese language models"
    default_model = "yi-large"
    models = ["yi-large", "yi-medium", "yi-spark", "yi-large-turbo"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.lingyiwanwu.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class CohereProvider(BaseProvider):
    name = "cohere"
    description = "Cohere — Enterprise AI platform"
    default_model = "command-r-plus"
    models = ["command-r-plus", "command-r", "command", "command-nightly"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = []
        for m in messages:
            formatted.append({"role": m.get("role", "user"), "message": m.get("content", "")})
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.cohere.ai/v1/chat", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["text"]


class VoyageProvider(BaseProvider):
    name = "voyage"
    description = "Voyage AI — Embeddings specialist"
    default_model = "voyage-3"
    models = ["voyage-3", "voyage-3-large", "voyage-code-3", "voyage-finance-2"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        return "Voyage AI is an embeddings provider. Use for vector search, not chat."


class AI21Provider(BaseProvider):
    name = "ai21"
    description = "AI21 Labs — Jamba models"
    default_model = "jamba-1.5-large"
    models = ["jamba-1.5-large", "jamba-1.5-mini", "jamba-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.ai21.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class PerplexityProvider(BaseProvider):
    name = "perplexity"
    description = "Perplexity AI — Search-augmented AI"
    default_model = "sonar-pro"
    models = ["sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-reasoning", "sonar-deep-research"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.perplexity.ai/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class ReplicateProvider(BaseProvider):
    name = "replicate"
    description = "Replicate — Run any ML model"
    default_model = "meta/llama-3.3-70b-instruct"
    models = ["meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct", "mistralai/mixtral-8x7b-instruct-v0.1"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"input": {"prompt": formatted[-1]["content"], "max_tokens": 4096}}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"https://api.replicate.com/v1/models/{model}/predictions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["output"]


class HuggingFaceProvider(BaseProvider):
    name = "huggingface"
    description = "Hugging Face — Open model hub"
    default_model = "meta-llama/Llama-3.3-70B-Instruct"
    models = ["meta-llama/Llama-3.3-70B-Instruct", "mistralai/Mixtral-8x7B-Instruct-v0.1", "google/gemma-2-27b-it"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class XAIProvider(BaseProvider):
    name = "xai"
    description = "xAI (Grok) — Elon's AI"
    default_model = "grok-3"
    models = ["grok-3", "grok-3-mini", "grok-2", "grok-2-mini"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.x.ai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class AmazonBedrockProvider(BaseProvider):
    name = "bedrock"
    description = "Amazon Bedrock — AWS AI platform"
    default_model = "anthropic.claude-sonnet-4-20250514-v1:0"
    models = ["anthropic.claude-sonnet-4-20250514-v1:0", "anthropic.claude-3-5-haiku-20241022-v1:0", "meta.llama3-3-70b-instruct-v1:0"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.region = kwargs.get("region", "us-east-1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        return "Amazon Bedrock requires AWS SDK (boto3). Configure AWS credentials separately."


class AzureOpenAIProvider(BaseProvider):
    name = "azure"
    description = "Azure OpenAI — Microsoft AI platform"
    default_model = "gpt-4o"
    models = ["gpt-4o", "gpt-4", "gpt-35-turbo"]

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key, **kwargs)
        self.endpoint = kwargs.get("endpoint", "")
        self.api_version = kwargs.get("api_version", "2024-02-15-preview")

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        model = model or self.default_model
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.endpoint}/openai/deployments/{model}/chat/completions?api-version={self.api_version}", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class CustomOpenAIProvider(BaseProvider):
    name = "custom"
    description = "Custom — Any OpenAI-compatible endpoint"
    default_model = "default"
    models = ["default"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs) -> str:
        import httpx
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": 4096}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🎯 Provider Manager — Auto-selects best available
# ═══════════════════════════════════════════════════════════════

class ProviderManager:
    """Manages all LLM providers — auto-selects the best one"""

    ALL_PROVIDERS = {
        # Tier 1 — Major Cloud
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        "google_vertex": GoogleVertexProvider,
        # Tier 2 — Fast Inference
        "groq": GroqProvider,
        "cerebras": CerebrasProvider,
        "sambanova": SambaNovaProvider,
        "fireworks": FireworksProvider,
        "together": TogetherProvider,
        # Tier 3 — Aggregators
        "openrouter": OpenRouterProvider,
        "unify": UnifyProvider,
        "portkey": PortkeyProvider,
        # Tier 4 — Local
        "ollama": OllamaProvider,
        "lmstudio": LMStudioProvider,
        "vllm": VLLMProvider,
        "textgen": TextGenWebUIProvider,
        "jan": JanProvider,
        "gpt4all": GPT4AllProvider,
        "llamacpp": LlamaCppProvider,
        # Tier 5 — International
        "mistral": MistralProvider,
        "deepseek": DeepSeekProvider,
        "qwen": QwenProvider,
        "baidu": BaiduProvider,
        "zhipu": ZhipuProvider,
        "moonshot": MoonshotProvider,
        "yi": YiProvider,
        "cohere": CohereProvider,
        "voyage": VoyageProvider,
        "ai21": AI21Provider,
        "perplexity": PerplexityProvider,
        "replicate": ReplicateProvider,
        "huggingface": HuggingFaceProvider,
        "xai": XAIProvider,
        "bedrock": AmazonBedrockProvider,
        "azure": AzureOpenAIProvider,
        "custom": CustomOpenAIProvider,
    }

    def __init__(self, config):
        self.config = config
        self.providers: dict[str, BaseProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize all available providers"""
        keys = self.config.get_provider_keys()

        # Map env vars to provider names
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "together": "TOGETHER_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "unify": "UNIFY_API_KEY",
            "portkey": "PORTKEY_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY",
            "baidu": "BAIDU_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "yi": "YI_API_KEY",
            "cohere": "COHERE_API_KEY",
            "ai21": "AI21_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "replicate": "REPLICATE_API_TOKEN",
            "huggingface": "HUGGINGFACE_API_KEY",
            "xai": "XAI_API_KEY",
            "bedrock": "AWS_BEARER_TOKEN",
            "azure": "AZURE_OPENAI_API_KEY",
        }

        for provider_name, provider_class in self.ALL_PROVIDERS.items():
            # Check config or env for API key
            api_key = keys.get(provider_name, "")
            if not api_key:
                env_var = env_map.get(provider_name, "")
                if env_var:
                    api_key = os.environ.get(env_var, "")

            # For custom provider, check base_url
            if provider_name == "custom":
                base_url = keys.get("custom_base_url", os.environ.get("CUSTOM_API_BASE", ""))
                if base_url:
                    provider = provider_class(api_key=api_key, base_url=base_url)
                    self.providers[provider_name] = provider
                continue

            # Initialize if key exists or no key required
            if api_key or not provider_class.requires_key:
                kwargs = {}
                # Special configs
                if provider_name == "google_vertex":
                    kwargs["project_id"] = keys.get("vertex_project_id", os.environ.get("VERTEX_PROJECT_ID", ""))
                    kwargs["location"] = keys.get("vertex_location", os.environ.get("VERTEX_LOCATION", "us-central1"))
                if provider_name == "azure":
                    kwargs["endpoint"] = keys.get("azure_endpoint", os.environ.get("AZURE_OPENAI_ENDPOINT", ""))
                if provider_name in ("ollama", "lmstudio", "vllm", "textgen", "jan", "gpt4all", "llamacpp"):
                    kwargs["host"] = keys.get(f"{provider_name}_host", "")
                    kwargs["base_url"] = keys.get(f"{provider_name}_base_url", "")

                provider = provider_class(api_key=api_key, **kwargs)
                self.providers[provider_name] = provider

    def get_available(self) -> list[str]:
        """Get list of available providers"""
        return [name for name, p in self.providers.items() if p.is_available()]

    def get_all_info(self) -> list[dict]:
        """Get info about all providers"""
        result = []
        for name, provider_class in self.ALL_PROVIDERS.items():
            p = self.providers.get(name)
            result.append({
                "name": name,
                "description": provider_class.description,
                "models": provider_class.models,
                "available": p is not None and p.is_available(),
                "requires_key": provider_class.requires_key,
            })
        return result

    async def chat(self, messages: list[dict], model: str = "auto", **kwargs) -> str:
        """Send chat using best available provider"""
        if model == "auto":
            return await self._auto_chat(messages, **kwargs)

        # Find provider for specific model
        for name, provider in self.providers.items():
            if model in provider.get_models():
                return await provider.chat(messages, model=model, **kwargs)

        # Try first available
        if self.providers:
            name, provider = next(iter(self.providers.items()))
            return await provider.chat(messages, model=model, **kwargs)

        raise RuntimeError("No AI providers configured. Set an API key to get started.")

    async def _auto_chat(self, messages: list[dict], **kwargs) -> str:
        """Auto-select best provider"""
        fallback_order = self.config.get("agent.auto_model.fallback_order", [
            "anthropic", "openai", "google", "groq", "openrouter", "deepseek", "mistral", "together", "fireworks", "ollama"
        ])

        for provider_name in fallback_order:
            if provider_name in self.providers:
                provider = self.providers[provider_name]
                try:
                    models = provider.get_models()
                    model = models[0] if models else "default"
                    return await provider.chat(messages, model=model, **kwargs)
                except Exception as e:
                    Theme.warning(f"{provider_name} failed: {e}")
                    continue

        # Last resort
        for name, provider in self.providers.items():
            try:
                models = provider.get_models()
                model = models[0] if models else "default"
                return await provider.chat(messages, model=model, **kwargs)
            except Exception:
                continue

        raise RuntimeError("All providers failed. Check your API keys.")
