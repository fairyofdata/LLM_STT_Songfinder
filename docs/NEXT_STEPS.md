# 이어서 할 일 (2026-10-24 기준)

평가 작업의 현재 상태와 재개 방법입니다. 배경은 [연구개발 기록](RESEARCH_LOG.md), 결정은 [ADR](adr/README.md)에 있습니다.

## 현재 상태

- **2026-10-24 가사 데이터 분리:** `line_metadata.json`, `song_metadata.json`을 비공개 레포 `LLM_STT_Songfinder-data`로 옮겼습니다.
  - 공개 레포는 git 기록 전체에서 두 파일을 지우고 강제 push했습니다. 그래서 모든 커밋 번호가 바뀌었습니다.
  - 재작성 전 전체 백업은 `C:\Users\fairy\LLM_STT_Songfinder_backup_2026-10-24.bundle`에 있습니다.
  - 자세한 내용은 [DATA.md](DATA.md)에 있습니다.
- **2026-10-23 서비스 단계 시작:** 브랜치 `service/search-quality`에서 검색을 `search.py`로 분리하고, 요약 분기 버그와 음성 개선 두 가지를 반영했습니다. 테스트 10개(`tests/`)와 전후 실측(`eval/compare_impl.py`)을 붙였습니다. 판정선, 짧은 줄 색인, 가사가 붙은 곡은 다음 단계입니다.

- **Songfinder:** 평가 코드, 결과, README, 포트폴리오 초안, 기록 문서를 모두 커밋했습니다.
  - **GitHub에 push 완료** (2026-10-22, `origin/master`).
  - **Hugging Face Space**는 가사가 든 옛 기록을 그대로 갖고 있어 비공개로 전환합니다(아래 「사용자가 할 일」).
- **LocalTTS** (`C:\Users\fairy\LocalTTS`): 별도 git 저장소이고 원격이 없습니다. 로컬 커밋만 했습니다.
- **앱 코드:** 2026-10-23부터 서비스 단계로 수정 중입니다([ADR-0013](adr/0013-search-module-and-voice-fixes.md)).
- **OpenAI API 사용:** 약 $0.50(`whisper-1` 음성 시험 1회)이 전부입니다.
- **LocalTTS 서버:** 정지했습니다(GPU 메모리 반환).

## 사용자 결정이 필요한 것

| 항목 | 근거 | 선택지 |
|---|---|---|
| 요약 분기 버그 (`search_pipeline_from_text`) | 2026-10-23 수정 (`search.py`, [ADR-0013](adr/0013-search-module-and-voice-fixes.md)) | 완료 |
| 텍스트 판정선 0.4 | DB에 없는 문장의 93%를 통과시킴, 0.8이면 7.8% | 올림 / 대조군을 늘려 다시 정함 |
| 음성: 한국어 감지 시 일본어 재전사 | 2026-10-23 `/stt`에 반영, 로컬 전사문 기준 한국인 발음 35.6 → 69.0% (투표와 함께) | 완료. `whisper-1`로 재측정 필요 |
| 음성: 줄 단위 조각 투표 | 2026-10-23 반영 (조건: 전체 코사인 < 0.9, 조각 3개 이상), 원어민 5줄 47.2 → 73.9% | 완료 |
| 짧은 가사 줄 색인 방식 | 오답 1순위의 25% | 앞뒤 줄과 묶어 색인 / 제외 / 그대로 |
| 줄로 나뉘지 않은 곡 1개 | `eval/results/data_quality.json`의 `unsplit_lines` | 데이터 정제 단계에서 줄 나누기 |
| 기존 README의 콧노래·흥얼거림 문구 | 앱은 가사를 받아 적어 검색하므로 성립하지 않는 주장 | 2026-10-22 「가사를 말하거나 입력」으로 정정함. 되돌릴지만 결정 |
| `whisper-1` 교차 확인 | 로컬 Whisper와 앱 STT의 차이 확인. 일부 표본으로 약 $0.7 | 실행 / 생략 |
| 공개 레포의 가사 메타데이터 | 2026-10-24 비공개 레포로 분리하고 공개 레포 기록에서 제거 | 완료 |

## 사용자가 할 일: Hugging Face Space 비공개 전환

Space(`fairyofdata/JPOP_STT_Module`)에는 가사 데이터 파일이 든 옛 기록(커밋 `df8e601`까지)이 공개돼 있습니다.
- Space 설정(Settings) → **Change visibility → Private**로 바꿔 주세요.
- 공개 레포의 기록을 다시 썼기 때문에, 예전에 안내한 「이어 붙이는 push」는 더 이상 맞지 않습니다. 실행하지 마세요.

## 사용자가 할 일: 사람 검수

1. `C:\Users\fairy\.cache\songfinder_eval\review\review_sheet_seed0.csv`를 엽니다(Excel 가능, UTF-8 BOM).
2. 100행마다 `rating (0/1/2)` 칸을 채웁니다.
   - 2: 사람이 이렇게 잘못 기억할 법함
   - 1: 애매함
   - 0: 기계적·비현실적
   - 유형은 일부러 가려 두었습니다.
3. 아래 명령을 실행해 `eval/results/review_summary.json`을 만듭니다.
   ```bash
   venv\Scripts\python eval/review_sheet.py ingest
   ```
4. `docs/PORTFOLIO.md`의 「(판정 후 채움)」 자리와 `docs/EVALUATION.md`의 교란 해석 문장을 그 결과로 갱신합니다.

## 재개 방법

```bash
C:\Users\fairy\LocalTTS\venv\Scripts\python.exe -m localtts serve --port 8880
```

- 위 명령은 로컬 음성 실험을 다시 돌릴 때만 필요합니다. Claude Code 데스크톱에서는 `.claude/launch.json`의 `localtts` 설정으로 미리보기 서버로 띄울 수 있습니다. 이 파일은 커밋하지 않았습니다.
- 평가 스크립트는 레포의 `venv`(CPU torch)로 돌리고, 명령은 [평가 상세](EVALUATION.md)의 「재현」 절에 있습니다.
- 받아쓰기와 음성은 캐시에 있으므로, 개선안을 바꿔 다시 추정할 때는 서버 없이 다음 명령만 돌리면 됩니다.
  ```bash
  venv\Scripts\python eval/audio_local_eval.py --score
  ```
  ```bash
  venv\Scripts\python eval/audio_fixes.py
  ```

## 다음 연구 후보 (우선순위 순)

1. **실제 녹음 소량 수집:** 한국인 5~10명 × 아는 곡 10~20개. 「기억나는 대로 말하기」와 「노래하기」 두 조건으로 하고, 동의를 받아 로컬에만 저장합니다. 실사용 수치를 말할 유일한 근거입니다.
2. **가나 읽기(발음) 기반 보조 색인 실험:** 소리 비슷한 말·동음 표기 교란과 한국인 발음 조건에서의 효과를 봅니다.
3. **개선안을 실제 앱 경로에 적용한 끝단 시험:** `/stt`에 실제 webm 녹음을 넣고 지연·비용을 잽니다(앱 수정 결정 뒤).
4. **추천 품질 평가 설계:** 정답이 없으므로 태그·장르 일치, 다양성, 사람 판정 중에서 고릅니다.
5. **음의 대조군 확대:** DB에 없는 다른 J-POP 가사를 쓰면 판정선을 다시 정할 근거가 됩니다. 이 가사는 레포에 넣지 않습니다.

## 정리할 것

| 대상 | 크기 | 내용 | 비고 |
|---|---:|---|---|
| `~/.cache/songfinder_eval/audio_local/` | 1.4GB | 가사 TTS 음성과 전사문 | 재추정에 필요. 끝나면 삭제 가능 |
| `~/.cache/songfinder_eval/review/` | — | 검수 시트와 유형 대응표 | 판정 전에는 지우지 말 것 |
| `~/.cache/huggingface/hub` | 11GB | Whisper large-v3, Kokoro, Supertonic, XLM-R, MiniLM 등 | 다른 프로젝트 모델과 공유 |
| `C:\Users\fairy\LocalTTS\venv` | 5.5GB | — | |
| 레포 `venv` | 1.6GB | — | gitignore 대상 |
| `.claude/launch.json` | — | — | 미추적. 원하면 `.gitignore`에 추가 |
