#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CALDROS-GTO V19 | ops_monitor/monitor.py
系统运维 & 自愈引擎：实时监控、异常告警、自动修复、性能追踪
"""

import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("OpsMonitor")

class OpsMonitor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics = {}
        self.alert_thresholds = config.get("ops_monitor", {}).get("critical_thresholds", {})
        self.alert_channels = config.get("ops_monitor", {}).get("alerting", {}).get("channels", ["slack"])
        self.alert_url = config.get("SLACK_WEBHOOK", None)

    # === 1️⃣ 实时指标更新 ===
    def update_metric(self, name: str, value: float):
        self.metrics[name] = value
        logger.info(f"[Metrics] {name} = {value}")

    # === 2️⃣ 运行健康检测 ===
    def check_health(self) -> Dict[str, Any]:
        report = {}
        for metric, value in self.metrics.items():
            threshold = self.alert_thresholds.get(metric)
            if threshold is None:
                continue
            violated = self._evaluate_threshold(value, threshold)
            report[metric] = {"value": value, "threshold": threshold, "status": "ALERT" if violated else "OK"}
        return report

    def _evaluate_threshold(self, value: float, threshold: str) -> bool:
        """比较指标和阈值"""
        if threshold.startswith("<"):
            return value < float(threshold[1:])
        if threshold.startswith(">"):
            return value > float(threshold[1:])
        return False

    # === 3️⃣ 异常自动告警 ===
    def send_alert(self, message: str):
        logger.warning(f"[ALERT] {message}")
        if "slack" in self.alert_channels and self.alert_url:
            requests.post(self.alert_url, json={"text": message})

    def monitor_and_alert(self):
        report = self.check_health()
        for metric, r in report.items():
            if r["status"] == "ALERT":
                self.send_alert(f"⚠️ {metric} 超过阈值！当前值：{r['value']} | 阈值：{r['threshold']}")

    # === 4️⃣ 自我修复机制 ===
    def self_heal(self):
        """当指标持续异常时自动重启或修复"""
        critical_conditions = [
            ("EV_accuracy", lambda v: v < 0.60),
            ("signal_failure_rate", lambda v: v > 0.05),
            ("latency_ms", lambda v: v > 1000)
        ]

        for metric, cond in critical_conditions:
            val = self.metrics.get(metric)
            if val is not None and cond(val):
                self._restart_service(metric)
                break

    def _restart_service(self, reason: str):
        logger.warning(f"[Self-Heal] Restarting modules due to abnormal: {reason}")
        # 在实际部署中，可调用 docker restart 或 Kubernetes API：
        # os.system("docker restart caldros_gto_core")

    # === 5️⃣ 定期生成报告 ===
    def generate_daily_report(self) -> Dict[str, Any]:
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "PnL": self.metrics.get("pnl", 0.0),
            "Sharpe": self.metrics.get("sharpe_ratio", 0.0),
            "EV_accuracy": self.metrics.get("EV_accuracy", 0.0),
            "drawdown": self.metrics.get("max_drawdown", 0.0),
            "win_rate": self.metrics.get("win_rate", 0.0)
        }
        logger.info("[Report] Daily summary generated.")
        return report

    # === 6️⃣ 自动配置修复 ===
    def auto_patch_config(self):
        """当发现某些模块性能退化时，自动调整参数"""
        if self.metrics.get("alpha_decay_rate", 0) > 0.3:
            logger.info("[AutoPatch] Alpha decay too high. Lowering EV threshold.")
            self.config["ev_engine"]["dynamic_thresholds"]["base_threshold"] *= 0.9

    # === 7️⃣ 主循环 ===
    def run_monitor_loop(self, interval_sec: int = 60):
        while True:
            self.monitor_and_alert()
            self.self_heal()
            self.auto_patch_config()
            time.sleep(interval_sec)
