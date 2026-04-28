import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/_core.js";

function buildCallArgs(args, signal) {
  if (args.length > 0) {
    const lastArg = args[args.length - 1];
    if (lastArg && typeof lastArg === "object" && !Array.isArray(lastArg)) {
      return [
        ...args.slice(0, -1),
        { ...lastArg, signal },
      ];
    }
  }
  return [...args, { signal }];
}

export function useApiCall(apiFn, options = {}) {
  const { domain: configuredDomain = "server", onSuccess, onError } = options;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const mountedRef = useRef(true);
  const abortRef = useRef(null);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const reset = useCallback(() => {
    if (!mountedRef.current) {
      return;
    }
    setError(null);
    setData(null);
  }, []);

  const execute = useCallback(async (...args) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    if (mountedRef.current) {
      setLoading(true);
      setError(null);
    }

    try {
      const result = await apiFn(...buildCallArgs(args, controller.signal));
      if (!mountedRef.current || controller.signal.aborted) {
        return null;
      }
      setData(result);
      onSuccess?.(result);
      return result;
    } catch (err) {
      if (!mountedRef.current || controller.signal.aborted) {
        return null;
      }

      if (err instanceof ApiError) {
        err.domain = configuredDomain;
        if (err.status === 401) {
          return null;
        }
        if (err.status === 408) {
          err.message = `${configuredDomain} timed out. Check your connection and try again.`;
        }
      }

      setError(err);
      onError?.(err);
      return null;
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      if (mountedRef.current && !controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [apiFn, configuredDomain, onError, onSuccess]);

  return { loading, error, data, execute, reset };
}

export default useApiCall;
