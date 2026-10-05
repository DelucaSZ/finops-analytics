import { Suspense } from "react";
import { CollectionWorkspace } from "@/components/collection-workspace";
import { ManualCollectionLauncher } from "@/components/manual-collection-launcher";

export default function CollectionsPage() {
  return (
    <div style={{ position: "relative" }}>
      <ManualCollectionLauncher />
      <Suspense fallback={<p role="status">Carregando coletas…</p>}>
        <CollectionWorkspace />
      </Suspense>
    </div>
  );
}
