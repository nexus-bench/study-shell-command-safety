# Claude subscription configuration

Claude now has a separate subscription launcher: `claude_subscription_job.py`.
Model: `claude-opus-5-5`. Authentication: existing Claude Code Pro login
in macOS Keychain, loaded only at launch. API credentials are not loaded or used
as a fallback. The SDK receives a placeholder OAuth token; the privileged relay
adds the real access token. Refresh tokens remain on the host.

The benchmark remains stopped. No inference or VM launch was performed for this
configuration change. After explicit authorization to resume, the launcher
requires `--execute`, validates the prior archive/shutdown, runs four development
pilots, and only then runs a separate 360-episode Claude collection. Existing API
results remain unchanged. A failed or incomplete pilot blocks collection;
attempted episodes are never silently retried. Token expiry stops before the
next episode; refresh the native Claude login before a later explicit resume.

The original frozen launcher still reproduces the original API study. Use the
subscription launcher for future Claude subscription collection. Record any
choice to resume only missing cases separately rather than mixing billing routes
without an amendment.

Local orchestration tests cover Claude-only selection, no automatic retries,
OAuth header replacement, and stopping on service errors or imminent expiry.
Live subscription SDK/relay compatibility passed all four smoke cases on 2026-10-03 (run claude-subscription-smoke-20261003-051044). The VM was stopped afterward; the full benchmark remains stopped.

Amendment and status: `study-results/claude-subscription-v1/`.
Anthropic subscription policy:
https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
