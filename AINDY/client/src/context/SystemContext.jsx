import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { bootIdentity } from "../api";
import { useAuth } from "./AuthContext";

const SystemContext = createContext(null);

const EMPTY_SYSTEM = {
  user_id: null,
  memory: [],
  runs: [],
  metrics: null,
  flows: [],
  system_state: {
    memory_count: 0,
    active_runs: 0,
    score: null,
    active_flows: 0,
  },
};

export function SystemProvider({ children }) {
  const { token, logout } = useAuth();
  const [system, setSystem] = useState(EMPTY_SYSTEM);
  const [booting, setBooting] = useState(false);
  const [booted, setBooted] = useState(false);
  const [bootError, setBootError] = useState("");
  const lastBootedTokenRef = useRef(null);

  const clearSystem = () => {
    setSystem(EMPTY_SYSTEM);
    setBooted(false);
    setBootError("");
    lastBootedTokenRef.current = null;
  };

  const bootSystem = async (overrideToken = token) => {
    if (!overrideToken) {
      clearSystem();
      return EMPTY_SYSTEM;
    }

    setBooting(true);
    setBootError("");
    try {
      const result = await bootIdentity(overrideToken);
      setSystem({
        ...EMPTY_SYSTEM,
        ...result,
        memory: result?.memory || [],
        runs: result?.runs || [],
        flows: result?.flows || [],
        metrics: result?.metrics || null,
        system_state: {
          ...EMPTY_SYSTEM.system_state,
          ...(result?.system_state || {}),
        },
      });
      setBooted(true);
      lastBootedTokenRef.current = overrideToken;
      return result;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to boot identity context.";
      setBootError(message);
      setBooted(false);
      if (String(message).includes("401")) {
        logout();
      }
      throw error;
    } finally {
      setBooting(false);
    }
  };

  useEffect(() => {
    if (!token) {
      clearSystem();
      return;
    }
    if (lastBootedTokenRef.current === token && booted) {
      return;
    }
    bootSystem(token).catch(() => {});
  }, [token, booted]);

  const value = useMemo(
    () => ({
      system,
      setSystem,
      clearSystem,
      bootSystem,
      booting,
      booted,
      bootError,
    }),
    [system, booting, booted, bootError],
  );

  return <SystemContext.Provider value={value}>{children}</SystemContext.Provider>;
}

export function useSystem() {
  const context = useContext(SystemContext);
  if (!context) {
    throw new Error("useSystem must be used within SystemProvider.");
  }
  return context;
}
