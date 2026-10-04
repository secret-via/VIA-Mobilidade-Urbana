/* Liga o front VIA | WD (script embutido em index.html) ao backend:
   registra a câmera MJPEG servida em /video (só quando a conta tem câmera
   local, ex. a organização interna) e conecta o WebSocket de IA em
   /ws/status automaticamente. O restante da interface (mapa, múltiplas
   câmeras, alertas, relatórios) já é tratado pelo script original. */
(() => {
  const LOCAL_CAMERA_ID = 'cam_local';

  function ensureLocalCamera() {
    if (!CameraStore.get(LOCAL_CAMERA_ID)) {
      CameraStore.add({
        id: LOCAL_CAMERA_ID,
        name: 'Câmera local',
        location: 'Conectada ao servidor do dashboard',
        protocol: 'mjpeg',
        url: '/video',
        deviceId: '',
        status: 'idle',
        cleanup: null,
        media: null,
        connectedAt: null,
        error: null,
      });
    }
    connectCamera(LOCAL_CAMERA_ID);
  }

  function connectBackendAi() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    // Endereço fixo e interno: o usuário não configura nem vê a conexão.
    connectAI(`${scheme}://${location.host}/ws/status`);
  }

  // Clientes de uma organização não têm a câmera do servidor: sem este teste
  // o front tentaria abrir /video e mostraria uma câmera "com erro".
  fetch('/api/me', { cache: 'no-store' })
    .then((response) => (response.ok ? response.json() : { has_local_camera: true }))
    .catch(() => ({ has_local_camera: true }))
    .then((me) => {
      if (me.has_local_camera) ensureLocalCamera();
      connectBackendAi();
    });
})();
