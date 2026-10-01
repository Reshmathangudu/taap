import type { TestCase } from "../../types/testCase";

export interface SignoffState {
  loading: boolean;
  error: string | null;
  queue: TestCase[];
  highlightId: string | null;
  modalTest: TestCase | null;
  submitting: boolean;
  noteError: boolean;
  submitError: string | null;
}

export const initialState: SignoffState = {
  loading: true,
  error: null,
  queue: [],
  highlightId: null,
  modalTest: null,
  submitting: false,
  noteError: false,
  submitError: null,
};

export type SignoffAction =
  | { type: "LOAD_START" }
  | { type: "LOAD_SUCCESS"; queue: TestCase[] }
  | { type: "LOAD_ERROR"; error: string }
  | { type: "HIGHLIGHT"; testId: string }
  | { type: "OPEN_MODAL"; test: TestCase }
  | { type: "CLOSE_MODAL" }
  | { type: "SUBMIT_START" }
  | { type: "SUBMIT_NOTE_MISSING" }
  | { type: "SUBMIT_ERROR"; error: string }
  | { type: "SUBMIT_SUCCESS"; testId: string };

export function signoffReducer(state: SignoffState, action: SignoffAction): SignoffState {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, loading: true, error: null };
    case "LOAD_SUCCESS":
      return { ...state, loading: false, queue: action.queue };
    case "LOAD_ERROR":
      return { ...state, loading: false, error: action.error };
    case "HIGHLIGHT":
      return { ...state, highlightId: action.testId };
    case "OPEN_MODAL":
      return { ...state, modalTest: action.test, noteError: false, submitError: null };
    case "CLOSE_MODAL":
      return { ...state, modalTest: null, noteError: false, submitError: null };
    case "SUBMIT_START":
      return { ...state, submitting: true, noteError: false, submitError: null };
    case "SUBMIT_NOTE_MISSING":
      return { ...state, submitting: false, noteError: true };
    case "SUBMIT_ERROR":
      return { ...state, submitting: false, submitError: action.error };
    case "SUBMIT_SUCCESS":
      return {
        ...state,
        submitting: false,
        modalTest: null,
        queue: state.queue.filter((t) => t.id !== action.testId),
      };
    default:
      return state;
  }
}
