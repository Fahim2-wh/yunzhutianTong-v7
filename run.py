import os
import uvicorn

os.environ.setdefault("YZT_SECRET_KEY", "yunzhutong-v8-change-me")
os.environ.setdefault("YOLO_MODE", "auto")
uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
