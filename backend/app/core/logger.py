"""
로거 모듈.

애플리케이션 로깅을 설정합니다.
나중에 디버깅과 모니터링에 사용됩니다.
"""

import logging
import sys
from pathlib import Path


def setup_logger(name: str = "libraian", level: str = "INFO") -> logging.Logger:
    """로거 설정.

    Args:
        name: 로거 이름
        level: 로깅 레벨

    Returns:
        설정된 로거
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    # 포맷터
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


# 기본 로거
logger = setup_logger()