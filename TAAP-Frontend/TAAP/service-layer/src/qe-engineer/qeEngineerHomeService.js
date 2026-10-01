import mockData from "../../../mock.json" with { type: "json" };
import { serviceEnvironment } from "../environment.js";
import { fetchJiraIssueGroups } from "../jira/serviceClient.js";
import { clone } from "../shared/clone.js";

const qeHomeRoleIds = new Set(["qe-engineers", "sdets"]);

const priorityScore = {
  Critical: 5,
  Highest: 5,
  High: 4,
  Medium: 3,
  Low: 2,
  Lowest: 1,
  P1: 5,
  P2: 4,
  P3: 3,
  P4: 2
};

const riskScore = {
  High: 3,
  Medium: 2,
  Low: 1
};

function topItems(items, getScore) {
  return clone(items)
    .map((item) => ({ ...item, score: getScore(item) }))
    .sort((first, second) => second.score - first.score)
    .slice(0, 5)
    .map(({ score, ...item }) => item);
}

function formatDisplayDate(value) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric"
  }).format(date);
}

function countByStatus(items, status) {
  return items.filter((item) => item.status === status).length;
}

function safePercent(value, total) {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

function progressPercentFor(issues) {
  const progress = issues.reduce((total, issue) => {
    if (isDoneStatus(issue.status)) {
      return total + 1;
    }

    return total + (isInProgressStatus(issue.status) ? 0.5 : 0);
  }, 0);

  return safePercent(progress, issues.length);
}

function isDoneStatus(status) {
  return ["done", "resolved", "closed", "complete", "completed"].includes(normalizeText(status));
}

function isInProgressStatus(status) {
  return [
    "in progress",
    "in review",
    "ready for qa",
    "ready for testing",
    "ready for retest",
    "in qa"
  ].includes(normalizeText(status));
}

function isHighPriority(issue) {
  return ["critical", "highest", "high", "p1", "p2"].includes(normalizeText(issue.priority));
}

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function assignedIssues(issues) {
  return issues.filter((issue) => {
    const assignee = normalizeText(issue.assignee);
    return assignee !== "" && assignee !== "unassigned";
  });
}

function buildMockMetricCards(data) {
  const doneEpics = countByStatus(data.epics, "Done");
  const doneStories = countByStatus(data.userStories, "Done");
  const doneBugs = countByStatus(data.bugs, "Done");
  const doneIssues = doneEpics + doneStories + doneBugs;
  const totalStoryPoints = data.userStories.reduce((total, story) => total + story.storyPoints, 0);
  const completedStoryPoints = data.userStories
    .filter((story) => story.status === "Done")
    .reduce((total, story) => total + story.storyPoints, 0);
  const openBugs = data.bugs.filter((bug) => bug.status !== "Done").length;
  const highestPriorityBugs = data.bugs.filter((bug) => bug.priority === "P1" || bug.severity === "Critical").length;
  const allIssues = [...data.epics, ...data.userStories, ...data.bugs];
  const overallProgressPercent = progressPercentFor(allIssues);
  const inProgressIssues = allIssues.filter((issue) => isInProgressStatus(issue.status)).length;

  return [
    {
      id: "epics",
      label: "Epics",
      value: data.epics.length,
      accent: "purple",
      detail: `${doneEpics} done - ${countByStatus(data.epics, "In Progress")} in progress`,
      progressPercent: progressPercentFor(data.epics)
    },
    {
      id: "stories",
      label: "Stories",
      value: data.userStories.length,
      accent: "green",
      detail: `${completedStoryPoints}/${totalStoryPoints} story points done`,
      progressPercent: progressPercentFor(data.userStories)
    },
    {
      id: "bugs",
      label: "Bugs",
      value: data.bugs.length,
      accent: "red",
      detail: `${openBugs} open - ${highestPriorityBugs} highest priority`,
      progressPercent: progressPercentFor(data.bugs)
    },
    {
      id: "overall",
      label: "Overall",
      value: `${overallProgressPercent}%`,
      accent: "slate",
      detail: `${doneIssues} done - ${inProgressIssues} in progress`,
      progressPercent: overallProgressPercent
    }
  ];
}

function buildJiraMetricCards(data) {
  const doneEpics = data.epics.filter((issue) => isDoneStatus(issue.status)).length;
  const doneStories = data.stories.filter((issue) => isDoneStatus(issue.status)).length;
  const doneBugs = data.bugs.filter((issue) => isDoneStatus(issue.status)).length;
  const doneIssues = doneEpics + doneStories + doneBugs;
  const inProgressEpics = data.epics.filter((issue) => isInProgressStatus(issue.status)).length;
  const inProgressStories = data.stories.filter((issue) => isInProgressStatus(issue.status)).length;
  const openBugs = data.bugs.filter((issue) => !isDoneStatus(issue.status)).length;
  const highestPriorityBugs = data.bugs.filter(isHighPriority).length;
  const allIssues = [...data.epics, ...data.stories, ...data.bugs];
  const overallProgressPercent = progressPercentFor(allIssues);
  const inProgressIssues = allIssues.filter((issue) => isInProgressStatus(issue.status)).length;

  return [
    {
      id: "epics",
      label: "Epics",
      value: data.epics.length,
      accent: "purple",
      detail: `${doneEpics} done - ${inProgressEpics} in progress`,
      progressPercent: progressPercentFor(data.epics)
    },
    {
      id: "stories",
      label: "Stories",
      value: data.stories.length,
      accent: "green",
      detail: `${doneStories} done - ${inProgressStories} in progress`,
      progressPercent: progressPercentFor(data.stories)
    },
    {
      id: "bugs",
      label: "Bugs",
      value: data.bugs.length,
      accent: "red",
      detail: `${openBugs} open - ${highestPriorityBugs} highest priority`,
      progressPercent: progressPercentFor(data.bugs)
    },
    {
      id: "overall",
      label: "Overall",
      value: `${overallProgressPercent}%`,
      accent: "slate",
      detail: `${doneIssues} done - ${inProgressIssues} in progress`,
      progressPercent: overallProgressPercent
    }
  ];
}

function buildMockEpicCards(epics) {
  return epics.map((epic) => ({
    id: epic.id,
    key: epic.key,
    title: epic.title,
    status: epic.status,
    progressPercent: epic.progressPercent,
    childIssueSummary: `${epic.qualitySignals.testedStories}/${epic.qualitySignals.totalStories} child issues done`,
    targetRelease: epic.targetRelease
  }));
}

function buildJiraEpicCards(epics, childIssues, fallbackDate) {
  return epics.map((epic) => {
    const children = childIssues.filter((issue) => issue.parentKey === epic.key);
    const doneChildren = children.filter((issue) => isDoneStatus(issue.status)).length;
    const totalChildren = children.length;
    const progressPercent = totalChildren > 0 ? safePercent(doneChildren, totalChildren) : progressForStatus(epic.status);

    return {
      id: epic.id,
      key: epic.key,
      title: epic.summary,
      status: epic.status || "-",
      progressPercent,
      childIssueSummary: `${doneChildren}/${totalChildren} child issues done`,
      targetRelease: `Updated ${formatDisplayDate(epic.updated || fallbackDate)}`
    };
  });
}

function progressForStatus(status) {
  if (isDoneStatus(status)) {
    return 100;
  }

  if (isInProgressStatus(status)) {
    return 50;
  }

  return 10;
}

function buildMockIssues(data) {
  const updated = formatDisplayDate(data.project.generatedAt);
  let jiraBaseUrl = serviceEnvironment.jiraBaseUrl;

  while (jiraBaseUrl.endsWith("/")) {
    jiraBaseUrl = jiraBaseUrl.slice(0, -1);
  }

  const epicUrls = new Map(data.epics.map((epic) => [epic.key, `${jiraBaseUrl}/browse/${epic.key}`]));

  return [
    ...data.epics.map((epic) => ({
      id: epic.id,
      type: "Epic",
      key: epic.key,
      summary: epic.title,
      status: epic.status,
      priority: epic.priority,
      assignee: epic.owner,
      epic: "-",
      points: "-",
      updated
    })),
    ...data.userStories.map((story) => ({
      id: story.id,
      type: "Story",
      key: story.key,
      summary: story.title,
      status: story.status,
      priority: story.priority,
      assignee: story.assignee,
      epic: story.epicKey,
      epicUrl: epicUrls.get(story.epicKey) ?? "",
      points: story.storyPoints,
      updated
    })),
    ...data.bugs.map((bug) => ({
      id: bug.id,
      type: "Bug",
      key: bug.key,
      summary: bug.title,
      status: bug.status,
      priority: bug.priority,
      assignee: bug.assignee,
      epic: bug.epicKey,
      epicUrl: epicUrls.get(bug.epicKey) ?? "",
      points: "-",
      updated
    }))
  ];
}

function buildJiraIssues(data, fetchedAt) {
  const epicUrls = new Map(data.epics.map((epic) => [epic.key, epic.url]));

  return [
    ...jiraIssuesForTable(data.epics, "Epic", fetchedAt, epicUrls),
    ...jiraIssuesForTable(data.stories, "Story", fetchedAt, epicUrls),
    ...jiraIssuesForTable(data.bugs, "Bug", fetchedAt, epicUrls)
  ];
}

function jiraIssuesForTable(issues, fallbackType, fetchedAt, epicUrls) {
  return issues.map((issue) => ({
    id: issue.id,
    type: issue.type || fallbackType,
    key: issue.key,
    summary: issue.summary,
    status: issue.status || "-",
    priority: issue.priority || "-",
    assignee: typeof issue.assignee === "string"
      ? issue.assignee
      : issue.assignee?.displayName || issue.assignee?.name || "Unassigned",
    relatedAssignees: (issue.relatedAssignees ?? []).map((assignee) => typeof assignee === "string"
      ? assignee
      : assignee?.displayName || assignee?.name || "Unassigned"),
    epic: issue.parentKey || "-",
    epicUrl: epicUrls.get(issue.parentKey) ?? "",
    points: issue.storyPoints || "-",
    updated: formatDisplayDate(issue.updated || fetchedAt)
  }));
}

function buildMockHomeData() {
  const data = {
    ...mockData,
    epics: assignedIssues(mockData.epics),
    userStories: assignedIssues(mockData.userStories),
    bugs: assignedIssues(mockData.bugs)
  };
  const topEpics = topItems(
    data.epics,
    (epic) => (priorityScore[epic.priority] ?? 0) * 10 + (riskScore[epic.riskLevel] ?? 0) * 5
  );

  return {
    source: "mock",
    project: data.project,
    metrics: buildMockMetricCards(data),
    epicCards: buildMockEpicCards(topEpics),
    issues: buildMockIssues(data)
  };
}

function buildJiraHomeData(issueGroups) {
  const allEpics = issueGroups.groups?.epics?.issues ?? [];
  const stories = assignedIssues(issueGroups.groups?.stories?.issues ?? []);
  const relatedAssigneesByEpic = new Map();

  for (const story of stories) {
    if (!story.parentKey) {
      continue;
    }

    const assignees = relatedAssigneesByEpic.get(story.parentKey) ?? [];

    if (!assignees.includes(story.assignee)) {
      assignees.push(story.assignee);
    }

    relatedAssigneesByEpic.set(story.parentKey, assignees);
  }

  const data = {
    epics: allEpics
      .filter((epic) => assignedIssues([epic]).length > 0 || relatedAssigneesByEpic.has(epic.key))
      .map((epic) => ({
        ...epic,
        relatedAssignees: relatedAssigneesByEpic.get(epic.key) ?? []
      })),
    stories,
    bugs: assignedIssues(issueGroups.groups?.bugs?.issues ?? [])
  };
  const topEpics = topItems(
    data.epics,
    (epic) => (priorityScore[epic.priority] ?? 0) * 10 + Date.parse(epic.updated || issueGroups.fetchedAt || 0) / 100000000000
  );
  const childIssues = [...data.stories, ...data.bugs];

  return {
    source: "jira",
    project: {
      id: issueGroups.projectKey,
      name: issueGroups.projectKey,
      generatedAt: issueGroups.fetchedAt
    },
    metrics: buildJiraMetricCards(data),
    epicCards: buildJiraEpicCards(topEpics, childIssues, issueGroups.fetchedAt),
    issues: buildJiraIssues(data, issueGroups.fetchedAt)
  };
}

export async function fetchEnterpriseHome(roleId) {
  if (!qeHomeRoleIds.has(roleId)) {
    return null;
  }

  if (serviceEnvironment.isMock) {
    return clone(buildMockHomeData());
  }

  const issueGroups = await fetchJiraIssueGroups({
    limit: 100,
    projectKey: serviceEnvironment.jiraProjectKey || undefined
  });

  return clone(buildJiraHomeData(issueGroups));
}
