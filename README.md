# cloud-tc

Terminal client for **OnlySq Cloud 2.0** (`https://cloud.onlysq.ru`). Talks to the public v2 REST API — no Telegram, no Postgres on your machine, just `httpx` + `typer` + `rich`.

## Install

From PyPI (when published):

```bash
pip install cloud-tc
```

Straight from git:

```bash
pip install git+https://github.com/xOnlySq/cloud-tc.git
```

Or for a local checkout (with `-e` for editable):

```bash
git clone https://github.com/xOnlySq/cloud-tc.git
cd cloud-tc
pip install -e .
```

Both `tc` and `cloud-tc` console scripts are installed.

## Quick start

1. Create an API token in the web UI: `https://cloud.onlysq.ru/v2/ui/settings` → "new token".
2. Log in locally:

   ```bash
   tc login --token tck_xxxxxxxxxxxxxxxxxxxx
   ```

   The token is stored in `~/.cloud-tc/config.json` (0600).

3. Use it:

   ```bash
   tc me
   tc quota
   tc ls
   tc upload ./photo.jpg
   tc share <uid> --role viewer
   ```

## Commands

| Command | Description |
|---|---|
| `tc login --token tck_…` | Save and verify an API token |
| `tc logout` | Remove local config |
| `tc info` | Show local config |
| `tc version` | Print package version |
| `tc me` | Show current user profile |
| `tc quota` | Show used / total quota |
| `tc ls [FOLDER_ID]` | List files |
| `tc upload PATH [-f FOLDER]` | Upload a local file |
| `tc download UID [-o PATH]` | Download a file |
| `tc rm UID` | Move to trash |
| `tc restore UID` | Restore from trash |
| `tc mv UID FOLDER_ID` | Move file to another folder |
| `tc rename UID NEW_NAME` | Rename |
| `tc mkdir NAME [-p PARENT_ID]` | Create folder |
| `tc share UID [-r ROLE] [--password] [--expires] [--max-uses]` | Create a share link |
| `tc tokens list / create NAME / revoke ID` | Manage API tokens |
| `tc migrate-self LEGACY_TOKEN` | Move a legacy account to v2 (no auth required) |

## Configuration

You can override the server with environment variables (useful for self-hosted instances):

```bash
export TC_BASE_URL="https://cloud.example.com"
export TC_TOKEN="tck_..."
tc ls
```

`TC_TOKEN` overrides the saved token if set. `TC_BASE_URL` overrides the configured base URL.

Config file: `~/.cloud-tc/config.json` — just `{ "token": "...", "base_url": "..." }`.

## Examples

Upload everything from a directory into a folder:

```bash
for f in *.jpg; do tc upload "$f" -f 42; done
```

Pipe a file through `tc upload` (Linux):

```bash
tc upload /dev/stdin <<< "hello"   # named pipe trick, see issues for binary
```

Quick public link for a file:

```bash
UID=$(tc upload ./report.pdf | awk '{print $2}')
tc share "$UID" --role viewer
```

Batch-migrate one legacy token from any script:

```bash
tc migrate-self USERS_LEGACY_TOKEN
```

## License

MIT. See [LICENSE](LICENSE).

## Related

- Cloud UI: <https://cloud.onlysq.ru>
- REST API docs: <https://cloud.onlysq.ru/docs> (see "Cloud 2.0" group)
- Service / issues: <https://github.com/xOnlySq/cloud-tc/issues>
