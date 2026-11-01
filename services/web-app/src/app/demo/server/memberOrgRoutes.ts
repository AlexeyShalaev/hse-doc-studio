import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import type { MyOrg } from "@entities/session";
import type { DemoOrg } from "./adminOrgs";
import { adminOrgsOf, type ServerDemoWorld } from "./world";

// Демо раздела «Организации» в настройках: мои организации и выход из них.
// Правила настоящего API: единственный владелец не выходит (409 last_owner),
// чужая организация это 404. После выхода меняется и список ролей в bootstrap.

export const createMemberOrgRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const summary = (org: DemoOrg, userId: string): MyOrg | null => {
    const me = org.members.find((m) => m.user_id === userId);
    if (!me) return null;
    const owners = org.members.filter((m) => m.role === "owner").length;
    return {
      slug: org.slug,
      name: org.name,
      my_role: me.role,
      member_count: org.members.length,
      groups: org.groups
        .filter((g) => g.member_ids.includes(userId))
        .map((g) => g.name),
      sole_owner: me.role === "owner" && owners === 1,
    };
  };

  return [
    {
      method: "GET",
      pattern: "/account/orgs",
      handler: () => {
        const world = getWorld();
        const user = world.bootstrap.user;
        if (!user) {
          return demoError(401, "auth_required", "Authentication required");
        }
        const items = adminOrgsOf(world).orgs.flatMap((org) => {
          const item = summary(org, user.id);
          return item ? [item] : [];
        });
        return demoJson(items);
      },
    },
    {
      method: "DELETE",
      pattern: "/account/orgs/:slug/membership",
      handler: (req) => {
        const world = getWorld();
        const user = world.bootstrap.user;
        if (!user) {
          return demoError(401, "auth_required", "Authentication required");
        }
        const org = adminOrgsOf(world).orgs.find(
          (o) => o.slug === req.params.slug,
        );
        const item = org ? summary(org, user.id) : null;
        if (!org || !item) return demoError(404, "not_found", "Not Found");
        if (item.sole_owner) {
          return demoError(409, "last_owner", "Sole owner cannot leave");
        }
        org.members = org.members.filter((m) => m.user_id !== user.id);
        for (const group of org.groups) {
          group.member_ids = group.member_ids.filter((id) => id !== user.id);
        }
        world.bootstrap = {
          ...world.bootstrap,
          user: {
            ...user,
            org_roles: user.org_roles.filter((o) => o.slug !== org.slug),
          },
        };
        return demoNoContent();
      },
    },
  ];
};
