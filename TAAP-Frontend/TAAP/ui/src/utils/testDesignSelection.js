export function testDesignRequirements(requirements, checkedKeys, selected) {
  const checked = new Set(checkedKeys);
  const selection = checked.size ? requirements.filter(item => checked.has(item.key)) : selected ? [selected] : [];
  return [...new Map(selection.map(item => [item.key, item])).values()];
}
