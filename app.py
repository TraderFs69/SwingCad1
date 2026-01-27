import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(layout="wide")

DISCORD_WEBHOOK = st.secrets.get("DISCORD_WEBHOOK_CANADA")

LOOKBACK = 200
TOP_N = 15

BATCH_SIZE = 40
SLEEP_PER_TICKER = 0.4

W_S1, W_S2, W_S3, W_S4 = 0.30, 0.25, 0.25, 0.20

# =====================================================
# LOAD TICKERS — TSX
# =====================================================
@st.cache_data
def load_tickers():
    df = pd.read_excel("tsxcomposite_constituents.xlsx")
    tickers = (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    return [t if t.endswith(".TO") else f"{t}.TO" for t in tickers]

TICKERS = load_tickers()

# =====================================================
# YAHOO FINANCE — SAFE
# =====================================================
@st.cache_data(ttl=3600)
def get_ohlc(ticker):
    try:
        df = yf.download(
            ticker,
            period=f"{LOOKBACK+5}d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
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
# STRATEGY 4
# =====================================================
def strategy4(df):
    if len(df) < 60:
        return np.nan

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
# PLACEHOLDERS STABLES
# =====================================================
def strategy1(df): return 50
def strategy2(df): return 50
def strategy3(df): return 50

# =====================================================
# SCORE GLOBAL (SAFE)
# =====================================================
def compute_score(df, offset):
    try:
        df = df.iloc[:offset]

        scores = [
            strategy1(df),
            strategy2(df),
            strategy3(df),
            strategy4(df)
        ]

        if any(pd.isna(s) for s in scores):
            return np.nan

        return round(
            W_S1*scores[0] +
            W_S2*scores[1] +
            W_S3*scores[2] +
            W_S4*scores[3],
            2
        )
    except Exception:
        return np.nan

# =====================================================
# BATCH STATE
# =====================================================
if "batch_index" not in st.session_state:
    st.session_state.batch_index = 0

# =====================================================
# SCAN PAR BATCH — ULTRA ROBUSTE
# =====================================================
def scan_batch(tickers):
    start = st.session_state.batch_index
    end = start + BATCH_SIZE
    batch = tickers[start:end]

    today, yesterday = [], []

    for t in batch:
        df = get_ohlc(t)
        time.sleep(SLEEP_PER_TICKER)

        if df is None:
            continue

        score_today = compute_score(df, -1)
        score_yesterday = compute_score(df, -2)

        if pd.isna(score_today) or pd.isna(score_yesterday):
            continue

        price = round(df["Close"].iloc[-1], 2)

        today.append([t, price, score_today])
        yesterday.append([t, score_yesterday])

    if not today or not yesterday:
        return pd.DataFrame()

    df_today = pd.DataFrame(today, columns=["Ticker", "Price", "Score"])
    df_yesterday = pd.DataFrame(yesterday, columns=["Ticker", "Score_Y"])

    df_today["Score"] = pd.to_numeric(df_today["Score"], errors="coerce")
    df_yesterday["Score_Y"] = pd.to_numeric(df_yesterday["Score_Y"], errors="coerce")

    df_today.dropna(inplace=True)
    df_yesterday.dropna(inplace=True)

    if df_today.empty or df_yesterday.empty:
        return pd.DataFrame()

    top_today = df_today.sort_values("Score", ascending=False).head(TOP_N)
    top_yesterday = df_yesterday.sort_values("Score_Y", ascending=False).head(TOP_N)

    new_entries = top_today[
        ~top_today["Ticker"].isin(top_yesterday["Ticker"])
    ]

    return new_entries.sort_values("Score", ascending=False)

# =====================================================
# ADVANCE BATCH
# =====================================================
def advance_batch(total):
    st.session_state.batch_index += BATCH_SIZE
    if st.session_state.batch_index >= total:
        st.session_state.batch_index = 0

# =====================================================
# UI
# =====================================================
st.title("🇨🇦 Swing Scanner TSX — Batch automatique (Yahoo)")

st.caption("Anti-rate-limit • Stable • Nouveaux entrants uniquement")

if st.button("🚀 Lancer le batch"):
    with st.spinner("Scan du batch en cours…"):
        df = scan_batch(TICKERS)

        if not df.empty:
            st.dataframe(df, use_container_width=True)
            send_lines = [
                f"🇨🇦 **{r['Ticker']}** @ ${r['Price']} | Score `{r['Score']}`"
                for _, r in df.iterrows()
            ]
            requests.post(
                DISCORD_WEBHOOK,
                json={"content": "🚨 **CANADA — Nouveaux entrants (Batch)**\n\n" + "\n".join(send_lines)},
                timeout=5
            )
            st.success("🚀 Nouveaux entrants envoyés sur Discord")
        else:
            st.info("Aucun nouvel entrant dans ce batch")

        advance_batch(len(TICKERS))

st.write("📦 Batch index actuel :", st.session_state.batch_index)
