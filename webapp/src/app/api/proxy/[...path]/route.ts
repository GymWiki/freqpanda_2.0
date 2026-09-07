/**
 * Same-origin proxy to the phase-5 backend. The browser only ever talks to
 * `/api/proxy/*`; this route attaches the real API key server-side
 * (`BACKEND_API_KEY`, never exposed to the client) and forwards to
 * `${BACKEND_API_URL}/api/v1/*`. That keeps the key out of the bundle and
 * out of the browser's network tab, and leaves room for a future
 * multi-user login to sit in front of this same proxy (check a session
 * cookie here, forward per-user credentials) without the client code
 * changing at all.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_API_URL;
const BACKEND_KEY = process.env.BACKEND_API_KEY;

async function forward(req: NextRequest, path: string[]): Promise<NextResponse> {
  if (!BACKEND_URL || !BACKEND_KEY) {
    return NextResponse.json(
      { detail: "Server is missing BACKEND_API_URL / BACKEND_API_KEY configuration." },
      { status: 500 },
    );
  }

  const targetUrl = new URL(`/api/v1/${path.join("/")}`, BACKEND_URL);
  targetUrl.search = req.nextUrl.search;

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.text() : undefined;

  const upstream = await fetch(targetUrl, {
    method: req.method,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": BACKEND_KEY,
    },
    body,
    cache: "no-store",
  });

  const responseBody = await upstream.text();
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

type RouteParams = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, { params }: RouteParams) {
  return forward(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: RouteParams) {
  return forward(req, (await params).path);
}
export async function PUT(req: NextRequest, { params }: RouteParams) {
  return forward(req, (await params).path);
}
export async function DELETE(req: NextRequest, { params }: RouteParams) {
  return forward(req, (await params).path);
}
