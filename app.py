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

# Sport configurations
SPORTS_CONFIG = {
    "NBA": {
        "key": "basketball_nba",
        "half_minutes": 24,
        "halftime_min": 15,
        "total_real_time": 150
    },
    "NCAAB": {
        "key": "basketball_ncaab",
        "half_minutes": 20,
        "halftime_min": 15,
        "total_real_time": 140
    },
    "WNBA": {
        "key": "basketball_wnba",
        "half_minutes": 20,
        "halftime_min": 15,
        "total_real_time": 135
    }
}

st.set_page_config(page_title="DraftKings Sports Monitor", layout="wide")
st.title("🏀 DraftKings Sports Monitor")

# Initialize Supabase
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# Sport selector
selected_sport = st.selectbox("Select Sport", list(SPORTS_CONFIG.keys()) + ["Historical Data"])

if selected_sport == "Historical Data":
    st.subheader("📊 Historical Data Analysis")
    st.write("This section is under development. It will pull betting trends from the Supabase database.")
    
    # Placeholder for historical data features
    st.info("Coming Soon: Historical trends, drop statistics, and performance metrics")
    
else:
    sport_config = SPORTS_CONFIG[selected_sport]

def fetch_odds(sport_key):
    try:
        res = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
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

def get_game_from_db(game_id, sport):
    result = (
        supabase.table("odds_snapshot")
        .select("*")
        .eq("game_id", game_id)
        .eq("sport", sport)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None

def save_game_to_db(payload):
    supabase.table("odds_snapshot").upsert(payload).execute()

def estimate_game_time(commence_time_str, config):
    now = datetime.now(timezone.utc)
    commence_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
    elapsed_real_total = (now - commence_time).total_seconds() / 60
    
    half_game_minutes = config["half_minutes"]
    halftime_min = config["halftime_min"]
    total_real_time = config["total_real_time"]
    
    half_real_total = (total_real_time - halftime_min) / 2
    
    if elapsed_real_total < half_real_total:
        proportion = elapsed_real_total / half_real_total
        minutes_elapsed = proportion * half_game_minutes
        minutes_left = half_game_minutes - minutes_elapsed
        return f"1H — {minutes_left:.1f} min left"
    elif elapsed_real_total < half_real_total + halftime_min:
        return "HALFTIME"
    elif elapsed_real_total < 2 * half_real_total + halftime_min:
        elapsed_second_half = elapsed_real_total - (half_real_total + halftime_min)
        proportion = elapsed_second_half / half_real_total
        minutes_elapsed = proportion * half_game_minutes
        minutes_left = half_game_minutes - minutes_elapsed
        return f"2H — {minutes_left:.1f} min left"
    else:
        return "FINAL"

def get_color(drop):
    if drop >= 20:
        return "#ff4c4c"
    elif drop >= 15:
        return "#ffa500"
    elif drop >= 10:
        return "#ffff66"
    else:
        return "#ffffff"

if selected_sport != "Historical Data":
    placeholder = st.empty()

    while True:
        data = fetch_odds(sport_config["key"])
        
        if data:
            live_games = []
            upcoming_games = []
            now = datetime.now(timezone.utc)
            
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
                commence_time = game.get("commence_time")
                commence_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                
                # Get totals
                totals_market = next((m for m in dk_book.get("markets", []) if m["key"] == "totals"), None)
                spreads_market = next((m for m in dk_book.get("markets", []) if m["key"] == "spreads"), None)
                
                current_total = None
                current_spread = None
                
                if totals_market:
                    outcomes = totals_market.get("outcomes", [])
                    over_points = [o["point"] for o in outcomes if o["name"] == "Over"]
                    if over_points:
                        current_total = over_points[0]
                
                if spreads_market:
                    outcomes = spreads_market.get("outcomes", [])
                    if outcomes:
                        current_spread = outcomes[0]["point"]
                
                # Get or create game record
                db_game = get_game_from_db(g_id, selected_sport)
                
                if not db_game and now < commence_dt:
                    # Store pregame data for upcoming games
                    db_game = {
                        "game_id": g_id,
                        "sport": selected_sport,
                        "home_team": home,
                        "away_team": away,
                        "pregame_total": current_total,
                        "pregame_spread": current_spread,
                        "commence_time": commence_time,
                        "created_at": now.isoformat()
                    }
                    save_game_to_db(db_game)
                
                pregame_total = db_game["pregame_total"] if db_game else None
                pregame_spread = db_game["pregame_spread"] if db_game else None
                
                # Calculate drop
                drop = 0
                if pregame_total and current_total:
                    drop = pregame_total - current_total
                
                # Upcoming games
                if now < commence_dt:
                    est_time = commence_dt.astimezone(timezone(timedelta(hours=-5)))
                    upcoming_games.append({
                        "Matchup": f"{away} @ {home}",
                        "Pregame Total": int(pregame_total) if pregame_total else None,
                        "Current Total": int(current_total) if current_total else None,
                        "Pregame Spread": pregame_spread,
                        "Current Spread": current_spread,
                        "Start Time": est_time.strftime("%Y-%m-%d %I:%M %p")
                    })
                # Live games
                else:
                    time_status = estimate_game_time(commence_time, sport_config)
                    color = get_color(drop)
                    
                    live_games.append({
                        "Matchup": f"{away} @ {home}",
                        "Pregame Total": int(pregame_total) if pregame_total else None,
                        "Current Total": int(current_total) if current_total else None,
                        "Drop": int(drop) if drop else 0,
                        "Pregame Spread": pregame_spread,
                        "Current Spread": current_spread,
                        "Time Left": time_status,
                        "color": color
                    })
                    
                    # Update final score when game ends
                    if time_status == "FINAL" and db_game:
                        db_game["final_total"] = current_total
                        db_game["final_spread"] = current_spread
                        save_game_to_db(db_game)
            
            # Sort live games by drop
            live_games.sort(key=lambda x: x["Drop"], reverse=True)
            
            # Create tables
            with placeholder.container():
                st.subheader(f"📊 {selected_sport} - Upcoming Games")
                if upcoming_games:
                    df_upcoming = pd.DataFrame(upcoming_games)
                    st.dataframe(df_upcoming, hide_index=True, use_container_width=True)
                else:
                    st.write("No upcoming games")
                
                st.subheader(f"🔴 {selected_sport} - Live Games")
                if live_games:
                    # Create styled dataframe
                    df_live = pd.DataFrame(live_games)
                    colors = df_live.pop("color")
                    
                    def color_cells(row):
                        return [f"background-color: {colors[row.name]}"] * len(row)
                    
                    styled_df = df_live.style.apply(color_cells, axis=1)
                    st.dataframe(styled_df, hide_index=True, use_container_width=True)
                else:
                    st.write("No live games")
        
        else:
            st.write("No data available...")
        
        time.sleep(REFRESH_SECONDS)
