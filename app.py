import streamlit as st
import requests

st.title("🧪 Test Vinted Deal Hunter")

try:
    api_key = st.secrets["PILOTERR_API_KEY"]
except Exception:
    st.error("❌ PILOTERR_API_KEY introuvable dans les Secrets.")
    st.stop()

query = st.text_input("Recherche", "Nike Tech Fleece")

if st.button("🔎 TESTER VINTED"):

    response = requests.get(
        "https://api.piloterr.com/v2/vinted/search",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
        },
        params={
            "query": query,
            "page": 1,
            "per_page": 24,
            "order": "relevance",
            "region": "fr",
        },
        timeout=30,
    )

    st.write("Code HTTP :", response.status_code)

    try:
        data = response.json()
        st.json(data)
    except Exception:
        st.text(response.text)