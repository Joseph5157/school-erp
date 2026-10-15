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
})();
