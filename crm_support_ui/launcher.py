from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

import uvicorn


HOST = "127.0.0.1"
PORT = 8765


def main() -> None:
    default_az = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd")
    if not os.environ.get("CRM_AZ_PATH") and default_az.is_file():
        os.environ["CRM_AZ_PATH"] = str(default_az)

    url = f"http://{HOST}:{PORT}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"CRM \u5f55\u5165\u5de5\u5177\u5df2\u542f\u52a8: {url}")
    print("\u8bf7\u4fdd\u6301\u6b64\u7a97\u53e3\u8fd0\u884c\uff1b\u6309 Ctrl+C \u53ef\u505c\u6b62\u3002")
    uvicorn.run("crm_support_ui.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
