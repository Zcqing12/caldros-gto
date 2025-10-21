#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | execution_system/executor.py
交易执行系统：信号→下单→动态退出→仓位轮换→风险联动
"""

import time
import logging
import random
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("ExecutionEngine")

class ExecutionEngine:
    def __init__(self, binance_client, ev_engine, accounting, risk_manager, config):
        """
        :param binance_client: Binance API 客户端
        :param ev_engine: EVEngine 实例
        :param accounting: Accounting 模块（余额、保证金、资金利用率）
        :param risk_manager: RiskManager 模块（风控、断路器）
        :param config: production.json 配置
        """
        self.client = binance_client
        self.ev_engine = ev_engine
        self.accounting = accounting
        self.risk_manager = risk_manager
        self.config = config
        self.active_positions = {}
        self.cooldowns = {}
        self.trade_log = []

    # === 入口：执行一轮交易决策 ===
    def execute_cycle(self, market_snapshot: Dict[str, Any]) -> None:
        """
        每次信号刷新时调用，执行下单/退出/轮换
        """
        for symbol, state in market_snapshot.items():
            ev_result = self.ev_engine.calculate_ev_for_symbol(symbol, state)
            if not ev_result:
                continue

            ev = ev_result["EV"]
            tier = ev_result["tier"]
            leverage = ev_result["recommended_leverage"]
            position_size = ev_result["kelly_position"]

            # 检查风控与冷却
            if not self._check_risk(symbol, ev):
                continue
            if self._in_cooldown(symbol):
                continue

            # 有仓位 → 判断是否需要退出或轮换
            if symbol in self.active_positions:
                self._maybe_exit(symbol, ev_result)
                self._maybe_rotate(symbol, ev_result)
            else:
                # 无仓位 → 决定是否建仓
                if ev > self.config["ev_engine"]["dynamic_thresholds"]["base_threshold"]:
                    self._enter_position(symbol, ev_result, leverage, position_size)

    # === 建仓 ===
    def _enter_position(self, symbol: str, ev_result: Dict[str, Any], leverage: int, position_size: float):
        """
        下单开仓
        """
        balance = self.accounting.get_available_balance()
        order_notional = balance * position_size * leverage

        logger.info(f"[ENTRY] {symbol} | EV: {ev_result['EV']:.3f} | Size: {order_notional:.2f} | Lev: {leverage}x")

        order = self._mock_order(
            symbol=symbol,
            side="BUY" if ev_result["p_win"] > 0.5 else "SELL",
            size=order_notional,
            leverage=leverage
        )

        self.active_positions[symbol] = {
            "entry_time": datetime.utcnow(),
            "entry_price": ev_result["components"].get("price", 0),
            "leverage": leverage,
            "notional": order_notional,
            "ev_entry": ev_result["EV"],
            "direction": order["side"],
            "open": True
        }

        self.trade_log.append(order)

    # === 退出逻辑 ===
    def _maybe_exit(self, symbol: str, ev_result: Dict[str, Any]):
        """
        判断是否触发退出条件（止盈、止损、信号失效、时间）
        """
        pos = self.active_positions[symbol]
        current_ev = ev_result["EV"]
        time_held = datetime.utcnow() - pos["entry_time"]

        # 条件 1：信号失效
        if current_ev < 0 or ev_result["p_win"] < 0.5:
            self._exit_position(symbol, reason="Signal invalid")

        # 条件 2：时间超限
        max_holding = timedelta(hours=24)
        if time_held > max_holding:
            self._exit_position(symbol, reason="Time exceeded")

        # 条件 3：15分钟无收益
        if time_held > timedelta(minutes=15) and not self._position_profitable(symbol):
            self._exit_position(symbol, reason="No profit after 15m")

        # 条件 4：EV 大幅衰减
        if current_ev < 0.5 * pos["ev_entry"]:
            self._exit_position(symbol, reason="EV decayed")

    # === 仓位轮换 ===
    def _maybe_rotate(self, symbol: str, ev_result: Dict[str, Any]):
        """
        如果有更高 EV 的仓位 → 自动轮换
        """
        pos = self.active_positions[symbol]
        current_ev = ev_result["EV"]
        if current_ev < ev_result["ev_entry"]:
            return
        if current_ev < 0.8 * max(p["ev_entry"] for p in self.active_positions.values()):
            return

        # 替换为更优仓位
        self._exit_position(symbol, reason="Rotated for higher EV")
        self._enter_position(symbol, ev_result, ev_result["recommended_leverage"], ev_result["kelly_position"])

    # === 平仓 ===
    def _exit_position(self, symbol: str, reason: str):
        """
        平仓逻辑
        """
        pos = self.active_positions.pop(symbol, None)
        if not pos:
            return

        logger.info(f"[EXIT] {symbol} | Reason: {reason}")
        self.cooldowns[symbol] = datetime.utcnow() + timedelta(minutes=5)

    # === 检查风险 ===
    def _check_risk(self, symbol: str, ev: float) -> bool:
        """
        检查风险指标是否允许交易
        """
        if self.risk_manager.check_circuit_breaker():
            logger.warning("[RISK] Circuit breaker active, trading paused.")
            return False
        if ev < -0.05:
            logger.warning(f"[RISK] Negative EV detected for {symbol}, skipping.")
            return False
        return True

    def _in_cooldown(self, symbol: str) -> bool:
        """
        检查冷却时间
        """
        if symbol in self.cooldowns and datetime.utcnow() < self.cooldowns[symbol]:
            return True
        return False

    def _position_profitable(self, symbol: str) -> bool:
        """
        模拟：判断当前仓位是否盈利
        （实盘应通过未实现盈亏计算）
        """
        return random.choice([True, False])

    def _mock_order(self, symbol: str, side: str, size: float, leverage: int) -> Dict[str, Any]:
        """
        模拟下单（实盘应替换为 Binance API 下单）
        """
        return {
            "symbol": symbol,
            "side": side,
            "size": size,
            "leverage": leverage,
            "timestamp": datetime.utcnow().isoformat()
        }
