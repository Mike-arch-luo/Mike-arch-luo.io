(() => {
  "use strict";

  const form = document.getElementById("f");
  const message = document.getElementById("m");
  const count = document.getElementById("message-count");
  const status = document.getElementById("fs");
  const submitButton = form?.querySelector('button[type="submit"]');
  const recipient = "akadiwofoundation@gmail.com";
  const requestTimeoutMs = 10000;

  if (!form || !message || !count || !status || !submitButton) return;

  const defaultButtonText = submitButton.textContent;

  function updateMessageCount() {
    count.textContent = `${message.value.length.toLocaleString("en-US")} characters`;
  }

  function openMailFallback(data) {
    const subject = `${data.topic} - message from ${data.name}`;
    const body = `${data.message}\n\n${data.name} (${data.email})`;
    const params = new URLSearchParams({ subject, body });
    window.location.href = `mailto:${recipient}?${params.toString()}`;
  }

  message.addEventListener("input", updateMessageCount);
  form.addEventListener("reset", () => requestAnimationFrame(updateMessageCount));
  updateMessageCount();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled || !form.reportValidity()) return;

    const data = Object.fromEntries(new FormData(form).entries());
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, requestTimeoutMs);

    submitButton.disabled = true;
    submitButton.textContent = "Sending...";
    form.setAttribute("aria-busy", "true");
    status.textContent = "Sending your message...";

    try {
      const response = await fetch(new URL("contact.php", window.location.href), {
        method: "POST",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(data),
        signal: controller.signal
      });
      const result = await response.json().catch(() => null);

      if (!response.ok || !result?.ok) {
        const error = new Error(result?.error || "Message could not be sent.");
        error.status = response.status;
        throw error;
      }

      status.textContent = "Thank you. Your message has been sent.";
      form.reset();
    } catch (error) {
      if (error.status === 422 || error.status === 429) {
        status.textContent = error.message;
        return;
      }

      status.textContent = timedOut
        ? "The message service took too long to respond. Opening an email draft instead."
        : "The message service is unavailable. Opening an email draft instead.";
      openMailFallback(data);
    } finally {
      window.clearTimeout(timeoutId);
      submitButton.disabled = false;
      submitButton.textContent = defaultButtonText;
      form.removeAttribute("aria-busy");
    }
  });
})();
