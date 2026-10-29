// The viewer without a server (ADR 0022): a static site carries every answer in one
// snapshot.json, keyed the way server/snapshot.py keys them - the endpoint and its
// parameters sorted by name, unencoded, so Python and the browser agree.

export function snapshotKey(path) {
  const [endpoint, query = ""] = path.replace(/^\/api\//, "").split("?");
  const params = [...new URLSearchParams(query)].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return params.length ? `${endpoint}?${params.map(([k, v]) => `${k}=${v}`).join("&")}` : endpoint;
}

export function answerFrom(answers, path) {
  const key = snapshotKey(path);
  if (!Object.hasOwn(answers, key)) throw new Error(`${key} is not part of this demo`);
  return answers[key];
}
