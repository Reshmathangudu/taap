import type { Classification, TestCase } from "../../types/testCase";

export type FilterValue = "all" | Classification;

export interface TestSelectionState {
  loading: boolean;
  error: string | null;
  tests: TestCase[];
  filter: FilterValue;
  search: string;
  selected: TestCase | null;
  view: "list" | "detail";
}

export const initialState: TestSelectionState = {
  loading: true,
  error: null,
  tests: [],
  filter: "all",
  search: "",
  selected: null,
  view: "list",
};

export type TestSelectionAction =
  | { type: "LOAD_START" }
  | { type: "LOAD_SUCCESS"; tests: TestCase[] }
  | { type: "LOAD_ERROR"; error: string }
  | { type: "SET_FILTER"; filter: FilterValue }
  | { type: "SET_SEARCH"; search: string }
  | { type: "OPEN_DETAIL"; test: TestCase }
  | { type: "BACK_TO_LIST" };

export function testSelectionReducer(
  state: TestSelectionState,
  action: TestSelectionAction
): TestSelectionState {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, loading: true, error: null };
    case "LOAD_SUCCESS":
      return { ...state, loading: false, tests: action.tests };
    case "LOAD_ERROR":
      return { ...state, loading: false, error: action.error };
    case "SET_FILTER":
      return { ...state, filter: action.filter };
    case "SET_SEARCH":
      return { ...state, search: action.search };
    case "OPEN_DETAIL":
      return { ...state, selected: action.test, view: "detail" };
    case "BACK_TO_LIST":
      return { ...state, view: "list" };
    default:
      return state;
  }
}

export function visibleTests(state: TestSelectionState): TestCase[] {
  const term = state.search.trim().toLowerCase();
  return state.tests.filter((t) => {
    const matchesFilter = state.filter === "all" || t.classification === state.filter;
    const matchesSearch =
      term === "" || t.name.toLowerCase().includes(term) || t.id.toLowerCase().includes(term);
    return matchesFilter && matchesSearch;
  });
}
