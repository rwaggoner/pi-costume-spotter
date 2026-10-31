"""user_prompt(): tonight's-costume-history injection (03-F13, originally issue #10)."""

from costume_spotter.vision import prompts


def test_no_history_means_the_base_prompt_unchanged():
    assert prompts.user_prompt(1) == prompts.user_prompt(1, [])
    assert "already greeted" not in prompts.user_prompt(3)


def test_history_appears_with_the_vary_instruction():
    text = prompts.user_prompt(1, ["witch", "vampire"])
    assert text.startswith(prompts.user_prompt(1))
    assert "witch, vampire" in text
    assert "fresh" in text  # the don't-repeat-jokes instruction


def test_history_is_capped_to_the_most_recent():
    many = [f"costume-{i}" for i in range(30)]
    text = prompts.user_prompt(2, many)
    assert "costume-29" in text  # newest kept
    assert "costume-0," not in text  # oldest dropped; prompt stays lean


def test_system_prompt_sets_the_halloween_scene():
    assert "Halloween night" in prompts.SYSTEM_PROMPT
