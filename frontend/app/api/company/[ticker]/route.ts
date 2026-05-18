import { NextResponse } from "next/server";

const API_BASE_URL = process.env.ALPHALENS_API_BASE_URL ?? "http://localhost:8000";

type RouteContext = {
  params: Promise<{
    ticker: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { ticker } = await context.params;
  const upstreamUrl = API_BASE_URL + "/company/" + encodeURIComponent(ticker);

  try {
    const response = await fetch(upstreamUrl, {
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);

    if (!response.ok) {
      return NextResponse.json(
        { detail: body?.detail ?? "Unable to load company data." },
        { status: response.status },
      );
    }

    return NextResponse.json(body);
  } catch {
    return NextResponse.json(
      {
        detail:
          "Backend API is not reachable. Start FastAPI on port 8000, or set ALPHALENS_API_BASE_URL for the frontend server.",
      },
      { status: 502 },
    );
  }
}
