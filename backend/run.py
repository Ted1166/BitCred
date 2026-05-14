import sys
import os
from pathlib import Path

backend_dir = str(Path(__file__).resolve().parent)

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ["PYTHONPATH"] = backend_dir + os.pathsep + os.environ.get("PYTHONPATH", "")

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    host = os.environ.get("HOST", "0.0.0.0")

    is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    reload = not is_production

    env_file_path = os.path.join(backend_dir, ".env")
    env_file = env_file_path if os.path.exists(env_file_path) else None

    print(f"Starting BitCred API on {host}:{port} (production={is_production})")

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[backend_dir] if reload else None,
        env_file=env_file,
    )