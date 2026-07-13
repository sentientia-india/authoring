# Five-minute MCP quickstart

## Hosted connection

Obtain the production HTTPS endpoint and private license key from the account
owner, then run:

```bash
claude mcp add --transport http samrat-course https://YOUR_DOMAIN/mcp \
  --header "Authorization: Bearer YOUR_LICENSE_KEY"
```

Do not place a license key in prompts, source documents, screenshots, or course
content. The endpoint must use HTTPS.

## Verify

Ask the connected client: `List the Samrat course templates.` A successful
response proves transport, authorization, and tool discovery without mutating a
course.

## Create

Attach one source and ask: `Create a 15-minute course for new managers using
this source.` Review and approve the proposed outline, then request SCORM 1.2 or
SCORM 2004 export.

Connection and verification should take less than five minutes. Generation time
depends on source length, human review, and media requirements.
