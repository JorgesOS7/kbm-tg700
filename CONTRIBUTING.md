# Como contribuir

Obrigado pelo interesse! Issues e pull requests são bem-vindos, em português ou inglês.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `kbm_tg700/protocol.py` | Comunicação com o teclado (pacotes HID) |
| `kbm_tg700/keymap.py`, `layouts.json` | Layouts dos modelos e montagem do mapa de teclas |
| `kbm_tg700/hidinput.py` | Leitura dos relatórios de teclado (aba Testar teclas) |
| `kbm_tg700/app.py` | Interface GTK4 / libadwaita |
| `tools/` | Scripts de diagnóstico usados com o teclado real |
| `tests/` | Testes que rodam sem o teclado |
| `docs/PROTOCOL.md` | Documentação do protocolo |

## Ambiente

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
sudo cp packaging/70-kbm-tg700.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules
python3 -m kbm_tg700
```

## Antes do pull request

```bash
python3 -m unittest discover -s tests
python3 -m pyflakes kbm_tg700 tests   # se tiver o pyflakes instalado
./build-deb.sh
```

## Regras importantes

- **Não envie arquivos do software original** (executáveis, DLLs, imagens, recursos extraídos).
  Documente o que descobriu em `docs/PROTOCOL.md`, com suas próprias palavras.
- Comandos novos do protocolo devem ser testados no teclado real; diga no PR qual modelo usou.
- Gravações erradas podem bagunçar o mapa de teclas. Tenha `python3 tools/factory_reset.py` à mão.

## Relatando problemas

Inclua o modelo do teclado, a distribuição Linux, a saída de `lsusb | grep 4a4c` e, se for problema
de tecla, o que aparece na aba **Testar teclas**.
