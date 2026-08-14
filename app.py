import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Vinted Deal Hunter",
    page_icon="🔎",
    layout="wide",
)

API_URL = "https://api.piloterr.com/v2/vinted/search"


# ============================================================
# OUTILS
# ============================================================

def get_api_key() -> str:
    """Récupère la clé API depuis les Secrets Streamlit."""

    try:
        key = st.secrets.get("PILOTERR_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass

    return os.getenv("PILOTERR_API_KEY", "").strip()


def to_float(value: Any) -> Optional[float]:
    """Convertit une valeur en nombre sans inventer de valeur."""

    if value is None:
        return None

    try:
        if isinstance(value, str):
            value = (
                value
                .replace("€", "")
                .replace(",", ".")
                .strip()
            )

        return float(value)

    except (ValueError, TypeError):
        return None


def euros(value: Optional[float]) -> str:
    if value is None:
        return "—"

    return f"{value:.2f} €"


def text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# RECHERCHE VINTED
# ============================================================

def search_vinted(
    query: str,
    max_price: float,
    pages: int = 3,
    per_page: int = 24,
) -> List[Dict[str, Any]]:
    """
    Recherche réellement des annonces Vinted via l'API configurée.

    Aucun résultat fictif n'est créé.
    """

    api_key = get_api_key()

    if not api_key:
        raise RuntimeError(
            "PILOTERR_API_KEY n'est pas configurée."
        )

    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }

    all_results = []

    for page in range(1, pages + 1):

        params = {
            "query": query,
            "page": page,
            "per_page": per_page,
            "order": "relevance",
            "region": "fr",
        }

        response = requests.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 401:
            raise RuntimeError(
                "La clé API est invalide ou non autorisée."
            )

        if response.status_code == 402:
            raise RuntimeError(
                "Le fournisseur indique que le quota/crédit est insuffisant."
            )

        if response.status_code == 429:
            raise RuntimeError(
                "La limite de requêtes a été atteinte."
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Erreur API HTTP {response.status_code}."
            )

        data = response.json()

        if isinstance(data, dict):
            results = data.get("results", [])
        elif isinstance(data, list):
            results = data
        else:
            results = []

        if not results:
            break

        all_results.extend(results)

        # Si la page contient moins de résultats que demandé,
        # il n'y a probablement plus de résultats à récupérer.
        if len(results) < per_page:
            break

    return all_results


# ============================================================
# NORMALISATION
# ============================================================

def extract_price(item: Dict[str, Any]) -> Optional[float]:

    candidates = [
        item.get("price"),
        item.get("current_price"),
        item.get("raw_price"),
    ]

    pricing = item.get("pricing")

    if isinstance(pricing, dict):
        candidates.extend([
            pricing.get("price"),
            pricing.get("raw_price"),
        ])

    for value in candidates:
        number = to_float(value)

        if number is not None:
            return number

    return None


def extract_image(item: Dict[str, Any]) -> str:

    direct = item.get("image_url")

    if direct:
        return text(direct)

    photos = item.get("photos")

    if isinstance(photos, list) and photos:

        first = photos[0]

        if isinstance(first, dict):
            return text(first.get("url"))

        if isinstance(first, str):
            return first

    photo = item.get("photo")

    if isinstance(photo, dict):
        return text(photo.get("url"))

    return ""


def extract_condition(item: Dict[str, Any]) -> str:

    condition = item.get("condition")

    if isinstance(condition, dict):

        return text(
            condition.get("title")
            or condition.get("name")
        )

    return text(condition)


def normalize_listing(
    item: Dict[str, Any]
) -> Dict[str, Any]:

    return {
        "id": text(item.get("id")),
        "title": text(item.get("title")),
        "brand": text(item.get("brand")),
        "price": extract_price(item),
        "condition": extract_condition(item),
        "size": text(item.get("size")),
        "color": text(item.get("color")),
        "url": text(
            item.get("url")
            or item.get("share_url")
        ),
        "image": extract_image(item),
        "favorites": to_float(
            item.get("favorites")
            or item.get("favourite_count")
        ),
        "raw": item,
    }


# ============================================================
# FILTRAGE
# ============================================================

def filter_listings(
    listings: List[Dict[str, Any]],
    max_price: float,
) -> List[Dict[str, Any]]:

    filtered = []

    seen = set()

    for listing in listings:

        price = listing["price"]

        if price is None:
            continue

        if price > max_price:
            continue

        identifier = (
            listing["id"]
            or listing["url"]
            or (
                listing["title"],
                price,
            )
        )

        if identifier in seen:
            continue

        seen.add(identifier)

        filtered.append(listing)

    return filtered


# ============================================================
# ÉVALUATION DE L'ANNONCE
# ============================================================

def calculate_basic_score(
    listing: Dict[str, Any],
    budget: float,
) -> int:

    score = 0

    price = listing["price"]

    if price is None:
        return 0

    # Plus le prix est bas par rapport au budget,
    # plus l'annonce est intéressante.
    ratio = price / budget if budget > 0 else 1

    if ratio <= 0.50:
        score += 50
    elif ratio <= 0.65:
        score += 42
    elif ratio <= 0.80:
        score += 35
    elif ratio <= 0.90:
        score += 28
    else:
        score += 20

    # État
    condition = listing["condition"].lower()

    if "neuf" in condition:
        score += 25
    elif "très bon" in condition:
        score += 20
    elif "bon" in condition:
        score += 12
    elif condition:
        score += 5

    # Informations disponibles
    if listing["image"]:
        score += 10

    if listing["brand"]:
        score += 5

    if listing["size"]:
        score += 5

    return min(score, 95)


# ============================================================
# HISTORIQUE DES VENTES
# ============================================================

def get_real_sales(
    listing: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    IMPORTANT :

    Cette fonction ne considère PAS les annonces actuellement
    en ligne comme des ventes.

    Tant qu'une véritable source d'historique de ventes n'est
    pas connectée, elle retourne volontairement une liste vide.
    """

    return []


# ============================================================
# MARCHÉ
# ============================================================

def market_analysis(
    sales: List[Dict[str, Any]]
) -> Dict[str, Any]:

    if not sales:

        return {
            "available": False,
            "sales_count": 0,
            "median": None,
            "q1": None,
            "q3": None,
            "confidence": 0,
        }

    prices = []

    for sale in sales:

        price = to_float(
            sale.get("sold_price")
        )

        if price is not None:
            prices.append(price)

    if not prices:

        return {
            "available": False,
            "sales_count": 0,
            "median": None,
            "q1": None,
            "q3": None,
            "confidence": 0,
        }

    series = pd.Series(prices)

    count = len(prices)

    if count >= 50:
        confidence = 95
    elif count >= 30:
        confidence = 90
    elif count >= 20:
        confidence = 80
    elif count >= 10:
        confidence = 65
    elif count >= 5:
        confidence = 50
    else:
        confidence = 25

    return {
        "available": True,
        "sales_count": count,
        "median": float(series.median()),
        "q1": float(series.quantile(0.25)),
        "q3": float(series.quantile(0.75)),
        "confidence": confidence,
    }


# ============================================================
# LIQUIDITÉ
# ============================================================

def liquidity_analysis(
    sales: List[Dict[str, Any]]
) -> Dict[str, Any]:

    days = []

    for sale in sales:

        value = to_float(
            sale.get("days_to_sell")
        )

        if value is not None:
            days.append(value)

    if not days:

        return {
            "available": False,
            "median_days": None,
            "label": "INCONNUE",
            "score": 0,
        }

    median = float(
        pd.Series(days).median()
    )

    if median <= 7:
        label = "ÉLEVÉE"
        score = 95

    elif median <= 14:
        label = "BONNE"
        score = 85

    elif median <= 30:
        label = "MOYENNE"
        score = 65

    elif median <= 60:
        label = "FAIBLE"
        score = 40

    else:
        label = "TRÈS FAIBLE"
        score = 20

    return {
        "available": True,
        "median_days": median,
        "label": label,
        "score": score,
    }


# ============================================================
# ANALYSE D'UNE ANNONCE
# ============================================================

def analyze_listing(
    listing: Dict[str, Any],
    budget: float,
    minimum_profit: float,
    fees: float,
) -> Dict[str, Any]:

    sales = get_real_sales(listing)

    market = market_analysis(sales)

    liquidity = liquidity_analysis(sales)

    # Aucun prix de revente inventé.
    resale_price = market["median"]

    purchase_price = listing["price"]

    margin = None
    roi = None

    if (
        purchase_price is not None
        and resale_price is not None
    ):

        margin = (
            resale_price
            - purchase_price
            - fees
        )

        if purchase_price > 0:
            roi = (
                margin
                / purchase_price
                * 100
            )

    score = calculate_basic_score(
        listing,
        budget,
    )

    # Si on dispose réellement d'un marché vendu,
    # on peut enrichir le score.
    if market["available"]:

        score = int(
            score * 0.5
            + liquidity["score"] * 0.2
            + market["confidence"] * 0.3
        )

    else:
        # Sans ventes réelles, plafond volontaire.
        score = min(score, 60)

    positives = []
    risks = []

    if purchase_price is not None:
        positives.append(
            f"Prix d'achat : {purchase_price:.2f} €"
        )

    if listing["condition"]:
        positives.append(
            f"État indiqué : {listing['condition']}"
        )

    if listing["image"]:
        positives.append(
            "Photo disponible."
        )

    if market["available"]:
        positives.append(
            f"{market['sales_count']} ventes comparables analysées."
        )
    else:
        risks.append(
            "Historique de ventes réelles indisponible."
        )

    if not listing["image"]:
        risks.append(
            "Photo non disponible."
        )

    if not listing["condition"]:
        risks.append(
            "État non précisé."
        )

    return {
        "listing": listing,
        "market": market,
        "liquidity": liquidity,
        "resale_price": resale_price,
        "margin": margin,
        "roi": roi,
        "score": score,
        "positives": positives,
        "risks": risks,
    }


# ============================================================
# AFFICHAGE
# ============================================================

def display_market(
    results: List[Dict[str, Any]]
):

    if not results:
        return

    market = results[0]["market"]

    st.header("📈 ANALYSE DU MARCHÉ")

    if not market["available"]:

        st.warning(
            "🟡 HISTORIQUE DE VENTES INSUFFISANT"
        )

        st.write(
            "Les annonces affichées sont de vraies annonces "
            "actuellement disponibles. Elles ne sont pas "
            "considérées comme des ventes."
        )

        return

    cols = st.columns(4)

    cols[0].metric(
        "Prix de revente réaliste",
        euros(market["median"]),
    )

    cols[1].metric(
        "Fourchette",
        f"{euros(market['q1'])} – "
        f"{euros(market['q3'])}",
    )

    cols[2].metric(
        "Ventes analysées",
        market["sales_count"],
    )

    cols[3].metric(
        "Confiance",
        f"{market['confidence']}%",
    )


def display_listing(
    result: Dict[str, Any]
):

    listing = result["listing"]

    score = result["score"]

    if score >= 85:
        verdict = "🔥 EXCELLENTE AFFAIRE"
    elif score >= 70:
        verdict = "🟢 TRÈS INTÉRESSANT"
    elif score >= 50:
        verdict = "🟠 À ANALYSER"
    else:
        verdict = "🔴 RISQUÉ"

    title = (
        listing["title"]
        or "Annonce Vinted"
    )

    st.subheader(
        f"{verdict} — {title}"
    )

    if listing["image"]:

        try:
            st.image(
                listing["image"],
                width=240,
            )
        except Exception:
            pass

    cols = st.columns(5)

    cols[0].metric(
        "Prix",
        euros(listing["price"]),
    )

    cols[1].metric(
        "Revente",
        euros(result["resale_price"]),
    )

    cols[2].metric(
        "Marge",
        euros(result["margin"]),
    )

    if result["roi"] is not None:
        roi_text = f"{result['roi']:.0f}%"
    else:
        roi_text = "—"

    cols[3].metric(
        "ROI",
        roi_text,
    )

    cols[4].metric(
        "Score",
        f"{score}/100",
    )

    st.write(
        f"**Marque :** "
        f"{listing['brand'] or 'Non précisée'}"
    )

    st.write(
        f"**État :** "
        f"{listing['condition'] or 'Non précisé'}"
    )

    st.write(
        f"**Taille :** "
        f"{listing['size'] or 'Non précisée'}"
    )

    if listing["favorites"] is not None:
        st.write(
            f"❤️ **Favoris :** "
            f"{int(listing['favorites'])}"
        )

    if result["market"]["available"]:

        st.write(
            f"**Liquidité :** "
            f"{result['liquidity']['label']}"
        )

    else:

        st.write(
            "**Liquidité :** ⚪ Inconnue"
        )

    st.write(
        f"**Confiance :** "
        f"{result['market']['confidence']}%"
    )

    if result["positives"]:

        st.markdown(
            "### ✅ Pourquoi cette annonce est intéressante"
        )

        for item in result["positives"]:
            st.write(
                f"• {item}"
            )

    if result["risks"]:

        st.markdown(
            "### ⚠️ Risques / limites"
        )

        for item in result["risks"]:
            st.write(
                f"• {item}"
            )

    if listing["url"]:

        st.link_button(
            "🔗 Ouvrir l'annonce Vinted",
            listing["url"],
        )

    st.divider()


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "🔎 Vinted Deal Hunter"
)

st.write(
    "Recherche automatiquement de vraies annonces Vinted "
    "et identifie les opportunités potentielles."
)


with st.sidebar:

    st.header("🎯 TA RECHERCHE")

    niche = st.text_input(
        "Niche",
        placeholder="Nike Tech Fleece",
    )

    budget = st.number_input(
        "Budget maximum (€)",
        min_value=1.0,
        max_value=10000.0,
        value=35.0,
        step=1.0,
    )

    minimum_profit = st.number_input(
        "Bénéfice minimum (€)",
        min_value=0.0,
        max_value=10000.0,
        value=20.0,
        step=1.0,
    )

    fees = st.number_input(
        "Frais / sécurité (€)",
        min_value=0.0,
        max_value=1000.0,
        value=3.0,
        step=0.5,
    )

    pages = st.slider(
        "Nombre de pages à rechercher",
        min_value=1,
        max_value=5,
        value=3,
    )

    search = st.button(
        "🔥 CHERCHER LES MEILLEURES OFFRES",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# ACTION DE RECHERCHE
# ============================================================

if search:

    if not niche.strip():

        st.error(
            "Veuillez entrer une niche."
        )

        st.stop()

    if not get_api_key():

        st.error(
            "⚠️ RECHERCHE AUTOMATIQUE NON CONFIGURÉE"
        )

        st.info(
            "Ajoute PILOTERR_API_KEY dans les Secrets "
            "de ton application Streamlit."
        )

        st.stop()

    with st.spinner(
        "🔎 Recherche réelle des annonces Vinted..."
    ):

        try:

            raw = search_vinted(
                query=niche.strip(),
                max_price=budget,
                pages=pages,
                per_page=24,
            )

        except Exception as error:

            st.error(
                f"❌ Erreur pendant la recherche : {error}"
            )

            st.stop()

    listings = [
        normalize_listing(item)
        for item in raw
    ]

    listings = filter_listings(
        listings,
        budget,
    )

    if not listings:

        st.warning(
            "Aucune annonce trouvée dans ton budget."
        )

        st.stop()

    results = []

    for listing in listings:

        results.append(
            analyze_listing(
                listing=listing,
                budget=budget,
                minimum_profit=minimum_profit,
                fees=fees,
            )
        )

    results.sort(
        key=lambda x: (
            x["score"],
            -(x["listing"]["price"] or 999999),
        ),
        reverse=True,
    )

    st.success(
        f"✅ {len(results)} annonce(s) réelle(s) trouvée(s)."
    )

    display_market(results)

    st.header(
        "🏆 MEILLEURES OPPORTUNITÉS"
    )

    for result in results:

        display_listing(result)


# ============================================================
# PAGE INITIALE
# ============================================================

else:

    st.header(
        "🚀 Trouve automatiquement tes opportunités"
    )

    st.write(
        """
        Entre simplement une niche, ton budget maximum et
        ton bénéfice minimum.

        Exemple :

        **Nike Tech Fleece**

        **Budget : 35 €**

        **Bénéfice minimum : 20 €**

        Puis clique sur :

        **🔥 CHERCHER LES MEILLEURES OFFRES**
        """
    )

    st.info(
        "Les annonces affichées proviennent d'une vraie "
        "recherche de données Vinted. Aucune annonce fictive "
        "n'est générée."
    )

    st.warning(
        "⚠️ Tant qu'une véritable source d'historique de "
        "ventes n'est pas connectée, l'application ne "
        "présente pas les prix des annonces actives comme "
        "des prix de vente réalisés."
    )
