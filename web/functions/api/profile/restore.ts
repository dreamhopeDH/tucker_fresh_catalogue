import {
  findProfile,
  jsonResponse,
  profileCookie,
  profileState,
  readJson,
  validSyncCode,
  type PersonalEnv,
} from "../../_shared/personal.ts";

export const onRequestPost: PagesFunction<PersonalEnv> = async (context) => {
  const request = context.request;
  const db = context.env.PERSONAL_DB;
  let body: unknown;
  try { body = await readJson(request); }
  catch { return jsonResponse({ error: "Invalid request body" }, { status: 400 }); }
  const syncCode = body && typeof body === "object"
    ? (body as Record<string, unknown>).sync_code
    : null;
  if (!validSyncCode(syncCode)) {
    return jsonResponse({ error: "Invalid Sync Code" }, { status: 404 });
  }
  const profile = await findProfile(db, syncCode);
  if (!profile) return jsonResponse({ error: "Invalid Sync Code" }, { status: 404 });
  return jsonResponse(await profileState(db, profile), {
    headers: { "Set-Cookie": profileCookie(syncCode) },
  });
};
