import {
  findProfile,
  generateSyncCode,
  jsonResponse,
  noProfileState,
  profileCookie,
  profileState,
  readJson,
  syncCodeFromRequest,
  validateDurableState,
  type PersonalEnv,
} from "../../_shared/personal.ts";

export const onRequestGet: PagesFunction<PersonalEnv> = async (context) => {
  const profile = await findProfile(
    context.env.PERSONAL_DB,
    syncCodeFromRequest(context.request),
  );
  return jsonResponse(
    profile ? await profileState(context.env.PERSONAL_DB, profile) : noProfileState(),
  );
};

export const onRequestPut: PagesFunction<PersonalEnv> = async (context) => {
  const request = context.request;
  const db = context.env.PERSONAL_DB;
  let input: ReturnType<typeof validateDurableState>;
  try {
    input = validateDurableState(await readJson(request));
  } catch {
    return jsonResponse({ error: "Invalid request body" }, { status: 400 });
  }
  if (!input) return jsonResponse({ error: "Invalid personal state" }, { status: 400 });

  let syncCode = syncCodeFromRequest(request);
  let profile = await findProfile(db, syncCode);
  let setCookie: string | null = null;
  const now = new Date().toISOString();
  const statements: D1PreparedStatement[] = [];
  if (!profile) {
    syncCode = generateSyncCode();
    statements.push(db.prepare(
      "INSERT INTO profiles (sync_code, history_enabled, customization_json, created_at, updated_at) VALUES (?, 0, ?, ?, ?)",
    ).bind(syncCode, JSON.stringify(input.customizations), now, now));
    setCookie = profileCookie(syncCode);
  } else {
    statements.push(db.prepare(
      "UPDATE profiles SET customization_json = ?, updated_at = ? WHERE id = ?",
    ).bind(JSON.stringify(input.customizations), now, profile.id));
  }
  const profileSelector = profile ? "?" : "(SELECT id FROM profiles WHERE sync_code = ?)";
  const profileParameter = profile ? profile.id : syncCode;
  statements.push(
    db.prepare(`DELETE FROM profile_favourites WHERE profile_id = ${profileSelector}`).bind(profileParameter),
    db.prepare(
      `INSERT INTO profile_favourites (profile_id, product_id) `
      + `SELECT ${profileSelector}, value FROM json_each(?)`,
    ).bind(profileParameter, JSON.stringify(input.favourites)),
  );
  await db.batch(statements);
  profile = await findProfile(db, syncCode);
  if (!profile) return jsonResponse({ error: "Personal state could not be saved" }, { status: 500 });
  const headers = setCookie ? { "Set-Cookie": setCookie } : undefined;
  return jsonResponse(await profileState(db, profile), { headers });
};
