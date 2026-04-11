import sqlite3
from datetime import date, datetime
from collections import defaultdict
import math

def calculate_trend_and_forecast(conn, category, current_month, current_year):
    """
    Calculate 3-month moving average and basic linear regression for forecasting.
    Returns trend data (last 6 months) and next month forecast.
    """
    # Get last 6 months data for the given category
    cursor = conn.cursor()
    
    # Calculate start date for last 6 months
    months_data = []
    
    # We'll fetch month by month for the last 6 months
    y, m = current_year, current_month
    for _ in range(6):
        months_data.insert(0, {"month": m, "year": y, "label": f"{m}/{y}", "total": 0})
        m -= 1
        if m == 0:
            m = 12
            y -= 1
            
    # Fetch data
    for md in months_data:
        row = cursor.execute(
            """SELECT COALESCE(SUM(amount), 0) as total FROM expense 
               WHERE category = ? AND CAST(strftime('%m', date) AS INTEGER) = ? 
               AND CAST(strftime('%Y', date) AS INTEGER) = ?""",
            (category, md["month"], md["year"])
        ).fetchone()
        md["total"] = row["total"]

    # Calculate 3-month moving average
    for i in range(len(months_data)):
        if i >= 2:
            ma = (months_data[i]["total"] + months_data[i-1]["total"] + months_data[i-2]["total"]) / 3
            months_data[i]["moving_average"] = ma
        else:
            months_data[i]["moving_average"] = None

    # Linear Regression for next month (using last 3 months to be responsive to recent changes)
    # y = mx + c
    recent_3 = months_data[-3:]
    x_mean = 1.0  # (0 + 1 + 2) / 3
    y_mean = sum(d["total"] for d in recent_3) / 3 if recent_3 else 0
    
    numerator = 0
    denominator = 0
    for i, d in enumerate(recent_3):
        x_diff = i - x_mean
        y_diff = d["total"] - y_mean
        numerator += x_diff * y_diff
        denominator += x_diff ** 2
        
    m_slope = numerator / denominator if denominator != 0 else 0
    c_intercept = y_mean - (m_slope * x_mean)
    
    # Predict for next month (x = 3)
    forecast = max(0, m_slope * 3 + c_intercept)

    return {
        "historical": months_data,
        "forecast": forecast,
        "trend_direction": "up" if m_slope > 0 else "down" if m_slope < 0 else "stable"
    }

def detect_anomalies(conn, current_month, current_year):
    """
    Detect spending spikes using Z-score per category in the current month.
    Z = (X - Mean) / StdDev
    If Z > 2, we consider it a spike.
    """
    anomalies = []
    cursor = conn.cursor()
    
    # Get all categories present this month
    this_month_expenses = cursor.execute(
        """SELECT id, category, amount, description, date 
           FROM expense 
           WHERE CAST(strftime('%m', date) AS INTEGER) = ? 
           AND CAST(strftime('%Y', date) AS INTEGER) = ?""",
        (current_month, current_year)
    ).fetchall()
    
    # We need historical mean and stddev for each category
    # Let's get them from the past 6 months
    history_stats = {}
    
    # Calculate historical transactions for all categories to find mean & stddev
    historical_tx = cursor.execute(
        """SELECT category, amount FROM expense 
           WHERE date < ? AND date >= date(?, '-6 months')""",
        (f"{current_year}-{current_month:02d}-01", f"{current_year}-{current_month:02d}-01")
    ).fetchall()
    
    cat_amounts = defaultdict(list)
    for tx in historical_tx:
        cat_amounts[tx["category"]].append(tx["amount"])
        
    for cat, amounts in cat_amounts.items():
        if len(amounts) >= 3:  # Need at least 3 for meaningful stddev
            mean = sum(amounts) / len(amounts)
            variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
            stddev = math.sqrt(variance)
            history_stats[cat] = {"mean": mean, "stddev": stddev}
            
    # Now check this month's transactions
    for tx in this_month_expenses:
        cat = tx["category"]
        if cat in history_stats and history_stats[cat]["stddev"] > 0:
            mean = history_stats[cat]["mean"]
            stddev = history_stats[cat]["stddev"]
            z_score = (tx["amount"] - mean) / stddev
            
            if z_score > 2.0: # Threshold for anomaly
                anomalies.append({
                    "tx": tx,
                    "z_score": z_score,
                    "mean_normal": mean
                })
                
    return anomalies

def evaluate_50_30_20(total_income, category_totals):
    """
    Evaluate spending based on 50/30/20 rule.
    """
    if total_income <= 0:
        return None
        
    # Mapping
    needs_cats = ["food", "transport", "bills", "health", "education"]
    wants_cats = ["entertainment", "shopping", "others"]
    
    needs_total = sum(v for k, v in category_totals.items() if k in needs_cats)
    wants_total = sum(v for k, v in category_totals.items() if k in wants_cats)
    savings_actual = total_income - (needs_total + wants_total)
    
    needs_pct = (needs_total / total_income) * 100
    wants_pct = (wants_total / total_income) * 100
    savings_pct = (savings_actual / total_income) * 100
    
    score = 100
    
    if needs_pct > 50:
        score -= min(30, (needs_pct - 50) * 1.5)
    if wants_pct > 30:
        score -= min(30, (wants_pct - 30) * 1.5)
    if savings_pct < 20:
        score -= min(40, (20 - savings_pct) * 2)
        
    insights = []
    if needs_pct > 60:
        insights.append("Your 'Needs' spending is quite high. Check for subscriptions or transport costs you could trim.")
    if wants_pct > 40:
        insights.append("Your 'Wants' spending is above average. Try reducing e-commerce checkouts or dining out to stay safe.")
    if savings_pct < 10:
        insights.append("Your savings/leftover cash is very thin this month. Try to set aside money at the start of the month.")
    if score >= 90:
        insights.append("Excellent! Your financial proportions are very healthy and meet the 50/30/20 benchmark.")

    return {
        "needs": {"total": needs_total, "pct": needs_pct, "target_pct": 50},
        "wants": {"total": wants_total, "pct": wants_pct, "target_pct": 30},
        "savings": {"total": savings_actual, "pct": savings_pct, "target_pct": 20},
        "score": max(0, int(score)),
        "insights": insights
    }

def generate_dynamic_insights(conn, total_income, category_totals, current_month, current_year, currency_symbol="$", rate=1.0):
    """Generate insight cards based on data."""
    insights = []
    
    if not category_totals:
        return insights
        
    # 1. Biggest spender
    biggest_cat = max(category_totals.items(), key=lambda x: x[1])
    if biggest_cat[1] > 0:
        insights.append({
            "type": "alert",
            "title": "Biggest Expense",
            "icon": "🔥",
            "message": f"{biggest_cat[0].title()} category is consuming the most funds ({currency_symbol}{biggest_cat[1] * rate:,.2f}). Keep an eye on this."
        })
        
    # 2. Add forecast insight for the biggest category
    forecast_data = calculate_trend_and_forecast(conn, biggest_cat[0], current_month, current_year)
    fc = forecast_data["forecast"]
    if fc > biggest_cat[1] * 1.1:
         insights.append({
            "type": "warning",
            "title": "Rising Trend",
            "icon": "📈",
            "message": f"Based on past patterns, {biggest_cat[0].title()} spending is predicted to rise next month to around {currency_symbol}{fc * rate:,.2f}."
        })
    elif fc < biggest_cat[1] * 0.9 and fc > 0:
        insights.append({
            "type": "success",
            "title": "Falling Trend",
            "icon": "📉",
            "message": f"Good! The spending trend for {biggest_cat[0].title()} is decreasing. Forecast for next month is around {currency_symbol}{fc * rate:,.2f}."
        })
        
        
    return insights

def process_recurring(conn, current_date):
    """
    Process recurring config and insert new expenses if they don't exist for the current month.
    """
    cursor = conn.cursor()
    configs = cursor.execute("SELECT * FROM recurring_config WHERE is_active = 1").fetchall()
    month = f"{current_date.month:02d}"
    year = str(current_date.year)
    
    for cfg in configs:
        existing = cursor.execute(
            """SELECT id FROM expense 
               WHERE is_recurring = 1 
               AND description = ? 
               AND strftime('%m', date) = ? 
               AND strftime('%Y', date) = ?""",
            (cfg["description"], month, year)
        ).fetchone()
        
        if not existing:
            if current_date.day >= cfg["day_of_month"]:
                import calendar
                last_day = calendar.monthrange(current_date.year, current_date.month)[1]
                safe_day = min(cfg["day_of_month"], last_day)
                exp_date = date(current_date.year, current_date.month, safe_day).isoformat()
                
                cursor.execute(
                    "INSERT INTO expense (amount, category, description, date, note, is_recurring) VALUES (?, ?, ?, ?, ?, 1)",
                    (cfg["amount"], cfg["category"], cfg["description"], exp_date, "⚙️ Auto-generated")
                )
    conn.commit()


def categorize_transaction(description):
    """
    Simple local categorization engine that maps common keywords to existing categories.
    Used for automatically categorizing incoming drafts (e.g., from Telegram).
    """
    if not description:
        return "others"
        
    desc_lower = description.lower()
    
    # Keyword mapping based on EXPENSE_CATEGORIES
    mappings = {
        'food': ['eating', 'food', 'lunch', 'dinner', 'breakfast', 'makan', 'snack', 'coffee', 'drink', 'restaurant', 'cafe', 'mcdonald', 'kfc', 'starbucks', 'burger', 'pizza', 'rice', 'boba', 'warung', 'grocery', 'supermarket', 'mart', 'indomaret', 'alfamart', 'bakery', 'steak', 'walmart', 'target'],
        'transport': ['transport', 'grab', 'gojek', 'taxi', 'bus', 'fuel', 'gas', 'petrol', 'parking', 'parkir', 'uber', 'lyft', 'train', 'subway', 'flight', 'plane', 'airline', 'mrt', 'lrt', 'krl', 'toll', 'bensin', 'pertamina', 'shell', 'chevron', 'ride', 'commute'],
        'shopping': ['shopping', 'clothes', 'clothing', 'shirt', 'shoes', 'buy', 'beli', 'amazon', 'mall', 'outfit', 'tech', 'gadget', 'laptop', 'phone', 'apple', 'best buy', 'tokopedia', 'tokped', 'shopee', 'lazada', 'skincare', 'makeup', 'electronics'],
        'entertainment': ['entertainment', 'movie', 'game', 'netflix', 'spotify', 'cinema', 'xxi', 'cgv', 'ticket', 'concert', 'trip', 'holiday', 'vacation', 'steam', 'xbox', 'playstation', 'nintendo', 'disney', 'youtube', 'hbogo', 'hobby', 'museum', 'club'],
        'health': ['health', 'medicine', 'doctor', 'gym', 'pharmacy', 'hospital', 'clinic', 'dentist', 'vet', 'apotek', 'skincare', 'fitness', 'workout', 'medical', 'supplement', 'vitamin', 'spa', 'massage', 'therapy', 'cvs', 'walgreens'],
        'bills': ['bills', 'electricity', 'electric', 'water', 'internet', 'phone', 'rent', 'wifi', 'data', 'credit', 'telkomsel', 'pln', 'pdam', 'insurance', 'subscription', 'membership', 'icloud', 'tax', 'laundry', 'maintenance', 'comcast', 'att', 'verizon', 'mortgage', 'indihome'],
        'education': ['education', 'school', 'college', 'university', 'tuition', 'course', 'udemy', 'coursera', 'bootcamp', 'bookstore', 'book'],
    }

    
    # Check exact word matches first for better accuracy
    words = set(desc_lower.replace('-', ' ').replace('_', ' ').split())
    for category, keywords in mappings.items():
        if any(keyword in words for keyword in keywords):
            return category
            
    # Fallback to substring matching if no exact word matches
    for category, keywords in mappings.items():
        if any(keyword in desc_lower for keyword in keywords):
            return category
            
    return "others"

def parse_telegram_message(text):
    """
    Parse a natural language message from Telegram.
    Example: "Coffee at Starbucks 15000" -> {amount: 15000, description: "Coffee at Starbucks", category: "food"}
    Example: "25000 Nasi Goreng" -> {amount: 25000, description: "Nasi Goreng", category: "food"}
    """
    if not text:
        return None
        
    import re
    
    # Find numbers in the text (potential amounts)
    # Support formats like 15000, 15.000, 15,000.00
    # We clean the string of common currency symbols first
    clean_text = text.replace('Rp', '').replace('$', '').replace('€', '').strip()
    
    # Match numbers (including those with . or , as separators)
    # This is a simple regex: it looks for consecutive digits, possibly with dots/commas
    # We pick the one that looks most like an amount (usually the largest or last one in simple inputs)
    # But for now, let's just find all numbers and pick the first one
    numbers = re.findall(r'\d+(?:[.,]\d+)*', clean_text)
    
    if not numbers:
        return None
        
    # Pick the number - let's assume if there are multiple words, 
    # the amount is often at the beginning or end
    # We'll try to refine this: if a number is very large or has separators, it's likely the amount
    amount_str = numbers[0]
    # Simple normalization: remove common separators if they aren't decimals
    # This is tricky without locale, but let's assume if it has 3 digits after a separator, it's a thousand separator
    normalized_amount = amount_str.replace(',', '') # Simplify for now
    try:
        amount = float(normalized_amount)
    except ValueError:
        return None
        
    # Description is the rest of the text
    description = clean_text.replace(amount_str, '').strip()
    if not description:
        description = "Telegram Transaction"
        
    # Auto-categorize
    category = categorize_transaction(description)
    
    return {
        "amount": amount,
        "description": description,
        "category": category
    }
