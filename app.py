import streamlit as st
import pandas as pd

st.set_page_config(page_title="Vinted Deal Hunter", page_icon="🔎")

st.title("🔎 Vinted Deal Hunter")
st.write("Analyse tes annonces Vinted et repère les meilleures affaires.")

st.sidebar.header("🎯 Tes critères")

niche = st.sidebar.text_input("Niche", "Nike Tech Fleece")
budget = st.sidebar.number_input("Prix maximum (€)", 0.0, 1000.0, 40.0)
benefice_min = st.sidebar.number_input("Bénéfice minimum (€)", 0.0, 1000.0, 15.0)
revente = st.sidebar.number_input("Prix de revente estimé (€)", 0.0, 2000.0, 60.0)
frais = st.sidebar.number_input("Frais / sécurité (€)", 0.0, 100.0, 3.0)

st.info("Une annonce par ligne : Nom | Prix | État | Taille | Lien")

annonces = st.text_area(
    "Colle tes annonces ici",
    placeholder="Nike Tech Fleece noir | 32 | très bon état | M | https://..."
)

if annonces.strip():

    resultats = []

    for ligne in annonces.splitlines():

        morceaux = [x.strip() for x in ligne.split("|")]

        if len(morceaux) < 2:
            continue

        nom = morceaux[0]

        try:
            prix = float(morceaux[1].replace("€", "").replace(",", "."))
        except:
            continue

        etat = morceaux[2] if len(morceaux) > 2 else "Non précisé"
        taille = morceaux[3] if len(morceaux) > 3 else "Non précisée"
        lien = morceaux[4] if len(morceaux) > 4 else ""

        marge = revente - prix - frais

        score = 0

        if prix <= budget:
            score += 40

        if marge >= benefice_min:
            score += 40

        if "très bon" in etat.lower() or "neuf" in etat.lower():
            score += 15
        elif "bon" in etat.lower():
            score += 8

        if taille.upper() in ["M", "L", "S"]:
            score += 5

        score = min(100, score)

        if score >= 80:
            verdict = "🔥 ACHAT À VÉRIFIER"
        elif score >= 60:
            verdict = "🟢 INTÉRESSANT"
        else:
            verdict = "🔴 PASSER"

        resultats.append({
            "Article": nom,
            "Prix": prix,
            "Revente": revente,
            "Marge": marge,
            "Score": score,
            "Verdict": verdict,
            "État": etat,
            "Taille": taille,
            "Lien": lien
        })

    df = pd.DataFrame(resultats)

    if len(df) > 0:

        df = df.sort_values(
            ["Score", "Marge"],
            ascending=False
        )

        st.header("🏆 Meilleures opportunités")

        for _, article in df.iterrows():

            st.subheader(
                f"{article['Verdict']} — {article['Article']}"
            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Prix",
                f"{article['Prix']:.0f} €"
            )

            col2.metric(
                "Revente estimée",
                f"{article['Revente']:.0f} €"
            )

            col3.metric(
                "Marge potentielle",
                f"{article['Marge']:.0f} €"
            )

            st.write(
                f"**Score : {article['Score']}/100**  \n"
                f"État : {article['État']}  \n"
                f"Taille : {article['Taille']}"
            )

            if article["Prix"] <= budget:
                st.write("✅ Prix d'achat dans ton budget")
            else:
                st.write("❌ Prix supérieur à ton budget")

            if article["Marge"] >= benefice_min:
                st.write("✅ Marge suffisante")
            else:
                st.write("❌ Marge insuffisante")

            if article["Lien"].startswith("http"):
                st.link_button("🔗 Ouvrir l'annonce", article["Lien"])

            st.warning(
                "⚠️ Vérifie toi-même l'authenticité, les défauts, "
                "les photos et le vendeur avant d'acheter."
            )

            st.divider()

    else:
        st.error("Je n'ai pas réussi à lire tes annonces.")

else:

    st.header("Comment ça marche ?")

    st.write(
        "1️⃣ Choisis ta niche et tes critères à gauche.\n\n"
        "2️⃣ Colle les annonces à analyser.\n\n"
        "3️⃣ Le système calcule la marge et un score.\n\n"
        "4️⃣ Tu vérifies l'annonce toi-même et tu décides si tu achètes."
      )
