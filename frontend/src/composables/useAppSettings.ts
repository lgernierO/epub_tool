import type { AppSettings, FontDecryptSettings, OcrCharPolicy } from "../types";

export const defaultSettings: AppSettings = {
  autoOpenOutputFolder: false,
  autoOpenLogFile: false,
  autoCheckUpdates: true,
  keepHistoryCount: 10,
  pythonWorkerAutoRestartLimit: 2,
  taskConcurrency: 1,
};

export const defaultFontDecryptSettings: FontDecryptSettings = {
  ocrCharPolicy: "strict",
  minOcrConfidence: 0.8,
};

export const normalizePythonWorkerAutoRestartLimit = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return defaultSettings.pythonWorkerAutoRestartLimit;
  }
  return Math.max(0, Math.min(5, Math.round(numeric)));
};

export const normalizeTaskConcurrency = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return defaultSettings.taskConcurrency;
  }
  return Math.max(1, Math.min(4, Math.round(numeric)));
};

export const normalizeOcrCharPolicy = (
  value: unknown,
  allowed: OcrCharPolicy[] = ["strict", "compatible"],
): OcrCharPolicy =>
  allowed.includes(value as OcrCharPolicy)
    ? (value as OcrCharPolicy)
    : defaultFontDecryptSettings.ocrCharPolicy;

export const normalizeMinOcrConfidence = (value: unknown): number => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return defaultFontDecryptSettings.minOcrConfidence;
  }
  return Math.max(0, Math.min(1, numeric));
};

export const normalizeFontDecryptSettings = (value: unknown): FontDecryptSettings => {
  const raw =
    value && typeof value === "object"
      ? (value as Partial<FontDecryptSettings>)
      : {};
  return {
    ocrCharPolicy: normalizeOcrCharPolicy(raw.ocrCharPolicy),
    minOcrConfidence: normalizeMinOcrConfidence(raw.minOcrConfidence),
  };
};

export const normalizeSettings = (value: unknown): AppSettings => {
  const raw =
    value && typeof value === "object"
      ? (value as Partial<AppSettings> & {
          autoOpenFirstOutput?: boolean;
          autoCheckUpdate?: boolean;
        })
      : {};

  return {
    autoOpenOutputFolder:
      typeof raw.autoOpenOutputFolder === "boolean"
        ? raw.autoOpenOutputFolder
        : typeof raw.autoOpenFirstOutput === "boolean"
          ? raw.autoOpenFirstOutput
          : defaultSettings.autoOpenOutputFolder,
    autoOpenLogFile:
      typeof raw.autoOpenLogFile === "boolean"
        ? raw.autoOpenLogFile
        : defaultSettings.autoOpenLogFile,
    autoCheckUpdates:
      typeof raw.autoCheckUpdates === "boolean"
        ? raw.autoCheckUpdates
        : typeof raw.autoCheckUpdate === "boolean"
          ? raw.autoCheckUpdate
          : defaultSettings.autoCheckUpdates,
    keepHistoryCount:
      typeof raw.keepHistoryCount === "number"
        ? raw.keepHistoryCount
        : defaultSettings.keepHistoryCount,
    pythonWorkerAutoRestartLimit: normalizePythonWorkerAutoRestartLimit(
      raw.pythonWorkerAutoRestartLimit,
    ),
    taskConcurrency: normalizeTaskConcurrency(raw.taskConcurrency),
  };
};
