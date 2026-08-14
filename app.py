import streamlit as st
import requests
import pandas as pd
import statistics
import re
from urllib.parse import quote


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Vinted Deal Hunter",
    page_icon="🔎",
    layout="wide"
)


API_URL = "https://api.piloterr.com/v2/vinted/search"


# ============================================================
# OUTILS
# ============================================================

def get_api_key():
    """Récupère la clé Piloterr depuis les Secrets Streamlit."""
    try:
        return st.secrets["PILOTERR_API_KEY"]
    except Exception:
        return None


def money_to_float(value):
    """Convertit différents formats de prix en nombre."""
    if value is None:
        return None

    if isinstance(value, dict):
        value = value.get("amount")

    if value is None:
        return None

    try:
        text = str(value)
        text = text.replace("€", "")
        text = text.replace(",", ".")
        text = re.sub(r"[^0-9.\-]", "", text)

        if not text:
            return None

        return float(text)
    except Exception:
        return None


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


# ============================================================
# RECHERCHE VINTED
# ============================================================

def search_vinted(query, pages=2, per_page=24):
    """
    Recherche de vraies annonces Vinted via Piloterr.

    Aucun résultat fictif n'est créé.
    """

    api_key = get_api_key()

    if not api_key:
        return {
            "success": False,
            "error": "PILOTERR_API_KEY manquante.",
            "listings": []
        }

    all_results = []

    for page in range(1, pages + 1):

        params = {
            "query": query,
            "page": page,
            "per_page": per_page,
            "order": "relevance",
            "region": "fr"
        }

        try:
            response = requests.get(
                API_URL,
                headers={
                    "x-api-key": api_key,
                    "Accept": "application/json"
                },
                params=params,
                timeout=30
            )

        except requests.RequestException as error:
            return {
                "success": False,
                "error": f"Erreur réseau : {error}",
                "listings": []
            }

        if response.status_code != 200:

            try:
                error_data = response.json()
            except Exception:
                error_data = response.text

            return {
                "success": False,
                "error": (
                    f"Piloterr HTTP {response.status_code} : "
                    f"{error_data}"
                ),
                "listings": []
            }

        try:
            data = response.json()
        except Exception:
            return {
                "success": False,
                "error": "La réponse de Piloterr n'est pas du JSON valide.",
                "listings": []
            }

        results = data.get("results", [])

        if not isinstance(results, list):
            return {
                "success": False,
                "error": "Format inattendu : 'results' n'est pas une liste.",
                "listings": []
            }

        all_results.extend(results)

        pagination = data.get("pagination", {})

        total_pages = pagination.get("total_pages")

        if total_pages and page >= total_pages:
            break

    return {
        "success": True,
        "error": None,
        "listings": all_results
    }


# ============================================================
# NORMALISATION
# ============================================================

def normalize_listing(item):
    """Transforme une annonce Piloterr en structure propre."""

    price = money_to_float(
        item.get("price")
    )

    total_price = money_to_float(
        item.get("total_item_price")
    )

    photo = item.get("photo") or {}

    photo_url = photo.get("url")

    if not photo_url:

        photos = item.get("photos") or []

        if photos:
            photo_url = photos[0].get("url")

    return {
        "id": item.get("id"),
        "title": clean_text(item.get("title")),
        "url": clean_text(item.get("url")),
        "price": price,
        "total_price": total_price,
        "currency": (
            (item.get("price") or {}).get(
                "currency_code",
                "EUR"
            )
        ),
        "status": clean_text(item.get("status")),
        "size": clean_text(item.get("size_title")),
        "brand": clean_text(item.get("brand_title")),
        "favourites": int(
            item.get("favourite_count") or 0
        ),
        "photo": photo_url,
        "promoted": bool(
            item.get("promoted", False)
        ),
        "visible": bool(
            item.get("is_visible", True)
        ),
        "seller": clean_text(
            (item.get("user") or {}).get("login")
        )
    }


# ============================================================
# FILTRAGE
# ============================================================

def filter_by_budget(listings, budget):
    """Garde uniquement les annonces dans le budget."""

    return [
        item
        for item in listings
        if item["price"] is not None
        and item["price"] <= budget
    ]


# ============================================================
# ANALYSE DU MARCHÉ DISPONIBLE
# ============================================================

def calculate_active_market(listings):
    """
    Analyse les prix actuellement demandés.

    IMPORTANT :
    Ce ne sont PAS des ventes réalisées.
    """

    prices = [
        item["price"]
        for item in listings
        if item["price"] is not None
        and item["price"] > 0
    ]

    if not prices:
        return {
            "count": 0,
            "median": None,
            "q1": None,
            "q3": None,
            "minimum": None,
            "maximum": None
        }

    prices_sorted = sorted(prices)

    return {
        "count": len(prices_sorted),
        "median": statistics.median(prices_sorted),
        "q1": (
            statistics.quantiles(
                prices_sorted,
                n=4
            )[0]
            if len(prices_sorted) >= 4
            else min(prices_sorted)
        ),
        "q3": (
            statistics.quantiles(
                prices_sorted,
                n=4
            )[2]
            if len(prices_sorted) >= 4
            else max(prices_sorted)
        ),
        "minimum": min(prices_sorted),
        "maximum": max(prices_sorted)
    }


# ============================================================
# PRIX DE REVENTE PRUDENT
# ============================================================

def calculate_resale_price(market):
    """
    Estimation prudente basée sur les annonces actives.

    Elle est volontairement présentée comme une estimation
    des prix demandés, pas comme un prix de vente réalisé.
    """

    if market["count"] == 0:
        return None

    median = market["median"]
    q1 = market["q1"]
    q3 = market["q3"]

    if median is None:
        return None

    # Estimation prudente :
    # on ne prend pas automatiquement le prix maximum.
    if q1 is not None and q3 is not None:
        recommended = (
            median * 0.55
            + q3 * 0.30
            + q1 * 0.15
        )
    else:
        recommended = median

    return round(recommended, 2)


# ============================================================
# MARGE
# ============================================================

def calculate_margin(
    purchase_price,
    resale_price,
    fees
):
    if (
        purchase_price is None
        or resale_price is None
    ):
        return None

    return round(
        resale_price
        - purchase_price
        - fees,
        2
    )


# ============================================================
# ROI
# ============================================================

def calculate_roi(
    purchase_price,
    margin
):
    if (
        purchase_price is None
        or purchase_price <= 0
        or margin is None
    ):
        return None

    return round(
        (margin / purchase_price) * 100,
        1
    )


# ============================================================
# ANALYSE DE LIQUIDITÉ
# ============================================================

def calculate_liquidity(listing, market_count):
    """
    Sans historique de dates de vente, nous ne prétendons
    pas connaître le délai de vente.

    Les favoris sont seulement utilisés comme signal secondaire.
    """

    favourites = listing.get("favourites", 0)

    if favourites >= 20:
        return "🟢 Signal de demande élevé"

    if favourites >= 8:
        return "🟡 Signal de demande moyen"

    return "⚪ Demande inconnue"


# ============================================================
# SCORE
# ============================================================

def calculate_opportunity_score(
    listing,
    resale_price,
    budget,
    minimum_profit,
    fees,
    market_count
):

    purchase = listing.get("price")

    if purchase is None:
        return 0

    margin = calculate_margin(
        purchase,
        resale_price,
        fees
    )

    roi = calculate_roi(
        purchase,
        margin
    )

    score = 0

    # --------------------------------------------------------
    # PRIX D'ACHAT
    # --------------------------------------------------------

    if purchase <= budget:
        score += 20

    # --------------------------------------------------------
    # MARGE
    # --------------------------------------------------------

    if margin is not None:

        if margin >= minimum_profit:
            score += 30

        elif margin >= minimum_profit * 0.75:
            score += 20

        elif margin > 0:
            score += 10

    # --------------------------------------------------------
    # ROI
    # --------------------------------------------------------

    if roi is not None:

        if roi >= 70:
            score += 20

        elif roi >= 50:
            score += 15

        elif roi >= 30:
            score += 10

        elif roi > 0:
            score += 5

    # --------------------------------------------------------
    # DONNÉES DE MARCHÉ
    # --------------------------------------------------------

    if market_count >= 50:
        score += 15

    elif market_count >= 25:
        score += 12

    elif market_count >= 10:
        score += 8

    elif market_count >= 5:
        score += 4

    # --------------------------------------------------------
    # ÉTAT
    # --------------------------------------------------------

    status = listing.get(
        "status",
        ""
    ).lower()

    if "new" in status or "neuf" in status:
        score += 10

    elif "very good" in status or "très bon" in status:
        score += 8

    elif "good" in status or "bon" in status:
        score += 5

    # --------------------------------------------------------
    # FAVORIS
    # --------------------------------------------------------

    favourites = listing.get(
        "favourites",
        0
    )

    if favourites >= 20:
        score += 5

    elif favourites >= 8:
        score += 3

    # --------------------------------------------------------
    # MAXIMUM
    # --------------------------------------------------------

    return min(
        100,
        max(0, int(score))
    )


# ============================================================
# EXPLICATION
# ============================================================

def generate_explanation(
    listing,
    resale_price,
    margin,
    roi,
    market_count,
    minimum_profit
):

    positives = []
    risks = []

    price = listing.get("price")
    favourites = listing.get("favourites", 0)
    status = listing.get("status", "")
    size = listing.get("size", "")

    if price is not None:
        positives.append(
            f"Prix d'achat : {price:.0f} €"
        )

    if resale_price is not None:
        positives.append(
            f"Prix demandé de revente estimé : "
            f"{resale_price:.0f} €"
        )

    if margin is not None:

        if margin >= minimum_profit:
            positives.append(
                f"Marge théorique : {margin:.0f} €"
            )
        elif margin > 0:
            risks.append(
                "La marge reste inférieure à ton objectif."
            )
        else:
            risks.append(
                "Marge théorique insuffisante."
            )

    if roi is not None and roi > 0:
        positives.append(
            f"ROI théorique : {roi:.0f} %"
        )

    if market_count >= 25:
        positives.append(
            f"{market_count} annonces comparables analysées"
        )

    elif market_count > 0:
        risks.append(
            "Échantillon de marché limité."
        )

    else:
        risks.append(
            "Aucune donnée de marché disponible."
        )

    if status:
        positives.append(
            f"État indiqué : {status}"
        )

    if size:
        positives.append(
            f"Taille : {size}"
        )

    if favourites >= 20:
        positives.append(
            f"{favourites} favoris : signal secondaire de demande"
        )

    elif favourites >= 8:
        positives.append(
            f"{favourites} favoris : petit signal de demande"
        )

    risks.append(
        "Les favoris ne sont pas des ventes."
    )

    risks.append(
        "L'historique des ventes réellement conclues "
        "n'est pas fourni par cette source."
    )

    risks.append(
        "Le prix de revente est donc une estimation "
        "prudente basée sur les prix demandés."
    )

    return positives, risks


# ============================================================
# INTERFACE
# ============================================================

st.title("🔎 Vinted Deal Hunter")

st.caption(
    "Recherche réelle d'annonces Vinted et analyse prudente "
    "des opportunités de revente."
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("🎯 TA RECHERCHE")

    niche = st.text_input(
        "Niche",
        value="Nike Tech Fleece"
    )

    budget = st.number_input(
        "Budget maximum (€)",
        min_value=0.0,
        max_value=5000.0,
        value=35.0,
        step=1.0
    )

    minimum_profit = st.number_input(
        "Bénéfice minimum (€)",
        min_value=0.0,
        max_value=5000.0,
        value=20.0,
        step=1.0
    )

    fees = st.number_input(
        "Frais / sécurité (€)",
        min_value=0.0,
        max_value=100.0,
        value=3.0,
        step=0.5
    )

    pages = st.slider(
        "Nombre de pages Vinted",
        min_value=1,
        max_value=5,
        value=2
    )

    search_button = st.button(
        "🔥 CHERCHER LES MEILLEURES OFFRES",
        use_container_width=True
    )


# ============================================================
# VALIDATION
# ============================================================

if search_button:

    if not niche.strip():

        st.error(
            "❌ Veuillez entrer une niche."
        )
        st.stop()

    api_key = get_api_key()

    if not api_key:

        st.error(
            "⚠️ RECHERCHE AUTOMATIQUE NON CONFIGURÉE"
        )

        st.info(
            "Ajoute PILOTERR_API_KEY dans "
            "les Secrets Streamlit."
        )

        st.stop()

    # --------------------------------------------------------
    # RECHERCHE
    # --------------------------------------------------------

    with st.spinner(
        "🔎 Recherche réelle des annonces Vinted..."
    ):

        search = search_vinted(
            niche.strip(),
            pages=pages,
            per_page=24
        )

    if not search["success"]:

        st.error(
            "❌ La recherche Vinted a échoué."
        )

        st.code(
            search["error"]
        )

        st.stop()

    raw_listings = search["listings"]

    if not raw_listings:

        st.warning(
            "Aucune annonce Vinted retournée "
            "pour cette recherche."
        )

        st.stop()

    # --------------------------------------------------------
    # NORMALISATION
    # --------------------------------------------------------

    listings = [
        normalize_listing(item)
        for item in raw_listings
    ]

    listings = [
        item
        for item in listings
        if item["price"] is not None
    ]

    # --------------------------------------------------------
    # MARCHÉ ACTIF
    # --------------------------------------------------------

    market = calculate_active_market(
        listings
    )

    resale_price = calculate_resale_price(
        market
    )

    # --------------------------------------------------------
    # FILTRE BUDGET
    # --------------------------------------------------------

    opportunities = filter_by_budget(
        listings,
        budget
    )

    # --------------------------------------------------------
    # CALCULS
    # --------------------------------------------------------

    for listing in opportunities:

        margin = calculate_margin(
            listing["price"],
            resale_price,
            fees
        )

        roi = calculate_roi(
            listing["price"],
            margin
        )

        score = calculate_opportunity_score(
            listing,
            resale_price,
            budget,
            minimum_profit,
            fees,
            market["count"]
        )

        listing["margin"] = margin
        listing["roi"] = roi
        listing["score"] = score

    # --------------------------------------------------------
    # TRI
    # --------------------------------------------------------

    opportunities.sort(
        key=lambda x: (
            x["score"],
            x["margin"] or -999
        ),
        reverse=True
    )

    # ========================================================
    # ANALYSE DU MARCHÉ
    # ========================================================

    st.header("📈 ANALYSE DU MARCHÉ")

    st.warning(
        "⚠️ Important : les données ci-dessous correspondent "
        "aux prix actuellement demandés sur Vinted. "
        "Elles ne constituent PAS un historique de ventes "
        "réellement conclues."
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Prix demandé médian",
        (
            f"{market['median']:.0f} €"
            if market["median"] is not None
            else "N/A"
        )
    )

    c2.metric(
        "Fourchette demandée",
        (
            f"{market['q1']:.0f}–{market['q3']:.0f} €"
            if market["q1"] is not None
            and market["q3"] is not None
            else "N/A"
        )
    )

    c3.metric(
        "Annonces analysées",
        market["count"]
    )

    c4.metric(
        "Confiance",
        (
            "Faible"
            if market["count"] < 10
            else "Moyenne"
            if market["count"] < 30
            else "Bonne"
        )
    )

    if resale_price is not None:

        st.subheader(
            f"💰 Prix de revente estimé : "
            f"{resale_price:.0f} €"
        )

        st.caption(
            "⚠️ Estimation basée sur les prix demandés "
            "actuellement visibles, pas sur des ventes "
            "réellement conclues."
        )

    # ========================================================
    # RÉSULTATS
    # ========================================================

    st.header("🏆 MEILLEURES OPPORTUNITÉS")

    if not opportunities:

        st.warning(
            f"Aucune annonce trouvée sous "
            f"{budget:.0f} €."
        )

        st.info(
            "Essaie d'augmenter temporairement le budget "
            "pour vérifier les annonces retournées par Vinted."
        )

        st.stop()

    # --------------------------------------------------------
    # AFFICHAGE
    # --------------------------------------------------------

    for index, listing in enumerate(
        opportunities[:30],
        start=1
    ):

        score = listing["score"]
        price = listing["price"]
        margin = listing["margin"]
        roi = listing["roi"]

        if score >= 80:
            verdict = "🔥 EXCELLENTE OPPORTUNITÉ"

        elif score >= 65:
            verdict = "🟢 INTÉRESSANT"

        elif score >= 50:
            verdict = "🟡 À ÉTUDIER"

        else:
            verdict = "🔴 FAIBLE"

        st.divider()

        st.subheader(
            f"#{index} — {verdict}"
        )

        col_image, col_info = st.columns(
            [1, 3]
        )

        with col_image:

            if listing["photo"]:

                st.image(
                    listing["photo"],
                    use_container_width=True
                )

        with col_info:

            st.markdown(
                f"### {listing['title']}"
            )

            a, b, c, d = st.columns(4)

            a.metric(
                "Achat",
                f"{price:.0f} €"
            )

            b.metric(
                "Revente estimée",
                (
                    f"{resale_price:.0f} €"
                    if resale_price is not None
                    else "N/A"
                )
            )

            c.metric(
                "Marge",
                (
                    f"{margin:.0f} €"
                    if margin is not None
                    else "N/A"
                )
            )

            d.metric(
                "ROI",
                (
                    f"{roi:.0f} %"
                    if roi is not None
                    else "N/A"
                )
            )

            st.progress(
                score / 100
            )

            st.write(
                f"🔥 **Score : {score}/100**"
            )

            st.write(
                f"**Marque :** "
                f"{listing['brand'] or 'Non précisée'}"
            )

            st.write(
                f"**Taille :** "
                f"{listing['size'] or 'Non précisée'}"
            )

            st.write(
                f"**État :** "
                f"{listing['status'] or 'Non précisé'}"
            )

            st.write(
                f"**Favoris :** "
                f"{listing['favourites']}"
            )

            st.write(
                "**Liquidité :** "
                + calculate_liquidity(
                    listing,
                    market["count"]
                )
            )

            positives, risks = generate_explanation(
                listing,
                resale_price,
                margin,
                roi,
                market["count"],
                minimum_profit
            )

            st.markdown(
                "#### ✅ Pourquoi c'est intéressant"
            )

            for positive in positives:
                st.write(
                    f"• {positive}"
                )

            st.markdown(
                "#### ⚠️ Risques / limites"
            )

            for risk in risks:
                st.write(
                    f"• {risk}"
                )

            if listing["url"].startswith("http"):

                st.link_button(
                    "🔗 Ouvrir l'annonce Vinted",
                    listing["url"]
                )


# ============================================================
# ÉCRAN D'ACCUEIL
# ============================================================

else:

    st.header(
        "🎯 Trouve des opportunités Vinted"
    )

    st.write(
        "Entre simplement une niche, ton budget et "
        "ton bénéfice minimum."
    )

    st.info(
        "L'application recherche réellement les annonces "
        "Vinted via Piloterr. Elle ne crée aucun résultat "
        "fictif."
    )

    st.markdown(
        """
### Comment ça fonctionne ?

**1️⃣ Tu écris une niche**

Exemple :

`Nike Tech Fleece`

**2️⃣ L'application recherche Vinted**

Elle récupère les annonces réellement disponibles.

**3️⃣ Elle analyse les prix**

Elle calcule notamment la médiane et les quartiles
des prix actuellement demandés.

**4️⃣ Elle analyse chaque opportunité**

Prix d'achat, marge théorique, ROI, état, taille,
favoris et quantité de données disponibles.

**5️⃣ Elle classe les annonces**

Chaque annonce reçoit un score /100.

⚠️ **Les ventes réellement conclues ne sont pas inventées.**

Si une source d'historique des ventes est ajoutée
plus tard, elle pourra être utilisée comme donnée
prioritaire pour remplacer les estimations basées
sur les prix demandés.
"""
    )