# OAuth sign-in setup guide

Some providers accept a **browser sign-in** instead of a pasted API key. In
Jarvis, open **Settings → Sign in with browser…**. Two standard flows are
built in — no private or undocumented token exchange is ever performed:

| Provider | Flow | Standard |
|---|---|---|
| Microsoft Entra ID (Azure OpenAI / AI Foundry) | Device code ("go to this URL and type this code") | RFC 8628 |
| Google (Gemini free tier) | Authorization code + PKCE on a loopback redirect | RFC 7636 |

What Jarvis needs from you is your **own client registration** so that *you*
own the app, keys, and consent. The flows below step through creating those
registrations in the two developer consoles.

> **Security model.** The resulting token is written straight to the Windows
> DPAPI credential store and is never displayed, logged, or included in
> backups. Jarvis implements only the standard grant flows and refuses to
> impersonate an official client. Signing in under **Test model access** in
> Settings confirms the token actually reaches a model.

---

## 1. Microsoft Entra ID — Azure OpenAI / AI Foundry

The Entra "Azure OpenAI / AI Foundry — browser sign-in" preset in Jarvis uses
the device-code grant against `login.microsoftonline.com`. You need:

- An Azure subscription with an **Azure OpenAI resource** (or AI Foundry
  project) that has at least one **model deployment**.
- Permission to register an app in **Microsoft Entra ID** and to assign roles
  on the Azure AI resource.
- A Microsoft identity that can be granted the **Cognitive Services OpenAI
  User** role on that resource.

### 1.1 Register a public-client app

1. Go to the **Azure portal** → **Microsoft Entra ID** → **App registrations**
   → **New registration**.
2. Name: `Jarvis`.
3. **Supported account types**: "Accounts in this organizational directory
   only" is simplest; you will paste your directory (tenant) id. Multi-tenant
   registrations also work with the tenant value `common`.
4. Leave **Redirect URI** empty — the device-code grant does not use one.
   Click **Register**.
5. From the **Overview** page copy:
   - **Application (client) ID** — paste into Jarvis's **Client id** field.
   - **Directory (tenant) ID** — paste into Jarvis's **Tenant** field (or type
     `common` for a multi-tenant registration).

### 1.2 Enable public client flows

The device-code grant requires the app to be a *public client*:

1. In the app registration, open **Authentication**.
2. Under **Advanced settings → Allow public client flows**, set the toggle to
   **Yes** and **Save**.

Without this, sign-in fails with `AADSTS7000218` ("public client flows are
disabled").

### 1.3 Assign the OpenAI role on the resource

Signing in alone does **not** grant API access. The signed-in identity must be
authorized on the Azure AI resource:

1. Open your **Azure OpenAI resource** → **Access control (IAM)** →
   **Add role assignment**.
2. Role: **Cognitive Services OpenAI User**.
3. Assign to the Microsoft identity you will sign in with, then **Save**.

A missing (or wrong) role is the most common cause of "signed in but chat
rejected" — you typically see `401`/`403` at the chat request, not at sign-in.

### 1.4  Sign in and configure the preset

1. In Jarvis: **Settings → Sign in with browser…** → choose **Microsoft Entra
   ID — Azure OpenAI / AI Foundry**.
2. Paste the **client id** and **tenant id**, then **Start sign-in**. Jarvis
   shows the code and opens Microsoft's page; approve it there.
3. After approval, Jarvis selects the **Azure OpenAI / AI Foundry — browser
   sign-in** preset automatically.
4. Edit the **Runtime URL**: replace `<resource-name>` with your resource name
   (for example `https://my-gpt.openai.azure.com/openai/v1`).
5. In the model box enter your **deployment name** — Azure OpenAI treats the
   "model" as the deployment (for example `gpt-4o-mini` is the *deployment
   name*, which may differ from the base model).
6. Press **Test model access** to confirm the token reaches a model.

---

## 2. Google — Gemini free tier

The Google preset in Jarvis uses an authorization code with PKCE on a
**loopback** redirect to `http://127.0.0.1:<port>/callback`. You need:

- A Google account with a **Cloud project**.
- The **Generative Language API** enabled in that project.
- An **OAuth consent screen** configured (Testing status is fine for personal
  use — no Google verification is needed).
- A **Desktop app** OAuth client.

### 2.1 Enable the API and consent screen

1. Open the **Google Cloud Console** → pick or create a project.
2. **APIs & Services → Library** → search **Generative Language API** →
   **Enable**.
3. **APIs & Services → OAuth consent screen**: choose **External**, fill the
   required fields, and leave status at **Testing**. Add the Google account you
   will sign in with as a **test user** — otherwise approval is refused.

### 2.2 Create a Desktop OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. **Application type: Desktop app**.
3. Name it `Jarvis` and click **Create**.
4. Copy the **Client ID**.

A **client secret is not needed** — Jarvis's Google flow sends none, and the
dialog disables the secret field for this provider. Because the client type is
*Desktop app*, Google accepts loopback redirect URIs
(`http://127.0.0.1:<port>`) without registering the exact port, so nothing
extra is required here.

### 2.3 Sign in

1. In Jarvis: **Settings → Sign in with browser…** → choose **Google — Gemini
   free tier (installed-app sign-in)**.
2. Paste the **client id** and **Start sign-in**. Your browser opens Google's
   consent page; approve it. Jarvis receives the redirect on its own loopback
   server and stores the token.
3. Jarvis selects the **Google Gemini — free tier** preset automatically
   (Runtime URL `https://generativelanguage.googleapis.com/v1beta/openai`).
   Pick a Gemini model in the model box and press **Test model access**.

> **Free-tier note:** with the free tier, your prompts may be used by Google to
> improve products. See the preset note in Settings.

---

## 3. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Microsoft `AADSTS7000218` | Public client flows disabled | Enable *Allow public client flows* (step 1.2) |
| Microsoft `AADSTS65001` / consent errors | Consent not granted, or tenant id mismatch | Re-run sign-in, pick the right tenant; approve on Microsoft's page |
| Signed in, but chat returns `401`/`403` | The Entra identity lacks a role on the Azure resource | Assign **Cognitive Services OpenAI User** (step 1.3) |
| Azure `model_not_found` / 404 | The model box is a deployment name, not a base model | Enter your deployment name (step 1.4) |
| Google `redirect_uri_mismatch` / `unregistered_application` | OAuth client is the wrong type | Recreate as **Desktop app** (step 2.2) |
| Google `access_denied` at approval | Consent screen has no test user (Testing status) | Add your account as a **test user** (step 2.1) |
| "Token expired" later | Access tokens expire like the provider's own | Open the sign-in dialog again and sign in; stored tokens are never shown |
| Any flow: uncertain whether it worked | — | **Settings → Test model access** sends one real request with the token |

Tokens expire like the provider's own tokens (Jarvis tries a refresh-token
exchange first and reports the provider's exact error if it fails). Re-enter
the dialog and sign in again once the token stops being accepted.

---

## 4. What Jarvis stores

- Tokens are kept under their own credential name (`azure_openai`,
  `google_gemini`) in the Windows DPAPI credential store — never in logs,
  backups, or exports, and never displayed by the UI.
- Signing in never sends a key anywhere except the provider's documented
  endpoints.
- Signing out / switching back to an API key: choose the provider's preset, or
  use **Clear key** on the preset to remove the stored credential.