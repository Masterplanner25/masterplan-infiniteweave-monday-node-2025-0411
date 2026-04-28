import { authRequest, taggedRequest, unwrapEnvelope } from "./_core.js";
import { ROUTES } from "./_routes.js";

export const getTasks = taggedRequest("tasks", () =>
  authRequest(ROUTES.TASKS.LIST, { method: "GET" }).then(unwrapEnvelope)
);

export const createTask = taggedRequest("tasks", (taskData) =>
  authRequest(ROUTES.TASKS.CREATE, {
    method: "POST",
    body: JSON.stringify(taskData),
  }).then(unwrapEnvelope)
);

export const completeTask = taggedRequest("tasks", (taskName) =>
  authRequest(ROUTES.TASKS.COMPLETE, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  }).then(unwrapEnvelope)
);

export const startTask = taggedRequest("tasks", (taskName) =>
  authRequest(ROUTES.TASKS.START, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  }).then(unwrapEnvelope)
);
