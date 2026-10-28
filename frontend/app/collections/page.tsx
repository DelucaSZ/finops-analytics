import { Suspense } from "react";
import { DataState } from "@/components/aven";
import { CollectionWorkspace } from "@/components/collection-workspace";
import { ManualCollectionLauncher } from "@/components/manual-collection-launcher";

export default function CollectionsPage() {
  return (
    <div style={{ position: "relative" }}>
      <ManualCollectionLauncher />
      <Suspense fallback={<DataState loading>{null}</DataState>}>
        <CollectionWorkspace />
      </Suspense>
    </div>
  );
}
