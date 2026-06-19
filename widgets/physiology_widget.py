from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from stream_state import AmbientLightSample, TemperatureSample


class PhysiologyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.title = QLabel("Context")
        self.title.setObjectName("panelTitle")
        self.light = QLabel("ALS: not available")
        self.temperature = QLabel("Device temp: not available")
        self.note = QLabel("Temperature is device/sensor metadata")
        self.note.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.light)
        layout.addWidget(self.temperature)
        layout.addWidget(self.note)

    def update_sample(
        self,
        light: AmbientLightSample | None,
        temperature: TemperatureSample | None,
    ) -> None:
        if light is None or light.lux is None:
            message = "ALS: not available"
            if light is not None and light.message:
                message = f"ALS: {light.state}"
            self.light.setText(message)
        else:
            self.light.setText(f"ALS: {light.lux:.0f} lux | {light.state}")

        if temperature is None or temperature.temperature_c is None:
            self.temperature.setText("Device temp: not available")
        else:
            prefix = "WARNING " if temperature.warning else ""
            self.temperature.setText(
                f"{prefix}Device temp: {temperature.temperature_c:.1f} C ({temperature.sensor_name})"
            )
