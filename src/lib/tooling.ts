import fs from "node:fs";
import path from "node:path";

export type ToolRisk = "LOW" | "MEDIUM" | "HIGH";
export type ToolName =
  | "open-browser-search"
  | "create-folder"
  | "open-notepad"
  | "find-files"
  | "run-powershell";

export interface ToolRequest {
  name: ToolName;
  risk: ToolRisk;
  requiresConfirmation?: boolean;
  confirmed?: boolean;
  params?: Record<string, string | number | boolean | undefined>;
}

export interface ToolExecutionResult {
  ok: boolean;
  action: ToolName;
  message: string;
  output?: string[];
}

const blockedPowerShellPatterns = [
  /remove-item/i,
  /delete/i,
  /stop-process/i,
  /start-process/i,
  /invoke-webrequest/i,
  /curl\s+/i,
  /wget\s+/i,
  /reg\s+delete/i,
  /del\s+\/s\s*\/q/i,
  /rmdir\s+\/s\s*\/q/i,
  /format-volume/i,
  /shutdown/i,
];

export const canExecuteTool = (
  request: Pick<
    ToolRequest,
    "name" | "risk" | "requiresConfirmation" | "confirmed"
  >,
  userConfirmed: boolean,
): boolean => {
  if (request.risk === "LOW") {
    return true;
  }

  if (request.requiresConfirmation) {
    return Boolean(request.confirmed ?? userConfirmed);
  }

  return true;
};

export const buildSearchUrl = (query: string): string => {
  const normalized = (query ?? "").trim() || "AI automation";
  return `https://www.google.com/search?q=${encodeURIComponent(normalized).replace(/%20/g, "+")}`;
};

export const validatePowerShellCommand = (command: string): boolean => {
  const normalized = String(command ?? "").trim();
  if (!normalized) {
    return false;
  }

  if (blockedPowerShellPatterns.some((pattern) => pattern.test(normalized))) {
    return false;
  }

  return /^(Get-|Test-|Write-|Out-|Select-|Where-|Sort-|Measure-|Compare-|Resolve-|Split-|Join-|Set-Location|cd\s|echo\s|Write-Output\s)/i.test(
    normalized,
  );
};

export const listFiles = (
  rootPath: string,
  extensions: string[] = [],
  maxResults = 25,
): string[] => {
  const resolvedRoot = rootPath || ".";
  const files = [] as string[];
  const visited = new Set<string>();

  const walk = (currentPath: string) => {
    if (files.length >= maxResults) {
      return;
    }

    if (!currentPath || visited.has(currentPath)) {
      return;
    }
    visited.add(currentPath);

    try {
      const directoryEntries = fs.readdirSync(currentPath, {
        withFileTypes: true,
      });
      for (const entry of directoryEntries) {
        const entryPath = path.join(currentPath, entry.name);
        if (entry.isDirectory()) {
          walk(entryPath);
        } else if (
          !extensions.length ||
          extensions.includes(path.extname(entry.name).slice(1))
        ) {
          files.push(entryPath);
          if (files.length >= maxResults) {
            return;
          }
        }
      }
    } catch {
      // Ignore unreadable directories.
    }
  };

  walk(resolvedRoot);
  return files;
};
