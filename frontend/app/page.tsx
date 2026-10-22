"use client";

import { Suspense } from "react";
import {
  DashboardBoot,
  ExecutiveDashboard,
} from "@/components/executive-dashboard";

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardBoot />}>
      <ExecutiveDashboard />
    </Suspense>
  );
}
