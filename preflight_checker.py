import os
import asana
import requests
import sys
from rich import print      # showding replacment name bind for print, for this source file only
from asana.rest import ApiException
from pprint import pprint

# ########################### Global vars
asana_token = None
configuration = asana.Configuration()
configuration.access_token = os.environ['ASANA_TOKEN']
api_client = asana.ApiClient(configuration)
workspace_membership_gid = "1214958615680543"
workspace__gid = "1214958615680522"
opts = { 'opt_fields': "created_at,is_active,is_admin,is_guest,is_view_only,user,user.name,user_task_list,user_task_list.name,user_task_list.owner,user_task_list.workspace,vacation_dates,vacation_dates.end_on,vacation_dates.start_on,workspace,workspace.name" }
_bg = "bold green"
_rg = "green"
_by = "bold yellow"
_rw = "white"
_yor = "yellow on red"

# ####################### main()
def main():

    _title = "Hello from ServiceNOW Asana challenge"
    print(f"\n[{_by}]{_title}[/{_by}]")
    #print("[yellow]Hello from ServiceNOW Asana challenge[/yellow]")
    print(f"=============================================================")
    print(f"Running API, Token, Endpoint, Credential pre-flight checks...\n")
    validation_check_1()
    asana_token = os.environ.get("ASANA_TOKEN")
    if not asana_token:
        print("💡 Environment variable 'ASANA_TOKEN' not found.")
        # Fallback interactive input if not found in environment
        asana_token = input("Please enter your Asana Personal Access Token to test: ").strip()
        
    if not asana_token:
        print("❌ Error: No token provided. Exiting.")
        sys.exit(1)
        
    validation_check_2(asana_token)
    validation_check_3()
    sys.exit(0)

# ##################### 1
def validation_check_1():
    # create an instance of the API class
    print ( f"[{_yor}]Validating...[/{_yor}]" )
    print ( f"------------ 1 -------------" )
    api_client = asana.ApiClient(configuration)
    try:
        workspace_memberships_api_instance = asana.WorkspaceMembershipsApi(api_client)
        try:
            # Get a workspace membership
            api_response = workspace_memberships_api_instance.get_workspace_membership(workspace_membership_gid, opts)
            pprint(api_response)
        except ApiException as e:
            print("Exception when calling WorkspaceMembershipsApi->get_workspace_membership: %s\n" % e)
    # api_client is closed here; pool threads joined; process exits cleanly
    # The asana.ApiClient is an OpenAPI-generated wrapper, and in its constructor threads in that pool are non-daemon threads.
    # So...Those pool worker threads sit idle in a wait() on a condition variable, waiting for tasks that will never come 
    # — they don't know the script is done. So we need to FORCE a close.
    finally:
        api_client.pool.close()
        api_client.pool.join()
    return


# ##################### 2

def validation_check_2(token: str) -> dict:
    """
    Verifies an Asana Personal Access Token (PAT) and retrieves available workspaces.
    - used simple raw REST endpoint and started html request()
    - does not excercise API or TOKENS
    """
    url = "https://app.asana.com/api/1.0/users/me"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    print ( f"\n[{_yor}]Validating...[/{_yor}]" )
    print ( f"------------ 2 -------------" )
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # 200 OK means the token is fully valid
        if response.status_code == 200:
            user_data = response.json().get("data", {})
            print(f"Token Verification Successful!]")
            print(f"User: {user_data.get('name')} ({user_data.get('email')})")
            workspaces = user_data.get("workspaces", [])
            if workspaces:
                print(f"Available Workspaces ({len(workspaces)}):")
                for ws in workspaces:
                    print(f"  • Name: {ws.get('name')}")
                    print(f"    GID:  {ws.get('gid')}\n")
            else:
                print(f"⚠️ Token is valid, but this account belongs to no workspaces.")
                
            return user_data
            
        # 401 Unauthorized means bad, expired, or revoked token
        elif response.status_code == 401:
            print(f"❌ Authentication Failed (401 Unauthorized).")
            print("Please check your token for typos, missing characters, or revocation.")
            sys.exit(1)
            
        # Catch other unexpected API responses
        else:
            print(f"⚠️ Unexpected status code {response.status_code} received.")
            print(f"Response details: {response.text}")
            sys.exit(1)

    except requests.exceptions.Timeout:
        print(f"❌ Error: The request timed out. Check your network connection.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network or connection error occurred: {e}")
        sys.exit(1)


# ##################### 3
def validation_check_3():
    print ( f"\n[{_yor}]Validating...[/{_yor}]" )
    print ( f"------------ 3 -------------" )
    users_api = asana.UsersApi(api_client)
    try:    # hack for bad assumed API threading, failure to close code
        me = users_api.get_user("me", {'opt_fields': 'name,email,workspaces.name'})
        try:
            print("Authenticated as:")
            pprint(me)
        except ApiException as e:
            print(f"get_user failed: {e}")
            raise

        # Step 2: list this user's workspace memberships
        wm_api = asana.WorkspaceMembershipsApi(api_client)
        try:
            memberships = wm_api.get_workspace_memberships_for_user(
                "me",
                {'opt_fields': 'workspace.name,is_admin,is_active,is_guest'}
            )
            print("\nWorkspace memberships:")
            for m in memberships:
                pprint(m)
        except ApiException as e:
            print(f"get_workspace_memberships_for_user failed: {e}")
            raise

    finally:
        api_client.pool.close()
        api_client.pool.join()

# ############################### 
if __name__ == "__main__":
    main()
