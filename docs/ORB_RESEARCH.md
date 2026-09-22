# Orb research

We reviewed current open source desktop assistants for a reusable interaction pattern rather than copying their application logic.

* **NovaAI**: Electron based voice assistant with a small glowing always on top orb, voice interaction and tool execution. citeturn0search0
* **Yumii**: Windows first local voice companion with a draggable floating orb, persistent memory and permission gated tools. citeturn0search1
* **Atlas**: Electron computer use agent with an orb that communicates idle, thinking, acting and waiting states, plus visible task progress. citeturn0search10
* **VOCA**: Tauri based local first floating orb with a transparent draggable window and local Whisper. citeturn0search8

Brainbox will use the useful visual ideas while keeping the implementation separate: the orb is a presentation layer and the Python harness remains the authority for model calls and OS actions.
