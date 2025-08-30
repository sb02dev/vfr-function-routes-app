"""Helper function to make VSCode understand the output of pylint when run as Task"""
#!/usr/bin/env python
# pylint_wrapper.py

import sys
import subprocess
import re

# Mapping from pylint category letter → VSCode severity
CATEGORY_MAP = {
    "E": "error",
    "F": "error",
    "W": "warning",
    "C": "info",
    "R": "hint",
}

# Collect command-line arguments for pylint
pylint_args = sys.argv[1:]

# Force msg-template to include category at the start
pylint_args = ["--msg-template={path}:{line}-{end_line}:{column}-{end_column}:" + \
               " {msg_id}: {msg} ({symbol})"] + pylint_args

# Run pylint and capture output
proc = subprocess.Popen( # pylint: disable=consider-using-with
    [sys.executable.replace("python.exe", "pylint.exe"), *pylint_args],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1  # line-buffered
)

# Regex to parse pylint output: path:line-end_line:col-end_col: category: message (symbol)
# Example: foo.py:10:5: E0602: Undefined variable 'bar' (undefined-variable)
pattern = re.compile(r"^(.*?):(\d+)-(\d*):(\d+)-(\d*): ([A-Z])(\d+): (.*) \((.*)\)$")

for line in proc.stdout:
    line = line.rstrip()
    m = pattern.match(line)
    if m:
        path, line_no, end_line, col_no, end_col, cat, code, msg, symbol = m.groups()
        severity = CATEGORY_MAP.get(cat, "info")
        # Output in a format the VSCode matcher can consume
        print(f"{path}:{line_no}-{end_line}:{int(col_no)+1}-" +
              f"{str(int(end_col)+1) if end_col != '' else ''}:" +
              f" {severity}: {msg} (Pylint({cat}{code}:{symbol}))", flush=True)
    else:
        # print unmodified if it doesn’t match
        print(line, flush=True)

proc.wait()
sys.exit(proc.returncode)
