/** Present the exact decimal string, without converting persisted money to Number. */
export function formatAwsPrice(value, locale = "pt-BR") {
  const match = typeof value === "string" ? /^(\d+)(?:\.(\d{1,8}))?$/.exec(value) : null;
  if (!match) return "—";
  const fraction = (match[2] ?? "").padEnd(Math.max(2, match[2]?.length ?? 0), "0");
  try {
    const integer = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 0,
      useGrouping: true,
    }).format(BigInt(match[1]));
    // Intl determines only the locale's separators and placement of USD.
    // The *stored monetary amount* never passes through floating-point.
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).formatToParts(0).map((part) => {
      if (part.type === "integer") return integer;
      if (part.type === "fraction") return fraction;
      return part.value;
    }).join("");
  } catch {
    return value + " USD";
  }
}
