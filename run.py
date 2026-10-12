"""Local launcher; browser UI and API share the same origin."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
os.chdir(root)
sys.path.insert(0, str(root / "backend"))

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        sys.exit("Instala las dependencias con setup_windows.cmd o setup_linux.sh.")
    if not (root / "frontend" / "dist" / "index.html").exists():
        sys.exit("Falta el frontend compilado. Ejecuta npm ci y npm run build dentro de frontend/.")
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, workers=1))
    app.state.shutdown_callback = lambda: print("Programa cerrado. Puedes reiniciarlo desde el navegador. Ctrl+C para salir completamente.")
    print("Data Science Workbench: http://127.0.0.1:8765")
    server.run()
