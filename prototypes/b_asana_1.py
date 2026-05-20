import os
import sys
import requests

def verify_asana_token(token: str) -> dict:
    """
    Verifies an Asana Personal Access Token (PAT) and retrieves available workspaces.
    """
    url = "https://app.asana.com/api/1.0/users/me"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # 200 OK means the token is fully valid
        if response.status_code == 200:
            user_data = response.json().get("data", {})
            print("✅ Token Verification Successful!")
            print(f"User: {user_data.get('name')} ({user_data.get('email')})")
            print("-" * 40)
            
            workspaces = user_data.get("workspaces", [])
            if workspaces:
                print(f"Available Workspaces ({len(workspaces)}):")
                for ws in workspaces:
                    print(f"  • Name: {ws.get('name')}")
                    print(f"    GID:  {ws.get('gid')}\n")
            else:
                print("⚠️ Token is valid, but this account belongs to no workspaces.")
                
            return user_data
            
        # 401 Unauthorized means bad, expired, or revoked token
        elif response.status_code == 401:
            print("❌ Authentication Failed (401 Unauthorized).")
            print("Please check your token for typos, missing characters, or revocation.")
            sys.exit(1)
            
        # Catch other unexpected API responses
        else:
            print(f"⚠️ Unexpected status code {response.status_code} received.")
            print(f"Response details: {response.text}")
            sys.exit(1)

    except requests.exceptions.Timeout:
        print("❌ Error: The request timed out. Check your network connection.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network or connection error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Best practice: Pull the token from your environment variables
    # You can set this in your shell using: export ASANA_TOKEN="your_token_here"
    asana_token = os.environ.get("ASANA_TOKEN")
    
    if not asana_token:
        print("💡 Environment variable 'ASANA_TOKEN' not found.")
        # Fallback interactive input if not found in environment
        asana_token = input("Please enter your Asana Personal Access Token to test: ").strip()
        
    if not asana_token:
        print("❌ Error: No token provided. Exiting.")
        sys.exit(1)
        
    verify_asana_token(asana_token)
