"""check_settings: what update.ps1 prints before restarting the app."""

from costume_spotter import check_settings


def run(monkeypatch, tmp_path, capsys, env: dict[str, str]) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path)  # no stray edge/.env
    for key in ("ANTHROPIC_API_KEY", "TRACKER_MIN_HITS", "CLAUDE_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    code = check_settings.main()
    return code, capsys.readouterr().out.strip()


def test_reports_the_model_when_the_key_is_set(monkeypatch, tmp_path, capsys):
    code, out = run(monkeypatch, tmp_path, capsys,
                    {"ANTHROPIC_API_KEY": "sk-test", "CLAUDE_MODEL": "claude-sonnet-5-5"})
    assert (code, out) == (0, "on: claude-sonnet-5-5")


def test_reports_off_without_a_key(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, capsys, {}) == (0, "OFF")


def test_names_the_bad_setting(monkeypatch, tmp_path, capsys):
    code, out = run(monkeypatch, tmp_path, capsys, {"TRACKER_MIN_HITS": "three"})
    assert code == 1
    assert out.startswith("BAD TRACKER_MIN_HITS: ")


def test_reads_the_env_file_like_the_app(monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-from-file\nCLAUDE_MODEL=m\n")
    assert run(monkeypatch, tmp_path, capsys, {}) == (0, "on: m")
