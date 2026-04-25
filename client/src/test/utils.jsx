import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "../context/AuthContext";
import { SystemProvider } from "../context/SystemContext";

export function AppProviders({ children }) {
  return (
    <BrowserRouter>
      <AuthProvider>
        <SystemProvider>{children}</SystemProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
