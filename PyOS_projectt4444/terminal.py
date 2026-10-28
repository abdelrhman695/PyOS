"""
Terminal Module — PyOS built-in Linux shell (pure Python)

Works on Windows, Linux, and macOS without WSL or any extra software.
Common Linux commands are implemented natively in Python:
  ls  cat  touch  mkdir  rm  rmdir  cp  mv  pwd  echo  grep
  find  head  tail  wc  sort  env  export  unset  whoami
  hostname  uname  date  python3  pip  which  man  history
  chmod  chown  stat  df  du  free  uptime  ps  kill  top
  ln  readlink  realpath  basename  dirname  tr  cut  uniq
  diff  comm  xargs  tee  yes  seq  printf  sleep  true  false
  md5sum  sha256sum  base64  gzip  gunzip  tar  zip  unzip
  curl  wget  ping  ifconfig  ip  ss  netstat  traceroute
  awk  sed  less  more  lsof  strace  watch  timeout  time
  alias  unalias  source  exec  nohup  jobs  bg  fg  wait
  nano  (full built-in text editor — identical feel to GNU nano)

User management commands (linked to PyOS UserManager):
  useradd  userdel  usermod  passwd  groupadd  groupdel
  groups   id       su

Unrecognised commands fall through to the real system shell.
"""

import os
import re
import sys
import shutil
import platform
import datetime
import subprocess
import fnmatch
import hashlib
import base64
import time as _time
import math
import itertools
from typing import Optional

_SYS        = platform.system()
_IS_LINUX   = _SYS == "Linux"
_IS_WINDOWS = _SYS == "Windows"

if _IS_LINUX:
    import select as _select
    import pty as _pty


# ── ANSI → HTML ───────────────────────────────────────────────────────────

_ANSI_COLORS = {
    "30": "#4e4e4e", "31": "#ff5555", "32": "#50fa7b",
    "33": "#f1fa8c", "34": "#bd93f9", "35": "#ff79c6",
    "36": "#8be9fd", "37": "#f8f8f2", "97": "#ffffff",
    "90": "#6272a4", "91": "#ff6e6e", "92": "#69ff94",
    "93": "#ffffa5", "94": "#d6acff", "95": "#ff92df",
    "96": "#a4ffff",
}
_ANSI_COLOR_RE = re.compile(r'\x1b\[([0-9;]*)m')
_ANSI_OTHER_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
_CTRL_RE       = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _he(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace(" ", "&nbsp;")
            .replace("\n", "<br>")
            .replace("\r", ""))


def ansi_to_html(raw: str) -> str:
    raw = _ANSI_OTHER_RE.sub("", raw)
    raw = _CTRL_RE.sub("", raw)
    parts, open_s, last = [], False, 0
    for m in _ANSI_COLOR_RE.finditer(raw):
        s, e = m.span()
        if raw[last:s]:
            parts.append(_he(raw[last:s]))
        codes = m.group(1).split(";")
        if open_s:
            parts.append("</span>"); open_s = False
        if codes not in (["0"], [""], []):
            if not (len(codes) == 1 and codes[0] == "0"):
                for c in codes:
                    col = _ANSI_COLORS.get(c)
                    if col:
                        parts.append(f'<span style="color:{col}">'); open_s = True; break
        last = e
    if raw[last:]:
        parts.append(_he(raw[last:]))
    if open_s:
        parts.append("</span>")
    return "".join(parts)


def _split_args(line: str) -> list[str]:
    args, cur, in_q, q_ch = [], [], False, '"'
    for ch in line:
        if in_q:
            if ch == q_ch:
                in_q = False
            else:
                cur.append(ch)
        elif ch in ('"', "'"):
            in_q, q_ch = True, ch
        elif ch == ' ':
            if cur:
                args.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return args


# ── Built-in Linux command implementations ────────────────────────────────

class _Builtins:
    _C = {
        "reset": "\x1b[0m",
        "dir":   "\x1b[1;34m",
        "exec":  "\x1b[1;32m",
        "link":  "\x1b[1;36m",
        "err":   "\x1b[1;31m",
        "ok":    "\x1b[1;32m",
        "dim":   "\x1b[0;90m",
    }

    @staticmethod
    def _abs(path: str, cwd: str) -> str:
        return os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))

    def ls(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        paths = [a for a in argv[1:] if not a.startswith("-")] or ["."]
        show_all = "-a" in flags or "-la" in flags or "-al" in flags
        long_fmt = "-l" in flags or "-la" in flags or "-al" in flags or "-lh" in flags
        human    = "-h" in flags or "-lh" in flags
        lines = []
        for p in paths:
            target = self._abs(p, cwd)
            if not os.path.exists(target):
                return f"ls: cannot access '{p}': No such file or directory\n", 2
            if os.path.isfile(target):
                entries = [os.path.basename(target)]; base = os.path.dirname(target)
            else:
                try: entries = os.listdir(target)
                except PermissionError: return f"ls: cannot open directory '{p}': Permission denied\n", 2
                base = target
            if not show_all:
                entries = [e for e in entries if not e.startswith(".")]
            entries.sort(key=str.lower)
            for name in entries:
                full = os.path.join(base, name)
                if long_fmt:
                    try:
                        st = os.stat(full)
                        size = st.st_size
                        if human:
                            for unit in ("B","K","M","G"):
                                if size < 1024: break
                                size //= 1024
                            size_s = f"{size}{unit}"
                        else: size_s = str(st.st_size)
                        ts = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%b %d %H:%M")
                        is_d = os.path.isdir(full)
                        is_l = os.path.islink(full)
                        if is_l: perm = "l" + "rwxrwxrwx"
                        elif is_d: perm = "d" + "rwxr-xr-x"
                        else: perm = "-" + "rw-r--r--"
                        col = self._C["link"] if is_l else (self._C["dir"] if is_d else "")
                        rst = self._C["reset"] if col else ""
                        lines.append(f"{perm} 1 user user {size_s:>8} {ts} {col}{name}{rst}")
                    except Exception: lines.append(name)
                else:
                    is_d = os.path.isdir(full)
                    is_l = os.path.islink(full)
                    col = self._C["link"] if is_l else (self._C["dir"] if is_d else "")
                    rst = self._C["reset"] if col else ""
                    lines.append(f"{col}{name}{rst}")
        if not long_fmt:
            max_w = max((len(e.split("\x1b")[0]) for e in lines), default=0) + 2
            cols  = max(1, 80 // max_w)
            rows  = []
            for i in range(0, len(lines), cols):
                rows.append("  ".join(f"{e:<{max_w}}" for e in lines[i:i+cols]))
            return "\n".join(rows) + "\n", 0
        return "\n".join(lines) + "\n", 0

    def cat(self, argv, cwd, env):
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "cat: no file specified\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p): out.append(f"cat: {f}: No such file or directory")
            elif os.path.isdir(p): out.append(f"cat: {f}: Is a directory")
            else:
                try: out.append(open(p, encoding="utf-8", errors="replace").read().rstrip())
                except Exception as e: out.append(f"cat: {f}: {e}")
        return "\n".join(out) + "\n", 0

    def touch(self, argv, cwd, env):
        if len(argv) < 2: return "touch: missing file operand\n", 1
        for f in argv[1:]:
            p = self._abs(f, cwd)
            try: open(p, "a").close(); os.utime(p, None)
            except Exception as e: return f"touch: cannot touch '{f}': {e}\n", 1
        return "", 0

    def mkdir(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        dirs  = [a for a in argv[1:] if not a.startswith("-")]
        if not dirs: return "mkdir: missing operand\n", 1
        parents = "-p" in flags
        for d in dirs:
            p = self._abs(d, cwd)
            try:
                os.makedirs(p) if parents else os.mkdir(p)
            except FileExistsError:
                if not parents: return f"mkdir: cannot create directory '{d}': File exists\n", 1
            except Exception as e: return f"mkdir: cannot create directory '{d}': {e}\n", 1
        return "", 0

    def rm(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        files = [a for a in argv[1:] if not a.startswith("-")]
        recur = "-r" in flags or "-rf" in flags or "-fr" in flags
        if not files: return "rm: missing operand\n", 1
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p): return f"rm: cannot remove '{f}': No such file or directory\n", 1
            try:
                if os.path.isdir(p):
                    if recur: shutil.rmtree(p)
                    else: return f"rm: cannot remove '{f}': Is a directory (use -r)\n", 1
                else: os.remove(p)
            except Exception as e: return f"rm: cannot remove '{f}': {e}\n", 1
        return "", 0

    def rmdir(self, argv, cwd, env):
        if len(argv) < 2: return "rmdir: missing operand\n", 1
        for d in argv[1:]:
            p = self._abs(d, cwd)
            try: os.rmdir(p)
            except Exception as e: return f"rmdir: failed to remove '{d}': {e}\n", 1
        return "", 0

    def cp(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        args  = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "cp: missing file operand\n", 1
        src, dst = self._abs(args[0], cwd), self._abs(args[1], cwd)
        try:
            if os.path.isdir(src):
                if "-r" in flags or "-R" in flags: shutil.copytree(src, dst)
                else: return f"cp: omitting directory '{args[0]}' (use -r)\n", 1
            else: shutil.copy2(src, dst)
        except Exception as e: return f"cp: {e}\n", 1
        return "", 0

    def mv(self, argv, cwd, env):
        args = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "mv: missing file operand\n", 1
        src, dst = self._abs(args[0], cwd), self._abs(args[1], cwd)
        try: shutil.move(src, dst)
        except Exception as e: return f"mv: {e}\n", 1
        return "", 0

    def pwd(self, argv, cwd, env):
        return cwd + "\n", 0

    def echo(self, argv, cwd, env):
        no_nl = "-n" in argv
        parts = [a for a in argv[1:] if a != "-n"]
        out   = []
        for p in parts:
            out.append(re.sub(r'\$(\w+)', lambda m: env.get(m.group(1), ""), p))
        line = " ".join(out)
        return (line if no_nl else line + "\n"), 0

    def grep(self, argv, cwd, env):
        flags   = {a for a in argv[1:] if a.startswith("-")}
        args    = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 1: return "grep: missing pattern\n", 2
        pattern = args[0]; files = args[1:]
        nocase = "-i" in flags; invert = "-v" in flags; nums = "-n" in flags
        count_only = "-c" in flags; only_name = "-l" in flags
        try: rx = re.compile(pattern, re.IGNORECASE if nocase else 0)
        except re.error as e: return f"grep: invalid regex: {e}\n", 2
        results, found = [], False
        sources = [(f, open(self._abs(f, cwd), encoding="utf-8", errors="replace")) for f in files] if files else [("<stdin>", None)]
        for name, fh in sources:
            if fh is None: continue
            match_count = 0
            try:
                for i, line in enumerate(fh, 1):
                    line = line.rstrip("\n")
                    hit  = bool(rx.search(line))
                    if invert: hit = not hit
                    if hit:
                        found = True; match_count += 1
                        if not count_only and not only_name:
                            pfx   = f"{name}:" if files else ""
                            npfx  = f"{i}:" if nums else ""
                            results.append(f"{pfx}{npfx}{line}")
                if count_only: results.append(f"{name}:{match_count}" if len(files) > 1 else str(match_count))
                elif only_name and match_count > 0: results.append(name)
            finally: fh.close()
        return ("\n".join(results) + "\n" if results else ""), (0 if found else 1)

    def find(self, argv, cwd, env):
        start = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else "."
        name_pat = None; type_filter = None; max_depth = None
        i = 1
        while i < len(argv):
            a = argv[i]
            if a == "-name" and i + 1 < len(argv): name_pat = argv[i + 1]; i += 2
            elif a == "-type" and i + 1 < len(argv): type_filter = argv[i + 1]; i += 2
            elif a == "-maxdepth" and i + 1 < len(argv): max_depth = int(argv[i + 1]); i += 2
            else: i += 1
        root  = self._abs(start, cwd); lines = []
        for dirpath, dirs, files in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if max_depth is not None and depth >= max_depth:
                dirs.clear()
            all_entries = ([(d, True) for d in dirs] + [(f, False) for f in files])
            for entry, is_dir in all_entries:
                rel  = os.path.join(dirpath, entry)
                disp = "." + rel[len(root):]
                if type_filter == "d" and not is_dir: continue
                if type_filter == "f" and is_dir: continue
                if name_pat is None or fnmatch.fnmatch(entry, name_pat): lines.append(disp)
        return "\n".join(lines) + "\n", 0

    def head(self, argv, cwd, env):
        n = 10
        for i, a in enumerate(argv):
            if a == "-n" and i + 1 < len(argv): n = int(argv[i + 1])
            elif re.match(r'^-\d+$', a): n = int(a[1:])
        files = [a for a in argv[1:] if not a.startswith("-") and not a.isdigit()]
        out   = []
        for f in files or ["<stdin>"]:
            if f == "<stdin>": continue
            p = self._abs(f, cwd)
            try: lines = open(p, encoding="utf-8", errors="replace").readlines(); out.append("".join(lines[:n]))
            except Exception as e: out.append(f"head: {f}: {e}")
        return "".join(out), 0

    def tail(self, argv, cwd, env):
        n = 10; follow = False
        for i, a in enumerate(argv):
            if a == "-n" and i + 1 < len(argv): n = int(argv[i + 1])
            elif re.match(r'^-\d+$', a): n = int(a[1:])
            elif a == "-f": follow = True
        files = [a for a in argv[1:] if not a.startswith("-") and not a.isdigit()]
        out   = []
        for f in files or ["<stdin>"]:
            if f == "<stdin>": continue
            p = self._abs(f, cwd)
            try: lines = open(p, encoding="utf-8", errors="replace").readlines(); out.append("".join(lines[-n:]))
            except Exception as e: out.append(f"tail: {f}: {e}")
        return "".join(out), 0

    def wc(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "wc: no input\n", 1
        only_l = "-l" in flags; only_w = "-w" in flags; only_c = "-c" in flags
        total_l = total_w = total_c = 0; lines_out = []
        for f in files:
            p    = self._abs(f, cwd)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except Exception as e:
                return f"wc: {f}: {e}\n", 1
            lc   = text.count("\n"); wc = len(text.split()); cc = len(text)
            total_l += lc; total_w += wc; total_c += cc
            if only_l: lines_out.append(f"{lc:>8} {f}")
            elif only_w: lines_out.append(f"{wc:>8} {f}")
            elif only_c: lines_out.append(f"{cc:>8} {f}")
            else: lines_out.append(f"{lc:>8} {wc:>8} {cc:>8} {f}")
        if len(files) > 1:
            if only_l: lines_out.append(f"{total_l:>8} total")
            elif only_w: lines_out.append(f"{total_w:>8} total")
            elif only_c: lines_out.append(f"{total_c:>8} total")
            else: lines_out.append(f"{total_l:>8} {total_w:>8} {total_c:>8} total")
        return "\n".join(lines_out) + "\n", 0

    def sort(self, argv, cwd, env):
        flags = {a for a in argv[1:] if a.startswith("-")}
        files = [a for a in argv[1:] if not a.startswith("-")]
        rev   = "-r" in flags; numeric = "-n" in flags; unique = "-u" in flags
        lines = []
        for f in files:
            p = self._abs(f, cwd)
            lines += open(p, encoding="utf-8", errors="replace").read().splitlines()
        if numeric:
            def _num_key(s):
                m = re.match(r'^\s*(-?\d+(?:\.\d+)?)', s)
                return float(m.group(1)) if m else float('inf')
            lines.sort(key=_num_key, reverse=rev)
        else:
            lines.sort(reverse=rev)
        if unique: lines = list(dict.fromkeys(lines))
        return "\n".join(lines) + "\n", 0

    def env(self, argv, cwd, env_d):
        return "\n".join(f"{k}={v}" for k, v in sorted(env_d.items())) + "\n", 0

    def export(self, argv, cwd, env):
        for a in argv[1:]:
            if "=" in a: k, v = a.split("=", 1); env[k] = v
        return "", 0

    def unset(self, argv, cwd, env):
        for a in argv[1:]: env.pop(a, None)
        return "", 0

    def whoami(self, argv, cwd, env):
        user = env.get("PYOS_USER", env.get("USER", env.get("USERNAME", "user")))
        return user + "\n", 0

    def hostname(self, argv, cwd, env):
        return platform.node() + "\n", 0

    def uname(self, argv, cwd, env):
        flags = set(argv[1:])
        if "-a" in flags:
            return (f"{platform.system()} {platform.node()} "
                    f"{platform.release()} {platform.version()} "
                    f"{platform.machine()}\n"), 0
        if "-r" in flags: return platform.release() + "\n", 0
        if "-m" in flags: return platform.machine() + "\n", 0
        if "-s" in flags: return platform.system() + "\n", 0
        return platform.system() + "\n", 0

    def date(self, argv, cwd, env):
        fmt = "%a %b %d %H:%M:%S %Z %Y"
        for a in argv[1:]:
            if a.startswith("+"): fmt = a[1:]; break
        return datetime.datetime.now().strftime(fmt) + "\n", 0

    def which(self, argv, cwd, env):
        if len(argv) < 2: return "which: missing argument\n", 1
        found = shutil.which(argv[1])
        return (found + "\n" if found else f"which: {argv[1]}: not found\n"), (0 if found else 1)

    # ── NEW: chmod ────────────────────────────────────────────────
    def chmod(self, argv, cwd, env):
        """chmod MODE file..."""
        args = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "chmod: missing operand\nUsage: chmod MODE file...\n", 1
        mode_str, files = args[0], args[1:]
        try:
            if mode_str.isdigit():
                mode = int(mode_str, 8)
            else:
                return f"chmod: symbolic modes not supported in PyOS — use octal (e.g. 755)\n", 1
        except ValueError:
            return f"chmod: invalid mode: '{mode_str}'\n", 1
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p):
                return f"chmod: cannot access '{f}': No such file or directory\n", 1
            try: os.chmod(p, mode)
            except Exception as e: return f"chmod: changing permissions of '{f}': {e}\n", 1
        return "", 0

    # ── NEW: chown ────────────────────────────────────────────────
    def chown(self, argv, cwd, env):
        """chown OWNER[:GROUP] file... (PyOS simulates this)"""
        args = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "chown: missing operand\n", 1
        owner, files = args[0], args[1:]
        out = []
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p): out.append(f"chown: cannot access '{f}': No such file or directory")
        if out: return "\n".join(out) + "\n", 1
        return f"[PyOS] ownership set to '{owner}' (simulated — no actual UID change)\n", 0

    # ── NEW: stat ─────────────────────────────────────────────────
    def stat(self, argv, cwd, env):
        """stat file..."""
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "stat: missing file operand\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p):
                out.append(f"stat: cannot stat '{f}': No such file or directory"); continue
            try:
                st = os.stat(p)
                ftype = "directory" if os.path.isdir(p) else ("symbolic link" if os.path.islink(p) else "regular file")
                mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                atime = datetime.datetime.fromtimestamp(st.st_atime).strftime("%Y-%m-%d %H:%M:%S")
                ctime = datetime.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                size = st.st_size
                out.append(
                    f"  File: {p}\n"
                    f"  Size: {size}\t\tType: {ftype}\n"
                    f"  Mode: {oct(st.st_mode)}\n"
                    f"Access: {atime}\n"
                    f"Modify: {mtime}\n"
                    f"Change: {ctime}"
                )
            except Exception as e: out.append(f"stat: {f}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: df ───────────────────────────────────────────────────
    def df(self, argv, cwd, env):
        """df [-h] — disk free"""
        try:
            import psutil
            human = "-h" in argv
            out = ["Filesystem           Size    Used    Free    Use%  Mounted on"]
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    def _fmt(n):
                        if not human: return str(n)
                        for u in ("B","K","M","G","T"):
                            if n < 1024: return f"{n:.1f}{u}"
                            n /= 1024
                        return f"{n:.1f}P"
                    out.append(f"{part.device:<20} {_fmt(usage.total):>6}  {_fmt(usage.used):>6}  {_fmt(usage.free):>6}  {usage.percent:>4.1f}%  {part.mountpoint}")
                except Exception: pass
            return "\n".join(out) + "\n", 0
        except ImportError:
            return "df: psutil not available\n", 1

    # ── NEW: du ───────────────────────────────────────────────────
    def du(self, argv, cwd, env):
        """du [-h] [-s] [dir]"""
        human = "-h" in argv; summary = "-s" in argv
        paths = [a for a in argv[1:] if not a.startswith("-")] or ["."]
        def _fmt(n):
            if not human: return str(n)
            for u in ("B","K","M","G"):
                if n < 1024: return f"{n:.1f}{u}"
                n /= 1024
            return f"{n:.1f}T"
        out = []
        for p in paths:
            target = self._abs(p, cwd)
            if not os.path.exists(target):
                out.append(f"du: cannot access '{p}': No such file or directory"); continue
            if os.path.isfile(target):
                out.append(f"{_fmt(os.path.getsize(target))}\t{target}"); continue
            total = 0
            for dirpath, dirs, files in os.walk(target):
                for fname in files:
                    try: total += os.path.getsize(os.path.join(dirpath, fname))
                    except: pass
                if not summary:
                    dir_sz = sum(os.path.getsize(os.path.join(dirpath, fn)) for fn in files if os.path.isfile(os.path.join(dirpath, fn)))
                    out.append(f"{_fmt(dir_sz)}\t{dirpath}")
            if summary: out.append(f"{_fmt(total)}\t{target}")
        return "\n".join(out) + "\n", 0

    # ── NEW: free ─────────────────────────────────────────────────
    def free(self, argv, cwd, env):
        """free [-h] — memory info"""
        try:
            import psutil
            human = "-h" in argv
            def _fmt(n):
                if not human: return str(n // 1024)
                for u in ("K","M","G"):
                    if n < 1024 * 1024: return f"{n//1024:.0f}{u}"
                    n //= 1024
                return f"{n}G"
            vm = psutil.virtual_memory(); sw = psutil.swap_memory()
            out = [
                f"{'':14} {'total':>10} {'used':>10} {'free':>10} {'available':>12}",
                f"{'Mem:':14} {_fmt(vm.total):>10} {_fmt(vm.used):>10} {_fmt(vm.free):>10} {_fmt(vm.available):>12}",
                f"{'Swap:':14} {_fmt(sw.total):>10} {_fmt(sw.used):>10} {_fmt(sw.free):>10}",
            ]
            return "\n".join(out) + "\n", 0
        except ImportError:
            return "free: psutil not available\n", 1

    # ── NEW: uptime ───────────────────────────────────────────────
    def uptime(self, argv, cwd, env):
        """uptime — system uptime"""
        try:
            import psutil
            boot = psutil.boot_time()
            delta = int(_time.time() - boot)
            h, rem = divmod(delta, 3600)
            m, s = divmod(rem, 60)
            cpu = psutil.cpu_percent(interval=None)
            now = datetime.datetime.now().strftime("%H:%M:%S")
            return f" {now} up {h}:{m:02d}, load average: {cpu:.2f}\n", 0
        except ImportError:
            return "uptime: psutil not available\n", 1

    # ── NEW: ps ───────────────────────────────────────────────────
    def ps(self, argv, cwd, env):
        """ps [aux] — process list"""
        flags = set(argv[1:])
        try:
            import psutil
            out = [f"{'PID':>7} {'PPID':>7} {'%CPU':>6} {'%MEM':>6} {'STATUS':<10} {'NAME'}"]
            attrs = ['pid', 'ppid', 'cpu_percent', 'memory_percent', 'status', 'name']
            procs = sorted(psutil.process_iter(attrs), key=lambda p: p.info.get('pid', 0))
            count = 0
            for proc in procs:
                try:
                    i = proc.info
                    out.append(f"{i['pid']:>7} {i['ppid'] or 0:>7} {i['cpu_percent'] or 0:>6.1f} "
                               f"{i['memory_percent'] or 0:>6.1f} {i['status'] or '?':<10} {i['name'] or '?'}")
                    count += 1
                    if count >= 40 and "a" not in "".join(flags): break
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            return "\n".join(out) + "\n", 0
        except ImportError:
            return "ps: psutil not available\n", 1

    # ── NEW: kill ─────────────────────────────────────────────────
    def kill(self, argv, cwd, env):
        """kill [-SIGNAL] PID..."""
        import signal as _sig
        flags = [a for a in argv[1:] if a.startswith("-")]
        pids  = [a for a in argv[1:] if not a.startswith("-")]
        sig = _sig.SIGTERM
        for f in flags:
            name = f.lstrip("-").upper()
            if name.isdigit(): sig = int(name)
            elif hasattr(_sig, f"SIG{name}"): sig = getattr(_sig, f"SIG{name}")
        if not pids: return "kill: usage: kill [-SIGNAL] PID...\n", 1
        out = []
        for pid_s in pids:
            try:
                pid = int(pid_s)
                os.kill(pid, sig)
                out.append(f"Sent signal {sig} to PID {pid}")
            except ValueError: out.append(f"kill: invalid PID: {pid_s}")
            except ProcessLookupError: out.append(f"kill: ({pid_s}) - No such process")
            except PermissionError: out.append(f"kill: ({pid_s}) - Permission denied")
            except Exception as e: out.append(f"kill: {pid_s}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: ln ───────────────────────────────────────────────────
    def ln(self, argv, cwd, env):
        """ln [-s] TARGET LINK_NAME"""
        flags = {a for a in argv[1:] if a.startswith("-")}
        args  = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "ln: missing file operand\nUsage: ln [-s] TARGET LINK_NAME\n", 1
        target, link = self._abs(args[0], cwd), self._abs(args[1], cwd)
        try:
            if "-s" in flags: os.symlink(target, link)
            else: os.link(target, link)
        except Exception as e: return f"ln: failed to create link '{args[1]}': {e}\n", 1
        return "", 0

    # ── NEW: readlink ─────────────────────────────────────────────
    def readlink(self, argv, cwd, env):
        """readlink [-f] FILE"""
        files = [a for a in argv[1:] if not a.startswith("-")]
        full  = "-f" in argv
        if not files: return "readlink: missing operand\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            try:
                if full: out.append(os.path.realpath(p))
                elif os.path.islink(p): out.append(os.readlink(p))
                else: out.append(f"readlink: {f}: not a symbolic link")
            except Exception as e: out.append(f"readlink: {f}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: realpath ─────────────────────────────────────────────
    def realpath(self, argv, cwd, env):
        """realpath PATH"""
        paths = [a for a in argv[1:] if not a.startswith("-")]
        if not paths: return "realpath: missing operand\n", 1
        out = [os.path.realpath(self._abs(p, cwd)) for p in paths]
        return "\n".join(out) + "\n", 0

    # ── NEW: basename / dirname ────────────────────────────────────
    def basename_cmd(self, argv, cwd, env):
        """basename PATH [SUFFIX]"""
        if len(argv) < 2: return "basename: missing operand\n", 1
        result = os.path.basename(argv[1])
        if len(argv) >= 3 and result.endswith(argv[2]):
            result = result[:-len(argv[2])]
        return result + "\n", 0

    def dirname_cmd(self, argv, cwd, env):
        """dirname PATH"""
        if len(argv) < 2: return "dirname: missing operand\n", 1
        return os.path.dirname(argv[1] or ".") + "\n", 0

    # ── NEW: tr ───────────────────────────────────────────────────
    def tr_cmd(self, argv, cwd, env):
        """tr SET1 SET2 — transliterate characters (reads from last piped result)"""
        args = [a for a in argv[1:] if not a.startswith("-")]
        if len(args) < 2: return "tr: usage: tr SET1 SET2\n", 1
        s1, s2 = args[0], args[1]
        text = env.get("__PIPE__", "")
        if not text: return "tr: no piped input (PyOS tr requires pipe data)\n", 1
        table = str.maketrans(s1, s2[:len(s1)])
        return text.translate(table), 0

    # ── NEW: cut ──────────────────────────────────────────────────
    def cut(self, argv, cwd, env):
        """cut -d DELIM -f FIELDS file"""
        delim = "\t"; fields = None
        i = 1
        while i < len(argv):
            if argv[i] == "-d" and i + 1 < len(argv): delim = argv[i + 1]; i += 2
            elif argv[i].startswith("-d") and len(argv[i]) > 2: delim = argv[i][2:]; i += 1
            elif argv[i] == "-f" and i + 1 < len(argv): fields = argv[i + 1]; i += 2
            elif argv[i].startswith("-f") and len(argv[i]) > 2: fields = argv[i][2:]; i += 1
            else: i += 1
        files = [a for a in argv[1:] if not a.startswith("-")]
        if fields is None: return "cut: you must specify a list of fields\n", 1
        # parse fields e.g. "1,3" or "2-4"
        fset = set()
        for part in fields.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                fset.update(range(int(a), int(b) + 1))
            else:
                fset.add(int(part))
        out = []
        def _process(text):
            for line in text.splitlines():
                parts = line.split(delim)
                selected = [parts[f - 1] for f in sorted(fset) if 1 <= f <= len(parts)]
                out.append(delim.join(selected))
        for f in files:
            p = self._abs(f, cwd)
            try: _process(open(p, encoding="utf-8", errors="replace").read())
            except Exception as e: return f"cut: {f}: {e}\n", 1
        return "\n".join(out) + "\n", 0

    # ── NEW: uniq ─────────────────────────────────────────────────
    def uniq(self, argv, cwd, env):
        """uniq [-c] [-d] [-u] [file]"""
        flags = {a for a in argv[1:] if a.startswith("-")}
        files = [a for a in argv[1:] if not a.startswith("-")]
        count = "-c" in flags; dup_only = "-d" in flags; unique_only = "-u" in flags
        lines = []
        for f in files:
            p = self._abs(f, cwd)
            try: lines += open(p, encoding="utf-8", errors="replace").read().splitlines()
            except Exception as e: return f"uniq: {f}: {e}\n", 1
        out = []
        for key, grp in itertools.groupby(lines):
            grp_list = list(grp)
            n = len(grp_list)
            if dup_only and n == 1: continue
            if unique_only and n > 1: continue
            prefix = f"  {n} " if count else ""
            out.append(f"{prefix}{key}")
        return "\n".join(out) + "\n", 0

    # ── NEW: diff ─────────────────────────────────────────────────
    def diff(self, argv, cwd, env):
        """diff FILE1 FILE2"""
        files = [a for a in argv[1:] if not a.startswith("-")]
        if len(files) < 2: return "diff: usage: diff FILE1 FILE2\n", 1
        p1, p2 = self._abs(files[0], cwd), self._abs(files[1], cwd)
        try:
            import difflib
            l1 = open(p1, encoding="utf-8", errors="replace").readlines()
            l2 = open(p2, encoding="utf-8", errors="replace").readlines()
            diff = list(difflib.unified_diff(l1, l2, fromfile=files[0], tofile=files[1]))
            if not diff: return "", 0
            return "".join(diff), 1
        except FileNotFoundError as e:
            return f"diff: {e}\n", 2

    # ── NEW: seq ──────────────────────────────────────────────────
    def seq(self, argv, cwd, env):
        """seq [FIRST] [INCREMENT] LAST"""
        args = argv[1:]
        try:
            if len(args) == 1: nums = range(1, int(args[0]) + 1)
            elif len(args) == 2: nums = range(int(args[0]), int(args[1]) + 1)
            elif len(args) == 3: nums = range(int(args[0]), int(args[2]) + 1, int(args[1]))
            else: return "seq: usage: seq [FIRST [INCREMENT]] LAST\n", 1
            return "\n".join(map(str, nums)) + "\n", 0
        except ValueError as e: return f"seq: {e}\n", 1

    # ── NEW: printf ───────────────────────────────────────────────
    def printf_cmd(self, argv, cwd, env):
        """printf FORMAT [ARGS...]"""
        if len(argv) < 2: return "printf: missing format\n", 1
        fmt = argv[1].replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        try:
            args = argv[2:]
            out = fmt % tuple(args) if args else fmt
            return out, 0
        except Exception:
            return fmt, 0

    # ── NEW: sleep ────────────────────────────────────────────────
    def sleep(self, argv, cwd, env):
        """sleep SECONDS"""
        if len(argv) < 2: return "sleep: missing operand\n", 1
        try:
            secs = float(argv[1])
            if secs > 10: return "sleep: max 10 seconds in PyOS terminal\n", 1
            _time.sleep(secs)
            return "", 0
        except ValueError: return f"sleep: invalid time interval: '{argv[1]}'\n", 1

    # ── NEW: md5sum ───────────────────────────────────────────────
    def md5sum(self, argv, cwd, env):
        """md5sum FILE..."""
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "md5sum: missing file operand\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            try:
                data = open(p, "rb").read()
                h = hashlib.md5(data).hexdigest()
                out.append(f"{h}  {f}")
            except Exception as e: out.append(f"md5sum: {f}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: sha256sum ────────────────────────────────────────────
    def sha256sum(self, argv, cwd, env):
        """sha256sum FILE..."""
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "sha256sum: missing file operand\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            try:
                data = open(p, "rb").read()
                h = hashlib.sha256(data).hexdigest()
                out.append(f"{h}  {f}")
            except Exception as e: out.append(f"sha256sum: {f}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: base64 ───────────────────────────────────────────────
    def base64_cmd(self, argv, cwd, env):
        """base64 [-d] [FILE]"""
        decode = "-d" in argv or "--decode" in argv
        files  = [a for a in argv[1:] if not a.startswith("-")]
        if files:
            p = self._abs(files[0], cwd)
            try: data = open(p, "rb").read()
            except Exception as e: return f"base64: {files[0]}: {e}\n", 1
        else:
            text = env.get("__PIPE__", "")
            data = text.encode()
        if decode:
            try: return base64.b64decode(data).decode(errors="replace") + "\n", 0
            except Exception as e: return f"base64: invalid input: {e}\n", 1
        return base64.b64encode(data).decode() + "\n", 0

    # ── NEW: awk (minimal) ────────────────────────────────────────
    def awk(self, argv, cwd, env):
        """awk 'PATTERN{ACTION}' FILE  — minimal: print $N, $NF, NR, NF"""
        args = [a for a in argv[1:] if not a.startswith("-")]
        if not args: return "awk: usage: awk 'program' [file]\n", 1
        prog = args[0]; files = args[1:]
        # Simple field printer: handles {print $1}, {print $NF}, {print NR,$2}
        lines_in = []
        for f in files:
            p = self._abs(f, cwd)
            try: lines_in += open(p, encoding="utf-8", errors="replace").readlines()
            except Exception as e: return f"awk: {f}: {e}\n", 1
        if not lines_in: return "awk: no input file in PyOS (piped input not yet supported)\n", 1
        FS = " "
        m_fs = re.search(r"-F\s*(\S+)", " ".join(argv))
        if m_fs: FS = m_fs.group(1)
        # Extract action block
        m_act = re.match(r"(?:.*?)\{(.+?)\}", prog, re.DOTALL)
        action = m_act.group(1).strip() if m_act else "print $0"
        out = []
        for nr, raw in enumerate(lines_in, 1):
            line = raw.rstrip("\n")
            fields = line.split(FS) if FS == " " else line.split(FS)
            NF = len(fields)
            def _repl(m):
                ref = m.group(1)
                if ref == "0": return line
                if ref == "NF": return fields[-1] if fields else ""
                if ref == "NR": return str(nr)
                try: return fields[int(ref) - 1] if 1 <= int(ref) <= NF else ""
                except: return ""
            resolved = re.sub(r'\$(\w+)', _repl, action)
            resolved = resolved.replace("NR", str(nr)).replace("NF", str(NF))
            if resolved.startswith("print"):
                val = resolved[5:].strip().strip('"')
                out.append(val)
        return "\n".join(out) + "\n", 0

    # ── NEW: sed (minimal) ────────────────────────────────────────
    def sed(self, argv, cwd, env):
        """sed 's/PATTERN/REPLACE/[g]' FILE  — substitution only"""
        args = [a for a in argv[1:] if not a.startswith("-")]
        if not args: return "sed: usage: sed 's/PAT/REP/[g]' [file]\n", 1
        script = args[0]; files = args[1:]
        m = re.match(r'^s(.)(.*?)\1(.*?)\1([gip]*)$', script)
        if not m: return f"sed: unrecognized command '{script}' (only s/// supported)\n", 1
        pat, rep, flags_s = m.group(2), m.group(3), m.group(4)
        count = 0 if "g" in flags_s else 1
        lines_in = []
        for f in files:
            p = self._abs(f, cwd)
            try: lines_in += open(p, encoding="utf-8", errors="replace").readlines()
            except Exception as e: return f"sed: {f}: {e}\n", 1
        if not lines_in: return "sed: no input file\n", 1
        out = []
        try: rx = re.compile(pat)
        except re.error as e: return f"sed: invalid regex: {e}\n", 1
        for line in lines_in:
            out.append(rx.sub(rep, line, count=count))
        return "".join(out), 0

    # ── NEW: tee ──────────────────────────────────────────────────
    def tee(self, argv, cwd, env):
        """tee FILE — write piped input to file (PyOS: writes env __PIPE__)"""
        append = "-a" in argv
        files  = [a for a in argv[1:] if not a.startswith("-")]
        text   = env.get("__PIPE__", "")
        if not text: return "tee: no piped input\n", 1
        for f in files:
            p = self._abs(f, cwd)
            try:
                mode = "a" if append else "w"
                open(p, mode, encoding="utf-8").write(text)
            except Exception as e: return f"tee: {f}: {e}\n", 1
        return text, 0

    # ── NEW: file type detector ────────────────────────────────────
    def file_cmd(self, argv, cwd, env):
        """file FILE..."""
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files: return "file: missing operand\n", 1
        out = []
        for f in files:
            p = self._abs(f, cwd)
            if not os.path.exists(p): out.append(f"{f}: cannot open (No such file or directory)"); continue
            if os.path.isdir(p): out.append(f"{f}: directory"); continue
            if os.path.islink(p): out.append(f"{f}: symbolic link"); continue
            try:
                with open(p, "rb") as fh:
                    hdr = fh.read(16)
                if hdr[:4] == b'\x7fELF': out.append(f"{f}: ELF executable")
                elif hdr[:2] == b'MZ': out.append(f"{f}: PE/COFF executable (Windows)")
                elif hdr[:2] == b'PK': out.append(f"{f}: Zip archive")
                elif hdr[:3] == b'\x1f\x8b\x08': out.append(f"{f}: gzip compressed data")
                elif hdr[:4] in (b'\x89PNG', b'GIF8', b'\xff\xd8\xff'): out.append(f"{f}: image data")
                else:
                    try:
                        snippet = open(p, encoding="utf-8", errors="strict").read(512)
                        out.append(f"{f}: ASCII text")
                    except UnicodeDecodeError:
                        out.append(f"{f}: binary data")
            except Exception as e: out.append(f"{f}: {e}")
        return "\n".join(out) + "\n", 0

    # ── NEW: lsof (simulated) ──────────────────────────────────────
    def lsof(self, argv, cwd, env):
        """lsof — list open files (simulated via psutil)"""
        try:
            import psutil
            out = [f"{'PID':>7} {'NAME':<20} {'FD':<5} TYPE  PATH"]
            count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for of in proc.open_files():
                        out.append(f"{proc.pid:>7} {(proc.info.get('name') or '?'):<20} {of.fd:<5} REG   {of.path}")
                        count += 1
                        if count >= 30: break
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                if count >= 30: break
            return "\n".join(out) + "\n", 0
        except ImportError:
            return "lsof: psutil not available\n", 1

    # ── NEW: watch (limited) ──────────────────────────────────────
    def watch(self, argv, cwd, env):
        """watch [-n N] COMMAND — runs command once in PyOS (no loop)"""
        n = 2; args = argv[1:]
        if args and args[0] == "-n" and len(args) > 1:
            try: n = float(args[1]); args = args[2:]
            except: args = args[1:]
        if not args: return "watch: missing command\n", 1
        cmd = " ".join(args)
        out, rc = run_builtin(cmd, cwd, env)
        note = f"\n[PyOS watch: ran once — loop not supported in terminal]\n"
        if out is not None: return (out or "") + note, rc
        return f"watch: '{cmd}' not a built-in command\n", 1

    # ── NEW: timeout ──────────────────────────────────────────────
    def timeout_cmd(self, argv, cwd, env):
        """timeout DURATION COMMAND"""
        if len(argv) < 3: return "timeout: usage: timeout DURATION COMMAND\n", 1
        try: float(argv[1])
        except ValueError: return f"timeout: invalid duration '{argv[1]}'\n", 1
        cmd = " ".join(argv[2:])
        out, rc = run_builtin(cmd, cwd, env)
        if out is not None: return out or "", rc
        return f"timeout: '{cmd}' not a built-in command\n", 1

    # ── NEW: alias / unalias ──────────────────────────────────────
    def alias(self, argv, cwd, env):
        """alias [name=value] — define or list aliases"""
        if len(argv) == 1:
            aliases = {k: v for k, v in env.items() if k.startswith("__ALIAS__")}
            if not aliases: return "No aliases defined.\n", 0
            return "\n".join(f"alias {k[9:]}='{v}'" for k, v in aliases.items()) + "\n", 0
        for a in argv[1:]:
            if "=" in a:
                name, val = a.split("=", 1)
                env[f"__ALIAS__{name}"] = val.strip("'\"")
        return "", 0

    def unalias(self, argv, cwd, env):
        """unalias name"""
        if len(argv) < 2: return "unalias: usage: unalias name\n", 1
        for name in argv[1:]:
            env.pop(f"__ALIAS__{name}", None)
        return "", 0

    # ── NEW: nohup (simulated) ────────────────────────────────────
    def nohup(self, argv, cwd, env):
        """nohup COMMAND — runs command (ignoring hangup, simulated)"""
        if len(argv) < 2: return "nohup: usage: nohup COMMAND\n", 1
        cmd = " ".join(argv[1:])
        out, rc = run_builtin(cmd, cwd, env)
        if out is not None: return (out or "") + "\n[nohup: ran as built-in]\n", rc
        return f"nohup: sending '{cmd}' to system shell\n", 0

    # ── NEW: ping (live via system) ────────────────────────────────
    def ping(self, argv, cwd, env):
        """ping HOST — send 4 ICMP probes"""
        hosts = [a for a in argv[1:] if not a.startswith("-")]
        count = 4
        for i, a in enumerate(argv):
            if a in ("-c", "-n") and i + 1 < len(argv):
                try: count = int(argv[i + 1])
                except: pass
        if not hosts: return "ping: usage: ping [-c COUNT] HOST\n", 1
        host = hosts[0]
        sys_n = platform.system().lower()
        try:
            if sys_n == "windows":
                cmd = ["ping", "-n", str(count), host]
            else:
                cmd = ["ping", "-c", str(count), host]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=count * 2 + 5)
            return (r.stdout or r.stderr) + "\n", r.returncode
        except subprocess.TimeoutExpired:
            return f"ping: {host}: timeout\n", 1
        except FileNotFoundError:
            return "ping: command not found on system\n", 1

    # ── NEW: ifconfig (read-only info) ────────────────────────────
    def ifconfig(self, argv, cwd, env):
        """ifconfig — show network interfaces"""
        try:
            import psutil, socket
            out = []
            for iface, addrs in psutil.net_if_addrs().items():
                out.append(f"{iface}:")
                for a in addrs:
                    if a.family == socket.AF_INET:
                        out.append(f"    inet  {a.address}  netmask {a.netmask or 'N/A'}")
                    elif a.family == socket.AF_INET6:
                        out.append(f"    inet6 {a.address}")
                    elif hasattr(socket, 'AF_PACKET') and a.family == socket.AF_PACKET:
                        out.append(f"    ether {a.address}")
                stats = psutil.net_if_stats().get(iface)
                if stats:
                    speed = f"{stats.speed}Mbps" if stats.speed else "N/A"
                    out.append(f"    status: {'UP' if stats.isup else 'DOWN'}  speed: {speed}")
                out.append("")
            return "\n".join(out), 0
        except ImportError:
            return "ifconfig: psutil not available\n", 1

    # ── NEW: ip addr ──────────────────────────────────────────────
    def ip_cmd(self, argv, cwd, env):
        """ip [addr|link|route] — network info"""
        sub = argv[1] if len(argv) > 1 else "addr"
        if sub in ("addr", "address", "a"):
            return self.ifconfig(argv, cwd, env)
        if sub in ("link", "l"):
            try:
                import psutil
                out = []
                for i, (name, stats) in enumerate(psutil.net_if_stats().items()):
                    state = "UP" if stats.isup else "DOWN"
                    out.append(f"{i + 1}: {name}: <{state}> mtu {stats.mtu}")
                return "\n".join(out) + "\n", 0
            except ImportError:
                return "ip: psutil not available\n", 1
        if sub in ("route", "r"):
            sys_n = platform.system().lower()
            try:
                if sys_n == "linux":
                    r = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=3)
                    return r.stdout + "\n", 0
                elif sys_n == "darwin":
                    r = subprocess.run(["netstat", "-rn"], capture_output=True, text=True, timeout=3)
                    return r.stdout + "\n", 0
                elif sys_n == "windows":
                    r = subprocess.run(["route", "print"], capture_output=True, text=True, timeout=3,
                                       creationflags=0x08000000)
                    return r.stdout + "\n", 0
            except Exception as e:
                return f"ip route: {e}\n", 1
        return f"ip: unknown subcommand '{sub}'. Try: addr, link, route\n", 1

    # ── NEW: netstat ──────────────────────────────────────────────
    def netstat(self, argv, cwd, env):
        """netstat [-t|-u|-l] — network connections"""
        try:
            import psutil
            flags = set(argv[1:])
            conns = psutil.net_connections()
            out = [f"{'Proto':<6} {'Local Address':<25} {'Remote Address':<25} {'Status':<12} {'PID'}"]
            for c in conns:
                if "-t" in flags and c.type != 1: continue
                if "-u" in flags and c.type != 2: continue
                if "-l" in flags and c.status not in ("LISTEN", "NONE", ""): continue
                proto = "TCP" if c.type == 1 else ("UDP" if c.type == 2 else "?")
                la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "*"
                ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "*"
                out.append(f"{proto:<6} {la:<25} {ra:<25} {c.status or '':<12} {c.pid or ''}")
            return "\n".join(out[:35]) + "\n", 0
        except ImportError:
            return "netstat: psutil not available\n", 1

    # ── NEW: ss ───────────────────────────────────────────────────
    def ss(self, argv, cwd, env):
        """ss [-t|-u|-l] — socket statistics (alias for netstat)"""
        return self.netstat(argv, cwd, env)

    # ── User Management Commands ──────────────────────────────────────────

    def useradd(self, argv, cwd, env):
        """useradd [-m] [-G group1,group2] [-s shell] [-p password] username"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        if actor and not um.is_admin(actor):
            return "useradd: Permission denied. Requires root/sudo.\n", 1

        flags     = {}
        positional = []
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in ("-G",) and i + 1 < len(argv):
                flags[a] = argv[i + 1]; i += 2
            elif a in ("-s","-p","--shell","--password") and i + 1 < len(argv):
                flags[a] = argv[i + 1]; i += 2
            elif a.startswith("-"): i += 1
            else: positional.append(a); i += 1

        if not positional:
            return "useradd: missing username\nUsage: useradd [-G groups] [-s shell] [-p password] username\n", 1

        username = positional[0]
        password = flags.get("-p", "changeme")
        shell    = flags.get("-s", flags.get("--shell", "/bin/bash"))
        groups   = [g.strip() for g in flags.get("-G", "").split(",") if g.strip()]

        ok, msg = um.create_user(username, password, groups=groups, shell=shell)
        return msg + "\n", 0 if ok else 1

    def userdel(self, argv, cwd, env):
        """userdel username"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        if actor and not um.is_admin(actor):
            return "userdel: Permission denied. Requires root/sudo.\n", 1
        if len(argv) < 2:
            return "userdel: missing username\n", 1
        ok, msg = um.delete_user(argv[1], actor=actor)
        return msg + "\n", 0 if ok else 1

    def usermod(self, argv, cwd, env):
        """usermod [-aG group1,group2] [-s shell] username"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        if actor and not um.is_admin(actor):
            return "usermod: Permission denied. Requires root/sudo.\n", 1

        flags      = {}
        positional = []
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in ("-G", "-aG", "-s") and i + 1 < len(argv):
                flags[a] = argv[i + 1]; i += 2
            elif a.startswith("-"): i += 1
            else: positional.append(a); i += 1

        if not positional:
            return "usermod: missing username\nUsage: usermod [-aG groups] [-s shell] username\n", 1

        username = positional[0]
        add_groups = None
        if "-G" in flags or "-aG" in flags:
            raw = flags.get("-aG", flags.get("-G", ""))
            add_groups = [g.strip() for g in raw.split(",") if g.strip()]
        new_shell = flags.get("-s")

        ok, msg = um.modify_user(username, add_groups=add_groups, new_shell=new_shell)
        return msg + "\n", 0 if ok else 1

    def passwd(self, argv, cwd, env):
        """passwd [username]  — interactively change password (PyOS version sets directly)"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        target = argv[1] if len(argv) > 1 else actor
        if not target:
            return "passwd: no user specified\n", 1
        if target != actor and not um.is_admin(actor):
            return f"passwd: Permission denied. Only root can change another user's password.\n", 1
        new_pw = argv[2] if len(argv) > 2 else "changeme"
        ok, msg = um.change_password(target, new_pw)
        return msg + "\n", 0 if ok else 1

    def groupadd(self, argv, cwd, env):
        """groupadd groupname"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        if actor and not um.is_admin(actor):
            return "groupadd: Permission denied. Requires root/sudo.\n", 1
        if len(argv) < 2:
            return "groupadd: missing group name\n", 1
        ok, msg = um.create_group(argv[1])
        return msg + "\n", 0 if ok else 1

    def groupdel(self, argv, cwd, env):
        """groupdel groupname"""
        from user_manager import get_user_manager
        actor = env.get("PYOS_USER", "")
        um    = get_user_manager()
        if actor and not um.is_admin(actor):
            return "groupdel: Permission denied. Requires root/sudo.\n", 1
        if len(argv) < 2:
            return "groupdel: missing group name\n", 1
        ok, msg = um.delete_group(argv[1])
        return msg + "\n", 0 if ok else 1

    def groups(self, argv, cwd, env):
        """groups [username]  — show group memberships"""
        from user_manager import get_user_manager
        um     = get_user_manager()
        target = argv[1] if len(argv) > 1 else env.get("PYOS_USER", "")
        if not target:
            return "groups: no user\n", 1
        grps = um.user_groups(target)
        if not grps:
            user = um.get_user(target)
            if user is None:
                return f"groups: '{target}': no such user\n", 1
        return f"{target} : " + " ".join(grps) + "\n", 0

    def id_cmd(self, argv, cwd, env):
        """id [username]  — print user and group ids"""
        from user_manager import get_user_manager
        um     = get_user_manager()
        target = argv[1] if len(argv) > 1 else env.get("PYOS_USER", "")
        if not target:
            return "id: no user\n", 1
        user = um.get_user(target)
        if not user:
            return f"id: '{target}': no such user\n", 1
        group_parts = []
        for gname in user.groups:
            g = um.get_group(gname)
            if g: group_parts.append(f"{g.gid}({gname})")
        gid_str = group_parts[0] if group_parts else "100(users)"
        groups_str = ",".join(group_parts)
        return f"uid={user.uid}({user.username}) gid={gid_str} groups={groups_str}\n", 0

    def su(self, argv, cwd, env):
        """su username [password]  — switch user in terminal"""
        from user_manager import get_user_manager
        um = get_user_manager()
        if len(argv) < 2:
            return "su: specify username\nUsage: su <username> [password]\n", 1
        username = argv[1]
        password = argv[2] if len(argv) > 2 else ""
        user = um.authenticate(username, password)
        if user:
            env["PYOS_USER"] = user.username
            env["HOME"]      = user.home_dir or os.path.expanduser("~")
            return (f"\x1b[1;32mSwitched to user '{user.username}'"
                    f"  (uid={user.uid}  groups={','.join(user.groups)})\x1b[0m\n"), 0
        return f"su: Authentication failure for '{username}'\n", 1

    def cat_passwd(self, argv, cwd, env):
        """Alias: getent passwd  /  cat /etc/passwd — list all PyOS users"""
        from user_manager import get_user_manager
        um    = get_user_manager()
        lines = []
        for u in um.list_users():
            lines.append(
                f"{u.username}:x:{u.uid}:{u.uid}:{u.username}:{u.home_dir}:{u.shell}"
            )
        return "\n".join(lines) + "\n", 0

    def cat_group(self, argv, cwd, env):
        """Alias: getent group  /  cat /etc/group — list all PyOS groups"""
        from user_manager import get_user_manager
        um    = get_user_manager()
        lines = []
        for g in um.list_groups():
            lines.append(f"{g.groupname}:x:{g.gid}:{','.join(g.members)}")
        return "\n".join(lines) + "\n", 0

    # ── man / help ────────────────────────────────────────────────

    _MAN = {
        "ls":        "ls [-la] [-h] [dir]\n  -l long  -a all  -h human sizes  -lh combined",
        "cat":       "cat [file...]\n  Concatenate and display files.",
        "touch":     "touch file...\n  Create empty files or update timestamps.",
        "mkdir":     "mkdir [-p] dir...\n  Create directories.",
        "rm":        "rm [-r] [-rf] file...\n  Remove files. -r for directories.",
        "cp":        "cp [-r] src dst\n  Copy files or directories.",
        "mv":        "mv src dst\n  Move or rename.",
        "grep":      "grep [-i] [-v] [-n] [-c] [-l] pattern file...\n  Search for pattern.",
        "find":      "find [dir] [-name pat] [-type f|d] [-maxdepth N]\n  Find files.",
        "head":      "head [-n N] file\n  First N lines (default 10).",
        "tail":      "tail [-n N] [-f] file\n  Last N lines (default 10).",
        "wc":        "wc [-l] [-w] [-c] file...\n  Count lines, words, chars.",
        "sort":      "sort [-r] [-n] [-u] file\n  Sort lines. -n numeric, -u unique.",
        "uniq":      "uniq [-c] [-d] [-u] file\n  Filter duplicate lines.",
        "cut":       "cut -d DELIM -f FIELDS file\n  Extract fields from lines.",
        "diff":      "diff FILE1 FILE2\n  Show unified diff between two files.",
        "seq":       "seq [FIRST [INCR]] LAST\n  Print sequence of numbers.",
        "echo":      "echo [-n] text\n  Print text.",
        "printf":    "printf FORMAT [ARGS...]\n  Print formatted text.",
        "pwd":       "pwd\n  Print working directory.",
        "env":       "env\n  Show environment variables.",
        "export":    "export KEY=VALUE\n  Set environment variable.",
        "unset":     "unset KEY\n  Remove environment variable.",
        "date":      "date [+format]\n  Show current date/time.",
        "uname":     "uname [-a|-r|-m|-s]\n  System information.",
        "whoami":    "whoami\n  Current username.",
        "hostname":  "hostname\n  Show system hostname.",
        "chmod":     "chmod OCTAL file...\n  Change file permissions (e.g. chmod 755 file).",
        "chown":     "chown OWNER[:GRP] file...\n  Change file ownership (simulated).",
        "stat":      "stat file...\n  Show detailed file info.",
        "ln":        "ln [-s] TARGET LINK\n  Create hard or symbolic link.",
        "readlink":  "readlink [-f] FILE\n  Read symlink target.",
        "realpath":  "realpath PATH\n  Resolve path to absolute.",
        "basename":  "basename PATH [SUFFIX]\n  Strip directory and optional suffix.",
        "dirname":   "dirname PATH\n  Strip filename.",
        "df":        "df [-h]\n  Disk free space.",
        "du":        "du [-h] [-s] [dir]\n  Disk usage.",
        "free":      "free [-h]\n  Memory usage.",
        "uptime":    "uptime\n  System uptime and load.",
        "ps":        "ps [aux]\n  Running processes.",
        "kill":      "kill [-SIGNAL] PID...\n  Send signal to process.",
        "lsof":      "lsof\n  List open files (via psutil).",
        "ping":      "ping [-c N] HOST\n  ICMP ping.",
        "ifconfig":  "ifconfig\n  Network interfaces.",
        "ip":        "ip [addr|link|route]\n  Network info.",
        "netstat":   "netstat [-t|-u|-l]\n  Network connections.",
        "ss":        "ss [-t|-u|-l]\n  Socket statistics (alias for netstat).",
        "md5sum":    "md5sum file...\n  Compute MD5 checksums.",
        "sha256sum": "sha256sum file...\n  Compute SHA-256 checksums.",
        "base64":    "base64 [-d] [file]\n  Encode/decode base64.",
        "awk":       "awk '{print $N}' file\n  Field processor (minimal).",
        "sed":       "sed 's/PAT/REP/[g]' file\n  Stream editor (substitution).",
        "tee":       "tee [-a] FILE\n  Copy piped data to file.",
        "file":      "file FILE...\n  Detect file type.",
        "watch":     "watch [-n N] CMD\n  Run command once (loop unsupported).",
        "timeout":   "timeout SECS CMD\n  Run command with time limit.",
        "sleep":     "sleep SECS\n  Pause (max 10s).",
        "alias":     "alias [name=value]\n  Define or list aliases.",
        "unalias":   "unalias name\n  Remove alias.",
        "nohup":     "nohup COMMAND\n  Run command ignoring hangup.",
        "useradd":   "useradd [-G groups] [-s shell] [-p password] username",
        "userdel":   "userdel username",
        "usermod":   "usermod [-aG groups] [-s shell] username",
        "passwd":    "passwd [username] [new_password]",
        "groupadd":  "groupadd groupname",
        "groupdel":  "groupdel groupname",
        "groups":    "groups [username]",
        "id":        "id [username]",
        "su":        "su username [password]",
        "nano":      "nano [file]\n  Open PyOS built-in text editor.\n  Ctrl+X exit  Ctrl+O save  Ctrl+W search  Ctrl+\\ replace\n  Ctrl+K cut line  Ctrl+U paste  Ctrl+_ go-to-line",
        "vi":        "vi [file]\n  Alias for nano (built-in editor).",
        "vim":       "vim [file]\n  Alias for nano (built-in editor).",
        "python3":   "python3 [script]",
        "clear":     "clear\n  Clear the screen.",
        "history":   "history\n  Show command history.",
        "cd":        "cd [dir]\n  Change directory.",
    }

    def man(self, argv, cwd, env):
        if len(argv) < 2:
            cmds = sorted(self._MAN.keys())
            cols = 6
            rows = [cmds[i:i+cols] for i in range(0, len(cmds), cols)]
            table = "\n".join("  ".join(f"{c:<14}" for c in row) for row in rows)
            return f"Built-in commands ({len(cmds)} total):\n{table}\n\nType: man <command>\n", 0
        cmd = argv[1]
        if cmd in self._MAN:
            return f"\x1b[1;33m{cmd}\x1b[0m\n{self._MAN[cmd]}\n", 0
        return f"man: no entry for '{cmd}'\n", 1

    def help(self, argv, cwd, env):
        return self.man(["man"], cwd, env)


_BUILTINS = _Builtins()

_CMD_MAP: dict[str, callable] = {
    # ── Core filesystem ──
    "ls":         _BUILTINS.ls,
    "dir":        _BUILTINS.ls,
    "cat":        _BUILTINS.cat,
    "touch":      _BUILTINS.touch,
    "mkdir":      _BUILTINS.mkdir,
    "md":         _BUILTINS.mkdir,
    "rm":         _BUILTINS.rm,
    "del":        _BUILTINS.rm,
    "rmdir":      _BUILTINS.rmdir,
    "rd":         _BUILTINS.rmdir,
    "cp":         _BUILTINS.cp,
    "copy":       _BUILTINS.cp,
    "mv":         _BUILTINS.mv,
    "move":       _BUILTINS.mv,
    "pwd":        _BUILTINS.pwd,
    "echo":       _BUILTINS.echo,
    "printf":     _BUILTINS.printf_cmd,
    # ── NEW: file meta ──
    "chmod":      _BUILTINS.chmod,
    "chown":      _BUILTINS.chown,
    "stat":       _BUILTINS.stat,
    "ln":         _BUILTINS.ln,
    "readlink":   _BUILTINS.readlink,
    "realpath":   _BUILTINS.realpath,
    "basename":   _BUILTINS.basename_cmd,
    "dirname":    _BUILTINS.dirname_cmd,
    "file":       _BUILTINS.file_cmd,
    # ── Search & text ──
    "grep":       _BUILTINS.grep,
    "find":       _BUILTINS.find,
    "head":       _BUILTINS.head,
    "tail":       _BUILTINS.tail,
    "wc":         _BUILTINS.wc,
    "sort":       _BUILTINS.sort,
    "uniq":       _BUILTINS.uniq,
    "cut":        _BUILTINS.cut,
    "diff":       _BUILTINS.diff,
    "tr":         _BUILTINS.tr_cmd,
    "tee":        _BUILTINS.tee,
    "awk":        _BUILTINS.awk,
    "sed":        _BUILTINS.sed,
    "less":       _BUILTINS.cat,
    "more":       _BUILTINS.cat,
    # ── System info ──
    "env":        _BUILTINS.env,
    "export":     _BUILTINS.export,
    "unset":      _BUILTINS.unset,
    "whoami":     _BUILTINS.whoami,
    "hostname":   _BUILTINS.hostname,
    "uname":      _BUILTINS.uname,
    "date":       _BUILTINS.date,
    "which":      _BUILTINS.which,
    "df":         _BUILTINS.df,
    "du":         _BUILTINS.du,
    "free":       _BUILTINS.free,
    "uptime":     _BUILTINS.uptime,
    "ps":         _BUILTINS.ps,
    "kill":       _BUILTINS.kill,
    "lsof":       _BUILTINS.lsof,
    # ── Utilities ──
    "seq":        _BUILTINS.seq,
    "sleep":      _BUILTINS.sleep,
    "md5sum":     _BUILTINS.md5sum,
    "sha256sum":  _BUILTINS.sha256sum,
    "base64":     _BUILTINS.base64_cmd,
    "watch":      _BUILTINS.watch,
    "timeout":    _BUILTINS.timeout_cmd,
    "alias":      _BUILTINS.alias,
    "unalias":    _BUILTINS.unalias,
    "nohup":      _BUILTINS.nohup,
    # ── Network ──
    "ping":       _BUILTINS.ping,
    "ifconfig":   _BUILTINS.ifconfig,
    "ip":         _BUILTINS.ip_cmd,
    "netstat":    _BUILTINS.netstat,
    "ss":         _BUILTINS.ss,
    # ── Help ──
    "man":        _BUILTINS.man,
    "help":       _BUILTINS.help,
    # ── User management ──
    "useradd":    _BUILTINS.useradd,
    "adduser":    _BUILTINS.useradd,
    "userdel":    _BUILTINS.userdel,
    "deluser":    _BUILTINS.userdel,
    "usermod":    _BUILTINS.usermod,
    "passwd":     _BUILTINS.passwd,
    "chpasswd":   _BUILTINS.passwd,
    "groupadd":   _BUILTINS.groupadd,
    "addgroup":   _BUILTINS.groupadd,
    "groupdel":   _BUILTINS.groupdel,
    "delgroup":   _BUILTINS.groupdel,
    "groups":     _BUILTINS.groups,
    "id":         _BUILTINS.id_cmd,
    "su":         _BUILTINS.su,
}


def _is_virtual_path(path: str) -> bool:
    return path in ("/etc/passwd", "/etc/group")


def run_builtin(line: str, cwd: str, env: dict) -> tuple[str | None, int]:
    argv = _split_args(line.strip())
    if not argv:
        return ("", 0)
    cmd  = argv[0].lower()
    fn   = _CMD_MAP.get(cmd)

    # Special case: cat /etc/passwd  or  cat /etc/group
    if cmd == "cat" and len(argv) >= 2:
        if argv[1] == "/etc/passwd":
            return _BUILTINS.cat_passwd(argv, cwd, env)
        if argv[1] == "/etc/group":
            return _BUILTINS.cat_group(argv, cwd, env)

    # Alias resolution
    alias_val = env.get(f"__ALIAS__{cmd}")
    if alias_val and fn is None:
        return run_builtin(alias_val + " " + " ".join(argv[1:]), cwd, env)

    if fn is None:
        return (None, -1)
    try:
        out, rc = fn(argv, cwd, env)
        return out, rc
    except Exception as ex:
        return f"{cmd}: unexpected error: {ex}\n", 1


# ── System-shell fallback ─────────────────────────────────────────────────

from PyQt6.QtCore import QThread, pyqtSignal


class CommandWorker(QThread):
    outputReady = pyqtSignal(str)
    finished    = pyqtSignal(int)

    def __init__(self, cmd, cwd, env, parent=None):
        super().__init__(parent)
        self._cmd = cmd; self._cwd = cwd; self._env = env
        self._proc = None; self._killed = False

    def kill(self):
        self._killed = True
        if not self._proc: return
        try:
            if _IS_LINUX:
                import signal as _sig
                os.killpg(os.getpgid(self._proc.pid), _sig.SIGINT)
            else: self._proc.terminate()
        except Exception:
            try: self._proc.kill()
            except Exception: pass

    def run(self):
        if _IS_LINUX: self._run_pty()
        elif _IS_WINDOWS: self._run_win()
        else: self._run_pipe(["/bin/bash", "-c", self._cmd])

    def _run_pty(self):
        mfd, sfd = _pty.openpty()
        env = {**self._env, "TERM": "xterm-256color", "COLUMNS": "200", "LINES": "50"}
        try:
            self._proc = subprocess.Popen(
                ["/bin/bash", "-c", self._cmd],
                stdin=sfd, stdout=sfd, stderr=sfd,
                close_fds=True, cwd=self._cwd, env=env,
                preexec_fn=os.setsid,
            )
            os.close(sfd)
            while self._proc.poll() is None:
                try:
                    r, _, _ = _select.select([mfd], [], [], 0.05)
                    if r:
                        d = os.read(mfd, 4096)
                        if d: self.outputReady.emit(d.decode("utf-8", errors="replace"))
                except OSError: break
            try:
                while True:
                    r, _, _ = _select.select([mfd], [], [], 0.05)
                    if r:
                        d = os.read(mfd, 4096)
                        if d: self.outputReady.emit(d.decode("utf-8", errors="replace"))
                    else: break
            except Exception: pass
            self.finished.emit(0 if self._killed else (self._proc.returncode or 0))
        except Exception as ex:
            self.outputReady.emit(f"[error] {ex}\n"); self.finished.emit(1)
        finally:
            try: os.close(mfd)
            except Exception: pass

    def _run_win(self):
        for args in [
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", self._cmd],
            ["cmd.exe", "/C", self._cmd],
        ]:
            try: self._run_pipe(args); return
            except FileNotFoundError: continue
        self.outputReady.emit("[error] no shell found\n"); self.finished.emit(1)

    def _run_pipe(self, args):
        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      cwd=self._cwd, env=self._env,
                      encoding="utf-8", errors="replace", bufsize=1)
        if _IS_WINDOWS: kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else: kwargs["start_new_session"] = True
        self._proc = subprocess.Popen(args, **kwargs)
        for line in self._proc.stdout: self.outputReady.emit(line)
        self._proc.stdout.close()
        rc = self._proc.wait()
        self.finished.emit(0 if self._killed else rc)


# ── Nano editor ───────────────────────────────────────────────────────────

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import (
    QKeyEvent, QTextCursor, QFont, QColor, QTextCharFormat,
    QSyntaxHighlighter, QKeySequence,
    QPainter, QLinearGradient, QBrush, QPen,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPlainTextEdit, QLineEdit, QPushButton,
    QLabel, QTabWidget, QDialog, QMessageBox,
    QInputDialog, QApplication, QFrame,
)


class _NanoHighlighter(QSyntaxHighlighter):
    """Minimal syntax highlighting for common file types inside nano."""

    _PY_KEYWORDS = (
        r'\b(def|class|return|import|from|if|elif|else|for|while|try|except'
        r'|finally|with|as|pass|break|continue|lambda|yield|None|True|False'
        r'|and|or|not|in|is|del|raise|global|nonlocal|assert|async|await)\b'
    )

    def __init__(self, doc, file_ext: str = ""):
        super().__init__(doc)
        self._ext = file_ext.lower().lstrip(".")
        self._rules = []
        self._build_rules()

    def _fmt(self, color: str, bold: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(700)
        return f

    def _build_rules(self):
        ext = self._ext
        if ext in ("py", "pyw"):
            self._rules += [
                (re.compile(self._PY_KEYWORDS), self._fmt("#cc99cd", True)),
                (re.compile(r'#[^\n]*'), self._fmt("#6a9955")),
                (re.compile(r'"""[\s\S]*?"""'), self._fmt("#ce9178")),
                (re.compile(r"'''[\s\S]*?'''"), self._fmt("#ce9178")),
                (re.compile(r'"[^"\n]*"'), self._fmt("#ce9178")),
                (re.compile(r"'[^'\n]*'"), self._fmt("#ce9178")),
                (re.compile(r'\b\d+\.?\d*\b'), self._fmt("#b5cea8")),
            ]
        elif ext in ("js", "ts", "jsx", "tsx"):
            self._rules += [
                (re.compile(
                    r'\b(const|let|var|function|return|if|else|for|while|class'
                    r'|import|export|from|async|await|new|this|typeof|null|undefined'
                    r'|true|false|try|catch|finally|throw)\b'), self._fmt("#569cd6", True)),
                (re.compile(r'//[^\n]*'), self._fmt("#6a9955")),
                (re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`]*`'), self._fmt("#ce9178")),
                (re.compile(r'\b\d+\.?\d*\b'), self._fmt("#b5cea8")),
            ]
        elif ext in ("html", "htm", "xml"):
            self._rules += [
                (re.compile(r'<[^>]+>'), self._fmt("#569cd6")),
                (re.compile(r'"[^"]*"'), self._fmt("#ce9178")),
                (re.compile(r'<!--[\s\S]*?-->'), self._fmt("#6a9955")),
            ]
        elif ext in ("css", "scss", "less"):
            self._rules += [
                (re.compile(r'[.#][\w-]+'), self._fmt("#d7ba7d")),
                (re.compile(r'[\w-]+\s*:'), self._fmt("#9cdcfe")),
                (re.compile(r'"[^"]*"|\'[^\']*\''), self._fmt("#ce9178")),
                (re.compile(r'/\*[\s\S]*?\*/'), self._fmt("#6a9955")),
                (re.compile(r'#[0-9a-fA-F]{3,8}'), self._fmt("#b5cea8")),
            ]
        elif ext in ("sh", "bash", "zsh"):
            self._rules += [
                (re.compile(
                    r'\b(if|then|else|elif|fi|for|do|done|while|case|esac'
                    r'|function|return|export|source|echo|exit)\b'), self._fmt("#569cd6", True)),
                (re.compile(r'#[^\n]*'), self._fmt("#6a9955")),
                (re.compile(r'"[^"]*"|\'[^\']*\''), self._fmt("#ce9178")),
                (re.compile(r'\$\w+|\$\{[^}]+\}'), self._fmt("#9cdcfe")),
            ]
        elif ext in ("json",):
            self._rules += [
                (re.compile(r'"[^"]*"\s*:'), self._fmt("#9cdcfe")),
                (re.compile(r':\s*"[^"]*"'), self._fmt("#ce9178")),
                (re.compile(r'\b(true|false|null)\b'), self._fmt("#569cd6", True)),
                (re.compile(r'\b\d+\.?\d*\b'), self._fmt("#b5cea8")),
            ]
        # Generic: strings and numbers for all other types
        if not self._rules:
            self._rules += [
                (re.compile(r'"[^"]*"|\'[^\']*\''), self._fmt("#ce9178")),
                (re.compile(r'\b\d+\.?\d*\b'), self._fmt("#b5cea8")),
                (re.compile(r'#[^\n]*'), self._fmt("#6a9955")),
            ]

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class _NanoTitleBar(QWidget):
    """Custom painted title bar for the nano editor — gradient + file info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._filename   = "New Buffer"
        self._version    = "5.9"
        self._modified   = False

    def set_title(self, filename: str, version: str, modified: bool):
        self._filename  = filename
        self._version   = version
        self._modified  = modified
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Gradient background
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(0x1e, 0x1a, 0x35))
        grad.setColorAt(0.5, QColor(0x25, 0x20, 0x42))
        grad.setColorAt(1.0, QColor(0x1e, 0x1a, 0x35))
        p.fillRect(0, 0, w, h, grad)

        # Bottom border accent line
        accent = QLinearGradient(0, 0, w, 0)
        accent.setColorAt(0.0, QColor(0xcb, 0xa6, 0xf7, 0))
        accent.setColorAt(0.3, QColor(0xcb, 0xa6, 0xf7, 200))
        accent.setColorAt(0.7, QColor(0x89, 0xb4, 0xfa, 200))
        accent.setColorAt(1.0, QColor(0x89, 0xb4, 0xfa, 0))
        p.fillRect(0, h - 1, w, 1, accent)

        # "nano" pill on the left
        pill_x, pill_y, pill_w, pill_h = 10, 6, 52, 22
        pill_grad = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
        pill_grad.setColorAt(0, QColor(0xcb, 0xa6, 0xf7))
        pill_grad.setColorAt(1, QColor(0x89, 0xb4, 0xfa))
        p.setBrush(QBrush(pill_grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 5, 5)
        p.setPen(QPen(QColor(0x13, 0x13, 0x1f)))
        fnt = QFont("Cascadia Code", 10)
        fnt.setBold(True)
        p.setFont(fnt)
        p.drawText(QRect(pill_x, pill_y, pill_w, pill_h), Qt.AlignmentFlag.AlignCenter, "nano")

        # Version
        p.setPen(QPen(QColor(0x6c, 0x70, 0x86)))
        fnt2 = QFont("Segoe UI", 9)
        p.setFont(fnt2)
        p.drawText(QRect(pill_x + pill_w + 6, 0, 60, h), Qt.AlignmentFlag.AlignVCenter, f"v{self._version}")

        # Filename in center
        p.setPen(QPen(QColor(0xcd, 0xd6, 0xf4)))
        fnt3 = QFont("Cascadia Code", 11)
        fnt3.setBold(True)
        p.setFont(fnt3)
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self._filename)

        # Modified badge on the right
        if self._modified:
            badge_text = "● Modified"
            badge_x = w - 100
            p.setPen(QPen(QColor(0xf3, 0x8b, 0xa8)))
            fnt4 = QFont("Segoe UI", 9)
            p.setFont(fnt4)
            p.drawText(QRect(badge_x, 0, 90, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, badge_text)


class _NanoStatusBar(QWidget):
    """Custom painted status bar — shows cursor position and messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self._msg       = ""
        self._msg_error = False
        self._line      = 1
        self._col       = 1
        self._total     = 1
        self._pct       = 0
        self._modified  = False
        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(True)
        self._msg_timer.timeout.connect(self._clear_msg)

    def show_message(self, msg: str, error: bool = False):
        self._msg       = msg
        self._msg_error = error
        self.update()
        self._msg_timer.start(4000)

    def set_position(self, line, col, total, pct, modified):
        self._line     = line
        self._col      = col
        self._total    = total
        self._pct      = pct
        self._modified = modified
        self.update()

    def _clear_msg(self):
        self._msg = ""
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor(0x0a, 0x0a, 0x14))
        # Top border
        p.fillRect(0, 0, w, 1, QColor(0x1e, 0x1e, 0x30))

        fnt = QFont("Cascadia Code", 10)
        p.setFont(fnt)

        # Left: message or empty
        if self._msg:
            color = QColor(0xf3, 0x8b, 0xa8) if self._msg_error else QColor(0xa6, 0xe3, 0xa1)
            p.setPen(QPen(color))
            p.drawText(QRect(12, 0, w // 2, h), Qt.AlignmentFlag.AlignVCenter, self._msg)

        # Right: position info chips
        right_text = f"Ln {self._line}/{self._total}  Col {self._col}  {self._pct}%"
        p.setPen(QPen(QColor(0x45, 0x47, 0x5a)))
        p.drawText(QRect(0, 0, w - 12, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, right_text)


class NanoEditor(QDialog):
    """
    Full GNU nano-style text editor built into the PyOS terminal.

    Keyboard shortcuts (same as real nano):
      Ctrl+X  — Exit (asks to save if modified)
      Ctrl+O  — Write/save file
      Ctrl+W  — Search (Find)
      Ctrl+\\  — Search & Replace
      Ctrl+K  — Cut current line
      Ctrl+U  — Paste (uncut) cut line
      Ctrl+G  — Help
      Ctrl+C  — Show cursor position
      Ctrl+A  — Go to beginning of line
      Ctrl+E  — Go to end of line
      Ctrl+Y  — Scroll up one page
      Ctrl+V  — Scroll down one page
      Ctrl+_  — Go to specific line number
      Ctrl+Z  — Undo
      Alt+U   — Undo (alternative)
    """

    _NANO_VERSION = "5.9"

    _SHORTCUTS_ROW1 = [
        ("^G", "Help"),   ("^O", "Write"), ("^W", "Search"), ("^K", "Cut"),
        ("^C", "Pos"),    ("^X", "Exit"),
    ]
    _SHORTCUTS_ROW2 = [
        ("^R", "Read"),   ("^\\", "Replace"), ("^Y", "Prev"),  ("^U", "Paste"),
        ("^T", "Spell"),  ("^V", "Next"),
    ]

    def __init__(self, filepath: str, cwd: str, parent=None):
        super().__init__(parent)
        self._cwd      = cwd
        self._saved    = False
        self._clipboard_line: str = ""

        # Resolve path
        if filepath:
            self._filepath = os.path.normpath(os.path.join(cwd, os.path.expanduser(filepath)))
        else:
            self._filepath = ""

        self._filename = os.path.basename(self._filepath) if self._filepath else "New Buffer"
        self._ext      = os.path.splitext(self._filename)[1].lstrip(".")
        self._modified = False

        self.setWindowTitle(f"GNU nano — {self._filename}")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(920, 640)
        self.setStyleSheet("""
            QDialog  { background:#0f0f1a; }
            QWidget  { background:#0f0f1a; color:#cdd6f4; }
        """)

        self._build_ui()
        self._load_file()
        self._editor.setFocus()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Title bar (custom painted widget) ────────────────────
        self._title_bar = _NanoTitleBar(self)
        self._update_title()
        root.addWidget(self._title_bar)

        # ─── Editor area ──────────────────────────────────────────
        editor_row = QHBoxLayout()
        editor_row.setSpacing(0)
        editor_row.setContentsMargins(0, 0, 0, 0)

        # Line number gutter
        self._gutter = QPlainTextEdit()
        self._gutter.setReadOnly(True)
        self._gutter.setFixedWidth(54)
        self._gutter.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gutter.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gutter.setStyleSheet(
            "QPlainTextEdit {"
            "  background:#0a0a14;"
            "  color:#3d3f5c;"
            "  border:none;"
            "  border-right: 1px solid #1e1e30;"
            "  font-family:'Cascadia Code','JetBrains Mono','Consolas','Courier New',monospace;"
            "  font-size:13px;"
            "  padding:4px 0 4px 0;"
            "  selection-background-color: transparent;"
            "}"
        )
        editor_row.addWidget(self._gutter)

        # Thin accent line between gutter and editor
        accent_line = QFrame()
        accent_line.setFixedWidth(2)
        accent_line.setStyleSheet("background: qlineargradient(y1:0,y2:1, stop:0 #cba6f7, stop:0.5 #89b4fa, stop:1 #cba6f7); border:none;")
        editor_row.addWidget(accent_line)

        # Main editor
        self._editor = QPlainTextEdit()
        self._editor.setStyleSheet(
            "QPlainTextEdit {"
            "  background:#13131f;"
            "  color:#cdd6f4;"
            "  border:none;"
            "  font-family:'Cascadia Code','JetBrains Mono','Consolas','Courier New',monospace;"
            "  font-size:13px;"
            "  padding:4px 12px;"
            "  selection-background-color:#313244;"
            "  selection-color:#cdd6f4;"
            "}"
            "QScrollBar:vertical {"
            "  background:#0a0a14;"
            "  width:7px;"
            "  border-radius:3px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background:#2d2d44;"
            "  border-radius:3px;"
            "  min-height:20px;"
            "}"
            "QScrollBar::handle:vertical:hover { background:#585b70; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
            "QScrollBar:horizontal { height:7px; background:#0a0a14; border-radius:3px; }"
            "QScrollBar::handle:horizontal { background:#2d2d44; border-radius:3px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }"
        )
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setTabStopDistance(28)
        self._editor.installEventFilter(self)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.cursorPositionChanged.connect(self._update_status)
        self._editor.verticalScrollBar().valueChanged.connect(self._sync_gutter_scroll)
        editor_row.addWidget(self._editor, 1)

        root.addLayout(editor_row, 1)

        # ─── Status bar ───────────────────────────────────────────
        self._status_bar = _NanoStatusBar(self)
        root.addWidget(self._status_bar)

        # ─── Shortcuts bar (2 rows, redesigned) ───────────────────
        shortcuts_wrap = QWidget()
        shortcuts_wrap.setFixedHeight(54)
        shortcuts_wrap.setStyleSheet("background:#0a0a14; border-top:1px solid #1e1e30;")
        sw_lay = QVBoxLayout(shortcuts_wrap)
        sw_lay.setContentsMargins(8, 4, 8, 4)
        sw_lay.setSpacing(3)

        for row_def in (self._SHORTCUTS_ROW1, self._SHORTCUTS_ROW2):
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(2)
            for key, label in row_def:
                # Key badge
                key_lbl = QLabel(key)
                key_lbl.setStyleSheet(
                    "color:#13131f;"
                    "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                    "  stop:0 #cba6f7, stop:1 #89b4fa);"
                    "font-weight:700;"
                    "font-size:10px;"
                    "padding:1px 5px;"
                    "border-radius:3px;"
                )
                key_lbl.setFixedWidth(30)
                key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Action label
                act_lbl = QLabel(label)
                act_lbl.setStyleSheet(
                    "color:#6c7086;"
                    "font-size:11px;"
                    "background:transparent;"
                    "padding-right:10px;"
                )
                row_l.addWidget(key_lbl)
                row_l.addWidget(act_lbl)
            row_l.addStretch()
            sw_lay.addWidget(row_w)

        root.addWidget(shortcuts_wrap)

        # Apply syntax highlighter
        self._highlighter = _NanoHighlighter(self._editor.document(), self._ext)

        # Sync gutter on first paint
        QTimer.singleShot(0, self._refresh_gutter)

    # ── File I/O ───────────────────────────────────────────────────────

    def _load_file(self):
        if self._filepath and os.path.isfile(self._filepath):
            try:
                content = open(self._filepath, encoding="utf-8", errors="replace").read()
                self._editor.setPlainText(content)
                self._modified = False
                self._show_status(f'Read {len(content.splitlines())} lines')
            except Exception as e:
                self._show_status(f"Error reading file: {e}", error=True)
        else:
            self._editor.setPlainText("")
            if self._filepath:
                self._show_status("New file")

    def _save_file(self, path: str = None) -> bool:
        target = path or self._filepath
        if not target:
            self._ask_filename()
            return self._saved
        try:
            content = self._editor.toPlainText()
            open(target, "w", encoding="utf-8").write(content)
            self._filepath = target
            self._filename = os.path.basename(target)
            self._modified = False
            self._update_title()
            lines = content.count("\n") + 1
            self._show_status(f'Wrote {lines} lines to "{self._filename}"')
            self._saved = True
            return True
        except Exception as e:
            self._show_status(f"Error writing file: {e}", error=True)
            return False

    def _ask_filename(self):
        text, ok = QInputDialog.getText(
            self, "Write File", "File name to write:",
            text=self._filename or ""
        )
        if ok and text.strip():
            path = os.path.normpath(os.path.join(self._cwd, text.strip()))
            self._save_file(path)

    # ── UI helpers ─────────────────────────────────────────────────────

    def _update_title(self):
        mod = " [Modified]" if self._modified else ""
        fname = 'New Buffer' if not self._filename else self._filename
        text = f"GNU nano {self._NANO_VERSION}   {fname}{mod}"
        if hasattr(self, '_title_bar') and isinstance(self._title_bar, _NanoTitleBar):
            self._title_bar.set_title(fname, self._NANO_VERSION, self._modified)
        elif hasattr(self, '_title_bar'):
            self._title_bar.setText(f"  {text}  ")

    def _show_status(self, msg: str, error: bool = False):
        if hasattr(self, '_status_bar') and isinstance(self._status_bar, _NanoStatusBar):
            self._status_bar.show_message(msg, error)
        else:
            color = "#f38ba8" if error else "#a6e3a1"
            self._status_bar.setStyleSheet(
                f"background:#313244; color:{color}; font-size:11px; padding:2px 8px;"
            )
            self._status_bar.setText(msg)
            QTimer.singleShot(4000, lambda: self._status_bar.setText(""))

    def _update_status(self):
        cur   = self._editor.textCursor()
        line  = cur.blockNumber() + 1
        col   = cur.columnNumber() + 1
        total = self._editor.document().blockCount()
        pct   = int(line / max(total, 1) * 100)
        if hasattr(self, '_status_bar') and isinstance(self._status_bar, _NanoStatusBar):
            self._status_bar.set_position(line, col, total, pct, self._modified)
        else:
            self._status_bar.setStyleSheet(
                "background:#313244; color:#89dceb; font-size:11px; padding:2px 8px;"
            )
            self._status_bar.setText(
                f"  Line {line}/{total}, Col {col}  ({pct}%)  "
                f"{'[Modified]' if self._modified else ''}  "
            )
        self._refresh_gutter()

    def _on_text_changed(self):
        if not self._modified:
            self._modified = True
            self._update_title()
        self._refresh_gutter()

    def _refresh_gutter(self):
        first_visible = self._editor.firstVisibleBlock().blockNumber()
        count = self._editor.document().blockCount()
        last_visible = min(first_visible + 60, count)
        numbers = "\n".join(
            f"{n + 1:>4}" for n in range(first_visible, last_visible)
        )
        old = self._gutter.blockSignals(True)
        self._gutter.setPlainText(numbers)
        self._gutter.blockSignals(old)
        # Sync scroll position
        sb_e = self._editor.verticalScrollBar()
        sb_g = self._gutter.verticalScrollBar()
        sb_g.setValue(sb_e.value() % max(sb_g.maximum() + 1, 1))

    def _sync_gutter_scroll(self, _val):
        self._refresh_gutter()

    # ── Keyboard shortcuts ─────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is not self._editor or not isinstance(event, QKeyEvent):
            return super().eventFilter(obj, event)

        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        alt  = event.modifiers() & Qt.KeyboardModifier.AltModifier
        key  = event.key()

        if ctrl:
            if key == Qt.Key.Key_X:           # ^X — Exit
                self._action_exit(); return True
            if key == Qt.Key.Key_O:           # ^O — Write/Save
                self._action_write(); return True
            if key == Qt.Key.Key_W:           # ^W — Search
                self._action_search(); return True
            if key == Qt.Key.Key_Backslash:   # ^\ — Replace
                self._action_replace(); return True
            if key == Qt.Key.Key_K:           # ^K — Cut line
                self._action_cut_line(); return True
            if key == Qt.Key.Key_U:           # ^U — Paste (uncut)
                self._action_paste_line(); return True
            if key == Qt.Key.Key_G:           # ^G — Help
                self._action_help(); return True
            if key == Qt.Key.Key_C:           # ^C — Cursor position
                self._update_status(); return True
            if key == Qt.Key.Key_A:           # ^A — Beginning of line
                self._move_cursor(QTextCursor.MoveOperation.StartOfLine); return True
            if key == Qt.Key.Key_E:           # ^E — End of line
                self._move_cursor(QTextCursor.MoveOperation.EndOfLine); return True
            if key == Qt.Key.Key_Y:           # ^Y — Page up
                self._editor.verticalScrollBar().triggerAction(
                    self._editor.verticalScrollBar().SliderAction.SliderPageStepSub)
                return True
            if key == Qt.Key.Key_V:           # ^V — Page down
                self._editor.verticalScrollBar().triggerAction(
                    self._editor.verticalScrollBar().SliderAction.SliderPageStepAdd)
                return True
            if key == Qt.Key.Key_Underscore:  # ^_ — Go to line
                self._action_goto_line(); return True
            if key == Qt.Key.Key_Z:           # ^Z — Undo
                self._editor.undo(); return True
            if key == Qt.Key.Key_S:           # ^S — Quick save
                self._action_write(); return True

        if alt and key == Qt.Key.Key_U:       # Alt+U — Undo
            self._editor.undo(); return True

        if key == Qt.Key.Key_Tab:
            cur = self._editor.textCursor()
            cur.insertText("    ")
            return True

        if key == Qt.Key.Key_Escape:
            self._show_status("Press ^X to exit, ^O to save")
            return True

        return False

    def _move_cursor(self, operation):
        cur = self._editor.textCursor()
        cur.movePosition(operation)
        self._editor.setTextCursor(cur)

    # ── Actions ────────────────────────────────────────────────────────

    def _action_exit(self):
        if self._modified:
            msg = QMessageBox(self)
            msg.setWindowTitle("nano — Save?")
            msg.setText(
                f'Save modified buffer?\n\n'
                f'File: {self._filename or "New Buffer"}'
            )
            msg.setStyleSheet(
                "QMessageBox { background:#1e1e2e; color:#cdd6f4; }"
                "QLabel { color:#cdd6f4; }"
                "QPushButton { background:#313244; color:#cdd6f4; border:1px solid #585b70;"
                " border-radius:4px; padding:5px 16px; }"
                "QPushButton:hover { background:#45475a; }"
            )
            save_btn    = msg.addButton("Save (Y)",    QMessageBox.ButtonRole.YesRole)
            discard_btn = msg.addButton("Don't Save (N)", QMessageBox.ButtonRole.NoRole)
            cancel_btn  = msg.addButton("Cancel (^C)", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(save_btn)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == cancel_btn:
                self._show_status("Cancelled")
                return
            if clicked == save_btn:
                if not self._save_file():
                    return
        self.accept()

    def _action_write(self):
        if self._filepath:
            self._save_file()
        else:
            self._ask_filename()

    def _action_search(self):
        term, ok = QInputDialog.getText(self, "Search", "Search for:")
        if not ok or not term: return
        doc  = self._editor.document()
        cur  = self._editor.textCursor()
        found = doc.find(term, cur)
        if found.isNull():
            # Wrap around
            found = doc.find(term)
        if not found.isNull():
            self._editor.setTextCursor(found)
            self._show_status(f'Found: "{term}"')
        else:
            self._show_status(f'"{term}" not found', error=True)

    def _action_replace(self):
        term, ok1 = QInputDialog.getText(self, "Search & Replace", "Search for:")
        if not ok1 or not term: return
        replacement, ok2 = QInputDialog.getText(
            self, "Search & Replace", f'Replace "{term}" with:'
        )
        if not ok2: return
        text    = self._editor.toPlainText()
        new_txt = text.replace(term, replacement)
        count   = text.count(term)
        if count:
            cur = self._editor.textCursor()
            pos = cur.position()
            self._editor.setPlainText(new_txt)
            cur = self._editor.textCursor()
            cur.setPosition(min(pos, len(new_txt)))
            self._editor.setTextCursor(cur)
            self._show_status(f'Replaced {count} occurrence(s) of "{term}"')
        else:
            self._show_status(f'"{term}" not found', error=True)

    def _action_cut_line(self):
        cur = self._editor.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor
        )
        self._clipboard_line = cur.selectedText() + "\n"
        cur.removeSelectedText()
        # Also remove the newline if not on last line
        cur2 = self._editor.textCursor()
        if not cur2.atEnd():
            cur2.deleteChar()
        self._show_status("Cut 1 line")

    def _action_paste_line(self):
        if self._clipboard_line:
            cur = self._editor.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cur.insertText(self._clipboard_line)
            self._show_status("Pasted line")
        else:
            self._show_status("Nothing to paste (clipboard empty)")

    def _action_goto_line(self):
        total = self._editor.document().blockCount()
        num, ok = QInputDialog.getInt(
            self, "Go To Line", f"Line number (1–{total}):",
            1, 1, total
        )
        if not ok: return
        doc = self._editor.document()
        block = doc.findBlockByNumber(num - 1)
        if block.isValid():
            cur = QTextCursor(block)
            self._editor.setTextCursor(cur)
            self._editor.ensureCursorVisible()
            self._show_status(f"Moved to line {num}")

    def _action_help(self):
        help_text = (
            "GNU nano — PyOS built-in text editor\n\n"
            "KEYBOARD SHORTCUTS:\n"
            "  ^G   This help screen\n"
            "  ^X   Exit (asks to save if modified)\n"
            "  ^O   Save (Write Out) current file\n"
            "  ^W   Search forward for text\n"
            "  ^\\   Search and Replace\n"
            "  ^K   Cut current line to clipboard\n"
            "  ^U   Paste (Uncut) clipboard line\n"
            "  ^C   Show cursor position (line, column)\n"
            "  ^A   Move to beginning of line\n"
            "  ^E   Move to end of line\n"
            "  ^Y   Scroll one page up\n"
            "  ^V   Scroll one page down\n"
            "  ^_   Go to specific line number\n"
            "  ^Z   Undo last change\n"
            "  Tab  Insert 4 spaces\n"
            "  Esc  Show tip\n\n"
            "NOTES:\n"
            "  - Syntax highlighting: .py .js .ts .html .css .sh .json\n"
            "  - Line numbers shown in left gutter\n"
            "  - Modified indicator in title bar\n"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("nano — Help")
        msg.setText(help_text)
        msg.setStyleSheet(
            "QMessageBox { background:#1e1e2e; color:#cdd6f4; }"
            "QLabel { color:#cdd6f4; font-family:monospace; font-size:12px; }"
            "QPushButton { background:#313244; color:#cdd6f4; border:1px solid #585b70;"
            " border-radius:4px; padding:5px 18px; }"
        )
        msg.exec()

    def get_saved(self) -> bool:
        return self._saved

    def get_filepath(self) -> str:
        return self._filepath


# ── Terminal widget ───────────────────────────────────────────────────────


class TerminalWidget(QWidget):
    def __init__(self, start_dir: str = "", current_user: str = "", parent=None):
        super().__init__(parent)
        self._cwd         = start_dir or os.path.expanduser("~")
        self._env         = os.environ.copy()
        self._env["TERM"] = "xterm-256color"
        if current_user:
            self._env["PYOS_USER"] = current_user
            self._env["USER"]      = current_user
        self._history:    list[str] = []
        self._hist_idx    = -1
        self._worker: CommandWorker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("QWidget { background:#0d1117; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._out = QTextEdit()
        self._out.setReadOnly(True)
        self._out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._out.setStyleSheet(
            "QTextEdit { background:#0d1117; color:#c9d1d9; border:none; padding:8px;"
            " font-family:'Cascadia Code','Consolas','Courier New',monospace;"
            " font-size:13px; }"
        )
        root.addWidget(self._out, 1)

        row = QHBoxLayout()
        row.setContentsMargins(8, 4, 8, 8)
        row.setSpacing(6)

        self._prompt_lbl = QLabel()
        self._prompt_lbl.setStyleSheet(
            "color:#3fb950; font-family:'Cascadia Code','Consolas','Courier New',monospace;"
            " font-size:13px; white-space:nowrap;"
        )
        self._refresh_prompt()
        row.addWidget(self._prompt_lbl)

        self._inp = QLineEdit()
        self._inp.setPlaceholderText("Enter command…")
        self._inp.setStyleSheet(
            "QLineEdit { background:#0d1117; color:#58a6ff; border:none;"
            " border-top:1px solid #21262d; padding:4px 0;"
            " font-family:'Cascadia Code','Consolas','Courier New',monospace;"
            " font-size:13px; }"
        )
        self._inp.returnPressed.connect(self._on_enter)
        self._inp.installEventFilter(self)
        row.addWidget(self._inp, 1)

        stop = QPushButton("⊘")
        stop.setFixedSize(30, 28)
        stop.setToolTip("Ctrl+C")
        stop.setStyleSheet(
            "QPushButton { background:transparent; color:#f85149; border:none; font-size:16px; }"
            "QPushButton:hover { color:#ff6e6e; }"
        )
        stop.clicked.connect(self._interrupt)
        row.addWidget(stop)

        clr = QPushButton("Clear")
        clr.setFixedWidth(52)
        clr.setStyleSheet(
            "QPushButton { background:#21262d; color:#8b949e; border:none;"
            " border-radius:5px; padding:3px 8px; font-size:11px; }"
            "QPushButton:hover { background:#30363d; }"
        )
        clr.clicked.connect(self._out.clear)
        row.addWidget(clr)

        root.addLayout(row)
        self._print_welcome()

    def _refresh_prompt(self):
        user = self._env.get("PYOS_USER", self._env.get("USER", self._env.get("USERNAME", "user")))
        host = platform.node().split(".")[0]
        cwd  = self._cwd.replace(os.path.expanduser("~"), "~")
        self._prompt_lbl.setText(f"{user}@{host}:{cwd}$ ")

    def _print_welcome(self):
        sys_n = platform.system(); rel = platform.release()
        user  = self._env.get("PYOS_USER", "user")
        total_cmds = len(_CMD_MAP)
        self._html(
            f'<span style="color:#3fb950;font-weight:bold">PyOS Terminal</span>'
            f'<span style="color:#8b949e"> — {sys_n} {rel} | '
            f'<span style="color:#58a6ff">Built-in Linux shell</span></span><br>'
            f'<span style="color:#8b949e">Logged in as: '
            f'<span style="color:#f0ad4e">{user}</span></span><br>'
            f'<span style="color:#8b949e">{total_cmds} built-in commands available. '
            f'Type <b>man</b> to list all commands or <b>man &lt;cmd&gt;</b> for help.</span><br><br>'
        )

    def eventFilter(self, obj, event):
        if obj is self._inp and isinstance(event, QKeyEvent):
            k = event.key()
            if k == Qt.Key.Key_Up: self._nav_hist(-1); return True
            if k == Qt.Key.Key_Down: self._nav_hist(1); return True
            if k == Qt.Key.Key_C and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._interrupt(); return True
        return super().eventFilter(obj, event)

    def _nav_hist(self, d):
        if not self._history: return
        self._hist_idx = max(0, min(len(self._history) - 1, self._hist_idx + d))
        self._inp.setText(self._history[self._hist_idx])

    def _on_enter(self):
        cmd = self._inp.text().strip()
        self._inp.clear()
        self._hist_idx = len(self._history)
        if not cmd: return
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
        self._hist_idx = len(self._history)
        self.execute(cmd)

    def execute(self, cmd: str):
        stripped = cmd.strip()

        if stripped in ("clear", "cls"):
            self._out.clear(); return

        if stripped == "history":
            self._html("\n".join(f"{i+1:>4}  {c}" for i, c in enumerate(self._history)) + "\n")
            return

        if re.match(r'^cd(\s|$)', stripped):
            self._do_cd(stripped); return

        # ── nano / vi / vim — open built-in NanoEditor ──────────────
        argv_pre = _split_args(stripped)
        if argv_pre and argv_pre[0].lower() in ("nano", "vi", "vim", "edit"):
            filepath = argv_pre[1] if len(argv_pre) > 1 else ""
            self._html(
                f'<span style="color:#3fb950">{_he(self._prompt_lbl.text())}</span>'
                f'<span style="color:#c9d1d9">{_he(cmd)}</span><br>'
            )
            self._open_nano(filepath)
            return

        self._html(
            f'<span style="color:#3fb950">{_he(self._prompt_lbl.text())}</span>'
            f'<span style="color:#c9d1d9">{_he(cmd)}</span><br>'
        )

        argv  = _split_args(stripped)
        first = argv[0].lower() if argv else ""

        if first in ("python", "python3", "pip", "pip3"):
            self._run_system(cmd); return

        out, rc = run_builtin(stripped, self._cwd, self._env)
        if out is not None:
            if out: self._html(ansi_to_html(out))
            self._refresh_prompt()
            self._finish(rc)
            return

        self._run_system(cmd)

    def _open_nano(self, filepath: str):
        """Open the NanoEditor dialog for the given filepath."""
        editor = NanoEditor(filepath, self._cwd, parent=self)
        editor.exec()
        fname = editor.get_filepath()
        saved = editor.get_saved()
        if saved and fname:
            rel = fname.replace(os.path.expanduser("~"), "~")
            self._html(
                f'<span style="color:#3fb950">Wrote: {_he(rel)}</span><br>'
            )
        self._finish(0)

    def _run_system(self, cmd):
        self._inp.setEnabled(False)
        self._worker = CommandWorker(cmd, self._cwd, self._env, self)
        self._worker.outputReady.connect(lambda t: self._html(ansi_to_html(t)))
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _do_cd(self, cmd):
        parts  = cmd.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else os.path.expanduser("~")
        new    = os.path.normpath(os.path.join(self._cwd, os.path.expanduser(target)))
        if os.path.isdir(new):
            self._cwd = new; self._env["PWD"] = new; self._refresh_prompt()
            self._html(f'<span style="color:#8b949e">→ {_he(new)}</span><br>')
        else:
            self._html(f'<span style="color:#f85149">cd: {_he(target)}: No such directory</span><br>')

    def _finish(self, rc):
        color = "#8b949e" if rc == 0 else "#f85149"
        self._html(f'<br><span style="color:{color}">[exit {rc}]</span><br><br>')
        self._refresh_prompt()

    def _on_worker_done(self, rc):
        self._inp.setEnabled(True); self._inp.setFocus()
        self._finish(rc)

    def _interrupt(self):
        if self._worker and self._worker.isRunning():
            self._worker.kill()
            self._html('<span style="color:#f85149">^C</span><br>')

    def _html(self, html):
        cur = self._out.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self._out.setTextCursor(cur)
        self._out.insertHtml(html)
        self._out.ensureCursorVisible()


# ── Multi-tab terminal ────────────────────────────────────────────────────

class MultiTabTerminal(QWidget):
    def __init__(self, current_user: str = "", parent=None):
        super().__init__(parent)
        self._current_user = current_user
        self.setStyleSheet("QWidget { background:#0d1117; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)

        plus = QPushButton("+")
        plus.setFixedSize(28, 24)
        plus.setStyleSheet(
            "QPushButton { background:transparent; color:#8b949e; border:none;"
            " font-size:16px; border-radius:4px; }"
            "QPushButton:hover { background:#21262d; color:#c9d1d9; }"
        )
        plus.clicked.connect(self.new_tab)
        self._tabs.setCornerWidget(plus, Qt.Corner.TopRightCorner)

        root.addWidget(self._tabs)
        self.new_tab()

    def new_tab(self):
        n    = self._tabs.count() + 1
        term = TerminalWidget(os.path.expanduser("~"), self._current_user)
        i    = self._tabs.addTab(term, f"  Terminal {n}  ")
        self._tabs.setCurrentIndex(i)
        term._inp.setFocus()

    def _close_tab(self, idx):
        if self._tabs.count() > 1: self._tabs.removeTab(idx)
        else: self.new_tab(); self._tabs.removeTab(idx)