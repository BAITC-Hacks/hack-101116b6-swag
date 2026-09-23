import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from src.config import demo_mode, ask_llm

st.set_page_config(page_title="HackAlem AI", page_icon="🚀", layout="wide")
st.title("🚀 HackAlem AI")
st.caption("Режим: " + ("демо (без ключей)" if demo_mode() else "с API"))

q = st.text_input("Проверка LLM", "Ответь одним словом: работает?")
if st.button("Отправить"):
    st.write(ask_llm(q))
