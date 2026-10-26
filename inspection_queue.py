"""Fila de raízes independentes, mantendo o motor seguro de cada vistoria."""
import csv
import os
import time
import uuid
from pathlib import Path
from inspection import prepare_locations, run_inspections, walk_folders
from safe_files import reject_links
from admin import require_admin
from scan_index import analyze, ScanCancelled

COUNTERS=('visited','folders','converted','removed','retained','errors','before','after')


def selection_roots(paths):
    """Deduplicação apenas textual: nenhuma consulta ao servidor na interface."""
    unique=list(dict.fromkeys(Path(os.path.normpath(str(p))) for p in paths))
    if any(not p.is_absolute() for p in unique): raise ValueError('Informe caminhos absolutos para as pastas.')
    accepted=set()
    for root in sorted(unique,key=lambda p:len(p.parts)):
        if not any(parent in accepted for parent in root.parents): accepted.add(root)
    return [p for p in unique if p in accepted]


def normalize_roots(paths,stop=None):
    roots=[]
    for path in selection_roots(paths):
        if stop is not None and stop.is_set(): raise ScanCancelled()
        root=reject_links(path)
        if not root.is_dir(): raise ValueError(f'Pasta indisponível: {root}')
        roots.append(root)
    return selection_roots(roots)


def report_directory():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'HEICLite'/'relatorios-sem-backup'


def validate_queue(paths,backup,backup_enabled=True,stop=None):
    roots=normalize_roots(paths,stop)
    if not roots: raise ValueError('Selecione pelo menos uma pasta de vistorias.')
    backup=reject_links(backup if backup_enabled else report_directory())
    # Valida TODAS as raízes antes de criar diários ou converter a primeira foto.
    for root in roots:
        if root==backup or root in backup.parents or backup in root.parents:
            raise ValueError(f'O backup deve ficar fora de todas as pastas selecionadas e não pode conter uma delas: {root}')
    return roots,backup


def prepare_queue(paths,backup):
    roots,backup=validate_queue(paths,backup)
    namespaces=[prepare_locations(root,backup)[1] for root in roots]
    return roots,namespaces


def merge_reports(reports,backup):
    target=Path(backup)/('relatorio-fila-'+time.strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]+'.csv')
    with target.open('x',encoding='utf-8-sig',newline='') as output:
        writer=csv.writer(output,delimiter=';')
        header_written=False
        for report in reports:
            with Path(report).open(encoding='utf-8-sig',newline='') as source:
                reader=csv.reader(source,delimiter=';')
                header=next(reader)
                if not header_written: writer.writerow(header); header_written=True
                writer.writerows(reader)
        output.flush(); os.fsync(output.fileno())
    return str(target)


def run_inspection_queue(paths,backup,events,stop,quality=75,max_workers=4,backup_enabled=True,use_index=True):
    totals=dict.fromkeys(COUNTERS,0)
    reports=[]
    roots=[]
    completed=0
    fatal=False
    total_photos=0
    processed=0
    skipped_roots=[]
    plans={}
    removed=[]
    class Relay:
        def put(self,event):
            nonlocal fatal,completed,processed
            kind=event[0]
            if kind=='inspection_done':
                stats=event[1]
                for key in COUNTERS: totals[key]+=stats[key]
                if stats.get('report'): reports.append(stats['report'])
                if not stats['cancelled'] and not fatal: completed+=1
                return
            if kind=='inspection_fatal': fatal=True
            if kind=='inspection_result' and event[1].get('removed'):
                removed.append(event[1]['source'])
            if kind=='inspection_folder_done' and removed:
                try: plans[root].forget_removed(removed)
                except Exception as error: events.put(('analysis_notice',f'Índice não atualizado: {error}'))
                removed.clear()
            if kind=='inspection_result' and Path(event[1]['source']).suffix.lower() in ('.heic','.heif'):
                processed+=1
                events.put(('inspection_progress',processed,total_photos))
            index={'inspection_result':2,'inspection_scan':2,'inspection_folder':3}.get(kind)
            if index is not None:
                event=list(event)
                event[index]={key:totals[key]+event[index][key] for key in COUNTERS}
                event=tuple(event)
            events.put(event)
    try:
        require_admin()
        roots,backup=validate_queue(paths,backup,backup_enabled,stop)
        events.put(('inspection_counting',))
        eligible=[]
        for root in roots:
            events.put(('analysis_root',len(plans)+1,len(roots),str(root)))
            plan=analyze(root,events,stop,force=not use_index)
            plans[root]=plan
            count=plan.count()
            issues=list(plan.issues())
            if stop.is_set(): break
            total_photos+=count
            if count:
                eligible.append(root)
            else:
                # Sem fotos elegíveis, não cria namespace, diário ou CSV.
                # Falhas de leitura não podem ser confundidas com pasta vazia.
                totals['visited']+=plan.meta['visited']
                for result in issues:
                    totals['errors' if result['status']=='error' else 'retained']+=1
                    events.put(('inspection_result',result,dict(totals)))
                skipped_roots.append(str(root))
                events.put(('inspection_skipped',str(root),bool(issues)))
        events.put(('inspection_progress',0,total_photos))
        events.put(('analysis_finished',total_photos))
        if not stop.is_set():
            # Prepara apenas origens com HEIC, antes de iniciar qualquer remoção.
            for root in eligible:
                if stop.is_set(): break
                prepare_locations(root,backup)
        for index,root in enumerate(roots):
            if stop.is_set(): break
            if root not in eligible: continue
            events.put(('inspection_root',index+1,len(roots),str(root)))
            removed.clear()
            run_inspections(root,backup,Relay(),stop,quality,max_workers,backup_enabled,plan=plans[root])
            # Não revisita fotos já removidas em execuções futuras do mesmo índice.
            if removed:
                try: plans[root].forget_removed(removed)
                except Exception as error: events.put(('analysis_notice',f'Não foi possível atualizar o índice: {error}. Use Atualizar análise.'))
            if fatal or stop.is_set(): break
    except ScanCancelled:
        stop.set()
    except Exception as error:
        fatal=True; totals['errors']+=1
        events.put(('inspection_fatal',str(error)))
    finally:
        if reports:
            try: totals['report']=merge_reports(reports,backup)
            except Exception as error:
                fatal=True
                totals['errors']+=1
                totals['report']=reports[-1]
                events.put(('inspection_fatal',f'Não foi possível reunir os relatórios: {error}. Os relatórios individuais permanecem nas pastas de backup.'))
        totals.update(cancelled=stop.is_set(),failed=fatal,completed_roots=completed,total_roots=len(roots),reports=reports,skipped_roots=skipped_roots,backup_enabled=backup_enabled)
        events.put(('inspection_done',totals))


def preload_roots(paths,events,stop):
    results=[]
    error=None
    try:
        roots=normalize_roots(paths,stop)
        for index,root in enumerate(roots):
            if stop.is_set(): break
            events.put(('analysis_root',index+1,len(roots),str(root)))
            plan=analyze(root,events,stop,force=True)
            results.append(dict(root=str(root),photos=plan.count(),**{key:plan.meta[key] for key in ('created','visited','empty','errors')}))
    except ScanCancelled: stop.set()
    except Exception as exception: error=str(exception)
    finally: events.put(('preload_done',results,stop.is_set(),error))
