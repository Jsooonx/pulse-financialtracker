"""Pulse - Personal Finance Intelligence Web App."""

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file, Response
import pandas as pd
from io import BytesIO, StringIO
import sqlite3
import os
from datetime import datetime, date
import intelligence
from dotenv import load_dotenv
from supabase import create_client, Client
import jwt
import json
from telegram import Update
import bot


load_dotenv()

app = Flask(__name__)
app.secret_key = "pulse-secret-key-change-in-production"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

@app.context_processor
def inject_supabase():
    return dict(SUPABASE_URL=SUPABASE_URL, SUPABASE_KEY=SUPABASE_KEY, now=datetime.now())


def get_supabase() -> Client:
    """Initialize Supabase client using the auth token from cookies."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Get the token from cookie
    access_token = request.cookies.get('sb-access-token')
    refresh_token = request.cookies.get('sb-refresh-token')
    
    if access_token:
        # Pass the user's session to the python client so RLS works
        supabase.auth.set_session(access_token, refresh_token)
        
    return supabase

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pulse.db")

EXPENSE_CATEGORIES = [
    {"id": "food", "label": "Food", "icon": "🍽️", "color": "#FF6B6B"},
    {"id": "transport", "label": "Transport", "icon": "🚗", "color": "#4ECDC4"},
    {"id": "bills", "label": "Bills & Utilities", "icon": "📄", "color": "#45B7D1"},
    {"id": "entertainment", "label": "Entertainment", "icon": "🎮", "color": "#96CEB4"},
    {"id": "shopping", "label": "Shopping", "icon": "🛒", "color": "#FFEAA7"},
    {"id": "health", "label": "Health", "icon": "💊", "color": "#DDA0DD"},
    {"id": "education", "label": "Education", "icon": "📚", "color": "#74B9FF"},
    {"id": "others", "label": "Others", "icon": "📦", "color": "#B2BEC3"},
]

CATEGORY_MAP = {c["id"]: c for c in EXPENSE_CATEGORIES}


# Use /tmp for SQLite on Vercel
if os.environ.get('VERCEL'):
    USER_DBS_DIR = '/tmp/user_dbs'
else:
    USER_DBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_dbs")

os.makedirs(USER_DBS_DIR, exist_ok=True)

def get_db():
    """Get per-user database connection with row factory. Syncs from Supabase if new."""
    user_id = "guest"
    token = request.cookies.get('sb-access-token')
    if token:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub", "guest")
        except:
            pass
            
    db_path = os.path.join(USER_DBS_DIR, f"pulse_{user_id}.db")
    needs_sync = not os.path.exists(db_path)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    
    if needs_sync:
        init_db(conn)
        sync_from_supabase(conn)
        
    return conn

def sync_from_supabase(conn):
    """Downloads all user data from Supabase and populates the local SQLite cache."""
    try:
        supabase = get_supabase()
        
        # Sync Settings
        settings = supabase.table('settings').select('*').execute()
        for row in settings.data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (row['key'], row['value']))
            
        # Sync Income
        income = supabase.table('income').select('*').execute()
        for row in income.data:
            conn.execute("INSERT OR REPLACE INTO income (id, amount, source, month, year, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (row['id'], row['amount'], row['source'], row['month'], row['year'], row['note'], row['created_at']))
                         
        # Sync Expense
        expense = supabase.table('expense').select('*').execute()
        for row in expense.data:
            conn.execute("INSERT OR REPLACE INTO expense (id, amount, category, description, date, note, is_recurring, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (row['id'], row['amount'], row['category'], row['description'], row['date'], row['note'], row['is_recurring'], row['created_at']))
                         
        # Sync Budget
        budget = supabase.table('budget').select('*').execute()
        for row in budget.data:
            conn.execute("INSERT OR REPLACE INTO budget (id, category, amount, month, year) VALUES (?, ?, ?, ?, ?)",
                         (row['id'], row['category'], row['amount'], row['month'], row['year']))
                         
        # Sync Drafts
        drafts = supabase.table('drafts').select('*').execute()
        for row in drafts.data:
            conn.execute("INSERT OR REPLACE INTO drafts (id, amount, description, date, category, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (row['id'], row['amount'], row['description'], row['date'], row['category'], row['source'], row['created_at']))
        
        conn.commit()
    except Exception as e:
        print("Error syncing from Supabase:", e)

def init_db(conn=None):
    """Initialize database tables."""
    close_after = False
    if conn is None:
        # Fallback for manual seed scripts
        db_path = os.path.join(USER_DBS_DIR, "pulse_guest.db")
        conn = sqlite3.connect(db_path)
        close_after = True
        
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'Salary',
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, month, year)
        );

        CREATE TABLE IF NOT EXISTS expense (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            note TEXT,
            is_recurring BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            UNIQUE(category, month, year)
        );

        CREATE TABLE IF NOT EXISTS recurring_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            day_of_month INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            category TEXT,
            source TEXT DEFAULT 'telegram',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Insert default settings if not exists
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('currency', 'USD')")
    conn.commit()
    if close_after:
        conn.close()


CURRENCY_RATES = {
    "USD": 1.0,
    "EUR": 0.86,
    "IDR": 17000.0
}


def get_setting(key, default=None):
    """Get a setting value from the database."""
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    """Set a setting value in the database."""
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def format_currency(value):
    """Format number as currency based on settings and rates."""
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    
    if value is None:
        value = 0
    
    converted_value = value * rate
    
    if currency == "IDR":
        return f"Rp{converted_value:,.0f}".replace(",", ".")
    elif currency == "EUR":
        return f"€{converted_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else: # USD
        return f"${converted_value:,.2f}"


# Register Jinja2 filters
app.jinja_env.filters["currency"] = format_currency


@app.context_processor
def inject_now():
    """Inject current datetime and supabase config into all templates."""
    return {
        "now": datetime.utcnow(),
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY
    }


# --- Dashboard ---
@app.route("/")
def dashboard():
    """Main dashboard with summary cards and charts."""
    conn = get_db()

    now = date.today()
    current_month = request.args.get("month", now.month, type=int)
    current_year = request.args.get("year", now.year, type=int)

    # Process Recurring rules for current month/year if we view the current month or past? 
    # Just a simple run on current month view.
    if current_month == now.month and current_year == now.year:
        intelligence.process_recurring(conn, now)

    # Net Worth Calculation (All time)
    total_historical_income = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM income").fetchone()["total"]
    total_historical_expense = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM expense").fetchone()["total"]
    net_worth = total_historical_income - total_historical_expense

    # Target previous month for MoM comparison
    prev_m = 12 if current_month == 1 else current_month - 1
    prev_y = current_year - 1 if current_month == 1 else current_year

    # Total income for this month
    income_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE month = ? AND year = ?",
        (current_month, current_year),
    ).fetchone()
    total_income = income_row["total"]

    # Total expense for this month
    expense_row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total FROM expense
           WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?""",
        (f"{current_month:02d}", str(current_year)),
    ).fetchone()
    total_expense = expense_row["total"]

    # Previous month data for MoM
    prev_income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE month = ? AND year = ?",
        (prev_m, prev_y),
    ).fetchone()["total"]
    
    prev_expense = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total FROM expense
           WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?""",
        (f"{prev_m:02d}", str(prev_y)),
    ).fetchone()["total"]

    mom_income = ((total_income - prev_income) / prev_income * 100) if prev_income > 0 else 0
    mom_expense = ((total_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else 0

    balance = total_income - total_expense

    # Expenses grouped by category
    categories_data = conn.execute(
        """SELECT category, SUM(amount) as total, COUNT(*) as count FROM expense
           WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
           GROUP BY category ORDER BY total DESC""",
        (f"{current_month:02d}", str(current_year)),
    ).fetchall()

    # Recent transactions (latest 10)
    recent_transactions = conn.execute(
        """SELECT * FROM expense ORDER BY date DESC, created_at DESC LIMIT 10"""
    ).fetchall()

    # Draft transactions (unreviewed)
    drafts = conn.execute(
        "SELECT * FROM drafts ORDER BY created_at DESC"
    ).fetchall()
    
    # Process drafts for display (apply currency rates)
    processed_drafts = []
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    for d in drafts:
        pd = dict(d)
        pd["amount_display"] = pd["amount"] * rate
        processed_drafts.append(pd)

    # Income entries for this month
    income_entries = conn.execute(
        "SELECT * FROM income WHERE month = ? AND year = ? ORDER BY created_at DESC",
        (current_month, current_year),
    ).fetchall()

    # Build chart data
    chart_labels = []
    chart_amounts = []
    chart_colors = []
    category_details = []

    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)

    # Fetch budgets for this period
    budget_rows = conn.execute(
        "SELECT category, amount FROM budget WHERE month = ? AND year = ?",
        (current_month, current_year)
    ).fetchall()
    budget_map = {b["category"]: b["amount"] for b in budget_rows}

    for row in categories_data:
        cat_id = row["category"]
        cat_config = CATEGORY_MAP.get(cat_id, {"label": cat_id, "icon": "📦", "color": "#B2BEC3"})
        
        budget_amt = budget_map.get(cat_id, 0)
        budget_usage_pct = (row["total"] / budget_amt * 100) if budget_amt > 0 else 0
        
        chart_labels.append(cat_config["label"])
        chart_amounts.append(row["total"] * rate)
        chart_colors.append(cat_config["color"])
        
        category_details.append({
            "id": cat_id,
            "label": cat_config["label"],
            "icon": cat_config["icon"],
            "color": cat_config["color"],
            "total": row["total"],
            "count": row["count"],
            "percentage": (row["total"] / total_expense * 100) if total_expense > 0 else 0,
            "budget": budget_amt,
            "budget_usage_pct": budget_usage_pct
        })

    # Available months for navigation
    available_months = conn.execute(
        """SELECT DISTINCT
               CAST(strftime('%m', date) AS INTEGER) as month,
               CAST(strftime('%Y', date) AS INTEGER) as year
           FROM expense
           UNION
           SELECT month, year FROM income
           ORDER BY year DESC, month DESC"""
    ).fetchall()

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    # 6-Month Trend Data
    trend_labels = []
    trend_income = []
    trend_expense = []
    
    y, m = current_year, current_month
    for _ in range(6):
        month_label = f"{month_names[m][:3]} '{str(y)[-2:]}"
        trend_labels.insert(0, month_label)
        
        inc_val = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE month = ? AND year = ?", (m, y)).fetchone()["total"]
        exp_val = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM expense WHERE CAST(strftime('%m', date) AS INTEGER) = ? AND CAST(strftime('%Y', date) AS INTEGER) = ?", (m, y)).fetchone()["total"]
        
        trend_income.insert(0, inc_val * rate)
        trend_expense.insert(0, exp_val * rate)
        
        m -= 1
        if m == 0:
            m = 12
            y -= 1
            
    # --- Intelligence Layer ---
    category_totals_dict = {row["category"]: row["total"] for row in categories_data}
    
    # Calculate 50/30/20 Score
    financial_score = intelligence.evaluate_50_30_20(total_income, category_totals_dict)
    
    # Get dynamic insights
    curr = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(curr, 1.0)
    symbol = "Rp" if curr == "IDR" else "€" if curr == "EUR" else "$"
    insights = intelligence.generate_dynamic_insights(conn, total_income, category_totals_dict, current_month, current_year, symbol, rate)
    
    # Detect Anomalies
    anomalies = intelligence.detect_anomalies(conn, current_month, current_year)
    anomaly_tx_ids = [a["tx"]["id"] for a in anomalies]
    
    # Add anomaly info to recent transactions
    recent_transactions_with_anomalies = []
    for tx in recent_transactions:
        tx_dict = dict(tx)
        tx_dict["is_anomaly"] = tx["id"] in anomaly_tx_ids
        for a in anomalies:
            if a["tx"]["id"] == tx["id"]:
                tx_dict["anomaly_details"] = a
        recent_transactions_with_anomalies.append(tx_dict)

    # Sankey Diagram Data (Flow from Income -> Current Balance / Expenses)
    # Define flows: [Source, Target, Value]
    sankey_data = []
    if total_income > 0:
        # Group income by source
        for inc in income_entries:
            sankey_data.append([inc["source"], "Total Budget", inc["amount"]])
            
        for cat in categories_data:
            sankey_data.append(["Total Budget", CATEGORY_MAP.get(cat["category"], {"label": cat["category"]})["label"], cat["total"]])
            
        if balance > 0:
            sankey_data.append(["Total Budget", "Savings/Balance", balance])

    conn.close()

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    return render_template(
        "dashboard.html",
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        category_details=category_details,
        recent_transactions=recent_transactions_with_anomalies,
        income_entries=income_entries,
        chart_labels=chart_labels,
        chart_amounts=chart_amounts,
        chart_colors=chart_colors,
        current_month=current_month,
        current_year=current_year,
        month_name=month_names[current_month],
        available_months=available_months,
        month_names=month_names,
        categories=EXPENSE_CATEGORIES,
        category_map=CATEGORY_MAP,
        financial_score=financial_score,
        insights=insights,
        net_worth=net_worth,
        mom_income=mom_income,
        mom_expense=mom_expense,
        sankey_data=sankey_data,
        trend_labels=trend_labels,
        trend_income=trend_income,
        trend_expense=trend_expense,
        drafts=processed_drafts,
        current_currency=get_setting("currency", "USD"),
        budgets=budget_rows,
        budget_map=budget_map,
        currency_rates=CURRENCY_RATES
    )


@app.route("/budget/upsert", methods=["POST"])
def upsert_budget():
    """Create or update a monthly budget for a category."""
    category = request.form.get("category", "").strip()
    amount = request.form.get("amount", type=float)
    month = request.form.get("month", type=int)
    year = request.form.get("year", type=int)

    if not category or amount is None:
        flash("Category and amount are required.", "error")
        return redirect(url_for("dashboard", month=month, year=year))

    # Convert to USD base
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    conn = get_db()
    conn.execute(
        """INSERT INTO budget (category, amount, month, year) VALUES (?, ?, ?, ?)
           ON CONFLICT(category, month, year) DO UPDATE SET amount = EXCLUDED.amount""",
        (category, usd_amount, month, year),
    )
    conn.commit()
    conn.close()

    flash(f"Budget updated for {category.title()}!", "success")
    return redirect(url_for("dashboard", month=month, year=year))


@app.route("/settings/currency", methods=["POST"])
def update_currency():
    """Update preferred currency."""
    currency = request.form.get("currency", "USD")
    if currency in ["USD", "EUR", "IDR"]:
        set_setting("currency", currency)
        flash(f"Currency changed to {currency}", "success")
    
    return redirect(request.referrer or url_for("dashboard"))


# --- Income CRUD ---
@app.route("/income/add", methods=["POST"])
def add_income():
    """Add new income entry."""
    amount = request.form.get("amount", type=float)
    source = request.form.get("source", "Salary").strip()
    month = request.form.get("month", type=int)
    year = request.form.get("year", type=int)
    note = request.form.get("note", "").strip()

    if not amount or amount <= 0:
        flash("Income amount must be greater than 0.", "error")
        return redirect(url_for("dashboard", month=month, year=year))

    # Convert to USD base
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    try:
        supabase = get_supabase()
        try:
            supabase.table('income').insert({
                'amount': usd_amount,
                'source': source,
                'month': month,
                'year': year,
                'note': note
            }).execute()
        except Exception as e:
            # If unique constraint violated, manually do additive update
            if "duplicate key" in str(e) or "23505" in str(e):
                existing = supabase.table('income').select('*').eq('source', source).eq('month', month).eq('year', year).execute()
                if existing.data:
                    old_amount = existing.data[0]['amount']
                    old_note = existing.data[0].get('note') or ''
                    new_note = f"{old_note}\n{note}" if old_note else note
                    
                    supabase.table('income').update({
                        'amount': old_amount + usd_amount,
                        'note': new_note
                    }).eq('id', existing.data[0]['id']).execute()

        # Local SQLite dual-write
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO income (amount, source, month, year, note) VALUES (?, ?, ?, ?, ?)",
                (usd_amount, source, month, year, note),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE income SET amount = amount + ?, note = COALESCE(note, '') || '\n' || ? WHERE source = ? AND month = ? AND year = ?",
                (usd_amount, note, source, month, year),
            )
            conn.commit()
        finally:
            conn.close()

        flash("Income added to Supabase & Local successfully!", "success")
    except Exception as e:
        flash(f"Error adding income: {str(e)}", "error")

    return redirect(url_for("dashboard", month=month, year=year))


@app.route("/income/delete/<int:income_id>", methods=["POST"])
def delete_income(income_id):
    """Delete income entry."""
    try:
        supabase = get_supabase()
        supabase.table('income').delete().eq('id', income_id).execute()
        
        # Local SQLite dual-write
        conn = get_db()
        row = conn.execute("SELECT month, year FROM income WHERE id = ?", (income_id,)).fetchone()
        month, year = (row["month"], row["year"]) if row else (date.today().month, date.today().year)
        conn.execute("DELETE FROM income WHERE id = ?", (income_id,))
        conn.commit()
        conn.close()
        
        flash("Income deleted from Supabase & Local.", "success")
    except Exception as e:
        flash(f"Error deleting income: {str(e)}", "error")
        month, year = date.today().month, date.today().year
        
    return redirect(url_for("dashboard", month=month, year=year))

# --- Telegram Link ---
@app.route("/link-telegram")
def link_telegram():
    """Link a Telegram Chat ID to the current Supabase Account."""
    chat_id = request.args.get("chat_id")
    if not chat_id:
        return render_template("link_telegram.html", status="error", title="Invalid Link", message="Missing Telegram Chat ID. Please click the link directly from the bot."), 400
        
    # Check if user is logged in
    token = request.cookies.get('sb-access-token')
    if not token:
        # Save chat_id in session/cookie and show a beautiful login required page
        response = render_template("link_telegram.html", status="login_required", title="Authentication Required", message="We need to securely connect your Telegram to your Pulse Cloud.")
        res = Response(response)
        res.set_cookie("pending_telegram_link", chat_id, max_age=3600)
        return res
        
    try:
        supabase = get_supabase()
        # Save chat_id to user settings in Supabase
        supabase.table('settings').upsert({
            'key': 'telegram_chat_id',
            'value': str(chat_id)
        }).execute()
        
        # Save locally
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('telegram_chat_id', str(chat_id)))
        conn.commit()
        conn.close()
        
        # Notify the user on Telegram
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if bot_token:
            import requests
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "🎉 *Account linked successfully!*\n\nType /help to learn about all the commands you can use.",
                        "parse_mode": "Markdown"
                    },
                    timeout=5
                )
            except Exception as e:
                print(f"Failed to send Telegram notification: {e}")
        
        return render_template("link_telegram.html", status="success", title="Account Linked", message=f"Telegram device ({chat_id}) is now connected to your Pulse account.")
    except Exception as e:
        return render_template("link_telegram.html", status="error", title="Link Failed", message=f"An error occurred: {str(e)}"), 500


# --- Expense CRUD ---
@app.route("/expense/add", methods=["POST"])
def add_expense():
    """Add new expense transaction."""
    amount = request.form.get("amount", type=float)
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    expense_date = request.form.get("date", "").strip()
    note = request.form.get("note", "").strip()

    if not amount or amount <= 0:
        flash("Expense amount must be greater than 0.", "error")
        return redirect(url_for("dashboard"))

    if not description:
        flash("Description cannot be empty.", "error")
        return redirect(url_for("dashboard"))

    if not expense_date:
        expense_date = date.today().isoformat()

    # Convert to USD base
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    try:
        supabase = get_supabase()
        supabase.table('expense').insert({
            'amount': usd_amount,
            'category': category,
            'description': description,
            'date': expense_date,
            'note': note
        }).execute()
        
        # We also need to keep the SQLite one for now so the dashboard doesn't break
        # (This is temporary until we migrate the dashboard queries)
        conn = get_db()
        conn.execute(
            "INSERT INTO expense (amount, category, description, date, note) VALUES (?, ?, ?, ?, ?)",
            (usd_amount, category, description, expense_date, note),
        )
        conn.commit()
        conn.close()
        
        flash("Expense added to Supabase (and local SQLite for preview)!", "success")
    except Exception as e:
        flash(f"Error adding expense: {str(e)}", "error")

    parsed_date = datetime.strptime(expense_date, "%Y-%m-%d")
    flash("Expense added successfully!", "success")
    return redirect(url_for("dashboard", month=parsed_date.month, year=parsed_date.year))


@app.route("/expense/edit/<int:expense_id>", methods=["POST"])
def edit_expense(expense_id):
    """Edit existing expense transaction."""
    amount = request.form.get("amount", type=float)
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    expense_date = request.form.get("date", "").strip()
    note = request.form.get("note", "").strip()

    # Convert to USD base
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    try:
        supabase = get_supabase()
        supabase.table('expense').update({
            'amount': usd_amount,
            'category': category,
            'description': description,
            'date': expense_date,
            'note': note
        }).eq('id', expense_id).execute()

        # Local SQLite dual-write
        conn = get_db()
        conn.execute(
            """UPDATE expense SET amount = ?, category = ?, description = ?, date = ?, note = ?
               WHERE id = ?""",
            (usd_amount, category, description, expense_date, note, expense_id),
        )
        conn.commit()
        conn.close()
        
        flash("Expense updated in Supabase & Local!", "success")
    except Exception as e:
        flash(f"Error updating expense: {str(e)}", "error")

    parsed_date = datetime.strptime(expense_date, "%Y-%m-%d")
    return redirect(url_for("dashboard", month=parsed_date.month, year=parsed_date.year))


@app.route("/expense/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    """Delete expense transaction."""
    try:
        supabase = get_supabase()
        supabase.table('expense').delete().eq('id', expense_id).execute()

        # Local SQLite dual-write
        conn = get_db()
        row = conn.execute("SELECT date FROM expense WHERE id = ?", (expense_id,)).fetchone()
        if row:
            parsed_date = datetime.strptime(row["date"], "%Y-%m-%d")
            month, year = parsed_date.month, parsed_date.year
        else:
            month, year = date.today().month, date.today().year
        conn.execute("DELETE FROM expense WHERE id = ?", (expense_id,))
        conn.commit()
        conn.close()
        
        flash("Expense deleted from Supabase & Local.", "success")
    except Exception as e:
        flash(f"Error deleting expense: {str(e)}", "error")
        month, year = date.today().month, date.today().year
        
    return redirect(url_for("dashboard", month=month, year=year))

@app.route("/api/load-dummy-data", methods=["POST"])
def load_dummy_data():
    """Loads dummy data into Supabase and resets local cache."""
    try:
        supabase = get_supabase()
        
        # Insert Income
        supabase.table('income').insert([
            {'amount': 5000, 'source': 'Salary', 'month': date.today().month, 'year': date.today().year},
            {'amount': 1500, 'source': 'Freelance', 'month': date.today().month, 'year': date.today().year}
        ]).execute()
        
        # Insert Expense
        supabase.table('expense').insert([
            {'amount': 50, 'category': 'food', 'description': 'Groceries', 'date': date.today().isoformat()},
            {'amount': 150, 'category': 'utilities', 'description': 'Electricity Bill', 'date': date.today().isoformat()},
            {'amount': 800, 'category': 'housing', 'description': 'Rent', 'date': date.today().isoformat()},
            {'amount': 120, 'category': 'entertainment', 'description': 'Netflix & Spotify', 'date': date.today().isoformat()}
        ]).execute()
        
        # Delete local DB so it resyncs on next load
        user_id = "guest"
        token = request.cookies.get('sb-access-token')
        if token:
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = payload.get("sub", "guest")
            except:
                pass
        db_path = os.path.join(USER_DBS_DIR, f"pulse_{user_id}.db")
        if os.path.exists(db_path):
            os.remove(db_path)
            
        flash("Dummy data loaded successfully! Local cache resynced.", "success")
    except Exception as e:
        flash(f"Error loading dummy data: {str(e)}", "error")
        
    return redirect(url_for("dashboard"))


# --- Category Drill-down ---
@app.route("/category/<category_id>")
def category_detail(category_id):
    """View all transactions for a specific category."""
    conn = get_db()

    now = date.today()
    current_month = request.args.get("month", now.month, type=int)
    current_year = request.args.get("year", now.year, type=int)

    transactions = conn.execute(
        """SELECT * FROM expense
           WHERE category = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?
           ORDER BY date DESC, created_at DESC""",
        (category_id, f"{current_month:02d}", str(current_year)),
    ).fetchall()

    total = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total FROM expense
           WHERE category = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?""",
        (category_id, f"{current_month:02d}", str(current_year)),
    ).fetchone()["total"]

    conn.close()

    cat = CATEGORY_MAP.get(category_id, {"label": category_id, "icon": "📦", "color": "#B2BEC3"})

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    return render_template(
        "category.html",
        category=cat,
        category_id=category_id,
        transactions=transactions,
        total=total,
        current_month=current_month,
        current_year=current_year,
        month_name=month_names[current_month],
        categories=EXPENSE_CATEGORIES,
        category_map=CATEGORY_MAP,
        current_currency=get_setting("currency", "USD")
    )


# --- All Transactions ---
@app.route("/transactions")
def all_transactions():
    """View all transactions for a specific month/year."""
    conn = get_db()

    now = date.today()
    current_month = request.args.get("month", now.month, type=int)
    current_year = request.args.get("year", now.year, type=int)

    transactions = conn.execute(
        """SELECT * FROM expense
           WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
           ORDER BY date DESC, created_at DESC""",
        (f"{current_month:02d}", str(current_year)),
    ).fetchall()

    total = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as total FROM expense
           WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?""",
        (f"{current_month:02d}", str(current_year)),
    ).fetchone()["total"]

    conn.close()

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    return render_template(
        "transactions.html",
        transactions=transactions,
        total=total,
        current_month=current_month,
        current_year=current_year,
        month_name=month_names[current_month],
        categories=EXPENSE_CATEGORIES,
        category_map=CATEGORY_MAP,
        current_currency=get_setting("currency", "USD")
    )


# --- API Endpoints ---
@app.route("/api/expense/<int:expense_id>")
def api_get_expense(expense_id):
    """Get single expense as JSON for edit modal, converted to current currency."""
    conn = get_db()
    row = conn.execute("SELECT * FROM expense WHERE id = ?", (expense_id,)).fetchone()
    conn.close()
    if row:
        data = dict(row)
        currency = get_setting("currency", "USD")
        rate = CURRENCY_RATES.get(currency, 1.0)
        data["amount"] = round(data["amount"] * rate, 2)
        return jsonify(data)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/webhook/telegram", methods=["POST"])
def telegram_webhook():
    """
    Webhook endpoint to receive transaction data from a Telegram bot.
    Supports:
    1. Structured bank email text: auto-parsed by parse_bank_email()
    2. Raw natural language: { "text": "25000 Starbucks" }
    3. Pre-parsed fields: { "amount": 15.5, "description": "Starbucks" }
    """
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    source = data.get("source", "telegram")
    tx_date = data.get("date", date.today().isoformat())

    try:
        # Case 1: Raw text input
        if "text" in data:
            raw_text = data["text"]

            # Try structured bank email first
            parsed = intelligence.parse_bank_email(raw_text)
            if parsed:
                amount = parsed["amount"]
                description = parsed["description"]
                category = parsed["category"]
                # Use extracted date if available
                if parsed.get("date"):
                    tx_date = parsed["date"]
                # Include tx_type in source label for audit trail
                if parsed.get("tx_type"):
                    source = f"bank_email ({parsed['tx_type']})"
                else:
                    source = "bank_email"
            else:
                # Fall back to free-text parser
                parsed = intelligence.parse_telegram_message(raw_text)
                if not parsed:
                    return jsonify({"status": "error", "message": "Could not parse text"}), 400
                amount = parsed["amount"]
                description = parsed["description"]
                category = parsed["category"]
                usd_amount = amount  # free-text: amount already in display units, store as-is

        # Case 2: Already parsed fields
        elif "amount" in data and "description" in data:
            amount = float(data["amount"])
            description = data["description"].strip()
            category = data.get("category") or intelligence.categorize_transaction(description)
            usd_amount = amount

        else:
            return jsonify({"status": "error", "message": "Missing amount/description or text"}), 400

        # For bank emails, convert using the detected source currency
        if source.startswith("bank_email") and parsed:
            raw_currency = parsed.get("amount_currency", "IDR")
            usd_amount = amount / CURRENCY_RATES.get(raw_currency, 1.0)

        conn = get_db()
        conn.execute(
            "INSERT INTO drafts (amount, description, date, category, source) VALUES (?, ?, ?, ?, ?)",
            (usd_amount, description, tx_date, category, source)
        )
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "message": "Draft saved successfully", "parsed": {"amount": amount, "description": description, "category": category}}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/parse-text", methods=["POST"])
def api_parse_text():
    """
    Parse raw text (bank email, SMS, or free text) and return extracted fields.
    Does NOT save to DB - returns parsed result for UI preview.

    Body: { "text": "<raw text>" }
    Response: { "amount": 180000, "description": "Alfacell", "date": "2026-04-24",
                "category": "food", "source_type": "bank_email" | "free_text" }
    """
    data = request.json
    if not data or "text" not in data:
        return jsonify({"status": "error", "message": "Missing 'text' field"}), 400

    raw_text = data["text"].strip()
    if not raw_text:
        return jsonify({"status": "error", "message": "Empty text"}), 400

    # Try structured bank email first
    parsed = intelligence.parse_bank_email(raw_text)
    if parsed:
        source_type = "bank_email"
    else:
        # Fall back to free-text
        parsed = intelligence.parse_telegram_message(raw_text)
        if not parsed:
            return jsonify({"status": "error", "message": "Could not parse text. Try: '25000 Nasi Goreng'"}), 422
        parsed["date"] = date.today().isoformat()
        source_type = "free_text"

    # Convert raw amount to display currency for the UI
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    if source_type == "bank_email":
        raw_currency = parsed.get("amount_currency", "IDR")
        raw_rate = CURRENCY_RATES.get(raw_currency, 1.0)
        display_amount = round(parsed["amount"] / raw_rate * rate, 2)
    else:
        display_amount = round(parsed["amount"] * rate, 2)

    return jsonify({
        "status": "success",
        "source_type": source_type,
        "amount_raw": parsed["amount"],
        "amount_display": display_amount,
        "amount_currency": parsed.get("amount_currency", "USD"),
        "description": parsed["description"],
        "date": parsed.get("date") or date.today().isoformat(),
        "category": parsed["category"],
        "tx_type": parsed.get("tx_type"),
        "lang": parsed.get("lang", "id"),
        "currency": currency,
    })



@app.route("/drafts/approve/<int:draft_id>", methods=["POST"])
def approve_draft(draft_id):
    """Approve a draft and move it to expenses."""
    conn = get_db()
    
    # Get form data which might override draft defaults
    category = request.form.get("category")
    amount = request.form.get("amount", type=float)
    currency_form = get_setting("currency", "USD")
    
    # Convert incoming amount back to USD base if it was edited in UI
    if amount is not None:
        rate = CURRENCY_RATES.get(currency_form, 1.0)
        amount = amount / rate

    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    
    if draft:
        final_amount = amount if amount is not None else draft["amount"]
        final_category = category if category else draft["category"]
        
        conn.execute(
            "INSERT INTO expense (amount, category, description, date, note) VALUES (?, ?, ?, ?, ?)",
            (final_amount, final_category, draft["description"], draft["date"], f"From {draft['source']}")
        )
        conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        conn.commit()
        flash("Draft approved and saved as expense!", "success")
        
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/drafts/reject/<int:draft_id>", methods=["POST"])
def reject_draft(draft_id):
    """Delete a draft."""
    conn = get_db()
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()
    flash("Draft deleted.", "success")
    return redirect(url_for("dashboard"))


# --- Recurring Manager ---
@app.route("/recurring")
def recurring_manager():
    """View and manage recurring expense rules."""
    conn = get_db()
    configs = conn.execute(
        "SELECT * FROM recurring_config ORDER BY day_of_month ASC, description ASC"
    ).fetchall()
    conn.close()

    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)

    active_count = sum(1 for c in configs if c["is_active"])
    total_active_amount = sum(c["amount"] for c in configs if c["is_active"])

    # Find the next day-of-month trigger that hasn't passed yet
    today = date.today()
    upcoming_days = sorted(
        set(c["day_of_month"] for c in configs if c["is_active"] and c["day_of_month"] >= today.day)
    )
    next_trigger_day = upcoming_days[0] if upcoming_days else None

    return render_template(
        "recurring.html",
        configs=configs,
        active_count=active_count,
        total_active_amount=total_active_amount,
        next_trigger_day=next_trigger_day,
        categories=EXPENSE_CATEGORIES,
        category_map=CATEGORY_MAP,
        current_currency=currency,
        currency_rates=CURRENCY_RATES,
    )


@app.route("/recurring/add", methods=["POST"])
def add_recurring():
    """Add a new recurring expense rule."""
    description = request.form.get("description", "").strip()
    amount = request.form.get("amount", type=float)
    category = request.form.get("category", "bills").strip()
    day_of_month = request.form.get("day_of_month", type=int)

    if not description or not amount or not day_of_month:
        flash("All fields are required.", "error")
        return redirect(url_for("recurring_manager"))

    if not (1 <= day_of_month <= 28):
        flash("Day of month must be between 1 and 28.", "error")
        return redirect(url_for("recurring_manager"))

    # Store amount in USD base
    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    conn = get_db()
    conn.execute(
        "INSERT INTO recurring_config (amount, category, description, day_of_month, is_active) VALUES (?, ?, ?, ?, 1)",
        (usd_amount, category, description, day_of_month),
    )
    conn.commit()
    conn.close()

    flash(f"Recurring rule '{description}' added!", "success")
    return redirect(url_for("recurring_manager"))


@app.route("/recurring/<int:config_id>/edit", methods=["POST"])
def edit_recurring(config_id):
    """Edit an existing recurring expense rule."""
    description = request.form.get("description", "").strip()
    amount = request.form.get("amount", type=float)
    category = request.form.get("category", "bills").strip()
    day_of_month = request.form.get("day_of_month", type=int)

    if not description or not amount or not day_of_month:
        flash("All fields are required.", "error")
        return redirect(url_for("recurring_manager"))

    if not (1 <= day_of_month <= 28):
        flash("Day of month must be between 1 and 28.", "error")
        return redirect(url_for("recurring_manager"))

    currency = get_setting("currency", "USD")
    rate = CURRENCY_RATES.get(currency, 1.0)
    usd_amount = amount / rate

    conn = get_db()
    conn.execute(
        "UPDATE recurring_config SET amount = ?, category = ?, description = ?, day_of_month = ? WHERE id = ?",
        (usd_amount, category, description, day_of_month, config_id),
    )
    conn.commit()
    conn.close()

    flash("Recurring rule updated.", "success")
    return redirect(url_for("recurring_manager"))


@app.route("/recurring/<int:config_id>/toggle", methods=["POST"])
def toggle_recurring(config_id):
    """Toggle a recurring rule between active and paused."""
    conn = get_db()
    row = conn.execute("SELECT is_active FROM recurring_config WHERE id = ?", (config_id,)).fetchone()
    if row:
        new_state = 0 if row["is_active"] else 1
        conn.execute("UPDATE recurring_config SET is_active = ? WHERE id = ?", (new_state, config_id))
        conn.commit()
        flash("Rule " + ("activated." if new_state else "paused."), "success")
    conn.close()
    return redirect(url_for("recurring_manager"))


@app.route("/recurring/<int:config_id>/delete", methods=["POST"])
def delete_recurring(config_id):
    """Delete a recurring expense rule."""
    conn = get_db()
    conn.execute("DELETE FROM recurring_config WHERE id = ?", (config_id,))
    conn.commit()
    conn.close()
    flash("Recurring rule deleted.", "success")
    return redirect(url_for("recurring_manager"))


# --- Export Data ---
@app.route("/export/csv")
def export_csv():
    """Export all expenses to CSV format."""
    conn = get_db()
    expenses = conn.execute("SELECT date, category, description, amount, note FROM expense ORDER BY date DESC").fetchall()
    conn.close()
    
    import csv
    from io import StringIO
    from flask import Response
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Category', 'Description', 'Amount', 'Note'])
    for e in expenses:
        cw.writerow([e['date'], e['category'], e['description'], e['amount'], e['note']])
        
    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=pulse_export.csv"}
    )


@app.route("/export/excel")
def export_excel():
    """Export all expenses and income to a professionally styled Excel format."""
    conn = get_db()
    expenses = conn.execute("SELECT date, category, description, amount, note FROM expense ORDER BY date DESC").fetchall()
    income = conn.execute("SELECT source, amount, month, year, note, created_at FROM income ORDER BY year DESC, month DESC").fetchall()
    conn.close()

    # Convert to DataFrames
    df_expenses = pd.DataFrame([dict(row) for row in expenses])
    df_income = pd.DataFrame([dict(row) for row in income])

    # Human-readable column names and basic cleanup
    if not df_expenses.empty:
        df_expenses.columns = [col.title() for col in df_expenses.columns]
    if not df_income.empty:
        df_income.columns = [col.replace('_', ' ').title() for col in df_income.columns]

    # Create Excel object in memory
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # Write sheets
    df_expenses.to_excel(writer, sheet_name='Expenses', index=False)
    df_income.to_excel(writer, sheet_name='Income', index=False)

    # Get workbook/worksheet objects for styling
    workbook = writer.book
    
    # STYLE DEFINITIONS
    header_style = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
        'fg_color': '#0D9488', # Teal 600
        'font_color': '#FFFFFF',
        'border': 1,
        'font_size': 11
    })
    
    amount_style = workbook.add_format({
        'num_format': '#,##0.00',
        'align': 'right',
        'border': 1,
        'valign': 'vcenter'
    })
    
    date_style = workbook.add_format({
        'num_format': 'yyyy-mm-dd',
        'align': 'center',
        'border': 1,
        'valign': 'vcenter'
    })
    
    base_style = workbook.add_format({
        'border': 1,
        'valign': 'vcenter'
    })
    
    stripe_style = workbook.add_format({
        'border': 1,
        'valign': 'vcenter',
        'fg_color': '#F8FAFC' # Slate 50
    })

    def apply_professional_styling(worksheet, df):
        if df.empty:
            return
            
        # Apply header styling
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_style)
        
        # Apply zebra stripes and borders to data rows
        for row_num in range(1, len(df) + 1):
            row_format = stripe_style if row_num % 2 == 0 else base_style
            for col_num in range(len(df.columns)):
                # We write the value again with the format
                val = df.iloc[row_num-1, col_num]
                
                # Special cases for column types
                col_name = df.columns[col_num].lower()
                if 'amount' in col_name:
                    worksheet.write(row_num, col_num, val, amount_style if row_num % 2 != 0 else workbook.add_format({'num_format': '#,##0.00', 'align': 'right', 'border': 1, 'valign': 'vcenter', 'fg_color': '#F8FAFC'}))
                elif 'date' in col_name or 'created at' in col_name:
                    worksheet.write(row_num, col_num, val, date_style if row_num % 2 != 0 else workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'center', 'border': 1, 'valign': 'vcenter', 'fg_color': '#F8FAFC'}))
                else:
                    worksheet.write(row_num, col_num, val, row_format)

        # Auto-adjust column width
        for i, col in enumerate(df.columns):
            max_len = max(
                df[col].astype(str).map(len).max() if not df[col].empty else 0,
                len(col)
            ) + 2
            worksheet.set_column(i, i, min(max_len, 60))

    apply_professional_styling(writer.sheets['Expenses'], df_expenses)
    apply_professional_styling(writer.sheets['Income'], df_income)

    writer.close()
    output.seek(0)

    filename = f"Pulse_Financial_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- Telegram Webhook Implementation ---
bot_app = bot.create_bot_app()
is_initialized = False

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming Telegram updates."""
    global is_initialized
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            
            # Only initialize once per instance lifecycle
            if not is_initialized:
                await bot_app.initialize()
                is_initialized = True
                
            await bot_app.process_update(update)
            return "ok", 200
        except Exception as e:
            print(f"Webhook Error: {e}")
            return str(e), 500


@app.route('/set_webhook', methods=['GET'])
async def set_webhook():
    """One-time route to register the webhook URL with Telegram."""
    webhook_url = f"{request.url_root.replace('http://', 'https://')}webhook"
    try:
        # Ensure bot is initialized
        await bot_app.initialize()
        success = await bot_app.bot.set_webhook(webhook_url)
        if success:
            return f"✅ Webhook successfully set to: {webhook_url}", 200
        return "❌ Failed to set webhook", 400
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

@app.route('/unset_webhook', methods=['GET'])
async def unset_webhook():
    """One-time route to remove the webhook URL (use this when moving to Koyeb/Polling)."""
    try:
        # Ensure bot is initialized
        await bot_app.initialize()
        success = await bot_app.bot.delete_webhook()
        if success:
            return "✅ Webhook successfully deleted. You can now use Polling mode (PythonAnywhere, etc.)!", 200

        return "❌ Failed to delete webhook", 400
    except Exception as e:
        return f"❌ Error: {str(e)}", 500



if __name__ == "__main__":
    app.run(debug=True)

