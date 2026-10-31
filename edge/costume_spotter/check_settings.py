"""Check that edge/.env loads, and say whether the AI is on.

    python -m costume_spotter.check_settings

Used by edge/deploy/windows/update.ps1 before it restarts the app. It's a module
rather than an inline ``python -c "..."`` because Windows PowerShell 5.1 mangles
double quotes in arguments passed to programs, which broke the inline version.

Prints one line and exits 0 when the settings load:
    on: claude-sonnet-5-5      (an API key is set; real identification)
    OFF                        (no API key; pretend mode)
Exits 1 with ``BAD <SETTING>: <problem>; ...`` when a value can't be used.
"""

import sys

from pydantic import ValidationError

from costume_spotter.config import Settings


def describe(error: ValidationError) -> str:
    """'TRACKER_MIN_HITS: Input should be a valid integer; ...' (env-var names)."""
    return "; ".join(f"{'.'.join(map(str, e['loc'])).upper()}: {e['msg']}"
                     for e in error.errors())


def main() -> int:
    try:
        settings = Settings()
    except ValidationError as error:
        print(f"BAD {describe(error)}")
        return 1
    print(f"on: {settings.claude_model}" if settings.anthropic_api_key else "OFF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
