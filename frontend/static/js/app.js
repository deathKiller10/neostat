const API_BASE = "/api/v1";

function humanizeLabel(name) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Not found";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(value);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str === null || str === undefined ? "" : String(str);
  return div.innerHTML;
}

function statusBadgeClass(status) {
  if (status === "PASS") return "badge badge-pass";
  if (status === "FAIL" || status === "FAILED") return "badge badge-fail";
  if (status === "NOT_APPLICABLE") return "badge badge-na";
  return "badge";
}

function fieldStatusClass(field) {
  if (!field || field.value === null || field.value === undefined) return "value-missing";
  if (field.grounded === false) return "value-ungrounded";
  if (typeof field.confidence === "number" && field.confidence < 0.6) return "value-low-confidence";
  return "value-ok";
}

async function apiFetch(url, options) {
  const response = await fetch(url, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = (body && body.error) || { code: "UNKNOWN_ERROR", message: `Request failed with status ${response.status}` };
    const err = new Error(error.message);
    err.code = error.code;
    throw err;
  }
  return body;
}

function initUploadPage() {
  const form = document.getElementById("upload-form");
  const progress = document.getElementById("progress-state");
  const errorBanner = document.getElementById("error-banner");
  const button = document.getElementById("process-button");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBanner.hidden = true;
    progress.hidden = false;
    button.disabled = true;

    const fileInput = document.getElementById("file-input");
    const documentType = document.getElementById("document-type").value;
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("document_type", documentType);

    try {
      const result = await apiFetch(`${API_BASE}/documents/process`, { method: "POST", body: formData });
      window.location.href = `/documents/${encodeURIComponent(result.document_name)}`;
    } catch (err) {
      progress.hidden = true;
      button.disabled = false;
      errorBanner.hidden = false;
      errorBanner.textContent = `${err.code || "ERROR"}: ${err.message}`;
    }
  });
}

let allDocuments = [];

function renderDashboardRows() {
  const tbody = document.getElementById("documents-tbody");
  const emptyState = document.getElementById("empty-state");
  const search = document.getElementById("search-input").value.trim().toLowerCase();
  const type = document.getElementById("type-filter").value;

  const filtered = allDocuments.filter((doc) => {
    const matchesSearch = !search || doc.document_name.toLowerCase().includes(search);
    const matchesType = !type || doc.document_type === type;
    return matchesSearch && matchesType;
  });

  tbody.innerHTML = "";
  filtered.forEach((doc) => {
    const tr = document.createElement("tr");
    tr.className = "clickable-row";
    tr.addEventListener("click", () => {
      window.location.href = `/documents/${encodeURIComponent(doc.document_name)}`;
    });
    const confidencePct =
      doc.overall_confidence === null || doc.overall_confidence === undefined
        ? "n/a"
        : `${Math.round(doc.overall_confidence * 100)}%`;
    tr.innerHTML = `
      <td>${escapeHtml(doc.document_name)}</td>
      <td>${escapeHtml(humanizeLabel(doc.document_type))}</td>
      <td><span class="${statusBadgeClass(doc.processing_status)}">${escapeHtml(doc.processing_status)}</span></td>
      <td>${confidencePct}</td>
      <td>${formatDate(doc.processed_at)}</td>
    `;
    tbody.appendChild(tr);
  });

  emptyState.hidden = filtered.length !== 0;
}

async function initDashboardPage() {
  document.getElementById("search-input").addEventListener("input", renderDashboardRows);
  document.getElementById("type-filter").addEventListener("change", renderDashboardRows);

  try {
    const data = await apiFetch(`${API_BASE}/documents?limit=500`);
    allDocuments = data.items;
    renderDashboardRows();
  } catch (err) {
    const emptyState = document.getElementById("empty-state");
    emptyState.hidden = false;
    emptyState.textContent = `Failed to load documents: ${err.message}`;
  }
}

function createFieldCard(name, field) {
  const wrapper = document.createElement("div");
  wrapper.className = "field-card";
  wrapper.innerHTML = `
    <div class="field-label">${escapeHtml(humanizeLabel(name))}</div>
    <div class="field-value ${fieldStatusClass(field)}">${escapeHtml(formatValue(field.value))}</div>
    ${field.grounded === false ? '<span class="flag flag-ungrounded">ungrounded</span>' : ""}
    ${field.source_text ? `<div class="field-source">"${escapeHtml(field.source_text)}"</div>` : ""}
  `;
  return wrapper;
}

function renderExtractedFields(container, extractedData, excludeKeys) {
  const grid = document.createElement("div");
  grid.className = "field-grid";
  Object.keys(extractedData).forEach((key) => {
    if (excludeKeys.includes(key)) return;
    const field = extractedData[key];
    if (field && typeof field === "object" && "value" in field) {
      grid.appendChild(createFieldCard(key, field));
    }
  });
  container.appendChild(grid);
}

function renderInvoiceLineItems(container, lineItems) {
  if (!lineItems || lineItems.length === 0) {
    container.appendChild(Object.assign(document.createElement("p"), { textContent: "No line items extracted." }));
    return;
  }
  const table = document.createElement("table");
  table.className = "data-table";
  table.innerHTML = "<thead><tr><th>Description</th><th>Quantity</th><th>Unit price</th><th>Amount</th></tr></thead>";
  const tbody = document.createElement("tbody");
  lineItems.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(item.description) || "Not found"}</td>
      <td>${formatValue(item.quantity)}</td>
      <td>${formatValue(item.unit_price)}</td>
      <td>${formatValue(item.amount)}</td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderFinancialLineItems(container, lineItems, periods) {
  if (!lineItems || lineItems.length === 0) {
    container.appendChild(Object.assign(document.createElement("p"), { textContent: "No line items extracted." }));
    return;
  }
  const table = document.createElement("table");
  table.className = "data-table";
  const headCells = ["<th>Label</th><th>Section</th>"].concat(periods.map((p) => `<th>${escapeHtml(p)}</th>`));
  table.innerHTML = `<thead><tr>${headCells.join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  lineItems.forEach((item) => {
    const tr = document.createElement("tr");
    let cells = `<td>${escapeHtml(item.label)}</td><td>${escapeHtml(item.section)}</td>`;
    periods.forEach((period) => {
      const field = item.values[period];
      const flag = field && field.grounded === false ? ' <span class="flag flag-ungrounded">ungrounded</span>' : "";
      cells += `<td class="${fieldStatusClass(field)}">${formatValue(field ? field.value : null)}${flag}</td>`;
    });
    tr.innerHTML = cells;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderValidationTable(container, validation) {
  const table = document.createElement("table");
  table.className = "data-table";
  table.innerHTML =
    "<thead><tr><th>Check</th><th>Formula</th><th>Operands</th><th>Calculated</th><th>Reported</th><th>Variance</th><th>Status</th></tr></thead>";
  const tbody = document.createElement("tbody");
  validation.checks.forEach((check) => {
    const operandsText = Object.entries(check.operands)
      .map(([k, v]) => `${k}=${v === null ? "null" : v}`)
      .join(", ");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(check.name)}</td>
      <td class="formula">${escapeHtml(check.formula)}</td>
      <td class="operands">${escapeHtml(operandsText)}</td>
      <td>${formatValue(check.calculated_value)}</td>
      <td>${formatValue(check.reported_value)}</td>
      <td>${formatValue(check.variance)}</td>
      <td><span class="${statusBadgeClass(check.status)}">${escapeHtml(check.status)}</span></td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);

  if (validation.issues.length > 0) {
    container.appendChild(Object.assign(document.createElement("h3"), { textContent: "Issues" }));
    const list = document.createElement("ul");
    list.className = "issues-list";
    validation.issues.forEach((issue) => {
      list.appendChild(Object.assign(document.createElement("li"), { textContent: issue.message }));
    });
    container.appendChild(list);
  }
}

function renderLegend(container) {
  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML = `
    <span class="legend-item"><span class="value-missing legend-swatch">abc</span> Not found</span>
    <span class="legend-item"><span class="badge badge-fail">FAIL</span> Failed check</span>
    <span class="legend-item"><span class="badge badge-na">N/A</span> Not applicable</span>
    <span class="legend-item"><span class="value-low-confidence legend-swatch">abc</span> Low confidence (&lt; 60%)</span>
    <span class="legend-item"><span class="flag flag-ungrounded">ungrounded</span> Not found in source text</span>
  `;
  container.appendChild(legend);
}

async function initResultPage(documentName) {
  const root = document.getElementById("result-root");
  try {
    const result = await apiFetch(`${API_BASE}/documents/${encodeURIComponent(documentName)}`);
    root.innerHTML = "";

    const confidencePct =
      result.overall_confidence === null || result.overall_confidence === undefined
        ? "n/a"
        : `${Math.round(result.overall_confidence * 100)}%`;
    const header = document.createElement("div");
    header.className = "result-header";
    header.innerHTML = `
      <h1>${escapeHtml(result.document_name)}</h1>
      <div class="result-meta">
        <span class="${statusBadgeClass(result.processing_status)}">${escapeHtml(result.processing_status)}</span>
        <span>${escapeHtml(humanizeLabel(result.document_type))}</span>
        <span>Confidence: ${confidencePct}</span>
        <span>Processed: ${formatDate(result.processing_metadata.processed_at)}</span>
      </div>
    `;
    root.appendChild(header);
    renderLegend(root);

    const fv = result.file_validation;
    const fileSection = document.createElement("section");
    fileSection.innerHTML = `
      <h2>File validation</h2>
      <p>Type: ${escapeHtml(fv.file_type)} | Pages: ${fv.page_count} | Status:
      <span class="${statusBadgeClass(fv.status)}">${escapeHtml(fv.status)}</span></p>
    `;
    root.appendChild(fileSection);

    const extractedSection = document.createElement("section");
    extractedSection.innerHTML = "<h2>Extracted data</h2>";
    renderExtractedFields(extractedSection, result.extracted_data, ["line_items", "periods"]);
    root.appendChild(extractedSection);

    const lineItemsSection = document.createElement("section");
    lineItemsSection.innerHTML = "<h2>Line items</h2>";
    if (result.document_type === "invoice") {
      renderInvoiceLineItems(lineItemsSection, result.extracted_data.line_items);
    } else {
      renderFinancialLineItems(lineItemsSection, result.extracted_data.line_items, result.extracted_data.periods || []);
    }
    root.appendChild(lineItemsSection);

    const validationSection = document.createElement("section");
    validationSection.innerHTML = `
      <h2>Financial validation</h2>
      <p>Overall: <span class="${statusBadgeClass(result.validation.overall_status)}">${escapeHtml(result.validation.overall_status)}</span></p>
    `;
    renderValidationTable(validationSection, result.validation);
    root.appendChild(validationSection);

    const jsonSection = document.createElement("section");
    jsonSection.innerHTML = "<h2>Raw JSON</h2>";
    const details = document.createElement("details");
    details.appendChild(Object.assign(document.createElement("summary"), { textContent: "View raw JSON" }));
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "copy-button";
    copyButton.textContent = "Copy JSON";
    copyButton.addEventListener("click", () => {
      navigator.clipboard.writeText(JSON.stringify(result, null, 2));
      copyButton.textContent = "Copied!";
      setTimeout(() => {
        copyButton.textContent = "Copy JSON";
      }, 1500);
    });
    details.appendChild(copyButton);
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(result, null, 2);
    details.appendChild(pre);
    jsonSection.appendChild(details);
    root.appendChild(jsonSection);
  } catch (err) {
    root.innerHTML = `<div class="status-banner status-error">${escapeHtml(err.code || "ERROR")}: ${escapeHtml(err.message)}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "upload") initUploadPage();
  if (page === "dashboard") initDashboardPage();
  if (page === "result") {
    const root = document.getElementById("result-root");
    initResultPage(root.dataset.documentName);
  }
});
