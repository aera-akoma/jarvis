from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    """A known OpenAI-compatible provider.

    ``credential_name`` is the name the key is stored under in the Windows
    DPAPI credential store. Each provider gets its own entry so adding a Groq
    key never overwrites your OpenCode key. The default ``OpenAI`` name is kept
    for the existing/custom setup so upgrading does not orphan a saved key.

    ``opencode_id`` is the provider id this preset maps to inside OpenCode's
    own provider catalog (models.dev), or an empty string when OpenCode does not
    list the provider. It is informational: it lets the UI say "OpenCode also
    supports this provider" and lets tests pin the mapping.
    """

    id: str
    label: str
    base_url: str
    credential_name: str
    keyless: bool = False
    docs_url: str = ""
    note: str = ""
    opencode_id: str = ""
    default_model: str = ""

    @property
    def in_opencode(self) -> bool:
        return bool(self.opencode_id)


# Free-first ordering, sourced from the "awesome-free-llm-apis" list and the
# free providers OpenCode itself documents. All listed endpoints are OpenAI
# Chat Completions compatible (``<base_url>/chat/completions`` and
# ``<base_url>/models``). The runtime URL stays editable, so a changed endpoint
# can always be corrected. Providers whose ``opencode_id`` is set are also
# first-class inside OpenCode.
PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="custom",
        label="Custom / existing setup",
        base_url="",
        credential_name="OpenAI",
        note="Any OpenAI-compatible base URL. Uses your existing saved key.",
    ),
    # ── Provider APIs (run by the model trainers) ────────────────────────────
    ProviderPreset(
        id="google_gemini",
        label="Google Gemini — free tier",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        credential_name="google_gemini",
        docs_url="https://aistudio.google.com/apikey",
        note="Free tier and multimodal (good for reading the screen). Free-tier prompts may be used by Google to improve products.",
        opencode_id="google",
    ),
    ProviderPreset(
        id="mistral",
        label="Mistral — free mode",
        base_url="https://api.mistral.ai/v1",
        credential_name="mistral",
        docs_url="https://console.mistral.ai/api-keys/",
        note="Free mode is on by default with a monthly credit. Free-mode prompts may be used to train Mistral models unless you opt out.",
        opencode_id="mistral",
    ),
    ProviderPreset(
        id="zai",
        label="Z AI (Zhipu) — free models",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        credential_name="zai",
        docs_url="https://open.bigmodel.cn/usercenter/apikeys",
        note="Permanent free models (for example GLM-Flash). The international endpoint is https://api.z.ai/api/paas/v4 — use whichever host your key was issued for.",
        opencode_id="zai",
    ),
    ProviderPreset(
        id="cohere",
        label="Cohere — free trial key",
        base_url="https://api.cohere.ai/compatibility/v1",
        credential_name="cohere",
        docs_url="https://dashboard.cohere.com/api-keys",
        note="Free trial key, non-commercial use only. Uses Cohere's OpenAI-compatible endpoint.",
        opencode_id="cohere",
    ),
    ProviderPreset(
        id="aionlabs",
        label="Aion Labs — free tier",
        base_url="https://api.aionlabs.ai/v1",
        credential_name="aionlabs",
        docs_url="https://www.aionlabs.ai/app/api-keys/",
        note="Free tier with a daily token cap; specialized for roleplay and storytelling.",
    ),
    # ── Inference providers / gateways ───────────────────────────────────────
    ProviderPreset(
        id="groq",
        label="Groq — free tier",
        base_url="https://api.groq.com/openai/v1",
        credential_name="groq",
        docs_url="https://console.groq.com/keys",
        note="Free, very fast tool-calling models (for example openai/gpt-oss-120b).",
        opencode_id="groq",
    ),
    ProviderPreset(
        id="cerebras",
        label="Cerebras — free tier",
        base_url="https://api.cerebras.ai/v1",
        credential_name="cerebras",
        docs_url="https://cloud.cerebras.ai",
        note="Free tier with very fast inference.",
        opencode_id="cerebras",
    ),
    ProviderPreset(
        id="openrouter",
        label="OpenRouter — has :free models",
        base_url="https://openrouter.ai/api/v1",
        credential_name="openrouter",
        docs_url="https://openrouter.ai/keys",
        note="Many models with a ':free' suffix; rates and availability vary.",
        opencode_id="openrouter",
    ),
    ProviderPreset(
        id="nvidia",
        label="NVIDIA NIM — free developer tier",
        base_url="https://integrate.api.nvidia.com/v1",
        credential_name="nvidia",
        docs_url="https://build.nvidia.com",
        note="Free developer credits; hosts Nemotron and gpt-oss.",
        opencode_id="nvidia",
    ),
    ProviderPreset(
        id="huggingface",
        label="Hugging Face Router",
        base_url="https://router.huggingface.co/v1",
        credential_name="huggingface",
        docs_url="https://huggingface.co/settings/tokens",
        note="Free monthly inference credits; routes to many hosts.",
        opencode_id="huggingface",
    ),
    ProviderPreset(
        id="modelscope",
        label="ModelScope — free inference",
        base_url="https://api-inference.modelscope.cn/v1",
        credential_name="modelscope",
        docs_url="https://modelscope.cn/my/myaccesstoken",
        note="Free API inference for registered users; may require real-name verification.",
        opencode_id="modelscope",
    ),
    ProviderPreset(
        id="kilo",
        label="Kilo Code — keyless free pool",
        base_url="https://api.kilo.ai/api/gateway",
        credential_name="kilo",
        keyless=True,
        docs_url="https://app.kilo.ai/profile",
        note="Free models with no key required; its auto-router picks from the free pool.",
        opencode_id="kilo",
        default_model="kilo-auto/free",
    ),
    ProviderPreset(
        id="llm7",
        label="LLM7.io — free / keyless",
        base_url="https://api.llm7.io/v1",
        credential_name="llm7",
        keyless=True,
        docs_url="https://token.llm7.io",
        note="Works anonymously for the turbo models; a free token raises the limits.",
        default_model="DeepSeek-V4-Flash-0731",
    ),
    ProviderPreset(
        id="ovhcloud",
        label="OVHcloud AI Endpoints — anonymous",
        base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        credential_name="ovhcloud",
        keyless=True,
        docs_url="https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/",
        note="Free anonymous tier (no key, no signup); rate-limited per IP.",
        opencode_id="ovhcloud",
        default_model="Mistral-7B-Instruct-v0.3",
    ),
    ProviderPreset(
        id="ollama_cloud",
        label="Ollama Cloud — free tier",
        base_url="https://ollama.com/v1",
        credential_name="ollama_cloud",
        docs_url="https://ollama.com/settings/keys",
        note="Ollama's hosted models, OpenAI-compatible via https://ollama.com/v1.",
        opencode_id="ollama-cloud",
    ),
    ProviderPreset(
        id="siliconflow",
        label="SiliconFlow — free models",
        base_url="https://api.siliconflow.cn/v1",
        credential_name="siliconflow",
        docs_url="https://cloud.siliconflow.cn/account/ak",
        note="Some models are permanently free; most of the catalog is paid.",
        opencode_id="siliconflow",
    ),
    ProviderPreset(
        id="cloudflare",
        label="Cloudflare Workers AI — free neurons",
        base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        credential_name="cloudflare",
        docs_url="https://dash.cloudflare.com/profile/api-tokens",
        note="Replace {account_id} with your Cloudflare account id; the /ai/v1 route is OpenAI-compatible.",
        opencode_id="cloudflare-workers-ai",
    ),
    ProviderPreset(
        id="together",
        label="Together AI — free models",
        base_url="https://api.together.xyz/v1",
        credential_name="together",
        docs_url="https://api.together.ai/settings/api-keys",
        note="Some models are free; others are billed.",
        opencode_id="togetherai",
    ),
    ProviderPreset(
        id="github_models",
        label="GitHub Models",
        base_url="https://models.github.ai/inference",
        credential_name="github_models",
        docs_url="https://github.com/settings/tokens",
        note="Free with a GitHub personal access token; the model list may need the model typed in.",
    ),
    ProviderPreset(
        id="azure_openai",
        label="Azure OpenAI / AI Foundry — browser sign-in",
        base_url="https://<resource-name>.openai.azure.com/openai/v1",
        credential_name="azure_openai",
        docs_url="https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource",
        note="Signed in through Settings > Sign in with browser… (Entra device-code flow). Replace <resource-name> with your Azure OpenAI resource; the model box takes your deployment name (for example gpt-4o-mini). The signed-in Entra identity also needs a role on the resource, such as Cognitive Services OpenAI User.",
    ),
    # ── OpenCode routes ──────────────────────────────────────────────────────
    ProviderPreset(
        id="opencode_zen",
        label="OpenCode Zen — /connect key",
        base_url="https://opencode.ai/zen/v1",
        credential_name="OpenCodeZen",
        docs_url="https://opencode.ai/docs",
        note="Key from the OpenCode TUI /connect command. If your key is a Console service-account key, choose the Console provider instead; pairing a key with the wrong route returns HTTP 403. Free-tier models are policy-blocked outside the official client.",
        opencode_id="opencode",
    ),
    ProviderPreset(
        id="opencode_console",
        label="OpenCode Console — service-account key",
        base_url="https://opencode.ai/inference/openai/v1",
        credential_name="OpenCodeConsole",
        docs_url="https://opencode.ai/console",
        note="Console > Keys > Add Service Account > Add API Key. If your key came from /connect, choose the Zen provider instead. Free-tier models are policy-blocked outside the official client.",
        opencode_id="opencode",
    ),
)

_BY_ID: dict[str, ProviderPreset] = {preset.id: preset for preset in PROVIDER_PRESETS}


def get_preset(provider_id: str | None) -> ProviderPreset | None:
    if not provider_id:
        return None
    return _BY_ID.get(provider_id)


def default_preset() -> ProviderPreset:
    """The back-compatible default: any URL, credential stored as ``OpenAI``."""
    return _BY_ID["custom"]


def provider_for_base_url(base_url: str | None) -> ProviderPreset | None:
    """Return the preset whose base URL matches, if any (ignoring a trailing slash)."""
    if not base_url:
        return None
    normalized = base_url.strip().rstrip("/").lower()
    if not normalized:
        return None
    for preset in PROVIDER_PRESETS:
        if preset.base_url and preset.base_url.rstrip("/").lower() == normalized:
            return preset
    return None


def opencode_presets() -> tuple[ProviderPreset, ...]:
    """Presets that OpenCode also knows, in display order."""
    return tuple(preset for preset in PROVIDER_PRESETS if preset.in_opencode)


def preset_order() -> tuple[ProviderPreset, ...]:
    return PROVIDER_PRESETS
