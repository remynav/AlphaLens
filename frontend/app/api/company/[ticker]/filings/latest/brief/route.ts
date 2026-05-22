import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.ALPHALENS_API_BASE_URL ?? "http://localhost:8000";

type RouteContext = {
  params: Promise<{ ticker: string }>;
};

export async function GET(_request: NextRequest, context: RouteContext) {
  const { ticker } = await context.params;
  const url = API_BASE_URL + "/company/" + encodeURIComponent(ticker) + "/filings/latest/brief";

  try {
    const response = await fetch(url, { cache: "no-store" });
    const body = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { detail: body?.detail ?? "Unable to generate investor brief." },
        { status: response.status },
      );
    }

    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ detail: "Backend API is unavailable." }, { status: 502 });
  }
}
