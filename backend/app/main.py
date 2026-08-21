from fastapi import FastAPI

app = FastAPI(title="AI Test Platform")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-test-platform"}
