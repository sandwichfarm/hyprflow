# Website & deployment

The landing page uses Vite; this documentation suite uses VitePress. Both import the copper and mint palette in `website/shared/palette.css`. The composition follows [hyprlax.com](https://hyprlax.com): centered monospace branding, a large real demo, a command block, project links, and a compact feature grid.

## Local development

Install **Node.js 22.12+** (CI uses Node 24) and npm. From the repository root:

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:5173/** for the landing page and **http://127.0.0.1:5173/docs/** for documentation. Vite proxies `/docs` to VitePress on port 5174, including WebSocket traffic for hot reload. Both servers stop when the parent command exits. Ports 5173 and 5174 must be free.

Edit `website/index.html` or `website/src/` for the landing page; edit `docs/*.md` for documentation. Preparation scripts copy the existing demo media and reference images into ignored public asset directories for both dev and production. Existing design and verification documents are included in the site. Evidence outside `docs/` links to its GitHub source. The VitePress 1.x dependency uses a pinned Vite 6.4.4 override for patched development-server dependencies.

## Build and preview

```sh
npm test
npm run build
npm run preview
```

Preview the combined output at **http://127.0.0.1:4173/** and **http://127.0.0.1:4173/docs/**. The output is:

```text
dist/
  index.html
  assets/
  favicon.svg
  media/
  docs/
    index.html
    getting-started.html
    assets/
    ...
```

The full build cleans `dist/`, builds the landing page, then builds VitePress into `dist/docs/`. A final check validates local HTML links and the docs asset prefix. Documentation uses `.html` URLs so the CDN needs no extensionless route rewriting. `npm run build:site` cleans the entire output; always run the full build before deploying.

## Prepare Bunny

1. Create a dedicated Bunny Storage Zone and connect a Pull Zone to it. Use the storage zone's **primary region** hostname from its Access tab.
2. Leave **Block Root Path Access** disabled on the Pull Zone. The build supplies `index.html` at the root and `docs/index.html` for the documentation directory. Do not enable SPA fallback or HTML minification; the docs deliberately use `.html` page links.
3. Attach your hostname and enable HTTPS, or use the Pull Zone's HTTPS `b-cdn.net` hostname.
4. Note the storage zone name, storage password, Pull Zone numeric ID, and account API key. The storage password uploads files; the account key purges the CDN. These are separate credentials.

See Bunny's [HTTP storage documentation](https://docs.bunny.net/storage/http) for endpoint and credential details.

## Configure GitHub

The helper needs the [GitHub CLI](https://cli.github.com/) authenticated with repository administration access:

```sh
gh auth login
npm run setup:bunny -- --repo sandwichfarm/hyprflow
```

Each prompt explains what the value does, where to find it, and an example. Values are checked immediately: an invalid entry repeats only that prompt. The Storage API hostname is prompted too, with Frankfurt's endpoint as the default; use your zone's actual primary-region hostname.

The helper checks GitHub authentication before asking for credentials. It creates the `production` GitHub environment if needed, preserves existing protection rules, and saves these values:

| Kind | Name | What to enter and where to find it |
| --- | --- | --- |
| Variable | `BUNNY_STORAGE_ZONE` | Zone name, not ID. **Storage → your zone**; also the username under **Access / FTP & API Access**. |
| Variable | `BUNNY_STORAGE_HOST` | Upload hostname from **Storage → your zone → Access / FTP & API Access**. For example, `storage.bunnycdn.com` or `ny.storage.bunnycdn.com`. No scheme or path. |
| Variable | `BUNNY_PULL_ZONE_ID` | Numeric ID of the connected CDN Pull Zone. Open **CDN → your Pull Zone** and copy its numeric ID from the dashboard URL, not the Storage Zone ID. |
| Variable | `BUNNY_PUBLIC_URL` | The website address visitors will open. Under **CDN → your Pull Zone → General → Hostnames**, use the default `your-zone.b-cdn.net` hostname or an HTTPS custom domain you connected. |
| Secret | `BUNNY_STORAGE_PASSWORD` | Writable Storage Zone password under **Storage → your zone → Access / FTP & API Access**. Do not use the read-only password, login password, or account API key. |
| Secret | `BUNNY_API_KEY` | Account API key from **[Account → API Key](https://dash.bunny.net/account/api-key)**, used to purge the CDN cache. |

**`BUNNY_PUBLIC_URL` is our variable name, not a Bunny setting.** For example, enter `https://hyprflow-site.b-cdn.net` or your connected custom domain, such as `https://hyprflow.com`. It only sets the clickable website link on the GitHub deployment. It does not configure DNS or select the upload destination. A bare hostname is accepted interactively and gets `https://` added; omit `/docs` and other paths.

Secret prompts remain visible while typing is hidden. Paste the secret and press Enter; `Received (hidden).` confirms it was read. Ctrl+C or end-of-input cancels without changing GitHub settings during the prompt phase. Once saving starts, progress names each operation, and every GitHub command has a 30-second timeout. If saving fails partway through, previously saved values remain; rerun the helper to finish.

Read all prompt explanations without entering values or contacting GitHub:

```sh
npm run setup:bunny -- --help
```

All values can instead be supplied as exported environment variables for noninteractive use. Secrets go to `gh` over stdin and are never printed or written to disk. The helper does not source `.env` files. Use `--environment NAME` only with a corresponding workflow environment change.

Preview the setup without changing GitHub:

```sh
npm run setup:bunny -- --repo sandwichfarm/hyprflow --dry-run
```

No credentials are needed for this dry run. Missing values are shown as unconfigured. This script does not create Bunny resources or change DNS.

## GitHub workflows

- **Website checks** runs tests, a combined build, and a deployment dry run on pull requests and pushes to `main`. It saves `dist/` as an artifact.
- **Deploy website to Bunny** builds and verifies the same output, then uploads it after relevant pushes to `main` or a manual dispatch on `main`. It reads the `production` environment and allows one deployment at a time without canceling an active upload.

Pull requests never receive deployment secrets. After configuring the environment, use **Actions → Deploy website to Bunny → Run workflow** on `main` for the first deployment. Later relevant pushes to `main` deploy automatically.

## Manual deployment and rollback

```sh
npm run build
npm run deploy:dry-run
# With all six BUNNY_* settings exported:
npm run deploy
```

The uploader checks the combined build before networking, uploads assets before HTML, includes SHA-256 checksums, and requests a Pull Zone cache purge only after every upload succeeds. Network errors, HTTP 429, and server errors retry up to three attempts. Other failures stop immediately with a nonzero exit code. Credentials are sent only to validated Bunny endpoints; redirects are rejected.

Uploads retain old files so cached pages can still fetch their previous hashed assets. Deployment is not atomic: an interrupted upload can leave a partial release. Re-run the workflow to finish it, or check out the previous commit, build, and deploy again to restore its pages. Removed pages and old assets remain until explicitly cleaned up in Bunny Storage. Use a dedicated zone so retained content is easy to manage.

After the first deployment, verify the configured public URL, `/docs/`, a deep page such as `/docs/getting-started.html`, and docs search. Bunny provisioning and live delivery require your credentials; local tests and dry runs make no remote changes.
