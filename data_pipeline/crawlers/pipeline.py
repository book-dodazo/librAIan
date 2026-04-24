"""
크롤링 파이프라인 모듈.

다양한 도서 API로부터 데이터를 수집하고 통합하는 파이프라인을 제공합니다.
나중에 데이터 수집 자동화에 사용됩니다.
"""

from typing import List, Dict, Any
from .aladin import AladinCrawler
from .yes24 import Yes24Crawler
from .naver import NaverCrawler


class CrawlingPipeline:
    """크롤링 파이프라인 클래스."""

    def __init__(self, aladin_key: str, yes24_key: str, naver_id: str, naver_secret: str) -> None:
        """파이프라인 초기화.

        Args:
            aladin_key: 알라딘 API 키
            yes24_key: 예스24 API 키
            naver_id: 네이버 클라이언트 ID
            naver_secret: 네이버 클라이언트 시크릿
        """
        self.crawlers = {
            'aladin': AladinCrawler(aladin_key),
            'yes24': Yes24Crawler(yes24_key),
            'naver': NaverCrawler(naver_id, naver_secret)
        }

    def collect_books(self, query: str, sources: List[str] = None) -> List[Dict[str, Any]]:
        """여러 소스로부터 도서 수집.

        Args:
            query: 검색 쿼리
            sources: 사용할 크롤러 리스트 (기본: 모두)

        Returns:
            통합된 도서 정보 리스트
        """
        if sources is None:
            sources = list(self.crawlers.keys())

        results = []
        for source in sources:
            if source in self.crawlers:
                results.extend(self.crawlers[source].search_books(query))

        # TODO: 중복 제거 및 통합 로직
        return results