import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(layout="wide")

DISCORD_WEBHOOK = st.secrets.get("DISCORD_WEBHOOK_CANADA")

LOOKBACK = 200
TOP_N = 15

W_S1, W_S2, W_S3, W_S4 = 0.30, 0.25, 0.25, 0.20

# =====================================================
# LOAD TICKERS — TSX COMPOSITE (CHEMIN CORRIGÉ)
# =====================================================
@st.cache_data
def load_tickers():
    df = pd.read_excel("tsxcomposite_constituents.xlsx")  # 👈 chemin RELATIF
    tickers = (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    # Yahoo Finance → .TO
    return [t if t.endswith(".TO") else f"{t}.TO" for t in tickers]

TICKERS = load_tickers()

# =====================================================
# YAHOO FINANCE — OHLC
# =====================================================
@st.cache_data(ttl=3600)
def get_ohlc(ticker):
    try:
        df = yf.download(
            ticker,
            period=f"{LOOKBACK + 5}d",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df.empty or len(df) < LOOKBACK:
            return None

        df = df.rename(columns={
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "Close",
            "Volume": "v"
        })

        return df[["o", "h", "l", "Close", "v"]]

    except Exception:
        return None

# =====================================================
# INDICATEURS
# =====================================================
def EMA(s, n):
    return s.ewm(span=n, adjust=False).mean()

def ROC(s, n):
    return s.pct_change(n) * 100

def RSI(s, n=14):
    d = s.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    rs = g.rolling(n).mean() / l.rolling(n).mean()
    return 100 - (100 / (1 + rs))

def ATR(df, n=14):
    tr = pd.concat([
        df["h"] - df["l"],
        (df["h"] - df["Close"].shift()).abs(),
        (df["l"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

# =====================================================
# STRATEGY 4 (TA LOGIQUE)
# =====================================================
def strategy4(df):
    if len(df) < 60:
        return 0

    close = df["Close"]
    rv = df["v"] / df["v"].rolling(20).mean()
    gap = (df["o"] - df["Close"].shift()) / df["Close"].shift() * 100
    i = -1

    s = sum([
        rv.iloc[i] > 1.3,
        rv.iloc[i] > 1.6,
        close.iloc[i] > close.rolling(20).max().iloc[i],
        close.iloc[i] > close.rolling(50).max().iloc[i],
        gap.tail(10).max() > 2,
        gap.tail(10).max() > 4
    ])

    return round(s / 6 * 100, 2)

# =====================================================
# PLACEHOLDERS (à remplacer plus tard)
# =====================================================
def strategy1(df): return 50
def strategy2(df): return 50
def strategy3(df): return 50

# =====================================================
# SCORE GLOBAL (OFFSET)
# =====================================================
def compute_score(df, offset):
    df = df.iloc[:offset]

    s1 = strategy1(df)
    s2 = strategy2(df)
    s3 = strategy3(df)
    s4 = strategy4(df)

    return round(
        W_S1 * s1 +
        W_S2 * s2 +
        W_S3 * s3 +
        W_S4 * s4,
        2
    )

# =====================================================
# SCAN — NOUVEAUX ENTRANTS UNIQUEMENT
# =====================================================
def scan_universe(tickers):
    today, yesterday = [], []

    for t in tickers:
        df = get_ohlc(t)
        if df is None:
            continue

        price = round(df["Close"].iloc[-1], 2)

        score_today = compute_score(df, -1)
        score_yesterday = compute_score(df, -2)

        today.append([t, price, score_today])
        yesterday.append([t, score_yesterday])

    df_today = pd.DataFrame(today, columns=["Ticker", "Price", "Score"])
    df_yesterday = pd.DataFrame(yesterday, columns=["Ticker", "Score_Y"])

    top_today = df_today.sort_values("Score", ascending=False).head(TOP_N)
    top_yesterday = df_yesterday.sort_values("Score_Y", ascending=False).head(TOP_N)

    new_entries = top_today[
        ~top_today["Ticker"].isin(top_yesterday["Ticker"])
    ]

    return new_entries.sort_values("Score", ascending=False)

# =====================================================
# DISCORD — CANADA
# =====================================================
def send_to_discord(df):
    if not DISCORD_WEBHOOK or df.empty:
        return

    lines = [
        f"🇨🇦 **{r['Ticker']}** @ ${r['Price']} | Score `{r['Score']}`"
        for _, r in df.iterrows()
    ]

    payload = {
        "content":
        "🚨 **CANADA — Nouveaux entrants Swing Scanner (Yahoo)**\n\n" +
        "\n".join(lines)
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except Exception:
        pass

# =====================================================
# UI
# =====================================================
st.title("🇨🇦 Swing Scanner — Nouveaux entrants TSX (Yahoo Finance)")

limit = st.slider("Nombre de tickers à scanner", 50, len(TICKERS), 300)

if st.button("🚀 Lancer le scan et envoyer sur Discord"):
    with st.spinner("Scan en cours…"):
        df = scan_universe(TICKERS[:limit])

        if not df.empty:
            st.dataframe(df, use_container_width=True)
            send_to_discord(df)
            st.success("🚀 Nouveaux entrants CANADA envoyés sur Discord")
        else:
            st.info("Aucun nouveau titre dans le TOP aujourd’hui.")
