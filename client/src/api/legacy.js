// Migrated to platform.js. This file is kept for one release cycle
// so any indirect callers continue to resolve. Remove after all
// direct imports have been updated to platform.js.
export {
  getDashboardOverview,
  getDashboardHealth,
  getInfluenceGraph,
  getCausalGraph,
  getNarrative,
} from "./platform.js";
