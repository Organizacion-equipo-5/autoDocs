"""Extraccion segura de archivos comprimidos (evita zip-slip / tar-slip y bombas de descompresion)."""
import os
import tarfile
import zipfile
from pathlib import Path

# Limite de tamano total descomprimido (por defecto 1 GB) y de numero de archivos.
MAX_TOTAL_BYTES = int(os.environ.get('MAX_EXTRACT_BYTES', str(1024 * 1024 * 1024)))
MAX_MEMBERS = int(os.environ.get('MAX_EXTRACT_FILES', '50000'))


class UnsafeArchiveError(ValueError):
    """El archivo comprimido intenta escribir fuera del destino o excede los limites."""


def _target_inside(dest: Path, name: str) -> Path:
    target = (dest / name).resolve()
    if target != dest and dest not in target.parents:
        raise UnsafeArchiveError(f"Ruta no permitida dentro del archivo comprimido: {name}")
    return target


def safe_extract_zip(zip_path, dest) -> None:
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise UnsafeArchiveError("El archivo comprimido contiene demasiados archivos")
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise UnsafeArchiveError("El archivo comprimido excede el tamano maximo permitido")
        for info in infos:
            _target_inside(dest, info.filename)
            # Los enlaces simbolicos dentro de un zip se marcan en los atributos externos.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UnsafeArchiveError(f"Enlaces simbolicos no permitidos: {info.filename}")
        archive.extractall(dest)


def safe_extract_tar(tar_path, dest) -> None:
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, 'r:*') as archive:
        members = archive.getmembers()
        if len(members) > MAX_MEMBERS:
            raise UnsafeArchiveError("El archivo comprimido contiene demasiados archivos")
        if sum(max(m.size, 0) for m in members) > MAX_TOTAL_BYTES:
            raise UnsafeArchiveError("El archivo comprimido excede el tamano maximo permitido")
        for member in members:
            _target_inside(dest, member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise UnsafeArchiveError(f"Entrada no permitida en el archivo: {member.name}")
        # El filtro 'data' (Python 3.12+) añade una capa extra de proteccion.
        try:
            archive.extractall(dest, filter='data')
        except TypeError:  # Python < 3.12
            archive.extractall(dest)
