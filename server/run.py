"""Development entry point.

    python run.py            # http://0.0.0.0:5000

Bind to 0.0.0.0 so the Flutter app on a device or an emulator can reach it.
The address provider key stays on this side of the network.
"""

from __future__ import annotations

import os

from home_ledger import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
