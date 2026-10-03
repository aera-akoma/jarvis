import { describe, expect, it } from "vitest";
import {
  buildSearchUrl,
  canExecuteTool,
  validatePowerShellCommand,
} from "./tooling";

describe("tooling permissions", () => {
  it("allows low-risk actions without confirmation and blocks medium-risk actions without approval", () => {
    expect(
      canExecuteTool(
        {
          name: "open-browser-search",
          risk: "LOW",
          requiresConfirmation: false,
        },
        false,
      ),
    ).toBe(true);

    expect(
      canExecuteTool(
        {
          name: "run-powershell",
          risk: "MEDIUM",
          requiresConfirmation: true,
        },
        false,
      ),
    ).toBe(false);

    expect(
      canExecuteTool(
        {
          name: "run-powershell",
          risk: "MEDIUM",
          requiresConfirmation: true,
        },
        true,
      ),
    ).toBe(true);
  });

  it("builds a proper browser search URL and accepts approved PowerShell commands", () => {
    expect(buildSearchUrl("AI education research")).toContain(
      "https://www.google.com/search?q=AI+education+research",
    );
    expect(validatePowerShellCommand("Get-ChildItem Env:Temp")).toBe(true);
    expect(
      validatePowerShellCommand(
        "Remove-Item -Recurse -Force C:\\temp\\delete-me",
      ),
    ).toBe(false);
  });
});
