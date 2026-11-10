import {notFound} from "next/navigation";

/** Task 24 UI laboratory is not a user-facing production route. */
export default function DevUiLayout({children}: Readonly<{children: React.ReactNode}>) {
  if (process.env.NODE_ENV === "production") notFound();
  return children;
}
