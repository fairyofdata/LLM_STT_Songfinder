import streamlit as st

st.set_page_config(page_title="로그인", page_icon="👤")

st.title("👤 로그인")
st.text_input("아이디")
st.text_input("비밀번호", type="password")
st.button("로그인")
st.markdown("*(실제 구현 시: Spring Security, JPA, AWS RDS(MySQL)로 구현)*")
