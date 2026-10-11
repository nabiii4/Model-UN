"""Load the example delegates and check the default settings.

Run:  python scripts/seed.py
Safe to run twice: it updates the 9 examples by their stable ids instead of making copies.
It never deletes members, drawings, or settings that editors changed.
"""
import _path  # noqa: F401

from app import create_app
from extensions import db
from logic.seeding import count_seeds, seed_all


def main():
    app = create_app()
    with app.app_context():
        n = seed_all()
        print(f"Seeded {n} example delegates ({count_seeds()} in the database). Default settings OK.")
        db.session.remove()


if __name__ == "__main__":
    main()
