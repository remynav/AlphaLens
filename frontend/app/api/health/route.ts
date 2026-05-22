import { NextResponse } from "next/server";

const API_BASE_URL = process.env.ALPHALENS_API_BASE_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(API_BASE_URL + "/health", { cache: "no-store" });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Backend API is unavailable." }, { status: 502 });
  }
}
