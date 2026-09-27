# Jetts-TUI

Jetts-TUI es un espacio de trabajo de IA centrado en la terminal: incluye una TUI a pantalla completa, agentes, memoria, subagentes, tareas programadas e integraciones de mensajería. El mismo motor también está disponible en las aplicaciones de escritorio y web de este repositorio.

Esta guía breve cubre la instalación. Para la documentación completa y actualizada, consulta el [README principal](README.md) y los [documentos del repositorio](website/docs).

## Instalación

Clona o descarga [este repositorio](https://github.com/Raioshok/JETTS-TUI) y ejecuta el script local correspondiente. No uses un instalador alojado en el dominio de otro proyecto.

En Linux, macOS o WSL2:

```bash
bash setup-jetts-tui.sh
```

En Windows PowerShell:

```powershell
.\setup-jetts-tui.ps1
```

Si PowerShell bloquea los scripts locales, ejecuta solo este proceso con una política temporal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-jetts-tui.ps1
```

Los scripts reutilizan el entorno existente cuando vuelves a ejecutarlos. Usa `--skip-setup` en Linux/macOS o `-SkipSetup` en Windows si quieres configurar el proveedor más tarde.

## Primer uso

```bash
jetts-tui          # Abrir la interfaz de terminal
jetts-tui setup    # Configurar proveedores y herramientas
jetts-tui model    # Elegir proveedor y modelo
jetts-tui doctor   # Diagnosticar problemas
```

Las integraciones existentes con proveedores y servicios alojados siguen estando disponibles; el cambio de marca no redirige esas conexiones. Los nombres técnicos antiguos, como `FREEIDE_HOME` y `~/.freeide`, se conservan para que las instalaciones existentes sigan funcionando.

## Contribuir y licencia

Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para el entorno de desarrollo y [LICENSE](LICENSE) para la licencia MIT y las atribuciones originales.
