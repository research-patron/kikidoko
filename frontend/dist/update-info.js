(() => {
  const MANIFEST_PATH = "/update-info/index.json";

  function formatDate(value) {
    if (!value) return "日時不明";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "日時不明";
    return date.toLocaleDateString("ja-JP", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function fetchManifest() {
    const response = await fetch(`${MANIFEST_PATH}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`update_info_fetch_failed:${response.status}`);
    }
    return response.json();
  }

  function buildTags(tags) {
    if (!Array.isArray(tags) || tags.length === 0) return "";
    return `
      <ul class="update-tags">
        ${tags.map((tag) => `<li>${escapeHtml(tag)}</li>`).join("")}
      </ul>
    `;
  }

  function buildMeta(entry) {
    const bits = [
      `<time datetime="${escapeHtml(entry.published_at)}">${escapeHtml(formatDate(entry.published_at))}</time>`,
    ];
    if (entry.version_label) {
      bits.push(`<span class="update-version">Ver. ${escapeHtml(entry.version_label)}</span>`);
    }
    if (entry.status) {
      bits.push(`<span class="update-status">${escapeHtml(entry.status)}</span>`);
    }
    return bits.join("");
  }

  function buildEntryMarkup(entry, level = "h3", featured = false) {
    return `
      <article class="update-entry${featured ? " is-featured" : ""}">
        <div class="update-entry-meta">${buildMeta(entry)}</div>
        <${level} class="update-entry-title">${escapeHtml(entry.title)}</${level}>
        <p class="update-entry-summary">${escapeHtml(entry.summary || "")}</p>
        <div class="update-entry-body">${entry.body_html || ""}</div>
        ${buildTags(entry.tags)}
      </article>
    `;
  }

  function renderMonthNav(months) {
    const nav = document.getElementById("update-month-nav");
    if (!nav) return;
    nav.innerHTML = "";
    if (!Array.isArray(months) || months.length === 0) {
      nav.hidden = true;
      return;
    }
    nav.hidden = false;
    nav.innerHTML = months
      .map(
        (month) =>
          `<a href="#month-${escapeHtml(month.key)}" class="update-month-link">${escapeHtml(month.label)}</a>`
      )
      .join("");
  }

  function renderLatest(entry) {
    const container = document.getElementById("update-latest");
    if (!container) return;
    if (!entry) {
      container.innerHTML = '<p class="empty">最新の更新はまだありません。</p>';
      return;
    }
    container.innerHTML = buildEntryMarkup(entry, "h3", true);
  }

  function renderArchive(months) {
    const container = document.getElementById("update-archive");
    if (!container) return;
    if (!Array.isArray(months) || months.length === 0) {
      container.innerHTML = '<p class="empty">過去の更新はまだありません。</p>';
      return;
    }
    container.innerHTML = months
      .map(
        (month) => `
          <section id="month-${escapeHtml(month.key)}" class="update-month-section">
            <h3 class="update-month-title">${escapeHtml(month.label)}</h3>
            <div class="update-month-entries">
              ${(month.entries || []).map((entry) => buildEntryMarkup(entry, "h4")).join("")}
            </div>
          </section>
        `
      )
      .join("");
  }

  function renderError() {
    const latest = document.getElementById("update-latest");
    const archive = document.getElementById("update-archive");
    const nav = document.getElementById("update-month-nav");
    if (latest) latest.innerHTML = '<p class="empty">更新情報の取得に失敗しました。</p>';
    if (archive) archive.innerHTML = "";
    if (nav) nav.hidden = true;
  }

  async function initPage() {
    try {
      const manifest = await fetchManifest();
      renderMonthNav(manifest.months || []);
      renderLatest(manifest.latest || null);
      renderArchive(manifest.months || []);
    } catch (error) {
      console.error(error);
      renderError();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initPage().catch((error) => console.error(error));
    });
  } else {
    initPage().catch((error) => console.error(error));
  }
})();
