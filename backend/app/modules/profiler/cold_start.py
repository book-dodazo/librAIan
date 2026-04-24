"""
콜드 스타트 분석 모듈.

시스템 시작 시간을 분석합니다.
나중에 시작 성능 최적화에 사용됩니다.
"""

import time
from typing import Dict, Any


class ColdStartAnalyzer:
    """콜드 스타트 분석기."""

    def __init__(self) -> None:
        """분석기 초기화."""
        self.start_time = None
        self.checkpoints = {}

    def start_measurement(self) -> None:
        """측정 시작."""
        self.start_time = time.time()
        self.checkpoints = {}

    def checkpoint(self, name: str) -> None:
        """체크포인트 기록.

        Args:
            name: 체크포인트 이름
        """
        if self.start_time is None:
            raise ValueError("측정이 시작되지 않았습니다.")
        self.checkpoints[name] = time.time()

    def get_report(self) -> Dict[str, Any]:
        """분석 리포트 생성.

        Returns:
            분석 결과
        """
        if self.start_time is None:
            return {}

        total_time = time.time() - self.start_time

        checkpoint_times = {}
        prev_time = self.start_time
        for name, checkpoint_time in self.checkpoints.items():
            checkpoint_times[name] = checkpoint_time - prev_time
            prev_time = checkpoint_time

        return {
            "total_startup_time": total_time,
            "checkpoint_times": checkpoint_times,
            "checkpoints": list(self.checkpoints.keys())
        }