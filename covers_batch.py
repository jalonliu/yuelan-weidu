# -*- coding: utf-8 -*-
"""批量豆瓣封面匹配：epub 读内嵌元数据(真书名) → 豆瓣 suggest → 大图(Referer 绕 418) → upload。
用法: py covers_batch.py [起始偏移] [每批数量]
断点: 状态存 D:/Hermes/cache/scratch/covers-batch-state.json
"""
import json, urllib.request as ur, zipfile, re, os, sys, time, importlib.util
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

spec = importlib.util.spec_from_file_location('srv', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py'))
srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)

NOISE = re.compile(r'\(Z-Library\)|\[.*?\]|[\(\【].*?[\)\】]|\.?\s*(epub|pdf|mobi|azw3?|txt)$|^\d+[\.、]\s*', re.I)
STATE = r'D:/Hermes/cache/scratch/covers-batch-state.json'

def epub_title(fp):
    try:
        z = zipfile.ZipFile(fp)
        opf = [n for n in z.namelist() if n.endswith('.opf')][0]
        t = z.read(opf).decode('utf-8', 'ignore')
        m = re.search(r'<dc:title[^>]*>(.*?)</dc:title>', t, re.S)
        return m.group(1).strip() if m else ''
    except Exception:
        return ''

def fetch_all():
    out = []
    for sh in ('main', 'misc', 'adult'):
        out += json.load(ur.urlopen(f'http://127.0.0.1:8766/api/books?shelf={sh}', timeout=60))['books']
    seen, miss = set(), []
    for x in out:
        if x['id'] in seen: continue
        seen.add(x['id'])
        if not x.get('cover'): miss.append(x)
    return miss

def try_cover(x):
    q = epub_title(os.path.join(srv.LIB_ROOT, x['path'])) if x['format'] == 'epub' else ''
    q = q or NOISE.sub(' ', x['title']).strip()
    q = q[:30]
    if not q or not re.search(r'[\u4e00-\u9fff]', q):
        return 'skip-pinyin'
    # 豆瓣 suggest（复用 server 的代理与 UA）
    url = 'https://book.douban.com/j/subject_suggest?q=' + ur.quote(q)
    op = ur.build_opener(ur.ProxyHandler(srv.PROXY))
    op.addheaders = [('User-Agent', srv.UA), ('Referer', 'https://book.douban.com/')]
    r = json.load(op.open(url, timeout=15))
    if not r: return 'no-hit'
    pic = (r[0].get('pic') or r[0].get('img') or '')
    if not pic: return 'no-pic'
    big = pic.replace('/sqxs/', '/lpic/').replace('/s/public/', '/l/public/').replace('/view/subject/s/public/', '/view/subject/l/public/')
    try:
        raw = srv._http_get(big, referer='https://book.douban.com/subject/' + str(r[0].get('id', '')) + '/', timeout=20)
    except Exception as e:
        return f'dl-fail:{type(e).__name__}'
    if not (raw[:3] == b'\xff\xd8\xff' or raw[:3] == b'\x89PN') or len(raw) < 5000:
        return 'bad-img'
    req = ur.Request(f"http://127.0.0.1:8766/api/covers/upload/{x['id']}", data=raw, headers={'Content-Type': 'image/jpeg'}, method='POST')
    rr = json.load(ur.urlopen(req, timeout=30))
    return 'ok' if rr.get('ok') else 'upload-fail'

def main():
    off = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    miss = fetch_all()
    state = json.load(open(STATE, encoding='utf-8')) if os.path.isfile(STATE) else {'done': 0, 'stats': {}}
    done = state['done']
    batch = miss[off:off + n]
    for x in batch:
        try:
            r = try_cover(x)
        except Exception as e:
            r = f'err:{type(e).__name__}'
        state['stats'][r] = state['stats'].get(r, 0) + 1
        state['done'] = off + len(batch)
        print(f"{x['title'][:22]!r} -> {r}")
        time.sleep(0.6)
    json.dump(state, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"本批 {len(batch)} | 累计 {state['done']}/{len(miss)} | 统计 {state['stats']}")

if __name__ == '__main__':
    main()
