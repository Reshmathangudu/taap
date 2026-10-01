import test from "node:test";
import assert from "node:assert/strict";
import { testDesignRequirements } from "./testDesignSelection.js";

const epic1 = { key: "A-1", type: "Epic" };
const epic2 = { key: "A-2", type: "Epic" };
const story = { key: "A-10", type: "Story", parentKey: "A-1" };
const all = [epic1, epic2, story];

test("focused single epic or story is used when no checkboxes are selected", () => {
  assert.deepEqual(testDesignRequirements(all, [], epic1), [epic1]);
  assert.deepEqual(testDesignRequirements(all, [], story), [story]);
});

test("checked selections override focus and retain epics hidden by search", () => {
  assert.deepEqual(testDesignRequirements(all, ["A-1", "A-2", "A-1"], story), [epic1, epic2]);
  assert.deepEqual(testDesignRequirements(all, ["A-1", "A-10"], epic2), [epic1, story]);
  assert.deepEqual(testDesignRequirements(all, ["REMOVED-1"], epic2), []);
});
