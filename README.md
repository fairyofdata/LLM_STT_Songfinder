# URFIT : LLM 음성인식(STT) 기반 플레이리스트 생성 커뮤니티 (리팩토링 버전)

> ⚠️ **알림**: 본 레포지토리는 기존 [Huggingface Space](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/tree/main)에서 구동되던 프로토타입을 **모던 웹 애플리케이션 아키텍처(Angular + FastAPI)** 로 완벽히 분리 및 리팩토링한 버전입니다. 이제 로컬 환경은 물론 Firebase, Cloud Run 등 다양한 클라우드 환경에 유연하게 배포할 수 있습니다.

URFIT은 "음성인식 기반 AI 플레이리스트 생성 커뮤니티"로, 머릿속에 맴도는 희미한 가사나 흥얼거리는 멜로디만으로도 원하는 J-POP을 찾아주는 서비스입니다. 기존 노래 검색 서비스의 한계인 '부정확한 가사로는 검색 불가'와 '단순 검색 이후의 확장성 부족'을 해결하기 위해 기획되었습니다. UR-FIT은 아래를 중의적으로 함축하여 모두 프로젝트의 목적과 정체성을 담아 지어진 프로젝트명입니다. 
>  * 한국어: 얼핏 듣다 (얼핏 들은 노래를 찾아주고, 해당 노래를 듣고 공유할 수 있는 플랫폼)
>  * 영어: Your(UR) Fit (Music Recognition & Recommendation)
>  * 일본어: 運命のリズム、触れ合う意味の繋がり。

## 🎵 주요 기능

  * **‘대충 아는 가사’로 ‘그 노래’ 찾기**: 사용자가 흥얼거리거나 불분명한 가사를 입력해도 노래를 찾아줍니다.
  * **AI 기반 유사 곡 추천**: 검색된 곡의 가사, 분위기, 장르 등을 복합적으로 분석하여 사용자 취향에 맞는 유사한 곡 3개를 추천합니다.
  * **Spotify 플레이리스트 생성**: 추천받은 곡들을 한 번에 모아 Spotify 플레이리스트로 만들 수 있습니다.
  * **AI 플레이리스트 타이틀/설명 생성**: OpenAI의 GPT 모델이 추천 곡들의 특징을 분석해 창의적인 플레이리스트 제목과 설명을 자동으로 생성합니다.
  * **커뮤니티 기능**: 검색한 곡과 플레이리스트를 다른 사용자와 공유하고 소통할 수 있는 커뮤니티 기능을 제공합니다.

-----

## 🛠 아키텍처 및 기술 스택 (리팩토링 적용)

기존 단일 애플리케이션 구조에서 확장성과 유지보수성을 위해 프론트엔드와 백엔드를 완벽히 분리했습니다.

### 1. Frontend (Angular)
  * **Framework**: Angular 17+ (기존 Vanilla JS/HTML 기반 코드 포팅)
  * **Styling**: TailwindCSS, SCSS
  * **주요 기능**: Spotify Web Playback SDK 연동, 마이크 오디오 스트림(MediaRecorder) 캡처 및 전송

### 2. Backend (FastAPI)
  * **Framework**: FastAPI (Python 3.10+)
  * **AI/ML**:
      * OpenAI **Whisper** (STT 변환)
      * **SentenceTransformer** (`paraphrase-multilingual-MiniLM-L12-v2`) 및 **FAISS** (가사 벡터 유사도 검색)
      * OpenAI **GPT-3.5-turbo** (플레이리스트 제목 및 설명 자동 생성)
  * **주요 기능**: Spotify OAuth 인증, STT 분석, 벡터 검색 API 제공, CORS 완벽 지원

-----

## 🚀 로컬 실행 방법 (How to Run)

프론트엔드와 백엔드 서버를 각각 실행해야 합니다.

### 사전 준비사항
1. Python 3.10+ 설치 (오류 시 `audioop-lts` 등 추가 확인)
2. Node.js (v18+) 및 npm 설치
3. [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)에서 앱 생성 및 `Client ID`, `Client Secret` 획득
   * **Redirect URI** 설정 필수: `http://localhost:7860/callback` (주의: https가 아닌 http 사용)
4. `.env` 파일 (또는 환경변수) 설정: `OPENAI_API_KEY`, `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI=http://localhost:7860/callback`

### 원클릭 실행 (Windows 전용)
바탕화면 등에 제공된 `Start_JPOP_Finder.bat` 파일을 더블클릭하면 프론트엔드와 백엔드가 동시에 실행됩니다. (최초 실행 시 AI 모델 다운로드로 인해 1~2분 소요될 수 있습니다.)

### 수동 실행
**1. Backend 서버 실행**
```bash
pip install -r requirements.txt
# 파이썬 3.13 이상 환경에서 오류 시: pip install audioop-lts
python app.py
```
* 서버가 `http://localhost:7860`에서 구동됩니다. (첫 실행 시 수백 MB 모델이 캐시 다운로드됩니다.)

**2. Frontend 서버 실행**
새 터미널을 열고 다음을 실행합니다.
```bash
cd frontend
npm install
npm start
```
* 서버가 `http://localhost:4200`에서 구동됩니다. 브라우저로 해당 주소에 접속하세요.

-----

## 🖼️ 사용 가이드

1. **검색 시작**: 메인 화면에서 **음성으로 찾기** 또는 **텍스트로 찾기** 버튼을 클릭합니다.
2. **STT 검색**: 마이크 권한을 허용하고 5~15초간 콧노래를 흥얼거리거나 가사를 말해보세요.
3. **결과 확인 및 재생**: FAISS 기반 검색 결과와 유사 곡들이 출력됩니다. Spotify 연동 후 Web Player로 바로 감상 가능합니다.
4. **플레이리스트 생성**: "이 곡들로 플레이리스트 만들기"를 누르면 AI가 제목/설명을 생성하여 내 Spotify 계정에 직접 저장해줍니다.

-----

## 💡 프로젝트의 가치 및 향후 계획

  * **AI 기술의 실용적 응용**: 사용자의 불편함을 해결하는 실용적인 서비스에 최신 AI 기술을 응용했습니다.
  * **확장 가능한 서비스 설계**: 마이크로서비스 아키텍처(분리형 구조)를 통해 향후 기능 확장이 용이하도록 설계했습니다.
  * **향후 계획**: 
    - 청취 기록 기반의 개인화 추천 기능 도입
    - Firebase Hosting (Frontend) + Cloud Run (Backend) 클라우드 배포 완전 자동화
    - 모바일 앱 버전 (Ionic / React Native) 출시를 통한 접근성 강화

-----

### 프로젝트 개요

* **프로젝트명**: URFIT (음성인식 기반 AI 플레이리스트 생성 커뮤니티)
* **개발 과정**: 한국무역협회 무역아카데미 Smart Cloud IT 과정 47기 프로젝트 (이후 모던 아키텍처 리팩토링)
* **개발 기간**: 2025년 7월 29일 ~ 2025년 9월 29일 (초기), 2026년 리팩토링 진행

### 저작권 고지

이 자료의 저작권은 한국무역협회 무역아카데미 Smart Cloud IT 과정 47기 팀 "노래불러조"에게 있으며, 허가 없이 복제, 배포, 전송, 전시 등의 행위를 금지합니다.
