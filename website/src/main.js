import "../shared/palette.css";
import "./style.css";
const button = document.querySelector("#copy");
const status = document.querySelector("#copy-status");
button.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(
      document.querySelector("#command").textContent,
    );
    button.textContent = "Copied";
    status.textContent =
      "Clone command copied. Follow the installation guide to build and configure.";
    setTimeout(() => {
      button.textContent = "Copy";
    }, 2500);
  } catch {
    status.textContent = "Select the command above and copy it manually.";
  }
});
