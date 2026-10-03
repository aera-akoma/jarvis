function createCredentialStore({ db, safeStorage }) {
  const assertEncryptionAvailable = () => {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error(
        "Secure credential storage is unavailable on this device.",
      );
    }
  };

  return {
    store({ credentialId, providerId, secret }) {
      assertEncryptionAvailable();
      if (!credentialId || !providerId || !secret) {
        throw new Error("Credential ID, provider ID, and secret are required.");
      }

      const existing = db
        .prepare("SELECT provider_id FROM credentials WHERE id = ?")
        .get(credentialId);
      if (existing && existing.provider_id !== providerId) {
        throw new Error(
          "Credential ID is already assigned to another provider.",
        );
      }

      const encryptedSecret = safeStorage.encryptString(String(secret));
      db.prepare(
        `INSERT INTO credentials (id, provider_id, encrypted_secret, updated_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           provider_id = excluded.provider_id,
           encrypted_secret = excluded.encrypted_secret,
           updated_at = excluded.updated_at`,
      ).run(
        credentialId,
        providerId,
        encryptedSecret,
        new Date().toISOString(),
      );
    },

    getSecret({ credentialId, providerId }) {
      assertEncryptionAvailable();
      const record = db
        .prepare(
          "SELECT provider_id, encrypted_secret FROM credentials WHERE id = ?",
        )
        .get(credentialId);

      if (!record || record.provider_id !== providerId) {
        throw new Error("Credential was not found for this provider.");
      }

      return safeStorage.decryptString(Buffer.from(record.encrypted_secret));
    },

    delete({ credentialId, providerId }) {
      db.prepare(
        "DELETE FROM credentials WHERE id = ? AND provider_id = ?",
      ).run(credentialId, providerId);
    },
  };
}

module.exports = { createCredentialStore };
