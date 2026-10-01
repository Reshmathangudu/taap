import { useEffect } from "react";
import { ChevronDown, X } from "lucide-react";
import "./sdet-shared.css";

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function startOfDay(date) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function formatClock(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

/** "Today 06:40", "Yesterday 23:20", "Fri 21:35", "1 Sep 02:40" */
export function formatWhen(value, { withTime = true } = {}) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const dayDiff = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000);
  const time = withTime ? ` ${formatClock(date)}` : "";

  if (dayDiff === 0) return `Today${time}`;
  if (dayDiff === 1) return `Yesterday${withTime ? time : ""}`;
  if (dayDiff > 1 && dayDiff < 7) return `${WEEKDAYS[date.getDay()]}${time}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]}${time}`;
}

/** "Today, 23:00" / "Tomorrow 06:00" / "Fri 21:00" / "1 Oct 02:00" */
export function formatNextRun(value) {
  if (!value) return "Paused";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const dayDiff = Math.round((startOfDay(date) - startOfDay(new Date())) / 86400000);
  if (dayDiff === 0) return `Today, ${formatClock(date)}`;
  if (dayDiff === 1) return `Tomorrow ${formatClock(date)}`;
  if (dayDiff > 1 && dayDiff < 7) return `${WEEKDAYS[date.getDay()]} ${formatClock(date)}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${formatClock(date)}`;
}

/** "in 15h 40m" */
export function formatCountdown(value) {
  if (!value) return "";
  const diff = new Date(value).getTime() - Date.now();
  if (!Number.isFinite(diff) || diff <= 0) return "due now";
  const totalMinutes = Math.round(diff / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `in ${days}d ${hours}h`;
  return `in ${hours}h ${String(minutes).padStart(2, "0")}m`;
}

export function scheduleSummary(schedule) {
  if (!schedule) return "-";
  if (schedule.frequency === "Weekly") return `Weekly · ${schedule.dayOfWeek} ${schedule.time}`;
  if (schedule.frequency === "Monthly") return `Monthly · ${ordinal(schedule.dayOfMonth ?? 1)} ${schedule.time}`;
  if (schedule.frequency === "Run once") return `Once · ${schedule.time}`;
  return `Daily ${schedule.time}`;
}

function ordinal(number) {
  const remainder = number % 100;
  if (remainder >= 11 && remainder <= 13) return `${number}th`;
  const suffix = { 1: "st", 2: "nd", 3: "rd" }[number % 10] ?? "th";
  return `${number}${suffix}`;
}

export function environmentTone(environment) {
  const value = String(environment ?? "").toLowerCase();
  if (value === "qa") return "green";
  if (value === "uat") return "amber";
  if (value === "stage" || value === "staging") return "blue";
  return "gray";
}

export function downloadCsv(filename, header, rows) {
  const escapeCell = (cell) => {
    const text = String(cell ?? "");
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const csv = [header, ...rows].map((row) => row.map(escapeCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------------ */
/* Page chrome                                                          */
/* ------------------------------------------------------------------ */

export function SdetPage({ ariaLabel, breadcrumbs = [], title, status, tabs = [], activeTab, onTabChange, notes = [], footer, children }) {
  return (
    <section className="sdet-page" aria-label={ariaLabel ?? title}>
      <header className="sdet-page__head">
        <nav className="sdet-page__crumbs" aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <span key={crumb}>
              {index > 0 ? <em>/</em> : null}
              {crumb}
            </span>
          ))}
        </nav>
        <div className="sdet-page__title-row">
          <h1>{title}</h1>
          {status ? (
            <span className={`sdet-page__status sdet-page__status--${status.tone ?? "green"}`}>
              {status.icon}
              {status.text}
            </span>
          ) : null}
        </div>
        {tabs.length > 0 ? (
          <div className="sdet-tabs" role="tablist">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={tab.id === activeTab}
                className={`sdet-tab ${tab.id === activeTab ? "sdet-tab--active" : ""}`}
                onClick={() => onTabChange?.(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        ) : null}
        {notes.length > 0 ? (
          <p className="sdet-page__notes">
            {notes.map((note, index) => (
              <span key={note}>
                {index === 0 ? <i /> : <em>·</em>}
                {note}
              </span>
            ))}
          </p>
        ) : null}
      </header>
      <div className="sdet-page__body">{children}</div>
      {footer ? (
        <footer className="sdet-page__footer">
          <span className="sdet-page__footer-summary">{footer.summary}</span>
          <div className="sdet-page__footer-actions">{footer.actions}</div>
        </footer>
      ) : null}
    </section>
  );
}

export function SdetPanel({ label, aside, className = "", children }) {
  return (
    <section className={`sdet-panel corner-frame ${className}`}>
      {label ? (
        <div className="sdet-panel__label-row">
          <h2 className="sdet-panel__label">{label}</h2>
          {aside ? <span className="sdet-panel__aside">{aside}</span> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function SdetField({ label, hint, className = "", children }) {
  return (
    <div className={`sdet-field ${className}`}>
      {label ? <span className="sdet-field__label">{label}</span> : null}
      {children}
      {hint ? <span className="sdet-hint">{hint}</span> : null}
    </div>
  );
}

export function SdetInput({ value, meta, mono = false, readOnly = false, placeholder, onChange, type = "text", ariaLabel }) {
  return (
    <label className={`sdet-input ${mono ? "sdet-input--mono" : ""} ${readOnly ? "sdet-input--readonly" : ""}`}>
      <input
        type={type}
        value={value}
        readOnly={readOnly}
        placeholder={placeholder}
        aria-label={ariaLabel}
        onChange={(event) => onChange?.(event.target.value)}
      />
      {meta ? <span className="sdet-input__meta">{meta}</span> : null}
    </label>
  );
}

export function SdetSelect({ value, options, onChange, dot, ariaLabel, disabled = false }) {
  return (
    <label className="sdet-select">
      {dot ? <i className={`sdet-dot sdet-dot--${dot}`} /> : null}
      <select value={value} aria-label={ariaLabel} disabled={disabled} onChange={(event) => onChange?.(event.target.value)}>
        {options.map((option) => {
          const item = typeof option === "string" ? { value: option, label: option } : option;
          return (
            <option key={item.value} value={item.value} disabled={item.disabled}>
              {item.label}
            </option>
          );
        })}
      </select>
      <ChevronDown size={15} strokeWidth={1.8} />
    </label>
  );
}

export function SdetTextarea({ value, onChange, rows = 3, placeholder, readOnly = false, ariaLabel }) {
  return (
    <textarea
      className={`sdet-textarea ${readOnly ? "sdet-input--readonly" : ""}`}
      rows={rows}
      value={value}
      readOnly={readOnly}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(event) => onChange?.(event.target.value)}
    />
  );
}

export function SdetToggleGroup({ options, selected, multi = false, onChange, ariaLabel }) {
  const isOn = (id) => (multi ? selected.includes(id) : selected === id);

  function toggle(id) {
    if (!multi) {
      onChange?.(id);
      return;
    }
    onChange?.(isOn(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  }

  return (
    <div className="sdet-toggle" role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const item = typeof option === "string" ? { id: option, label: option } : option;
        const on = isOn(item.id);
        return (
          <button
            key={item.id}
            type="button"
            aria-pressed={on}
            className={`sdet-toggle__btn ${on ? "sdet-toggle__btn--on" : ""}`}
            onClick={() => toggle(item.id)}
          >
            {item.label}
            {multi && on ? " ✓" : ""}
          </button>
        );
      })}
    </div>
  );
}

export function SdetChips({ items, onRemove, onAdd, placeholder = "Add…" }) {
  return (
    <div className="sdet-chips">
      {items.map((item) => (
        <span key={item} className="sdet-chip">
          {item}
          {onRemove ? (
            <button type="button" aria-label={`Remove ${item}`} onClick={() => onRemove(item)}>
              <X size={12} strokeWidth={2} />
            </button>
          ) : null}
        </span>
      ))}
      {onAdd ? (
        <input
          className="sdet-chips__input"
          placeholder={placeholder}
          aria-label={placeholder}
          onKeyDown={(event) => {
            if (event.key === "Enter" && event.currentTarget.value.trim()) {
              onAdd(event.currentTarget.value.trim());
              event.currentTarget.value = "";
            }
          }}
        />
      ) : null}
    </div>
  );
}

export function SdetStat({ label, value, detail, tone = "default", swatch }) {
  return (
    <div className="sdet-stat corner-frame">
      <span className="sdet-stat__label">
        {swatch ? <i className={`sdet-swatch sdet-swatch--${swatch}`} /> : null}
        {label}
      </span>
      <span className={`sdet-stat__value sdet-stat__value--${tone}`}>
        {value}
        {detail ? <small>{detail}</small> : null}
      </span>
    </div>
  );
}

export function SdetPill({ tone = "gray", children, className = "" }) {
  return <span className={`sdet-pill sdet-pill--${tone} ${className}`}>{children}</span>;
}

export function SdetReason({ reason }) {
  const tone = reason.startsWith("Script") ? "failure" : reason.startsWith("Flaky") ? "flaky" : "enhancement";
  return <span className={`sdet-reason sdet-reason--${tone}`}>{reason}</span>;
}

export function SdetFilters({ label, filters, active, onChange, note }) {
  return (
    <div className="sdet-filters">
      {label ? <span className="sdet-filters__label">{label}</span> : null}
      {filters.map((filter) => (
        <button
          key={filter.id}
          type="button"
          className={`sdet-filter ${filter.id === active ? "sdet-filter--active" : ""}`}
          onClick={() => onChange(filter.id)}
        >
          {filter.label}
          {filter.count != null ? ` ${filter.count}` : ""}
        </button>
      ))}
      {note ? <span className="sdet-filters__note">{note}</span> : null}
    </div>
  );
}

export function SdetToast({ message, onDone, duration = 3200 }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => onDone?.(), duration);
    return () => window.clearTimeout(timer);
  }, [message, duration, onDone]);

  if (!message) return null;
  return (
    <div className="sdet-toast" role="status">
      {message}
    </div>
  );
}

export function SdetLoading({ label = "Loading…" }) {
  return <div className="sdet-loading">{label}</div>;
}

export function SdetError({ message, onRetry }) {
  return (
    <div className="sdet-error" role="alert">
      <span>{message}</span>
      {onRetry ? (
        <button type="button" className="sdet-btn sdet-btn--sm" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function JiraStatusLine({ jira }) {
  if (!jira) return null;
  if (jira.mode === "mock") return <span className="sdet-jira sdet-jira--off">Sample data · Jira sync disabled (VITE_TAAP_IS_MOCK=true)</span>;
  if (!jira.connected) return <span className="sdet-jira sdet-jira--off">Jira unavailable · {jira.error || "using sample data"}</span>;
  return (
    <span className="sdet-jira sdet-jira--on">
      <i />
      Jira · {jira.projectKey} · {jira.counts.stories} stories · {jira.counts.bugs} bugs · fetched {formatClock(jira.fetchedAt)}
    </span>
  );
}
