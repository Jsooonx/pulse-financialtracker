# Pulse - Personal Finance Intelligence

> *"Know your financial rhythm."*

Pulse is a proactive personal finance application that goes beyond passive tracking. It actively learns your spending patterns, detects anomalies, and forecasts future trends to give you complete control over your financial health.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.1-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-3.41-blue?style=flat-square)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4-blue?style=flat-square)

---

## Key Upgrades in Pulse

-   **Multi-Currency Engine**: Full support for **USD ($)**, **EUR (€)**, and **IDR (Rp)**. All data is stored in a USD base for consistency, with dynamic conversion and localized formatting for both display and input.
-   **Drafts Inbox (Telegram Ready)**: A built-in staging area for incoming transactions. Integrated specifically for Telegram Bot/OCR inputs, allowing you to review, categorize, and approve data before it hits your main dashboard.
-   **6-Month Spending Trend**: A high-fidelity line chart to visualize Income vs. Expense history, helping you track your saving rate over half a year.
-   **Local Intelligence (Categorization)**: A keyword-based engine that automatically suggests categories (Food, Health, Transport, etc.) for incoming transactions without needing external APIs.
-   **Premium "Teal Forest" Aesthetic**: A refined UI/UX using a tailored "Teal Forest & Vanilla Latte" color palette, custom SVG icons, and smooth interactive components.

---

## Portfolio Write-up

**The Problem:**
Traditional trackers are passive data dumps. Users often fail to notice gradual spending increases or sudden spikes until the damage is done.

**The Pulse Solution:**
We injected an Intelligence Layer using classical statistical models to make finance management proactive:
-   **Moving Averages**: Smooths out transaction volatility to reveal true spending trends.
-   **Linear Regression**: Forecasts upcoming category spending based on history.
-   **Z-Score Anomaly Detection**: Automatically flags transactions where $Z > 2.0$ as "Spikes," alerting the user to investigate unusual activity.
-   **50/30/20 Rule Engine**: Real-time measurement of *Needs*, *Wants*, and *Savings* with a dynamic financial health score.

---

## Tech Stack

-   **Backend**: Python / Flask (Restful API Ready)
-   **Database**: SQLite (Row-factory optimized, PRAGMA foreign keys)
-   **Frontend**: HTML5, Vanilla CSS3 (Custom Design System with Variables), Vanilla JS
-   **Visualization**: Chart.js (Line & Doughnut distributions)
-   **Intelligence**: Standard Deviation / Z-Score Anomaly Detection, Linear Regression Forecasting

---

## Getting Started

1.  **Clone the repository**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Initialize & Seed Data**:
    ```bash
    python -c "from app import init_db; init_db()"
    python seed.py
    ```
4.  **Run Pulse**:
    ```bash
    python app.py
    ```
5.  Open `http://127.0.0.1:5000` in your browser.

---
*Created by Jsooonx for Portfolio | 2026*
