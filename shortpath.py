import ctypes
from ctypes import wintypes

p = "E:\\新建文件夹\\prompt-studio"
buf = ctypes.create_unicode_buffer(600)
n = ctypes.windll.kernel32.GetShortPathNameW(p, buf, 600)
print("short:", buf.value if n else "FAILED n=%d err=%d" % (n, ctypes.get_last_error()))
