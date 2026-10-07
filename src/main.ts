import { invoke } from "@tauri-apps/api/core";

export interface SystemInfo {
  app_name: string;
  version: string;
  architecture: string;
  status: string;
}

window.addEventListener("DOMContentLoaded", async () => {
  const lblStatus = document.getElementById("lbl-status");
  const lblArch = document.getElementById("lbl-arch");
  const btnPing = document.getElementById("btn-ping");
  const btnClear = document.getElementById("btn-clear");
  const consoleOutput = document.getElementById("console-output");

  function log(msg: string) {
    if (consoleOutput) {
      const ts = new Date().toLocaleTimeString();
      consoleOutput.textContent += `[${ts}] ${msg}\n`;
      consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }
  }

  log("Subterranean Staircase v2 frontend initialized.");

  try {
    const info = await invoke<SystemInfo>("get_system_info");
    if (lblStatus) lblStatus.textContent = info.status;
    if (lblArch) lblArch.textContent = info.architecture;
    log(`Connected to Rust core: ${info.app_name} (${info.version}) on ${info.architecture}`);
  } catch (err) {
    if (lblStatus) lblStatus.textContent = "Standby / Web Preview";
    log(`Initial handshake: ${String(err)} (Running in standalone browser or awaiting core)`);
  }

  if (btnClear && consoleOutput) {
    btnClear.addEventListener("click", () => {
      consoleOutput.textContent = "";
    });
  }

  if (btnPing) {
    btnPing.addEventListener("click", async () => {
      try {
        const reply = await invoke<string>("ping", { message: "Hello from Vite Frontend!" });
        log(`Rust Core Reply: ${reply}`);
      } catch (err) {
        log(`Ping error: ${String(err)}`);
      }
    });
  }
});
