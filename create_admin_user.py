"""
Script to create an admin user for the authentication system.
Run with: python create_admin_user.py
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')
load_dotenv()

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app import db, auth

def create_admin_user(username: str, password: str):
    """Create an admin user with the given username and password."""
    try:
        # Check if user already exists
        existing_user = db.get_user_by_username(username)
        if existing_user:
            print(f"User '{username}' already exists!")
            return False

        # Hash password
        password_hash = auth.hash_password(password)

        # Create user
        user_id = db.create_user(username, password_hash)

        print(f"✅ Admin user created successfully!")
        print(f"   Username: {username}")
        print(f"   User ID: {user_id}")
        print(f"\nYou can now log in at http://localhost:8000/")
        return True

    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Create Admin User for Tieout Authentication")
    print("=" * 60)
    print()

    # Get username and password from user input
    username = input("Enter username (default: admin): ").strip() or "admin"
    password = input("Enter password (default: admin123): ").strip() or "admin123"

    print()
    create_admin_user(username, password)
