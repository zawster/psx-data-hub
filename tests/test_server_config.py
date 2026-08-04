from __future__ import annotations

from psx_data_hub import main


def test_main_disables_uvicorn_server_header(monkeypatch):
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(main.uvicorn, "run", fake_run)
    monkeypatch.setattr(main.settings, "hide_server_header", True)

    main.main()

    assert captured["server_header"] is False
