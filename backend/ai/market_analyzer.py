"""AI market analyzer with multi-provider routing for prediction markets."""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from backend.ai.logger import get_ai_logger

logger = logging.getLogger("trading_bot.ai")


@dataclass
class AIAnalysis:
    probability: float
    confidence: float
    reasoning: str
    provider: str
    cost_usd: float


def _build_prompt(
    question: str,
    current_price: float,
    volume: float,
    category: str = "",
    context: str = "",
) -> str:
    prompt = f"""Analyze this prediction market and estimate the TRUE probability of YES.

Question: {question}
Current YES price: ${current_price}
Volume: ${volume}"""
    if category:
        prompt += f"\nCategory: {category}"
    if context:
        prompt += f"\nContext: {context}"
    prompt += """

You MUST respond with EXACTLY these three lines and nothing else:
PROBABILITY: <number between 0.0 and 1.0>
CONFIDENCE: <number between 0.0 and 1.0>
REASONING: <one sentence explanation>

Example response:
PROBABILITY: 0.35
CONFIDENCE: 0.70
REASONING: Market is overpriced given current polling data shows only 35% support."""
    return prompt


def _extract_number(text: str, keywords: list[str]) -> Optional[float]:
    """Extract a float value associated with any of the given keywords.

    Handles formats like:
      PROBABILITY: 0.35
      Probability = 0.35
      Probability ≈ 0.35
      probability is 0.35
      **Probability**: 0.35
      - Probability: 0.35
      prob: 0.35
    """
    for kw in keywords:
        # Pattern: keyword followed by separator then number
        pattern = (
            rf"(?:\*{{0,2}}){kw}(?:\*{{0,2}})\s*[:=≈~\-–—is]\s*\*{{0,2}}\s*(-?[\d.]+)"
        )
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return max(0.0, min(1.0, float(match.group(1))))
            except ValueError:
                continue
    return None


def _parse_ai_response(response: str) -> tuple[float, float, str]:
    """Parse PROBABILITY/CONFIDENCE/REASONING from an LLM response.

    Tries in order:
    1. JSON object with probability/confidence keys
    2. Flexible keyword extraction (handles many LLM output formats)
    3. Fallback defaults
    """
    # Strategy 1: JSON object
    start = response.find("{")
    if start != -1:
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(response, start)
            prob = float(
                data.get(
                    "probability", data.get("prob", data.get("true_probability", -1))
                )
            )
            conf = float(data.get("confidence", data.get("conf", -1)))
            reasoning = str(
                data.get(
                    "reasoning", data.get("reason", data.get("explanation", response))
                )
            )
            if prob >= 0:
                prob = max(0.0, min(1.0, prob))
                conf = max(0.0, min(1.0, conf)) if conf >= 0 else 0.5
                return (prob, conf, reasoning)
        except (ValueError, KeyError, TypeError):
            pass

    # Strategy 2: Flexible keyword extraction
    prob = _extract_number(
        response,
        [
            "probability",
            "prob",
            "true_probability",
            "true probability",
            "estimated probability",
        ],
    )
    conf = _extract_number(
        response, ["confidence", "conf", "confidence level", "certainty"]
    )

    reasoning = ""
    reasoning_match = re.search(
        r"REASONING:\s*(.+)", response, re.IGNORECASE | re.DOTALL
    )
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()
        # Trim at next keyword if present
        next_kw = re.search(
            r"\n\s*(?:PROBABILITY|CONFIDENCE):", reasoning, re.IGNORECASE
        )
        if next_kw:
            reasoning = reasoning[: next_kw.start()].strip()

    if prob is not None:
        # If we found probability but not confidence, assume moderate confidence
        if conf is None:
            conf = 0.5
        return (prob, conf, reasoning or response[:500])

    # Strategy 3: Last resort — scan for any standalone decimal between 0 and 1
    # that looks like a probability (in the first few lines)
    first_lines = "\n".join(response.split("\n")[:10])
    decimals = re.findall(r"\b(0\.\d{1,4})\b", first_lines)
    if decimals:
        try:
            prob = float(decimals[0])
            if 0.01 <= prob <= 0.99:
                logger.info(f"AI response parsed via decimal fallback: prob={prob}")
                return (prob, 0.3, response[:500])
        except ValueError:
            pass

    return (0.5, 0.0, response)


async def _call_groq(prompt: str) -> Optional[str]:
    start_time = time.time()
    try:
        from backend.config import settings
        from groq import Groq

        api_key = settings.GROQ_API_KEY
        if not api_key:
            logger.warning("GROQ_API_KEY not configured")
            return None

        model = settings.GROQ_MODEL
        client = Groq(api_key=api_key)
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a prediction market analyst. "
                        "Always respond with EXACTLY three lines:\n"
                        "PROBABILITY: <number>\nCONFIDENCE: <number>\nREASONING: <one sentence>\n"
                        "Never include any other text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=0.2,
        )

        result = response.choices[0].message.content.strip()
        latency_ms = (time.time() - start_time) * 1000
        tokens_used = response.usage.total_tokens if response.usage else 0

        ai_logger = get_ai_logger()
        ai_logger.log_call(
            provider="groq",
            model=model,
            prompt=prompt,
            response=result,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            call_type="market_analysis",
            success=True,
        )

        return result

    except ImportError:
        logger.error("groq package not installed")
        return None
    except Exception as e:
        logger.error(f"Groq market analysis failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        try:
            from backend.config import settings

            ai_logger = get_ai_logger()
            ai_logger.log_call(
                provider="groq",
                model=settings.GROQ_MODEL,
                prompt=prompt,
                response="",
                latency_ms=latency_ms,
                tokens_used=0,
                call_type="market_analysis",
                success=False,
                error=str(e),
            )
        except Exception:
            pass
        return None


async def _call_claude(prompt: str) -> Optional[str]:
    start_time = time.time()
    model = "claude-sonnet-4-20250514"
    try:
        from backend.config import settings
        import anthropic

        api_key = (
            settings.ANTHROPIC_API_KEY
            if hasattr(settings, "ANTHROPIC_API_KEY")
            else None
        )
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not configured")
            return None

        client = anthropic.Anthropic(api_key=api_key)
        message = await asyncio.to_thread(
            client.messages.create,
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        result = message.content[0].text
        latency_ms = (time.time() - start_time) * 1000
        tokens_used = message.usage.input_tokens + message.usage.output_tokens

        ai_logger = get_ai_logger()
        ai_logger.log_call(
            provider="claude",
            model=model,
            prompt=prompt,
            response=result,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            call_type="market_analysis",
            success=True,
        )

        return result

    except ImportError:
        logger.error("anthropic package not installed")
        return None
    except Exception as e:
        logger.error(f"Claude market analysis failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        try:
            ai_logger = get_ai_logger()
            ai_logger.log_call(
                provider="claude",
                model=model,
                prompt=prompt,
                response="",
                latency_ms=latency_ms,
                tokens_used=0,
                call_type="market_analysis",
                success=False,
                error=str(e),
            )
        except Exception:
            pass
        return None


async def check_ai_budget() -> dict:
    """Return current AI spend vs daily budget."""
    from backend.config import settings

    ai_logger = get_ai_logger()
    stats = ai_logger.get_daily_stats()
    spent = stats.get("total_cost_usd", 0.0)
    limit = settings.AI_DAILY_BUDGET_USD
    remaining = max(0.0, limit - spent)

    return {
        "spent_today": spent,
        "limit": limit,
        "remaining": remaining,
        "can_call": spent < limit,
    }


async def analyze_market(
    question: str,
    current_price: float,
    volume: float,
    category: str = "",
    context: str = "",
) -> Optional[AIAnalysis]:
    """Analyze a market: screen with Groq, escalate to Claude if edge > 5%."""
    budget = await check_ai_budget()
    if not budget["can_call"]:
        logger.warning(
            f"AI daily budget exceeded (${budget['spent_today']:.4f} / ${budget['limit']:.2f})"
        )
        return None

    prompt = _build_prompt(question, current_price, volume, category, context)

    groq_response = await _call_groq(prompt)
    if groq_response is None:
        return None

    groq_prob, groq_conf, groq_reasoning = _parse_ai_response(groq_response)
    if groq_conf == 0.0 and groq_prob == 0.5:
        logger.warning(
            f"Failed to parse Groq response (first 200 chars): {groq_response[:200]}"
        )
        return None

    groq_edge = abs(groq_prob - current_price)

    if groq_edge <= 0.05:
        ai_logger = get_ai_logger()
        daily_stats = ai_logger.get_daily_stats()
        cost = daily_stats.get("total_cost_usd", 0.0)
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=cost,
        )

    budget = await check_ai_budget()
    if not budget["can_call"]:
        logger.warning(
            "Budget exhausted before Claude escalation, returning Groq result"
        )
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=budget["spent_today"],
        )

    claude_response = await _call_claude(prompt)
    if claude_response is None:
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=budget["spent_today"],
        )

    claude_prob, claude_conf, claude_reasoning = _parse_ai_response(claude_response)
    if claude_conf == 0.0 and claude_prob == 0.5:
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=budget["spent_today"],
        )

    final_budget = await check_ai_budget()
    return AIAnalysis(
        probability=claude_prob,
        confidence=claude_conf,
        reasoning=claude_reasoning,
        provider="claude",
        cost_usd=final_budget["spent_today"],
    )
