import os
from pprint import pprint
import asana
from asana.rest import ApiException

# Pull token from environment; export ASANA_TOKEN=... in your shell first.
# Don't hardcode it back into the file.
configuration = asana.Configuration()
configuration.access_token = os.environ['ASANA_TOKEN']
api_client = asana.ApiClient(configuration)

# Step 1: confirm who we are

users_api = asana.UsersApi(api_client)
try:
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