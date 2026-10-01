from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.api.api:app", host="127.0.0.1", port=4001, reload=True)
