# HEICLite

Conversor HEIC/HEIF para JPEG no Windows, com conversão em massa de subpastas, processamento paralelo, backup opcional e verificado dos originais e acesso administrativo ao modo de vistorias.

**Versão 2.11.** Aplicativo local em português. Não envia fotos para a internet nem depende do plugin HEIC do Windows.

## Abrir

Use `dist/versao-2.11/HEICLite.exe` ou `iniciar.bat`. O executável não exige Python. Para executar o código, instale Python 3.13, execute `instalar.bat` e depois `iniciar.bat`. `gerar_executavel.bat` gera o aplicativo com ícone e temas incluídos.

## Converter fotos

- Use **+ Fotos** ou **+ Pasta**. Este modo inclui somente os arquivos da pasta escolhida, sem suas subpastas.
- Qualidade padrão **75**, com opções na lista e entrada de qualquer inteiro de 1 a 100.
- **Escolher destino…** é obrigatório: selecione uma pasta diferente das pastas de origem. Cancelar o seletor mantém o destino já escolhido. A conversão é bloqueada se o destino for uma das pastas originais.
- Clique em **Converter fotos**. Este modo mantém os HEICs e não pede administrador.

## Vistorias em lote — conversão em massa automática

Pastas sem HEIC/HEIF são ignoradas: não criam pasta de backup, diário nem relatório vazio. A busca continua nas subpastas mesmo quando a pasta principal contém somente JPG/PNG. Se houver formatos misturados na mesma pasta, apenas HEIC/HEIF são processados. Origens sem HEIC acessível aparecem no resumo e no histórico; falhas de acesso aparecem como ocorrências, sem serem confundidas com pastas vazias. Backups antigos não são apagados.

**Selecionar várias pastas:** use Ctrl/Shift no seletor nativo ou adicione pastas em etapas. Seleções repetidas são eliminadas; quando uma pasta principal está na fila, suas subpastas não aparecem novamente como origens independentes. Todas as pastas de backup são verificadas contra todas as origens antes de iniciar a conversão. O programa termina cada origem e suas subpastas antes de passar à próxima, mantendo até quatro fotos em paralelo na pasta atual.

**Arrastar e soltar:** disponível nas janelas normal e administrativa. No módulo **Converter fotos**, solte fotos HEIC/HEIF para adicioná-las à lista; solte pastas para preparar a fila de vistorias. No módulo **Vistorias em lote**, solte pastas e confira em **Ver fila**. Fotos soltas nesse módulo recebem orientação para usar Converter fotos; outros formatos são ignorados. Soltar itens nunca inicia conversão ou exclusão. O destino da conversão comum continua obrigatório, e a vistoria mantém a confirmação e a validação. O backup fica ativado por padrão.

A área registra também os componentes internos sob o ponteiro. Na janela administrativa, a recepção do Explorer usa uma exceção por janela apenas para as mensagens de transferência de arquivos (`WM_DROPFILES` e `WM_COPYGLOBALDATA`), sem alterar o UAC ou as permissões das pastas. Caminhos recebidos são tratados como seleção e revalidados antes de processar. A conta usada na janela ainda precisa ter acesso ao caminho; políticas do ambiente podem restringir transferências entre sessões. [Filtro de mensagens por janela da Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-changewindowmessagefilterex).

Ao abrir Vistorias pela janela normal, a fila continua sendo transferida à janela administrativa para revisão e confirmação. A transferência contém somente caminhos e opções com verificação de integridade; não contém fotos ou senhas.

Cada origem mantém seu próprio diário e backup `HEICLite-...`, que pode ser escolhido separadamente para restauração. O resumo acumula os resultados de toda a fila, e **Abrir relatório** abre um CSV reunindo os relatórios das origens executadas. **Parar com segurança** também impede o início das origens seguintes. Uma falha que interrompa o processamento de uma origem interrompe a fila; falhas isoladas em fotos continuam registradas como antes.

**Pastas do servidor:** os botões de pasta abrem o seletor moderno do Windows, com a lateral do Explorer (Este Computador, unidades mapeadas e Rede), como o seletor de fotos. Escolha a unidade e navegue normalmente; também é possível colar um caminho UNC na barra de endereço ou nos campos de origem e backup.

Ao abrir a janela administrativa pelo programa, os compartilhamentos mapeados da sessão original são enviados como atalhos UNC para o seletor. Isso não recria letras de unidade, não transfere credenciais e não altera permissões. A conta administrativa continua precisando ter acesso ao servidor. Se o programa for iniciado diretamente como administrador, ele verá os locais disponíveis nessa sessão.

1. Clique em **Vistorias em lote**. O Windows solicita elevação e abre outra janela, identificada como **Administrador**. A janela comum continua disponível.
2. Informe uma conta de administrador na tela do Windows. Pode ser `DOMINIO\usuario`, desde que a conta tenha permissão de administrador no computador e acesso às pastas. O HEICLite não recebe nem armazena senhas.
3. Use **Adicionar pastas** para selecionar várias pastas com Ctrl/Shift. Repita para adicionar pastas de outros locais. Confira ou remova itens em **Ver / remover**, e escolha **Backup dos HEICs**. O backup deve estar fora da árvore de vistorias e não pode ser uma pasta que contenha essa árvore.
4. Clique em **Iniciar vistorias** e confira a lista de origens e o destino do backup na confirmação.
5. O programa percorre a raiz e todas as subpastas, terminando uma pasta antes de iniciar a próxima. Até quatro fotos da pasta atual são convertidas em processos paralelos, limitado pelo número de processadores. Não há botão de aceleração.
6. Cada JPEG fica na pasta de seu HEIC. Com o backup ativado, o HEIC sai da pasta da vistoria somente depois da cópia integral de backup, da validação do JPEG e da gravação do diário. O modo sem backup é descrito abaixo.
7. **Parar com segurança** impede novas conversões e aguarda as fotos já iniciadas. Para continuar, selecione as mesmas pastas e execute novamente. Fotos retiradas não são reencontradas; registros verificados permitem recuperar interrupções anteriores quando possível.

A lista mostra tamanhos, redução, JPEG gerado e pasta de destino. O duplo clique mostra caminhos completos, backup e detalhes. No modo de vistorias, a lista mantém os últimos 1.000 resultados para limitar o consumo de memória; **Abrir relatório** abre o CSV completo da execução.

### Converter sem backup (opcional)

A opção **Criar backup dos HEICs (recomendado)** fica ativada ao abrir o programa. Para desativá-la, desligue o controle em **Vistorias em lote**. O campo de backup fica desabilitado e o aviso **SEM BACKUP** aparece no módulo. Ao iniciar, uma confirmação específica explica a remoção definitiva; cancelar não começa a operação.

Nesse modo, o aplicativo converte diretamente do original bloqueado, sem copiar HEICs para outra pasta. O JPEG é sincronizado em disco, reaberto e validado; o original é conferido e o diário é confirmado antes da remoção. Falhas de conversão, validação ou gravação anterior à remoção mantêm o HEIC. Arquivos HEIF com múltiplas imagens continuam preservados.

**Depois da remoção, não há restauração do HEIC pelo programa.** JPEG usa compressão com perda e não guarda todos os dados do original. Falhas físicas posteriores à remoção não têm a proteção de uma cópia HEIC. A redução do tempo depende do disco, da rede e das fotos; as validações continuam sendo feitas.

Somente diários e relatórios ficam em `%LOCALAPPDATA%/HEICLite/relatorios-sem-backup`, na conta que executa as vistorias. Nenhuma cópia HEIC é criada ali. A localização dos relatórios deve ficar fora das origens selecionadas. O histórico identifica operações sem backup; elas não entram na restauração de originais. Backups de execuções anteriores permanecem intactos.

### Proteção dos originais

- Com backup ativado: backup integral com SHA-256 conferido antes da remoção, mantendo os bytes originais, inclusive informações que não cabem no JPEG.
- JPEG escrito em arquivo temporário, sincronizado em disco, reaberto e decodificado por completo. Formato e dimensões são conferidos antes da publicação.
- Arquivos existentes não são sobrescritos. Colisões recebem nomes como `foto (1).jpg`.
- Durante a etapa crítica, o Windows bloqueia escrita e renomeação do original, backup e JPEG. A remoção usa o identificador do próprio original aberto.
- Diário SQLite confirmado em disco antes da remoção. Falhas de backup, gravação ou validação mantêm o original. Falhas depois da remoção são informadas com JPEG e backup já existentes.
- HEIF com múltiplas imagens é preservado para revisão. Links, junções e pontos de redirecionamento são ignorados; arquivos com múltiplos links físicos ou bloqueados por outros programas são preservados.
- A varredura não carrega todas as fotos na memória. Uma segunda execução no mesmo backup é bloqueada enquanto a primeira está ativa.

**JPEG 75 tem perdas.** HDR é convertido para 8 bits, transparência é composta sobre branco e componentes auxiliares não são exportados. Resolução, orientação e EXIF/perfil de cores são mantidos quando suportados. O JPEG pode ficar maior que o HEIC.

**Mantenha o backup.** Nenhum programa garante risco zero diante de falha física de disco, falta de energia ou alteração externa das pastas. Para vistorias importantes, mantenha uma cópia independente, de preferência em outro disco ou servidor, e valide primeiro uma cópia de uma vistoria representativa. É necessário espaço para os HEICs de backup e os JPEGs. A economia exibida compara os formatos e não desconta o espaço ocupado pelo backup.

### Restaurar HEICs

Clique em **Restaurar originais** (também exige administrador) e selecione a pasta `HEICLite-...` que contém `manifesto.sqlite3`. O programa confere os backups e copia os HEICs de volta aos caminhos registrados. Não sobrescreve arquivos existentes, não remove JPEGs e não apaga backups. Se um backup estiver alterado, a restauração para e informa a falha; arquivos já restaurados permanecem disponíveis. Preserve a pasta inteira do backup, incluindo diário e subpastas.

### Administração na empresa

A proteção exige um processo elevado pelo UAC, inclusive nas rotinas de conversão de vistorias e restauração. Administradores locais também são aceitos; não há restrição a um grupo específico do domínio. A política de UAC da empresa determina se haverá pedido de credenciais ou confirmação. Feche a janela administrativa ao terminar, pois ela permanece autorizada enquanto aberta.

Isso não altera permissões das pastas. Para impedir exclusões pelo Explorer ou outros programas, a TI precisa configurar permissões NTFS e do compartilhamento. Instale a versão distribuída em uma pasta protegida contra alterações por usuários comuns. Contas diferentes podem não enxergar unidades de rede mapeadas; use caminhos UNC como `\\servidor\vistorias` com uma conta autorizada. Consulte a [documentação do UAC da Microsoft](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/how-it-works).

## Pré-análise e seleção de grandes volumes

A seleção de pastas pelo seletor nativo é adicionada à fila sem consultar a existência de cada caminho no servidor. A deduplicação usa somente os textos dos caminhos, em vez de percorrer repetidamente a rede. Ao arrastar itens, a classificação de fotos e pastas roda em segundo plano. O seletor nativo do Windows ainda pode demorar ao navegar ou listar compartilhamentos; é possível evitar essa navegação colando o caminho em **Pré-analisar…**.

Ao iniciar vistorias, a validação e a análise rodam fora da interface. Uma janela menor mostra caminho atual, pastas lidas, HEIC/HEIF encontrados, pastas sem HEIC e falhas. **Cancelar análise** impede o início da conversão. Se o Windows estiver aguardando uma resposta do servidor, o cancelamento aguarda essa chamada de leitura terminar; a interface continua disponível.

**Para pré-carregar:** abra **Pré-analisar…**, cole a raiz (por exemplo `\\servidor\vistorias`) e clique em **Analisar caminho**, ou use **Analisar fila** para as pastas já selecionadas. Essa operação somente lê nomes e salva o índice local: não converte, copia nem apaga fotos. O índice guarda caminhos e ocorrências em `%LOCALAPPDATA%/HEICLite/indices`, na conta do Windows que fez a análise. Não guarda o conteúdo das fotos.

Com **Usar análise salva** marcado, a conversão reutiliza a análise disponível, inclusive quando você seleciona uma subpasta de uma raiz pré-analisada. Pastas conhecidas sem HEIC são ignoradas. Se não houver uma análise compatível, ela é feita uma vez e usada diretamente pela conversão: não há uma segunda varredura recursiva. A conversão continua terminando uma pasta antes da próxima, com até quatro fotos em paralelo.

**Atualização:** o índice representa a data da análise. Arquivos novos, inclusive em pastas antes vazias, só são descobertos ao executar novamente **Pré-analisar…** ou desmarcar **Usar análise salva** ao iniciar. A primeira análise ainda precisa ler a árvore inteira e pode demorar na rede. Índices de análises canceladas não são publicados; uma versão anterior completa é mantida. Origens com falhas de leitura precisam ser reanalisadas.

Arquivos removidos com sucesso pelo programa saem do índice. Arquivos que desapareceram ou foram renomeados externamente são relatados como ocorrências: o programa não tenta adivinhar outro arquivo para substituí-los. Cada foto presente ainda passa pelas validações, bloqueios e verificações de JPEG e backup antes de remover o HEIC. O índice não autoriza exclusão por si só.

## Histórico e acompanhamento

**Histórico** mostra as operações iniciadas a partir da versão 2.4: data, módulo, origens selecionadas, pastas efetivamente processadas, fotos convertidas, falhas, preservadas, tamanhos, duração e acesso ao relatório de vistorias. É salvo em `%LOCALAPPDATA%/HEICLite/historico.sqlite3`, sem fotos ou credenciais. Contas diferentes do Windows têm históricos separados, inclusive quando a elevação usa outro usuário do domínio. Operações antigas não são importadas automaticamente.

A operação é registrada ao iniciar e os resultados são atualizados ao terminar ou parar com segurança. Se o processo for encerrado abruptamente, fica identificada como **sem registro de conclusão**; o diário e os relatórios das vistorias continuam sendo a referência para recuperação.

Trocar de módulo mantém a lista, os resultados, o resumo, o percentual e o tempo de cada módulo durante a sessão. A troca fica bloqueada enquanto há uma operação ativa. Fechar o programa encerra a sessão; o histórico continua disponível ao reabrir.

O tempo decorrido inclui contagem, conversão, backup, validação e exportação. Nas vistorias, a janela de análise mostra pastas lidas, fotos encontradas, pastas sem HEIC, falhas e caminho atual, com cancelamento. O total de pastas é desconhecido durante a descoberta, portanto essa etapa usa animação e contadores, sem porcentagem fictícia. Depois, a conversão avança por fotos processadas e só chega a 100% ao finalizar. Em caso de parada, mantém o percentual alcançado. Se arquivos forem adicionados ou removidos externamente durante a execução, a contagem inicial pode divergir dos resultados. Falhas e fotos preservadas contam como processadas, mas ficam discriminadas no resultado.

## Aparência e resumo

Temas **Claro**, **Escuro** e **Automático**, que acompanha o Windows. Interface com controles acima da lista, janela redimensionável e tamanho mínimo. Ícone próprio em `assets/heiclite.ico`. Barras de rolagem arredondadas e barra de progresso com porcentagem. A barra de título acompanha a cor do aplicativo no Windows 11; versões anteriores usam o suporte de tema disponível no sistema. [API de cores da Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute).

Os tamanhos usam unidades decimais compactas (1 GB = 1.000 MB): por exemplo, **950 MB** ou **2,86 GB**.

O resumo soma os bytes das conversões concluídas com sucesso. O percentual usa esses totais, sem fazer média dos percentuais individuais. Erros e originais preservados não entram na economia; o relatório registra seus motivos.

## Desenvolvimento e testes

Python 3.13, CustomTkinter, Pillow e pillow-heif. Interface em `ui.py`; conversão comum em `converter.py`; varredura, backup e restauração em `inspection.py`; bloqueios em `safe_files.py`; UAC em `admin.py`; agendamento comum em `batch.py`.

```powershell
.\.venv\Scripts\python.exe -m unittest test_converter test_inspection test_inspection_queue test_operation_ui test_admin test_network_folders test_windows_folders test_folder_drop test_scan_index -v
.\.venv\Scripts\python.exe build_app.py
$env:HEIC_TEST_EXECUTABLE = (Resolve-Path 'dist/versao-2.11/HEICLite.exe').Path
.\.venv\Scripts\python.exe -m unittest test_converter test_admin -v
```

Os testes usam fotos sintéticas e pastas temporárias: backup e restauração byte a byte, corrupção, colisões, falhas de gravação, retomada, cancelamento, barreira entre pastas, 5.001 subpastas, controles e bloqueio sem administrador. A autorização é simulada nos testes de vistorias; credenciais reais do domínio precisam ser validadas pela TI no computador de destino.

Fotos de imóveis, backups e executáveis não devem ser versionados.

A recepção de arrastes usa uma fila: callbacks nativos não chamam Tcl/Tk. O teste de regressão entrega `WM_DROPFILES` por `PostMessageW` durante `mainloop`, reproduzindo a falha de fechamento corrigida na versão 2.8.
