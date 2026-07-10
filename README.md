# Aria Streamer — Gen 2 Live Dashboard

Dashboard locale PySide6 per demo con Meta Project Aria Gen 2: camera con gaze
overlay, eye tracking (blink/PERCLOS), BPM da PPG, hand tracking, esperimenti
di visione (oggetto guardato, gesti) — senza `aria_streaming_viewer` e senza
Rerun.

L'interfaccia è una dashboard scura professionale:

- **header** con badge modalità (USB / WI-FI / MOCK), pill di stato
  (DISCONNECTED → CONNECTING → CONNECTED → STREAMING, con stati degradati
  `STREAMING · NO CONTROL` e `STREAMING · NO DATA`), chip batteria / rete
  Wi-Fi / temperatura del device e pulsanti Start/Stop;
- **pannello video hero** con overlay gaze, bounding box esperimenti, chip
  LIVE / STALE / WAITING e fps correnti;
- **colonna metriche**: Heart Rate (BPM, qualità segnale, variabilità, trend
  60 s), Eye Tracking (direzione, yaw/pitch, profondità, blink rate, PERCLOS,
  pupille), Hand Tracking (skeleton L/R con confidenza), card esperimenti;
- **status bar** diagnostica: seriale device, profilo, interfaccia di
  streaming, batch ms, endpoint receiver, stato RX e versione SDK, più
  l'ultimo messaggio di log.

## Politica dati reali

In modalità reale (USB o Wi-Fi) la dashboard mostra **solo** dati ricevuti
dagli occhiali o metriche calcolate da quei dati (blink rate e PERCLOS dalla
validità del gaze, BPM dal PPG grezzo). Quando un dato non è disponibile o non
è affidabile compare `N/A`, `Waiting for real data...` o l'equivalente — mai
valori inventati. In particolare:

- **BPM**: resta `--` finché il PPG reale non produce una stima stabile; la
  card riporta il motivo (`Not enough PPG data`, qualità POOR, ...).
- **Pupille**: la callback EyeGaze live dell'SDK Gen 2 (verificato su
  `projectaria-client-sdk` 2.4.0) non espone il diametro pupillare → la riga
  resta `N/A · not in live SDK`.
- **ALS**: nessuna callback nel receiver di questa build → non mostrato.
- **Batteria/temperatura**: sono letture live; se il canale di controllo cade
  (cavo USB scollegato) spariscono invece di congelarsi sull'ultimo valore.
- **Gaze overlay**: disegnato solo quando `combined_gaze_valid` non è False.
- I dati sintetici esistono **solo** in `--mock` (worker separato in `mock/`).

## Installazione

`projectaria-client-sdk` pubblica wheel solo per **Linux x86_64 e macOS Apple
Silicon (Python 3.10–3.12)**: la modalità reale richiede una di queste
piattaforme. Su Windows funzionano modalità mock e test.

```bash
python3 -m venv ~/projectaria_gen2_python_env
source ~/projectaria_gen2_python_env/bin/activate
cd <repo>/Aria_Streemer
pip install -r requirements.txt
```

Verifica del device e pairing:

```bash
aria_doctor
aria_gen2 device list
aria_gen2 auth check          # se serve: aria_gen2 auth pair
```

API Gen 2 usate (verificate contro l'SDK 2.4.0 installato, vedi
`tests/test_sdk_contract.py`):

- `aria.sdk_gen2.DeviceClient` / `DeviceTarget` / `HttpStreamingConfig`
  (incl. `streaming_interface`, `batch_period_ms`,
  `keep_streaming_on_disconnection`, `advanced_config.endpoint.url`)
- `aria.stream_receiver.StreamReceiver` + callback tipizzate
  (`register_rgb_callback`, `register_slam_callback`, `register_et_callback`,
  `register_eye_gaze_callback`, `register_hand_pose_callback`,
  `register_ppg_callback`, `register_barometer_callback`)
- `AriaGen2HttpServer.connections()` per rilevare lato receiver se gli
  occhiali stanno effettivamente pubblicando (usato per lo stato RX e per il
  flusso "scollega il cavo").

## Modalità USB (consigliata per stabilità)

```bash
python app.py --usb
```

Interfaccia `USB_NCM`, batch 20 ms (default storico, invariato).

## Modalità Wi-Fi

Prerequisito: occhiali connessi a una rete Wi-Fi raggiungibile dal PC
(`aria_gen2 device wifi connect --ssid <SSID> --password <password>`), oppure
stessa rete del PC.

### Flusso ufficiale: parti via USB, poi scollega il cavo

È il flusso raccomandato dalla documentazione Aria Gen 2 e quello che l'app
implementa:

```bash
# cavo USB collegato
python app.py --wifi
# premi "Start Streaming", verifica il pill STREAMING, poi scollega il cavo
```

Cosa fa l'app in `--wifi`:

1. apre il canale di controllo (via IP se `--device-ip`/`ARIA_DEVICE_IP` è
   impostato, altrimenti via USB come da flusso ufficiale);
2. verifica che gli occhiali siano connessi a una rete Wi-Fi (altrimenti
   errore chiaro con il comando CLI da eseguire);
3. configura `StreamingInterface.WIFI_STA` con `batch_period_ms = 200`
   (raccomandazione ufficiale per il wireless; override con
   `--stream-batch-ms`) e `keep_streaming_on_disconnection = True`, così lo
   stream sopravvive allo scollegamento del cavo e ai drop transitori;
4. imposta come endpoint del receiver l'IP dell'interfaccia host che instrada
   verso l'IP Wi-Fi degli occhiali (es. `https://192.168.1.10:6768`), evitando
   il default mDNS `oatmeal_server.local` che su molte reti è bloccato o può
   risolversi sull'indirizzo USB che muore con il cavo; override manuale con
   `--wifi-endpoint https://<ip-host>:6768`;
5. avvia il receiver e lo streaming; se il device sta già streammando (es.
   avviato da CLI) l'app si aggancia alla sessione esistente senza riavviarla.

Dopo lo scollegamento del cavo:

- il monitor rileva la perdita del canale di controllo (3 status falliti) e
  mostra `STREAMING · NO CONTROL`; i dati continuano ad arrivare dal receiver
  e lo stato RX in status bar conferma che gli occhiali pubblicano ancora;
- l'app ritenta la riconnessione del controllo ogni ~6 s (via IP Wi-Fi noto o
  USB quando ricolleghi il cavo); al ripristino compare `Control channel
  restored`;
- **Stop** ferma sempre il receiver locale; se il device non è raggiungibile
  avvisa di ricollegare il cavo o usare `aria_gen2 streaming stop`.

### Controllo direttamente via Wi-Fi (senza cavo)

```bash
python app.py --wifi --device-ip 192.168.1.42
# oppure: ARIA_DEVICE_IP=192.168.1.42 python app.py --wifi
```

L'IP degli occhiali è in `aria_gen2 device status` (campo `wifi_ip_address`).

### Parametri utili

```bash
python app.py --rgb-fps 10 --ht-fps 10 --et-fps 5 --hr-update-hz 1
python app.py --rgb-width 960 --rgb-height 540
python app.py --stream-batch-ms 200       # default: 20 USB, 200 Wi-Fi
python app.py --wifi-endpoint https://192.168.1.10:6768
python app.py --output-dir ./recordings
python app.py --debug-streams
python app.py --debug-image-dump /tmp/aria_gui_debug
```

## Modalità mock (senza occhiali, anche su Windows)

```bash
python app.py --mock
```

Genera RGB, ET, gaze, pupille, blink/PERCLOS, PPG/BPM e mani sintetici,
etichettati come mock nell'interfaccia.

## Esperimenti (oggetto guardato / gesti)

Invariati: card dedicate nella colonna destra, configurazione in
`config/experiment_config.yaml`, log CSV in `--output-dir`, YOLO-World
(`ultralytics`) per gli oggetti e HaGRID per i gesti; TTS via
`speech_announcer`. Il fallback al centro immagine quando il gaze manca vale
solo per la selezione dell'oggetto (ROI), non per l'overlay.

## Log diagnostici

All'avvio dello streaming l'app logga: riepilogo config (interfaccia, profilo,
batch, certificato, `keep_streaming_on_disconnection`, endpoint), stato Wi-Fi
del device (SSID/IP), bind del receiver, `get_streaming_info()` e — dal
monitor — transizioni del canale di controllo e connessioni/disconnessioni del
device al receiver (`server.connections()`). Con `--debug-streams` il livello
sale a DEBUG.

## Test

```bash
QT_QPA_PLATFORM=offscreen pytest -q          # 43 test
QT_QPA_PLATFORM=offscreen python tools/smoke_test_gui.py
```

- `tests/test_stream_worker_wifi.py`: flusso Wi-Fi completo su SDK finto
  (WIFI_STA + batch 200 + keep flag + endpoint, USB invariato, aggancio a
  stream esistente, stop con device irraggiungibile, perdita/recupero
  controllo, stato publishing dal receiver).
- `tests/test_sdk_contract.py`: gira solo dove l'SDK reale è installato e
  verifica che l'API usata esista davvero in quella build (incl. l'assenza del
  diametro pupillare in EyeGaze).
- `tests/test_no_fake_data.py`: N/A e waiting states in assenza di dati reali;
  batteria nascosta a canale di controllo perso.
- Test GUI offscreen su widget video/qimage e smoke test completo mock.

Debug del flusso immagini reale:

```bash
python tools/debug_image_stream.py --usb --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
ARIA_DEVICE_IP=<ip> python tools/debug_image_stream.py --wifi --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
```

## Performance

- buffer thread-safe `LatestValueBuffer` (un campione utile per stream) con
  età del dato usata dalla UI per gli stati LIVE/STALE;
- queue SDK a 1 dove supportato; RGB max 960x540 @10 fps; ET 5 fps; HT 10 fps;
  BPM 1 Hz; UI refresh 30 Hz;
- niente `QGraphicsDropShadowEffect` sui pannelli (jank in resize durante lo
  streaming);
- default demo: preview SLAM frontale in scala di grigi a bassa latenza;
  `--decode-rgb` abilita l'RGB H265 a colori (più latenza su Linux).

## Limitazioni note

- Decoder Python RGB H265 su Linux: possibili messaggi `PPS id out of range` /
  `bad optional access` e latenza extra (per questo il default è la SLAM).
- Pupille e ALS non esposti dalle callback live di questa build SDK → `N/A`.
- La proiezione del gaze usa la calibrazione reale quando il receiver la
  fornisce (`register_device_calib_callback`), altrimenti un fallback
  geometrico yaw/pitch calcolato dai dati reali.
- `keep_streaming_on_disconnection` mantiene lo stream attivo dopo lo
  scollegamento: ricordarsi di premere Stop (o `aria_gen2 streaming stop`) a
  fine demo per non lasciare gli occhiali a trasmettere.

## Troubleshooting

Wi-Fi non parte / nessun dato:

1. `aria_gen2 device status` → `wifi_connected: true` e `wifi_ip_address`
   valorizzato; altrimenti `aria_gen2 device wifi connect --ssid ... --password ...`
2. PC e occhiali sulla stessa rete; firewall che permetta la porta 6768 in
   ingresso.
3. Se l'endpoint automatico non va (reti multi-interfaccia):
   `--wifi-endpoint https://<ip-del-pc>:6768`.
4. Certificati: `aria_gen2 streaming stop && aria_gen2 streaming install-certs`;
   in caso di stato incerto rieseguire `aria_gen2 streaming stop` e provare il
   sample ufficiale `device_streaming.py --interface wifi_sta`.
5. Stream rimasto attivo sul device: `aria_gen2 streaming stop`.

Pannello video giallo/piatto o senza frame:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_mock_rgb_frame.py tests/test_qimage_conversion.py tests/test_video_widget_offscreen.py
QT_QPA_PLATFORM=offscreen python tools/smoke_test_gui.py
python tools/debug_image_stream.py --usb --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
```

Device non trovato: `aria_gen2 device list`, `aria_gen2 auth check`,
`aria_doctor`; per USB verificare cavo/USB networking; una registrazione
attiva sul device va fermata prima dello streaming.
