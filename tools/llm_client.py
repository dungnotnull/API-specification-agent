"""UnifiedLLMClient — Claude / OpenAI / Ollama with streaming, retry, and cost tracking."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import AsyncIterator, Optional

ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)


def get_prompt_manager():
    """Get the global prompt template manager."""
    from tools.prompt_templates import get_prompt_manager
    return get_prompt_manager()

COST_PER_1K: dict[str, dict[str, float]] = {
    "claude-opus-4-8":    {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-6":  {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5":   {"input": 0.00025, "output": 0.00125},
    "gpt-4o":             {"input": 0.005, "output": 0.015},
    "gpt-4o-mini":        {"input": 0.00015, "output": 0.0006},
    "llama3":             {"input": 0.0, "output": 0.0},
    "mistral":            {"input": 0.0, "output": 0.0},
}

PROVIDER_PRIORITY = ["claude", "openai", "ollama"]


class LLMError(Exception):
    pass


class AllProvidersExhausted(LLMError):
    pass


class UnifiedLLMClient:
    """
    Unified client for Claude (primary), OpenAI (fallback), Ollama (offline).

    Provider selection:
    - PRIVACY_MODE=true → Ollama only
    - ANTHROPIC_API_KEY set → Claude first
    - OPENAI_API_KEY set → OpenAI as fallback
    - OLLAMA_BASE_URL set → Ollama as final fallback
    """

    def __init__(self):
        self._anthropic_client = None
        self._openai_client = None
        self._memory = None

        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        self.ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.privacy_mode = os.getenv("PRIVACY_MODE", "false").lower() == "true"

    def _get_memory(self):
        if self._memory is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from agent.memory.memory_manager import MemoryManager
            self._memory = MemoryManager()
        return self._memory

    def _get_anthropic(self):
        if self._anthropic_client is None:
            import anthropic
            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY", "")
            )
        return self._anthropic_client

    def _get_openai(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        return self._openai_client

    async def complete(
        self,
        system: str = None,
        user: str = "",
        task: str = "general",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """
        Generate a completion using the provider chain.

        Args:
            system: System prompt (if None, uses template from task)
            user: User message
            task: Task identifier for prompt template lookup
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Raises AllProvidersExhausted if all providers fail.
        """
        # Use prompt template if system not provided
        if system is None:
            system = get_prompt_manager().get_prompt(task)

        if self.privacy_mode:
            return await self._call_ollama_with_retry(system, user, max_tokens, temperature)

        providers = self._build_provider_chain()
        last_error = None

        for provider in providers:
            try:
                if provider == "claude":
                    result, in_tok, out_tok = await self._call_with_retry(
                        self._call_claude, system, user, max_tokens, temperature
                    )
                    self._log_cost("claude", self.claude_model, task, in_tok, out_tok)
                    return result
                elif provider == "openai":
                    result, in_tok, out_tok = await self._call_with_retry(
                        self._call_openai, system, user, max_tokens, temperature
                    )
                    self._log_cost("openai", self.openai_model, task, in_tok, out_tok)
                    return result
                elif provider == "ollama":
                    result = await self._call_ollama_with_retry(system, user, max_tokens, temperature)
                    return result
            except Exception as e:
                logger.warning("Provider %s failed for task '%s': %s", provider, task, e)
                last_error = e

        raise AllProvidersExhausted(f"All providers failed. Last error: {last_error}")

    async def stream(
        self,
        system: str = None,
        user: str = "",
        task: str = "general",
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream completion tokens from Claude (primary). Falls back to chunked non-streaming."""
        # Use prompt template if system not provided
        if system is None:
            system = get_prompt_manager().get_prompt(task)

        if not os.getenv("ANTHROPIC_API_KEY"):
            # Fallback: chunk the non-streaming response
            full = await self.complete(system, user, task, max_tokens)
            chunk_size = 20
            for i in range(0, len(full), chunk_size):
                yield full[i:i + chunk_size]
            return

        try:
            client = self._get_anthropic()
            async with client.messages.stream(
                model=self.claude_model,
                max_tokens=max_tokens,
                temperature=0.2,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.warning("Streaming failed, falling back to non-streaming: %s", e)
            full = await self.complete(system, user, task, max_tokens)
            chunk_size = 20
            for i in range(0, len(full), chunk_size):
                yield full[i:i + chunk_size]

    async def _call_claude(self, system: str, user: str, max_tokens: int, temperature: float):
        client = self._get_anthropic()
        response = await client.messages.create(
            model=self.claude_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        return text, in_tok, out_tok

    async def _call_openai(self, system: str, user: str, max_tokens: int, temperature: float):
        client = self._get_openai()
        response = await client.chat.completions.create(
            model=self.openai_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = response.choices[0].message.content
        in_tok = response.usage.prompt_tokens
        out_tok = response.usage.completion_tokens
        return text, in_tok, out_tok

    async def _call_ollama_with_retry(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        """Call Ollama with retry logic."""
        return await self._call_with_retry(
            self._call_ollama, system, user, max_tokens, temperature
        )

    async def _call_ollama(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        import aiohttp

        payload = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        url = f"{self.ollama_base}/api/chat"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    raise LLMError(f"Ollama returned HTTP {resp.status}")
                data = await resp.json()
        return (data.get("message") or {}).get("content", "")

    async def _call_with_retry(self, fn, system, user, max_tokens, temperature, max_retries=3):
        last_exc = None
        for attempt in range(max_retries):
            try:
                return await fn(system, user, max_tokens, temperature)
            except Exception as e:
                wait = 2 ** attempt
                logger.warning("LLM call attempt %d failed (%s); retrying in %ds", attempt + 1, e, wait)
                last_exc = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
        raise last_exc

    def _build_provider_chain(self) -> list[str]:
        chain = []
        if os.getenv("ANTHROPIC_API_KEY"):
            chain.append("claude")
        if os.getenv("OPENAI_API_KEY"):
            chain.append("openai")
        chain.append("ollama")
        return chain

    def _log_cost(self, provider: str, model: str, task: str, in_tok: int, out_tok: int):
        rates = COST_PER_1K.get(model, {"input": 0.0, "output": 0.0})
        cost = (in_tok / 1000) * rates["input"] + (out_tok / 1000) * rates["output"]
        try:
            self._get_memory().log_llm_cost(provider, task, in_tok, out_tok, cost)
        except Exception as e:
            logger.debug("Cost logging failed: %s", e)

    def complete_sync(self, system: str, user: str, task: str = "general", max_tokens: int = 2048) -> str:
        """Synchronous wrapper for use in non-async contexts."""
        return asyncio.run(self.complete(system, user, task, max_tokens))
