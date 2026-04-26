import { authRequest } from "./_core.js";
import { ROUTES } from "./_routes.js";

export function getTasks() {
  return authRequest(ROUTES.TASKS.LIST, { method: "GET" });
}

export function createTask(taskData) {
  return authRequest(ROUTES.TASKS.CREATE, {
    method: "POST",
    body: JSON.stringify(taskData),
  });
}

export function completeTask(taskName) {
  return authRequest(ROUTES.TASKS.COMPLETE, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}

export function startTask(taskName) {
  return authRequest(ROUTES.TASKS.START, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}
