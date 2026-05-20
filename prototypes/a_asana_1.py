import os
import sys
import asana
from asana.rest import ApiException
from pprint import pprint

configuration = asana.Configuration()
configuration.access_token = os.environ['ASANA_TOKEN']
api_client = asana.ApiClient(configuration)
# workspace_membership_gid = "1214958615680522"     # this is a regaulr Workspace_gid - NOT a membershgip_gid
workspace_membership_gid = "1214958615680543"

opts = { 'opt_fields': "created_at,is_active,is_admin,is_guest,is_view_only,user,user.name,user_task_list,user_task_list.name,user_task_list.owner,user_task_list.workspace,vacation_dates,vacation_dates.end_on,vacation_dates.start_on,workspace,workspace.name" }

# create an instance of the API class
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
