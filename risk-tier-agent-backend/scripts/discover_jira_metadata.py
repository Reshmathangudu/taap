from __future__ import annotations

import os
from dotenv import load_dotenv

from app.integrations.jira_client import JiraClient, JiraConfig

load_dotenv()
config = JiraConfig(
    base_url=os.environ["JIRA_BASE_URL"],
    email=os.environ["JIRA_EMAIL"],
    api_token=os.environ["JIRA_API_TOKEN"],
    project_key=os.environ["JIRA_PROJECT_KEY"],
)
client = JiraClient(config)
print("Connected as:", client.test_connection().get("displayName"))
print("\nIssue types:")
for issue_type in client.issue_types():
    print(issue_type.get("name"), "->", issue_type.get("id"), "subtask=", issue_type.get("subtask"))

wanted = {"Epic ID", "Story ID", "Module ID", "Change Status"}
print("\nCustom fields:")
for field in client.list_fields():
    if field.get("name") in wanted:
        print(field.get("name"), "->", field.get("id"))
