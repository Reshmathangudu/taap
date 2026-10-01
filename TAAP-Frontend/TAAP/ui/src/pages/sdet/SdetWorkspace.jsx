import { SdetTestDesign } from "./test-design/SdetTestDesign.jsx";
import { SdetTestDataSetup } from "./test-data/SdetTestDataSetup.jsx";
import { SdetTestSummaryReport } from "./test-summary-report/SdetTestSummaryReport.jsx";
import { SdetDefectsScreen } from "./defects/SdetDefectsScreen.jsx";
import { ScriptGenerationPage } from "./script-generation/ScriptGenerationPage.jsx";
import { AutomationExecutionPage } from "./automation-execution/AutomationExecutionPage.jsx";
import { AutomationMaintenancePage } from "./automation-maintenance/AutomationMaintenancePage.jsx";

// Section ids come from service-layer/src/sdet/sdetMenu.js. Sections without
// a page yet (Failures, Connectors) render blank on purpose. Home and
// Requirements are rendered by App.jsx with the QE screens.
const sdetPages = {
  "test-design": SdetTestDesign,
  "test-data": SdetTestDataSetup,
  "test-summary-report": SdetTestSummaryReport,
  defects: SdetDefectsScreen,
  "script-generation": ScriptGenerationPage,
  "automation-execution": AutomationExecutionPage,
  "automation-maintenance": AutomationMaintenancePage
};

export function SdetWorkspace({ selectedSection, onSectionOpen }) {
  const Page = selectedSection?.id ? sdetPages[selectedSection.id] : null;

  if (Page) {
    return (
      <div className="blank-workspace sdet-workspace">
        <Page onSectionOpen={onSectionOpen} />
      </div>
    );
  }

  const sectionLabel = selectedSection?.label ?? "Home";
  return <section className="blank-workspace sdet-workspace" aria-label={`${sectionLabel} blank page`} />;
}
