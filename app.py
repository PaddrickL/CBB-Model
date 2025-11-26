import requests
import streamlit as st
import time
import json
from datetime import datetime, timezone, timedelta

API_KEY = st.secrets["ODDS_API_KEY"]
SPORT = "basketball_ncaab"
REGIONS = "us"
MARKETS = "totals"
ODDS_FORMAT = "american"
BOOKMAKER_KEY = "draftkings"

REFRESH_SECONDS = 30
API_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"
JSON_FILE = "pregame_totals.json"
FINAL_FILE = "final_totals.json"

# Game timing parameters
HALF_GAME_MINUTES = 20
HALFTIME_REAL_MIN = 20
TV_TIMEOUTS_PER_HALF = 5
TV_TIMEOUT_LENGTH = 2      # minutes real time
TOTAL_REAL_TIME = 125      # total game including halftime

st.set_page_config(page_title="DraftKings NCAAB O/U Drop Monitor", layout="wide")
st.title("🏀 DraftKings NCAAB O/U Drop Monitor")
st.write("Highlights: 🟨 10+, 🟧 15+, 🟥 20+")

placeholder = st.empty()

# Load pregame totals
try:
    with open(JSON_FILE, "r") as f:
        pregame_totals = json.load(f)
except:
    pregame_totals = {}

# Load final totals for stats
try:
    with open(FINAL_FILE, "r") as f:
        final_totals = json.load(f)
except:
    final_totals = {}

def save_pregame_totals():
    with open(JSON_FILE, "w") as f:
        json.dump(pregame_totals, f)

def save_final_totals():
    with open(FINAL_FILE, "w") as f:
        json.dump(final_totals, f)

def fetch_odds():
    try:
        response = requests.get(
            API_URL,
            params={
                "apiKey": API_KEY,
                "regions": REGIONS,
                "markets": MARKETS,
                "oddsFormat": ODDS_FORMAT,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching API data: {e}")
        return None

def get_color(drop):
    if drop >= 20:
        return "#ff4c4c"  # red
    elif drop >= 15:
        return "#ffa500"  # orange
    elif drop >= 10:
        return "#ffff66"  # yellow
    else:
        return "#ffffff"  # white

def estimate_game_time(commence_time_str):
    now = datetime.now(timezone.utc)
    commence_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
    elapsed_real_total = (now - commence_time).total_seconds() / 60  # minutes

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

def calculate_drop_stats(final_totals, margin=7):
    stats = {"10+": {"within":0, "total":0},
             "15+": {"within":0, "total":0},
             "20+": {"within":0, "total":0}}
    
    for g_id, g in final_totals.items():
        pregame = g["pregame"]
        drop = g["drop_before_halftime"]
        final_total = g["final_total"]
        if drop >= 10:
            stats["10+"]["total"] += 1
            if abs(final_total - pregame) <= margin:
                stats["10+"]["within"] += 1
        if drop >= 15:
            stats["15+"]["total"] += 1
            if abs(final_total - pregame) <= margin:
                stats["15+"]["within"] += 1
        if drop >= 20:
            stats["20+"]["total"] += 1
            if abs(final_total - pregame) <= margin:
                stats["20+"]["within"] += 1
    
    for k in stats:
        if stats[k]["total"] > 0:
            stats[k]["percent"] = round(100 * stats[k]["within"] / stats[k]["total"], 1)
        else:
            stats[k]["percent"] = None
    return stats

def render_table(games, headers, live=True):
    table_html = "<div style='overflow-x:auto; margin-bottom:20px; width:100%;'>"
    table_html += "<table style='width:100%; min-width:600px; border-collapse: collapse; font-family:sans-serif; font-size:14px; border-radius:10px; overflow:hidden; box-shadow:0 2px 5px rgba(0,0,0,0.1);'>"

    # Table header
    table_html += "<tr style='background-color:#4c6ef5; color:white; text-align:center; height:35px;'>"
    for h in headers:
        table_html += f"<th style='padding:6px;'>{h}</th>"
    table_html += "</tr>"

    # Table rows
    for i, row in enumerate(games):
        bg = "#f0f2f6" if i % 2 == 0 else "#ffffff"
        if live:
            bg = row["color"]
        table_html += f"<tr style='text-align:center; height:35px; background-color:{bg};'>"
        for h in headers:
            value = row.get(h.lower(), '')
            table_html += f"<td style='padding:6px;'>{value}</td>"
        table_html += "</tr>"

    table_html += "</table></div>"
    return table_html

while True:
    data = fetch_odds()
    if data:
        live_games = []
        upcoming_games = []

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

            totals_market = next((m for m in dk_book.get("markets", []) if m["key"] == "totals"), None)
            if not totals_market:
                continue
            outcomes = totals_market.get("outcomes", [])
            over_points = [o["point"] for o in outcomes if o["name"] == "Over"]
            if not over_points:
                continue
            current_total = over_points[0]

            # Store pregame total if game hasn't started
            if g_id not in pregame_totals and now < commence_dt:
                pregame_totals[g_id] = current_total
                save_pregame_totals()

            pregame_total = pregame_totals.get(g_id)
            drop = pregame_total - current_total if pregame_total else 0
            color = get_color(drop)

            # Skip live games with N/A drop
            if drop is None and now >= commence_dt:
                continue

            # Upcoming games
            if now < commence_dt:
                est_time = commence_dt.astimezone(timezone(timedelta(hours=-5)))  # EST
                start_str = est_time.strftime("%Y-%m-%d %I:%M %p")
                upcoming_games.append({
                    "matchup": f"{away} @ {home}",
                    "pregame_total": pregame_total,
                    "current_total": current_total,
                    "start_time": start_str
                })
            # Live games
            else:
                time_status = estimate_game_time(commence_time)
                live_games.append({
                    "matchup": f"{away} @ {home}",
                    "pregame": pregame_total,
                    "current": current_total,
                    "drop": drop,
                    "color": color,
                    "time_status": time_status
                })

                # Store final totals when game ends
                if time_status == "FINAL":
                    final_totals[g_id] = {
                        "pregame": pregame_total,
                        "drop_before_halftime": drop,
                        "final_total": current_total
                    }
                    save_final_totals()

        live_games.sort(key=lambda x: x["drop"], reverse=True)

        html_live = "<h3>Live Games</h3>" + render_table(live_games, ["Matchup", "Pregame", "Current", "Drop", "Time_Status"], live=True)
        html_upcoming = "<h3>Upcoming Games</h3>" + render_table(upcoming_games, ["Matchup", "Pregame_Total", "Current_Total", "Start_Time"], live=False)

        stats = calculate_drop_stats(final_totals, margin=7)
        stats_html = "<h3>Historical % within 7 points (final)</h3>"
        for k in ["10+", "15+", "20+"]:
            val = stats[k]["percent"]
            stats_html += f"<p>{k} drop: {val if val is not None else 'N/A'}%</p>"

        placeholder.markdown(html_live + "<br><br>" + html_upcoming + "<br><br>" + stats_html, unsafe_allow_html=True)

    else:
        st.write("No data available...")

    time.sleep(REFRESH_SECONDS)
