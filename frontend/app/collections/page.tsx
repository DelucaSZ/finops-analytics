import { Suspense } from "react";
import { CollectionWorkspace } from "@/components/collection-workspace";

export default function CollectionsPage() {
  return (
    <Suspense fallback={<p role="status">Carregando coletas…</p>}>
      <CollectionWorkspace />
    </Suspense>
  );
}
