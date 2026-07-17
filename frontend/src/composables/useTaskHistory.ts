import type { TaskHistoryEntry, TaskResult, TaskType } from "../types";

export const createHistoryEntry = (
  taskType: TaskType,
  taskResult: TaskResult,
): TaskHistoryEntry => ({
  id: crypto.randomUUID(),
  createdAt: new Date().toISOString(),
  taskType,
  status: taskResult.status,
  summary: taskResult.summary,
  firstOutput: taskResult.outputs[0] ?? null,
});

export const appendHistoryEntry = (
  history: TaskHistoryEntry[],
  entry: TaskHistoryEntry,
  limit: number,
): TaskHistoryEntry[] => [entry, ...history].slice(0, Math.max(1, limit));
