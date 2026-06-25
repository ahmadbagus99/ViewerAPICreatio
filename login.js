const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#login-error");

async function checkSession() {
  const response = await fetch("/api/admin/session", { cache: "no-store" });
  if (response.ok) window.location.replace("/admin.html");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.querySelector("#username").value,
        password: document.querySelector("#password").value
      })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Login failed.");
    window.location.replace("/admin.html");
  } catch (error) {
    errorBox.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

checkSession();

