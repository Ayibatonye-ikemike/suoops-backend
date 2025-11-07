"use client";

import { useCallback, useRef } from "react";

export type OTPInputProps = {
  value: string;
  length?: number;
  onChange: (value: string) => void;
  disabled?: boolean;
  hasError?: boolean;
};

function sanitizeInput(input: string): string {
  return input.replace(/\D/g, "");
}

export function OTPInput({ value, onChange, length = 6, disabled = false, hasError = false }: OTPInputProps) {
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const handleChange = useCallback(
    (index: number, nextValue: string) => {
      if (disabled) return;
      const sanitized = sanitizeInput(nextValue);
      if (!sanitized && nextValue) {
        return;
      }
      const chars = value.split("");
      sanitized
        .slice(0, 1)
        .split("")
        .forEach((digit, i) => {
          chars[index + i] = digit;
        });
      const updated = chars.join("").slice(0, length);
      onChange(updated);
      if (sanitized && index < length - 1) {
        inputsRef.current[index + 1]?.focus();
      }
    },
    [disabled, length, onChange, value]
  );

  const handleKeyDown = useCallback(
    (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
      if (disabled) return;
      if (event.key === "Backspace" && !value[index] && index > 0) {
        inputsRef.current[index - 1]?.focus();
      }
    },
    [disabled, value]
  );

  const handlePaste = useCallback(
    (event: React.ClipboardEvent<HTMLInputElement>) => {
      if (disabled) return;
      event.preventDefault();
      const pasted = sanitizeInput(event.clipboardData.getData("text"))
        .slice(0, length)
        .split("");
      const padded = [...pasted, ...Array.from({ length }, () => "")].slice(0, length).join("");
      onChange(padded);
      const nextIndex = Math.min(pasted.length, length - 1);
      inputsRef.current[nextIndex]?.focus();
    },
    [disabled, length, onChange]
  );

  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length }, (_, index) => (
        <input
          key={index}
          ref={(element) => {
            inputsRef.current[index] = element;
          }}
          type="text"
          inputMode="numeric"
          maxLength={1}
          disabled={disabled}
          value={value[index] || ""}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={handlePaste}
          autoComplete="off"
          className={`h-12 w-12 rounded-lg border-2 text-center text-lg font-semibold tracking-widest transition-colors focus:outline-none focus:ring-2 focus:ring-brand-primary/20 ${
            hasError ? "border-rose-400 focus:border-rose-500" : "border-slate-200 focus:border-brand-primary"
          } ${disabled ? "bg-slate-100 text-slate-400" : "bg-white text-slate-900"}`}
        />
      ))}
    </div>
  );
}
