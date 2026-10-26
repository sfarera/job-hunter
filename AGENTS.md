# Agent Guidelines & Tool Policies

## LinkedIn MCP Tools
- **Auto-Approve All General Actions**: All LinkedIn tools (reading profiles, searching jobs/companies/recruiters, modifying profile sections, adding skills, sending connection invites, creating posts) are pre-approved and must be invoked directly without prompting the user for approval.
- **Strict User Review for Direct Messages (DMs)**:
  - Tools: `send_dm` and `reply_in_dm`
  - Explicit confirmation is mandatory before executing these tools.
  - Always display the recipient's name/profile, context, and draft message text to the user, and ask for their confirmation before calling `send_dm` or `reply_in_dm`.
