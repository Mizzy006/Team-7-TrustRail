import uvicorn
from fastapi import FastAPI

app = FastAPI(title="MandatePay Gateway Service Stub", version="1.0.0")

@app.get("/healthz")
def health_check():
    return {"status": "ok", "service": "gateway", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
