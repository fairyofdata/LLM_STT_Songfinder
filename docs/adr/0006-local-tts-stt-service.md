# ADR-0006: 음성 생성·인식은 별도 저장소의 로컬 서버(LocalTTS)로 한다

- 상태: 채택
- 결정일: 2026-10-21
- 기록: 2026-10-22 소급 작성 (근거: [연구개발 기록](../RESEARCH_LOG.md))

## 맥락
조건 수 × 목소리 수만큼 음성이 필요하다. API로 하면 조건마다 비용이 쌓이고, 사용자는 다른 프로젝트에서도 로컬 TTS를 쓰고 싶어 했다. RTX 3070(8GB)이 있다.

## 결정
- `C:\Users\fairy\LocalTTS`에 별도 git 저장소로 만든다(원격 없음). OpenAI 호환 HTTP 서버(127.0.0.1:8880), Python API, CLI를 제공한다.
- Songfinder 평가는 이 서버를 HTTP로 부른다. 가사가 파일로 남지 않고, 다른 프로젝트와 같은 방식으로 쓴다는 것을 보여 준다.
- 엔진: Kokoro, Supertonic-3, Windows OneCore 음성, Whisper large-v3. 선정 이유와 3.14 호환 우회는 LocalTTS의 `docs/adr/`에 있다.
- 앱과 같은 `whisper-1`로의 추가 교차 확인은 비용(약 $0.7) 문제라 사용자 결정으로 남긴다.

## 결과
- 받아쓰기 8,996번을 무료로, 약 1시간 안에 처리했다(GPU 일괄 처리).
- 로컬 STT(large-v3)는 앱의 STT(`whisper-1`)와 다른 모델이다. 수치를 앱 그대로라고 쓰지 않는다.
