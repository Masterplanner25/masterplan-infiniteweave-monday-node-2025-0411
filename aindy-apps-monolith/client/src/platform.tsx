import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import PlatformApp from "./PlatformApp";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PlatformApp />
  </StrictMode>,
);
