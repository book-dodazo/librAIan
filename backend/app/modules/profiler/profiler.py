"""
프로파일러 모듈.

코드 실행 시간을 측정합니다.
나중에 성능 병목 분석에 사용됩니다.
"""

import time
from typing import Callable, Any
from contextlib import contextmanager


class Profiler:
    """프로파일러 클래스."""

    def __init__(self) -> None:
        """프로파일러 초기화."""
        self.timers = {}

    @contextmanager
    def timer(self, name: str):
        """타이머 컨텍스트 매니저.

        Args:
            name: 타이머 이름
        """
        start_time = time.time()
        try:
            yield
        finally:
            end_time = time.time()
            elapsed = end_time - start_time
            if name not in self.timers:
                self.timers[name] = []
            self.timers[name].append(elapsed)

    def profile_function(self, func: Callable, *args, **kwargs) -> Any:
        """함수 실행 프로파일링.

        Args:
            func: 프로파일링할 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과
        """
        func_name = func.__name__
        with self.timer(func_name):
            return func(*args, **kwargs)

    def get_stats(self, name: str = None) -> Dict[str, Any]:
        """타이머 통계 반환.

        Args:
            name: 특정 타이머 이름 (없으면 모두)

        Returns:
            통계 딕셔너리
        """
        if name:
            times = self.timers.get(name, [])
            if not times:
                return {}
            return {
                "count": len(times),
                "total": sum(times),
                "avg": sum(times) / len(times),
                "min": min(times),
                "max": max(times)
            }
        else:
            return {key: self.get_stats(key) for key in self.timers}