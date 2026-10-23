document.getElementById("external-script").textContent =
  "allowed.js çalıştı.";
document.getElementById("external-event").addEventListener("click", function () {
  document.body.dataset.externalEvent = "ran";
});
