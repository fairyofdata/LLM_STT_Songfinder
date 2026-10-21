# 아키텍처 결정 기록 (ADR)

Songfinder 평가 작업(2026-10-21~22)에서 내린 결정을 소급해 기록합니다. 맥락과 수치는 [연구개발 기록](../RESEARCH_LOG.md)에 있습니다.
LocalTTS 자체의 결정은 그 저장소의 `docs/adr/`에 따로 있습니다.

| 번호 | 결정 | 날짜 |
|---|---|---|
| [0001](0001-reimplement-app-logic-and-verify.md) | 평가 코드에서 앱 로직을 재구현하고 원본과 대조한다 | 2026-10-21 |
| [0002](0002-no-lyric-text-in-outputs.md) | 가사 원문을 어떤 산출물에도 새로 내보내지 않는다 | 2026-10-21 |
| [0003](0003-song-level-ground-truth.md) | 정답 단위는 곡이고, 줄 검색 결과를 곡으로 묶는다 | 2026-10-21 |
| [0004](0004-report-bug-without-fixing.md) | 요약 분기 버그는 고치지 않고 두 변형을 평가해 보고한다 | 2026-10-21 |
| [0005](0005-tts-speech-as-proxy.md) | TTS 음성은 사용자 음성의 대용으로, 상대 비교에만 쓴다 | 2026-10-21 |
| [0006](0006-local-tts-stt-service.md) | 음성 생성·인식은 별도 저장소의 로컬 서버(LocalTTS)로 한다 | 2026-10-21 |
| [0007](0007-app-length-voice-queries.md) | 음성 질의는 앱이 받는 길이(약 5~15초)로 만들고, 짧으면 무음을 붙인다 | 2026-10-21 |
| [0008](0008-memory-error-perturbations.md) | 기억 오류는 문절 단위 7유형으로 흉내 내고, 사람이 맹검으로 검수한다 | 2026-10-21 |
| [0009](0009-song-level-uncertainty.md) | 불확실성은 곡 단위 부트스트랩, 짝지은 비교는 McNemar로 낸다 | 2026-10-21 |
| [0010](0010-noise-curves-three-seeds.md) | 교란 곡선은 시드 5개 대신 3개로 확정한다 | 2026-10-22 |
| [0011](0011-korean-speaker-approximation.md) | 한국인 발음은 한글 독음 변환 + 한국어 TTS로 근사한다 | 2026-10-21 |
| [0012](0012-estimate-fixes-from-existing-transcripts.md) | 개선안 효과는 앱을 바꾸지 않고 기존 전사문으로 추정하고, 따로 떼어 둔 질의로 확인한다 | 2026-10-22 |
