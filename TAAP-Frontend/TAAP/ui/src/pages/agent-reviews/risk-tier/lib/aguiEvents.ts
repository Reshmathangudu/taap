// Cross-panel signaling for independently-mounted AGUI components.
//
// TestSelectionReport and ExclusionSignoffQueue are two separate components
// that Spider's Workbench mounts side by side — neither imports the other,
// and neither shares React state or context with the other (that's the
// whole point of the Level 2/AGUI split: each panel must work if it's the
// only one on the page). But the product does need one small signal to
// cross between them: "the user wants to look at this test's sign-off".
//
// This mirrors the plain CustomEvent approach used in the HTML prototype's
// panel1/panel2 split. Dispatching on `window` is the right layer for now
// because it doesn't assume anything about how Spider's shell composes the
// two components (same page, same iframe, whatever) beyond "same
// document". If Spider's AGUI host contract turns out to offer a proper
// message-passing API (postMessage across iframes, a provided event bus,
// etc.), swap the implementation here — every component only imports the
// functions below, never `window` directly, so the call sites don't change.

export interface NavigateToSignoffDetail {
  testId: string;
}

const NAVIGATE_TO_SIGNOFF = "agui:navigate-to-signoff";

export function dispatchNavigateToSignoff(testId: string): void {
  window.dispatchEvent(
    new CustomEvent<NavigateToSignoffDetail>(NAVIGATE_TO_SIGNOFF, { detail: { testId } })
  );
}

/** Subscribe to the navigate-to-signoff signal; returns an unsubscribe function. */
export function onNavigateToSignoff(handler: (detail: NavigateToSignoffDetail) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<NavigateToSignoffDetail>).detail);
  window.addEventListener(NAVIGATE_TO_SIGNOFF, listener);
  return () => window.removeEventListener(NAVIGATE_TO_SIGNOFF, listener);
}
