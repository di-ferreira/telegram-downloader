# Gerador de Script para Backup Completo de Canal do Telegram

**Prompt:**

 Quero que você atue como um desenvolvedor Python especialista na API do Telegram utilizando a biblioteca **Telethon**.

 Crie um script completo para realizar o backup integral de um canal do Telegram.

 O script deve atender aos seguintes requisitos:

## Configuração

* utilizar Python 3.12+
* utilizar Telethon
* permitir configuração de:

  * API_ID
  * API_HASH
  * nome do canal
  * pasta de saída

## Download das mensagens

 O script deve percorrer todas as mensagens do canal desde a primeira até a última.

 Deve salvar:

* texto
* legendas
* data
* id da mensagem
* remetente (quando existir)
* tipo da mensagem
* quantidade de visualizações (quando disponível)

## Download das mídias

 Baixar automaticamente:

* fotos
* vídeos
* documentos
* PDFs
* GIFs
* stickers
* áudios
* voice messages
* músicas
* arquivos compactados
* qualquer mídia suportada pela API

 Mantendo os nomes originais sempre que possível.

 Caso não exista nome, gerar um nome utilizando o ID da mensagem.

## Estrutura das pastas

 Organizar os arquivos da seguinte forma:

 ``` text
 backup/
 │
 ├── media/
 │     ├── photos/
 │     ├── videos/
 │     ├── documents/
 │     ├── audios/
 │     ├── gifs/
 │     ├── stickers/
 │     └── others/
 │
 ├── messages.json
 ├── messages.csv
 └── log.txt
 ```

## Banco de dados

 Além dos arquivos JSON e CSV, criar opcionalmente um banco SQLite contendo:

* id
* data
* texto
* caminho da mídia
* tipo da mídia
* nome do arquivo
* tamanho
* mime type

## Performance

 Implementar:

* barra de progresso com tqdm
* download assíncrono
* tratamento de FloodWait
* retomada automática caso o script seja interrompido
* logs de erro
* limite configurável de downloads simultâneos

## Organização do código

 Separar em funções:

 ``` text
 login()
 create_folders()
 download_media()
 save_message()
 export_csv()
 export_json()
 export_sqlite()
 resume_backup()
 main()
 ```

## Recursos extras

 Implementar:

* opção para baixar apenas mensagens novas
* opção para baixar apenas mídias
* opção para baixar apenas textos
* filtro por data inicial e final
* filtro por tipo de mídia
* opção para ignorar arquivos já baixados
* hash MD5 para evitar duplicatas

## Dependências

 Gerar também:

* requirements.txt
* arquivo .env
* README.md explicando como configurar API_ID e API_HASH
* comentários detalhados em todo o código

 O código deve seguir boas práticas de Python, ser modular, reutilizável e pronto para execução.
