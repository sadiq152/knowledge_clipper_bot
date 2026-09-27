import instaloader

USERNAME = input("Instagram username: ").strip()
SESSION_ID = input("sessionid cookie: ").strip()
CSRF_TOKEN = input("csrftoken cookie: ").strip()
SESSION_FILENAME = "instagram_session"

cookies = {
    "sessionid": SESSION_ID,
    "csrftoken": CSRF_TOKEN,
    "ds_user_id": SESSION_ID.split("%")[0],
}

L = instaloader.Instaloader()
L.load_session(USERNAME, cookies)

logged_in_as = L.test_login()
if not logged_in_as:
    raise SystemExit("Login check failed: the cookies are expired or wrong. Copy fresh ones from your browser.")

L.save_session_to_file(SESSION_FILENAME)
print(f"SUCCESS: saved session for {logged_in_as} to '{SESSION_FILENAME}'")