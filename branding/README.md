# Branding

Place your custom branding assets in this directory. They are mounted into the OpenWebUI container to replace default logos and favicons.

## Required Files

| File | Purpose | Recommended Size |
|------|---------|-----------------|
| `favicon.ico` | Browser tab icon | 32x32 or 48x48 |
| `favicon.svg` | SVG favicon (modern browsers) | Any |
| `apple-touch-icon.png` | iOS home screen icon | 180x180 |
| `chat.svg` | Main app logo (top-left) | Any |
| `logo.png` | Sidebar logo and splash screen | 512x512 |

## Model Icons (Optional)

Upload model-specific icons via **Admin Panel > Workspace > Models > Edit > Avatar Photo**.

Place source files in `static/images/` if you want to track them:

| File | Purpose |
|------|---------|
| `static/images/claude-icon.png` | Avatar for Claude models |
| `static/images/openai-icon.png` | Avatar for GPT models |
| `static/images/gemini-icon.png` | Avatar for Gemini models |

## Enabling Branding

After placing your files, uncomment the branding volume mounts in `docker-compose.yml` under the `openwebui` service, then restart:

```bash
docker compose restart openwebui
```

## Dashboard Branding

To change the dashboard accent color, edit the Tailwind config in `dashboard/templates/index.html`:

```javascript
colors: {
    brand: { DEFAULT: '#2563EB', dark: '#1D4ED8' },
},
```

Replace `#2563EB` and `#1D4ED8` with your organization's primary and dark-hover colors.
