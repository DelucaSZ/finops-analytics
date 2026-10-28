import { Suspense } from "react";
import { CollectionWorkspace } from "@/components/collection-workspace";
import { ManualCollectionLauncher } from "@/components/manual-collection-launcher";
import { Skeleton } from "@/components/ui";

function ReportsFallback() {
  return (
    <div aria-label="Carregando relatórios" role="status">
      <Skeleton />
      <Skeleton />
      <Skeleton />
    </div>
  );
}

export default function CollectionsPage() {
  return (
    <Suspense fallback={<ReportsFallback />}>
      <CollectionWorkspace headerAction={<ManualCollectionLauncher />} />
    </Suspense>
  );
}
