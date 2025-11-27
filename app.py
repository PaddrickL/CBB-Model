import requests
import streamlit as st
import time
import json
from datetime import datetime, timezone, timedelta

API_KEY = st.secrets["ODDS_API_KEY"]
SPORT = "basketball_ncaab"
REGIONS = "us"
ODDS_FORMAT = "american"
BOOKMAKER_KEY = "draftkings"

REFRESH_SECONDS = 30
API_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"

JSON_TOTALS_FILE = "pregame_totals.json"
FINAL_TOTALS_FILE = "final_totals.json"
JSON_SPREADS_FILE = "pregame_spreads.json"

# Game timing parameters
HALF_GAME_MINUTES = 20
HALFTIME_REAL_MIN = 20
TOTAL_REAL_TIME = 125

st.set_page_config(page_title="DraftKings NCAAB O/U & Spread Monitor", layout="wide")
st.title("🏀 DraftKings NCAAB O/U & Spread Monitor")
st.write("Highlights: 🟨 10+, 🟧 15+, 🟥 20+")

placeholder = st.empty()

# ------------------- Load JSONs -------------------
def load_json(file_name):
    try:
        with open(file_name, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file_name, data):
    with open(file_name, "w") as f:
        json.dump(data, f)

pregame_totals = load_json(JSON_TOTALS_FILE)
final_totals = load_json(FINAL_TOTALS_FILE)
pregame_spreads = load_json(JSON_SPREADS_FILE)

# ------------------- Helper functions -------------------
def fetch_odds():
    try:
        response = requests.get(
            API_URL,
            params={
                "apiKey": API_KEY,
                "regions": REGIONS,
                "markets": "totals,spreads",
                "oddsFormat": ODDS_FORMAT,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching API data: {e}")
        return None

def get_color(value):
    if value >= 20:
        return "#ff4c4c"
    elif value >= 15:
        return "#ffa500"
    elif value >= 10:
        return "#ffff66"
    else:
        return "#ffffff"

def estimate_game_time(commence_time_str):
    now = datetime.now(timezone.utc)
    commence_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
    elapsed_real_total = (now - commence_time).total_seconds() / 60

    HALF_REAL_TOTAL = (TOTAL_REAL_TIME - HALFTIME_REAL_MIN) / 2

    if elapsed_real_total < HALF_REAL_TOTAL:
        proportion = elapsed_real_total / HALF_REAL_TOTAL
        minutes_elapsed = proportion * HALF_GAME_MINUTES
        minutes_left = HALF_GAME_MINUTES - minutes_elapsed
        status = f"1H — {minutes_left:.1f} min left"
    elif elapsed_real_total < HALF_REAL_TOTAL + HALFTIME_REAL_MIN:
        status = "HALFTIME"
    elif elapsed_real_total < 2 * HALF_REAL_TOTAL + HALFTIME_REAL_MIN:
        elapsed_second_half = elapsed_real_total - (HALF_REAL_TOTAL + HALFTIME_REAL_MIN)
        proportion = elapsed_second_half / HALF_REAL_TOTAL
        minutes_elapsed = proportion * HALF_GAME_MINUTES
        minutes_left = HALF_GAME_MINUTES - minutes_elapsed
        status = f"2H — {minutes_left:.1f} min left"
    else:
        status = "FINAL"

    return status

def render_table(games, headers, live=True):
    table_html = "<div style='overflow-x:auto; margin-bottom:20px; width:100%;'>"
    table_html += "<table style='width:100%; min-width:600px; border-collapse: collapse; font-family:sans-serif; font-size:14px; border-radius:10px; overflow:hidden; box-shadow:0 2px 5px rgba(0,0,0,0.1);'>"

    # Header
    table_html += "<tr style='background-color:#4c6ef5; color:white; text-align:center; height:35px;'>"
    for h in headers:
        table_html += f"<th style='padding:6px;'>{h}</th>"
    table_html += "</tr>"

    # Rows
    for i, row in enumerate(games):
        bg = "#f0f2f6" if i % 2 == 0 else "#ffffff"
        if live:
            bg = row.get("color", bg)
        table_html += f"<tr style='text-align:center; height:35px; background-color:{bg};'>"
        for h in headers:
            value = row.get(h.lower(), "")
            table_html += f"<td style='padding:6px;'>{value}</td>"
        table_html += "</tr>"

    table_html += "</table></div>"
    return table_html

# ------------------- Main Loop -------------------
while True:
    data = fetch_odds()
    if data:
        live_totals = []
        upcoming_totals = []
        live_spreads = []
        upcoming_spreads = []

        now = datetime.now(timezone.utc)

        for game in data:
            g_id = str(game["id"])
            dk_book = next((b for b in game.get("bookmakers", []) if b["key"] == BOOKMAKER_KEY), None)
            if not dk_book:
                continue

            home = game["home_team"]
            away = game["away_team"]
            commence_time = game.get("commence_time")
            commence_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))

            # ----- Totals -----
            totals_market = next((m for m in dk_book.get("markets", []) if m["key"] == "totals"), None)
            if totals_market:
                outcomes = totals_market.get("outcomes", [])
                over_points = [o["point"] for o in outcomes if o["name"] == "Over"]
                if over_points:
                    current_total = over_points[0]
                    if g_id not in pregame_totals and now < commence_dt:
                        pregame_totals[g_id] = current_total
                        save_json(JSON_TOTALS_FILE, pregame_totals)
                    pregame_total = pregame_totals.get(g_id)
                    drop = pregame_total - current_total if pregame_total else 0
                    color = get_color(drop)

                    if now < commence_dt:
                        est_time = commence_dt.astimezone(timezone(timedelta(hours=-5)))
                        upcoming_totals.append({
                            "matchup": f"{away} @ {home}",
                            "pregame_total": pregame_total,
                            "current_total": current_total,
                            "start_time": est_time.strftime("%Y-%m-%d %I:%M %p")
                        })
                    else:
                        time_status = estimate_game_time(commence_time)
                        live_totals.append({
                            "matchup": f"{away} @ {home}",
                            "pregame": pregame_total,
                            "current": current_total,
                            "drop": drop,
                            "color": color,
                            "time_status": time_status
                        })
                        if time_status == "FINAL":
                            final_totals[g_id] = {
                                "pregame": pregame_total,
                                "drop_before_halftime": drop,
                                "final_total": current_total
                            }
                            save_json(FINAL_TOTALS_FILE, final_totals)

            # ----- Spreads -----
            spreads_market = next((m for m in dk_book.get("markets", []) if m["key"] == "spreads"), None)
            if spreads_market:
                outcomes = spreads_market.get("outcomes", [])
                home_spread = next((o["point"] for o in outcomes if o["name"] == home), None)
                if home_spread is not None:
                    if g_id not in pregame_spreads and now < commence_dt:
                        pregame_spreads[g_id] = home_spread
                        save_json(JSON_SPREADS_FILE, pregame_spreads)
                    pregame_spread = pregame_spreads.get(g_id)
                    shift = pregame_spread - home_spread if pregame_spread else 0
                    color = get_color(abs(shift))

                    if now < commence_dt:
                        upcoming_spreads.append({
                            "matchup": f"{away} @ {home}",
                            "pregame_spread": pregame_spread,
                            "current_spread": home_spread,
                            "start_time": commence_dt.astimezone(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %I:%M %p")
                        })
                    else:
                        time_status = estimate_game_time(commence_time)
                        live_spreads.append({
                            "matchup": f"{away} @ {home}",
                            "pregame": pregame_spread,
                            "current": home_spread,
                            "shift": shift,
                            "color": color,
                            "time_status": time_status
                        })

        # Sort live tables independently
        live_totals.sort(key=lambda x: x["drop"], reverse=True)
        live_spreads.sort(key=lambda x: abs(x["shift"]), reverse=True)

        # Render tables side by side
        html_totals = "<h3>Live Totals</h3>" + render_table(live_totals, ["Matchup", "Pregame", "Current", "Drop", "Time_Status"], live=True)
        html_upcoming_totals = "<h3>Upcoming Totals</h3>" + render_table(upcoming_totals, ["Matchup", "Pregame_Total", "Current_Total", "Start_Time"], live=False)
        html_spreads = "<h3>Live Spreads</h3>" + render_table(live_spreads, ["Matchup", "Pregame", "Current", "Shift", "Time_Status"], live=True)
        html_upcoming_spreads = "<h3>Upcoming Spreads</h3>" + render_table(upcoming_spreads, ["Matchup", "Pregame_Spread", "Current_Spread", "Start_Time"], live=False)

        combined_html = f"""
        <div style="display:flex; gap:20px;">
            <div style="flex:1">{html_totals + html_upcoming_totals}</div>
            <div style="flex:1">{html_spreads + html_upcoming_spreads}</div>
        </div>
        """
        placeholder.markdown(combined_html, unsafe_allow_html=True)

    else:
        st.write("No data available...")

    time.sleep(REFRESH_SECONDS)