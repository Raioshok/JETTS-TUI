from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from agent.model_metadata import fetch_endpoint_model_metadata, fetch_model_metadata
from utils import base_url_host_matches

DEFAULT_PRICING = {"input": 0.0, "output": 0.0}

_ZERO = Decimal("0")
_ONE_MILLION = Decimal("1000000")

CostStatus = Literal["actual", "estimated", "included", "unknown"]
CostSource = Literal[
    "provider_cost_api",
    "provider_generation_api",
    "provider_models_api",
    "official_docs_snapshot",
    "user_override",
    "custom_contract",
    "none",
]


@dataclass(frozen=True)
class CanonicalUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    request_count: int = 1
    # Anthropic reports which speed actually served the request in
    # ``usage.speed`` ("fast" | "standard"). It is authoritative for billing:
    # a fast-mode request made without preview access silently runs at standard
    # speed and is billed at *standard* rates, so the REQUEST flag cannot be
    # trusted, only this response field. None = the provider did not say.
    # https://platform.claude.com/docs/en/build-with-claude/fast-mode
    speed: Optional[str] = None
    raw_usage: Optional[dict[str, Any]] = None

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens

    def __add__(self, other: "CanonicalUsage") -> "CanonicalUsage":
        """Sum two usage buckets (e.g. MoA advisor fan-out + aggregator).

        ``raw_usage`` and ``speed`` are dropped on the sum — both describe a
        single API response. ``request_count`` adds so callers can see how many
        underlying API calls a combined figure covers.

        Note the consequence for cost: a bucket that mixes fast and standard
        calls is priced at *standard* rates (``speed`` becomes None), so a MoA
        fan-out that mixed speeds under-reports. Per-response costing — the
        normal path — is exact.
        """
        if not isinstance(other, CanonicalUsage):
            return NotImplemented
        return CanonicalUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            request_count=self.request_count + other.request_count,
            speed=self.speed if self.speed == other.speed else None,
            raw_usage=None,
        )


@dataclass(frozen=True)
class BillingRoute:
    provider: str
    model: str
    base_url: str = ""
    billing_mode: str = "unknown"


@dataclass(frozen=True)
class PricingEntry:
    input_cost_per_million: Optional[Decimal] = None
    output_cost_per_million: Optional[Decimal] = None
    cache_read_cost_per_million: Optional[Decimal] = None
    cache_write_cost_per_million: Optional[Decimal] = None
    request_cost: Optional[Decimal] = None
    source: CostSource = "none"
    source_url: Optional[str] = None
    pricing_version: Optional[str] = None
    fetched_at: Optional[datetime] = None


@dataclass(frozen=True)
class CostResult:
    amount_usd: Optional[Decimal]
    status: CostStatus
    source: CostSource
    label: str
    fetched_at: Optional[datetime] = None
    pricing_version: Optional[str] = None
    notes: tuple[str, ...] = ()


_UTC_NOW = lambda: datetime.now(timezone.utc)


# Official docs snapshot entries. Models whose published pricing and cache
# semantics are stable enough to encode exactly.
_OFFICIAL_DOCS_PRICING: Dict[tuple[str, str], PricingEntry] = {
    # ── OpenAI GPT-5.6 series (Sol/Terra/Luna) ───────────────────────────
    # Announced in limited preview 2026-06-26; GA 2026-07-09. Rates below were
    # RE-VERIFIED 2026-09-23 and corrected. The previous snapshot carried
    # values belonging to other SKUs: "Sol $5/$30" is GPT-5.5 standard,
    # "Terra $2.50/$15" is GPT-5.4 standard, and "Luna $1/$6" is Terra's batch
    # tier — none were GPT-5.6 standard. Current standard tier, short context
    # (<272K): Sol $4/$20, Terra $2/$12, Luna $0.20/$1.20 per 1M in/out.
    # Cache writes bill at 1.25x the uncached input rate; cache reads at
    # 0.10x. Long-context (>272K) rates are higher (Sol $8/$30, Terra $4/$18,
    # Luna $0.40/$1.80). Sol's rates are promotional — OpenAI: "available at
    # least through November 21, 2026".
    # Note: Fast mode (formerly Priority; renamed 2026-07-30) is a separate
    # serving tier billed ABOVE standard — Sol Fast $8/$40 short context and
    # $16/$60 long — and is NOT covered by these entries. Corrected 2026-09-23:
    # an earlier note here attributed "$12.5/$75" and "750 tok/s via Cerebras"
    # to Sol Fast mode. "$12.50/$75" is gpt-5.5's Fast-mode rate and the
    # standard rate of the Cyber models; the Cerebras throughput figure appears
    # in no OpenAI pricing document and was dropped as unsupported.
    # The "-pro" variants are aliased onto these entries below the dict because
    # GPT-5.6 publishes no -pro SKU and some gateways list them as separate
    # catalogue entries at identical prices. NB this is NOT an OpenAI-wide rule:
    # gpt-5.5-pro ($30/$180) and o3-pro ($20/$80) are real, separately priced
    # SKUs (re-verified 2026-09-23).
    # Source: https://platform.openai.com/docs/pricing.md
    (
        "openai",
        "gpt-5.6-sol",
    ): PricingEntry(
        input_cost_per_million=Decimal("4.00"),
        output_cost_per_million=Decimal("20.00"),
        cache_read_cost_per_million=Decimal("0.40"),
        cache_write_cost_per_million=Decimal("5.00"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-5.6-terra",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("12.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("2.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-5.6-luna",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.20"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.02"),
        cache_write_cost_per_million=Decimal("0.25"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    # ── OpenAI GPT-5.5 (catalogued but previously unpriced) ──────────────
    # Standard tier, short context (<272K): $5/$30 with cached input at 0.10x.
    # OpenAI publishes NO cache-write rate for 5.5 ("-"), so that field is left
    # unset. Long context (>272K) is $10/$45. gpt-5.5-pro is a genuinely
    # separately priced SKU ($30/$180 short, $60/$270 long) — see the note on
    # the "-pro" aliases at the top of this block; do NOT alias it to 5.5.
    # Source: https://platform.openai.com/docs/pricing.md (verified 2026-09-23)
    (
        "openai",
        "gpt-5.5",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("30.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-5.5-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("30.00"),
        output_cost_per_million=Decimal("180.00"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    # ── OpenAI GPT-6 generation (Astra / Sol / Luna) ─────────────────────
    # OpenAI's current flagship line, published with prices on its list. These
    # rows are DATA for cost estimation (gateway-routed gpt-6 sessions
    # previously reported "unknown"); no repo model list advertises gpt-6 yet,
    # so nothing is selectable from the picker until a maintainer adds it.
    # Standard tier, short context (<272K): input / cached / cache write /
    # output. Long context (>272K) in the comment, since the snapshot stores
    # one rate set per model: astra $20/$2.00/$25/$75, sol $4/$0.40/$5/$15,
    # luna $0.20/$0.02/$0.25/$0.75.
    # Source: https://platform.openai.com/docs/pricing.md (verified 2026-09-23)
    (
        "openai",
        "gpt-6-astra",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-6-sol",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("10.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("2.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-6-luna",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.10"),
        output_cost_per_million=Decimal("0.50"),
        cache_read_cost_per_million=Decimal("0.01"),
        cache_write_cost_per_million=Decimal("0.125"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    # ── OpenAI Cyber / Daybreak series ───────────────────────────────────
    # "Daybreak" is OpenAI's cyber-capable line (Cyber section of its price
    # list). gpt-5.6-cyber publishes a full cache tier set; gpt-5.5-cyber
    # publishes no cache-write rate ("-"). The aliases
    # gpt-daybreak-blue-latest / -red-latest point at Sol / Cyber and re-point
    # as new Daybreak models ship, so they are aliased rather than inlined.
    # Source: https://platform.openai.com/docs/pricing.md (verified 2026-09-23)
    (
        "openai",
        "gpt-5.6-cyber",
    ): PricingEntry(
        input_cost_per_million=Decimal("12.50"),
        output_cost_per_million=Decimal("75.00"),
        cache_read_cost_per_million=Decimal("1.25"),
        cache_write_cost_per_million=Decimal("15.625"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-5.5-cyber",
    ): PricingEntry(
        input_cost_per_million=Decimal("12.50"),
        output_cost_per_million=Decimal("75.00"),
        cache_read_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    # ── Anthropic Claude 4.8 ─────────────────────────────────────────────
    # Same $5/$25 base pricing as 4.6/4.7. The row below is FAST MODE pricing
    # for Opus 4.8/5, which Anthropic bills at a multiplier on standard rates
    # ($10/$50 vs $5/$25) — fast mode is a REQUEST PARAMETER (speed: "fast"),
    # not a model ID, so this key is a lookup convention rather than a real
    # model. Corrected 2026-09-23: the previous note described the "-fast"
    # suffix as a separate model ID; no such ID exists in Anthropic's or
    # OpenRouter's catalogue, and the OpenRouter source URL cited here 404s.
    # Source: https://platform.claude.com/docs/en/build-with-claude/fast-mode
    # (Opus 5.5 fast mode is cheaper: $8/$40 → add a row if it gets routed.)
    (
        "anthropic",
        "claude-opus-4-8",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── Anthropic fast mode (`speed: "fast"`) ────────────────────────────
    # Priced at a MULTIPLIER on standard rates, and billed per response
    # according to the speed actually served. Anthropic publishes the fast
    # rates directly ("Fast mode pricing for the supported models"), verified
    # 2026-09-23: Claude Opus 5.5 = $8/$40, Claude Opus 5 and Claude Opus 4.8 =
    # $10/$50 per MTok. Prompt-caching multipliers stack on top, hence the
    # 0.1x cache-read and 1.25x cache-write figures below.
    # https://platform.claude.com/docs/en/about-claude/pricing#fast-mode-pricing
    # A `speed: "fast"` request WITHOUT research-preview access does not error:
    # it runs at standard speed and is billed at standard rates, so
    # `estimate_usage_cost` resolves these rows from `usage.speed` in the
    # response — never from the request flag. Both spellings are registered so
    # a dotted OpenRouter-style id ("claude-opus-5.5") resolves too.
    (
        "anthropic",
        "claude-opus-4.8-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5-5-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("8.00"),
        output_cost_per_million=Decimal("40.00"),
        cache_read_cost_per_million=Decimal("0.80"),
        cache_write_cost_per_million=Decimal("10.00"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5.5-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("8.00"),
        output_cost_per_million=Decimal("40.00"),
        cache_read_cost_per_million=Decimal("0.80"),
        cache_write_cost_per_million=Decimal("10.00"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-4-8-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── Anthropic Claude Sonnet 5 ────────────────────────────────────────
    # Launched 2026-06-30. $2/$10 was announced as introductory pricing
    # "through 2026-08-31"; Anthropic's pricing page now states this is the
    # STANDARD price and that "the previously scheduled increase to $3/$15
    # per million input/output tokens on September 1, 2026 will not occur"
    # (re-verified 2026-09-23). Do NOT bump these to $3/$15 — the window
    # closed without an increase.
    # Cache write was missing; the page lists the 5m tier at $2.50 (1.25x
    # input) and the 1h tier at $4 (2x); this field carries the 5m tier,
    # matching how opus-4-x rows encode cache_write.
    # Source: https://platform.claude.com/docs/en/about-claude/pricing
    (
        "anthropic",
        "claude-sonnet-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("10.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("2.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    # ── Anthropic newest generation (Fable / Opus 5) ─────────────────────
    # Fable 5 and Opus 5 are catalogued for context length in
    # agent/model_metadata.py but had NO price rows, so their sessions
    # reported cost as unknown. Row values are the literal table cells
    # (model | base input | 5m cache write | 1h cache write | cache hit |
    # output). Cache hit is the standard 0.1x here.
    # Non-standard cache-hit multipliers (pricing-page footnotes 1 and 2) are
    # published as literal values, so they are encoded directly rather than as
    # an arithmetic multiplier: Fable 5.1 / Mythos 5.1 cache hit $0.25 (0.025x
    # of $10), Opus 5.5 $0.20 (0.05x of $4). The earlier note here deferred
    # these rows "only together with catalog entries"; reversed 2026-09-23 on
    # the reasoning recorded for the GPT-6 rows in §R of SOURCE-FACT-CHECK.md:
    # the price table is also consulted for gateway-routed models
    # (provider=anthropic with a custom base_url resolves to these same keys),
    # so their absence meant a real "unknown cost" for those sessions. Data
    # only — no catalog/picker entry is added, which stays a maintainer call.
    # Source: https://platform.claude.com/docs/en/about-claude/pricing
    (
        "anthropic",
        "claude-fable-5-1",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("0.25"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-fable-5.1",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("0.25"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-mythos-5-1",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("0.25"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-mythos-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("4.00"),
        output_cost_per_million=Decimal("20.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("5.00"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5.5",
    ): PricingEntry(
        input_cost_per_million=Decimal("4.00"),
        output_cost_per_million=Decimal("20.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("5.00"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-fable-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("10.00"),
        output_cost_per_million=Decimal("50.00"),
        cache_read_cost_per_million=Decimal("1.00"),
        cache_write_cost_per_million=Decimal("12.50"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    (
        "anthropic",
        "claude-opus-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-09",
    ),
    # ── Anthropic Claude 4.7 ─────────────────────────────────────────────
    # Opus 4.5/4.6/4.7 share $5/$25 pricing (new tokenizer, up to 35% more
    # tokens for the same text).
    # Source: https://platform.claude.com/docs/en/about-claude/pricing
    (
        "anthropic",
        "claude-opus-4-7",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── Anthropic Claude 4.6 ─────────────────────────────────────────────
    (
        "anthropic",
        "claude-opus-4-6",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-sonnet-4-6",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── Anthropic Claude 4.5 ─────────────────────────────────────────────
    (
        "anthropic",
        "claude-opus-4-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-sonnet-4-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-haiku-4-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.00"),
        output_cost_per_million=Decimal("5.00"),
        cache_read_cost_per_million=Decimal("0.10"),
        cache_write_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # ── Anthropic Claude 4 / 4.1 ─────────────────────────────────────────
    (
        "anthropic",
        "claude-opus-4-20250514",
    ): PricingEntry(
        input_cost_per_million=Decimal("15.00"),
        output_cost_per_million=Decimal("75.00"),
        cache_read_cost_per_million=Decimal("1.50"),
        cache_write_cost_per_million=Decimal("18.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-sonnet-4-20250514",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # OpenAI
    (
        "openai",
        "gpt-4o",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.50"),
        output_cost_per_million=Decimal("10.00"),
        cache_read_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-4o-mini",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.15"),
        output_cost_per_million=Decimal("0.60"),
        cache_read_cost_per_million=Decimal("0.075"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-4.1",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-4.1-mini",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.40"),
        output_cost_per_million=Decimal("1.60"),
        cache_read_cost_per_million=Decimal("0.10"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "gpt-4.1-nano",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.10"),
        output_cost_per_million=Decimal("0.40"),
        cache_read_cost_per_million=Decimal("0.025"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "o3",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "o3-mini",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.10"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.55"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "o4-mini",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.10"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.275"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    (
        "openai",
        "o3-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("20.00"),
        output_cost_per_million=Decimal("80.00"),
        source="official_docs_snapshot",
        source_url="https://platform.openai.com/docs/pricing.md",
        pricing_version="openai-pricing-2026-09",
    ),
    # ── Anthropic older models (pre-4.5 generation) ────────────────────────
    (
        "anthropic",
        "claude-3-5-sonnet-20241022",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-3-5-haiku-20241022",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.80"),
        output_cost_per_million=Decimal("4.00"),
        cache_read_cost_per_million=Decimal("0.08"),
        cache_write_cost_per_million=Decimal("1.00"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-3-opus-20240229",
    ): PricingEntry(
        input_cost_per_million=Decimal("15.00"),
        output_cost_per_million=Decimal("75.00"),
        cache_read_cost_per_million=Decimal("1.50"),
        cache_write_cost_per_million=Decimal("18.75"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    (
        "anthropic",
        "claude-3-haiku-20240307",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("1.25"),
        cache_read_cost_per_million=Decimal("0.03"),
        cache_write_cost_per_million=Decimal("0.30"),
        source="official_docs_snapshot",
        source_url="https://platform.claude.com/docs/en/about-claude/pricing",
        pricing_version="anthropic-pricing-2026-05",
    ),
    # DeepSeek
    # Snapshot of https://api-docs.deepseek.com/quick_start/pricing (2026-07).
    # deepseek-chat / deepseek-reasoner are deprecated 2026-07-24 and now alias
    # deepseek-v4-flash's non-thinking / thinking modes — same rates.
    (
        "deepseek",
        "deepseek-chat",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.006"),
        source="official_docs_snapshot",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        pricing_version="deepseek-pricing-2026-09-peak",
    ),
    (
        "deepseek",
        "deepseek-reasoner",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.006"),
        source="official_docs_snapshot",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        pricing_version="deepseek-pricing-2026-09-peak",
    ),
    (
        "deepseek",
        "deepseek-v4-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.32"),
        output_cost_per_million=Decimal("3.96"),
        cache_read_cost_per_million=Decimal("0.044"),
        source="official_docs_snapshot",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        pricing_version="deepseek-pricing-2026-09-peak",
    ),
    (
        "deepseek",
        "deepseek-v4-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.006"),
        source="official_docs_snapshot",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        pricing_version="deepseek-pricing-2026-09-peak",
    ),
    # Google Gemini
    (
        "google",
        "gemini-2.5-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.25"),
        output_cost_per_million=Decimal("10.00"),
        # Context caching was missing: Google lists $0.125/M for prompts <=200k
        # ($0.25 >200k) plus $4.50/M tokens/hour of storage (verified 2026-09-23,
        # https://ai.google.dev/pricing). The >200k prompt band prices at
        # $2.50/$15.00, so this row is the <=200k band.
        cache_read_cost_per_million=Decimal("0.125"),
        source="official_docs_snapshot",
        source_url="https://ai.google.dev/pricing",
        pricing_version="google-pricing-2026-09",
    ),
    (
        "google",
        "gemini-2.5-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("2.50"),
        # Was None; Google publishes context caching at $0.03/M for
        # text/image/video ($0.10 audio), storage $1.00/M tokens/hour
        # (verified 2026-09-23). Cached Flash traffic was being costed as
        # uncached. Note the audio input rate is $1.00/M, not $0.30.
        cache_read_cost_per_million=Decimal("0.03"),
        source="official_docs_snapshot",
        source_url="https://ai.google.dev/pricing",
        pricing_version="google-pricing-2026-09",
    ),
    (
        "google",
        # Historical: `gemini-2.0-flash` no longer appears anywhere on Google's
        # current price list (0 occurrences of "2.0 Flash", checked 2026-09-23),
        # i.e. it has been pulled from the pricing page rather than deprecated
        # in place. Rates are retained so old sessions still estimate; the
        # successor named by Google's deprecations table is gemini-3.6-flash.
        "gemini-2.0-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.10"),
        output_cost_per_million=Decimal("0.40"),
        source="official_docs_snapshot",
        source_url="https://ai.google.dev/pricing",
        pricing_version="google-pricing-2026-03-16",
    ),
    # AWS Bedrock — pricing per the Bedrock pricing page.
    # Bedrock charges the same per-token rates as the model provider but
    # through AWS billing.  These are the on-demand prices (no commitment).
    # Source: https://aws.amazon.com/bedrock/pricing/
    # Current-gen Claude on Bedrock. Values are the AWS Price List API's
    # MACHINE-READABLE cross-region **global** tier for us-east-1 on-demand
    # (offer `AmazonBedrockFoundationModels`, `USE1-MP:*_global_standard`
    # dimensions; version 20260922164418, re-verified 2026-09-23). The
    # earlier note here claimed the API had not published these SKUs — that
    # is no longer true. TIER MATTERS: Bedrock also publishes an in-region /
    # CRIS tier roughly 10% higher for Opus and ~33% higher for Sonnet 5
    # (Opus 4.6-4.8 => $5.50/$27.50; Sonnet 5 => $2.20/$11.00); every row
    # below is the GLOBAL tier. Cache write = 1.25x input at the 5-minute
    # TTL, cache read = 0.1x input.
    (
        "bedrock",
        "anthropic.claude-opus-4-8",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="anthropic-list-2026-07",
    ),
    (
        "bedrock",
        "anthropic.claude-opus-4-7",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="anthropic-list-2026-07",
    ),
    (
        "bedrock",
        "anthropic.claude-opus-4-6",
    ): PricingEntry(
        input_cost_per_million=Decimal("5.00"),
        output_cost_per_million=Decimal("25.00"),
        cache_read_cost_per_million=Decimal("0.50"),
        cache_write_cost_per_million=Decimal("6.25"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="anthropic-list-2026-07",
    ),
    # Corrected 2026-09-23: the previous $3/$15/$0.30/$3.75 was Claude Sonnet
    # 4.5/4.6's Bedrock price copied onto Sonnet 5, which Bedrock sells at the
    # same rate as Anthropic's direct Sonnet 5 list ($2/$10).
    (
        "bedrock",
        "anthropic.claude-sonnet-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("10.00"),
        cache_read_cost_per_million=Decimal("0.20"),
        cache_write_cost_per_million=Decimal("2.50"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="bedrock-pricing-2026-06",
    ),
    (
        "bedrock",
        "anthropic.claude-sonnet-4-6",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="bedrock-pricing-2026-04",
    ),
    (
        "bedrock",
        "anthropic.claude-sonnet-4-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        cache_write_cost_per_million=Decimal("3.75"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="bedrock-pricing-2026-04",
    ),
    # Corrected 2026-09-23: the previous $0.80/$4.00/$0.08/$1.00 is Claude 3.5
    # Haiku's list price, not Haiku 4.5's — an understatement of ~20%.
    (
        "bedrock",
        "anthropic.claude-haiku-4-5",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.00"),
        output_cost_per_million=Decimal("5.00"),
        cache_read_cost_per_million=Decimal("0.10"),
        cache_write_cost_per_million=Decimal("1.25"),
        source="official_docs_snapshot",
        source_url="https://aws.amazon.com/bedrock/pricing/",
        pricing_version="bedrock-pricing-2026-04",
    ),
    # Nova adds prompt-caching rates that were previously omitted (so cached
    # Nova traffic was costed as uncached). Values are the AWS Price List API's
    # us-east-1 standard on-demand dimensions, per 1K tokens converted to 1M
    # (offer `AmazonBedrock`, version 20260922212139, verified 2026-09-23):
    # Nova Pro input $0.0008 / output $0.0032 / cache read $0.0002;
    # Nova Lite $0.00006 / $0.00024 / $0.000015;
    # Nova Micro $0.000035 / $0.00014 / $0.00000875.
    # Nova cache WRITES bill $0.00, but cache_write is deliberately left unset
    # rather than set to Decimal("0") — a falsy zero would read as "unknown"
    # in the estimator's cache-write handling, which is the same outcome.
    (
        "bedrock",
        "amazon.nova-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.80"),
        output_cost_per_million=Decimal("3.20"),
        cache_read_cost_per_million=Decimal("0.20"),
        source="official_docs_snapshot",
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json",
        pricing_version="bedrock-pricing-2026-09",
    ),
    (
        "bedrock",
        "amazon.nova-lite",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.06"),
        output_cost_per_million=Decimal("0.24"),
        cache_read_cost_per_million=Decimal("0.015"),
        source="official_docs_snapshot",
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json",
        pricing_version="bedrock-pricing-2026-09",
    ),
    (
        "bedrock",
        "amazon.nova-micro",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.035"),
        output_cost_per_million=Decimal("0.14"),
        cache_read_cost_per_million=Decimal("0.00875"),
        source="official_docs_snapshot",
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json",
        pricing_version="bedrock-pricing-2026-09",
    ),
    # MiniMax
    (
        "minimax",
        "minimax-m2.7",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.06"),
        cache_write_cost_per_million=Decimal("0.375"),
        source="official_docs_snapshot",
        source_url="https://platform.minimax.io/docs/guides/pricing-paygo",
        pricing_version="minimax-pricing-2026-09",
    ),
    # The CN platform mirrors the same pay-as-you-go text rates; its pricing
    # page (platform.minimax.cn) was reachable but its text-model table could
    # not be extracted on 2026-09-23, so this row cites the parsed global page
    # and is marked accordingly rather than claiming a CN-only reading.
    (
        "minimax-cn",
        "minimax-m2.7",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        source="official_docs_snapshot",
        source_url="https://platform.minimax.io/docs/guides/pricing-paygo",
        pricing_version="minimax-pricing-2026-09",
    ),
    # Fireworks AI — serverless pricing for the models freeide typically routes
    # through when configured with provider="fireworks". Fireworks publishes a
    # cached_input rate per model alongside input/output, which maps to
    # cache_read_cost_per_million. No separately published cache_write rate.
    # Snapshot of https://docs.fireworks.ai/serverless/pricing (Standard tier,
    # the first price cell in each row — the second is Fireworks' premium tier).
    #
    # Re-verified 2026-09-23 against the live table (16 serverless text rows):
    # kimi-k2p6, kimi-k2p7-code, glm-5p2, minimax-m3 and gpt-oss-120b are exact.
    # Fireworks' release notes (https://docs.fireworks.ai/updates, 2026-08-27)
    # deprecate from SERVERLESS: MiniMax M2.7, GPT OSS 20B, Kimi K2.6
    # Turbo/Fast, Kimi K2.7 Code Fast and unversioned DeepSeek V4 Pro, with
    # migrations to MiniMax M3 / GPT OSS 120B / K2.6 standard / K2.7 Code
    # standard / DeepSeek V4 Pro (0813). "Deprecated from serverless" is not
    # "withdrawn" — dedicated deployments still bill these rates — so the rows
    # are annotated rather than deleted, and the successor ids are added below.
    # Also note glm-5p1's stored figures are GLM 5.3's (1.40/0.26/4.40) and
    # deepseek-v4-flash's are DeepSeek V4.1 Flash's: label drift onto the
    # successor SKU, so their successors are priced explicitly here.
    # glm-5p2-fast IS live and its stored 2.10/6.60/0.21 is exact ("GLM 5.2
    # Fast"); an earlier note calling it absent was wrong.
    # Slug ambiguity to be aware of: Fireworks serves BOTH `deepseek-v4p1-flash`
    # (0.30/1.20, cached 0.006) and the dated `deepseek-v4-flash-0731`
    # (0.22/0.66, cached 0.007). The legacy `deepseek-v4-flash` row carries the
    # V4.1 price, so an account pinned to the 0731 SKU over-estimates ~36%; both
    # live ids now have their own rows.
    (
        "fireworks",
        "kimi-k2p6",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.95"),
        output_cost_per_million=Decimal("4.00"),
        cache_read_cost_per_million=Decimal("0.16"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "kimi-k2p7-code",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.95"),
        output_cost_per_million=Decimal("4.00"),
        cache_read_cost_per_million=Decimal("0.19"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "glm-5p2",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.40"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.14"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "deepseek-v4-pro",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.32"),
        output_cost_per_million=Decimal("3.96"),
        cache_read_cost_per_million=Decimal("0.044"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    (
        "fireworks",
        "deepseek-v4-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.006"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    (
        "fireworks",
        "qwen3p7-plus",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.40"),
        output_cost_per_million=Decimal("1.60"),
        cache_read_cost_per_million=Decimal("0.08"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "minimax-m3",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.06"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "gpt-oss-120b",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.15"),
        output_cost_per_million=Decimal("0.60"),
        cache_read_cost_per_million=Decimal("0.015"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "gpt-oss-20b",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.07"),
        output_cost_per_million=Decimal("0.30"),
        cache_read_cost_per_million=Decimal("0.035"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "glm-5p1",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.40"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.26"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "minimax-m2p7",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.06"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    # Fast/turbo serving tiers — exposed as accounts/fireworks/routers/<name>,
    # so rsplit("/", 1) yields these distinct ids with their own (higher) rates.
    (
        "fireworks",
        "kimi-k2p6-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "kimi-k2p6-turbo",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "kimi-k2p7-code-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.90"),
        output_cost_per_million=Decimal("8.00"),
        cache_read_cost_per_million=Decimal("0.38"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "glm-5p2-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.10"),
        output_cost_per_million=Decimal("6.60"),
        cache_read_cost_per_million=Decimal("0.21"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    (
        "fireworks",
        "glm-5p1-fast",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.80"),
        output_cost_per_million=Decimal("8.80"),
        cache_read_cost_per_million=Decimal("0.52"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-07",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "deepseek-v4-pro-0813",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.32"),
        output_cost_per_million=Decimal("3.96"),
        cache_read_cost_per_million=Decimal("0.044"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "deepseek-v4p1-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.30"),
        output_cost_per_million=Decimal("1.20"),
        cache_read_cost_per_million=Decimal("0.006"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "glm-5p3",
    ): PricingEntry(
        input_cost_per_million=Decimal("1.40"),
        output_cost_per_million=Decimal("4.40"),
        cache_read_cost_per_million=Decimal("0.26"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "glm-5p3-flash",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.15"),
        output_cost_per_million=Decimal("0.50"),
        cache_read_cost_per_million=Decimal("0.03"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "kimi-k3",
    ): PricingEntry(
        input_cost_per_million=Decimal("3.00"),
        output_cost_per_million=Decimal("15.00"),
        cache_read_cost_per_million=Decimal("0.30"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "qwen3p8-max",
    ): PricingEntry(
        input_cost_per_million=Decimal("2.00"),
        output_cost_per_million=Decimal("6.00"),
        cache_read_cost_per_million=Decimal("0.25"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "muse-glimmer-30b",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.35"),
        output_cost_per_million=Decimal("1.50"),
        cache_read_cost_per_million=Decimal("0.04"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "nemotron-3-ultra-nvfp4",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.60"),
        output_cost_per_million=Decimal("2.40"),
        cache_read_cost_per_million=Decimal("0.12"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "nemotron-lightning-3p5-30b-a3b",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.05"),
        output_cost_per_million=Decimal("0.20"),
        cache_read_cost_per_million=Decimal("0.01"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "deepseek-v4-flash-0731",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.22"),
        output_cost_per_million=Decimal("0.66"),
        cache_read_cost_per_million=Decimal("0.007"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
    # live id as of 2026-09-23
    (
        "fireworks",
        "deepseek-v4-flash-vision-exp",
    ): PricingEntry(
        input_cost_per_million=Decimal("0.22"),
        output_cost_per_million=Decimal("0.66"),
        cache_read_cost_per_million=Decimal("0.007"),
        source="official_docs_snapshot",
        source_url="https://docs.fireworks.ai/serverless/pricing",
        pricing_version="fireworks-pricing-2026-09",
    ),
}

# GPT-5.6 "-pro" high-effort variants bill at the same per-token rates as
# their base tiers (more tokens per task, not a higher rate). Alias them
# onto the base entries so the snapshot stays single-source.
for _base_56 in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
    _OFFICIAL_DOCS_PRICING[("openai", f"{_base_56}-pro")] = _OFFICIAL_DOCS_PRICING[
        ("openai", _base_56)
    ]
# Daybreak aliases (OpenAI price list, Cyber section): blue -> Sol, red -> Cyber.
# Both are moving aliases that re-point as new Daybreak models ship.
_OFFICIAL_DOCS_PRICING[("openai", "gpt-daybreak-blue-latest")] = _OFFICIAL_DOCS_PRICING[("openai", "gpt-5.6-sol")]
_OFFICIAL_DOCS_PRICING[("openai", "gpt-daybreak-red-latest")] = _OFFICIAL_DOCS_PRICING[("openai", "gpt-5.6-cyber")]
del _base_56


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def resolve_billing_route(
    model_name: str,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BillingRoute:
    provider_name = (provider or "").strip().lower()
    base = (base_url or "").strip().lower()
    model = (model_name or "").strip()
    if not provider_name and "/" in model:
        inferred_provider, bare_model = model.split("/", 1)
        if inferred_provider in {"anthropic", "openai", "google"}:
            provider_name = inferred_provider
            model = bare_model

    if provider_name == "openai-codex":
        return BillingRoute(provider="openai-codex", model=model, base_url=base_url or "", billing_mode="subscription_included")
    if provider_name == "openrouter" or base_url_host_matches(base_url or "", "openrouter.ai"):
        return BillingRoute(provider="openrouter", model=model, base_url=base_url or "", billing_mode="official_models_api")
    if provider_name == "anthropic":
        return BillingRoute(provider="anthropic", model=model.split("/")[-1], base_url=base_url or "", billing_mode="official_docs_snapshot")
    # "openai-api" is the picker/registry slug for direct api.openai.com; it
    # bills identically to bare "openai", so normalize it here — otherwise the
    # ("openai", <model>) _OFFICIAL_DOCS_PRICING keys are unreachable from the
    # openai-api provider path.
    if provider_name in {"openai", "openai-api"}:
        return BillingRoute(provider="openai", model=model.split("/")[-1], base_url=base_url or "", billing_mode="official_docs_snapshot")
    if provider_name in {"minimax", "minimax-cn"}:
        return BillingRoute(provider=provider_name, model=model.split("/")[-1], base_url=base_url or "", billing_mode="official_docs_snapshot")
    # Vertex AI hosts the same Gemini models as Google AI Studio; price them
    # off the gemini official-docs snapshot. Strip the "google/" vendor prefix
    # the OpenAI-compat endpoint requires so the pricing key matches.
    if provider_name == "vertex" or base_url_host_matches(base_url or "", "aiplatform.googleapis.com"):
        return BillingRoute(provider="gemini", model=model.split("/")[-1], base_url=base_url or "", billing_mode="official_docs_snapshot")
    if provider_name == "fireworks" or base_url_host_matches(base_url or "", "api.fireworks.ai"):
        # Fireworks model ids look like accounts/fireworks/models/<name>;
        # rsplit("/", 1)[-1] yields just <name> which is what the dict keys on.
        return BillingRoute(provider="fireworks", model=model.rsplit("/", 1)[-1], base_url=base_url or "", billing_mode="official_docs_snapshot")
    if provider_name in {"custom", "local"} or provider_name.startswith("custom:") or (base and "localhost" in base):
        return BillingRoute(provider=provider_name or "custom", model=model, base_url=base_url or "", billing_mode="unknown")
    return BillingRoute(provider=provider_name or "unknown", model=model.split("/")[-1] if model else "", base_url=base_url or "", billing_mode="unknown")


def _normalize_bedrock_model_name(model: str) -> str:
    """Normalize a Bedrock model id to its bare foundation-model form.

    Bedrock cross-region inference profiles prefix the foundation model id
    with a region scope (``us.`` / ``global.`` / ``eu.`` / ``apac.`` / ``au.``
    / ...), e.g. ``us.anthropic.claude-opus-4-7`` or
    ``au.anthropic.claude-sonnet-4-5-20250929-v1:0``.  The pricing table is
    keyed on the bare ``anthropic.claude-*`` id, so the prefix must be
    stripped before the lookup or every cross-region session prices as
    unknown.  Note Asia-Pacific uses ``apac.`` (a bare ``ap.`` never matches
    an ``apac.*`` id) and Australia/New Zealand use ``au.``.  Also normalizes
    dot-notation version numbers (``4.7`` → ``4-7``) and the documented
    trailing date, revision, and profile components (``-20250514-v1:0``).
    """
    name = model.lower().strip()
    for prefix in (
        "global.",
        "us.",
        "eu.",
        "apac.",
        "ap.",
        "au.",
        "jp.",
        "ca.",
        "sa.",
        "me.",
        "af.",
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = re.sub(r"(\d+)\.(\d+)", r"\1-\2", name)
    # Bedrock inference profile IDs append these documented components to the
    # foundation model ID. Strip only the trailing forms, not arbitrary model
    # name continuations that could be a distinct SKU.
    name = re.sub(r":\d+$", "", name)
    name = re.sub(r"-v\d+$", "", name)
    name = re.sub(r"-\d{8}$", "", name)
    return name


def _normalize_anthropic_model_name(model: str) -> str:
    """Normalize Anthropic model name variants to canonical form.

    Handles:
      - Dot notation: claude-opus-4.7 → claude-opus-4-7
      - Short aliases: claude-opus-4.7 → claude-opus-4-7
      - Strips anthropic/ prefix if present
    """
    name = model.lower().strip()
    if name.startswith("anthropic/"):
        name = name[len("anthropic/"):]
    # Normalize dots to dashes in version numbers (e.g. 4.7 → 4-7, 4.6 → 4-6)
    # But preserve the rest of the name structure
    name = re.sub(r"(\d+)\.(\d+)", r"\1-\2", name)
    return name


def _lookup_official_docs_pricing(route: BillingRoute) -> Optional[PricingEntry]:
    model = route.model.lower()
    # Direct lookup first
    entry = _OFFICIAL_DOCS_PRICING.get((route.provider, model))
    if entry:
        return entry
    # Try normalized name for Anthropic (handles dot-notation like opus-4.7)
    if route.provider == "anthropic":
        normalized = _normalize_anthropic_model_name(model)
        if normalized != model:
            entry = _OFFICIAL_DOCS_PRICING.get((route.provider, normalized))
            if entry:
                return entry
    # Bedrock cross-region inference profiles carry a region prefix
    # (us./global./eu./...) that the bare pricing keys don't have.
    if route.provider == "bedrock":
        normalized = _normalize_bedrock_model_name(model)
        if normalized != model:
            entry = _OFFICIAL_DOCS_PRICING.get((route.provider, normalized))
            if entry:
                return entry
    return None


def _openrouter_pricing_entry(route: BillingRoute) -> Optional[PricingEntry]:
    return _pricing_entry_from_metadata(
        fetch_model_metadata(),
        route.model,
        source_url="https://openrouter.ai/docs/api/api-reference/models/get-models",
        pricing_version="openrouter-models-api",
    )


def _pricing_entry_from_metadata(
    metadata: Dict[str, Dict[str, Any]],
    model_id: str,
    *,
    source_url: str,
    pricing_version: str,
) -> Optional[PricingEntry]:
    if model_id not in metadata:
        return None
    pricing = metadata[model_id].get("pricing") or {}
    prompt = _to_decimal(pricing.get("prompt"))
    completion = _to_decimal(pricing.get("completion"))
    request = _to_decimal(pricing.get("request"))
    cache_read = _to_decimal(
        pricing.get("cache_read")
        or pricing.get("cached_prompt")
        or pricing.get("input_cache_read")
    )
    cache_write = _to_decimal(
        pricing.get("cache_write")
        or pricing.get("cache_creation")
        or pricing.get("input_cache_write")
    )
    if prompt is None and completion is None and request is None:
        return None

    def _per_token_to_per_million(value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return None
        return value * _ONE_MILLION

    return PricingEntry(
        input_cost_per_million=_per_token_to_per_million(prompt),
        output_cost_per_million=_per_token_to_per_million(completion),
        cache_read_cost_per_million=_per_token_to_per_million(cache_read),
        cache_write_cost_per_million=_per_token_to_per_million(cache_write),
        request_cost=request,
        source="provider_models_api",
        source_url=source_url,
        pricing_version=pricing_version,
        fetched_at=_UTC_NOW(),
    )


def get_pricing_entry(
    model_name: str,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[PricingEntry]:
    route = resolve_billing_route(model_name, provider=provider, base_url=base_url)
    if route.billing_mode == "subscription_included":
        return PricingEntry(
            input_cost_per_million=_ZERO,
            output_cost_per_million=_ZERO,
            cache_read_cost_per_million=_ZERO,
            cache_write_cost_per_million=_ZERO,
            source="none",
            pricing_version="included-route",
        )
    if route.provider == "openrouter":
        return _openrouter_pricing_entry(route)
    if route.base_url:
        entry = _pricing_entry_from_metadata(
            fetch_endpoint_model_metadata(route.base_url, api_key=api_key or ""),
            route.model,
            source_url=f"{route.base_url.rstrip('/')}/models",
            pricing_version="openai-compatible-models-api",
        )
        if entry:
            return entry
    return _lookup_official_docs_pricing(route)


def normalize_usage(
    response_usage: Any,
    *,
    provider: Optional[str] = None,
    api_mode: Optional[str] = None,
) -> CanonicalUsage:
    """Normalize raw API response usage into canonical token buckets.

    Handles three API shapes:
    - Anthropic: input_tokens/output_tokens/cache_read_input_tokens/cache_creation_input_tokens
    - Codex Responses: input_tokens includes cache tokens; input_tokens_details.cached_tokens separates them
    - OpenAI Chat Completions: prompt_tokens includes cache tokens; prompt_tokens_details.cached_tokens separates them

    In both Codex and OpenAI modes, input_tokens is derived by subtracting cache
    tokens from the total — the API contract is that input/prompt totals include
    cached tokens and the details object breaks them out.
    """
    if not response_usage:
        return CanonicalUsage()

    provider_name = (provider or "").strip().lower()
    mode = (api_mode or "").strip().lower()

    if mode == "anthropic_messages" or provider_name == "anthropic":
        input_tokens = _to_int(getattr(response_usage, "input_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "output_tokens", 0))
        cache_read_tokens = _to_int(getattr(response_usage, "cache_read_input_tokens", 0))
        cache_write_tokens = _to_int(getattr(response_usage, "cache_creation_input_tokens", 0))
    elif mode == "codex_responses":
        input_total = _to_int(getattr(response_usage, "input_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "output_tokens", 0))
        details = getattr(response_usage, "input_tokens_details", None)
        cache_read_tokens = _to_int(getattr(details, "cached_tokens", 0) if details else 0)
        cache_write_tokens = _to_int(
            getattr(details, "cache_creation_tokens", 0) if details else 0
        )
        input_tokens = max(0, input_total - cache_read_tokens - cache_write_tokens)
    else:
        prompt_total = _to_int(getattr(response_usage, "prompt_tokens", 0))
        output_tokens = _to_int(getattr(response_usage, "completion_tokens", 0))
        details = getattr(response_usage, "prompt_tokens_details", None)
        # Primary: OpenAI-style prompt_tokens_details. Fallback: Anthropic-style
        # top-level fields that some OpenAI-compatible proxies (OpenRouter, Cline)
        # expose when routing Claude models — without this
        # fallback, cache writes are undercounted as 0 and cache reads can be
        # missed when the proxy only surfaces them at the top level.
        # Port of cline/cline#10266.
        cache_read_tokens = _to_int(getattr(details, "cached_tokens", 0) if details else 0)
        if not cache_read_tokens:
            cache_read_tokens = _to_int(getattr(response_usage, "cache_read_input_tokens", 0))
        if not cache_read_tokens:
            # DeepSeek's native API (api.deepseek.com) reports context-cache
            # hits as top-level prompt_cache_hit_tokens (+ the complementary
            # prompt_cache_miss_tokens; prompt_tokens = hit + miss), not the
            # OpenAI nested shape. Without this, direct DeepSeek sessions
            # always showed 0 cache-hit tokens (#61871).
            cache_read_tokens = _to_int(
                getattr(response_usage, "prompt_cache_hit_tokens", 0)
            )
        cache_write_tokens = _to_int(
            getattr(details, "cache_write_tokens", 0) if details else 0
        )
        if not cache_write_tokens:
            cache_write_tokens = _to_int(
                getattr(response_usage, "cache_creation_input_tokens", 0)
            )
        input_tokens = max(0, prompt_total - cache_read_tokens - cache_write_tokens)

    # Speed actually served (Anthropic fast mode). Read defensively: it is a
    # plain string on the usage object, absent on every other provider.
    _speed = getattr(response_usage, "speed", None)
    speed = str(_speed).strip().lower() if _speed else None
    if speed not in ("fast", "standard"):
        speed = None

    reasoning_tokens = 0
    # Responses API shape: output_tokens_details.reasoning_tokens.
    # Chat Completions shape (OpenAI, OpenRouter, DeepSeek, etc.):
    # completion_tokens_details.reasoning_tokens. Reading only the former
    # left reasoning_tokens=0 for every chat_completions reasoning model —
    # hidden thinking was invisible in session accounting even though it
    # dominates output spend on models like deepseek-v4-flash (measured:
    # single calls burning 21K reasoning tokens to emit 500 visible tokens).
    output_details = getattr(response_usage, "output_tokens_details", None)
    if output_details:
        reasoning_tokens = _to_int(getattr(output_details, "reasoning_tokens", 0))
    if not reasoning_tokens:
        completion_details = getattr(response_usage, "completion_tokens_details", None)
        if completion_details:
            reasoning_tokens = _to_int(
                getattr(completion_details, "reasoning_tokens", 0)
            )

    return CanonicalUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
        speed=speed,
    )


def estimate_usage_cost(
    model_name: str,
    usage: CanonicalUsage,
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> CostResult:
    route = resolve_billing_route(model_name, provider=provider, base_url=base_url)
    if route.billing_mode == "subscription_included":
        return CostResult(
            amount_usd=_ZERO,
            status="included",
            source="none",
            label="included",
            pricing_version="included-route",
        )

    entry = get_pricing_entry(model_name, provider=provider, base_url=base_url, api_key=api_key)
    if not entry:
        return CostResult(amount_usd=None, status="unknown", source="none", label="n/a")

    notes: list[str] = []
    amount = _ZERO

    # Fast mode (Anthropic) is billed by the speed that actually served the
    # response, which the API reports as `usage.speed`. Resolve the fast sibling
    # row from that — not from the request flag, because a fast request without
    # preview access silently runs (and bills) at standard speed.
    if (usage.speed or "").lower() == "fast":
        _fast_entry = get_pricing_entry(
            f"{model_name}-fast", provider=provider, base_url=base_url, api_key=api_key
        )
        if _fast_entry is not None and _fast_entry.input_cost_per_million is not None:
            entry = _fast_entry
            notes.append("fast-mode rates applied (usage.speed=fast)")
        else:
            notes.append(
                "usage.speed=fast but no fast-mode rate is published for this model; "
                "standard rates applied"
            )

    if usage.input_tokens and entry.input_cost_per_million is None:
        return CostResult(amount_usd=None, status="unknown", source=entry.source, label="n/a")
    if usage.output_tokens and entry.output_cost_per_million is None:
        return CostResult(amount_usd=None, status="unknown", source=entry.source, label="n/a")
    if usage.cache_read_tokens:
        if entry.cache_read_cost_per_million is None:
            return CostResult(
                amount_usd=None,
                status="unknown",
                source=entry.source,
                label="n/a",
                notes=("cache-read pricing unavailable for route",),
            )
    if usage.cache_write_tokens:
        if entry.cache_write_cost_per_million is None:
            return CostResult(
                amount_usd=None,
                status="unknown",
                source=entry.source,
                label="n/a",
                notes=("cache-write pricing unavailable for route",),
            )

    if entry.input_cost_per_million is not None:
        amount += Decimal(usage.input_tokens) * entry.input_cost_per_million / _ONE_MILLION
    if entry.output_cost_per_million is not None:
        amount += Decimal(usage.output_tokens) * entry.output_cost_per_million / _ONE_MILLION
    if entry.cache_read_cost_per_million is not None:
        amount += Decimal(usage.cache_read_tokens) * entry.cache_read_cost_per_million / _ONE_MILLION
    if entry.cache_write_cost_per_million is not None:
        amount += Decimal(usage.cache_write_tokens) * entry.cache_write_cost_per_million / _ONE_MILLION
    if entry.request_cost is not None and usage.request_count:
        amount += Decimal(usage.request_count) * entry.request_cost

    status: CostStatus = "estimated"
    label = f"~${amount:.2f}"
    if entry.source == "none" and amount == _ZERO:
        status = "included"
        label = "included"

    if route.provider == "openrouter":
        notes.append("OpenRouter cost is estimated from the models API until reconciled.")

    return CostResult(
        amount_usd=amount,
        status=status,
        source=entry.source,
        label=label,
        fetched_at=entry.fetched_at,
        pricing_version=entry.pricing_version,
        notes=tuple(notes),
    )


def has_known_pricing(
    model_name: str,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> bool:
    """Check whether we have pricing data for this model+route.

    Uses direct lookup instead of routing through the full estimation
    pipeline — avoids creating dummy usage objects just to check status.
    """
    route = resolve_billing_route(model_name, provider=provider, base_url=base_url)
    if route.billing_mode == "subscription_included":
        return True
    entry = get_pricing_entry(model_name, provider=provider, base_url=base_url, api_key=api_key)
    return entry is not None



def format_duration_compact(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"


def format_token_count_compact(value: int) -> str:
    abs_value = abs(int(value))
    if abs_value < 1_000:
        return str(int(value))

    sign = "-" if value < 0 else ""
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))
    for threshold, suffix in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            if scaled < 10:
                text = f"{scaled:.2f}"
            elif scaled < 100:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.0f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"

    return f"{value:,}"
