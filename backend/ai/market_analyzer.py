"""AI market analyzer with multi-provider routing for prediction markets."""
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
    probability: float  # model's estimated probability [0, 1]
    confidence: float  # how confident the model is [0, 1]
    reasoning: str  # explanation
    provider: str  # which AI was used
    cost_usd: float  # estimated cost


def _build_prompt(
    question: str,
    current_price: float,
    volume: float,
    category: str = "",
    context: str = "",
) -> str:
    prompt = f"""Analyze this prediction market:
Question: {question}
Current YES price: ${current_price}
Volume: ${volume}
Category: {category}"""
    if context:
        prompt += f"\nContext: {context}"
    prompt += """

Estimate the TRUE probability of YES outcome.
Return your analysis as:
PROBABILITY: [0.0 to 1.0]
CONFIDENCE: [0.0 to 1.0]
REASONING: [brief explanation]"""
    return prompt


def _parse_ai_response(response: str) -> tuple[float, float, str]:
    """Extract probability, confidence, reasoning from LLM text response.

    Handles structured PROBABILITY/CONFIDENCE/REASONING format and JSON.
    Returns (probability, confidence, reasoning). Falls back to (0.5, 0.0, response)
    on parse failure.
    """
    # Try JSON first
    json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            prob = float(data.get("probability", data.get("prob", 0.5)))
            conf = float(data.get("confidence", data.get("conf", 0.0)))
            reasoning = str(data.get("reasoning", data.get("reason", response)))
            prob = max(0.0, min(1.0, prob))
            conf = max(0.0, min(1.0, conf))
            return (prob, conf, reasoning)
        except (ValueError, KeyError):
            pass

    # Try structured text format
    prob: Optional[float] = None
    conf: Optional[float] = None
    reasoning = ""

    prob_match = re.search(r'PROBABILITY:\s*(-?[\d.]+)', response, re.IGNORECASE)
    if prob_match:
        try:
            prob = max(0.0, min(1.0, float(prob_match.group(1))))
        except ValueError:
            pass

    conf_match = re.search(r'CONFIDENCE:\s*(-?[\d.]+)', response, re.IGNORECASE)
    if conf_match:
        try:
            conf = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            pass

    reasoning_match = re.search(r'REASONING:\s*(.+)', response, re.IGNORECASE | re.DOTALL)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()

    if prob is not None and conf is not None:
        return (prob, conf, reasoning or response)

    # Fallback: return neutral values so callers can detect parse failure via confidence=0
    return (0.5, 0.0, response)


async def _call_groq(prompt: str) -> Optional[str]:
    """Call Groq API using the existing GroqClassifier pattern."""
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
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
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
    """Call Claude API using the existing ClaudeAnalyzer pattern."""
    start_time = time.time()
    model = "claude-sonnet-4-20250514"
    try:
        from backend.config import settings
        import anthropic

        api_key = settings.ANTHROPIC_API_KEY if hasattr(settings, "ANTHROPIC_API_KEY") else None
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not configured")
            return None

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
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
    """Return current AI spend vs daily budget.

    Returns dict with keys: spent_today, limit, remaining, can_call.
    """
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
    """Analyze a prediction market and return an AIAnalysis.

    Routing strategy:
    - Use Groq (cheap) for initial screening.
    - If Groq returns an edge > 5% vs current_price, escalate to Claude.
    - Respects AI_DAILY_BUDGET_USD; returns None if budget exceeded.
    - Returns None on API error or response parse failure.
    """
    budget = await check_ai_budget()
    if not budget["can_call"]:
        logger.warning(
            f"AI daily budget exceeded (${budget['spent_today']:.4f} / ${budget['limit']:.2f})"
        )
        return None

    prompt = _build_prompt(question, current_price, volume, category, context)

    # --- Groq screening pass ---
    groq_response = await _call_groq(prompt)
    if groq_response is None:
        return None

    groq_prob, groq_conf, groq_reasoning = _parse_ai_response(groq_response)
    if groq_conf == 0.0 and groq_prob == 0.5:
        # Parse failed
        logger.warning("Failed to parse Groq response")
        return None

    groq_edge = abs(groq_prob - current_price)

    # If edge is <= 5%, stick with Groq result
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

    # --- Escalate to Claude for higher-edge signals ---
    budget = await check_ai_budget()
    if not budget["can_call"]:
        logger.warning("Budget exhausted before Claude escalation, returning Groq result")
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=budget["spent_today"],
        )

    claude_response = await _call_claude(prompt)
    if claude_response is None:
        # Fall back to Groq result
        return AIAnalysis(
            probability=groq_prob,
            confidence=groq_conf,
            reasoning=groq_reasoning,
            provider="groq",
            cost_usd=budget["spent_today"],
        )

    claude_prob, claude_conf, claude_reasoning = _parse_ai_response(claude_response)
    if claude_conf == 0.0 and claude_prob == 0.5:
        # Claude parse failed, fall back to Groq
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
