"""Ajuste estes valores para a câmera e a maquete reais."""
from datetime import timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

# Horário de Brasília fixo (UTC-3). O Brasil não usa mais horário de verão
# desde 2019, então um offset fixo é correto o ano todo e não depende do
# fuso configurado no sistema operacional onde o servidor roda (diferente de
# datetime.astimezone() sem argumento, que usa o fuso local da máquina e
# pode estar errado/ambíguo dependendo de como o Windows está configurado).
BR_TIMEZONE = timezone(timedelta(hours=-3), name="America/Sao_Paulo")
PRODUCTION_DIR = ROOT_DIR / "models" / "production"
# Após promoção, a câmera usa a versão oficial; antes do primeiro ciclo preserva o peso legado.
MODEL_PATH = next(iter(sorted(PRODUCTION_DIR.glob("*.pt"))), ROOT_DIR / "runs" / "transito" / "weights" / "best.pt")
DATA_YAML = ROOT_DIR / "data" / "data.yaml"
RUNS_DIR = ROOT_DIR / "runs"

CAMERA_ID = 0
# Resolução de captura. 1280x720 é um bom equilíbrio qualidade/desempenho em CPU;
# suba para 1920x1080 se a máquina aguentar, ou baixe se o FPS cair muito.
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
# Meta pedida: 45 fps. O valor real de entrega depende da câmera e da CPU —
# o backend sempre processa o frame mais recente disponível (sem enfileirar
# atraso), então em hardware mais fraco o FPS efetivo cai sozinho em vez de
# travar a transmissão.
CAMERA_FPS = 45
ROLLING_WINDOW_SECONDS = 12  # janela usada para suavizar as contagens por classe exibidas ao vivo
CONFIDENCE = 0.35
IOU_THRESHOLD = 0.45
TRACKER = "bytetrack.yaml"
# Resolução usada internamente pelo YOLO para a inferência (independente da
# resolução de captura/exibição - o resultado é sempre reescalado de volta
# para o tamanho do frame original). Medido nesta máquina: 640 -> ~108ms/frame
# (~9 fps no máximo teórico, sem CPU dedicada/GPU); 480 -> ~73ms (~14 fps).
# Reduzir aqui é o jeito mais direto de destravar o vídeo em CPU, ao custo de
# alguma precisão para objetos pequenos/distantes (ex. placas). Se a maquete
# tiver os veículos sempre próximos da câmera, 480 costuma não perder detecção
# perceptível; suba para 640 se notar objetos pequenos sendo ignorados.
INFERENCE_IMGSZ = 480
TRAIL_LENGTH = 40
STOP_THRESHOLD = 3.0  # pixels entre observações; calibrar para a maquete
STOP_TIME = 3.0       # segundos quase imóvel antes de marcar PARADO

# Linhas e zonas de EXEMPLO. Calibre para a resolução/posição final da câmera.
COUNTING_LINES = {
    "entrada": ((100, 300), (540, 300)),
    "saida": ((100, 500), (540, 500)),
}
ZONES = {
    "ZONA 1": [(100, 100), (300, 100), (300, 280), (100, 280)],
    "ZONA 2": [(320, 100), (540, 100), (540, 280), (320, 280)],
    "ZONA 3": [(100, 320), (540, 320), (540, 600), (100, 600)],
}

# None impede converter pixel/s em km/h sem calibração física.
CALIBRATION_DISTANCE_METERS = None
CALIBRATION_DISTANCE_PIXELS = None

# Aprendizado contínuo controlado. Nenhuma previsão é usada como rótulo sem revisão humana.
LEARNING_ENABLED = True
LOW_CONFIDENCE_THRESHOLD = 0.50
INTERMEDIATE_CONFIDENCE_THRESHOLD = 0.65
MIN_LEARNING_INTERVAL = 5.0
MAX_LEARNING_CASES = 500
MODEL_AUTO_TRAIN = False
MODEL_AUTO_PROMOTE = False
MIN_MODEL_IMPROVEMENT = 0.01  # melhoria mínima de mAP50-95
MODEL_VERSION = "v001"

# Câmeras "webcam do navegador" empurram frames ao servidor via WebSocket e
# cada uma roda seu próprio YOLO (ver BrowserPushService, dashboard/app.py) -
# custo de CPU cresce direto com o número de visitantes simultâneos, por isso
# um limite é aplicado em /api/cameras/browser.
MAX_BROWSER_CAMERAS = 4
