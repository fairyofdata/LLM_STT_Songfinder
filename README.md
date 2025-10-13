# URFIT (음성인식 기반 AI 플레이리스트 생성 커뮤니티)

> ⚠️ **알림**: 본 프로젝트의 핵심 모듈 프로토타입은 [Huggingface Space](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/tree/main)에 업로드되어 서버 역할을 겸하고 있어 Github 대신 [Huggingface Space](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/tree/main)를 통해 제공됩니다.

URFIT은 "음성인식 기반 AI 플레이리스트 생성 커뮤니티"로, 머릿속에 맴도는 희미한 가사나 흥얼거리는 멜로디만으로도 원하는 J-POP을 찾아주는 서비스입니다. 기존 노래 검색 서비스의 한계인 '부정확한 가사로는 검색 불가'와 '단순 검색 이후의 확장성 부족'을 해결하기 위해 기획되었습니다.

## 🎵 주요 기능

  * **‘대충 아는 가사’로 ‘그 노래’ 찾기**: 사용자가 흥얼거리거나 불분명한 가사를 입력해도 노래를 찾아줍니다.
  * **AI 기반 유사 곡 추천**: 검색된 곡의 가사, 분위기, 장르 등을 복합적으로 분석하여 사용자 취향에 맞는 유사한 곡 3개를 추천합니다.
  * **Spotify 플레이리스트 생성**: 추천받은 곡들을 한 번에 모아 Spotify 플레이리스트로 만들 수 있습니다.
  * **AI 플레이리스트 타이틀/설명 생성**: OpenAI의 GPT 모델이 추천 곡들의 특징을 분석해 창의적인 플레이리스트 제목과 설명을 자동으로 생성합니다.
  * **커뮤니티 기능**: 검색한 곡과 플레이리스트를 다른 사용자와 공유하고 소통할 수 있는 커뮤니티 기능을 제공합니다.

-----

## 🛠 아키텍처 및 기술 스택

### 전체 시스템 아키텍처

URFIT은 확장성을 고려하여 세 가지 주요 컴포넌트로 분리된 마이크로서비스 아키텍처로 설계되었습니다:

  * **Frontend**: 사용자 인터페이스를 담당하며, **React**로 구현됩니다.
  * **Main Server**: 백엔드 로직을 처리하는 메인 서버로, **Spring** 프레임워크 기반으로 구축됩니다.
  * **AI Server**: 음성 인식 및 AI 기반 추천 로직을 담당하는 서버로, **Python**과 **FastAPI**를 활용한 프로토타입 형태로 개발되었습니다.

### 기술 상세

  * **Frontend**: **React**, **Vite**, **TypeScript**를 사용하며, **Axios**를 통해 API 통신을 최적화하고 **React Query**로 캐싱 및 낙관적 업데이트를 적용해 사용자 경험을 향상시켰습니다.
  * **Backend**: **Spring Framework**를 사용하여 RESTful API를 구현했으며, **AWS**를 클라우드 인프라로 활용합니다. 데이터베이스는 **MySQL**, 캐시 및 세션 관리는 **Redis**를 사용합니다. 또한, 음성 파일 변환을 위해 **FFmpeg**이 사용됩니다.
  * **AI/ML**:
      * **음성-텍스트 변환 (STT)**: OpenAI의 **Whisper** API를 사용하여 사용자의 음성을 텍스트로 변환합니다.
      * **의미 기반 음악 검색**: **SentenceTransformer** 모델을 기반으로 가사 데이터를 벡터화하고, **FAISS**를 활용한 벡터 검색을 통해 사용자의 입력(텍스트)과 가장 유사한 곡을 찾아냅니다.
      * **플레이리스트 정보 생성**: OpenAI의 **GPT-3.5-turbo** 모델을 호출하여 추천된 곡의 특징을 분석하고, 플레이리스트 제목과 설명을 생성합니다.
      * **외부 서비스 연동**: **Spotify API & SDK**를 연동하여 플레이리스트 생성부터 웹 플레이어 재생까지의 전 과정을 자동화합니다.

-----

## 🤗 Huggingface Space Files

  * **Backend**: `uvicorn app:app --host 0.0.0.0 --port 7860`
  * **Dependencies**:
      * [requirements.txt](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/requirements.txt)
  * **Main Service**:
      * [app.py](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/app.py)
  * **Interface**:
      * [Index.html](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/static/index.html)
      * [tag_color.json](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/static/tag_colors.json)
  * **Data**:
      * [song_metadata.json](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/song_metadata.json)
      * [line_metadata.json](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/line_metadata.json)
      * [line_embeddings.npy](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/line_embeddings.npy)
      * [song_embeddings.npy](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/song_embeddings.npy)
      * [summary_embeddings.npy](https://huggingface.co/spaces/fairyofdata/JPOP_STT_Module/blob/main/summary_embeddings.npy)

-----

## 🖼️ 사용 방법

### 1\. 검색 시작하기

메인 화면에서 **음성으로 찾기** 또는 **텍스트로 찾기** 버튼을 클릭하여 검색을 시작합니다.
*초기 검색 화면: "음성으로 찾기"와 "텍스트로 찾기" 버튼이 보입니다.*

### 2\. 음성으로 검색하기 (STT)

마이크 버튼을 누르고 노래를 흥얼거리거나 가사를 말해보세요. 서비스가 음성을 텍스트로 변환하고, 그 텍스트를 기반으로 노래를 찾아줍니다.
*마이크 버튼을 눌러 음성 검색을 시작하고, 녹음이 진행 중임을 보여줍니다.*

### 3\. 텍스트로 검색하기

**텍스트로 찾기** 버튼을 누르면 검색창이 나타납니다. 가사나 곡의 분위기를 입력하고 검색 버튼을 누르면 됩니다.
*텍스트 입력 모달 창: "가사로 찾기" 제목과 텍스트 입력창이 보입니다.*

### 4\. 검색 결과 확인 및 재생

검색 결과 화면에서 찾은 곡과 추천 곡 목록을 확인할 수 있습니다. Spotify Web Player가 활성화되면 바로 재생할 수 있습니다.
*검색 결과 화면: 찾은 노래와 추천 노래 목록, 그리고 Spotify Web Player가 있는 화면입니다.*

### 5\. 플레이리스트 생성 (Spotify 연동)

**이 곡들로 플레이리스트 만들기** 버튼을 누르면, AI가 생성한 제목과 설명으로 Spotify에 새로운 플레이리스트가 생성됩니다.
*플레이리스트 생성 성공을 알리는 토스트 메시지 화면입니다.*


-----

## 🔰 Example of Prototype Execution

![Example of Prototype Execution](sample.png)

-----

## 💡 프로젝트의 가치

  * **AI 기술의 실용적 응용**: 사용자의 불편함을 해결하는 실용적인 서비스에 최신 AI 기술을 응용했습니다.
  * **도메인 문제 해결**: '부정확한 가사로 특정 노래 탐색'이라는 기존 시장의 한계를 극복하고 차별화된 경쟁력을 확보했습니다.
  * **확장 가능한 서비스 설계**: 마이크로서비스 아키텍처를 통해 향후 기능 확장이 용이하도록 설계했습니다.

## 📌 한계 및 해결 과제

  * **의존성 및 비용 문제**: Whisper, GPT 등 외부 유료 API에 대한 의존성과 그에 따른 비용 문제가 있습니다.
  * **데이터 저작권 이슈**: 가사 데이터의 저작권 문제 해결이 필요합니다.
  * **추천 정교화**: 유사한 곡을 분별하는 더 정교한 추천 방법이 필요합니다.

## 🛣️ 향후 계획

  * 음원 라이선스를 확보하여 서비스 확장
  * 청취 기록 기반의 개인화 추천 기능 도입
  * 모바일 앱 버전 출시를 통한 접근성 강화

-----

### 프로젝트 개요

* **프로젝트명**: URFIT (음성인식 기반 AI 플레이리스트 생성 커뮤니티)
* **개발 과정**: 한국무역협회 무역아카데미 Smart Cloud IT 과정 47기 프로젝트
* **개발 기간**: 2025년 7월 29일 ~ 2025년 9월 29일

### 팀 구성원

* **황문규** (Team Leader & Back-End Leader)
* **임수빈** (Technical PM & Front-End Leader)
* **백지헌** (LLM & RecSys & PPT)
* **유승철** (Back-End & Presenter)
* **이한석** (Front-End)
* **부경원** (Official PM)
  
### 저작권 고지

이 자료의 저작권은 한국무역협회 무역아카데미 Smart Cloud IT 과정 47기 팀 "노래불러조"에게 있으며, 허가 없이 복제, 배포, 전송, 전시 등의 행위를 금지합니다.

-----
