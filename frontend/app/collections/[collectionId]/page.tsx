"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { DataState } from "@/components/aven";
import { CollectionWorkspace } from "@/components/collection-workspace";

export default function CollectionPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  return (
    <Suspense fallback={<DataState loading>{null}</DataState>}>
      <CollectionWorkspace collectionId={collectionId} />
    </Suspense>
  );
}
