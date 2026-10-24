"""Conversão local; nunca apaga o original nem sobrescreve outro arquivo."""
from pathlib import Path
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)
EXTENSIONS = {'.heic', '.heif'}


def convert_photo(source: Path, quality: int = 90, output_folder: Path | None = None) -> Path:
    source = Path(source)
    if source.suffix.lower() not in EXTENSIONS:
        raise ValueError('Selecione uma foto HEIC ou HEIF.')
    if not 1 <= quality <= 100:
        raise ValueError('Qualidade deve estar entre 1 e 100.')
    destination = source.parent if output_folder is None else Path(output_folder)
    if not destination.is_dir():
        raise ValueError('A pasta de destino não existe ou não está disponível.')
    with Image.open(source) as original:
        original.load()
        photo = ImageOps.exif_transpose(original)
        if 'A' in photo.getbands():
            rgba = photo.convert('RGBA')
            rgb = Image.new('RGB', rgba.size, 'white')
            rgb.paste(rgba, mask=rgba.getchannel('A'))
        else:
            rgb = photo.convert('RGB')
        options = dict(quality=quality, optimize=True)
        exif = photo.getexif()
        if exif:
            options['exif'] = exif.tobytes()
        if photo.info.get('icc_profile'):
            options['icc_profile'] = photo.info['icc_profile']
        number = 0
        while True:
            suffix = '' if number == 0 else f' ({number})'
            output = destination / f'{source.stem}{suffix}.jpg'
            try:
                stream = output.open('xb')
                break
            except FileExistsError:
                number += 1
        try:
            with stream:
                rgb.save(stream, format='JPEG', **options)
            with Image.open(output) as check:
                check.load()
                if check.format != 'JPEG' or check.size != rgb.size:
                    raise ValueError('Não foi possível validar o JPEG.')
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return output
