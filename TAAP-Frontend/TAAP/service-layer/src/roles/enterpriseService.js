import { serviceEnvironment } from "../environment.js";
import { clone } from "../shared/clone.js";
import { getMockUserForRole } from "../users/mockUsers.js";
import { enterpriseMenuGroups } from "./enterpriseMenu.js";
import { enterpriseRoles } from "./enterpriseRoles.js";
import { sdetMenuGroups } from "../sdet/sdetMenu.js";

// Each role with navigation owns its own menu so QE and SDET can diverge.
const menuGroupsByRole = {
  "qe-engineers": enterpriseMenuGroups,
  sdets: sdetMenuGroups
};

function menuGroupsForRole(roleId) {
  return menuGroupsByRole[roleId] ?? enterpriseMenuGroups;
}

export async function fetchEnterpriseRoles() {
  return clone(enterpriseRoles);
}

export async function openEnterprise(roleId) {
  const role = enterpriseRoles.find((item) => item.id === roleId);

  if (!role) {
    throw new Error(`Unknown enterprise role: ${roleId}`);
  }

  return {
    role: clone(role),
    hasNavigation: role.hasNavigation,
    user: serviceEnvironment.isMock ? clone(getMockUserForRole(roleId)) : null,
    menuGroups: role.hasNavigation ? clone(menuGroupsForRole(role.id)) : [],
    activeSectionId: "home"
  };
}

export async function openEnterpriseSection(roleId, sectionId) {
  const enterprise = await openEnterprise(roleId);
  const section = enterprise.menuGroups
    .flatMap((group) => group.items)
    .find((item) => item.id === sectionId);

  if (!enterprise.hasNavigation) {
    return {
      role: enterprise.role,
      section: null,
      pageState: "blank"
    };
  }

  return {
    role: enterprise.role,
    section: section ? clone(section) : null,
    pageState: "blank"
  };
}
