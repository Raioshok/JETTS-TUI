"""The curated provider set.

Upstream registers ~45 provider profiles. Most are enterprise plumbing —
Bedrock, Vertex, Azure Foundry — or thin resellers, and a 50-item picker is a
menu you re-read every time you switch models rather than a feature.

The bar here is QUALITY, not price: providers that actually serve a
best-in-class coding model. Cost is a SEPARATE axis, so the list is split into
two groups rather than filtered down to one:

  PAID  — the strongest models available, billed per token
  FREE  — no card required
  LOCAL — runs on your own machine

Nothing is deleted. Every provider still resolves by name, so `--provider
bedrock` and any existing config keep working — curation only decides what the
picker OFFERS. JETTSTUI_ALL_PROVIDERS=1 restores the full list.
"""

from __future__ import annotations

import os

# Ordered groups. The picker renders them in this order, separated by a rule.
CURATED_TIERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "paid",
        "Best models available, billed per token",
        (
            # deepseek-v4-pro / v4-flash. Frontier coding at a fraction of the
            # price of the US labs — the reason this group exists at all.
            "deepseek",
            # Claude — still the reference point for agentic coding.
            "anthropic",
            # GPT-5 class.
            "openai-api",
            # GLM-5.2: very strong coder, aggressive pricing.
            "zai",
            # Kimi K2 — long context, strong tool use.
            "kimi-coding",
            # MiniMax M2 class.
            "minimax",
            # Grok.
            "xai",
            # Fast OSS hosting (Kimi, DeepSeek, Qwen) when you want throughput.
            "fireworks",
        ),
    ),
    (
        "free",
        "No card required",
        (
            # gpt-oss-120b / qwen3.6-27b — the fastest free tier.
            "groq",
            # glm-5.2, deepseek-v4-flash. Verified working end to end.
            "nvidia",
            # zai-glm-4.7 and gpt-oss-120b at very high tokens/sec.
            "cerebras",
            # DeepSeek-V3.1 and MiniMax-M2.7 on a free tier.
            "sambanova",
            # Devstral 2 and Codestral — purpose-built for coding.
            "mistral",
            # gemini-3.6-flash on a generous AI Studio free tier.
            "gemini",
            # 15 verified :free ids incl. cohere/north-mini-code and the
            # poolside/laguna coding family. Also the cheapest paid gateway.
            "openrouter",
            # qwen3-coder-plus, 1M free tokens over 90 days.
            # Upstream ships this as "alibaba" and owns the "dashscope" alias.
            "alibaba",
            # Qwen3-Coder-30B at 262k context, EU-hosted.
            #
            # OVHcloud also serves this anonymously at 2 req/min, but only when
            # the request carries NO Authorization header — a placeholder token
            # returns 403. This fork's transport always sends credentials, so
            # the keyless path is not reachable here and a free token is needed.
            "ovhcloud",
        ),
    ),
    (
        "local",
        "Runs on your own machine, no quota at all",
        (
            "ollama-local",
        ),
    ),
)

#: Flat set of curated provider names.
CURATED: frozenset[str] = frozenset(
    name for _title, _blurb, names in CURATED_TIERS for name in names
)

# Hidden from the picker, with the reason. Kept as data so the rationale is
# reviewable rather than folded into a comment nobody reads. None of these are
# removed — they all still resolve by name.
EXCLUDED: dict[str, str] = {
    # Good models, wrong economics or wrong limits
    "githubmodels": "caps every tier at 8k in / 4k out per request — too small for real coding",
    "llm7": "no signup, but the keyless tier only serves small models",
    "nebius": "trial credits that expire rather than an ongoing tier",
    "huggingface": "free tier too rate-limited for agentic use",
    # Redundant with something already offered
    "minimax-cn": "China endpoint of minimax",
    "minimax-oauth": "OAuth variant of minimax",
    "kimi-coding-cn": "China endpoint of kimi-coding",
    "qwen-oauth": "overlaps alibaba, which has the clearer quota",
    "alibaba-coding-plan": "subscription variant of alibaba",
    "ollama-cloud": "hosted tier — ollama-local is the free one",
    "openai-codex": "requires a ChatGPT plan; openai-api is the direct route",
    "copilot": "requires a Copilot subscription",
    "copilot-acp": "Copilot transport variant",
    # Enterprise billing plumbing
    "bedrock": "enterprise AWS billing",
    "vertex": "enterprise GCP billing",
    "azure-foundry": "enterprise Azure billing",
    # Resellers and smaller hosts — nothing here you cannot get above
    "deepinfra": "reseller; OpenRouter covers the same models",
    "novita": "reseller",
    "gmi": "reseller",
    "arcee": "niche models",
    "stepfun": "niche models",
    "upstage": "niche models",
    "xiaomi": "niche models",
    "opencode-zen": "aggregator subscription",
    "opencode-go": "aggregator subscription",
    "kilocode": "aggregator subscription",
    "custom": "user-supplied endpoint, configured directly",
}


def show_all() -> bool:
    """True when the user has asked to see every registered provider."""
    return os.environ.get("JETTSTUI_ALL_PROVIDERS", "").strip().lower() in {"1", "true", "yes"}


def is_curated(name: str) -> bool:
    return name in CURATED


def tier_of(name: str) -> str | None:
    """Which curated group a provider belongs to, or None."""
    for title, _blurb, names in CURATED_TIERS:
        if name in names:
            return title
    return None
