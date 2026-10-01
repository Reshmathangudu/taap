import { Search } from "lucide-react";
import { TaapLogo } from "./TaapLogo.jsx";

function getInitials(name) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("");
}

export function EnterpriseHeader({
  role,
  user,
  showSearch = false,
  searchValue = "",
  onSearchChange,
  onHome
}) {
  return (
    <header className="enterprise-header">
      <div className="enterprise-header__brand">
        <TaapLogo compact />
      </div>
      {showSearch ? (
        <label className="enterprise-search">
          <Search size={17} strokeWidth={1.6} />
          <input
            aria-label="Search"
            placeholder="Search epics, stories, bugs..."
            value={searchValue}
            onChange={(event) => onSearchChange?.(event.target.value)}
          />
        </label>
      ) : null}
      {user ? (
        <button className="mock-user-button" type="button" onClick={onHome} aria-label="Back to role selection">
          <span>{getInitials(user.name)}</span>
          <div>
            <strong>{user.name}</strong>
            <small>{user.position}</small>
          </div>
        </button>
      ) : (
        <button className="enterprise-name-button" type="button" onClick={onHome}>
          {role.label}
        </button>
      )}
    </header>
  );
}
