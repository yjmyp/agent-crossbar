import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  Blocks,
  CheckCircle2,
  CircleAlert,
  Cpu,
  Database,
  Eye,
  EyeOff,
  KeyRound,
  LockKeyhole,
  PlugZap,
  Server,
  ShieldCheck,
  Trash2,
  Wrench,
} from "lucide-react";
import type {
  Bridge,
  ProviderCredentialSummary,
  ProviderProfile,
  ToolDefinition,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

type Feedback = {
  tone: "success" | "danger";
  title: string;
  message: string;
};

const emptyCredential: ProviderCredentialSummary = {
  configured: false,
  baseUrl: null,
  model: null,
  storage: "Windows Credential Manager",
};

export function RegistryPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [credential, setCredential] =
    useState<ProviderCredentialSummary>(emptyCredential);
  const [credentialLoading, setCredentialLoading] = useState(true);
  const [credentialError, setCredentialError] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [confirmRemoval, setConfirmRemoval] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listProviders(), bridge.listTools()])
      .then(([nextProviders, nextTools]) => {
        if (!current) return;
        setProviders(nextProviders);
        setTools(nextTools);
      })
      .catch((reason: unknown) => {
        if (current) setCatalogError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setCatalogLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    bridge
      .getProviderCredential()
      .then((summary) => {
        if (!current) return;
        setCredential(summary);
        setBaseUrl(summary.baseUrl ?? "");
        setModel(summary.model ?? "");
      })
      .catch((reason: unknown) => {
        if (current) setCredentialError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setCredentialLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  const openAIProvider = providers.find(
    (provider) => provider.id === "openai.default",
  );
  const canSave =
    baseUrl.trim().length > 0 && model.trim().length > 0 && apiKey.trim().length > 0;
  const busy = saving || testing || removing;

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave || busy) return;
    setSaving(true);
    setFeedback(null);
    try {
      const activeProvider = await bridge.saveProviderCredential({
        baseUrl: baseUrl.trim(),
        apiKey,
        model: model.trim(),
      });
      setCredential({
        configured: true,
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        storage: "Windows Credential Manager",
      });
      setProviders((current) => replaceProvider(current, activeProvider));
      setApiKey("");
      setShowApiKey(false);
      setFeedback({
        tone: "success",
        title: "Connection stored",
        message:
          "The API key is in Windows Credential Manager and the running service is ready.",
      });
    } catch (reason) {
      const message = errorMessage(reason);
      if (message.startsWith("The credential was saved")) {
        setCredential({
          configured: true,
          baseUrl: baseUrl.trim(),
          model: model.trim(),
          storage: "Windows Credential Manager",
        });
        setApiKey("");
        setShowApiKey(false);
      }
      setFeedback({ tone: "danger", title: "Could not activate connection", message });
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    if (!credential.configured || busy) return;
    setTesting(true);
    setFeedback(null);
    try {
      const result = await bridge.testProvider();
      setFeedback({
        tone: "success",
        title: "Connection verified",
        message: result.message,
      });
    } catch (reason) {
      setFeedback({
        tone: "danger",
        title: "Connection test failed",
        message: errorMessage(reason),
      });
    } finally {
      setTesting(false);
    }
  }

  async function removeConnection() {
    if (busy) return;
    setRemoving(true);
    setFeedback(null);
    try {
      const inactiveProvider = await bridge.deleteProviderCredential();
      setCredential(emptyCredential);
      setProviders((current) => replaceProvider(current, inactiveProvider));
      setBaseUrl("");
      setModel("");
      setApiKey("");
      setShowApiKey(false);
      setConfirmRemoval(false);
      setFeedback({
        tone: "success",
        title: "Connection removed",
        message:
          "The vault entry and the running service configuration were both cleared.",
      });
    } catch (reason) {
      setFeedback({
        tone: "danger",
        title: "Could not remove connection",
        message: errorMessage(reason),
      });
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="page page--registry">
      <PageHeader
        eyebrow="Capabilities"
        title="Registry"
        description="Bind real model connections and inspect the exact tools an agent may use."
        actions={
          <StatusBadge
            tone={credential.configured ? "positive" : "warning"}
            dot
          >
            {credential.configured ? "Vault-backed" : "Offline only"}
          </StatusBadge>
        }
      />

      <section className="registry-trust-strip" aria-label="Connection security">
        <TrustItem
          icon={<LockKeyhole size={16} />}
          label="Secret storage"
          value={credential.storage}
        />
        <TrustItem
          icon={<ShieldCheck size={16} />}
          label="Runtime boundary"
          value="Authenticated loopback"
        />
        <TrustItem
          icon={<Database size={16} />}
          label="Data policy"
          value="No key in runs or traces"
        />
      </section>

      <div className="registry-layout">
        <section className="panel connection-panel" aria-labelledby="connection-title">
          <div className="connection-panel__header">
            <div className="connection-panel__identity">
              <span className="connection-panel__icon">
                <PlugZap size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="section-kicker">OpenAI-compatible</p>
                <h2 id="connection-title">Model connection</h2>
                <p>
                  Configure one live adapter without exposing its secret to the web layer
                  or persistent runtime data.
                </p>
              </div>
            </div>
            <ConnectionState
              configured={credential.configured}
              provider={openAIProvider}
            />
          </div>

          {credentialLoading ? (
            <LoadingState label="Reading the operating system credential vault" />
          ) : (
            <form className="connection-form" onSubmit={saveConnection}>
              <div className="connection-form__grid">
                <label className="field" htmlFor="provider-base-url">
                  <span>Base URL</span>
                  <input
                    id="provider-base-url"
                    aria-label="Base URL"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://api.openai.com/v1"
                    inputMode="url"
                    spellCheck={false}
                    maxLength={2_048}
                    required
                  />
                  <small>Use the complete HTTP(S) API root, without query parameters.</small>
                </label>

                <label className="field" htmlFor="provider-model">
                  <span>Model</span>
                  <input
                    id="provider-model"
                    aria-label="Model"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder="Model identifier"
                    spellCheck={false}
                    maxLength={200}
                    required
                  />
                  <small>The exact model name accepted by your compatible endpoint.</small>
                </label>

                <label className="field field--full" htmlFor="provider-api-key">
                  <span>API key</span>
                  <span className="secret-input">
                    <KeyRound size={15} aria-hidden="true" />
                    <input
                      id="provider-api-key"
                      aria-label="API key"
                      type={showApiKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(event) => setApiKey(event.target.value)}
                      placeholder={
                        credential.configured
                          ? "Stored securely · enter a new key only to replace it"
                          : "Enter the provider API key"
                      }
                      autoComplete="new-password"
                      spellCheck={false}
                      maxLength={4_096}
                      required
                    />
                    <button
                      type="button"
                      className="secret-input__toggle"
                      aria-label={showApiKey ? "Hide API key" : "Show API key"}
                      onClick={() => setShowApiKey((current) => !current)}
                    >
                      {showApiKey ? (
                        <EyeOff size={15} aria-hidden="true" />
                      ) : (
                        <Eye size={15} aria-hidden="true" />
                      )}
                    </button>
                  </span>
                  <small>
                    Written only to {credential.storage}. The field clears after a
                    successful save.
                  </small>
                </label>
              </div>

              {credentialError ? (
                <div className="inline-alert" role="alert">
                  <CircleAlert size={16} aria-hidden="true" />
                  <span>{credentialError}</span>
                </div>
              ) : null}

              {feedback ? (
                <div
                  className={`inline-alert inline-alert--${feedback.tone}`}
                  role={feedback.tone === "danger" ? "alert" : "status"}
                >
                  {feedback.tone === "success" ? (
                    <CheckCircle2 size={16} aria-hidden="true" />
                  ) : (
                    <CircleAlert size={16} aria-hidden="true" />
                  )}
                  <span>
                    <strong>{feedback.title}</strong>
                    {feedback.message}
                  </span>
                </div>
              ) : null}

              {confirmRemoval ? (
                <div className="connection-confirm" role="alertdialog">
                  <div>
                    <strong>Remove this model connection?</strong>
                    <p>
                      The key will be deleted from the operating system vault and the
                      live provider will be unloaded.
                    </p>
                  </div>
                  <div className="connection-confirm__actions">
                    <Button
                      tone="ghost"
                      onClick={() => setConfirmRemoval(false)}
                      disabled={busy}
                    >
                      Cancel
                    </Button>
                    <Button
                      tone="danger"
                      onClick={removeConnection}
                      loading={removing}
                    >
                      Confirm removal
                    </Button>
                  </div>
                </div>
              ) : null}

              <div className="connection-form__footer">
                <div className="connection-form__note">
                  <ShieldCheck size={15} aria-hidden="true" />
                  <span>
                    The API key never enters AgentSpecs, SQLite, traces, logs, or this
                    page after save.
                  </span>
                </div>
                <div className="connection-form__actions">
                  {credential.configured ? (
                    <Button
                      tone="ghost"
                      onClick={() => setConfirmRemoval(true)}
                      disabled={busy || confirmRemoval}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Remove connection
                    </Button>
                  ) : null}
                  <Button
                    tone="secondary"
                    onClick={testConnection}
                    disabled={!credential.configured || busy}
                    loading={testing}
                  >
                    <PlugZap size={14} aria-hidden="true" />
                    Test connection
                  </Button>
                  <Button
                    tone="primary"
                    type="submit"
                    disabled={!canSave || busy}
                    loading={saving}
                  >
                    Save connection
                  </Button>
                </div>
              </div>
            </form>
          )}
        </section>

        <aside className="registry-aside">
          <section className="panel registry-card">
            <div className="panel__header">
              <div>
                <h2>Runtime providers</h2>
                <p>Adapters currently known to the private service.</p>
              </div>
              <span className="count-pill">{providers.length}</span>
            </div>
            {catalogLoading ? <LoadingState label="Reading provider catalog" /> : null}
            {catalogError ? (
              <div className="registry-card__error" role="alert">
                <CircleAlert size={16} aria-hidden="true" />
                {catalogError}
              </div>
            ) : null}
            {!catalogLoading && !catalogError ? (
              <div className="capability-list">
                {providers.map((provider) => (
                  <div className="capability-row" key={provider.id}>
                    <span className="capability-row__icon">
                      <Server size={15} aria-hidden="true" />
                    </span>
                    <span className="capability-row__copy">
                      <strong>{provider.label}</strong>
                      <small>{provider.id}</small>
                    </span>
                    <StatusBadge tone={provider.configured ? "positive" : "warning"}>
                      {provider.configured ? "ready" : "offline"}
                    </StatusBadge>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel registry-card">
            <div className="panel__header">
              <div>
                <h2>Tool authority</h2>
                <p>Only declared tools become executable.</p>
              </div>
              <span className="count-pill">{tools.length}</span>
            </div>
            <div className="capability-list">
              {tools.map((tool) => (
                <div className="tool-registry-row" key={tool.name}>
                  <span className="capability-row__icon">
                    <Wrench size={15} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{tool.name}</strong>
                    <small>{tool.description}</small>
                    <em>
                      {tool.risk} risk · {tool.timeout_seconds}s timeout
                    </em>
                  </span>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="registry-link"
              onClick={() => navigate("/studio")}
            >
              <Cpu size={14} aria-hidden="true" />
              Bind capabilities in Agent Studio
            </button>
          </section>

          <section className="registry-note">
            <Blocks size={17} aria-hidden="true" />
            <div>
              <strong>Registry scope</strong>
              <p>
                Model connections and local tools are active. MCP servers, datasets,
                and release gates remain later milestones.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function TrustItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="registry-trust-item">
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function ConnectionState({
  configured,
  provider,
}: {
  configured: boolean;
  provider?: ProviderProfile;
}) {
  if (configured) {
    return (
      <div className="connection-state connection-state--ready">
        <span aria-hidden="true" />
        <div>
          <strong>Connection stored securely</strong>
          <small>{provider?.model ?? "Ready for explicit testing"}</small>
        </div>
      </div>
    );
  }

  return (
    <div className="connection-state">
      <CircleAlert size={15} aria-hidden="true" />
      <div>
        <strong>No live model connection</strong>
        <small>Offline providers remain available</small>
      </div>
    </div>
  );
}

function replaceProvider(
  providers: ProviderProfile[],
  replacement: ProviderProfile,
): ProviderProfile[] {
  const index = providers.findIndex(
    (provider) => provider.id === replacement.id,
  );
  if (index === -1) return [...providers, replacement];
  return providers.map((provider, providerIndex) =>
    providerIndex === index ? replacement : provider,
  );
}
