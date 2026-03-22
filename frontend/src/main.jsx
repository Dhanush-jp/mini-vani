import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error('Missing DOM element "#root" — check index.html.');
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>
);
