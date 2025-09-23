from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import requests
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv
from openai import OpenAI  # ✅ modern SDK (openai>=1.0.0)

# ----------------------
# Setup
# ----------------------
load_dotenv()
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Required for flashing messages & sessions

# Initialize OpenAI client (reads OPENAI_API_KEY from env automatically)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  WARNING: OPENAI_API_KEY is not set in your environment (.env)")
client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------------
# Routes
# ----------------------
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Fake login for now
        if email == 'admin@pennocksystems.com' and password == 'BluePanda2025':
            session['user_email'] = email
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid credentials. Try again.'

    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        flash("Please log in first.")
        return redirect(url_for('login'))

    pelosi_stats = {}
    error_message = None

    try:
        url = "https://www.capitoltrades.com/politicians/P000197"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "StockAgent/1.0"})
        soup = BeautifulSoup(resp.text, "lxml")

        # --- Name & subtitle ---
        name_el = soup.find("h1")
        subtitle_el = soup.find("h2") or soup.find("p")
        pelosi_stats["name"] = name_el.get_text(strip=True) if name_el else "Nancy Pelosi"
        pelosi_stats["subtitle"] = subtitle_el.get_text(" / ", strip=True) if subtitle_el else "Democrat / House / California"

        # --- Extract stats from plain text (robust vs DOM changes) ---
        page_text = soup.get_text(" ", strip=True)

        def grab(pattern, default="—"):
            m = re.search(pattern, page_text, flags=re.I)
            return m.group(1).strip() if m else default

        pelosi_stats["trades"]       = grab(r'(\d+)\s+Trades\b')
        pelosi_stats["issuers"]      = grab(r'(\d+)\s+Issuers\b')
        pelosi_stats["volume"]       = grab(r'(\$?\d[\d.,]*\s*[KMB]?)\s+Volume\b')
        pelosi_stats["last_traded"]  = grab(r'(\d{4}-\d{2}-\d{2})\s+Last Traded\b')
        pelosi_stats["district"]     = grab(r'(\d+)\s+District\b')
        pelosi_stats["years_active"] = grab(r'(\d{4}\s*–\s*\d{4})\s+Years Active\b')
        pelosi_stats["dob"]          = grab(r'(\d{4}-\d{2}-\d{2})\s+Date of Birth\b')
        pelosi_stats["age"]          = grab(r'(\d+)\s+Age\b')

        # Debug to confirm clean values
        print("Parsed Pelosi Stats:", pelosi_stats)

    except Exception as e:
        error_message = f"Error fetching Pelosi profile stats: {e}"
        pelosi_stats = {"name": "Nancy Pelosi", "subtitle": "Democrat / House / California"}
        print("Dashboard scrape error:", e)

    if error_message:
        flash(error_message)

    return render_template(
        'dashboard.html',
        user_email=session['user_email'],
        stats=pelosi_stats
    )

@app.route('/reports')
def reports():
    if 'user_email' not in session:
        flash("Please log in first.")
        return redirect(url_for('login'))

    pelosi_trades = []
    error_message = None

    try:
        url = "https://www.capitoltrades.com/politicians/P000197"
        response = requests.get(url, timeout=20, headers={"User-Agent": "StockAgent/1.0"})
        soup = BeautifulSoup(response.text, "lxml")

        table = soup.find("table")
        if not table:
            error_message = "Could not find trade table on CapitolTrades."
        else:
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                cols = [c.get_text(strip=True) for c in row.find_all("td")]

                if len(cols) >= 6:
                    pelosi_trades.append({
                        "ticker": cols[0],     # Ticker
                        "action": cols[4],     # Buy/Sell
                        "time": cols[2],       # Transaction Date
                        "price": cols[5],      # Amount
                        "change": cols[1]      # Disclosure Date
                    })

    except Exception as e:
        error_message = f"Error fetching Pelosi trades: {e}"
        print("Reports scrape error:", e)

    if error_message:
        flash(error_message)

    return render_template(
        'reports.html',
        user_email=session['user_email'],
        reports=pelosi_trades
    )

@app.route('/raw_reports_capitol')
def raw_reports_capitol():
    """Debug endpoint: fetch raw HTML snippet of Pelosi's page."""
    try:
        url = "https://www.capitoltrades.com/politicians/P000197"
        response = requests.get(url, timeout=20, headers={"User-Agent": "StockAgent/1.0"})
        return response.text
    except Exception as e:
        return f"<pre>Error: {e}</pre>"

@app.route('/agent')
def agent():
    if 'user_email' not in session:
        flash("Please log in first.")
        return redirect(url_for('login'))

    return render_template('agent.html', user_email=session['user_email'])

@app.route('/agent_chat', methods=['POST'])
def agent_chat():
    if 'user_email' not in session:
        return jsonify({"reply": "Please log in first."}), 401

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    if not OPENAI_API_KEY:
        # Return a friendly error instead of crashing the route
        return jsonify({"reply": "OpenAI API key is missing. Set OPENAI_API_KEY in your .env."}), 500

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",  # or "gpt-4o" for more advanced reasoning
            messages=[
                {"role": "system", "content": (
                    "You are TickerBot 📈, a helpful assistant that educates users "
                    "on stock market trends, reports, and financial concepts. "
                    "You are not a financial advisor and should remind users to "
                    "consult professionals before trading."
                )},
                {"role": "user", "content": user_message},
            ]
        )
        reply = completion.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        # Log the exception and return a controlled error so fetch() doesn't hard-crash
        print("OpenAI error:", e)
        return jsonify({"reply": f"⚠️ Error connecting to OpenAI: {e}"}), 502

@app.route('/profile')
def profile():
    if 'user_email' not in session:
        flash("Please log in first.")
        return redirect(url_for('login'))

    return render_template('profile.html', user_email=session['user_email'])

@app.route('/signup')
def signup():
    return "<h1>Signup page coming soon!</h1>"

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    flash("You have been signed out.")
    return redirect(url_for('login'))

# Optional: simple health check
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(debug=True)
