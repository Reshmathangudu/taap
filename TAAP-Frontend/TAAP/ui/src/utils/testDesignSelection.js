function isStory(requirement) {
  return ["story", "user story"].includes(String(requirement?.type ?? "").toLowerCase());
}

function uniqueByKey(requirements) {
  const seen = new Set();
  return requirements.filter((requirement) => {
    const key = requirement?.key;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function testDesignRequirements(requirements, checkedKeys, selected) {
  const checked = new Set(checkedKeys);

  if (checked.size) {
    const story = requirements.find(item => checked.has(item.key) && isStory(item));
    return story ? [story] : [];
  }

  if (!selected) return [];
  if (isStory(selected)) return [selected];

  if (String(selected?.type ?? "").toLowerCase() === "epic") {
    return uniqueByKey([
      ...((Array.isArray(selected.children) ? selected.children : []).filter(isStory)),
      ...requirements.filter(item => isStory(item) && item.parentKey === selected.key)
    ]);
  }

  return [];
}
