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


# -- who is visiting: age bands, no-costume specifics, sarcasm (03-F14) ------------

def test_sarcasm_is_switched_on_per_call_only():
    assert "SARCASTIC" not in prompts.user_prompt(1)
    on = prompts.user_prompt(2, ["witch"], sarcastic=True)
    assert on.startswith(prompts.user_prompt(2, ["witch"]))  # history kept, switch appended
    assert "SARCASTIC" in on and "Little kids" in on


def test_prompt_asks_for_an_age_band_and_guesses_younger():
    text = prompts.SYSTEM_PROMPT
    assert '"age": "little kid|big kid|teen or adult|pet"' in text
    assert "pick the YOUNGER band" in text
    assert "never said out loud" in text


def test_no_costume_rules_tease_only_teens_and_adults():
    text = prompts.SYSTEM_PROMPT
    no_costume = text[text.index("No costume:"):text.index("Sarcasm (only")]
    assert "ONE specific, friendly detail" in no_costume
    assert '"little kid" or "big kid": warm' in no_costume
    assert '"teen or adult": tease' in no_costume


def test_specifics_are_only_about_things_people_chose():
    text = prompts.SYSTEM_PROMPT
    assert "something they CHOSE" in text
    for off_limits in ("body", "weight", "face", "skin", "glasses", "mobility aid"):
        assert off_limits in text
    assert "Little kids and pets are never sarcastic targets" in text
