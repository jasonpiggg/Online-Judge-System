from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_login_surface_renders() -> None:
    app = AppTest.from_file(Path(__file__).parents[1] / "frontend" / "app.py")
    app.run(timeout=20)
    assert not app.exception
    assert any(button.label == "进入工作台" for button in app.button)
    assert any(button.label == "注册" for button in app.button)
