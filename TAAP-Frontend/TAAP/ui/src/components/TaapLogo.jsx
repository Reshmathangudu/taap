import { Check } from "lucide-react";

export function TaapLogo({ compact = false, onClick }) {
  const className = `taap-logo ${compact ? "taap-logo--compact" : ""}`;
  const logoContent = (
    <>
      <span className="taap-logo__mark">
        <Check size={16} strokeWidth={1.5} />
      </span>
      <span className="taap-logo__word">TAAP</span>
    </>
  );

  if (!onClick) {
    return (
      <div className={className} aria-label="TAAP">
        {logoContent}
      </div>
    );
  }

  return (
    <button className={className} type="button" aria-label="Back to role selection" onClick={onClick}>
      {logoContent}
    </button>
  );
}
