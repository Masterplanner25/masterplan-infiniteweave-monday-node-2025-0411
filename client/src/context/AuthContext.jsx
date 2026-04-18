import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  clearStoredToken,
  getStoredToken,
  loginUser,
  registerUser,
  setStoredToken,
} from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getStoredToken());

  useEffect(() => {
    setToken(getStoredToken());
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
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
      setToken,
    }),
    [token],
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
