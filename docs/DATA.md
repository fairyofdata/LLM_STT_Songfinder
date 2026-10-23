# 데이터

Songfinder는 J-POP 차트 곡 461개의 가사, 메타데이터, 임베딩을 씁니다. **가사 원문은 저작권 때문에 이 공개 레포에 두지 않습니다.**

## 공개 / 비공개 구분

| 파일 | 내용 | 위치 |
|---|---|---|
| `line_metadata.json` | 가사 줄 22,806개 (`original_song_index`, `artist`, `title`, `line_text`) | **비공개** 레포 `LLM_STT_Songfinder-data` |
| `song_metadata.json` | 곡 461개: 제목, 아티스트, Spotify·Bugs id, 앨범 커버 URL, 가사 원문, LLM 요약, 태그 | **비공개** |
| `line_embeddings.npy` | 가사 줄 임베딩 22,806 × 384 (L2 정규화) | 공개 (Git LFS) |
| `song_embeddings.npy`, `summary_embeddings.npy` | 곡·요약 임베딩 461 × 384 | 공개 (Git LFS) |

- 임베딩은 [`paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)로 만든 숫자 벡터라 가사 원문을 담고 있지 않습니다.
- 2026-10-24에 두 JSON 파일을 이 레포의 git 기록 전체에서 지웠습니다. 그래서 그 이전 커밋 번호는 모두 바뀌었습니다.
- 평가 결과(`eval/results/`)와 문서에는 가사 문장이 없습니다. 질의는 id와 인덱스로만 기록했습니다([ADR-0002](adr/0002-no-lyric-text-in-outputs.md)).

## 데이터를 만든 과정

레포 루트의 노트북에 남아 있습니다.

1. `250807 …`: 일본 음원 차트에서 곡 목록 수집, 가사 수집
2. `250814 …`: 곡 id 정리, 언어 필터링, 중복 제거, 토큰화, 임베딩
3. `250825 …`: LLM으로 곡 태그와 요약 생성
4. `250901 …`: 앨범 커버 수집

## 실행할 때

앱(`app.py`)과 평가 코드는 두 JSON 파일이 있어야 돌아갑니다.
- 비공개 데이터 레포의 두 파일을 레포 루트에 두거나, 환경 변수 `SONGFINDER_DATA_DIR`로 그 폴더를 지정합니다.
- 루트의 두 파일은 `.gitignore`에 들어 있어 다시 커밋되지 않습니다.
- 데이터 없이도 `pytest -q tests`의 단위 테스트는 돌아갑니다(가짜 색인 사용). 실제 데이터가 필요한 통합 테스트는 자동으로 건너뜁니다.
