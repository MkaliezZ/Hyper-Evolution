"""Original-page identity and bounded decoding. Never transforms the original bytes."""
import base64
import hashlib
import io
import warnings

def decode_original(encoded):
    from PIL import Image
    try:
        raw=base64.b64decode(encoded,validate=True)
        if not 1<=len(raw)<=2*1024*1024:raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ['PNG','JPEG'] or getattr(image,'n_frames',1)!=1:raise ValueError()
                width,height=image.size
                if width*height>12000000 or max(width,height)>8000:raise ValueError()
                fmt=image.format
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load();orientation=image.getexif().get(274,1)
    except Exception:raise ValueError('请使用完整的单页 PNG / JPEG；单图不超过2MB、1200万像素和8000像素边长。') from None
    return raw,{'source_hash':hashlib.sha256(raw).hexdigest(),'mime':'image/png' if fmt=='PNG' else 'image/jpeg',
        'width':width,'height':height,'orientation':orientation,'bytes':len(raw),
        'coordinate_space':'normalized_display_orientation','quality':{'processing':'decoded_original',
        'domain_review':'unknown','task_fit':'requires_task_judgment','ocr':'not_performed'}}

def check_original(raw,expected_hash):
    if hashlib.sha256(raw).hexdigest()!=expected_hash:raise ValueError('原图内容发生变化，停止使用该来源')
    return raw
