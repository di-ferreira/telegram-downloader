# Criador de Canal e Restaurador Completo de Backup do Telegram

**Prompt:**

 Quero que você atue como um desenvolvedor Python especialista na API do Telegram utilizando a biblioteca **Telethon**.

 Crie um sistema completo capaz de restaurar um backup previamente realizado de um canal do Telegram, recriando todo o conteúdo em um novo canal.

 O sistema deve ser modular, escalável, totalmente comentado e seguir boas práticas de desenvolvimento em Python.

---

## Objetivo

O script deverá:

1. Criar automaticamente um novo canal no Telegram.
2. Configurar o canal.
3. Ler o backup existente.
4. Publicar novamente todas as mensagens.
5. Reenviar todas as mídias.
6. Preservar a ordem cronológica das mensagens.
7. Ser capaz de interromper e continuar exatamente do ponto onde parou.

---

## Configuração

O script deverá utilizar:

* Python 3.12+
* Telethon
* asyncio
* tqdm
* SQLite
* python-dotenv

Permitir configuração através de `.env`:

``` text
API_ID=

API_HASH=

PHONE=

CHANNEL_NAME=

CHANNEL_DESCRIPTION=

CHANNEL_USERNAME=

BACKUP_FOLDER=
```

---

## Estrutura esperada do backup

O script deverá utilizar exatamente a estrutura abaixo:

``` text
backup/

├── media/

│   ├── photos/

│   ├── videos/

│   ├── documents/

│   ├── audios/

│   ├── gifs/

│   ├── stickers/

│   └── others/

├── messages.json

├── messages.csv

├── backup.db

└── log.txt
```

Caso exista SQLite, utilizá-lo como fonte principal.

Caso contrário utilizar o JSON.

---

## Criação do canal

O script deverá:

* criar um novo canal automaticamente
* definir nome
* definir descrição
* configurar username caso disponível
* retornar o ID do canal criado

---

## Publicação das mensagens

Percorrer todas as mensagens em ordem cronológica.

Para cada registro:

Publicar:

* texto
* legenda
* emojis
* markdown
* links

Mantendo exatamente o conteúdo original.

---

## Publicação das mídias

Caso exista mídia:

Enviar automaticamente:

* fotos
* vídeos
* PDFs
* documentos
* GIFs
* stickers
* áudios
* voice
* músicas
* arquivos zip
* qualquer arquivo existente

Sempre utilizando o arquivo salvo no backup.

Caso o arquivo esteja ausente:

* registrar no log
* continuar o processo

---

## Ordem cronológica

As mensagens deverão ser restauradas exatamente na ordem em que foram publicadas originalmente.

Não utilizar processamento paralelo para envio das mensagens.

---

## Intervalos de segurança

Implementar automaticamente:

* delay aleatório entre mensagens
* delay maior após determinado número de envios
* tratamento automático de FloodWait
* espera automática quando solicitado pela API

Nunca perder o progresso.

---

## Controle de progresso

Criar um banco SQLite contendo:

``` text
message_id_original

message_id_novo

status

data_envio

tentativas

erro
```

Assim o script poderá continuar exatamente do ponto onde foi interrompido.

---

## Logs

Criar:

``` text
logs/

restore.log

errors.log

missing_media.log
```

Registrar:

* criação do canal
* envio de mensagens
* envio de mídias
* erros
* arquivos inexistentes
* FloodWait
* retomadas

---

## Barra de progresso

Utilizar tqdm mostrando:

``` text
Mensagens enviadas

Mensagens restantes

%

Tempo restante

Velocidade
```

---

## Organização do código

Separar em módulos:

``` text
config.py

telegram_client.py

database.py

restore.py

channel_creator.py

media_sender.py

logger.py

utils.py

main.py
```

---

## Funções esperadas

``` text
login()

create_channel()

load_backup()

load_messages()

send_text()

send_media()

restore_message()

save_progress()

resume_restore()

create_logs()

main()
```

---

## Recursos extras

Adicionar suporte para:

### Restaurar apenas um intervalo

``` text
Data inicial

Data final
```

---

### Restaurar apenas mídias

``` text
--only-media
```

---

### Restaurar apenas textos

``` text
--only-text
```

---

### Restaurar apenas PDFs

``` text
--type=document
```

---

### Restaurar apenas fotos

``` text
--type=photo
```

---

### Restaurar apenas vídeos

``` text
--type=video
```

---

### Restaurar apenas mensagens que falharam

``` text
--retry-errors
```

---

### Simulação

Criar um modo:

``` text
--dry-run
```

Que apenas mostra:

* quantidade de mensagens
* quantidade de mídias
* tamanho total
* tempo estimado
* possíveis erros

Sem publicar nada.

---

## Segurança

O script deve:

* validar existência dos arquivos
* validar integridade do backup
* validar conexão com Telegram
* impedir mensagens duplicadas
* impedir reenvio de mensagens já restauradas

---

## Arquivos adicionais

Gerar também:

* `requirements.txt`
* `.env.example`
* `README.md`
* `config.ini`
* documentação completa de instalação
* instruções para obtenção do API_ID e API_HASH
* explicação detalhada do fluxo de execução

---

## Qualidade do código

O código deve ser:

* totalmente comentado
* modular
* orientado a objetos quando fizer sentido
* reutilizável
* compatível com Linux, Windows e macOS
* preparado para canais com mais de 100 mil mensagens
* otimizado para baixo consumo de memória
* pronto para produção, com tratamento robusto de exceções e recuperação automática em caso de interrupção.
