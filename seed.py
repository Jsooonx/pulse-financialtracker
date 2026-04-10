"""Seed script — generates 3+ months of demo data for Pulse."""

import sqlite3
import os
import random
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pulse.db")


def seed():
    """Populate database with realistic English financial demo data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM income")
    cursor.execute("DELETE FROM expense")

    # --- Income Data (4 months) ---
    today = date.today()
    months = []
    for i in range(4):
        d = today.replace(day=1) - timedelta(days=30 * i)
        months.append((d.month, d.year))

    income_sources = [
        ("Salary", 5000),
        ("Freelance", 1200),
    ]

    for month, year in months:
        for source, base_amount in income_sources:
            variation = random.randint(-200, 500)
            amount = base_amount + variation
            cursor.execute(
                "INSERT OR REPLACE INTO income (amount, source, month, year, note) VALUES (?, ?, ?, ?, ?)",
                (amount, source, month, year, f"{source} income for {month}/{year}"),
            )

    # --- Expense Data ---
    expense_templates = {
        "food": [
            ("Lunch with colleagues", 15, 30),
            ("Coffee bean", 5, 10),
            ("Dinner at Italian rest.", 40, 80),
            ("Grocery shopping", 50, 120),
            ("Mc Donald's", 10, 25),
            ("Taco Bell", 8, 20),
            ("Steakhouse", 60, 150),
            ("Office snacks", 10, 20),
            ("Takeout pizza", 20, 40),
            ("Smoothie bowl", 10, 15),
        ],
        "transport": [
            ("Uber to office", 12, 25),
            ("Lyft ride home", 15, 30),
            ("Gas station", 30, 60),
            ("Toll bridge", 5, 15),
            ("Public transit pass", 50, 50),
            ("Parking fee", 10, 20),
        ],
        "bills": [
            ("Electricity bill", 80, 150),
            ("Water utility", 40, 70),
            ("Internet fiber", 60, 80),
            ("Mobile data plan", 30, 60),
            ("Netflix subscription", 15, 15),
            ("Spotify", 10, 10),
        ],
        "entertainment": [
            ("Movie tickets", 15, 30),
            ("Cinema snacks", 10, 25),
            ("Steam game purchase", 20, 70),
            ("Bowling night", 30, 50),
            ("Concert ticket", 100, 300),
        ],
        "shopping": [
            ("Clothing", 40, 150),
            ("Electronics", 100, 500),
            ("Home decor", 30, 100),
            ("Amazon order", 20, 200),
            ("Gifts", 50, 150),
        ],
        "health": [
            ("Pharmacy - Cold medicine", 15, 35),
            ("Vitamins", 20, 50),
            ("Dentist checkup", 100, 300),
            ("Gym membership", 50, 50),
        ],
        "education": [
            ("Online course", 10, 100),
            ("Textbooks", 40, 120),
            ("Newsletter sub", 5, 15),
        ],
        "others": [
            ("Charity donation", 20, 100),
            ("Haircut", 30, 60),
            ("Laundry service", 15, 40),
            ("Pet supplies", 30, 80),
        ],
    }

    # Category frequency weights
    category_weights = {
        "food": (15, 25),
        "transport": (8, 15),
        "bills": (4, 6),
        "entertainment": (2, 5),
        "shopping": (3, 6),
        "health": (0, 3),
        "education": (0, 2),
        "others": (2, 4),
    }

    for month, year in months:
        if month == 12:
            days_in_month = 31
        else:
            next_month = date(year + (month // 12), (month % 12) + 1, 1)
            days_in_month = (next_month - timedelta(days=1)).day

        for category, templates in expense_templates.items():
            min_count, max_count = category_weights[category]
            count = random.randint(min_count, max_count)

            for _ in range(count):
                template = random.choice(templates)
                desc, min_amt, max_amt = template
                amount = random.randint(min_amt, max_amt)
                day = random.randint(1, days_in_month)
                expense_date = date(year, month, day).isoformat()

                cursor.execute(
                    "INSERT INTO expense (amount, category, description, date) VALUES (?, ?, ?, ?)",
                    (amount, category, desc, expense_date),
                )

    conn.commit()
    conn.close()

    print("✅ Seed data successfully added!")
    print(f"   📅 {len(months)} months of data")

    # Print summary
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    income_count = cursor.execute("SELECT COUNT(*) FROM income").fetchone()[0]
    expense_count = cursor.execute("SELECT COUNT(*) FROM expense").fetchone()[0]
    print(f"   💰 {income_count} income entries")
    print(f"   💸 {expense_count} expense entries")
    conn.close()


if __name__ == "__main__":
    seed()
