#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

# permite rodar como script sem instalar pacote
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import Settings  # noqa: E402


def utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run_cmd(cmd: list[str], dry_run: bool = False) -> int:
    print(">>", " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.call(cmd)


def ssh_cmd(s: Settings, remote_command: str) -> list[str]:
    return [
        "ssh",
        "-i", s.key_path,
        "-p", str(s.port),
        f"{s.user}@{s.host}",
        remote_command,
    ]


def ensure_remote_dir(s: Settings, dry_run: bool) -> None:
    # mkdir -p no destino remoto
    cmd = ssh_cmd(s, f"mkdir -p '{s.remote_dir}'")
    code = run_cmd(cmd, dry_run=dry_run)
    if code != 0:
        raise RuntimeError(f"Falha ao criar/verificar pasta remota (exit={code}).")


def remote_file_exists(s: Settings, remote_path: str, dry_run: bool) -> bool:
    # testa existência do arquivo remoto
    # (retorna 0 se existir, 1 se não existir)
    cmd = ssh_cmd(s, f"test -f '{remote_path}'")
    if dry_run:
        # no dry-run, assume que não existe para mostrar upload
        return False
    code = run_cmd(cmd, dry_run=False)
    return code == 0


def scp_upload(s: Settings, local_file: Path, remote_path: str, dry_run: bool) -> None:
    cmd = [
        "scp",
        "-i", s.key_path,
        "-P", str(s.port),
        str(local_file),
        f"{s.user}@{s.host}:{remote_path}",
    ]
    code = run_cmd(cmd, dry_run=dry_run)
    if code != 0:
        raise RuntimeError(f"SCP falhou (exit={code}).")


def iter_files(base_dir: Path, pattern: str, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from (p for p in base_dir.rglob(pattern) if p.is_file())
    else:
        yield from (p for p in base_dir.glob(pattern) if p.is_file())


def write_jsonl(log_file: Path, obj: dict) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def make_log_path(logs_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return logs_dir / f"upload_{ts}.jsonl"


def parse_args(s: Settings) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Envia arquivos via SCP para a pasta inputs do GAIO (com logs e pós-processamento)."
    )

    ap.add_argument("--local-dir", default=s.local_files_dir, help="Pasta local de entrada (default: files/).")
    ap.add_argument("--sent-dir", default=s.local_sent_dir, help="Pasta local para mover após sucesso (default: sent/).")
    ap.add_argument("--logs-dir", default=s.local_logs_dir, help="Pasta de logs (default: logs/).")

    ap.add_argument("--pattern", default=s.pattern, help="Filtro glob (ex: '*.csv').")
    ap.add_argument("--recursive", action="store_true", help="Busca arquivos também em subpastas.")

    ap.add_argument("--overwrite", action="store_true", help="Se usado, envia mesmo se já existir no remoto.")
    ap.add_argument("--keep-local", action="store_true", help="Se usado, NÃO move para sent/ (deixa no files/).")
    ap.add_argument("--delete-after", action="store_true", help="Se usado, deleta local após sucesso (prioridade sobre sent/).")

    ap.add_argument("--dry-run", action="store_true", help="Mostra comandos e ações sem executar.")
    return ap.parse_args()


def validate_env(s: Settings) -> None:
    key_path = Path(s.key_path).expanduser().resolve()
    if not key_path.exists():
        raise FileNotFoundError(f"Chave não encontrada: {key_path}")

    # dica: permissões comuns
    # não vamos forçar chmod, mas avisar se parecer aberto demais
    try:
        mode = key_path.stat().st_mode & 0o777
        if mode & 0o077:
            print(f"AVISO: sua chave tem permissão {oct(mode)}. Se der erro, rode: chmod 600 {key_path}")
    except Exception:
        pass


def main() -> int:
    s = Settings()
    args = parse_args(s)

    validate_env(s)

    local_dir = (PROJECT_ROOT / args.local_dir).resolve() if not os.path.isabs(args.local_dir) else Path(args.local_dir).expanduser().resolve()
    sent_dir = (PROJECT_ROOT / args.sent_dir).resolve() if not os.path.isabs(args.sent_dir) else Path(args.sent_dir).expanduser().resolve()
    logs_dir = (PROJECT_ROOT / args.logs_dir).resolve() if not os.path.isabs(args.logs_dir) else Path(args.logs_dir).expanduser().resolve()

    if not local_dir.exists() or not local_dir.is_dir():
        print(f"ERRO: pasta local inválida: {local_dir}", file=sys.stderr)
        return 2

    log_path = make_log_path(logs_dir)
    ensure_remote_dir(s, dry_run=args.dry_run)

    files = list(iter_files(local_dir, args.pattern, args.recursive))
    if not files:
        print("Nenhum arquivo encontrado.")
        write_jsonl(log_path, {
            "ts": utc_iso(),
            "event": "run_end",
            "status": "no_files",
            "local_dir": str(local_dir),
            "pattern": args.pattern,
        })
        return 0

    ok = 0
    skipped = 0
    fail = 0

    for f in files:
        # destino remoto = inputs/<nome do arquivo>
        remote_path = str(Path(s.remote_dir) / f.name)

        entry = {
            "ts": utc_iso(),
            "event": "file",
            "local_path": str(f),
            "remote_path": remote_path,
            "size_bytes": f.stat().st_size,
            "sha256": None,
            "status": None,
            "error": None,
        }

        try:
            entry["sha256"] = sha256_file(f)

            if (not args.overwrite) and remote_file_exists(s, remote_path, dry_run=args.dry_run):
                entry["status"] = "skipped_remote_exists"
                skipped += 1
                write_jsonl(log_path, entry)
                continue

            scp_upload(s, f, remote_path, dry_run=args.dry_run)

            # pós-ação
            if args.delete_after:
                if args.dry_run:
                    print(f":: (dry) deletaria: {f}")
                else:
                    f.unlink()
            elif not args.keep_local:
                sent_dir.mkdir(parents=True, exist_ok=True)
                target = sent_dir / f.name
                if args.dry_run:
                    print(f":: (dry) moveria: {f} -> {target}")
                else:
                    # se já existe no sent/, renomeia com timestamp
                    if target.exists():
                        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
                        target = sent_dir / f"{f.stem}_{suffix}{f.suffix}"
                    shutil.move(str(f), str(target))

            entry["status"] = "uploaded"
            ok += 1

        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            fail += 1

        write_jsonl(log_path, entry)

    # resumo
    summary = {
        "ts": utc_iso(),
        "event": "run_end",
        "status": "ok" if fail == 0 else "partial_fail",
        "local_dir": str(local_dir),
        "remote_dir": s.remote_dir,
        "pattern": args.pattern,
        "recursive": bool(args.recursive),
        "overwrite": bool(args.overwrite),
        "keep_local": bool(args.keep_local),
        "delete_after": bool(args.delete_after),
        "dry_run": bool(args.dry_run),
        "count_total": len(files),
        "count_uploaded": ok,
        "count_skipped": skipped,
        "count_failed": fail,
        "log_file": str(log_path),
    }
    write_jsonl(log_path, summary)

    print("\nResumo:")
    print(f"  total:    {len(files)}")
    print(f"  enviados:  {ok}")
    print(f"  pulados:   {skipped}")
    print(f"  falhas:    {fail}")
    print(f"  log:       {log_path}")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
