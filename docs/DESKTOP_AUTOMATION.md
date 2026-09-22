# Desktop automation

Brainbox OS is intended to operate the user's PC, not only remote services.

The first desktop capability is `open_application`. On Windows it searches registered Start Menu applications, opens an exact match when available, and otherwise falls back to a shell target such as an executable, path or URL. Windows PowerShell's `Start-Process` supports launching local executables and files associated with installed applications. citeturn0search5turn0search6

Needle 3 is responsible for selecting the tool and extracting its arguments. Its documented contract is structured function calls with arguments matching the declared schema. citeturn0search0turn0search1

Example voice turns:

* “Open Chrome.”
* “Open Discord.”
* “Open VS Code.”
* “Open this file in Excel.”
* “Open the Brainbox OS folder.”

The desktop tool is deliberately a harness capability rather than something Needle can execute by itself. This keeps the model from receiving operating system privileges directly. The harness can later add confirmation rules, foreground window checks, process verification and an audit event for every desktop action.

Future desktop tools should cover:

1. Open and close applications
2. Focus a window
3. Read the active window
4. Click and type through an approved UI automation layer
5. Clipboard operations
6. File operations
7. Screenshots and visual grounding
8. Browser control
9. Keyboard shortcuts
10. Process inspection

Destructive or externally consequential actions must remain behind the Brainbox policy layer.
