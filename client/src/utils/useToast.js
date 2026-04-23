import { useCallback, useState } from "react";

export function useToast() {
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = "error") => {
    setToast({ message: String(message), type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const clearToast = useCallback(() => setToast(null), []);

  return { toast, showToast, clearToast };
}
