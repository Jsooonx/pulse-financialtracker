"""Pulse — Personal Finance Intelligence Web App."""

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import sqlite3
import os
from datetime import datetime, date
import intelligence

app = Flask(__name__)
app.secret_key = "pulse-secret-key-change-in-production"

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


def get_db():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
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
    """Inject current datetime into all templates."""
    return {"now": datetime.utcnow()}


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

    for row in categories_data:
        cat = CATEGORY_MAP.get(row["category"], {"label": row["category"], "icon": "📦", "color": "#B2BEC3"})
        chart_labels.append(cat["label"])
        chart_amounts.append(row["total"] * rate)
        chart_colors.append(cat["color"])
        category_details.append({
            "id": row["category"],
            "label": cat["label"],
            "icon": cat["icon"],
            "color": cat["color"],
            "total": row["total"],
            "count": row["count"],
            "percentage": (row["total"] / total_expense * 100) if total_expense > 0 else 0,
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
        current_currency=get_setting("currency", "USD")
    )


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

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO income (amount, source, month, year, note) VALUES (?, ?, ?, ?, ?)",
            (usd_amount, source, month, year, note),
        )
        conn.commit()
        flash("Income added successfully!", "success")
    except sqlite3.IntegrityError:
        # Update existing
        conn.execute(
            "UPDATE income SET amount = ?, note = ? WHERE source = ? AND month = ? AND year = ?",
            (usd_amount, note, source, month, year),
        )
        conn.commit()
        flash("Income updated successfully!", "success")
    finally:
        conn.close()

    return redirect(url_for("dashboard", month=month, year=year))


@app.route("/income/delete/<int:income_id>", methods=["POST"])
def delete_income(income_id):
    """Delete income entry."""
    conn = get_db()
    row = conn.execute("SELECT month, year FROM income WHERE id = ?", (income_id,)).fetchone()
    month, year = (row["month"], row["year"]) if row else (date.today().month, date.today().year)
    conn.execute("DELETE FROM income WHERE id = ?", (income_id,))
    conn.commit()
    conn.close()
    flash("Income deleted successfully.", "success")
    return redirect(url_for("dashboard", month=month, year=year))


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

    conn = get_db()
    conn.execute(
        "INSERT INTO expense (amount, category, description, date, note) VALUES (?, ?, ?, ?, ?)",
        (usd_amount, category, description, expense_date, note),
    )
    conn.commit()
    conn.close()

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

    conn = get_db()
    conn.execute(
        """UPDATE expense SET amount = ?, category = ?, description = ?, date = ?, note = ?
           WHERE id = ?""",
        (usd_amount, category, description, expense_date, note, expense_id),
    )
    conn.commit()
    conn.close()

    parsed_date = datetime.strptime(expense_date, "%Y-%m-%d")
    flash("Expense updated successfully!", "success")
    return redirect(url_for("dashboard", month=parsed_date.month, year=parsed_date.year))


@app.route("/expense/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    """Delete expense transaction."""
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
    flash("Expense deleted successfully.", "success")
    return redirect(url_for("dashboard", month=month, year=year))


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
    1. Parsed data: { "amount": 15.5, "description": "Starbucks Coffee", "source": "telegram" }
    2. Raw text: { "text": "25000 Starbucks", "source": "telegram" }
    """
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    source = data.get("source", "telegram")
    tx_date = data.get("date", date.today().isoformat())

    try:
        # Case 1: Raw text input (Natural Language)
        if "text" in data:
            parsed = intelligence.parse_telegram_message(data["text"])
            if not parsed:
                return jsonify({"status": "error", "message": "Could not parse text"}), 400
            
            amount = parsed["amount"]
            description = parsed["description"]
            category = parsed["category"]
        
        # Case 2: Already parsed fields
        elif "amount" in data and "description" in data:
            amount = float(data["amount"])
            description = data["description"].strip()
            category = data.get("category") or intelligence.categorize_transaction(description)
        
        else:
            return jsonify({"status": "error", "message": "Missing amount/description or text"}), 400

        conn = get_db()
        conn.execute(
            "INSERT INTO drafts (amount, description, date, category, source) VALUES (?, ?, ?, ?, ?)",
            (amount, description, tx_date, category, source)
        )
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "message": "Draft saved successfully", "parsed": {"amount": amount, "description": description, "category": category}}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
