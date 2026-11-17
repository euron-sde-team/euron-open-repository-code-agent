/** Ready-to-run examples for an API key. They are shown in the UI and must work as written. */

export function curlExample(apiUrl: string, workspace: string, key: string): string {
  return [
    `curl -s "${apiUrl}/api/v1/workspaces/${workspace}/search/symbols?q=Invoice" \\`,
    `  -H "Authorization: Bearer ${key}"`,
  ].join("\n");
}

export function askExample(apiUrl: string, workspace: string, key: string): string {
  return [
    `curl -s "${apiUrl}/api/v1/workspaces/${workspace}/ask" \\`,
    `  -H "Authorization: Bearer ${key}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"question": "Where is the tax for an invoice calculated?"}'`,
  ].join("\n");
}
