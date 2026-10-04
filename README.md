# Câmera Inteligente de Trânsito com YOLO26

Sistema local para uma maquete de trânsito: YOLO26 detecta, ByteTrack mantém IDs e o motor de tráfego interpreta fluxo, paradas e congestionamento. Um agente local baseado em regras registra experiências e conduz aprendizado contínuo **controlado**. Uma previsão nunca vira rótulo sem confirmação humana.

## Arquitetura

```text
câmera/vídeo → YOLO26 + ByteTrack → contagem/trilhas/paradas → eventos + memória
                                      ↓
                               agente de regras → casos incertos → revisão humana
                                      ↓                                 ↓
                          treinamento de candidato ← dataset versionado ← aprovados
                                      ↓
                         avaliação → promoção ou rejeição → histórico
```

O código existente permanece em `utils/`: `pipeline.py` executa a visão, `tracking.py` guarda trajetórias, `counting.py` conta cruzamentos e `traffic.py` calcula o indicador heurístico. Os novos módulos têm responsabilidades separadas:

- `traffic/events.py`: eventos JSON Lines em `logs/events.jsonl`.
- `agent/`: agente local e memória persistente em `data/memory/memory.jsonl`.
- `learning/`: seleção, coleta, revisão, versões de dataset, avaliação e modelos.
- `models/production`, `models/candidates`, `models/archive`: versões de pesos sem exclusão automática.
- `data/postgres.py`: camada PostgreSQL oficial; SQLite só é fallback offline sem `.env` PostgreSQL.

## Instalação no Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

As classes e IDs do dataset atual são: `0 carro`, `1 moto`, `2 onibus`, `3 caminhao`, `4 pessoa`, `5 placa`.

## Detecção e demonstração

Treine uma primeira vez para produzir `runs/transito/weights/best.pt`:

```powershell
python scripts/treinar.py
python scripts/detectar_webcam.py
python scripts/detectar_video.py --source video.mp4
python scripts/detectar_maquete.py
```

A tela mostra modelo, estado do agente, objetos, IDs, confiança, trilhas, fluxo, parados e o nível de congestionamento. Pressione `q` ou `Esc` para encerrar. Ajuste câmera, linhas, zonas e limiares em `config/config.py`.

Velocidade somente é estimada quando `CALIBRATION_DISTANCE_METERS` e `CALIBRATION_DISTANCE_PIXELS` estiverem definidos; sem eles, não há km/h. O congestionamento é marcado como **estimativa heurística**, não como medida cientificamente validada.

## Dashboard web, API e WebSocket

O dashboard mantém a câmera e o YOLO no computador local; o navegador recebe o vídeo anotado por MJPEG e as métricas por WebSocket. O vídeo mostra apenas caixas, rótulo curto e trilha — nenhuma estatística agregada é desenhada em cima da imagem; todos os números (contagens, fluxo, congestionamento) vão para o dashboard via WebSocket.

A interface é a VIA | WD (`dashboard/templates/index.html`), com suporte nativo a múltiplas câmeras, mapa configurável e registro de ocorrências. O `dashboard/static/dashboard.js` só faz o "bootstrap": registra a câmera local (`/video`) e conecta o WebSocket de IA automaticamente ao abrir a página — o restante do comportamento está no script embutido no próprio `index.html`.

Em "Adicionar câmera" (tela de Monitoramento), a opção **"Câmera do servidor (com IA)"** manda o backend abrir mais um dispositivo de vídeo conectado a este PC (índice 0, 1, 2… igual ao `--camera` do terminal) e rodar YOLO + ByteTrack nele de verdade — cada câmera adicionada assim tem seu próprio processo de detecção, aparece com "IA agora" (verde) no card assim que os primeiros dados chegam, e some da lista de câmeras do backend quando removida. As demais opções do modal (webcam do navegador, HLS, MJPEG externo, WHEP, RTSP) só conectam vídeo — úteis para mostrar uma fonte externa na tela, mas **sem detecção**, e por isso ficam marcadas "sem IA" e nunca mostram "IA agora". `GET /api/cameras`, `POST /api/cameras` e `DELETE /api/cameras/<id>` são as rotas por trás dessa função.

Após instalar as dependências, inicie:

```powershell
python scripts/dashboard.py
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000). Para acessar a partir de outro PC/monitor na mesma rede Wi-Fi (uso recomendado para apresentações com múltiplas telas), use:

```powershell
python scripts/dashboard.py --host 0.0.0.0
```

Então acesse `http://IP-DO-COMPUTADOR:5000` no outro dispositivo (o `INICIAR_DASHBOARD.bat` já sobe com `--host 0.0.0.0` e imprime os IPs disponíveis). O dashboard serve a interface em `GET /`, o vídeo anotado em `GET /video` (MJPEG) e consome o WebSocket local `ws://HOST:5000/ws/status`, que transmite uma atualização por segundo no contrato `{"type":"traffic_update","cameraId":...,"data":{...}}` que o front já espera. A página reconecta automaticamente e consulta estas APIs locais, sem duplicar YOLO ou ByteTrack no navegador:

- `GET /api/status`: métricas atuais, status real da câmera e modelo carregado.
- `GET /api/events`: eventos recentes persistidos em `logs/events.jsonl`.
- `GET /api/learning`: estado do aprendizado controlado e contagens das filas de revisão.
- `GET /api/models`: pesos de produção, candidatos e histórico de decisões.

Como navegador e Flask usam a mesma origem, CORS não é necessário. Pressione `Ctrl+C` no terminal para parar o servidor. O dashboard não expõe os arquivos do projeto nem o `.env`.

## Contas, organizações e planos (multi-cliente)

Com `DATABASE_BACKEND=postgres` o VIA funciona como app para vários clientes: cada cliente é uma **organização** com plano, usuários e dados próprios. Sem PostgreSQL continua o modo local antigo (senha única opcional, sem limites).

- **Acesso:** login por e-mail e senha. Papéis: `via_admin` (equipe VIA), `owner` (responsável do cliente, gerencia usuários) e `member`. Trocar a senha encerra as outras sessões.
- **Isolamento:** todo dado (eventos, detecções, câmeras, relatórios, assistente, mapa) é filtrado pela organização da sessão, nunca por parâmetro vindo do navegador. Eventos anteriores ao multi-cliente passam à organização interna "VIA (interno)".
- **Planos** em `config/plans.py` (Report, Insight, Intelligence, Business): máximo de usuários e câmeras, relatórios PDF e consultas ao assistente por mês, e recursos liberados. **Os números são valores iniciais de trabalho**; ajuste nesse arquivo. Não há cobrança automática: a VIA cria a organização depois do orçamento fechado.
- **Câmeras de clientes:** só por URL de rede pública (`rtsp://`, `http(s)://`). Índice de dispositivo, arquivo do servidor e endereços internos são exclusivos da equipe VIA.
- **Configurações** (menu da conta, canto superior direito): Perfil (nome, foto, município do mapa), Segurança, Plano e uso, Equipe, Câmeras, Ajuda e privacidade e, para a equipe VIA, Administração.
- **Foto de perfil:** JPG/PNG/WebP até 3 MB, reprocessada no servidor (recorte quadrado, 256 px, JPEG, sem metadados). Fica em `data/avatars/` (ou `VIA_AVATAR_DIR`).

Primeiro uso:

```powershell
python scripts/gerenciar_contas.py criar-admin --email voce@via.com --senha "minimo8caracteres"
python scripts/gerenciar_contas.py criar-org --nome "Prefeitura de Tubarão" --plano intelligence --email gestor@exemplo.gov.br --senha "minimo8caracteres"
python scripts/gerenciar_contas.py listar
```

Variáveis de ambiente úteis (`.env`): `FLASK_SECRET_KEY` (sessões sobrevivem a reinícios), `VIA_HTTPS=1` (cookie de sessão só em HTTPS, obrigatório em produção), `VIA_AVATAR_DIR`.

**Segurança aplicada:** sessões versionadas, limite de tentativas de login e de troca de senha, checagem de origem em requisições que alteram dados, cabeçalhos de segurança, URLs de câmera validadas contra redes internas, e APIs que só devolvem o que a tela usa. Atrás de um proxy reverso, configure o encaminhamento de host/IP para a checagem de origem funcionar. Não há Content-Security-Policy ainda (o painel usa scripts inline).

## Estatísticas, relatórios e mapa

- **Estatísticas** mostra o resumo (total e tipos por 24 h, 7 dias ou 30 dias, em janelas corridas até agora) e as contagens ao vivo. Fluxo total, pico de movimento e hora mais movimentada aparecem de verdade (um "gostinho"; são os únicos números enviados). O resto da análise aparece **desfocado e travado**: ao clicar, "Baixe o relatório para ter acesso". O desfoque é feito sobre formas genéricas, não sobre os números: os dados detalhados não são enviados ao navegador.
- **Relatórios** serve só para gerar e exportar o PDF (período, horário e câmera), com contagem no limite mensal do plano. O PDF e os números só consideram o que foi registrado: horários sem leitura não entram nas contas.
- **Assistente VIA** com histórico de conversas (lista ao lado, nova conversa, renomear, excluir). Com contas, as conversas ficam no banco e são **privadas de cada usuário** (nem o responsável da organização nem a equipe VIA leem as de outro usuário). Perguntas de acompanhamento herdam período, horário e câmera da pergunta anterior ("e as ocorrências?"). Cada pergunta consome 1 do limite mensal do plano. No desktop a aba VIA ocupa a página inteira e o popup da bolinha é arrastável; em celular e tablet a bolinha leva à aba.
- **Primeiro acesso:** o login é só e-mail e senha. Na primeira entrada o usuário escolhe estado e município uma única vez; depois vai direto ao painel (pode trocar em Configurações).
- **Mapa operacional** (Leaflet + OpenStreetMap) abre no município escolhido (estado, depois município; no login ou em Configurações), com o contorno oficial do IBGE. Mostra **somente câmeras já cadastradas em Câmeras**: o endereço digitado no cadastro é localizado e a câmera já aparece lá. A posição não depende do computador de quem monitora. O alfinete do mapa volta ao município.

Serviços externos usados pelo mapa: IBGE (estados, municípios e contornos; cache em `data/geo_cache/`), OpenStreetMap (blocos do mapa) e Nominatim (busca de endereço, no máximo 1 requisição por segundo, identificada). Leaflet vem do unpkg com verificação de integridade. O uso gratuito dos blocos do OpenStreetMap é para volume baixo: em produção com muitos clientes, contrate um provedor de mapas (MapTiler, Stadia etc.) e troque a URL em `dashboard/static/via-map.js`.

## Aprendizado contínuo controlado

Com `LEARNING_ENABLED=True`, baixa ou média confiança pode gerar um frame em `data/learning_queue/pending/`, acompanhado de JSON com a previsão. O `LearningSampler` limita a frequência por classe para não salvar sequências quase idênticas. Eventos e memória sobrevivem ao encerramento.

Revise os casos, fornecendo caixa YOLO confirmada para um caso aprovado:

```powershell
python scripts/revisar_casos.py
python scripts/criar_dataset.py
```

Confirmados vão para `approved`; rejeitados para `rejected`; incompletos ou duvidosos para `uncertain`. `criar_dataset.py` cria `data/dataset_v001`, `dataset_v002` etc., mantendo intocado o dataset original e gravando `manifest.json`.

Treine, avalie e promova explicitamente:

```powershell
python scripts/treinar_candidato.py --data data/dataset_v001/data.yaml --version v002
python scripts/avaliar_modelo.py --candidate models/candidates/candidate_v002.pt
python scripts/promover_modelo.py --candidate models/candidates/candidate_v002.pt --report logs/evaluation_candidate_v002.json --version v002
python scripts/rollback_modelo.py --model models/archive/v001.pt --version v001
```

O avaliador compara precision, recall, mAP50 e mAP50-95. A promoção só acontece se o relatório contiver a melhoria mínima configurada (`MIN_MODEL_IMPROVEMENT`); caso contrário, o candidato é arquivado como rejeitado. As decisões e métricas são registradas em `models/history.jsonl` e os pesos anteriores são preservados em `models/archive`.

## PostgreSQL e DBeaver

O PostgreSQL é o banco oficial quando `DATABASE_BACKEND=postgres`. O DBeaver somente administra e visualiza esse mesmo banco; YOLO, ByteTrack e o agente continuam executando no Python/VS Code. Imagens e labels não são enviados ao banco: apenas seus caminhos, hash e metadados são registrados.

Crie o banco uma única vez no PostgreSQL:

```sql
CREATE DATABASE transito_ia;
```

Copie `.env.example` para `.env` e preencha a senha local. Nunca versione esse arquivo. Depois:

```powershell
python scripts/testar_banco.py
python scripts/inicializar_banco.py
python scripts/consultar_banco.py --events 30
```

`inicializar_banco.py` cria as tabelas de câmeras, classes, amostras/anotações, detecções, tracks, eventos, memória, datasets, modelos, métricas e contexto externo. As quatro classes são carregadas diretamente de `data/data.yaml`.

No DBeaver, crie uma conexão PostgreSQL com host, porta, banco, usuário e senha idênticos aos do `.env`; então abra `transito_ia` e o schema `public`.

### Importar imagens de treinamento

Coloque pares com o mesmo nome em `data/training/images/` e `data/training/labels/`, por exemplo `imagem001.jpg` e `imagem001.txt`. Valide antes de importar:

```powershell
python scripts/validar_labels.py
python scripts/importar_dataset.py
```

O importador valida YOLO, calcula o SHA-256 de cada imagem, evita duplicação no PostgreSQL e grava o relatório em `logs/dataset_import_report.json`. Labels inválidos não são apagados.

## Limites atuais e próximos passos

O núcleo é offline e não depende de Waze, GPU nem API de LLM. Waze deve ser acrescentado apenas como contexto externo, nunca como substituto da visão. A revisão é por terminal e o usuário fornece a caixa YOLO confirmada; dashboard web e rotulagem gráfica são próximos incrementos. Os limiares, zonas, velocidade e congestionamento precisam ser calibrados na câmera e maquete reais.

## Testes

```powershell
python -m unittest discover -s tests -v
```
