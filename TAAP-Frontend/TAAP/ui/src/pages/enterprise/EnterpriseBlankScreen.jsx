import { EnterpriseHeader } from "../../components/EnterpriseHeader.jsx";

export function EnterpriseBlankScreen({ role, onHome }) {
  return (
    <main className="enterprise-screen">
      <EnterpriseHeader role={role} onHome={onHome} />
      <section className="standalone-blank-screen" aria-label={`${role.label} blank page`} />
    </main>
  );
}
