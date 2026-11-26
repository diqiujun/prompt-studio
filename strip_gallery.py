import io

p = r"static\app.js"
s = io.open(p, encoding="utf-8").read()
start = s.index("/* ------------------------------------------------------------------ 姿势库 */")
end = s.index("function insertText(ta, text) {")
print("removing chars:", end - start)
s = s[:start] + "__PLUGIN_HOST__\n\n" + s[end:]
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("placeholder inserted; file size", len(s))
