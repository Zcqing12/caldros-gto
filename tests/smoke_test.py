#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO | tests/smoke_test.py
全链路烟雾测试：确保系统的每个核心组件都能正确初始化和协同工作。
"""

import sys
import json
import asyncio
import logging
from pathlib import Path

# === 模块导入 ===
from caldros_gto.data_ingestion import feeds
from caldros_gto.signal_engine import core as signal_core
from caldros_gto.ev_engine import core as ev_core
from caldros_gto.execution_system import executor
from caldros_gto.risk_management import manager

logger = logging.getLogger("SmokeTest")

async def run_smoke_test():
    logger.info("🚀 启动 CALDROS-GTO 烟雾测试...")

    # 1️⃣ 加载配置
    cfg_path = Path("production.json")
    if not cfg_path.exists():
        raise FileNotFoundError("❌ 未找到 production.json 配置文件")
    cfg = json.loads(cfg_path.read_text())
    logger.info("✅ 配置加载成功")

    # 2️⃣ 数据流
    data_ok = await feeds.test_connection()
    assert data_ok, "❌ 数据源连接失败"
    logger.info("✅ 数据采集模块通过")

    # 3️⃣ 信号引擎
    signal = signal_core.generate_dummy_signal()
    assert signal is not None, "❌ 信号引擎未返回信号"
    logger.info(f"✅ 信号生成成功: {signal}")

    # 4️⃣ EV 引擎
    ev_value = ev_core.calculate_ev(signal)
    assert isinstance(ev_value, float), "❌ EV 计算失败"
    logger.info(f"✅ EV 计算结果: {ev_value:.4f}")

    # 5️⃣ 执行系统
    result = executor.simulate_trade(signal, ev_value)
    assert result.get("status") == "ok", "❌ 执行系统异常"
    logger.info("✅ 执行系统通过")

    # 6️⃣ 风控系统
    risk_ok = manager.run_risk_checks(result)
    assert risk_ok, "❌ 风控系统未通过"
    logger.info("✅ 风控系统通过")

    logger.info("🎉 烟雾测试全部通过，系统可安全启动")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
