export const mockUsersByRole = {
  "qe-engineers": {
    name: "Mohit Bhardwaj",
    position: "QE Engineer"
  },
  sdets: {
    name: "Alex Rivera",
    position: "SDET · Quality Eng"
  }
};

export function getMockUserForRole(roleId) {
  return mockUsersByRole[roleId] ?? null;
}
