/**
 * atva — app.js
 *
 * SSE progress updates, toast auto-dismiss, and modal keyboard handling.
 */

function loadScript(src, { timeoutMs = 2500 } = {}) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;

    const timeout = setTimeout(() => {
      s.remove();
      reject(new Error("Script load timeout: " + src));
    }, timeoutMs);

    s.onload = () => {
      clearTimeout(timeout);
      resolve();
    };
    s.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("Script load error: " + src));
    };

    document.head.appendChild(s);
  });
}

function installHtmxCsrf() {
  if (window.__atvaHtmxCsrfInstalled) return;
  window.__atvaHtmxCsrfInstalled = true;

  document.body.addEventListener("htmx:configRequest", function (evt) {
    try {
      const token = getCookie("csrftoken");
      if (token) {
        evt.detail.headers["X-CSRFToken"] = token;
      }
    } catch (e) {
      // ignore
    }
  });
}

async function ensureHtmxLoaded() {
  if (window.htmx) return true;
  try {
    await loadScript("https://unpkg.com/htmx.org@1.9.12", { timeoutMs: 2500 });
    if (!window.htmx) return false;
    // Needed for <template> fragments (e.g., OOB <tr> swaps).
    window.htmx.config.useTemplateFragments = true;
    installHtmxCsrf();
    return true;
  } catch (e) {
    console.warn(String(e));
    return false;
  }
}

async function ensureSseExtensionLoaded() {
  // SSE extension requires HTMX.
  const ok = await ensureHtmxLoaded();
  if (!ok) return false;

  // If already installed, skip.
  if (window.htmx && window.htmx._ && window.htmx._.extensions && window.htmx._.extensions["sse"]) {
    return true;
  }

  try {
    await loadScript("https://unpkg.com/htmx-ext-sse@2.2.2/sse.js", { timeoutMs: 2500 });
    // Process the DOM after extensions are loaded so behaviors attach correctly.
    window.htmx.process(document.body);
    return true;
  } catch (e) {
    console.warn(String(e));
    return false;
  }
}

function getCookie(name) {
  const prefix = name + "=";
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (let i = 0; i < cookies.length; i++) {
    const c = cookies[i].trim();
    if (c.startsWith(prefix)) {
      return decodeURIComponent(c.substring(prefix.length));
    }
  }
  return null;
}

function ensureToastArea() {
  let toastArea = document.getElementById("toast-area");
  if (toastArea) return toastArea;

  toastArea = document.createElement("div");
  toastArea.id = "toast-area";
  toastArea.className = "toast-area";

  // Insert near top of shell, matching server-rendered placement.
  const shell = document.querySelector(".app-shell");
  if (shell) {
    shell.insertBefore(toastArea, shell.querySelector(".app-main") || null);
  } else {
    document.body.appendChild(toastArea);
  }
  return toastArea;
}

function showToast(message, { variant = "success" } = {}) {
  const toastArea = ensureToastArea();
  const el = document.createElement("div");
  el.className =
    "toast " +
    (variant === "error" ? "toast--error" : variant === "success" ? "toast--success" : "");
  el.textContent = message;
  toastArea.appendChild(el);

  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.4s ease";
    setTimeout(() => el.remove(), 400);
  }, 4000);
}

document.addEventListener("htmx:sseMessage", function (evt) {
  try {
    const data = JSON.parse(evt.detail.data);
    const jobId = data.job_id;
    const progress = data.progress;
    const stage = data.stage;

    const bar = document.getElementById("bar-" + jobId);
    if (bar) {
      bar.style.width = progress + "%";
    }

    const progressEl = document.getElementById("progress-" + jobId);
    if (progressEl) {
      const label = progressEl.querySelector(".progress-label");
      if (label) {
        label.textContent = progress + "%" + (stage ? " \u00b7 " + stage : "");
      }
    }

    const row = document.getElementById("job-" + jobId);
    if (row) {
      const cells = row.querySelectorAll("td");
      if (cells[1]) {
        const stageSpan = cells[1].querySelector("span");
        if (stageSpan) {
          stageSpan.textContent = stage || "";
        }
      }
    }

    if (progress >= 100) {
      setTimeout(() => {
        if (row) {
          if (window.htmx) {
            window.htmx.trigger(row, "reload");
          }
        }
      }, 1500);
    }
  } catch (e) {
    // Non-JSON or malformed — ignore
  }
});

document.addEventListener("DOMContentLoaded", function () {
  // Load HTMX/SSE after initial render to prevent “infinite loading” when CDNs are blocked.
  // This keeps normal navigation fast even if HTMX is unavailable.
  ensureSseExtensionLoaded();
  // If HTMX is already present (e.g., locally vendored), ensure CSRF is installed.
  if (window.htmx) {
    installHtmxCsrf();
  }

  // Avoid FOIT: render with system fonts immediately, then swap to Typekit font when ready.
  // If Typekit is blocked, we still show text (system fonts).
  (function enableFontSwap() {
    const root = document.documentElement;
    const markLoaded = () => root.classList.add("fonts-loaded");

    // If the Font Loading API isn't available, just mark loaded.
    if (!document.fonts || !document.fonts.load) {
      markLoaded();
      return;
    }

    // Try to load the font face; race with a timeout so we don't delay forever.
    const timeoutMs = 1500;
    Promise.race([
      document.fonts.load('1em "sofia-pro-narrow"'),
      new Promise((resolve) => setTimeout(resolve, timeoutMs)),
    ]).finally(markLoaded);
  })();

  // Auto-dismiss toasts
  const toastArea = document.getElementById("toast-area");
  if (toastArea) {
    setTimeout(() => {
      toastArea.style.opacity = "0";
      toastArea.style.transition = "opacity 0.4s ease";
      setTimeout(() => toastArea.remove(), 400);
    }, 4000);
  }

  // Vanilla-JS fallbacks for critical actions when HTMX/CDNs are blocked.
  // These handlers no-op if HTMX is present (HTMX will handle the request).
  document.body.addEventListener("atva:channelSaved", function (e) {
    try {
      const created = Boolean(e.detail && e.detail.created);
      const modal = document.getElementById("add-modal");
      if (modal) modal.classList.add("hidden");
      showToast(created ? "Channel added. Sync started." : "Channel already exists. Sync started.", {
        variant: "success",
      });
    } catch (err) {
      // ignore
    }
  });

  document.body.addEventListener("atva:syncTriggered", function () {
    try {
      showToast("Sync triggered.", { variant: "success" });
    } catch (err) {
      // ignore
    }
  });

  document.addEventListener("submit", async function (e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!form.matches('form[data-atva-add-channel="1"]')) return;
    if (window.htmx) return;

    e.preventDefault();

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const resp = await fetch(form.action, {
        method: "POST",
        headers: {
          "X-Atva-Ajax": "1",
          "X-CSRFToken": getCookie("csrftoken") || "",
          Accept: "application/json",
        },
        body: new FormData(form),
      });

      const payload = await resp.json().catch(() => ({}));

      const container = document.getElementById("add-form-container");
      if (container && payload.form_html) {
        container.innerHTML = payload.form_html;
      }

      if (resp.ok) {
        const list = document.getElementById("channel-list");
        if (list && payload.row_html) {
          list.insertAdjacentHTML("afterbegin", payload.row_html);
        }
        const modal = document.getElementById("add-modal");
        if (modal) modal.classList.add("hidden");
        showToast("Channel added. Sync started.", { variant: "success" });
      } else if (resp.status === 422) {
        // Validation errors are already rendered into the form_html.
      } else {
        showToast("Could not add channel.", { variant: "error" });
      }
    } catch (err) {
      showToast("Network error while adding channel.", { variant: "error" });
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  document.addEventListener("click", async function (e) {
    const btn = e.target instanceof Element ? e.target.closest('button[data-atva-sync="1"]') : null;
    if (!btn) return;
    if (window.htmx) return;

    e.preventDefault();

    const msg = btn.getAttribute("hx-confirm");
    if (msg && !window.confirm(msg)) return;

    const url = btn.getAttribute("data-post-url") || btn.getAttribute("hx-post");
    if (!url) return;

    btn.disabled = true;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "X-Atva-Ajax": "1",
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
      });
      if (resp.ok) {
        showToast("Sync triggered.", { variant: "success" });
      } else {
        showToast("Could not trigger sync.", { variant: "error" });
      }
    } catch (err) {
      showToast("Network error while triggering sync.", { variant: "error" });
    } finally {
      btn.disabled = false;
    }
  });

  // Close modals with Escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop:not(.hidden)").forEach(function (modal) {
        modal.classList.add("hidden");
      });
    }
  });

  // Close modal on backdrop click
  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("modal-backdrop")) {
      e.target.classList.add("hidden");
    }
  });

  // Close dropdown menus when clicking outside
  document.addEventListener("click", function (e) {
    document.querySelectorAll(".dropdown.open").forEach(function (dd) {
      if (!dd.contains(e.target)) {
        dd.classList.remove("open");
      }
    });
  });
});
