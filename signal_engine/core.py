#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | signal_engine/core.py
信号引擎：多维信号融合 + 贝叶斯EV决策 + 动态权重与共识机制
"""

import numpy as np
import logging
import asyncio
from typing import Dict, Any, List, Tuple
from collections import deque
from datetime import datetime

logger = logging.getLogger("SignalEngine")

class SignalEngine:
    def __init__(self, config: Dict[str, Any], feature_source):
        """
        :param config: production.json 配置
        :param feature_source: DataIngestionManager 实例，用于获取实时特征
        """
        self.config = config
        self.feature_source = feature_source
        self.signals = {}
        self.history = deque(maxlen=1000)
        self.weights = config["signal_engine"]["fusion_logic"]["weights"]
        self.activation_threshold = config["signal_engine"]["fusion_logic"]["activation_threshold"]
        self.consistency_threshold = config["signal_engine"]["fusion_logic"]["consistency_factor"]["threshold"]

    async def run(self):
        """主循环：持续计算信号"""
        logger.info("🧠 启动信号融合引擎...")
        while True:
            try:
                features = self.feature_source.get_features()
                self.signals = self._compute_signals(features)
                logger.info("✅ 信号更新完成 %d 个交易对", len(self.signals))
            except Exception as e:
                logger.error(f"❌ 信号计算失败: {e}")
            await asyncio.sleep(10)

    def _compute_signals(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算所有交易对的最终信号评分
        :return: {symbol: {signal_score, EV, tier, breakdown}}
        """
        signals = {}
        for symbol, feat in features.items():
            score_breakdown, weighted_score = self._fusion(feat)
            ev, tier = self._ev_classify(weighted_score, feat)

            signals[symbol] = {
                "signal_score": weighted_score,
                "EV_estimate": ev,
                "tier": tier,
                "components": score_breakdown
            }

            # 存储历史，用于回测/AI再训练
            self.history.append({
                "t": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "score": weighted_score,
                "ev": ev,
                "tier": tier
            })

        return signals

    def _fusion(self, feat: Dict[str, Any]) -> Tuple[Dict[str, float], float]:
        """
        信号融合逻辑：技术面 + 资金面 + 信息面 + 链上
        输出加权得分
        """
        breakdown = {}
        total_score = 0.0

        # 📈 Breakout 信号
        breakout = 1 if feat.get("price_velocity", 0) > 0.0005 else 0
        breakdown["breakout"] = breakout * self.weights["breakout"]

        # ⚡ Momentum 信号（成交量加速度）
        momentum = min(feat.get("volume_acceleration", 0) / 5, 1)
        breakdown["momentum"] = momentum * self.weights["momentum"]

        # 🐋 Whale Flow 信号
        whale = min(feat.get("liquidation_heat", 0) / 10, 1)
        breakdown["whale_flow"] = whale * self.weights["whale_flow"]

        # 🪙 Orderbook Imbalance（流动性偏向）
        ob_imbalance = min(abs(feat.get("order_imbalance", 0)), 1)
        breakdown["orderbook_imbalance"] = ob_imbalance * self.weights["orderbook_imbalance"]

        # 📉 Funding Flip（资金方向信号）
        funding_flip = 0.2 if feat.get("funding_bias", 0) > 0 else -0.2
        breakdown["funding_flip"] = funding_flip * self.weights["funding_flip"]

        # 📢 信息面信号（宏观/社媒/ETF等）
        info_signal = feat.get("macro_sentiment_score", 0)
        breakdown["macro_sentiment"] = info_signal * self.weights["macro_sentiment"]

        # 🔗 链上信号（鲸鱼地址活跃度等）
        onchain = feat.get("onchain_score", 0)
        breakdown["onchain_flow"] = onchain * self.weights["onchain_flow"]

        # 🧪 ETF 流入
        etf_flow = feat.get("etf_flow_score", 0)
        breakdown["etf_flow"] = etf_flow * self.weights.get("etf_flow", 0)

        # 🧠 社交舆情
        social = feat.get("social_sentiment_score", 0)
        breakdown["social_sentiment"] = social * self.weights.get("social_sentiment", 0)

        # 汇总总分
        total_score = sum(breakdown.values())
        return breakdown, total_score

    def _ev_classify(self, score: float, feat: Dict[str, Any]) -> Tuple[float, str]:
        """
        根据信号分数和特征计算 EV 并分层
        """
        # 胜率估计：Sigmoid 转换（贝叶斯+RL）
        p = 1 / (1 + np.exp(-6 * (score - self.activation_threshold)))
        G = 1.0 + 2.5 * feat.get("volume_acceleration", 0) / 5
        L = 1.0 + feat.get("volatility", 1.0)

        ev = p * G - (1 - p) * L - 0.0016  # 减去手续费

        if ev >= 0.35:
            tier = "T1_explosive"
        elif ev >= 0.20:
            tier = "T2_strong"
        elif ev >= 0.10:
            tier = "T3_moderate"
        elif ev >= 0.03:
            tier = "T4_neutral"
        elif ev >= -0.02:
            tier = "T5_scalping"
        else:
            tier = "T6_defensive"

        return ev, tier

    def get_signal(self, symbol: str) -> Dict[str, Any]:
        """单一币种信号查询"""
        return self.signals.get(symbol, {})

    def get_all_signals(self) -> Dict[str, Any]:
        """获取所有当前信号"""
        return self.signals

    def get_historical_signals(self) -> List[Dict[str, Any]]:
        """获取历史信号轨迹（用于AI再训练）"""
        return list(self.history)
