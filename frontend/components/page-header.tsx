import type { ReactNode } from "react";
import { PageHeader as AvenPageHeader } from "@/components/aven";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <AvenPageHeader
      title={title}
      description={description}
      metadata={eyebrow}
      actions={actions}
    />
  );
}
