# -*- coding: utf-8 -*-
"""拼音文件名 → 汉字书名批量改名。
书名来源优先级: epub OPF 元数据 > mobi EXTH > pdf Info.Title > (否则跳过)
同步处理: 同名 .cover.jpg 改名、opened.json 路径键改写、books.json 由服务端 rescan 重算。
用法: py rename_pinyin.py [--dry] [limit]
"""
import json, zipfile, re, os, sys, struct, time, importlib.util

spec = importlib.util.spec_from_file_location('srv', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py'))
srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)

PYNAME = re.compile(r'^[A-Za-z0-9\s\-_.\(\)\[\]]+\.(epub|mobi|pdf|azw3?|txt)$')
BAD = r'[\\/:*?"<>|]'
OPENED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'opened.json')

def epub_meta(fp):
    try:
        z = zipfile.ZipFile(fp)
        opf = [n for n in z.namelist() if n.endswith('.opf')][0]
        t = z.read(opf).decode('utf-8', 'ignore')
        ti = re.search(r'<dc:title[^>]*>(.*?)</dc:title>', t, re.S)
        au = re.search(r'<dc:creator[^>]*>(.*?)</dc:creator>', t, re.S)
        return (ti.group(1).strip() if ti else '', au.group(1).strip() if au else '')
    except Exception:
        return ('', '')

def mobi_meta(fp):
    try:
        raw = open(fp, 'rb').read(6 * 1024 * 1024)
        if raw[:4] not in (b'BOOK', b'TEXt'): return ('', '')
        off = struct.unpack('>I', raw[16:20])[0]  # MOBI header start
        if raw[off+16:off+20] != b'MOBI': return ('', '')
        exth = off + struct.unpack('>I', raw[off+20:off+24])[0]
        if raw[exth:exth+4] != b'EXTH': return ('', '')
        cnt = struct.unpack('>I', raw[exth+8:exth+12])[0]
        p = exth + 12; title = author = ''
        for _ in range(cnt):
            rtype, rlen = struct.unpack('>II', raw[p:p+8])
            val = raw[p+8:p+rlen].decode('utf-8', 'ignore')
            if rtype == 503: title = val
            elif rtype == 100: author = val
            p += rlen
        return (title.strip(), author.strip())
    except Exception:
        return ('', '')

def pdf_title(fp):
    try:
        raw = open(fp, 'rb').read(3 * 1024 * 1024)
        m = re.search(rb'/Title\s*\(([^)]{2,80})\)', raw)
        if m:
            try: return m.group(1).decode('utf-16-be').strip('\x00')
            except Exception: return m.group(1).decode('latin-1', 'ignore').strip()
    except Exception:
        pass
    return ''

def has_cjk(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s))

def plan_renames():
    out = []
    for d in ('书库', '杂书架', '18+'):
        full_dir = os.path.join(srv.LIB_ROOT, d)
        for f in sorted(os.listdir(full_dir)):
            if f.endswith('.cover.jpg') or not PYNAME.match(f):
                continue
            fp = os.path.join(full_dir, f)
            ext = os.path.splitext(f)[1].lower()
            if ext == '.epub':
                title, author = epub_meta(fp)
            elif ext == '.mobi' or ext == '.azw3':
                title, author = mobi_meta(fp)
            elif ext == '.pdf':
                title, author = pdf_title(fp), ''
            else:
                title, author = '', ''
            if not title or not has_cjk(title):
                continue
            title = re.sub(BAD, '', title).strip()
            author = re.sub(BAD, '', author).strip()
            # 清洗出版商杂质与超长书名（文件名 ≤ 60 字符）
            title = re.sub(r'\s*[\(\[](BookDNA|果麦|博集|后浪|磨铁|读客|掌阅|微信读书|Kindle)[^\)\]]*[\)\]]', '', title).strip()
            title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
            title = re.split(r'\s*[-–:：]\s*(?:\[[^\]]*\]|[\u4e00-\u9fff]{0,3}出版社|译)', title)[0].strip() or title
            if len(title) > 60:
                title = title[:60].rstrip()
            if len(author) > 30:
                author = author[:30].rstrip()
            if author.lower() in ('unknown', '', 'z-library', 'calibre'):
                newname = f'{title}{ext}'
            else:
                newname = f'{title} - {author}{ext}'
            if len(newname) > 150:
                newname = newname[:147] + ext
            cov = os.path.splitext(f)[0] + '.cover.jpg'
            out.append({
                'dir': d, 'old': f, 'new': newname,
                'src': fp, 'dst': os.path.join(full_dir, newname),
                'cov_old': os.path.join(full_dir, cov) if os.path.isfile(os.path.join(full_dir, cov)) else None,
                'cov_new': os.path.join(full_dir, os.path.splitext(newname)[0] + '.cover.jpg'),
            })
    return out

def apply_renames(items):
    moved_keys = {}
    for it in items:
        try:
            os.rename(it['src'], it['dst'])
            if it['cov_old']:
                os.rename(it['cov_old'], it['cov_new'])
        except OSError as e:
            print('改名失败:', it['old'][:40], type(e).__name__)
            continue
        rel_old = os.path.join(it['dir'], it['old']).lower()
        rel_new = os.path.join(it['dir'], it['new']).lower()
        moved_keys[rel_old] = rel_new
    # opened.json 路径键改写
    try:
        op = json.load(open(OPENED_FILE, encoding='utf-8'))
    except Exception:
        op = {}
    for k in list(op.keys()):
        kk = k.replace('/', '\\')
        if kk in moved_keys:
            op[moved_keys[kk]] = op.pop(k)
    json.dump(op, open(OPENED_FILE, 'w', encoding='utf-8'), ensure_ascii=False)
    return len(moved_keys)

if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    dry = '--dry' in sys.argv
    limit = 0
    for a in sys.argv[1:]:
        if a.isdigit(): limit = int(a)
    items = plan_renames()
    # 目标同名冲突检测
    conflict = [it for it in items if os.path.isfile(it['dst']) and os.path.normcase(it['dst']) != os.path.normcase(it['src'])]
    ok_items = [it for it in items if it not in conflict]
    print(f'可改名: {len(items)} (冲突 {len(conflict)} 跳过)')
    for it in ok_items[:limit if limit else 15]:
        print(f"  {it['old'][:38]} -> {it['new'][:46]}")
    if dry:
        print('DRY RUN，未改名')
    else:
        n = apply_renames(ok_items if limit == 0 else ok_items[:limit])
        print(f'已改名 {n} 本, rescan...')
        import urllib.request as ur
        ur.urlopen(ur.Request('http://127.0.0.1:8766/api/rescan', data=b'', method='POST'), timeout=180)
        print('rescan 完成')
