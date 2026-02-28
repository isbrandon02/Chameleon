import { Auth0Provider } from "@auth0/auth0-react";
import { StrictMode, Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const domain = import.meta.env.VITE_AUTH0_DOMAIN as string;
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID as string;
const audience = import.meta.env.VITE_AUTH0_AUDIENCE as string;

class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          background: "#0B0F0E",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "Inter, system-ui, sans-serif",
        }}>
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 18, fontWeight: 600 }}>Something went wrong.</p>
            <p style={{ marginTop: 8, color: "rgba(255,255,255,0.35)", fontSize: 14 }}>
              Please refresh the page.
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: 24,
                background: "#4ADE80",
                color: "#0B0F0E",
                border: "none",
                borderRadius: 999,
                padding: "10px 28px",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Refresh
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        authorizationParams={{
          redirect_uri: `${window.location.origin}/callback`,
          audience,
        }}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </Auth0Provider>
    </ErrorBoundary>
  </StrictMode>
);
