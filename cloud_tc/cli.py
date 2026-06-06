from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from cloud_tc import __version__

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
    help="Terminal client for OnlySq Cloud 2.0",
)
console = Console()

CONFIG_DIR = Path(os.path.expanduser("~")) / ".cloud-tc"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_BASE = "https://cloud.onlysq.ru"


def _save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass


def _load() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _client(require_auth: bool = True) -> httpx.Client:
    cfg = _load()
    base = cfg.get("base_url") or os.environ.get("TC_BASE_URL") or DEFAULT_BASE
    token = cfg.get("token") or os.environ.get("TC_TOKEN")
    headers = {"User-Agent": f"cloud-tc/{__version__}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif require_auth:
        console.print("[red]no token configured[/] · run [bold]tc login --token tck_…[/]")
        raise typer.Exit(1)
    return httpx.Client(base_url=base, headers=headers, timeout=120.0, follow_redirects=False)


def _hsize(n) -> str:
    n = int(n or 0)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    if n >= 1024 ** 6:
        return "∞"
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    if i == 0:
        return f"{int(f)} {units[i]}"
    if i == 1:
        return f"{f:.1f} {units[i]}"
    return f"{f:.2f} {units[i]}"


def _fail_if_bad(r: httpx.Response, ctx: str = "") -> dict:
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if r.status_code >= 300 or (isinstance(data, dict) and data.get("ok") is False):
        msg = data.get("error") if isinstance(data, dict) else r.text
        console.print(f"[red]{ctx or 'error'}[/] HTTP {r.status_code} · {msg}")
        raise typer.Exit(1)
    return data


@app.command()
def version():
    console.print(f"cloud-tc [bold]{__version__}[/]")


@app.command()
def info():
    cfg = _load()
    console.print(f"[bold]cloud-tc[/] v{__version__}")
    console.print(f"  config: {CONFIG_FILE}")
    if cfg:
        console.print(f"  base_url = {cfg.get('base_url', DEFAULT_BASE)}")
        if cfg.get("token"):
            console.print(f"  token    = {cfg['token'][:14]}…")
    else:
        console.print("  [dim]not logged in[/]")


@app.command()
def login(
    token: str = typer.Option(..., "--token", "-t", help="API token (tck_…) — create one at /v2/ui/settings"),
    base_url: str = typer.Option(DEFAULT_BASE, "--base-url", "-u"),
):
    """Save an API token locally and verify it works."""
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as cli:
        r = cli.get("/v2/quota")
        if r.status_code != 200:
            console.print(f"[red]token rejected[/] HTTP {r.status_code} · {r.text}")
            raise typer.Exit(1)
        q = r.json()
    _save({"token": token, "base_url": base_url})
    console.print(
        f"[green]ok[/] logged in · used {_hsize(q['used_bytes'])} / "
        f"{_hsize(q['quota_bytes'])}"
    )


@app.command()
def logout():
    """Remove the local config."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    console.print("[green]ok[/] config removed")


@app.command()
def me():
    """Print the current user profile."""
    with _client() as cli:
        r = cli.get("/auth/me")
        data = _fail_if_bad(r, "me")
        u = data.get("user") or {}
        console.print(f"[bold]{u.get('name')}[/] · {u.get('email') or 'no email'}")
        console.print(f"  sauth_id: {u.get('sauth_id')}  level: {u.get('level')}{' · admin' if u.get('is_admin') else ''}")
        console.print(f"  storage:  {_hsize(u.get('used_bytes'))} / {_hsize(u.get('quota_bytes'))}")
        if u.get("has_legacy"):
            console.print(f"  legacy:   {'migrated' if u.get('migrated') else 'linked, not migrated'}")


@app.command()
def quota():
    """Show used / total quota."""
    with _client() as cli:
        r = cli.get("/v2/quota")
        q = _fail_if_bad(r, "quota")
        used = q["used_bytes"]
        total = q["quota_bytes"]
        pct = (used / max(1, total)) * 100
        if total >= 1024 ** 6:
            console.print(f"used [bold]{_hsize(used)}[/] / ∞ (unlimited tier)")
        else:
            console.print(f"used [bold]{_hsize(used)}[/] / {_hsize(total)} ([yellow]{pct:.1f}%[/])")


@app.command()
def ls(folder_id: Optional[int] = typer.Argument(None, help="folder id (omit for root)")):
    """List files in a folder."""
    with _client() as cli:
        q = f"?folder_id={folder_id}" if folder_id else "?root=1"
        r = cli.get(f"/v2/files{q}")
        data = _fail_if_bad(r, "list")
        files = data.get("files", [])
        if not files:
            console.print("[dim]empty[/]")
            return
        t = Table(show_lines=False, header_style="bold")
        t.add_column("UID", style="cyan", no_wrap=True)
        t.add_column("Name")
        t.add_column("Size", justify="right", style="dim")
        t.add_column("Mime", style="dim")
        t.add_column("Status", justify="center")
        for f in files:
            status = "ready" if f.get("status") == 1 else f"#{f.get('status')}"
            t.add_row(
                f["uid"], f["name"], _hsize(f.get("size")),
                f.get("mime") or "—", status,
            )
        console.print(t)


@app.command()
def upload(
    path: Path = typer.Argument(..., exists=True, readable=True),
    folder_id: Optional[int] = typer.Option(None, "--folder", "-f"),
):
    """Upload a local file."""
    if not path.is_file():
        console.print("[red]not a file[/]")
        raise typer.Exit(1)
    with _client() as cli:
        with path.open("rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {"folder_id": str(folder_id)} if folder_id else {}
            r = cli.post("/v2/files/upload", files=files, data=data)
        out = _fail_if_bad(r, "upload")
        f = out["file"]
        console.print(f"[green]ok[/] {f['uid']} · {f['name']} · {_hsize(f['size'])}")


@app.command()
def download(
    uid: str = typer.Argument(...),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
):
    """Download a file by uid."""
    with _client() as cli:
        meta = _fail_if_bad(cli.get(f"/v2/files/{uid}"), "meta")
        name = meta["file"]["name"]
        target = out or Path(name)
        with cli.stream("GET", f"/v2/files/{uid}/stream?mode=dl") as r:
            if r.status_code != 200:
                console.print(f"[red]error[/] HTTP {r.status_code}")
                raise typer.Exit(1)
            with target.open("wb") as fp:
                for chunk in r.iter_bytes(chunk_size=65536):
                    fp.write(chunk)
    console.print(f"[green]ok[/] saved {target}")


@app.command()
def rm(uid: str = typer.Argument(...)):
    """Soft-delete a file (moves to trash for 30 days)."""
    with _client() as cli:
        _fail_if_bad(cli.delete(f"/v2/files/{uid}"), "delete")
        console.print(f"[green]ok[/] {uid} → trash")


@app.command()
def restore(uid: str = typer.Argument(...)):
    """Restore a file from trash."""
    with _client() as cli:
        _fail_if_bad(cli.post(f"/v2/files/{uid}/restore"), "restore")
        console.print(f"[green]ok[/] {uid} restored")


@app.command()
def mv(
    uid: str = typer.Argument(...),
    folder_id: int = typer.Argument(...),
):
    """Move a file to another folder."""
    with _client() as cli:
        _fail_if_bad(cli.patch(f"/v2/files/{uid}", json={"folder_id": folder_id}), "move")
        console.print(f"[green]ok[/] {uid} → folder #{folder_id}")


@app.command()
def rename(
    uid: str = typer.Argument(...),
    name: str = typer.Argument(...),
):
    """Rename a file."""
    with _client() as cli:
        _fail_if_bad(cli.patch(f"/v2/files/{uid}", json={"name": name}), "rename")
        console.print(f"[green]ok[/] renamed to {name}")


@app.command()
def mkdir(
    name: str = typer.Argument(...),
    parent: Optional[int] = typer.Option(None, "--parent", "-p"),
):
    """Create a folder."""
    with _client() as cli:
        body = {"name": name}
        if parent is not None:
            body["parent_id"] = parent
        data = _fail_if_bad(cli.post("/v2/folders", json=body), "mkdir")
        f = data["folder"]
        console.print(f"[green]ok[/] folder #{f['id']} · {f['name']}")


@app.command()
def share(
    uid: str = typer.Argument(...),
    role: str = typer.Option("viewer", "--role", "-r", help="viewer | commenter | editor"),
    expires: Optional[str] = typer.Option(None, "--expires", help="ISO 8601 expiry"),
    password: Optional[str] = typer.Option(None, "--password"),
    max_uses: Optional[int] = typer.Option(None, "--max-uses"),
):
    """Create a public share link."""
    with _client() as cli:
        body: dict = {"role": role}
        if expires:
            body["expires_at"] = expires
        if password:
            body["password"] = password
        if max_uses:
            body["max_uses"] = max_uses
        data = _fail_if_bad(cli.post(f"/v2/files/{uid}/share", json=body), "share")
        cfg = _load()
        base = cfg.get("base_url", DEFAULT_BASE)
        url = f"{base}/v2/ui/s/{data['share']['token']}"
        console.print(f"[green]share[/] {url}")


tokens_app = typer.Typer(no_args_is_help=True, help="Manage API tokens")
app.add_typer(tokens_app, name="tokens")


@tokens_app.command("list")
def tokens_list():
    with _client() as cli:
        data = _fail_if_bad(cli.get("/v2/tokens"), "tokens")
        t = Table(header_style="bold")
        t.add_column("Name")
        t.add_column("Prefix", style="cyan")
        t.add_column("Scopes", style="yellow")
        t.add_column("Last used", style="dim")
        for row in data.get("tokens", []):
            scopes = ",".join(row.get("scopes") or []) or "default"
            t.add_row(
                row["name"], row["prefix"] + "…",
                scopes, row.get("last_used_at") or "never",
            )
        console.print(t)


@tokens_app.command("create")
def tokens_create(
    name: str = typer.Argument(...),
    scopes: Optional[str] = typer.Option(None, "--scopes", "-s", help="comma-separated scopes"),
):
    sc = [x.strip() for x in (scopes or "").split(",") if x.strip()]
    with _client() as cli:
        data = _fail_if_bad(cli.post("/v2/tokens", json={"name": name, "scopes": sc}), "create token")
        console.print(f"[green]ok[/] {data['token']['name']}")
        console.print(f"[bold yellow]token (shown once):[/] {data['token']['token']}")


@tokens_app.command("revoke")
def tokens_revoke(id: int = typer.Argument(...)):
    with _client() as cli:
        _fail_if_bad(cli.delete(f"/v2/tokens/{id}"), "revoke")
        console.print(f"[green]ok[/] revoked #{id}")


@app.command(name="migrate-self")
def migrate_self(
    legacy_token: str = typer.Argument(...),
    base_url: str = typer.Option(DEFAULT_BASE, "--base-url", "-u"),
):
    """Migrate a legacy account into v2 (no auth required)."""
    with httpx.Client(base_url=base_url, timeout=60) as cli:
        r = cli.post("/v2/migrate/legacy/self", json={"legacy_token": legacy_token})
        data = _fail_if_bad(r, "migrate")
        console.print(
            f"[green]ok[/] migrated={data.get('migrated_count', 0)} "
            f"already={data.get('already')} stub={data.get('stub')} "
            f"cloud2_user_id={data.get('cloud2_user_id')}"
        )
        console.print(f"login: {base_url}{data['login_url']}")


def main():
    app()


if __name__ == "__main__":
    main()
