import getpass
from app import create_app, db
from app.models import User


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        username = input("Admin username: ").strip()
        if not username:
            raise SystemExit("Username is required")
        existing = User.query.filter_by(username=username).first()
        if existing:
            raise SystemExit("User already exists")
        full_name = input("Full name: ").strip() or username
        password = getpass.getpass("Password: ")
        password2 = getpass.getpass("Repeat password: ")
        if password != password2:
            raise SystemExit("Passwords do not match")
        if len(password) < 8:
            raise SystemExit("Password must be at least 8 characters")
        user = User(username=username, full_name=full_name, role="admin", is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("Admin user created")


if __name__ == "__main__":
    main()
