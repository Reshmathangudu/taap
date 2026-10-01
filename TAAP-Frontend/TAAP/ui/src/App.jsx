import { useEffect, useState } from "react";
import {
  fetchEnterpriseHome,
  fetchEnterpriseRoles,
  openEnterprise,
  openEnterpriseSection
} from "@taap/service-layer";
import { EnterpriseHeader } from "./components/EnterpriseHeader.jsx";
import { Sidebar } from "./components/Sidebar.jsx";
import { AgentReviewsHome } from "./pages/agent-reviews/AgentReviewsHome.jsx";
import { EnterpriseBlankScreen } from "./pages/enterprise/EnterpriseBlankScreen.jsx";
import { QeEngineerHome } from "./pages/qe-engineer/QeEngineerHome.jsx";
import { RequirementsScreen } from "./pages/requirements/RequirementsScreen.jsx";
import { RoleSelection } from "./pages/role-selection/RoleSelection.jsx";
import { TestDataSetup } from "./pages/test-data-setup/TestDataSetup.jsx";
import { TestDesign } from "./pages/test-design/TestDesign.jsx";
import { WorkflowPage } from "./pages/workflow/WorkflowPage.jsx";
import { SprintTestPlanPage } from "./pages/sprint-test-plan/SprintTestPlanPage.jsx";
import { DefectsScreen } from "./pages/defects/DefectsScreen.jsx";
import { TestSummaryReport } from "./pages/test-summary-report/TestSummaryReport.jsx";
import { SdetWorkspace } from "./pages/sdet/SdetWorkspace.jsx";

function BlankWorkspace({ roleId, selectedSection, homeData, homeError, isHomeLoading, searchQuery, onSearchChange, onCreateTestCases, testDesignSelection, onSectionOpen }) {
  const sectionLabel = selectedSection?.label ?? "Home";

  if (selectedSection?.id === "home" && homeData) {
    return <QeEngineerHome data={homeData} query={searchQuery} onQueryChange={onSearchChange} />;
  }

  if (selectedSection?.id === "requirements") {
    return <RequirementsScreen onCreateTestCases={onCreateTestCases} />;
  }

  if (selectedSection?.id === "home" && homeError) {
    return (
      <section className="blank-workspace blank-workspace--message" aria-label="QE Engineer home error">
        <div className="blank-workspace__message">
          <h1>Unable to load QE Engineer home</h1>
          <p>{homeError}</p>
        </div>
      </section>
    );
  }

  if (selectedSection?.id === "home" && isHomeLoading) {
    return (
      <section className="blank-workspace blank-workspace--message" aria-label="QE Engineer home loading">
        <div className="blank-workspace__message">
          <h1>Loading QE Engineer home</h1>
        </div>
      </section>
    );
  }

  // The SDET profile has its own pages and routing beyond shared Home/Requirements.
  if (roleId === "sdets") {
    return <SdetWorkspace selectedSection={selectedSection} onSectionOpen={onSectionOpen} />;
  }

  if (selectedSection?.id === "agent-reviews") {
    return <AgentReviewsHome />;
  }

  if (selectedSection?.id === "test-design") {
    return <TestDesign selectedRequirements={testDesignSelection?.requirements} selectedSource={testDesignSelection?.source} onPrepareTestData={() => onSectionOpen("test-data-envs")} />;
  }

  if (selectedSection?.id === "test-data-envs") {
    return <TestDataSetup />;
  }

  if (selectedSection?.id === "workflow") {
    return <WorkflowPage />;
  }
 
  if (selectedSection?.id === "sprint-test-plan") {
    return <SprintTestPlanPage />;
  }

  if (selectedSection?.id === "defects") {
    return <DefectsScreen />;
  }

  if (selectedSection?.id === "reports-status") {
    return <TestSummaryReport />;
  }

  return <section className="blank-workspace" aria-label={`${sectionLabel} blank page`} />;
}

function EnterpriseShell({ enterprise, activeSectionId, selectedSection, onSectionOpen, onHome, onCreateTestCases, testDesignSelection }) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [homeData, setHomeData] = useState(null);
  const [homeError, setHomeError] = useState("");
  const [isHomeLoading, setIsHomeLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const usesQeHome = enterprise.role.id === "qe-engineers" || enterprise.role.id === "sdets";

  useEffect(() => {
    let isMounted = true;

    if (!usesQeHome || activeSectionId !== "home") {
      setHomeData(null);
      setHomeError("");
      setIsHomeLoading(false);
      setSearchQuery("");
      return undefined;
    }

    setIsHomeLoading(true);
    setHomeError("");

    fetchEnterpriseHome(enterprise.role.id)
      .then((data) => {
        if (isMounted) {
          setHomeData(data);
          setHomeError("");
        }
      })
      .catch((error) => {
        if (isMounted) {
          setHomeData(null);
          setHomeError(error instanceof Error ? error.message : "Unable to fetch QE Engineer home data.");
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsHomeLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [enterprise.role.id, enterprise.user, usesQeHome, activeSectionId]);

  return (
    <main className="enterprise-screen">
      <EnterpriseHeader
        role={enterprise.role}
        user={enterprise.user}
        showSearch={usesQeHome}
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        onHome={onHome}
      />
      <div className={`enterprise-body ${isSidebarCollapsed ? "enterprise-body--collapsed" : ""}`}>
        <Sidebar
          menuGroups={enterprise.menuGroups}
          disabledSectionIds={enterprise.role.id === "qe-engineers" ? ["test-data-envs", ...(!testDesignSelection?.requirements?.length ? ["test-design"] : [])] : []}
          activeSectionId={activeSectionId}
          isCollapsed={isSidebarCollapsed}
          onSectionOpen={onSectionOpen}
          onToggleCollapse={() => setIsSidebarCollapsed((value) => !value)}
        />
        <BlankWorkspace
          onSectionOpen={onSectionOpen}
          roleId={enterprise.role.id}
          selectedSection={selectedSection}
          homeData={homeData}
          homeError={homeError}
          isHomeLoading={isHomeLoading}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onCreateTestCases={onCreateTestCases}
          testDesignSelection={testDesignSelection}
        />
      </div>
    </main>
  );
}

export default function App() {
  const [roles, setRoles] = useState([]);
  const [currentEnterprise, setCurrentEnterprise] = useState(null);
  const [activeSectionId, setActiveSectionId] = useState("home");
  const [selectedSection, setSelectedSection] = useState(null);
  const [placeholderRole, setPlaceholderRole] = useState(null);
  const [testDesignSelection, setTestDesignSelection] = useState(null);

  useEffect(() => {
    fetchEnterpriseRoles().then(setRoles);
  }, []);

  async function handleOpenEnterprise(roleId) {
    setTestDesignSelection(null);
    const enterprise = await openEnterprise(roleId);

    if (!enterprise.hasNavigation) {
      setPlaceholderRole(enterprise.role);
      setCurrentEnterprise(null);
      return;
    }

    const page = await openEnterpriseSection(roleId, enterprise.activeSectionId);
    setCurrentEnterprise(enterprise);
    setActiveSectionId(enterprise.activeSectionId);
    setSelectedSection(page.section);
    setPlaceholderRole(null);
  }

  async function handleOpenSection(sectionId) {
    if (!currentEnterprise) {
      return;
    }

    const page = await openEnterpriseSection(currentEnterprise.role.id, sectionId);
    setActiveSectionId(sectionId);
    setSelectedSection(page.section);
  }

  async function handleCreateTestCases(requirements, source) {
    if (!requirements?.length) return;
    setTestDesignSelection({ requirements, source });
    await handleOpenSection("test-design");
  }

  function handleHome() {
    setCurrentEnterprise(null);
    setSelectedSection(null);
    setPlaceholderRole(null);
    setActiveSectionId("home");
  }

  if (currentEnterprise) {
    return (
      <EnterpriseShell
        enterprise={currentEnterprise}
        activeSectionId={activeSectionId}
        selectedSection={selectedSection}
        onSectionOpen={handleOpenSection}
        onHome={handleHome}
        onCreateTestCases={handleCreateTestCases}
        testDesignSelection={testDesignSelection}
      />
    );
  }

  if (placeholderRole) {
    return <EnterpriseBlankScreen role={placeholderRole} onHome={handleHome} />;
  }

  return <RoleSelection roles={roles} onOpen={handleOpenEnterprise} />;
}
