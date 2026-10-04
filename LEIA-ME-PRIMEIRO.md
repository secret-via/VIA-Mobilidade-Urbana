# Como abrir em outro computador

Este pacote já inclui o modelo treinado em `runs\transito\weights\best.pt` e a interface web VIA | WD integrada ao backend.

## Antes de começar

1. Instale Python 3.10 ou superior e marque **Add Python to PATH** durante a instalação.
2. Conecte a câmera USB antes de abrir o sistema.
3. Descompacte todo o ZIP em uma pasta normal, por exemplo `C:\Projetos\transito`.

## Abrir

1. Dê duplo clique em `INICIAR_DASHBOARD.bat`.
2. Na primeira execução, aguarde a criação do ambiente e a instalação das dependências. É necessário internet apenas nessa primeira vez.
3. Quando aparecer `Dashboard: http://127.0.0.1:5000`, abra esse endereço no navegador.

## Se a câmera não abrir

Feche o programa com `Ctrl+C`, abra o terminal dentro da pasta do projeto e tente:

```powershell
.venv\Scripts\activate
python scripts\dashboard.py --camera 1
```

Tente `--camera 0`, depois `--camera 1` e `--camera 2` até encontrar a câmera correta.

## Banco de dados

O sistema funciona sem PostgreSQL. Eventos locais continuam disponíveis em `logs\events.jsonl`; ausência do banco não interrompe a IA nem o vídeo.

## Não mova estes itens

- `runs\transito\weights\best.pt`: seu modelo treinado.
- `dashboard\`: interface web integrada.
- `requirements.txt`: dependências necessárias no primeiro uso.
