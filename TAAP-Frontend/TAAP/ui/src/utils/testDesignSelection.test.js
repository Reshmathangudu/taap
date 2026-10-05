import test from "node:test";
import assert from "node:assert/strict";
import { testDesignRequirements } from "./testDesignSelection.js";

const story = { key: "A-10", type: "Story", parentKey: "A-1" };
const story2 = { key: "A-11", type: "Story", parentKey: "A-2" };
const epic1 = { key: "A-1", type: "Epic", children: [story] };
const epic2 = { key: "A-2", type: "Epic" };
const all = [epic1, epic2, story];

test("focused epic or single story is used when no checkboxes are selected", () => {
  assert.deepEqual(testDesignRequirements(all, [], epic1), [story]);
  assert.deepEqual(testDesignRequirements(all, [], story), [story]);
});

test("checked selection keeps only one story for test-case creation", () => {
  assert.deepEqual(testDesignRequirements(all, ["A-1", "A-2", "A-1"], story), []);
  assert.deepEqual(testDesignRequirements(all, ["A-1", "A-10"], epic2), [story]);
  assert.deepEqual(testDesignRequirements(all, ["REMOVED-1"], epic2), []);
});

test("first checked story wins if older state contains multiple stories", () => {
  assert.deepEqual(testDesignRequirements([...all, story2], ["A-10", "A-11"], epic2), [story]);
});
