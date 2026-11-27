import argparse
from app.sync_db import get_sync_db
from app.utils.crypto import encrypt_cookie


def add_or_update_account(name: str, raw_cookie: str, proxy_url: str | None = None):
    encrypted_cookie = encrypt_cookie(raw_cookie.strip())

    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM linkedin_accounts WHERE account_name = %s",
                (name,),
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    """
                    UPDATE linkedin_accounts
                    SET li_at_cookie = %s, proxy_url = %s, status = 'ACTIVE'
                    WHERE account_name = %s
                    """,
                    (encrypted_cookie, proxy_url, name),
                )
                print(f"Updated existing account [{name}] and reset status to ACTIVE.")
            else:
                cur.execute(
                    """
                    INSERT INTO linkedin_accounts (account_name, li_at_cookie, proxy_url, status)
                    VALUES (%s, %s, %s, 'ACTIVE')
                    """,
                    (name, encrypted_cookie, proxy_url),
                )
                print(f"Added new encrypted account [{name}] to the pool.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Encrypt and store a LinkedIn li_at cookie.")
    parser.add_argument("--name", required=True, help="Account label (e.g., college_acc_1)")
    parser.add_argument("--cookie", required=True, help="Raw li_at cookie value from DevTools")
    parser.add_argument("--proxy", default=None, help="Optional proxy URL (http://user:pass@ip:port)")

    args = parser.parse_args()
    add_or_update_account(args.name, args.cookie, args.proxy)