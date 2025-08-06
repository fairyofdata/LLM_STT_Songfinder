import streamlit as st

st.set_page_config(page_title="검색 결과", page_icon="🎤")

st.markdown("# 🎤 AI가 찾은 노래 목록입니다.")
st.write("결과를 클릭하면 상세 학습 페이지로 이동합니다.")
st.markdown("*(실제 구현 시: AI가 찾은 노래 목록을 정확도 순으로 표시)*")

# 메인 페이지에서 전달된 검색 결과가 있는지 확인
if 'search_results' not in st.session_state or not st.session_state.search_results:
    st.warning("먼저 메인 페이지에서 노래를 검색해주세요.")
    if st.button("메인으로 돌아가기"):
        st.switch_page("app.py")
else:
    db = st.session_state.db
    results = st.session_state.search_results
    
    # 검색 결과를 2열로 표시
    cols = st.columns(2)
    for i, song_id in enumerate(results):
        song = db[song_id]
        with cols[i % 2]:
            with st.container(border=True):
                st.image(song["album_art"])
                st.subheader(song["title"])
                st.write(song["artist"])
                if st.button("학습 페이지로 이동", key=song_id):
                    # 선택된 노래 ID를 session_state에 저장
                    st.session_state.selected_song_id = song_id
                    # 학습 페이지로 이동
                    st.switch_page("pages/2_Learning.py")

