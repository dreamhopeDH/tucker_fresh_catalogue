import { jsonResponse } from "../_shared/personal.ts";

export const onRequest: PagesFunction = async (context) => {
  try {
    const response = await context.next();
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "no-store");
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  } catch {
    return jsonResponse({ error: "Personal service is temporarily unavailable" }, { status: 500 });
  }
};
