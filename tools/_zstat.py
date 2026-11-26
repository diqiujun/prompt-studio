import zipfile, collections, os
p = r"E:\新建文件夹\prompt-studio\dist\release\PromptStudio-1.1-src.zip"
z = zipfile.ZipFile(p)
agg = collections.Counter()
for i in z.infolist():
    rel = i.filename.split("/", 1)[1] if "/" in i.filename else i.filename
    top = rel.split("/")[0] if "/" in rel else "(root)"
    agg[top] += i.file_size
for k, v in agg.most_common(12):
    print("%-16s %8.2f MB" % (k, v/1e6))
print("files:", len(z.infolist()))
