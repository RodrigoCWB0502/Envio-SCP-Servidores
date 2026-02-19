# GAIO SCP Uploader

Automação em Python para envio de arquivos locais para o diretório `inputs` do GAIO via SCP, com controle de logs, movimentação pós-envio e suporte a execução recursiva.

---

## Visão Geral

Este projeto implementa um pipeline simples, rastreável e reproduzível de ingestão de arquivos:

files/ → Upload via SCP → GAIO inputs/
→ sent/
→ logs/

---

## Funcionalidades:

- Envio automático via SSH + SCP
- Criação automática do diretório remoto
- Verificação de existência remota
- Logs estruturados em JSONL
- Movimentação ou remoção de arquivos após envio
- Execução com dry-run
- Execução recursiva em subpastas
- Controle de overwrite

---

## Requisitos

- Linux ou WSL (recomendado)
- Python 3.10+
- SSH configurado
- Chave privada válida para acesso ao servidor
- Permissão de escrita no diretório remoto do GAIO

Instalar dependências:

```bash
pip install -r requirements.txt
```
---

## Configuração Inicial

Crie um arquivo .env na raiz do projeto com as variaveis do ambiente

GAIO_HOST=SEU_HOST
GAIO_PORT=PORTA_SSH
GAIO_USER=USUARIO_SSH
GAIO_KEY=/caminho/para/sua/chave.pem
GAIO_REMOTE_DIR=/caminho/remoto/inputs

LOCAL_FILES_DIR=files
LOCAL_SENT_DIR=sent
LOCAL_LOGS_DIR=logs
UPLOAD_PATTERN=*


---

## Configuração do Ambiente

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

---

## Execução

### Envio padrão

python3 src/upload_to_gaio_inputs.py --recursive

### Envio arquivos específicos

python3 src/upload_to_gaio_inputs.py --recursive --pattern "*.csv" # Exemplo com CSV

---

## Logs

As logs são em formatos JSONL

logs/upload_YYYYMMDD_HHMMSS.jsonl

Cada linha contém:

- Timestamp
- Caminho local
- Caminho remoto
- SHA256
- Status (uploaded, skipped, failed)
- Erro (se aplicável)
- Resumo da execução

Isso permite auditoria e rastreabilidade.

