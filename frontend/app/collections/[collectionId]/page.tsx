"use client";
import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CollectionWorkspace } from "@/components/collection-workspace";

export default function CollectionPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  return (
    <Suspense fallback={<p role="status">Carregando coleta…</p>}>
      <CollectionWorkspace collectionId={collectionId} />
    </Suspense>
  );
}
