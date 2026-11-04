import { useCallback, useEffect, useRef, useState } from "react";

export interface UsePollingOptions<T> {
  callback: () => Promise<T>;
  intervalMs?: number;
  backoffIntervalMs?: number;
  maxConsecutiveErrors?: number;
  stopWhen?: (data: T) => boolean;
  enabled?: boolean;
}

export interface UsePollingResult {
  isPolling: boolean;
  consecutiveErrors: number;
  isConnectionIssue: boolean;
  restart: () => void;
}

/**
 * Polls an async callback at a regular interval.
 * - Refetches at intervalMs (default 3000ms)
 * - Stops when stopWhen(data) returns true
 * - Pauses automatically when tab is hidden (visibilitychange)
 * - Cleans up timers on unmount
 * - Never overlaps requests (schedules next poll only after previous completes)
 * - Backs off to backoffIntervalMs (default 10000ms) after 3 consecutive fetch errors
 * - Exposes isConnectionIssue when consecutive errors reach the threshold
 */
export function usePolling<T>({
  callback,
  intervalMs = 3000,
  backoffIntervalMs = 10000,
  maxConsecutiveErrors = 3,
  stopWhen,
  enabled = true,
}: UsePollingOptions<T>): UsePollingResult {
  const [isPolling, setIsPolling] = useState(enabled);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const stoppedRef = useRef(!enabled);
  const consecutiveErrorsRef = useRef(0);

  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const stopWhenRef = useRef(stopWhen);
  stopWhenRef.current = stopWhen;

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const executePollRef = useRef<() => Promise<void>>(() => Promise.resolve());

  const scheduleNext = useCallback(
    (delayMs: number) => {
      clearTimer();
      if (stoppedRef.current) return;
      if (typeof document !== "undefined" && document.hidden) return;
      timerRef.current = setTimeout(() => {
        void executePollRef.current();
      }, delayMs);
    },
    [clearTimer],
  );

  executePollRef.current = async () => {
    if (stoppedRef.current || inFlightRef.current) {
      return;
    }

    if (typeof document !== "undefined" && document.hidden) {
      return;
    }

    inFlightRef.current = true;
    try {
      const data = await callbackRef.current();
      consecutiveErrorsRef.current = 0;
      setConsecutiveErrors(0);

      if (stopWhenRef.current && stopWhenRef.current(data)) {
        stoppedRef.current = true;
        setIsPolling(false);
        clearTimer();
        return;
      }

      scheduleNext(intervalMs);
    } catch {
      consecutiveErrorsRef.current += 1;
      const count = consecutiveErrorsRef.current;
      setConsecutiveErrors(count);

      const delay = count >= maxConsecutiveErrors ? backoffIntervalMs : intervalMs;
      scheduleNext(delay);
    } finally {
      inFlightRef.current = false;
    }
  };

  const restart = useCallback(() => {
    stoppedRef.current = false;
    consecutiveErrorsRef.current = 0;
    setConsecutiveErrors(0);
    setIsPolling(true);
    clearTimer();
    void executePollRef.current();
  }, [clearTimer]);

  useEffect(() => {
    if (!enabled) {
      stoppedRef.current = true;
      setIsPolling(false);
      clearTimer();
      return;
    }

    stoppedRef.current = false;
    setIsPolling(true);
    void executePollRef.current();

    const handleVisibilityChange = () => {
      if (document.hidden) {
        clearTimer();
      } else if (!stoppedRef.current && !inFlightRef.current) {
        void executePollRef.current();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stoppedRef.current = true;
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [enabled, clearTimer]);

  return {
    isPolling,
    consecutiveErrors,
    isConnectionIssue: consecutiveErrors >= maxConsecutiveErrors,
    restart,
  };
}
