import app.config as config


def test_cors_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert config.cors_allow_origins() == config.DEFAULT_CORS_ORIGINS


def test_cors_explicit_wildcard(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    assert config.cors_allow_origins() == ["*"]


def test_cors_localhost_list_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:4173, http://127.0.0.1:5173")
    assert config.cors_allow_origins() == ["http://localhost:4173", "http://127.0.0.1:5173"]


def test_cors_non_localhost_opens_to_all(monkeypatch) -> None:
    # A real deployment origin -> open to all sources so the frontend can be
    # served from anywhere without enumerating its exact origin.
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://gis.example.org")
    assert config.cors_allow_origins() == ["*"]
