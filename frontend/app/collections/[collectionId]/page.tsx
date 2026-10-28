"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CollectionWorkspace } from "@/components/collection-workspace";
import { Skeleton } from "@/components/ui";

export default function CollectionPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  return (
    <Suspense fallback={<div aria-label="Carregando relatório" role="status"><Skeleton /><Skeleton /><Skeleton /></div>}>
      <CollectionWorkspace collectionId={collectionId} />
    </Suspense>
  );
}
