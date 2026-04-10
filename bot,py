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

CATEGORY_KEYWORDS = {
    'food': ['eating', 'food', 'lunch', 'dinner', 'breakfast', 'makan', 'snack', 'coffee', 'drink'],
    'transport': ['transport', 'grab', 'gojek', 'taxi', 'bus', 'fuel', 'gas', 'parking'],
    'shopping': ['shopping', 'clothes', 'shirt', 'shoes', 'buy', 'beli'],
    'entertainment': ['entertainment', 'movie', 'game', 'netflix', 'spotify'],
    'health': ['health', 'medicine', 'doctor', 'gym', 'pharmacy'],
    'bills': ['bills', 'electricity', 'water', 'internet', 'phone', 'rent'],
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Welcome to Pulsar* — your Pulse finance assistant.\n\n"
        "Here's what I can do:\n"
        "/summary — Monthly overview\n"
        "/insight — Pulse Intelligence\n"
        "/add [desc] [amount] [currency] — Add expense\n\n"
        "Example: `/add eating 20k idr`",
        parse_mode='Markdown'
    )

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
        f"📊 *Summary — {now.strftime('%B %Y')}*\n\n"
        f"💰 Income: `${income:,.2f}`\n"
        f"💸 Expenses: `${expenses:,.2f}`\n"
        f"✅ Balance: `${balance:,.2f}`\n"
        f"📈 Savings rate: `{savings_rate:.1f}%`",
        parse_mode='Markdown'
    )

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

    text = ' '.join(context.args)
    tokens = text.split()

    amount_raw = None
    currency = 'usd'
    desc_tokens = []

    for token in tokens:
        if re.search(r'\d', token):
            amount_raw = token
        elif token.lower() in CURRENCY_RATES:
            currency = token.lower()
        else:
            desc_tokens.append(token)

    if not amount_raw:
        await update.message.reply_text("❌ Couldn't find an amount. Example: `/add eating 20k idr`", parse_mode='Markdown')
        return

    amount_local = parse_amount(amount_raw)
    if not amount_local:
        await update.message.reply_text("❌ Invalid amount format.", parse_mode='Markdown')
        return

    amount_usd = convert_to_usd(amount_local, currency)
    description = ' '.join(desc_tokens) if desc_tokens else 'expense'
    category = guess_category(description)
    today = datetime.now().strftime('%Y-%m-%d')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO expense (amount, category, description, date, note) VALUES (?, ?, ?, ?, ?)",
        (amount_usd, category, description, today, f"Added via Pulsar bot ({amount_local:,.0f} {currency.upper()})")
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ *Expense added!*\n\n"
        f"📝 {description.capitalize()}\n"
        f"💸 {amount_local:,.0f} {currency.upper()} (≈ `${amount_usd:.2f}`)\n"
        f"🏷️ Category: `{category}`\n"
        f"📅 {today}",
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(re.search(r'\d', word) for word in text.split()):
        context.args = text.split()
        await add_expense(update, context)
    else:
        await update.message.reply_text(
            "I didn't understand that. Try:\n"
            "• `/add eating 20k idr`\n"
            "• `/summary`\n"
            "• `/insight`",
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Pulsar bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()