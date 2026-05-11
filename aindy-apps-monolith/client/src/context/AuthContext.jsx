import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  clearStoredToken,
  getStoredToken,
  loginUser,
  registerUser,
  setStoredToken,
} from "../api";

const AuthContext = createContext(null);

function parseJwtPayload(token) {
  if (!token) {
    return null;
  }

  try {
    const [, payload = ""] = token.split(".");
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

function isTokenExpired(token) {
  const payload = parseJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") {
    return false;
  }
  return Date.now() / 1000 > payload.exp - 30;
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => {
    const stored = getStoredToken();
    if (stored && isTokenExpired(stored)) {
      clearStoredToken();
      return null;
    }
    return stored || null;
  });
  const user = useMemo(() => {
    const payload = parseJwtPayload(token);
    if (!payload) {
      return null;
    }
    return {
      ...payload,
      is_admin: payload?.is_admin === true,
    };
  }, [token]);
  const isAdmin = user?.is_admin === true;

  useEffect(() => {
    const stored = getStoredToken();
    if (stored && isTokenExpired(stored)) {
      clearStoredToken();
      setToken(null);
      return;
    }
    setToken(stored || null);
  }, []);

  useEffect(() => {
    if (!token) {
      return undefined;
    }
    const interval = setInterval(() => {
      if (isTokenExpired(token)) {
        clearStoredToken();
        setToken(null);
      }
    }, 60_000);
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    const handleExpiry = () => {
      clearStoredToken();
      setToken(null);
    };
    window.addEventListener("aindy:session-expired", handleExpiry);
    return () => window.removeEventListener("aindy:session-expired", handleExpiry);
  }, []);

  const login = async (email, password) => {
    const response = await loginUser({ email, password });
    const nextToken = response?.access_token;
    if (!nextToken) {
      throw new Error("Authentication did not return an access token.");
    }
    setStoredToken(nextToken);
    setToken(nextToken);
    return nextToken;
  };

  const register = async (email, password, username = null) => {
    const response = await registerUser({ email, password, username });
    const nextToken = response?.access_token;
    if (!nextToken) {
      throw new Error("Authentication did not return an access token.");
    }
    setStoredToken(nextToken);
    setToken(nextToken);
    return nextToken;
  };

  const logout = () => {
    clearStoredToken();
    setToken(null);
  };

  const value = useMemo(
    () => ({
      token,
      user,
      isAdmin,
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
      setToken,
    }),
    [token, user, isAdmin],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
