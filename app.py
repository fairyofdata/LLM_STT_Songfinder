import streamlit as st

# -----------------------------------------------------------------------------
# 1. HTML/CSS 디자인을 Python 코드로 가져오기
# -----------------------------------------------------------------------------

# HTML 파일의 <style> 태그 내용을 그대로 가져와 CSS를 적용합니다.
def local_css():
    st.markdown("""
    <style>
        /* --- 기본 스타일 리셋 --- */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Noto Sans KR', sans-serif; }
        a { text-decoration: none; color: inherit; }
        ul { list-style: none; }

        /* --- 헤더 --- */
        /* Streamlit에서는 헤더를 직접 제어하기 어려우므로 일부 스타일은 적용되지 않을 수 있습니다. */
        .header { background-color: #ffffff; padding: 1rem 5%; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e9ecef; }
        .logo a { font-size: 1.5rem; font-weight: 700; color: #7048e8; }
        .nav-menu ul { display: flex; gap: 40px; font-weight: 500; }
        .nav-menu a:hover { color: #7048e8; }
        .user-actions button { background-color: transparent; border: 1px solid #ced4da; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
        .user-actions button:hover { background-color: #f1f3f5; }
        .user-actions .btn-primary { background-color: #7048e8; color: #ffffff; border: none; }
        .user-actions .btn-primary:hover { background-color: #5f3dc4; }

        /* --- 메인 컨텐츠 --- */
        .main-container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }

        /* --- 핵심 기능: 허밍 검색 --- */
        .hero-section { text-align: center; padding: 80px 0; background: linear-gradient(135deg, #f3f0ff, #e6fcf5); border-radius: 20px; }
        .hero-section h1 { font-size: 2.5rem; margin-bottom: 15px; }
        .hero-section p { font-size: 1.1rem; color: #495057; margin-bottom: 40px; }
        .mic-button { display: inline-block; background-color: #7048e8; width: 120px; height: 120px; border-radius: 50%; border: none; cursor: pointer; box-shadow: 0 8px 20px rgba(112, 72, 232, 0.3); transition: all 0.3s; }
        .mic-button:hover { transform: scale(1.1); box-shadow: 0 12px 25px rgba(112, 72, 232, 0.4); }
        .mic-button svg { width: 50px; height: 50px; color: white; margin-top: 35px; }

        /* --- 섹션 공통 스타일 --- */
        .section { margin-top: 80px; }
        .section-title { font-size: 2rem; text-align: center; margin-bottom: 40px; }

        /* --- 랭킹 & 게시판 그리드 --- */
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
        .list-card { background-color: #ffffff; border-radius: 16px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .list-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .list-card-header h3 { font-size: 1.5rem; }
        .list-card-header a { font-size: 0.9rem; color: #868e96; }
        .list-item { display: flex; align-items: center; padding: 15px 0; border-bottom: 1px solid #f1f3f5; }
        .list-item:last-child { border-bottom: none; }
        .item-info { flex-grow: 1; }
        .item-info .title { font-weight: 500; }
        .item-info .artist { font-size: 0.9rem; color: #868e96; }
        .item-thumbnail { width: 50px; height: 50px; border-radius: 8px; background-color: #e9ecef; margin-right: 15px; object-fit: cover; }

        /* --- 부가 기능 카드 --- */
        .features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 30px; }
        .feature-card { background-color: #ffffff; border-radius: 16px; padding: 30px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: all 0.3s; }
        .feature-card:hover { transform: translateY(-10px); box-shadow: 0 8px 20px rgba(0,0,0,0.08); }
        .feature-icon { font-size: 3rem; margin-bottom: 20px; color: #7048e8; }
        .feature-card h3 { font-size: 1.3rem; margin-bottom: 10px; }
        .feature-card p { color: #495057; font-size: 0.95rem; }

        /* --- 푸터 --- */
        .footer { margin-top: 100px; background-color: #e9ecef; color: #868e96; text-align: center; padding: 40px 20px; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# 각 섹션을 HTML 문자열로 반환하는 함수들을 만듭니다.
def get_header_html():
    return """
    <header class="header">
        <div class="logo"><a href="#">Melody-Verse</a></div>
        <nav class="nav-menu">
            <ul>
                <li><a href="#">랭킹</a></li>
                <li><a href="#">플레이리스트</a></li>
                <li><a href="#">커뮤니티</a></li>
            </ul>
        </nav>
        <div class="user-actions">
            <button>로그인</button>
            <button class="btn-primary">회원가입</button>
        </div>
    </header>
    """

def get_hero_section_html():
    # 참고: Streamlit에서는 a 태그로 다른 페이지로 이동하는 것이 기본 방식이 아닙니다.
    # 여기서는 시각적인 목적으로만 사용합니다.
    return """
    <section class="hero-section">
        <h1>어떤 노래인지 궁금하세요?</h1>
        <p>기억나지 않는 노래, 이제 흥얼거리기만 하세요!</p>
        <a href="#" class="mic-button" aria-label="음성 검색 시작">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14a2 2 0 0 0 2-2V6a2 2 0 0 0-4 0v6a2 2 0 0 0 2 2z"/><path d="M12 17a5 5 0 0 1-5-5V6a5 5 0 0 1 10 0v6a5 5 0 0 1-5 5z"/><path d="M19 11h-1.1a6.9 6.9 0 0 0-1.8-4.2l.8-.8a1 1 0 0 0-1.4-1.4l-.8.8A7 7 0 0 0 5 11H4a1 1 0 0 0 0 2h1a7 7 0 0 0 6 6v2a1 1 0 0 0 2 0v-2a7 7 0 0 0 6-6h1a1 1 0 0 0 0-2z"/></svg>
        </a>
    </section>
    """

def get_grid_section_html():
    return """
    <section class="section">
        <div class="grid-container">
            <div class="list-card">
                <div class="list-card-header"><h3>실시간 랭킹</h3><a href="#">더보기 &gt;</a></div>
                <ul>
                    <li class="list-item"><img src="https://placehold.co/100x100/7048e8/ffffff?text=1" alt="앨범 아트" class="item-thumbnail"><div class="item-info"><div class="title">밤양갱</div><div class="artist">비비 (BIBI)</div></div></li>
                    <li class="list-item"><img src="https://placehold.co/100x100/7048e8/ffffff?text=2" alt="앨범 아트" class="item-thumbnail"><div class="item-info"><div class="title">첫 만남은 계획대로 되지 않아</div><div class="artist">TWS (투어스)</div></div></li>
                    <li class="list-item"><img src="https://placehold.co/100x100/7048e8/ffffff?text=3" alt="앨범 아트" class="item-thumbnail"><div class="item-info"><div class="title">Love wins all</div><div class="artist">아이유 (IU)</div></div></li>
                </ul>
            </div>
            <div class="list-card">
                <div class="list-card-header"><h3>커뮤니티 최신글</h3><a href="#">더보기 &gt;</a></div>
                 <ul>
                    <li class="list-item"><div class="item-info"><div class="title">이 노래 아시는 분?? 라라라~ 하는 건데</div><div class="artist">user123 · 5분 전</div></div></li>
                    <li class="list-item"><div class="item-info"><div class="title">AI가 만들어준 J-POP 플레이리스트</div><div class="artist">musiclover · 12분 전</div></div></li>
                    <li class="list-item"><div class="item-info"><div class="title">밤양갱이랑 비슷한 노래 추천해주세요!</div><div class="artist">달디달고달디단 · 28분 전</div></div></li>
                </ul>
            </div>
        </div>
    </section>
    """
    
def get_features_section_html():
    return """
    <section class="section">
        <h2 class="section-title">Melody-Verse의 특별한 기능들</h2>
        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">🎼</div><h3>AI 플레이리스트</h3><p>찾은 노래를 기반으로 취향에 꼭 맞는 플레이리스트를 AI가 자동으로 생성해줘요.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📈</div><h3>비슷한 곡 찾기</h3><p>노래의 분위기와 리듬을 분석해 지금 듣는 곡과 비슷한 다른 명곡들을 찾아보세요.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🇯🇵</div><h3>일본어 단어 학습</h3><p>J-POP 가사에 나온 핵심 단어와 표현을 학습하며 즐겁게 일본어를 공부할 수 있어요.</p>
            </div>
        </div>
    </section>
    """

def get_footer_html():
    return """
    <footer class="footer">
        <p>&copy; 2025 Melody-Verse. All Rights Reserved.</p>
        <p>Team Project for Bootcamp</p>
    </footer>
    """

# -----------------------------------------------------------------------------
# 2. Streamlit 앱 구성
# -----------------------------------------------------------------------------

# Streamlit 페이지 기본 설정
st.set_page_config(layout="wide") # 전체 너비 사용

# CSS 적용
local_css()

# HTML 컴포넌트 렌더링
# 참고: 헤더는 Streamlit의 기본 레이아웃과 충돌할 수 있어 제외하거나 다른 방식으로 구현해야 합니다.
# st.markdown(get_header_html(), unsafe_allow_html=True)

# 메인 컨테이너 안에 각 섹션을 렌더링합니다.
st.markdown('<main class="main-container">', unsafe_allow_html=True)

# Hero Section (음성 검색)
# 이 부분은 실제 기능과 연동하기 위해 Streamlit의 네이티브 컴포넌트를 함께 사용합니다.
st.markdown(get_hero_section_html(), unsafe_allow_html=True)
st.info("위 마이크 버튼은 HTML/CSS로 구현된 디자인 목업입니다. 실제 기능은 아래 Streamlit 컴포넌트를 사용합니다.")
audio_bytes = st.audio_recorder(text="여기에 흥얼거려보세요 (Streamlit 기능)", icon_size="2x")
if audio_bytes:
    st.success("음성 녹음 완료! (실제로는 이 데이터를 AI 서버로 보냅니다)")

# 나머지 섹션들
st.markdown(get_grid_section_html(), unsafe_allow_html=True)
st.markdown(get_features_section_html(), unsafe_allow_html=True)

st.markdown('</main>', unsafe_allow_html=True)

# 푸터
st.markdown(get_footer_html(), unsafe_allow_html=True)

