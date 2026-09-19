"""FastAPI 入口:提供规划 API 与静态前端页面。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .planner import plan
from .schemas import PlanRequest

app = FastAPI(
    title="冷链装箱温控规划器 API",
    description="按温区兼容与容量约束生成冷链分箱方案,支持分段运输逐段温区校验"
    "与累计热暴露(度时)预算",
    version="1.2.0",
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """规划器抛出的业务校验错误统一返回 400,消息直接展示给用户。"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/plan", tags=["plan"])
async def api_plan(req: PlanRequest) -> dict:
    return plan(req.model_dump())


# 前端静态资源(挂载在最后,避免覆盖 /api 与 /docs)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
