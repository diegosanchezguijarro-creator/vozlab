"""Tiny i18n layer (English / Spanish). Follows Windows locale by default."""

import locale

STRINGS = {
    "en": {
        "app_name": "VozLab",
        "tray_tooltip": "VozLab — hold {key} and speak",
        "menu_dictate": "Dictate (toggle)",
        "menu_settings": "Settings…",
        "menu_calibrate": "Change dictation key…",
        "menu_folder": "Open settings folder",
        "menu_about": "About VozLab",
        "menu_quit": "Quit",
        "state_listening": "Listening…",
        "state_transcribing": "Transcribing…",
        "state_done": "Done",
        "state_error": "Error",
        "state_offline": "Server offline",
        "wizard_title": "VozLab setup",
        "wizard_welcome": "Welcome! Two quick steps and you're ready to dictate.",
        "wizard_server_hint": "Server URL (your VozLab server, e.g. http://192.168.0.23:8092)",
        "wizard_token_hint": "Access token (printed by the server on first start)",
        "wizard_test": "Test connection",
        "wizard_test_ok": "Connected! Model: {model} on {device}",
        "wizard_test_fail": "Could not connect: {error}",
        "wizard_hotkey_hint": "Press the key you want to use for dictation (e.g. right Ctrl).",
        "wizard_hotkey_captured": "Key captured: {name}",
        "wizard_mic_test": "Record 3 seconds and transcribe",
        "wizard_mic_working": "Recording 3 seconds…",
        "wizard_mic_result": "Heard: {text}",
        "wizard_next": "Next",
        "wizard_back": "Back",
        "wizard_finish": "Finish",
        "wizard_press_key": "Press a key…",
        "settings_title": "VozLab settings",
        "settings_server": "Server URL",
        "settings_token": "Token",
        "settings_hotkey": "Dictation key",
        "settings_hotkey_change": "Change…",
        "settings_mode": "Dictation mode",
        "settings_mode_hold": "Hold to talk",
        "settings_mode_toggle": "Press to start / stop",
        "settings_auto_stop": "Stop automatically when I stop speaking",
        "settings_cleanup": "Format text with the local AI (remove filler words, punctuation)",
        "settings_language": "Dictation language",
        "settings_language_auto": "Detect automatically",
        "settings_ui_language": "Interface language",
        "settings_beeps": "Sound feedback",
        "settings_clipboard": "Restore clipboard after pasting",
        "settings_pill": "Show floating status pill",
        "settings_startup": "Start with Windows",
        "settings_debug": "Debug logging",
        "settings_save": "Save",
        "settings_cancel": "Cancel",
        "settings_saved": "Settings saved",
        "settings_test": "Test connection",
        "err_server_unreachable": "Cannot reach the server — is it running and on the same network?",
        "err_bad_token": "The token was rejected. Copy the token from the server logs.",
        "err_empty_transcript": "Nothing was recognized — check your microphone.",
        "err_mic": "Could not open the microphone: {error}",
        "err_too_short": "Recording too short — ignored",
        "err_generic": "Error: {error}",
        "paste_done": "Text pasted",
    },
    "es": {
        "app_name": "VozLab",
        "tray_tooltip": "VozLab — mantén {key} y habla",
        "menu_dictate": "Dictar (alternar)",
        "menu_settings": "Ajustes…",
        "menu_calibrate": "Cambiar tecla de dictado…",
        "menu_folder": "Abrir carpeta de ajustes",
        "menu_about": "Acerca de VozLab",
        "menu_quit": "Salir",
        "state_listening": "Escuchando…",
        "state_transcribing": "Transcribiendo…",
        "state_done": "Listo",
        "state_error": "Error",
        "state_offline": "Servidor desconectado",
        "wizard_title": "Configuración de VozLab",
        "wizard_welcome": "¡Bienvenido! Dos pasos rápidos y ya puedes dictar.",
        "wizard_server_hint": "URL del servidor (tu servidor VozLab, p. ej. http://192.168.0.23:8092)",
        "wizard_token_hint": "Token de acceso (el servidor lo muestra al arrancar)",
        "wizard_test": "Probar conexión",
        "wizard_test_ok": "¡Conectado! Modelo: {model} en {device}",
        "wizard_test_fail": "No se pudo conectar: {error}",
        "wizard_hotkey_hint": "Pulsa la tecla que quieras usar para dictar (p. ej. Ctrl derecho).",
        "wizard_hotkey_captured": "Tecla capturada: {name}",
        "wizard_mic_test": "Grabar 3 segundos y transcribir",
        "wizard_mic_working": "Grabando 3 segundos…",
        "wizard_mic_result": "Se escuchó: {text}",
        "wizard_next": "Siguiente",
        "wizard_back": "Atrás",
        "wizard_finish": "Terminar",
        "wizard_press_key": "Pulsa una tecla…",
        "settings_title": "Ajustes de VozLab",
        "settings_server": "URL del servidor",
        "settings_token": "Token",
        "settings_hotkey": "Tecla de dictado",
        "settings_hotkey_change": "Cambiar…",
        "settings_mode": "Modo de dictado",
        "settings_mode_hold": "Mantener pulsado",
        "settings_mode_toggle": "Pulsar para empezar / parar",
        "settings_auto_stop": "Parar solo cuando dejo de hablar",
        "settings_cleanup": "Formatear el texto con la IA local (quitar muletillas, puntuación)",
        "settings_language": "Idioma del dictado",
        "settings_language_auto": "Detectar automáticamente",
        "settings_ui_language": "Idioma de la interfaz",
        "settings_beeps": "Sonidos de aviso",
        "settings_clipboard": "Restaurar el portapapeles tras pegar",
        "settings_pill": "Mostrar la píldora de estado flotante",
        "settings_startup": "Iniciar con Windows",
        "settings_debug": "Registro de depuración",
        "settings_save": "Guardar",
        "settings_cancel": "Cancelar",
        "settings_saved": "Ajustes guardados",
        "settings_test": "Probar conexión",
        "err_server_unreachable": "No se alcanza el servidor — ¿está encendido y en la misma red?",
        "err_bad_token": "El token fue rechazado. Cópialo desde los registros del servidor.",
        "err_empty_transcript": "No se reconoció nada — revisa el micrófono.",
        "err_mic": "No se pudo abrir el micrófono: {error}",
        "err_too_short": "Grabación demasiado corta — ignorada",
        "err_generic": "Error: {error}",
        "paste_done": "Texto pegado",
    },
}


def detect_language() -> str:
    """Return 'es' or 'en' from the OS locale."""
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    return "es" if str(loc).lower().startswith("es") else "en"


class Translator:
    def __init__(self, ui_language: str = "auto"):
        self.language = detect_language() if ui_language in (None, "", "auto") else ui_language
        if self.language not in STRINGS:
            self.language = "en"

    def set_language(self, ui_language: str) -> None:
        self.language = detect_language() if ui_language in (None, "", "auto") else ui_language
        if self.language not in STRINGS:
            self.language = "en"

    def __call__(self, key: str, **kwargs) -> str:
        text = STRINGS.get(self.language, STRINGS["en"]).get(key) \
            or STRINGS["en"].get(key) or key
        return text.format(**kwargs) if kwargs else text
