"""The curated provider set.

Upstream ships 33 provider profiles and this fork adds 10 more. Most of the
inherited ones are paid or enterprise backends — Bedrock, Vertex, Azure,
Anthropic, OpenAI — which are noise in a tool whose whole point is running on
free inference. A 46-item picker is not a feature; it is a menu you have to
read every time you switch models.

So the registry is filtered to providers that clear BOTH bars:

  1. a genuinely capable coding model, and
  2. a real free tier you can use today without a card

"Free trial credits that expire" and "good models behind a subscription" both
fail bar 2, and a free tier serving only small weak models fails bar 1.

Nothing is deleted. Everything still resolves by name, so `--provider bedrock`
keeps working and any config that already names one is unaffected — the
curation only decides what the picker OFFERS. Set FREEIDE_ALL_PROVIDERS=1 to
see the full list again.
"""

from __future__ import annotations

import os

# Ordered tiers. The picker renders them in this order, separated by a rule.
CURATED_TIERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "no signup",
        "Works right now, no account and no key",
        (
            # Qwen3-Coder-30B at 262k context, EU-hosted. Anonymous access is
            # 2 requests/min per IP — fine for a conversation, not for a batch.
            "ovhcloud",
        ),
    ),
    (
        "free key",
        "One free key, no card, genuinely usable for real work",
        (
            # gpt-oss-120b / qwen3.6-27b / minimax-m2.7 — the fastest free tier.
            "groq",
            # glm-5.2, deepseek-v4-flash, minimax-m3. Verified working.
            "nvidia",
            # zai-glm-4.7 and gpt-oss-120b at very high tokens/sec.
            "cerebras",
            # DeepSeek-V3.1 and MiniMax-M2.7 on a free tier.
            "sambanova",
            # Devstral 2 and Codestral — purpose-built for coding.
            "mistral",
            # gemini-3.6-flash on a generous AI Studio free tier.
            "gemini",
            # 15 verified :free models incl. cohere/north-mini-code and the
            # poolside/laguna coding family.
            "openrouter",
            # qwen3-coder-plus, 1M free tokens over 90 days.
            # Upstream ships this as "alibaba" and owns the "dashscope" alias.
            "alibaba",
        ),
    ),
    (
        "on your machine",
        "Fully offline, no quota at all",
        (
            "ollama-local",
        ),
    ),
)

#: Flat set of curated provider names.
CURATED: frozenset[str] = frozenset(
    name for _title, _blurb, names in CURATED_TIERS for name in names
)

# Deliberately excluded, with the reason. Kept as data so the rationale is
# reviewable rather than folded into a comment nobody reads.
EXCLUDED: dict[str, str] = {
    "githubmodels": "good models, but every tier caps a request at 8k in / 4k out — too small for real coding",
    "llm7": "no signup, but the keyless tier only serves small models",
    "nebius": "trial credits that expire, not an ongoing free tier",
    "zai": "strong GLM coding models, but paid/subscription",
    "deepseek": "paid API",
    "kimi-coding": "paid subscription",
    "anthropic": "paid API",
    "openai": "paid API",
    "openai-codex": "requires a paid ChatGPT plan",
    "copilot": "requires a paid Copilot subscription",
    "bedrock": "enterprise AWS billing",
    "vertex": "enterprise GCP billing",
    "azure-foundry": "enterprise Azure billing",
    "fireworks": "paid",
    "deepinfra": "paid",
    "novita": "paid",
    "gmi": "paid",
    "minimax": "paid direct API — reachable free via OpenRouter instead",
    "stepfun": "paid",
    "upstage": "paid",
    "xai": "paid",
    "xiaomi": "paid",
    "arcee": "paid",
    "huggingface": "free tier too rate-limited for agentic use",
    "ollama-cloud": "paid hosted tier — the local profile is the free one",
    "qwen-oauth": "overlaps dashscope, which has the clearer free quota",
    "alibaba-coding-plan": "paid subscription",
}


def show_all() -> bool:
    """True when the user has asked to see every registered provider."""
    return os.environ.get("FREEIDE_ALL_PROVIDERS", "").strip().lower() in {"1", "true", "yes"}


def is_curated(name: str) -> bool:
    return name in CURATED


def tier_of(name: str) -> str | None:
    """Which curated tier a provider belongs to, or None."""
    for title, _blurb, names in CURATED_TIERS:
        if name in names:
            return title
    return None
