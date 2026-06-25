const rows = document.querySelector("#instance-rows");
const search = document.querySelector("#search-input");
const empty = document.querySelector("#admin-empty");
const meta = document.querySelector("#admin-meta");
const form = document.querySelector("#instance-form");
const statusText = document.querySelector("#form-status");
const logoutButton = document.querySelector("#logout-button");
const scannerRows = document.querySelector("#scanner-rows");
const scannerEmpty = document.querySelector("#scanner-empty");
const sectionButtons = document.querySelectorAll("[data-admin-section]");
const sections = document.querySelectorAll(".admin-section");
const modalElement = document.querySelector("#instance-modal");
const modal = new bootstrap.Modal(modalElement);
const deleteModalElement = document.querySelector("#delete-modal");
const deleteModal = new bootstrap.Modal(deleteModalElement);
const deleteInstanceName = document.querySelector("#delete-instance-name");
const deleteInstanceSlug = document.querySelector("#delete-instance-slug");
const deleteStatus = document.querySelector("#delete-status");
const confirmDeleteButton = document.querySelector("#confirm-delete-button");
const deleteScannerModalElement = document.querySelector("#delete-scanner-modal");
const deleteScannerModal = new bootstrap.Modal(deleteScannerModalElement);
const deleteScannerName = document.querySelector("#delete-scanner-name");
const deleteScannerId = document.querySelector("#delete-scanner-id");
const deleteScannerConfirmation = document.querySelector("#delete-scanner-confirmation");
const deleteScannerResult = document.querySelector("#delete-scanner-result");
const deleteScannerClose = document.querySelector("#delete-scanner-close");
const confirmDeleteScanner = document.querySelector("#confirm-delete-scanner");

let items = [];
let selectedSlug = "";
let csrfToken = "";
let scanners = [];
let pendingDeleteSlug = "";
let pendingDeleteScannerId = "";

const fields = {
  slug: document.querySelector("#instance-slug"),
  name: document.querySelector("#instance-name"),
  description: document.querySelector("#instance-description"),
  baseUrl: document.querySelector("#instance-base-url"),
  packagePrefix: document.querySelector("#instance-prefix"),
  status: document.querySelector("#instance-status"),
  visibility: document.querySelector("#instance-visibility")
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function dateLabel(value) {
  return value ? new Date(value).toLocaleString("en-US") : "-";
}

function render() {
  const term = search.value.trim().toLowerCase();
  const visible = items.filter((item) =>
    `${item.name} ${item.slug} ${item.packagePrefix}`.toLowerCase().includes(term)
  );
  empty.style.display = visible.length ? "none" : "block";
  rows.innerHTML = visible.map((item) => `
    <tr class="${item.slug === selectedSlug ? "selected" : ""}">
      <td>
        <button class="btn btn-link table-name p-0 text-start" data-select="${escapeHtml(item.slug)}">${escapeHtml(item.name)}</button>
        <small class="d-block text-secondary">${escapeHtml(item.slug)}</small>
      </td>
      <td>
        <code class="local-id">${escapeHtml(item.ownerScannerId || "Legacy")}</code>
        ${item.ownerScannerName ? `<small class="d-block text-secondary">${escapeHtml(item.ownerScannerName)}</small>` : ""}
      </td>
      <td><span class="status-badge ${escapeHtml(item.status || "active")}">${escapeHtml(item.status || "active")}</span></td>
      <td>${escapeHtml(item.visibility || "public")}</td>
      <td>${Number(item.endpointCount || 0)}</td>
      <td>${escapeHtml(dateLabel(item.publishedAt))}</td>
      <td>
        <div class="d-flex justify-content-end gap-2">
          <a class="btn btn-sm btn-outline-secondary" href="/?doc=${encodeURIComponent(item.slug)}" target="_blank" rel="noreferrer" title="Open documentation">
            <i class="bi bi-eye" aria-hidden="true"></i>
            <span class="d-none d-xl-inline ms-1">View</span>
          </a>
          <button class="btn btn-sm btn-outline-danger" type="button" data-delete="${escapeHtml(item.slug)}" title="Delete instance">
            <i class="bi bi-trash3" aria-hidden="true"></i>
            <span class="d-none d-xl-inline ms-1">Delete</span>
          </button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderScanners() {
  scannerEmpty.style.display = scanners.length ? "none" : "block";
  scannerRows.innerHTML = scanners.map((scanner) => {
    const approved = scanner.status === "approved";
    const nextStatus = approved ? "revoked" : "approved";
    const buttonClass = approved ? "btn-outline-danger" : "btn-success";
    const buttonIcon = approved ? "bi-slash-circle" : "bi-check2-circle";
    const buttonLabel = approved ? "Revoke" : "Approve";
    return `
    <tr>
      <td><strong>${escapeHtml(scanner.name)}</strong></td>
      <td><code>${escapeHtml(scanner.scannerId)}</code></td>
      <td><span class="status-badge ${escapeHtml(scanner.status)}">${escapeHtml(scanner.status)}</span></td>
      <td>${escapeHtml(dateLabel(scanner.registeredAt))}</td>
      <td class="text-end">
        <div class="d-flex justify-content-end gap-2">
          <button class="btn btn-sm ${buttonClass}" type="button" data-scanner-status="${nextStatus}" data-scanner-id="${escapeHtml(scanner.scannerId)}">
            <i class="bi ${buttonIcon}" aria-hidden="true"></i>
            <span class="ms-1">${buttonLabel}</span>
          </button>
          <button class="btn btn-sm btn-outline-danger" type="button" data-delete-scanner="${escapeHtml(scanner.scannerId)}" title="Delete scanner">
            <i class="bi bi-trash3" aria-hidden="true"></i>
            <span class="d-none d-xl-inline ms-1">Delete</span>
          </button>
        </div>
      </td>
    </tr>
  `;
  }).join("");
}

function showSection(name) {
  sectionButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.adminSection === name);
  });
  sections.forEach((section) => {
    section.classList.toggle("active", section.id === `section-${name}`);
  });

  const sidebar = document.querySelector("#admin-sidebar");
  const offcanvas = bootstrap.Offcanvas.getInstance(sidebar);
  if (offcanvas) offcanvas.hide();
}

function selectItem(slug) {
  const item = items.find((entry) => entry.slug === slug);
  if (!item) return;
  selectedSlug = slug;
  fields.slug.value = item.slug;
  fields.name.value = item.name || "";
  fields.description.value = item.description || "";
  fields.baseUrl.value = item.baseUrl || "";
  fields.packagePrefix.value = item.packagePrefix || "";
  fields.status.value = item.status || "active";
  fields.visibility.value = item.visibility || "public";
  statusText.textContent = item.slug;
  render();
  modal.show();
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.method && options.method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
      ...(options.headers || {})
    }
  });
  if (response.status === 401) {
    window.location.replace("/login.html");
    throw new Error("The session has expired.");
  }
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed.");
  return payload;
}

async function boot() {
  try {
    const session = await api("/api/admin/session");
    csrfToken = session.csrfToken;
    const catalog = await api("/api/admin/instances");
    const scannerCatalog = await api("/api/admin/scanners");
    items = catalog.items || [];
    scanners = scannerCatalog.items || [];
    meta.textContent = `${items.length} published instances - signed in as ${session.username}`;
    render();
    renderScanners();
  } catch (error) {
    meta.textContent = error.message;
  }
}

rows.addEventListener("click", (event) => {
  const selectButton = event.target.closest("[data-select]");
  if (selectButton) {
    selectItem(selectButton.dataset.select);
    return;
  }
  const deleteAction = event.target.closest("[data-delete]");
  if (deleteAction) openDeleteModal(deleteAction.dataset.delete);
});

search.addEventListener("input", render);

sectionButtons.forEach((button) => {
  button.addEventListener("click", () => showSection(button.dataset.adminSection));
});

scannerRows.addEventListener("click", async (event) => {
  const deleteButton = event.target.closest("[data-delete-scanner]");
  if (deleteButton) {
    openDeleteScannerModal(deleteButton.dataset.deleteScanner);
    return;
  }
  const button = event.target.closest("[data-scanner-status]");
  if (!button) return;
  button.disabled = true;
  try {
    const result = await api(`/api/admin/scanners/${encodeURIComponent(button.dataset.scannerId)}`, {
      method: "PUT",
      body: JSON.stringify({ status: button.dataset.scannerStatus })
    });
    scanners = scanners.map((scanner) =>
      scanner.scannerId === result.scanner.scannerId ? result.scanner : scanner
    );
    renderScanners();
  } catch (error) {
    meta.textContent = error.message;
  }
});

function openDeleteScannerModal(scannerId) {
  const scanner = scanners.find((item) => item.scannerId === scannerId);
  if (!scanner) return;
  pendingDeleteScannerId = scannerId;
  deleteScannerName.textContent = scanner.name;
  deleteScannerId.textContent = scanner.scannerId;
  deleteScannerConfirmation.classList.remove("d-none");
  deleteScannerResult.className = "alert d-none mb-0";
  deleteScannerResult.textContent = "";
  confirmDeleteScanner.classList.remove("d-none");
  confirmDeleteScanner.disabled = false;
  deleteScannerClose.textContent = "Cancel";
  deleteScannerModal.show();
}

async function deleteRegisteredScanner() {
  if (!pendingDeleteScannerId) return;
  confirmDeleteScanner.disabled = true;
  confirmDeleteScanner.innerHTML =
    '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Deleting...';
  deleteScannerClose.disabled = true;
  try {
    await api(`/api/admin/scanners/${encodeURIComponent(pendingDeleteScannerId)}`, {
      method: "DELETE"
    });
    scanners = scanners.filter((item) => item.scannerId !== pendingDeleteScannerId);
    renderScanners();
    deleteScannerConfirmation.classList.add("d-none");
    deleteScannerResult.className = "alert alert-success mb-0";
    deleteScannerResult.textContent = "Registered scanner deleted successfully.";
    confirmDeleteScanner.classList.add("d-none");
    deleteScannerClose.textContent = "Close";
  } catch (error) {
    deleteScannerConfirmation.classList.add("d-none");
    deleteScannerResult.className = "alert alert-danger mb-0";
    deleteScannerResult.textContent = error.message;
    confirmDeleteScanner.classList.add("d-none");
    deleteScannerClose.textContent = "Close";
  } finally {
    confirmDeleteScanner.disabled = false;
    deleteScannerClose.disabled = false;
  }
}

confirmDeleteScanner.addEventListener("click", deleteRegisteredScanner);
deleteScannerModalElement.addEventListener("hidden.bs.modal", () => {
  pendingDeleteScannerId = "";
  deleteScannerName.textContent = "";
  deleteScannerId.textContent = "";
  deleteScannerConfirmation.classList.remove("d-none");
  deleteScannerResult.className = "alert d-none mb-0";
  deleteScannerResult.textContent = "";
  confirmDeleteScanner.classList.remove("d-none");
  confirmDeleteScanner.disabled = false;
  confirmDeleteScanner.innerHTML = '<i class="bi bi-trash3 me-1" aria-hidden="true"></i>Delete';
  deleteScannerClose.disabled = false;
  deleteScannerClose.textContent = "Cancel";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api(`/api/admin/instances/${encodeURIComponent(selectedSlug)}`, {
      method: "PUT",
      body: JSON.stringify({
        name: fields.name.value,
        description: fields.description.value,
        baseUrl: fields.baseUrl.value,
        packagePrefix: fields.packagePrefix.value,
        status: fields.status.value,
        visibility: fields.visibility.value
      })
    });
    items = items.map((item) => item.slug === selectedSlug ? payload.item : item);
    render();
    modal.hide();
  } catch (error) {
    statusText.textContent = error.message;
  }
});

function openDeleteModal(slug) {
  const item = items.find((entry) => entry.slug === slug);
  if (!item) return;
  pendingDeleteSlug = slug;
  deleteInstanceName.textContent = item.name;
  deleteInstanceSlug.textContent = item.slug;
  deleteStatus.classList.add("d-none");
  deleteStatus.textContent = "";
  deleteModal.show();
}

async function confirmDelete() {
  if (!pendingDeleteSlug) return;
  confirmDeleteButton.disabled = true;
  try {
    await api(`/api/admin/instances/${encodeURIComponent(pendingDeleteSlug)}`, { method: "DELETE" });
    items = items.filter((entry) => entry.slug !== pendingDeleteSlug);
    meta.textContent = `${items.length} published instances`;
    render();
    deleteModal.hide();
  } catch (error) {
    deleteStatus.textContent = error.message;
    deleteStatus.classList.remove("d-none");
  } finally {
    confirmDeleteButton.disabled = false;
  }
}

confirmDeleteButton.addEventListener("click", confirmDelete);
deleteModalElement.addEventListener("hidden.bs.modal", () => {
  pendingDeleteSlug = "";
  deleteInstanceName.textContent = "";
  deleteInstanceSlug.textContent = "";
  deleteStatus.classList.add("d-none");
  deleteStatus.textContent = "";
});

modalElement.addEventListener("shown.bs.modal", () => fields.name.focus());
modalElement.addEventListener("hidden.bs.modal", () => {
  selectedSlug = "";
  form.reset();
  statusText.textContent = "Update documentation information.";
  render();
});

logoutButton.addEventListener("click", async () => {
  await api("/api/admin/logout", { method: "POST", body: "{}" });
  window.location.replace("/login.html");
});

boot();

