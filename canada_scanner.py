import os
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf

# =====================================================
# CONFIG
# =====================================================

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

LOOKBACK = 200
TOP_N = 15

SLEEP_PER_TICKER = 0.4

W_S1, W_S2, W_S3, W_S4 = 0.30, 0.25, 0.25, 0.20

# =====================================================
# LOAD TICKERS
# =====================================================

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

    return [
        t if t.endswith(".TO")
        else f"{t}.TO"
        for t in tickers
    ]

# =====================================================
# YAHOO
# =====================================================

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

    except Exception as e:
        print(f"{ticker}: {e}")
        return None

# =====================================================
# STRATEGIES
# =====================================================

def strategy1(df):
    return 50

def strategy2(df):
    return 50

def strategy3(df):
    return 50

def strategy4(df):

    if len(df) < 60:
        return np.nan

    close = df["Close"]

    rv = df["v"] / df["v"].rolling(20).mean()

    gap = (
        (df["o"] - df["Close"].shift())
        / df["Close"].shift()
        * 100
    )

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
# SCORE
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
            W_S1 * scores[0]
            + W_S2 * scores[1]
            + W_S3 * scores[2]
            + W_S4 * scores[3],
            2
        )

    except Exception:
        return np.nan

# =====================================================
# SCAN COMPLET
# =====================================================

def scan_market():

    tickers = load_tickers()

    today = []
    yesterday = []

    total = len(tickers)

    for n, ticker in enumerate(tickers, start=1):

        print(f"{n}/{total} {ticker}")

        df = get_ohlc(ticker)

        time.sleep(SLEEP_PER_TICKER)

        if df is None:
            continue

        score_today = compute_score(df, -1)
        score_yesterday = compute_score(df, -2)

        if pd.isna(score_today) or pd.isna(score_yesterday):
            continue

        price = round(df["Close"].iloc[-1], 2)

        today.append([
            ticker,
            price,
            score_today
        ])

        yesterday.append([
            ticker,
            score_yesterday
        ])

    if not today:
        return pd.DataFrame()

    df_today = pd.DataFrame(
        today,
        columns=["Ticker", "Price", "Score"]
    )

    df_yesterday = pd.DataFrame(
        yesterday,
        columns=["Ticker", "Score_Y"]
    )

    top_today = (
        df_today
        .sort_values("Score", ascending=False)
        .head(TOP_N)
    )

    top_yesterday = (
        df_yesterday
        .sort_values("Score_Y", ascending=False)
        .head(TOP_N)
    )

    new_entries = top_today[
        ~top_today["Ticker"].isin(
            top_yesterday["Ticker"]
        )
    ]

    return new_entries.sort_values(
        "Score",
        ascending=False
    )

# =====================================================
# DISCORD
# =====================================================

def send_discord(df):

    if df.empty:
        print("Aucun nouvel entrant.")
        return

    lines = [
        f"🇨🇦 **{r['Ticker']}** @ ${r['Price']} | Score `{r['Score']}`"
        for _, r in df.iterrows()
    ]

    message = (
        "🚨 **CANADA — Nouveaux entrants**\n\n"
        + "\n".join(lines)
    )

    requests.post(
        DISCORD_WEBHOOK,
        json={"content": message},
        timeout=10
    )

    print("Discord envoyé.")

# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    print("Début du scan TSX...")

    df = scan_market()

    if not df.empty:
        print(df)
    else:
        print("Aucun signal.")

    send_discord(df)

    print("Scan terminé.")

