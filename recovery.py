"""JURISRESUMO - Recovery & Checkpoint Management System.

Provides robust snapshot creation, rollback, listing, and diffing for the project
without external dependencies (e.g. Git).

Usage:
    python recovery.py save "initial_working_version"
    python recovery.py list
    python recovery.py restore "initial_working_version"
    python recovery.py diff "initial_working_version"
    python recovery.py show "initial_working_version"
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
RECOVERY_DIR = PROJECT_ROOT / ".recovery"
SNAPSHOTS_DIR = RECOVERY_DIR / "snapshots"
HISTORY_FILE = RECOVERY_DIR / "history.json"

# File patterns to track in checkpoints
TRACKED_PATTERNS = [
    "app/**/*",
    "tests/**/*",
    "*.py",
    "*.md",
    "*.txt",
    "*.json",
]

# Patterns strictly ignored to keep snapshots lightweight and fast
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".recovery",
    "*.pyc",
    "*.pdf",
    "*.docx",
    "test_output_*.docx",
}


def _calculate_sha256(file_path: Path) -> str:
    """Calculates SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _is_excluded(path: Path) -> bool:
    """Checks if a path matches any exclusion rule."""
    path_parts = path.parts
    for part in path_parts:
        if part in EXCLUDE_PATTERNS:
            return True
        if part.startswith(".") and part != ".":
            # Exclude hidden directories like .pytest_cache, except project root
            if part in (".pytest_cache", ".recovery"):
                return True

    name = path.name
    if name.endswith(".pyc") or name.endswith(".pdf") or name.endswith(".docx"):
        return True

    return False


def _get_tracked_files(include_large: bool = False) -> List[Path]:
    """Collects all source code, tests, and configuration files in the project."""
    files: Set[Path] = set()

    for pattern in TRACKED_PATTERNS:
        for p in PROJECT_ROOT.glob(pattern):
            if p.is_file():
                if not include_large and _is_excluded(p):
                    continue
                files.add(p)

    return sorted(list(files))


def _load_history() -> List[Dict]:
    """Loads checkpoint history metadata."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(history: List[Dict]):
    """Saves checkpoint history metadata."""
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_checkpoint(label: str, description: str = "", include_large: bool = False) -> str:
    """Creates a new point-in-time snapshot of the codebase."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
    snapshot_id = f"{timestamp}_{safe_label}"
    zip_path = SNAPSHOTS_DIR / f"{snapshot_id}.zip"

    tracked_files = _get_tracked_files(include_large=include_large)
    if not tracked_files:
        print("[ERRO] Nenhum arquivo localizado para salvar no checkpoint.")
        return ""

    manifest = {
        "id": snapshot_id,
        "label": label,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "file_count": len(tracked_files),
        "files": {},
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tracked_files:
            rel_path = f.relative_to(PROJECT_ROOT).as_posix()
            f_hash = _calculate_sha256(f)
            manifest["files"][rel_path] = {
                "size": f.stat().st_size,
                "sha256": f_hash,
            }
            z.write(f, arcname=rel_path)

        # Include manifest inside the zip
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    history = _load_history()
    history.append({
        "id": snapshot_id,
        "label": label,
        "description": description,
        "created_at": manifest["created_at"],
        "file_count": len(tracked_files),
        "archive": zip_path.name,
        "size_kb": round(zip_path.stat().st_size / 1024, 2),
    })
    _save_history(history)

    print(f"\n[OK] Checkpoint salvo com sucesso!")
    print(f"     ID:          {snapshot_id}")
    print(f"     Rótulo:      {label}")
    print(f"     Arquivos:    {len(tracked_files)}")
    print(f"     Arquivo:     {zip_path.name} ({round(zip_path.stat().st_size / 1024, 1)} KB)")
    return snapshot_id


def list_checkpoints():
    """Displays all available recovery checkpoints."""
    history = _load_history()
    if not history:
        print("\n[INFO] Nenhum checkpoint salvo até o momento.")
        print("       Crie um novo checkpoint com: python recovery.py save \"nome_do_ponto\"")
        return

    sep = "=" * 96
    thin_sep = "-" * 96

    print("\n" + sep)
    print(" JURISRESUMO - PONTOS DE RESTAURAÇÃO / CHECKPOINTS SALVOS")
    print(sep)
    print(f"{'ID do Checkpoint':<26} | {'Rótulo / Descrição':<34} | {'Data / Hora':<19} | {'Tam. (KB)':<9}")
    print(thin_sep)

    for c in reversed(history):
        created_dt = datetime.fromisoformat(c["created_at"]).strftime("%d/%m/%Y %H:%M:%S")
        label_desc = f"{c['label']} ({c.get('description', '')})".strip() if c.get("description") else c["label"]
        if len(label_desc) > 34:
            label_desc = label_desc[:31] + "..."
        print(f"{c['id']:<26} | {label_desc:<34} | {created_dt:<19} | {c.get('size_kb', 0):<9}")

    print(sep)
    print(f"Total de checkpoints: {len(history)}")
    print("Para restaurar: python recovery.py restore <ID_OU_ROTULO>\n")


def _find_checkpoint(identifier: str) -> Optional[Dict]:
    """Finds a checkpoint by exact ID, label, or prefix."""
    history = _load_history()
    identifier_clean = identifier.strip().lower()

    # Exact ID match
    for c in history:
        if c["id"].lower() == identifier_clean:
            return c

    # Exact label match
    for c in history:
        if c["label"].lower() == identifier_clean:
            return c

    # Prefix or partial match
    matches = [c for c in history if identifier_clean in c["id"].lower() or identifier_clean in c["label"].lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"[AVISO] Múltiplos checkpoints correspondem a '{identifier}': {[m['id'] for m in matches]}")
        print("        Por favor, especifique o ID completo.")
        return None

    return None


def restore_checkpoint(identifier: str, no_backup: bool = False) -> bool:
    """Restores the project to a specified checkpoint state."""
    ckpt = _find_checkpoint(identifier)
    if not ckpt:
        print(f"[ERRO] Checkpoint '{identifier}' não encontrado.")
        return False

    zip_path = SNAPSHOTS_DIR / ckpt["archive"]
    if not zip_path.exists():
        print(f"[ERRO] Arquivo de snapshot '{zip_path}' não foi encontrado em disco.")
        return False

    # Safety Pre-Restore Backup (Guarantees zero data loss if restore was accidental)
    if not no_backup:
        print("\n[1/3] Criando ponto de segurança automático pré-restauração...")
        save_checkpoint(label=f"pre_restore_backup", description=f"Backup antes de restaurar {ckpt['id']}")

    print(f"\n[2/3] Extraindo arquivos do checkpoint '{ckpt['id']}'...")
    restored_count = 0
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if member == "manifest.json":
                continue

            target = PROJECT_ROOT / member
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            restored_count += 1

    print(f"[3/3] Restauração concluída com sucesso!")
    print(f"      Total de arquivos restaurados: {restored_count}")
    print(f"      Estado atualizado para: {ckpt['label']} ({ckpt['id']})\n")
    return True


def diff_checkpoint(identifier: str):
    """Compares current working directory files against a saved checkpoint."""
    ckpt = _find_checkpoint(identifier)
    if not ckpt:
        print(f"[ERRO] Checkpoint '{identifier}' não encontrado.")
        return

    zip_path = SNAPSHOTS_DIR / ckpt["archive"]
    if not zip_path.exists():
        print(f"[ERRO] Arquivo do checkpoint não encontrado: {zip_path}")
        return

    with zipfile.ZipFile(zip_path, "r") as z:
        manifest_data = json.loads(z.read("manifest.json").decode("utf-8"))

    checkpoint_files = manifest_data.get("files", {})
    current_files = {f.relative_to(PROJECT_ROOT).as_posix(): f for f in _get_tracked_files()}

    modified = []
    added = []
    deleted = []
    identical = []

    for rel_path, info in checkpoint_files.items():
        if rel_path not in current_files:
            deleted.append(rel_path)
        else:
            cur_file = current_files[rel_path]
            cur_hash = _calculate_sha256(cur_file)
            if cur_hash != info["sha256"]:
                modified.append(rel_path)
            else:
                identical.append(rel_path)

    for rel_path in current_files:
        if rel_path not in checkpoint_files:
            added.append(rel_path)

    sep = "=" * 80
    print("\n" + sep)
    print(f" DIFERENÇA EM RELAÇÃO AO CHECKPOINT: {ckpt['id']} ({ckpt['label']})")
    print(sep)
    print(f"Arquivos idênticos: {len(identical)}")
    print(f"Arquivos modificados: {len(modified)}")
    print(f"Arquivos novos adicionados: {len(added)}")
    print(f"Arquivos removidos: {len(deleted)}")
    print("-" * 80)

    if modified:
        print("\nModificados:")
        for m in modified:
            print(f"  [M] {m}")

    if added:
        print("\nNovos / Não rastreados no checkpoint:")
        for a in added:
            print(f"  [+] {a}")

    if deleted:
        print("\nExcluídos do disco:")
        for d in deleted:
            print(f"  [-] {d}")

    print(sep + "\n")


def main():
    parser = argparse.ArgumentParser(description="JURISRESUMO - Sistema de Recuperação e Checkpoints")
    subparsers = parser.add_subparsers(dest="command", help="Comando a executar")

    # Save
    p_save = subparsers.add_parser("save", help="Criar novo checkpoint")
    p_save.add_argument("label", help="Nome / rótulo identificador do checkpoint")
    p_save.add_argument("-d", "--desc", default="", help="Descrição adicional")
    p_save.add_argument("--include-large", action="store_true", help="Incluir PDFs e arquivos volumosos")

    # List
    subparsers.add_parser("list", help="Listar todos os checkpoints")

    # Restore
    p_restore = subparsers.add_parser("restore", help="Restaurar projeto para um checkpoint")
    p_restore.add_argument("identifier", help="ID ou rótulo do checkpoint")
    p_restore.add_argument("--no-backup", action="store_true", help="Não criar backup automático de segurança")

    # Diff
    p_diff = subparsers.add_parser("diff", help="Ver diferenças entre o estado atual e um checkpoint")
    p_diff.add_argument("identifier", help="ID ou rótulo do checkpoint")

    args = parser.parse_args()

    if args.command == "save":
        save_checkpoint(label=args.label, description=args.desc, include_large=args.include_large)
    elif args.command == "list":
        list_checkpoints()
    elif args.command == "restore":
        restore_checkpoint(identifier=args.identifier, no_backup=args.no_backup)
    elif args.command == "diff":
        diff_checkpoint(identifier=args.identifier)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
