"use client";

import { useCallback, useState } from "react";

interface UseControllableStateOptions<T> {
  value?: T;
  defaultValue: T;
  onChange?: (value: T) => void;
}

export function useControllableState<T>({ value, defaultValue, onChange }: UseControllableStateOptions<T>) {
  const [internalValue, setInternalValue] = useState(defaultValue);
  const controlled = value !== undefined;
  const currentValue = controlled ? value : internalValue;

  const setValue = useCallback((nextValue: T) => {
    if (!controlled) setInternalValue(nextValue);
    onChange?.(nextValue);
  }, [controlled, onChange]);

  return [currentValue, setValue] as const;
}
