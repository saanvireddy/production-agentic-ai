"""Seed the structured HR tables and the admin user.

Employee records are generated from a fixed random seed, so every environment
(laptop, CI, Kubernetes) gets exactly the same data and the same answers.
All names are synthetic.
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from app.auth.security import hash_password
from app.config import get_settings
from app.database.connection import get_conn

logger = logging.getLogger(__name__)

DEPARTMENTS = [
    # name, location, budget, head, headcount, (role, base_salary) choices
    (
        "Engineering",
        "Atlanta",
        9_500_000,
        "Priya Raman",
        48,
        [
            ("Software Engineer", 125_000),
            ("Senior Software Engineer", 155_000),
            ("Staff Engineer", 190_000),
            ("DevOps Engineer", 135_000),
            ("Engineering Manager", 175_000),
        ],
    ),
    (
        "Data Science",
        "Austin",
        3_200_000,
        "Marcus Webb",
        14,
        [("Data Scientist", 135_000), ("ML Engineer", 150_000), ("Data Analyst", 95_000)],
    ),
    (
        "Finance",
        "Chicago",
        2_100_000,
        "Elena Petrova",
        16,
        [("Financial Analyst", 88_000), ("Senior Accountant", 98_000), ("Controller", 145_000)],
    ),
    (
        "Sales",
        "Denver",
        4_000_000,
        "Jordan Ellis",
        30,
        [("Account Executive", 95_000), ("Sales Development Rep", 62_000), ("Sales Manager", 130_000)],
    ),
    (
        "Marketing",
        "Austin",
        1_800_000,
        "Hannah Brooks",
        12,
        [("Marketing Specialist", 72_000), ("Content Strategist", 78_000), ("Marketing Manager", 115_000)],
    ),
    (
        "People Operations",
        "Atlanta",
        900_000,
        "Samuel Okafor",
        8,
        [("HR Generalist", 70_000), ("Recruiter", 75_000), ("People Ops Manager", 110_000)],
    ),
    (
        "Security",
        "Remote",
        1_500_000,
        "Aiko Tanaka",
        9,
        [("Security Engineer", 145_000), ("Security Analyst", 105_000)],
    ),
]

FIRST = [
    "Alex",
    "Sam",
    "Taylor",
    "Jordan",
    "Casey",
    "Riley",
    "Morgan",
    "Avery",
    "Quinn",
    "Jamie",
    "Drew",
    "Reese",
    "Rowan",
    "Parker",
    "Skyler",
    "Emerson",
    "Hayden",
    "Kendall",
    "Logan",
    "Micah",
    "Noel",
    "Aria",
    "Dev",
    "Ravi",
    "Mei",
    "Omar",
    "Lina",
    "Tomas",
    "Ines",
    "Kofi",
]
LAST = [
    "Nguyen",
    "Patel",
    "Garcia",
    "Kim",
    "Smith",
    "Johnson",
    "Okoro",
    "Silva",
    "Chen",
    "Kowalski",
    "Haddad",
    "Novak",
    "Rossi",
    "Mendes",
    "Singh",
    "Larsen",
    "Moreau",
    "Ito",
    "Brennan",
    "Duarte",
]
LOCATIONS = ["Atlanta", "Austin", "Chicago", "Denver", "Remote"]


def generate_employees(seed: int = 42) -> list[tuple]:
    rng = random.Random(seed)
    rows = []
    today = date(2026, 9, 1)
    for dept, home, _budget, _head, headcount, roles in DEPARTMENTS:
        for _ in range(headcount):
            role, base = rng.choice(roles)
            exp = rng.randint(0, 15)
            salary = round(base * (1 + exp * 0.02) * rng.uniform(0.92, 1.08), -2)
            location = home if rng.random() < 0.7 else rng.choice(LOCATIONS)
            hire = today - timedelta(days=int(min(exp, 10) * 365 * rng.uniform(0.3, 1.0)) + rng.randint(30, 300))
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            rows.append((name, dept, role, salary, location, exp, hire))
    return rows


def seed_hr_data(force: bool = False) -> int:
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM employees").fetchone()["n"]
        if existing and not force:
            logger.info("employees already seeded (%s rows)", existing)
            return existing
        conn.execute("TRUNCATE employees, departments RESTART IDENTITY CASCADE")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO departments (name, location, budget, head) VALUES (%s, %s, %s, %s)",
                [(d[0], d[1], d[2], d[3]) for d in DEPARTMENTS],
            )
            rows = generate_employees()
            cur.executemany(
                "INSERT INTO employees (name, department, role, salary, location, experience_years, hire_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
        conn.commit()
        logger.info("seeded %s employees", len(rows))
        return len(rows)


def seed_admin_user() -> None:
    s = get_settings()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (%s, %s, 'admin') "
            "ON CONFLICT (username) DO NOTHING",
            (s.admin_username, hash_password(s.admin_password.get_secret_value())),
        )
        conn.commit()


if __name__ == "__main__":
    from app.database.connection import apply_schema

    logging.basicConfig(level=logging.INFO)
    apply_schema()
    seed_admin_user()
    print(f"employees: {seed_hr_data(force=True)}")
