# HEICLite

Conversor HEIC/HEIF para JPEG no Windows, com processamento paralelo, qualidade ajustável, seleção da pasta de destino e resumo da redução de tamanho.

Versão 1.2 — Parte 1, incremento 2.

Aplicativo local para Windows, em português, para preparar fotos para os programas da imobiliária.

## Como usar

1. Se já tiver o executável, abra `dist/versao-1.2/Conversor HEIC JPEG.exe` com dois cliques (ou `iniciar.bat`). Ao baixar o código deste repositório, execute primeiro `instalar.bat` com Python 3.13 instalado; depois use `iniciar.bat`. Para gerar seu próprio executável, execute `gerar_executavel.bat`. O executável não precisa de Python nem do plugin HEIC do Windows.
2. Clique em **Adicionar fotos** para escolher várias fotos, ou em **Adicionar pasta** para incluir os HEIC / HEIF daquela pasta. Subpastas não são incluídas.
3. Escolha a qualidade JPEG na lista ou digite qualquer inteiro de **1 a 100**, incluindo **75**. O valor inicial continua sendo **90**.
4. Clique em **Ativar aceleração** se quiser converter várias fotos ao mesmo tempo. O botão pode ser usado antes ou durante a conversão.
5. Se quiser, marque **Após converter, selecionar os HEICs convertidos no Explorador**.
6. Deixe **Mesma pasta** selecionado para salvar ao lado de cada original. Para salvar em outro lugar, marque **Outra pasta** e clique em **Escolher pasta…** antes de converter.
7. Clique em **Converter fotos**, no topo da janela. Cada JPEG é salvo no destino escolhido, com extensão `.jpg`. Ao terminar, confira o resumo com o tamanho total de HEIC e JPEG, a economia e o percentual total (ou o aumento, se os JPEGs ficarem maiores).
8. Confira os JPEGs. Use **Selecionar originais no Explorador**, caso não tenha marcado a opção automática. Apenas os originais convertidos com sucesso são selecionados; se houver várias pastas, cada pasta será aberta.
9. No Explorador, pressione **Delete** quando decidir apagar os originais. O aplicativo não apaga fotos.

## Comportamento

- Fotos não são enviadas à internet; a conversão funciona offline.
- A janela tem tamanho fixo, ajustado à área disponível da tela. Os comandos ficam fora da área rolável da lista e **Converter fotos** aparece no topo.
- Aceleração usa processos separados para converter até quatro fotos simultaneamente, limitada pelo número de processadores disponíveis. Começa desativada. Ao desativá-la durante a conversão, as fotos em andamento terminam normalmente e as próximas são processadas uma por vez. O ganho depende das fotos, do processador e do disco; o modo paralelo usa mais memória.
- A lista mostra os tamanhos de cada HEIC e JPEG, além da redução percentual: `(tamanho HEIC − tamanho JPEG) / tamanho HEIC × 100`. Se o JPEG ficar maior, mostra **Aumento**, com o percentual correspondente.
- O resumo final soma os bytes dos originais e dos JPEGs convertidos com sucesso que estão na lista. O percentual é calculado sobre esses totais, e não pela média dos percentuais de cada foto. Falhas não entram nos totais. Ao adicionar novas fotos e converter, o resumo inclui também os sucessos anteriores da lista. **Limpar lista** reinicia os totais.
- **Mesma pasta** é o padrão em cada abertura do programa. **Outra pasta** salva todos os JPEGs na pasta escolhida, sem mover os HEICs. Fotos com nomes iguais recebem sufixos numéricos, inclusive na conversão paralela. A qualidade e o destino são definidos antes de iniciar o lote.
- Não sobrescreve arquivos: se `foto.jpg` já existir, cria `foto (1).jpg`, e assim por diante.
- Falhas aparecem por arquivo; as outras fotos continuam sendo convertidas. Clique duas vezes em uma linha para consultar detalhes.
- Mantém a resolução, a orientação decodificada, os metadados EXIF e o perfil de cores quando disponíveis. Transparência é composta sobre branco.
- Converte a imagem principal de cada arquivo. Sequências, fotos auxiliares, mapas de profundidade e componentes de Live Photos não são exportados.
- JPEG é um formato com perdas e o tamanho final não é garantido menor que o HEIC. Qualidade menor costuma produzir arquivos menores. HDR é convertido para 8 bits pela biblioteca.
- Fotos já convertidas na lista não são convertidas novamente. Para repetir com outra qualidade ou outro destino, limpe a lista e adicione as fotos outra vez.
- Para selecionar os originais, o programa verifica se os HEICs não foram alterados desde a conversão e se os JPEGs gerados ainda existem.

## Desenvolvimento e próximos incrementos

Python 3.13, Tkinter, Pillow e pillow-heif. A conversão fica em `converter.py`, o agendamento paralelo em `batch.py`, a interface em `app.py`, e a integração com o Explorador em `explorer.py`. O agendamento usa [ProcessPoolExecutor do Python](https://docs.python.org/3.13/library/concurrent.futures.html#processpoolexecutor).

Para preparar o ambiente, execute `instalar.bat` (requer internet e Python instalado). Para gerar o executável, execute `gerar_executavel.bat`. Para executar os testes:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Para verificar também o executável empacotado e os processos que ele inicia, depois de gerar o EXE:

```powershell
$env:HEIC_TEST_EXECUTABLE = (Resolve-Path '.\dist\versao-1.2\Conversor HEIC JPEG.exe').Path
.\.venv\Scripts\python.exe -m unittest -v
```

Esse teste usa apenas fotos sintéticas em uma pasta temporária.

A leitura HEIC usa o [plugin oficial pillow-heif para Pillow](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html).
