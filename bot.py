import os
import sys
import sqlite3
import re
from datetime import datetime, date
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client

# Import shared intelligence layer
sys.path.insert(0, os.path.dirname(__file__))
import intelligence

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
# Use service role key if available for bot backend operations
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

USER_DBS_DIR = os.path.join(os.path.dirname(__file__), 'user_dbs')


CURRENCY_RATES = {'USD': 1.0, 'EUR': 0.86, 'IDR': 17000.0}

def get_currency():
    """Read currency setting from DB."""
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key='currency'").fetchone()
        conn.close()
        return row[0] if row else 'IDR'
    except:
        return 'IDR'

def fmt(amount_usd):
    """Format a USD-base amount in the user's display currency."""
    curr = get_currency()
    rate = CURRENCY_RATES.get(curr, 1.0)
    val = amount_usd * rate
    if curr == 'IDR':
        return f"Rp{val:,.0f}"
    elif curr == 'EUR':
        return f"€{val:,.2f}"
    return f"${val:,.2f}"

def get_progress_bar(pct):
    """Generate a text-based progress bar."""
    length = 10
    filled = min(length, int(round(pct / (100 / length))))
    return "█" * filled + "░" * (length - filled)

CATEGORY_KEYWORDS = {
    'food': ['eating', 'food', 'lunch', 'dinner', 'breakfast', 'makan', 'snack', 'coffee', 'drink', 'restaurant', 'cafe', 'mcdonald', 'kfc', 'starbucks', 'burger', 'pizza', 'rice', 'boba', 'warung', 'grocery', 'supermarket', 'mart', 'indomaret', 'alfamart', 'bakery', 'steak', 'walmart', 'target'],
    'transport': ['transport', 'grab', 'gojek', 'taxi', 'bus', 'fuel', 'gas', 'petrol', 'parking', 'parkir', 'uber', 'lyft', 'train', 'subway', 'flight', 'plane', 'airline', 'mrt', 'lrt', 'krl', 'toll', 'bensin', 'pertamina', 'shell', 'chevron', 'ride', 'commute'],
    'shopping': ['shopping', 'clothes', 'clothing', 'shirt', 'shoes', 'buy', 'beli', 'amazon', 'mall', 'outfit', 'tech', 'gadget', 'laptop', 'phone', 'apple', 'best buy', 'tokopedia', 'tokped', 'shopee', 'lazada', 'skincare', 'makeup', 'electronics'],
    'entertainment': ['entertainment', 'movie', 'game', 'netflix', 'spotify', 'cinema', 'xxi', 'cgv', 'ticket', 'concert', 'trip', 'holiday', 'vacation', 'steam', 'xbox', 'playstation', 'nintendo', 'disney', 'youtube', 'hbogo', 'hobby', 'museum', 'club'],
    'health': ['health', 'medicine', 'doctor', 'gym', 'pharmacy', 'hospital', 'clinic', 'dentist', 'vet', 'apotek', 'skincare', 'fitness', 'workout', 'medical', 'supplement', 'vitamin', 'spa', 'massage', 'therapy', 'cvs', 'walgreens'],
    'bills': ['bills', 'electricity', 'electric', 'water', 'internet', 'phone', 'rent', 'wifi', 'data', 'credit', 'telkomsel', 'pln', 'pdam', 'insurance', 'subscription', 'membership', 'icloud', 'tax', 'laundry', 'maintenance', 'comcast', 'att', 'verizon', 'mortgage', 'indihome'],
    'education': ['education', 'school', 'college', 'university', 'tuition', 'course', 'udemy', 'coursera', 'bootcamp', 'bookstore', 'book'],
}



BOT_CURRENCY_RATES = {'idr': 1/17000, 'usd': 1, 'eur': 1.08}

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_id_from_chat(chat_id):
    """Scan local user DBs to find which one has this Telegram chat_id linked."""
    if not os.path.exists(USER_DBS_DIR):
        return None
        
    for filename in os.listdir(USER_DBS_DIR):
        if filename.startswith('pulse_') and filename.endswith('.db'):
            db_path = os.path.join(USER_DBS_DIR, filename)
            try:
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT value FROM settings WHERE key='telegram_chat_id'").fetchone()
                conn.close()
                if row and str(row[0]) == str(chat_id):
                    # extract user_id from pulse_<user_id>.db
                    return filename[6:-3]
            except:
                continue
    return None

def get_db(chat_id=None):
    """Get the SQLite connection for the user."""
    if chat_id:
        user_id = get_user_id_from_chat(chat_id)
        if user_id:
            return sqlite3.connect(os.path.join(USER_DBS_DIR, f"pulse_{user_id}.db"))
    # Fallback to guest/old db
    fallback = os.path.join(USER_DBS_DIR, "pulse_guest.db")
    if not os.path.exists(fallback):
        fallback = os.path.join(os.path.dirname(__file__), 'pulse.db')
    return sqlite3.connect(fallback)

def parse_amount(text):
    text = text.lower().strip()
    multiplier = 1
    if 'k' in text:
        multiplier = 1000
        text = text.replace('k', '')
    elif 'm' in text:
        multiplier = 1000000
        text = text.replace('m', '')
    try:
        return float(re.sub(r'[^\d.]', '', text)) * multiplier
    except:
        return None

def parse_currency(text):
    text = text.lower()
    for currency in CURRENCY_RATES:
        if currency in text:
            return currency
    return 'usd'

def guess_category(description):
    description = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in description for kw in keywords):
            return category
    return 'others'

def convert_to_usd(amount, currency):
    rate = BOT_CURRENCY_RATES.get(currency, 1)
    return amount * rate

def get_user_currency(chat_id):
    try:
        conn = get_db(chat_id)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'default_currency'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].lower()
    except Exception:
        pass
    return 'idr' # Default to IDR if not set

def parse_transaction_parts(tokens, chat_id):
    """Shared helper to parse amount, currency and description/source from tokens."""
    amount_raw = None
    currency = None
    other_tokens = []

    for token in tokens:
        if re.search(r'\d', token):
            amount_raw = token
        elif token.lower() in CURRENCY_RATES:
            currency = token.lower()
        else:
            other_tokens.append(token)
            
    if not currency:
        currency = get_user_currency(chat_id)
    
    amount_local = parse_amount(amount_raw) if amount_raw else None
    description = ' '.join(other_tokens) if other_tokens else ''
    
    return amount_local, currency, description

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = get_user_id_from_chat(chat_id)
    
    msg = (
        "⚡ *Welcome to Pulsar* - Pulse Finance Intelligence\n\n"
        "📝 *Record Transactions*\n"
        "• `/add [desc] [amt] [curr]` - Log expense\n"
        "• `/income [src] [amt] [curr]` - Log income\n\n"
        "🏦 *Smart Parse (NEW!)*\n"
        "Paste your bank email / SMS and I will auto-extract it!\n\n"
        "📊 *Analysis*\n"
        "• `/summary` - Monthly balance + budget bars\n"
        "• `/insight` - Financial score + 50/30/20\n"
        "• `/history` - Last 10 transactions\n\n"
    )
    
    if not user_id:
        msg += "⚠️ *NOT LINKED:*\nYour Telegram is not linked to your Pulse Cloud account.\nClick the button below to link it!"
        keyboard = [[InlineKeyboardButton("🔗 Link Pulse Account", url=f"http://127.0.0.1:5000/link-telegram?chat_id={chat_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        msg += "✅ *Account Linked!*\nYou are connected to your Pulse Cloud account.\n\nType /help to see full examples and settings (like /unlink)."
        await update.message.reply_text(msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed help and examples."""
    help_text = (
        "💡 *Pulse Bot Commands*\n\n"
        "✨ *Smart Tracker (Just type!)*\n"
        "If you don't type a currency, your default currency will be used automatically!\n"
        "• `Beli kopi 50k`\n"
        "• `Grab to office 35000`\n"
        "• `Netflix subscription 15 USD` (Overrides default currency)\n\n"
        
        "📊 *Reports & Insights*\n"
        "• `/summary` - View current month's expenses & remaining budget\n"
        "• `/insight` - View total expenses and income\n"
        "• `/history` - See your 10 most recent transactions\n\n"
        
        "💰 *Income & Budget*\n"
        "• `/add_income 5000000 Salary` - Add your monthly income\n"
        "• `/set_budget Food 2000000` - Set a budget limit for a category\n"
        "• `/clear_budget Food` - Remove a category budget limit\n\n"
        
        "🔄 *Recurring Transactions*\n"
        "• `/recurring add 150000 Spotify 25` - Add 150k for Spotify on the 25th\n"
        "• `/recurring list` - See all recurring rules\n"
        "• `/recurring rm <id>` - Remove a recurring rule\n\n"
        
        "⚙️ *Settings*\n"
        "• `/currency` - Set your default currency (e.g. `/currency IDR`)\n"
        "• `/undo` - Delete the last expense you entered\n"
        "• `/undo_income` - Delete the last income you entered\n"
        "• `/unlink` - Unlink your Telegram account from Pulse\n"
        "• `/help` - Show this message"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unlink Telegram account."""
    chat_id = update.message.chat_id
    user_id = get_user_id_from_chat(chat_id)
    
    if not user_id:
        await update.message.reply_text("⚠️ Your account is not linked.")
        return
        
    try:
        # Delete from Supabase
        supabase = get_supabase()
        supabase.table('settings').delete().eq('key', 'telegram_chat_id').eq('value', str(chat_id)).execute()
        
        # Delete locally
        conn = get_db(chat_id)
        conn.execute("DELETE FROM settings WHERE key = 'telegram_chat_id'")
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "🔌 *Account Unlinked*\n\n"
            "Your Telegram account has been disconnected from Pulse. "
            "You can link it again anytime using /start.",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unlink account: {str(e)}")

async def set_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = get_user_id_from_chat(chat_id)
    
    if not user_id:
        await update.message.reply_text("⚠️ Please /start and link your account first.")
        return

    if not context.args:
        current_currency = get_user_currency(chat_id)
        await update.message.reply_text(
            f"🌍 Your current default currency is: *{current_currency.upper()}*\n\n"
            f"To change it, use: `/currency <USD|IDR|EUR>`\n"
            f"Example: `/currency IDR`",
            parse_mode='Markdown'
        )
        return

    new_curr = context.args[0].lower()
    if new_curr not in BOT_CURRENCY_RATES:
        await update.message.reply_text(f"❌ Unsupported currency. Supported: {', '.join(k.upper() for k in BOT_CURRENCY_RATES)}")
        return

    # Save locally
    conn = get_db(chat_id)
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_currency', ?)", (new_curr,))
    conn.commit()
    conn.close()

    # Save to Supabase (using Service Key)
    try:
        supabase = get_supabase()
        supabase.table('settings').upsert({
            'user_id': user_id,
            'key': 'default_currency',
            'value': new_curr
        }).execute()
    except Exception as e:
        print(f"Failed to sync currency to Supabase: {e}")

    await update.message.reply_text(
        f"✅ Default currency updated to *{new_curr.upper()}*.\n"
        f"You no longer need to type '{new_curr.upper()}' when adding expenses or incomes!",
        parse_mode='Markdown'
    )

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    month, year = now.month, now.year
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM income WHERE month=? AND year=?", (month, year))
    income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM expense WHERE strftime('%m', date)=? AND strftime('%Y', date)=?",
                   (str(month).zfill(2), str(year)))
    expenses = cursor.fetchone()[0]
    conn.close()

    balance = income - expenses
    savings_rate = ((balance / income) * 100) if income > 0 else 0

    await update.message.reply_text(
        f"📊 *Summary - {now.strftime('%B %Y')}*\n\n"
        f"💰 Income: `${income:,.2f}`\n"
        f"💸 Expenses: `${expenses:,.2f}`\n"
        f"✅ Balance: `${balance:,.2f}`\n"
        f"📈 Savings rate: `{savings_rate:.1f}%`",
        parse_mode='Markdown'
    )
    
    # Category Budgets Breakdown
    conn = get_db(chat_id)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.category, SUM(e.amount) as total, b.amount as budget
        FROM expense e
        LEFT JOIN budget b ON e.category = b.category AND b.month = ? AND b.year = ?
        WHERE strftime('%m', e.date) = ? AND strftime('%Y', e.date) = ?
        GROUP BY e.category
    """, (month, year, str(month).zfill(2), str(year)))
    cats = cursor.fetchall()
    conn.close()

    if cats:
        budget_msg = "\n📂 *Category Budgets:*"
        for cat, total, budget in cats:
            if budget:
                pct = (total / budget) * 100
                bar = get_progress_bar(pct)
                status = "🛑" if pct >= 100 else "⚠️" if pct >= 80 else "🟢"
                budget_msg += f"\n{status} *{cat.title()}*: `{pct:.0f}%` of `${budget:.0f}`\n`{bar}`"
            else:
                budget_msg += f"\n⚪ *{cat.title()}*: `${total:.2f}`"
        await update.message.reply_text(budget_msg, parse_mode='Markdown')

async def insight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    month, year = now.month, now.year
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM income WHERE month=? AND year=?", (month, year))
    income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM expense WHERE strftime('%m', date)=? AND strftime('%Y', date)=?",
                   (str(month).zfill(2), str(year)))
    total_expense = cursor.fetchone()[0]

    cursor.execute("""
        SELECT category, SUM(amount) as total 
        FROM expense 
        WHERE strftime('%m', date)=? AND strftime('%Y', date)=?
        GROUP BY category ORDER BY total DESC LIMIT 1
    """, (str(month).zfill(2), str(year)))
    top = cursor.fetchone()
    conn.close()

    needs_pct = (total_expense / income * 100) if income > 0 else 0
    savings_pct = ((income - total_expense) / income * 100) if income > 0 else 0
    score = min(100, int(savings_pct * 1.5))

    msg = f"✨ *Pulse Intelligence*\n\n"
    msg += f"🏆 Financial Score: `{score}/100`\n\n"
    msg += f"📊 *50/30/20 Check*\n"
    msg += f"Needs: `{needs_pct:.1f}%` (target ≤50%)\n"
    msg += f"Savings: `{savings_pct:.1f}%` (target ≥20%)\n\n"

    if top:
        msg += f"🔥 Biggest expense: *{top[0]}* (`${top[1]:,.2f}`)\n"

    if savings_pct >= 20:
        msg += "\n✅ You're on track with your savings goal!"
    else:
        msg += "\n⚠️ Savings below 20% - consider cutting discretionary spending."

    await update.message.reply_text(msg, parse_mode='Markdown')

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/add [description] [amount] [currency]`\n"
            "Example: `/add eating 20k idr`",
            parse_mode='Markdown'
        )
        return

    tokens = context.args
    chat_id = update.message.chat_id
    amount_local, currency, description = parse_transaction_parts(tokens, chat_id)

    if not amount_local:
        await update.message.reply_text("❌ Couldn't find or parse amount. Example: `/add eating 20k idr`", parse_mode='Markdown')
        return

    amount_usd = convert_to_usd(amount_local, currency)
    description = description if description else 'expense'
    category = guess_category(description)
    today = datetime.now().strftime('%Y-%m-%d')
    chat_id = update.message.chat_id

    # 1. Write to Supabase (Cloud)
    try:
        supabase = get_supabase()
        supabase.table('expense').insert({
            'amount': amount_usd,
            'category': category,
            'description': description,
            'date': today,
            'note': f"Added via bot ({amount_local:,.0f} {currency.upper()})"
        }).execute()
    except Exception as e:
        print(f"Failed to sync to Supabase: {e}")

    # 2. Write to Local DB (for instant bot feedback)
    conn = get_db(chat_id)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO expense (amount, category, description, date, note) VALUES (?, ?, ?, ?, ?)",
        (amount_usd, category, description, today, f"Added via bot ({amount_local:,.0f} {currency.upper()})")
    )
    conn.commit()
    # Budget Alert Logic
    cursor.execute(
        "SELECT amount FROM budget WHERE category = ? AND month = ? AND year = ?",
        (category, datetime.now().month, datetime.now().year)
    )
    budget_row = cursor.fetchone()
    
    alert_msg = ""
    if budget_row:
        budget_amt = budget_row[0]
        # Calculate total spending for this category/month
        cursor.execute(
            """SELECT SUM(amount) FROM expense 
               WHERE category = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?""",
            (category, datetime.now().strftime('%m'), datetime.now().strftime('%Y'))
        )
        total_spent = cursor.fetchone()[0] or 0
        usage_pct = (total_spent / budget_amt) * 100
        
        if usage_pct >= 100:
            alert_msg = f"\n\n🛑 *CRITICAL:* Over budget! (`{usage_pct:.1f}%` of `${budget_amt:.2f}`)"
        elif usage_pct >= 80:
            alert_msg = f"\n\n⚠️ *Warning:* Near budget limit! (`{usage_pct:.1f}%` of `${budget_amt:.2f}`)"

    conn.close()

    await update.message.reply_text(
        f"✅ *Expense added!*\n\n"
        f"📝 {description.capitalize()}\n"
        f"💸 {amount_local:,.0f} {currency.upper()} (≈ `${amount_usd:.2f}`)\n"
        f"🏷️ Category: `{category}`\n"
        f"📅 {today}{alert_msg}",
        parse_mode='Markdown'
    )

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/income [source] [amount] [currency]`\n"
            "Example: `/income salary 5000 usd`",
            parse_mode='Markdown'
        )
        return

    tokens = context.args
    chat_id = update.message.chat_id
    amount_local, currency, source = parse_transaction_parts(tokens, chat_id)

    if not amount_local:
        await update.message.reply_text("❌ Couldn't find or parse amount. Example: `/income salary 5m idr`", parse_mode='Markdown')
        return

    amount_usd = convert_to_usd(amount_local, currency)
    source = source.capitalize() if source else 'Income'
    now = datetime.now()
    month, year = now.month, now.year

    # 1. Write to Supabase (Cloud)
    try:
        supabase = get_supabase()
        supabase.table('income').insert({
            'amount': amount_usd,
            'source': source,
            'month': month,
            'year': year,
            'note': f"Added via bot ({amount_local:,.0f} {currency.upper()})"
        }).execute()
    except Exception as e:
        print(f"Failed to sync to Supabase: {e}")

    # 2. Write to Local DB (for instant bot feedback)
    conn = get_db(chat_id)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO income (amount, source, month, year, note) VALUES (?, ?, ?, ?, ?)",
            (amount_usd, source, month, year, f"Added via bot ({amount_local:,.0f} {currency.upper()})")
        )
    except sqlite3.IntegrityError:
        # User requested additive behavior
        cursor.execute(
            "UPDATE income SET amount = amount + ?, note = note || '\n' || ? WHERE source = ? AND month = ? AND year = ?",
            (amount_usd, f"Added via bot ({amount_local:,.0f} {currency.upper()})", source, month, year)
        )
    
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"💰 *Income recorded!*\n\n"
        f"🏢 Source: *{source}*\n"
        f"💵 {amount_local:,.0f} {currency.upper()} (≈ `${amount_usd:.2f}`)\n"
        f"📅 {now.strftime('%B %Y')}",
        parse_mode='Markdown'
    )

async def clear_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    month, year = now.month, now.year
    chat_id = update.message.chat_id
    
    if not context.args:
        conn = get_db(chat_id)
        cursor = conn.cursor()
        cursor.execute("SELECT category, amount FROM budget WHERE month = ? AND year = ?", (month, year))
        budgets = cursor.fetchall()
        conn.close()

        if not budgets:
            await update.message.reply_text("No active budgets found for this month.")
            return

        msg = "🎯 *Active Budgets for this month:*\n"
        for cat, amt in budgets:
            msg += f"• *{cat.title()}*: `${amt:.2f}`\n"
        msg += "\nTo clear, use: `/clearbudget [category]`"
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    category = context.args[0].lower()
    conn = get_db(chat_id)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM budget WHERE category = ? AND month = ? AND year = ?", (category, month, year))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Budget for *{category.title()}* has been cleared for this month.", parse_mode='Markdown')

async def set_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Requirement: [category] [amount] [currency]
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/setbudget [category] [amount] [currency]`\nEx: `/setbudget food 500k idr`", parse_mode='Markdown')
        return

    try:
        category = context.args[0].lower()
        amount_str = context.args[1]
        currency = context.args[2].upper() if len(context.args) > 2 else "USD"
        
        # Reuse existing amount parsing logic (handles 'k', 'm' etc)
        amount_local = float(re.sub(r'[^0-9.]', '', amount_str.replace('k', '000').replace('m', '000000')))
        
        # Simple currency conversion (matching app.py logic)
        RATES = {"USD": 1.0, "EUR": 0.92, "IDR": 15800}
        rate = RATES.get(currency, 1.0)
        amount_usd = amount_local / rate
        
        now = datetime.now()
        chat_id = update.message.chat_id
        conn = get_db(chat_id)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO budget (category, amount, month, year) VALUES (?, ?, ?, ?)
               ON CONFLICT(category, month, year) DO UPDATE SET amount = EXCLUDED.amount""",
            (category, amount_usd, now.month, now.year)
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"🎯 *Budget Set!*\n"
            f"🏷️ Category: `{category.title()}`\n"
            f"💰 Limit: `{amount_local:,.0f} {currency}` (≈ `${amount_usd:.2f}`)\n"
            f"📅 Period: {now.strftime('%B %Y')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to set budget: {str(e)}")

async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    cursor = conn.cursor()
    # Get last transaction
    cursor.execute("SELECT id, description, amount, date FROM expense ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()
    
    if not last:
        await update.message.reply_text("Nothing to undo!")
        conn.close()
        return

    cursor.execute("DELETE FROM expense WHERE id = ?", (last[0],))
    conn.commit()
    conn.close()
    
    # Try to delete from Supabase too
    try:
        supabase = get_supabase()
        res = supabase.table('expense').select('id').eq('amount', last[2]).eq('description', last[1]).eq('date', last[3]).order('id', desc=True).limit(1).execute()
        if res.data:
            supabase.table('expense').delete().eq('id', res.data[0]['id']).execute()
    except Exception as e:
        print(f"Failed to undo expense from Supabase: {e}")
        
    await update.message.reply_text(f"🗑️ *Expense Deleted*\n`{last[1]}` - `${last[2]:.2f}`", parse_mode='Markdown')

async def undo_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    cursor = conn.cursor()
    # Get last income
    cursor.execute("SELECT id, source, amount, month, year FROM income ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()
    
    if not last:
        await update.message.reply_text("No income to undo!")
        conn.close()
        return

    cursor.execute("DELETE FROM income WHERE id = ?", (last[0],))
    conn.commit()
    conn.close()
    
    # Supabase undo
    try:
        supabase = get_supabase()
        res = supabase.table('income').select('id').eq('amount', last[2]).eq('source', last[1]).eq('month', last[3]).eq('year', last[4]).order('id', desc=True).limit(1).execute()
        if res.data:
            supabase.table('income').delete().eq('id', res.data[0]['id']).execute()
    except Exception as e:
        print(f"Failed to undo income from Supabase: {e}")

    await update.message.reply_text(f"🗑️ *Income Deleted*\n`{last[1]}` - `${last[2]:.2f}`", parse_mode='Markdown')

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    cursor = conn.cursor()
    cursor.execute("SELECT date, description, amount, category FROM expense ORDER BY date DESC, id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No transactions found.")
        return

    msg = "📋 *Recent Transactions*\n\n"
    for date, desc, amt, cat in rows:
        msg += f"• `{date}` | *{desc}*\n  `${amt:.2f}` ({cat})\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def recurring_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all recurring rules."""
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    rows = conn.execute(
        "SELECT id, description, amount, category, day_of_month, is_active FROM recurring_config ORDER BY day_of_month"
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "🔁 No recurring rules yet.\n"
            "Add one with: `/addrecurring Netflix 180k idr 1`",
            parse_mode='Markdown'
        )
        return

    msg = "🔁 *Recurring Rules*\n\n"
    for rid, desc, amt, cat, day, active in rows:
        status = "🟢" if active else "⏸"
        msg += f"{status} *#{rid}* {desc}\n"
        msg += f"   {fmt(amt)} · {cat} · every day {day}\n\n"
    msg += "Delete: `/delrecurring [id]`"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def add_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a recurring rule. Usage: /addrecurring [desc] [amt] [curr] [day]"""
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: `/addrecurring [desc] [amt] [curr] [day]`\n"
            "_e.g. `/addrecurring Netflix 180k idr 1`_",
            parse_mode='Markdown'
        )
        return

    # Last arg = day if numeric, else default 1
    if args[-1].isdigit():
        day = int(args[-1])
        remaining = args[:-1]
    else:
        day = 1
        remaining = args

    amount_local, currency, description = parse_transaction_parts(remaining)
    if not amount_local or not description:
        await update.message.reply_text("❌ Couldn't parse. Try: `/addrecurring Kos 1.5m idr 1`", parse_mode='Markdown')
        return

    if not (1 <= day <= 28):
        await update.message.reply_text("❌ Day must be 1–28.")
        return

    amount_usd = convert_to_usd(amount_local, currency)
    category = guess_category(description)
    chat_id = update.message.chat_id

    conn = get_db(chat_id)
    conn.execute(
        "INSERT INTO recurring_config (amount, category, description, day_of_month, is_active) VALUES (?,?,?,?,1)",
        (amount_usd, category, description, day)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ *Recurring rule added!*\n"
        f"📝 {description}\n"
        f"💸 {fmt(amount_usd)} · {category}\n"
        f"📅 Triggers every month on day {day}",
        parse_mode='Markdown'
    )


async def del_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a recurring rule by ID."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: `/delrecurring [id]`\nGet IDs from `/recurring`", parse_mode='Markdown')
        return

    rid = int(context.args[0])
    chat_id = update.message.chat_id
    conn = get_db(chat_id)
    row = conn.execute("SELECT description FROM recurring_config WHERE id=?", (rid,)).fetchone()
    if not row:
        await update.message.reply_text(f"❌ No rule with ID {rid}.")
        conn.close()
        return
    conn.execute("DELETE FROM recurring_config WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ Deleted recurring rule: *{row[0]}*", parse_mode='Markdown')


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages: bank email paste or natural language expense."""
    text = update.message.text
    income_keywords = ['income', 'salary', 'wage', 'gaji', 'wages', 'pemasukan']

    # --- Try Smart Parse (bank email) first ---
    parsed = intelligence.parse_bank_email(text)
    if parsed:
        raw_currency = parsed.get('amount_currency', 'IDR')
        amount_usd = parsed['amount'] / CURRENCY_RATES.get(raw_currency, 17000.0)
        category = parsed['category']
        description = parsed['description']
        tx_date = parsed.get('date') or date.today().isoformat()
        tx_type = parsed.get('tx_type', 'Bank Transaction')
        lang = parsed.get('lang', 'id')
        chat_id = update.message.chat_id

        # Save directly as Draft
        conn = get_db(chat_id)
        conn.execute(
            "INSERT INTO drafts (amount, description, date, category, source) VALUES (?,?,?,?,?)",
            (amount_usd, description, tx_date, category, f"telegram_bot ({tx_type})")
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"🏦 *Bank notification detected!*\n\n"
            f"📝 Vendor: *{description}*\n"
            f"💸 Amount: *{fmt(amount_usd)}*\n"
            f"📅 Date: {tx_date}\n"
            f"🏷️ Category: {category}\n"
            f"🔖 Type: {tx_type}\n\n"
            f"✅ Saved as *Draft* - review it on the dashboard to approve.",
            parse_mode='Markdown'
        )
        return

    # --- Fall back: natural language expense/income ---
    text_lower = text.lower()
    if any(re.search(r'\d', word) for word in text_lower.split()):
        context.args = text_lower.split()
        if any(kw in text_lower for kw in income_keywords):
            await add_income(update, context)
        else:
            await add_expense(update, context)
    else:
        await update.message.reply_text(
            "I didn't understand that. Try:\n"
            "• `/add alfamart 25k idr`\n"
            "• `/income salary 5m idr`\n"
            "• Or paste a BCA email notification directly!\n"
            "• `/summary` or `/insight`",
            parse_mode='Markdown'
        )

async def send_monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not chat_id:
        return
    now = datetime.now()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM income WHERE month=? AND year=?", (now.month, now.year))
    income = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM expense WHERE strftime('%m', date)=? AND strftime('%Y', date)=?",
                   (str(now.month).zfill(2), str(now.year)))
    expenses = cursor.fetchone()[0]
    conn.close()
    balance = income - expenses
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📅 *Monthly Wrap-up - {now.strftime('%B %Y')}*\n\n"
             f"💰 Income: `${income:,.2f}`\n"
             f"💸 Expenses: `${expenses:,.2f}`\n"
             f"✅ Balance: `${balance:,.2f}`",
        parse_mode='Markdown'
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("unlink", unlink))
    app.add_handler(CommandHandler("currency", set_currency))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("insight", insight))
    app.add_handler(CommandHandler("add", add_expense))
    app.add_handler(CommandHandler("income", add_income))
    app.add_handler(CommandHandler("add_income", add_income))
    app.add_handler(CommandHandler("wage", add_income))
    app.add_handler(CommandHandler("clearbudget", clear_budget))
    app.add_handler(CommandHandler("setbudget", set_budget))
    app.add_handler(CommandHandler("undo", undo))
    app.add_handler(CommandHandler("undo_income", undo_income))
    app.add_handler(CommandHandler("history", history))
    # --- New: Recurring Manager ---
    app.add_handler(CommandHandler("recurring", recurring_list))
    app.add_handler(CommandHandler("addrecurring", add_recurring))
    app.add_handler(CommandHandler("delrecurring", del_recurring))
    # --- Smart Parse lives in handle_text ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Pulsar bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()