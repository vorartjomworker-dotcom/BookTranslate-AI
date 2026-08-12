from __future__ import annotations

from app.services.context_builder import TranslationContext


ROLE_PROMPTS: dict[str, tuple[str, str]] = {
    "translator": (
        "You are a professional technical-book translator. Preserve meaning, terminology, code, numbers, references, and structure. Return only the translated segment, without commentary.",
        "Translate the SOURCE from {source_language} to {target_language}. Use CONTEXT only to resolve meaning and terminology.",
    ),
    "reviewer": (
        "You are a senior bilingual technical editor. Correct mistranslations, terminology drift, omissions, additions, grammar, and style. Return only the revised translation.",
        "Review CANDIDATE against SOURCE and CONTEXT. Produce the corrected translation in {target_language}.",
    ),
    "critic": (
        "You are a rigorous translation quality critic and technical editor. Detect semantic, terminology, factual, formatting, and consistency errors, then silently fix them. Return only the improved translation.",
        "Improve CANDIDATE using SOURCE, glossary, translation memory, and surrounding context. Return only the improved {target_language} translation.",
    ),
    "finalizer": (
        "You are the final editor for a technical book. Produce publication-ready text faithful to the source and consistent with the glossary. Return only final translated text.",
        "Finalize CANDIDATE in {target_language}. Do not explain your edits.",
    ),
}


def get_default_role_prompt(role: str) -> tuple[str, str]:
    if role not in ROLE_PROMPTS:
        raise ValueError(f"Unsupported translation role: {role}")
    return ROLE_PROMPTS[role]


def _section(title: str, values: list[str]) -> str:
    if not values:
        return f"[{title}]\n(none)"
    return f"[{title}]\n" + "\n".join(values)


def render_user_prompt(
    context: TranslationContext,
    *,
    role: str,
    template: str,
    candidate_text: str | None = None,
) -> str:
    glossary_lines = [
        f"{item.source_term} => {item.target_term}"
        + (f" ({item.notes})" if item.notes else "")
        for item in context.glossary
    ]
    memory_lines = [
        f"SOURCE: {item.source_text}\nTARGET: {item.target_text}"
        for item in context.memory_matches
    ]

    header = template.format(
        source_language=context.source_language,
        target_language=context.target_language,
    )
    sections = [
        header,
        f"[CHAPTER]\n{context.chapter_title or '(untitled)'}",
        _section("PREVIOUS SOURCE CONTEXT", context.previous_segments),
        _section("NEXT SOURCE CONTEXT", context.next_segments),
        _section("GLOSSARY", glossary_lines),
        _section("TRANSLATION MEMORY", memory_lines),
        f"[SOURCE]\n{context.source_text}",
    ]
    if role != "translator":
        if not candidate_text:
            raise ValueError(f"Role '{role}' requires a candidate translation")
        sections.append(f"[CANDIDATE]\n{candidate_text}")
    return "\n\n".join(sections)
