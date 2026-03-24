import os
import re
import tarfile
import zipfile
import shutil
from datetime import datetime
import uuid

try:
    import py7zr
except Exception:
    py7zr = None

try:
    import rarfile
except Exception:
    rarfile = None


def _is_text_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {".txt", ".log"}


def _is_archive_file(file_path: str) -> bool:
    lower = file_path.lower()
    ext = os.path.splitext(lower)[1]
    if ext in {".zip", ".7z", ".rar", ".tar"}:
        return True
    return lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tar.lz", ".tar.lzma", ".tar.z"))


def _collect_txt_log_files(root_dir: str) -> list[str]:
    files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            if _is_text_file(path):
                files.append(path)
    return files


def _archive_stem(file_path: str) -> str:
    name = os.path.basename(file_path)
    lower = name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.lz", ".tar.lzma", ".tar.z"):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def extract_archive(file_path, extract_to=None):
    """
    根据文件扩展名自动选择解压缩方式，支持 zip/7z/rar/tar 及其多种压缩格式。
    非压缩格式（log/txt）直接跳过。
    返回解压后的目录路径；若无需解压则返回原文件路径。
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 提取文件扩展名
    ext = os.path.splitext(file_path)[1].lower()
    # 处理 .tar.* 复合扩展名
    if file_path.lower().endswith(('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.lz', '.tar.lzma', '.tar.z')):
        ext = '.tar'

    # 若为非压缩格式，直接返回原路径
    if ext in {'.log', '.txt'}:
        print(f"[INFO] 非压缩格式，跳过解压: {file_path}")
        return file_path

    # 若未指定输出目录，默认解压到当前文件所在目录
    if extract_to is None:
        extract_to = os.path.dirname(file_path)

    print(f"[INFO] 开始解压 {file_path} 到 {extract_to}")

    # 根据扩展名执行解压
    if ext == '.zip':
        with zipfile.ZipFile(file_path, 'r') as zf:
            zf.extractall(extract_to)
        print(f"[INFO] ZIP 解压完成")
    elif ext == '.7z':
        if py7zr is None:
            print(f"[INFO] 未安装 py7zr，跳过解压: {file_path}")
            return file_path
        with py7zr.SevenZipFile(file_path, mode='r') as sz:
            sz.extractall(path=extract_to)
        print(f"[INFO] 7Z 解压完成")
    elif ext == '.rar':
        if rarfile is None:
            print(f"[INFO] 未安装 rarfile，跳过解压: {file_path}")
            return file_path
        with rarfile.RarFile(file_path) as rf:
            rf.extractall(path=extract_to)
        print(f"[INFO] RAR 解压完成")
    elif ext == '.tar':
        with tarfile.open(file_path, 'r:*') as tf:
            tf.extractall(path=extract_to)
        print(f"[INFO] TAR 解压完成")
    else:
        # 未支持的压缩格式，返回原路径
        print(f"[INFO] 不支持的压缩格式，跳过解压: {file_path}")
        return file_path

    return extract_to

def extract_all_archives(root_dir, extract_to=None, is_extract_all=True, need_recursive=False):
    """
    递归遍历 root_dir 下的所有文件（含子目录），
    对每个文件调用 extract_archive 进行解压。
    若解压成功，则继续对解压出的目录再次递归处理，直到没有可解压文件为止。
    返回已解压的目录路径列表（去重）。
    """
    if not os.path.isdir(root_dir):
        raise NotADirectoryError(f"目录不存在: {root_dir}")

    # 默认解压到原目录
    if extract_to is None:
        extract_to = root_dir
    extracted_dirs = set()

    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            file_path = os.path.join(dirpath, fname)
            try:
                # 尝试解压
                result_path = extract_archive(file_path, extract_to=extract_to)
                # 如果返回的是目录且不是原文件，说明解压成功
                if os.path.isdir(result_path) and result_path != file_path:
                    extracted_dirs.add(os.path.abspath(result_path))
            except Exception as e:
                # 解压失败则跳过，打印日志
                print(f"[WARN] 解压失败，跳过文件: {file_path} 原因: {e}")
    if need_recursive:
        # 对解压出的目录再次递归扫描
        for extracted_dir in list(extracted_dirs):
            sub_dirs = extract_all_archives(extracted_dir, extract_to=extracted_dir)
            extracted_dirs.update(sub_dirs)

    return list(extracted_dirs)

def fetch_all_txt_files(file_path, download_dir, original_name=None):
    """
    传入一个文件路径和下载目录：
    - 若为 .txt/.log，直接返回该文件路径列表
    - 若为压缩文件，解压到文件所在目录下，以压缩包文件名创建目录承载解压内容，
      并递归解压内部压缩包，最后返回其中所有 .txt/.log 文件路径列表
    返回值统一为: List[str]
    """
    result = []

    if not file_path or not download_dir:
        return result

    os.makedirs(download_dir, exist_ok=True)

    candidate_paths = []
    if isinstance(file_path, str):
        candidate_paths.append(file_path)
        candidate_paths.append(os.path.join(download_dir, file_path))
        candidate_paths.append(os.path.join(download_dir, os.path.basename(file_path)))

    target_path = None
    for path in candidate_paths:
        if path and os.path.isfile(path):
            target_path = path
            break
    if not target_path:
        return result

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_name = os.path.basename(target_path)
    stem, ext = os.path.splitext(base_name)
    if original_name:
        o_stem, o_ext = os.path.splitext(os.path.basename(original_name))
        if o_ext:
            stem, ext = o_stem, o_ext
    new_name = f"{stem}_{ts}_{uuid.uuid4().hex}{ext}"
    renamed_path = os.path.join(download_dir, new_name)
    try:
        shutil.copy2(target_path, renamed_path)
        target_path = renamed_path
    except Exception as e:
        print(f"[WARN] 复制文件失败，使用原路径: {target_path} 原因: {e}")

    if _is_text_file(target_path):
        return [target_path]

    if not _is_archive_file(target_path):
        return result

    parent_dir = os.path.dirname(target_path)
    extract_dir = os.path.join(parent_dir, _archive_stem(target_path))
    os.makedirs(extract_dir, exist_ok=True)

    if os.listdir(extract_dir):
        return _collect_txt_log_files(extract_dir)

    extract_archive(target_path, extract_to=extract_dir)
    extract_all_archives(extract_dir, extract_dir, need_recursive=True)
    return _collect_txt_log_files(extract_dir)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python unzip_client.py <file_path> <download_dir>")
        sys.exit(1)

    file_path = sys.argv[1]
    download_dir = sys.argv[2]

    result = fetch_all_txt_files(file_path, download_dir)
    print(result)
