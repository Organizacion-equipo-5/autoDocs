#!/usr/bin/env python3
"""
scripts/autodocs_ci.py

CLI para integrar AutoDocs en CI (GitHub Actions u otro). Solo usa la librería
estándar de Python 3.9+, no necesita instalar dependencias.

Subcomandos
-----------
analyze   Analiza una carpeta y guarda un snapshot JSON (análisis + salud del código).
report    Genera docs/AUTODOCS.md (resumen del proyecto) a partir de un snapshot.
pr        Analiza la rama base y la del PR, compara y comenta el PR con el cambio del score.

Variables útiles: AUTODOCS_IGNORE (carpetas a excluir, separadas por comas), GITHUB_TOKEN.

Ejemplos
--------
    python scripts/autodocs_ci.py analyze --path . --out snapshot.json
    python scripts/autodocs_ci.py report --snapshot snapshot.json --out docs/AUTODOCS.md
    python scripts/autodocs_ci.py pr --path . --fail-under 60 --max-drop 5
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# Permite ejecutar el script desde cualquier carpeta (también como Action de otro repo)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import code_health as _code_health  # noqa: E402
from services.analysis_history import build_snapshot, diff_snapshots  # noqa: E402
from services.analyzer import ProjectAnalyzer  # noqa: E402
from services.ci_report import (  # noqa: E402
    COMMENT_MARKER, render_pr_comment, render_project_report,
)
from services.code_health import analyze_code_health  # noqa: E402

API = "https://api.github.com"


# ── Utilidades ───────────────────────────────────────────────────────────────
def _event_payload() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if path and Path(path).is_file():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def _git(args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def apply_ignores(names) -> set:
    """
    Excluye carpetas (por nombre, en cualquier nivel) del análisis y de la salud del código.
    Acepta una lista o un texto separado por comas; ignora rutas con separadores.
    """
    if isinstance(names, str):
        names = names.split(",")
    extra = {n.strip() for n in names or [] if n and n.strip() and "/" not in n and "\\" not in n}
    ProjectAnalyzer.IGNORE_DIRS = set(ProjectAnalyzer.IGNORE_DIRS) | extra
    _code_health.IGNORE_DIRS = set(_code_health.IGNORE_DIRS) | extra
    return extra


def analyze_path(path, source=None) -> tuple:
    """Devuelve (snapshot, results) de una carpeta."""
    analyzer = ProjectAnalyzer(str(path))
    results = analyzer.analyze()
    results["code_health"] = analyze_code_health(path, results)
    return build_snapshot(results, source=source), results


def extract_commit(sha: str, repo_dir: Path, dest: Path):
    """Extrae el árbol de un commit en `dest` (sin tocar el directorio de trabajo)."""
    check = _git(["cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo_dir, check=False)
    if check.returncode != 0:
        _git(["fetch", "--no-tags", "--depth=1", "origin", sha], cwd=repo_dir, check=False)
    archive = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo_dir,
                             capture_output=True)
    if archive.returncode != 0:
        raise RuntimeError(
            f"No se pudo leer el commit base {sha[:7]}. En actions/checkout usa `fetch-depth: 0`.")
    dest.mkdir(parents=True, exist_ok=True)
    untar = subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, capture_output=True)
    if untar.returncode != 0:
        raise RuntimeError(f"No se pudo extraer el commit base: {untar.stderr.decode(errors='ignore')}")


def _write_output(name, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def _write_summary(markdown):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def _api(method, url, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "autodocs-ai-action",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def upsert_pr_comment(repo, pr_number, token, body) -> str:
    """Crea el comentario del reporte o actualiza el existente (identificado por un marcador)."""
    page = 1
    while True:
        comments = _api("GET", f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}",
                        token) or []
        for c in comments:
            if COMMENT_MARKER in (c.get("body") or ""):
                _api("PATCH", f"{API}/repos/{repo}/issues/comments/{c['id']}", token, {"body": body})
                return "updated"
        if len(comments) < 100:
            break
        page += 1
    _api("POST", f"{API}/repos/{repo}/issues/{pr_number}/comments", token, {"body": body})
    return "created"


# ── Subcomandos ──────────────────────────────────────────────────────────────
def cmd_analyze(args) -> int:
    apply_ignores(args.ignore or os.environ.get("AUTODOCS_IGNORE", ""))
    event = _event_payload()
    source = {
        "event": os.environ.get("GITHUB_EVENT_NAME", "manual"),
        "sha": args.sha or os.environ.get("GITHUB_SHA", ""),
        "branch": args.branch or os.environ.get("GITHUB_REF_NAME", ""),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "message": ((event.get("head_commit") or {}).get("message") or "").splitlines()[0]
        if event.get("head_commit") else "",
    }
    snapshot, _ = analyze_path(Path(args.path).resolve(), source)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot guardado en {args.out}: score {snapshot['quality_score']}, "
          f"{snapshot['totals']['functions']} funciones, {snapshot['totals']['endpoints']} endpoints.")
    _write_output("score", snapshot["quality_score"])
    return 0


def cmd_report(args) -> int:
    apply_ignores(args.ignore or os.environ.get("AUTODOCS_IGNORE", ""))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    health = None
    if args.path:
        health = analyze_code_health(Path(args.path).resolve())
    text = render_project_report(snapshot, health, project_name=args.name or "")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"Documento generado: {args.out}")
    return 0


def cmd_pr(args) -> int:
    apply_ignores(args.ignore or os.environ.get("AUTODOCS_IGNORE", ""))
    event = _event_payload()
    pr = event.get("pull_request") or {}
    repo_dir = Path(args.path).resolve()
    base_sha = args.base_sha or (pr.get("base") or {}).get("sha")
    head_sha = args.head_sha or (pr.get("head") or {}).get("sha") or os.environ.get("GITHUB_SHA", "")
    pr_number = args.pr_number or pr.get("number")
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")
    token = args.token or os.environ.get("GITHUB_TOKEN", "")

    if not base_sha:
        print("::error::No se pudo determinar el commit base. Ejecuta esta acción en eventos "
              "`pull_request` o pasa --base-sha.")
        return 2

    base_source = {"event": "base", "sha": base_sha, "repo": repo}
    head_source = {"event": "pull_request", "sha": head_sha, "repo": repo, "pr": pr_number,
                   "branch": (pr.get("head") or {}).get("ref", "")}

    tmp = Path(tempfile.mkdtemp(prefix="autodocs_base_"))
    try:
        extract_commit(base_sha, repo_dir, tmp)
        base_snap, _ = analyze_path(tmp, base_source)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    head_snap, _ = analyze_path(repo_dir, head_source)

    diff = diff_snapshots(base_snap, head_snap)
    score_new, delta = head_snap["quality_score"], diff["score"]["delta"] or 0

    failed = []
    if args.fail_under is not None and score_new < args.fail_under:
        failed.append(f"El score {score_new} es menor al mínimo requerido ({args.fail_under}).")
    if args.max_drop is not None and -delta > args.max_drop:
        failed.append(f"El score bajó {-delta:g} puntos y el máximo permitido es {args.max_drop}.")
    gate = {"fail_under": args.fail_under, "max_drop": args.max_drop, "failed": failed}

    body = render_pr_comment(diff, head_snap, base_snap, gate)
    _write_summary(body)
    _write_output("score", score_new)
    _write_output("base_score", base_snap["quality_score"])
    _write_output("delta", f"{delta:g}")

    if args.diff_out:
        Path(args.diff_out).write_text(json.dumps(diff, ensure_ascii=False), encoding="utf-8")

    if args.comment and pr_number and repo and token:
        try:
            action = upsert_pr_comment(repo, pr_number, token, body)
            print(f"Comentario del PR #{pr_number} {action}.")
        except (urllib.error.URLError, OSError) as e:
            # PRs desde forks tienen token de solo lectura: no es motivo para fallar el CI
            print(f"::warning::No se pudo comentar en el PR ({e}). El reporte está en el resumen del job.")
    elif args.comment:
        print("::notice::Sin token, repositorio o número de PR: el reporte solo se muestra en el resumen del job.")

    print(f"Score base {base_snap['quality_score']} → PR {score_new} ({delta:+g}).")
    for msg in failed:
        print(f"::error::{msg}")
    return 1 if failed else 0


def build_parser():
    p = argparse.ArgumentParser(description="AutoDocs AI para CI")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="Analiza una carpeta y guarda un snapshot JSON")
    a.add_argument("--path", default=".")
    a.add_argument("--out", default="autodocs-snapshot.json")
    a.add_argument("--sha")
    a.add_argument("--branch")
    a.add_argument("--ignore", help="Carpetas a excluir, separadas por comas (p. ej. docs,examples)")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("report", help="Genera el documento Markdown del proyecto")
    r.add_argument("--snapshot", required=True)
    r.add_argument("--path", help="Carpeta del proyecto (opcional, añade el detalle de salud del código)")
    r.add_argument("--out", default="docs/AUTODOCS.md")
    r.add_argument("--name")
    r.add_argument("--ignore", help="Carpetas a excluir, separadas por comas")
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("pr", help="Compara la rama base con el PR y comenta el cambio del score")
    c.add_argument("--path", default=".")
    c.add_argument("--base-sha")
    c.add_argument("--head-sha")
    c.add_argument("--pr-number", type=int)
    c.add_argument("--repo")
    c.add_argument("--token")
    c.add_argument("--fail-under", type=float, default=None)
    c.add_argument("--max-drop", type=float, default=None)
    c.add_argument("--diff-out")
    c.add_argument("--ignore", help="Carpetas a excluir, separadas por comas")
    c.add_argument("--no-comment", dest="comment", action="store_false")
    c.set_defaults(func=cmd_pr, comment=True)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as e:
        print(f"::error::{e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
