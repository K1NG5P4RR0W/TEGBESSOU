import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./design-system/tokens.css";

const rootEl = document.getElementById("root");
if (rootEl === null) {
  throw new Error("élément #root introuvable");
}
createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
