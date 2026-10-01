// Left-hand navigation for the SDET profile. Kept separate from the QE
// Engineer menu (roles/enterpriseMenu.js) so either role's navigation can
// change without touching the other.
export const sdetMenuGroups = [
  {
    label: "Plan",
    items: [
      { id: "home", label: "Home", icon: "home" },
      { id: "requirements", label: "Requirements", icon: "file-text" },
      { id: "test-design", label: "Test Design", icon: "layout-grid" }
    ]
  },
  {
    label: "Build & Run",
    items: [
      { id: "script-generation", label: "Script Generation", icon: "code" },
      { id: "test-data", label: "Test Data", icon: "database" },
      { id: "automation-execution", label: "Automation Execution", icon: "play" },
      { id: "automation-maintenance", label: "Automation Maintenance", icon: "wrench" },
      { id: "failures", label: "Failures", icon: "alert-triangle" },
      { id: "defects", label: "Defects", icon: "bug" }
    ]
  },
  {
    label: "Insight",
    items: [
      { id: "test-summary-report", label: "Test Summary Report", icon: "file-bar-chart" }
    ]
  },
  {
    label: "Setup",
    items: [{ id: "connectors", label: "Connectors", icon: "plug" }]
  }
];
