// 슬롯 관련 상수 — SlotStatusBar, ProfilePage 등에서 공통 사용
// 새 슬롯을 추가할 때 이 파일 하나만 수정하면 됩니다.

export const SLOT_DEFS = [
  { key: 'topic',         label: '주제',        fullLabel: '관심 주제' },
  { key: 'purpose',       label: '목적',        fullLabel: '독서 목적' },
  { key: 'reading_level', label: '독서 수준',   fullLabel: '독서 수준' },
  { key: 'mood',          label: '분위기',      fullLabel: '원하는 분위기' },
  { key: 'pages',         label: '페이지 수',   fullLabel: '선호 페이지 수' },
  { key: 'year',          label: '출판연도',    fullLabel: '출판 연도' },
  { key: 'availability',  label: '대출 여부',   fullLabel: '대출 가능 여부' },
];

// key → fullLabel 맵 (ProfilePage에서 사용)
export const SLOT_LABELS = Object.fromEntries(
  SLOT_DEFS.map(({ key, fullLabel }) => [key, fullLabel])
);
