# Aria Gen 2 Realtime Demo Dashboard

Dashboard locale PySide6 per demo pubbliche con Meta Project Aria Gen 2.

Obiettivo: mostrare in realtime camera RGB, gaze, blink/PERCLOS, pupille se disponibili,
PPG/BPM, qualita PPG, pulse variability, hand tracking, ALS/temperatura e performance,
senza usare `aria_streaming_viewer` e senza usare Rerun come viewer principale.

La app lavora in due modi:

- Preview Mode: default, mostra solo dati realtime e non salva dati.
- Experiment Mode: parte solo con `Inizia esperimento`, abilita un modello di visione artificiale YOLO-World in background per riconoscere l'oggetto guardato e salva un log CSV.

## Installazione

Usare il virtualenv Project Aria Gen 2 gia configurato:

```bash
source ~/projectaria_gen2_python_env/bin/activate
cd /home/andrea/Desktop/Aria_Streemer
pip install -r requirements.txt
```

Il pacchetto SDK ufficiale e `projectaria-client-sdk`. Questa app usa le API Gen 2:

- `aria.sdk_gen2.DeviceClient`
- `aria.sdk_gen2.DeviceTarget`
- `aria.sdk_gen2.HttpStreamingConfig`
- `aria.sdk_gen2.RecordingConfig`
- `aria.stream_receiver.StreamReceiver`
- callback ufficiali come `register_rgb_callback`, `register_et_callback`,
  `register_eye_gaze_callback`, `register_hand_pose_callback`, `register_ppg_callback`
  e `register_barometer_callback`.

## Setup SDK e sample ufficiali

Verifica il dispositivo:

```bash
source ~/projectaria_gen2_python_env/bin/activate
aria_doctor
aria_gen2 device list
aria_gen2 auth check
```

Se serve pairing:

```bash
aria_gen2 auth pair
```

Estrai i sample ufficiali:

```bash
python3 -m aria.extract_sdk_samples --output ~
ls ~/projectaria_client_sdk_samples_gen2
```

Sample usati come riferimento:

- `device_connect.py`
- `device_streaming.py`
- `device_raw_streaming.py`
- `device_record.py`

## Avvio in modalita reale

USB, consigliato per stabilita:

```bash
source ~/projectaria_gen2_python_env/bin/activate
python app.py --usb
```

WiFi STA:

```bash
source ~/projectaria_gen2_python_env/bin/activate
ARIA_DEVICE_IP=192.168.159.37 python app.py --wifi
```

Parametri utili:

```bash
python app.py --rgb-fps 10 --ht-fps 10 --et-fps 5 --hr-update-hz 1
python app.py --rgb-width 960 --rgb-height 540
python app.py --output-dir ./recordings
python app.py --debug-streams
python app.py --debug-image-dump /tmp/aria_gui_debug
python app.py --decode-rgb
```

Default demo: la preview principale usa una camera SLAM frontale in scala di
grigi a bassa latenza con gaze overlay. `--decode-rgb` abilita il flusso RGB
H265 a colori, ma puo aumentare molto il ritardo su Linux.

## Avvio in modalita mock

```bash
source ~/projectaria_gen2_python_env/bin/activate
python app.py --mock
```

La modalita mock genera dati finti ma realistici per RGB, ET cameras, gaze,
pupille, blink/PERCLOS, PPG/BPM, qualita PPG, pulse variability e mani.

## Esperimento Gaze Object Detection

L'app include una modalità sperimentale per stimare l'oggetto guardato usando un modello di Object Detection (YOLO-World) in tempo reale.

### Prerequisiti YOLO-World

Per usare YOLO-World, installare il pacchetto ultralytics (se non è già presente nel requirements.txt):
```bash
pip install ultralytics torch
```
*Se non è disponibile una GPU CUDA, l'inferenza avverrà su CPU, che potrebbe essere più lenta. Assicurarsi di mantenere bassa la frequenza di inferenza se si usa solo la CPU.*

### Come avviare l'esperimento

Dalla dashboard principale, dopo aver connesso gli occhiali e avviato lo streaming:
1. Cliccare su **Inizia esperimento** (ex tasto di registrazione).
2. L'app disabiliterà gli stream non essenziali (HR, SLAM, etc) e si concentrerà sullo stream RGB e sul Gaze Tracker.
3. Il worker in background leggerà la configurazione da `config/experiment_config.yaml` e caricherà il modello `yolov8s-worldv2.pt`.
4. Nel pannello dedicato appariranno lo stato dell'esperimento (ON/OFF), l'ultimo oggetto guardato con la relativa confidenza, e gli FPS di inferenza.
5. Cliccare su **Ferma esperimento** per arrestarlo.

### Configurazione

I parametri dell'esperimento possono essere modificati nel file `config/experiment_config.yaml`:
- **inference_interval**: Frequenza di inferenza (default 2.0 secondi)
- **crop_size**: Dimensione della ROI centrata sul gaze (default 640px)
- **max_radius_px**: Raggio di ricerca per associare le bounding box al gaze point (default 200px)
- **classes**: Lista degli oggetti open-vocabulary da riconoscere (libro, smartphone, ecc.)

### Salvataggio Log

I log dell'esperimento vengono salvati come file CSV nella directory indicata nel campo testo (default `./recordings/`). Il file è nominato `experiment_log_<timestamp>.csv` e contiene:
- `timestamp`: momento dell'evento
- `gaze_x`, `gaze_y`: coordinate dello sguardo
- `detection_label`, `confidence`: oggetto riconosciuto e confidenza
- `bbox_*`: coordinate del bounding box
- `inference_time_ms`: durata inferenza

### Gestione Gaze Assente

Se il sensore Eye Tracking fallisce nel restituire il punto di Gaze, il sistema usa automaticamente il **centro dell'immagine** come fallback sia per calcolare il crop (ROI) che per associare l'oggetto. Se nessun oggetto riconosciuto si trova vicino al punto di gaze/centro o ha scarsa confidenza, l'interfaccia mostrerà *unknown*.

## Performance

Scelte implementate:

- buffer thread-safe `LatestValueBuffer`, un solo campione utile per stream;
- queue SDK impostate a 1 dove il receiver lo consente;
- resize RGB massimo configurabile, default 960x540;
- target RGB 10 fps;
- ET cameras max 5 fps;
- hand tracking max 5-10 fps;
- BPM aggiornato a 1 Hz;
- PPG processato internamente a frequenza piena, plot solo decimato;
- UI refresh massimo 30 Hz;
- nessun video locale salvato durante Recording Mode.

## Debug video

Se serve ispezionare cosa arriva davvero dal decoder immagini, avvia la GUI con
dump limitato dei primi frame:

```bash
python app.py --usb --debug-streams --debug-image-dump /tmp/aria_gui_debug
```

Per isolare completamente la GUI dal device:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
QT_QPA_PLATFORM=offscreen python tools/smoke_test_gui.py
```

Per salvare i primi frame reali RGB/SLAM/ET con PNG e JSON:

```bash
python tools/debug_image_stream.py --usb --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
```

WiFi:

```bash
ARIA_DEVICE_IP=192.168.159.37 python tools/debug_image_stream.py --wifi --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
```

## Limitazioni note

- Su Linux il decoder Python/XPRS del vero RGB H265 puo stampare messaggi tipo
  `PPS id out of range` o `bad optional access` e introdurre ritardo. Per la demo
  la dashboard non decodifica RGB di default: mostra `Low-latency camera + gaze`
  dalla camera SLAM frontale in scala di grigi. Usare `--decode-rgb` solo se
  serve provare il colore e si accetta piu latenza.
- In questa build SDK il receiver espone callback per PPG e barometro, ma non
  espone callback tipizzate per ALS e temperatura dedicata. La app usa
  `device.status().skin_temp_celsius` e `BarometerData.temperature` per la
  temperatura dispositivo/sensore. ALS resta "not available" in reale se il
  receiver non espone il dato.
- La proiezione gaze su RGB usa una fallback stabile yaw/pitch. La funzione
  `project_gaze_to_rgb()` e pronta per collegare la calibrazione reale.
- La proiezione mano usa una fallback 2D per lo skeleton. La funzione
  `project_hand_to_camera()` e pronta per collegare la calibrazione reale.
- Le pupille live dipendono da cosa espone la callback EyeGaze SDK. Se diametro
  e centro pupilla non sono disponibili, il pannello resta visibile ma segnala
  "not available".

## Troubleshooting

Se il pannello RGB e un rettangolo giallo pieno:

1. Esegui il test immagine mock:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_mock_rgb_frame.py tests/test_qimage_conversion.py tests/test_video_widget_offscreen.py
```

2. Esegui lo smoke test GUI:

```bash
QT_QPA_PLATFORM=offscreen python tools/smoke_test_gui.py
```

3. Esegui il dump reale del flusso:

```bash
python tools/debug_image_stream.py --usb --profile mp_streaming_demo --out /tmp/aria_frame_debug --max-frames 20
```

4. Ispeziona `/tmp/aria_frame_debug/*.png` e `/tmp/aria_frame_debug/*.json`.
5. Se RGB e invalido ma SLAM e valido, usa la preview SLAM in scala di grigi
   per la demo.
6. Non abilitare hook privati o decoder monkey-patch per la demo pubblica.

Dispositivo non trovato:

```bash
aria_gen2 device list
aria_gen2 auth check
```

Se la GUI non riceve callback:

- verifica che la porta 6768 sia libera;
- disattiva VPN/firewall restrittivi;
- usa USB per prove lunghe;
- prova `aria_doctor`;
- se c'e una registrazione gia attiva sul device, fermarla puo essere necessario
  prima dello streaming.
- se compaiono errori sui certificati streaming, esegui:

```bash
aria_gen2 streaming stop
aria_gen2 streaming install-certs
```

Se `install-certs` fallisce ma lo streaming resta in stato incerto, riesegui
`aria_gen2 streaming stop` e prova il sample ufficiale:

```bash
python ~/projectaria_client_sdk_samples_gen2/device_streaming.py --profile-name mp_streaming_demo
```

Nel test su questa macchina il sample ha rigenerato/installato il certificato
persistente, dopo di che il worker della dashboard ha ricevuto callback RGB,
eye gaze, hand pose e PPG.

PySide6 mancante:

```bash
pip install PySide6
```

ADB non disponibile:

- la CLI puo ancora vedere il device tramite IP noto;
- per WiFi usare `ARIA_DEVICE_IP=<ip> python app.py --wifi`;
- per USB verificare USB networking e ADB nel setup SDK.

## Comandi richiesti

```bash
python app.py
python app.py --usb
python app.py --wifi
python app.py --mock
python app.py --rgb-fps 10
python app.py --ht-fps 10
python app.py --et-fps 10
python app.py --hr-update-hz 1
python app.py --rgb-width 960
python app.py --rgb-height 540
python app.py --output-dir ./recordings
python app.py --debug-streams
python app.py --debug-image-dump /tmp/aria_gui_debug
```
