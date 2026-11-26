import py_compile, sys, pathlib
bad = []
for p in sorted(pathlib.Path("src").glob("*.py")) + [pathlib.Path("selftest.py"), pathlib.Path("probe_api.py")]:
    try:
        py_compile.compile(str(p), doraise=True)
        print("ok  ", p)
    except py_compile.PyCompileError as e:
        bad.append(str(e))
        print("FAIL", p, e.msg if hasattr(e, "msg") else e)
sys.exit(1 if bad else 0)
