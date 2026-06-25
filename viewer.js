const meta = document.querySelector("#viewer-meta");
const emptyState = document.querySelector("#empty-state");
const emptyMessage = document.querySelector("#empty-message");
const statusBadge = document.querySelector("#status-badge");

function setQuery(slug) {
  const url = new URL(window.location.href);
  url.searchParams.set("doc", slug);
  window.history.replaceState({}, "", url);
}

function formatMeta(item) {
  const generated = item.generatedAt ? new Date(item.generatedAt).toLocaleString("en-US") : "-";
  return `${item.endpointCount || 0} endpoint - ${item.packageCount || 0} package - update ${generated}`;
}

async function loadSwagger(item) {
  emptyState.classList.add("d-none");
  document.querySelector("#swagger-ui").innerHTML = "";
  meta.textContent = formatMeta(item);
  statusBadge.textContent = item.status === "deprecated" ? "Deprecated" : "Active";
  statusBadge.className = item.status === "deprecated"
    ? "badge text-bg-danger"
    : "badge text-bg-success";
  setQuery(item.slug);

  try {
    const response = await fetch(item.url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Documentation failed to load (${response.status}).`);
    }
    const spec = await response.json();
    const oauthFlow =
      spec.components?.securitySchemes?.oauth2ClientCredentials?.flows
        ?.clientCredentials;
    const configuredTokenUrl = oauthFlow?.tokenUrl || "";
    const oauthProxyUrl =
      `${window.location.origin}/api/oauth/token/${encodeURIComponent(item.slug)}`;
    SwaggerUIBundle({
      spec,
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: true,
      displayRequestDuration: true,
      defaultModelsExpandDepth: -1,
      tryItOutEnabled: true,
      requestInterceptor: (request) => {
        if (configuredTokenUrl && request.url === configuredTokenUrl) {
          request.url = oauthProxyUrl;
        }
        return request;
      }
    });
  } catch (error) {
    meta.textContent = error.message;
    emptyMessage.textContent = error.message;
    emptyState.classList.remove("d-none");
    statusBadge.classList.add("d-none");
  }
}

async function boot() {
  try {
    const response = await fetch("/api/catalog", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("The catalog is unavailable.");
    }

    const catalog = await response.json();
    const items = catalog.items || [];
    if (!items.length) {
      throw new Error("No documentation is available.");
    }

    const requested = new URLSearchParams(window.location.search).get("doc");
    const current = requested
      ? items.find((item) => item.slug === requested)
      : items[0];
    if (!current) {
      throw new Error(`Documentation "${requested}" was not found.`);
    }
    await loadSwagger(current);
  } catch (error) {
    meta.textContent = error.message;
    emptyMessage.textContent = error.message;
    emptyState.classList.remove("d-none");
    statusBadge.classList.add("d-none");
    document.querySelector("#swagger-ui").innerHTML = "";
  }
}

boot();

