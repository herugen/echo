"""Command line entry point for the Echo pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from pipeline import PipelineConfig, load_config, run_pipeline


app = typer.Typer(help="Run video translation pipeline locally.")


def _parse_force(force: Optional[str]) -> set:
    if not force:
        return set()
    return {part.strip() for part in force.split(",") if part.strip()}


@app.command()
def translate(
    url: Optional[str] = typer.Option(None, "--url", help="Source video URL"),
    local_video: Optional[Path] = typer.Option(None, "--local-video", exists=True, file_okay=True, dir_okay=False),
    target_language: str = typer.Option("zh", "--lang", help="Target language code"),
    job_name: Optional[str] = typer.Option(None, "--job-name", help="Slug used for run directory"),
    keep_temp: bool = typer.Option(False, "--keep-temp", help="Preserve tmp files"),
    force_steps: Optional[str] = typer.Option(None, "--force", help="Comma-separated list of stages to re-run"),
    workdir: Path = typer.Option(Path("runs"), "--workdir", help="Root directory to store runs"),
):
    """Translate a video into the target language."""

    config = load_config(
        source_url=url,
        local_video=local_video,
        target_language=target_language,
        job_name=job_name,
        keep_temp=keep_temp,
        workdir=workdir,
        force_steps=_parse_force(force_steps),
    )
    typer.echo("🚀 Starting pipeline...")
    result = run_pipeline(config)
    typer.echo(f"✅ Completed run {result.run_id}")
    if result.output_video:
        typer.echo(f"🎞️ Final video: {result.output_video}")
    typer.echo(f"🗂️ Run directory: {result.context.root}")


@app.command()
def list_runs(
    workdir: Path = typer.Option(Path("runs"), "--workdir", help="Root directory to inspect"),
):
    """List previous runs."""

    if not workdir.exists():
        typer.echo("No runs yet.")
        raise typer.Exit(code=0)

    for slug_dir in sorted(workdir.iterdir()):
        if not slug_dir.is_dir():
            continue
        typer.echo(f"Project: {slug_dir.name}")
        for run_dir in sorted(slug_dir.iterdir()):
            metadata_file = run_dir / "logs" / "metadata.json"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                status = metadata.get("status", "completed")
                typer.echo(f"  - {run_dir.name} [{status}] -> {metadata.get('artifacts', {}).get('final_video')}")
            else:
                typer.echo(f"  - {run_dir.name} [no metadata]")


@app.command()
def show_run(
    run_path: Path = typer.Argument(..., help="Path to the run directory"),
):
    """Show metadata for a specific run."""

    metadata_file = run_path / "logs" / "metadata.json"
    if not metadata_file.exists():
        typer.echo("Metadata not found")
        raise typer.Exit(code=1)
    typer.echo(metadata_file.read_text(encoding="utf-8"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

