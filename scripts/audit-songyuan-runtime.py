#!/usr/bin/env python3
"""Public-source AArch64 recovery DT_NEEDED dependency audit, NEVER a flashability test."""
from collections import defaultdict, deque
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys

if len(sys.argv)!=5:
    sys.exit("Usage: audit-songyuan-runtime.py ELF PRODUCT_DIR SOONG_OUTPUT_DIR OUT_DIR")
binary, product, soong, out=map(Path,sys.argv[1:])
def elf(path,which):
    p=subprocess.run(["readelf",which,str(path)],capture_output=True,text=True)
    return p.stdout if p.returncode==0 else ""
def arm64(path):
    return bool(re.search(r"Machine:\s+AArch64\b",elf(path,"-h")))
def needed(path):
    return re.findall(r"\(NEEDED\)\s+Shared library:\s+\[([^]]+)\]",elf(path,"-d"))
def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def priority(path):
    p=path.as_posix()
    if "/recovery/root/system/lib64/" in p:return 0
    if "/recovery/root/" in p:return 1
    if "/system/lib64/" in p:return 2
    if "/obj/SHARED_LIBRARIES/" in p:return 3
    if "/out/soong/.intermediates/bootable/recovery/" in p:return 4
    return 5
if not binary.is_file() or not arm64(binary):
    sys.exit("ERROR: compiled recovery must be AArch64 ELF")
out.mkdir(parents=True,exist_ok=True)
index=defaultdict(list)
dirs=0
for base in (product,soong):
    if not base.is_dir():continue
    for folder,subs,names in os.walk(base):
        subs[:]=[d for d in subs if d not in (".git",".repo")]
        for name in names:
            if name.endswith(".so") or name=="linker64":index[name].append(Path(folder)/name)
        dirs+=1
        if dirs>500000:break
report={"status":"INCOMPLETE","compiled_recovery_aarch64":True,
        "direct_dependencies":needed(binary),"dependencies":{},"missing":[],"ambiguous":[],
        "library_sources":{},"linker64":None,"indexed_directories":dirs,
        "warning":"Source-only candidate; no OEM vendor HAL, stock ABI, recovery init, decrypt or flashability proof."}
files=out/"SOURCE-BUILT-LIB64";files.mkdir(exist_ok=True)
queue=deque([("recovery",binary)])
processed=set()
while queue:
    parent,path=queue.popleft()
    deps=needed(path)
    report["dependencies"][parent]=deps
    for lib in deps:
        if lib in processed:continue
        possibilities=sorted(index.get(lib,[]),key=lambda p:(priority(p),len(p.parts),str(p)))
        candidates=[p for p in possibilities if p.is_file() and arm64(p)]
        if not candidates:
            if lib not in report["missing"]:report["missing"].append(lib)
            continue
        chosen=candidates[0]
        alternatives=[x for x in candidates if priority(x)==priority(chosen)][:6]
        if len({digest(x) for x in alternatives})>1:
            report["ambiguous"].append({"name":lib,"candidates":[str(x) for x in alternatives]})
        dst=files/lib
        shutil.copyfile(chosen,dst)
        processed.add(lib)
        report["library_sources"][lib]=str(chosen)
        queue.append((lib,dst))
linkers=sorted([f for f in index.get("linker64",[]) if f.is_file() and arm64(f)],
               key=lambda p:(priority(p),len(p.parts),str(p)))
if linkers:
    shutil.copyfile(linkers[0],out/"SOURCE-BUILT-LINKER64")
    report["linker64"]=str(linkers[0])
if not report["missing"] and not report["ambiguous"] and linkers:
    report["status"]="CANDIDATE_DT_NEEDED_RESOLVED_NOT_FLASHABLE"
report["missing"].sort()
report["found_count"]=len(processed)
(out/"RUNTIME-AUDIT.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
(out/"RUNTIME-CLOSURE-STATUS.txt").write_text(
    "STATUS="+report["status"]+"\nMISSING="+(",".join(report["missing"]) or "none")
    +"\nAMBIGUOUS="+str(len(report["ambiguous"]))+"\nLINKER="+str(report["linker64"])
    +"\nNEVER FLASH THIS ARTIFACT; STOCK OEM ABIs/KeyMint/SELinux UNTESTED\n")
print("Runtime closure:",report["status"],"found:",len(processed),
      "missing:",len(report["missing"]),"ambiguous:",len(report["ambiguous"]))
