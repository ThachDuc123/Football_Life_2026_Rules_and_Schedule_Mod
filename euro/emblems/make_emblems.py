"""Competition emblems of the new competitions from their official logos.

The game shows a competition's emblem from common/render/symbol/emblemLc/
emb_<database id, 4 decimal digits>_<variant>_<size>.png: variant '' (colour),
'b' (colour, light backgrounds), 'w' (white, dark backgrounds); size 'l' 256 px,
'll' 512 px. Sources (Wikipedia / Wikimedia Commons, see SOURCES) are in logos/;
output goes to livecpk/UEFA36 (higher priority than UML_Logos).
Usage: python make_emblems.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
LOGOS = HERE / 'logos'
OUT = Path(r'D:\FL26\SiderAddons\livecpk\UEFA36\common\render\symbol\emblemLc')

SOURCES = {
    'uecl.png': 'https://commons.wikimedia.org/wiki/File:UEFA_Conference_League_full_logo_(2024_version).svg',
    'efl.png': 'https://en.wikipedia.org/wiki/File:EFL_(Carabao)_Cup_Logo.svg',
    'taca.png': 'https://commons.wikimedia.org/wiki/File:S%C3%ADmbolo_da_Allianz_Cup.png',
    'scot.png': 'https://commons.wikimedia.org/wiki/File:Premier_Sports_Cup_Large_Landscape_Identity_Positive_on_Black.png',
}


def trim(im):
    box = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    return im.crop(box) if box else im


def square(im, size, margin=0.04):
    im = trim(im)
    room = int(size * (1 - 2 * margin))
    scale = min(room / im.width, room / im.height)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


def recolour(im, rule):
    """rule(r, g, b) -> mask of pixels to paint, painted with the given colour."""
    a = np.array(im.convert('RGBA')).astype(np.int32)
    mask, colour = rule(a[..., 0], a[..., 1], a[..., 2])
    a[mask, 0], a[mask, 1], a[mask, 2] = colour
    return Image.fromarray(a.astype(np.uint8), 'RGBA')


def dark(r, g, b):
    return (r < 90) & (g < 90) & (b < 90)


def all_pixels(r, g, b):
    return np.ones(r.shape, bool)


def light(r, g, b):
    return (r > 200) & (g > 200) & (b > 200)


def uecl():
    src = Image.open(LOGOS / 'uecl.png').convert('RGBA')
    white = recolour(src, lambda r, g, b: (dark(r, g, b), (255, 255, 255)))
    return {'': src, 'b_': src, 'w_': white}


def efl():
    src = Image.open(LOGOS / 'efl.png').convert('RGBA')
    return {'': src, 'b_': src, 'w_': src}          # the shield carries its own background


def taca():
    src = Image.open(LOGOS / 'taca.png').convert('RGBA')
    white = recolour(src, lambda r, g, b: (all_pixels(r, g, b), (255, 255, 255)))
    return {'': src, 'b_': src, 'w_': white}


def scot():
    """Landscape logo on black: black -> transparent, then trophy above the text."""
    a = np.array(Image.open(LOGOS / 'scot.png').convert('RGBA')).astype(np.int32)
    lum = a[..., :3].max(axis=2)
    a[..., 3] = np.clip((lum - 30) * 255 // 90, 0, 255) * (a[..., 3] > 0)
    im = trim(Image.fromarray(a.astype(np.uint8), 'RGBA'))
    # split at the widest empty column between the trophy and the words
    alpha = np.array(im.getchannel('A')) > 20
    cols = alpha.any(axis=0)
    w = im.width
    gaps = [x for x in range(int(w * 0.25), int(w * 0.6)) if not cols[x]]
    cut = gaps[len(gaps) // 2] if gaps else int(w * 0.42)
    cup, words = trim(im.crop((0, 0, cut, im.height))), trim(im.crop((cut, 0, w, im.height)))
    words = words.resize((int(cup.width * 1.5), int(words.height * cup.width * 1.5 / words.width)), Image.LANCZOS)
    stack = Image.new('RGBA', (max(cup.width, words.width), cup.height + words.height + cup.height // 10), (0, 0, 0, 0))
    stack.alpha_composite(cup, ((stack.width - cup.width) // 2, 0))
    stack.alpha_composite(words, ((stack.width - words.width) // 2, cup.height + cup.height // 10))
    on_light = recolour(stack, lambda r, g, b: (light(r, g, b), (20, 20, 20)))
    white = recolour(stack, lambda r, g, b: (all_pixels(r, g, b), (255, 255, 255)))
    return {'': on_light, 'b_': on_light, 'w_': white}


EMBLEMS = {6: uecl, 146: efl, 147: taca, 148: scot}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for dbid, make in EMBLEMS.items():
        for variant, im in make().items():
            for tag, size in (('l', 256), ('ll', 512)):
                square(im, size).save(OUT / f'emb_{dbid:04d}_{variant}{tag}.png')
                n += 1
    print(f'{n} emblems -> {OUT}')


if __name__ == '__main__':
    main()
