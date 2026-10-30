import { Suspense } from "react";
import { DataState } from "@/components/aven";
import { CollectionWorkspace } from "@/components/collection-workspace";
import { ManualCollectionLauncher } from "@/components/manual-collection-launcher";
import styles from "./collections.module.css";

export default function CollectionsPage() {
  return (
    <div className={styles.page}>
      <ManualCollectionLauncher />
      <Suspense fallback={<DataState loading>{null}</DataState>}>
        <CollectionWorkspace />
      </Suspense>
    </div>
  );
}
