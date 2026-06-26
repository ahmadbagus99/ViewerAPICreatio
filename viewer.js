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

function isApiTarget(targetUrl, baseUrl) {
  if (!targetUrl || !baseUrl) return false;
  try {
    const target = new URL(targetUrl);
    const base = new URL(baseUrl);
    const basePath = base.pathname.replace(/\/+$/, "");
    return target.origin === base.origin && (
      !basePath ||
      target.pathname === basePath ||
      target.pathname.startsWith(`${basePath}/`)
    );
  } catch {
    return false;
  }
}

function basicCredentials(authPayload) {
  const auth = authPayload?.creatioBasicAuth;
  const value = auth?.value;
  if (value?.username || value?.password) {
    return {
      username: value.username || "",
      password: value.password || ""
    };
  }
  if (auth?.username || auth?.password) {
    return {
      username: auth.username || "",
      password: auth.password || ""
    };
  }
  if (typeof value === "string" && value.toLowerCase().startsWith("basic ")) {
    try {
      const decoded = atob(value.slice(6).trim());
      const separator = decoded.indexOf(":");
      if (separator >= 0) {
        return {
          username: decoded.slice(0, separator),
          password: decoded.slice(separator + 1)
        };
      }
    } catch {
      return { username: "", password: "" };
    }
  }
  return { username: "", password: "" };
}

function clearSwaggerAuthError() {
  document
    .querySelectorAll("#swagger-ui .bpmcsrf-auth-error")
    .forEach((element) => element.remove());
}

function showSwaggerAuthError(message) {
  clearSwaggerAuthError();
  const modal =
    document.querySelector("#swagger-ui .dialog-ux .modal-ux-content") ||
    document.querySelector("#swagger-ui .modal-ux-content") ||
    document.querySelector("#swagger-ui .auth-container") ||
    document.querySelector("#swagger-ui");
  if (!modal) return;

  const error = document.createElement("div");
  error.className = "bpmcsrf-auth-error";
  error.setAttribute("role", "alert");
  error.style.cssText = [
    "margin: 12px 0",
    "padding: 10px 12px",
    "border: 1px solid #f1aeb5",
    "border-radius: 4px",
    "background: #f8d7da",
    "color: #842029",
    "font-size: 14px",
    "line-height: 1.4"
  ].join(";");
  error.textContent = message;

  const buttonRow =
    modal.querySelector(".auth-btn-wrapper") ||
    modal.querySelector(".modal-btn") ||
    modal.querySelector("button.authorize")?.parentElement;
  if (buttonRow) {
    buttonRow.before(error);
  } else {
    modal.append(error);
  }
}

function bpmcsrfAuthValidatorPlugin(authenticationMode, slug) {
  return {
    statePlugins: {
      auth: {
        wrapActions: {
          authorize: (original) => async (payload) => {
            if (
              authenticationMode !== "bpmcsrf" ||
              !payload?.creatioBasicAuth ||
              !slug
            ) {
              return original(payload);
            }

            const credentials = basicCredentials(payload);
            if (!credentials.username || !credentials.password) {
              const message = "Username and password are required.";
              showSwaggerAuthError(message);
              throw new Error(message);
            }

            const body = new URLSearchParams({
              username: credentials.username,
              password: credentials.password
            });
            const response = await fetch(
              `/api/bpmcsrf/token/${encodeURIComponent(slug)}`,
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/x-www-form-urlencoded"
                },
                body
              }
            );
            const result = await response.json().catch(() => ({}));
            if (!response.ok) {
              const message = result.error || "Creatio username or password is invalid.";
              showSwaggerAuthError(message);
              throw new Error(message);
            }

            clearSwaggerAuthError();
            return original(payload);
          }
        }
      }
    }
  };
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
    const authenticationMode = spec["x-authentication-mode"] || item.authMode || "bpmcsrf";
    const oauthFlow =
      spec.components?.securitySchemes?.oauth2ClientCredentials?.flows
        ?.clientCredentials;
    const configuredTokenUrl = oauthFlow?.tokenUrl || "";
    const oauthProxyUrl =
      `${window.location.origin}/api/oauth/token/${encodeURIComponent(item.slug)}`;
    const apiProxyUrl =
      `${window.location.origin}/api/proxy/${encodeURIComponent(item.slug)}`;
    const swaggerElement = document.querySelector("#swagger-ui");
    swaggerElement.classList.toggle(
      "oauth-hide-global-errors",
      authenticationMode === "oauth"
    );
    SwaggerUIBundle({
      spec,
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: true,
      displayRequestDuration: true,
      defaultModelsExpandDepth: -1,
      tryItOutEnabled: true,
      plugins: [bpmcsrfAuthValidatorPlugin(authenticationMode, item.slug)],
      requestInterceptor: (request) => {
        if (configuredTokenUrl && request.url === configuredTokenUrl) {
          request.url = oauthProxyUrl;
        } else if (isApiTarget(request.url, item.baseUrl)) {
          request.url = `${apiProxyUrl}?url=${encodeURIComponent(request.url)}`;
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
