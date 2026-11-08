# -*- coding: utf-8 -*-
import os, re, hashlib, random
from PIL import Image, ImageDraw, ImageFont

LIB = r"F:\Users\Calibre 书库\杂书架"
FONT_PATH = r"C:\Windows\Fonts\msyhbd.ttc"   # 微软雅黑 Bold
FONT_REG  = r"C:\Windows\Fonts\msyh.ttc"

W, H = 600, 800  # 3:4 常见封面比

def load_font(size):
    return ImageFont.truetype(FONT_PATH, size)

def clean_name(basename):
    """从文件基名提取 书名 / 作者"""
    s = basename
    s = re.sub(r'\s*\(\d+\)\s*$', '', s)      # 去尾部 (2)
    # 尝试按 ' - ' 拆书名-作者
    if ' - ' in s:
        parts = s.split(' - ', 1)
        title, author = parts[0].strip(), parts[1].strip()
    else:
        title, author = s.strip(), ''
    # 去括号里的冗余标记
    title = title.strip()
    return title, author

def wrap_text(draw, text, font, max_width):
    """按像素宽度换行，兼顾中文无空格"""
    lines = []
    cur = ''
    for ch in text:
        test = cur + ch
        w = draw.textlength(test, font=font)
        if w > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines

def color_from_name(name):
    """按名字哈希生成稳定的深色渐变对"""
    h = hashlib.md5(name.encode('utf-8')).hexdigest()
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    # 压暗做背景色1
    c1 = (int(r*0.35)+20, int(g*0.35)+25, int(b*0.35)+40)
    # 背景色2 稍亮
    c2 = (int(r*0.55)+30, int(g*0.55)+35, int(b*0.55)+55)
    return c1, c2

def make_cover(title, author, outpath):
    c1, c2 = color_from_name(title)
    img = Image.new('RGB', (W, H), c1)
    draw = ImageDraw.Draw(img)
    # 垂直渐变
    for y in range(H):
        t = y / (H - 1)
        col = tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=col)
    # 顶部/底部细装饰线
    draw.rectangle([40, 60, W-40, 66], fill=(255, 255, 255, 60))
    # 书名
    max_text_w = W - 120
    # 动态字号：长书名缩小
    fsize = 64
    while fsize > 30:
        font = load_font(fsize)
        lines = wrap_text(draw, title, font, max_text_w)
        total_h = len(lines) * int(fsize*1.35)
        if total_h <= 460 and all(draw.textlength(l,font=font)<=max_text_w for l in lines):
            break
        fsize -= 4
    font = load_font(fsize)
    lines = wrap_text(draw, title, font, max_text_w)
    line_h = int(fsize*1.35)
    total_h = len(lines)*line_h
    start_y = (H - total_h)//2 - 30
    for i, line in enumerate(lines):
        lw = draw.textlength(line, font=font)
        x = (W - lw)//2
        y = start_y + i*line_h
        # 阴影
        draw.text((x+2, y+2), line, font=font, fill=(0,0,0))
        draw.text((x, y), line, font=font, fill=(255,255,255))
    # 作者
    if author:
        afont = load_font(30)
        alines = wrap_text(draw, author, afont, max_text_w)
        ay = start_y + total_h + 30
        for line in alines[:3]:
            lw = draw.textlength(line, font=afont)
            draw.text(((W-lw)//2, ay), line, font=afont, fill=(230,230,230))
            ay += 40
    # 底部装饰线
    draw.rectangle([40, H-66, W-40, H-60], fill=(255, 255, 255, 60))
    img.save(outpath, 'JPEG', quality=88)
    return outpath

def main():
    txts = [f for f in os.listdir(LIB) if f.lower().endswith('.txt')]
    extra = ['《泡妞惯例秘籍》 - Administrator [Administrator].epub',
             '慕容雪村《做爱的经济学分析》.azw3']
    done = 0
    for f in txts + extra:
        base = os.path.splitext(f)[0]
        # sidecar 名基于书基名
        out = os.path.join(LIB, base + '.cover.jpg')
        if os.path.exists(out):
            print('SKIP exists:', out); continue
        title, author = clean_name(base)
        if not title:
            title = base
        make_cover(title, author, out)
        print('MADE:', base, '| title=', title, '| author=', author)
        done += 1
    print('TOTAL generated:', done)

if __name__ == '__main__':
    main()
