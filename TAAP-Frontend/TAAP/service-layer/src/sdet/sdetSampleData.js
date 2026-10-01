// Sample execution and maintenance data for the SDET profile.
//
// Jira has no notion of automation runs, scheduled scripts or runner
// machines, so those come from here. Everything that CAN come from Jira
// (stories, defects, assignees, release labels) is merged in by
// sdetService.js on top of this.

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function at(daysAgo, hour, minute = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
}

function lastWeekday(name, hour, minute = 0) {
  const target = WEEKDAYS.indexOf(name);
  const date = new Date();
  const diff = (date.getDay() - target + 7) % 7 || 7;
  date.setDate(date.getDate() - diff);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
}

/** Next occurrence of a schedule as an ISO string, or null when paused. */
export function computeNextRun(schedule, now = new Date()) {
  if (!schedule || schedule.paused) return null;
  const [hour, minute] = String(schedule.time || "00:00").split(":").map((part) => Number.parseInt(part, 10) || 0);
  const next = new Date(now);
  next.setSeconds(0, 0);

  if (schedule.frequency === "Daily" || schedule.frequency === "Run once") {
    next.setHours(hour, minute, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    return next.toISOString();
  }

  if (schedule.frequency === "Weekly") {
    const target = WEEKDAYS.indexOf(schedule.dayOfWeek || "Mon");
    next.setHours(hour, minute, 0, 0);
    let diff = (target - next.getDay() + 7) % 7;
    if (diff === 0 && next <= now) diff = 7;
    next.setDate(next.getDate() + diff);
    return next.toISOString();
  }

  if (schedule.frequency === "Monthly") {
    const day = schedule.dayOfMonth || 1;
    next.setDate(day);
    next.setHours(hour, minute, 0, 0);
    if (next <= now) next.setMonth(next.getMonth() + 1, day);
    return next.toISOString();
  }

  return null;
}

export const sdetUsers = {
  currentUser: "Alex Rivera",
  members: ["Alex Rivera", "Priya N", "Ravi K"]
};

export const sdetScripts = [
  {
    id: "SCR-2041",
    suite: "Checkout suite",
    name: "Checkout & promo regression",
    description: "Checkout & promo-code regression: cart, discounts, payment, order confirmation",
    testType: "Regression",
    layers: ["UI", "API"],
    testsInScope: 42,
    tag: "checkout-regression",
    workflow: "checkout-regression.yml",
    workflowParams: "env, build, tag",
    environment: "QA",
    build: "24.8.183",
    machine: "qa-runner-02",
    browsers: ["Chrome", "Edge"],
    retry: "Off",
    schedule: { frequency: "Daily", time: "23:00", cadence: "weekdays", paused: false },
    recipients: ["qa-leads@hcltech.com", "release-mgmt@hcltech.com", "priya.n@hcltech.com"],
    sendEmail: "After every run",
    estimatedMinutes: { min: 14, max: 19, perBrowser: { Chrome: "8-11m", Edge: "6-8m" } },
    active: true
  },
  {
    id: "SCR-1987",
    suite: "Payments",
    name: "Payment API smoke",
    description: "Payment API smoke: authorise, capture, refund and retry paths against the sandbox gateway",
    testType: "Smoke",
    layers: ["API"],
    testsInScope: 18,
    tag: "payment-smoke",
    workflow: "payment-smoke.yml",
    workflowParams: "env, build",
    environment: "QA",
    build: "24.8.183",
    machine: "qa-runner-02",
    browsers: [],
    retry: "Off",
    schedule: { frequency: "Daily", time: "06:00", cadence: "daily", paused: false },
    recipients: ["qa-leads@hcltech.com", "payments-dev@hcltech.com"],
    sendEmail: "After every run",
    estimatedMinutes: { min: 4, max: 6, perBrowser: {} },
    active: true
  },
  {
    id: "SCR-2103",
    suite: "Order to cash",
    name: "Order-to-cash end to end (SIT)",
    description: "Order-to-cash system integration: order capture, fulfilment, invoicing and confirmation across OMS, billing and notifications",
    testType: "SIT",
    layers: ["End to end"],
    testsInScope: 64,
    tag: "order-to-cash-sit",
    workflow: "order-to-cash-sit.yml",
    workflowParams: "env, build, tag",
    environment: "UAT",
    build: "24.8.180",
    machine: "uat-runner-01",
    browsers: ["Chrome"],
    retry: "Off",
    schedule: { frequency: "Weekly", dayOfWeek: "Fri", time: "21:00", cadence: "weekly", paused: false },
    recipients: ["qa-leads@hcltech.com", "release-mgmt@hcltech.com"],
    sendEmail: "After every run",
    estimatedMinutes: { min: 32, max: 41, perBrowser: { Chrome: "32-41m" } },
    active: true
  },
  {
    id: "SCR-1750",
    suite: "Catalogue",
    name: "Catalogue search regression",
    description: "Catalogue search regression: suggestions, filters, sorting and empty states",
    testType: "Regression",
    layers: ["UI"],
    testsInScope: 35,
    tag: "catalogue-regression",
    workflow: "catalogue-regression.yml",
    workflowParams: "env, build, tag",
    environment: "QA",
    build: "24.8.183",
    machine: "qa-runner-02",
    browsers: ["Chrome", "Edge"],
    retry: "Off",
    schedule: { frequency: "Weekly", dayOfWeek: "Mon", time: "22:00", cadence: "weekly", paused: false },
    recipients: ["qa-leads@hcltech.com"],
    sendEmail: "Only on failure",
    estimatedMinutes: { min: 11, max: 15, perBrowser: { Chrome: "6-8m", Edge: "5-7m" } },
    active: true
  },
  {
    id: "SCR-1622",
    suite: "Billing",
    name: "Month-end billing system test",
    description: "Month-end billing system test: statement generation, proration, tax lines and invoice PDF download",
    testType: "System test",
    layers: ["UI", "API"],
    testsInScope: 120,
    tag: "billing-month-end",
    workflow: "billing-month-end.yml",
    workflowParams: "env, build",
    environment: "Stage",
    build: "24.7.310",
    machine: "stage-runner-01",
    browsers: ["Chrome"],
    retry: "Off",
    schedule: { frequency: "Monthly", dayOfMonth: 1, time: "02:00", cadence: "monthly", paused: true },
    recipients: ["billing-qa@hcltech.com", "release-mgmt@hcltech.com"],
    sendEmail: "After every run",
    estimatedMinutes: { min: 48, max: 60, perBrowser: { Chrome: "48-60m" } },
    active: false
  }
];

export const sdetMachines = [
  {
    id: "qa-runner-02",
    label: "qa-runner-02",
    status: "Online",
    ready: true,
    summary: "Node 20 · Chrome 127 · ready",
    dependencies: "Node 20.11 · Playwright 1.46 · Chrome 127",
    lastHeartbeat: at(0, 7, 11)
  },
  {
    id: "uat-runner-01",
    label: "uat-runner-01",
    status: "Online",
    ready: true,
    summary: "Node 20 · Chrome 127 · ready",
    dependencies: "Node 20.11 · Playwright 1.46 · Chrome 127",
    lastHeartbeat: at(0, 7, 9)
  },
  {
    id: "stage-runner-01",
    label: "stage-runner-01",
    status: "Degraded",
    ready: false,
    summary: "Node 18 · Chrome 125 · needs upgrade",
    dependencies: "Node 18.20 · Playwright 1.44 · Chrome 125",
    lastHeartbeat: at(1, 22, 40)
  }
];

export const sdetEnvironments = [
  { id: "QA", label: "QA", latestBuild: "24.8.183", tone: "green" },
  { id: "UAT", label: "UAT", latestBuild: "24.8.180", tone: "amber" },
  { id: "Stage", label: "Stage", latestBuild: "24.7.310", tone: "blue" }
];

const explicitRuns = [
  {
    id: "RUN-1842", type: "Scheduled", script: "SCR-2041", environment: "QA", build: "24.8.183", phase: "Regression",
    executedAt: at(0, 6, 40), total: 42, pass: 38, fail: 3, skip: 1, result: "Failed",
    analysis: "awaiting",
    failures: [
      { test: "TC-1041 Apply promo code on cart", error: "locator [data-testid=apply-promo] not found (renamed to apply-promo-code)", category: "Script issue" },
      { test: "TC-1044 Remove promo code", error: "locator [data-testid=apply-promo] not found", category: "Script issue" },
      { test: "TC-1049 Stacked discounts total", error: "locator [data-testid=apply-promo] not found", category: "Script issue" }
    ],
    rca: "All three failures click the same Apply-promo control. The data-testid was renamed in build 24.8.183; the application flow itself passes when driven manually. Classified as a script issue, not an application defect."
  },
  {
    id: "RUN-1841", type: "Scheduled", script: "SCR-1987", environment: "QA", build: "24.8.183", phase: "Smoke",
    executedAt: at(0, 6, 5), total: 18, pass: 18, fail: 0, skip: 0, result: "Passed", analysis: "none", failures: [], rca: ""
  },
  {
    id: "RUN-1840", type: "Manual rerun", script: "SCR-2041", environment: "QA", build: "24.8.182", phase: "Regression",
    executedAt: at(1, 23, 20), total: 42, pass: 40, fail: 0, skip: 2, result: "Passed", analysis: "none", failures: [], rca: ""
  },
  {
    id: "RUN-1839", type: "Scheduled", script: "SCR-2103", environment: "UAT", build: "24.8.180", phase: "SIT",
    executedAt: lastWeekday("Fri", 21, 35), total: 64, pass: 57, fail: 6, skip: 1, result: "Failed",
    analysis: "awaiting",
    failures: [
      { test: "TC-2210 Order confirmation payload", error: "expected orderId at $.orderId, found at $.data.order.orderId", category: "Script issue" },
      { test: "TC-2211 Confirmation email reference", error: "expected orderId at $.orderId", category: "Script issue" },
      { test: "TC-2214 Invoice number on confirmation", error: "expected orderId at $.orderId", category: "Script issue" },
      { test: "TC-2230 Fulfilment status sync", error: "timeout waiting for OMS callback (UAT queue backlog)", category: "Environment" },
      { test: "TC-2231 Partial shipment update", error: "timeout waiting for OMS callback", category: "Environment" },
      { test: "TC-2240 Credit note on cancellation", error: "credit note total 0.00, expected 129.90", category: "Application defect" }
    ],
    rca: "Order-confirmation API moved orderId under data.order (3 assertion failures). Two timeouts trace to an OMS queue backlog on UAT and are environment issues eligible for rerun. TC-2240 reproduces manually and needs a defect."
  },
  {
    id: "RUN-1838", type: "Scheduled", script: "SCR-1750", environment: "QA", build: "24.8.181", phase: "Regression",
    executedAt: lastWeekday("Mon", 22, 25), total: 35, pass: 35, fail: 0, skip: 0, result: "Passed", analysis: "none", failures: [], rca: ""
  },
  {
    id: "RUN-1837", type: "Scheduled", script: "SCR-2041", environment: "QA", build: "24.8.181", phase: "Regression",
    executedAt: lastWeekday("Mon", 23, 20), total: 42, pass: 36, fail: 5, skip: 1, result: "Failed",
    analysis: "done",
    failures: [
      { test: "TC-1052 Guest checkout", error: "fixed 3s timeout elapsed before cart summary rendered", category: "Flaky" },
      { test: "TC-1061 Address validation", error: "postcode service 503", category: "Environment" },
      { test: "TC-1062 Address autocomplete", error: "postcode service 503", category: "Environment" },
      { test: "TC-1063 Saved address selection", error: "postcode service 503", category: "Environment" },
      { test: "TC-1070 Gift card split payment", error: "balance mismatch after split", category: "Application defect" }
    ],
    rca: "Three failures were a postcode service outage on QA and were rerun manually (RUN-1840, passed). TC-1052 is flaky and is tracked as MT-115. TC-1070 was raised as a defect."
  },
  {
    id: "RUN-1836", type: "Scheduled", script: "SCR-1622", environment: "Stage", build: "24.7.310", phase: "System test",
    executedAt: new Date(new Date().getFullYear(), 8, 1, 2, 40).toISOString(), total: 120, pass: 118, fail: 0, skip: 2, result: "Passed", analysis: "none", failures: [], rca: ""
  }
];

// Older runs so the seven-day counters (18 runs · 12 scheduled · 6 manual ·
// 14 passed · 4 failed) add up to the rows the table can show.
function olderRuns() {
  const specs = [
    ["RUN-1835", "Manual rerun", "SCR-2103", "UAT", "24.8.179", "SIT", 2, 9, 15, 64, 62, 0, 2, "Passed"],
    ["RUN-1834", "Scheduled", "SCR-1987", "QA", "24.8.181", "Smoke", 2, 6, 4, 18, 18, 0, 0, "Passed"],
    ["RUN-1833", "Scheduled", "SCR-2103", "UAT", "24.8.179", "SIT", 3, 21, 12, 64, 60, 2, 2, "Failed"],
    ["RUN-1832", "Manual rerun", "SCR-1750", "QA", "24.8.180", "Regression", 3, 14, 5, 35, 35, 0, 0, "Passed"],
    ["RUN-1831", "Scheduled", "SCR-1987", "QA", "24.8.180", "Smoke", 3, 6, 6, 18, 18, 0, 0, "Passed"],
    ["RUN-1830", "Scheduled", "SCR-2041", "QA", "24.8.180", "Regression", 4, 23, 8, 42, 41, 0, 1, "Passed"],
    ["RUN-1829", "Manual rerun", "SCR-2041", "QA", "24.8.179", "Regression", 4, 11, 30, 42, 42, 0, 0, "Passed"],
    ["RUN-1828", "Scheduled", "SCR-1987", "QA", "24.8.179", "Smoke", 4, 6, 3, 18, 18, 0, 0, "Passed"],
    ["RUN-1827", "Manual rerun", "SCR-1987", "QA", "24.8.179", "Smoke", 5, 15, 42, 18, 18, 0, 0, "Passed"],
    ["RUN-1826", "Scheduled", "SCR-2041", "QA", "24.8.179", "Regression", 5, 23, 9, 42, 40, 0, 2, "Passed"],
    ["RUN-1825", "Manual rerun", "SCR-1750", "QA", "24.8.178", "Regression", 6, 10, 20, 35, 35, 0, 0, "Passed"]
  ];

  return specs.map(([id, type, script, environment, build, phase, daysAgo, hour, minute, total, pass, fail, skip, result]) => ({
    id, type, script, environment, build, phase,
    executedAt: at(daysAgo, hour, minute), total, pass, fail, skip, result,
    analysis: result === "Failed" ? "done" : "none",
    failures: result === "Failed"
      ? [
          { test: "TC-2260 Invoice PDF download", error: "download selector changed after UI library upgrade", category: "Script issue" },
          { test: "TC-2261 Invoice PDF filename", error: "download selector changed after UI library upgrade", category: "Script issue" }
        ]
      : [],
    rca: result === "Failed" ? "Invoice PDF download selector changed after the UI library upgrade; fixed under MT-110." : ""
  }));
}

export const sdetRuns = [...explicitRuns, ...olderRuns()];

export const sdetMaintenanceItems = [
  { id: "MT-117", script: "SCR-2041", reason: "Script failure", source: { type: "Failed run", ref: "RUN-1842" }, change: "Apply-promo button locator changed (data-testid renamed) — 3 tests fail on click", priority: "High", assignee: "Alex Rivera", status: "In progress", updatedAt: at(0, 8, 10), origin: "sample" },
  { id: "MT-116", script: "SCR-2103", reason: "Script failure", source: { type: "Failed run", ref: "RUN-1839" }, change: "Order-confirmation API response moved orderId under data.order — assertion path outdated", priority: "High", assignee: "Priya N", status: "New", updatedAt: at(0, 7, 40), origin: "sample" },
  { id: "MT-115", script: "SCR-2041", reason: "Flaky test", source: { type: "Allure report", ref: "Allure · 30 days" }, change: "TC-1052 guest checkout passes 7/10 — waits on fixed 3s timeout; replace with await for network idle", priority: "Medium", assignee: "Alex Rivera", status: "In progress", updatedAt: at(1, 16, 5), origin: "sample" },
  { id: "MT-114", script: "SCR-1750", reason: "Flaky test", source: { type: "Allure report", ref: "Allure · 30 days" }, change: "Search suggestions dropdown read before render — use locator.waitFor instead of sleep", priority: "Medium", assignee: "Unassigned", status: "New", updatedAt: at(1, 11, 30), origin: "sample" },
  { id: "MT-113", script: "SCR-2041", reason: "Enhancement · app change", source: { type: "User story", ref: "US-471" }, change: "New GST number field on checkout address step — not covered; existing tests still pass", priority: "High", assignee: "Alex Rivera", status: "New", updatedAt: at(1, 9, 15), origin: "sample" },
  { id: "MT-112", script: "SCR-1987", reason: "Enhancement · app change", source: { type: "User story", ref: "US-466" }, change: "Payment API v2 adds currency parameter — extend smoke tests for INR and USD", priority: "Medium", assignee: "Ravi K", status: "In progress", updatedAt: lastWeekday("Mon", 14, 0), origin: "sample" },
  { id: "MT-111", script: "SCR-2041", reason: "Enhancement · coverage gap", source: { type: "Defect", ref: "JIRA-4821" }, change: "Bug found manually: promo code applied twice on page refresh — no test covers refresh after discount", priority: "High", assignee: "Priya N", status: "In progress", updatedAt: lastWeekday("Mon", 10, 20), origin: "sample" },
  { id: "MT-110", script: "SCR-2103", reason: "Script failure", source: { type: "Failed run", ref: "RUN-1833" }, change: "Invoice PDF download selector changed after UI library upgrade", priority: "Low", assignee: "Ravi K", status: "Fixed", updatedAt: lastWeekday("Fri", 17, 45), origin: "sample" },
  { id: "MT-109", script: "SCR-1622", reason: "Script failure", source: { type: "Failed run", ref: "RUN-1830" }, change: "Month-end billing date picker locator changed — verified by rerun RUN-1836", priority: "Low", assignee: "Alex Rivera", status: "Verified", updatedAt: new Date(new Date().getFullYear(), 8, 1, 9, 0).toISOString(), origin: "sample" },
  { id: "MT-108", script: "SCR-1987", reason: "Script failure", source: { type: "Failed run", ref: "RUN-1821" }, change: "Refund endpoint moved to /v2/refunds — base path updated in API client", priority: "Medium", assignee: "Ravi K", status: "Closed", updatedAt: at(9, 15, 0), origin: "sample" },
  { id: "MT-107", script: "SCR-1750", reason: "Flaky test", source: { type: "Allure report", ref: "Allure · 30 days" }, change: "Filter chips asserted before debounce — await response instead of sleep", priority: "Low", assignee: "Priya N", status: "Closed", updatedAt: at(10, 12, 0), origin: "sample" },
  { id: "MT-106", script: "SCR-2041", reason: "Enhancement · coverage gap", source: { type: "Defect", ref: "JIRA-4790" }, change: "Cart total not refreshed after quantity change — added regression scenario", priority: "Medium", assignee: "Alex Rivera", status: "Closed", updatedAt: at(12, 17, 30), origin: "sample" },
  { id: "MT-105", script: "SCR-2103", reason: "Enhancement · app change", source: { type: "User story", ref: "US-452" }, change: "Split shipment confirmation — added two end-to-end scenarios", priority: "Medium", assignee: "Priya N", status: "Closed", updatedAt: at(13, 11, 0), origin: "sample" }
];

export const sdetSampleReferences = {
  "US-471": { key: "US-471", type: "User story", title: "Capture GST number at checkout for B2B customers", description: "Acceptance criteria 2 and 4 are not covered by any current test in SCR-2041. Test Design has 3 accepted cases ready to automate.", status: "In Progress", priority: "High", assignee: "Alex Rivera", acceptedCases: 3, origin: "sample" },
  "US-466": { key: "US-466", type: "User story", title: "Payment API v2 currency parameter", description: "Payment API v2 adds a currency parameter. Smoke tests must cover INR and USD authorisation and capture.", status: "In Progress", priority: "Medium", assignee: "Ravi K", acceptedCases: 2, origin: "sample" },
  "JIRA-4821": { key: "JIRA-4821", type: "Defect", title: "Promo code applied twice on page refresh", description: "Refreshing the cart page after applying a promo code applies the discount a second time. Found manually; no automated scenario covers refresh after discount.", status: "Open", priority: "High", assignee: "Priya N", acceptedCases: 1, origin: "sample" }
};

export const sdetSprint = {
  name: "Sprint 18",
  options: ["Sprint 18", "Sprint 19", "Sprint 20"],
  scenariosAdded: 11,
  scriptsFixed: 6,
  release: "Release 24.8"
};
