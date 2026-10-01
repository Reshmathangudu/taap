import {
  ClipboardCheck,
  Code2,
  Gauge,
  LoaderCircle,
  MessageSquare,
  Search,
  Shield,
  Star,
  UserRound,
  UsersRound
} from "lucide-react";
import { TaapLogo } from "../../components/TaapLogo.jsx";

const roleIcons = {
  "clipboard-check": ClipboardCheck,
  "code-2": Code2,
  gauge: Gauge,
  shield: Shield,
  "user-round": UserRound,
  "message-square": MessageSquare,
  "users-round": UsersRound,
  star: Star,
  search: Search,
  "loader-circle": LoaderCircle
};

function RoleCard({ role, onOpen }) {
  const Icon = roleIcons[role.icon] ?? ClipboardCheck;

  return (
    <button className="role-card corner-frame" type="button" onClick={() => onOpen(role.id)}>
      <Icon className="role-card__icon" size={26} strokeWidth={1.65} />
      <span className="role-card__title">{role.label}</span>
    </button>
  );
}

export function RoleSelection({ roles, onOpen }) {
  return (
    <main className="role-screen">
      <section className="role-shell" aria-labelledby="role-selection-title">
        <TaapLogo />
        <h1 id="role-selection-title">Enterprise QE Platform</h1>
        <p>Select your role to continue. TAAP tailors screens, navigation and AI assistance to how you work.</p>
        <div className="role-grid" aria-label="Enterprise role options">
          {roles.map((role) => (
            <RoleCard key={role.id} role={role} onOpen={onOpen} />
          ))}
        </div>
      </section>
    </main>
  );
}
