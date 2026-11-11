"use client";

import { Check, ChevronDown } from "lucide-react";
import {
  Children,
  forwardRef,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type OptionHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { iconDefaults } from "@/lib/iconography";
import { positionDropdown, type DropdownPosition } from "./viewport-position";
import styles from "./primitives.module.css";
import { Field, FieldDescription, FieldError, FieldLabel } from "./field";
import { cx, setRef } from "./utils";
import type { ControlSize } from "./button";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: ReactNode;
  placeholder?: string;
  helperText?: ReactNode;
  error?: ReactNode;
  options: SelectOption[];
  controlSize?: ControlSize;
  /** Used by NativeSelect inside existing labelled filter layouts. */
  bare?: boolean;
}

function optionText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(optionText).join("");
  if (isValidElement<{ children?: ReactNode }>(children)) return optionText(children.props.children);
  return "";
}

/** Compatibility adapter for existing native option trees; keeps their values and callbacks. */
export const NativeSelect = forwardRef<
  HTMLSelectElement,
  Omit<SelectProps, "options" | "bare"> & { children: ReactNode }
>(function NativeSelect({ children, ...props }, ref) {
  const options = Children.toArray(children).flatMap((child): SelectOption[] => {
    if (!isValidElement<OptionHTMLAttributes<HTMLOptionElement>>(child) || child.type !== "option") return [];
    return [{
      value: String(child.props.value ?? optionText(child.props.children)),
      label: child.props.label ?? optionText(child.props.children),
      disabled: child.props.disabled,
    }];
  });
  return <Select {...props} options={options} ref={ref} bare />;
});

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    id,
    label,
    placeholder,
    helperText,
    error,
    options,
    controlSize = "md",
    className,
    disabled,
    multiple,
    bare = false,
    value,
    defaultValue,
    onChange,
    name,
    required,
    "aria-describedby": ariaDescribedBy,
    "aria-label": ariaLabel,
    "aria-labelledby": ariaLabelledBy,
    ...nativeProps
  },
  forwardedRef,
) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const listId = selectId + "-listbox";
  const helperId = helperText ? selectId + "-description" : undefined;
  const errorId = error ? selectId + "-error" : undefined;
  const labelId = label ? selectId + "-label" : undefined;
  const describedBy = [ariaDescribedBy, helperId, errorId].filter(Boolean).join(" ") || undefined;
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const nativeRef = useRef<HTMLSelectElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [position, setPosition] = useState<DropdownPosition | null>(null);
  const [internalValue, setInternalValue] = useState(() => {
    if (typeof defaultValue === "string" || typeof defaultValue === "number") return String(defaultValue);
    return placeholder ? "" : options[0]?.value ?? "";
  });
  const currentValue = typeof value === "string" || typeof value === "number" ? String(value) : internalValue;
  const selectedIndex = options.findIndex((option) => option.value === currentValue);
  const selectedOption = options[selectedIndex];
  const readonly = nativeProps["aria-readonly"] === true || nativeProps["aria-readonly"] === "true";
  const available = !disabled && !readonly && options.some((option) => !option.disabled);
  const labelledBy = ariaLabel ? undefined : [ariaLabelledBy, labelId].filter(Boolean).join(" ") || undefined;

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!available) setOpen(false);
  }, [available]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!shellRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !mounted || multiple) return;
    const update = () => {
      if (!triggerRef.current || !panelRef.current) return;
      const next = positionDropdown(triggerRef.current.getBoundingClientRect(), panelRef.current.getBoundingClientRect());
      setPosition((previous) => previous && Object.keys(next).every((key) => (
        previous[key as keyof DropdownPosition] === next[key as keyof DropdownPosition]
      )) ? previous : next);
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    if (triggerRef.current) observer?.observe(triggerRef.current);
    if (panelRef.current) observer?.observe(panelRef.current);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [mounted, multiple, open, options, currentValue]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    panelRef.current?.querySelectorAll<HTMLElement>('[role="option"]')[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  const openList = () => {
    if (!available) return;
    const current = selectedIndex >= 0 && !options[selectedIndex].disabled
      ? selectedIndex : options.findIndex((option) => !option.disabled);
    setActiveIndex(current);
    setPosition(null);
    setOpen(true);
  };

  const choose = (nextValue: string) => {
    if (!available) return;
    if (value === undefined) setInternalValue(nextValue);
    const select = nativeRef.current;
    if (select) {
      // Use the native change event so existing consumers still receive event.target.value.
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
      setter?.call(select, nextValue);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    setOpen(false);
    triggerRef.current?.focus();
  };

  const move = (from: number, direction: number) => {
    if (!options.length) return;
    for (let i = 1; i <= options.length; i += 1) {
      const next = (from + direction * i + options.length * (i + 1)) % options.length;
      if (!options[next].disabled) {
        setActiveIndex(next);
        return;
      }
    }
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!available) return;
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openList();
      else move(activeIndex, event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      if (!open) openList();
      setActiveIndex(event.key === "Home" ? options.findIndex((o) => !o.disabled) : options.findLastIndex((o) => !o.disabled));
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) openList();
      else if (activeIndex >= 0 && !options[activeIndex].disabled) choose(options[activeIndex].value);
    } else if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
      const query = event.key.toLocaleLowerCase();
      const found = options.findIndex((option) => !option.disabled && option.label.toLocaleLowerCase().startsWith(query));
      if (found >= 0) {
        event.preventDefault();
        if (!open) openList();
        setActiveIndex(found);
      }
    }
  };

  const hiddenSelect = (
    <select
      {...nativeProps}
      id={selectId + "-native"}
      ref={(node) => {
        nativeRef.current = node;
        setRef(forwardedRef, node);
      }}
      data-aven-control-inner=""
      data-aven-native-select=""
      className={multiple ? cx(styles.select, className) : styles.selectNative}
      name={name}
      required={required}
      disabled={disabled}
      multiple={multiple}
      value={value}
      defaultValue={defaultValue}
      onChange={onChange}
      tabIndex={multiple ? nativeProps.tabIndex : -1}
      aria-hidden={multiple ? undefined : true}
      aria-describedby={multiple ? describedBy : undefined}
      aria-label={multiple ? ariaLabel : undefined}
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}
    </select>
  );

  const control = (
    <div
      ref={shellRef}
      className={styles.selectShell}
      data-aven-select=""
      data-size={controlSize}
      data-multiple={multiple || undefined}
      data-disabled={disabled || readonly || undefined}
      data-error={Boolean(error) || undefined}
      data-open={open || undefined}
    >
      {multiple ? hiddenSelect : (
        <>
          <button
            id={selectId}
            ref={triggerRef}
            type="button"
            className={cx(styles.selectTrigger, className)}
            disabled={disabled}
            aria-label={ariaLabel}
            aria-labelledby={labelledBy}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            aria-required={required || undefined}
            aria-readonly={readonly || undefined}
            aria-haspopup="listbox"
            role="combobox"
            aria-expanded={open}
            aria-controls={open ? listId : undefined}
            aria-activedescendant={open && activeIndex >= 0 ? listId + "-option-" + activeIndex : undefined}
            onClick={() => open ? setOpen(false) : openList()}
            onKeyDown={handleKeyDown}
            onBlur={(event) => {
              if (!panelRef.current?.contains(event.relatedTarget as Node)) setOpen(false);
            }}
          >
            <span className={cx(styles.selectValue, !selectedOption && styles.selectPlaceholder)}>
              {selectedOption?.label ?? placeholder ?? ""}
            </span>
            <ChevronDown className={styles.selectChevron} {...iconDefaults} aria-hidden="true" />
          </button>
          {hiddenSelect}
        </>
      )}
    </div>
  );

  return (
    <>
      {bare ? control : (
        <Field>
          {label && <FieldLabel id={labelId} htmlFor={selectId}>{label}</FieldLabel>}
          {control}
          {helperText && <FieldDescription id={helperId}>{helperText}</FieldDescription>}
          {error && <FieldError id={errorId}>{error}</FieldError>}
        </Field>
      )}
      {!multiple && open && mounted && createPortal(
        <div
          id={listId}
          ref={panelRef}
          role="listbox"
          aria-label={ariaLabel ?? (typeof label === "string" ? label : undefined)}
          aria-labelledby={labelledBy ?? selectId}
          className={styles.selectPopover}
          data-side={position?.side}
          data-positioned={Boolean(position)}
          style={position ? {
            top: position.top,
            left: position.left,
            minInlineSize: Math.min(position.minInlineSize, window.visualViewport?.width ?? window.innerWidth),
            maxBlockSize: position.maxBlockSize,
          } : undefined}
        >
          {options.map((option, index) => (
            <button
              key={option.value}
              id={listId + "-option-" + index}
              type="button"
              role="option"
              tabIndex={-1}
              aria-selected={currentValue === option.value}
              disabled={option.disabled}
              className={styles.selectOption}
              data-active={activeIndex === index || undefined}
              onPointerMove={() => !option.disabled && setActiveIndex(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(option.value)}
            >
              <span className={styles.selectOptionLabel}>{option.label}</span>
              {currentValue === option.value && <Check className={styles.selectCheck} {...iconDefaults} aria-hidden="true" />}
            </button>
          ))}
        </div>,
        triggerRef.current?.closest("dialog[open]") ?? document.body,
      )}
    </>
  );
});
