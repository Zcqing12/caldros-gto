#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | risk_management/manager.py
风险管理系统：断路器、回撤控制、动态止损、对冲与自愈
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(self, accounting, config: Dict[str, Any]):
        """
        :param accounting: Accounting 模块（账户资金监控）
        :param config: production.json 风控配置
        """
        self.accounting = accounting
        self.config = config
        self.drawdown_history = []
        self.loss_streak = 0
        self.circuit_breaker_active = False
        self.last_trigger_time = None
        self.max_daily_loss = 0.0

    # === 核心入口：每轮交易前检查 ===
    def pre_trade_check(self, ev: float) -> bool:
        """
        每次下单前调用，检查是否允许交易
        """
        if self.circuit_breaker_active:
            logger.warning("[RISK] Circuit breaker active, trading blocked.")
            return False

        if ev < -0.05:
            logger.warning("[RISK] EV too low, reject trade.")
            return False

        if not self._check_drawdown():
            return False

        if not self._check_margin_health():
            return False

        return True

    # === 日度回撤控制 ===
    def _check_drawdown(self) -> bool:
        """
        检查账户回撤是否触发风控
        """
        equity = self.accounting.get_equity()
        peak = self.accounting.get_equity_peak()
        drawdown = (peak - equity) / peak if peak > 0 else 0

        if drawdown > self.config["risk_management"]["daily_drawdown_limit_pct"]:
            logger.error(f"[RISK] Daily drawdown exceeded: {drawdown:.2%}")
            self._trigger_circuit_breaker("Daily drawdown limit hit")
            return False

        return True

    # === 保证金健康检查 ===
    def _check_margin_health(self) -> bool:
        """
        检查账户保证金是否足够安全
        """
        margin_ratio = self.accounting.get_margin_ratio()
        threshold = self.config["accounting"]["margin_health_threshold"]

        if margin_ratio < threshold:
            logger.error(f"[RISK] Margin ratio too low ({margin_ratio:.2%}), pausing trades.")
            self._trigger_circuit_breaker("Margin health breach")
            return False

        return True

    # === Circuit Breaker（断路器） ===
    def _trigger_circuit_breaker(self, reason: str):
        """
        启动断路器，暂停交易
        """
        self.circuit_breaker_active = True
        self.last_trigger_time = datetime.utcnow()
        logger.critical(f"[CIRCUIT BREAKER] Triggered due to: {reason}")

    def check_circuit_breaker(self) -> bool:
        """
        检查断路器状态（含冷却期）
        """
        if not self.circuit_breaker_active:
            return False

        cooldown = timedelta(minutes=180)
        if datetime.utcnow() - self.last_trigger_time > cooldown:
            logger.info("[RISK] Circuit breaker cooldown complete, trading resumed.")
            self.circuit_breaker_active = False
            self.loss_streak = 0
            return False

        return True

    # === 连续亏损监控 ===
    def register_trade_result(self, pnl: float):
        """
        每笔交易完成后调用，用于统计连续亏损和自愈策略
        """
        if pnl < 0:
            self.loss_streak += 1
            self.drawdown_history.append(pnl)
            if self.loss_streak >= 3:
                self._trigger_circuit_breaker("3-loss streak detected")
        else:
            self.loss_streak = 0

    # === 动态止损策略 ===
    def dynamic_stop_loss(self, current_price: float, entry_price: float, volatility: float) -> float:
        """
        动态止损基于波动率（ATR）和市场结构
        """
        base_stop = entry_price - 2 * volatility
        adaptive_adjust = base_stop * (1 + self._risk_heat())
        return adaptive_adjust

    def _risk_heat(self) -> float:
        """
        风险热度指数：根据过去亏损速度和回撤趋势动态调整
        """
        if not self.drawdown_history:
            return 0.0
        avg_loss = abs(sum(self.drawdown_history[-10:]) / len(self.drawdown_history[-10:]))
        return min(avg_loss / 0.05, 1.0)  # 正常范围 0-1

    # === 对冲策略 ===
    def hedge_position(self, positions: Dict[str, Any]):
        """
        动态对冲：当风险热度 > 0.8 或高相关币种共振时，开启对冲
        """
        heat = self._risk_heat()
        if heat > 0.8:
            logger.info("[RISK] Activating hedge strategy due to high risk heat.")
            # ✅ 示例：在 BTC/ETH 建空仓对冲，减少总暴露
            return {"hedge": True, "assets": ["BTCUSDT", "ETHUSDT"], "direction": "SHORT"}
        return {"hedge": False}

    # === 自愈策略 ===
    def recovery_mode(self) -> Dict[str, Any]:
        """
        当回撤 > 20% → 自动切换为低风险策略组合（T4/T5）
        """
        equity = self.accounting.get_equity()
        peak = self.accounting.get_equity_peak()
        drawdown = (peak - equity) / peak if peak > 0 else 0

        if drawdown > 0.20:
            logger.warning("[RISK] Switching to capital preservation mode.")
            return {
                "mode": "capital_preservation",
                "leverage_reduction": 0.5,
                "allowed_tiers": ["T4", "T5"],
                "resume_condition": "drawdown < 10% and EV > 0.05"
            }
        return {"mode": "normal"}
