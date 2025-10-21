#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO | ai_adaptation/meta_loop.py
自进化循环：持续优化信号、参数、结构，保持系统适应性
"""

import time
import logging
from caldros_gto.ai_adaptation.trainer import Trainer
from caldros_gto.ai_adaptation.evaluator import Evaluator

logger = logging.getLogger("MetaLoop")

class MetaLearningLoop:
    def __init__(self, cfg):
        self.cfg = cfg
        self.trainer = Trainer(cfg)
        self.evaluator = Evaluator(cfg)

    def run(self):
        logger.info("🧬 启动自进化循环...")
        while True:
            # 1️⃣ 收集最新数据 & 信号结果
            self.trainer.collect_training_data()

            # 2️⃣ 重新训练贝叶斯模型 & RL 策略
            self.trainer.retrain_models()

            # 3️⃣ 性能评估与对比
            perf = self.evaluator.evaluate_performance()
            logger.info(f"📈 当前策略表现: {perf}")

            # 4️⃣ 若EV漂移 > 阈值 → 自动替换策略
            if perf["ev_drift"] > 0.15 or perf["win_rate"] < 0.45:
                self.trainer.mutate_strategy()
                logger.warning("⚠️ 策略漂移检测，已触发结构进化！")

            # 5️⃣ 等待下一轮（默认6小时）
            time.sleep(21600)

if __name__ == "__main__":
    from utils.config_loader import load_config
    cfg = load_config("production.json")
    loop = MetaLearningLoop(cfg)
    loop.run()
