"""Build an NB4+ 1.0.31 external data file. Never launches an updater or accesses USB."""
from pathlib import Path
import argparse, struct, hashlib, json, zlib
from checksums import crc32_nonref, reverse_words
from png_codec import save_png

UPDATER_SHA256 = '522eeaeecc4ba120d08229ba6f12c828935c6ae61a45f002681d64c60bdfb4c5'
RESOURCE_OFFSET = 908680
RESOURCE_LENGTH = 5695344
WIDTH, HEIGHT = 320, 398
SLOTS = {'model': (0x131c, 0x4418d6), 'character': (0x132c, 0x47fbd6), 'scenery': (0x133c, 0x4bded6)}
CHARACTER_THEME_SLOT = (0x134c, 0x4fc1d6)
WALLPAPER_ARTWORK = dict(SLOTS, character_theme=CHARACTER_THEME_SLOT)

def read_png(path):
    data=Path(path).read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Input must be a PNG image. Export your photo as PNG first.')
    p=8; compressed=bytearray(); palette=None; transparency=b''; header=None; ended=False
    while p+12<=len(data):
        size=struct.unpack_from('>I',data,p)[0]
        kind=data[p+4:p+8]; payload=data[p+8:p+8+size]
        if p+12+size>len(data): raise ValueError('Truncated PNG')
        if zlib.crc32(kind+payload)!=struct.unpack_from('>I',data,p+8+size)[0]: raise ValueError('PNG chunk checksum mismatch')
        if kind==b'IHDR': header=struct.unpack('>IIBBBBB',payload)
        elif kind==b'PLTE': palette=payload
        elif kind==b'tRNS': transparency=payload
        elif kind==b'IDAT': compressed.extend(payload)
        elif kind==b'IEND': ended=True; break
        p+=size+12
    if not ended or header is None: raise ValueError('Incomplete PNG')
    w,h,depth,color,compression,filter_method,interlace=header
    if depth!=8 or color not in (0,2,3,4,6) or compression or filter_method or interlace:
        raise ValueError('Use a non-interlaced 8-bit PNG (RGB, RGBA, grayscale, or palette).')
    if w!=WIDTH or h!=HEIGHT: raise ValueError(f'Image must be {WIDTH} × {HEIGHT} pixels; received {w} × {h}. Crop/resize it first.')
    channels={0:1,2:3,3:1,4:2,6:4}[color]; stride=w*channels
    raw=zlib.decompress(compressed)
    if len(raw)!=(stride+1)*h: raise ValueError('Unexpected PNG pixel data size')
    previous=bytearray(stride); rgb=bytearray()
    def paeth(a,b,c):
        p=a+b-c; distances=(abs(p-a),abs(p-b),abs(p-c))
        return (a,b,c)[distances.index(min(distances))]
    for y in range(h):
        start=y*(stride+1); mode=raw[start]; row=bytearray(raw[start+1:start+1+stride])
        if mode>4: raise ValueError('Invalid PNG filter')
        for x in range(stride):
            left=row[x-channels] if x>=channels else 0
            up=previous[x]; diagonal=previous[x-channels] if x>=channels else 0
            predictor=(0,left,up,(left+up)//2,paeth(left,up,diagonal))[mode]
            row[x]=(row[x]+predictor)&255
        for x in range(w):
            pixel=row[x*channels:(x+1)*channels]
            alpha=255
            if color in (0,4):
                r=g=b=pixel[0]
                if color==4: alpha=pixel[1]
                elif transparency and pixel[0]==struct.unpack('>H',transparency)[0]: alpha=0
            elif color==3:
                index=pixel[0]
                if palette is None or index*3+3>len(palette): raise ValueError('Invalid palette index')
                r,g,b=palette[index*3:index*3+3]
                if index<len(transparency):alpha=transparency[index]
            else:
                r,g,b=pixel[:3]
                if color==6:alpha=pixel[3]
                elif transparency and (r,g,b)==struct.unpack('>HHH',transparency):alpha=0
            rgb.extend(((r*alpha+127)//255,(g*alpha+127)//255,(b*alpha+127)//255))
        previous=row
    return rgb

def validate_resource(data):
    if len(data)!=RESOURCE_LENGTH: raise ValueError('Unexpected resource size')
    if struct.unpack_from('<H',data)[0]!=0x5a5a: raise ValueError('Resource magic mismatch')
    if struct.unpack_from('<I',data,2)[0]!=len(data)-4: raise ValueError('Resource length field mismatch')
    if struct.unpack_from('<H',data,18)[0]!=(sum(data[:18])&0xffff)^0xffff: raise ValueError('Resource header checksum mismatch')
    checksum=crc32_nonref(reverse_words(data[:-4]))
    if checksum!=struct.unpack_from('<I',data,len(data)-4)[0]: raise ValueError('Resource CRC mismatch')
    return checksum

def patch_resource(original,rgb,slot):
    return _patch_wallpaper(original, rgb, *SLOTS[slot])


def patch_character_theme(original, rgb):
    """Update the alternate Character artwork selected by themes 2 and 3."""
    return _patch_wallpaper(original, rgb, *CHARACTER_THEME_SLOT)


def _patch_wallpaper(original, rgb, descriptor, offset):
    validate_resource(original)
    if len(rgb)!=WIDTH*HEIGHT*3:raise ValueError('Unexpected pixel count')
    w,h,key,pointer=struct.unpack_from('<IIII',original,descriptor)
    if (w,h,pointer)!=(WIDTH,HEIGHT,0xc0280000+offset):raise ValueError('Wallpaper descriptor mismatch')
    encoded=bytearray(); preview=bytearray(); adjusted=0
    for i in range(0,len(rgb),3):
        r,g,b=rgb[i:i+3]; value=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
        # 0xA897 appears to be the renderer's transparent color. Avoid accidental holes.
        if value==key:value^=1;adjusted+=1
        encoded.extend(struct.pack('<H',value))
        r5,g6,b5=value>>11,(value>>5)&63,value&31
        preview.extend(((r5<<3)|(r5>>2),(g6<<2)|(g6>>4),(b5<<3)|(b5>>2)))
    result=bytearray(original)
    result[offset:offset+len(encoded)]=encoded
    struct.pack_into('<I',result,len(result)-4,crc32_nonref(reverse_words(result[:-4])))
    validate_resource(result)
    if result[:offset]!=original[:offset] or result[offset+len(encoded):-4]!=original[offset+len(encoded):-4]:
        raise AssertionError('Modification escaped the image and CRC ranges')
    return result,preview,adjusted

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--updater',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True,help='320 × 398 non-interlaced 8-bit PNG')
    parser.add_argument('--slot',choices=SLOTS,default='scenery')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    updater=args.updater.read_bytes()
    if hashlib.sha256(updater).hexdigest()!=UPDATER_SHA256:parser.error('Updater does not match the inspected 1.0.31-4 package')
    original=updater[RESOURCE_OFFSET:RESOURCE_OFFSET+RESOURCE_LENGTH]
    result,preview,adjusted=patch_resource(original,read_png(args.image),args.slot)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    output=args.output_dir/'FS_FG4_CN_Data.bin'
    if output.exists():parser.error(f'Output already exists: {output}. Choose a new directory.')
    output.write_bytes(result)
    save_png(args.output_dir/'wallpaper_preview.png',WIDTH,HEIGHT,preview)
    report=dict(slot=args.slot,width=WIDTH,height=HEIGHT,source_updater_sha256=UPDATER_SHA256,
        data_sha256=hashlib.sha256(result).hexdigest(),data_crc32=hex(struct.unpack_from('<I',result,len(result)-4)[0]),
        image_offset=hex(SLOTS[args.slot][1]),image_bytes=WIDTH*HEIGHT*2,color_key_pixels_adjusted=adjusted,
        validation='Original CRC reproduced; output CRC verified; only selected pixels and trailing CRC changed.',
        device_tested=False)
    (args.output_dir/'patch_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2));print('Wrote',output)

if __name__=='__main__':main()
