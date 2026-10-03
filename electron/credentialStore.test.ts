import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { createCredentialStore } = require("./credentialStore.cjs") as {
  createCredentialStore: (options: {
    db: any;
    safeStorage: {
      isEncryptionAvailable: () => boolean;
      encryptString: (secret: string) => Buffer;
      decryptString: (encrypted: Buffer) => string;
    };
  }) => {
    store: (entry: {
      credentialId: string;
      providerId: string;
      secret: string;
    }) => void;
    getSecret: (entry: { credentialId: string; providerId: string }) => string;
    delete: (entry: { credentialId: string; providerId: string }) => void;
  };
};

describe("secure credential store", () => {
  it("persists encrypted values and scopes retrieval to a provider", () => {
    let stored: { provider_id: string; encrypted_secret: Buffer } | undefined;
    const db = {
      prepare: (sql: string) => ({
        run: (...values: unknown[]) => {
          if (sql.startsWith("INSERT")) {
            stored = {
              provider_id: String(values[1]),
              encrypted_secret: values[2] as Buffer,
            };
          }
        },
        get: () => stored,
      }),
    };
    const safeStorage = {
      isEncryptionAvailable: () => true,
      encryptString: (secret: string) =>
        Buffer.from(`encrypted:${secret}`, "utf8"),
      decryptString: (encrypted: Buffer) =>
        encrypted.toString("utf8").replace(/^encrypted:/, ""),
    };
    const store = createCredentialStore({ db, safeStorage });

    store.store({
      credentialId: "credential-1",
      providerId: "opencode-zen",
      secret: "sk-secret",
    });

    expect(stored?.encrypted_secret.toString("utf8")).not.toBe("sk-secret");
    expect(() =>
      store.store({
        credentialId: "credential-1",
        providerId: "other-provider",
        secret: "replacement-secret",
      }),
    ).toThrow("Credential ID is already assigned to another provider.");
    expect(
      store.getSecret({
        credentialId: "credential-1",
        providerId: "opencode-zen",
      }),
    ).toBe("sk-secret");
    expect(() =>
      store.getSecret({ credentialId: "credential-1", providerId: "other" }),
    ).toThrow("Credential was not found for this provider.");
  });

  it("refuses to store credentials when OS encryption is unavailable", () => {
    const store = createCredentialStore({
      db: { prepare: () => ({ run: () => undefined, get: () => undefined }) },
      safeStorage: {
        isEncryptionAvailable: () => false,
        encryptString: () => Buffer.alloc(0),
        decryptString: () => "",
      },
    });

    expect(() =>
      store.store({
        credentialId: "credential-1",
        providerId: "opencode-zen",
        secret: "sk-secret",
      }),
    ).toThrow("Secure credential storage is unavailable on this device.");
  });
});
