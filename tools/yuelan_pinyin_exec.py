# -*- coding: utf-8 -*-
"""书库目录：拼音文件名转中文(读内部元数据) + 删3组拼音重复azw3。"""
import os, re, shutil, subprocess

LIB = r'F:\Users\Calibre 书库\书库'
TRASH = r'F:\Users\Calibre 书库\_trash_dedup'
META = r'C:\Program Files\Calibre2\ebook-meta.exe'
os.makedirs(TRASH, exist_ok=True)

# 3组拼音重复: 删拼音azw3(留中文epub)
DELETE = [
 'chi xu xing dong - scalers.azw3',
 'jue zhao _nei guan zi wo yu shi - [(mei )] jie fu _qia pu.azw3',
 'ru he zhao dao xiang zuo de gon - [(ri )] tu gu ai.azw3',
]

# 需改名的拼音书: 文件名 -> 元数据中文title/author(exact). 从json读
import json
rows = json.load(open(r'F:\jalon\deepseek\.tmp\yuelan_pinyin_files.json', encoding='utf-8'))

def safe(s): return re.sub(r'[\\/:*?"<>|]','_',s).strip()

def get_meta(full):
    r=subprocess.run([META,full],capture_output=True,timeout=40)
    txt=r.stdout.decode('utf-8',errors='ignore')
    t=a=''
    for line in txt.splitlines():
        line=line.strip()
        if line.startswith('Title') and not t and ':' in line: t=line.split(':',1)[1].strip()
        if line.startswith('Author') and not a and ':' in line: a=line.split(':',1)[1].strip()
    return t,a

# 1) 删除
moved=0
for f in DELETE:
    src=os.path.join(LIB,f)
    if os.path.isfile(src):
        # 同时移走其sidecar
        side=os.path.splitext(src)[0]+'.cover.jpg'
        shutil.move(src, os.path.join(TRASH,f)); moved+=1
        if os.path.isfile(side): shutil.move(side, os.path.join(TRASH, os.path.basename(side)))
print("删除拼音重复azw3:", moved)

# 2) 改名: 遍历剩余拼音书(排除已删), 元数据有中文名者改名
rename_count=0
for r in rows:
    old=r['file']
    src=os.path.join(LIB, old)
    if not os.path.isfile(src): continue
    # 重新取元数据(确保最新)
    t,a=get_meta(src)
    cn=sum(1 for c in t if '\u4e00'<=c<='\u9fff')
    if cn==0:
        print("  跳过(元数据无中文):", old); continue
    # 清理 title: 去掉 "Microsoft Word - xxx.doc" 这类前缀
    t=re.sub(r'^Microsoft Word\s*-\s*','',t)
    t=re.sub(r'\.docx?$','',t.strip())
    ext=os.path.splitext(old)[1]
    # 作者：取元数据author，过长则截取真实姓名段
    a=a.strip()
    # author 可能形如 "Schember, John" 或 "Administrator [Administrator]"
    a=re.sub(r'\s*\[[^\]]*\]\s*$','',a)  # 去尾部[..]
    if not a: a='未知'
    new = f"{safe(t)} - {safe(a)}{ext}" if a!='未知' else f"{safe(t)}{ext}"
    # 长度限制(Windows 255)
    if len(new)>200:
        new = safe(t)[:150] + f" - {safe(a)[:30]}{ext}"
    tmp=os.path.join(LIB, f"__pt_{rename_count}{ext}")
    shutil.move(src, tmp)
    shutil.move(tmp, os.path.join(LIB,new))
    # sidecar 同步改名
    oldside=os.path.splitext(src)[0]+'.cover.jpg'
    if os.path.isfile(oldside):
        os.rename(oldside, os.path.join(LIB, os.path.splitext(new)[0]+'.cover.jpg'))
    print(f"  改名: {old}\n     -> {new}")
    rename_count+=1
print("改名:", rename_count)
