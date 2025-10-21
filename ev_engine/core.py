#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | ev_engine/core.py
EV 引擎：贝叶斯胜率估计 + 动态 G/L 调整 + 风报比优化 + 多层决策引擎
"""

import numpy as np
import logging
from typing import Dict, Any, Tuple
from scipy.stats import beta

logger = logging.getLogger("EVEngine")


class EVEngine:
    def __init__(self, config: Dict[str, Any], signal_engine):
        """
        :param config: production.json 配置文件
        :param signal_engine: SignalEngine 实例（提供实时信号）
        """
        self.config = config
        self.signal_engine = signal_engine
        self.beta_prior = config["ev_engine"]["estimation"]["beta_prior"]
        self.base_threshold = config["ev_engine"]["dynamic_thresholds"]["base_threshold"]
        self.trade_window = config["ev_engine"]["estimation"]["window_trades"]
        self.history = []  # 用于后验胜率更新和再训练

    def calculate_ev_for_symbol(self, symbol: str, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        对单一币种计算 EV、胜率、期望收益等指标
        :param symbol: 币种名称
        :param market_state: 市场特征（波动率、成交量、深度、结构等）
        """
        signal_data = self.signal_engine.get_signal(symbol)
        if not signal_data:
            return {}

        score = signal_data["signal_score"]
        components = signal_data["components"]

        # === 胜率估计 p ===
        p = self._estimate_probability(symbol, score, market_state)

        # === 收益潜力 G ===
        G = self._estimate_gain(market_state)

        # === 风险损失 L ===
        L = self._estimate_loss(market_state)

        # === EV 计算 ===
        ev = p * G - (1 - p) * L - self._estimate_fees(market_state)

        # === 分层与策略决策 ===
        tier = self._classify_ev(ev)
        optimal_leverage = self._recommend_leverage(ev)
        position_size = self._dynamic_kelly(p, G, L)

        # === 存储历史，用于自学习 ===
        self._record_history(symbol, p, G, L, ev, tier)

        return {
            "symbol": symbol,
            "p_win": p,
            "G": G,
            "L": L,
            "EV": ev,
            "tier": tier,
            "kelly_position": position_size,
            "recommended_leverage": optimal_leverage,
            "components": components
        }

    def _estimate_probability(self, symbol: str, score: float, state: Dict[str, Any]) -> float:
        """
        胜率估计（贝叶斯 + 强化学习修正）
        """
        α0, β0 = self.beta_prior["alpha"], self.beta_prior["beta"]
        past_wins = sum(1 for t in self.history if t["symbol"] == symbol and t["win"])
        past_losses = sum(1 for t in self.history if t["symbol"] == symbol and not t["win"])

        α_post = α0 + past_wins + (score * 10)
        β_post = β0 + past_losses + (1 - score) * 10

        # Beta 后验均值作为 p
        p = α_post / (α_post + β_post)

        # 加入市场修正：波动率高时降低信心，趋势一致时提升信心
        vol_penalty = np.exp(-state.get("volatility", 0.5))
        trend_boost = 1 + 0.15 * state.get("trend_consistency", 0.0)
        p *= vol_penalty * trend_boost

        return np.clip(p, 0.01, 0.99)

    def _estimate_gain(self, state: Dict[str, Any]) -> float:
        """
        收益潜力 G：基于波动率、成交量和结构空间
        """
        atr = state.get("ATR", 0.01)
        momentum = state.get("momentum", 1.0)
        liquidity = state.get("liquidity_score", 1.0)

        # 收益潜力基准：波动率 + 动量 + 流动性乘数
        G = 1 + 3 * atr * momentum * liquidity
        return np.clip(G, 0.5, 5.0)

    def _estimate_loss(self, state: Dict[str, Any]) -> float:
        """
        风险损失 L：基于支撑结构、市场深度与波动风险
        """
        vol = state.get("volatility", 1.0)
        depth = state.get("depth_score", 1.0)
        slippage = state.get("slippage", 0.01)

        # 损失函数：波动越大、深度越低、滑点越高 → L 越大
        L = 1 + 2 * vol * (1 / depth) + slippage * 10
        return np.clip(L, 0.5, 5.0)

    def _estimate_fees(self, state: Dict[str, Any]) -> float:
        """
        费用估计：基础手续费 + 资金费率成本 + 滑点惩罚
        """
        base_fee = 0.0016
        funding = abs(state.get("funding_rate", 0.0)) * 10
        slippage_cost = state.get("slippage", 0.01) * 2

        return base_fee + funding + slippage_cost

    def _classify_ev(self, ev: float) -> str:
        """
        EV 分层决策
        """
        if ev >= 0.35:
            return "T1_explosive"
        elif ev >= 0.20:
            return "T2_strong"
        elif ev >= 0.10:
            return "T3_moderate"
        elif ev >= 0.03:
            return "T4_neutral"
        elif ev >= -0.02:
            return "T5_scalping"
        else:
            return "T6_defensive"

    def _recommend_leverage(self, ev: float) -> int:
        """
        根据信号 EV 推荐杠杆区间
        """
        if ev >= 0.35:
            return np.random.randint(90, 120)
        elif ev >= 0.20:
            return np.random.randint(50, 85)
        elif ev >= 0.10:
            return np.random.randint(20, 50)
        elif ev >= 0.03:
            return np.random.randint(10, 30)
        elif ev >= -0.02:
            return np.random.randint(5, 15)
        else:
            return np.random.randint(1, 5)

    def _dynamic_kelly(self, p: float, G: float, L: float) -> float:
        """
        动态 Kelly 仓位控制：考虑波动性和信号置信度
        """
        edge = (p * (G + 1)) - (1 - p) * L
        b = G / L if L != 0 else 1
        kelly_fraction = (p * (b + 1) - 1) / b
        return np.clip(kelly_fraction, 0.0, 0.25)  # 限制最大仓位为总资产的25%

    def _record_history(self, symbol: str, p: float, G: float, L: float, ev: float, tier: str):
        """
        保存交易结果到历史数据库，用于 AI 强化学习 & 胜率校准
        """
        self.history.append({
            "symbol": symbol,
            "p": p,
            "G": G,
            "L": L,
            "EV": ev,
            "tier": tier,
            "win": ev > 0
        })
        if len(self.history) > self.trade_window:
            self.history.pop(0)
