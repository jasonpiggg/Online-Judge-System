"""Isolated Streamlit browser backend; shares the existing deterministic AI fixture."""

import uvicorn

from scripts.serve_web_test import app

app.state.settings.streamlit_origins = ["http://127.0.0.1:18501", "http://localhost:18501"]

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18765, log_level="warning")
