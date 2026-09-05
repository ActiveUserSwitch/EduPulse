"""Whisper initial_prompt token budget — measure, fit, optional trade patch.

See docs/whisper_prompt_budget.md for the dissertation/methods write-up.

Stock faster-whisper keeps only the last (max_length // 2 - 1) ≈ 223 tokens of
the encoded initial_prompt. The architectural ceiling is max_length = 448.
Trading output slots for a larger prompt budget is an experimental fork, not a
free raise of model capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Stock Whisper / faster-whisper constants (large-v3 and siblings).
WHISPER_N_TEXT_CTX = 448
STOCK_PROMPT_BUDGET = WHISPER_N_TEXT_CTX // 2 - 1  # 223
STOCK_OUTPUT_BUDGET = WHISPER_N_TEXT_CTX // 2  # 224


@dataclass
class PromptBudgetReport:
    chars: int
    tokens: int
    budget: int
    dropped: int
    kept: int
    truncated: bool
    dropped_text: str
    kept_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chars": self.chars,
            "tokens": self.tokens,
            "budget": self.budget,
            "dropped": self.dropped,
            "kept": self.kept,
            "truncated": self.truncated,
            "dropped_text": self.dropped_text,
            "kept_text": self.kept_text,
        }


def get_whisper_tokenizer(model: Any = None):
    """Return a Whisper tokenizer; load large-v3 once if model is None."""
    if model is not None and hasattr(model, "hf_tokenizer"):
        return model.hf_tokenizer
    from faster_whisper import WhisperModel

    m = WhisperModel("large-v3", device="cpu", compute_type="int8")
    return m.hf_tokenizer


def encode_prompt_tokens(prompt: str, tokenizer=None) -> list[int]:
    tok = tokenizer or get_whisper_tokenizer()
    text = " " + (prompt or "").strip()  # faster-whisper prepends a space
    enc = tok.encode(text)
    return list(enc.ids if hasattr(enc, "ids") else enc)


def measure_prompt(
    prompt: str,
    budget: int = STOCK_PROMPT_BUDGET,
    tokenizer=None,
) -> PromptBudgetReport:
    """Measure how a prompt is sliced under a given token budget (tail kept)."""
    tok = tokenizer or get_whisper_tokenizer()
    ids = encode_prompt_tokens(prompt, tok)
    n = len(ids)
    drop_n = max(0, n - budget)
    dropped_ids = ids[:drop_n]
    kept_ids = ids[drop_n:]
    return PromptBudgetReport(
        chars=len(prompt or ""),
        tokens=n,
        budget=budget,
        dropped=drop_n,
        kept=len(kept_ids),
        truncated=drop_n > 0,
        dropped_text=tok.decode(dropped_ids) if dropped_ids else "",
        kept_text=tok.decode(kept_ids) if kept_ids else "",
    )


def fit_prompt_to_budget(
    prompt: str,
    budget: int = STOCK_PROMPT_BUDGET,
    tokenizer=None,
) -> str:
    """Return only the tail of `prompt` that fits in `budget` tokens.

    Prefer building a short prompt; use this as a safety net so we never
    silently depend on Whisper's truncation of content we care about at the front.
    """
    tok = tokenizer or get_whisper_tokenizer()
    ids = encode_prompt_tokens(prompt, tok)
    if len(ids) <= budget:
        return (prompt or "").strip()
    kept = ids[-budget:]
    # decode may include the leading space we added at encode time
    text = tok.decode(kept).strip()
    return text


def apply_prompt_budget_patch(
    model: Any,
    prompt_budget: int,
) -> Callable[[], None]:
    """Monkey-patch ``model.get_prompt`` to keep ``prompt_budget`` tokens.

    This reallocates the 448-slot decoder window; it does **not** raise
    ``n_text_ctx``. Caller should also pass ``max_new_tokens`` so that
    ``prompt_budget + max_new_tokens < 448`` (leave room for SOT / specials).

    Returns an undo() callable that restores the original ``get_prompt``.
    """
    if prompt_budget < 32:
        raise ValueError("prompt_budget too small")
    if prompt_budget >= WHISPER_N_TEXT_CTX - 16:
        raise ValueError(
            f"prompt_budget={prompt_budget} leaves almost no room for output "
            f"inside n_text_ctx={WHISPER_N_TEXT_CTX}"
        )

    original = model.get_prompt

    def get_prompt(
        tokenizer,
        previous_tokens,
        without_timestamps: bool = False,
        prefix=None,
        hotwords=None,
    ):
        prompt: list[int] = []
        keep = prompt_budget

        if previous_tokens or (hotwords and not prefix):
            prompt.append(tokenizer.sot_prev)
            if hotwords and not prefix:
                hotwords_tokens = tokenizer.encode(" " + hotwords.strip())
                if len(hotwords_tokens) >= keep:
                    hotwords_tokens = hotwords_tokens[: keep - 1]
                prompt.extend(hotwords_tokens)
            if previous_tokens:
                prompt.extend(previous_tokens[-keep:])

        prompt.extend(tokenizer.sot_sequence)

        if without_timestamps:
            prompt.append(tokenizer.no_timestamps)

        if prefix:
            prefix_tokens = tokenizer.encode(" " + prefix.strip())
            if len(prefix_tokens) >= keep:
                prefix_tokens = prefix_tokens[: keep - 1]
            if not without_timestamps:
                prompt.append(tokenizer.timestamp_begin)
            prompt.extend(prefix_tokens)

        return prompt

    model.get_prompt = get_prompt  # type: ignore[method-assign]
    model._edupulse_prompt_budget = prompt_budget  # type: ignore[attr-defined]

    def undo() -> None:
        model.get_prompt = original  # type: ignore[method-assign]
        if hasattr(model, "_edupulse_prompt_budget"):
            delattr(model, "_edupulse_prompt_budget")

    return undo


def suggested_max_new_tokens(prompt_budget: int, reserve_specials: int = 12) -> int:
    """Max new tokens so prompt_budget + output stays under n_text_ctx."""
    return max(16, WHISPER_N_TEXT_CTX - prompt_budget - reserve_specials)
