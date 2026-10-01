import {
  BarChart3,
  Briefcase,
  Bug,
  CalendarDays,
  ClipboardList,
  Code2,
  Database,
  FileBarChart,
  FileText,
  Home,
  LayoutGrid,
  Play,
  Plug,
  Presentation,
  SidebarClose,
  SidebarOpen,
  TriangleAlert,
  Workflow,
  Wrench
} from "lucide-react";

const menuIcons = {
  home: Home,
  workflow: Workflow,
  "calendar-days": CalendarDays,
  "file-text": FileText,
  "layout-grid": LayoutGrid,
  play: Play,
  database: Database,
  bug: Bug,
  "clipboard-list": ClipboardList,
  "file-bar-chart": FileBarChart,
  "bar-chart-3": BarChart3,
  presentation: Presentation,
  plug: Plug,
  briefcase: Briefcase,
  code: Code2,
  wrench: Wrench,
  "alert-triangle": TriangleAlert
};

export function Sidebar({ menuGroups, activeSectionId, isCollapsed, onSectionOpen, onToggleCollapse, disabledSectionIds = [] }) {
  const ToggleIcon = isCollapsed ? SidebarOpen : SidebarClose;

  return (
    <aside className={`enterprise-sidebar ${isCollapsed ? "enterprise-sidebar--collapsed" : ""}`}>
      <nav aria-label="Enterprise submenu">
        {menuGroups.map((group) => (
          <section className="menu-group" key={group.label}>
            <h2>{group.label}</h2>
            {group.items.map((item) => {
              const Icon = menuIcons[item.icon] ?? Home;
              const selected = item.id === activeSectionId;

              return (
                <button
                  className={`menu-item ${selected ? "menu-item--selected" : ""}`}
                  key={item.id}
                  type="button"
                  disabled={disabledSectionIds.includes(item.id)}
                  onClick={() => onSectionOpen(item.id)}
                  aria-current={selected ? "page" : undefined}
                  aria-label={item.label}
                  title={item.label}
                >
                  <Icon size={17} strokeWidth={1.6} />
                  <span>{item.label}</span>
                  {item.badge ? (
                    <em className={`menu-item__badge ${item.badgeTone ? `menu-item__badge--${item.badgeTone}` : ""}`}>
                      {item.badge}
                    </em>
                  ) : null}
                </button>
              );
            })}
          </section>
        ))}
      </nav>
      <button
        className="collapse-button"
        type="button"
        onClick={onToggleCollapse}
        aria-label={isCollapsed ? "Expand menu" : "Collapse menu"}
        title={isCollapsed ? "Expand menu" : "Collapse menu"}
      >
        <ToggleIcon size={16} />
        <span>{isCollapsed ? "Expand" : "Collapse"}</span>
      </button>
    </aside>
  );
}
