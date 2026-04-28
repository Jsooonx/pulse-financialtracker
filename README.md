# Pulse - Personal Finance Intelligence

> *"Know your financial rhythm."*

Pulse is a proactive personal finance application that goes beyond passive tracking. It actively learns your spending patterns, detects anomalies, and forecasts future trends to give you complete control over your financial health.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.1-green?style=flat-square)
![Anime.js](https://img.shields.io/badge/Anime.js-3.2-orange?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-3.41-blue?style=flat-square)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4-blue?style=flat-square)

---

![Pulse Dashboard](static/images/landingpage.png)

---

## High-Craft Micro-interactions

Pulse features a bespoke animation system powered by **Anime.js**, designed to provide a premium, "Apple-inspired" tactile experience:

- **Metric Count-Up**: Financial figures animate smoothly from zero to their target value on page load.
- **Magnetic Grid**: Summary cards respond to your cursor with a subtle spring-based tilt and scale effect.
- **Staggered Entry**: All layout components, lists, and transaction items slide into view with a sequential, cinematic flow.
- **Cinematic Modals**: Ultra-smooth scaling and opacity transitions for all interaction dialogs.
- **Contextual Page Transitions**: Staggered exit animations when navigating between months or categories to prevent harsh "hard reloads."
- **Tactile Inputs**: Interactive focus states for form fields with subtle scaling and glow effects.

---

## Hosting & Free Tier Limitations

Pulse is designed to be highly interactive, especially with its **Telegram Bot (Pulsar)**. Running a bot 24/7 requires a continuous background process (polling).

> [!IMPORTANT]
> **Why Local Setup is Recommended:**
> Most free hosting providers (e.g., PythonAnywhere, Render, or Railway free tiers) often restrict long-running background tasks or outbound internet access, making it difficult to keep the Telegram bot alive 24/7 for free. 
> 
> For the best experience without costs, **running Pulse locally on your machine** or an always-on home server (like a Raspberry Pi) is the most reliable way to maintain your "financial rhythm."

---

## Local Setup Guide

Follow these steps to get Pulse running on your own computer:

### 1. Prerequisites
- **Python 3.10+** installed.
- A **Telegram Bot Token** (Get it from [@BotFather](https://t.me/botfather)).

### 2. Installation
1.  **Clone the repository** to your local machine.
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

### 3. Environment Configuration
Create a file named `.env` in the root directory and add your credentials:
```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_personal_chat_id # Optional for auto-summaries
```

### 4. Database Initialization
Initialize the database. You can optionally populate it with sample data if you want to test the dashboard immediately:
```bash
python -c "from app import init_db; init_db()"
python seed.py  # Optional: Only run this if you want dummy data for testing
```

### 5. Running the Application
To have the full Pulse experience, you need to run **two** processes simultaneously:

**Terminal A: The Web Dashboard**
```bash
python app.py
```
*Access your dashboard at `http://127.0.0.1:5000`*

**Terminal B: The Telegram Bot**
```bash
python bot.py
```
*You can now chat with your bot to log expenses!*

---

## Premium Features

- **Apple-inspired "Digital Editorial" Aesthetic**: A bespoke Bento Grid layout featuring a "Teal Forest & Vanilla Latte" palette, designed for maximum clarity and high-end feel.
- **Pulse Intelligence**: A proactive layer that evaluates your finances against the **50/30/20 benchmark**, detects anomalies, and provides dynamic textual insights.
- **Cashflow Flow (Sankey)**: A high-fidelity visualization mapping your income sources directly to your expenses and savings.
- **Smart Paste (AI-Powered Stage)**: Paste raw bank emails or free-text messages directly into the dashboard. Pulse extracts amounts, dates, and categories with zero external API calls.
- **Recurring Manager**: Effortlessly automate monthly subscriptions, rent, or utilities.
- **Multi-Currency Engine**: Native support for **USD ($)**, **EUR (€)**, and **IDR (Rp)** with localized formatting and accurate internal conversion.
- **Professional Reporting**: Export beautifully styled **Excel (.xlsx)** reports with auto-formatting or clean **CSV** for data nerds.

---

## Telegram Bot (Pulsar) Commands

- `/start` - Introduction and help.
- `/add [desc] [amount] [currency]` - Quick log (e.g., `/add coffee 5 usd`).
- `/summary` - Monthly financial overview with budget progress bars.
- `/history` - View the last 10 transactions.
- `/undo` - Remove the very last transaction added.
- `/setbudget [category] [amount] [currency]` - Set a monthly spending target.
- `/insight` - Real-time Pulse Intelligence report.

---
*Created by Jsooonx for Portfolio | 2026*
