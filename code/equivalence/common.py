import os, subprocess, json, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "common")); sys.path.insert(0, os.path.join(ROOT, "code", "backend", "python"))
# Every C program in this capsule is built so that floating point is a compile error.
CFLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-mgeneral-regs-only"]
KC = os.path.join(ROOT, "code", "kernel_c")
BUILD = os.path.join(ROOT, "results", "build")
def compile_c(out, *sources):
    os.makedirs(BUILD, exist_ok=True)
    exe = os.path.join(BUILD, out)
    subprocess.run(["gcc", *CFLAGS, "-I", os.path.join(KC, "include"), *sources, "-o", exe], check=True)
    return exe
def emit(obj): print("RESULT " + json.dumps(obj, sort_keys=True))
