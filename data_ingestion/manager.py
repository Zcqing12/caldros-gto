#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | data_ingestion/manager.py
实时数据采集引擎：行情、深度、资金费率、清算事件等全流量接入与预处理
"""

import asyncio
import json
import time
import logging
import aiohttp
import websockets
from collections import deque
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("DataIngestion")

class DataIngestionManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbols: List[str] = []
        self.raw_data = {}
        self.features = {}
        self.stream_tasks = []

        self.cadence = config["data_ingestion"]["cadence_seconds"]
        self.top_n = config["data_ingestion"]["top_symbols_tracking"]
        self.dynamic_selection = config["data_ingestion"]["dynamic_selection"]

        self.ws_endpoints = {
            "agg_trades": "wss://fstream.binance.com/ws/{symbol}@aggTrade",
            "kline": "wss://fstream.binance.com/ws/{symbol}@kline_1m",
            "orderbook": "wss://fstream.binance.com/ws/{symbol}@depth20@100ms",
            "liquidations": "wss://fstream.binance.com/ws/{symbol}@forceOrder"
        }

        # 缓存队列：用于计算价格动量、成交量加速度等特征
        self.price_cache = {}
        self.volume_cache = {}
        self.liquidation_cache = {}

    async def start_stream(self):
        """
        启动主数据流逻辑
        1. 动态选择Top N币种
        2. 建立WebSocket订阅
        3. 定时数据清洗与特征提取
        """
        await self._refresh_top_symbols()

        # 并行启动所有数据流
        self.stream_tasks = [
            asyncio.create_task(self._stream_ws("agg_trades")),
            asyncio.create_task(self._stream_ws("kline")),
            asyncio.create_task(self._stream_ws("orderbook")),
            asyncio.create_task(self._stream_ws("liquidations")),
            asyncio.create_task(self._periodic_feature_engineering())
        ]

        await asyncio.gather(*self.stream_tasks)

    async def _refresh_top_symbols(self):
        """通过成交量+波动率+舆情动态获取Top N交易对"""
        logger.info("🔎 动态选择 Top%d 币种...", self.top_n)
        async with aiohttp.ClientSession() as session:
            async with session.get("https://fapi.binance.com/fapi/v1/ticker/24hr") as resp:
                tickers = await resp.json()
        ranked = sorted(
            tickers,
            key=lambda x: float(x["quoteVolume"]) * float(x["priceChangePercent"]),
            reverse=True
        )
        self.symbols = [t["symbol"] for t in ranked if "USDT" in t["symbol"]][:self.top_n]
        logger.info("✅ 已选中交易对: %s", self.symbols)

    async def _stream_ws(self, source: str):
        """订阅指定WebSocket数据流"""
        logger.info(f"📡 启动数据流: {source}")
        while True:
            try:
                for symbol in self.symbols:
                    url = self.ws_endpoints[source].format(symbol=symbol.lower())
                    asyncio.create_task(self._connect_ws(url, source, symbol))
                break
            except Exception as e:
                logger.error(f"❌ WS连接失败 [{source}]: {e}")
                await asyncio.sleep(5)

    async def _connect_ws(self, url: str, source: str, symbol: str):
        """连接单一WebSocket流"""
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    async for msg in ws:
                        data = json.loads(msg)
                        await self._handle_message(source, symbol, data)
            except Exception as e:
                logger.warning(f"⚠️ WS断开 [{source} {symbol}]：{e}，重连中...")
                await asyncio.sleep(3)

    async def _handle_message(self, source: str, symbol: str, data: Dict[str, Any]):
        """解析消息并缓存"""
        ts = int(time.time() * 1000)
        if symbol not in self.raw_data:
            self.raw_data[symbol] = {}
        if source not in self.raw_data[symbol]:
            self.raw_data[symbol][source] = deque(maxlen=1000)

        self.raw_data[symbol][source].append({"t": ts, "data": data})

        # 针对不同数据类型，做即时缓存处理
        if source == "agg_trades":
            self._update_price_velocity(symbol, data)
        elif source == "liquidations":
            self._update_liquidation_impact(symbol, data)

    def _update_price_velocity(self, symbol: str, data: Dict[str, Any]):
        """计算价格速度（Δp/Δt）和成交量加速度"""
        price = float(data["p"])
        qty = float(data["q"])
        now = time.time()

        if symbol not in self.price_cache:
            self.price_cache[symbol] = deque(maxlen=50)
        if symbol not in self.volume_cache:
            self.volume_cache[symbol] = deque(maxlen=50)

        self.price_cache[symbol].append((now, price))
        self.volume_cache[symbol].append((now, qty))

    def _update_liquidation_impact(self, symbol: str, data: Dict[str, Any]):
        """记录大额清算事件"""
        notional = float(data["o"]["p"]) * float(data["o"]["q"])
        if symbol not in self.liquidation_cache:
            self.liquidation_cache[symbol] = deque(maxlen=100)
        self.liquidation_cache[symbol].append(notional)

    async def _periodic_feature_engineering(self):
        """周期性进行特征提取"""
        while True:
            await asyncio.sleep(self.cadence)
            try:
                self.features = self._compute_features()
                logger.info("📊 特征计算完成: %d 个交易对", len(self.features))
            except Exception as e:
                logger.error(f"❌ 特征计算失败: {e}")

    def _compute_features(self) -> Dict[str, Any]:
        """从缓存数据计算高阶特征"""
        features = {}
        for symbol in self.symbols:
            if symbol not in self.price_cache or len(self.price_cache[symbol]) < 5:
                continue

            # 价格动量
            t0, p0 = self.price_cache[symbol][0]
            t1, p1 = self.price_cache[symbol][-1]
            price_velocity = (p1 - p0) / max(t1 - t0, 1e-9)

            # 成交量加速度
            v_total = sum(q for _, q in self.volume_cache[symbol])
            v_avg = v_total / max(len(self.volume_cache[symbol]), 1)
            volume_accel = v_total / v_avg if v_avg > 0 else 0

            # 清算热度
            liq_heat = sum(self.liquidation_cache.get(symbol, [])) / 1e6

            features[symbol] = {
                "price_velocity": price_velocity,
                "volume_acceleration": volume_accel,
                "liquidation_heat": liq_heat
            }

        return features

    def get_features(self) -> Dict[str, Any]:
        """外部调用接口：返回实时特征"""
        return self.features

    def get_raw_data(self) -> Dict[str, Any]:
        """外部调用接口：返回原始数据"""
        return self.raw_data
