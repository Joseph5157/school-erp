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
    var hint = roster.querySelector("[data-erp-hint]");
    var filter = "all";

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
      if (hint) {
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
    // Nothing is saved until the form is submitted, so an unopened register is never present.
    var markPresent = roster.querySelector("[data-erp-mark-present]");
    if (markPresent) {
      markPresent.addEventListener("click", function () {
        rows.forEach(function (row) {
          if (statusOf(row) === "unmarked") {
            var present = row.querySelector('input[type="radio"][value="PRESENT"]');
            if (present) present.checked = true;
          }
        });
        refresh();
      });
    }

    roster.addEventListener("change", function (event) {
      if (event.target.type === "radio") refresh();
    });
    refresh();
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
