import { fetchJiraIssueGroups } from "./rest-client.js";
import { loadLocalEnv } from "../server.js";

loadLocalEnv();

const issueGroups = await fetchJiraIssueGroups({ limit: 5 });
const counts = Object.fromEntries(
  Object.entries(issueGroups.groups).map(([key, group]) => [key, group.issues.length])
);

console.log(
  JSON.stringify(
    {
      projectKey: issueGroups.projectKey,
      fetchedAt: issueGroups.fetchedAt,
      counts,
      snapshotPath: "service-layer/data/jira-issue-groups.json"
    },
    null,
    2
  )
);
