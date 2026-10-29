import { NextResponse } from "next/server";

const buildSha = process.env.NEXT_PUBLIC_BUILD_SHA?.trim() || "unversioned";

export const dynamic = "force-static";

export function GET() {
  return NextResponse.json(
    { buildSha },
    {
      headers: {
        "Cache-Control": "public, max-age=0, must-revalidate",
      },
    },
  );
}
