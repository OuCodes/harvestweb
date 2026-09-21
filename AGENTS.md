## Browser routing — operator correction, September 21, 2026

Read `/Users/agent/code/ops/ouattribution/docs/operator-agent-bootstrap.md`
and `/Users/agent/AGENTS.md` before browser work. These are the canonical rules;
this dated correction supersedes older MCP-only or mandatory-Playwright wording.

- Keep established direct APIs/CLIs first. For interactive browsing, prefer the
  existing authenticated native Chrome route or the task's established direct
  browser connector. Preserve brand-specific profiles and connector ownership.
- MCP is optional, not a prerequisite. Routine navigation/read-only inspection
  on the existing shared Chrome connection has standing permission; do not add
  another conversational approval gate. Runtime/tool/OS approvals still apply.
- Verify page/account identity and preserve unsaved work. Do not create another
  browser profile, debugging service, credential copy or login flow.
- Preserve business-write approvals and genuine denials. An MCP error alone is
  not proof of logout or that native access failed; diagnose the actual cause.
  Never reroute a denied action or weaken security settings to make it succeed.
