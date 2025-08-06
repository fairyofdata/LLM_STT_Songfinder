import streamlit as st
import time

# --- 더미 데이터 (Gradio 목업과 동일) ---
YOASOBI_IMG_URL = "http://googleusercontent.com/file_content/1"
DUMMY_DB = {
    "s01": { "title": "ラブレター (Love Letter)", "artist": "YOASOBI", "album_art": YOASOBI_IMG_URL, "lyrics": [("もしもあなたに出会えてなかったらなんて", "만약에 당신을 만나지 못했다면 어떻게 됐을까"), ("思うだけで怖いほど大好きなんだ", "생각만 해도 무서울 정도로 정말 좋아해"), ("受け取ってどうか私の想いを", "받아주세요 부디 제 마음을")], "key_expression": "ほど" },
    "s02": { "title": "残響散歌 (Zankyosanka)", "artist": "Aimer", "album_art": "https://placehold.co/300x300/E84D5F/FFFFFF?text=Aimer", "lyrics": [("誰が袖に咲く幻花 ただそこに藍を落とした", "누군가의 소매에 피는 환상화 그저 그곳에 남색을 떨어뜨렸어"), ("涙が出るほど美しい夕焼けだった", "눈물이 나올 정도로 아름다운 노을이었어"), ("派手に咲き誇れ", "화려하게 만개해라")], "key_expression": "ほど" },
    "s03": { "title": "Pretender", "artist": "Official髭男dism", "album_art": "https://placehold.co/300x300/3498DB/FFFFFF?text=Higedan", "lyrics": [("君とのラブストーリー それは予想通り", "너와의 러브스토리 그건 예상대로"), ("叫びたいほど会いたい夜を越えて", "소리치고 싶을 만큼 보고 싶은 밤을 넘어서"), ("グッバイ", "굿바이")], "key_expression": "ほど" },
    "s04": { "title": "アイドル (Idol)", "artist": "YOASOBI", "album_art": "https://placehold.co/300x300/F1C40F/FFFFFF?text=YOASOBI", "lyrics": [("無敵の笑顔で荒らすメディア", "무적의 미소로 휩쓰는 미디어"), ("知りたくない秘密一つくらいは", "알고 싶지 않은 비밀 하나쯤은"), ("誰もが目を奪われていく 君は完璧で究極のアイドル", "누구나 시선을 빼앗겨버리는 너는 완벽하고 궁극의 아이돌")], "key_expression": None }
}

# st.session_state에 더미 DB 저장 (페이지 간 공유)
if 'db' not in st.session_state:
    st.session_state.db = DUMMY_DB

# --- UI 구성 ---
st.set_page_config(page_title="Melody-Verse", page_icon="🎵")

st.title("🎵 Melody-Verse")
st.markdown("<h2 style='text-align: center;'>어떤 노래인지 궁금하세요?</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>기억나지 않는 노래, 이제 흥얼거리기만 하세요!</p>", unsafe_allow_html=True)

# 음성 녹음 컴포넌트
audio_bytes = st.audio_recorder(text="여기에 흥얼거려주세요", icon_size="3x")

if audio_bytes:
    # 음성 데이터가 녹음되면 검색 버튼 표시
    if st.button("🔍 이 노래 찾기"):
        with st.spinner("AI가 노래를 분석 중입니다..."):
            # 실제 구현 시: Whisper API로 음성 인식 → Elasticsearch로 가사 검색
            time.sleep(2) # 더미 로딩 시간
            
            # 검색 결과를 session_state에 저장
            st.session_state.search_results = list(st.session_state.db.keys())
            
            # 검색 결과 페이지로 이동
            st.switch_page("pages/1_Search_Result.py")

st.markdown("---")
st.info("이 페이지는 서비스의 메인 화면입니다. 마이크 버튼을 눌러 음성을 녹음한 후, '이 노래 찾기' 버튼을 눌러보세요.")

