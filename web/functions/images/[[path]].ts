import { AwsClient } from "aws4fetch";

interface Env {
  B2_ENDPOINT: string;
  B2_BUCKET: string;
  B2_READ_KEY_ID: string;
  B2_READ_APPLICATION_KEY: string;
}

const IMMUTABLE_CACHE = "public, max-age=31536000, immutable";

export function normalizeObjectKey(path: string | string[] | undefined): string | null {
  const rawSegments = Array.isArray(path) ? path : path ? path.split("/") : [];
  const segments: string[] = [];

  for (const rawSegment of rawSegments) {
    let segment: string;
    try {
      segment = decodeURIComponent(rawSegment);
    } catch {
      return null;
    }
    if (
      !segment ||
      segment === "." ||
      segment === ".." ||
      segment.includes("/") ||
      segment.includes("\\") ||
      /[\u0000-\u001f\u007f]/.test(segment)
    ) {
      return null;
    }
    segments.push(segment);
  }

  const key = segments.join("/");
  if (segments.length < 4 || segments[0] !== "test" || segments[1] !== "products") {
    return null;
  }
  return key.endsWith(".webp") ? key : null;
}

export function buildB2Target(
  endpoint: string,
  bucket: string,
  objectKey: string,
): { url: string; region: string } | null {
  let url: URL;
  try {
    url = new URL(endpoint);
  } catch {
    return null;
  }
  const regionMatch = /^s3[.-]([a-z0-9-]+)\.backblazeb2\.com$/i.exec(url.hostname);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    !regionMatch ||
    !bucket ||
    bucket.includes("/") ||
    bucket.includes("\\") ||
    /[\u0000-\u001f\u007f]/.test(bucket)
  ) {
    return null;
  }

  const encodedKey = objectKey.split("/").map(encodeURIComponent).join("/");
  url.pathname = `/${encodeURIComponent(bucket)}/${encodedKey}`;
  return { url: url.toString(), region: regionMatch[1] };
}

export const onRequest: PagesFunction<Env, "path"> = async (context) => {
  if (context.request.method !== "GET") {
    return new Response("Method not allowed", {
      status: 405,
      headers: { Allow: "GET" },
    });
  }

  const objectKey = normalizeObjectKey(context.params.path);
  if (!objectKey) {
    return new Response("Invalid image path", { status: 400 });
  }

  const cacheUrl = new URL(context.request.url);
  cacheUrl.search = "";
  const cacheKey = new Request(cacheUrl.toString(), { method: "GET" });
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  const target = buildB2Target(context.env.B2_ENDPOINT, context.env.B2_BUCKET, objectKey);
  if (
    !target ||
    !context.env.B2_READ_KEY_ID ||
    !context.env.B2_READ_APPLICATION_KEY
  ) {
    return new Response("Image service is not configured", { status: 500 });
  }

  try {
    const client = new AwsClient({
      accessKeyId: context.env.B2_READ_KEY_ID,
      secretAccessKey: context.env.B2_READ_APPLICATION_KEY,
      service: "s3",
      region: target.region,
      retries: 1,
    });
    const upstream = await client.fetch(target.url, { method: "GET" });
    if (upstream.status === 404) {
      return new Response("Image not found", { status: 404 });
    }
    if (!upstream.ok || !upstream.body) {
      return new Response("Image storage request failed", { status: 502 });
    }

    const headers = new Headers({
      "Content-Type": "image/webp",
      "Cache-Control": IMMUTABLE_CACHE,
    });
    for (const name of ["Content-Length", "ETag", "Last-Modified"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    const response = new Response(upstream.body, { status: 200, headers });
    context.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  } catch {
    return new Response("Image storage request failed", { status: 502 });
  }
};
