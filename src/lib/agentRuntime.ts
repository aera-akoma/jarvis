import type {
  AgentTask,
  ModelDefinition,
  ProviderAdapterResult,
} from "./types";

const uid = (prefix: string) =>
  `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;

export const createTaskState = (
  objective: string,
  initialModelId?: string,
): AgentTask => ({
  id: uid("task"),
  objective,
  status: "active",
  progress: 0,
  completed: ["Task created"],
  current: "Capturing objective and model context",
  remaining: ["Continue analysis", "Finalize output"],
  modelHistory: initialModelId ? [initialModelId] : [],
  fallbackOrder: initialModelId ? [initialModelId] : [],
  contextSummary: `Objective: ${objective}`,
  lastModelId: initialModelId,
});

export const buildTaskContextSnapshot = (task: AgentTask) => ({
  objective: task.objective,
  progress: task.progress,
  completed: task.completed,
  current: task.current,
  remaining: task.remaining,
  modelHistory: task.modelHistory,
  lastModelId: task.lastModelId,
});

export const switchModelPreservingTask = (
  task: AgentTask,
  nextModelId: string,
  nextModelLabel: string,
) => {
  const nextHistory = [...task.modelHistory, nextModelId];
  const updated: AgentTask = {
    ...task,
    modelHistory: nextHistory,
    fallbackOrder: [...new Set([...task.fallbackOrder, nextModelId])],
    lastModelId: nextModelId,
    contextSummary: JSON.stringify(buildTaskContextSnapshot(task)),
    status: "active",
  };

  return {
    task: updated,
    preserved: true,
    summary: `Switched to ${nextModelLabel}. Objective and task state were preserved without restarting.`,
  };
};

export const validateModelCapabilities = (
  model: Pick<ModelDefinition, "capabilities">,
  requiredCapabilities: string[],
) =>
  requiredCapabilities.every((capability) =>
    model.capabilities.includes(capability),
  );

export const buildFallbackOrder = (primary: string, ...fallbacks: string[]) => [
  primary,
  ...fallbacks,
];

export const runModelSwitchSequence = (task: AgentTask, sequence: string[]) => {
  let currentTask = { ...task };
  return sequence.map((modelId, index) => {
    const label = modelId;
    const result = switchModelPreservingTask(currentTask, modelId, label);
    currentTask = result.task;
    return {
      ...result,
      index,
      preserved: result.preserved,
    };
  });
};

export const simulateProviderRequest = (
  model: Pick<
    ModelDefinition,
    "id" | "providerId" | "displayName" | "capabilities"
  >,
  prompt: string,
  requiredCapabilities: string[] = ["text"],
): ProviderAdapterResult => {
  if (!validateModelCapabilities(model, requiredCapabilities)) {
    return {
      ok: false,
      modelId: model.id,
      providerId: model.providerId,
      error: `The selected model does not support the required capabilities: ${requiredCapabilities.join(", ")}`,
      status: "capability-mismatch",
      content: "",
    };
  }

  const trimmed = prompt.trim();
  if (!trimmed) {
    return {
      ok: false,
      modelId: model.id,
      providerId: model.providerId,
      error: "Prompt is empty.",
      status: "invalid-input",
      content: "",
    };
  }

  return {
    ok: true,
    modelId: model.id,
    providerId: model.providerId,
    content: `${model.displayName} processed the request: ${trimmed.slice(0, 160)}${trimmed.length > 160 ? "…" : ""}`,
    status: "ok",
  };
};
