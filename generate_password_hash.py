"""
generate_password_hash.py
--------------------------
One-off helper: generates a bcrypt password hash to paste into
auth_config.yaml. streamlit-authenticator stores hashed passwords, never
plain text, so you can't just type your password directly into the YAML.

Run:
    python generate_password_hash.py

It will ask you to type a password (hidden input), then print the hash
to copy into auth_config.yaml's `password:` field for that user.
"""

import getpass

import bcrypt

if __name__ == "__main__":
    password = getpass.getpass("Enter the password to hash: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords didn't match — try again.")
    else:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        print("\nPaste this into auth_config.yaml as that user's `password:` value:\n")
        print(hashed)
