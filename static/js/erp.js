// School ERP progressive enhancements. Every page works without this file.
(function () {
  "use strict";

  // Show/hide password: buttons start hidden so no-JS users never see a dead control.
  document.querySelectorAll("[data-erp-toggle-password]").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;
    button.hidden = false;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.textContent = showing ? "Show" : "Hide";
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      input.focus();
    });
  });

  // Sidebar groups: the group with the active page (and Home) stays open; the others remember being opened
  // or closed in this browser. Without JS or storage the server-rendered state is used as is.
  (function () {
    var key = "erp.nav.open";
    var groups = document.querySelectorAll("[data-erp-nav-group]");
    if (!groups.length) return;
    var stored = null;
    try { stored = JSON.parse(window.localStorage.getItem(key)); } catch (error) { stored = null; }
    if (!stored || typeof stored !== "object") stored = {};
    groups.forEach(function (group) {
      var name = group.getAttribute("data-erp-nav-group");
      if (!group.hasAttribute("data-erp-nav-pinned") && stored[name] === true) group.open = true;
      group.addEventListener("toggle", function () {
        if (group.hasAttribute("data-erp-nav-pinned")) return;
        stored[name] = group.open;
        try { window.localStorage.setItem(key, JSON.stringify(stored)); } catch (error) { /* storage unavailable */ }
      });
    });
    var active = document.querySelector(".erp-sidebar .nav-link.active");
    if (active && active.scrollIntoView) active.scrollIntoView({ block: "nearest" });
  })();

  // Success and info messages close after 6 seconds; warnings and errors stay until dismissed.
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll("[data-erp-autohide]").forEach(function (alert) {
    window.setTimeout(function () {
      if (window.bootstrap && window.bootstrap.Alert && !reduceMotion) {
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      } else {
        alert.remove();
      }
    }, 6000);
  });

  // Attendance roster: live counts, filter tabs, mark-unanswered-present, submit hint.
  // Without JS the static count line stays and every row is shown.
  document.querySelectorAll("[data-erp-roster]").forEach(function (roster) {
    var rows = Array.prototype.slice.call(roster.querySelectorAll("[data-erp-row]"));
    var tabs = roster.querySelector("[data-erp-tabs]");
    var staticCounts = roster.querySelector("[data-erp-static-counts]");
    var filter = "all";
    var autosaveOn = false; // set once HTMX autosave is wired below

    function statusOf(row) {
      var checked = row.querySelector('input[type="radio"]:checked');
      return checked ? checked.value.toLowerCase() : "unmarked";
    }

    function refresh() {
      var counts = { all: rows.length, present: 0, absent: 0, unmarked: 0 };
      rows.forEach(function (row) {
        var status = statusOf(row);
        counts[status] += 1;
        row.hidden = filter !== "all" && filter !== status;
      });
      Object.keys(counts).forEach(function (key) {
        var target = roster.querySelector('[data-erp-count="' + key + '"]');
        if (target) target.textContent = counts[key];
      });
      roster.querySelectorAll(".erp-count-unmarked").forEach(function (el) {
        el.classList.toggle("is-warn", counts.unmarked > 0);
      });
      // Looked up each time: an HTMX autosave response may have replaced the element.
      var hint = roster.querySelector("[data-erp-hint]");
      if (hint) {
        hint.classList.toggle("is-warn", counts.unmarked > 0);
        hint.textContent = counts.unmarked
          ? "Mark all students to submit (" + counts.unmarked + " unmarked)"
          : "All students marked";
      }
    }

    if (tabs) {
      tabs.hidden = false;
      if (staticCounts) staticCounts.hidden = true;
      tabs.querySelectorAll("[data-erp-filter]").forEach(function (button) {
        button.addEventListener("click", function () {
          filter = button.getAttribute("data-erp-filter");
          tabs.querySelectorAll("[data-erp-filter]").forEach(function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
          });
          refresh();
        });
      });
    }

    // Fills Present only for rows not yet answered and never overrides a choice.
    // Without autosave nothing is saved until the form is submitted.
    var markPresent = roster.querySelector("[data-erp-mark-present]");
    if (markPresent) {
      markPresent.addEventListener("click", function () {
        rows.forEach(function (row) {
          if (statusOf(row) === "unmarked") {
            var present = row.querySelector('input[type="radio"][value="PRESENT"]');
            if (!present) return;
            present.checked = true;
            // With autosave each bulk-marked row takes the same save path as a manual change.
            if (autosaveOn) present.dispatchEvent(new Event("change", { bubbles: true }));
          }
        });
        refresh();
      });
    }

    roster.addEventListener("change", function (event) {
      if (event.target.type === "radio") refresh();
    });
    refresh();

    // HTMX draft autosave (teacher page only). Each row saves itself on change; the form's
    // Save draft / Save and submit buttons remain the complete fallback and the only way to
    // submit. A row is only shown as saved once the server confirms it.
    var announce = roster.querySelector("[data-erp-autosave-announce]");
    var swapping = null;

    function nameOf(row) {
      var legend = row.querySelector("legend");
      return legend ? legend.textContent.trim() : "student";
    }
    function statusOfRow(row) {
      return row.querySelector("[data-erp-row-status]");
    }
    function showFailure(row, text) {
      var target = statusOfRow(row);
      target.textContent = "";
      var message = document.createElement("span");
      message.className = "erp-row-failed";
      message.textContent = text + " ";
      var retry = document.createElement("button");
      retry.type = "button";
      retry.className = "btn btn-sm btn-outline-secondary";
      retry.setAttribute("data-erp-retry", "");
      retry.textContent = "Retry";
      target.appendChild(message);
      target.appendChild(retry);
    }
    function othersDirty() {
      return rows.some(function (row) {
        return row._dirty && (row !== swapping || row._sent !== row._seq);
      });
    }

    if (window.htmx && roster.querySelector("[hx-post]")) {
      window.htmx.config.responseHandling = [
        { code: "204", swap: false },
        { code: "[23]..", swap: true },
        { code: "409|422", swap: true, error: true },
        { code: "[45]..", swap: false, error: true },
        { code: "...", swap: false },
      ];

      // Capture phase: must run before HTMX's own listener on the row reads _seq.
      roster.addEventListener("change", function (event) {
        var row = event.target.closest("[data-erp-row]");
        if (!row) return;
        row._seq = (row._seq || 0) + 1;
        row._dirty = true;
        var target = statusOfRow(row);
        if (target) target.textContent = "Saving…";
        row.classList.remove("is-unsaved");
      }, true);

      // Present never carries a note: clear it with the choice, as the server would refuse it.
      roster.addEventListener("htmx:configRequest", function (event) {
        var row = event.detail.elt;
        row._sent = row._seq; // the change this request carries
        var note = row.querySelector('input[name^="note_"]');
        var chosen = row.querySelector('input[type="radio"]:checked');
        if (note && chosen && chosen.value === "PRESENT" && note.value) {
          note.value = "";
          event.detail.parameters[note.name] = "";
        }
      });

      roster.addEventListener("htmx:beforeSwap", function (event) {
        // detail.elt is the swap target; the row that made the request is on requestConfig.
        swapping = event.detail.requestConfig ? event.detail.requestConfig.elt : null;
      });
      // Counts in a response only describe saved rows; skip them while other rows are in flight.
      roster.addEventListener("htmx:oobBeforeSwap", function (event) {
        if (othersDirty()) event.preventDefault();
      });
      roster.addEventListener("htmx:afterSwap", function () {
        swapping = null;
      });
      roster.addEventListener("htmx:afterRequest", function (event) {
        var row = event.detail.elt;
        if (!row.hasAttribute || !row.hasAttribute("data-erp-row")) return;
        if (row._sent === row._seq) row._dirty = false;
        var ok = event.detail.successful;
        row.classList.toggle("is-unsaved", !ok);
        if (announce) {
          announce.textContent = ok
            ? "Saved " + nameOf(row) + "."
            : "Could not save " + nameOf(row) + ". Use Retry or Save draft.";
        }
        if (!ok) {
          var status = event.detail.xhr ? event.detail.xhr.status : 0;
          // 409 and 422 responses carry their own message and are already swapped in.
          if (status !== 409 && status !== 422) showFailure(row, "Not saved.");
        }
        if (!othersDirty()) refresh();
      });
      autosaveOn = true;

      // Save draft / Save and submit wait for in-flight row saves so the two never race.
      var form = roster.closest("form");
      var waitMessage = roster.querySelector("[data-erp-wait-message]");
      function anyDirty() {
        return rows.some(function (row) { return row._dirty; });
      }
      if (form) {
        form.addEventListener("submit", function (event) {
          if (!anyDirty()) return;
          event.preventDefault();
          if (waitMessage) waitMessage.hidden = false;
          if (announce) announce.textContent = "Waiting for attendance changes to save.";
        });
        roster.addEventListener("htmx:afterRequest", function () {
          if (waitMessage && !anyDirty()) waitMessage.hidden = true;
        });
      }

      roster.addEventListener("click", function (event) {
        var retry = event.target.closest("[data-erp-retry]");
        if (retry) window.htmx.trigger(retry.closest("[data-erp-row]"), "change");
      });
    }
  });

  // Marks entry: live counts and filter tabs; typing a score selects Marked;
  // Absent clears and disables the score box. Without JS the server rules apply.
  document.querySelectorAll("[data-erp-marks]").forEach(function (sheet) {
    var rows = Array.prototype.slice.call(sheet.querySelectorAll("[data-erp-row]"));
    var tabs = sheet.querySelector("[data-erp-tabs]");
    var staticCounts = sheet.querySelector("[data-erp-static-counts]");
    var hint = sheet.querySelector("[data-erp-hint]");
    var filter = "all";

    function parts(row) {
      return {
        score: row.querySelector("input.erp-score"),
        checked: row.querySelector('input[type="radio"]:checked'),
        marked: row.querySelector('input[type="radio"][value="MARKED"]'),
      };
    }

    function statusOf(row) {
      var p = parts(row);
      var value = p.checked ? p.checked.value : "";
      if (value === "ABSENT") return "absent";
      if (value === "MARKED" || (p.score && p.score.value.trim() !== "")) return "marked";
      return "unmarked";
    }

    // reapply is false while typing so a row never vanishes mid-keystroke.
    function refresh(reapply) {
      var counts = { all: rows.length, marked: 0, absent: 0, unmarked: 0 };
      rows.forEach(function (row) {
        var status = statusOf(row);
        counts[status] += 1;
        if (reapply) row.hidden = filter !== "all" && filter !== status;
        var p = parts(row);
        if (p.score) p.score.disabled = status === "absent";
      });
      Object.keys(counts).forEach(function (key) {
        var target = sheet.querySelector('[data-erp-count="' + key + '"]');
        if (target) target.textContent = counts[key];
      });
      if (hint) hint.textContent = counts.unmarked + " not entered";
    }

    if (tabs) {
      tabs.hidden = false;
      if (staticCounts) staticCounts.hidden = true;
      tabs.querySelectorAll("[data-erp-filter]").forEach(function (button) {
        button.addEventListener("click", function () {
          filter = button.getAttribute("data-erp-filter");
          tabs.querySelectorAll("[data-erp-filter]").forEach(function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
          });
          refresh(true);
        });
      });
    }

    sheet.addEventListener("input", function (event) {
      if (!event.target.classList.contains("erp-score")) return;
      var p = parts(event.target.closest("[data-erp-row]"));
      if (event.target.value.trim() !== "" && (!p.checked || p.checked.value === "")) {
        p.marked.checked = true;
      }
      refresh(false);
    });
    sheet.addEventListener("change", function (event) {
      if (event.target.type !== "radio") return;
      var p = parts(event.target.closest("[data-erp-row]"));
      if ((event.target.value === "ABSENT" || event.target.value === "") && p.score) p.score.value = "";
      refresh(true);
    });
    // Keypad Next/Enter moves to the next student instead of submitting the form.
    sheet.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || !event.target.classList.contains("erp-score")) return;
      event.preventDefault();
      var index = rows.indexOf(event.target.closest("[data-erp-row]"));
      for (var i = index + 1; i < rows.length; i++) {
        var next = rows[i].querySelector("input.erp-score");
        if (!rows[i].hidden && next && !next.disabled) { next.focus(); return; }
      }
      var save = sheet.querySelector('button[type="submit"]');
      if (save) save.focus();
    });
    var firstInvalid = sheet.querySelector(".erp-roster-row.is-invalid");
    if (firstInvalid && firstInvalid.scrollIntoView) firstInvalid.scrollIntoView({ block: "center" });
    refresh(true);
  });

  // Announcement form: show the Class or Section selector only for its audience.
  // Hidden fields are disabled so they are not submitted. Without JS both stay visible.
  document.querySelectorAll("[data-erp-audience-form]").forEach(function (form) {
    var radios = Array.prototype.slice.call(form.querySelectorAll('input[type="radio"][name="audience"]'));
    var fields = Array.prototype.slice.call(form.querySelectorAll("[data-erp-audience-field]"));
    if (!radios.length || !fields.length) return;

    function refresh() {
      var checked = radios.filter(function (radio) { return radio.checked; })[0];
      var audience = checked ? checked.value : "";
      fields.forEach(function (field) {
        var show = field.getAttribute("data-erp-audience-field") === audience;
        field.hidden = !show;
        field.querySelectorAll("select, input").forEach(function (control) {
          control.disabled = !show;
        });
      });
    }

    form.addEventListener("change", function (event) {
      if (event.target.name === "audience") refresh();
    });
    refresh();
  });

  // One-shot submit buttons: disable after the first submit so a double click cannot
  // publish twice. The form carries its own hidden confirm input, so nothing is lost.
  document.querySelectorAll("[data-erp-once]").forEach(function (button) {
    var form = button.form;
    if (!form) return;
    form.addEventListener("submit", function () {
      window.setTimeout(function () { button.disabled = true; }, 0);
    });
  });
})();

// Child switcher: a native details element, so the links work without JS. This only adds
// Escape / outside-tap closing and returns focus to the toggle.
(function () {
  var switcher = document.querySelector("[data-erp-switcher]");
  if (!switcher) return;
  function close() {
    if (!switcher.open) return;
    switcher.open = false;
    var toggle = switcher.querySelector("summary");
    if (toggle) toggle.focus();
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") close();
  });
  document.addEventListener("click", function (event) {
    if (!switcher.contains(event.target) || event.target === switcher) close();
  });
})();

// Install button (PWA): shown only when the browser offers a usable install prompt, and only on
// the install help page. Everywhere else the browser's own install affordance is left alone.
(function () {
  var button = document.querySelector("[data-erp-install]");
  if (!button) return;
  var offered = null;
  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    offered = event;
    button.hidden = false;
  });
  button.addEventListener("click", function () {
    if (!offered) return;
    var prompt = offered;
    offered = null;
    button.hidden = true;
    prompt.prompt();
  });
  window.addEventListener("appinstalled", function () {
    offered = null;
    button.hidden = true;
  });
})();
