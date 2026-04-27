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
    # Expanded with common Indonesian QRIS merchants and e-wallet vendors
    mappings = {
        'food': [
            # General
            'eating', 'food', 'lunch', 'dinner', 'breakfast', 'makan', 'snack', 'coffee',
            'drink', 'restaurant', 'cafe', 'bakery', 'steak', 'rice', 'boba', 'warung',
            'grocery', 'supermarket', 'mart',
            # Fast food chains
            'mcdonald', 'kfc', 'starbucks', 'burger', 'pizza', 'subway', 'wendys',
            'domino', 'popeyes', 'jollibee',
            # Indonesian grocery & convenience
            'indomaret', 'alfamart', 'alfacell', 'alfamidi', 'lawson', 'circle k',
            'familymart', 'hypermart', 'superindo', 'giant', 'carrefour', 'transmart',
            'lotte mart', 'lottemart', 'hero', 'yogya', 'borma', 'ramayana',
            # Delivery & apps
            'gofood', 'grabfood', 'shopeefood', 'shoppefood', 'traveloka eats',
            # International
            'walmart', 'target', 'costco', 'trader joe',
        ],
        'transport': [
            'transport', 'grab', 'gojek', 'taxi', 'bus', 'fuel', 'gas', 'petrol',
            'parking', 'parkir', 'uber', 'lyft', 'flight', 'plane', 'airline',
            'mrt', 'lrt', 'krl', 'toll', 'bensin', 'pertamina', 'shell', 'chevron',
            'ride', 'commute', 'gocar', 'grabcar', 'maxim', 'indriver', 'bluebird',
            'kereta', 'damri', 'transjakarta', 'busway', 'pelni', 'garuda', 'citilink',
            'lion air', 'airasia', 'batik air', 'sriwijaya', 'tol', 'jasa marga',
        ],
        'shopping': [
            'shopping', 'clothes', 'clothing', 'shirt', 'shoes', 'buy', 'beli',
            'amazon', 'mall', 'outfit', 'tech', 'gadget', 'laptop', 'apple', 'best buy',
            'tokopedia', 'tokped', 'shopee', 'lazada', 'blibli', 'bukalapak',
            'tiktok shop', 'zalora', 'berrybenka', 'hijup', 'uniqlo', 'zara', 'h&m',
            'iphone', 'samsung', 'electronics', 'skincare', 'makeup', 'wardah',
            'sogo', 'matahari', 'the body shop', 'guardian', 'watson',
        ],
        'entertainment': [
            'entertainment', 'movie', 'game', 'netflix', 'spotify', 'cinema', 'xxi', 'cgv',
            'ticket', 'concert', 'trip', 'holiday', 'vacation', 'steam', 'xbox',
            'playstation', 'nintendo', 'disney', 'youtube', 'hbogo', 'vidio', 'mola',
            'viu', 'wetv', 'iqiyi', 'prime video', 'apple tv', 'hobby', 'museum',
            'club', 'karaoke', 'bowling', 'billiard', 'esports', 'tiket', 'traveloka',
        ],
        'health': [
            'health', 'medicine', 'doctor', 'gym', 'pharmacy', 'hospital', 'clinic',
            'dentist', 'vet', 'apotek', 'fitness', 'workout', 'medical', 'supplement',
            'vitamin', 'spa', 'massage', 'therapy', 'cvs', 'walgreens',
            'kimia farma', 'guardian', 'k24', 'century', 'generik', 'puskesmas',
            'rs ', 'rumah sakit', 'bpjs', 'halodoc', 'alodokter', 'klikdokter',
        ],
        'bills': [
            'bills', 'electricity', 'electric', 'water', 'internet', 'rent', 'wifi',
            'data', 'credit', 'pln', 'pdam', 'insurance', 'subscription', 'membership',
            'icloud', 'tax', 'laundry', 'maintenance', 'mortgage',
            'telkomsel', 'xl', 'indosat', 'tri', 'smartfren', 'byuprifix',
            'indihome', 'myrepublic', 'firstmedia', 'biznet', 'cbni',
            'comcast', 'att', 'verizon', 'kos', 'kontrakan', 'sewa',
        ],
        'education': [
            'education', 'school', 'college', 'university', 'tuition', 'course',
            'udemy', 'coursera', 'bootcamp', 'bookstore', 'book', 'dicoding',
            'ruangguru', 'zenius', 'skill academy', 'bimbel', 'les', 'kursus',
        ],
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


def parse_bank_email(text):
    """
    Parse structured bank notification email/SMS text.

    Supported formats:
    ── Indonesian ──────────────────────────────────────────
    - BCA myBCA   : "Total Bayar : IDR 180,000.00"
    - Mandiri     : "Transaksi berhasil sebesar IDR..."
    - BNI / BRI   : similar field labels in Indonesian

    ── English ─────────────────────────────────────────────
    - Visa/MC SMS : "A transaction of USD 12.50 at Starbucks"
    - PayPal      : "You sent $25.00 to merchant@example.com"
    - Generic EN  : "Amount: $180.00 | Merchant: Amazon"
    - UK banks    : "Payment of £50.00 to TESCO"
    - SG banks    : "SGD 120.00 was debited from your account"

    Returns a dict or None if text is not a bank notification.
    Extra key `amount_currency` carries the detected currency code
    so callers can convert correctly (default 'IDR' for Indonesian).
    """
    if not text:
        return None

    import re

    text_lower = text.lower()

    # ── Detection markers ───────────────────────────────────
    id_markers = [
        'total bayar', 'tanggal transaksi', 'pembayaran ke', 'jenis transaksi',
        'nomor referensi', 'sumber dana', 'halo bca', 'transfer berhasil',
        'transaksi berhasil', 'debit rekening', 'tabungan', 'mybca',
        'mandiri', 'bni mobile', 'bri mobile', 'blu by bca', 'jenius',
        'gopay', 'ovo', 'dana', 'linkaja',
    ]
    en_markers = [
        'transaction alert', 'payment confirmation', 'you have made a payment',
        'a transaction of', 'was charged to your', 'was debited from your',
        'payment of', 'you sent', 'purchase at', 'transaction at',
        'amount due', 'amount charged', 'card ending', 'your account ending',
        'authorization code', 'reference number', 'transaction id',
        'merchant name', 'merchant:', 'paypal', 'stripe', 'wise transfer',
        'revolut', 'monzo', 'chase', 'barclays', 'hsbc alert',
        # PayPal / wallet patterns
        'you sent $', 'you sent £', 'you sent €', 'you sent usd',
        'sent to', 'payment sent', 'receipt from', 'receipt for',
    ]

    is_indonesian = any(m in text_lower for m in id_markers)
    is_english    = any(m in text_lower for m in en_markers)

    if not is_indonesian and not is_english:
        return None  # Not a bank notification — let caller use parse_telegram_message

    detected_currency = 'IDR' if is_indonesian else 'USD'  # default; refined below

    # ── Amount extraction ────────────────────────────────────
    # Currency symbol → code map for English notifications
    symbol_map = {
        r'\$': 'USD', r'usd': 'USD',
        r'£':  'GBP', r'gbp': 'GBP',
        r'€':  'EUR', r'eur': 'EUR',
        r'sgd':'SGD', r's\$': 'SGD',
        r'aud':'AUD', r'a\$': 'AUD',
        r'idr':'IDR', r'rp\.?': 'IDR',
    }

    # Indonesian amount patterns
    id_amount_patterns = [
        r'Total Bayar\s*:\s*IDR\s*([\d,\.]+)',
        r'Total Bayar\s*:\s*Rp\.?\s*([\d,\.]+)',
        r'sebesar\s+(?:IDR|Rp)\.?\s*([\d,\.]+)',
        r'jumlah\s*:\s*(?:IDR|Rp)\.?\s*([\d,\.]+)',
        r'nominal\s*:\s*(?:IDR|Rp)\.?\s*([\d,\.]+)',
        r'(?:IDR|Rp)\.?\s*([\d]{3,}(?:[,\.][\d]+)*)',  # any IDR amount as fallback
    ]

    # English amount patterns — each captures (symbol_hint, digits)
    en_amount_patterns = [
        # "a transaction of USD 12.50"
        r'(?:transaction|payment|amount|charged?|debited?)\s+of\s+(?:USD|GBP|EUR|SGD|AUD)?\s*([\d,\.]+)',
        # "Amount: $180.00" or "Amount Due: £50"
        r'[Aa]mount(?:\s+[Dd]ue|\s+[Cc]harged?)?\s*:\s*[\$£€]?\s*([\d,\.]+)',
        # "you sent $25.00"
        r'(?:you\s+sent|sent)\s+[\$£€]?\s*([\d,\.]+)',
        # "Payment of £50.00"
        r'[Pp]ayment\s+of\s+[\$£€]?\s*([\d,\.]+)',
        # "SGD 120.00 was debited"
        r'(?:USD|GBP|EUR|SGD|AUD|IDR)\s+([\d,\.]+)',
        # "$25.00" standalone
        r'[\$£€]([\d,\.]+)',
        # "25.00 USD"
        r'([\d,\.]+)\s+(?:USD|GBP|EUR|SGD|AUD)',
    ]

    def _normalize_amount(raw):
        """Normalize a raw amount string to float, handling both locale formats."""
        raw = raw.strip()
        # European: 1.234,56 → comma is decimal
        if re.search(r',\d{2}$', raw):
            return float(raw.replace('.', '').replace(',', '.'))
        # American / IDR: 1,234.56 → comma is thousands
        return float(raw.replace(',', ''))

    amount = None
    patterns_to_try = (id_amount_patterns if is_indonesian else []) + en_amount_patterns
    for pat in patterns_to_try:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                amount = _normalize_amount(m.group(1))
                # Detect currency from surrounding context
                start = max(0, m.start() - 10)
                ctx = text[start: m.end() + 4].upper()
                for sym, code in [('IDR','IDR'),('RP','IDR'),('USD','USD'),
                                   ('GBP','GBP'),('EUR','EUR'),('SGD','SGD'),
                                   ('AUD','AUD'),('£','GBP'),('€','EUR'),('$','USD')]:
                    if sym in ctx:
                        detected_currency = code
                        break
                break
            except ValueError:
                continue

    if amount is None:
        return None

    # ── Vendor / Merchant extraction ─────────────────────────
    vendor = None
    vendor_patterns = [
        # Indonesian
        r'Pembayaran Ke\s*:\s*(.+)',
        r'Ditransfer ke\s*:\s*(.+)',
        r'Kepada\s*:\s*(.+)',
        r'Tujuan\s*:\s*(.+)',
        # English
        r'[Mm]erchant(?:\s+[Nn]ame)?\s*:\s*(.+)',
        r'[Pp]ayment\s+[Tt]o\s*:\s*(.+)',
        r'[Pp]aid\s+[Tt]o\s*:\s*(.+)',
        r'[Pp]urchase\s+[Aa]t\s*:\s*(.+)',
        r'[Tt]ransaction\s+[Aa]t\s*:\s*(.+)',
        r'[Tt]o\s*:\s*(.+@.+)',                # PayPal "To: email@x.com"
        r'[Ss]ent\s+to\s*:\s*(.+)',
        r'[Pp]ayee\s*:\s*(.+)',
        r'[Bb]eneficiary\s*:\s*(.+)',
        r'[Ss]tore\s*:\s*(.+)',
        r'[Vv]endor\s*:\s*(.+)',
        # Generic: "at <Merchant>" — works inline (no newline needed)
        r'(?:at|@)\s+([A-Z][A-Za-z0-9 &\'\-\.]{2,40})(?=\s*(?:was|on|[,\.\n\r]|$))',
        # PayPal: "to email@domain" — use domain as vendor
        r'(?:to|sent\s+to)\s+([\w\.\-]+@[\w\.]+)',
    ]
    for pat in vendor_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            vendor = re.split(r'[\t\n\r]', m.group(1).strip())[0].strip()
            # Strip trailing junk like reference numbers
            vendor = re.sub(r'\s{2,}.*$', '', vendor).strip()
            if vendor:
                break

    if not vendor:
        vendor = 'Bank Transaction'

    # ── Date extraction ──────────────────────────────────────
    tx_date = None
    date_patterns = [
        # Indonesian
        (r'Tanggal Transaksi\s*:\s*(\d{1,2}\s+\w+\s+\d{4})',    '%d %b %Y'),
        (r'Tanggal Transaksi\s*:\s*(\d{1,2}-\w+-\d{4})',         '%d-%b-%Y'),
        (r'Tanggal\s*:\s*(\d{1,2}\s+\w+\s+\d{4})',              '%d %b %Y'),
        # English labelled
        (r'[Dd]ate\s*:\s*(\d{4}-\d{2}-\d{2})',                  '%Y-%m-%d'),
        (r'[Dd]ate\s*:\s*(\d{1,2}/\d{2}/\d{4})',                '%d/%m/%Y'),
        (r'[Dd]ate\s*:\s*(\d{1,2}\s+\w+\s+\d{4})',             '%d %b %Y'),
        (r'[Dd]ate\s*:\s*(\w+\s+\d{1,2},?\s+\d{4})',           '%B %d %Y'),
        (r'[Tt]ransaction [Dd]ate\s*:\s*(\d{4}-\d{2}-\d{2})',  '%Y-%m-%d'),
        (r'[Tt]ransaction [Dd]ate\s*:\s*(\d{1,2}/\d{2}/\d{4})','%d/%m/%Y'),
        # ISO anywhere in text
        (r'(\d{4}-\d{2}-\d{2})',                                 '%Y-%m-%d'),
    ]
    for pat, fmt in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                from datetime import datetime as _dt
                raw_date = m.group(1).strip().replace(',', '')
                tx_date = _dt.strptime(raw_date, fmt).strftime('%Y-%m-%d')
                break
            except ValueError:
                continue

    # ── Transaction type ─────────────────────────────────────
    tx_type = None
    type_patterns = [
        r'Jenis Transaksi\s*:\s*(.+)',          # Indonesian
        r'[Tt]ransaction [Tt]ype\s*:\s*(.+)',   # English
        r'[Pp]ayment [Tt]ype\s*:\s*(.+)',
        r'[Tt]ype\s*:\s*(.+)',
    ]
    for pat in type_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            tx_type = re.split(r'[\t\n\r]', m.group(1).strip())[0].strip()
            break

    if not tx_type:
        tx_type = 'English Bank Notification' if is_english else 'Indonesian Bank Notification'

    category = categorize_transaction(vendor)

    return {
        'amount':           amount,
        'amount_currency':  detected_currency,   # NEW: lets caller convert correctly
        'description':      vendor,
        'date':             tx_date,
        'category':         category,
        'source_type':      'bank_email',
        'tx_type':          tx_type,
        'lang':             'en' if is_english else 'id',
    }
