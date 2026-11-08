"""Generate a 1280x640 GitHub social image from the existing wallpaper artwork."""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "showcase/images"

def font(n, serif=False, bold=False):
    name = ("DejaVuSerif" if serif else "DejaVuSans") + ("-Bold" if bold else "") + ".ttf"
    try: return ImageFont.truetype(name,n)
    except OSError: return ImageFont.load_default()

def framed(im, name, xy, caption):
    x0,y0,x1,y1=xy
    shadow=Image.new("RGBA",im.size)
    ImageDraw.Draw(shadow).rounded_rectangle((x0+6,y0+13,x1+6,y1+13),radius=9,fill=(0,0,0,180))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((x0-5,y0-5,x1+5,y1+27),radius=7,fill=(19,21,20,255),outline=(125,115,102,255),width=2)
    with Image.open(SOURCES / name) as original:
        art=ImageOps.fit(original.convert("RGB"),(x1-x0,y1-y0),method=Image.Resampling.LANCZOS)
    im.paste(art,(x0,y0))
    ImageDraw.Draw(im).text((x1-4,y1+7),caption,font=font(11),fill=(176,174,162),anchor="ra")

def render(out):
    if out.suffix.lower() not in (".jpg",".jpeg"): raise ValueError("Social preview must be JPEG")
    im=Image.new("RGBA",(1280,640),(17,18,16,255))
    d=ImageDraw.Draw(im)
    for y in range(640):
        c=17+y//92
        d.line((0,y,1280,y),fill=(c,c+1,c-1,255))
    glow=Image.new("RGBA",im.size)
    ImageDraw.Draw(glow).ellipse((750,-210,1490,540),fill=(176,104,51,85))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(105)))
    grid=Image.new("RGBA",im.size)
    g=ImageDraw.Draw(grid)
    for x in range(740,1280,44): g.line((x,0,x,640),fill=(255,244,217,17))
    for y in range(0,640,44): g.line((710,y,1280,y),fill=(255,244,217,17))
    im.alpha_composite(grid)
    framed(im,"station-exterior.png",(765,108,1218,358),"DISPLAY 01 / EXTERIOR")
    framed(im,"station-interior.png",(906,378,1224,550),"DISPLAY 02 / INTERIOR")
    framed(im,"station-laptop.png",(622,283,898,472),"LAPTOP / ENTRANCE")
    d=ImageDraw.Draw(im)
    amber=(227,169,102)
    d.ellipse((75,77,127,129),outline=amber,width=2)
    d.ellipse((88,91,99,102),fill=amber)
    d.ellipse((110,111,116,117),fill=amber)
    d.text((146,90),"AMBIENT  /  WALLPAPERS",font=font(20,bold=True),fill=(245,239,230))
    d.text((75,189),"Made to feel",font=font(57,serif=True),fill=(245,239,230))
    d.text((75,274),"like yours.",font=font(71,serif=True),fill=amber)
    d.text((78,395),"AI wallpaper art shaped by your taste.",font=font(20),fill=(185,182,171))
    d.line((78,513,382,513),fill=(136,106,78),width=2)
    d.text((78,531),"ONE WORLD  /  THREE SCREENS",font=font(13,bold=True),fill=(185,182,171))
    d.text((78,588),"A PERSONAL CODEX SKILL",font=font(13),fill=(148,146,137))
    out.parent.mkdir(parents=True,exist_ok=True)
    im.convert("RGB").save(out,"JPEG",quality=88,optimize=True,subsampling=0)
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"dist/ambient-wallpapers-social-preview.jpg")
    path=render(p.parse_args().output)
    with Image.open(path) as preview: assert preview.size==(1280,640)
    print(f"Social preview: {path} ({path.stat().st_size:,} bytes)")
