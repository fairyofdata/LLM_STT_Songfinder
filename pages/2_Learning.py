import streamlit as st

st.set_page_config(page_title="노래 학습", page_icon="📖")

def find_similar_examples(db, song_id):
    # Gradio 목업의 함수와 동일한 로직
    key_expression = db[song_id].get("key_expression")
    if not key_expression:
        return "<p style='text-align:center; color:#adb5bd;'>이 노래에서는 주요 학습 표현을 찾지 못했습니다.</p>"

    html = f"<h4>'{key_expression}'가 사용된 다른 노래 예시</h4>"
    for s_id, info in db.items():
        if info.get("key_expression") == key_expression:
            for lyric_jp, lyric_kr in info["lyrics"]:
                if key_expression in lyric_jp:
                    highlighted_jp = lyric_jp.replace(key_expression, f"<strong style='color:#7048e8;'>{key_expression}</strong>")
                    highlighted_kr = lyric_kr.replace("정도", f"<strong style='color:#7048e8;'>정도</strong>").replace("만큼", f"<strong style='color:#7048e8;'>만큼</strong>")
                    html += f"""
                    <div style="margin-bottom: 15px; padding: 15px; border: 1px solid #e9ecef; border-radius: 8px;">
                        <p style="font-size: 1.1em; font-weight: 500;">{highlighted_jp}</p>
                        <p style="font-size: 0.9em; color: #495057;">{highlighted_kr}</p>
                        <p style="font-size: 0.8em; color: #868e96; text-align: right;">- {info['artist']} / {info['title']}</p>
                    </div>
                    """
                    break
    return html

# 검색 결과 페이지에서 전달된 노래 ID가 있는지 확인
if 'selected_song_id' not in st.session_state:
    st.error("먼저 검색 결과 페이지에서 노래를 선택해주세요.")
    if st.button("검색 결과로 돌아가기"):
        st.switch_page("pages/1_Search_Result.py")
else:
    db = st.session_state.db
    song_id = st.session_state.selected_song_id
    song = db[song_id]

    # 노래 정보 표시
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(song["album_art"])
    with col2:
        st.title(song["title"])
        st.subheader(song["artist"])

    # 가라오케 뷰
    st.markdown("### 가사 (가라오케 뷰)")
    for i, (jp, kr) in enumerate(song["lyrics"]):
        if song.get("key_expression") and song.get("key_expression") in jp:
            st.markdown(f"""
            <div style="text-align:center; margin: 20px 0;">
                <p style="font-size: 1.3em; font-weight: 500;">{jp.replace(song['key_expression'], f"<strong style='color:#7048e8;'>{song['key_expression']}</strong>")}</p>
                <p style="font-size: 1em; color: #495057;">{kr.replace("정도", f"<strong style='color:#7048e8;'>정도</strong>").replace("만큼", f"<strong style='color:#7048e8;'>만큼</strong>")}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"<p style='text-align:center; color: #adb5bd;'>{jp}</p>", unsafe_allow_html=True)

    # 유사 표현 학습
    st.markdown("---")
    st.markdown("### 📖 가사 속 일본어 학습")
    st.markdown("*(실제 구현 시: LLM 또는 RAG 모델을 활용해 유사 표현 검색)*", unsafe_allow_html=True)
    
    similar_html = find_similar_examples(db, song_id)
    st.markdown(similar_html, unsafe_allow_html=True)

    if st.button("다른 노래 보러가기"):
        st.switch_page("pages/1_Search_Result.py")
