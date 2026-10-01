export const enterpriseMenuGroups = [
  {
    label: "Plan",
    items: [
      { id: "home", label: "Home", icon: "home" },
      // { id: "workflow", label: "Workflow", icon: "workflow" },
      // { id: "sprint-test-plan", label: "Sprint Test Plan", icon: "calendar-days" },
      { id: "requirements", label: "Requirements", icon: "file-text" },
      { id: "test-design", label: "Test Design", icon: "layout-grid" }
    ]
  },
  {
    label: "Execute",
    items: [
      // { id: "test-execution", label: "Test Execution", icon: "play" },
      { id: "test-data-envs", label: "Test Data & Envs", icon: "database" },
      { id: "defects", label: "Defects", icon: "bug" }
    ]
  },
  {
    label: "Agents & Report",
    items: [
      { id: "agent-reviews", label: "Risk Tier Agent", icon: "clipboard-list" },
      // { id: "reports-status", label: "Reports & Status", icon: "file-bar-chart" }
      { id: "reports-status", label: "Test Summary Report", icon: "file-bar-chart" }
    ]
  },
  // {
  //   label: "Insight",
  //   items: [
  //     { id: "quality-insight", label: "Quality Insight", icon: "bar-chart-3" },
  //     { id: "release-readiness", label: "Release Readiness", icon: "presentation" }
  //   ]
  // },
  // {
  //   label: "Setup",
  //   items: [
  //     { id: "integrations", label: "Integrations", icon: "plug" }
  //   ]
  // }
];
