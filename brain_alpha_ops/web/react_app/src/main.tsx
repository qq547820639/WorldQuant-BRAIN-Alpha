import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "@/components/ErrorBoundary";
import { GlobalDataProvider } from "@/hooks/useGlobalData";
import "./index.css";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found in DOM");
ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ErrorBoundary>
      <GlobalDataProvider>
        <App />
      </GlobalDataProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
