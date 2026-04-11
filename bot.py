import os
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DB_PATH = os.path.join(os.path.dirname(__file__), 'pulse.db')

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



CURRENCY_RATES = {'idr': 1/17000, 'usd': 1, 'eur': 1.08}

def get_db():
    return sqlite3.connect(DB_PATH)

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
    rate = CURRENCY_RATES.get(currency, 1)
    return amount * rate

def parse_transaction_parts(tokens):
    """Shared helper to parse amount, currency and description/source from tokens."""
    amount_raw = None
    currency = 'usd'
    other_tokens = []

    for token in tokens:
        if re.search(r'\d', token):
            amount_raw = token
        elif token.lower() in CURRENCY_RATES:
            currency = token.lower()
        else:
            other_tokens.append(token)
    
    amount_local = parse_amount(amount_raw) if amount_raw else None
    description = ' '.join(other_tokens) if other_tokens else ''
    
    return amount_local, currency, description

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "⚡ *Welcome to Pulsar* — Your Pulse Finance Intelligence\n\n"
        "I'm here to help you track and understand your financial rhythm. Here is how you can use me:\n\n"
        
        "📝 *Recording Transactions*\n"
        "• `/add [desc] [amt] [curr]` - Log an expense\n"
        "  _Ex: `/add Starbucks 55k idr`_\n"
        "• `/income [src] [amt] [curr]` - Log income\n"
        "  _Ex: `/income Salary 5000 usd`_\n\n"
        
        "📊 *Analysis & Overview*\n"
        "• `/summary` - View this month's balance and budget progress bars.\n"
        "• `/insight` - Get your Pulse financial score and 50/30/20 breakdown.\n"
        "• `/history` - See your last 10 transactions.\n\n"
        
        "⚙️ *Management*\n"
        "• `/undo` - Accidentally added something? Delete the very last entry.\n"
        "• `/setbudget [cat] [amt] [curr]` - Set a monthly spending target.\n"
        "  _Ex: `/setbudget food 200 usd`_\n"
        "• `/clearbudget` - Manage your monthly spending targets.\n\n"
        
        "💡 *Tip:* You can also just type naturally like `'buy lunch 30k idr'` and I will try to understand it!"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    month, year = now.month, now.year
    conn = get_db()
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
    conn = get_db()
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
    conn = get_db()
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
        msg += "\n⚠️ Savings below 20% — consider cutting discretionary spending."

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
    amount_local, currency, description = parse_transaction_parts(tokens)

    if not amount_local:
        await update.message.reply_text("❌ Couldn't find or parse amount. Example: `/add eating 20k idr`", parse_mode='Markdown')
        return

    amount_usd = convert_to_usd(amount_local, currency)
    description = description if description else 'expense'
    category = guess_category(description)
    today = datetime.now().strftime('%Y-%m-%d')

    conn = get_db()
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
    amount_local, currency, source = parse_transaction_parts(tokens)

    if not amount_local:
        await update.message.reply_text("❌ Couldn't find or parse amount. Example: `/income salary 5m idr`", parse_mode='Markdown')
        return

    amount_usd = convert_to_usd(amount_local, currency)
    source = source.capitalize() if source else 'Income'
    now = datetime.now()
    month, year = now.month, now.year

    conn = get_db()
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
    
    if not context.args:
        conn = get_db()
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
    conn = get_db()
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
        conn = get_db()
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
    conn = get_db()
    cursor = conn.cursor()
    # Get last transaction
    cursor.execute("SELECT id, description, amount FROM expense ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()
    
    if not last:
        await update.message.reply_text("Nothing to undo!")
        return

    cursor.execute("DELETE FROM expense WHERE id = ?", (last[0],))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"🗑️ *Transaction Deleted*\n`{last[1]}` - `${last[2]:.2f}`", parse_mode='Markdown')

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
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

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    income_keywords = ['income', 'salary', 'wage', 'gaji', 'wages', 'pemasukan']
    
    if any(re.search(r'\d', word) for word in text.split()):
        context.args = text.split()
        if any(kw in text for kw in income_keywords):
            await add_income(update, context)
        else:
            await add_expense(update, context)
    else:
        await update.message.reply_text(
            "I didn't understand that. Try:\n"
            "• `/add coffee 5 usd`\n"
            "• `/income salary 5000 usd`\n"
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
        text=f"📅 *Monthly Wrap-up — {now.strftime('%B %Y')}*\n\n"
             f"💰 Income: `${income:,.2f}`\n"
             f"💸 Expenses: `${expenses:,.2f}`\n"
             f"✅ Balance: `${balance:,.2f}`",
        parse_mode='Markdown'
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("insight", insight))
    app.add_handler(CommandHandler("add", add_expense))
    app.add_handler(CommandHandler("income", add_income))
    app.add_handler(CommandHandler("wage", add_income))
    app.add_handler(CommandHandler("clearbudget", clear_budget))
    app.add_handler(CommandHandler("setbudget", set_budget))
    app.add_handler(CommandHandler("undo", undo))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Pulsar bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()

if __name__ == '__main__':
    main()