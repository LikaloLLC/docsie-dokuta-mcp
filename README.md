# Docsie Video-to-Docs MCP Server

Remote MCP server for [Anthropic's Connectors Directory](https://claude.ai/customize/connectors). Converts videos into structured documentation using Dokuta AI.

## What It Does

Users on Claude can:
1. Submit a video URL (YouTube, Loom, Vimeo, direct MP4, etc.)
2. Choose a doc type (user guide, SOP, product docs, policy, blog)
3. Get structured markdown documentation back

**Free tier**: Videos up to 5 minutes are processed free. Longer videos require a Docsie account with AI credits.

## Architecture

```
Claude → POST https://mcp.docsie.io/mcp (Bearer token)
              │
              ├─→ Docsie /o2/ (OAuth2 token validation)
              ├─→ Dokuta API (video analysis)
              └─→ Docsie /api/internal/mcp/ (credit deduction)
```

- **Transport**: Streamable HTTP (MCP spec)
- **Auth**: OAuth2 Authorization Code + PKCE via Docsie's `/o2/` provider
- **Runtime**: Python 3.12 + FastMCP + Starlette + uvicorn

## MCP Tools

| Tool | Description |
|------|-------------|
| `analyze_video` | Submit a video URL for documentation generation |
| `check_job_status` | Poll for progress and retrieve completed results |
| `list_doc_types` | List available doc types and quality tiers |

## Local Development

```bash
cd mcp-server

# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your Dokuta API key and Docsie internal URL

# Run
uvicorn app.main:app --reload --port 8000
```

### Test endpoints

```bash
# Health check
curl http://localhost:8000/health

# OAuth metadata
curl http://localhost:8000/.well-known/oauth-authorization-server

# MCP tool listing (via MCP protocol)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_DOCSIE_BASE_URL` | Docsie public URL (for OAuth metadata) | `https://app.docsie.io` |
| `MCP_DOCSIE_INTERNAL_URL` | Docsie internal URL (for API calls) | `http://docsie-web:8080` |
| `MCP_DOKUTA_API_URL` | Dokuta video analysis API | `https://app.videodokuta.com/api/v1` |
| `MCP_DOKUTA_API_KEY` | Dokuta API key | (required) |
| `MCP_MCP_INTERNAL_API_KEY` | Shared secret for Django internal endpoints | (required) |
| `MCP_OAUTH2_CLIENT_ID` | OAuth2 client ID for the MCP app | (required) |
| `MCP_FREE_TIER_MAX_SECONDS` | Max free video duration in seconds | `300` |

## Deployment (Hetzner K3s)

```bash
# Build and push Docker image
docker build -t registry.docsie.io/docsie-mcp:latest .
docker push registry.docsie.io/docsie-mcp:latest

# Deploy with Helm
helm upgrade --install docsie-mcp helm/docsie-mcp/ \
  --set secretEnv.MCP_DOKUTA_API_KEY=$DOKUTA_API_KEY \
  --set secretEnv.MCP_MCP_INTERNAL_API_KEY=$MCP_INTERNAL_KEY
```

## Django Side Setup

### 1. Add internal API key to Django settings

In your `.env` or environment:
```
MCP_INTERNAL_API_KEY=your-shared-secret-here
```

### 2. Register OAuth2 Application

In Django admin at `/o2/applications/register/`:
- **Name**: Claude MCP Connector
- **Client type**: Public
- **Authorization grant type**: Authorization code
- **Redirect URIs**: (provided by Anthropic during directory registration)
- **Skip authorization**: Yes

### 3. Internal endpoints (already wired)

- `GET /api/internal/mcp/user-context/` — token validation + user info
- `POST /api/internal/mcp/deduct-credits/` — credit deduction

## Anthropic Connectors Directory Submission

To submit to the directory, you'll need:

1. **MCP Server URL**: `https://mcp.docsie.io/mcp`
2. **OAuth2 metadata URL**: `https://mcp.docsie.io/.well-known/oauth-authorization-server`
3. **Company name**: Docsie / Likalo Inc.
4. **Description**: "Convert videos into structured documentation using AI. Submit a video URL and get back a user guide, SOP, product docs, or blog post."
5. **Logo**: Docsie logo (SVG/PNG)
6. **Privacy policy**: https://www.docsie.io/privacy-policy/
7. **Terms of service**: https://www.docsie.io/terms-of-service/

Submit at: https://forms.gle/... (Anthropic's MCP Directory Submission Form)
