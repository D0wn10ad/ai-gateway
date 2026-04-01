import os
import requests
import secrets
import string
import argparse
import urllib3
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# Configuration from Environment
OW_URL = os.getenv("OPEN_WEBUI_BASE_URL")
OW_KEY = os.getenv("OPEN_WEBUI_ADMIN_KEY")
LT_URL = os.getenv("LITELLM_PROXY_BASE_URL")
LT_KEY = os.getenv("LITELLM_MASTER_KEY")

def get_or_create_open_webui_user(email, name, verify_ssl):
    """Finds an existing user or creates a new one in Open WebUI."""
    headers = {"Authorization": f"Bearer {OW_KEY}", "Content-Type": "application/json"}

    # We use OPTIONS to ask the server what methods are allowed
    #resp = requests.options(f"{OW_URL}/api/v1/users", headers=headers, verify=verify_ssl)
    #print(f"[*] Status: {resp.status_code}")
    #print(f"[*] Allowed Methods: {resp.headers.get('Allow')}")

    print(f"[*] Checking Open WebUI for {email}...")
    resp = requests.get(f"{OW_URL}/api/v1/users/", headers=headers, verify=verify_ssl)

    # If we get a 401 or 403, the API key is likely the issue
    if resp.status_code != 200:
        raise Exception(f"API Error ({resp.status_code}): {resp.text}")

    data = resp.json()

    # --- Robust Handling of Response Structure ---
    if isinstance(data, list):
        users = data
    elif isinstance(data, dict):
        # If it's a dict, try to find the list inside common keys
        users = data.get("users", data.get("data", []))
        # If still empty but 'email' is in the dict, it's a single user object
        if not users and "email" in data:
            users = [data]
    else:
        users = []

    # Now we can safely search
    existing_user = next((u for u in users if isinstance(u, dict) and u.get('email') == email), None)

    if existing_user:
        print(f"[+] Found existing user! ID: {existing_user['id']}")
        return existing_user['id'], None

    # Create new user if not found (rest of the code remains the same)
    print(f"[*] User not found. Creating new account...")
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for i in range(16))
    
    payload = {
        "email": email,
        "name": name or email.split('@')[0],
        "password": password,
        "role": "user"
    }
    
#    create_resp = requests.post(f"{OW_URL}/api/v1/users/", json=payload, headers=headers, verify=verify_ssl)

    create_resp = requests.post(f"{OW_URL}/api/v1/auths/add", json=payload, headers=headers, verify=verify_ssl)

    # CREATE IS NOT WORKING DUE TO 405 from open-webui....
    create_resp.raise_for_status()
    return create_resp.json()['id'], password

def provision_litellm(user_uuid, email, verify_ssl):
    """Syncs the UUID to LiteLLM and returns an invitation link."""
    headers = {"x-litellm-api-key": f"{LT_KEY}", "Content-Type": "application/json"}
    
    print(f"[*] Syncing UUID {user_uuid} to LiteLLM...")
    lt_payload = {
       "max_budget": 10,
        "user_email": email,
        "user_id": user_uuid,
        "user_role": "internal_user",
        #"send_invite_email": True,
        "auto_create_key": False
    }

    # Idempotent user creation in LiteLLM
    new_user = requests.post(f"{LT_URL}/user/new", json=lt_payload, headers=headers, verify=verify_ssl)
    new_user.raise_for_status()
    result = new_user.json()

    # Generate the invitation link
    inv_resp = requests.post(f"{LT_URL}/invitation/new", json={"user_id": user_uuid}, headers=headers, verify=verify_ssl)
    inv_resp.raise_for_status()
    result = inv_resp.json()


    return f"""{LT_URL}/ui/?invitation_id={result.get("id")}"""

def main():
    parser = argparse.ArgumentParser(description="Onboard Open WebUI users to LiteLLM for cost tracking.")
    parser.add_argument("email", help="The email address of the user.")
    parser.add_argument("--name", help="The display name of the user (optional).", default=None)
    parser.add_argument("--skip-verify", action="store_true", help="Skip SSL certificate verification (non-production).")
    
    args = parser.parse_args()
    
    # Handle SSL Warning suppression if skipping verification
    verify_ssl = not args.skip_verify
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("[!] Warning: SSL verification is DISABLED.")

    try:
        uuid, password = get_or_create_open_webui_user(args.email, args.name, verify_ssl)
        invite_link = provision_litellm(uuid, args.email, verify_ssl)

        print("\n" + "═"*40)
        print(f"  Onboarding Complete")
        print("─"*40)
        print(f"  User Email: {args.email}")
        print(f"  System UUID: {uuid}")
        if password:
            print(f"  Temporary PWD: {password}")
        else:
            print(f"  Password: [Kept existing password]")
        print(f"  LiteLLM Link: {invite_link}")
        print("═"*40 + "\n")

    except Exception as e:
        print(f"[-] Critical Error: {e}")

if __name__ == "__main__":
    main()
