from app.services.context_builder import GlossaryMatch, MemoryMatch, TranslationContext
from app.services.prompt_builder import get_default_role_prompt, render_user_prompt


def _context() -> TranslationContext:
    import uuid

    return TranslationContext(
        segment_id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        source_language="en",
        target_language="ru",
        chapter_title="Latency",
        source_text="The lock-free queue reduces latency.",
        previous_segments=["Previous paragraph."],
        next_segments=["Next paragraph."],
        glossary=[GlossaryMatch("lock-free queue", "безблокировочная очередь")],
        memory_matches=[MemoryMatch("latency", "задержка", 0.98)],
    )


def test_translator_prompt_contains_structured_context() -> None:
    system_prompt, template = get_default_role_prompt("translator")
    prompt = render_user_prompt(_context(), role="translator", template=template)
    assert "technical-book translator" in system_prompt
    assert "[SOURCE]" in prompt
    assert "lock-free queue => безблокировочная очередь" in prompt
    assert "[TRANSLATION MEMORY]" in prompt
    assert "[CANDIDATE]" not in prompt


def test_reviewer_requires_and_includes_candidate() -> None:
    _system_prompt, template = get_default_role_prompt("reviewer")
    prompt = render_user_prompt(
        _context(),
        role="reviewer",
        template=template,
        candidate_text="Черновой перевод.",
    )
    assert "[CANDIDATE]" in prompt
    assert "Черновой перевод." in prompt
