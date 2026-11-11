import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import telegram  # noqa: E402


def test_chunks_fit_limit_and_keep_text():
    text = "".join(f"line {i}\n" for i in range(2000))
    pieces = telegram._chunks(text, limit=500)
    assert all(len(p) <= 500 for p in pieces)
    assert "".join(pieces) == text


def test_chunks_split_overlong_line():
    pieces = telegram._chunks("x" * 1200, limit=500)
    assert [len(p) for p in pieces] == [500, 500, 200]


def test_send_file_routes_by_type(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(telegram, "_call", lambda method, fields=None, *a: calls.append(method))
    (tmp_path / "r.md").write_text("# report\nok\n")
    (tmp_path / "r.html").write_text("<p>hi</p>")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")
    assert telegram.send_file(tmp_path / "r.md") == "text"
    assert telegram.send_file(tmp_path / "r.md", as_file=True) == "document"
    assert telegram.send_file(tmp_path / "r.html", caption="x") == "document"
    assert telegram.send_file(tmp_path / "c.png") == "photo"
    assert calls == ["sendMessage", "sendDocument", "sendDocument", "sendPhoto"]
