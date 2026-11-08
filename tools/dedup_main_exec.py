# -*- coding: utf-8 -*-
"""执行去重：基于dedup_main_plan.json，但加保护规则。删除=移入_trash_dedup。"""
import os, re, json, shutil

LIB = r'F:\Users\Calibre 书库'
TRASH = os.path.join(LIB, '_trash_dedup')
os.makedirs(TRASH, exist_ok=True)
plan = json.load(open(r'F:\jalon\deepseek\.tmp\dedup_main_plan.json', encoding='utf-8'))

# 保护：这些"删"项不执行
PROTECT_KEEP_BOTH = [
  ('老实人启蒙', None),      # epub与pdf都保留(pdf 24MB可能扫描版)
]
def is_copy_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return bool(re.search(r'[\(（]\d+[\)）]\s*$', stem))

executed=skipped=0
skip_log=[]
for p in plan:
    dele = p['delete']; keep = p['keep']
    # 保护1: 老实人启蒙 保留两者
    if any(kw in dele for kw,_ in PROTECT_KEEP_BOTH):
        skipped+=1; skip_log.append(('保护关键词',dele)); continue
    # 保护2: 体积比例异常(非纯(n)副本)且体积差>2.5倍 -> 跳过(可能不同版本/内容)
    ds, ks = p['del_size'], p['keep_size']
    if not is_copy_name(dele) and not is_copy_name(keep):
        ratio = max(ds,ks)/max(min(ds,ks),1)
        if ratio > 2.5 and min(ds,ks) < 2*1024*1024:
            # 小文件与大文件不同版本风险 -> 跳过
            skipped+=1; skip_log.append((f'体积比{ratio:.1f}x',dele)); continue
    src = os.path.join(LIB, dele)
    if not os.path.isfile(src):
        skipped+=1; skip_log.append(('不存在',dele)); continue
    # 移走主文件 + sidecar
    dst = os.path.join(TRASH, os.path.basename(src))
    # 若trash已有同名，加后缀
    if os.path.exists(dst):
        b,e=os.path.splitext(os.path.basename(src)); dst=os.path.join(TRASH,f"{b}__dup{e}")
    shutil.move(src, dst); executed+=1
    side = os.path.splitext(src)[0]+'.cover.jpg'
    if os.path.isfile(side):
        sside=os.path.join(TRASH,os.path.basename(side))
        if os.path.exists(sside):
            b,e=os.path.splitext(os.path.basename(side)); sside=os.path.join(TRASH,f"{b}__dup{e}")
        shutil.move(side, sside)

print(f"已移走: {executed}  跳过: {skipped}")
print("--- 跳过明细 ---")
for r,d in skip_log: print(f"  [{r}] {d}")
