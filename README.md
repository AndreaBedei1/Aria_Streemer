# Aria Gen 2 Realtime Demo Dashboard

Dashboard locale PySide6 per demo pubbliche con Meta Project Aria Gen 2.

Obiettivo: mostrare in realtime camera RGB, gaze, blink/PERCLOS, pupille se disponibili,
PPG/BPM, qualita PPG, pulse variability, hand tracking, ALS/temperatura e performance,
senza usare `aria_streaming_viewer` e senza usare Rerun come viewer principale.

La app lavora in due modi:

- Preview Mode: default, mostra solo dati realtime e non salva dati.
- Recording Mode: parte solo con `Start Recording`, usa la registrazione device-side
  del Client SDK quando disponibile e salva localmente solo un CSV leggero di stime/metadati.

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
```

## Avvio in modalita mock

```bash
source ~/projectaria_gen2_python_env/bin/activate
python app.py --mock
```

La modalita mock genera dati finti ma realistici per RGB, ET cameras, gaze,
pupille, blink/PERCLOS, PPG/BPM, qualita PPG, pulse variability e mani.

## Registrazione

La dashboard non registra in Preview Mode.

Con `Start Recording`:

- crea un nome sessione automatico `aria_demo_YYYYMMDD_HHMMSS`;
- chiama `device.set_recording_config(...)`;
- chiama `device.start_recording()`;
- crea un CSV leggero in output;
- mostra `REC` e timer.

Con `Stop Recording`:

- chiama `device.stop_recording()`;
- chiude il CSV locale.

Il CSV locale non contiene video. Contiene solo timestamp, BPM stimato, qualita
PPG, gaze, blink/PERCLOS, pupille se disponibili, stato mani, FPS e stato UI.

Nota: la VRS device-side rimane sul dispositivo. Scaricarla durante una demo puo
essere pesante; usare la CLI ufficiale dopo la sessione:

```bash
aria_gen2 recording list
aria_gen2 recording download -u <uuid> -o ./recordings
```

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

## Limitazioni note

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
```
