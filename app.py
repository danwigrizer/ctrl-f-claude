#!/usr/bin/env python3
"""CTRL+F+Claude — local Mac app for browsing Claude Code sessions."""

import webview
from api import Api

if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "CTRL+F+Claude",
        "index.html",
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 500),
    )
    webview.start()
