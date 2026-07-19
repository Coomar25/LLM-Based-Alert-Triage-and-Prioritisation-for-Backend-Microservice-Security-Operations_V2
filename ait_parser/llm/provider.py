"""
Provider dispatch.

Selects the inference backend (local Ollama or hosted Groq) and exposes a
uniform interface so the runners don't need provider-specific code. Both
backends expose the same `generate()` -> LlmResponse and a health check, so
switching is a matter of choosing which module's functions to call.

Usage in a runner:
    from llm.provider import get_provider
    prov = get_provider("groq", model="llama-3.1-8b-instant")
    ok, msg = prov.check()
    resp = prov.generate(prompt)   # returns an LlmResponse

The --provider flag on the runners drives get_provider().
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from . import ollama_client
from . import groq_client
from . import gemini_client
from . import anthropic_client


# Default model per provider (used if --model not given).
DEFAULT_MODEL_BY_PROVIDER = {
    "ollama": ollama_client.DEFAULT_MODEL,          # "mistral"
    "groq": groq_client.DEFAULT_GROQ_MODEL,          # "llama-3.1-8b-instant"
    "gemini": gemini_client.DEFAULT_GEMINI_MODEL,    # "gemini-2.0-flash"
    "anthropic": anthropic_client.DEFAULT_ANTHROPIC_MODEL,  # "claude-haiku-4-5-..."
}


@dataclass
class Provider:
    """A resolved inference backend with a uniform interface."""
    name: str
    model: str
    _generate: Callable
    _check: Callable
    _url: str

    def generate(self, prompt: str):
        """Run one generation. Returns an LlmResponse (same shape for both)."""
        return self._generate(prompt, model=self.model, url=self._url)

    def check(self) -> Tuple[bool, str]:
        """Health-check the backend."""
        return self._check(model=self.model, url=self._url)


def get_provider(provider: str, model: Optional[str] = None,
                 ollama_url: Optional[str] = None) -> Provider:
    """Resolve a provider name into a Provider object.

    provider: "ollama" or "groq"
    model: model identifier; if None, the provider's default is used. Note the
           identifiers differ (e.g. ollama "llama3.1:8b" vs groq
           "llama-3.1-8b-instant").
    """
    provider = provider.lower()

    if provider == "ollama":
        return Provider(
            name="ollama",
            model=model or ollama_client.DEFAULT_MODEL,
            _generate=ollama_client.generate,
            _check=ollama_client.check_ollama,
            _url=ollama_url or ollama_client.DEFAULT_OLLAMA_URL,
        )

    if provider == "groq":
        return Provider(
            name="groq",
            model=model or groq_client.DEFAULT_GROQ_MODEL,
            _generate=groq_client.generate,
            _check=groq_client.check_groq,
            _url=groq_client.GROQ_URL,
        )

    if provider == "gemini":
        return Provider(
            name="gemini",
            model=model or gemini_client.DEFAULT_GEMINI_MODEL,
            _generate=gemini_client.generate,
            _check=gemini_client.check_gemini,
            # Gemini builds its endpoint from the model internally; pass None
            # so the client uses its URL template.
            _url=None,
        )

    if provider == "anthropic":
        return Provider(
            name="anthropic",
            model=model or anthropic_client.DEFAULT_ANTHROPIC_MODEL,
            _generate=anthropic_client.generate,
            _check=anthropic_client.check_anthropic,
            _url=anthropic_client.ANTHROPIC_URL,
        )

    raise ValueError(f"Unknown provider '{provider}'. "
                     f"Choose from: ollama, groq, gemini, anthropic")
