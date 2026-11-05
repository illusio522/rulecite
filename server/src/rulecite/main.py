from fastapi import FastAPI

app = FastAPI(title="RuleCite")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
