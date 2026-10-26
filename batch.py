"""Agenda somente as fotos necessárias e permite mudar o paralelismo em execução."""
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from converter import convert_photo


def convert_job(path, quality, output_folder=None):
    path = Path(path)
    before = path.stat()
    output = convert_photo(path, quality, output_folder)
    return output, (before.st_size, before.st_mtime_ns), output.stat().st_size


def run_batch(work, quality, events, accelerated, max_workers, output_folder=None):
    pending = iter(work)
    active = {}
    exhausted = False
    unfinished = {row for row, _path in work}
    try:
        with ProcessPoolExecutor(max_workers=max_workers,
                                 mp_context=multiprocessing.get_context('spawn')) as pool:
            while active or not exhausted:
                limit = max_workers if accelerated.is_set() else 1
                while not exhausted and len(active) < limit:
                    try:
                        row, path = next(pending)
                    except StopIteration:
                        exhausted = True
                        break
                    future = pool.submit(convert_job, path, quality, output_folder)
                    active[future] = row
                    events.put(('working', row))
                if not active:
                    continue
                completed, _ = wait(active, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in completed:
                    row = active.pop(future)
                    try:
                        output, signature, size = future.result()
                        events.put(('ok', row, output, signature, size))
                    except Exception as error:
                        events.put(('error', row, str(error)))
                    unfinished.discard(row)
    except Exception as error:
        for row in unfinished:
            events.put(('error', row, f'Falha no processamento: {error}'))
    finally:
        events.put(('done',))


def format_size(size):
    if size is None:
        return '—'
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if abs(value) < 1000 or unit == 'PB':
            digits = 0 if unit == 'B' or abs(value) >= 10 else 2
            number = f'{value:.{digits}f}'
            if digits: number = number.rstrip('0').rstrip('.')
            return f'{number.replace(".", ",")} {unit}'
        value /= 1000


def format_reduction(before, after):
    if before <= 0:
        return '—'
    reduction = (before - after) / before * 100
    value = f'{abs(reduction):.1f}%'.replace('.', ',')
    return value if reduction >= 0 else f'Aumento {value}'


def format_summary(sizes):
    sizes = list(sizes)
    if not sizes:
        return 'Nenhuma foto convertida com sucesso. Não há tamanhos para comparar.'
    before = sum(pair[0] for pair in sizes)
    after = sum(pair[1] for pair in sizes)
    difference = before - after
    comparison = f'Total convertido ({len(sizes)} foto(s)): HEIC {format_size(before)} → JPEG {format_size(after)}'
    percentage = format_reduction(before, after)
    if difference >= 0:
        detail = f'Economia: {format_size(difference)} • redução de {percentage}'
    else:
        detail = f'Aumento: {format_size(-difference)} • {percentage.removeprefix("Aumento ")}'
    return f'{comparison}\n{detail}'
