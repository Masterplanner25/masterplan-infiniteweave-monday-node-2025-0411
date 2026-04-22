import { authRequest } from "./_core.js";

export function getTasks() {
  return authRequest(`/tasks/list`, { method: "GET" });
}

export function createTask(taskData) {
  return authRequest(`/tasks/create`, {
    method: "POST",
    body: JSON.stringify(taskData),
  });
}

export function completeTask(taskName) {
  return authRequest(`/tasks/complete`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}

export function startTask(taskName) {
  return authRequest(`/tasks/start`, {
    method: "POST",
    body: JSON.stringify({ name: taskName }),
  });
}
