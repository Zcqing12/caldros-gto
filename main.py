#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | main.py
主控入口：负责系统初始化、调度、模块加载与服务启动。
"""

import asyncio
import logging
import uvicorn
from fastapi import FastAPI

from caldros_gto.configs.loader import load_config
from caldros_gto.data_ingestion.manager import DataIngestionManager
from caldros_gto.signal_engine.core import SignalEngine
from caldros_gto.ev_engine.core import EVEngine
from caldros_gto.execution_system.executor import ExecutionSystem
from caldros_gto.risk_management.manager import RiskManager
from caldros_gto.ai_adaptation.trainer import AIAdaptation
from caldros_gto.ops_monitor.monitor import OpsMonitor
from caldros_gto.backtesting.runner import Backtester
from caldros_gto.simulation.stress import StressTester

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("CALDROS-GTO")

# === FastAPI 初始化 ===
app = FastAPI(title="CALDROS-GTO V19", version="1.0.0")

# === 全局组件容器 ===
components = {}

@app.on_event("startup")
async def startup_event():
    """
    启动时自动执行：
    1. 加载配置
    2. 初始化各模块
    3. 启动回测 & 数据流
    4. 触发AI自适应循环
    """
    logger.info("🚀 CALDROS-GTO V19 启动中...")

    config = load_config("production.json")
    components["config"] = config

    # 初始化模块
    components["data_ingestion"] = DataIngestionManager(config)
    components["signal_engine"] = SignalEngine(config)
    components["ev_engine"] = EVEngine(config)
    components["execution_system"] = ExecutionSystem(config)
    components["risk_manager"] = RiskManager(config)
    components["ai_adaptation"] = AIAdaptation(config)
    components["ops_monitor"] = OpsMonitor(config)
    components["backtester"] = Backtester(config)
    components["stress_tester"] = StressTester(config)

    # 历史回测（首次启动校准）
    logger.info("📊 启动历史回测以校准初始参数...")
    await components["backtester"].run_initial_backtest()

    # 实时数据采集
    logger.info("📡 启动数据采集引擎...")
    asyncio.create_task(components["data_ingestion"].start_stream())

    # 信号计算 + EV 模块
    logger.info("📈 启动信号融合与期望值计算...")
    asyncio.create_task(components["signal_engine"].start_loop())
    asyncio.create_task(components["ev_engine"].start_loop())

    # 执行系统
    logger.info("⚙️ 启动交易执行引擎...")
    asyncio.create_task(components["execution_system"].start_loop())

    # AI 自适应调优
    logger.info("🧠 启动 AI 自进化模块...")
    asyncio.create_task(components["ai_adaptation"].start_learning_loop())

    # 运维监控
    logger.info("📊 启动监控模块...")
    asyncio.create_task(components["ops_monitor"].start_metrics_loop())

    logger.info("✅ 系统初始化完成，实盘交易已准备就绪。")

@app.get("/")
async def root():
    return {"status": "running", "version": "V19", "message": "CALDROS-GTO ready."}

@app.post("/api/auto-build")
async def auto_build():
    return {"status": "ok", "detail": "Auto-build pipeline triggered."}

@app.post("/api/backtest")
async def run_backtest():
    result = await components["backtester"].run_manual_backtest()
    return {"status": "completed", "result": result}

@app.post("/api/stress")
async def run_stress_test():
    result = await components["stress_tester"].run_all()
    return {"status": "completed", "result": result}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
