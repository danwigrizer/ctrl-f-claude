#!/usr/bin/env python3
"""Claude Conversations Viewer — local Mac app."""

import webview
from api import Api

if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "Claude Conversations",
        "index.html",
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 500),
    )
    webview.start()
