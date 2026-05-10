import requests
import streamlit as st
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client

# ------------------- CONFIG -------------------
API_KEY = st.secrets["ODDS_API_KEY"]

REGIONS = "us"
ODDS_FORMAT = "american"
BOOKMAKER_KEY = "draftkings"
REFRESH_SECONDS = 30

# ------------------- SPORT SELECTOR -------------------
SPORT_MAP = {
    "NBA": "basketball_nba",
    "WNBA": "basketball_wnba",
    "NCAAB": "basketball_ncaab",
    "NFL": "americanfootball_nfl",
    "MLB": "baseball_mlb",
}

SPORT_LABEL = st.selectbox("Select Sport", list(SPORT_MAP.keys()))
SPORT = SPORT_MAP[SPORT_LABEL]

# ------------------- SUPABASE -------------------
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# ------------------- STREAMLIT -------------------
st.set_page_config(page_title="Odds Monitor", layout="wide")
st.title("📈 Sharp Money Odds Monitor")

# ------------------- AUTO REFRESH -------------------
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > REFRESH_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()

# ------------------- HELPERS -------------------
def fetch_odds(sport):
    try:
        res = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds",
            params={
                "apiKey": API_KEY,
                "regions": REGIONS,
                "markets": "totals,spreads",
                "oddsFormat": ODDS_FORMAT,
            },
            timeout=10,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def get_existing_game(game_id):
    result = (
        supabase.table("odds_snapshot")
        .select("*")
        .eq("game_id", game_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_game(payload):
    supabase.table("odds_snapshot").upsert(payload).execute()


# ------------------- CLEAN NUMBER (TRUE FIX) -------------------
def clean_number(v):
    if v is None or v == "":
        return None  # IMPORTANT: keep numeric-safe for pandas

    try:
        v = float(v)
    except:
        return None

    # Round to 1 decimal place first to ensure consistency
    v = round(v, 1)
    
    # If it's a whole number after rounding, return as int
    if v.is_integer():
        return int(v)
    
    return v


# ------------------- TIME ESTIMATOR -------------------
def estimate_game_time(sport, start_dt):
    now = datetime.now(timezone.utc)

    if now < start_dt:
        return "PRE"

    elapsed = (now - start_dt).total_seconds() / 60

    if sport in ["basketball_nba", "basketball_wnba"]:
        total_game_time = 135  # Total game time including breaks
        quarter_play_time = 12  # Actual playing time per quarter
        halftime_duration = 15  # Halftime break
        
        # Calculate what fraction of the total game has elapsed
        game_fraction = min(elapsed / total_game_time, 1.0)
        
        # Determine current quarter based on fraction, accounting for halftime
        if game_fraction < 0.22:  # First quarter (~30 min / 135 min)
            quarter_fraction = game_fraction / 0.22
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q1 - {remaining}m"
        elif game_fraction < 0.44:  # Second quarter (~60 min / 135 min)
            quarter_fraction = (game_fraction - 0.22) / 0.22
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q2 - {remaining}m"
        elif game_fraction < 0.5:  # Halftime (~67.5 min / 135 min)
            return "HALF"
        elif game_fraction < 0.72:  # Third quarter (~97.5 min / 135 min)
            quarter_fraction = (game_fraction - 0.5) / 0.22
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q3 - {remaining}m"
        elif game_fraction < 0.94:  # Fourth quarter (~127.5 min / 135 min)
            quarter_fraction = (game_fraction - 0.72) / 0.22
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q4 - {remaining}m"
        else:
            return "FINAL"

    if sport == "basketball_ncaab":
        total_game_time = 120  # Total game time including breaks
        half_play_time = 20  # Actual playing time per half
        halftime_duration = 15  # Halftime break
        
        # Calculate what fraction of the total game has elapsed
        game_fraction = min(elapsed / total_game_time, 1.0)
        
        # Determine current half based on fraction, accounting for halftime
        if game_fraction < 0.42:  # First half (~50 min / 120 min)
            half_fraction = game_fraction / 0.42
            elapsed_in_half = half_fraction * half_play_time
            remaining = int(half_play_time - elapsed_in_half)
            return f"1H - {remaining}m"
        elif game_fraction < 0.5:  # Halftime (~60 min / 120 min)
            return "HALF"
        elif game_fraction < 0.92:  # Second half (~110 min / 120 min)
            half_fraction = (game_fraction - 0.5) / 0.42
            elapsed_in_half = half_fraction * half_play_time
            remaining = int(half_play_time - elapsed_in_half)
            return f"2H - {remaining}m"
        else:
            return "FINAL"

    if sport == "americanfootball_nfl":
        total_game_time = 210  # Total game time including breaks
        quarter_play_time = 15  # Actual playing time per quarter
        halftime_duration = 20  # Halftime break
        
        # Calculate what fraction of the total game has elapsed
        game_fraction = min(elapsed / total_game_time, 1.0)
        
        # Determine current quarter based on fraction, accounting for halftime
        if game_fraction < 0.24:  # First quarter (~50 min / 210 min)
            quarter_fraction = game_fraction / 0.24
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q1 - {remaining}m"
        elif game_fraction < 0.48:  # Second quarter (~100 min / 210 min)
            quarter_fraction = (game_fraction - 0.24) / 0.24
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q2 - {remaining}m"
        elif game_fraction < 0.52:  # Halftime (~110 min / 210 min)
            return "HALF"
        elif game_fraction < 0.76:  # Third quarter (~160 min / 210 min)
            quarter_fraction = (game_fraction - 0.52) / 0.24
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q3 - {remaining}m"
        elif game_fraction < 0.98:  # Fourth quarter (~205 min / 210 min)
            quarter_fraction = (game_fraction - 0.76) / 0.22
            elapsed_in_quarter = quarter_fraction * quarter_play_time
            remaining = int(quarter_play_time - elapsed_in_quarter)
            return f"Q4 - {remaining}m"
        else:
            return "FINAL"

    if sport == "baseball_mlb":
        total_game_time = 160  # Average MLB game time including breaks
        total_innings = 9
        
        # Calculate what fraction of the total game has elapsed
        game_fraction = min(elapsed / total_game_time, 1.0)
        
        # Determine current inning based on fraction
        if game_fraction < 0.11:  # 1st inning (~20 min / 180 min)
            return "1st"
        elif game_fraction < 0.22:  # 2nd inning (~40 min / 180 min)
            return "2nd"
        elif game_fraction < 0.33:  # 3rd inning (~60 min / 180 min)
            return "3rd"
        elif game_fraction < 0.44:  # 4th inning (~80 min / 180 min)
            return "4th"
        elif game_fraction < 0.55:  # 5th inning (~100 min / 180 min)
            return "5th"
        elif game_fraction < 0.66:  # 6th inning (~120 min / 180 min)
            return "6th"
        elif game_fraction < 0.77:  # 7th inning (~140 min / 180 min)
            return "7th"
        elif game_fraction < 0.88:  # 8th inning (~160 min / 180 min)
            return "8th"
        elif game_fraction < 0.98:  # 9th inning (~175 min / 180 min)
            return "9th"
        else:
            return "FINAL"

    return "LIVE"


# ------------------- SAFE HIGHLIGHT -------------------
def highlight_row(row):
    value = 0

    if "drop" in row and row["drop"] is not None:
        value = abs(float(row["drop"]))
    elif "shift" in row and row["shift"] is not None:
        value = abs(float(row["shift"]))

    color = ""
    if value >= 20:
        color = "#ff4c4c"
    elif value >= 15:
        color = "#ffa500"
    elif value >= 10:
        color = "#ffff66"

    return [f"background-color: {color}"] * len(row)


# ------------------- FETCH DATA -------------------
data = fetch_odds(SPORT)

if not data:
    st.warning("No data available for this sport right now.")
    st.stop()

now = datetime.now(timezone.utc)

live_totals = []
upcoming_totals = []
live_spreads = []
upcoming_spreads = []

# ------------------- PROCESS -------------------
for game in data:

    g_id = str(game["id"])

    dk_book = next(
        (b for b in game.get("bookmakers", []) if b["key"] == BOOKMAKER_KEY),
        None
    )
    if not dk_book:
        continue

    home = game["home_team"]
    away = game["away_team"]

    start_dt = datetime.fromisoformat(
        game["commence_time"].replace("Z", "+00:00")
    )

    existing = get_existing_game(g_id)
    time_status = estimate_game_time(SPORT, start_dt)
    is_live = now >= start_dt

    # ------------------- TOTALS -------------------
    current_total = None
    pregame_total = None
    drop = None

    totals_market = next(
        (m for m in dk_book.get("markets", []) if m["key"] == "totals"),
        None
    )

    if totals_market:
        over_points = [
            o["point"]
            for o in totals_market.get("outcomes", [])
            if o["name"] == "Over"
        ]

        if over_points:
            current_total = over_points[0]

            pregame_total = (
                existing["pregame_total"]
                if existing and existing.get("pregame_total") is not None
                else current_total
            )

            drop = round(float(pregame_total) - float(current_total), 1)

    # ------------------- SPREADS -------------------
    current_spread = None
    pregame_spread = None
    shift = None

    spreads_market = next(
        (m for m in dk_book.get("markets", []) if m["key"] == "spreads"),
        None
    )

    if spreads_market:
        home_spread = next(
            (o["point"] for o in spreads_market.get("outcomes", []) if o["name"] == home),
            None
        )

        if home_spread is not None:
            current_spread = home_spread

            pregame_spread = (
                existing["pregame_spread"]
                if existing and existing.get("pregame_spread") is not None
                else current_spread
            )

            shift = round(float(pregame_spread) - float(current_spread), 1)

    # ------------------- SAVE -------------------
    upsert_game({
        "game_id": g_id,
        "sport": SPORT,
        "matchup": f"{away} @ {home}",
        "pregame_total": pregame_total,
        "current_total": current_total,
        "drop_value": drop,
        "pregame_spread": pregame_spread,
        "current_spread": current_spread,
        "shift_value": shift,
        "updated_at": now.isoformat()
    })

    # Determine time display based on whether game is live
    time_display = time_status if is_live else start_dt.astimezone(timezone(timedelta(hours=-4))).strftime("%I:%M %p EDT")

    row_total = {
        "matchup": f"{away} @ {home}",
        "time": time_display,
        "pregame": clean_number(pregame_total),
        "current": clean_number(current_total),
        "drop": clean_number(drop)
    }

    row_spread = {
        "matchup": f"{away} @ {home}",
        "time": time_display,
        "pregame": clean_number(pregame_spread),
        "current": clean_number(current_spread),
        "shift": clean_number(shift)
    }

    if is_live:
        live_totals.append(row_total)
        live_spreads.append(row_spread)
    else:
        upcoming_totals.append(row_total)
        upcoming_spreads.append(row_spread)

# ------------------- SORT -------------------
live_totals.sort(key=lambda x: abs(float(x["drop"] or 0)), reverse=True)
live_spreads.sort(key=lambda x: abs(float(x["shift"] or 0)), reverse=True)
upcoming_totals.sort(key=lambda x: abs(float(x["drop"] or 0)), reverse=True)
upcoming_spreads.sort(key=lambda x: abs(float(x["shift"] or 0)), reverse=True)

# ------------------- DATAFRAMES -------------------
live_totals_df = pd.DataFrame(live_totals)
live_spreads_df = pd.DataFrame(live_spreads)
upcoming_totals_df = pd.DataFrame(upcoming_totals)
upcoming_spreads_df = pd.DataFrame(upcoming_spreads)

# Format numeric columns to avoid floating precision issues
for df in [live_totals_df, live_spreads_df, upcoming_totals_df, upcoming_spreads_df]:
    for col in ['pregame', 'current', 'drop', 'shift']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.1f}" if x is not None and isinstance(x, float) and not float(x).is_integer() else x)

# ------------------- DISPLAY -------------------
st.subheader("📊 Live Totals")
st.dataframe(live_totals_df.style.apply(highlight_row, axis=1),
             use_container_width=True, hide_index=True)

st.subheader("📉 Live Spreads")
st.dataframe(live_spreads_df.style.apply(highlight_row, axis=1),
             use_container_width=True, hide_index=True)

st.subheader("🕒 Upcoming Totals")
st.dataframe(upcoming_totals_df.style.apply(highlight_row, axis=1),
             use_container_width=True, hide_index=True)

st.subheader("🕒 Upcoming Spreads")
st.dataframe(upcoming_spreads_df.style.apply(highlight_row, axis=1),
             use_container_width=True, hide_index=True)