"""build_user_prompt(): tonight's-costume-history injection (issue #10)."""

from costume_spotter.vision import prompts


def test_no_history_means_the_base_prompt_unchanged():
    assert prompts.build_user_prompt([]) == prompts.USER_PROMPT


def test_history_appears_with_the_vary_instruction():
    text = prompts.build_user_prompt(["witch", "vampire"])
    assert text.startswith(prompts.USER_PROMPT)
    assert "witch, vampire" in text
    assert "fresh" in text  # the don't-repeat-jokes instruction


def test_history_is_capped_to_the_most_recent():
    many = [f"costume-{i}" for i in range(30)]
    text = prompts.build_user_prompt(many)
    assert "costume-29" in text  # newest kept
    assert "costume-0" not in text  # oldest dropped — prompt stays lean
