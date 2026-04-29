// SHIM — scheduled for deletion after 2026-05-28 (one release cycle from 2026-04-28).
// All callers migrated to platform.js. Delete this file when V1-VAL-019 passes fully.
// To remove: delete this file, remove the legacy.js entries from api/index.js.
export {
  getDashboardOverview,
  getDashboardHealth,
  getInfluenceGraph,
  getCausalGraph,
  getNarrative,
} from "./platform.js";
