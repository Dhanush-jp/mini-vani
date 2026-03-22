"""
Populate the database with demo users, subjects, grades, and attendance.

Run from the backend folder:
    python seed.py

Requires MySQL (or your configured DB) to be running and DATABASE_URL / config to match.
"""

from seed_data import seed

if __name__ == "__main__":
    seed()
