"""One-time setup: creates DB tables and sets the app password."""

import sys
import bcrypt
from app import create_app
from models import db, User

PASSWORD_ARG_HELP = "Usage: python init_db.py <password>"


def main():
    if len(sys.argv) < 2:
        print(PASSWORD_ARG_HELP)
        sys.exit(1)

    password = sys.argv[1]

    app = create_app()
    with app.app_context():
        db.create_all()

        existing = User.query.first()
        if existing:
            print("User already exists. Updating password.")
            existing.password_hash = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt()
            ).decode()
        else:
            print("Creating user.")
            user = User(
                password_hash=bcrypt.hashpw(
                    password.encode(), bcrypt.gensalt()
                ).decode()
            )
            db.session.add(user)

        db.session.commit()
        print("Done. Database initialized.")


if __name__ == "__main__":
    main()
